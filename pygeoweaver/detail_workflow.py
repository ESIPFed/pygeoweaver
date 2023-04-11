import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def detail_workflow(workflow_id):
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "detail", f"--workflow-id={workflow_id}"], 
                   cwd=f"{get_root_dir()}/")

