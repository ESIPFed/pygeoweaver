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

def test_server_start_stop():
    # Start the server
    start(exit_on_finish=False)

    # Check if the server is up by making a GET request
    response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
    assert response.status_code == 200, f"Failed to access URL: {GEOWEAVER_DEFAULT_ENDPOINT_URL}"

    # Stop the server
    stop(exit_on_finish=False)
    
    time.sleep(5)

    # Check that the server has stopped by expecting a connection error
    with pytest.raises(requests.exceptions.ConnectionError):
        print(f"Test {GEOWEAVER_DEFAULT_ENDPOINT_URL}")
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
        print(response)

    # Stop the server again should have no issue
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

