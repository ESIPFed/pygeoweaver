import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def list_hosts():
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "list", "--host"], cwd=f"{get_root_dir()}/")


def list_processes():
    download_geoweaver_jar()
    subprocess.run(["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/")
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "list", "--process"], cwd=f"{get_root_dir()}/")


def list_workflows():
    download_geoweaver_jar()
    subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "list", "--workflow"], cwd=f"{get_root_dir()}/")

