import subprocess
from unittest.mock import patch

import pytest

from pygeoweaver.commands.pgw_detail import (
    detail_process,
    detail_workflow,
    detail_host,
)


def _failed_detail_result(message):
    return subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr=message,
    )


@patch("pygeoweaver.commands.pgw_detail.get_geoweaver_jar_path", return_value="/tmp/geoweaver.jar")
@patch("pygeoweaver.commands.pgw_detail.get_java_bin_path", return_value="java")
@patch("pygeoweaver.commands.pgw_detail.subprocess.run")
@patch("pygeoweaver.commands.pgw_detail.ensure_geoweaver_started")
@patch("pygeoweaver.commands.pgw_detail.download_geoweaver_jar")
def test_detail_process(
    mock_download,
    mock_ensure_started,
    mock_run,
    mock_java_path,
    mock_jar_path,
    capsys,
):
    mock_run.return_value = _failed_detail_result(
        "Error: process not found: not_existing_id"
    )
    detail_process("not_existing_id")
    mock_ensure_started.assert_called_once()
    mock_run.assert_called_once()
    captured = capsys.readouterr()
    assert "Error" in captured.out or "not_existing_id" in captured.out


@patch("pygeoweaver.commands.pgw_detail.get_geoweaver_jar_path", return_value="/tmp/geoweaver.jar")
@patch("pygeoweaver.commands.pgw_detail.get_java_bin_path", return_value="java")
@patch("pygeoweaver.commands.pgw_detail.subprocess.run")
@patch("pygeoweaver.commands.pgw_detail.ensure_geoweaver_started")
@patch("pygeoweaver.commands.pgw_detail.download_geoweaver_jar")
def test_detail_workflow(
    mock_download,
    mock_ensure_started,
    mock_run,
    mock_java_path,
    mock_jar_path,
    capsys,
):
    mock_run.return_value = _failed_detail_result(
        "Error: workflow not found: not_existing_id"
    )
    detail_workflow("not_existing_id")
    mock_ensure_started.assert_called_once()
    mock_run.assert_called_once()
    captured = capsys.readouterr()
    assert "Error" in captured.out or "not_existing_id" in captured.out


@patch("pygeoweaver.commands.pgw_detail.get_geoweaver_jar_path", return_value="/tmp/geoweaver.jar")
@patch("pygeoweaver.commands.pgw_detail.get_java_bin_path", return_value="java")
@patch("pygeoweaver.commands.pgw_detail.subprocess.run")
@patch("pygeoweaver.commands.pgw_detail.ensure_geoweaver_started")
@patch("pygeoweaver.commands.pgw_detail.download_geoweaver_jar")
def test_detail_host(
    mock_download,
    mock_ensure_started,
    mock_run,
    mock_java_path,
    mock_jar_path,
    capsys,
):
    mock_run.return_value = _failed_detail_result(
        "Error: host not found: not_existing_id"
    )
    detail_host("not_existing_id")
    mock_ensure_started.assert_called_once()
    mock_run.assert_called_once()
    captured = capsys.readouterr()
    assert "Error" in captured.out or "not_existing_id" in captured.out


@pytest.mark.parametrize(
    "func,missing_id",
    [
        (detail_process, ""),
        (detail_workflow, ""),
        (detail_host, ""),
    ],
)
def test_detail_requires_id(func, missing_id):
    with pytest.raises(RuntimeError, match="id is missing"):
        func(missing_id)
