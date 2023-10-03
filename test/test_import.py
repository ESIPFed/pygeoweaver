import os
import unittest
from unittest.mock import patch, Mock
from pygeoweaver.sc_import import import_workflow


class TestImportWorkflow(unittest.TestCase):

    @patch('os.path.basename')
    @patch('os.path.splitext')
    @patch('builtins.open')
    @patch('requests.post')
    def test_import_workflow(self, mock_post, mock_open, mock_splitext, mock_basename):
        # Setup
        mock_basename.return_value = 'test_file.zip'
        mock_splitext.return_value = ('test_file', '.zip')
        mock_open.return_value = Mock()

        mock_response = Mock()
        mock_response.json.return_value = {'status': 'success'}
        mock_post.return_value = mock_response

        # Mocking GEOWEAVER_DEFAULT_ENDPOINT_URL
        with patch('pygeoweaver.constants.GEOWEAVER_DEFAULT_ENDPOINT_URL', 'http://example.com'):
            # Run
            result = import_workflow('/path/to/test_file.zip')

        # Asserts
        self.assertEqual(result, 'Import success.')
        mock_post.assert_called()
        mock_open.assert_called_with('/path/to/test_file.zip', 'rb')


if __name__ == '__main__':
    unittest.main()
