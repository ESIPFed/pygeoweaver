import re
from unittest.mock import patch
from pygeoweaver.commands.pgw_detail import (
    detail_process,
    detail_workflow,
    detail_host,
    get_process_code,
)


def clean_output(output):
    """
    Clean escape sequences and spinner content from the output.
    """
    return re.sub(r"\x1b\[.*?m|\r|\⠋.*?\⠙.*?", "", output).strip()


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running")
def test_detail_process(mock_ensure_server_running, capfd):
    """
    Test the detail_process function with a non-existing process ID.
    """
    mock_ensure_server_running.return_value = None  # Mock server check
    detail_process("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No process found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'process', 'not_existing_id'" in clean_out
    )


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running")
def test_detail_workflow(mock_ensure_server_running, capfd):
    """
    Test the detail_workflow function with a non-existing workflow ID.
    """
    mock_ensure_server_running.return_value = None  # Mock server check
    detail_workflow("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No workflow found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'workflow', 'not_existing_id'" in clean_out
    )


@patch("pygeoweaver.commands.pgw_detail.ensure_server_running")
def test_detail_host(mock_ensure_server_running, capfd):
    """
    Test the detail_host function with a non-existing host ID.
    """
    mock_ensure_server_running.return_value = None  # Mock server check
    detail_host("not_existing_id")
    output, err = capfd.readouterr()
    clean_out = clean_output(output)
    assert (
        "No host found with id: not_existing_id" in clean_out
        or "Unmatched arguments from index 1: 'host', 'not_existing_id'" in clean_out
    )
