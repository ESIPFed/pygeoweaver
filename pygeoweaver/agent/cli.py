"""
``gw agent`` — fast, JSON-first commands for AI agents (and humans) driving a live Geoweaver.

Every command talks to the running server over ``/api/v1``: no second JVM, no direct
H2 access, and the GUI sees each change immediately. stdout is JSON (pretty on a TTY,
compact otherwise); errors are JSON on stderr with a stable exit code.
"""
import getpass
import json
import os
import re
import sys
import tempfile

import click

from pygeoweaver.agent.client import (
    EXIT_ERROR,
    EXIT_USAGE,
    MAX_STEPS,
    MIN_POLL_INTERVAL,
    AgentClient,
    EXIT_RUN_FAILED,
    AgentError,
    linear_workflow_graph,
)
from pygeoweaver.agent import discovery


class _Ctx:
    def __init__(self, base_url, token, timeout, pretty):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.pretty = pretty
        self._client = None
        self.info = None

    def client(self, sends_password=False):
        if self._client is None:
            self._client, self.info = discovery.connect(self.base_url, self.token, self.timeout,
                                                        sends_password=sends_password)
        return self._client


# Server data (run logs, process code, error messages) is untrusted. JSON already escapes
# C0 controls; also escape C1 controls (e.g. U+009B CSI), bidi overrides and line
# separators so they cannot drive a terminal or hide text from a reader.
_UNSAFE_JSON = re.compile("[\u007f-\u009f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
# Raw text to a terminal: drop ESC/OSC sequences and other controls, keep \t and \n.
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
_UNSAFE_TEXT = re.compile("[\x00-\x08\x0b-\x1f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _json_text(data, indent=None):
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    return _UNSAFE_JSON.sub(lambda m: "\\u%04x" % ord(m.group()), text)


def emit(ctx, data):
    pretty = ctx.pretty if ctx.pretty is not None else sys.stdout.isatty()
    click.echo(_json_text(data, indent=2 if pretty else None))


def emit_text(text, nl=True):
    """Raw server text (logs, code). Sanitized on a terminal; byte-exact when piped."""
    if sys.stdout.isatty():
        text = _UNSAFE_TEXT.sub("", _ANSI.sub("", text.replace("\r\n", "\n")))
    # Not click.echo: it rewrites escape sequences even when piped (e.g. `> code.py`).
    sys.stdout.write(text + ("\n" if nl else ""))
    sys.stdout.flush()


def fail(err):
    click.echo(_json_text(err.to_dict()), err=True)
    sys.exit(err.exit_code)


def _override(attr):
    def callback(ctx, _param, value):
        if value is not None:
            setattr(ctx.find_object(_Ctx), attr, value)
    return callback


class AgentCommand(click.Command):
    """Leaf command that also accepts the group options after the subcommand name
    (agents write ``gw agent process list --base-url ...`` as often as the other order)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.extend([
            click.Option(["--base-url"], default=None, expose_value=False,
                         callback=_override("base_url"), help="Same as `gw agent --base-url`."),
            click.Option(["--pretty/--compact"], default=None, expose_value=False,
                         callback=_override("pretty"), help="JSON formatting."),
        ])


class AgentGroup(click.Group):
    """Turn :class:`AgentError` into JSON on stderr + exit code for every subcommand."""

    command_class = AgentCommand
    group_class = type

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except AgentError as e:
            fail(e)
        except click.exceptions.Exit:
            raise
        except click.ClickException as e:
            fail(AgentError("usage", e.format_message(), exit_code=2))
        except (OSError, KeyError, ValueError) as e:
            fail(AgentError(type(e).__name__, str(e), exit_code=EXIT_ERROR))


def _read_code(code, file_path):
    if code is not None and file_path is not None:
        raise click.UsageError("Use either --code or --file, not both")
    if file_path == "-" or code == "-":
        return sys.stdin.read()
    if file_path is not None:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return code


def _read_json_arg(value):
    """Accept inline JSON, ``@path`` to a JSON file, or ``-`` for stdin."""
    if value is None:
        return None
    if value == "-":
        value = sys.stdin.read()
    elif value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as f:
            value = f.read()
    try:
        json.loads(value)
    except ValueError as e:
        raise click.BadParameter(f"not valid JSON: {e}")
    return value


def _chain_ids(chain):
    ids = [p.strip() for p in chain.split(",") if p.strip()]
    if len(ids) > MAX_STEPS:
        raise click.UsageError(f"--chain accepts at most {MAX_STEPS} process ids")
    return ids


def _read_secret(prompt, from_stdin):
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    return getpass.getpass(prompt)


def _host_password(flag):
    """GUI localhost password for runs, only when the server disallows token-only runs."""
    if not flag:
        return None
    password = _read_secret("", True)
    if not password:
        raise AgentError("bad_request", "--host-password-stdin given but stdin had no password",
                         exit_code=EXIT_ERROR)
    return password


def _require_yes(yes, what):
    if not yes:
        raise click.UsageError(f"Deleting {what} cannot be undone; add --yes to confirm")


def _host_passwords(flag):
    """``{host_id: password}`` as one JSON object on stdin (never on the command line)."""
    if not flag:
        return None
    try:
        data = json.loads(sys.stdin.readline())
    except ValueError:
        data = None
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise AgentError("bad_request", "--host-passwords-stdin expects one line of JSON "
                         '{"<hostId>": "<password>", ...}', exit_code=EXIT_USAGE)
    return data


def _write_new_file(path, data, force):
    """Write ``data`` to ``path`` in one step; never replace an existing file unless ``force``."""
    path = os.path.abspath(path)
    if os.path.lexists(path) and not force:
        raise AgentError("exists", f"{path} already exists (use --force)", exit_code=EXIT_USAGE)
    fd, tmp = tempfile.mkstemp(prefix=".gw-export-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        if force:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # fails if someone created the file meanwhile
            os.unlink(tmp)
    except FileExistsError:
        os.unlink(tmp)
        raise AgentError("exists", f"{path} already exists (use --force)",
                         exit_code=EXIT_USAGE) from None
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def _finish_run(ctx, client, started, wait, timeout, interval, log_limit):
    if not wait:
        emit(ctx, started)
        return
    run = client.wait_run(started["historyId"], timeout=timeout, interval=interval,
                          log_limit=log_limit)
    run = client.with_steps(run, log_limit=log_limit)
    run["reusedExisting"] = started.get("reusedExisting", False)
    emit(ctx, run)
    if run.get("status") != "Done":
        sys.exit(EXIT_RUN_FAILED)


_LOG_LIMIT = click.IntRange(0, 1_000_000)
_INTERVAL = click.FloatRange(min=MIN_POLL_INTERVAL)
_TIMEOUT = click.FloatRange(min=0)


def _wait_options(f):
    f = click.option("--log-limit", type=_LOG_LIMIT, default=4000, show_default=True,
                     help="Max log characters returned with --wait.")(f)
    f = click.option("--interval", type=_INTERVAL, default=2.0, show_default=True,
                     help="Max seconds between polls with --wait.")(f)
    f = click.option("--timeout", "wait_timeout", type=_TIMEOUT, default=3600, show_default=True,
                     help="Seconds to wait with --wait (the run keeps going after).")(f)
    f = click.option("--wait", is_flag=True,
                     help="Block until the run finishes; exit 8 unless status is Done.")(f)
    return f


@click.group("agent", cls=AgentGroup)
@click.option("--base-url", envvar=None, default=None,
              help="Geoweaver base URL incl. /Geoweaver. Default: GEOWEAVER_BASE_URL, "
                   "GEOWEAVER_PORT, your running Geoweaver JVM, then :8070.")
@click.option("--http-timeout", type=click.FloatRange(min=0.1, max=600), default=30.0,
              show_default=True)
@click.option("--pretty/--compact", default=None, help="JSON formatting (default: pretty on a TTY).")
@click.pass_context
def agent(ctx, base_url, http_timeout, pretty):
    """
    Fast AI-agent interface to a live Geoweaver (JSON in/out, no JVM boot).

    \b
    Typical agent session over SSH:
      gw agent ensure                       # make sure the server is up (never restarts it)
      gw agent login --password-stdin       # once; stores a token (0600) for this server
      gw agent process create --name hello --lang python --code 'print(42)'
      gw agent process run <id> --wait      # live in the GUI while it runs
      gw agent guide                        # full playbook for AI agents
    """
    # Tokens never go on the command line (visible in `ps`): store or GEOWEAVER_API_TOKEN.
    ctx.obj = _Ctx(base_url, None, http_timeout, pretty)


# ------------------------------------------------------------------ server

@agent.command("status")
@click.pass_obj
def status_cmd(c):
    """Base URL, health, latency, and whether the token is accepted."""
    import time

    client = c.client()
    out = dict(c.info)
    t0 = time.perf_counter()
    out["healthy"] = client.is_up(timeout=2.0)
    out["healthMs"] = round((time.perf_counter() - t0) * 1000, 1)
    out["serverPids"] = [p.pid for p in discovery.own_geoweaver_processes()]
    if out.get("baseUrlSource") == "discovered":
        others = sorted({discovery.local_base_url(port) for _pid, port in
                         discovery.discover_local_servers()} - {client.base_url})
        others = [u for u in others if AgentClient(u).is_up(timeout=0.3)]
        if others:
            out["otherLocalServers"] = others
    if out["healthy"]:
        if not client.token:
            out["auth"] = "missing"
        else:
            try:
                caps = client.capabilities()
                out["auth"] = "ok"
                out["allowLocalhostRuns"] = caps.get("allowLocalhostRuns")
            except AgentError as e:
                out["auth"] = "invalid" if e.status in (401, 403) else "unknown"
                out["authError"] = e.message
    entry = discovery.stored_token_entry(client.base_url)
    if entry and c.info.get("tokenSource", "").startswith("store"):
        out["tokenFingerprint"] = entry.get("fingerprint")
        out["tokenExpiresAt"] = entry.get("expiresAt")
    emit(c, out)


@agent.command("ensure")
@click.option("--timeout", type=_TIMEOUT, default=240, show_default=True,
              help="Seconds to wait for the server to answer.")
@click.option("--no-start", is_flag=True, help="Only check / wait; never start a JVM.")
@click.option("--allow-second-server", is_flag=True,
              help="Start even if another of your Geoweaver JVMs is running (only safe when "
                   "it uses a different database / home).")
@click.pass_obj
def ensure_cmd(c, timeout, no_start, allow_second_server):
    """Make sure Geoweaver is up. A healthy server is never restarted or touched."""
    from pygeoweaver.agent.ensure import ensure_server

    base_url, source = discovery.resolve_base_url(c.base_url)
    out = ensure_server(base_url, timeout=timeout, start=not no_start,
                        allow_second_server=allow_second_server,
                        explicit_url=source in discovery.EXPLICIT_URL_SOURCES)
    out["baseUrlSource"] = source
    emit(c, out)


@agent.command("capabilities")
@click.pass_obj
def capabilities_cmd(c):
    """What this server's Agent API allows."""
    emit(c, c.client().capabilities())


@agent.command("login")
@click.option("--password-stdin", is_flag=True,
              help="Read the GUI localhost password from the first line of stdin.")
@click.option("--ttl-days", type=click.IntRange(1, 180), default=30, show_default=True)
@click.option("--revoke-others", is_flag=True, help="Revoke this server's other tokens.")
@click.option("--token-file", default=None, type=click.Path(dir_okay=False),
              help="Required when the port is not owned by your account (Docker -p, sshd -R): "
                   "write the token to this new file (0600) instead of the store.")
@click.pass_obj
def login_cmd(c, password_stdin, ttl_days, revoke_others, token_file):
    """
    Mint an Agent API token with the Geoweaver GUI password and store it (0600).

    The password is never accepted on the command line (it would show in `ps`), and the
    token is never printed.
    """
    client = c.client(sends_password=True)
    foreign = bool(c.info.get("warning"))
    if foreign and not token_file:
        raise AgentError(
            "token_file_required",
            "This port is not owned by your account, so the token cannot go to the shared "
            "store (it would replace your own Geoweaver's token) and is never printed. "
            "Re-run with --token-file PATH, then pass it as GEOWEAVER_API_TOKEN with --base-url.",
            exit_code=EXIT_USAGE)
    out_fd = None
    if token_file:
        # Create before sending the password: fail early, and never overwrite/follow a link.
        out_fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        password = _read_secret("Geoweaver GUI localhost password: ", password_stdin)
        if not password:
            raise AgentError("bad_request", "Empty password", exit_code=EXIT_ERROR)
        created = client.create_token(password, ttl_days=ttl_days, revoke_others=revoke_others)
    except BaseException:
        if out_fd is not None:
            os.close(out_fd)
            os.unlink(token_file)
        raise
    if out_fd is not None:
        with os.fdopen(out_fd, "w", encoding="utf-8") as f:
            f.write(created["token"] + "\n")
        emit(c, {"baseUrl": client.base_url, "fingerprint": created.get("fingerprint"),
                 "expiresAt": created.get("expiresAt"), "stored": None,
                 "tokenFile": os.path.abspath(token_file)})
        return
    entry = discovery.save_token(client.base_url, created)
    emit(c, {"baseUrl": client.base_url, "fingerprint": entry["fingerprint"],
             "expiresAt": entry["expiresAt"],
             "stored": os.path.join(discovery.config_dir(), "agent-tokens.json")})


@agent.command("logout")
@click.option("--local-only", is_flag=True, help="Only delete the stored token; keep it valid on the server.")
@click.pass_obj
def logout_cmd(c, local_only):
    """Revoke the stored token on the server and delete it locally."""
    client = c.client()
    entry = discovery.stored_token_entry(client.base_url)
    out = {"baseUrl": client.base_url, "revoked": False, "deleted": False}
    if entry:
        if not local_only and entry.get("fingerprint"):
            try:
                client.token = entry["token"]
                client.revoke_token(entry["fingerprint"])
                out["revoked"] = True
            except AgentError as e:
                out["revokeError"] = e.message
        out["deleted"] = discovery.forget_token(client.base_url) is not None
        out["fingerprint"] = entry.get("fingerprint")
    emit(c, out)


@agent.command("tokens")
@click.pass_obj
def tokens_cmd(c):
    """List token fingerprints on the server (no secrets)."""
    emit(c, c.client().list_tokens())


# ------------------------------------------------------------------ processes

@agent.group("process", cls=AgentGroup)
def process_grp():
    """Create, edit, run, delete and inspect processes (python | shell | builtin)."""


@process_grp.command("list")
@click.option("--name", "name_filter", default=None, help="Case-insensitive substring filter.")
@click.option("--lang", default=None)
@click.option("--query", "-q", default=None, help="Server-side filter on id, name or description.")
@click.pass_obj
def process_list(c, name_filter, lang, query):
    items = c.client().list_processes(query=query) or []
    if name_filter:
        items = [p for p in items if name_filter.lower() in (p.get("name") or "").lower()]
    if lang:
        items = [p for p in items if (p.get("lang") or "").lower() == lang.lower()]
    emit(c, items)


@process_grp.command("get")
@click.argument("process_id")
@click.option("--code-only", is_flag=True,
              help="Print the raw code instead of JSON (control characters removed on a TTY).")
@click.pass_obj
def process_get(c, process_id, code_only):
    p = c.client().get_process(process_id)
    if code_only:
        emit_text(p.get("code") or "", nl=False)
        return
    emit(c, p)


@process_grp.command("create")
@click.option("--name", required=True)
@click.option("--lang", type=click.Choice(["python", "shell", "builtin"]), default="python",
              show_default=True)
@click.option("--code", default=None, help="Code text, or '-' for stdin.")
@click.option("--file", "file_path", default=None, help="Read code from a file ('-' = stdin).")
@click.option("--description", default=None)
@click.pass_obj
def process_create(c, name, lang, code, file_path, description):
    """Create a process; it appears in open GUIs immediately."""
    body = _read_code(code, file_path)
    if body is None:
        raise click.UsageError("--code or --file is required")
    emit(c, c.client().create_process(name, body, lang=lang, description=description))


@process_grp.command("update")
@click.argument("process_id")
@click.option("--name", default=None)
@click.option("--lang", type=click.Choice(["python", "shell", "builtin"]), default=None)
@click.option("--code", default=None, help="New code, or '-' for stdin.")
@click.option("--file", "file_path", default=None)
@click.option("--description", default=None)
@click.pass_obj
def process_update(c, process_id, name, lang, code, file_path, description):
    """Edit fields of a process (omitted fields are kept)."""
    body = _read_code(code, file_path)
    emit(c, c.client().update_process(process_id, name=name, code=body, lang=lang,
                                      description=description))


@process_grp.command("delete")
@click.argument("process_id")
@click.option("--yes", is_flag=True, help="Confirm the delete.")
@click.pass_obj
def process_delete(c, process_id, yes):
    """Delete a process (refused while a workflow uses it)."""
    _require_yes(yes, "a process")
    emit(c, c.client().delete_process(process_id))


@process_grp.command("run")
@click.argument("process_id")
@click.option("--host-id", default=None,
              help="Run on this host (`gw agent host list`); default the Geoweaver machine.")
@click.option("--env-id", default=None, help="Geoweaver environment id (python binary / venv).")
@click.option("--key", "client_run_key", default=None,
              help="Idempotency key: re-sending it (same token, same server uptime) returns "
                   "the existing run instead of starting a new one.")
@click.option("--host-password-stdin", "ask_password", is_flag=True,
              help="Read the host's password from stdin: the SSH password for an SSH host, or "
                   "the GUI localhost password if the server requires it.")
@_wait_options
@click.pass_obj
def process_run(c, process_id, host_id, env_id, client_run_key, ask_password, wait,
                wait_timeout, interval, log_limit):
    """Run a process on the Geoweaver machine (default) or a registered host."""
    client = c.client()
    started = client.run_process(process_id, env_id=env_id, host_id=host_id,
                                 host_password=_host_password(ask_password),
                                 client_run_key=client_run_key)
    _finish_run(c, client, started, wait, wait_timeout, interval, log_limit)


@process_grp.command("runs")
@click.argument("process_id")
@click.option("--log-limit", type=_LOG_LIMIT, default=0, show_default=True)
@click.option("--limit", type=click.IntRange(min=1), default=None,
              help="Only the N most recent runs.")
@click.pass_obj
def process_runs(c, process_id, log_limit, limit):
    """Run history of a process."""
    runs = c.client().list_process_runs(process_id, log_limit=log_limit) or []
    emit(c, runs[:limit] if limit else runs)


# ------------------------------------------------------------------ workflows

@agent.group("workflow", cls=AgentGroup)
def workflow_grp():
    """Create, edit, run, share and inspect workflows."""


@workflow_grp.command("list")
@click.option("--name", "name_filter", default=None)
@click.option("--query", "-q", default=None, help="Server-side filter on id, name or description.")
@click.pass_obj
def workflow_list(c, name_filter, query):
    items = c.client().list_workflows(query=query) or []
    if name_filter:
        items = [w for w in items if name_filter.lower() in (w.get("name") or "").lower()]
    emit(c, items)


@workflow_grp.command("get")
@click.argument("workflow_id")
@click.pass_obj
def workflow_get(c, workflow_id):
    emit(c, c.client().get_workflow(workflow_id))


@workflow_grp.command("create")
@click.option("--name", required=True)
@click.option("--chain", default=None,
              help="Comma-separated process ids run in this order (builds nodes+edges).")
@click.option("--nodes", default=None, help="Nodes JSON, @file, or '-' (Geoweaver GUI format).")
@click.option("--edges", default=None, help="Edges JSON, @file, or '-'.")
@click.option("--description", default=None)
@click.pass_obj
def workflow_create(c, name, chain, nodes, edges, description):
    """Create a workflow from a process chain or raw Geoweaver nodes/edges."""
    client = c.client()
    if chain:
        if nodes or edges:
            raise click.UsageError("Use --chain or --nodes/--edges, not both")
        ids = _chain_ids(chain)
        titles = [client.get_process(pid).get("name") or pid for pid in ids]
        node_list, edge_list = linear_workflow_graph(ids, titles)
        nodes, edges = json.dumps(node_list), json.dumps(edge_list)
    else:
        nodes, edges = _read_json_arg(nodes), _read_json_arg(edges)
        if not nodes:
            raise click.UsageError("--chain or --nodes is required")
    emit(c, client.create_workflow(name, nodes, edges or "[]", description=description))


@workflow_grp.command("update")
@click.argument("workflow_id")
@click.option("--name", default=None)
@click.option("--chain", default=None, help="Replace the graph with this process chain.")
@click.option("--nodes", default=None)
@click.option("--edges", default=None)
@click.option("--description", default=None)
@click.pass_obj
def workflow_update(c, workflow_id, name, chain, nodes, edges, description):
    """Edit a workflow (omitted fields are kept)."""
    client = c.client()
    if chain:
        ids = _chain_ids(chain)
        titles = [client.get_process(pid).get("name") or pid for pid in ids]
        node_list, edge_list = linear_workflow_graph(ids, titles)
        nodes, edges = json.dumps(node_list), json.dumps(edge_list)
    else:
        nodes, edges = _read_json_arg(nodes), _read_json_arg(edges)
    emit(c, client.update_workflow(workflow_id, name=name, nodes=nodes, edges=edges,
                                   description=description))


@workflow_grp.command("run")
@click.argument("workflow_id")
@click.option("--mode", type=click.Choice(["one", "multiple"]), default="one", show_default=True)
@click.option("--host-id", default=None, help="Run every step on this host.")
@click.option("--env-id", default=None, help="Python environment for every step.")
@click.option("--node-hosts", default=None,
              help='Per-step hosts: JSON, @file or \'-\': {"<nodeId>": {"hostId": ..., "envId": ...}}.')
@click.option("--key", "client_run_key", default=None, help="Idempotency key.")
@click.option("--host-password-stdin", "ask_password", is_flag=True,
              help="Read one password from stdin: the SSH password of --host-id, or the GUI "
                   "localhost password if the server requires it.")
@click.option("--host-passwords-stdin", "ask_passwords", is_flag=True,
              help='Read SSH passwords for several hosts from stdin as one JSON line '
                   '{"<hostId>": "<password>"}.')
@_wait_options
@click.pass_obj
def workflow_run(c, workflow_id, mode, host_id, env_id, node_hosts, client_run_key,
                 ask_password, ask_passwords, wait, wait_timeout, interval, log_limit):
    """Run a workflow on the Geoweaver machine (default) or registered hosts."""
    if ask_password and ask_passwords:
        raise click.UsageError("Use --host-password-stdin or --host-passwords-stdin, not both")
    if node_hosts == "-" and (ask_password or ask_passwords):
        raise click.UsageError("stdin is used for passwords; pass --node-hosts as JSON or @file")
    nodes = json.loads(_read_json_arg(node_hosts)) if node_hosts else None
    if nodes is not None and not isinstance(nodes, dict):
        raise click.BadParameter("--node-hosts must be a JSON object")
    client = c.client()
    started = client.run_workflow(workflow_id, mode=mode, host_id=host_id, env_id=env_id,
                                  node_hosts=nodes,
                                  host_password=_host_password(ask_password),
                                  host_passwords=_host_passwords(ask_passwords),
                                  client_run_key=client_run_key)
    _finish_run(c, client, started, wait, wait_timeout, interval, log_limit)


@workflow_grp.command("delete")
@click.argument("workflow_id")
@click.option("--yes", is_flag=True, help="Confirm the delete.")
@click.pass_obj
def workflow_delete(c, workflow_id, yes):
    """Delete a workflow (its processes and run history are kept)."""
    _require_yes(yes, "a workflow")
    emit(c, c.client().delete_workflow(workflow_id))


@workflow_grp.command("runs")
@click.argument("workflow_id")
@click.option("--log-limit", type=_LOG_LIMIT, default=0, show_default=True)
@click.option("--limit", type=click.IntRange(min=1), default=None, help="Only the N most recent runs.")
@click.pass_obj
def workflow_runs(c, workflow_id, log_limit, limit):
    """Run history of a workflow, newest first, with per-step status."""
    runs = c.client().list_workflow_runs(workflow_id, log_limit=log_limit) or []
    emit(c, runs[:limit] if limit else runs)


@workflow_grp.command("skip")
@click.argument("workflow_id")
@click.argument("node_id")
@click.option("--off", is_flag=True, help="Stop skipping this step.")
@click.pass_obj
def workflow_skip(c, workflow_id, node_id, off):
    """Skip one step (node id from `workflow get`) on later runs."""
    emit(c, c.client().set_step_skipped(workflow_id, node_id, skip=not off))


@workflow_grp.command("checkpoints")
@click.argument("workflow_id")
@click.pass_obj
def workflow_checkpoints(c, workflow_id):
    """Graph and code snapshots saved at each run, newest first."""
    emit(c, c.client().list_checkpoints(workflow_id))


@workflow_grp.command("restore")
@click.argument("workflow_id")
@click.option("--run-id", required=True, help="Workflow run whose graph and step code to restore.")
@click.pass_obj
def workflow_restore(c, workflow_id, run_id):
    """Restore the workflow to the graph and code used by an earlier run."""
    emit(c, c.client().restore_checkpoint(workflow_id, run_id))


@workflow_grp.command("export")
@click.argument("workflow_id")
@click.option("--out", "out_path", default=None,
              help="Write the bundle to this file instead of stdout.")
@click.option("--force", is_flag=True, help="Replace --out if it exists.")
@click.pass_obj
def workflow_export(c, workflow_id, out_path, force):
    """The workflow plus the code of every process it uses, as JSON."""
    bundle = c.client().export_workflow(workflow_id)
    if out_path:
        path = _write_new_file(out_path, json.dumps(bundle, indent=2), force)
        emit(c, {"workflowId": workflow_id, "file": path})
    else:
        emit(c, bundle)


@workflow_grp.command("import")
@click.argument("bundle")
@click.option("--replace", is_flag=True,
              help="Replace existing processes/workflow with the same ids and different content.")
@click.pass_obj
def workflow_import(c, bundle, replace):
    """Import a bundle from `workflow export` (a file, or '-' for stdin)."""
    if bundle == "-":
        data = sys.stdin.buffer.read()
    else:
        if not os.path.isfile(bundle):
            raise click.BadParameter(f"{bundle}: no such file")
        with open(bundle, "rb") as f:
            data = f.read()
    emit(c, c.client().import_workflow(data, replace=replace))


# ------------------------------------------------------------------ hosts

@agent.group("host", cls=AgentGroup)
def host_grp():
    """Machines that run processes: SSH servers, Jupyter, Earth Engine."""


@host_grp.command("list")
@click.option("--query", "-q", default=None, help="Filter on id, name, ip or url.")
@click.pass_obj
def host_list(c, query):
    emit(c, c.client().list_hosts(query=query))


@host_grp.command("get")
@click.argument("host_id")
@click.pass_obj
def host_get(c, host_id):
    emit(c, c.client().get_host(host_id))


_HOST_TYPES = click.Choice(["ssh", "jupyter", "jupyterhub", "jupyterlab", "gee"])


@host_grp.command("create")
@click.option("--name", required=True)
@click.option("--type", "host_type", type=_HOST_TYPES, default="ssh", show_default=True)
@click.option("--ip", default=None, help="SSH: address of the machine.")
@click.option("--port", type=click.IntRange(1, 65535), default=None, help="SSH: port (22).")
@click.option("--username", default=None, help="SSH: login name.")
@click.option("--url", default=None, help="Jupyter / Earth Engine: URL.")
@click.pass_obj
def host_create(c, name, host_type, ip, port, username, url):
    """Add a host. No password is stored; runs ask for it each time."""
    emit(c, c.client().create_host(name, type=host_type, ip=ip, port=port, username=username,
                                   url=url))


@host_grp.command("update")
@click.argument("host_id")
@click.option("--name", default=None)
@click.option("--type", "host_type", type=_HOST_TYPES, default=None)
@click.option("--ip", default=None)
@click.option("--port", type=click.IntRange(1, 65535), default=None)
@click.option("--username", default=None)
@click.option("--url", default=None)
@click.pass_obj
def host_update(c, host_id, name, host_type, ip, port, username, url):
    """Edit a host (omitted fields are kept)."""
    emit(c, c.client().update_host(host_id, name=name, type=host_type, ip=ip, port=port,
                                   username=username, url=url))


@host_grp.command("delete")
@click.argument("host_id")
@click.option("--yes", is_flag=True, help="Confirm the delete.")
@click.pass_obj
def host_delete(c, host_id, yes):
    """Delete a host and its saved environments (run history is kept)."""
    _require_yes(yes, "a host")
    emit(c, c.client().delete_host(host_id))


@host_grp.command("envs")
@click.argument("host_id")
@click.option("--scan", is_flag=True, help="Look for Python environments on the host first.")
@click.option("--host-password-stdin", "ask_password", is_flag=True,
              help="Read the host's SSH password from stdin (for --scan on an SSH host).")
@click.pass_obj
def host_envs(c, host_id, scan, ask_password):
    """Python environments of a host; pass an id as --env-id to runs."""
    client = c.client()
    if scan:
        emit(c, client.scan_environments(host_id, host_password=_host_password(ask_password)))
    else:
        emit(c, client.list_environments(host_id))


# ------------------------------------------------------------------ runs

@agent.group("run", cls=AgentGroup)
def run_grp():
    """Monitor and stop runs (history ids)."""


@run_grp.command("get")
@click.argument("history_id")
@click.option("--log-limit", type=_LOG_LIMIT, default=4000, show_default=True)
@click.pass_obj
def run_get(c, history_id, log_limit):
    """Status + log of a run; workflow runs include per-step ``steps``."""
    client = c.client()
    emit(c, client.with_steps(client.get_run(history_id, log_limit=log_limit), log_limit=log_limit))


@run_grp.command("wait")
@click.argument("history_id")
@click.option("--timeout", type=_TIMEOUT, default=3600, show_default=True)
@click.option("--interval", type=_INTERVAL, default=2.0, show_default=True)
@click.option("--log-limit", type=_LOG_LIMIT, default=4000, show_default=True)
@click.pass_obj
def run_wait(c, history_id, timeout, interval, log_limit):
    """Block until the run is terminal. Exit 0 if Done, 8 otherwise, 124 on timeout."""
    client = c.client()
    run = client.wait_run(history_id, timeout=timeout, interval=interval, log_limit=log_limit)
    emit(c, client.with_steps(run, log_limit=log_limit))
    if run.get("status") != "Done":
        sys.exit(EXIT_RUN_FAILED)


@run_grp.command("logs")
@click.argument("history_id")
@click.option("--log-limit", type=_LOG_LIMIT, default=4000, show_default=True)
@click.pass_obj
def run_logs(c, history_id, log_limit):
    """Print the run's log as plain text."""
    run = c.client().get_run(history_id, log_limit=log_limit)
    emit_text(run.get("log") or "")


@run_grp.command("stop")
@click.argument("history_id")
@click.pass_obj
def run_stop(c, history_id):
    emit(c, c.client().stop_run(history_id))


@run_grp.command("list")
@click.option("--status", default=None, help="Only runs with this status, e.g. Running or Failed.")
@click.option("--limit", type=click.IntRange(1, 500), default=None, help="Default 50.")
@click.option("--log-limit", type=click.IntRange(0, 4000), default=None)
@click.pass_obj
def run_list(c, status, limit, log_limit):
    """Recent runs of every process and workflow, newest first."""
    emit(c, c.client().list_runs(limit=limit, status=status, log_limit=log_limit))


@run_grp.command("delete")
@click.argument("history_id")
@click.option("--yes", is_flag=True, help="Confirm the delete.")
@click.pass_obj
def run_delete(c, history_id, yes):
    """Delete a finished run (a workflow run also removes its step runs)."""
    _require_yes(yes, "a run")
    emit(c, c.client().delete_run(history_id))


@run_grp.command("prune")
@click.option("--status", type=click.Choice(["Failed", "Skipped"]), required=True)
@click.option("--process-id", default=None, help="Only runs of this process.")
@click.option("--yes", is_flag=True, help="Confirm the delete.")
@click.pass_obj
def run_prune(c, status, process_id, yes):
    """Delete all Failed (or Skipped) runs."""
    _require_yes(yes, f"all {status} runs")
    emit(c, c.client().delete_runs(status, process_id=process_id))


@run_grp.command("notes")
@click.argument("history_id")
@click.option("--text", default=None, help="Notes text, or '-' for stdin.")
@click.pass_obj
def run_notes(c, history_id, text):
    """Set the notes shown with a run in the Geoweaver history."""
    if text is None:
        raise click.UsageError("--text is required ('-' reads stdin)")
    emit(c, c.client().set_run_notes(history_id, sys.stdin.read() if text == "-" else text))


# ------------------------------------------------------------------ results

@agent.group("results", cls=AgentGroup)
def results_grp():
    """Browse and download files in the Geoweaver results folder."""


@results_grp.command("list")
@click.argument("path", required=False)
@click.pass_obj
def results_list(c, path):
    """One folder of results (PATH relative to the results folder)."""
    emit(c, c.client().list_results(path))


@results_grp.command("get")
@click.argument("path")
@click.option("--out", "out_path", default=".", show_default=True,
              help="Folder or file to save to; '-' writes the bytes to stdout "
                   "(`ssh host gw agent results get f.png --out - > f.png`).")
@click.option("--force", is_flag=True, help="Replace an existing file.")
@click.pass_obj
def results_get(c, path, out_path, force):
    """Download one result file."""
    client = c.client()
    if out_path == "-":
        if sys.stdout.isatty():
            raise click.UsageError("--out - writes raw file bytes; redirect it to a file "
                                   "(`> file`) instead of the terminal")
        client.copy_result(path, sys.stdout.buffer)
        sys.stdout.buffer.flush()
        return
    saved = client.download_result(path, out_path, overwrite=force)
    emit(c, {"path": path, "file": saved, "bytes": os.path.getsize(saved)})


# ------------------------------------------------------------------ guide

@agent.command("guide")
def guide_cmd():
    """Print the AI-agent playbook (Markdown)."""
    from pygeoweaver.agent import GUIDE

    click.echo(GUIDE)
