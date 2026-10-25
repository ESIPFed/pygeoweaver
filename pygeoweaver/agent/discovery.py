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
import time

import urllib.parse

from pygeoweaver.agent.client import EXIT_FOREIGN, AgentClient, AgentError, is_loopback_url

DEFAULT_PORT = "8070"
_LOOPBACK_LATEST = "loopback:latest"


def config_dir():
    return os.getenv("GEOWEAVER_AGENT_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".config", "geoweaver-agent"
    )


def _ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def local_base_url(port):
    return f"http://127.0.0.1:{port}/Geoweaver"


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


def _listen_ports(proc):
    ports = []
    try:
        conns = proc.net_connections(kind="tcp") if hasattr(proc, "net_connections") \
            else proc.connections(kind="tcp")
        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                ports.append(str(c.laddr.port))
    except Exception:
        pass
    if not ports:
        # macOS may deny socket introspection; fall back to -Dserver.port in the command line.
        try:
            m = re.search(r"-Dserver\.port=(\d+)", " ".join(proc.cmdline()))
            if m:
                ports.append(m.group(1))
        except Exception:
            pass
    return ports


_SCAN_CACHE = {"at": 0.0, "value": None}


def discover_local_servers(max_age=2.0):
    """[(pid, port), ...] for the caller's Geoweaver JVMs, newest first (cached briefly:
    one CLI call should scan the process table once even on busy login nodes)."""
    now = time.monotonic()
    if _SCAN_CACHE["value"] is not None and now - _SCAN_CACHE["at"] < max_age:
        return _SCAN_CACHE["value"]
    procs = sorted(own_geoweaver_processes(),
                   key=lambda p: p.info.get("create_time") or 0, reverse=True)
    out = []
    for proc in procs:
        for port in _listen_ports(proc):
            out.append((proc.pid, port))
    _SCAN_CACHE.update(at=now, value=out)
    return out


def loopback_port_owner(port):
    """
    Who listens on loopback ``port``: ``"me"``, ``"other"`` (another account), or ``None``
    (nothing listening, or the OS will not say — e.g. macOS without root).

    ``/api/v1/health`` is public, so on a shared login/compute node it cannot tell your
    Geoweaver from a colleague's; this check keeps your token away from theirs.
    """
    port = str(port)
    if any(p == port for _pid, p in discover_local_servers()):
        return "me"
    try:
        import psutil

        conns = psutil.net_connections(kind="tcp")
    except Exception:
        return None
    me = os.getuid() if hasattr(os, "getuid") else None
    listeners = [c for c in conns if c.status == "LISTEN" and c.laddr
                 and str(c.laddr.port) == port]
    if not listeners:
        return None
    for c in listeners:
        if c.pid is None:
            continue
        if me is None:
            return "me"
        try:
            if psutil.Process(c.pid).uids().real == me:
                return "me"
        except Exception:
            continue
    # Unprivileged Linux reports pid=None only for sockets of other accounts.
    return "other" if all(c.pid is None for c in listeners) else None


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
    """True when ``base_url`` is a loopback port held by another account (see above)."""
    if not is_loopback_url(base_url) or os.getenv(ALLOW_FOREIGN_ENV) == "1":
        return False
    port = urllib.parse.urlsplit(base_url).port
    return bool(port) and loopback_port_owner(port) == "other"


def check_not_foreign(base_url):
    """Raise if ``base_url`` is a loopback port held by another account."""
    if is_foreign_loopback(base_url):
        raise foreign_port_error(urllib.parse.urlsplit(base_url).port)


def resolve_base_url(explicit=None, probe=True):
    """Return ``(base_url, source)``."""
    if explicit:
        return explicit.rstrip("/"), "argument"
    env_url = os.getenv("GEOWEAVER_BASE_URL")
    if env_url:
        return env_url.rstrip("/"), "GEOWEAVER_BASE_URL"
    env_port = os.getenv("GEOWEAVER_PORT")
    if env_port:
        return local_base_url(env_port), "GEOWEAVER_PORT"
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
    try:
        with open(_store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_store(data):
    _ensure_private_dir(config_dir())
    path = _store_path()
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


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
    # A discovered URL is one of our own JVMs by construction; check everything else.
    if secret and url_source != "discovered" and is_foreign_loopback(url):
        explicit = url_source in EXPLICIT_URL_SOURCES and (
            sends_password or tok_source in EXPLICIT_TOKEN_SOURCES)
        if not explicit:
            raise foreign_port_error(urllib.parse.urlsplit(url).port)
        # Docker -p, sshd -R tunnel, service account: the user named both URL and secret.
        info["warning"] = ("listener on this port is not owned by your account; "
                           "sending the secret because URL and secret were given explicitly")
    client = AgentClient(url, token=tok, timeout=timeout)
    return client, info
