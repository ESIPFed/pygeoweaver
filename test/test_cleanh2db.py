import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open
from pygeoweaver.commands.pgw_cleanh2db import clean_h2db
import builtins
import subprocess as sp

real_open = builtins.open
_real_subprocess_run = sp.run  # 保存原始引用

def selective_open_factory(sql_lines):
    def selective_open(file, mode='r', *args, **kwargs):
        if isinstance(file, str) and file.endswith("gw_backup.sql"):
            return mock_open(read_data="INSERT INTO ...;\n" * sql_lines)()
        return real_open(file, mode, *args, **kwargs)
    return selective_open

def make_temp_db_file(tmp_path, name="gw.db", size=1024):
    db_file = tmp_path / name
    db_file.write_bytes(b"0" * size)
    return str(db_file)

def make_temp_sql_file(tmp_path, name="gw_backup.sql", lines=20):
    sql_file = tmp_path / name
    sql_file.write_text("\n".join(["INSERT INTO ...;"] * lines))
    return str(sql_file)

def selective_run_factory(success=True, raise_exc=False):
    def selective_run(args, *a, **kw):
        if any("org.h2.tools.Script" in str(arg) or "org.h2.tools.RunScript" in str(arg) for arg in args):
            if raise_exc:
                raise Exception("Export failed")
            if success:
                m = MagicMock()
                m.returncode = 0
                m.stdout = "Exported"
                m.stderr = ""
                return m
            else:
                m = MagicMock()
                m.returncode = 1
                m.stdout = ""
                m.stderr = "Error"
                return m
        # 其他 subprocess.run 调用走原生
        return _real_subprocess_run(args, *a, **kw)
    return selective_run

@patch("pygeoweaver.commands.pgw_cleanh2db.os.remove")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_database_url_from_properties", return_value=None)
@patch("pygeoweaver.commands.pgw_cleanh2db.get_home_dir", return_value=tempfile.gettempdir())
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", return_value=True)
@patch("pygeoweaver.commands.pgw_cleanh2db.os.listdir", return_value=["gw.db"])
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", return_value=1024)
@patch("pygeoweaver.commands.pgw_cleanh2db.shutil.copy2")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.makedirs")
def test_cleanh2db_success(mock_makedirs, mock_copy2, mock_getsize, mock_listdir, mock_exists, mock_spinner, mock_get_home, mock_get_db_url, mock_start, mock_stop, mock_status, mock_java, mock_remove):
    with patch("pygeoweaver.commands.pgw_cleanh2db.subprocess.run", side_effect=selective_run_factory(success=True)):
        with patch("builtins.open", new=selective_open_factory(20)):
            with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", side_effect=lambda f: 1024 if f.endswith(".db") else 100):
                with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", side_effect=lambda f: True):
                    assert clean_h2db(h2_jar_path="h2.jar", temp_dir=tempfile.gettempdir(), db_path="/tmp/gw", db_username="geoweaver", password="pw") is True

@patch("pygeoweaver.commands.pgw_cleanh2db.os.remove")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_database_url_from_properties", return_value=None)
@patch("pygeoweaver.commands.pgw_cleanh2db.get_home_dir", return_value=tempfile.gettempdir())
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", return_value=True)
@patch("pygeoweaver.commands.pgw_cleanh2db.os.listdir", return_value=["gw.db"])
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", return_value=1024)
@patch("pygeoweaver.commands.pgw_cleanh2db.shutil.copy2")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.makedirs")
def test_cleanh2db_sql_too_few_lines(mock_makedirs, mock_copy2, mock_getsize, mock_listdir, mock_exists, mock_spinner, mock_get_home, mock_get_db_url, mock_start, mock_stop, mock_status, mock_java, mock_remove):
    with patch("pygeoweaver.commands.pgw_cleanh2db.subprocess.run", side_effect=selective_run_factory(success=True)):
        with patch("builtins.open", new=selective_open_factory(5)):
            with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", side_effect=lambda f: 1024 if f.endswith(".db") else 100):
                with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", side_effect=lambda f: True):
                    assert clean_h2db(h2_jar_path="h2.jar", temp_dir=tempfile.gettempdir(), db_path="/tmp/gw", db_username="geoweaver", password="pw") is False

@patch("pygeoweaver.commands.pgw_cleanh2db.os.remove")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_database_url_from_properties", return_value=None)
@patch("pygeoweaver.commands.pgw_cleanh2db.get_home_dir", return_value=tempfile.gettempdir())
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", return_value=True)
@patch("pygeoweaver.commands.pgw_cleanh2db.os.listdir", return_value=["gw.db"])
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", return_value=1024)
@patch("pygeoweaver.commands.pgw_cleanh2db.shutil.copy2")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.makedirs")
def test_cleanh2db_export_exception(mock_makedirs, mock_copy2, mock_getsize, mock_listdir, mock_exists, mock_spinner, mock_get_home, mock_get_db_url, mock_start, mock_stop, mock_status, mock_java, mock_remove):
    with patch("pygeoweaver.commands.pgw_cleanh2db.subprocess.run", side_effect=selective_run_factory(success=False, raise_exc=True)):
        with patch("builtins.open", new=selective_open_factory(20)):
            with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", side_effect=lambda f: 1024 if f.endswith(".db") else 100):
                with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", side_effect=lambda f: True):
                    assert clean_h2db(h2_jar_path="h2.jar", temp_dir=tempfile.gettempdir(), db_path="/tmp/gw", db_username="geoweaver", password="pw") is False

@patch("pygeoweaver.commands.pgw_cleanh2db.os.remove")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_java")
@patch("pygeoweaver.commands.pgw_cleanh2db.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.commands.pgw_cleanh2db.stop")
@patch("pygeoweaver.commands.pgw_cleanh2db.start")
@patch("pygeoweaver.commands.pgw_cleanh2db.get_database_url_from_properties", return_value=None)
@patch("pygeoweaver.commands.pgw_cleanh2db.get_home_dir", return_value=tempfile.gettempdir())
@patch("pygeoweaver.commands.pgw_cleanh2db.get_spinner")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.exists", return_value=True)
@patch("pygeoweaver.commands.pgw_cleanh2db.os.listdir", return_value=["gw.db"])
@patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", return_value=1024)
@patch("pygeoweaver.commands.pgw_cleanh2db.shutil.copy2")
@patch("pygeoweaver.commands.pgw_cleanh2db.os.makedirs")
def test_cleanh2db_file_size_mismatch(mock_makedirs, mock_copy2, mock_getsize, mock_listdir, mock_exists, mock_spinner, mock_get_home, mock_get_db_url, mock_start, mock_stop, mock_status, mock_java, mock_remove):
    # Patch copy2 to simulate file size mismatch
    with patch("pygeoweaver.commands.pgw_cleanh2db.os.path.getsize", side_effect=lambda f: 1024 if f.endswith(".db") else 512):
        assert clean_h2db(h2_jar_path="h2.jar", temp_dir=tempfile.gettempdir(), db_path="/tmp/gw", db_username="geoweaver", password="pw") is False 