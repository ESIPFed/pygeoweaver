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
        self.assertEqual(response.status_code, 200, f"Failed to access URL: {GEOWEAVER_DEFAULT_ENDPOINT_URL}")
        stop()
        with self.assertRaises(requests.exceptions.ConnectionError):
            response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL)




if __name__ == "__main__":
    unittest.main()