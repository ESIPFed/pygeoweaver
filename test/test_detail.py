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


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
def test_detail_process(mock_status, mock_ensure, capfd):
    """
    Test the detail_process function with a non-existing process ID.
    """
    detail_process("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No process found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'process', 'not_existing_id'" in clean_out
    )


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
def test_detail_workflow(mock_status, mock_ensure, capfd):
    """
    Test the detail_workflow function with a non-existing workflow ID.
    """
    detail_workflow("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No workflow found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'workflow', 'not_existing_id'" in clean_out
    )


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running", return_value=None)
@patch("pygeoweaver.commands.pgw_detail.check_geoweaver_status", return_value=True)
def test_detail_host(mock_status, mock_ensure, capfd):
    """
    Test the detail_host function with a non-existing host ID.
    """
    detail_host("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No host found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'host', 'not_existing_id'" in clean_out
    )
