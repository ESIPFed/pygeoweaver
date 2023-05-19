import os
import subprocess
import requests
import platform
import sys


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

    print("Downloading latest version of Geoweaver...")
    geoweaver_url = "https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
    r = requests.get(geoweaver_url)

    with open(get_geoweaver_jar_path(), 'wb') as f:
        f.write(r.content)

    if check_geoweaver_jar():
        print("Geoweaver.jar is downloaded")

    else:
        raise RuntimeError("Fail to download geoweaver.jar")


def checkOS():
    if platform.system() == "Linux" or platform == "Linux2":
        return 1
    elif platform.system() == "Darwin":
        return 2
    elif platform == "Windows":
        return 3


def checkIPython():
    return get_ipython().__class__.__name__ == "ZMQInteractiveShell"


def is_java_installed():
    try:
        # Check if Java is installed by running "java -version" command
        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

def install_java():
    system = platform.system()
    if system == "Darwin":
        # Install Java on MacOS using Homebrew
        os.system("/bin/bash -c '/usr/bin/ruby -e \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)\"'")
        os.system("brew install openjdk")
    elif system == "Linux":
        # Install Java on Linux using apt package manager
        os.system("sudo apt update")
        os.system("sudo apt install -y default-jre default-jdk")
    elif system == "Windows":
        # Install Java on Windows using Chocolatey package manager
        os.system("powershell -Command \"Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))\"")
        os.system("choco install -y openjdk")
    else:
        print("Unsupported operating system.")
        sys.exit(1)

def checkJava():
    # Check if Java is installed
    if is_java_installed():
        print("Java is already installed.")
    else:
        print("Java is not installed. Installing...")
        install_java()
        print("Java installation complete.")