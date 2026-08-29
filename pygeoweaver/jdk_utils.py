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
    GEOWEAVER_JAR_CHANNEL_LATEST,
    GEOWEAVER_JAR_CHANNEL_LEGACY,
    GEOWEAVER_LEGACY_JAR_URL,
    GEOWEAVER_LEGACY_JAVA11_LINE,
    GEOWEAVER_MANAGED_JDK17_VERSION,
    GEOWEAVER_MIN_JAVA_MAJOR,
    GEOWEAVER_RELEASES_URL,
    GEOWEAVER_URL,
)

# Temurin 17 LTS used when pygeoweaver auto-installs a JDK.
_DEFAULT_JDK17_VERSION = GEOWEAVER_MANAGED_JDK17_VERSION

# Cached result of ensure_geoweaver_runtime() for the current process.
_runtime_cache = None


class GeoweaverRuntime:
    """Resolved Java binary and Geoweaver jar channel for this process."""

    __slots__ = ("java_bin", "major", "channel", "jar_url", "managed")

    def __init__(self, java_bin, major, channel, jar_url, managed=False):
        self.java_bin = java_bin
        self.major = major
        self.channel = channel
        self.jar_url = jar_url
        self.managed = managed


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


def print_legacy_jar_fallback_message(detected_major=None):
    """Explain that an unmanaged old JDK will run Geoweaver 2.1.x."""
    major_txt = str(detected_major) if detected_major is not None else "unknown (<17)"
    click.echo()
    click.echo(click.style("=" * 72, fg="yellow", bold=True))
    click.echo(
        click.style(
            "  Geoweaver: using legacy 2.1.x (system JDK too old for 2.2+)",
            fg="yellow",
            bold=True,
        )
    )
    click.echo(click.style("=" * 72, fg="yellow", bold=True))
    click.echo(f"  Detected Java major version: {major_txt}")
    click.echo(
        f"  Latest Geoweaver (2.2+) needs Java {GEOWEAVER_MIN_JAVA_MAJOR}+; "
        "your JDK is not managed by PyGeoWeaver."
    )
    click.echo(f"  Auto-selecting {GEOWEAVER_LEGACY_JAVA11_LINE}: {GEOWEAVER_LEGACY_JAR_URL}")
    click.echo(
        f"  To run Geoweaver 2.2+, install Java {GEOWEAVER_MIN_JAVA_MAJOR}+ "
        "or let PyGeoWeaver manage a JDK under ~/jdk (gw installjdk)."
    )
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


def get_managed_jdk_root():
    """Directory where pygeoweaver installs JDKs (``~/jdk``)."""
    return os.path.join(get_home_dir(), "jdk")


def get_default_managed_jdk17_home():
    version_dir = f"jdk-{_DEFAULT_JDK17_VERSION.replace('-', '+')}"
    return os.path.join(get_managed_jdk_root(), version_dir)


def is_pygeoweaver_managed_path(path):
    """True if ``path`` lives under the pygeoweaver-managed ``~/jdk`` tree."""
    if not path:
        return False
    try:
        real = os.path.realpath(path)
        root = os.path.realpath(get_managed_jdk_root())
        return real == root or real.startswith(root + os.sep)
    except Exception:
        return False


def has_managed_jdk_install():
    """True if ``~/jdk`` contains at least one JDK home directory."""
    root = get_managed_jdk_root()
    if not os.path.isdir(root):
        return False
    try:
        for name in os.listdir(root):
            candidate = os.path.join(root, name)
            if not os.path.isdir(candidate):
                continue
            java_bin = os.path.join(candidate, "bin", "java")
            java_exe = os.path.join(candidate, "bin", "java.exe")
            if os.path.isfile(java_bin) or os.path.isfile(java_exe):
                return True
    except OSError:
        return False
    return False


def find_managed_java_bin(min_major=None):
    """
    Find the best ``java`` under ``~/jdk``.

    Prefers the highest major version; if ``min_major`` is set, only return
    binaries that meet that floor.
    """
    root = get_managed_jdk_root()
    if not os.path.isdir(root):
        return None

    best = None  # (major, path)
    try:
        for name in os.listdir(root):
            home = os.path.join(root, name)
            if not os.path.isdir(home):
                continue
            for exe in ("java", "java.exe"):
                java_bin = os.path.join(home, "bin", exe)
                if not os.path.isfile(java_bin):
                    continue
                major = get_java_major_version(java_bin)
                if major is None:
                    continue
                if min_major is not None and major < min_major:
                    continue
                if best is None or major > best[0]:
                    best = (major, java_bin)
    except OSError:
        return None
    return best[1] if best else None


def activate_jdk_in_process(jdk_install_dir):
    """Make ``jdk_install_dir`` the active JAVA_HOME/PATH for this process."""
    if not jdk_install_dir or not os.path.isdir(jdk_install_dir):
        return
    java_bin_dir = os.path.join(jdk_install_dir, "bin")
    os.environ["JAVA_HOME"] = jdk_install_dir
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    path_parts = [p for p in path_parts if p and os.path.realpath(p) != os.path.realpath(java_bin_dir)]
    os.environ["PATH"] = java_bin_dir + os.pathsep + os.pathsep.join(path_parts)


def _java_home_from_bin(java_bin):
    """Derive JDK home from a ``.../bin/java`` path."""
    if not java_bin or java_bin == "java":
        return None
    real = os.path.realpath(java_bin)
    bin_dir = os.path.dirname(real)
    if os.path.basename(bin_dir) != "bin":
        return None
    return os.path.dirname(bin_dir)


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
    """Extract a JDK tarball into ``destination_dir`` (creates dir if needed)."""
    os.makedirs(destination_dir, exist_ok=True)
    print(f"Extracting {archive_path}...")
    with tarfile.open(archive_path, "r:gz") as tar_ref:
        tar_ref.extractall(destination_dir)
    print(f"{archive_path} extracted to {destination_dir}.")


def extract_zip_archive(archive_path, destination_dir):
    """Extract a JDK zip into ``destination_dir`` (creates dir if needed)."""
    os.makedirs(destination_dir, exist_ok=True)
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
    # Always activate for the current process so subsequent java lookups work.
    activate_jdk_in_process(jdk_install_dir)


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


def is_java_installed(java_bin=None):
    try:
        bin_path = java_bin or get_java_bin_path()
        # Check if Java is installed by running "java -version" command
        subprocess.run(
            [bin_path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return True
    except Exception:
        return False


def _fail_java_install_help():
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


def _install_and_activate_jdk17():
    """Install Temurin 17 under ~/jdk and activate it in this process."""
    click.echo(click.style("Installing / upgrading OpenJDK 17 under ~/jdk ...", fg="yellow"))
    install_jdk()
    jdk_home = get_default_managed_jdk17_home()
    activate_jdk_in_process(jdk_home)
    java_bin = find_managed_java_bin(min_major=GEOWEAVER_MIN_JAVA_MAJOR)
    if not java_bin:
        # Fall back to expected layout even if version probe failed briefly.
        for exe in ("java", "java.exe"):
            candidate = os.path.join(jdk_home, "bin", exe)
            if os.path.isfile(candidate):
                java_bin = candidate
                break
    if not java_bin or not is_java_installed(java_bin):
        _fail_java_install_help()
    click.echo(click.style(f"Using managed JDK: {java_bin}", fg="green"))
    return java_bin


def _runtime_latest(java_bin, major=None, managed=False):
    if major is None:
        major = get_java_major_version(java_bin)
    return GeoweaverRuntime(
        java_bin=java_bin,
        major=major,
        channel=GEOWEAVER_JAR_CHANNEL_LATEST,
        jar_url=GEOWEAVER_URL,
        managed=managed,
    )


def _runtime_legacy(java_bin, major=None, managed=False):
    if major is None:
        major = get_java_major_version(java_bin)
    return GeoweaverRuntime(
        java_bin=java_bin,
        major=major,
        channel=GEOWEAVER_JAR_CHANNEL_LEGACY,
        jar_url=GEOWEAVER_LEGACY_JAR_URL,
        managed=managed,
    )


def ensure_geoweaver_runtime(force_recheck=False):
    """
    Resolve which Java binary and Geoweaver jar channel to use.

    Policy:
    - Prefer a pygeoweaver-managed JDK 17+ under ``~/jdk`` when present.
    - If no Java is installed, install Temurin 17 under ``~/jdk`` and use latest jar.
    - If active Java is 17+, use the latest Geoweaver jar.
    - If Java is older than 17 and pygeoweaver manages a JDK under ``~/jdk``
      (or the active binary is under that tree), bump the managed JDK to 17
      and use the latest jar.
    - If Java is older than 17 and unmanaged (system JDK), keep that JDK and
      automatically use the Geoweaver 2.1.x legacy jar.
    """
    global _runtime_cache
    if _runtime_cache is not None and not force_recheck:
        return _runtime_cache

    # 1) Prefer an already-installed managed JDK 17+.
    managed_17 = find_managed_java_bin(min_major=GEOWEAVER_MIN_JAVA_MAJOR)
    if managed_17:
        home = _java_home_from_bin(managed_17)
        if home:
            activate_jdk_in_process(home)
        major = get_java_major_version(managed_17)
        _runtime_cache = _runtime_latest(managed_17, major=major, managed=True)
        return _runtime_cache

    # 2) No Java at all -> install managed 17.
    if not is_java_installed():
        try:
            java_bin = _install_and_activate_jdk17()
            major = get_java_major_version(java_bin)
            _runtime_cache = _runtime_latest(java_bin, major=major, managed=True)
            return _runtime_cache
        except SystemExit:
            raise
        except Exception as e:
            click.echo(click.style(f"Error: {e}", fg="red"))
            click.echo(
                click.style(
                    "Please contact support at geoweaver.app@gmail.com for further assistance.",
                    fg="red",
                )
            )
            safe_exit(1)

    java_bin = get_java_bin_path()
    major = get_java_major_version(java_bin)
    managed = is_pygeoweaver_managed_path(java_bin) or has_managed_jdk_install()

    # 3) Java 17+ -> latest Geoweaver.
    if major is not None and major >= GEOWEAVER_MIN_JAVA_MAJOR:
        _runtime_cache = _runtime_latest(
            java_bin, major=major, managed=is_pygeoweaver_managed_path(java_bin)
        )
        return _runtime_cache

    # 4) Old Java, but pygeoweaver manages ~/jdk -> bump to 17, latest jar.
    if managed:
        click.echo(
            click.style(
                f"Detected Java {major if major is not None else 'unknown'} under "
                f"pygeoweaver-managed ~/jdk (or active binary). Bumping to JDK "
                f"{GEOWEAVER_MIN_JAVA_MAJOR} before starting Geoweaver...",
                fg="yellow",
            )
        )
        try:
            java_bin = _install_and_activate_jdk17()
            major = get_java_major_version(java_bin)
            if major is None or major < GEOWEAVER_MIN_JAVA_MAJOR:
                print_unsupported_java_warning(major)
                safe_exit(1)
            _runtime_cache = _runtime_latest(java_bin, major=major, managed=True)
            return _runtime_cache
        except SystemExit:
            raise
        except Exception as e:
            click.echo(click.style(f"Error upgrading managed JDK: {e}", fg="red"))
            safe_exit(1)

    # 5) Unmanaged system JDK too old -> legacy Geoweaver 2.1.x.
    if major is None:
        click.echo(
            click.style(
                "Warning: could not parse Java version; assuming it may be older "
                "than 17 and selecting legacy Geoweaver 2.1.x jar.",
                fg="yellow",
            )
        )
    print_legacy_jar_fallback_message(major)
    _runtime_cache = _runtime_legacy(java_bin, major=major, managed=False)
    return _runtime_cache


def get_geoweaver_runtime():
    """Return the cached runtime, resolving it first if needed."""
    return ensure_geoweaver_runtime()


def check_java():
    """
    Ensure a usable Java binary exists and select the Geoweaver jar channel.

    Backward-compatible entry point used across pygeoweaver. Does not exit when
    the system JDK is too old; instead ensure_geoweaver_runtime() selects the
    legacy Geoweaver 2.1.x jar. Managed JDKs under ~/jdk are bumped to 17.
    """
    return ensure_geoweaver_runtime()
