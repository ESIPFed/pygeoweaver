import json
import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import pygeoweaver.h2_utils as h2_utils


def _maintenance_state(tmp_path, monkeypatch, **values):
    geoweaver_dir = tmp_path / "geoweaver"
    geoweaver_dir.mkdir(parents=True, exist_ok=True)
    state_path = geoweaver_dir / "h2_maintenance_state.json"
    if values:
        state_path.write_text(json.dumps(values), encoding="utf-8")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    return state_path


def _db_layout(tmp_path, db_name="gw", size_bytes=1024):
    db_dir = tmp_path / "h2"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / db_name
    (db_dir / f"{db_name}.mv.db").write_bytes(b"x" * size_bytes)
    return str(db_path)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Database may be already in use", "locked"),
        ("Could not lock file", "locked"),
        ("Wrong user name or password", "auth"),
        ("Authentication failure for user", "auth"),
        ("some other failure", "unknown"),
    ],
)
def test_classify_h2_error(message, expected):
    assert h2_utils.classify_h2_error(message) == expected


def test_consecutive_automatic_maintenance_skips_second_run(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path, size_bytes=200 * 1024 * 1024)
    _maintenance_state(
        tmp_path,
        monkeypatch,
        last_maintenance_at=datetime.now().isoformat(),
        last_maintenance_action="compact",
    )
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_MAINTENANCE_COOLDOWN_SECONDS", 300)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "compact_h2_database") as mock_compact:
        with patch.object(h2_utils, "rebuild_h2_database_safely") as mock_rebuild:
            with patch.object(h2_utils, "verify_h2_database", return_value=True):
                assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
                mock_compact.assert_not_called()
                mock_rebuild.assert_not_called()


def test_pending_rebuild_triggers_rebuild_even_when_database_is_small(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path, size_bytes=80 * 1024 * 1024)
    _maintenance_state(tmp_path, monkeypatch, pending_rebuild=True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
        with patch.object(h2_utils, "rebuild_h2_database_safely", return_value=(True, "/tmp/backup")) as mock_rebuild:
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
            mock_rebuild.assert_called_once()


def test_rebuild_failure_sets_pending_rebuild(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path, size_bytes=2 * 1024 * 1024 * 1024)
    state_path = _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
        with patch.object(h2_utils, "rebuild_h2_database_safely", return_value=(False, "/tmp/backup")):
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pending_rebuild"] is True


def test_start_fails_when_database_unreadable_and_no_backup(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=False):
        with patch.object(h2_utils, "restore_from_latest_backup", return_value=False):
            with patch.object(h2_utils, "rebuild_h2_database_safely") as mock_rebuild:
                assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is False
                mock_rebuild.assert_not_called()


def test_start_restores_from_backup_when_database_unreadable(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=False):
        with patch.object(h2_utils, "restore_from_latest_backup", return_value=True) as mock_restore:
            with patch.object(h2_utils, "verify_h2_database", return_value=True):
                assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is True
                mock_restore.assert_called_once()


def test_geoweaver_still_running_blocks_start_maintenance(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: True)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "rebuild_h2_database_safely") as mock_rebuild:
        assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is False
        mock_rebuild.assert_not_called()


def test_geoweaver_still_running_allows_stop_to_complete_without_maintenance(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: True)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "compact_h2_database") as mock_compact:
        assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
        mock_compact.assert_not_called()


def test_rebuild_aborts_when_geoweaver_still_running(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: True)
    monkeypatch.setattr(h2_utils, "get_h2_jar_path", lambda *_args, **_kwargs: "h2.jar")

    success, work_dir = h2_utils.rebuild_h2_database_safely(db_path=db_path, force=True)
    assert success is False
    assert work_dir is None


def test_rebuild_aborts_when_database_locked_before_copy(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "H2_LOCK_RETRY_COUNT", 1)
    monkeypatch.setattr(h2_utils, "get_h2_jar_path", lambda *_args, **_kwargs: "h2.jar")

    production_file = tmp_path / "h2" / "gw.mv.db"
    original_bytes = production_file.read_bytes()

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=False):
        success, work_dir = h2_utils.rebuild_h2_database_safely(db_path=db_path, force=True)

    assert success is False
    assert work_dir is not None
    assert production_file.read_bytes() == original_bytes


def test_auth_failure_during_export_leaves_production_unchanged(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "get_h2_jar_path", lambda *_args, **_kwargs: "h2.jar")
    monkeypatch.setattr(h2_utils, "get_java_bin_path", lambda *_args, **_kwargs: "java")

    production_file = tmp_path / "h2" / "gw.mv.db"
    original_bytes = production_file.read_bytes()

    auth_error = subprocess.CalledProcessError(
        1,
        "java",
        stderr="Wrong user name or password",
    )

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
        with patch("pygeoweaver.h2_utils.subprocess.run", side_effect=auth_error):
            success, work_dir = h2_utils.rebuild_h2_database_safely(
                db_path=db_path,
                force=True,
                db_username="geoweaver",
                password="bad-password",
            )

    assert success is False
    assert work_dir is not None
    assert production_file.read_bytes() == original_bytes
    assert (tmp_path / "h2" / "gw.mv.db").exists()


def test_compact_auth_failure_sets_pending_rebuild_on_stop(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path, size_bytes=200 * 1024 * 1024)
    state_path = _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "H2_COMPACT_MIN_MB", 50)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
        with patch.object(h2_utils, "compact_h2_database", return_value=False):
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pending_rebuild"] is True


def test_consecutive_rebuilds_create_unique_work_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    first = h2_utils.create_timestamped_work_dir(str(backup_root))
    second = h2_utils.create_timestamped_work_dir(str(backup_root))

    assert first != second
    assert first.startswith(str(backup_root))
    assert second.startswith(str(backup_root))


def test_cleanh2db_can_run_twice_and_force_rebuild_each_time():
    with patch("pygeoweaver.commands.pgw_cleanh2db.check_java"):
        with patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False):
            with patch("pygeoweaver.commands.pgw_cleanh2db.stop"):
                with patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value="h2.jar"):
                    with patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner"):
                        with patch("pygeoweaver.commands.pgw_cleanh2db.start"):
                            with patch(
                                "pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely",
                                side_effect=[(True, "/tmp/backup-1"), (True, "/tmp/backup-2")],
                            ) as mock_rebuild:
                                from pygeoweaver.commands.pgw_cleanh2db import clean_h2db

                                assert clean_h2db(db_path="/tmp/gw") is True
                                assert clean_h2db(db_path="/tmp/gw") is True
                                assert mock_rebuild.call_count == 2
                                assert all(call.kwargs.get("force") is True for call in mock_rebuild.call_args_list)


def test_recent_maintenance_skip_still_restores_unreadable_database_on_start(tmp_path, monkeypatch):
    db_path = _db_layout(tmp_path)
    _maintenance_state(
        tmp_path,
        monkeypatch,
        last_maintenance_at=datetime.now().isoformat(),
        last_maintenance_action="rebuild",
    )
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_MAINTENANCE_COOLDOWN_SECONDS", 300)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "verify_h2_database", return_value=False):
        with patch.object(h2_utils, "restore_from_latest_backup", return_value=True) as mock_restore:
            assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is True
            mock_restore.assert_called_once()
