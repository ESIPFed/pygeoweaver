import json

import requests

from IPython.core.display import display, HTML

from pygeoweaver.constants import *
from pygeoweaver.utils import (
    download_geoweaver_jar,
    check_ipython, create_table,
)
import pandas as pd


def list_hosts():
    from IPython import get_ipython
    ip = get_ipython()
    download_geoweaver_jar()
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'host'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if ip is not None:
        # Running in a Jupyter Notebook, display as HTML table
        data_json = data.json()
        table_html = create_table(data_json)
        return display(HTML(table_html))
    else:
        # Not running in a Jupyter Notebook, display as Pandas DataFrame
        data_json = data.json()
        df = pd.DataFrame(data_json)
        return df


def list_processes():
    from IPython import get_ipython
    ip = get_ipython()
    download_geoweaver_jar()
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'process'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if ip is not None:
        data_json = data.json()
        table_html = create_table(data_json)
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
    from IPython import get_ipython
    ip = get_ipython()
    download_geoweaver_jar()
    url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list"
    form_data = {'type': 'workflow'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = requests.post(url=url, headers=headers, data=form_data)

    if ip is not None:
        data_json = data.json()
        table_html = create_table(data_json)
        display(HTML(table_html))
    else:
        data_json = data.json()
        df = pd.DataFrame(data_json)
        return df
