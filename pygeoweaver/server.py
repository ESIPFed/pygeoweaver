import os
import socket
import subprocess
import sys
import webbrowser
import time
import psutil
import requests
from halo import Halo

from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.jdk_utils import check_java
from pygeoweaver.pgw_log_config import get_logger
from pygeoweaver.utils import (
    check_ipython,
    check_os,
    download_geoweaver_jar,
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
        java_cmd = "java"
        try:
            subprocess.run(["where", "java"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            # Java command not found in PATH, check JDK folder in home directory
            jdk_home = os.path.join(home_dir, "jdk", "jdk-11.0.18+10")  # Change this to your JDK installation directory
            print("Check jdk_home", jdk_home)
            java_cmd = os.path.join(jdk_home, "bin", "java.exe")
            if not os.path.exists(java_cmd):
                print("Java command not found.")
                safe_exit(1)

    with get_spinner(text=f'Starting Geowaever...', spinner='dots'):
        geoweaver_jar = os.path.join(home_dir, "geoweaver.jar")
        print(f'"{java_cmd}" -jar "{geoweaver_jar}"')
        subprocess.Popen([java_cmd, "-jar", geoweaver_jar], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_CONSOLE)

        status = 0
        counter = 0
        max_attempts = 20
        retry_delay = 2
        while counter < max_attempts:
            time.sleep(retry_delay)
            counter += 1
            try:
                response = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL, allow_redirects=False)
                if response.status_code == 302:
                    log_file = os.path.join(home_dir, "geoweaver.log")
                    # Ensure the log file exists, create it if it doesn't
                    if not os.path.exists(log_file):
                        open(log_file, "a").close()  # Create an empty file if it doesn't exist

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


def stop_on_windows():
    print("Stopping Geoweaver...")
    subprocess.run(["taskkill", "/f", "/im", "java.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Geoweaver stopped successfully.")


def check_java_exists():
    with get_spinner(text=f'Check if Java is installed...', spinner='dots'):
        specified_path = os.path.expanduser("~/jdk/jdk-11.0.18+10/bin/java")
        if os.path.isfile(specified_path):
            print(f"Using Java in home directory: {specified_path}")
            return specified_path

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
    if force_restart:
        # First stop any existing Geoweaver
        stop_on_mac_linux(exit_on_finish=exit_on_finish)

    # Checking Java
    java_path = check_java_exists()
    if java_path is None:
        print("Java not found. Exiting...")
        if exit_on_finish:
            safe_exit(1)

    with get_spinner(text=f'Starting Geoweaver...', spinner='dots'):
        # Start Geoweaver
        cmds = [java_path, "-jar", os.path.expanduser("~/geoweaver.jar")]
        logger.info("Running ", " ".join(cmds))
        with open(os.path.expanduser("~/geoweaver.log"), 'w') as log_file:
            subprocess.Popen(cmds, 
                            stdout=log_file, 
                            stderr=subprocess.STDOUT)

        # Wait for Geoweaver to start
        time.sleep(2)  # Adjust as necessary

        status = 0
        counter = 0
        max_counter = 10
        while counter != max_counter:  # max wait for 20 seconds
            try:
                status = requests.get(GEOWEAVER_DEFAULT_ENDPOINT_URL).status_code
                logger.debug(f"Received code {status}")
                if status == 302 or status == 200:
                    break
            except requests.exceptions.ConnectionError:
                pass  # Connection error, retrying
            time.sleep(2)
            counter += 1

        if counter == max_counter:
            print("Error: Geoweaver is not up")
            if exit_on_finish:
                safe_exit(1)
        else:
            print("Success: Geoweaver is up")
            if exit_on_finish:
                safe_exit(0)


def stop_on_mac_linux(exit_on_finish: bool=False) -> int:
    with get_spinner(text=f'Stopping Geoweaver...', spinner='dots'):
        logger.info("Stop running Geoweaver if any..")

        # Get current user's UID
        current_uid = os.getuid()

        # Find all processes running geoweaver.jar that are started by the current user
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'uids']):
            if proc and proc.info and proc.info['cmdline'] \
                and 'geoweaver.jar' in " ".join(proc.info['cmdline']) \
                and proc.info['uids'] and proc.info['uids'].real == current_uid:
                processes.append(proc)

        if not processes:
            print("No running Geoweaver processes found for the current user.")
            return 0

        # Attempt to kill each process
        errors = []
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)  # Wait for the process to terminate
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired) as e:
                errors.append(f"Failed to kill process {proc.info['pid']}: {e}")

        if errors:
            for error in errors:
                logger.error(error)
            print("Some processes could not be stopped.")
            return 1

        # Check status of Geoweaver
        status = subprocess.run(["curl", "-s", "-o", "/dev/null", 
                                    "-w", "%{http_code}\n", 
                                    GEOWEAVER_DEFAULT_ENDPOINT_URL], 
                                    capture_output=True, text=True).stdout.strip()
        logger.info("status: "+ status)
        if status != "302":
            print("Stopped.")
            return 0
        else:
            print("Error: unable to stop.")
            return 1


def start(force_download=False, force_restart=False, exit_on_finish=True):
    download_geoweaver_jar(overwrite=force_download)
    check_java()

    if check_os() == 3:
        logger.debug(f"Detected Windows, running start python script..")
        start_on_windows(force_restart=force_restart, force_download=force_download, exit_on_finish=exit_on_finish)
    else:
        logger.debug(f"Detected Linux/MacOs, running start python script..")
        start_on_mac_linux(force_restart=force_restart, force_download=force_download, exit_on_finish=exit_on_finish)


def stop(exit_on_finish: bool=False):
    check_java()
    if check_os() == 3:
        stop_on_windows()
    else:
        exit_code = stop_on_mac_linux()
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
