"""
Make sure a Geoweaver server is up **without disturbing one that already is**.

* Healthy server: returns immediately, no JVM is touched.
* Own Geoweaver JVM exists but not answering yet (booting): wait for it.
* Own Geoweaver JVM answers on a *different* port: refuse to start a second JVM on the
  same H2 database and report the port instead.
* Nothing running: start Geoweaver detached from the SSH session (survives logout),
  under an exclusive lock so parallel agents never boot two JVMs.
"""
import os
import subprocess
import sys
import time
import urllib.parse

from pygeoweaver.agent.client import (
    EXIT_HTTP,
    EXIT_TIMEOUT,
    EXIT_UNREACHABLE,
    AgentClient,
    AgentError,
    is_loopback_url,
)
from pygeoweaver.agent.discovery import (
    agent_child_env,
    foreign_port_error,
    is_foreign_loopback,
    discover_local_servers,
    local_base_url,
    open_private_log,
    own_geoweaver_processes,
    private_config_dir,
)
from pygeoweaver.agent.locking import start_lock

ALLOW_SECOND_ENV = "GEOWEAVER_AGENT_ALLOW_SECOND_SERVER"


def _own_jvm_on_port(port):
    port = str(port)
    if any(p == port for _pid, p in discover_local_servers(max_age=0)):
        return True
    for proc in own_geoweaver_processes():  # still booting: not listening yet
        try:
            if f"-Dserver.port={port}" in proc.cmdline():
                return True
        except Exception:
            continue
    return False


def _wait_up(client, deadline, interval=0.5, child=None):
    """
    Poll health until ``deadline``. If the starter ``child`` exited and none of this user's
    Geoweaver JVMs exists, the start failed: give up early instead of waiting it out.
    (A child also exits normally when a parallel start won, or after ~90 s of a slow cold
    boot; a JVM then exists and we keep waiting.)
    """
    exited_at = None
    while time.monotonic() < deadline:
        if client.is_up(timeout=1.0):
            return True
        if child is not None and exited_at is None and child.poll() is not None:
            exited_at = time.monotonic()
        if exited_at is not None and time.monotonic() - exited_at > 5:
            port = urllib.parse.urlsplit(client.base_url).port
            if not _own_jvm_on_port(port):
                return False
            exited_at = None
            child = None
        time.sleep(interval)
    return False


def _child_start():
    """
    Entry point of the starter child (``python -m pygeoweaver.agent.ensure``).

    The parent already verified that none of this user's Geoweaver JVMs is running, so this
    runs the normal ``gw start`` steps without its "already running" short-circuit.
    """
    from pygeoweaver.h2_utils import prepare_h2_database_for_start
    from pygeoweaver.jdk_utils import ensure_geoweaver_runtime
    from pygeoweaver.server import start_on_mac_linux, start_on_windows
    from pygeoweaver.utils import check_os, download_geoweaver_jar

    # Hold the start lock for the whole start (downloads included) and re-check under it:
    # a parallel `gw start` / `ensure` that got the lock first may already have a JVM up.
    with start_lock(timeout=3600):
        port = os.getenv("GEOWEAVER_PORT", "")
        if os.getenv(ALLOW_SECOND_ENV) == "1":
            running = any(p == port for _pid, p in discover_local_servers(max_age=0))
        else:
            running = bool(own_geoweaver_processes())
        if running:
            print("A Geoweaver JVM for this user is already running; not starting another.")
            sys.exit(0)
        ensure_geoweaver_runtime()
        download_geoweaver_jar()
        if not prepare_h2_database_for_start():
            print("Error: H2 database maintenance failed. Geoweaver was not started.")
            sys.exit(1)
        if check_os() == 3:
            start_on_windows(exit_on_finish=False)
        else:
            start_on_mac_linux(exit_on_finish=False)


def _spawn_start(port, log_path, allow_second_server=False):
    """
    Start Geoweaver from a child so its prints never pollute the caller's JSON stdout.

    ``python -m`` puts the working directory first on ``sys.path``; the agent's cwd may be
    an untrusted checkout, so the child runs in the private config dir instead.
    """
    env = agent_child_env()
    env["GEOWEAVER_PORT"] = str(port)
    if allow_second_server:
        env[ALLOW_SECOND_ENV] = "1"
    with open_private_log(log_path) as log:
        return subprocess.Popen(
            [sys.executable, "-m", "pygeoweaver.agent.ensure"],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=private_config_dir(),
            start_new_session=True,
        )


def ensure_server(base_url, timeout=240.0, start=True, allow_second_server=False,
                  explicit_url=False):
    """
    Return a status dict once ``base_url`` answers ``/api/v1/health``.

    Raises :class:`AgentError` when the server cannot be reached/started in ``timeout``.
    """
    t0 = time.monotonic()
    deadline = t0 + timeout
    client = AgentClient(base_url)

    def result(action, **extra):
        out = {"status": "up", "baseUrl": base_url, "action": action,
               "elapsedMs": int((time.monotonic() - t0) * 1000)}
        pids = [p.pid for p in own_geoweaver_processes()]
        if pids:
            out["serverPids"] = pids
        out.update(extra)
        return out

    def no_agent_api():
        return AgentError(
            "agent_api_unavailable",
            f"Something answers HTTP at {base_url} but not /api/v1/health. Needs Geoweaver "
            ">= 3.0 with geoweaver.agent.api-enabled=true (run `gw upgrade`), or a login wall "
            "is in front of it.", exit_code=EXIT_HTTP)

    foreign = is_foreign_loopback(base_url)
    state = client.probe(timeout=1.0)
    if state == "up":
        if foreign:
            if not explicit_url:
                # Chosen automatically (default port): it is someone else's server, not "ours".
                raise foreign_port_error(urllib.parse.urlsplit(base_url).port)
            return result("none", warning="this Geoweaver is not owned by your account; "
                                          "only explicitly given tokens will be sent to it")
        return result("none")
    if foreign:
        raise foreign_port_error(urllib.parse.urlsplit(base_url).port)
    if state == "no_agent_api":
        raise no_agent_api()

    if not is_loopback_url(base_url):
        raise AgentError("unreachable",
                         f"{base_url} is not answering and is not local, so it cannot be "
                         "started from here. SSH to the Geoweaver machine and run "
                         "`gw agent ensure` there.", exit_code=EXIT_UNREACHABLE)

    port = urllib.parse.urlsplit(base_url).port or 80

    with start_lock(timeout):
        state = client.probe(timeout=1.0)
        if state == "up":
            return result("waited-for-other-agent")
        if state == "no_agent_api":
            raise no_agent_api()

        running = discover_local_servers(max_age=0)
        other_ports = [] if allow_second_server else sorted(
            {p for _pid, p in running if p != str(port)})
        for other in other_ports:
            if AgentClient(local_base_url(other)).is_up(timeout=0.5):
                raise AgentError(
                    "running_on_other_port",
                    f"Your Geoweaver is already running on port {other}, not {port}. "
                    f"Use --base-url {local_base_url(other)} (or export GEOWEAVER_PORT={other}); "
                    "not starting a second JVM on the same database.",
                    exit_code=EXIT_UNREACHABLE,
                )

        if not allow_second_server and own_geoweaver_processes():
            # A JVM is booting (or wedged). Never kill it from an agent; just wait.
            if _wait_up(client, deadline):
                return result("waited-for-boot")
            raise AgentError("timeout",
                             f"A Geoweaver JVM exists but {base_url} did not answer within "
                             f"{timeout:g}s. Inspect ~/geoweaver.log; not restarting it.",
                             exit_code=EXIT_TIMEOUT)

        if not start:
            raise AgentError("unreachable", f"Geoweaver is not running at {base_url}",
                             exit_code=EXIT_UNREACHABLE)

        log_path = os.path.join(private_config_dir(), "ensure-start.log")
        child = _spawn_start(port, log_path, allow_second_server)
    # The child takes the start lock itself and holds it until its JVM is launched, so the
    # lock outlives this caller's timeout (slow JDK/jar downloads on clusters).
    if _wait_up(client, deadline, child=child):
        return result("started", startLog=log_path)
    raise AgentError("timeout",
                     f"Started Geoweaver but {base_url} did not answer yet; the start continues "
                     f"in the background. See {log_path} and ~/geoweaver.log.",
                     exit_code=EXIT_TIMEOUT)


if __name__ == "__main__":
    _child_start()
