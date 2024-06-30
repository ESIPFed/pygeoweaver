"""
The main function of pygeoweaver
To run in CLI mode. 
"""
import logging
from unittest.mock import patch
import requests
from pygeoweaver import start, stop

import unittest

from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.log_config import get_logger
from pygeoweaver.server import show


logger = get_logger(__name__)


class TestServer(unittest.TestCase):
    def test_server_start_stop(self):
        start()
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
        self.assertEqual(
            response.status_code,
            200,
            f"Failed to access URL: {GEOWEAVER_DEFAULT_ENDPOINT_URL}",
        )
        stop(exit_on_finish=False)
        with self.assertRaises(requests.exceptions.ConnectionError):
            response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)

        stop(exit_on_finish=False)  # stop again should have no issue

    def test_windows(self):
        with patch("pygeoweaver.server.checkOS") as mock_checkos:
            mock_checkos.return_value = 3
            with self.assertRaises(RuntimeError):
                start(exit_on_finish=False)
            with self.assertRaises(RuntimeError):
                stop(exit_on_finish=False)

    def test_show_gui(self):
        with patch("pygeoweaver.webbrowser.open") as mock_browser_open:
            show()
            mock_browser_open.assert_called_once()

            with patch("pygeoweaver.server.checkIPython") as mock_checkipython:
                mock_checkipython.return_value = True
                show()
                mock_browser_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
