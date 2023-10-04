"""
Detail subcommand
"""
import json

import pandas as pd
import requests
from pygeoweaver.constants import *

from pygeoweaver.utils import (
    download_geoweaver_jar,
    create_table,
    get_detail
)
import ipywidgets as widgets
from IPython.display import display, HTML


def detail_workflow(workflow_id):
    return get_detail(workflow_id, 'workflow')


def detail_process(process_id):
    return get_detail(process_id, 'process')


def detail_host(host_id):
    return get_detail(host_id, 'host')


def get_process_code(process_id):
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
        data={"type": "process", "id": process_id},
    ).json()
    return r["code"]
