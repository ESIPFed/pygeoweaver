import platform
import os
import subprocess
import shutil
import sys
import tarfile
import zipfile
import urllib.request

import click

from pygeoweaver.utils import detect_rc_file, get_home_dir, get_java_bin_path, safe_exit
from pygeoweaver.constants import (
    GEOWEAVER_LEGACY_JAR_URL,
    GEOWEAVER_LEGACY_JAVA11_LINE,
    GEOWEAVER_MIN_JAVA_MAJOR,
    GEOWEAVER_RELEASES_URL,
)

# Temurin 17 LTS used when pygeoweaver auto-installs a JDK.
_DEFAULT_JDK17_VERSION = "17.0.13-11"


def print_unsupported_java_warning(detected_major=None):
    """Warn that latest Geoweaver no longer supports JDK < 17."""
    major_txt = str(detected_major) if detected_major is not None else "unknown (<17)"
    click.echo()
    click.echo(click.style("=" * 72, fg="yellow", bold=True))
    click.echo(click.style("  Geoweaver WARNING: Unsupported Java version", fg="yellow", bold=True))
    click.echo(click.style("=" * 72, fg="yellow", bold=True))
    click.echo(f"  Detected Java major version: {major_txt}")
    click.echo(
        f"  Latest Geoweaver (2.2+ / Spring Boot 3) requires Java {GEOWEAVER_MIN_JAVA_MAJOR}+."
    )
    click.echo(f"  JDK versions older than {GEOWEAVER_MIN_JAVA_MAJOR} are no longer supported.")
    click.echo()
    click.echo("  If you cannot bump your JDK, use an older Geoweaver release instead:")
    click.echo(f"    - Stay on {GEOWEAVER_LEGACY_JAVA11_LINE} (Java 11 compatible)")
    click.echo(f"    - Releases: {GEOWEAVER_RELEASES_URL}")
    click.echo(f"    - Example jar: {GEOWEAVER_LEGACY_JAR_URL}")
    click.echo()
    click.echo("  With PyGeoWeaver: download that legacy jar to ~/geoweaver.jar,")
    click.echo("  or pin an older Geoweaver/pygeoweaver stack that still targets Java 11.")
    click.echo(click.style("=" * 72, fg="yellow", bold=True))
    click.echo()


def get_java_major_version(java_bin=None):
    """
    Return the major Java version as int, or None if it cannot be determined.
    Parses ``java -version`` output (written to stderr).
    """
    java_bin = java_bin or get_java_bin_path()
    try:
        result = subprocess.run(
            [java_bin, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        blob = (result.stderr or "") + "\n" + (result.stdout or "")
        # Examples: 'openjdk version "17.0.13"' / 'java version "1.8.0_392"'
        import re

        match = re.search(r'version\s+"([^"]+)"', blob)
        if not match:
            return None
        ver = match.group(1)
        if ver.startswith("1."):
            # 1.8.0_xxx -> major 8
            parts = ver.split(".")
            return int(parts[1]) if len(parts) > 1 else None
        return int(ver.split(".")[0])
    except Exception:
        return None


def install_jdk():
    system = platform.system()
    architecture = platform.machine()
    jdk_version = _DEFAULT_JDK17_VERSION

    if system == "Darwin":
        if architecture == "x86_64":
            install_jdk_macos(jdk_version, "jdk_x64_mac_hotspot")
        elif architecture == "arm64":
            install_jdk_macos(jdk_version, "jdk_aarch64_mac_hotspot")
        else:
            print("Unsupported architecture.")

    elif system == "Linux":
        if architecture == "x86_64":
            install_jdk_linux(jdk_version, "jdk_x64_linux_hotspot")
        elif architecture == "aarch64":
            install_jdk_linux(jdk_version, "jdk_aarch64_linux_hotspot")
        else:
            print("Unsupported architecture.")

    elif system == "Windows":
        if architecture == "AMD64" or architecture == "x86_64":
            install_jdk_windows(jdk_version, "jdk_x64_windows_hotspot")
        elif architecture == "x86-32":
            install_jdk_windows(jdk_version, "jdk_x86-32_windows_hotspot")
        else:
            print("Unsupported architecture.")

    else:
        print("Unsupported platform.")


def install_jdk_macos(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.tar.gz"
    )
    jdk_install_dir = os.path.expanduser("~/jdk")

    # Download JDK archive
    download_file(jdk_url, f"{get_home_dir()}/jdk.tar.gz")

    # Extract JDK archive
    extract_tar_archive(f"{get_home_dir()}/jdk.tar.gz", jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(f'{jdk_install_dir}/jdk-{jdk_version.replace("-", "+")}')


def install_jdk_linux(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.tar.gz"
    )
    jdk_install_dir = os.path.expanduser("~/jdk")

    # Download JDK archive
    download_file(jdk_url, f"{get_home_dir()}/jdk.tar.gz")

    # Extract JDK archive
    extract_tar_archive(f"{get_home_dir()}/jdk.tar.gz", jdk_install_dir)

    # Set JDK environment variables
    set_jdk_env_vars(f'{jdk_install_dir}/jdk-{jdk_version.replace("-", "+")}')


def install_jdk_windows(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.zip"
    )
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
    print(f"Setting JDK environment variables for Windows...")
    java_bin = os.path.join(jdk_install_dir, "bin")

    # Append JAVA_HOME to the user's PATH environment variable
    try:
        import winreg  # winreg module is only available on windows and should not be globally imported.

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
            0,
            winreg.KEY_ALL_ACCESS,
        ) as regkey:
            current_path = winreg.QueryValueEx(regkey, "PATH")[0]
            print(f"current_path = {current_path}")
            if java_bin not in current_path:
                new_path = f"{current_path};{java_bin}"
                winreg.SetValueEx(regkey, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                print(f"Added JDK bin directory to PATH: {java_bin}")
                subprocess.call(["setx", "PATH", ";".join([current_path, java_bin])])
                print("JDK environment variables set.")
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


def set_jdk_env_vars_for_linux_mac(jdk_install_dir):
    print(f"Setting JDK environment variables...")
    java_line = f'\nexport JAVA_HOME="{jdk_install_dir}"\n'
    rc_file_path = detect_rc_file()

    check_java = False
    with open(rc_file_path, "r") as file:
        for line in file:
            if line.strip() == java_line:
                check_java = True
                break

    if not check_java:
        with open(rc_file_path, "a") as bashrc:
            bashrc.write(f'export JAVA_HOME="{jdk_install_dir}"\n')
            bashrc.write(f'export PATH="$JAVA_HOME/bin:$PATH"\n')
            print("JDK environment variables set.")

    subprocess.run(["bash", "-i", "-c", f"source {rc_file_path} && echo 'Java environment sourced.'"])


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
            safe_exit(1)
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
        safe_exit(1)


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
    """
    Ensure a usable Java binary exists and meets Geoweaver's minimum major version.

    Latest Geoweaver requires Java 17+. Older JDKs get a clear warning and exit;
    users who cannot upgrade should use Geoweaver 2.1.x instead.
    """
    if not is_java_installed():
        click.echo(click.style("Java is not installed. Installing OpenJDK 17...", fg="yellow"))
        try:
            install_jdk()
            if is_java_installed():
                click.echo(click.style("Java installation complete.", fg="green"))
            else:
                click.echo(
                    click.style(
                        "Java is still not installed correctly. Please follow the instructions below.",
                        fg="red",
                    )
                )
                click.echo(
                    click.style(
                        "Step 1: Visit https://adoptium.net/ to download and install OpenJDK 17+ (Eclipse Adoptium).",
                        fg="blue",
                    )
                )
                click.echo(
                    click.style(
                        "Step 2: Choose the appropriate JDK version for your operating system.",
                        fg="blue",
                    )
                )
                click.echo(
                    click.style(
                        "Step 3: Follow the installation instructions provided on the website.",
                        fg="blue",
                    )
                )
                click.echo(
                    click.style(
                        "Step 4: After installation, make sure JAVA_HOME and PATH are set correctly.",
                        fg="blue",
                    )
                )
                click.echo(
                    click.style(
                        "If you encounter any problems, please contact support at geoweaver.app@gmail.com or post in GitHub issues: https://github.com/ESIPFed/pygeoweaver/issues.",
                        fg="red",
                    )
                )
                safe_exit(1)
        except Exception as e:
            click.echo(click.style(f"Error: {e}", fg="red"))
            click.echo(
                click.style(
                    "Please contact support at geoweaver.app@gmail.com for further assistance.",
                    fg="red",
                )
            )
            safe_exit(1)

    major = get_java_major_version()
    if major is None:
        click.echo(
            click.style(
                "Warning: could not parse Java version; continuing, but Geoweaver needs Java 17+.",
                fg="yellow",
            )
        )
        return

    if major < GEOWEAVER_MIN_JAVA_MAJOR:
        print_unsupported_java_warning(major)
        safe_exit(1)
