import platform
import os
import subprocess
import shutil
import sys
import tarfile
import winreg
import zipfile
import urllib.request

from pygeoweaver.utils import get_home_dir, get_java_bin_path


def install_jdk():
    system = platform.system()
    architecture = platform.machine()

    if system == "Darwin":
        if architecture == "x86_64":
            install_jdk_macos("11.0.18-10", "jdk_x64_mac_hotspot")
        elif architecture == "arm64":
            install_jdk_macos("11.0.18-10", "jdk_aarch64_mac_hotspot")
        else:
            print("Unsupported architecture.")

    elif system == "Linux":
        if architecture == "x86_64":
            install_jdk_linux("11.0.18-10", "jdk_x64_linux_hotspot")
        elif architecture == "aarch64":
            install_jdk_linux("11.0.18-10", "jdk_aarch64_linux_hotspot")
        else:
            print("Unsupported architecture.")

    elif system == "Windows":
        if architecture == "AMD64" or architecture == "x86_64":
            install_jdk_windows("11.0.18-10", "jdk_x64_windows_hotspot")
        elif architecture == "x86-32":
            install_jdk_windows("11.0.18-10", "jdk_x86-32_windows_hotspot")
        else:
            print("Unsupported architecture.")

    else:
        print("Unsupported platform.")


def install_jdk_macos(jdk_version, jdk_arch):
    # jdk_aarch64_linux_hotspot
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.tar.gz'
    jdk_install_dir = os.path.expanduser("~/jdk")

    # Download JDK archive
    download_file(jdk_url, f"{get_home_dir()}/jdk.tar.gz")

    # Extract JDK archive
    extract_tar_archive(f"{get_home_dir()}/jdk.tar.gz", jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(f'{jdk_install_dir}/jdk-{jdk_version.replace("-", "+")}')


def install_jdk_linux(jdk_version, jdk_arch):
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.tar.gz'
    jdk_install_dir = os.path.expanduser("~/jdk")

    # Download JDK archive
    download_file(jdk_url, f"{get_home_dir()}/jdk.tar.gz")

    # Extract JDK archive
    extract_tar_archive(f"{get_home_dir()}/jdk.tar.gz", jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(f'{jdk_install_dir}/jdk-{jdk_version.replace("-", "+")}')


def install_jdk_windows(jdk_version, jdk_arch):
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.zip'
    jdk_install_dir = os.path.expanduser("~/jdk")

    # Download JDK archive
    download_file(jdk_url, f"{get_home_dir()}/jdk.zip")

    # Extract JDK archive
    extract_zip_archive(f"{get_home_dir()}/jdk.zip", jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(f'{jdk_install_dir}/jdk-{jdk_version.replace("-", "+")}')


def download_file(url, filename):
    if os.path.exists(filename):
        print(f"{filename} already exists.")
        return
    print(f"Downloading {filename}...", url)
    urllib.request.urlretrieve(url, filename)
    print(f"{filename} downloaded.")


def extract_tar_archive(archive_path, destination_dir):
    if not os.path.exists(destination_dir):
        print(f"Extracting {archive_path}...")
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            tar_ref.extractall(destination_dir)
        print(f"{archive_path} extracted to {destination_dir}.")


def extract_zip_archive(archive_path, destination_dir):
    print(f"Extracting {archive_path}...")
    with zipfile.ZipFile(archive_path, "r") as zip_ref:
        zip_ref.extractall(destination_dir)
    print(f"{archive_path} extracted to {destination_dir}.")


def set_jdk_env_vars_for_windows(jdk_install_dir):
    print(f"Setting JDK environment variables...")
    java_bin = os.path.join(jdk_install_dir, "bin")

    # Append JAVA_HOME to the user's PATH environment variable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS) as regkey:
            current_path = winreg.QueryValueEx(regkey, "PATH")[0]
            if java_bin not in current_path:
                new_path = f"{current_path};{java_bin}"
                winreg.SetValueEx(regkey, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                print("Added JDK bin directory to PATH.")
    except Exception as e:
        print(f"Error adding JDK bin directory to PATH: {e}")

    # Set JAVA_HOME environment variable
    # try:
    #     with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS) as regkey:
    #         winreg.SetValueEx(regkey, "JAVA_HOME", 0, winreg.REG_EXPAND_SZ, jdk_install_dir)
    #         print("Set JAVA_HOME environment variable.")
    # except Exception as e:
    #     print(f"Error setting JAVA_HOME environment variable: {e}")

    # Update the environment variables of the current process
    # subprocess.call(["setx", "JAVA_HOME", java_home])
    subprocess.call(["setx", "PATH", ";".join([current_path, java_bin])])
    print("JDK environment variables set.")


def set_jdk_env_vars_for_linux_mac(jdk_install_dir):
    print(f"Setting JDK environment variables...")
    java_line = f'\nexport JAVA_HOME="{jdk_install_dir}"\n'

    check_java = False
    with open(os.path.expanduser("~/.bashrc"), "r") as file:
        for line in file:
            if line.strip() == java_line:
                check_java = True
                break

    if not check_java:
        with open(os.path.expanduser("~/.bashrc"), "a") as bashrc:
            bashrc.write(f'export JAVA_HOME="{jdk_install_dir}"\n')
            bashrc.write(f'export PATH="$JAVA_HOME/bin:$PATH"\n')
            print("JDK environment variables set.")

    subprocess.run(["bash", "-c", "source ~/.bashrc"])


def set_jdk_env_vars(jdk_install_dir):
    print(f"Setting environment variables for {platform.system()}")
    if platform.system() == "Windows":
        set_jdk_env_vars_for_windows(jdk_install_dir)
    else:
        set_jdk_env_vars_for_linux_mac(jdk_install_dir)


def install_java():
    system = platform.system()
    if system == "Darwin":
        os.system(
            "/bin/bash -c '/usr/bin/ruby -e \"$(curl -fsSL "
            "https://raw.githubusercontent.com/Homebrew/install/master/install)\"'"
        )
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
            'powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; ['
            "System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object "
            "System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))\""
        )
        os.system("choco install -y openjdk")
    else:
        print("Unsupported operating system.")
        sys.exit(1)


def is_java_installed():
    try:
        # Check if Java is installed by running "java -version" command
        subprocess.run(
            [get_java_bin_path(), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except:
        return False


def check_java():
    # Check if Java is installed
    if not is_java_installed():
        print("Java is not installed. Installing...")
        install_jdk()
        print("Java installation complete.")
