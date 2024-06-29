import requests
from pygeoweaver.constants import *
import pandas as pd

from pygeoweaver.utils import check_ipython


def get_process_by_name(process_name):
    """
    Get processes by their name.

    :param process_name: The name of the process.
    :type process_name: str
    """
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
    pd.DataFrame(matching_processes)
    if not check_ipython():
        return pd.DataFrame(matching_processes)


def get_process_by_id(process_id):
    """
    Get a process by its ID.

    :param process_id: The ID of the process.
    :type process_id: str
    """
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
    pd.DataFrame(matching_processes)
    if not check_ipython():
        return pd.DataFrame(matching_processes)


def get_process_by_language(language):
    """
    Get processes by their programming language.

    :param language: The programming language of the processes.
    :type language: str
    """
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
    pd.DataFrame(matching_processes)
    if not check_ipython():
        return pd.DataFrame(matching_processes)
