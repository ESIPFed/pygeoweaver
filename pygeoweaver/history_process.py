import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def show_process_history(process_history_id):
    if not process_history_id:
        raise RuntimeError("Process history id is missing")
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "history", process_history_id], cwd=f"{get_root_dir()}/")
