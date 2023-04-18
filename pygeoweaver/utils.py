import os
import subprocess
import requests
import platform

from IPython import get_ipython
from IPython.display import IFrame


def ui():
    download_geoweaver_jar()  # check if geoweaver is initialized
    shell_type = str(get_ipython().__class__.__module__)
    if shell_type == "google.colab._shell" or shell_type == "ipykernel.zmqshell":
        return IFrame(src="http://localhost:8070/Geoweaver/", width='100%', height='500px')
    else:
        print('Web UI for python bindings can be only used for Colab / Jupyter / Interactive Python shell')


def get_home_dir():
    return os.path.expanduser('~')


def get_root_dir():
    head, tail = os.path.split(__file__)
    return head


def get_geoweaver_jar_path():
    return f"{get_home_dir()}/geoweaver.jar"


def check_geoweaver_jar():
    return os.path.isfile(get_geoweaver_jar_path())


def download_geoweaver_jar(overwrite=False):
    if check_geoweaver_jar():
        if overwrite:
            os.remove(get_geoweaver_jar_path())
        else:
            subprocess.run(["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/")
            return

    geoweaver_url = "https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
    r = requests.get(geoweaver_url)

    with open(get_geoweaver_jar_path(), 'wb') as f:
        f.write(r.content)

    if check_geoweaver_jar():
        print("Geoweaver.jar is downloaded")

    else:
        raise RuntimeError("Fail to download geoweaver.jar")


def checkOS():
    if platform.system() == "Linux" or platform == "Linux2":
        return 1
    elif platform.system() == "Darwin":
        return 2
    elif platform == "Windows":
        return 3
