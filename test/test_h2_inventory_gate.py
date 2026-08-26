"""Unit tests for H2 inventory gates, retry classification, and fail-closed recover."""

import json
from unittest.mock import patch

import pygeoweaver.h2_utils as h2_utils


def test_inventory_meets_baseline_rejects_workflow_shrink():
    ok, reason = h2_utils.inventory_meets_baseline(
        {"WORKFLOW": 5, "GWPROCESS": 2, "HOST": 1},
        {"WORKFLOW": 0, "GWPROCESS": 2, "HOST": 1},
    )
    assert ok is False
    assert "WORKFLOW" in reason


def test_inventory_meets_baseline_accepts_equal_strict_tables():
    ok, reason = h2_utils.inventory_meets_baseline(
        {"WORKFLOW": 5, "GWPROCESS": 2, "HOST": 1, "HISTORY": 100},
        {"WORKFLOW": 5, "GWPROCESS": 2, "HOST": 1, "HISTORY": 90},
    )
    assert ok is True
    assert reason == "ok"


def test_production_needs_restore_when_empty_but_backup_has_workflows():
    assert (
        h2_utils.production_needs_restore_from_backup(
            {"WORKFLOW": 0, "GWPROCESS": 0, "HOST": 0},
            {"WORKFLOW": 3, "GWPROCESS": 1, "HOST": 1},
        )
        is True
    )


def test_production_needs_restore_when_inventory_unavailable():
    assert (
        h2_utils.production_needs_restore_from_backup(
            None,
            {"WORKFLOW": 3, "GWPROCESS": 1, "HOST": 1},
        )
        is True
    )


def test_classify_h2_error_timeout_and_fatal():
    assert h2_utils.classify_h2_error("H2 import timed out after 10s") == "timeout"
    assert h2_utils.classify_h2_error("No space left on device") == "fatal"
    assert h2_utils.classify_h2_error("Wrong user name or password") == "auth"
    assert h2_utils.classify_h2_error("Database may be already in use") == "locked"


def test_sql_export_suggests_workflow_data(tmp_path):
    sql_file = tmp_path / "gw_backup.sql"
    sql_file.write_text(
        "CREATE TABLE WORKFLOW(...);\nINSERT INTO PUBLIC.WORKFLOW VALUES('a');\n",
        encoding="utf-8",
    )
    assert h2_utils.sql_export_suggests_workflow_data(str(sql_file)) is True


def test_recover_restores_empty_openable_prod_when_inventory_says_backup_has_data(
    tmp_path, monkeypatch
):
    db_dir = tmp_path / "h2"
    db_dir.mkdir()
    db_path = db_dir / "gw"
    (db_dir / "gw.mv.db").write_bytes(b"empty-but-openable")

    work_dir = tmp_path / "geoweaver" / "h2_backups" / "geoweaver_h2_backup_test"
    original = work_dir / "original"
    original.mkdir(parents=True)
    (original / "gw.mv.db").write_bytes(b"full-backup-with-workflows")
    (work_dir / ".in_progress").write_text("{}", encoding="utf-8")
    (work_dir / "pre_inventory.json").write_text(
        json.dumps(
            {
                "tables": {
                    "WORKFLOW": 4,
                    "GWPROCESS": 2,
                    "HOST": 1,
                    "HISTORY": 10,
                    "ENVIRONMENT": 0,
                    "WORKFLOW_CHECKPOINT": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))

    with patch.object(h2_utils, "verify_h2_database", side_effect=[True, True]):
        with patch.object(
            h2_utils,
            "capture_table_inventory",
            return_value=({"WORKFLOW": 0, "GWPROCESS": 0, "HOST": 0}, None),
        ):
            recovered = h2_utils.recover_from_interrupted_maintenance(db_path=str(db_path))

    assert recovered is True
    assert (db_dir / "gw.mv.db").read_bytes() == b"full-backup-with-workflows"


def test_rebuild_refuses_promote_when_inventory_shrinks(tmp_path, monkeypatch):
    db_dir = tmp_path / "h2"
    db_dir.mkdir()
    db_path = db_dir / "gw"
    (db_dir / "gw.mv.db").write_bytes(b"production-db")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "get_h2_jar_path", lambda *_a, **_k: "h2.jar")
    monkeypatch.setattr(h2_utils, "get_java_bin_path", lambda *_a, **_k: "java")

    pre = {"WORKFLOW": 3, "GWPROCESS": 1, "HOST": 1, "HISTORY": 5}
    post = {"WORKFLOW": 0, "GWPROCESS": 1, "HOST": 1, "HISTORY": 5}

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
        with patch.object(h2_utils, "capture_table_inventory", side_effect=[(pre, None), (post, None)]):
            with patch.object(h2_utils, "run_h2_tool_with_retry", return_value=(True, "")):
                with patch.object(h2_utils, "_validate_sql_export", return_value=True):
                    with patch.object(h2_utils, "sql_export_suggests_workflow_data", return_value=False):
                        with patch.object(h2_utils, "verify_h2_database", return_value=True):
                            with patch.object(h2_utils, "promote_rebuilt_database") as mock_promote:
                                success, work_dir = h2_utils.rebuild_h2_database_safely(
                                    db_path=str(db_path), force=True
                                )

    assert success is False
    assert work_dir is not None
    mock_promote.assert_not_called()
    assert (db_dir / "gw.mv.db").read_bytes() == b"production-db"


def test_run_h2_tool_with_retry_retries_lock_then_succeeds(monkeypatch):
    monkeypatch.setattr(h2_utils, "H2_EXPORT_IMPORT_RETRY_COUNT", 3)
    monkeypatch.setattr(h2_utils, "H2_EXPORT_IMPORT_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(h2_utils, "H2_TOOL_HEARTBEAT_SECONDS", 1)
    monkeypatch.setattr(h2_utils, "H2_EXPORT_IMPORT_TIMEOUT_SECONDS", 30)

    class FakeProc:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self._stdout = stdout
            self._stderr = stderr
            self.pid = 123

        def communicate(self, timeout=None):
            return self._stdout, self._stderr

        def kill(self):
            return None

    calls = {"n": 0}

    def fake_popen(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeProc(1, stderr="Database may be already in use")
        return FakeProc(0, stdout="ok")

    with patch("pygeoweaver.h2_utils.subprocess.Popen", side_effect=fake_popen):
        ok, err = h2_utils.run_h2_tool_with_retry(["java"], phase="export")

    assert ok is True
    assert err == ""
    assert calls["n"] == 2


def test_cli_help_does_not_describe_delete_then_import():
    from click.testing import CliRunner
    from pygeoweaver.__main__ import geoweaver

    runner = CliRunner()
    result = runner.invoke(geoweaver, ["cleanh2db", "--help"])
    assert result.exit_code == 0
    assert "Remove the original database files" not in result.output
    assert "verify-then-promote" in result.output.lower() or "Promote" in result.output
