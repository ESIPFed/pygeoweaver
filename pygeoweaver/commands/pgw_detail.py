"""
Detail subcommand with integrated server management.
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
    check_os,
)
from pygeoweaver.server import (
    start_on_windows,
    start_on_mac_linux,
    check_geoweaver_status,
    stop_on_windows,
    stop_on_mac_linux,
)

logger = logging.getLogger(__name__)

def ensure_server_running(force_restart=False, force_download=False):
    """
    Ensure the Geoweaver server is running. If not, start it.
    
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not force_restart and check_geoweaver_status():
        logger.info("Geoweaver server is already running.")
        return
    
    logger.info("Starting Geoweaver server...")
    
    # Determine the operating system and start accordingly
    os_type = check_os()
    if os_type == 3:  # Windows
        start_on_windows(force_restart=force_restart, force_download=force_download, exit_on_finish=False)
    else:  # macOS or Linux
        start_on_mac_linux(force_restart=force_restart, force_download=force_download, exit_on_finish=False)
    
    # Verify server status after starting
    if not check_geoweaver_status():
        raise RuntimeError("Failed to start Geoweaver server. Please check logs for details.")

def detail_workflow(workflow_id, force_restart=False, force_download=False):
    """
    Display detailed information about a workflow.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not workflow_id:
        raise RuntimeError("Workflow ID is missing.")
    
    # Ensure server is running before proceeding
    ensure_server_running(force_restart=force_restart, force_download=force_download)
    
    with get_spinner(text="Getting workflow details...", spinner="dots"):
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

def detail_process(process_id, force_restart=False, force_download=False):
    """
    Display detailed information about a process.

    :param process_id: The ID of the process.
    :type process_id: str
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not process_id:
        raise RuntimeError("Process ID is missing.")
    
    # Ensure server is running before proceeding
    ensure_server_running(force_restart=force_restart, force_download=force_download)
    
    with get_spinner(text="Getting process details...", spinner="dots"):
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

def detail_host(host_id, force_restart=False, force_download=False):
    """
    Display detailed information about a host.

    :param host_id: The ID of the host.
    :type host_id: str
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not host_id:
        raise RuntimeError("Host ID is missing.")
    
    # Ensure server is running before proceeding
    ensure_server_running(force_restart=force_restart, force_download=force_download)
    
    with get_spinner(text="Getting host ...", spinner="dots"):
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

def get_process_code(process_id, force_restart=False, force_download=False):
    """
    Get the code of a process.

    :param process_id: The ID of the process.
    :type process_id: str
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    :return: The code of the process.
    :rtype: str
    """
    # Ensure server is running before proceeding
    ensure_server_running(force_restart=force_restart, force_download=force_download)
    
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
        data={"type": "process", "id": process_id},
    ).json()
    return r["code"]
