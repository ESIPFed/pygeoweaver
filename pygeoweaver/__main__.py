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


@geoweaver.group("create")
def create_command():
    """
    Create commands for Geoweaver.
    """
    pass






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
