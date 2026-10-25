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
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        if allow_insecure is None:
            allow_insecure = os.getenv("GEOWEAVER_AGENT_INSECURE", "") in ("1", "true", "yes")
        self.allow_insecure = allow_insecure
        handlers = [_NoRedirect()]
        if is_loopback_url(self.base_url):
            # Cluster nodes often export http_proxy; loopback must never go through it.
            handlers.append(urllib.request.ProxyHandler({}))
        cookie_jar = cookie_jar or os.getenv("GEOWEAVER_OOD_COOKIE_JAR")
        if cookie_jar and os.path.isfile(cookie_jar):
            jar = http.cookiejar.MozillaCookieJar(cookie_jar)
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
                handlers.append(urllib.request.HTTPCookieProcessor(jar))
            except (OSError, http.cookiejar.LoadError):
                pass
        self._opener = urllib.request.build_opener(*handlers)

    # ------------------------------------------------------------------ transport

    def request(self, method, path, body=None, params=None, auth=True, timeout=None):
        url = f"{self.base_url}/api/v1{path}"
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            if query:
                url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if (auth or body is not None) and not self.allow_insecure:
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
            # Some Open OnDemand proxies strip Authorization; Geoweaver also reads this header.
            headers["X-Geoweaver-Agent-Token"] = self.token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
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
        return self.request("DELETE", f"/tokens/{urllib.parse.quote(fingerprint)}")

    # ------------------------------------------------------------------ processes

    def list_processes(self):
        return self.request("GET", "/processes")

    def get_process(self, process_id):
        return self.request("GET", f"/processes/{urllib.parse.quote(process_id)}")

    def create_process(self, name, code, lang="python", description=None):
        return self.request(
            "POST", "/processes",
            body={"name": name, "lang": lang, "code": code, "description": description},
        )

    def update_process(self, process_id, name=None, code=None, lang=None, description=None):
        return self.request(
            "PUT", f"/processes/{urllib.parse.quote(process_id)}",
            body={"name": name, "lang": lang, "code": code, "description": description},
        )

    def run_process(self, process_id, env_id=None, host_password=None, client_run_key=None):
        return self.request(
            "POST", f"/processes/{urllib.parse.quote(process_id)}/runs",
            body={"hostId": None, "hostPassword": host_password, "envId": env_id,
                  "clientRunKey": client_run_key},
        )

    def list_process_runs(self, process_id, log_limit=None):
        return self.request(
            "GET", f"/processes/{urllib.parse.quote(process_id)}/runs",
            params={"logLimit": log_limit},
        )

    # ------------------------------------------------------------------ workflows

    def list_workflows(self):
        return self.request("GET", "/workflows")

    def get_workflow(self, workflow_id):
        return self.request("GET", f"/workflows/{urllib.parse.quote(workflow_id)}")

    def create_workflow(self, name, nodes, edges="[]", description=None):
        return self.request(
            "POST", "/workflows",
            body={"name": name, "nodes": _as_json_text(nodes), "edges": _as_json_text(edges),
                  "description": description},
        )

    def update_workflow(self, workflow_id, name=None, nodes=None, edges=None, description=None):
        return self.request(
            "PUT", f"/workflows/{urllib.parse.quote(workflow_id)}",
            body={"name": name, "nodes": _as_json_text(nodes), "edges": _as_json_text(edges),
                  "description": description},
        )

    def run_workflow(self, workflow_id, mode="one", host_password=None, client_run_key=None):
        return self.request(
            "POST", f"/workflows/{urllib.parse.quote(workflow_id)}/runs",
            body={"mode": mode, "hostPassword": host_password, "clientRunKey": client_run_key},
        )

    # ------------------------------------------------------------------ runs

    def with_steps(self, run, log_limit=None):
        """Attach ``steps`` (per-process child runs) to a workflow run dict."""
        if run and run.get("steps") is not None:  # Geoweaver >= 3.0.1 returns steps itself
            return run
        ids = workflow_step_ids(run)
        if ids:
            steps = []
            for hid in ids:
                try:
                    steps.append(self.get_run(hid, log_limit=log_limit))
                except AgentError as e:
                    steps.append({"historyId": hid, "error": e.error, "message": e.message})
            run = dict(run, steps=steps)
        return run

    def get_run(self, history_id, log_limit=None):
        return self.request(
            "GET", f"/runs/{urllib.parse.quote(history_id)}", params={"logLimit": log_limit}
        )

    def stop_run(self, history_id):
        return self.request("POST", f"/runs/{urllib.parse.quote(history_id)}/stop")

    def wait_run(self, history_id, timeout=600.0, interval=1.0, log_limit=None, on_poll=None):
        """Poll a run until it reaches a terminal status; raises ``AgentError`` on timeout."""
        deadline = time.monotonic() + timeout
        delay = min(0.25, interval)
        while True:
            run = self.get_run(history_id, log_limit=log_limit)
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
            time.sleep(delay)
            delay = min(delay * 2, interval)


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
