

from io import StringIO
import sys
import unittest
from pygeoweaver.sc_detail import detail_host, detail_process, detail_workflow
from pygeoweaver.utils import get_logger


logger = get_logger(__name__)



class TestDetail(unittest.TestCase):


    def test_detail_process(self, capsys):
        output_capture = StringIO()
        detail_process("not_existing_id")
        captured = capsys.readouterr()
        output = output_capture.getvalue()
        self.assertIn("No host found with id: not_existing_id", output)

    @unittest.skip("")
    def test_detail_workflow(self):
        stdout_capture = StringIO()
        detail_workflow("not_existing_id")
        output = stdout_capture.getvalue()
        self.assertIn("No process found with id: not_existing_id", output)

    @unittest.skip("")
    def test_detail_host(self):
        stdout_capture = StringIO()
        detail_host("not_existing_id")
        output = stdout_capture.getvalue()
        self.assertIn("No workflow found with id: not_existing_id", output)

