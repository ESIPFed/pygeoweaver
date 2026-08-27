"""
Tests for impatient-user scenarios: repeated gw start/stop, Ctrl+C, and data safety.
"""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import pygeoweaver.h2_utils as h2_utils


def _db_layout(tmp_path, db_name="gw", production_data=b"production-db"):
    db_dir = tmp_path / "h2"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / db_name
    (db_dir / f"{db_name}.mv.db").write_bytes(production_data)
    return str(db_path), db_dir


def _backup_layout(tmp_path, backup_name, backup_data, *, in_progress=True):
    backup_root = tmp_path / "geoweaver" / "h2_backups"
    work_dir = backup_root / backup_name
    original_dir = work_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)
    (original_dir / "gw.mv.db").write_bytes(backup_data)
    if in_progress:
        (work_dir / ".in_progress").write_text("{}", encoding="utf-8")
    return str(work_dir)


def _maintenance_state(tmp_path, monkeypatch, **values):
    geoweaver_dir = tmp_path / "geoweaver"
    geoweaver_dir.mkdir(parents=True, exist_ok=True)
    state_path = geoweaver_dir / "h2_maintenance_state.json"
    if values:
        state_path.write_text(json.dumps(values), encoding="utf-8")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    return state_path


@contextmanager
def _guard_always_run(_trigger=None):
    yield True


@contextmanager
def _guard_blocked(_trigger=None):
    yield False


def _verify_reads_production_health(resolved_db_path, **kwargs):
    mv_db_path = h2_utils.get_h2_mv_db_path(resolved_db_path)
    if not os.path.exists(mv_db_path):
        return False
    content = open(mv_db_path, "rb").read()
    return content not in (b"broken", b"broken-after-stop", b"")


def test_recover_from_interrupted_maintenance_restores_original_backup(tmp_path, monkeypatch):
    db_path, db_dir = _db_layout(tmp_path, production_data=b"broken")
    _backup_layout(tmp_path, "geoweaver_h2_backup_test", b"good-backup")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))

    with patch.object(h2_utils, "verify_h2_database", side_effect=[False, True]):
        recovered = h2_utils.recover_from_interrupted_maintenance(db_path=db_path)

    assert recovered is True
    assert (db_dir / "gw.mv.db").read_bytes() == b"good-backup"
    assert not (tmp_path / "geoweaver" / "h2_backups" / "geoweaver_h2_backup_test" / ".in_progress").exists()


def test_recover_prefers_newest_interrupted_backup(tmp_path, monkeypatch):
    db_path, db_dir = _db_layout(tmp_path, production_data=b"broken")
    older = _backup_layout(tmp_path, "backup_old", b"older-data")
    newer = _backup_layout(tmp_path, "backup_new", b"newer-data")
    os.utime(older, (1, 1))
    os.utime(newer, None)
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))

    with patch.object(h2_utils, "verify_h2_database", side_effect=[False, True]):
        assert h2_utils.recover_from_interrupted_maintenance(db_path=db_path) is True

    assert (db_dir / "gw.mv.db").read_bytes() == b"newer-data"


def test_acquire_maintenance_lock_blocks_second_process(tmp_path, monkeypatch):
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    assert h2_utils.acquire_maintenance_lock(wait_seconds=1) is True
    assert h2_utils.acquire_maintenance_lock(wait_seconds=1) is False
    h2_utils.release_maintenance_lock()
    assert h2_utils.acquire_maintenance_lock(wait_seconds=1) is True
    h2_utils.release_maintenance_lock()


def test_stale_maintenance_lock_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    lock_path = tmp_path / "geoweaver" / "h2_maintenance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": 999999999, "started_at": "2000-01-01T00:00:00"}),
        encoding="utf-8",
    )

    assert h2_utils.acquire_maintenance_lock(wait_seconds=1) is True
    h2_utils.release_maintenance_lock()


def test_maintenance_guard_does_not_recover_on_keyboard_interrupt(tmp_path, monkeypatch):
    _db_layout(tmp_path)
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))

    with patch.object(h2_utils, "recover_from_interrupted_maintenance", return_value=True) as mock_recover:
        try:
            with h2_utils.h2_maintenance_guard("stop") as should_run:
                assert should_run is True
                raise KeyboardInterrupt
        except KeyboardInterrupt:
            pass

    # recover runs once at guard entry, never again on interrupt
    assert mock_recover.call_count == 1
    assert not os.path.exists(h2_utils._maintenance_lock_path())


def test_sigint_marks_interrupted_without_pending_rebuild(tmp_path, monkeypatch):
    state_path = _maintenance_state(tmp_path, monkeypatch)
    monkeypatch.setattr(h2_utils, "H2_MAINTENANCE_LOCK_WAIT_STOP_SECONDS", 1)

    handler = None

    def capture_signal(signum, fn):
        nonlocal handler
        if signum == __import__("signal").SIGINT:
            handler = fn
        return fn

    with patch.object(h2_utils, "recover_from_interrupted_maintenance", return_value=True) as mock_recover:
        with patch.object(h2_utils.signal, "signal", side_effect=capture_signal):
            with patch.object(h2_utils, "acquire_maintenance_lock", return_value=True):
                with pytest.raises(KeyboardInterrupt):
                    with h2_utils.h2_maintenance_guard("stop") as should_run:
                        assert should_run is True
                        handler(__import__("signal").SIGINT, None)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["interrupted_maintenance"] is True
    assert state.get("pending_rebuild") is not True
    # recover only at entry, not from signal handler
    assert mock_recover.call_count == 1


def test_impatient_double_stop_skips_second_maintenance(tmp_path, monkeypatch):
    db_path, _ = _db_layout(tmp_path, production_data=b"x" * (200 * 1024 * 1024))
    state_path = _maintenance_state(
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
        with patch.object(h2_utils, "verify_h2_database", return_value=True):
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
            mock_compact.assert_not_called()

    state = json.loads(state_path.read_text(encoding="utf-8"))


def test_impatient_stop_then_start_recovers_unreadable_db(tmp_path, monkeypatch):
    db_path, db_dir = _db_layout(tmp_path, production_data=b"broken-after-stop")
    _backup_layout(tmp_path, "backup_after_stop", b"recovered-data")
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

    with patch.object(h2_utils, "verify_h2_database", side_effect=_verify_reads_production_health):
        with patch.object(h2_utils, "compact_h2_database") as mock_compact:
            assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
            assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is True
            mock_compact.assert_not_called()

    assert (db_dir / "gw.mv.db").read_bytes() == b"recovered-data"


def test_impatient_start_start_second_is_noop(tmp_path, monkeypatch):
    with patch("pygeoweaver.server.download_geoweaver_jar"):
        with patch("pygeoweaver.server.check_java"):
            with patch("pygeoweaver.server.check_geoweaver_status", return_value=True):
                with patch("pygeoweaver.server.prepare_h2_database_for_start") as mock_prepare:
                    with patch("pygeoweaver.server.start_on_mac_linux") as mock_start:
                        with patch("pygeoweaver.server.check_os", return_value=2):
                            from pygeoweaver.server import start

                            start(exit_on_finish=False)
                            start(exit_on_finish=False)
                            mock_prepare.assert_not_called()
                            mock_start.assert_not_called()


def test_force_restart_stops_before_start():
    with patch("pygeoweaver.server.download_geoweaver_jar"):
        with patch("pygeoweaver.server.check_java"):
            with patch("pygeoweaver.server.stop") as mock_stop:
                with patch("pygeoweaver.server.check_geoweaver_status", return_value=True):
                    with patch("pygeoweaver.server.prepare_h2_database_for_start", return_value=True):
                        with patch("pygeoweaver.server.start_on_mac_linux"):
                            with patch("pygeoweaver.server.check_os", return_value=2):
                                from pygeoweaver.server import start

                                start(force_restart=True, exit_on_finish=False)
                                mock_stop.assert_called_once_with(exit_on_finish=False, maintain_h2=False)


def test_start_aborts_when_h2_prepare_fails():
    with patch("pygeoweaver.server.download_geoweaver_jar"):
        with patch("pygeoweaver.server.check_java"):
            with patch("pygeoweaver.server.check_geoweaver_status", return_value=False):
                with patch("pygeoweaver.server.prepare_h2_database_for_start", return_value=False):
                    with patch("pygeoweaver.server.start_on_mac_linux") as mock_start:
                        with patch("pygeoweaver.server.check_os", return_value=2):
                            from pygeoweaver.server import start

                            start(exit_on_finish=False)
                            mock_start.assert_not_called()


def test_double_stop_without_running_processes_is_safe():
    with patch("pygeoweaver.server.check_java"):
        with patch("pygeoweaver.server.check_os", return_value=2):
            with patch("pygeoweaver.server.find_geoweaver_processes", return_value=[]):
                with patch("pygeoweaver.server.warn_oversized_h2_on_lifecycle"):
                    with patch("pygeoweaver.server.maintain_h2_database_on_stop") as mock_maintain:
                        with patch("pygeoweaver.server._wait_for_geoweaver_shutdown", return_value=True):
                            from pygeoweaver.server import stop_on_mac_linux

                            assert stop_on_mac_linux(exit_on_finish=False) == 0
                            assert stop_on_mac_linux(exit_on_finish=False) == 0
                            mock_maintain.assert_not_called()


def test_default_stop_does_not_rebuild_oversized_db(tmp_path, monkeypatch):
    db_path, _ = _db_layout(tmp_path, production_data=b"x" * (200 * 1024))
    # Pretend the file is huge without allocating gigabytes
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "get_h2_database_size_bytes", lambda _=None: 2 * 1024 * 1024 * 1024)
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "rebuild_h2_database_safely") as mock_rebuild:
        with patch.object(h2_utils, "compact_h2_database") as mock_compact:
            with patch.object(h2_utils, "verify_h2_database", return_value=True):
                assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
                mock_rebuild.assert_not_called()
                mock_compact.assert_not_called()


def test_cleanh2db_refuses_when_maintenance_lock_is_busy():
    with patch("pygeoweaver.commands.pgw_cleanh2db.check_java"):
        with patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False):
            with patch("pygeoweaver.commands.pgw_cleanh2db.stop"):
                with patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value="h2.jar"):
                    with patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner"):
                        with patch("pygeoweaver.commands.pgw_cleanh2db.h2_maintenance_guard", _guard_blocked):
                            with patch("pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely") as mock_rebuild:
                                with patch("pygeoweaver.commands.pgw_cleanh2db.start") as mock_start:
                                    from pygeoweaver.commands.pgw_cleanh2db import clean_h2db

                                    assert clean_h2db(db_path="/tmp/gw") is False
                                    mock_rebuild.assert_not_called()
                                    mock_start.assert_not_called()


def test_cleanh2db_success_releases_guard_and_starts(tmp_path, monkeypatch):
    with patch("pygeoweaver.commands.pgw_cleanh2db.check_java"):
        with patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False):
            with patch("pygeoweaver.commands.pgw_cleanh2db.stop"):
                with patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value="h2.jar"):
                    with patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner"):
                        with patch("pygeoweaver.commands.pgw_cleanh2db.h2_maintenance_guard", _guard_always_run):
                            with patch(
                                "pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely",
                                return_value=(True, "/tmp/backup"),
                            ) as mock_rebuild:
                                with patch("pygeoweaver.commands.pgw_cleanh2db.start") as mock_start:
                                    from pygeoweaver.commands.pgw_cleanh2db import clean_h2db

                                    assert clean_h2db(db_path="/tmp/gw") is True
                                    mock_rebuild.assert_called_once()
                                    mock_start.assert_called_once()


def test_interrupted_empty_production_restored_before_next_start(tmp_path, monkeypatch):
    db_path, db_dir = _db_layout(tmp_path, production_data=b"broken")
    _backup_layout(tmp_path, "backup_empty_prod", b"restored-by-next-start")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    with patch.object(h2_utils, "verify_h2_database", side_effect=_verify_reads_production_health):
        assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is True

    assert (db_dir / "gw.mv.db").read_bytes() == b"restored-by-next-start"


def test_concurrent_maintenance_skipped_on_stop_but_start_recovers(tmp_path, monkeypatch):
    db_path, db_dir = _db_layout(tmp_path, production_data=b"broken")
    _backup_layout(tmp_path, "backup_concurrent", b"safe-data")
    monkeypatch.setattr(h2_utils, "get_home_dir", lambda: str(tmp_path))
    monkeypatch.setattr(h2_utils, "H2_AUTO_MAINTENANCE", True)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    monkeypatch.setattr(h2_utils, "is_geoweaver_process_running", lambda: False)
    monkeypatch.setattr(h2_utils, "ensure_h2_safe_datasource_url", lambda: False)

    lock_attempts = {"count": 0}

    def fake_acquire(wait_seconds=None):
        lock_attempts["count"] += 1
        return lock_attempts["count"] == 1

    with patch.object(h2_utils, "acquire_maintenance_lock", side_effect=fake_acquire):
        with patch.object(h2_utils, "_wait_for_database_unlock", return_value=True):
            with patch.object(h2_utils, "compact_h2_database") as mock_compact:
                with patch.object(h2_utils, "verify_h2_database", side_effect=_verify_reads_production_health):
                    assert h2_utils.run_automatic_h2_maintenance("stop", db_path=db_path) is True
                    (db_dir / "gw.mv.db").write_bytes(b"broken")
                    assert h2_utils.run_automatic_h2_maintenance("start", db_path=db_path) is True
                    mock_compact.assert_not_called()

    assert (db_dir / "gw.mv.db").read_bytes() == b"safe-data"


def test_promote_failure_restores_original_bytes(tmp_path):
    production_dir = tmp_path / "production"
    rebuilt_dir = tmp_path / "rebuilt"
    displaced_dir = tmp_path / "displaced"
    original_dir = tmp_path / "original"
    for directory in (production_dir, rebuilt_dir, displaced_dir, original_dir):
        directory.mkdir()

    original_data = b"user-data-must-survive"
    (original_dir / "gw.mv.db").write_bytes(original_data)
    (production_dir / "gw.mv.db").write_bytes(original_data)

    promoted = h2_utils.promote_rebuilt_database(
        str(production_dir),
        str(rebuilt_dir),
        str(displaced_dir),
        "gw",
        str(original_dir),
    )

    assert promoted is False
    assert (production_dir / "gw.mv.db").read_bytes() == original_data
    assert (displaced_dir / "gw.mv.db").read_bytes() == original_data
