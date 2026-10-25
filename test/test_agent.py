"""Tests for pygeoweaver.agent (fast Agent API client + `gw agent` CLI) against a stub server."""
import json
import os
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pygeoweaver.agent import client as client_mod
from pygeoweaver.agent import discovery, ensure
from pygeoweaver.agent.cli import agent
from pygeoweaver.agent.client import AgentClient, AgentError, linear_workflow_graph, workflow_step_ids

TOKEN = "tok-123"


class _Stub(BaseHTTPRequestHandler):
    runs = {}
    calls = []

    def log_message(self, *args):
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else None

    def _route(self, method):
        path = self.path.split("?")[0].replace("/Geoweaver/api/v1", "", 1)
        body = self._body()
        _Stub.calls.append((method, path, body, dict(self.headers)))
        if path == "/health":
            return self._send(200, {"status": "up"})
        if path == "/redirect":
            return self._send(302, {}, {"Location": "https://idp.example/login"})
        if method == "POST" and path == "/tokens":
            if (body or {}).get("hostPassword") != "pw":
                return self._send(403, {"error": "forbidden", "message": "Wrong localhost password."})
            return self._send(201, {"token": TOKEN, "fingerprint": "fp1", "expiresAt": "2099-01-01"})
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"error": "unauthorized", "message": "Missing or invalid"})
        if path == "/capabilities":
            return self._send(200, {"apiVersion": "v1", "allowLocalhostRuns": True})
        if path == "/processes" and method == "GET":
            return self._send(200, [{"id": "p1", "name": "fetch", "lang": "python"},
                                    {"id": "p2", "name": "plot", "lang": "shell"}])
        if path == "/processes" and method == "POST":
            return self._send(200, dict(body, id="pnew", owner="111111"))
        if path.startswith("/processes/") and path.endswith("/runs") and method == "POST":
            _Stub.runs["h1"] = 0
            return self._send(200, {"historyId": "h1", "status": "Running", "reusedExisting": False})
        if path.startswith("/processes/") and method == "GET":
            return self._send(200, {"id": path.split("/")[2], "name": "n-" + path.split("/")[2],
                                    "code": "print(1)"})
        if path == "/workflows" and method == "POST":
            return self._send(200, dict(body, id="wnew"))
        if path.startswith("/runs/"):
            hid = path.split("/")[2]
            if hid == "wf":
                return self._send(200, {"historyId": "wf", "status": "Failed", "terminal": True,
                                        "log": "s1;s2;"})
            if hid in ("s1", "s2"):
                return self._send(200, {"historyId": hid, "terminal": True,
                                        "status": "Done" if hid == "s1" else "Failed", "log": hid})
            if hid not in _Stub.runs:
                return self._send(404, {"error": "not_found", "message": "Run not found"})
            _Stub.runs[hid] += 1
            done = _Stub.runs[hid] >= 3
            return self._send(200, {"historyId": hid, "status": "Done" if done else "Running",
                                    "terminal": done, "log": "ok"})
        return self._send(404, {"error": "not_found", "message": path})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")


@pytest.fixture
def server():
    _Stub.runs, _Stub.calls = {}, []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}/Geoweaver"
    httpd.shutdown()


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOWEAVER_AGENT_CONFIG_DIR", str(tmp_path / "cfg"))
    for var in ("GEOWEAVER_BASE_URL", "GEOWEAVER_PORT", "GEOWEAVER_API_TOKEN",
                "GEOWEAVER_OOD_COOKIE_JAR"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


# ----------------------------------------------------------------------------- speed

def test_import_pygeoweaver_does_not_load_heavy_modules():
    code = ("import sys, pygeoweaver, pygeoweaver.__main__; "
            "heavy = [m for m in ('pandas', 'IPython', 'halo', 'pydantic', 'requests') "
            "if m in sys.modules]; print(','.join(heavy))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


def test_lazy_package_attributes_still_work():
    import pygeoweaver

    assert callable(pygeoweaver.start)
    assert callable(pygeoweaver.list_processes)
    assert "run_workflow" in dir(pygeoweaver)
    with pytest.raises(AttributeError):
        pygeoweaver.definitely_not_a_function


# ----------------------------------------------------------------------------- client

def test_client_crud_and_auth_headers(server):
    c = AgentClient(server, token=TOKEN)
    assert c.is_up()
    assert [p["id"] for p in c.list_processes()] == ["p1", "p2"]
    created = c.create_process("hello", "print(42)", lang="python")
    assert created["id"] == "pnew" and created["code"] == "print(42)"
    headers = _Stub.calls[-1][3]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["X-Geoweaver-Agent-Token"] == TOKEN  # survives proxies that strip Authorization


def test_client_error_mapping(server):
    with pytest.raises(AgentError) as e:
        AgentClient(server, token="wrong").list_processes()
    assert e.value.exit_code == client_mod.EXIT_UNAUTHORIZED and e.value.status == 401
    with pytest.raises(AgentError) as e:
        AgentClient(server, token=TOKEN).get_run("missing")
    assert e.value.exit_code == client_mod.EXIT_NOT_FOUND
    with pytest.raises(AgentError) as e:
        AgentClient(server).list_processes()
    assert e.value.error == "no_token"
    with pytest.raises(AgentError) as e:
        AgentClient(server, token=TOKEN).request("GET", "/redirect")
    assert e.value.error == "login_redirect" and e.value.exit_code == client_mod.EXIT_UNAUTHORIZED
    with pytest.raises(AgentError) as e:
        AgentClient("http://127.0.0.1:1/Geoweaver", token=TOKEN).list_processes()
    assert e.value.exit_code == client_mod.EXIT_UNREACHABLE


def test_wait_run_polls_until_terminal(server):
    c = AgentClient(server, token=TOKEN)
    started = c.run_process("p1")
    run = c.wait_run(started["historyId"], timeout=10, interval=0.01)
    assert run["status"] == "Done" and _Stub.runs["h1"] == 3


def test_wait_run_timeout(server):
    c = AgentClient(server, token=TOKEN)
    c.run_process("p1")
    with pytest.raises(AgentError) as e:
        c.wait_run("h1", timeout=0, interval=0.01)
    assert e.value.exit_code == client_mod.EXIT_TIMEOUT


def test_workflow_steps(server):
    c = AgentClient(server, token=TOKEN)
    run = c.with_steps(c.get_run("wf"))
    assert [s["status"] for s in run["steps"]] == ["Done", "Failed"]
    assert workflow_step_ids({"log": "plain output\n"}) == []


def test_linear_workflow_graph():
    nodes, edges = linear_workflow_graph(["a", "b", "c"], ["A", "B", "C"])
    assert [n["id"] for n in nodes] == ["a-n0001", "b-n0002", "c-n0003"]
    assert [(e["source"]["id"], e["target"]["id"]) for e in edges] == [
        ("a-n0001", "b-n0002"), ("b-n0002", "c-n0003")]


# ----------------------------------------------------------------------------- discovery

def test_is_geoweaver_jvm():
    assert discovery.is_geoweaver_jvm(["java", "-jar", "/home/u/geoweaver.jar"])
    assert discovery.is_geoweaver_jvm(["/opt/jdk/bin/java", "-Dserver.port=1", "-jar", "geoweaver.jar"])
    assert discovery.is_geoweaver_jvm(["java", "-cp", "x", "com.gw.GeoweaverApplication"])
    # shells / editors mentioning the jar are not servers (gw stop must never kill them)
    assert not discovery.is_geoweaver_jvm(["/bin/zsh", "-c", "java -jar ~/geoweaver.jar"])
    assert not discovery.is_geoweaver_jvm(["vim", "geoweaver.jar"])
    assert not discovery.is_geoweaver_jvm([])


def test_base_url_precedence(monkeypatch):
    with patch.object(discovery, "discover_local_servers", return_value=[]):
        assert discovery.resolve_base_url()[1] == "default"
        monkeypatch.setenv("GEOWEAVER_PORT", "9999")
        assert discovery.resolve_base_url() == ("http://127.0.0.1:9999/Geoweaver", "GEOWEAVER_PORT")
        monkeypatch.setenv("GEOWEAVER_BASE_URL", "https://gw.example/Geoweaver/")
        assert discovery.resolve_base_url()[0] == "https://gw.example/Geoweaver"
        assert discovery.resolve_base_url("http://x/Geoweaver")[1] == "argument"


def test_discovery_picks_live_own_server(server):
    port = server.split(":")[2].split("/")[0]
    with patch.object(discovery, "discover_local_servers", return_value=[(1, "1"), (2, port)]):
        assert discovery.resolve_base_url() == (server, "discovered")


def test_token_store_private_and_loopback_fallback(isolated_env):
    url = "http://127.0.0.1:18080/Geoweaver"
    discovery.save_token(url, {"token": "secret", "fingerprint": "f", "expiresAt": "x"})
    path = os.path.join(discovery.config_dir(), "agent-tokens.json")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(discovery.config_dir()).st_mode) == 0o700
    assert discovery.resolve_token(url) == ("secret", "store")
    # Open OnDemand: new job -> new port, same database
    assert discovery.resolve_token("http://127.0.0.1:23594/Geoweaver") == ("secret", "store:loopback-latest")
    # never sent to a remote host
    assert discovery.resolve_token("https://other.example/Geoweaver") == (None, None)
    discovery.forget_token(url)
    assert discovery.resolve_token("http://127.0.0.1:23594/Geoweaver") == (None, None)


def test_env_token_wins(monkeypatch):
    monkeypatch.setenv("GEOWEAVER_API_TOKEN", " envtok ")
    assert discovery.resolve_token("http://127.0.0.1:1/Geoweaver") == ("envtok", "GEOWEAVER_API_TOKEN")


def test_legacy_ood_token_only_for_its_base_url(isolated_env):
    cdir = discovery.config_dir()
    os.makedirs(cdir)
    ood = "https://ondemand.example.edu/rnode/n1/23594/Geoweaver"
    with open(os.path.join(cdir, "ood-session.meta"), "w") as f:
        f.write(f"geoweaver_base_url={ood}\n")
    with open(os.path.join(cdir, "api-token"), "w") as f:
        f.write("oodtok\n")
    assert discovery.resolve_token(ood) == ("oodtok", "ood-api-token")
    assert discovery.resolve_token("https://evil.example/Geoweaver") == (None, None)


# ----------------------------------------------------------------------------- ensure

def test_ensure_healthy_server_is_not_touched(server):
    with patch.object(ensure, "_spawn_start") as spawn:
        out = ensure.ensure_server(server, timeout=5)
    assert out["action"] == "none"
    spawn.assert_not_called()


def test_ensure_refuses_second_jvm_on_other_port(server):
    port = server.split(":")[2].split("/")[0]
    with patch.object(ensure, "discover_local_servers", return_value=[(1, port)]), \
            patch.object(ensure, "_spawn_start") as spawn:
        with pytest.raises(AgentError) as e:
            ensure.ensure_server("http://127.0.0.1:1/Geoweaver", timeout=2)
    assert e.value.error == "running_on_other_port"
    spawn.assert_not_called()


def test_ensure_waits_for_booting_jvm_instead_of_starting(server):
    with patch.object(ensure, "discover_local_servers", return_value=[]), \
            patch.object(ensure, "own_geoweaver_processes", return_value=[object()]), \
            patch.object(ensure, "_spawn_start") as spawn:
        with pytest.raises(AgentError) as e:
            ensure.ensure_server("http://127.0.0.1:1/Geoweaver", timeout=1)
    assert e.value.exit_code == client_mod.EXIT_TIMEOUT
    spawn.assert_not_called()


def test_ensure_never_starts_remote():
    with pytest.raises(AgentError) as e:
        ensure.ensure_server("https://203.0.113.1:1/Geoweaver", timeout=1)
    assert "SSH" in e.value.message


def test_ensure_concurrent_callers_start_one_jvm(isolated_env):
    """Two agents racing: the lock holder starts, the other sees it up and does not spawn."""
    state = {"up": False, "spawns": 0}
    barrier = threading.Barrier(2)

    class _Child:
        def poll(self):
            return None

    def fake_spawn(port, log, allow_second=False):
        state["spawns"] += 1
        state["up"] = True
        return _Child()

    def fake_probe(self, timeout=1.0):
        return "up" if state["up"] else "down"

    results = []

    def worker():
        barrier.wait()
        results.append(ensure.ensure_server("http://127.0.0.1:1/Geoweaver", timeout=10)["action"])

    with patch.object(ensure, "_spawn_start", side_effect=fake_spawn), \
            patch.object(ensure, "discover_local_servers", return_value=[]), \
            patch.object(ensure, "own_geoweaver_processes", return_value=[]), \
            patch.object(AgentClient, "probe", fake_probe):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    assert state["spawns"] == 1
    assert sorted(results) in (["started", "waited-for-other-agent"], ["none", "started"])


# ----------------------------------------------------------------------------- CLI

def _cli(*args, input=None, token=None):
    env = {"GEOWEAVER_API_TOKEN": token} if token else None
    return CliRunner().invoke(agent, list(args), input=input, env=env, catch_exceptions=False)


def test_cli_login_list_and_options_after_subcommand(server):
    r = _cli("login", "--password-stdin", "--base-url", server, input="pw\n")
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["fingerprint"] == "fp1"
    # password never in argv; token now comes from the store
    r = _cli("process", "list", "--lang", "shell", "--base-url", server, "--compact")
    assert r.exit_code == 0
    assert json.loads(r.output) == [{"id": "p2", "name": "plot", "lang": "shell"}]
    r = _cli("--base-url", server, "status")
    assert json.loads(r.output)["auth"] == "ok"


def test_cli_errors_are_json_with_exit_codes(server):
    r = _cli("--base-url", server, "process", "list", token="bad")
    assert r.exit_code == client_mod.EXIT_UNAUTHORIZED
    r = _cli("--base-url", server, "run", "get", "missing", token=TOKEN)
    assert r.exit_code == client_mod.EXIT_NOT_FOUND
    r = _cli("login", "--password-stdin", "--base-url", server, input="nope\n")
    assert r.exit_code == client_mod.EXIT_UNAUTHORIZED


def test_cli_run_wait_and_workflow_chain(server):
    r = _cli("--base-url", server, "process", "run", "p1", "--wait", "--interval", "0.01",
             token=TOKEN)
    assert r.exit_code == 0 and json.loads(r.output)["status"] == "Done"
    r = _cli("--base-url", server, "workflow", "create", "--name", "w", "--chain", "p1,p2",
             token=TOKEN)
    wf = json.loads(r.output)
    assert [n["title"] for n in json.loads(wf["nodes"])] == ["n-p1", "n-p2"]
    assert len(json.loads(wf["edges"])) == 1
    r = _cli("--base-url", server, "run", "wait", "wf", token=TOKEN)
    assert r.exit_code == client_mod.EXIT_RUN_FAILED
    assert [s["historyId"] for s in json.loads(r.output)["steps"]] == ["s1", "s2"]


def test_cli_guide_mentions_core_commands():
    r = _cli("guide")
    for needle in ("gw agent ensure", "gw agent login", "--wait", "Exit codes"):
        assert needle in r.output


# ----------------------------------------------------------------------------- review round 1

def test_cli_has_no_token_argv_option():
    r = CliRunner().invoke(agent, ["--token", "x", "status"])
    assert r.exit_code == 2


def test_token_never_sent_to_another_users_port(server):
    """HIGH-010: /health is public, so a colleague's Geoweaver on a shared node looks 'up'."""
    port = server.split(":")[2].split("/")[0]
    discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": TOKEN, "fingerprint": "f"})
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        r = _cli("--base-url", server, "process", "list")
        assert r.exit_code == client_mod.EXIT_FOREIGN
        assert "another account" in r.output
        with patch.object(ensure, "_spawn_start") as spawn:
            out = ensure.ensure_server(server, timeout=1, explicit_url=True)  # report, no token
            assert out["action"] == "none" and "not owned" in out["warning"]
            with pytest.raises(AgentError) as e:  # down + foreign port: never start there
                ensure.ensure_server("http://127.0.0.1:1/Geoweaver", timeout=1)
        assert e.value.error == "foreign_server"
        spawn.assert_not_called()
    assert not any(c[0] == "GET" and c[1] == "/processes" for c in _Stub.calls)


def test_explicit_url_and_token_allowed_on_foreign_port_with_warning(server, monkeypatch):
    """MEDIUM-032: Docker / sshd -R tunnels look 'foreign' but the user chose them explicitly."""
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        r = _cli("--base-url", server, "process", "list", token=TOKEN)
        assert r.exit_code == 0
        _client, info = discovery.connect(server, token=TOKEN)
        assert "not owned" in info["warning"]
        monkeypatch.setenv("GEOWEAVER_AGENT_ALLOW_FOREIGN", "1")
        discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": TOKEN, "fingerprint": "f"})
        assert _cli("--base-url", server, "process", "list").exit_code == 0


def test_windows_lock_probe_never_calls_os_kill(monkeypatch):
    """CRITICAL-030: os.kill(pid, 0) terminates the process on Windows."""
    from pygeoweaver.agent import locking

    import psutil

    monkeypatch.setattr(locking.os, "name", "nt")
    with patch.object(locking.os, "kill", side_effect=AssertionError("os.kill used")), \
            patch.object(psutil, "pid_exists", side_effect=lambda pid: pid == 42):
        assert locking._pid_alive(42) is True
        assert locking._pid_alive(43) is False


def test_child_start_rechecks_under_lock(isolated_env):
    """MEDIUM-031: the starter child holds the lock and exits if a JVM appeared meanwhile."""
    with patch.object(ensure, "own_geoweaver_processes", return_value=[object()]), \
            patch("pygeoweaver.server.start_on_mac_linux") as start_mac:
        with pytest.raises(SystemExit) as e:
            ensure._child_start()
    assert e.value.code == 0
    start_mac.assert_not_called()


def test_insecure_http_remote_refused():
    c = AgentClient("http://203.0.113.9:8070/Geoweaver", token=TOKEN)
    with pytest.raises(AgentError) as e:
        c.list_processes()
    assert e.value.error == "insecure_transport"
    with pytest.raises(AgentError) as e:
        c.create_token("pw")  # the GUI password must not travel in clear text either
    assert e.value.error == "insecure_transport"


def test_probe_distinguishes_missing_agent_api(server):
    assert AgentClient(server).probe() == "up"
    assert AgentClient(server + "/nope").probe() == "no_agent_api"
    assert AgentClient("http://127.0.0.1:1/Geoweaver").probe() == "down"
    with patch.object(ensure, "_spawn_start") as spawn:
        with pytest.raises(AgentError) as e:
            ensure.ensure_server(server + "/nope", timeout=30)
    assert e.value.error == "agent_api_unavailable"
    spawn.assert_not_called()


def test_server_steps_preferred(server):
    c = AgentClient(server, token=TOKEN)
    run = {"historyId": "x", "log": "s1;s2;", "workflowRun": True, "steps": [{"id": "srv"}]}
    assert c.with_steps(run)["steps"] == [{"id": "srv"}]


def test_lock_falls_back_when_flock_unsupported(isolated_env):
    """HIGH-011: NFS homes without flock support must still serialize starts."""
    import errno
    import fcntl

    from pygeoweaver.agent import locking

    path = os.path.join(str(isolated_env), "cfg", "x.lock")

    def no_flock(fd, op):
        raise OSError(errno.ENOLCK, "No locks available")

    with patch.object(fcntl, "flock", no_flock):
        with locking.file_lock(path, timeout=1):
            assert os.path.exists(path + ".excl")
            with pytest.raises(AgentError):
                with locking.file_lock(path, timeout=0.3):
                    pass
        assert not os.path.exists(path + ".excl")


def test_gw_start_takes_the_start_lock(isolated_env):
    from pygeoweaver import server as server_mod
    from pygeoweaver.agent import locking

    seen = {}

    def fake_locked(*a, **k):
        seen["locked"] = True
        with pytest.raises(AgentError):
            with locking.start_lock(timeout=0.3):
                pass

    with patch.object(server_mod, "_start_locked", fake_locked), \
            patch.object(server_mod, "check_geoweaver_status", return_value=False):
        server_mod.start(exit_on_finish=False)
    assert seen == {"locked": True}


def test_cli_non_agent_errors_are_json(server):
    r = _cli("--base-url", server, "process", "create", "--name", "x", "--file", "/no/such",
             token=TOKEN)
    assert r.exit_code == client_mod.EXIT_ERROR
    assert json.loads(r.output.strip().splitlines()[-1])["error"] == "FileNotFoundError"


def test_cli_host_password_stdin_empty_is_an_error(server):
    r = _cli("--base-url", server, "process", "run", "p1", "--host-password-stdin", input="",
             token=TOKEN)
    assert r.exit_code == client_mod.EXIT_ERROR


# ----------------------------------------------------------------------------- review round 3

def test_login_refuses_foreign_default_port(server):
    """HIGH-050: first login must not POST the GUI password to another user's 8070."""
    port = server.split(":")[2].split("/")[0]
    with patch.object(discovery, "loopback_port_owner", return_value="other"), \
            patch.object(discovery, "DEFAULT_PORT", port), \
            patch.object(discovery, "discover_local_servers", return_value=[]):
        r = _cli("login", "--password-stdin", input="pw\n")
        assert r.exit_code == client_mod.EXIT_FOREIGN
        # explicit URL is the user's informed choice (e.g. Docker)
        r = _cli("login", "--password-stdin", "--base-url", server, input="pw\n")
        assert r.exit_code == 0
    assert sum(1 for c in _Stub.calls if c[1] == "/tokens") == 1


def test_stored_token_blocked_on_reused_foreign_port(server, monkeypatch):
    """MEDIUM-051: OOD port reused by another user; GEOWEAVER_PORT + stored token is automatic."""
    port = server.split(":")[2].split("/")[0]
    monkeypatch.setenv("GEOWEAVER_PORT", port)
    discovery.save_token(f"http://127.0.0.1:{port}/Geoweaver", {"token": TOKEN, "fingerprint": "f"})
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        assert _cli("process", "list").exit_code == client_mod.EXIT_FOREIGN
        assert _cli("--base-url", server, "process", "list").exit_code == client_mod.EXIT_FOREIGN
    assert not any(c[1] == "/processes" for c in _Stub.calls)


def test_ensure_default_url_on_foreign_server_fails(server):
    """LOW-053: `gw agent ensure && ...` must not continue on someone else's server."""
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        with pytest.raises(AgentError) as e:
            ensure.ensure_server(server, timeout=1, explicit_url=False)
    assert e.value.exit_code == client_mod.EXIT_FOREIGN


def test_wait_up_keeps_waiting_when_child_exits_but_jvm_boots():
    """MEDIUM-052: child exits (parallel start won / slow boot) while a JVM is still booting."""
    import time as _time

    class _Exited:
        def poll(self):
            return 0

    calls = {"n": 0}

    def is_up(timeout=1.0):
        calls["n"] += 1
        return calls["n"] > 14  # comes up ~7 s later

    client = AgentClient("http://127.0.0.1:1/Geoweaver")
    client.is_up = is_up
    with patch.object(ensure, "_own_jvm_on_port", return_value=True):
        assert ensure._wait_up(client, _time.monotonic() + 20, interval=0.5, child=_Exited())
    calls["n"] = -10 ** 6
    with patch.object(ensure, "_own_jvm_on_port", return_value=False):
        t0 = _time.monotonic()
        assert not ensure._wait_up(client, _time.monotonic() + 30, interval=0.5, child=_Exited())
        assert _time.monotonic() - t0 < 8


# ----------------------------------------------------------------------------- review round 4

def test_login_on_foreign_listener_returns_token_without_storing(server):
    """MEDIUM-070: never store (or make loopback-latest) a token for someone else's listener."""
    discovery.save_token("http://127.0.0.1:9/Geoweaver", {"token": "mine", "fingerprint": "m"})
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        r = _cli("login", "--password-stdin", "--base-url", server, input="pw\n")
    out = json.loads(r.output)
    assert r.exit_code == 0 and out["stored"] is None and out["token"] == TOKEN
    assert discovery.resolve_token("http://127.0.0.1:12345/Geoweaver") == ("mine", "store:loopback-latest")
    assert discovery.resolve_token(server)[0] == "mine"  # only via loopback-latest, not stored


def test_ensure_defaults_fail_closed(server):
    with patch.object(discovery, "loopback_port_owner", return_value="other"):
        with pytest.raises(AgentError):
            ensure.ensure_server(server, timeout=1)
