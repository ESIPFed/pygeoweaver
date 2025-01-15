import logging
import subprocess
import requests
from pygeoweaver.constants import *

from pygeoweaver.server import ensure_geoweaver_started
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
)

logger = logging.getLogger(__name__)

def ensure_server_running(force_restart=False, force_download=False):
    """
    Ensure the Geoweaver server is running. If not, start the sever.
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    logger.info("Ensuring Geoweaver server is running...")
    if force_download:
        download_geoweaver_jar()

    if not force_restart and check_geoweaver_status():
        logger.info("Geoweaver server is already running.")
        return

    logger.info("Starting Geoweaver server...")
    os_type = check_os()
    try:
        if os_type == 3:  # Windows
            start_on_windows(force_restart=force_restart, exit_on_finish=False)
        else:  # macOS or Linux
            start_on_mac_linux(force_restart=force_restart, exit_on_finish=False)

        # Recheck server status
        if not check_geoweaver_status():
            raise RuntimeError("Failed to start Geoweaver server.")
        logger.info("Geoweaver server started successfully.")
    except Exception as e:
        logger.error(f"Error starting Geoweaver server: {e}")
        raise


def get_geoweaver_endpoint():
    """
    Get the endpoint URL for the Geoweaver server.
    """
    return GEOWEAVER_DEFAULT_ENDPOINT_URL or "http://localhost:8070/Geoweaver"


def detail_workflow(workflow_id, force_restart=False, force_download=False):
    """
    Display detailed information about a workflow.
    :param workflow_id: The ID of the workflow.
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    with get_spinner(text="Getting workflow details..", spinner="dots"):
        download_geoweaver_jar()
        ensure_geoweaver_started()
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
    
    print("\n", process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)
        

def detail_process(process_id):
    """
    Display detailed information about a process.
    :param process_id: The ID of the process.
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not process_id:
        raise RuntimeError("Process id is missing")
    with get_spinner(text="Getting process details..", spinner="dots"):
        download_geoweaver_jar()
        ensure_geoweaver_started()
        process = subprocess.run(
            [
                "java", "-jar", get_geoweaver_jar_path(), "detail",
                "--process-id", process_id
            ],
            text=True,
            capture_output=True
        )
    print("\n", process.stdout)
    if process.stderr:
        print("=== Error ===")
        print(process.stderr)
        logger.error(process.stderr)

        if process.stderr:
            print("=== Error ===")
            print(process.stderr)
            logger.error(process.stderr)
        if process.stdout:
            print("=== Process Details ===")
            print(process.stdout)


def detail_host(host_id, force_restart=False, force_download=False):
    """
    Display detailed information about a host.
    :param host_id: The ID of the host.
    :param force_restart: Restart the server even if it's already running.
    :param force_download: Force download of Geoweaver jar if necessary.
    """
    if not host_id:
        raise RuntimeError("Host id is missing")
    with get_spinner(text="Getting host details..\n", spinner="dots"):
        download_geoweaver_jar()
        ensure_geoweaver_started()
        process = subprocess.run(
            [
                "java", "-jar", get_geoweaver_jar_path(), "detail",
                "--host-id", host_id
            ],
            capture_output=True,
            text=True
        )
    
        print("\n" + process.stdout)
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
    ensure_geoweaver_started()
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
        data={"type": "process", "id": process_id},
    ).json()
    return r["code"]
