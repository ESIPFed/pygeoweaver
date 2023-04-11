"""
The main function of pygeoweaver
To run in CLI mode. 
"""
from pygeoweaver.history_process import show_process_history
from pygeoweaver.list_hosts import list_hosts
from pygeoweaver.list_processes import list_processes
from pygeoweaver.list_workflows import list_workflows
from pygeoweaver.server import start, stop

def main():
    # start geoweaver
    #start()
    # stop geoweaver
    # stop()
    # list resources
    #list_hosts()
    #list_processes()
    #list_workflows()
    # show history
    show_process_history("gfvnp8a7rgh")


if __name__ == "__main__":
    main()
