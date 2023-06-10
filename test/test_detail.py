from io import StringIO
import sys
import unittest
from pygeoweaver.sc_detail import detail_host, detail_process, detail_workflow
from pygeoweaver.utils import get_logger


logger = get_logger(__name__)


def test_detail_process(capfd):
    detail_process("not_existing_id")
    output, err = capfd.readouterr()
    logger.debug("stdout_output" + output)
    assert "No process found with id: not_existing_id" in output


def test_detail_workflow(capfd):
    detail_workflow("not_existing_id")
    output, err = capfd.readouterr()
    logger.debug("stdout_output" + output)
    assert "No workflow found with id: not_existing_id" in output


def test_detail_host(capfd):
    detail_host("not_existing_id")
    output, err = capfd.readouterr()
    logger.debug("stdout_output" + output)
    assert "No host found with id: not_existing_id" in output
