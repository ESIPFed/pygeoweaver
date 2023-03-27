
import subprocess

"""
This module provides function to start and stop Geoweaver server.
If it detects the current environment is Jupyter notebook, it will 
open Geoweaver GUI in the output cell (if gui is not disabld.)

"""


def start():
    print("start Geoweaver instance..")
    result = subprocess.run(['java', '-jar', 'geoweaver.jar'], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)


def stop():
    print("stop Geoweaver instance..")
    result = subprocess.run(['java', '-jar', 'geoweaver.jar'], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)




