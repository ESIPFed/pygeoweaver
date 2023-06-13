import os
import socket
import subprocess
import webbrowser
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


def start(force=False):
    download_geoweaver_jar(overwrite=force)
    check_java()

    if check_os() == 3:
        subprocess.run(
            [f"{get_module_absolute_path()}/start.bat"], cwd=f"{get_root_dir()}/"
        )
    else:
        subprocess.run(
            [f"{get_module_absolute_path()}/start.sh"], cwd=f"{get_root_dir()}/"
        )


def stop():
    check_java()
    if check_os() == 3:
        subprocess.run(
            [f"{get_module_absolute_path()}/stop.bat"],
            cwd=f"{get_root_dir()}/",
            shell=True,
        )
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
