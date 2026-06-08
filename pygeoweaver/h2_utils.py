"""H2 database maintenance utilities to prevent unbounded MVStore file growth."""

import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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
H2_BACKUP_RETENTION_COUNT = int(os.getenv("H2_BACKUP_RETENTION_COUNT", "3"))
H2_SQL_MIN_LINES = int(os.getenv("H2_SQL_MIN_LINES", "10"))
H2_SIZE_WARN_THRESHOLD_MB = int(os.getenv("H2_SIZE_WARN_THRESHOLD_MB", "2048"))
H2_LOCK_RETRY_COUNT = int(os.getenv("H2_LOCK_RETRY_COUNT", "3"))
H2_LOCK_RETRY_DELAY_SECONDS = float(os.getenv("H2_LOCK_RETRY_DELAY_SECONDS", "2"))

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


def _geoweaver_properties_path() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "application.properties")


def get_h2_backup_base_dir() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "h2_backups")


def _maintenance_state_path() -> str:
    return os.path.join(get_home_dir(), "geoweaver", "h2_maintenance_state.json")


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
    if any(marker in lowered for marker in H2_LOCK_ERROR_MARKERS):
        return "locked"
    if any(marker in lowered for marker in H2_AUTH_ERROR_MARKERS):
        return "auth"
    return "unknown"


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
            timeout=3600,
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
    work_dir = create_timestamped_work_dir(backup_root)
    original_dir = os.path.join(work_dir, "original")
    rebuilt_dir = os.path.join(work_dir, "rebuilt")
    displaced_dir = os.path.join(work_dir, "displaced")
    sql_file = os.path.join(work_dir, "gw_backup.sql")
    os.makedirs(original_dir, exist_ok=True)
    os.makedirs(rebuilt_dir, exist_ok=True)
    os.makedirs(displaced_dir, exist_ok=True)

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
    try:
        subprocess.run(export_cmd, check=True, capture_output=True, text=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        error_text = _extract_process_output(exc)
        error_kind = classify_h2_error(error_text)
        logger.error("H2 export failed (%s): %s", error_kind, error_text.strip())
        return False, work_dir
    except Exception as exc:
        logger.error("Unexpected H2 export error: %s", exc)
        return False, work_dir

    if not _validate_sql_export(sql_file):
        return False, work_dir

    rebuilt_db_path = os.path.join(rebuilt_dir, db_basename)
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
    try:
        subprocess.run(import_cmd, check=True, capture_output=True, text=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        error_text = _extract_process_output(exc)
        error_kind = classify_h2_error(error_text)
        logger.error("H2 import failed (%s): %s", error_kind, error_text.strip())
        return False, work_dir
    except Exception as exc:
        logger.error("Unexpected H2 import error: %s", exc)
        return False, work_dir

    if not verify_h2_database(
        rebuilt_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=jar_path,
    ):
        logger.error("Rebuilt database verification failed for %s", rebuilt_db_path)
        return False, work_dir

    os.makedirs(db_dir, exist_ok=True)
    if not promote_rebuilt_database(
        production_dir=db_dir,
        rebuilt_dir=rebuilt_dir,
        displaced_dir=displaced_dir,
        db_basename=db_basename,
        original_backup_dir=original_dir,
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
    prune_old_h2_backups()
    return True, work_dir


def run_automatic_h2_maintenance(
    trigger: str = "stop",
    force_rebuild: bool = False,
    db_path: Optional[str] = None,
    db_username: Optional[str] = None,
    password: Optional[str] = None,
    h2_jar_path: Optional[str] = None,
) -> bool:
    """
    Run intelligent, safe H2 maintenance while Geoweaver is stopped.

    - Rebuilds oversized databases with verify-then-promote semantics.
    - Compacts healthy databases on a schedule.
    - Restores from the latest backup if production files are unreadable on start.
    """
    if not H2_AUTO_MAINTENANCE:
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

    size_mb = size_bytes / (1024 * 1024)
    state = _load_maintenance_state()

    if not force_rebuild and _should_skip_recent_maintenance(state):
        logger.info("Skipping H2 maintenance: completed recently")
        if trigger == "start" and not verify_h2_database(
            resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        ):
            logger.warning("Recent maintenance recorded but production database is unreadable")
            return restore_from_latest_backup(resolved_db_path)
        return True

    production_ok = _wait_for_database_unlock(
        resolved_db_path,
        db_username=db_username,
        password=password,
        h2_jar_path=h2_jar_path,
    )

    if trigger == "start" and not production_ok:
        logger.warning("Production H2 database failed verification before start")
        if restore_from_latest_backup(resolved_db_path):
            production_ok = verify_h2_database(
                resolved_db_path,
                db_username=db_username,
                password=password,
                h2_jar_path=h2_jar_path,
            )
        if not production_ok and not _needs_rebuild(size_mb, state, force_rebuild):
            logger.error("Production H2 database is unreadable and no backup could be restored")
            return False

    if _needs_rebuild(size_mb, state, force_rebuild):
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
            _save_maintenance_state(state)
            logger.error("Automatic H2 rebuild failed; production was left unchanged when possible")
            return trigger != "start"
        return True

    if trigger == "stop" and _needs_compact(size_mb, state):
        logger.info("Automatic H2 compact triggered on stop (%.2f MB)", size_mb)
        if compact_h2_database(
            db_path=resolved_db_path,
            db_username=db_username,
            password=password,
            h2_jar_path=h2_jar_path,
        ):
            compact_size = get_h2_database_size_bytes(resolved_db_path)
            _record_maintenance("compact", compact_size)
            return True

        state["pending_rebuild"] = True
        _save_maintenance_state(state)
        logger.warning("Automatic H2 compact failed; full rebuild will be attempted next time")
        return True

    if trigger == "start" and not production_ok:
        logger.error("Production H2 database is not readable after maintenance checks")
        return False

    logger.info("H2 database healthy (%.2f MB); no maintenance required", size_mb)
    return True


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
    """Verify, restore if needed, and maintain the H2 database before Geoweaver starts."""
    warn_if_h2_database_is_large(db_path)
    return run_automatic_h2_maintenance(
        trigger="start",
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
) -> bool:
    """Run safe automatic H2 maintenance after Geoweaver stops."""
    return run_automatic_h2_maintenance(
        trigger="stop",
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
) -> bool:
    """
    Replace production database files only after a verified rebuild exists.

    Production files are archived under displaced_dir. On failure, the untouched
    original backup copy is restored into production.
    """
    try:
        if get_matching_db_files(production_dir, db_basename):
            move_matching_db_files(production_dir, displaced_dir, db_basename)
        if not copy_matching_db_files(rebuilt_dir, production_dir, db_basename):
            raise RuntimeError("Failed to copy rebuilt database into production")
        if not get_matching_db_files(production_dir, db_basename):
            raise RuntimeError("Rebuilt database files were not promoted into production")
        return True
    except Exception as exc:
        logger.error("Database promotion failed: %s", exc)
        logger.exception("Database promotion exception:")
        restored = restore_database_from_backup(
            original_backup_dir,
            production_dir,
            db_basename,
        )
        if restored:
            logger.info("Restored production database from original backup copy")
        else:
            logger.error(
                "Failed to restore production database from %s",
                original_backup_dir,
            )
        return False
