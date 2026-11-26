"""
Thin, stdlib-only client for the Geoweaver Agent API (``/api/v1``).

Talks to the *already running* Geoweaver server over HTTP, so calls take
milliseconds instead of booting a second Geoweaver JVM, never touch the H2 file
directly, and every create/update is broadcast by the server to open GUI
browsers (workspace events).
"""
import http.client
import http.cookiejar
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

TERMINAL_STATUSES = ("Done", "Failed", "Stopped", "Skipped")

# Exit codes shared by the ``gw agent`` CLI (documented in docs/agent-ssh.md).
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNREACHABLE = 3
EXIT_UNAUTHORIZED = 4
EXIT_NOT_FOUND = 5
EXIT_HTTP = 6
EXIT_RUN_FAILED = 8
EXIT_FOREIGN = 9
EXIT_TIMEOUT = 124

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
EXIT_USAGE = 2
MIN_POLL_INTERVAL = 0.25  # never busy-poll a live server
MAX_STEPS = 500


class AgentError(Exception):
    """Agent API failure with a machine-readable ``error`` code and an exit code."""

    def __init__(self, error, message, status=None, exit_code=EXIT_ERROR):
        super().__init__(message)
        self.error = error
        self.message = message
        self.status = status
        self.exit_code = exit_code

    def to_dict(self):
        out = {"error": self.error, "message": self.message}
        if self.status is not None:
            out["status"] = self.status
        return out


def is_loopback_url(base_url):
    host = urllib.parse.urlsplit(base_url).hostname or ""
    return host in LOOPBACK_HOSTS


def validate_base_url(base_url):
    """Only plain ``http(s)://host[:port]/path`` URLs: no other schemes (urllib would read
    ``file://``), no credentials (they would be echoed in errors), no query/fragment."""
    def bad(why):
        return AgentError("bad_base_url", f"Invalid Geoweaver base URL ({why}); expected "
                          "http(s)://host:port/Geoweaver", exit_code=EXIT_USAGE)
    try:
        parts = urllib.parse.urlsplit(base_url)
        parts.port  # raises ValueError for a non-numeric / out-of-range port
    except ValueError:
        raise bad("bad port") from None
    if parts.scheme not in ("http", "https"):
        raise bad("scheme must be http or https")
    if not parts.hostname:
        raise bad("no host")
    if "@" in parts.netloc:
        raise bad("credentials in the URL are not allowed")
    if parts.query or parts.fragment:
        raise bad("query/fragment not allowed")
    return base_url


def _normalize_loopback(base_url):
    from pygeoweaver.agent.discovery import normalize_loopback

    return normalize_loopback(base_url)


_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _seg(value, what="id"):
    """One URL path segment from an id; ``../x`` or ``a/b`` never reaches another endpoint."""
    value = str(value)
    if not _ID.match(value):
        raise AgentError("bad_request", f"Invalid {what} {value[:40]!r}: expected letters, "
                         "digits, '_' or '-'", exit_code=EXIT_USAGE)
    return urllib.parse.quote(value, safe="")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect on /api/v1 means a login wall (e.g. Open OnDemand IdP), not data.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _exit_code_for_status(status):
    if status in (401, 403):
        return EXIT_UNAUTHORIZED
    if status == 404:
        return EXIT_NOT_FOUND
    return EXIT_HTTP


class AgentClient:
    """
    Client for ``{base_url}/api/v1``.

    :param base_url: Geoweaver base URL including ``/Geoweaver``.
    :param token: Agent API Bearer token (optional for :meth:`health` and :meth:`create_token`).
    :param cookie_jar: Optional Netscape cookie file (Open OnDemand session cookies).
    """

    def __init__(self, base_url, token=None, cookie_jar=None, timeout=30.0, allow_insecure=None):
        self.base_url = validate_base_url(_normalize_loopback(base_url.rstrip("/")))
        self.token = token
        self.timeout = timeout
        if allow_insecure is None:
            allow_insecure = os.getenv("GEOWEAVER_AGENT_INSECURE", "") in ("1", "true", "yes")
        self.allow_insecure = allow_insecure
        handlers = [_NoRedirect()]
        if is_loopback_url(self.base_url):
            # Cluster nodes often export http_proxy; loopback must never go through it.
            handlers.append(urllib.request.ProxyHandler({}))
        self.uses_cookies = False
        cookie_jar = cookie_jar or os.getenv("GEOWEAVER_OOD_COOKIE_JAR")
        if cookie_jar and os.path.isfile(cookie_jar):
            jar = http.cookiejar.MozillaCookieJar(cookie_jar)
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
                handlers.append(urllib.request.HTTPCookieProcessor(jar))
                self.uses_cookies = True
            except (OSError, http.cookiejar.LoadError):
                pass
        self._opener = urllib.request.build_opener(*handlers)

    # ------------------------------------------------------------------ transport

    def _open(self, method, path, body=None, params=None, auth=True, timeout=None,
              raw_body=None, accept="application/json"):
        """Send one request and return the open response (caller closes it)."""
        url = f"{self.base_url}/api/v1{path}"
        if params:
            query = {k: _param(v) for k, v in params.items() if v is not None}
            if query:
                url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": accept}
        data = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = "application/json"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        # OOD session cookies are credentials too.
        if (auth or data is not None or self.uses_cookies) and not self.allow_insecure:
            self._require_secure_transport()
        if auth:
            if not self.token:
                raise AgentError(
                    "no_token",
                    "No Agent API token for this Geoweaver. Run `gw agent login` "
                    "(asks for the Geoweaver GUI password once) or set GEOWEAVER_API_TOKEN.",
                    exit_code=EXIT_UNAUTHORIZED,
                )
            headers["Authorization"] = f"Bearer {self.token}"
            if self.uses_cookies:
                # Some Open OnDemand proxies strip Authorization; Geoweaver also reads this
                # header. Only sent through OOD, so the token is not duplicated elsewhere.
                headers["X-Geoweaver-Agent-Token"] = self.token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return self._opener.open(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            raise self._http_error(e) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            reason = getattr(e, "reason", e)
            raise AgentError(
                "unreachable",
                f"Cannot reach Geoweaver at {self.base_url}: {reason}. "
                "Run `gw agent ensure` to start it.",
                exit_code=EXIT_UNREACHABLE,
            ) from None

    def request(self, method, path, body=None, params=None, auth=True, timeout=None,
                raw_body=None):
        url = f"{self.base_url}/api/v1{path}"
        resp = self._open(method, path, body=body, params=params, auth=auth, timeout=timeout,
                          raw_body=raw_body)
        try:
            with resp:
                raw = resp.read()
        except (http.client.HTTPException, OSError) as e:
            raise AgentError("unreachable", f"Connection to {self.base_url} broke: {e}",
                             exit_code=EXIT_UNREACHABLE) from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise AgentError(
                "bad_response",
                f"Non-JSON response from {url} (is this a Geoweaver base URL ending in /Geoweaver?)",
                exit_code=EXIT_HTTP,
            ) from None

    def _require_secure_transport(self):
        parts = urllib.parse.urlsplit(self.base_url)
        if parts.scheme == "http" and not is_loopback_url(self.base_url):
            raise AgentError(
                "insecure_transport",
                f"Refusing to send a token/password over plain HTTP to {parts.hostname}. "
                "Use https://, an SSH tunnel to 127.0.0.1, or run pygeoweaver on the Geoweaver "
                "machine over SSH. Override: GEOWEAVER_AGENT_INSECURE=1.",
                exit_code=EXIT_UNAUTHORIZED,
            )

    def _http_error(self, e):
        status = e.code
        if 300 <= status < 400:
            location = e.headers.get("Location", "") if e.headers else ""
            return AgentError(
                "login_redirect",
                f"HTTP {status} redirect to {location or 'a login page'}: a proxy/login wall "
                "is in front of Geoweaver. Run pygeoweaver on the Geoweaver machine over SSH "
                "(base URL http://127.0.0.1:<port>/Geoweaver) or refresh GEOWEAVER_OOD_COOKIE_JAR.",
                status=status,
                exit_code=EXIT_UNAUTHORIZED,
            )
        error, message = "http_error", e.reason
        try:
            payload = json.loads(e.read().decode("utf-8"))
            error = payload.get("error") or error
            message = payload.get("message") or message
        except Exception:
            pass
        if status == 401:
            message = f"{message}. Run `gw agent login` to mint a fresh token for {self.base_url}."
        elif status == 409 and "replace=true" in str(message):
            message = (str(message).replace("Re-send with ?replace=true to overwrite.", "").strip()
                       + " Import again with --replace (Python: replace=True) to overwrite.")
        elif error == "local_only":
            message = (f"{message}. This Geoweaver answers only programs on its own computer: "
                       "install pygeoweaver there and run `ssh user@host gw agent ...`.")
        return AgentError(error, f"HTTP {status}: {message}", status=status,
                          exit_code=_exit_code_for_status(status))

    # ------------------------------------------------------------------ public

    def health(self, timeout=2.0):
        return self.request("GET", "/health", auth=False, timeout=timeout)

    def probe(self, timeout=1.0):
        """
        ``"up"``: Agent API answers. ``"down"``: nothing reachable.
        ``"no_agent_api"``: something answers HTTP but not ``/api/v1/health`` (Geoweaver < 3.0,
        Agent API disabled, a login wall, or not Geoweaver at all).
        """
        try:
            ok = (self.health(timeout=timeout) or {}).get("status") == "up"
            return "up" if ok else "no_agent_api"
        except AgentError as e:
            return "down" if e.status is None and e.error == "unreachable" else "no_agent_api"

    def is_up(self, timeout=1.0):
        return self.probe(timeout=timeout) == "up"

    def capabilities(self):
        return self.request("GET", "/capabilities")

    # ------------------------------------------------------------------ tokens

    def create_token(self, host_password, ttl_days=None, revoke_others=False):
        body = {"hostPassword": host_password}
        if ttl_days:
            body["ttlDays"] = int(ttl_days)
        if revoke_others:
            body["revokeOthers"] = True
        return self.request("POST", "/tokens", body=body, auth=False)

    def list_tokens(self):
        return self.request("GET", "/tokens")

    def revoke_token(self, fingerprint):
        return self.request("DELETE", f"/tokens/{_seg(fingerprint)}")

    # ------------------------------------------------------------------ processes

    def list_processes(self, query=None):
        """Processes; ``query`` filters by id, name or description on the server."""
        return self.request("GET", "/processes", params={"q": query})

    def get_process(self, process_id):
        return self.request("GET", f"/processes/{_seg(process_id)}")

    def create_process(self, name, code, lang="python", description=None):
        """``lang``: ``python``, ``shell`` or ``builtin``."""
        return self.request(
            "POST", "/processes",
            body={"name": name, "lang": lang, "code": code, "description": description},
        )

    def update_process(self, process_id, name=None, code=None, lang=None, description=None):
        return self.request(
            "PUT", f"/processes/{_seg(process_id)}",
            body={"name": name, "lang": lang, "code": code, "description": description},
        )

    def delete_process(self, process_id):
        """Delete a process (HTTP 409 while a workflow still uses it)."""
        return self.request("DELETE", f"/processes/{_seg(process_id)}")

    def run_process(self, process_id, env_id=None, host_password=None, client_run_key=None,
                    host_id=None):
        """
        Start a process run. ``host_id`` defaults to the Geoweaver server itself (100001);
        an SSH host needs its ``host_password`` (used for this call only, never stored).
        """
        return self.request(
            "POST", f"/processes/{_seg(process_id)}/runs",
            body={"hostId": _opt_seg(host_id, "host id"), "hostPassword": host_password,
                  "envId": _opt_seg(env_id, "environment id"), "clientRunKey": client_run_key},
        )

    def list_process_runs(self, process_id, log_limit=None):
        return self.request(
            "GET", f"/processes/{_seg(process_id)}/runs",
            params={"logLimit": log_limit},
        )

    # ------------------------------------------------------------------ workflows

    def list_workflows(self, query=None):
        """Workflows; ``query`` filters by id, name or description on the server."""
        return self.request("GET", "/workflows", params={"q": query})

    def get_workflow(self, workflow_id):
        return self.request("GET", f"/workflows/{_seg(workflow_id)}")

    def create_workflow(self, name, nodes, edges="[]", description=None):
        return self.request(
            "POST", "/workflows",
            body={"name": name, "nodes": _as_json_text(nodes), "edges": _as_json_text(edges),
                  "description": description},
        )

    def update_workflow(self, workflow_id, name=None, nodes=None, edges=None, description=None):
        return self.request(
            "PUT", f"/workflows/{_seg(workflow_id)}",
            body={"name": name, "nodes": _as_json_text(nodes), "edges": _as_json_text(edges),
                  "description": description},
        )

    def delete_workflow(self, workflow_id):
        """Delete a workflow; its processes and run history are kept."""
        return self.request("DELETE", f"/workflows/{_seg(workflow_id)}")

    def run_workflow(self, workflow_id, mode="one", host_password=None, client_run_key=None,
                     host_id=None, env_id=None, node_hosts=None, host_passwords=None):
        """
        Start a workflow run.

        :param host_id: run every step on this host (default: the Geoweaver server).
        :param env_id: Python environment for every step.
        :param node_hosts: per-step hosts, ``{node_id: {"hostId": ..., "envId": ...}}``.
        :param host_passwords: SSH passwords per host id, ``{host_id: password}``; used for
            this run only, never stored.
        """
        body = {"mode": mode, "hostPassword": host_password, "clientRunKey": client_run_key,
                "hostId": _opt_seg(host_id, "host id"), "envId": _opt_seg(env_id, "environment id")}
        if node_hosts:
            body["nodeHosts"] = {
                str(node): {"hostId": _opt_seg((h or {}).get("hostId"), "host id"),
                            "envId": _opt_seg((h or {}).get("envId"), "environment id")}
                for node, h in node_hosts.items()
            }
        if host_passwords:
            body["hostPasswords"] = {_seg(h, "host id"): pw for h, pw in host_passwords.items()}
        return self.request("POST", f"/workflows/{_seg(workflow_id)}/runs", body=body)

    def list_workflow_runs(self, workflow_id, log_limit=None):
        """Workflow run history, newest first (up to 50), with per-step status."""
        return self.request("GET", f"/workflows/{_seg(workflow_id)}/runs",
                            params={"logLimit": log_limit})

    def set_step_skipped(self, workflow_id, node_id, skip=True):
        """Skip (or stop skipping) one step on later runs; it shows as Skipped."""
        return self.request("PUT", f"/workflows/{_seg(workflow_id)}/steps/{_seg(node_id, 'node id')}",
                            body={"skip": bool(skip)})

    def list_checkpoints(self, workflow_id):
        """Graph and code snapshots saved at each run, newest first."""
        return self.request("GET", f"/workflows/{_seg(workflow_id)}/checkpoints")

    def restore_checkpoint(self, workflow_id, run_id):
        """Restore the graph and step code that the run ``run_id`` used."""
        return self.request("POST", f"/workflows/{_seg(workflow_id)}/restore",
                            body={"runId": _seg(run_id, "run id")})

    def export_workflow(self, workflow_id):
        """A JSON bundle: the workflow plus the code of every process it uses."""
        return self.request("GET", f"/workflows/{_seg(workflow_id)}/export")

    def import_workflow(self, bundle, replace=False):
        """
        Import a bundle from :meth:`export_workflow` (a dict, JSON text, or a file path).
        Ids are kept; HTTP 409 when different content exists under them unless ``replace``.
        """
        if isinstance(bundle, (dict, list)):
            raw = json.dumps(bundle).encode("utf-8")
        elif isinstance(bundle, bytes):
            raw = bundle
        elif isinstance(bundle, os.PathLike) or (isinstance(bundle, str) and os.path.isfile(bundle)):
            with open(bundle, "rb") as f:
                raw = f.read()
        elif isinstance(bundle, str):
            raw = bundle.encode("utf-8")
        else:
            raise AgentError("bad_request", "bundle must be a dict, JSON text or a file path",
                             exit_code=EXIT_USAGE)
        try:
            if not isinstance(json.loads(raw.decode("utf-8")), dict):
                raise ValueError
        except ValueError:
            raise AgentError("bad_request", "Workflow bundle is not valid JSON",
                             exit_code=EXIT_USAGE) from None
        return self.request("POST", "/workflows/import", raw_body=raw,
                            params={"replace": "true" if replace else None})

    # ------------------------------------------------------------------ hosts

    def list_hosts(self, query=None):
        """Hosts (no passwords are stored); ``query`` filters by id, name, ip or url."""
        return self.request("GET", "/hosts", params={"q": query})

    def get_host(self, host_id):
        return self.request("GET", f"/hosts/{_seg(host_id, 'host id')}")

    def create_host(self, name, type="ssh", ip=None, port=None, username=None, url=None):
        """Add a host. ssh: ``ip``, ``port``, ``username``; jupyter/jupyterhub/jupyterlab/gee: ``url``."""
        return self.request("POST", "/hosts", body=_host_body(name, type, ip, port, username, url))

    def update_host(self, host_id, name=None, type=None, ip=None, port=None, username=None,
                    url=None):
        """Edit a host; omitted fields are kept."""
        return self.request("PUT", f"/hosts/{_seg(host_id, 'host id')}",
                            body=_host_body(name, type, ip, port, username, url))

    def delete_host(self, host_id):
        """Delete a host and its saved environments (run history is kept)."""
        return self.request("DELETE", f"/hosts/{_seg(host_id, 'host id')}")

    def list_environments(self, host_id):
        """Python environments saved for a host; pass an ``id`` as ``env_id`` to runs."""
        return self.request("GET", f"/hosts/{_seg(host_id, 'host id')}/environments")

    def scan_environments(self, host_id, host_password=None, timeout=None):
        """Find and save the Python environments on a host (SSH hosts need ``host_password``)."""
        return self.request("POST", f"/hosts/{_seg(host_id, 'host id')}/environments/scan",
                            body={"hostPassword": host_password},
                            timeout=timeout or max(self.timeout, 120.0))

    # ------------------------------------------------------------------ runs

    def with_steps(self, run, log_limit=None):
        """Attach ``steps`` (per-process child runs) to a workflow run dict."""
        if run and run.get("steps") is not None:  # Geoweaver >= 3.0.1 returns steps itself
            return run
        ids = workflow_step_ids(run)
        if ids:
            steps = []
            for hid in ids[:MAX_STEPS]:
                try:
                    steps.append(self.get_run(hid, log_limit=log_limit))
                except AgentError as e:
                    steps.append({"historyId": hid, "error": e.error, "message": e.message})
            run = dict(run, steps=steps)
        return run

    def get_run(self, history_id, log_limit=None, wait_seconds=None, include_step_logs=None):
        """
        Run status and log. ``wait_seconds`` (up to 60) lets the server hold the answer until
        the run ends; ``include_step_logs`` adds each workflow step's log.
        """
        wait = None
        if wait_seconds:
            wait = max(0, min(int(wait_seconds), MAX_SERVER_WAIT))
        return self.request(
            "GET", f"/runs/{_seg(history_id)}",
            params={"logLimit": log_limit, "waitSeconds": wait or None,
                    "includeStepLogs": "true" if include_step_logs else None},
            timeout=(self.timeout + wait) if wait else None,
        )

    def list_runs(self, limit=None, status=None, log_limit=None):
        """Newest runs first. ``status="Running"`` lists active runs; ``limit`` 1-500."""
        return self.request("GET", "/runs",
                            params={"limit": limit, "status": status, "logLimit": log_limit})

    def stop_run(self, history_id):
        return self.request("POST", f"/runs/{_seg(history_id)}/stop")

    def delete_run(self, history_id):
        """Delete a finished run (a workflow run also removes its step runs)."""
        return self.request("DELETE", f"/runs/{_seg(history_id)}")

    def delete_runs(self, status, process_id=None):
        """Delete all runs with ``status`` ``Failed`` or ``Skipped``, optionally of one process."""
        if status not in ("Failed", "Skipped"):
            raise AgentError("bad_request", "Bulk delete takes status Failed or Skipped",
                             exit_code=EXIT_USAGE)
        return self.request("DELETE", "/runs",
                            params={"status": status, "processId": _opt_seg(process_id)})

    def set_run_notes(self, history_id, notes):
        """Set the notes shown with this run in the Geoweaver history."""
        return self.request("PUT", f"/runs/{_seg(history_id)}/notes", body={"notes": notes})

    def wait_run(self, history_id, timeout=600.0, interval=1.0, log_limit=None, on_poll=None):
        """
        Wait until a run reaches a terminal status; raises ``AgentError`` on timeout.

        The server holds each request until the run ends (up to 30 s at a time), so a long run
        costs a request every 30 s, not a poll every second. Older servers that answer at once
        are polled with back-off up to ``interval``.
        """
        deadline = time.monotonic() + timeout
        interval = max(interval, MIN_POLL_INTERVAL)
        delay = MIN_POLL_INTERVAL
        while True:
            remaining = deadline - time.monotonic()
            hold = int(max(0, min(remaining, LONG_POLL_SECONDS)))
            asked = time.monotonic()
            run = self.get_run(history_id, log_limit=log_limit, wait_seconds=hold or None)
            if on_poll:
                on_poll(run)
            if run.get("terminal") or run.get("status") in TERMINAL_STATUSES:
                return run
            if time.monotonic() >= deadline:
                raise AgentError(
                    "timeout",
                    f"Run {history_id} still {run.get('status')} after {timeout:g}s "
                    "(it keeps running on the server; poll again or stop it)",
                    exit_code=EXIT_TIMEOUT,
                )
            if time.monotonic() - asked < max(1.0, hold / 2):
                # The server did not hold the request (older Geoweaver): back off.
                time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
                delay = min(delay * 2, interval)

    # ------------------------------------------------------------------ results

    def list_results(self, path=None):
        """One folder of the Geoweaver results folder (``path`` is relative to it)."""
        return self.request("GET", "/results", params={"path": _result_path(path, allow_empty=True)})

    def open_result(self, path):
        """Open one result file for reading (a binary file-like object; close it after)."""
        return self._open("GET", "/results/file", params={"path": _result_path(path)},
                          accept="application/octet-stream, application/json;q=0.9")

    def download_result(self, path, dest=".", overwrite=False):
        """
        Save one result file. ``dest`` is a folder (the file keeps its name; a path ending in
        ``/`` is created as a folder) or a file path. Never overwrites an existing file unless
        ``overwrite``; returns the saved path. The file is created readable only by you.
        """
        rel = _result_path(path)
        name = os.path.basename(rel)
        dest = str(dest)
        if dest.endswith(("/", os.sep)):
            os.makedirs(dest, exist_ok=True)
        target = os.path.join(dest, name) if os.path.isdir(dest) else dest
        target = os.path.abspath(target)
        if os.path.exists(target) and not overwrite:
            raise AgentError("exists", f"{target} already exists "
                             "(gw agent: --force; Python: overwrite=True)", exit_code=EXIT_USAGE)
        folder = os.path.dirname(target)
        if not os.path.isdir(folder):
            raise AgentError("bad_request", f"Folder {folder} does not exist", exit_code=EXIT_USAGE)
        fd, tmp = tempfile.mkstemp(prefix=".gw-download-", dir=folder)
        try:
            with os.fdopen(fd, "wb") as out:
                self.copy_result(path, out)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return target

    def copy_result(self, path, out):
        """Stream one result file into the binary file object ``out``."""
        resp = self.open_result(path)
        try:
            with resp:
                shutil.copyfileobj(resp, out, 1024 * 1024)
        except (http.client.HTTPException, OSError) as e:
            raise AgentError("unreachable", f"Download of {path!r} from {self.base_url} broke: {e}",
                             exit_code=EXIT_UNREACHABLE) from None


MAX_SERVER_WAIT = 60
LONG_POLL_SECONDS = 30


def _param(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _opt_seg(value, what="id"):
    return None if value in (None, "") else _seg(value, what)


def _host_body(name, type, ip, port, username, url):
    return {"name": name, "type": type, "ip": ip,
            "port": None if port is None else str(port), "username": username, "url": url}


def _result_path(path, allow_empty=False):
    """A results path relative to the results folder; no ``..``, no absolute paths."""
    if path in (None, "", "."):
        if allow_empty:
            return None
        raise AgentError("bad_request", "A result file path is required", exit_code=EXIT_USAGE)
    p = str(path).replace("\\", "/")
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if p.startswith("/") or ".." in parts or not parts or any("\x00" in x for x in parts):
        raise AgentError("bad_request", f"Invalid result path {str(path)[:80]!r}: use a path "
                         "relative to the results folder, without '..'", exit_code=EXIT_USAGE)
    return "/".join(parts)


_STEP_IDS = re.compile(r"^(?:[A-Za-z0-9]+;)+$")


def workflow_step_ids(run):
    """Child history ids of a workflow run (Geoweaver stores them as ``id1;id2;`` in log)."""
    log = (run or {}).get("log") or ""
    if not _STEP_IDS.match(log.strip()):
        return []
    return [h for h in log.strip().split(";") if h]


def _as_json_text(value):
    """Geoweaver stores workflow nodes/edges as JSON *strings*; accept lists too."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def linear_workflow_graph(process_ids, titles=None):
    """
    Build Geoweaver ``nodes``/``edges`` for a sequential chain of process ids
    (same node-id convention as the GUI: ``{processId}-{suffix}``).
    """
    nodes, edges = [], []
    for i, pid in enumerate(process_ids):
        title = titles[i] if titles else pid
        nodes.append({"title": title, "id": f"{pid}-n{i + 1:04d}", "x": 80 + 240 * i, "y": 120})
    for a, b in zip(nodes, nodes[1:]):
        edges.append({"source": dict(a), "target": dict(b)})
    return nodes, edges
