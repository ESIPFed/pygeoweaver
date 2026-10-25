import hashlib
import platform
import os
import subprocess
import shutil
import sys
import tarfile
import time
import zipfile
import urllib.parse
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


def managed_jdk_dir_name(jdk_version):
    """Temurin folder name under ~/jdk, e.g. ``jdk-17.0.13+11``."""
    return f"jdk-{jdk_version.replace('-', '+')}"


def move_aside_path(path):
    """
    Rename ``path`` to ``path.bak.<timestamp>`` so a fresh install can proceed.

    Renaming only needs write permission on the parent directory (typical for
    cluster home installs without sudo). Returns the backup path, or None.
    """
    if not path or not os.path.exists(path):
        return None
    stamp = time.strftime("%Y%m%d%H%M%S")
    backup = f"{path}.bak.{stamp}"
    n = 0
    while os.path.exists(backup):
        n += 1
        backup = f"{path}.bak.{stamp}.{n}"
    os.rename(path, backup)
    print(f"Moved aside {path} -> {backup}")
    return backup


def archive_top_level_name(archive_path):
    """Return the first top-level path component inside a JDK tar/zip, or None."""
    try:
        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zip_ref:
                for name in zip_ref.namelist():
                    top = name.replace("\\", "/").split("/")[0]
                    if top:
                        return top
        else:
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                for member in tar_ref.getmembers():
                    top = member.name.replace("\\", "/").split("/")[0]
                    if top:
                        return top
    except Exception:
        return None
    return None


def archive_matches_jdk_version(archive_path, jdk_version):
    """True if the archive's top-level directory matches the Temurin version layout."""
    if not archive_path or not os.path.isfile(archive_path):
        return False
    top = archive_top_level_name(archive_path)
    if not top:
        return False
    expected = managed_jdk_dir_name(jdk_version)
    if top == expected:
        return True
    # Accept any jdk-17* when installing a 17.x build (patch-level drift in cache).
    if jdk_version.startswith("17") and top.startswith("jdk-17"):
        return True
    return False


# SHA-256 of the pinned Temurin archives (from Adoptium's *.sha256.txt release files).
# Update together with GEOWEAVER_MANAGED_JDK17_VERSION; a missing entry fails closed.
TEMURIN_SHA256 = {
    "OpenJDK17U-jdk_x64_mac_hotspot_17.0.13_11.tar.gz":
        "840535070200a944a6b582d258ee84608bd25c9f2b5d1cdddb58dfadb019675a",
    "OpenJDK17U-jdk_aarch64_mac_hotspot_17.0.13_11.tar.gz":
        "d8b2f77f755d06e81a540834c5be22ed86f3c8a51a20396606c074303f8f9e2d",
    "OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz":
        "8682892fc02965930b9022c066fa164dd6f458ef4a5dc262016aa28333b30f49",
    "OpenJDK17U-jdk_aarch64_linux_hotspot_17.0.13_11.tar.gz":
        "0c17fa4f14c0d2cc9e9334f996fccdddc5da4459d768f3105c7ff0283c47bf62",
    "OpenJDK17U-jdk_x64_windows_hotspot_17.0.13_11.zip":
        "6b64255e1bd690b09a135d44ac6b0d6bd4490728a8bad81904941d2789d394c0",
    "OpenJDK17U-jdk_x86-32_windows_hotspot_17.0.13_11.zip":
        "04874767c1c82f0aee20fd558770fbf2e7aca7c3c19e1df0a8dd3d0ab4b668a2",
}

DOWNLOAD_TIMEOUT = 60  # seconds without data; downloads run under the Geoweaver start lock
DOWNLOAD_DEADLINE = 1800  # seconds for a whole download (a slow drip must not hold the lock)


def copy_with_deadline(chunks, out, url, deadline_s=DOWNLOAD_DEADLINE):
    deadline = time.monotonic() + deadline_s
    for chunk in chunks:
        out.write(chunk)
        if time.monotonic() > deadline:
            raise RuntimeError(f"Download of {url} took longer than {deadline_s}s")


def pinned_jdk_sha256(url):
    name = os.path.basename(urllib.parse.urlsplit(url).path)
    digest = TEMURIN_SHA256.get(name)
    if not digest:
        raise RuntimeError(f"No pinned SHA-256 for {name}; refusing to install an unverified JDK.")
    return digest


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url, dest):
    """Stream ``url`` to ``dest`` (https only, with a timeout)."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise RuntimeError(f"Refusing non-https download: {url}")
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest, "wb") as out:
        copy_with_deadline(iter(lambda: resp.read(1 << 20), b""), out, url)


def download_file(url, filename, force=False, sha256=None):
    """
    Download ``url`` to ``filename`` atomically (temp file + rename), optionally verifying
    ``sha256``; a partial or tampered download never takes the final name.

    When ``force`` is True, replace any existing file (after moving it aside).
    """
    if os.path.exists(filename):
        if not force:
            print(f"{filename} already exists.")
            return
        print(f"Replacing existing download cache: {filename}")
        try:
            move_aside_path(filename)
        except OSError:
            os.remove(filename)
    print(f"Downloading {filename}...", url)
    part = f"{filename}.{os.getpid()}.part"
    try:
        _fetch(url, part)
        if sha256:
            actual = file_sha256(part)
            if actual != sha256:
                raise RuntimeError(f"SHA-256 mismatch for {url}: expected {sha256}, got {actual}")
        os.replace(part, filename)
    finally:
        if os.path.exists(part):
            os.remove(part)
    print(f"{filename} downloaded.")


def download_jdk_archive(url, filename, jdk_version, sha256=None):
    """
    Ensure ``filename`` holds the Temurin archive for ``jdk_version`` (and, when given,
    exactly the bytes with digest ``sha256``; a cached archive is re-verified).

    A leftover ``~/jdk.tar.gz`` from an older Java 11 install must not be reused:
    extracting it again over ``~/jdk/jdk-11*`` causes PermissionError on locked files.
    """
    if os.path.isfile(filename) and archive_matches_jdk_version(filename, jdk_version):
        if sha256 is None or file_sha256(filename) == sha256:
            print(f"{filename} already exists and matches JDK {jdk_version}.")
            return
        print(f"{filename} does not match the pinned SHA-256. Downloading a fresh copy...")
        download_file(url, filename, force=True, sha256=sha256)
        return
    if os.path.isfile(filename):
        top = archive_top_level_name(filename)
        print(
            f"{filename} is stale or mismatched "
            f"(archive top-level: {top!r}; need {managed_jdk_dir_name(jdk_version)!r}). "
            "Downloading a fresh copy..."
        )
        download_file(url, filename, force=True, sha256=sha256)
        return
    download_file(url, filename, force=False, sha256=sha256)


def prepare_managed_jdk_root(jdk_install_dir, jdk_version):
    """
    Create ``~/jdk`` and move aside other managed JDK homes before extract.

    This avoids extractall writing into an old ``jdk-11*`` tree when a stale
    archive is present, and keeps the install directory writable without sudo.
    """
    os.makedirs(jdk_install_dir, exist_ok=True)
    expected = managed_jdk_dir_name(jdk_version)
    try:
        names = os.listdir(jdk_install_dir)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot list managed JDK directory {jdk_install_dir}: {exc}"
        ) from exc

    for name in names:
        path = os.path.join(jdk_install_dir, name)
        if not os.path.isdir(path):
            continue
        if not name.startswith("jdk-"):
            continue
        if name == expected:
            continue
        try:
            move_aside_path(path)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot move aside old managed JDK at {path}: {exc}. "
                f"From your account (no sudo), run: mv '{path}' '{path}.bak' "
                f"and retry `gw installjdk`."
            ) from exc


def _safe_extractall(tar_ref, destination_dir):
    """Refuse members that escape ``destination_dir`` (absolute, ``..``, links outside)."""
    if hasattr(tarfile, "data_filter"):
        tar_ref.extractall(destination_dir, filter="data")
        return
    # Older Pythons: extract one member at a time and resolve every path against the tree
    # as it exists on disk, so a chain of links (d -> ., d/e -> ..) cannot walk out.
    os.makedirs(destination_dir, exist_ok=True)
    root = os.path.realpath(destination_dir)

    def inside(path):
        return path == root or path.startswith(root + os.sep)

    for member in tar_ref.getmembers():
        if member.isdev():
            raise RuntimeError(f"Device file in archive: {member.name}")
        name = member.name
        if os.path.isabs(name) or name.startswith(("/", "\\")) or os.path.splitdrive(name)[0]:
            raise RuntimeError(f"Absolute path in archive: {member.name}")
        parent = os.path.realpath(os.path.join(root, os.path.dirname(name)))
        target = os.path.join(parent, os.path.basename(name))
        if not inside(parent) or not inside(os.path.realpath(target)):
            raise RuntimeError(f"Unsafe path in archive: {member.name}")
        if member.issym():
            link = os.path.realpath(os.path.join(parent, member.linkname))
        elif member.islnk():
            link = os.path.realpath(os.path.join(root, member.linkname))
        else:
            link = root
        if os.path.isabs(member.linkname or "") or not inside(link):
            raise RuntimeError(f"Unsafe link in archive: {member.name}")
        member.mode &= 0o755  # no setuid/setgid/sticky, no group/other write
        tar_ref.extract(member, root)


def extract_tar_archive(archive_path, destination_dir):
    """Extract a JDK tarball into ``destination_dir`` (creates dir if needed)."""
    os.makedirs(destination_dir, exist_ok=True)
    print(f"Extracting {archive_path}...")
    try:
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            _safe_extractall(tar_ref, destination_dir)
    except PermissionError as exc:
        raise PermissionError(
            f"{exc}. A leftover Java 11 tree or archive under ~/jdk is blocking "
            "the install. PyGeoWeaver will try to move old jdk-* folders aside; "
            "if this persists, run: "
            "mv ~/jdk.tar.gz ~/jdk.tar.gz.bak; mv ~/jdk ~/jdk.bak; gw installjdk"
        ) from exc
    print(f"{archive_path} extracted to {destination_dir}.")


def extract_zip_archive(archive_path, destination_dir):
    """Extract a JDK zip into ``destination_dir`` (creates dir if needed)."""
    os.makedirs(destination_dir, exist_ok=True)
    print(f"Extracting {archive_path}...")
    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(destination_dir)
    except PermissionError as exc:
        raise PermissionError(
            f"{exc}. A leftover Java 11 tree or archive under ~/jdk is blocking "
            "the install. Run: mv ~/jdk.zip ~/jdk.zip.bak; "
            "mv ~/jdk ~/jdk.bak; gw installjdk"
        ) from exc
    print(f"{archive_path} extracted to {destination_dir}.")


def install_jdk_macos(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.tar.gz"
    )
    jdk_install_dir = os.path.expanduser("~/jdk")
    archive_path = f"{get_home_dir()}/jdk.tar.gz"

    download_jdk_archive(jdk_url, archive_path, jdk_version, sha256=pinned_jdk_sha256(jdk_url))
    prepare_managed_jdk_root(jdk_install_dir, jdk_version)
    extract_tar_archive(archive_path, jdk_install_dir)
    set_jdk_env_vars(f"{jdk_install_dir}/{managed_jdk_dir_name(jdk_version)}")


def install_jdk_linux(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.tar.gz"
    )
    jdk_install_dir = os.path.expanduser("~/jdk")
    archive_path = f"{get_home_dir()}/jdk.tar.gz"

    download_jdk_archive(jdk_url, archive_path, jdk_version, sha256=pinned_jdk_sha256(jdk_url))
    prepare_managed_jdk_root(jdk_install_dir, jdk_version)
    extract_tar_archive(archive_path, jdk_install_dir)
    set_jdk_env_vars(f"{jdk_install_dir}/{managed_jdk_dir_name(jdk_version)}")


def install_jdk_windows(jdk_version, jdk_arch):
    jdk_url = (
        f"https://github.com/adoptium/temurin17-binaries/releases/download/"
        f"jdk-{jdk_version.replace('-', '%2B')}/"
        f"OpenJDK17U-{jdk_arch}_{jdk_version.replace('-', '_')}.zip"
    )
    jdk_install_dir = os.path.expanduser("~/jdk")
    archive_path = f"{get_home_dir()}/jdk.zip"

    download_jdk_archive(jdk_url, archive_path, jdk_version, sha256=pinned_jdk_sha256(jdk_url))
    prepare_managed_jdk_root(jdk_install_dir, jdk_version)
    extract_zip_archive(archive_path, jdk_install_dir)
    set_jdk_env_vars(f"{jdk_install_dir}/{managed_jdk_dir_name(jdk_version)}")


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
