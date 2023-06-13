import os
import json
import zipfile

import requests
import typing
from enum import Enum

from . import constants
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
    copy_files,
)


class Direction(str, Enum):
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"


def sync(process_id: str, sync_to_path: typing.Union[str, os.PathLike], direction: Direction):
    print(f'Proceeding with {direction}\n')
    if direction == Direction.DOWNLOAD:
        if not sync_to_path:
            raise Exception("Sync path not found.")
        r = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                          data={'type': 'process', 'id': process_id}).json()
        code = r['code']
        decoded_string = code
        file_name = r['name']
        ext = None
        if r['lang'] == "python":
            ext = ".py"
        elif r['lang'] == "bash":
            ext = ".sh"
        else:
            raise Exception("Unknown file format.")
        with open(os.path.join(sync_to_path, file_name + ext), 'w') as file:
            file.write(decoded_string)
    if direction == Direction.UPLOAD:
        if not sync_to_path:
            raise Exception("Sync path not found.")
        process_prev_state = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                                           data={'type': 'process', 'id': process_id}).json()
        f = open(sync_to_path, 'r')
        f_content = f.read()
        f.close()
        process_prev_state['code'] = f_content
        requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/edit/process",
                      data=json.dumps(process_prev_state), headers={'Content-Type': 'application/json'})
    else:
        raise Exception("Please specify the direction to sync. Choices - [UPLOAD, DOWNLOAD]")


def sync_workflow(workflow_id: str, sync_to_path: typing.Union[str, os.PathLike]):
    download_geoweaver_jar()
    # download workflow
    r = requests.post(
        f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/downloadworkflow",
        data={"id": workflow_id, "option": "workflowwithprocesscodeallhistory"},
    ).text
    filename = r.rsplit("/")[-1]
    home_dir = os.path.expanduser("~")
    tmp_dir = os.path.join(home_dir, "tmp")
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    # unzip the workflow
    with zipfile.ZipFile(
            os.path.join(home_dir, "gw-workspace", "temp", filename)
    ) as ref:
        ref.extractall(os.path.join(home_dir, "tmp"))
    # check if target workflow path and the unzipped workflow match
    if not sync_to_path:
        raise Exception(
            "Please provide path to workflow that you wish to sync code and history"
        )
    import_id = json.loads(
        open(os.path.join(home_dir, "tmp", "workflow.json"), "r").read()
    ).get("id")
    sync_id = json.loads(
        open(os.path.join(sync_to_path, "workflow.json"), "r").read()
    ).get("id")

    if import_id == sync_id:
        # if they match perform file replace
        copy_files(
            source_folder=os.path.join(home_dir, "tmp"), destination_folder=sync_to_path
        )
    else:
        print("Workflow ID mismatch, please check the `sync_to_path` path.")
