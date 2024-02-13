import os
import socket
import subprocess
import webbrowser
import time
import requests
from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.jdk_utils import check_java
from pygeoweaver.utils import (
    check_ipython,
    check_os,
    download_geoweaver_jar,
    get_logger,
    get_module_absolute_path,
    get_root_dir,
)

"""
This module provides function to start and stop Geoweaver server.
If it detects the current environment is Jupyter notebook, it will 
open Geoweaver GUI in the output cell (if gui is not disabld.)

"""

logger = get_logger(__name__)


def start_on_windows():
    
    # Stop running Geoweaver if any
    print("Stop running Geoweaver if any..")
    subprocess.run(["taskkill", "/f", "/im", "geoweaver.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Get the user's home directory
    home_dir = os.path.expanduser("~")

    # Check if Java command exists in the system PATH
    print("Check java exists..")
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
            exit(1)

    print("Start Geoweaver..")
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
            response = requests.get("http://localhost:8070/Geoweaver", allow_redirects=False)
            if response.status_code == 302:
                log_file = os.path.join(home_dir, "geoweaver.log")
                # Ensure the log file exists, create it if it doesn't
                if not os.path.exists(log_file):
                    open(log_file, "a").close()  # Create an empty file if it doesn't exist

                # Now you can safely open the log file for reading
                with open(log_file, "r") as f:
                    print(f.read())
                print("Success: Geoweaver is up")
                exit(0)
        except Exception as e:
            # print(f"Error occurred during request: {e}")
            continue

    print("Error: Geoweaver is not up")
    exit(1)


def stop_on_windows():
    print("Stopping Geoweaver...")
    subprocess.run(["taskkill", "/f", "/im", "java.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Geoweaver stopped successfully.")


def start(force=False):
    download_geoweaver_jar(overwrite=force)
    check_java()

    if check_os() == 3:
        logger.debug(f"Detected Windows, running start python script..")
        start_on_windows()
    else:
        logger.debug(f"Detected Linux/MacOs, running {get_module_absolute_path()}/start.sh")
        subprocess.run(
            [f"{get_module_absolute_path()}/start.sh"], cwd=f"{get_root_dir()}/"
        )


def stop():
    check_java()
    if check_os() == 3:
        stop_on_windows()
    else:
        subprocess.run(
            [f"{get_module_absolute_path()}/stop.sh"],
            cwd=f"{get_root_dir()}/",
            shell=True,
        )


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
