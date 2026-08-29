import os
import socket
import subprocess
import sys
import webbrowser
import time
from typing import Optional

import psutil
import requests
from halo import Halo

from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.h2_utils import (
    get_safe_datasource_url_for_start,
    maintain_h2_database_on_stop,
    prepare_h2_database_for_start,
    warn_oversized_h2_on_lifecycle,
)
from pygeoweaver.jdk_utils import check_java, ensure_geoweaver_runtime, get_default_managed_jdk17_home
from pygeoweaver.pgw_log_config import get_logger
from pygeoweaver.utils import (
    check_ipython,
    check_os,
    download_geoweaver_jar,
    get_log_file_path,
    get_module_absolute_path,
    get_root_dir,
    get_spinner,
    safe_exit,
)

"""
This module provides function to start and stop Geoweaver server.
If it detects the current environment is Jupyter notebook, it will 
open Geoweaver GUI in the output cell (if gui is not disabld.)

"""

logger = get_logger(__name__)

# Get the user's home directory
home_dir = os.path.expanduser("~")


def check_geoweaver_status() -> bool:
    """
    Check if geoweaver is running
    """
    try:
        # Run 'ps' command to list all processes
        ps_output = subprocess.check_output(['ps', 'aux']).decode('utf-8').splitlines()
        
        # Check each line of ps output for 'geoweaver.jar'
        geoweaver_running = False
        for line in ps_output:
            if 'geoweaver.jar' in line:
                geoweaver_running = True
                break
        
        if geoweaver_running:
            logger.info("Geoweaver is running.")
            return True
        else:
            logger.info("Geoweaver is not running.")
            return False
    
    except subprocess.CalledProcessError as e:
        err_msg = f"Error checking Geoweaver status: {e}"
        logger.error(err_msg)
        raise ValueError(err_msg)


def start_on_windows(force_restart=False, force_download=False, exit_on_finish=True):
    
    with get_spinner(text=f'Stop running Geoweaver if any...', spinner='dots'):
        subprocess.run(["taskkill", "/f", "/im", "geoweaver.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with get_spinner(text=f'Check if Java is installed...', spinner='dots'):
        runtime = ensure_geoweaver_runtime()
        java_cmd = runtime.java_bin
        if java_cmd == "java":
            java_cmd = "java.exe"
        if java_cmd not in ("java", "java.exe") and not os.path.exists(java_cmd):
            jdk_home = get_default_managed_jdk17_home()
            candidate = os.path.join(jdk_home, "bin", "java.exe")
            if os.path.exists(candidate):
                java_cmd = candidate
            else:
                print("Java command not found.")
                safe_exit(1)

    with get_spinner(text=f'Starting Geowaever...', spinner='dots'):
        geoweaver_jar = os.path.join(home_dir, "geoweaver.jar")
        # Pass datasource as a JVM system property — Geoweaver's picocli CLI
        # rejects Spring Boot `--spring.*` program arguments and exits.
        start_cmd = [java_cmd]
        datasource_url = get_safe_datasource_url_for_start()
        if datasource_url:
            start_cmd.append(f"-Dspring.datasource.url={datasource_url}")
        start_cmd.extend(["-jar", geoweaver_jar])
        print(" ".join(start_cmd))
        subprocess.Popen(start_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_CONSOLE)

        status = 0
        counter = 0
        max_attempts = 45
        retry_delay = 2
        while counter < max_attempts:
            time.sleep(retry_delay)
            counter += 1
            try:
                response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL, allow_redirects=False)
                if response.status_code == 302:
                    log_file = get_log_file_path()
                    # Now you can safely open the log file for reading
                    with open(log_file, "r") as f:
                        print(f.read())
                    print("Success: Geoweaver is up")
                    if exit_on_finish:
                        safe_exit(0)
            except Exception as e:
                # print(f"Error occurred during request: {e}")
                continue

        print("Error: Geoweaver is not up")
        if exit_on_finish:
            safe_exit(1)


def stop_on_windows(maintain_h2: bool = False, compact_h2: Optional[bool] = None):
    """Stop Geoweaver on Windows. ``compact_h2`` is a deprecated alias for ``maintain_h2``."""
    if compact_h2 is not None:
        maintain_h2 = compact_h2
    print("Stopping Geoweaver...")
    subprocess.run(["taskkill", "/f", "/im", "java.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    warn_oversized_h2_on_lifecycle()
    if maintain_h2:
        with get_spinner(text="Maintaining H2 database safely...", spinner="dots"):
            maintain_h2_database_on_stop(allow_compact=True)
    print("Geoweaver stopped successfully.")


def check_java_exists():
    with get_spinner(text=f'Check if Java is installed...', spinner='dots'):
        runtime = ensure_geoweaver_runtime()
        if runtime and runtime.java_bin:
            print(f"Using Java: {runtime.java_bin} (channel={runtime.channel})")
            return runtime.java_bin

        # Prefer auto-installed Temurin 17 home layout used by pygeoweaver.
        for candidate in (
            os.path.join(get_default_managed_jdk17_home(), "bin", "java"),
            os.path.expanduser("~/jdk/jdk-11.0.18+10/bin/java"),  # legacy layout
        ):
            if os.path.isfile(candidate):
                print(f"Using Java in home directory: {candidate}")
                return candidate

        # Check if default Java exists
        try:
            result = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                print("Using Java from system..")
                return "java"
        except FileNotFoundError:
            pass

        return None


def start_on_mac_linux(force_restart: bool=False, force_download: bool=False, exit_on_finish: bool=False):
    # Checking Java
    java_path = check_java_exists()
    if java_path is None:
        print("Java not found. Exiting...")
        if exit_on_finish:
            safe_exit(1)

    with get_spinner(text=f'Starting Geoweaver...', spinner='dots'):
        # Pass datasource as a JVM system property — Geoweaver's picocli CLI
        # rejects Spring Boot `--spring.*` program arguments and exits.
        cmds = [java_path]
        datasource_url = get_safe_datasource_url_for_start()
        if datasource_url:
            cmds.append(f"-Dspring.datasource.url={datasource_url}")
        cmds.extend(["-jar", os.path.expanduser("~/geoweaver.jar")])
        logger.info("Running %s", " ".join(cmds))
        with open(os.path.expanduser("~/geoweaver.log"), 'w') as log_file:
            subprocess.Popen(cmds, 
                            stdout=log_file, 
                            stderr=subprocess.STDOUT)

        # Wait for Geoweaver to start (Boot 3 / large jar needs more than ~20s on CI)
        time.sleep(2)

        status = 0
        counter = 0
        max_counter = 45  # ~90s plus initial sleep
        while counter != max_counter:  # max wait for cold start
            try:
                status = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL, allow_redirects=False, timeout=5).status_code
                logger.debug(f"Received code {status}")
                if status == 302 or status == 200:
                    break
            except requests.exceptions.RequestException:
                pass  # Connection error, retrying
            time.sleep(2)
            counter += 1

        if counter == max_counter:
            print("Error: Geoweaver is not up")
            log_path = os.path.expanduser("~/geoweaver.log")
            if os.path.isfile(log_path):
                try:
                    with open(log_path, "r", errors="replace") as f:
                        print("===== ~/geoweaver.log (tail) =====")
                        print("".join(f.readlines()[-80:]))
                except OSError:
                    pass
            if exit_on_finish:
                safe_exit(1)
        else:
            print("Success: Geoweaver is up")
            if exit_on_finish:
                safe_exit(0)


def _wait_for_geoweaver_shutdown(timeout_seconds: int = 30) -> bool:
    """Wait until Geoweaver JVM processes have fully exited before H2 maintenance."""
    if check_os() == 3:
        return True

    current_uid = os.getuid()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not find_geoweaver_processes(current_uid):
            return True
        time.sleep(1)

    logger.warning("Timed out waiting for Geoweaver processes to exit")
    return False


def find_geoweaver_processes(current_uid):
    """
    Find all Geoweaver-related processes started by the current user.
    
    :param current_uid: The UID of the current user.
    :return: A list of matching process objects.
    """
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'uids']):
        try:
            if (proc.info and proc.info['cmdline'] and
                ('geoweaver.jar' in " ".join(proc.info['cmdline']) or
                 'GeoweaverApplication' in " ".join(proc.info['cmdline'])) and
                proc.info['uids'] and proc.info['uids'].real == current_uid):
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue  # Skip processes that have exited or are inaccessible
    return processes

def stop_on_mac_linux(
    exit_on_finish: bool = False,
    maintain_h2: bool = False,
    compact_h2: Optional[bool] = None,
) -> int:
    """Stop Geoweaver on macOS/Linux. ``compact_h2`` is a deprecated alias for ``maintain_h2``."""
    if compact_h2 is not None:
        maintain_h2 = compact_h2
    with get_spinner(text='Stopping Geoweaver...', spinner='dots'):
        logger.info("Stopping any running Geoweaver processes...")

        # Get current user's UID
        current_uid = os.getuid()

        # Find all processes running geoweaver.jar or GeoweaverApplication that are started by the current user
        processes = find_geoweaver_processes(current_uid)

        if not processes:
            print("No running Geoweaver processes found for the current user.")
        else:
            # Attempt to kill each process
            errors = []
            for proc in processes:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)  # Wait for the process to terminate
                    logger.info(f"Successfully stopped process {proc.info['pid']}.")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    logger.error(f"Process {proc.info['pid']} has already exited or is inaccessible.")
                    errors.append(f"Process {proc.info['pid']} is not accessible.")
                except psutil.TimeoutExpired:
                    logger.warning(f"Process {proc.info['pid']} did not terminate in time, forcing kill.")
                    proc.kill()  # Forcefully kill if it didn't terminate in time
                    errors.append(f"Process {proc.info['pid']} was forcefully killed.")

            # Log errors if any
            if errors:
                for error in errors:
                    logger.error(error)
                print("Some processes could not be stopped.")
                return 1

        _wait_for_geoweaver_shutdown()

        warn_oversized_h2_on_lifecycle()
        if maintain_h2:
            with get_spinner(text="Maintaining H2 database safely...", spinner="dots"):
                maintain_h2_database_on_stop(allow_compact=True)

        if not processes:
            return 0

        # Check status of Geoweaver
        status = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}\n", GEOWEAVER_DEFAULT_ENDPOINT_URL],
            capture_output=True, text=True
        ).stdout.strip()

        logger.info("Geoweaver status: " + status)
        if status != "302":
            print("Stopped Geoweaver successfully.")
            return 0
        else:
            print("Error: Unable to stop Geoweaver.")
            return 1


def start(force_download=False, force_restart=False, exit_on_finish=True):
    # Resolve Java / jar channel first so download picks latest vs legacy correctly.
    ensure_geoweaver_runtime()
    download_geoweaver_jar(overwrite=force_download)

    if force_restart:
        stop(exit_on_finish=False, maintain_h2=False)
    elif check_geoweaver_status():
        print("Geoweaver is already running.")
        if exit_on_finish:
            safe_exit(0)
        return

    with get_spinner(text="Checking H2 database before start...", spinner="dots"):
        if not prepare_h2_database_for_start():
            print("Error: H2 database maintenance failed. Geoweaver was not started.")
            if exit_on_finish:
                safe_exit(1)
            return

    if check_os() == 3:
        logger.debug(f"Detected Windows, running start python script..")
        start_on_windows(force_restart=force_restart, force_download=force_download, exit_on_finish=exit_on_finish)
    else:
        logger.debug(f"Detected Linux/MacOs, running start python script..")
        start_on_mac_linux(force_restart=force_restart, force_download=force_download, exit_on_finish=exit_on_finish)


def stop(exit_on_finish: bool = False, maintain_h2: bool = False, compact_h2: Optional[bool] = None):
    """
    Stop Geoweaver.

    By default stop only terminates the JVM and prints an oversized-H2 hint.
    Pass ``maintain_h2=True`` (or deprecated ``compact_h2=True``) for optional
    short compact. Full rebuild is ``gw cleanh2db``.
    """
    if compact_h2 is not None:
        maintain_h2 = compact_h2
    check_java()
    if check_os() == 3:
        stop_on_windows(maintain_h2=maintain_h2)
    else:
        exit_code = stop_on_mac_linux(maintain_h2=maintain_h2)
        if exit_on_finish:
            safe_exit(exit_code)


def show(geoweaver_url=GEOWEAVER_DEFAULT_ENDPOINT_URL):
    download_geoweaver_jar()  # check if geoweaver is initialized
    check_java()
    if check_ipython():
        logger.info("enter ipython block")
        from IPython.display import IFrame

        logger.warning("This only works when the Jupyter is visited from localhost!")
        return IFrame(src=geoweaver_url, width="100%", height="500px")
    else:
        logger.info("enter self opening block")
        webbrowser.open(geoweaver_url)


def ensure_geoweaver_started():
    geoweaver_running = check_geoweaver_status()
    if not geoweaver_running:
        start(exit_on_finish=False)
