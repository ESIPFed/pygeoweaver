import json
import logging

import requests
import subprocess
from pygeoweaver.constants import *
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    check_ipython,
    get_spinner,
)
import pandas as pd
from halo import Halo


logger = logging.getLogger(__name__)


def list_hosts():
    """
    List all hosts in Geoweaver.

    Downloads the Geoweaver JAR, then runs the 'list' command with the '--host' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    with get_spinner(text=f'Find all registered hosts...', spinner='dots'):
        download_geoweaver_jar()
        process = subprocess.run(
            [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--host"],
            cwd=f"{get_root_dir()}/",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)


def list_processes():
    """
    List all processes in Geoweaver.

    Downloads the Geoweaver JAR, ensures executable permissions, and then runs the 'list' command with the '--process' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    with get_spinner(text=f'Find all registered processes...', spinner='dots'):
        download_geoweaver_jar()
        subprocess.run(["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/")
        process = subprocess.run(
            [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--process"],
            cwd=f"{get_root_dir()}/",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)


def list_processes_in_workflow(workflow_id):
    """
    List processes in a specific workflow.

    Downloads the Geoweaver JAR and queries the Geoweaver server for details of a workflow.
    Extracts information about nodes in the workflow and returns a list of dictionaries containing 'title' and 'id'.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    :return: List of dictionaries containing 'title' and 'id' of processes in the workflow.
    :rtype: list
    """
    with get_spinner(text=f'Find all processes in workflow {workflow_id}...', spinner='dots'):
        download_geoweaver_jar()
        payload = {"id": workflow_id, "type": "workflow"}
        r = requests.post(
            f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail", data=payload
        )
        nodes = json.loads(r.json()["nodes"])
        result = [
            {"title": item["title"], "id": item["id"].split(".")[0]} for item in nodes
        ]

    if check_ipython():
        return pd.DataFrame(result)
    return result


def list_workflows():
    """
    List all workflows in Geoweaver.

    Downloads the Geoweaver JAR, then runs the 'list' command with the '--workflow' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    with get_spinner(text=f'Find all registered workflows...', spinner='dots'):
        download_geoweaver_jar()
        process = subprocess.run(
            [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--workflow"],
            cwd=f"{get_root_dir()}/",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    
    print(process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)

