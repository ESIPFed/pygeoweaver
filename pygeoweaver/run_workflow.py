import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def run_worklfow(workflow_id, workflow_folder_path, workflow_zip_file_path, environments, hosts, passwords):
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
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "run", "workflow", workflow_id, 
                    "-d", workflow_folder_path,
                    "-e", environments,
                    "-f", workflow_zip_file_path, 
                    "-h", hosts,
                    "-p", passwords], 
                   cwd=f"{get_root_dir()}/")