"""
``gw agent`` — fast, JSON-first commands for AI agents (and humans) driving a live Geoweaver.

Every command talks to the running server over ``/api/v1``: no second JVM, no direct
H2 access, and the GUI sees each change immediately. stdout is JSON (pretty on a TTY,
compact otherwise); errors are JSON on stderr with a stable exit code.
"""
import getpass
import json
import os
import sys

import click

from pygeoweaver.agent.client import (
    EXIT_ERROR,
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


def emit(ctx, data):
    pretty = ctx.pretty if ctx.pretty is not None else sys.stdout.isatty()
    click.echo(json.dumps(data, indent=2 if pretty else None, ensure_ascii=False))


def fail(err):
    click.echo(json.dumps(err.to_dict(), ensure_ascii=False), err=True)
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


def _wait_options(f):
    f = click.option("--log-limit", type=int, default=4000, show_default=True,
                     help="Max log characters returned with --wait.")(f)
    f = click.option("--interval", type=float, default=2.0, show_default=True,
                     help="Max seconds between polls with --wait.")(f)
    f = click.option("--timeout", "wait_timeout", type=float, default=3600, show_default=True,
                     help="Seconds to wait with --wait (the run keeps going after).")(f)
    f = click.option("--wait", is_flag=True,
                     help="Block until the run finishes; exit 8 unless status is Done.")(f)
    return f


@click.group("agent", cls=AgentGroup)
@click.option("--base-url", envvar=None, default=None,
              help="Geoweaver base URL incl. /Geoweaver. Default: GEOWEAVER_BASE_URL, "
                   "GEOWEAVER_PORT, your running Geoweaver JVM, then :8070.")
@click.option("--http-timeout", type=float, default=30.0, show_default=True)
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
@click.option("--timeout", type=float, default=240, show_default=True,
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
@click.option("--ttl-days", type=int, default=30, show_default=True, help="1..180")
@click.option("--revoke-others", is_flag=True, help="Revoke this server's other tokens.")
@click.pass_obj
def login_cmd(c, password_stdin, ttl_days, revoke_others):
    """
    Mint an Agent API token with the Geoweaver GUI password and store it (0600).

    The password is never accepted on the command line (it would show in `ps`).
    """
    client = c.client(sends_password=True)
    password = _read_secret("Geoweaver GUI localhost password: ", password_stdin)
    if not password:
        raise AgentError("bad_request", "Empty password", exit_code=EXIT_ERROR)
    created = client.create_token(password, ttl_days=ttl_days, revoke_others=revoke_others)
    if c.info.get("warning"):
        # Listener not owned by this account (Docker -p, sshd -R, service account): a stored
        # token would never be sent there automatically, and it must not replace the
        # loopback token of the user's own Geoweaver. Hand it over once instead.
        emit(c, {"baseUrl": client.base_url, "fingerprint": created.get("fingerprint"),
                 "expiresAt": created.get("expiresAt"), "stored": None,
                 "token": created["token"],
                 "hint": "Not stored: this port is not owned by your account. Keep the token in "
                         "a secret store and pass it as GEOWEAVER_API_TOKEN with --base-url."})
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
    """Create, edit, run and inspect processes (python | shell)."""


@process_grp.command("list")
@click.option("--name", "name_filter", default=None, help="Case-insensitive substring filter.")
@click.option("--lang", default=None)
@click.pass_obj
def process_list(c, name_filter, lang):
    items = c.client().list_processes() or []
    if name_filter:
        items = [p for p in items if name_filter.lower() in (p.get("name") or "").lower()]
    if lang:
        items = [p for p in items if (p.get("lang") or "").lower() == lang.lower()]
    emit(c, items)


@process_grp.command("get")
@click.argument("process_id")
@click.option("--code-only", is_flag=True, help="Print the raw code instead of JSON.")
@click.pass_obj
def process_get(c, process_id, code_only):
    p = c.client().get_process(process_id)
    if code_only:
        click.echo(p.get("code") or "", nl=False)
        return
    emit(c, p)


@process_grp.command("create")
@click.option("--name", required=True)
@click.option("--lang", type=click.Choice(["python", "shell"]), default="python", show_default=True)
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
@click.option("--lang", type=click.Choice(["python", "shell"]), default=None)
@click.option("--code", default=None, help="New code, or '-' for stdin.")
@click.option("--file", "file_path", default=None)
@click.option("--description", default=None)
@click.pass_obj
def process_update(c, process_id, name, lang, code, file_path, description):
    """Edit fields of a process (omitted fields are kept)."""
    body = _read_code(code, file_path)
    emit(c, c.client().update_process(process_id, name=name, code=body, lang=lang,
                                      description=description))


@process_grp.command("run")
@click.argument("process_id")
@click.option("--env-id", default=None, help="Geoweaver environment id (python binary / venv).")
@click.option("--key", "client_run_key", default=None,
              help="Idempotency key: re-sending it (same token, same server uptime) returns "
                   "the existing run instead of starting a new one.")
@click.option("--host-password-stdin", "ask_password", is_flag=True,
              help="Read the GUI localhost password from stdin (only if the server requires it).")
@_wait_options
@click.pass_obj
def process_run(c, process_id, env_id, client_run_key, ask_password, wait, wait_timeout,
                interval, log_limit):
    """Run a process on the Geoweaver host (100001)."""
    client = c.client()
    started = client.run_process(process_id, env_id=env_id,
                                 host_password=_host_password(ask_password),
                                 client_run_key=client_run_key)
    _finish_run(c, client, started, wait, wait_timeout, interval, log_limit)


@process_grp.command("runs")
@click.argument("process_id")
@click.option("--log-limit", type=int, default=0, show_default=True)
@click.option("--limit", type=int, default=None, help="Only the N most recent runs.")
@click.pass_obj
def process_runs(c, process_id, log_limit, limit):
    """Run history of a process."""
    runs = c.client().list_process_runs(process_id, log_limit=log_limit) or []
    emit(c, runs[:limit] if limit else runs)


# ------------------------------------------------------------------ workflows

@agent.group("workflow", cls=AgentGroup)
def workflow_grp():
    """Create, edit, run and inspect workflows."""


@workflow_grp.command("list")
@click.option("--name", "name_filter", default=None)
@click.pass_obj
def workflow_list(c, name_filter):
    items = c.client().list_workflows() or []
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
        ids = [p.strip() for p in chain.split(",") if p.strip()]
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
        ids = [p.strip() for p in chain.split(",") if p.strip()]
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
@click.option("--key", "client_run_key", default=None, help="Idempotency key.")
@click.option("--host-password-stdin", "ask_password", is_flag=True,
              help="Read the GUI localhost password from stdin (only if the server requires it).")
@_wait_options
@click.pass_obj
def workflow_run(c, workflow_id, mode, client_run_key, ask_password, wait, wait_timeout,
                 interval, log_limit):
    """Run a workflow on the Geoweaver host."""
    client = c.client()
    started = client.run_workflow(workflow_id, mode=mode,
                                  host_password=_host_password(ask_password),
                                  client_run_key=client_run_key)
    _finish_run(c, client, started, wait, wait_timeout, interval, log_limit)


# ------------------------------------------------------------------ runs

@agent.group("run", cls=AgentGroup)
def run_grp():
    """Monitor and stop runs (history ids)."""


@run_grp.command("get")
@click.argument("history_id")
@click.option("--log-limit", type=int, default=4000, show_default=True)
@click.pass_obj
def run_get(c, history_id, log_limit):
    """Status + log of a run; workflow runs include per-step ``steps``."""
    client = c.client()
    emit(c, client.with_steps(client.get_run(history_id, log_limit=log_limit), log_limit=log_limit))


@run_grp.command("wait")
@click.argument("history_id")
@click.option("--timeout", type=float, default=3600, show_default=True)
@click.option("--interval", type=float, default=2.0, show_default=True)
@click.option("--log-limit", type=int, default=4000, show_default=True)
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
@click.option("--log-limit", type=int, default=4000, show_default=True)
@click.pass_obj
def run_logs(c, history_id, log_limit):
    """Print the run's log as plain text."""
    run = c.client().get_run(history_id, log_limit=log_limit)
    click.echo(run.get("log") or "")


@run_grp.command("stop")
@click.argument("history_id")
@click.pass_obj
def run_stop(c, history_id):
    emit(c, c.client().stop_run(history_id))


# ------------------------------------------------------------------ guide

@agent.command("guide")
def guide_cmd():
    """Print the AI-agent playbook (Markdown)."""
    from pygeoweaver.agent import GUIDE

    click.echo(GUIDE)
