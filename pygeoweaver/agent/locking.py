"""
Cross-process lock shared by ``gw agent ensure``, ``gw start`` and the token store.

``flock`` on the config directory (``msvcrt.locking`` on Windows); when the home directory
is on NFS without lock support (``ENOLCK``/``EOPNOTSUPP``), fall back to an ``O_EXCL`` lock
file holding ``pid@host`` that works across login nodes sharing ``$HOME``.
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
    """Inode of ``path`` if its holder is gone (or it is too old), else None."""
    try:
        with open(path, "r") as f:
            st = os.fstat(f.fileno())
            pid_s, _, host = f.read().strip().partition("@")
    except (OSError, ValueError):
        return None
    if host == socket.gethostname() and pid_s.isdigit():
        stale = not _pid_alive(int(pid_s))
    else:
        stale = time.time() - st.st_mtime > _STALE_SECONDS
    return st.st_ino if stale else None


def _break_stale(path, stale_ino):
    """
    Remove a stale lock without ever removing a fresh one: two waiters may both judge the
    same lock stale; the second must not delete the lock the first just created.
    """
    aside = f"{path}.{os.getpid()}.{os.urandom(4).hex()}.stale"
    try:
        os.rename(path, aside)
    except OSError:
        return
    try:
        if os.stat(aside).st_ino != stale_ino:
            # Took someone's fresh lock: put it back (link fails if a newer one exists).
            try:
                os.link(aside, path)
            except OSError:
                pass
    except OSError:
        pass
    try:
        os.unlink(aside)
    except OSError:
        pass


@contextmanager
def _excl_lock(path, timeout, what):
    path = path + ".excl"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, f"{os.getpid()}@{socket.gethostname()}".encode())
            my_ino = os.fstat(fd).st_ino
            os.close(fd)
            break
        except FileExistsError:
            stale_ino = _excl_stale(path)
            if stale_ino is not None:
                _break_stale(path, stale_ino)
                continue
            if time.monotonic() >= deadline:
                raise AgentError("lock_timeout", f"{what} (lock {path})", exit_code=EXIT_TIMEOUT)
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            # Only remove our own lock, never one a later holder created after a break.
            if os.stat(path).st_ino == my_ino:
                os.unlink(path)
        except OSError:
            pass


@contextmanager
def _windows_lock(path, timeout, what):
    """``msvcrt.locking`` byte lock: released by the OS if the holder dies, no stale files."""
    import msvcrt

    deadline = time.monotonic() + timeout
    with open(path, "a+") as fh:
        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise AgentError("lock_timeout", f"{what} (lock {path})",
                                     exit_code=EXIT_TIMEOUT)
                time.sleep(0.2)
        try:
            yield
        finally:
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass


@contextmanager
def file_lock(path, timeout=300.0, what="Another agent holds the Geoweaver lock"):
    from pygeoweaver.agent.discovery import _ensure_private_dir

    _ensure_private_dir(os.path.dirname(path))
    try:
        import fcntl
    except ImportError:  # Windows
        with _windows_lock(path, timeout, what):
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
