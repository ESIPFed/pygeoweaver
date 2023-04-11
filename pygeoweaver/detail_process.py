import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def detail_process(process_id):
    if not process_id:
        raise RuntimeError("Process id is missing")
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "detail", f"--process-id={process_id}"], 
                   cwd=f"{get_root_dir()}/")