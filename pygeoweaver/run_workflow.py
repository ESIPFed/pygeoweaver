import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def run_worklfow(*, workflow_id, workflow_folder_path, workflow_zip_file_path, environments, host, password):
    """
    Missing required parameter: '<workflowId>'
    Usage: <main class> run workflow [-d=<workflowFolderPath>]
                                    [-f=<workflowZipPath>] [-e=<envs>]...
                                    [-h=<hostStrings>]... [-p=<passes>]...
                                    <workflowId>
        <workflowId>           workflow id to run
    -d, --workflow-folder-path=<workflowFolderPath>
                                geoweaver workflow folder path
    -e, --environments=<envs>  environments to run on
    -f, --workflow-zip-file-path=<workflowZipPath>
                                workflow package or path to workflow zip to run
    -h, --hosts=<hostStrings>  hosts to run on
    -p, --passwords=<passes>   passwords to the target hosts
    """
    download_geoweaver_jar()

    if workflow_folder_path and workflow_zip_file_path:
        raise RuntimeError("Please provide either Folder path or Zip path")

    if workflow_folder_path and not workflow_zip_file_path:
        # command to run workflow from folder
        subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
                        "-d", workflow_folder_path,
                        "-e", environments,
                        "-h", host,
                        "-p", password],
                       cwd=f"{get_root_dir()}/")

    if not workflow_folder_path and workflow_zip_file_path:
        subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id,
                        "-e", environments,
                        "-f", workflow_zip_file_path,
                        "-h", host,
                        "-p", password],
                       cwd=f"{get_root_dir()}/")

    raise RuntimeError("Please provide either zip path or directory path to run workflow.")
