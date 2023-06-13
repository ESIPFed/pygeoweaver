"""
Detail subcommand
"""

import subprocess

import requests
from . import constants

from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def detail_workflow(workflow_id):
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--workflow-id={workflow_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )


def detail_process(process_id):
    if not process_id:
        raise RuntimeError("Process id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--process-id={process_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )


def detail_host(host_id):
    if not host_id:
        raise RuntimeError("Host id is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "detail",
            f"--host-id={host_id}",
        ],
        cwd=f"{get_root_dir()}/",
    )


def get_code_for_process(process_id):
    r = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
                      data={'type': 'process', 'id': process_id}).json()
    code = r['code']
    decoded_string = code
    print(decoded_string)


