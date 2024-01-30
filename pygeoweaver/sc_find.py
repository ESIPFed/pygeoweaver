import requests
from pygeoweaver.constants import *
import pandas as pd


def get_process_by_name(process_name):
    response = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={"type": "process"}
    )
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process["name"] == process_name:
            matching_processes.append(process)
    pd.set_option("display.max_columns", None)  # Display all columns
    pd.set_option("display.max_rows", None)  # Display all rows
    pd.set_option("display.expand_frame_repr", False)  # Prevent truncation of columns
    return pd.DataFrame(matching_processes)


def get_process_by_id(process_id):
    response = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={"type": "process"}
    )
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process["id"] == process_id:
            matching_processes.append(process)
    pd.set_option("display.max_columns", None)  # Display all columns
    pd.set_option("display.max_rows", None)  # Display all rows
    pd.set_option("display.expand_frame_repr", False)  # Prevent truncation of columns
    return pd.DataFrame(matching_processes)


def get_process_by_language(language):
    response = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/list", data={"type": "process"}
    )
    process_list = response.json()

    matching_processes = []

    for process in process_list:
        if process["lang"] == language:
            matching_processes.append(process)
    pd.set_option("display.max_columns", None)  # Display all columns
    pd.set_option("display.max_rows", None)  # Display all rows
    pd.set_option("display.expand_frame_repr", False)  # Prevent truncation of columns
    return pd.DataFrame(matching_processes)
