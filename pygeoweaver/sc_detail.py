"""
Detail subcommand
"""

import subprocess

import requests
from pygeoweaver.constants import *

from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def detail_workflow(workflow_id):
    """
    Display detailed information about a workflow.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    """
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--workflow-id={workflow_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )

def detail_process(process_id):
    """
    Display detailed information about a process.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    if not process_id:
        raise RuntimeError("Process id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--process-id={process_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )

def detail_host(host_id):
    """
    Display detailed information about a host.

    :param host_id: The ID of the host.
    :type host_id: str
    """
    if not host_id:
        raise RuntimeError("Host id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--host-id={host_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )

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
