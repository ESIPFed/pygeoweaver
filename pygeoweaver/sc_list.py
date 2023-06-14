import json

import requests
import subprocess
from . import constants
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    check_ipython,
)
import pandas as pd


def list_hosts():
    download_geoweaver_jar()
    subprocess.run(
        [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--host"],
        cwd=f"{get_root_dir()}/",
    )


def list_processes():
    download_geoweaver_jar()
    subprocess.run(["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/")
    subprocess.run(
        [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--process"],
        cwd=f"{get_root_dir()}/",
    )


def list_processes_in_workflow(workflow_id):
    download_geoweaver_jar()
    payload = {"id": workflow_id, "type": "workflow"}
    r = requests.post(
        f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail", data=payload
    )
    nodes = json.loads(r.json()["nodes"])
    result = [
        {"title": item["title"], "id": item["id"].split(".")[0]} for item in nodes
    ]

    if check_ipython():
        return pd.DataFrame(result)
    return result


def list_workflows():
    download_geoweaver_jar()
    subprocess.run(
        [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "list", "--workflow"],
        cwd=f"{get_root_dir()}/",
    )
