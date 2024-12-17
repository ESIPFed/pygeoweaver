import re
from unittest.mock import patch
from pygeoweaver.commands.pgw_detail import (
    detail_process,
    detail_workflow,
    detail_host,
)


def clean_output(output):
    """
    Clean escape sequences and spinner content from the output.
    """
    return re.sub(r"\x1b\[.*?m|\r|\⠋.*?\⠙.*?", "", output).strip()


# Correct mock path: Mock check_geoweaver_status where it is used (pgw_detail)
@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
def test_detail_process(mock_ensure_server, mock_check_status, capfd):
    """
    Test the detail_process function with a non-existing process ID.
    """
    detail_process("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert "Error" in clean_out or "not_existing_id" in clean_out


@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
def test_detail_workflow(mock_ensure_server, mock_check_status, capfd):
    """
    Test the detail_workflow function with a non-existing workflow ID.
    """
    detail_workflow("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert "Error" in clean_out or "not_existing_id" in clean_out


@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
def test_detail_host(mock_ensure_server, mock_check_status, capfd):
    """
    Test the detail_host function with a non-existing host ID.
    """
    detail_host("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert "Error" in clean_out or "not_existing_id" in clean_out
