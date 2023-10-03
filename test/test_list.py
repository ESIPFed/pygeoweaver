import unittest
from unittest.mock import patch, MagicMock
import pygeoweaver  # replace 'your_module' with the actual module name where pygeoweaver is defined


class TestListHosts(unittest.TestCase):
    @patch('IPython.core.display_functions.display')
    @patch('requests.post')
    def test_list_hosts(self, mock_post, mock_display):
        mock_post.return_value.json.return_value = [{'some': 'data'}]
        pygeoweaver.create_table = MagicMock(return_value=('table_html', 'some_other_value'))

        with patch('builtins.globals', return_value={'get_ipython': None}):
            pygeoweaver.list_hosts()


class TestListProcesses(unittest.TestCase):

    @patch('IPython.core.display_functions.display')
    @patch('requests.post')
    def test_list_processes(self, mock_post, mock_display):
        mock_post.return_value.json.return_value = [{'some': 'data'}]
        pygeoweaver.create_table = MagicMock(return_value=('table_html', None))

        with patch('builtins.globals', return_value={'get_ipython': None}):
            pygeoweaver.list_processes()


class TestListProcessesInWorkflow(unittest.TestCase):

    @patch('json.loads')
    @patch('requests.post')
    def test_list_processes_in_workflow(self, mock_post, mock_json_loads):
        mock_post.return_value.json.return_value = {'nodes': '[{"title": "some_title", "id": "some_id"}]'}
        mock_json_loads.return_value = [{'title': 'some_title', 'id': 'some_id'}]

        result = pygeoweaver.list_processes_in_workflow('some_workflow_id')

        expected_result = [{'title': 'some_title', 'id': 'some_id'}]
        self.assertEqual(result, expected_result)


class TestListWorkflows(unittest.TestCase):

    @patch('IPython.core.display_functions.display')
    @patch('requests.post')
    def test_list_workflows(self, mock_post, mock_display):
        mock_post.return_value.json.return_value = [{'some': 'data'}]
        pygeoweaver.create_table = MagicMock(return_value=('table_html', None))

        with patch('builtins.globals', return_value={'get_ipython': None}):
            pygeoweaver.list_workflows()


if __name__ == '__main__':
    unittest.main()
