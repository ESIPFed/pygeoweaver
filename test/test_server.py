"""
The main function of pygeoweaver
To run in CLI mode. 
"""
import logging
import time
from unittest.mock import patch
import requests
from pygeoweaver import start, stop

import unittest

from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.pgw_log_config import get_logger
from pygeoweaver.server import show
import pytest


logger = get_logger(__name__)


def _wait_for_geoweaver(timeout_seconds=30):
    """Poll Geoweaver until it responds or timeout."""
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL, timeout=2)
            if response.status_code in (200, 302):
                return response
        except requests.exceptions.RequestException as exc:
            last_error = exc
        time.sleep(2)
    raise AssertionError(
        f"Geoweaver did not become reachable at {GEOWEAVER_DEFAULT_ENDPOINT_URL}: {last_error}"
    )


@patch("pygeoweaver.server.maintain_h2_database_on_stop", return_value=True)
@patch("pygeoweaver.server.prepare_h2_database_for_start", return_value=True)
def test_server_start_stop(mock_prepare, mock_maintain):
    # Integration test for Geoweaver lifecycle; H2 maintenance is covered separately.
    start(exit_on_finish=False)
    mock_prepare.assert_called_once()

    response = _wait_for_geoweaver()
    assert response.status_code in (200, 302), f"Failed to access URL: {GEOWEAVER_DEFAULT_ENDPOINT_URL}"

    stop(exit_on_finish=False)
    mock_maintain.assert_called()
    
    time.sleep(5)

    with pytest.raises(requests.exceptions.ConnectionError):
        print(f"Test {GEOWEAVER_DEFAULT_ENDPOINT_URL}")
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
        print(response)

    stop(exit_on_finish=False)

def test_windows():
    with patch("pygeoweaver.server.check_os") as mock_checkos:
        mock_checkos.return_value = 3
        
        # Check that FileNotFoundError is raised when starting the server
        with pytest.raises(FileNotFoundError):
            start(exit_on_finish=False)
        
        # Check that FileNotFoundError is raised when stopping the server
        with pytest.raises(FileNotFoundError):
            stop(exit_on_finish=False)

def test_show_gui():
    with patch("pygeoweaver.webbrowser.open") as mock_browser_open:
        show()
        mock_browser_open.assert_called_once()

        with patch("pygeoweaver.server.check_ipython") as mock_checkipython:
            mock_checkipython.return_value = True
            show()
            mock_browser_open.assert_called_once()

