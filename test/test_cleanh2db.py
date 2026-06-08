import tempfile
from contextlib import contextmanager
from unittest.mock import patch

from pygeoweaver.commands.pgw_cleanh2db import clean_h2db


@contextmanager
def _guard_always_run(_trigger=None):
    yield True


@patch("pygeoweaver.commands.pgw_cleanh2db.h2_maintenance_guard", _guard_always_run)
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely", return_value=(True, "/tmp/backup"))
@patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value="h2.jar")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
def test_cleanh2db_success(
    mock_spinner,
    mock_java,
    mock_stop,
    mock_status,
    mock_get_jar,
    mock_rebuild,
    mock_start,
):
    assert clean_h2db(db_path="/tmp/gw", db_username="geoweaver", password="pw") is True
    mock_rebuild.assert_called_once()


@patch("pygeoweaver.commands.pgw_cleanh2db.h2_maintenance_guard", _guard_always_run)
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely", return_value=(False, "/tmp/backup"))
@patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value="h2.jar")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
def test_cleanh2db_rebuild_failure(
    mock_spinner,
    mock_java,
    mock_stop,
    mock_status,
    mock_get_jar,
    mock_rebuild,
    mock_start,
):
    assert clean_h2db(db_path="/tmp/gw", db_username="geoweaver", password="pw") is False
    mock_start.assert_not_called()


@patch("pygeoweaver.commands.pgw_cleanh2db.rebuild_h2_database_safely")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_h2_jar_path", return_value=None)
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
def test_cleanh2db_missing_h2_jar(
    mock_spinner,
    mock_java,
    mock_stop,
    mock_status,
    mock_get_jar,
    mock_rebuild,
):
    assert clean_h2db(db_path="/tmp/gw", db_username="geoweaver", password="pw") is False
    mock_rebuild.assert_not_called()
