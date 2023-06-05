import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_java_bin_path, get_root_dir


def show_history(history_id):
    """
    Workflow and process history uses the same method to check
    """
    if not history_id:
        raise RuntimeError("history id is missing")
    download_geoweaver_jar()
    subprocess.run([get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "history", history_id], cwd=f"{get_root_dir()}/")
