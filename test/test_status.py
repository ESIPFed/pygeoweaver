"""Tests for credential-safe Geoweaver status reporting."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from pygeoweaver.__main__ import geoweaver
from pygeoweaver.commands.pgw_status import (
    collect_geoweaver_status,
    redact_jdbc_url,
    show_geoweaver_status,
)


def test_redact_jdbc_url_strips_password_and_user():
    url = "jdbc:h2:file:/tmp/gw;USER=geoweaver;PASSWORD=super-secret;FOO=1"
    summary = redact_jdbc_url(url)
    assert summary is not None
    assert summary["engine"] == "h2"
    assert summary["file_path"].endswith("/gw") or summary["file_path"].endswith("\\gw")
    assert summary["has_embedded_credentials"] is True
    assert "PASSWORD" in summary["credential_param_names"]
    assert "USER" in summary["credential_param_names"]
    blob = json.dumps(summary)
    assert "super-secret" not in blob
    assert "geoweaver" not in blob or "USER" in summary["credential_param_names"]


def test_redact_jdbc_url_none():
    assert redact_jdbc_url(None) is None


def test_collect_status_never_embeds_default_db_password(tmp_path, monkeypatch):
    from pygeoweaver import constants

    db_dir = tmp_path / "h2"
    db_dir.mkdir()
    (db_dir / "gw.mv.db").write_bytes(b"x" * 100)

    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.resolve_h2_db_path",
        lambda db_path=None: str(db_dir / "gw"),
    )
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.get_h2_database_size_bytes",
        lambda db_path=None: 100,
    )
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.is_geoweaver_process_running",
        lambda: True,
    )
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.check_geoweaver_status",
        lambda: False,
    )
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.get_database_url_from_properties",
        lambda: f"jdbc:h2:file:{db_dir / 'gw'};PASSWORD={constants.GEOWEAVER_DEFAULT_DB_PASSWORD}",
    )

    report = collect_geoweaver_status()
    serialized = json.dumps(report)
    assert constants.GEOWEAVER_DEFAULT_DB_PASSWORD not in serialized
    assert ".secret" not in serialized
    assert report["config"]["localhost_credentials"] == "redacted"
    assert report["credentials_redacted"] is True
    assert report["database"]["configured_url"]["has_embedded_credentials"] is True


def test_status_cli_json(monkeypatch):
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_status.collect_geoweaver_status",
        lambda db_path=None: {
            "checked_at": "now",
            "credentials_redacted": True,
            "database": {"path": "/tmp/gw", "exists": False},
            "process": {"running": False, "pids": []},
            "endpoint": {"url": "http://localhost:8070/Geoweaver", "reachable": False},
            "java": {"available": True, "detail": "openjdk"},
            "geoweaver_jar": {"path": "/tmp/geoweaver.jar", "exists": False, "size_human": "n/a"},
            "h2_tool_jar": {"path": None, "exists": False},
            "config": {
                "properties_path": "/tmp/p",
                "properties_exists": False,
                "summary": None,
                "localhost_credentials": "redacted",
            },
            "maintenance": {
                "state": {},
                "lock_present": False,
                "backup_root": "/tmp/b",
                "backup_count": 0,
            },
            "log": {"path": "/tmp/l", "exists": False, "size_human": "n/a"},
            "pygeoweaver_version": "test",
            "port": "8070",
        },
    )
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["credentials_redacted"] is True
