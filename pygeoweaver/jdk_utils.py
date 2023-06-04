import platform
import os
import subprocess
import shutil
import sys
import tarfile
import zipfile
import urllib.request


def install_jdk():
    # Check the platform
    system = platform.system()

    if system == 'Darwin':  # macOS
        install_jdk_macos()

    elif system == 'Linux':  # Linux
        install_jdk_linux()

    elif system == 'Windows':  # Windows
        install_jdk_windows()

    else:
        print('Unsupported platform.')


def install_jdk_macos():
    jdk_version = 'adopt@1.11.0-8'
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/{jdk_version}/OpenJDK11U-jdk_x64_mac_hotspot_{jdk_version.replace("@", "-")}.tar.gz'

    jdk_file_name = jdk_url.split('/')[-1]
    jdk_dir_name = jdk_file_name.replace('.tar.gz', '')

    # Download JDK
    print('Downloading JDK...')
    urllib.request.urlretrieve(jdk_url, jdk_file_name)

    # Extract JDK
    print('Extracting JDK...')
    with tarfile.open(jdk_file_name, 'r:gz') as tar:
        tar.extractall()

    # Move JDK to user's home directory
    home_dir = os.path.expanduser('~')
    jdk_install_dir = os.path.join(home_dir, jdk_dir_name)
    shutil.move(jdk_dir_name, jdk_install_dir)

    # Set environment variables
    os.environ['JAVA_HOME'] = jdk_install_dir
    os.environ['PATH'] = f'{jdk_install_dir}/bin:{os.environ["PATH"]}'

    print('JDK installation completed.')


def install_jdk_linux():
    # https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.19%2B7/OpenJDK11U-debugimage_aarch64_linux_hotspot_11.0.19_7.tar.gz
    jdk_version = '11.0.19-7'
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-{jdk_version}/OpenJDK11U-jdk_x64_linux_hotspot_{jdk_version.replace("-", "_")}.tar.gz'

    jdk_file_name = jdk_url.split('/')[-1]
    jdk_dir_name = jdk_file_name.replace('.tar.gz', '')

    # Download JDK
    print('Downloading JDK...')
    print('jdk_url: ', jdk_url)
    urllib.request.urlretrieve(jdk_url, jdk_file_name)

    # Extract JDK
    print('Extracting JDK...')
    with tarfile.open(jdk_file_name, 'r:gz') as tar:
        tar.extractall()

    # Move JDK to user's home directory
    home_dir = os.path.expanduser('~')
    jdk_install_dir = os.path.join(home_dir, jdk_dir_name)
    shutil.move(jdk_dir_name, jdk_install_dir)

    # Set environment variables
    with open(os.path.join(home_dir, '.bashrc'), 'a') as bashrc:
        bashrc.write(f'\nexport JAVA_HOME="{jdk_install_dir}"\nexport PATH="$JAVA_HOME/bin:$PATH"\n')

    print('JDK installation completed. Please restart your terminal or run "source ~/.bashrc" to apply the changes.')


def install_jdk_windows():
    jdk_version = 'adopt@1.11.0-8'
    jdk_url = f'https://github.com/adoptium/temurin11-binaries/releases/download/{jdk_version}/OpenJDK11U-jdk_x64_windows_hotspot_{jdk_version.replace("@", "-")}.zip'

    jdk_file_name = jdk_url.split('/')[-1]
    jdk_dir_name = jdk_file_name.replace('.zip', '')

    # Download JDK
    print('Downloading JDK...')
    urllib.request.urlretrieve(jdk_url, jdk_file_name)

    # Extract JDK
    print('Extracting JDK...')
    with zipfile.ZipFile(jdk_file_name, 'r') as zip_ref:
        zip_ref.extractall()

    # Move JDK to user's home directory
    home_dir = os.path.expanduser('~')
    jdk_install_dir = os.path.join(home_dir, jdk_dir_name)
    shutil.move(jdk_dir_name, jdk_install_dir)

    # Set environment variables
    subprocess.run(['setx', 'JAVA_HOME', jdk_install_dir])
    os.environ['JAVA_HOME'] = jdk_install_dir
    os.environ['PATH'] = f'{jdk_install_dir}\\bin;{os.environ["PATH"]}'

    print('JDK installation completed. Please restart your command prompt to apply the changes.')


def is_java_installed():
    try:
        # Check if Java is installed by running "java -version" command
        subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except:
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
    if not is_java_installed():
        print("Java is not installed. Installing...")
        install_jdk()
        print("Java installation complete.")