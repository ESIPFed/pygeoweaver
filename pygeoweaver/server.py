import os
import subprocess
from pygeoweaver.utils import checkOS, download_geoweaver_jar, get_root_dir

"""
This module provides function to start and stop Geoweaver server.
If it detects the current environment is Jupyter notebook, it will 
open Geoweaver GUI in the output cell (if gui is not disabld.)

"""


def start(force=False):
    download_geoweaver_jar(overwrite=force)
    if checkOS() == 3:
        raise RuntimeError("windows is not supported yet")
    else:
        result = subprocess.run(['./start.sh'], cwd=f"{get_root_dir()}/")
    


def stop():
    if checkOS() == 3:
        raise RuntimeError("Windows is not supported yet")
    else:
        result = subprocess.run(['./stop.sh'], cwd=f"{get_root_dir()}/", shell=True)
    




