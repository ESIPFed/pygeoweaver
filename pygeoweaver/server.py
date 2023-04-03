import os
import subprocess
from utils import get_root_dir

"""
This module provides function to start and stop Geoweaver server.
If it detects the current environment is Jupyter notebook, it will 
open Geoweaver GUI in the output cell (if gui is not disabld.)

"""

def download_geoweaver():
    """
    Download Geoweaver to user home directory
    """
    pass


def start():
    print("start Geoweaver instance..")
    result = subprocess.run(['./start.sh'], cwd=f"{get_root_dir()}/")
    


def stop():
    print("stop Geoweaver instance..")
    result = subprocess.run(['./stop.sh'], cwd=f"{get_root_dir()}/", shell=True)
    




