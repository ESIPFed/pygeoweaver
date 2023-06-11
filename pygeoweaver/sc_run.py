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
    password: str,
    environment: str = None,
    sync_path: os.PathLike = None,
):
    """
    Run a process

    Args: process_id - required
        host_id - required
        password - required
        environment - optional
    """
    if sync_path:
        ext, matching_dict = None, None
        process_file = os.path.exists(os.path.join(sync_path, "code", "process.json"))
        if not process_file:
            print("process file does not exists, please check the path")
            return
        p_file = json.loads(
            open(os.path.join(sync_path, "code", "process.json"), "r").read()
        )
        for item in p_file:
            if item.get("id") == process_id:
                matching_dict = item
                break
        if not matching_dict:
            print("Could not find the file, please check the path")
            return
        if matching_dict["lang"] == "python":
            ext = ".py"
        if matching_dict["lang"] == "bash":
            ext = ".bash"
        if not ext:
            print("Invalid file format.")
        source_filename = matching_dict["name"] + ext
        source_file_exists = os.path.exists(
            os.path.join(sync_path, "code", source_filename)
        )
        if source_file_exists:
            f = open(os.path.join(sync_path, "code", source_filename), "r").read()
            matching_dict["code"] = f
            requests.post(
                f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/edit/process",
                data=json.dumps(matching_dict),
                headers={"Content-Type": "application/json"},
            )
        else:
            print("File does not exists")
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
        # prompt to ask for password
        password_list = []
        for host in host_list.split(","):
            password = getpass.getpass(f"Enter password for host - {host}: ")
            password_list.append(password)
    elif len(password_list.split(",")) != len(host_list.split(",")):
        raise RuntimeError("The password list length doesn't match host list")

    if sync_path:
        from . import sync_workflow

        sync_workflow(workflow_id=workflow_id, sync_to_path=sync_path)

    if not workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        raise RuntimeError(
            "Please provide at least one of the three options: workflow id, "
            "folder path or zip path"
        )

    if workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        command = [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "run",
            "workflow",
            workflow_id,
        ]
        if environment_list:
            command.extend(["-e", environment_list])
        command.extend(["-h", host_list, "-p", ",".join(password_list)])
        subprocess.run(command, cwd=f"{get_root_dir()}/")

    if workflow_folder_path and not workflow_zip_file_path:
        # command to run workflow from folder
        command = [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "run",
            "workflow",
            workflow_id,
        ]
        if environment_list:
            command.extend(["-e", environment_list])
        command.extend(
            ["-d", workflow_folder_path, "-h", host_list, "-p", password_list]
        )
        subprocess.run(command, cwd=f"{get_root_dir()}/")

    if not workflow_folder_path and workflow_zip_file_path:
        command = [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "run",
            "workflow",
            workflow_id,
        ]
        if environment_list:
            command.extend(["-e", environment_list])
        command.extend(
            ["-f", workflow_zip_file_path, "-h", host_list, "-p", password_list]
        )
        subprocess.run(command, cwd=f"{get_root_dir()}/")
