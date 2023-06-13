import json

import requests
import subprocess
from . import constants
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir, check_ipython,
)
import pandas as pd


def get_process_by_name(process_name):
    response = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={'type': 'process'})
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process['name'] == process_name:
            matching_processes.append(process)
    pd.DataFrame(matching_processes)


def get_process_by_id(process_id):
    response = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={'type': 'process'})
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process['id'] == process_id:
            matching_processes.append(process)
    pd.DataFrame(matching_processes)


def get_process_by_language(language):
    response = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={'type': 'process'})
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process['lang'] == language:
            matching_processes.append(process)
    pd.DataFrame(matching_processes)

