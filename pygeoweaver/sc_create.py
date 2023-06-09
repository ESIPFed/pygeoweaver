import json
import requests
from IPython.core.display_functions import display
from ipywidgets import widgets
from pydantic import BaseModel

from . import constants
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_java_bin_path, get_root_dir, \
    check_ipython


class ProcessData(BaseModel):
    type: str = "process"
    lang: str
    description: str
    name: str
    code: str
    owner: str = "111111"
    confidential: bool = False


class WorkflowData(BaseModel):
    type: str = "workflow"
    confidential: bool = False
    description: str
    edges: str
    name: str
    nodes: str
    owner: str = "111111"


def create_process(lang, description, name, code, owner="111111", confidential=False):
    """
        Function to create a process with given data if valid.
    :param lang: The programming language of the process
    :type lang: str
    :param description: The description of the process
    :type description: str
    :param name: The name of the process
    :type name: str
    :param code: The code of the process
    :type code: str
    :param owner: The owner of the process, defaults to "111111"
    :type owner: str, optional
    :param confidential: The confidentiality status of the process, defaults to False
    :type confidential: bool, optional
    :return: Returns the id of the created process
    :rtype: dict
    """
    download_geoweaver_jar()
    process = ProcessData(
        type="process",
        lang=lang,
        description=description,
        name=name,
        code=code,
        owner=owner,
        confidential=confidential
    )
    data_json = process.json()
    r = requests.post(
        f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/add/process",
        data=data_json,
        headers=constants.COMMON_API_HEADER
    )
    if check_ipython() and r.ok:
        data = json.loads(data_json)
        header_labels = ['Key', 'Value']
        header_widgets = [widgets.Label(value=label) for label in header_labels]
        row_widgets = [widgets.Label(value=str(item)) for item in data.items()]
        grid = widgets.GridBox(header_widgets + row_widgets,
                               layout=widgets.Layout(grid_template_columns="repeat(2, auto)"))
        grid.layout.border = '1px solid black'
        display(grid)
    else:
        return r.json()


def create_workflow(description, edges, name, nodes, owner="111111", confidential=False):
    """
        Function to create a workflow with given data if valid
    :param confidential: The confidentiality status of the workflow, defaults to False
    :type confidential: bool, optional
    :param description: The description of the workflow
    :type description: str
    :param edges: The edges of the workflow
    :type edges: str
    :param name: The name of the workflow
    :type name: str
    :param nodes: The nodes of the workflow
    :type nodes: str
    :param owner: The owner of the workflow, defaults to "111111"
    :type owner: str, optional
    :return: Returns the id of the created workflow
    :rtype: dict
    """
    download_geoweaver_jar()
    workflow = WorkflowData(
        type="workflow",
        confidential=confidential,
        description=description,
        edges=edges,
        name=name,
        nodes=nodes,
        owner=owner
    )
    data_json = workflow.json()
    r = requests.post(
        f"{constants.GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/add/workflow",
        data=data_json,
        headers=constants.COMMON_API_HEADER
    )
    if check_ipython():
        pass
    else:
        return r.json()
