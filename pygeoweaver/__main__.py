"""
The main function of pygeoweaver
To run in CLI mode. 
"""
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
from pygeoweaver.sc_create import create_process, create_process_from_file, create_workflow
from pygeoweaver.sc_detail import get_process_code
from pygeoweaver.sc_find import get_process_by_id, get_process_by_language, get_process_by_name
from pygeoweaver.server import show


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
    get_process_by_name(process_name)


@find_command.command("id")
@click.argument('process_id', type=str)
def get_process_by_id_command(process_id):
    """
    Get a process by its ID.

    :param process_id: The ID of the process.
    :type process_id: str
    """
    get_process_by_id(process_id)
    
    
@find_command.command("language")
@click.argument('language', type=str)
def get_process_by_language_command(language):
    """
    Get processes by their programming language.

    :param language: The programming language of the processes.
    :type language: str
    """
    get_process_by_language(language)


def main():
    # start geoweaver
    # start()
    # stop geoweaver
    # stop()
    # list resources
    # list_hosts()
    # list_processes()
    # list_workflows()
    # show history
    # show_history("ll3u3W78eOEfklxhBJ")
    # detail host
    # detail_host("100001")
    # detail process
    # detail_process("7pxu8c")
    # detail_workflow("5jnhcrq33znbu2mue9v2")
    # import workflow
    # import_workflow("/Users/joe/Downloads/gr3ykr8dynu12vrwq11oy.zip")
    # export workflow
    # export_workflow("gr3ykr8dynu12vrwq11oy", "4", "/Users/joe/Downloads/test_pygeoweaver_export.zip")
    # run process
    # run_process(process_id="7zwnvx", host_id="100001", )
    # run workflow by id
    # run_worklfow(workflow_id="9sszomwhiiusakodb1ft", host_list="100001", password_list="xxx",
    #              environment_list="",)
    # run_workflow(workflow_id="9sszomwhiiusakodb1ft", host_list="100001", )
    # run workflow by zip path

    # run workflow by folder path

    # reset localhost password for Geoweaver
    # reset_password()
    # show()
    # helpwith()
    # check_java()
    pass


if __name__ == "__main__":
    geoweaver()
