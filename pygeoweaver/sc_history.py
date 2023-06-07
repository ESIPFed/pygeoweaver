import subprocess
import requests

from . import constants
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_java_bin_path, get_root_dir


def show_history(history_id):
    """
    Workflow and process history uses the same method to check
    """
    if not history_id:
        raise RuntimeError("history id is missing")
    download_geoweaver_jar()
    subprocess.run([get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "history", history_id],
                   cwd=f"{get_root_dir()}/")


def get_process_history(process_id):
    """
        Get list of history for a process using process id
    :param process_id: str    :type process_id: str
    """
    if not process_id:
        raise Exception("please pass `process_id` as a parameter to the function.")
    r = requests.post(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/logs", data={'type': 'process', 'id': process_id}).json()
    return r


def get_workflow_history(workflow_id):
    """
        Get list of history for a workflow using workflow id
    :param workflow_id: str
    """
    if not workflow_id:
        raise Exception("please pass `workflow_id` as a parameter to the function.")
    r = requests.get(f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/logs", data={'type': 'workflow', 'id': workflow_id}).json()
    return r
