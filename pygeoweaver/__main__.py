"""
The main function of pygeoweaver
To run in CLI mode. 
"""
from pygeoweaver import detail_host, detail_process, detail_workflow, export_workflow, \
    show_history, import_workflow, list_hosts, list_processes, list_workflows, \
    start, stop, reset_password, run_process, run_workflow, helpwith
from pygeoweaver.server import show


def main():
    # start geoweaver
    start()
    # stop geoweaver
    # stop()
    # list resources
    list_hosts()
    list_processes()
    list_workflows()
    # show history
    #show_history("ll3u3W78eOEfklxhBJ")
    # detail host
    # detail_host("100001")
    # detail process
    # detail_process("7pxu8c")
    #detail_workflow("5jnhcrq33znbu2mue9v2")
    # import workflow
    #import_workflow("/Users/joe/Downloads/gr3ykr8dynu12vrwq11oy.zip")
    # export workflow
    # export_workflow("gr3ykr8dynu12vrwq11oy", "4", "/Users/joe/Downloads/test_pygeoweaver_export.zip")
    # run process
    # run_process(process_id="7zwnvx", host_id="100001", password="xxx", environment="",)
    # run workflow by id
    # run_worklfow(workflow_id="9sszomwhiiusakodb1ft", host_list="100001", password_list="xxx", 
    #              environment_list="",)
    # run workflow by zip path

    # run workflow by folder path

    # reset localhost password for Geoweaver
    # reset_password()
    # show()
    # helpwith()
    # check_java()


if __name__ == "__main__":
     main()