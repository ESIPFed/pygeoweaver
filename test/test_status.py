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
            "java": {
                "available": True,
                "detail": "openjdk",
                "major": 17,
                "meets_min_version": True,
                "min_required_major": 17,
            },
            "geoweaver_jar": {
                "path": "/tmp/geoweaver.jar",
                "exists": False,
                "size_human": "n/a",
                "version": None,
                "channel": None,
            },
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


def test_get_geoweaver_jar_version_from_manifest(tmp_path):
    import zipfile

    from pygeoweaver.constants import GEOWEAVER_JAR_CHANNEL_LATEST, GEOWEAVER_JAR_CHANNEL_LEGACY
    from pygeoweaver.utils import (
        get_geoweaver_jar_version,
        infer_geoweaver_jar_channel,
        resolve_geoweaver_jar_channel,
    )

    jar = tmp_path / "geoweaver.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\n"
            "Implementation-Title: geoweaver\n"
            "Implementation-Version: 2.1.1\n"
            "Main-Class: org.springframework.boot.loader.JarLauncher\n",
        )

    assert get_geoweaver_jar_version(str(jar)) == "2.1.1"
    assert infer_geoweaver_jar_channel("2.1.1") == GEOWEAVER_JAR_CHANNEL_LEGACY
    assert infer_geoweaver_jar_channel("2.2.0") == GEOWEAVER_JAR_CHANNEL_LATEST
    assert infer_geoweaver_jar_channel("2.2.0-SNAPSHOT") == GEOWEAVER_JAR_CHANNEL_LATEST
    # Jar version wins over a stale home-dir channel marker (CI often has one).
    with patch(
        "pygeoweaver.utils.read_geoweaver_jar_channel",
        return_value=GEOWEAVER_JAR_CHANNEL_LATEST,
    ):
        assert resolve_geoweaver_jar_channel(str(jar)) == GEOWEAVER_JAR_CHANNEL_LEGACY


def test_resolve_channel_falls_back_to_marker_without_version(tmp_path):
    import zipfile

    from pygeoweaver.constants import GEOWEAVER_JAR_CHANNEL_LEGACY
    from pygeoweaver.utils import resolve_geoweaver_jar_channel

    jar = tmp_path / "geoweaver.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")

    with patch(
        "pygeoweaver.utils.read_geoweaver_jar_channel",
        return_value=GEOWEAVER_JAR_CHANNEL_LEGACY,
    ):
        assert resolve_geoweaver_jar_channel(str(jar)) == GEOWEAVER_JAR_CHANNEL_LEGACY


def test_get_geoweaver_jar_version_from_build_info(tmp_path):
    import zipfile

    from pygeoweaver.utils import get_geoweaver_jar_version

    jar = tmp_path / "geoweaver.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        zf.writestr(
            "META-INF/build-info.properties",
            "build.artifact=geoweaver\nbuild.version=2.2.0\n",
        )

    assert get_geoweaver_jar_version(str(jar)) == "2.2.0"
