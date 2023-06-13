import getpass
import json
import os
import subprocess

import requests

from . import constants
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def run_process(
        *,
        process_id: str,
        host_id: str,
        password: str = None,
        environment: str = None,
        sync_path: os.PathLike = None,
):
    """
    Run a process

    Args: process_id - required
        host_id - required
        password - optional
        environment - optional
    """
    if password is None:
        # prompt to ask for password
        password = getpass.getpass(f"Enter password for host - {host_id}: ")

    if sync_path:
        if not os.path.exists(sync_path):
            print('The specified path does nto exists')
        print('Updating code on workflow with the given file path.\n')
        f = open(sync_path, "r")
        context = f.read()
        f.close()
        details = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                                data={'type': 'process', 'id': process_id}).json()
        details['code'] = context
        requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/edit/process",
                      data=json.dumps(details), headers={'Content-Type': 'application/json'})

    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "run",
            "process",
            f"--host={host_id}",
            f"--password={password}",
            f"--environment={environment}",
            process_id,
        ],
        cwd=f"{get_root_dir()}/",
    )


def run_workflow(
        *,
        workflow_id: str,
        workflow_folder_path: str = None,
        workflow_zip_file_path: str = None,
        environment_list: str = None,
        host_list: str = None,
        password_list: str = None,
        sync_path: os.PathLike = None,
):
    """
    Usage: <main class> run workflow [-d=<workflowFolderPath>]
                                    [-f=<workflowZipPath>] [-e=<envs>]...
                                    [-h=<hostStrings>]... [-p=<passes>]...
                                    <workflowId>
        <workflowId>           workflow id to run
    -d, --workflow-folder-path=<workflowFolderPath>
                                geoweaver workflow folder path
    -e, --environments=<envs>  environments to run on. List of environment ids with comma as separator
    -f, --workflow-zip-file-path=<workflowZipPath>
                                workflow package or path to workflow zip to run
    -h, --hosts=<hostStrings>  hosts to run on. list of host ids with comma as separator.
    -p, --passwords=<passes>   passwords to the target hosts. list of passwords with comma as separator.
    """
    download_geoweaver_jar()

    if password_list is None:
        password_list = getpass.getpass(f"Enter password for host: ")

    if sync_path:
        from . import sync_workflow

        sync_workflow(workflow_id=workflow_id, sync_to_path=sync_path)

    if not workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        raise RuntimeError(
            "Please provide at least one of the three options: workflow id, "
            "folder path or zip path"
        )

    if workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        command = [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "run", "workflow",
                   workflow_id, "-h", host_list, "-p", password_list]
        subprocess.run(command, cwd=f"{get_root_dir()}/")

    if workflow_folder_path and not workflow_zip_file_path:
        # command to run workflow from folder
        # command = [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
        #            "-d", workflow_folder_path, "-h", host_list, "-p", password_list]
        command = f"{get_java_bin_path()} -jar {get_geoweaver_jar_path()} run workflow {workflow_id}" \
                  f"-d {workflow_folder_path} -h {host_list} -p {password_list}"
        subprocess.run(command, cwd=f"{get_root_dir()}/", shell=True)

    if not workflow_folder_path and workflow_zip_file_path:
        command = [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id, "-f",
                   workflow_zip_file_path, "-h", host_list, "-p", password_list]
        subprocess.run(command, cwd=f"{get_root_dir()}/")
