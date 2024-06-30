import http
import json
import logging
import subprocess
import traceback
from urllib.parse import urlencode, urlparse

import click
import pandas as pd
import requests
from tabulate import tabulate

from pygeoweaver.constants import *
from pygeoweaver.server import check_geoweaver_status, start
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    get_spinner,
    is_interactive,
)

logger = logging.getLogger(__name__)


def display_response_table(response_json):
    """
    Convert the response JSON into a table format and display it.
    
    Args:
        response_json (str or dict): The JSON response to display.
    """
    if isinstance(response_json, str):
        data = json.loads(response_json)
    else:
        data = response_json

    # Convert data into a DataFrame for better visualization
    df = pd.DataFrame([data])

    # Check if running in Jupyter
    if is_interactive():
        from IPython.display import display
        display(df)
    else:
        # Use tabulate for terminal display
        table = tabulate(df, headers='keys', tablefmt='psql')
        print(table)
        


def show_history(history_id):
    """
    History uses the same method to check
    """
    if not history_id:
        raise RuntimeError("history id is missing")
    
    try:
        if not check_geoweaver_status():
            start()
        
        log_url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/log"
        json_data = f"type=process&id={history_id}"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
        response = requests.post(log_url, headers=headers, data=json_data)

        if response.status_code == 200:
            try:
                display_response_table(response.json())
            except requests.exceptions.JSONDecodeError:
                raise ValueError('Response is not in JSON format:', response.text)
        else:
            raise ValueError(f'POST request failed with status code {response.text}')
    except Exception as e:
        with get_spinner(text=f'Get workflow history...', spinner='dots'):
            logger.error(e)
            traceback_str = traceback.format_exc()
            print(f"Error occurred: {str(e)}")
            print(f"Traceback:\n{traceback_str}")
            
            download_geoweaver_jar()
            process = subprocess.run(
                [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "history", history_id],
                cwd=f"{get_root_dir()}/",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        
        print(process.stdout)
        if process.stderr:
            print("=== Error ===")
            print(process.stderr)
            logger.error(process.stderr)


def get_process_history(process_id):
    """
        Get list of history for a process using process id
    :param process_id: str    :type process_id: str
    """
    if not process_id:
        raise Exception("please pass `process_id` as a parameter to the function.")
    try:
        print("why it is still here")
        if check_geoweaver_status():
            start(exit_on_finish=False)
            print("why it is still here")
        
        json_data = f"type=process&id={process_id}"
        print(json_data)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
        r = requests.post(
            f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/logs",
            data=json_data,
            headers=headers,
        )
        print("r.text = ", r.text)
        if r.status_code == 200:
            try:
                display_response_table(r.json())
            except requests.exceptions.JSONDecodeError:
                raise ValueError('Response is not in JSON format:', r.text)
        else:
            raise ValueError(f'POST request failed with status code {r.text}')
    except Exception as e:
        with get_spinner(text=f'Get workflow history...', spinner='dots'):
            process = subprocess.run(
                f"{get_java_bin_path()} -jar {get_geoweaver_jar_path()} process-history {process_id}",
                cwd=f"{get_root_dir()}/",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        
        print(process.stdout)
        if process.stderr:
            print("=== Error ===")
            print(process.stderr)
            logger.error(process.stderr)


def get_workflow_history(workflow_id):
    """
        Get list of history for a workflow using workflow id
    :param workflow_id: str
    """
    if not workflow_id:
        raise Exception("please pass `workflow_id` as a parameter to the function.")
    try:
        if check_geoweaver_status():
            start()
        r = requests.post(
            f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/logs",
            data={"type": "workflow", "id": workflow_id},
        ).json()
        df = pd.DataFrame(r)
        df["history_begin_time"] = pd.to_datetime(df["history_begin_time"], unit="ms")
        df["history_end_time"] = pd.to_datetime(df["history_end_time"], unit="ms")
        if is_interactive():
            return df
        else:
            print(df)
    except Exception as e:
        with get_spinner(text=f'Get workflow history via slow CLI...', spinner='dots'):
            process = subprocess.run(
                f"{get_java_bin_path()} -jar {get_geoweaver_jar_path()} workflow-history {workflow_id}",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, 
                cwd=f"{get_root_dir()}/",
            )
            
        print(process.stdout)
        if process.stderr:
            print("=== Error ===")
            print(process.stderr)
            logger.error(process.stderr)


def save_history(code: str = None, status: str = None, log_output: str = None, ):
    
    pass
