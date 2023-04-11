import os
import subprocess
import requests

def get_home_dir():
    return os.path.expanduser('~')

def get_root_dir():
    head, tail = os.path.split(__file__)
    return head

def get_geoweaver_jar_path():
    return f"{get_home_dir()}/geoweaver.jar"

def check_geoweaver_jar():
    return os.path.isfile(get_geoweaver_jar_path())

def download_geoweaver_jar(overwrite=False):
    if check_geoweaver_jar():
        if overwrite:
            os.remove(get_geoweaver_jar_path())
        else:
            subprocess.run(["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/")
            return
    
    geoweaver_url = "https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
    r = requests.get(geoweaver_url)
    
    with open(get_geoweaver_jar_path(),'wb') as f:
        f.write(r.content)
    
    if check_geoweaver_jar():
        print("Geoweaver.jar is downloaded")
        
    else:
        raise RuntimeError("Fail to download geoweaver.jar")
