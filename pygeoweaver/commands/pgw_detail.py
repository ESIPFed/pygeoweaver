import logging
import subprocess
import requests
from pygeoweaver.constants import *
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_spinner,
    check_os,
)
from pygeoweaver.server import (
    start_on_windows,
    start_on_mac_linux,
    check_geoweaver_status,
)

logger = logging.getLogger(__name__)

def ensure_server_running(force_restart=False, force_download=False):
    """
    Ensure the Geoweaver server is running. If not, start it.

    :param force_restart: Restart the server even if it's already running.
    :param force_download: (Optional) Force download of Geoweaver jar if necessary.
    """
    if not force_restart and check_geoweaver_status():
        logger.info("Geoweaver server is already running.")
        return

    logger.info("Starting Geoweaver server...")

    # Download jar if forced
    if force_download:
        download_geoweaver_jar()

    # Start server based on OS
    os_type = check_os()
    if os_type == 3:  # Windows
        start_on_windows(force_restart=force_restart, exit_on_finish=False)
    else:  # macOS or Linux
        start_on_mac_linux(force_restart=force_restart, exit_on_finish=False)

    if not check_geoweaver_status():
        raise RuntimeError("Failed to start Geoweaver server.")


def detail_workflow(workflow_id):
    """
    Display detailed information about a workflow.
    :param workflow_id: The ID of the workflow.
    """
    if not workflow_id:
        raise ValueError("Workflow ID is missing.")

    ensure_server_running()
    with get_spinner(text="Getting workflow details...", spinner="dots"):
        process = subprocess.run(
            [
                "java", "-jar", get_geoweaver_jar_path(), "detail",
                "--workflow-id", workflow_id
            ],
            capture_output=True,
            text=True
        )
        if process.returncode != 0:
            logger.error(f"Error fetching workflow details: {process.stderr}")
            print("=== Error ===")
            print(process.stderr)
        else:
            print(process.stdout)

def detail_process(process_id):
    """
    Display detailed information about a process.
    :param process_id: The ID of the process.
    """
    if not process_id:
        raise ValueError("Process ID is missing.")

    ensure_server_running()
    with get_spinner(text="Getting process details...", spinner="dots"):
        process = subprocess.run(
            [
                "java", "-jar", get_geoweaver_jar_path(), "detail",
                "--process-id", process_id
            ],
            capture_output=True,
            text=True
        )
        if process.returncode != 0:
            logger.error(f"Error fetching process details: {process.stderr}")
            print("=== Error ===")
            print(process.stderr)
        else:
            print(process.stdout)

def detail_host(host_id):
    """
    Display detailed information about a host.
    :param host_id: The ID of the host.
    """
    if not host_id:
        raise ValueError("Host ID is missing.")

    ensure_server_running()
    with get_spinner(text="Getting host details...", spinner="dots"):
        process = subprocess.run(
            [
                "java", "-jar", get_geoweaver_jar_path(), "detail",
                "--host-id", host_id
            ],
            capture_output=True,
            text=True
        )
        if process.returncode != 0:
            logger.error(f"Error fetching host details: {process.stderr}")
            print("=== Error ===")
            print(process.stderr)
        else:
            print(process.stdout)


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