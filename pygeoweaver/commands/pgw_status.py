"""Geoweaver health / status diagnostics (credential-safe)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import click
import requests

from pygeoweaver.config_utils import get_database_url_from_properties, read_properties_file
from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL, GEOWEAVER_MIN_JAVA_MAJOR, GEOWEAVER_PORT
from pygeoweaver.h2_utils import (
    H2_AUTO_REBUILD_THRESHOLD_MB,
    _geoweaver_properties_path,
    _load_maintenance_state,
    _maintenance_lock_path,
    capture_table_inventory,
    get_h2_backup_base_dir,
    get_h2_database_size_bytes,
    get_h2_jar_path,
    get_h2_mv_db_path,
    is_geoweaver_process_running,
    resolve_h2_db_path,
    verify_h2_database,
)
from pygeoweaver.server import check_geoweaver_status, find_geoweaver_processes
from pygeoweaver.utils import get_home_dir, get_java_bin_path, get_log_file_path
from pygeoweaver.jdk_utils import get_java_major_version, print_unsupported_java_warning
from pygeoweaver.version import __version__

# Property keys that must never be printed in clear text.
_SENSITIVE_PROPERTY_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|credential|private)",
    re.IGNORECASE,
)

_JDBC_SENSITIVE_PARAM_RE = re.compile(
    r"(?i)\b(PASSWORD|PWD|USER|USERNAME)\s*=\s*[^;]*"
)


def redact_jdbc_url(url: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Summarize a JDBC URL without exposing credentials or full query secrets.

    Returns a small dict suitable for display/JSON, or None if no URL.
    """
    if not url:
        return None

    engine = "unknown"
    if "jdbc:h2:" in url.lower():
        engine = "h2"
    elif "jdbc:postgresql:" in url.lower():
        engine = "postgresql"
    elif "jdbc:mysql:" in url.lower():
        engine = "mysql"
    elif "jdbc:" in url.lower():
        match = re.match(r"jdbc:([^:]+):", url, re.IGNORECASE)
        if match:
            engine = match.group(1).lower()

    file_path = None
    path_match = re.search(r"jdbc:h2:(?:file:)?(.+?)(?:;|$)", url, re.IGNORECASE)
    if path_match:
        file_path = os.path.abspath(os.path.expanduser(path_match.group(1)))

    param_keys = []
    for part in url.split(";")[1:]:
        if "=" in part:
            key = part.split("=", 1)[0].strip()
            if key:
                param_keys.append(key.upper())

    sensitive_keys = [
        k for k in param_keys if _SENSITIVE_PROPERTY_KEY_RE.search(k) or k in ("USER", "USERNAME", "PASSWORD", "PWD")
    ]

    return {
        "engine": engine,
        "file_path": file_path,
        "param_count": len(param_keys),
        "has_embedded_credentials": bool(sensitive_keys),
        "credential_param_names": sensitive_keys,  # names only, never values
        "redacted": True,
    }


def _safe_property_summary(properties: Dict[str, str]) -> Dict[str, Any]:
    """Return non-sensitive config hints from application.properties."""
    summary: Dict[str, Any] = {
        "keys_present": sorted(properties.keys()),
        "sensitive_keys_present": [],
        "datasource_url": None,
    }
    for key, value in properties.items():
        if _SENSITIVE_PROPERTY_KEY_RE.search(key):
            summary["sensitive_keys_present"].append(key)
            continue
        if key.lower() in (
            "spring.datasource.url",
            "database.url",
            "db.url",
            "datasource.url",
            "jdbc.url",
        ):
            summary["datasource_url"] = redact_jdbc_url(value)
    return summary


def _format_bytes(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def _java_version() -> Tuple[bool, str, Optional[int], bool]:
    java_bin = get_java_bin_path()
    if not java_bin or (java_bin != "java" and not os.path.exists(java_bin)):
        # get_java_bin_path may return "java" from PATH
        if shutil.which("java") is None and java_bin == "java":
            return False, "Java not found on PATH", None, False
    try:
        result = subprocess.run(
            [java_bin if java_bin else "java", "-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # java -version writes to stderr
        output = (result.stderr or result.stdout or "").strip().splitlines()
        line = output[0] if output else "java present (version unknown)"
        major = get_java_major_version(java_bin if java_bin else "java")
        meets_min = major is not None and major >= GEOWEAVER_MIN_JAVA_MAJOR
        return True, line, major, meets_min
    except Exception as exc:
        return False, f"Unable to run java: {exc}", None, False


def _http_endpoint_status() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "url": GEOWEAVER_DEFAULT_ENDPOINT_URL,
        "reachable": False,
        "http_status": None,
        "error": None,
    }
    try:
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL, allow_redirects=False, timeout=5)
        info["reachable"] = True
        info["http_status"] = response.status_code
    except requests.RequestException as exc:
        info["error"] = type(exc).__name__
    return info


def _process_info() -> Dict[str, Any]:
    running = False
    pids: List[int] = []
    try:
        running = check_geoweaver_status()
    except Exception:
        running = is_geoweaver_process_running()

    try:
        if hasattr(os, "getuid"):
            procs = find_geoweaver_processes(os.getuid())
            pids = [int(p.info["pid"]) for p in procs if p.info.get("pid")]
    except Exception:
        pass

    return {
        "running": bool(running or pids),
        "pids": pids,
        "process_detected": is_geoweaver_process_running(),
    }


def _db_status(db_path: Optional[str] = None) -> Dict[str, Any]:
    resolved = resolve_h2_db_path(db_path)
    mv_path = get_h2_mv_db_path(resolved)
    size_bytes = get_h2_database_size_bytes(resolved)
    size_mb = size_bytes / (1024 * 1024) if size_bytes else 0.0

    trace_path = mv_path.replace(".mv.db", ".trace.db")
    lock_candidates = [
        mv_path + ".lock",
        resolved + ".lock.db",
        os.path.join(os.path.dirname(mv_path), os.path.basename(resolved) + ".lock.db"),
    ]

    status: Dict[str, Any] = {
        "path": resolved,
        "mv_db_path": mv_path,
        "exists": os.path.exists(mv_path),
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
        "size_mb": round(size_mb, 2),
        "oversized": size_mb >= H2_AUTO_REBUILD_THRESHOLD_MB,
        "rebuild_threshold_mb": H2_AUTO_REBUILD_THRESHOLD_MB,
        "trace_db_present": os.path.exists(trace_path),
        "file_lock_present": any(os.path.exists(p) for p in lock_candidates),
        "readable": None,
        "inventory": None,
        "inventory_error": None,
        "note": None,
    }

    props_url = get_database_url_from_properties()
    status["configured_url"] = redact_jdbc_url(props_url)

    geoweaver_up = is_geoweaver_process_running()
    if not status["exists"]:
        status["note"] = "No H2 database file found"
        status["readable"] = False
        return status

    if geoweaver_up:
        status["note"] = "Geoweaver is running; skipping open/inventory checks to avoid lock contention"
        return status

    try:
        status["readable"] = verify_h2_database(resolved)
    except Exception as exc:
        status["readable"] = False
        status["inventory_error"] = f"verify failed: {type(exc).__name__}"
        return status

    if status["readable"]:
        inventory, inv_error = capture_table_inventory(resolved)
        if inv_error:
            status["inventory_error"] = inv_error
            # Ensure inventory errors never echo passwords from JDBC tooling
            if status["inventory_error"]:
                status["inventory_error"] = _JDBC_SENSITIVE_PARAM_RE.sub(
                    r"\1=<redacted>", status["inventory_error"]
                )
        else:
            status["inventory"] = inventory

    return status


def _maintenance_status() -> Dict[str, Any]:
    state = _load_maintenance_state()
    lock_path = _maintenance_lock_path()
    backup_root = get_h2_backup_base_dir()
    backup_count = 0
    if os.path.isdir(backup_root):
        backup_count = sum(
            1 for name in os.listdir(backup_root) if os.path.isdir(os.path.join(backup_root, name))
        )

    # Only expose non-sensitive state fields
    safe_state = {
        "last_maintenance_at": state.get("last_maintenance_at"),
        "last_maintenance_action": state.get("last_maintenance_action"),
        "last_maintenance_size_mb": state.get("last_maintenance_size_mb"),
        "interrupted_maintenance": bool(state.get("interrupted_maintenance")),
        "pending_rebuild": bool(state.get("pending_rebuild")),
    }

    return {
        "state": safe_state,
        "lock_present": os.path.exists(lock_path),
        "backup_root": backup_root,
        "backup_count": backup_count,
    }


def collect_geoweaver_status(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Collect a full Geoweaver status report with secrets redacted."""
    home = get_home_dir()
    jar_path = os.path.join(home, "geoweaver.jar")
    props_path = _geoweaver_properties_path()
    log_path = get_log_file_path()
    java_ok, java_msg, java_major, java_meets_min = _java_version()
    h2_jar = get_h2_jar_path()

    properties = read_properties_file(props_path) if os.path.exists(props_path) else {}

    report: Dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "pygeoweaver_version": __version__,
        "endpoint": _http_endpoint_status(),
        "process": _process_info(),
        "java": {
            "available": java_ok,
            "detail": java_msg,
            "major": java_major,
            "meets_min_version": java_meets_min,
            "min_required_major": GEOWEAVER_MIN_JAVA_MAJOR,
        },
        "geoweaver_jar": {
            "path": jar_path,
            "exists": os.path.exists(jar_path),
            "size_human": _format_bytes(os.path.getsize(jar_path)) if os.path.exists(jar_path) else "n/a",
        },
        "h2_tool_jar": {
            "path": h2_jar,
            "exists": bool(h2_jar and os.path.exists(h2_jar)),
        },
        "config": {
            "properties_path": props_path,
            "properties_exists": os.path.exists(props_path),
            "summary": _safe_property_summary(properties) if properties else None,
            # Never report .secret path, presence, or contents (localhost password).
            "localhost_credentials": "redacted",
        },
        "database": _db_status(db_path),
        "maintenance": _maintenance_status(),
        "log": {
            "path": log_path,
            "exists": os.path.exists(log_path) if log_path else False,
            "size_human": _format_bytes(os.path.getsize(log_path))
            if log_path and os.path.exists(log_path)
            else "n/a",
        },
        "port": GEOWEAVER_PORT,
        "credentials_redacted": True,
    }
    return report


def _print_section(title: str) -> None:
    click.echo()
    click.echo(click.style(title, bold=True, fg="cyan"))
    click.echo("-" * len(title))


def print_status_report(report: Dict[str, Any]) -> None:
    """Pretty-print a status report to the terminal."""
    click.echo(click.style("Geoweaver Status", bold=True, fg="bright_white"))
    click.echo(f"Checked at: {report['checked_at']}")
    click.echo(f"pygeoweaver: {report['pygeoweaver_version']}")
    click.echo(click.style("Credentials are redacted in this report.", fg="yellow"))

    _print_section("Runtime")
    proc = report["process"]
    if proc["running"]:
        click.echo(click.style("  Geoweaver process: RUNNING", fg="green", bold=True))
    else:
        click.echo(click.style("  Geoweaver process: STOPPED", fg="red", bold=True))
    if proc.get("pids"):
        click.echo(f"  PIDs: {', '.join(str(p) for p in proc['pids'])}")

    endpoint = report["endpoint"]
    if endpoint["reachable"]:
        click.echo(
            click.style(
                f"  HTTP {endpoint['url']}: reachable (status {endpoint['http_status']})",
                fg="green",
            )
        )
    else:
        click.echo(
            click.style(
                f"  HTTP {endpoint['url']}: not reachable ({endpoint.get('error') or 'n/a'})",
                fg="yellow",
            )
        )

    java = report["java"]
    click.echo(
        ("  Java: " + click.style("OK", fg="green") if java["available"] else "  Java: " + click.style("MISSING", fg="red"))
        + f" — {java['detail']}"
    )
    if java.get("available") and java.get("meets_min_version") is False:
        click.echo(
            click.style(
                f"  WARNING: Java {java.get('major')} < required {java.get('min_required_major')}. "
                "Latest Geoweaver no longer supports JDK < 17; use Geoweaver 2.1.x or upgrade Java.",
                fg="yellow",
                bold=True,
            )
        )
        print_unsupported_java_warning(java.get("major"))
    jar = report["geoweaver_jar"]
    click.echo(
        f"  geoweaver.jar: {'present' if jar['exists'] else 'MISSING'} ({jar['path']}, {jar['size_human']})"
    )
    h2j = report["h2_tool_jar"]
    click.echo(
        f"  H2 tool JAR: {'present' if h2j['exists'] else 'MISSING'}"
        + (f" ({h2j['path']})" if h2j.get("path") else "")
    )

    _print_section("Configuration")
    cfg = report["config"]
    click.echo(
        f"  application.properties: {'present' if cfg['properties_exists'] else 'absent'} ({cfg['properties_path']})"
    )
    click.echo("  localhost credentials: redacted")
    summary = cfg.get("summary") or {}
    if summary.get("sensitive_keys_present"):
        click.echo(
            f"  Sensitive property keys present (values hidden): {', '.join(summary['sensitive_keys_present'])}"
        )
    ds = summary.get("datasource_url")
    if ds:
        click.echo(
            f"  Datasource: engine={ds.get('engine')} path={ds.get('file_path') or 'n/a'} "
            f"embedded_credentials={ds.get('has_embedded_credentials')}"
        )

    _print_section("Database (H2)")
    db = report["database"]
    click.echo(f"  Path: {db['path']}")
    click.echo(f"  File: {db['mv_db_path']}")
    if not db["exists"]:
        click.echo(click.style("  Status: FILE MISSING", fg="red", bold=True))
    else:
        click.echo(f"  Size: {db['size_human']} ({db['size_mb']} MB)")
        if db["oversized"]:
            click.echo(
                click.style(
                    f"  Warning: size ≥ rebuild threshold ({db['rebuild_threshold_mb']} MB). "
                    "Consider: gw cleanh2db",
                    fg="yellow",
                )
            )
        if db["readable"] is True:
            click.echo(click.style("  Open check: OK", fg="green"))
        elif db["readable"] is False:
            click.echo(click.style("  Open check: FAILED", fg="red"))
        else:
            click.echo("  Open check: skipped")
        if db.get("note"):
            click.echo(f"  Note: {db['note']}")
        if db.get("inventory"):
            click.echo("  Table inventory:")
            for table, count in db["inventory"].items():
                click.echo(f"    - {table}: {count if count is not None else 'missing'}")
        if db.get("inventory_error"):
            click.echo(click.style(f"  Inventory error: {db['inventory_error']}", fg="yellow"))
        if db.get("file_lock_present"):
            click.echo(click.style("  On-disk lock file detected", fg="yellow"))
        if db.get("trace_db_present"):
            click.echo("  trace.db present: yes")

    _print_section("Maintenance")
    maint = report["maintenance"]
    st = maint["state"]
    click.echo(f"  Last action: {st.get('last_maintenance_action') or 'n/a'} at {st.get('last_maintenance_at') or 'n/a'}")
    click.echo(f"  Interrupted flag: {st.get('interrupted_maintenance')}")
    click.echo(f"  Pending rebuild flag: {st.get('pending_rebuild')}")
    click.echo(f"  Maintenance lock present: {maint['lock_present']}")
    click.echo(f"  Backup root: {maint['backup_root']} ({maint['backup_count']} backup dirs)")
    if maint["backup_count"]:
        click.echo("  Manage backups: gw cleanh2backups")

    _print_section("Logs")
    log = report["log"]
    click.echo(f"  Path: {log['path']}")
    click.echo(f"  Exists: {log['exists']} ({log['size_human']})")
    click.echo()


def show_geoweaver_status(
    db_path: Optional[str] = None,
    as_json: bool = False,
) -> Dict[str, Any]:
    """Collect and print Geoweaver status. Returns the report dict."""
    report = collect_geoweaver_status(db_path=db_path)
    if as_json:
        click.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_status_report(report)
    return report
