"""
The main function of pygeoweaver
To run in CLI mode. 
"""
import requests
from pygeoweaver import start, stop

import unittest

from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL

class TestServer(unittest.TestCase):

    def test_server(self):
        start()
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
        self.assertEqual(response.status_code, 200, f"Failed to access URL: {url}")
        stop()
        response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)
        self.assertEqual(response.status_code, 200, f"Failed to access URL: {url}")
        # stop geoweaver
        # stop()
        # list resources
        #list_hosts()
        #list_processes()
        # list_workflows()
        # show history
        #show_history("ll3u3W78eOEfklxhBJ")
        # detail host
        # detail_host("100001")
        # detail process
        # detail_process("7pxu8c")
        #detail_workflow("5jnhcrq33znbu2mue9v2")
        # import workflow
        #import_workflow("/Users/joe/Downloads/gr3ykr8dynu12vrwq11oy.zip")
        # export workflow
        # export_workflow("gr3ykr8dynu12vrwq11oy", "4", "/Users/joe/Downloads/test_pygeoweaver_export.zip")


if __name__ == "__main__":
    unittest.main()