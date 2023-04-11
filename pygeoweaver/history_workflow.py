import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def show_workflow_history(workflow_history_id):
    if not workflow_history_id:
        raise RuntimeError("Workflow history id is missing")
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "history", workflow_history_id], cwd=f"{get_root_dir()}/")
