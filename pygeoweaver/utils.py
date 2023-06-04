import logging
import os
import subprocess
import requests
import platform
import sys

from IPython import get_ipython


def get_home_dir():
    return os.path.expanduser('~')


def get_root_dir():
    head, tail = os.path.split(__file__)
    return head


def get_module_absolute_path():
    module_path = os.path.abspath(__file__)
    return os.path.dirname(module_path)


def get_geoweaver_jar_path():
    return f"{get_home_dir()}/geoweaver.jar"


def check_geoweaver_jar():
    return os.path.isfile(get_geoweaver_jar_path())


def download_geoweaver_jar(overwrite=False):
    if check_geoweaver_jar():
        if overwrite:
            os.remove(get_geoweaver_jar_path())
        else:
            system = platform.system()
            if not system == "Windows":  # Windows files are exec by default
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


def check_os():
    if platform.system() == "Linux" or platform == "Linux2":
        return 1
    elif platform.system() == "Darwin":
        return 2
    elif platform.system() == "Windows":
        return 3


def check_ipython():
    try:
        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except:
        return False


def is_java_installed():
    try:
        # Check if Java is installed by running "java -version" command
        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False


def install_java():
    system = platform.system()
    if system == "Darwin":
        os.system(
            "/bin/bash -c '/usr/bin/ruby -e \"$(curl -fsSL "
            "https://raw.githubusercontent.com/Homebrew/install/master/install)\"'")
        os.system("brew install openjdk")
    elif system == "Linux":
        # need to check if the package manager type is apt or yum
        # arch / debian
        package_manager = None
        if os.path.exists("/usr/bin/apt"):
            package_manager = "apt"
        elif os.path.exists("/usr/bin/yum"):
            package_manager = "yum"

        if package_manager:
            os.system(f"sudo {package_manager} update")
            os.system(f"sudo {package_manager} install -y default-jre default-jdk")
        else:
            print("Package manager not found. Unable to install Java.")
            sys.exit(1)
    elif system == "Windows":
        # note: this requires admin access to the pc, else it will fail saying
        # Access to the path 'C:\ProgramData\chocolatey\lib-bad' is denied.
        os.system(
            "powershell -Command \"Set-ExecutionPolicy Bypass -Scope Process -Force; ["
            "System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object "
            "System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))\"")
        os.system("choco install -y openjdk")
    else:
        print("Unsupported operating system.")
        sys.exit(1)


def check_java():
    # Check if Java is installed
    if is_java_installed():
        print("Java is already installed.")
    else:
        print("Java is not installed. Installing...")
        install_java()
        print("Java installation complete.")


def get_logger(class_name):
    logger = logging.getLogger(class_name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger
