import json

import requests
import subprocess

from IPython.core.display_functions import display
from ipywidgets import HTML

from pygeoweaver.constants import *
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    check_ipython, create_table,
)
import pandas as pd


def list_hosts():
    download_geoweaver_jar()
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'host'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if 'get_ipython' in globals():
        # Running in a Jupyter Notebook, display as HTML table
        data_json = data.json()
        table_html, _ = create_table(data_json)
        display(HTML(table_html))
    else:
        # Not running in a Jupyter Notebook, display as Pandas DataFrame
        data_json = data.json()
        df = pd.DataFrame(data_json)
        return df


def list_processes():
    download_geoweaver_jar()
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'process'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if 'get_ipython' in globals():
        data_json = data.json()
        table_html, _ = create_table(data_json)
        display(HTML(table_html))
    else:
        data_json = data.json()
        df = pd.DataFrame(data_json)
        return df


def list_processes_in_workflow(workflow_id):
    download_geoweaver_jar()
    payload = {"id": workflow_id, "type": "workflow"}
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail", data=payload
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
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'workflow'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if 'get_ipython' in globals():
        data_json = data.json()
        table_html, _ = create_table(data_json)
        display(HTML(table_html))
    else:
        data_json = data.json()
        df = pd.DataFrame(data_json)
        return df
