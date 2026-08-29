import os
import sys
import shutil
import logging
import subprocess
import requests
import platform

from IPython import get_ipython
from halo import Halo
from pygeoweaver.constants import (
    GEOWEAVER_JAR_CHANNEL_LATEST,
    GEOWEAVER_JAR_CHANNEL_LEGACY,
    GEOWEAVER_URL,
)
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


def get_geoweaver_jar_channel_marker_path():
    """Marker file recording whether ~/geoweaver.jar is latest or legacy."""
    return f"{get_home_dir()}/geoweaver.jar.channel"


def read_geoweaver_jar_channel():
    marker = get_geoweaver_jar_channel_marker_path()
    if not os.path.isfile(marker):
        return None
    try:
        with open(marker, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def write_geoweaver_jar_channel(channel):
    marker = get_geoweaver_jar_channel_marker_path()
    with open(marker, "w", encoding="utf-8") as f:
        f.write(channel or GEOWEAVER_JAR_CHANNEL_LATEST)


def get_geoweaver_jar_version(jar_path=None):
    """
    Read Geoweaver version from the JAR ``META-INF/MANIFEST.MF``.

    Prefer ``Implementation-Version`` (set by the Spring Boot / Maven build).
    Returns ``None`` if the jar is missing or the version cannot be parsed.
    """
    import zipfile

    path = jar_path or get_geoweaver_jar_path()
    if not path or not os.path.isfile(path):
        return None
    try:
        with zipfile.ZipFile(path, "r") as zf:
            # Spring Boot also writes build-info.properties; try both.
            candidates = (
                "META-INF/MANIFEST.MF",
                "META-INF/build-info.properties",
            )
            for member in candidates:
                try:
                    raw = zf.read(member).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                version = _parse_version_from_metadata(raw, member)
                if version:
                    return version
            # Fallback: Maven pom.properties inside the jar
            for name in zf.namelist():
                if name.endswith("pom.properties") and "/geoweaver/" in name.replace("\\", "/"):
                    raw = zf.read(name).decode("utf-8", errors="replace")
                    version = _parse_version_from_metadata(raw, name)
                    if version:
                        return version
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        logger.debug("Unable to read Geoweaver jar version from %s: %s", path, exc)
    return None


def _parse_version_from_metadata(raw, source_name=""):
    """Extract a version string from MANIFEST.MF or *.properties content."""
    import re

    if "MANIFEST" in source_name.upper() or "Manifest-Version" in raw:
        match = re.search(
            r"(?im)^Implementation-Version:\s*(.+?)\s*$",
            raw,
        )
        if match:
            return match.group(1).strip()
    # build-info.properties / pom.properties: build.version=... or version=...
    for key in ("build.version", "version"):
        match = re.search(rf"(?im)^{re.escape(key)}\s*=\s*(.+?)\s*$", raw)
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in ("null", "unknown"):
                return value
    return None


def infer_geoweaver_jar_channel(version=None, jar_path=None):
    """
    Infer jar channel from version when the channel marker is missing.

    Geoweaver 2.2+ maps to ``latest``; 2.1.x (and older) maps to ``legacy``.
    """
    version = version if version is not None else get_geoweaver_jar_version(jar_path)
    if not version:
        return None
    # Strip common suffixes: 2.2.0-SNAPSHOT -> 2.2.0
    import re

    match = re.match(r"^(\d+)(?:\.(\d+))?", version.strip())
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major > 2 or (major == 2 and minor >= 2):
        return GEOWEAVER_JAR_CHANNEL_LATEST
    return GEOWEAVER_JAR_CHANNEL_LEGACY


def resolve_geoweaver_jar_channel(jar_path=None):
    """
    Resolve jar channel for status / download decisions.

    Prefer the version embedded in the JAR (source of truth for what is
    installed). Fall back to ``~/geoweaver.jar.channel`` only when the
    version cannot be read — so a stale global marker cannot override a
    specifically inspected jar (e.g. unit tests or a manually replaced jar).
    """
    inferred = infer_geoweaver_jar_channel(jar_path=jar_path)
    if inferred:
        return inferred
    return read_geoweaver_jar_channel()


def check_geoweaver_jar():
    """
    Check if the Geoweaver JAR file exists.
    """
    return os.path.isfile(get_geoweaver_jar_path())


def download_geoweaver_jar(overwrite=False, url=None, channel=None):
    """
    Download Geoweaver JAR file matching the resolved runtime channel.

    If ``url`` / ``channel`` are omitted, ``ensure_geoweaver_runtime()`` decides
    between latest (2.2+, Java 17+) and legacy (2.1.x, older JDKs).
    Re-downloads when the channel marker differs from the desired channel.
    """
    # Lazy import avoids circular dependency with jdk_utils -> utils.
    from pygeoweaver.jdk_utils import ensure_geoweaver_runtime

    runtime = ensure_geoweaver_runtime()
    jar_url = url or runtime.jar_url or GEOWEAVER_URL
    jar_channel = channel or runtime.channel or GEOWEAVER_JAR_CHANNEL_LATEST
    jar_path = get_geoweaver_jar_path()
    current_channel = read_geoweaver_jar_channel()
    channel_mismatch = check_geoweaver_jar() and current_channel and current_channel != jar_channel

    with get_spinner(text='Checking Geoweaver JAR file...', spinner='dots'):
        if check_geoweaver_jar() and not overwrite and not channel_mismatch:
            system = platform.system()
            if not system == "Windows":  # Windows files are exec by default
                subprocess.run(
                    ["chmod", "+x", jar_path], cwd=f"{get_root_dir()}/"
                )
            return

    if channel_mismatch and check_geoweaver_jar():
        print(
            f"Geoweaver jar channel changed ({current_channel} -> {jar_channel}); "
            "re-downloading..."
        )
        try:
            os.remove(jar_path)
        except OSError:
            pass
    elif overwrite and check_geoweaver_jar():
        try:
            os.remove(jar_path)
        except OSError:
            pass

    label = "legacy Geoweaver 2.1.x" if jar_channel != GEOWEAVER_JAR_CHANNEL_LATEST else "latest Geoweaver"
    with get_spinner(text=f'Downloading {label}...', spinner='dots'):
        r = requests.get(jar_url)
        r.raise_for_status()
        with open(jar_path, "wb") as f:
            f.write(r.content)

        if check_geoweaver_jar():
            write_geoweaver_jar_channel(jar_channel)
            print(f"Geoweaver.jar downloaded ({jar_channel}): {jar_url}")
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

