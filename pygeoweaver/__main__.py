"""
The main function of pygeoweaver
To run in CLI mode. 
"""
import logging
import os
import typing
import click
from pygeoweaver import (
    detail_host,
    detail_process,
    detail_workflow,
    export_workflow,
    show_history,
    import_workflow,
    list_hosts,
    list_processes,
    list_workflows,
    start,
    stop,
    reset_password,
    run_process,
    run_workflow,
    helpwith,
)
from pygeoweaver.constants import GEOWEAVER_DEFAULT_ENDPOINT_URL
from pygeoweaver.commands.pgw_create import create_process, create_process_from_file, create_workflow
from pygeoweaver.commands.pgw_detail import get_process_code
from pygeoweaver.commands.pgw_find import get_process_by_id, get_process_by_language, get_process_by_name
from pygeoweaver.commands.pgw_history import get_process_history, get_workflow_history
from pygeoweaver.commands.pgw_list import list_processes_in_workflow
from pygeoweaver.commands.pgw_sync import sync, sync_workflow
from pygeoweaver.server import check_geoweaver_status, show
from halo import Halo


def setup_logging():
    log_file = '~/geoweaver.log'
    log_file = os.path.expanduser(log_file)

    # Ensure the directory for the log file exists, create if not
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    with open('logging.ini', 'rt') as f:
        config_str = f.read()
        config_str = config_str.replace('%(log_file)s', os.path.expanduser(log_file))

    config_file = 'logging_temp.ini'
    with open(config_file, 'wt') as f:
        f.write(config_str)

    logging.config.fileConfig(config_file)
    os.remove(config_file)

setup_logging()


@click.group()
def geoweaver():
    """
    Geoweaver CLI: A tool for managing workflows and processes.
    """
    pass


@geoweaver.command("start")
@click.option('--force', is_flag=True, help='Force overwrite the Geoweaver JAR file if it already exists.')
def start_command(force):
    """
    Start the Geoweaver application.
    """
    start(force)


@geoweaver.command("stop")
def stop_command():
    """
    Start the Geoweaver application.
    """
    stop()

@geoweaver.command("show")
@click.option('--geoweaver-url', default=GEOWEAVER_DEFAULT_ENDPOINT_URL, help='Geoweaver URL (default is GEOWEAVER_DEFAULT_ENDPOINT_URL)')
def show_command(geoweaver_url):
    """
    Show graphical user interface of Geoweaver in browser

    Args:
        geoweaver_url (_type_): _description_
    """
    show(geoweaver_url)


@geoweaver.command("reset_password")
def reset_password_command():
    """
    Reset the password for localhost.
    """
    reset_password()


@geoweaver.group("create")
def create_command():
    """
    Create commands for Geoweaver.
    """
    pass


@create_command.command("process")
@click.option('--lang', prompt='Programming Language', help='The programming language of the process')
@click.option('--description', prompt='Description', help='The description of the process')
@click.option('--name', prompt='Name', help='The name of the process')
@click.option('--code', prompt='Code', help='The code of the process')
@click.option('--file-path', prompt='File Path', type=click.Path(exists=True), help='The path to the file containing the code')
@click.option('--owner', default='111111', help='The owner of the process (default: "111111")')
@click.option('--confidential', is_flag=True, help='Set if the process is confidential')
def create_process_command(lang, description, name, code, file_path, owner, confidential):
    """
    Create a process with given code or given file_path, which ever is valid first.
    """
    if code is not None:
        create_process(lang, description, name, code, owner, confidential)
    elif file_path is not None:
        create_process_from_file(lang, description, name, file_path, owner, confidential)


@create_command.command("workflow")
@click.option('--description', prompt='Description', help='The description of the workflow')
@click.option('--edges', prompt='Edges', help='The edges of the workflow')
@click.option('--name', prompt='Name', help='The name of the workflow')
@click.option('--nodes', prompt='Nodes', help='The nodes of the workflow')
@click.option('--owner', default='111111', help='The owner of the workflow (default: "111111")')
@click.option('--confidential', is_flag=True, help='Set if the workflow is confidential')
def create_workflow_command(description, edges, name, nodes, owner, confidential):
    """
    Create a workflow with given data if valid.
    """
    create_workflow(description, edges, name, nodes, owner, confidential)


@geoweaver.group("detail")
def detail_command():
    """
    Detail commands for Geoweaver.
    """
    pass


@detail_command.command("workflow")
@click.argument('workflow_id', type=str)
def detail_workflow_command(workflow_id):
    """
    Display detailed information about a workflow.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    """
    detail_workflow(workflow_id)


@detail_command.command("process")
@click.argument('process_id', type=str)
def detail_process_command(process_id):
    """
    Display detailed information about a process.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    detail_process(process_id)


@detail_command.command("host")
@click.argument('host_id', type=str)
def detail_host_command(host_id):
    """
    Display detailed information about a host.

    :param host_id: The ID of the host.
    :type host_id: str
    """
    detail_host(host_id)


@detail_command.command("code")
@click.argument('process_id', type=str)
def get_process_code_command(process_id):
    """
    Get the code of a process.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    get_process_code(process_id)


@geoweaver.group("export")
def export_command():
    """
    Export commands for Geoweaver.
    """
    pass


@export_command.command()
@click.argument('workflow_id', type=str)
@click.option('--mode', default=4, type=int, help='Exportation mode options: 1 - workflow only, 2 - workflow with process code, 3 - workflow with process code and only good history, 4 - workflow with process code and all the history. Default option is 4.')
@click.argument('target_file_path', type=click.Path())
@click.option('--unzip', is_flag=True, help='Unzip the exported file.')
@click.option('--unzip-directory-name', help='Specify the directory name when unzipping.')
def export_workflow_command(workflow_id, mode, target_file_path, unzip, unzip_directory_name):
    """
    Export a Geoweaver workflow.

    :param workflow_id: Geoweaver workflow ID.
    :type workflow_id: str
    :param mode: Exportation mode options: 1 - workflow only, 2 - workflow with process code, 3 - workflow with process code and only good history, 4 - workflow with process code and all the history. Default option is 4.
    :type mode: int
    :param target_file_path: Target file path to save the workflow zip.
    :type target_file_path: str
    :param unzip: Unzip the exported file.
    :type unzip: bool
    :param unzip_directory_name: Specify the directory name when unzipping.
    :type unzip_directory_name: str
    """
    export_workflow(workflow_id, mode, target_file_path, unzip, unzip_directory_name)


@geoweaver.group("find")
def find_command():
    """
    Find commands for Geoweaver.
    """
    pass


@find_command.command("name")
@click.argument('process_name', type=str)
def get_process_by_name_command(process_name):
    """
    Get processes by their name.

    :param process_name: The name of the process.
    :type process_name: str
    """
    return get_process_by_name(process_name)


@find_command.command("id")
@click.argument('process_id', type=str)
def get_process_by_id_command(process_id):
    """
    Get a process by its ID.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    return get_process_by_id(process_id)
    
    
@find_command.command("language")
@click.argument('language', type=str)
def get_process_by_language_command(language):
    """
    Get processes by their programming language.

    :param language: The programming language of the processes.
    :type language: str
    """
    return get_process_by_language(language)

@geoweaver.group("history")
def history_command():
    """
    history commands for Geoweaver.
    """
    pass

@history_command.command("show")
@click.argument('history_id', type=str)
def show_history_command(history_id):
    """
    Show history for a workflow or process.

    :param history_id: The ID of the history.
    :type history_id: str
    """
    show_history(history_id)
    
    
@history_command.command("get_process")
@click.argument('process_id', type=str)
def get_process_history_command(process_id):
    """
    Get list of history for a process using process id.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    get_process_history(process_id)


@history_command.command("get_workflow")
@click.argument('workflow_id', type=str)
def get_workflow_history_command(workflow_id):
    """
    Get list of history for a workflow using workflow id.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    """
    get_workflow_history(workflow_id)


@geoweaver.group("import")
def import_command():
    """
    import commands for Geoweaver.
    """
    pass

@import_command.command("workflow")
@click.argument('workflow_zip_file_path', type=click.Path(exists=True, dir_okay=False))
def import_workflow_command(workflow_zip_file_path):
    """
    Import a workflow from a zip file.

    :param workflow_zip_file_path: The path to the Geoweaver workflow zip file.
    :type workflow_zip_file_path: str
    """
    import_workflow(workflow_zip_file_path)


@geoweaver.group("list")
def list_command():
    """
    list commands for Geoweaver.
    """
    pass


@list_command.command("host")
def list_hosts_command():
    """
    List all hosts in Geoweaver.

    Downloads the Geoweaver JAR, then runs the 'list' command with the '--host' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    list_hosts()


@list_command.command("process")
def list_processes_command():
    """
    List all processes in Geoweaver.

    Downloads the Geoweaver JAR, ensures executable permissions, and then runs the 'list' command with the '--process' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    list_processes()


@list_command.command()
@click.argument('workflow_id', type=str)
def list_processes_in_workflow_command(workflow_id):
    """
    List processes in a specific workflow.

    Downloads the Geoweaver JAR and queries the Geoweaver server for details of a workflow.
    Extracts information about nodes in the workflow and returns a list of dictionaries containing 'title' and 'id'.

    :param workflow_id: The ID of the workflow.
    :type workflow_id: str
    :return: List of dictionaries containing 'title' and 'id' of processes in the workflow.
    :rtype: list
    """
    list_processes_in_workflow(workflow_id)


@list_command.command("workflow")
def list_workflows_command():
    """
    List all workflows in Geoweaver.

    Downloads the Geoweaver JAR, then runs the 'list' command with the '--workflow' option.

    Note: Requires Geoweaver to be initialized and the JAR file to be available.
    """
    list_workflows()


@geoweaver.group("run")
def run_command():
    """
    Run commands for Geoweaver.
    """
    pass


@run_command.command()
@click.option('--process-id', required=True, type=str, help='ID of the process.')
@click.option('--host-id', required=True, type=str, help='ID of the host.')
@click.option('--password', type=str, help='Password for authentication.')
@click.option('--environment', type=str, help='Environment for the process.')
@click.option('--sync-path', type=click.Path(exists=True), help='Path for synchronization.')
def run_process_command(process_id, host_id, password, environment, sync_path):
    """
    Run a process.

    Args:
        --process-id: ID of the process. (required)
        --host-id: ID of the host. (required)
        --password: Password for authentication. (optional)
        --environment: Environment for the process. (optional)
        --sync-path: Path for synchronization. (optional)
    """
    run_process(
        process_id=process_id,
        host_id=host_id,
        password=password,
        environment=environment,
        sync_path=sync_path,
    )


@run_command.command()
@click.argument('workflow_id', type=str)
@click.option('--workflow-folder-path', '-d', type=str, help='Geoweaver workflow folder path.')
@click.option('--workflow-zip-file-path', '-f', type=str, help='Path to workflow zip file.')
@click.option('--environments', '-e', type=str, help='Environments to run on. List of environment ids with comma as separator.')
@click.option('--hosts', '-h', type=str, help='Hosts to run on. List of host ids with comma as separator.')
@click.option('--passwords', '-p', type=str, help='Passwords to the target hosts. List of passwords with comma as separator.')
@click.option('--sync-path', type=click.Path(exists=True), help='Path for synchronization.')
def run_workflow_command(workflow_id, workflow_folder_path, workflow_zip_file_path, environments, hosts, passwords, sync_path):
    """
    Run a workflow.

    Args:
        <workflow_id>: Workflow ID to run.
        -d, --workflow-folder-path: Geoweaver workflow folder path. (optional)
        -f, --workflow-zip-file-path: Path to workflow zip file. (optional)
        -e, --environments: Environments to run on. List of environment ids with comma as separator. (optional)
        -h, --hosts: Hosts to run on. List of host ids with comma as separator. (optional)
        -p, --passwords: Passwords to the target hosts. List of passwords with comma as separator. (optional)
    """
    run_workflow(
        workflow_id=workflow_id,
        workflow_folder_path=workflow_folder_path,
        workflow_zip_file_path=workflow_zip_file_path,
        environment_list=environments,
        host_list=hosts,
        password_list=passwords,
        sync_path=sync_path,
    )


@geoweaver.group("sync")
def sync_command():
    """
    sync commands for Geoweaver.
    """
    pass

@sync_command.command("process")
@click.option('--process-id', required=True, type=str, help='The ID of the Geoweaver process.')
@click.option('--local-path', required=True, type=click.Path(exists=True, file_okay=True, dir_okay=True),
              help='The local path to save or load the process code.')
@click.option('--direction', required=True, type=click.Choice(['download', 'upload'], case_sensitive=False),
              help='The direction of the sync, either "download" or "upload".')
def sync_process_command(process_id: str, local_path: typing.Union[str, os.PathLike], direction: str):
    """
    Sync code for a Geoweaver process between the local machine and the Geoweaver server.

    :param process_id: The ID of the Geoweaver process.
    :type process_id: str
    :param local_path: The local path to save or load the process code.
    :type local_path: Union[str, os.PathLike]
    :param direction: The direction of the sync, either "download" or "upload".
    :type direction: str
    """
    
    sync(process_id, local_path, direction)
    

@sync_command.command("workflow")
@click.option('--workflow-id', required=True, type=str, help='The ID of the Geoweaver workflow.')
@click.option('--sync-to-path', required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='The local path to sync the Geoweaver workflow.')
def sync_workflow_command(workflow_id: str, sync_to_path: typing.Union[str, os.PathLike]):
    """
    Sync a Geoweaver workflow, including its code and history, between the local machine and the Geoweaver server.

    :param workflow_id: The ID of the Geoweaver workflow.
    :type workflow_id: str
    :param sync_to_path: The local path to sync the Geoweaver workflow.
    :type sync_to_path: Union[str, os.PathLike]
    """
    
    sync_workflow(workflow_id, sync_to_path)


@geoweaver.command("status")
def status():
    """
    Check the status of Geoweaver.
    """
    with Halo(text='Checking Geoweaver status...', spinner='dots'):
        geoweaver_running = check_geoweaver_status()
    
    if geoweaver_running:
        click.echo(click.style("Geoweaver is running", fg='green', bold=True))
    else:
        click.echo(click.style("Geoweaver is not running", fg='red', bold=True))
    


if __name__ == "__main__":
    geoweaver()
