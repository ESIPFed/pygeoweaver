import os
import json
import zipfile

import requests
import typing

from . import constants
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_java_bin_path, get_root_dir, \
    copy_files


def sync_workflow(workflow_id: str, sync_to_path: typing.Union[str, os.PathLike]):
    download_geoweaver_jar()
    # download workflow
    r = requests.post(f'{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/downloadworkflow',
                      data={'id': workflow_id, 'option': 'workflowwithprocesscodeallhistory'},
                      headers=constants.COMMON_API_HEADER).text
    filename = r.rsplit('/')[-1]
    home_dir = os.path.expanduser("~")
    tmp_dir = os.path.join(home_dir, 'tmp')
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    # unzip the workflow
    with zipfile.ZipFile(os.path.join(home_dir, 'gw-workspace', 'temp', filename)) as ref:
        ref.extractall(os.path.join(home_dir, 'tmp'))
    # check if target workflow path and the unzipped workflow match
    if not sync_to_path:
        raise Exception("Please provide path to workflow that you wish to sync code and history")
    import_id = json.loads(open(os.path.join(home_dir, 'tmp', 'workflow.json'), "r").read()).get("id")
    sync_id = json.loads(open(sync_to_path, "r").read()).get("id")

    if import_id == sync_id:
        # if they match perform file replace
        copy_files(source_folder=os.path.join(home_dir, 'tmp'), destination_folder=sync_to_path)
    else:
        print("Workflow ID mismatch, please check the `sync_to_path` path.")


