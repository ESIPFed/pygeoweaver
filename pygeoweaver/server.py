import os
import subprocess
import webbrowser
from pygeoweaver.utils import checkIPython, checkOS, download_geoweaver_jar, get_root_dir

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
    

def show(geoweaver_url = GEOWEAVER_DEFAULT_ENDPOINT_URL):
    download_geoweaver_jar()  # check if geoweaver is initialized
    if checkIPython():
        from IPython.display import IFrame
        return IFrame(src=geoweaver_url, width='100%', height='500px')
    else:
        webbrowser.open(geoweaver_url)


