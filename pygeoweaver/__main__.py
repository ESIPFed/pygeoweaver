"""
The main function of pygeoweaver
To run in CLI mode. 
"""
from pygeoweaver.sc_detail import detail_host, detail_process, detail_workflow
from pygeoweaver.sc_export import export_workflow
from pygeoweaver.sc_history import show_history
from pygeoweaver.sc_import import import_workflow
from pygeoweaver.sc_list import list_hosts, list_processes, list_workflows
from pygeoweaver.server import start, stop

def main():
    # start geoweaver
    #start()
    # stop geoweaver
    # stop()
    # list resources
    #list_hosts()
    #list_processes()
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
    export_workflow("gr3ykr8dynu12vrwq11oy", "4", "/Users/joe/Downloads/test_pygeoweaver_export.zip")


if __name__ == "__main__":
     main()