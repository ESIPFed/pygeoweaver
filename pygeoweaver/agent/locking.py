"""
Cross-process lock shared by ``gw agent ensure``, ``gw start`` and the token store.

``flock`` on the config directory; when the home directory is on NFS without lock support
(``ENOLCK``/``EOPNOTSUPP``), fall back to an ``O_EXCL`` lock file holding ``pid@host`` that
works across login nodes sharing ``$HOME``.
"""
import errno
import os
import socket
import time
from contextlib import contextmanager

from pygeoweaver.agent.client import EXIT_TIMEOUT, AgentError

# Cross-host O_EXCL locks cannot check the holder pid; treat them as stale after this long
# (longer than a slow JDK + jar download on a cluster node).
_STALE_SECONDS = 3600


def _pid_alive(pid):
    if os.name == "nt":
        # os.kill(pid, 0) on Windows calls TerminateProcess: never use it as a probe there.
        try:
            import psutil

            return psutil.pid_exists(pid)
        except ImportError:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def _excl_stale(path):
    try:
        with open(path, "r") as f:
            pid_s, _, host = f.read().strip().partition("@")
        age = time.time() - os.stat(path).st_mtime
    except (OSError, ValueError):
        return True
    if host == socket.gethostname() and pid_s.isdigit():
        return not _pid_alive(int(pid_s))
    return age > _STALE_SECONDS


@contextmanager
def _excl_lock(path, timeout, what):
    path = path + ".excl"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, f"{os.getpid()}@{socket.gethostname()}".encode())
            os.close(fd)
            break
        except FileExistsError:
            if _excl_stale(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise AgentError("lock_timeout", f"{what} (lock {path})", exit_code=EXIT_TIMEOUT)
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@contextmanager
def file_lock(path, timeout=300.0, what="Another agent holds the Geoweaver lock"):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # Windows
        with _excl_lock(path, timeout, what):
            yield
        return
    with open(path, "a") as fh:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno in (errno.ENOLCK, errno.EOPNOTSUPP, getattr(errno, "ENOTSUP", -1)):
                    with _excl_lock(path, max(0.0, deadline - time.monotonic()), what):
                        yield
                    return
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise AgentError("lock_timeout", f"{what} (lock {path})",
                                     exit_code=EXIT_TIMEOUT)
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def start_lock_path():
    from pygeoweaver.agent.discovery import config_dir

    return os.path.join(config_dir(), "ensure.lock")


def start_lock(timeout=300.0):
    """Serialize every Geoweaver start for this user (ensure + gw start)."""
    return file_lock(start_lock_path(), timeout, "Another agent or `gw start` is starting Geoweaver")
