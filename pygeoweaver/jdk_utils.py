import platform
import os
import subprocess
import shutil
import sys
import tarfile
import zipfile
import urllib.request


def install_jdk():
    system = platform.system()
    architecture = platform.machine()

    if system == 'Darwin':
        if architecture == 'x86_64':
            install_jdk_macos('11.0.18-10', 'jdk_x64_mac_hotspot')
        elif architecture == 'arm64':
            install_jdk_macos('11.0.18-10', 'jdk_aarch64_mac_hotspot')
        else:
            print('Unsupported architecture.')

    elif system == 'Linux':
        # https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.18%2B10/OpenJDK11U-jdk_x64_linux_hotspot_11.0.18_10.tar.gz
        # https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.18_10/OpenJDK11U-jdk_x64_linux_hotspot_11.0.18_10.tar.gz
        if architecture == 'x86_64':
            install_jdk_linux('11.0.18-10', 'jdk_x64_linux_hotspot')
        elif architecture == 'aarch64':
            install_jdk_linux('11.0.18-10', 'jdk_aarch64_linux_hotspot')
        else:
            print('Unsupported architecture.')

    elif system == 'Windows':
        if architecture == 'AMD64' or architecture == 'x86_64':
            install_jdk_windows('11.0.18-10', 'jdk_x64_windows_hotspot')
        elif architecture == 'x86-32':
            install_jdk_windows('11.0.18-10', 'jdk_x86-32_windows_hotspot')
        else:
            print('Unsupported architecture.')

    else:
        print('Unsupported platform.')


def install_jdk_macos(jdk_version, jdk_arch):
    # jdk_aarch64_linux_hotspot
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.tar.gz'
    jdk_install_dir = os.path.expanduser('~/jdk')

    # Download JDK archive
    download_file(jdk_url, 'jdk.tar.gz')

    # Extract JDK archive
    extract_tar_archive('jdk.tar.gz', jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(jdk_install_dir)


def install_jdk_linux(jdk_version, jdk_arch):
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.tar.gz'
    jdk_install_dir = os.path.expanduser('~/jdk')

    # Download JDK archive
    download_file(jdk_url, 'jdk.tar.gz')

    # Extract JDK archive
    extract_tar_archive('jdk.tar.gz', jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(jdk_install_dir)


def install_jdk_windows(jdk_version, jdk_arch):
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version.replace("-", "%2B")}/OpenJDK11U-{jdk_arch}_{jdk_version.replace("-", "_")}.zip'
    jdk_install_dir = os.path.expanduser('~/jdk')

    # Download JDK archive
    download_file(jdk_url, 'jdk.zip')

    # Extract JDK archive
    extract_zip_archive('jdk.zip', jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(jdk_install_dir)


def download_file(url, filename):
    print(f'Downloading {filename}...', url)
    urllib.request.urlretrieve(url, filename)
    print(f'{filename} downloaded.')


def extract_tar_archive(archive_path, destination_dir):
    print(f'Extracting {archive_path}...')
    with tarfile.open(archive_path, 'r:gz') as tar_ref:
        tar_ref.extractall(destination_dir)
    print(f'{archive_path} extracted to {destination_dir}.')


def extract_zip_archive(archive_path, destination_dir):
    print(f'Extracting {archive_path}...')
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(destination_dir)
    print(f'{archive_path} extracted to {destination_dir}.')


def set_jdk_env_vars(jdk_install_dir):
    print(f'Setting JDK environment variables...')

    # Update PATH environment variable
    path_var = os.environ.get('PATH', '')
    jdk_bin_path = os.path.join(jdk_install_dir, 'bin')
    path_var = f'{jdk_bin_path};{path_var}' if platform.system() == 'Windows' else f'{jdk_bin_path}:{path_var}'
    os.environ['PATH'] = path_var

    # Update JAVA_HOME environment variable
    os.environ['JAVA_HOME'] = jdk_install_dir

    print('JDK environment variables set.')



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



def is_java_installed():
    try:
        # Check if Java is installed by running "java -version" command
        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except:
        return False
    


def check_java():
    # Check if Java is installed
    if not is_java_installed():
        print("Java is not installed. Installing...")
        install_jdk()
        print("Java installation complete.")



