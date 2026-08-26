"""H2 database maintenance utilities to prevent unbounded MVStore file growth."""

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterator, List, Optional, Tuple

from pygeoweaver.config import H2_VERSION
from pygeoweaver.config_utils import get_database_url_from_properties, read_properties_file
from pygeoweaver.constants import GEOWEAVER_DEFAULT_DB_PASSWORD, GEOWEAVER_DEFAULT_DB_USERNAME
from pygeoweaver.jdk_utils import download_file
from pygeoweaver.utils import get_home_dir, get_java_bin_path

logger = logging.getLogger(__name__)

DATASOURCE_URL_KEYS = (
    "spring.datasource.url",
    "database.url",
    "db.url",
    "datasource.url",
    "jdbc.url",
)

# AUTO_COMPACT_FILL_RATE=0 disables the MVStore background writer loop that can
# cause multi-terabyte file growth. Compaction is handled on graceful shutdown.
H2_SAFE_JDBC_PARAMS: Dict[str, str] = {
    "RETENTION_TIME": "0",
    "DEFRAG_ALWAYS": "TRUE",
    "AUTO_COMPACT_FILL_RATE": "0",
    "DB_CLOSE_ON_EXIT": "TRUE",
}

H2_AUTO_MAINTENANCE = os.getenv("H2_AUTO_MAINTENANCE", "true").lower() in ("1", "true", "yes")
H2_COMPACT_MIN_MB = int(os.getenv("H2_COMPACT_MIN_MB", "50"))
H2_AUTO_REBUILD_THRESHOLD_MB = int(os.getenv("H2_AUTO_REBUILD_THRESHOLD_MB", "1024"))
H2_COMPACT_INTERVAL_HOURS = int(os.getenv("H2_COMPACT_INTERVAL_HOURS", "24"))
H2_MAINTENANCE_COOLDOWN_SECONDS = int(os.getenv("H2_MAINTENANCE_COOLDOWN_SECONDS", "300"))
# Compact during optional ``gw stop --maintain-h2`` must stay short so stop cannot hang.
H2_STOP_COMPACT_TIMEOUT_SECONDS = int(os.getenv("H2_STOP_COMPACT_TIMEOUT_SECONDS", "60"))
H2_BACKUP_RETENTION_COUNT = int(os.getenv("H2_BACKUP_RETENTION_COUNT", "3"))
H2_SQL_MIN_LINES = int(os.getenv("H2_SQL_MIN_LINES", "10"))
H2_SIZE_WARN_THRESHOLD_MB = int(os.getenv("H2_SIZE_WARN_THRESHOLD_MB", "2048"))
H2_MAINTENANCE_LOCK_STALE_SECONDS = int(os.getenv("H2_MAINTENANCE_LOCK_STALE_SECONDS", "14400"))
H2_MAINTENANCE_LOCK_WAIT_START_SECONDS = int(os.getenv("H2_MAINTENANCE_LOCK_WAIT_START_SECONDS", "60"))
H2_MAINTENANCE_LOCK_WAIT_STOP_SECONDS = int(os.getenv("H2_MAINTENANCE_LOCK_WAIT_STOP_SECONDS", "10"))
H2_LOCK_RETRY_COUNT = int(os.getenv("H2_LOCK_RETRY_COUNT", "3"))
H2_LOCK_RETRY_DELAY_SECONDS = float(os.getenv("H2_LOCK_RETRY_DELAY_SECONDS", "2"))
H2_EXPORT_IMPORT_RETRY_COUNT = int(os.getenv("H2_EXPORT_IMPORT_RETRY_COUNT", "3"))
H2_EXPORT_IMPORT_TIMEOUT_SECONDS = int(os.getenv("H2_EXPORT_IMPORT_TIMEOUT_SECONDS", "7200"))
H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS = float(
    os.getenv("H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS", "5")
)
# Heartbeat is observability only — never kills the child by default (HIGH-003).
H2_TOOL_HEARTBEAT_SECONDS = int(os.getenv("H2_TOOL_HEARTBEAT_SECONDS", "60"))

# Strict tables must not lose rows across rebuild (MEDIUM-001).
H2_INVENTORY_STRICT_TABLES = ("WORKFLOW", "GWPROCESS", "HOST")
H2_INVENTORY_SOFT_TABLES = ("HISTORY", "ENVIRONMENT", "WORKFLOW_CHECKPOINT")
H2_INVENTORY_TABLES = H2_INVENTORY_STRICT_TABLES + H2_INVENTORY_SOFT_TABLES

H2_LOCK_ERROR_MARKERS = (
    "already open",
    "already in use",
    "database is already in use",
    "could not lock",
    "file is locked",
    "concurrent update",
    "another process",
)

H2_AUTH_ERROR_MARKERS = (
    "wrong user name or password",
    "invalid password",
    "authentication failure",
    "access denied",
)

H2_NONRETRYABLE_ERROR_MARKERS = (
    "no space left",
    "disk full",
    "out of memory",
    "java.lang.outofmemoryerror",
    "checksum",
    "file corrupted",
    "mvstoreexception",
)


def _geoweaver_properties_path() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "application.properties")


def get_h2_backup_base_dir() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "h2_backups")


def _maintenance_state_path() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "h2_maintenance_state.json")


def _maintenance_lock_path() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "h2_maintenance.lock")


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_maintenance_lock() -> Dict[str, object]:
    lock_path = _maintenance_lock_path()
    if not os.path.exists(lock_path):
        return {}
    try:
        with open(lock_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Could not read H2 maintenance lock: %s", exc)
        return {}


def _is_stale_maintenance_lock() -> bool:
    lock_info = _read_maintenance_lock()
    if not lock_info:
        return True

    pid = lock_info.get("pid")
    if pid is not None and not _pid_is_alive(int(pid)):
        return True

    started_at = lock_info.get("started_at")
    if started_at:
        try:
            age_seconds = time.time() - datetime.fromisoformat(str(started_at)).timestamp()
            if age_seconds > H2_MAINTENANCE_LOCK_STALE_SECONDS:
                return True
        except ValueError:
            return True

    return False


def release_maintenance_lock() -> None:
    """Release the cross-process H2 maintenance lock."""
    try:
        os.remove(_maintenance_lock_path())
    except FileNotFoundError:
        pass


def acquire_maintenance_lock(wait_seconds: int) -> bool:
    """Acquire an exclusive maintenance lock, waiting briefly for other gw processes."""
    lock_path = _maintenance_lock_path()
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    deadline = time.time() + wait_seconds

    while time.time() < deadline:
        if os.path.exists(lock_path) and _is_stale_maintenance_lock():
            logger.warning("Removing stale H2 maintenance lock at %s", lock_path)
            release_maintenance_lock()

        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {"pid": os.getpid(), "started_at": datetime.now().isoformat()},
                    handle,
                )
            return True
        except FileExistsError:
            time.sleep(1)

    logger.warning("Timed out waiting for H2 maintenance lock")
    return False


def _in_progress_marker_path(work_dir: str) -> str:
    return os.path.join(work_dir, ".in_progress")


def _mark_maintenance_in_progress(work_dir: str, phase: str) -> None:
    marker_path = _in_progress_marker_path(work_dir)
    with open(marker_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"started_at": datetime.now().isoformat(), "pid": os.getpid(), "phase": phase},
            handle,
        )


def _clear_maintenance_in_progress(work_dir: Optional[str]) -> None:
    if not work_dir:
        return
    try:
        os.remove(_in_progress_marker_path(work_dir))
    except FileNotFoundError:
        pass


def _find_recoverable_work_dirs(db_basename: str) -> List[str]:
    backup_roots = [get_h2_backup_base_dir()]
    state = _load_maintenance_state()
    for root in state.get("extra_backup_roots") or []:
        if isinstance(root, str) and root not in backup_roots:
            backup_roots.append(root)

    candidates = []
    for backup_root in backup_roots:
        if not os.path.isdir(backup_root):
            continue
        for entry in os.listdir(backup_root):
            work_dir = os.path.join(backup_root, entry)
            if not os.path.isdir(work_dir):
                continue
            original_dir = os.path.join(work_dir, "original")
            marker_path = _in_progress_marker_path(work_dir)
            promote_phase = str(read_promote_state(work_dir).get("phase") or "")
            incomplete_promote = promote_phase in (
                "displacing",
                "copying",
                "verifying_production",
            )
            if (
                os.path.exists(marker_path)
                or incomplete_promote
                or get_matching_db_files(original_dir, db_basename)
            ):
                if get_matching_db_files(original_dir, db_basename):
                    candidates.append(work_dir)

    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates


def recover_from_interrupted_maintenance(
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    """
    Repair production database state after Ctrl+C, crashes, or partial maintenance.

    Fail closed (CRITICAL-002): an openable empty production DB must NOT clear
    backups when original/ still has critical rows. Prefer newest interrupted
    work directory with an original/ backup, then fall back to latest retained set.
    """
    resolved_db_path = resolve_h2_db_path(db_path)
    db_dir = os.path.dirname(resolved_db_path)
    db_basename = os.path.basename(resolved_db_path)
    db_username = db_username or GEOWEAVER_DEFAULT_DB_USERNAME
    password = password or GEOWEAVER_DEFAULT_DB_PASSWORD

    if os.path.exists(_maintenance_lock_path()) and _is_stale_maintenance_lock():
        logger.warning("Clearing stale H2 maintenance lock before recovery")
        release_maintenance_lock()

    candidates = _find_recoverable_work_dirs(db_basename)

    production_opens = verify_h2_database(
        resolved_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=h2_jar_path,
    )
    production_inventory = None
    # Only inventory production when we have backups to compare (avoid Java in happy path).
    if production_opens and candidates:
        production_inventory, inv_error = capture_table_inventory(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        )
        if inv_error:
            logger.warning("Could not inventory production DB during recover: %s", inv_error)

    # Always inspect backups when markers / incomplete promote / inventory loss exists.
    for work_dir in candidates:
        original_dir = os.path.join(work_dir, "original")
        promote_phase = str(read_promote_state(work_dir).get("phase") or "")
        incomplete_promote = promote_phase in (
            "displacing",
            "copying",
            "verifying_production",
        )
        needs_restore = incomplete_promote or (not production_opens)

        if production_opens and not needs_restore:
            baseline = load_inventory(work_dir)
            if baseline is not None:
                needs_restore = production_needs_restore_from_backup(
                    production_inventory, baseline
                )
            elif os.path.exists(_in_progress_marker_path(work_dir)):
                # Interrupted run without inventory file: fail closed and restore.
                needs_restore = True

        if not needs_restore:
            continue

        logger.warning(
            "Recovering production H2 from %s (promote_phase=%s, production_opens=%s)",
            work_dir,
            promote_phase or "none",
            production_opens,
        )
        if restore_database_from_backup(original_dir, db_dir, db_basename):
            if verify_h2_database(
                resolved_db_path,
                db_username=db_username,
                password=password,
                h2_jar_path=h2_jar_path,
            ):
                logger.info(
                    "Recovered production database from interrupted maintenance backup at %s",
                    work_dir,
                )
                _clear_maintenance_in_progress(work_dir)
                write_promote_state(work_dir, "restored")
                state = _load_maintenance_state()
                state.pop("interrupted_maintenance", None)
                state["pending_rebuild"] = False
                _save_maintenance_state(state)
                return True

    if production_opens and not any(
        os.path.exists(_in_progress_marker_path(work_dir))
        or str(read_promote_state(work_dir).get("phase") or "")
        in ("displacing", "copying", "verifying_production")
        for work_dir in candidates
    ):
        # Healthy production and no incomplete promote — clear leftover markers only.
        for work_dir in candidates:
            _clear_maintenance_in_progress(work_dir)
        state = _load_maintenance_state()
        state.pop("interrupted_maintenance", None)
        _save_maintenance_state(state)
        return True

    if not production_opens and restore_from_latest_backup(resolved_db_path):
        recovered = verify_h2_database(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        )
        if recovered:
            logger.info("Recovered production database from latest retained backup")
        return recovered

    if production_opens:
        logger.info("Production H2 database opens and no superior backup inventory found")
        return True

    logger.error("Could not recover production H2 database from interrupted maintenance")
    return False


@contextmanager
def h2_maintenance_guard(trigger: str = "stop") -> Iterator[bool]:
    """
    Serialize maintenance and handle Ctrl+C without blocking the CLI.

    Yields:
        bool: True when this process should run maintenance, False when skipped.

    On SIGINT/SIGTERM: mark interrupted, release the lock, and re-raise.
    Heavy recover/rebuild must NOT run in the signal path (deferred to start /
    ``gw cleanh2db``).
    """
    recover_from_interrupted_maintenance()

    wait_seconds = (
        H2_MAINTENANCE_LOCK_WAIT_START_SECONDS
        if trigger == "start"
        else H2_MAINTENANCE_LOCK_WAIT_STOP_SECONDS
    )
    if not acquire_maintenance_lock(wait_seconds=wait_seconds):
        logger.warning("Another gw process is maintaining the H2 database; skipping %s maintenance", trigger)
        yield False
        return

    interrupted = {"value": False}

    def _handle_interrupt(signum, frame):
        interrupted["value"] = True
        try:
            state = _load_maintenance_state()
            state["interrupted_maintenance"] = True
            # Do not set pending_rebuild — size rebuild is explicit via cleanh2db.
            _save_maintenance_state(state)
        except Exception:
            pass
        try:
            release_maintenance_lock()
        except Exception:
            pass
        raise KeyboardInterrupt

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)

    try:
        yield True
    except KeyboardInterrupt:
        if not interrupted["value"]:
            try:
                state = _load_maintenance_state()
                state["interrupted_maintenance"] = True
                _save_maintenance_state(state)
            except Exception:
                pass
        raise
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        release_maintenance_lock()


def _load_maintenance_state() -> Dict[str, object]:
    path = _maintenance_state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Could not read H2 maintenance state: %s", exc)
        return {}


def _save_maintenance_state(state: Dict[str, object]) -> None:
    path = _maintenance_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _record_maintenance(action: str, size_bytes: int, work_dir: Optional[str] = None) -> None:
    state = _load_maintenance_state()
    now = datetime.now().isoformat()
    size_mb = round(size_bytes / (1024 * 1024), 2)
    state["last_maintenance_at"] = now
    state["last_maintenance_action"] = action
    state["last_maintenance_size_mb"] = size_mb
    if work_dir:
        state["last_backup_dir"] = work_dir
    if action == "compact":
        state["last_compact_at"] = now
        state["last_compact_size_mb"] = size_mb
        state["pending_rebuild"] = False
    elif action == "rebuild":
        state["last_rebuild_at"] = now
        state["last_rebuild_size_mb"] = size_mb
        state["pending_rebuild"] = False
    _save_maintenance_state(state)


def _seconds_since_last_maintenance(state: Dict[str, object]) -> Optional[float]:
    last_maintenance = state.get("last_maintenance_at")
    if not last_maintenance:
        return None
    try:
        last_dt = datetime.fromisoformat(str(last_maintenance))
    except ValueError:
        return None
    return time.time() - last_dt.timestamp()


def _needs_rebuild(size_mb: float, state: Dict[str, object], force: bool = False) -> bool:
    if force:
        return True
    if state.get("pending_rebuild"):
        return True
    return size_mb >= H2_AUTO_REBUILD_THRESHOLD_MB


def _needs_compact(size_mb: float, state: Dict[str, object]) -> bool:
    if size_mb < H2_COMPACT_MIN_MB:
        return False
    if size_mb >= H2_AUTO_REBUILD_THRESHOLD_MB:
        return False

    last_compact = state.get("last_compact_at")
    if not last_compact:
        return True

    try:
        hours_since_compact = (time.time() - datetime.fromisoformat(str(last_compact)).timestamp()) / 3600
    except ValueError:
        return True

    if hours_since_compact >= H2_COMPACT_INTERVAL_HOURS:
        return True

    last_compact_size = float(state.get("last_compact_size_mb") or 0)
    if last_compact_size and size_mb > last_compact_size * 1.2:
        return True

    return False


def _should_skip_recent_maintenance(state: Dict[str, object]) -> bool:
    elapsed = _seconds_since_last_maintenance(state)
    return elapsed is not None and elapsed < H2_MAINTENANCE_COOLDOWN_SECONDS


def _extract_process_output(exc: Exception) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        return f"{exc.stdout or ''}\n{exc.stderr or ''}"
    return str(exc)


def classify_h2_error(message: str) -> str:
    """Classify common H2 subprocess failures."""
    lowered = (message or "").lower()
    if any(marker in lowered for marker in H2_AUTH_ERROR_MARKERS):
        return "auth"
    if any(marker in lowered for marker in H2_NONRETRYABLE_ERROR_MARKERS):
        return "fatal"
    if any(marker in lowered for marker in H2_LOCK_ERROR_MARKERS):
        return "locked"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    return "unknown"


def register_h2_backup_root(work_base_dir: Optional[str]) -> None:
    """Remember custom --temp-dir roots so recover can find original/ backups."""
    if not work_base_dir:
        return
    abs_root = os.path.abspath(os.path.expanduser(work_base_dir))
    state = _load_maintenance_state()
    roots = list(state.get("extra_backup_roots") or [])
    if abs_root not in roots:
        roots.append(abs_root)
        state["extra_backup_roots"] = roots[-10:]
        _save_maintenance_state(state)
        logger.info("Registered H2 backup root for recovery: %s", abs_root)


def _inventory_path(work_dir: str) -> str:
    return os.path.join(work_dir, "pre_inventory.json")


def _promote_state_path(work_dir: str) -> str:
    return os.path.join(work_dir, "promote_state.json")


def _write_json_atomic(path: str, payload: Dict[str, object]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def write_promote_state(work_dir: str, phase: str, **extra) -> None:
    payload = {
        "phase": phase,
        "updated_at": datetime.now().isoformat(),
        "pid": os.getpid(),
    }
    payload.update(extra)
    _write_json_atomic(_promote_state_path(work_dir), payload)


def read_promote_state(work_dir: str) -> Dict[str, object]:
    path = _promote_state_path(work_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Could not read promote state at %s: %s", path, exc)
        return {}


def save_inventory(work_dir: str, inventory: Dict[str, Optional[int]]) -> None:
    _write_json_atomic(
        _inventory_path(work_dir),
        {"captured_at": datetime.now().isoformat(), "tables": inventory},
    )


def load_inventory(work_dir: str) -> Optional[Dict[str, Optional[int]]]:
    path = _inventory_path(work_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        tables = payload.get("tables")
        return tables if isinstance(tables, dict) else None
    except Exception as exc:
        logger.warning("Could not read inventory at %s: %s", path, exc)
        return None


def _parse_count_from_shell_output(stdout: str) -> Optional[int]:
    """Parse H2 Shell COUNT(*) output; prefer the last standalone integer line."""
    candidates = []
    for line in (stdout or "").splitlines():
        stripped = line.strip().replace(",", "")
        if re.fullmatch(r"\d+", stripped):
            candidates.append(int(stripped))
    if candidates:
        return candidates[-1]
    return None


def capture_table_inventory(
    db_path: str,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Optional[int]]], Optional[str]]:
    """
    Count rows in critical Geoweaver tables.

    Returns (inventory, error_message). inventory values may be None when a table
    is missing. On total connection failure returns (None, error).
    """
    jar_path = get_h2_jar_path(h2_jar_path)
    if not jar_path:
        return None, "H2 JAR not available for inventory"

    mv_db_path = get_h2_mv_db_path(db_path)
    if not os.path.exists(mv_db_path) or os.path.getsize(mv_db_path) == 0:
        return None, f"Database file missing or empty: {mv_db_path}"

    inventory: Dict[str, Optional[int]] = {}
    db_username = db_username or GEOWEAVER_DEFAULT_DB_USERNAME
    password = password or GEOWEAVER_DEFAULT_DB_PASSWORD

    for table in H2_INVENTORY_TABLES:
        cmd = [
            get_java_bin_path(),
            "-cp",
            jar_path,
            "org.h2.tools.Shell",
            "-url",
            f"jdbc:h2:{db_path}",
            "-user",
            db_username,
            "-password",
            password,
            "-sql",
            f'SELECT COUNT(*) FROM "{table}";',
        ]
        # Unquoted names are uppercased by H2; try unquoted first for Hibernate defaults.
        cmd_unquoted = list(cmd)
        cmd_unquoted[-1] = f"SELECT COUNT(*) FROM {table};"
        try:
            result = subprocess.run(
                cmd_unquoted,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            count = _parse_count_from_shell_output(result.stdout)
            if count is None:
                inventory[table] = None
            else:
                inventory[table] = count
        except subprocess.CalledProcessError as exc:
            error_text = _extract_process_output(exc)
            # Table missing is recorded as None (fail-closed later if unexpected).
            if "not found" in error_text.lower() or "42102" in error_text:
                inventory[table] = None
            else:
                return None, f"Inventory query failed for {table}: {error_text.strip()}"
        except Exception as exc:
            return None, f"Inventory query error for {table}: {exc}"

    logger.info("Captured H2 table inventory for %s: %s", db_path, inventory)
    return inventory, None


def inventory_meets_baseline(
    baseline: Dict[str, Optional[int]],
    candidate: Dict[str, Optional[int]],
) -> Tuple[bool, str]:
    """Fail closed unless strict tables retain at least baseline row counts."""
    for table in H2_INVENTORY_STRICT_TABLES:
        pre = baseline.get(table)
        post = candidate.get(table)
        if pre is None:
            continue
        if post is None:
            return False, f"Critical table {table} missing after rebuild (had {pre} rows)"
        if post < pre:
            return False, f"Critical table {table} shrank {pre} -> {post}"
    for table in H2_INVENTORY_SOFT_TABLES:
        pre = baseline.get(table) or 0
        post = candidate.get(table)
        if pre > 0 and post is None:
            return False, f"Soft table {table} missing after rebuild (had {pre} rows)"
        if pre > 0 and post is not None and post < pre:
            logger.warning(
                "Soft table %s shrank %s -> %s (allowed with warning)", table, pre, post
            )
    return True, "ok"


def sql_export_suggests_workflow_data(sql_file: str) -> bool:
    """Cheap scan: true if SQL dump appears to contain WORKFLOW inserts."""
    if not os.path.exists(sql_file):
        return False
    pattern = re.compile(r"INSERT\s+INTO\s+(?:PUBLIC\.)?WORKFLOW\b", re.IGNORECASE)
    try:
        with open(sql_file, "r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if pattern.search(line):
                    return True
                if index >= 2_000_000:
                    break
    except OSError as exc:
        logger.warning("Could not scan SQL export for WORKFLOW inserts: %s", exc)
    return False


def _is_retryable_h2_failure(error_kind: str) -> bool:
    return error_kind in ("locked", "timeout")


def run_h2_tool_with_retry(
    cmd: List[str],
    *,
    phase: str,
    timeout_seconds: Optional[int] = None,
    retries: Optional[int] = None,
    on_before_attempt=None,
) -> Tuple[bool, str]:
    """
    Run an H2 CLI tool with bounded retries for transient lock/timeout errors.

    Fail closed: auth/fatal/unknown after retries → False. Never kills on heartbeat alone.
    """
    timeout = (
        H2_EXPORT_IMPORT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    )
    max_attempts = H2_EXPORT_IMPORT_RETRY_COUNT if retries is None else retries
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        if on_before_attempt is not None:
            on_before_attempt(attempt)

        logger.info(
            "H2 %s attempt %s/%s (timeout=%ss)",
            phase,
            attempt,
            max_attempts,
            timeout,
        )
        started = time.time()
        try:
            # Heartbeat: log elapsed while waiting; do not kill (HIGH-003).
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            timed_out = False
            stdout, stderr = "", ""
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=H2_TOOL_HEARTBEAT_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = int(time.time() - started)
                    logger.info(
                        "H2 %s still running... elapsed=%ss pid=%s",
                        phase,
                        elapsed,
                        process.pid,
                    )
                    if timeout and elapsed >= timeout:
                        process.kill()
                        try:
                            process.communicate(timeout=30)
                        except Exception:
                            pass
                        timed_out = True
                        last_error = f"H2 {phase} timed out after {elapsed}s"
                        logger.error(last_error)
                        break

            if timed_out:
                if attempt < max_attempts and _is_retryable_h2_failure("timeout"):
                    time.sleep(H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return False, last_error

            if process.returncode != 0:
                last_error = f"{stdout or ''}\n{stderr or ''}".strip()
                error_kind = classify_h2_error(last_error)
                logger.error("H2 %s failed (%s): %s", phase, error_kind, last_error)
                if attempt < max_attempts and _is_retryable_h2_failure(error_kind):
                    time.sleep(H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return False, last_error or f"H2 {phase} failed"

            logger.info("H2 %s succeeded in %.1fs", phase, time.time() - started)
            return True, ""

        except Exception as exc:
            last_error = str(exc)
            error_kind = classify_h2_error(last_error)
            logger.error("H2 %s unexpected error (%s): %s", phase, error_kind, exc)
            if attempt < max_attempts and _is_retryable_h2_failure(error_kind):
                time.sleep(H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS * attempt)
                continue
            return False, last_error

    return False, last_error or f"H2 {phase} failed"


def clear_directory_files(directory: str) -> None:
    """Remove all files under directory (keep directory). Used to wipe partial rebuilt/."""
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as exc:
            logger.warning("Could not remove %s: %s", path, exc)


def production_needs_restore_from_backup(
    production_inventory: Optional[Dict[str, Optional[int]]],
    backup_inventory: Optional[Dict[str, Optional[int]]],
) -> bool:
    """True when production looks empty/openable but backup still has critical rows."""
    if not backup_inventory:
        return False
    if production_inventory is None:
        return True
    for table in H2_INVENTORY_STRICT_TABLES:
        backup_count = backup_inventory.get(table) or 0
        prod_count = production_inventory.get(table)
        if backup_count > 0 and (prod_count is None or prod_count < backup_count):
            return True
    return False



def is_geoweaver_process_running() -> bool:
    """Return True when a Geoweaver JVM still holds the database open."""
    try:
        import psutil
    except ImportError:
        logger.debug("psutil unavailable; skipping Geoweaver process check")
        return False

    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            joined = " ".join(cmdline)
            if "geoweaver.jar" in joined or "GeoweaverApplication" in joined:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _wait_for_database_unlock(
    db_path: str,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    for attempt in range(1, H2_LOCK_RETRY_COUNT + 1):
        if not is_geoweaver_process_running() and verify_h2_database(
            db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        ):
            return True

        if attempt < H2_LOCK_RETRY_COUNT:
            logger.info(
                "H2 database is busy (attempt %s/%s); retrying in %.1fs",
                attempt,
                H2_LOCK_RETRY_COUNT,
                H2_LOCK_RETRY_DELAY_SECONDS,
            )
            time.sleep(H2_LOCK_RETRY_DELAY_SECONDS)

    return False


def _validate_sql_export(sql_file: str) -> bool:
    if not os.path.exists(sql_file):
        logger.error("SQL export file was not created: %s", sql_file)
        return False

    sql_file_size = os.path.getsize(sql_file)
    if sql_file_size == 0:
        logger.error("SQL export file is empty: %s", sql_file)
        return False

    with open(sql_file, "r", encoding="utf-8", errors="replace") as handle:
        line_count = sum(1 for _ in handle)

    if line_count < H2_SQL_MIN_LINES:
        logger.error("SQL export file has too few lines (%s): %s", line_count, sql_file)
        return False

    return True


def prune_old_h2_backups() -> None:
    backup_root = get_h2_backup_base_dir()
    if not os.path.isdir(backup_root):
        return

    backups = [
        os.path.join(backup_root, entry)
        for entry in os.listdir(backup_root)
        if os.path.isdir(os.path.join(backup_root, entry))
    ]
    backups.sort(key=os.path.getmtime, reverse=True)

    for old_backup in backups[H2_BACKUP_RETENTION_COUNT:]:
        try:
            shutil.rmtree(old_backup)
            logger.info("Removed old H2 backup: %s", old_backup)
        except Exception as exc:
            logger.warning("Failed to remove old H2 backup %s: %s", old_backup, exc)


def restore_from_latest_backup(db_path: Optional[str] = None) -> bool:
    """Restore production database files from the newest retained backup."""
    resolved_db_path = resolve_h2_db_path(db_path)
    db_dir = os.path.dirname(resolved_db_path)
    db_basename = os.path.basename(resolved_db_path)
    backup_root = get_h2_backup_base_dir()

    if not os.path.isdir(backup_root):
        return False

    candidates = []
    for entry in os.listdir(backup_root):
        work_dir = os.path.join(backup_root, entry)
        original_dir = os.path.join(work_dir, "original")
        if os.path.isdir(original_dir) and get_matching_db_files(original_dir, db_basename):
            candidates.append(work_dir)

    if not candidates:
        logger.warning("No H2 backups with original database copies were found")
        return False

    candidates.sort(key=os.path.getmtime, reverse=True)
    latest_backup = candidates[0]
    original_dir = os.path.join(latest_backup, "original")
    logger.info("Restoring production database from backup %s", latest_backup)

    if restore_database_from_backup(original_dir, db_dir, db_basename):
        logger.info("Production database restored from %s", original_dir)
        return True

    logger.error("Failed to restore production database from %s", original_dir)
    return False


def _parse_jdbc_url_path(db_url: str) -> Optional[str]:
    match = re.search(r"jdbc:h2:(?:file:)?(.+?)(?:;|$)", db_url)
    if not match:
        return None
    return os.path.abspath(os.path.expanduser(match.group(1)))


def resolve_h2_db_path(db_path: Optional[str] = None) -> str:
    """Resolve the H2 database file path from an override, properties, or default."""
    if db_path:
        resolved = os.path.abspath(os.path.expanduser(db_path))
        logger.info("Using provided H2 database path: %s", resolved)
        return resolved

    custom_db_url = get_database_url_from_properties()
    if custom_db_url and "jdbc:h2:" in custom_db_url:
        parsed = _parse_jdbc_url_path(custom_db_url)
        if parsed:
            logger.info("Using H2 database path from application.properties: %s", parsed)
            return parsed
        logger.warning("Could not parse database path from URL: %s", custom_db_url)

    default_path = os.path.join(get_home_dir(), "h2", "gw")
    logger.info("Using default H2 database path: %s", default_path)
    return default_path


def get_h2_mv_db_path(db_path: Optional[str] = None) -> str:
    """Return the primary on-disk H2 database file path."""
    resolved = resolve_h2_db_path(db_path)
    if resolved.endswith(".mv.db"):
        return resolved
    return f"{resolved}.mv.db"


def get_h2_database_size_bytes(db_path: Optional[str] = None) -> int:
    """Return the size of the H2 database file in bytes, or 0 if it does not exist."""
    mv_db_path = get_h2_mv_db_path(db_path)
    if not os.path.exists(mv_db_path):
        return 0
    return os.path.getsize(mv_db_path)


def _append_missing_jdbc_params(url: str, params: Dict[str, str]) -> Tuple[str, bool]:
    existing_keys = set()
    for part in url.split(";")[1:]:
        if "=" in part:
            existing_keys.add(part.split("=", 1)[0].strip().upper())

    additions = [
        f"{key}={value}"
        for key, value in params.items()
        if key.upper() not in existing_keys
    ]
    if not additions:
        return url, False
    return f"{url};{';'.join(additions)}", True


def ensure_h2_safe_datasource_url() -> bool:
    """
    Patch application.properties so the H2 JDBC URL includes anti-bloat settings.

    Returns True when the file was updated.
    """
    properties_path = _geoweaver_properties_path()
    if not os.path.exists(properties_path):
        logger.debug("No application.properties found at %s", properties_path)
        return False

    with open(properties_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key not in DATASOURCE_URL_KEYS or "jdbc:h2:" not in value:
            new_lines.append(line)
            continue

        patched_url, changed = _append_missing_jdbc_params(value, H2_SAFE_JDBC_PARAMS)
        if changed:
            new_lines.append(f"{key}={patched_url}\n")
            updated = True
            logger.info("Updated %s with H2 anti-bloat JDBC parameters", key)
        else:
            new_lines.append(line)

    if updated:
        with open(properties_path, "w", encoding="utf-8") as handle:
            handle.writelines(new_lines)

    return updated


def get_h2_jar_path(h2_jar_path: Optional[str] = None) -> Optional[str]:
    """Locate or download the H2 JAR used for maintenance commands."""
    if h2_jar_path and os.path.exists(h2_jar_path):
        return h2_jar_path

    candidates = [
        os.path.join(os.getcwd(), f"h2-{H2_VERSION}.jar"),
        os.path.join(get_home_dir(), f"h2-{H2_VERSION}.jar"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    target = os.path.join(get_home_dir(), f"h2-{H2_VERSION}.jar")
    download_url = (
        f"https://repo1.maven.org/maven2/com/h2database/h2/{H2_VERSION}/h2-{H2_VERSION}.jar"
    )
    try:
        download_file(download_url, target)
        return target if os.path.exists(target) else None
    except Exception as exc:
        logger.warning("Failed to download H2 JAR for maintenance: %s", exc)
        return None


def compact_h2_database(
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
) -> bool:
    """
    Compact the H2 database while Geoweaver is stopped.

    Runs SHUTDOWN COMPACT to reclaim MVStore free space and prevent file bloat.
    """
    resolved_db_path = resolve_h2_db_path(db_path)
    mv_db_path = get_h2_mv_db_path(resolved_db_path)
    if not os.path.exists(mv_db_path):
        logger.info("No H2 database file found at %s, skipping compaction", mv_db_path)
        return True

    size_before = os.path.getsize(mv_db_path)
    logger.info(
        "Compacting H2 database at %s (%.2f MB before compaction)",
        mv_db_path,
        size_before / (1024 * 1024),
    )

    jar_path = get_h2_jar_path(h2_jar_path)
    if not jar_path:
        logger.warning("H2 JAR not available, skipping compaction")
        return False

    compact_timeout = (
        H2_STOP_COMPACT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    )

    compact_cmd = [
        get_java_bin_path(),
        "-cp",
        jar_path,
        "org.h2.tools.Shell",
        "-url",
        f"jdbc:h2:{resolved_db_path}",
        "-user",
        db_username or GEOWEAVER_DEFAULT_DB_USERNAME,
        "-password",
        password or GEOWEAVER_DEFAULT_DB_PASSWORD,
        "-sql",
        "SHUTDOWN COMPACT;",
    ]

    try:
        result = subprocess.run(
            compact_cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=compact_timeout,
        )
        if result.stdout:
            logger.debug("H2 compaction stdout: %s", result.stdout.strip())
        if result.stderr:
            logger.debug("H2 compaction stderr: %s", result.stderr.strip())
    except subprocess.TimeoutExpired:
        logger.error("H2 compaction timed out for %s", resolved_db_path)
        return False
    except subprocess.CalledProcessError as exc:
        error_text = _extract_process_output(exc)
        error_kind = classify_h2_error(error_text)
        logger.error("H2 compaction failed (%s): %s", error_kind, error_text.strip())
        return False
    except Exception as exc:
        logger.error("Unexpected error during H2 compaction: %s", exc)
        return False

    if os.path.exists(mv_db_path):
        size_after = os.path.getsize(mv_db_path)
        logger.info(
            "H2 compaction finished: %.2f MB -> %.2f MB",
            size_before / (1024 * 1024),
            size_after / (1024 * 1024),
        )
    else:
        logger.info("H2 compaction finished for %s", resolved_db_path)

    return True


def warn_if_h2_database_is_large(db_path: Optional[str] = None) -> None:
    """Log a warning when the H2 database exceeds the configured size threshold."""
    size_bytes = get_h2_database_size_bytes(db_path)
    if size_bytes == 0:
        return

    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= H2_SIZE_WARN_THRESHOLD_MB:
        logger.warning(
            "H2 database is %.2f MB (threshold: %d MB). Automatic maintenance will rebuild it.",
            size_mb,
            H2_SIZE_WARN_THRESHOLD_MB,
        )


def rebuild_h2_database_safely(
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
    work_base_dir: Optional[str] = None,
    force: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Safely rebuild the H2 database without touching production until verification succeeds.

    Returns:
        Tuple[bool, Optional[str]]: success flag and work directory containing backups.
    """
    resolved_db_path = resolve_h2_db_path(db_path)
    db_dir = os.path.dirname(resolved_db_path)
    db_basename = os.path.basename(resolved_db_path)
    db_username = db_username or GEOWEAVER_DEFAULT_DB_USERNAME
    password = password or GEOWEAVER_DEFAULT_DB_PASSWORD

    if not force and not get_matching_db_files(db_dir, db_basename):
        logger.info("No production H2 database files found, skipping rebuild")
        return True, None

    if is_geoweaver_process_running():
        logger.error("Cannot rebuild H2 database while Geoweaver is still running")
        return False, None

    jar_path = get_h2_jar_path(h2_jar_path)
    if not jar_path:
        logger.error("H2 JAR not available for safe rebuild")
        return False, None

    backup_root = work_base_dir or get_h2_backup_base_dir()
    os.makedirs(backup_root, exist_ok=True)
    register_h2_backup_root(backup_root)
    work_dir = create_timestamped_work_dir(backup_root)
    original_dir = os.path.join(work_dir, "original")
    rebuilt_dir = os.path.join(work_dir, "rebuilt")
    displaced_dir = os.path.join(work_dir, "displaced")
    sql_file = os.path.join(work_dir, "gw_backup.sql")
    os.makedirs(original_dir, exist_ok=True)
    os.makedirs(rebuilt_dir, exist_ok=True)
    os.makedirs(displaced_dir, exist_ok=True)
    _mark_maintenance_in_progress(work_dir, "backup")

    size_before = get_h2_database_size_bytes(resolved_db_path)
    logger.info(
        "Starting safe H2 rebuild for %s (%.2f MB). Backup directory: %s",
        resolved_db_path,
        size_before / (1024 * 1024),
        work_dir,
    )

    if get_matching_db_files(db_dir, db_basename):
        if not _wait_for_database_unlock(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=jar_path,
        ):
            logger.error(
                "H2 database is locked or unreadable; rebuild aborted before copying production files"
            )
            return False, work_dir

        if not copy_matching_db_files(db_dir, original_dir, db_basename):
            logger.error("Failed to copy production database into %s", original_dir)
            return False, work_dir

    export_source_path = os.path.join(original_dir, db_basename)
    if not get_matching_db_files(original_dir, db_basename):
        export_source_path = resolved_db_path

    # Capture baseline inventory from the copy we will export (fail closed).
    pre_inventory, inv_error = capture_table_inventory(
        export_source_path,
        db_username=db_username,
        password=password,
        h2_jar_path=jar_path,
    )
    if inv_error or pre_inventory is None:
        logger.error("Refusing rebuild: cannot capture pre-inventory (%s)", inv_error)
        return False, work_dir
    save_inventory(work_dir, pre_inventory)

    export_cmd = [
        get_java_bin_path(),
        "-cp",
        jar_path,
        "org.h2.tools.Script",
        "-url",
        f"jdbc:h2:{export_source_path}",
        "-user",
        db_username,
        "-script",
        sql_file,
        "-password",
        password,
    ]
    export_ok, export_error = run_h2_tool_with_retry(export_cmd, phase="export")
    if not export_ok:
        logger.error("H2 export failed after retries: %s", export_error)
        return False, work_dir

    if not _validate_sql_export(sql_file):
        return False, work_dir

    # CRITICAL-003: refuse to continue if baseline said empty but SQL clearly has workflows
    # while the DB file is large — likely wiped production / bad inventory.
    workflow_pre = pre_inventory.get("WORKFLOW") or 0
    if workflow_pre == 0 and sql_export_suggests_workflow_data(sql_file):
        logger.error(
            "Refusing rebuild: pre-inventory WORKFLOW=0 but SQL contains WORKFLOW inserts"
        )
        return False, work_dir

    _mark_maintenance_in_progress(work_dir, "import")
    rebuilt_db_path = os.path.join(rebuilt_dir, db_basename)

    def _wipe_rebuilt_before_attempt(_attempt: int) -> None:
        clear_directory_files(rebuilt_dir)

    import_cmd = [
        get_java_bin_path(),
        "-cp",
        jar_path,
        "org.h2.tools.RunScript",
        "-url",
        f"jdbc:h2:{rebuilt_db_path}",
        "-user",
        db_username,
        "-script",
        sql_file,
        "-password",
        password,
    ]
    import_ok, import_error = run_h2_tool_with_retry(
        import_cmd,
        phase="import",
        on_before_attempt=_wipe_rebuilt_before_attempt,
    )
    if not import_ok:
        logger.error("H2 import failed after retries: %s", import_error)
        return False, work_dir

    if not verify_h2_database(
        rebuilt_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=jar_path,
    ):
        logger.error("Rebuilt database verification failed for %s", rebuilt_db_path)
        return False, work_dir

    post_inventory, post_error = capture_table_inventory(
        rebuilt_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=jar_path,
    )
    if post_error or post_inventory is None:
        logger.error("Refusing promote: cannot inventory rebuilt DB (%s)", post_error)
        return False, work_dir

    ok_inventory, reason = inventory_meets_baseline(pre_inventory, post_inventory)
    if not ok_inventory:
        logger.error("Refusing promote: inventory gate failed: %s", reason)
        return False, work_dir

    if workflow_pre > 0 and (post_inventory.get("WORKFLOW") or 0) == 0:
        logger.error("Refusing promote: WORKFLOW rows dropped to zero")
        return False, work_dir

    _mark_maintenance_in_progress(work_dir, "promote")
    os.makedirs(db_dir, exist_ok=True)
    if not promote_rebuilt_database(
        production_dir=db_dir,
        rebuilt_dir=rebuilt_dir,
        displaced_dir=displaced_dir,
        db_basename=db_basename,
        original_backup_dir=original_dir,
        work_dir=work_dir,
        expected_inventory=pre_inventory,
        db_username=db_username,
        password=password,
        h2_jar_path=jar_path,
        production_db_path=resolved_db_path,
    ):
        return False, work_dir

    size_after = get_h2_database_size_bytes(resolved_db_path)
    logger.info(
        "Safe H2 rebuild completed: %.2f MB -> %.2f MB. Backup retained at %s",
        size_before / (1024 * 1024),
        size_after / (1024 * 1024),
        work_dir,
    )
    _record_maintenance("rebuild", size_after, work_dir)
    _clear_maintenance_in_progress(work_dir)
    write_promote_state(work_dir, "done")
    # Keep the latest successful original/ available (MEDIUM-003): prune older only.
    prune_old_h2_backups()
    return True, work_dir


def _emit_oversized_h2_remediation(size_mb: float) -> None:
    """Stdout + log hint when the DB exceeds the rebuild threshold."""
    if size_mb < H2_AUTO_REBUILD_THRESHOLD_MB:
        return
    message = (
        f"H2 database is {size_mb:.0f} MB (≥ threshold {H2_AUTO_REBUILD_THRESHOLD_MB} MB). "
        "Run: gw cleanh2db"
    )
    print(message)
    logger.warning(message)


def warn_oversized_h2_on_lifecycle(db_path: Optional[str] = None) -> None:
    """Fast size check used by default ``gw stop`` (no maintenance)."""
    size_bytes = get_h2_database_size_bytes(db_path)
    if size_bytes == 0:
        return
    _emit_oversized_h2_remediation(size_bytes / (1024 * 1024))


def _run_automatic_h2_maintenance_body(
    trigger: str,
    force_rebuild: bool,
    allow_compact: bool,
    allow_size_rebuild: bool,
    resolved_db_path: str,
    db_username: str,
    password: str,
    h2_jar_path: Optional[str],
    size_bytes: int,
) -> bool:
    size_mb = size_bytes / (1024 * 1024)
    state = _load_maintenance_state()

    _emit_oversized_h2_remediation(size_mb)

    if not force_rebuild and _should_skip_recent_maintenance(state):
        logger.info("Skipping H2 maintenance: completed recently")
        if trigger == "start" and not verify_h2_database(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        ):
            logger.warning("Recent maintenance recorded but production database is unreadable")
            return recover_from_interrupted_maintenance(
                resolved_db_path,
                db_username=db_username,
                password=password,
                h2_jar_path=h2_jar_path,
            )
        return True

    production_ok = _wait_for_database_unlock(
        resolved_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=h2_jar_path,
    )

    if trigger == "start" and not production_ok:
        logger.warning("Production H2 database failed verification before start")
        if recover_from_interrupted_maintenance(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        ):
            production_ok = True
        if not production_ok:
            logger.error("Production H2 database is unreadable and could not be recovered")
            return False

    # Size-based / pending rebuild only when explicitly allowed (e.g. tests or tools).
    # Default start/stop never auto-rebuild; use ``gw cleanh2db``.
    should_rebuild = force_rebuild or (
        allow_size_rebuild and _needs_rebuild(size_mb, state, force=False)
    )
    if should_rebuild:
        logger.info(
            "Automatic H2 rebuild triggered (%s, %.2f MB, threshold=%d MB)",
            trigger,
            size_mb,
            H2_AUTO_REBUILD_THRESHOLD_MB,
        )
        success, work_dir = rebuild_h2_database_safely(
            db_path=resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
            force=True,
        )
        if not success:
            state["pending_rebuild"] = True
            state["interrupted_maintenance"] = True
            _save_maintenance_state(state)
            logger.error("Automatic H2 rebuild failed; production was left unchanged when possible")
            return trigger != "start"
        return True

    if trigger == "stop" and allow_compact and _needs_compact(size_mb, state):
        logger.info("Optional H2 compact on stop (%.2f MB, timeout=%ss)", size_mb, H2_STOP_COMPACT_TIMEOUT_SECONDS)
        if compact_h2_database(
            db_path=resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
            timeout_seconds=H2_STOP_COMPACT_TIMEOUT_SECONDS,
        ):
            compact_size = get_h2_database_size_bytes(resolved_db_path)
            _record_maintenance("compact", compact_size)
            return True

        state["interrupted_maintenance"] = True
        _save_maintenance_state(state)
        logger.warning(
            "Optional H2 compact failed or timed out; run `gw cleanh2db` if the file keeps growing"
        )
        return True

    if trigger == "start" and not production_ok:
        logger.error("Production H2 database is not readable after maintenance checks")
        return False

    logger.info("H2 database healthy (%.2f MB); no maintenance required", size_mb)
    return True


def run_automatic_h2_maintenance(
    trigger: str = "stop",
    force_rebuild: bool = False,
    allow_compact: bool = False,
    allow_size_rebuild: bool = False,
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    """
    Run safe H2 checks while Geoweaver is stopped.

    Default start/stop: recover/verify as needed; never size-rebuild; compact only
    when ``allow_compact`` is True (``gw stop --maintain-h2``). Full rebuild is
    ``gw cleanh2db`` / ``force_rebuild=True``.
    """
    if not H2_AUTO_MAINTENANCE and not force_rebuild:
        logger.info("Automatic H2 maintenance is disabled")
        return True

    ensure_h2_safe_datasource_url()
    resolved_db_path = resolve_h2_db_path(db_path)
    db_username = db_username or GEOWEAVER_DEFAULT_DB_USERNAME
    password = password or GEOWEAVER_DEFAULT_DB_PASSWORD
    size_bytes = get_h2_database_size_bytes(resolved_db_path)

    if size_bytes == 0:
        logger.info("No H2 database file found, skipping automatic maintenance")
        return True

    if is_geoweaver_process_running():
        logger.warning("Geoweaver is still running; H2 maintenance cannot run safely")
        return trigger != "start"

    with h2_maintenance_guard(trigger) as should_run:
        if not should_run:
            if trigger == "start":
                return recover_from_interrupted_maintenance(
                    resolved_db_path,
                    db_username=db_username,
                    password=password,
                    h2_jar_path=h2_jar_path,
                )
            return True

        return _run_automatic_h2_maintenance_body(
            trigger=trigger,
            force_rebuild=force_rebuild,
            allow_compact=allow_compact,
            allow_size_rebuild=allow_size_rebuild,
            resolved_db_path=resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
            size_bytes=size_bytes,
        )


def get_safe_datasource_url_for_start() -> Optional[str]:
    """
    Return a safe JDBC URL override for startup when application.properties is absent.
    """
    if os.path.exists(_geoweaver_properties_path()):
        return None

    default_db = os.path.join(get_home_dir(), "h2", "gw")
    base_url = f"jdbc:h2:file:{default_db}"
    patched_url, _ = _append_missing_jdbc_params(base_url, H2_SAFE_JDBC_PARAMS)
    return patched_url


def prepare_h2_database_for_start(
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    """Verify and recover H2 if needed before Geoweaver starts (no size rebuild)."""
    warn_if_h2_database_is_large(db_path)
    return run_automatic_h2_maintenance(
        trigger="start",
        allow_compact=False,
        allow_size_rebuild=False,
        db_path=db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=h2_jar_path,
    )


def maintain_h2_database_on_stop(
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
    allow_compact: bool = False,
) -> bool:
    """
    Optional post-stop H2 work.

    Default callers should prefer ``warn_oversized_h2_on_lifecycle`` only.
    Pass ``allow_compact=True`` for ``gw stop --maintain-h2``.
    """
    return run_automatic_h2_maintenance(
        trigger="stop",
        allow_compact=allow_compact,
        allow_size_rebuild=False,
        db_path=db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=h2_jar_path,
    )


def create_timestamped_work_dir(base_dir: str, prefix: str = "geoweaver_h2_backup") -> str:
    """Create a unique work directory so repeated cleanups never overwrite prior backups."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    work_dir = os.path.join(base_dir, f"{prefix}_{timestamp}")
    suffix = 0
    while os.path.exists(work_dir):
        suffix += 1
        work_dir = os.path.join(base_dir, f"{prefix}_{timestamp}_{suffix}")
    os.makedirs(work_dir, exist_ok=True)
    return work_dir


def get_matching_db_files(directory: str, db_basename: str) -> List[str]:
    """Return database-related filenames that share the H2 database basename."""
    if not os.path.isdir(directory):
        return []
    return sorted(
        filename
        for filename in os.listdir(directory)
        if filename.startswith(db_basename)
    )


def copy_matching_db_files(src_dir: str, dst_dir: str, db_basename: str) -> bool:
    """Copy H2 database files and verify byte-for-byte sizes."""
    os.makedirs(dst_dir, exist_ok=True)
    files = get_matching_db_files(src_dir, db_basename)
    if not files:
        return False

    for filename in files:
        src_file = os.path.join(src_dir, filename)
        dst_file = os.path.join(dst_dir, filename)
        shutil.copy2(src_file, dst_file)
        if os.path.getsize(src_file) != os.path.getsize(dst_file):
            logger.error(
                "File size mismatch after copy: %s (%s bytes) -> %s (%s bytes)",
                src_file,
                os.path.getsize(src_file),
                dst_file,
                os.path.getsize(dst_file),
            )
            return False
    return True


def move_matching_db_files(src_dir: str, dst_dir: str, db_basename: str) -> bool:
    """Move H2 database files into an archive directory."""
    os.makedirs(dst_dir, exist_ok=True)
    files = get_matching_db_files(src_dir, db_basename)
    for filename in files:
        src_file = os.path.join(src_dir, filename)
        dst_file = os.path.join(dst_dir, filename)
        if os.path.exists(dst_file):
            os.remove(dst_file)
        shutil.move(src_file, dst_file)
    return True


def restore_database_from_backup(backup_dir: str, target_dir: str, db_basename: str) -> bool:
    """Restore production database files from a backup copy."""
    os.makedirs(target_dir, exist_ok=True)
    for filename in get_matching_db_files(target_dir, db_basename):
        os.remove(os.path.join(target_dir, filename))
    return copy_matching_db_files(backup_dir, target_dir, db_basename)


def verify_h2_database(
    db_path: str,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    """Confirm the rebuilt database can be opened before touching production files."""
    mv_db_path = get_h2_mv_db_path(db_path)
    if not os.path.exists(mv_db_path) or os.path.getsize(mv_db_path) == 0:
        logger.error("Rebuilt database file is missing or empty: %s", mv_db_path)
        return False

    jar_path = get_h2_jar_path(h2_jar_path)
    if not jar_path:
        logger.error("H2 JAR not available for database verification")
        return False

    verify_cmd = [
        get_java_bin_path(),
        "-cp",
        jar_path,
        "org.h2.tools.Shell",
        "-url",
        f"jdbc:h2:{db_path}",
        "-user",
        db_username or GEOWEAVER_DEFAULT_DB_USERNAME,
        "-password",
        password or GEOWEAVER_DEFAULT_DB_PASSWORD,
        "-sql",
        "SELECT 1;",
    ]
    try:
        subprocess.run(
            verify_cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return True
    except subprocess.CalledProcessError as exc:
        error_text = _extract_process_output(exc)
        error_kind = classify_h2_error(error_text)
        logger.error("H2 verification failed (%s): %s", error_kind, error_text.strip())
        return False
    except Exception as exc:
        logger.error("Unexpected error during H2 verification: %s", exc)
        return False


def promote_rebuilt_database(
    production_dir: str,
    rebuilt_dir: str,
    displaced_dir: str,
    db_basename: str,
    original_backup_dir: str,
    work_dir: Optional[str] = None,
    expected_inventory: Optional[Dict[str, Optional[int]]] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
    production_db_path: Optional[str] = None,
) -> bool:
    """
    Replace production database files only after a verified rebuild exists.

    Production files are archived under displaced_dir. On failure, the untouched
    original backup copy is restored into production.

    Multi-file swap is best-effort (HIGH-001); promote_state + inventory check
    after copy are the real safety net.
    """
    try:
        if work_dir:
            write_promote_state(work_dir, "displacing")
        if get_matching_db_files(production_dir, db_basename):
            move_matching_db_files(production_dir, displaced_dir, db_basename)
        if work_dir:
            write_promote_state(work_dir, "copying")
        if not copy_matching_db_files(rebuilt_dir, production_dir, db_basename):
            raise RuntimeError("Failed to copy rebuilt database into production")
        if not get_matching_db_files(production_dir, db_basename):
            raise RuntimeError("Rebuilt database files were not promoted into production")

        if expected_inventory is not None and production_db_path:
            if work_dir:
                write_promote_state(work_dir, "verifying_production")
            if not verify_h2_database(
                production_db_path,
                db_username=db_username,
                password=password,
                h2_jar_path=h2_jar_path,
            ):
                raise RuntimeError("Promoted production database failed open check")
            prod_inventory, prod_error = capture_table_inventory(
                production_db_path,
                db_username=db_username,
                password=password,
                h2_jar_path=h2_jar_path,
            )
            if prod_error or prod_inventory is None:
                raise RuntimeError(f"Promoted production inventory failed: {prod_error}")
            ok_inventory, reason = inventory_meets_baseline(
                expected_inventory, prod_inventory
            )
            if not ok_inventory:
                raise RuntimeError(f"Promoted production inventory gate failed: {reason}")

        if work_dir:
            write_promote_state(work_dir, "done")
        return True
    except Exception as exc:
        logger.error("Database promotion failed: %s", exc)
        logger.exception("Database promotion exception:")
        if work_dir:
            write_promote_state(work_dir, "failed", error=str(exc))
        restored = restore_database_from_backup(
            original_backup_dir,
            production_dir,
            db_basename,
        )
        if restored:
            logger.info("Restored production database from original backup copy")
            if work_dir:
                write_promote_state(work_dir, "restored")
        else:
            logger.error(
                "Failed to restore production database from %s",
                original_backup_dir,
            )
        return False
