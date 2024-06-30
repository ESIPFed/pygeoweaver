"""
Detail subcommand
"""

import logging
import subprocess

import requests
from pygeoweaver.constants import *

from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    get_spinner,
)

logger = logging.getLogger(__name__)


def detail_workflow(workflow_id):
    """
    Display detailed information about a workflow.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    """
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    with get_spinner(text="Getting host details..", spinner="dots"):
        download_geoweaver_jar()
        process = subprocess.run(
            [
                get_java_bin_path(),
                "-jar",
                get_geoweaver_jar_path(),
                "detail",
                f"--workflow-id={workflow_id}",
            ],
            cwd=f"{get_root_dir()}/",
        )
    
    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)
        

def detail_process(process_id):
    """
    Display detailed information about a process.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    if not process_id:
        raise RuntimeError("Process id is missing")
    with get_spinner(text="Getting host details..", spinner="dots"):
        download_geoweaver_jar()
        process = subprocess.run(
            [
                get_java_bin_path(),
                "-jar",
                get_geoweaver_jar_path(),
                "detail",
                f"--process-id={process_id}",
            ],
            cwd=f"{get_root_dir()}/",
        )
    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)

def detail_host(host_id):
    """
    Display detailed information about a host.

    :param host_id: The ID of the host.
    :type host_id: str
    """
    if not host_id:
        raise RuntimeError("Host id is missing")
    with get_spinner(text="Getting host details..", spinner="dots"):
        download_geoweaver_jar()
        process = subprocess.run(
            [
                get_java_bin_path(),
                "-jar",
                get_geoweaver_jar_path(),
                "detail",
                f"--host-id={host_id}",
            ],
            cwd=f"{get_root_dir()}/",
        )
    
    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)

def get_process_code(process_id):
    """
    Get the code of a process.

    :param process_id: The ID of the process.
    :type process_id: str
    :return: The code of the process.
    :rtype: str
    """
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
        data={"type": "process", "id": process_id},
    ).json()
    return r["code"]
