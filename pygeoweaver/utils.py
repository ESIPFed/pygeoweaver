import os
import sys
import shutil
import logging
import subprocess
import requests
import platform

from IPython import get_ipython
from halo import Halo
from pygeoweaver.constants import GEOWEAVER_URL
from pygeoweaver.pgw_log_config import get_logger
from pygeoweaver.pgw_spinner import Spinner

logger = get_logger(__name__)

def is_interactive():
    """
    Check if the code is running in an interactive environment like Jupyter Notebook.
    """
    try:
        shell = get_ipython().__class__.__name__
        if shell == 'ZMQInteractiveShell':
            return True   # Jupyter notebook or qtconsole
        elif shell == 'TerminalInteractiveShell':
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False      # Probably standard Python interpreter


def get_spinner(text: str, spinner: str = "dots"):
    if is_interactive():
        return Spinner(text=text, style=spinner)
    else:
        return Halo(text=text, spinner=spinner)


def safe_exit(code=0):
    """
    Safely exit the script or notebook session.

    Parameters:
    - code (int): Exit status code (default: 0 for success).
    """
    if 'ipykernel' in sys.modules:
        # Running in Jupyter notebook or IPython
        # don't exit at all in Jupyter
        pass
    else:
        # Running in a terminal or other environment
        sys.exit(code)


def get_home_dir():
    """
    Get the user's home directory.
    """
    if platform.system() == "Windows":
        return os.path.expandvars("%USERPROFILE%")
    else:
        return os.path.expanduser("~")


def get_root_dir():
    """
    Get the root directory of the module.
    """
    head, tail = os.path.split(__file__)
    return head


def detect_rc_file():
    """
    Detect the user's shell and return the appropriate shell configuration (rc) file path.
    Create the rc file if it doesn't exist.
    
    Returns:
        str: Path to the shell configuration file (e.g., .bashrc, .zshrc, config.fish).
    """
    # Detect user's shell
    user_shell = os.environ.get('SHELL', '/bin/bash')
    
    # Determine appropriate shell configuration file based on the detected shell
    if 'bash' in user_shell:
        rc_file = os.path.expanduser("~/.bashrc")
    elif 'zsh' in user_shell:
        rc_file = os.path.expanduser("~/.zshrc")
    elif 'fish' in user_shell:
        rc_file = os.path.expanduser("~/.config/fish/config.fish")
    else:
        # Default to bashrc if unknown shell
        rc_file = os.path.expanduser("~/.bashrc")
    
    # Check if the shell configuration file exists, create if it doesn't
    if not os.path.exists(rc_file):
        print(f"{rc_file} does not exist. Creating it...")
        # Ensure the directory exists (for fish, the config directory may not exist)
        os.makedirs(os.path.dirname(rc_file), exist_ok=True)
        open(rc_file, 'a').close()
    
    return rc_file


def get_java_bin_from_which():
    """
    Get the path of the Java binary using the 'which' command.
    """
    system = platform.system()

    if system == "Darwin" or system == "Linux":
        try:
            # Source ~/.bashrc (Assuming it's a non-login shell)
            bashrc_path = detect_rc_file()
            subprocess.run(["bash", "-c", f"source {bashrc_path}"])

            # Check the location of Java executable
            result = subprocess.run(["which", "java"], capture_output=True, text=True)
            java_bin_path = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Command execution failed: {e.output}")
            return None
    elif system == "Windows":
        # Check the location of Java executable
        result = subprocess.run(["where", "java"], capture_output=True, text=True)
        java_bin_path = result.stdout.strip()
        
    else:
        print("Unsupported platform.")

    return java_bin_path


def check_java_in_default_env(java_exe="java"):
    try:
        # Attempt to run 'java -version' in the default environment
        subprocess.run([java_exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except FileNotFoundError:
        # If 'java' is not found in the default environment
        return False
    except subprocess.CalledProcessError:
        # If 'java' is found but there is an issue with execution
        return False

def get_java_bin_path(java_exe="java"):
    java_bin_path = None
    home_dir = get_home_dir()

    # First check if Java is available in the default environment
    if check_java_in_default_env(java_exe):
        # If Java is found in the default environment, return its path
        logger.info(f"Java is available in the default environment.")
        return java_exe

    # Check if JAVA_HOME is set
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        java_cmd = os.path.join(java_home, "bin", java_exe)
        if os.path.exists(java_cmd):
            java_bin_path = java_cmd
            print(f"Found Java in JAVA_HOME: {java_bin_path}")
            return java_bin_path

    # Look for common installation paths
    common_paths = [
        os.path.join(home_dir, "jdk"),
        os.path.join(home_dir, "java"),
        "/usr/lib/jvm",  # Common location on Linux
        "/usr/bin/java",  # Alternate location on Linux
        "/usr/local/bin/java",
        "C:\\Program Files\\Java",  # Common location on Windows
        "C:\\Program Files (x86)\\Java",  # Alternate location on Windows
    ]

    for base_path in common_paths:
        if os.path.exists(base_path):
            for root, dirs, _ in os.walk(base_path):
                if "bin" in dirs:
                    java_cmd = os.path.join(root, "bin", java_exe)
                    if os.path.exists(java_cmd):
                        java_bin_path = java_cmd
                        print(f"Found Java in {base_path}: {java_bin_path}")
                        return java_bin_path

    # If Java is still not found, we can download and install it to the home directory
    print("Java not found, proceeding to download and install it to the home directory.")
    # Add code to download and install Java here (for example using wget, curl, or a package manager)
    # For now, let's assume the installation is handled and return the path after installation.
    java_bin_path = os.path.join(home_dir, "java", "bin", java_exe)
    return java_bin_path

def get_module_absolute_path():
    """
    Get the absolute path of the module.
    """
    module_path = os.path.abspath(__file__)
    return os.path.dirname(module_path)


def get_geoweaver_jar_path():
    """
    Get the path of the Geoweaver JAR file.
    """
    return f"{get_home_dir()}/geoweaver.jar"


def check_geoweaver_jar():
    """
    Check if the Geoweaver JAR file exists.
    """
    return os.path.isfile(get_geoweaver_jar_path())


def download_geoweaver_jar(overwrite=False):
    """
    Download the latest version of Geoweaver JAR file.
    """
    with get_spinner(text='Checking Geoweaver JAR file...', spinner='dots'):
        if check_geoweaver_jar():
            if overwrite:
                os.remove(get_geoweaver_jar_path())
            else:
                system = platform.system()
                if not system == "Windows":  # Windows files are exec by default
                    subprocess.run(
                        ["chmod", "+x", get_geoweaver_jar_path()], cwd=f"{get_root_dir()}/"
                    )
                return

    with get_spinner(text='Downloading latest version of Geoweaver...', spinner='dots'):
        r = requests.get(GEOWEAVER_URL)
        with open(get_geoweaver_jar_path(), "wb") as f:
            f.write(r.content)

        if check_geoweaver_jar():
            print("Geoweaver.jar is downloaded")
        else:
            raise RuntimeError("Fail to download geoweaver.jar")


def check_os():
    """
    Check the operating system and return corresponding code.
    1: Linux, 2: MacOS, 3: Windows
    """
    if platform.system() == "Linux" or platform == "Linux2":
        return 1
    elif platform.system() == "Darwin":
        return 2
    elif platform.system() == "Windows":
        return 3


def check_ipython():
    """
    Check if the code is running in an IPython environment.
    """
    try:
        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except:
        return False


def copy_files(source_folder, destination_folder):
    """
    Copy files from the source folder to the destination folder.
    """
    for root, dirs, files in os.walk(source_folder):
        for file in files:
            source_file = os.path.join(root, file)
            destination_file = os.path.join(
                destination_folder, os.path.relpath(source_file, source_folder)
            )
            os.makedirs(os.path.dirname(destination_file), exist_ok=True)
            shutil.copy2(source_file, destination_file)

def get_geoweaver_port():
    return os.getenv("GEOWEAVER_PORT", "8070")

def get_log_file_path():
    """
    Determine the best location to store the geoweaver log file
    based on the operating system.
    
    Returns:
        str: The full path to the geoweaver log file.
    """
    # Get the user's home directory
    home_dir = os.path.expanduser("~")
    
    # Determine the log directory based on the platform
    if os.name == 'nt':  # Windows
        log_dir = os.path.join(os.getenv('APPDATA'), 'Geoweaver', 'logs')
    else:  # macOS/Linux
        log_dir = os.path.join(home_dir, '.local', 'share', 'geoweaver', 'logs')
    
    # Create the directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Define the full path to the log file
    log_file = os.path.join(log_dir, "geoweaver.log")
    
    # Ensure the log file exists, create it if it doesn't
    if not os.path.exists(log_file):
        open(log_file, "a").close()  # Create an empty log file if it doesn't exist
    
    return log_file

