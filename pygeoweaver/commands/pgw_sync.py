import os
import json
import shutil
import zipfile

import requests
import typing

from pygeoweaver.constants import *
from pygeoweaver.utils import (
    download_geoweaver_jar,
    copy_files,
    get_spinner,
    safe_exit,
)
from halo import Halo


def overwrite_files(source_dir, destination_dir):
    """
    Overwrite all files from the source directory to the destination directory.
    
    Args:
        source_dir (str): The source directory path.
        destination_dir (str): The destination directory path.
    """
    if not os.path.exists(source_dir):
        print(f"Source directory {source_dir} does not exist.")
        return

    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)
    
    for item in os.listdir(source_dir):
        source_path = os.path.join(source_dir, item)
        destination_path = os.path.join(destination_dir, item)
        
        if os.path.isfile(source_path):
            shutil.copy2(source_path, destination_path)
        elif os.path.isdir(source_path):
            if os.path.exists(destination_path):
                shutil.rmtree(destination_path)
            shutil.copytree(source_path, destination_path)


def sync(process_id: str, local_path: typing.Union[str, os.PathLike], direction: str):
    """
    Sync code for a Geoweaver process between the local machine and the Geoweaver server.

    :param process_id: The ID of the Geoweaver process.
    :param local_path: The local path to save or load the process code.
    :param direction: The direction of the sync, either "download" or "upload".
    """
    with get_spinner(text=f'Sync Geoweaver process {process_id} from database to local folder {local_path}...', 
              spinner='dots'):
        print(f"Proceeding with {direction}\n")
        if direction == "download":
            if not local_path:
                raise Exception("Sync path not found.")
            r = requests.post(
                f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                data={"type": "process", "id": process_id},
            ).json()
            code = r["code"]
            decoded_string = code
            file_name = r["name"]
            ext = None
            if r["lang"] == "python":
                ext = ".py"
            elif r["lang"] == "shell":
                ext = ".sh"
            elif r["lang"] == "jupyter":
                ext = "ipynb"
            else:
                raise Exception("Unknown file format.")
            with open(os.path.join(local_path, file_name + ext), "w") as file:
                file.write(decoded_string)
            print(f"Wrote file {file_name + ext} to {local_path}")
        elif direction == "upload":
            if not local_path:
                raise Exception("Sync path not found.")
            process_prev_state = requests.post(
                f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                data={"type": "process", "id": process_id},
            ).json()
            with open(local_path, "r") as f:
                f_content = f.read()
                process_prev_state["code"] = f_content
                response = requests.post(
                    f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/edit/process",
                    data=json.dumps(process_prev_state),
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    print("Process update was successful")
                else:
                    print("Update failed with status code:", response.status_code)
        else:
            raise Exception(
                "Please specify the direction to sync. Choices - [UPLOAD, DOWNLOAD]"
            )

def sync_workflow(workflow_id: str, sync_to_path: typing.Union[str, os.PathLike]):
    """
    Sync a Geoweaver workflow, including its code and history, between the local machine and the Geoweaver server.

    :param workflow_id: The ID of the Geoweaver workflow.
    :param sync_to_path: The local path to sync the Geoweaver workflow.
    """
    with get_spinner(text=f'Sync Geoweaver workflow {workflow_id} from database to local folder {sync_to_path}...', 
              spinner='dots'):
        download_geoweaver_jar()
        # download workflow
        r = requests.post(
            f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/downloadworkflow",
            data=f"id={workflow_id}&option=workflowwithprocesscodeallhistory",
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            }
        )
        if r.status_code != 200:
            print("Error: Fail to prepare the workflow folder.")
            safe_exit(1)
        home_dir = os.path.expanduser("~")
        source_folder = os.path.join(home_dir, "gw-workspace", "temp", workflow_id)
        # check if target workflow path and the unzipped workflow match
        if not sync_to_path:
            raise Exception(
                "Please provide path to workflow that you wish to sync code and history"
            )
        
        target_workflow_json_path = os.path.join(sync_to_path, "workflow.json")
        if os.path.exists(target_workflow_json_path):
            sync_id = json.loads(
                open(target_workflow_json_path, "r").read()
            ).get("id")

            if workflow_id != sync_id:
                print("Error: Workflow ID mismatch, please check the existing workflow.json in the `sync_to_path` path.")
                safe_exit(1)
        copy_files(
            source_folder=source_folder, destination_folder=sync_to_path
        )
        print("Sync is complete.")
