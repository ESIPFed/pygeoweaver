import os
import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def run_process(*, process_id: str, host_id: str, password: str, environment: str=None):
    """
    Run a process

    Args: process_id - required
        host_id - required
        password - required
        environment - optional
    """
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "process", f"--host={host_id}",
                    f"--password={password}", f"--environment={environment}", process_id],
                   cwd=f"{get_root_dir()}/")

def run_worklfow(*, workflow_id: str, workflow_folder_path: str=None, workflow_zip_file_path: str=None, 
                 environment_list: str=None, host_list: str, password_list: str):
    """
    Usage: <main class> run workflow [-d=<workflowFolderPath>]
                                    [-f=<workflowZipPath>] [-e=<envs>]...
                                    [-h=<hostStrings>]... [-p=<passes>]...
                                    <workflowId>
        <workflowId>           workflow id to run
    -d, --workflow-folder-path=<workflowFolderPath>
                                geoweaver workflow folder path
    -e, --environments=<envs>  environments to run on. List of environment ids with comma as separator
    -f, --workflow-zip-file-path=<workflowZipPath>
                                workflow package or path to workflow zip to run
    -h, --hosts=<hostStrings>  hosts to run on. list of host ids with comma as separator.
    -p, --passwords=<passes>   passwords to the target hosts. list of passwords with comma as separator. 
    """
    download_geoweaver_jar()

    if not workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        raise RuntimeError("Please provide at least one of the three options: workflow id, " \
                           "folder path or zip path")
    
    if workflow_id and not workflow_folder_path and not workflow_zip_file_path:
        subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
                        "-e", environment_list,
                        "-h", host_list,
                        "-p", password_list],
                       cwd=f"{get_root_dir()}/")

    if workflow_folder_path and not workflow_zip_file_path:
        # command to run workflow from folder
        subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
                        "-d", workflow_folder_path,
                        "-e", environment_list,
                        "-h", host_list,
                        "-p", password_list],
                       cwd=f"{get_root_dir()}/")

    if not workflow_folder_path and workflow_zip_file_path:
        subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
                        "-e", environment_list,
                        "-f", workflow_zip_file_path,
                        "-h", host_list,
                        "-p", password_list],
                       cwd=f"{get_root_dir()}/")
        
