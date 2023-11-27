"""
Detail subcommand
"""
import requests

from pygeoweaver.utils import (
    get_detail
)


def detail_workflow(workflow_id):
    return get_detail(workflow_id, 'workflow')


def detail_process(process_id):
    return get_detail(process_id, 'process')


def detail_host(host_id):
    return get_detail(host_id, 'host')


def get_process_code(process_id):
    from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
    r = requests.post(
        f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/detail",
        data={"type": "process", "id": process_id},
    ).json()
    return r["code"]
