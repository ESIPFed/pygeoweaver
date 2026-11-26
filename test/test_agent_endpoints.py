"""Every Agent API endpoint through AgentClient and `gw agent`, against an echoing stub server."""
import json
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from pygeoweaver.agent import client as client_mod
from pygeoweaver.agent.cli import agent
from pygeoweaver.agent.client import AgentClient, AgentError

TOKEN = "tok-endpoints"
FILE_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 50


class _Echo(BaseHTTPRequestHandler):
    calls = []
    polls = 0
    hold_full = False

    def log_message(self, *args):
        pass

    def _send(self, code, payload, ctype="application/json"):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, method):
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path.replace("/Geoweaver/api/v1", "", 1)
        query = dict(urllib.parse.parse_qsl(parts.query))
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        _Echo.calls.append({"method": method, "path": path, "query": query, "body": body})
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"error": "unauthorized", "message": "no"})
        if path == "/workflows/import" and query.get("replace") != "true":
            return self._send(409, {"error": "conflict", "message": "Already on this server with "
                                    "different content: workflow w1. Re-send with ?replace=true "
                                    "to overwrite."})
        if path == "/local-only":
            return self._send(403, {"error": "local_only", "message": "Agent API is local only"})
        if path == "/results/file":
            return self._send(200, FILE_BYTES, "application/octet-stream")
        if path == "/runs/held":
            _Echo.polls += 1
            wait = float(query.get("waitSeconds", 0))
            if wait and _Echo.hold_full:
                time.sleep(wait)  # a real server holds until the run ends
            done = _Echo.polls >= 2
            return self._send(200, {"historyId": "held", "terminal": done,
                                    "status": "Done" if done else "Running"})
        return self._send(200, {"method": method, "path": path, "query": query, "body": body})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOWEAVER_AGENT_CONFIG_DIR", str(tmp_path / "cfg"))
    for var in ("GEOWEAVER_BASE_URL", "GEOWEAVER_PORT", "GEOWEAVER_API_TOKEN",
                "GEOWEAVER_OOD_COOKIE_JAR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def server():
    _Echo.calls, _Echo.polls = [], 0
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}/Geoweaver"
    httpd.shutdown()


@pytest.fixture
def c(server):
    return AgentClient(server, token=TOKEN)


def last():
    return _Echo.calls[-1]


# ----------------------------------------------------------------------------- client

CLIENT_CASES = [
    (lambda c: c.list_processes(query="fetch"), "GET", "/processes", {"q": "fetch"}, None),
    (lambda c: c.delete_process("p1"), "DELETE", "/processes/p1", {}, None),
    (lambda c: c.run_process("p1", host_id="h7", env_id="e2", host_password="pw"),
     "POST", "/processes/p1/runs", {},
     {"hostId": "h7", "envId": "e2", "hostPassword": "pw", "clientRunKey": None}),
    (lambda c: c.list_workflows(query="snow"), "GET", "/workflows", {"q": "snow"}, None),
    (lambda c: c.delete_workflow("w1"), "DELETE", "/workflows/w1", {}, None),
    (lambda c: c.list_workflow_runs("w1", log_limit=10), "GET", "/workflows/w1/runs",
     {"logLimit": "10"}, None),
    (lambda c: c.run_workflow("w1", host_id="h7", env_id="e2",
                              node_hosts={"p1-n0001": {"hostId": "h8"}},
                              host_passwords={"h7": "a", "h8": "b"}),
     "POST", "/workflows/w1/runs", {},
     {"mode": "one", "hostId": "h7", "envId": "e2", "hostPassword": None, "clientRunKey": None,
      "nodeHosts": {"p1-n0001": {"hostId": "h8", "envId": None}},
      "hostPasswords": {"h7": "a", "h8": "b"}}),
    (lambda c: c.set_step_skipped("w1", "p1-n0001", True), "PUT", "/workflows/w1/steps/p1-n0001",
     {}, {"skip": True}),
    (lambda c: c.set_step_skipped("w1", "p1-n0001", False), "PUT", "/workflows/w1/steps/p1-n0001",
     {}, {"skip": False}),
    (lambda c: c.list_checkpoints("w1"), "GET", "/workflows/w1/checkpoints", {}, None),
    (lambda c: c.restore_checkpoint("w1", "r9"), "POST", "/workflows/w1/restore", {},
     {"runId": "r9"}),
    (lambda c: c.export_workflow("w1"), "GET", "/workflows/w1/export", {}, None),
    (lambda c: c.import_workflow({"workflow": {"id": "w1"}}, replace=True), "POST",
     "/workflows/import", {"replace": "true"}, {"workflow": {"id": "w1"}}),
    (lambda c: c.import_workflow('{"workflow": {}}', replace=True), "POST", "/workflows/import",
     {"replace": "true"}, {"workflow": {}}),
    (lambda c: c.list_hosts(query="hpc"), "GET", "/hosts", {"q": "hpc"}, None),
    (lambda c: c.get_host("h7"), "GET", "/hosts/h7", {}, None),
    (lambda c: c.create_host("hpc", ip="10.0.0.5", port=2222, username="me"), "POST", "/hosts",
     {}, {"name": "hpc", "type": "ssh", "ip": "10.0.0.5", "port": "2222", "username": "me",
          "url": None}),
    (lambda c: c.update_host("h7", name="renamed"), "PUT", "/hosts/h7", {},
     {"name": "renamed", "type": None, "ip": None, "port": None, "username": None, "url": None}),
    (lambda c: c.delete_host("h7"), "DELETE", "/hosts/h7", {}, None),
    (lambda c: c.list_environments("h7"), "GET", "/hosts/h7/environments", {}, None),
    (lambda c: c.scan_environments("h7", host_password="pw"), "POST",
     "/hosts/h7/environments/scan", {}, {"hostPassword": "pw"}),
    (lambda c: c.get_run("r1", log_limit=5, wait_seconds=99, include_step_logs=True), "GET",
     "/runs/r1", {"logLimit": "5", "waitSeconds": "60", "includeStepLogs": "true"}, None),
    (lambda c: c.list_runs(limit=5, status="Running"), "GET", "/runs",
     {"limit": "5", "status": "Running"}, None),
    (lambda c: c.delete_run("r1"), "DELETE", "/runs/r1", {}, None),
    (lambda c: c.delete_runs("Failed", process_id="p1"), "DELETE", "/runs",
     {"status": "Failed", "processId": "p1"}, None),
    (lambda c: c.set_run_notes("r1", "baseline"), "PUT", "/runs/r1/notes", {},
     {"notes": "baseline"}),
    (lambda c: c.list_results("maps/2026"), "GET", "/results", {"path": "maps/2026"}, None),
    (lambda c: c.list_results(), "GET", "/results", {}, None),
]


@pytest.mark.parametrize("call,method,path,query,body", CLIENT_CASES)
def test_client_endpoint(c, call, method, path, query, body):
    call(c)
    got = last()
    assert (got["method"], got["path"], got["query"]) == (method, path, query)
    assert got["body"] == body


@pytest.mark.parametrize("call", [
    lambda c: c.get_host("../tokens"),
    lambda c: c.set_step_skipped("w1", "a/b"),
    lambda c: c.restore_checkpoint("w1", "x?y"),
    lambda c: c.run_process("p1", host_id="h 1"),
    lambda c: c.run_workflow("w1", host_passwords={"../h": "pw"}),
    lambda c: c.delete_runs("Done"),
    lambda c: c.list_results("../secret"),
    lambda c: c.list_results("/etc"),
    lambda c: c.download_result("a/../../b"),
    lambda c: c.import_workflow("{not json"),
])
def test_client_rejects_bad_input_before_sending(c, call):
    with pytest.raises(AgentError) as e:
        call(c)
    assert e.value.exit_code == client_mod.EXIT_USAGE
    assert _Echo.calls == []


def test_download_result_never_overwrites(c, tmp_path):
    saved = c.download_result("maps/swe.png", str(tmp_path))
    assert saved == str(tmp_path / "swe.png")
    assert open(saved, "rb").read() == FILE_BYTES
    assert last()["query"] == {"path": "maps/swe.png"}
    with pytest.raises(AgentError) as e:
        c.download_result("maps/swe.png", str(tmp_path))
    assert e.value.error == "exists"
    other = tmp_path / "renamed.png"
    assert c.download_result("maps/swe.png", str(other)) == str(other)
    c.download_result("maps/swe.png", str(other), overwrite=True)
    assert [f for f in os.listdir(tmp_path) if f.startswith(".gw-download-")] == []


def test_import_workflow_from_file(c, tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"workflow": {"id": "w2"}, "processes": []}))
    c.import_workflow(str(bundle), replace=True)
    assert last()["body"] == {"workflow": {"id": "w2"}, "processes": []}
    with pytest.raises(AgentError) as e:
        c.import_workflow(str(bundle))
    assert e.value.status == 409 and "--replace" in e.value.message
    assert "?replace=true" not in e.value.message


def test_wait_run_lets_the_server_hold_the_request(c, monkeypatch):
    import types

    sleeps = []
    monkeypatch.setattr(client_mod, "LONG_POLL_SECONDS", 1)
    monkeypatch.setattr(client_mod, "time", types.SimpleNamespace(
        monotonic=time.monotonic, sleep=lambda s: sleeps.append(s)))
    _Echo.hold_full = True
    try:
        run = c.wait_run("held", timeout=20)
    finally:
        _Echo.hold_full = False
    assert run["status"] == "Done"
    assert _Echo.polls == 2
    assert all(call["query"]["waitSeconds"] == "1" for call in _Echo.calls)
    assert sleeps == []  # no client-side polling while the server holds the request


def test_wait_run_backs_off_on_servers_that_answer_at_once(c, monkeypatch):
    import types

    sleeps = []
    monkeypatch.setattr(client_mod, "time", types.SimpleNamespace(
        monotonic=time.monotonic, sleep=lambda s: sleeps.append(s)))
    run = c.wait_run("held", timeout=20, interval=2)
    assert run["status"] == "Done" and sleeps == [client_mod.MIN_POLL_INTERVAL]


def test_local_only_error_explains_ssh(c):
    with pytest.raises(AgentError) as e:
        c.request("GET", "/local-only")
    assert e.value.error == "local_only" and e.value.status == 403
    assert "ssh user@host gw agent" in e.value.message


# ----------------------------------------------------------------------------- CLI

def gw(server, *args, input=None):
    env = {"GEOWEAVER_API_TOKEN": TOKEN}
    return CliRunner().invoke(agent, ["--base-url", server, "--compact", *args], input=input,
                              env=env)


def test_cli_deletes_need_yes(server):
    for args in (["process", "delete", "p1"], ["workflow", "delete", "w1"],
                 ["host", "delete", "h7"], ["run", "delete", "r1"],
                 ["run", "prune", "--status", "Failed"]):
        r = gw(server, *args)
        assert r.exit_code == 2, (args, r.output)
    assert _Echo.calls == []
    r = gw(server, "run", "prune", "--status", "Skipped", "--process-id", "p1", "--yes")
    assert r.exit_code == 0, r.output
    assert last()["method"] == "DELETE" and last()["query"] == {"status": "Skipped",
                                                                 "processId": "p1"}


@pytest.mark.parametrize("args,method,path,query,body", [
    (["process", "list", "-q", "fetch"], "GET", "/processes", {"q": "fetch"}, None),
    (["process", "delete", "p1", "--yes"], "DELETE", "/processes/p1", {}, None),
    (["workflow", "delete", "w1", "--yes"], "DELETE", "/workflows/w1", {}, None),
    (["workflow", "runs", "w1"], "GET", "/workflows/w1/runs", {"logLimit": "0"}, None),
    (["workflow", "skip", "w1", "p1-n1"], "PUT", "/workflows/w1/steps/p1-n1", {}, {"skip": True}),
    (["workflow", "skip", "w1", "p1-n1", "--off"], "PUT", "/workflows/w1/steps/p1-n1", {},
     {"skip": False}),
    (["workflow", "checkpoints", "w1"], "GET", "/workflows/w1/checkpoints", {}, None),
    (["workflow", "restore", "w1", "--run-id", "r9"], "POST", "/workflows/w1/restore", {},
     {"runId": "r9"}),
    (["host", "list"], "GET", "/hosts", {}, None),
    (["host", "create", "--name", "hpc", "--ip", "10.0.0.5", "--username", "me"], "POST",
     "/hosts", {}, {"name": "hpc", "type": "ssh", "ip": "10.0.0.5", "port": None,
                    "username": "me", "url": None}),
    (["host", "update", "h7", "--port", "2222"], "PUT", "/hosts/h7", {},
     {"name": None, "type": None, "ip": None, "port": "2222", "username": None, "url": None}),
    (["host", "delete", "h7", "--yes"], "DELETE", "/hosts/h7", {}, None),
    (["host", "envs", "h7"], "GET", "/hosts/h7/environments", {}, None),
    (["run", "list", "--status", "Running"], "GET", "/runs", {"status": "Running"}, None),
    (["run", "delete", "r1", "--yes"], "DELETE", "/runs/r1", {}, None),
    (["run", "notes", "r1", "--text", "baseline"], "PUT", "/runs/r1/notes", {},
     {"notes": "baseline"}),
    (["results", "list", "maps"], "GET", "/results", {"path": "maps"}, None),
])
def test_cli_endpoint(server, args, method, path, query, body):
    r = gw(server, *args)
    assert r.exit_code == 0, r.output
    got = last()
    assert (got["method"], got["path"], got["query"], got["body"]) == (method, path, query, body)


def test_cli_passwords_only_from_stdin(server):
    r = gw(server, "host", "envs", "h7", "--scan", "--host-password-stdin", input="s3cret\n")
    assert r.exit_code == 0, r.output
    assert last()["body"] == {"hostPassword": "s3cret"}
    r = gw(server, "process", "run", "p1", "--host-id", "h7", "--host-password-stdin",
           input="s3cret\n")
    assert r.exit_code == 0, r.output
    assert last()["body"]["hostId"] == "h7" and last()["body"]["hostPassword"] == "s3cret"
    r = gw(server, "workflow", "run", "w1", "--node-hosts", '{"p1-n1": {"hostId": "h8"}}',
           "--host-passwords-stdin", input='{"h8": "pw8"}\n')
    assert r.exit_code == 0, r.output
    assert last()["body"]["nodeHosts"] == {"p1-n1": {"hostId": "h8", "envId": None}}
    assert last()["body"]["hostPasswords"] == {"h8": "pw8"}
    r = gw(server, "workflow", "run", "w1", "--host-passwords-stdin", input="not json\n")
    assert r.exit_code == 2


def test_cli_export_and_import_through_files_and_stdin(server, tmp_path):
    r = gw(server, "workflow", "export", "w1", "--out", "bundle.json")
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["file"] == str(tmp_path / "bundle.json")
    assert json.loads((tmp_path / "bundle.json").read_text())["path"] == "/workflows/w1/export"
    r = gw(server, "workflow", "export", "w1", "--out", "bundle.json")
    assert r.exit_code == 2 and "already exists" in r.output
    r = gw(server, "workflow", "import", "-", "--replace", input='{"workflow": {"id": "w1"}}')
    assert r.exit_code == 0, r.output
    assert last()["body"] == {"workflow": {"id": "w1"}} and last()["query"] == {"replace": "true"}
    r = gw(server, "workflow", "import", "bundle.json")
    assert r.exit_code == 6 and "--replace" in r.output
    r = gw(server, "workflow", "import", "missing.json")
    assert r.exit_code == 2


def test_cli_results_get_to_file_and_stdout(server, tmp_path):
    r = gw(server, "results", "get", "maps/swe.png")
    assert r.exit_code == 0, r.output
    assert (tmp_path / "swe.png").read_bytes() == FILE_BYTES
    r = gw(server, "results", "get", "maps/swe.png")
    assert r.exit_code == 2
    r = CliRunner().invoke(agent, ["--base-url", server, "results", "get", "maps/swe.png",
                                   "--out", "-"], env={"GEOWEAVER_API_TOKEN": TOKEN})
    assert r.exit_code == 0
    assert r.stdout_bytes == FILE_BYTES


def test_download_into_new_folder_and_error_cases(c, tmp_path):
    saved = c.download_result("maps/swe.png", str(tmp_path / "new") + "/")
    assert saved == str(tmp_path / "new" / "swe.png")
    with pytest.raises(AgentError) as e:
        c.download_result("maps/swe.png", str(tmp_path / "missing" / "x.png"))
    assert e.value.exit_code == client_mod.EXIT_USAGE
    assert open(saved, "rb").read() == FILE_BYTES


def test_import_rejects_non_object_bundles(c):
    for bad in ("[1, 2]", b"", "   "):
        with pytest.raises(AgentError):
            c.import_workflow(bad)
    assert _Echo.calls == []


def test_cli_export_force_replaces_atomically(server, tmp_path):
    (tmp_path / "b.json").write_text("old")
    r = gw(server, "workflow", "export", "w1", "--out", "b.json", "--force")
    assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "b.json").read_text())["path"] == "/workflows/w1/export"
    assert [f for f in os.listdir(tmp_path) if f.startswith(".gw-export-")] == []


def test_guide_examples_survive_a_remote_shell():
    from pygeoweaver.agent import GUIDE

    assert "--code 'echo" not in GUIDE and "--text '" not in GUIDE
