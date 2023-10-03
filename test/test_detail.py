import json
import unittest
import pandas as pd
from unittest.mock import patch, Mock

from pygeoweaver import get_logger

logger = get_logger(__name__)


class TestDetailFunctions(unittest.TestCase):

    @patch('pygeoweaver.utils.download_geoweaver_jar')
    @patch('requests.post')
    def test_detail_workflow(self, mock_post, mock_download):
        from pygeoweaver.sc_detail import detail_workflow
        with self.assertRaises(RuntimeError):
            detail_workflow(None)
        mock_response = Mock()
        mock_response.json.return_value = {'nodes': json.dumps({"some_key": "some_value"})}
        mock_post.return_value = mock_response
        result = detail_workflow('some_id')
        self.assertIsInstance(result, pd.DataFrame)

    @patch('pygeoweaver.utils.download_geoweaver_jar')
    @patch('requests.post')
    def test_detail_process(self, mock_post, mock_download):
        from pygeoweaver.sc_detail import detail_process

        with self.assertRaises(RuntimeError):
            detail_process(None)
        mock_response = Mock()
        mock_response.json.return_value = {'nodes': json.dumps({"some_key": "some_value"})}
        mock_post.return_value = mock_response
        result = detail_process('some_id')
        self.assertIsInstance(result, pd.DataFrame)

    @patch('pygeoweaver.utils.download_geoweaver_jar')
    @patch('requests.post')
    def test_detail_host(self, mock_post, mock_download):
        from pygeoweaver.sc_detail import detail_host

        with self.assertRaises(RuntimeError):
            detail_host(None)

        mock_response = Mock()
        mock_response.json.return_value = {"some_key": "some_value"}
        mock_post.return_value = mock_response

        result = detail_host('some_id')
        self.assertIsInstance(result, pd.DataFrame)


if __name__ == '__main__':
    unittest.main()
