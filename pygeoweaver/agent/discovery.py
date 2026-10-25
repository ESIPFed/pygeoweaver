"""
Find the Geoweaver server an agent should talk to, and the token for it.

Base URL precedence: explicit argument > ``GEOWEAVER_BASE_URL`` > ``GEOWEAVER_PORT`` >
listening port of the caller's own ``geoweaver.jar`` JVM > ``8070``.

Token precedence: explicit argument > ``GEOWEAVER_API_TOKEN`` > token store
(``~/.config/geoweaver-agent/agent-tokens.json``, 0600) > legacy ``api-token`` file
written by Geoweaver's ``gw-ood-login`` (only for the base URL it was minted for).
"""
import json
import os
import re
import socket
import stat
import time

import urllib.parse

from pygeoweaver.agent.client import (
    EXIT_ERROR,
    EXIT_FOREIGN,
    EXIT_USAGE,
    AgentClient,
    AgentError,
    is_loopback_url,
)

DEFAULT_PORT = "8070"
_LOOPBACK_LATEST = "loopback:latest"


def config_dir():
    return os.getenv("GEOWEAVER_AGENT_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".config", "geoweaver-agent"
    )


def _ensure_private_dir(path):
    """
    Create ``path`` 0700, or accept an existing one only if it is owned by this user and
    not writable by group/other (else tokens and locks could be read or swapped by another
    account). Fails closed.
    """
    os.makedirs(path, mode=0o700, exist_ok=True)
    if not hasattr(os, "getuid"):  # Windows: per-user profile ACLs
        return
    st = os.stat(path)
    if st.st_uid != os.getuid():
        raise AgentError("insecure_config_dir",
                         f"{path} is owned by another account; refusing to keep tokens there. "
                         "Set GEOWEAVER_AGENT_CONFIG_DIR to a directory you own.",
                         exit_code=EXIT_ERROR)
    if stat.S_IMODE(st.st_mode) & 0o077:
        try:
            os.chmod(path, 0o700)
        except OSError:
            raise AgentError("insecure_config_dir",
                             f"{path} is accessible by other accounts and cannot be chmod 700",
                             exit_code=EXIT_ERROR) from None


def private_config_dir():
    path = config_dir()
    _ensure_private_dir(path)
    return path


def open_private_log(path, mode="ab"):
    """Open a log file readable only by this user (``~`` is often 0755 on clusters)."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if "a" in mode else 0)
    fd = os.open(path, flags, 0o600)  # a symlink (e.g. to scratch) is fine if the file is ours
    try:
        if hasattr(os, "getuid") and os.fstat(fd).st_uid != os.getuid():
            raise AgentError("insecure_log", f"{path} is owned by another account",
                             exit_code=EXIT_ERROR)
        if "a" not in mode:
            os.ftruncate(fd, 0)  # only after the ownership check
        os.fchmod(fd, 0o600)
    except AgentError:
        os.close(fd)
        raise
    except (AttributeError, OSError):
        pass
    return os.fdopen(fd, mode)


# Agent credentials / switches that must not leak into the Geoweaver JVM (and from there
# into every process it runs) or into the start helper.
SECRET_ENV = ("GEOWEAVER_API_TOKEN", "GEOWEAVER_OOD_COOKIE_JAR", "GEOWEAVER_AGENT_INSECURE",
              "GEOWEAVER_AGENT_ALLOW_FOREIGN")


def agent_child_env(jvm=False):
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    if jvm:
        env = {k: v for k, v in env.items() if not k.startswith("GEOWEAVER_AGENT_")}
    return env


def validate_port(port):
    port = str(port).strip()
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise AgentError("bad_port", f"Invalid port {port[:20]!r}", exit_code=EXIT_USAGE)
    return port


def local_base_url(port):
    return f"http://127.0.0.1:{validate_port(port)}/Geoweaver"


# --------------------------------------------------------------------------- processes

_GEOWEAVER_JAR = re.compile(r"(^|[/\\])geoweaver[^/\\]*\.jar$", re.IGNORECASE)


def is_geoweaver_jvm(cmdline):
    """
    True for ``java ... -jar .../geoweaver*.jar`` or ``java ... GeoweaverApplication``.

    Shells or editors that merely mention ``geoweaver.jar`` in their arguments do not count.
    """
    if not cmdline:
        return False
    exe = os.path.basename(cmdline[0]).lower()
    if not exe.startswith("java"):
        return False
    return any(_GEOWEAVER_JAR.search(arg) or arg.endswith("GeoweaverApplication")
               for arg in cmdline[1:])


def own_geoweaver_processes():
    """psutil.Process objects for Geoweaver JVMs owned by the current user."""
    try:
        import psutil
    except ImportError:
        return []
    uid = os.getuid() if hasattr(os, "getuid") else None
    attrs = ["pid", "cmdline", "create_time"]
    if uid is not None and hasattr(psutil.Process, "uids"):
        attrs.append("uids")
    found = []
    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            if not is_geoweaver_jvm(info.get("cmdline")):
                continue
            if uid is not None and info.get("uids") and info["uids"].real != uid:
                continue
            found.append(proc)
        except Exception:
            continue
    return found


def _proc_listen_ports(proc):
    """Ports ``proc`` really LISTENs on where 127.0.0.1 reaches it (None if the OS will not say)."""
    try:
        conns = proc.net_connections(kind="tcp") if hasattr(proc, "net_connections") \
            else proc.connections(kind="tcp")
    except Exception:
        return None
    return [str(c.laddr.port) for c in conns if c.status == "LISTEN" and c.laddr
            and _reaches(c.laddr, str(c.laddr.port), "127.0.0.1")]


def _listen_ports(proc):
    """``(ports, verified)``: real listening sockets, else ``-Dserver.port`` (booting JVM,
    or socket introspection denied). Only verified ports count as "mine" for secrets."""
    ports = _proc_listen_ports(proc)
    if ports:
        return ports, True
    try:
        m = re.search(r"-Dserver\.port=(\d+)", " ".join(proc.cmdline()))
        if m:
            return [m.group(1)], False
    except Exception:
        pass
    return [], False


_SCAN_CACHE = {"at": 0.0, "value": None, "verified": frozenset()}


def discover_local_servers(max_age=2.0):
    """[(pid, port), ...] for the caller's Geoweaver JVMs, newest first (cached briefly:
    one CLI call should scan the process table once even on busy login nodes)."""
    now = time.monotonic()
    if _SCAN_CACHE["value"] is not None and now - _SCAN_CACHE["at"] < max_age:
        return _SCAN_CACHE["value"]
    procs = sorted(own_geoweaver_processes(),
                   key=lambda p: p.info.get("create_time") or 0, reverse=True)
    out, verified = [], set()
    for proc in procs:
        ports, ok = _listen_ports(proc)
        for port in ports:
            out.append((proc.pid, port))
            if ok:
                verified.add(port)
    _SCAN_CACHE.update(at=now, value=out, verified=frozenset(verified))
    return out


def _verified_own_ports():
    discover_local_servers()
    return _SCAN_CACHE["verified"]


_IPV4_REACH = ("127.0.0.1", "0.0.0.0", "::", "::ffff:127.0.0.1", "", "*")
_IPV6_REACH = ("::1", "::", "")


def _reaches(laddr, port, host):
    """Would a connection to ``host:port`` land on a socket listening on ``laddr``?"""
    if not laddr or str(laddr.port) != port:
        return False
    ip = laddr.ip.split("%")[0]
    if host == "::1":
        return ip in _IPV6_REACH
    return ip in _IPV4_REACH  # exact address or wildcard; 127.0.0.2 is a different socket


def _current_user(psutil):
    try:
        return psutil.Process().username()
    except Exception:
        return None


def _is_mine(proc, psutil, me_user=None):
    """Owned by this account: real uid on POSIX, user name elsewhere (Windows); unknown → no."""
    try:
        if hasattr(os, "getuid"):
            return proc.uids().real == os.getuid()
        return me_user is not None and proc.username() == me_user
    except Exception:
        return False


def _own_process_listens(port, host, psutil):
    """Scan only this user's processes (works without root on macOS, unlike the global table)."""
    me_user = _current_user(psutil)
    for proc in psutil.process_iter():
        try:
            if not _is_mine(proc, psutil, me_user):
                continue
            conns = proc.net_connections(kind="tcp") if hasattr(proc, "net_connections") \
                else proc.connections(kind="tcp")
            if any(c.status == "LISTEN" and _reaches(c.laddr, port, host) for c in conns):
                return True
        except Exception:
            continue
    return False


def _something_listens(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def loopback_port_owner(port, host="127.0.0.1"):
    """
    Who listens on loopback ``port``: ``"me"`` (a verified listening socket of one of your
    processes), ``"other"`` (another account, root, docker-proxy, ...), ``"none"`` (nothing
    listens) or ``None`` (cannot tell; callers treat it like ``"other"``).

    ``/api/v1/health`` is public, so on a shared login/compute node it cannot tell your
    Geoweaver from a colleague's; this check keeps your token away from theirs.
    """
    port = str(port)
    if host != "::1" and port in _verified_own_ports():
        return "me"  # fast path: our own Geoweaver JVM listens there (checked socket)
    try:
        import psutil
    except ImportError:
        return None
    try:
        conns = psutil.net_connections(kind="tcp")
    except Exception:
        conns = None  # macOS without root: only our own processes can be inspected
    if conns is None:
        if not _something_listens(host, port):
            return "none"
        return "me" if _own_process_listens(port, host, psutil) else "other"
    listeners = [c for c in conns if c.status == "LISTEN" and _reaches(c.laddr, port, host)]
    if not listeners:
        return "none"
    # Every socket the connection could reach must be ours (an IPv4 and an IPv6 listener on
    # the same port may belong to different accounts).
    me_user = _current_user(psutil)
    for c in listeners:
        # Unprivileged Linux reports pid=None only for sockets of other accounts.
        if c.pid is None:
            return "other"
        try:
            if not _is_mine(psutil.Process(c.pid), psutil, me_user):
                return "other"
        except Exception:
            return None
    return "me"


ALLOW_FOREIGN_ENV = "GEOWEAVER_AGENT_ALLOW_FOREIGN"


def foreign_port_error(port):
    return AgentError(
        "foreign_server",
        f"Port {port} on this machine is held by another account's process (or by a root-owned "
        "proxy such as docker-proxy / an sshd -R tunnel). Refusing to send an automatically "
        "chosen token there or start Geoweaver on it. Use your own port "
        "(export GEOWEAVER_PORT=<free port> && gw agent ensure), or if this listener is yours, "
        f"pass --base-url explicitly with GEOWEAVER_API_TOKEN, or set {ALLOW_FOREIGN_ENV}=1.",
        exit_code=EXIT_FOREIGN,
    )


def is_foreign_loopback(base_url):
    """
    True when ``base_url`` is a loopback port held by another account, or by a listener whose
    owner cannot be determined (fail closed). False when nothing listens.
    """
    if not is_loopback_url(base_url) or os.getenv(ALLOW_FOREIGN_ENV) == "1":
        return False
    parts = urllib.parse.urlsplit(normalize_loopback(base_url))
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return loopback_port_owner(port, parts.hostname) not in ("me", "none")


def check_not_foreign(base_url):
    """Raise if ``base_url`` is a loopback port held by another account."""
    if is_foreign_loopback(base_url):
        raise foreign_port_error(urllib.parse.urlsplit(base_url).port)


def normalize_loopback(base_url):
    """``localhost`` → ``127.0.0.1``: one address that both the ownership check and the request
    use (``localhost`` may resolve to ``::1`` first, where someone else could listen)."""
    parts = urllib.parse.urlsplit(base_url)
    if (parts.hostname or "").lower() == "localhost":
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc))
    return base_url


def resolve_base_url(explicit=None, probe=True):
    """Return ``(base_url, source)``."""
    if explicit:
        return normalize_loopback(explicit.rstrip("/")), "argument"
    env_url = os.getenv("GEOWEAVER_BASE_URL")
    if env_url:
        return normalize_loopback(env_url.rstrip("/")), "GEOWEAVER_BASE_URL"
    env_port = os.getenv("GEOWEAVER_PORT")
    if env_port:
        return local_base_url(env_port), "GEOWEAVER_PORT"  # validated: digits only
    candidates = discover_local_servers()
    if not probe:
        if candidates:
            return local_base_url(candidates[0][1]), "discovered"
        return local_base_url(DEFAULT_PORT), "default"
    healthy = []
    for _pid, port in candidates:
        url = local_base_url(port)
        if url not in healthy and AgentClient(url).is_up(timeout=0.5):
            healthy.append(url)
    if len(healthy) == 1:
        return healthy[0], "discovered"
    if healthy:
        # Several Geoweaver JVMs: prefer one we hold a token for, then the default port,
        # then the newest. `gw agent status` lists the others.
        tokens = _read_store().get("tokens", {})
        for url in healthy:
            if _store_key(url) in tokens:
                return url, "discovered"
        default_url = local_base_url(DEFAULT_PORT)
        if default_url in healthy:
            return default_url, "discovered"
        return healthy[0], "discovered"
    return local_base_url(DEFAULT_PORT), "default"


# --------------------------------------------------------------------------- tokens

def _store_path():
    return os.path.join(config_dir(), "agent-tokens.json")


def _store_key(base_url):
    return base_url.rstrip("/")


def _read_store():
    path = _store_path()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return {}
    try:
        if hasattr(os, "getuid"):
            st = os.fstat(fd)
            if st.st_uid != os.getuid():
                return {}  # never trust (or send) tokens from a file another account owns
            if stat.S_IMODE(st.st_mode) & 0o077:
                os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            fd = None
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
    finally:
        if fd is not None:
            os.close(fd)


def _write_store(data):
    _ensure_private_dir(config_dir())
    path = _store_path()
    tmp = f"{path}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _store_lock():
    from pygeoweaver.agent.locking import file_lock

    return file_lock(os.path.join(config_dir(), "agent-tokens.lock"), timeout=30,
                     what="Another `gw agent login` is writing the token store")


def save_token(base_url, created):
    """Persist a ``POST /tokens`` response for ``base_url`` (file mode 0600)."""
    entry = {
        "token": created["token"],
        "fingerprint": created.get("fingerprint"),
        "expiresAt": created.get("expiresAt"),
        "baseUrl": _store_key(base_url),
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _store_lock():
        data = _read_store()
        tokens = data.setdefault("tokens", {})
        tokens[_store_key(base_url)] = entry
        if is_loopback_url(base_url):
            # Open OnDemand gives every job a new port but the same ~/h2/gw database,
            # so the newest loopback token is the best guess for an unseen loopback port.
            tokens[_LOOPBACK_LATEST] = entry
        _write_store(data)
    return entry


def forget_token(base_url):
    with _store_lock():
        data = _read_store()
        tokens = data.get("tokens", {})
        entry = tokens.pop(_store_key(base_url), None)
        latest = tokens.get(_LOOPBACK_LATEST)
        if entry and latest and latest.get("token") == entry.get("token"):
            tokens.pop(_LOOPBACK_LATEST, None)
        _write_store(data)
    return entry


def _legacy_ood_token(base_url):
    cdir = config_dir()
    try:
        with open(os.path.join(cdir, "ood-session.meta"), "r", encoding="utf-8") as f:
            meta = dict(line.strip().split("=", 1) for line in f if "=" in line)
        if meta.get("geoweaver_base_url", "").rstrip("/") != _store_key(base_url):
            return None
        with open(os.path.join(cdir, "api-token"), "r", encoding="utf-8") as f:
            token = f.read().strip()
        return token or None
    except (OSError, ValueError):
        return None


def resolve_token(base_url, explicit=None):
    """Return ``(token, source)``; ``(None, None)`` when nothing is configured."""
    if explicit:
        return explicit, "argument"
    env_token = os.getenv("GEOWEAVER_API_TOKEN")
    if env_token:
        return env_token.strip(), "GEOWEAVER_API_TOKEN"
    tokens = _read_store().get("tokens", {})
    entry = tokens.get(_store_key(base_url))
    if entry and entry.get("token"):
        return entry["token"], "store"
    if is_loopback_url(base_url):
        entry = tokens.get(_LOOPBACK_LATEST)
        if entry and entry.get("token"):
            return entry["token"], "store:loopback-latest"
    legacy = _legacy_ood_token(base_url)
    if legacy:
        return legacy, "ood-api-token"
    return None, None


def stored_token_entry(base_url):
    tokens = _read_store().get("tokens", {})
    return tokens.get(_store_key(base_url)) or (
        tokens.get(_LOOPBACK_LATEST) if is_loopback_url(base_url) else None
    )


EXPLICIT_URL_SOURCES = ("argument", "GEOWEAVER_BASE_URL")
EXPLICIT_TOKEN_SOURCES = ("argument", "GEOWEAVER_API_TOKEN")


def connect(base_url=None, token=None, timeout=30.0, probe=True, sends_password=False):
    """
    Resolve base URL + token and return ``(AgentClient, info_dict)``.

    Before a secret (stored token, or the GUI password when ``sends_password``) can go to a
    loopback port held by another account, the URL *and* the secret must both have been given
    explicitly; automatic choices are refused with exit 9.
    """
    url, url_source = resolve_base_url(base_url, probe=probe)
    tok, tok_source = resolve_token(url, token)
    info = {"baseUrl": url, "baseUrlSource": url_source, "tokenSource": tok_source}
    secret = sends_password or bool(tok)
    # Discovered URLs are checked too: a JVM that has not bound its port yet is "discovered"
    # from -Dserver.port while another account may still hold that port.
    if secret and is_foreign_loopback(url):
        explicit = url_source in EXPLICIT_URL_SOURCES and (
            sends_password or tok_source in EXPLICIT_TOKEN_SOURCES)
        if not explicit:
            raise foreign_port_error(urllib.parse.urlsplit(url).port)
        # Docker -p, sshd -R tunnel, service account: the user named both URL and secret.
        info["warning"] = ("listener on this port is not owned by your account; "
                           "sending the secret because URL and secret were given explicitly")
    client = AgentClient(url, token=tok, timeout=timeout)
    return client, info
