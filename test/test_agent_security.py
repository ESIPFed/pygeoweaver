"""Security regression tests for `gw agent` (CHG-0002, findings SEC-001..SEC-013)."""
import io
import json
import os
import socket
import stat
import tarfile
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pygeoweaver import jdk_utils
from pygeoweaver.agent import cli as cli_mod
from pygeoweaver.agent import client as client_mod
from pygeoweaver.agent import discovery, ensure, locking
from pygeoweaver.agent.cli import agent
from pygeoweaver.agent.client import AgentClient, AgentError

from test.test_agent import TOKEN, _Stub, isolated_env, server  # noqa: F401  (fixtures)


def _cli(*args, input=None, env=None):
    return CliRunner().invoke(agent, list(args), input=input, env=env or {})


# ----------------------------------------------------------------------------- SEC-013 URLs

@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://127.0.0.1/Geoweaver",
    "http://user:secret@127.0.0.1:8070/Geoweaver",
    "http://127.0.0.1:8070/Geoweaver?x=1",
    "http://127.0.0.1:99999/Geoweaver",
    "http:///Geoweaver",
])
def test_bad_base_urls_rejected(url):
    with pytest.raises(AgentError) as e:
        AgentClient(url)
    assert e.value.exit_code == client_mod.EXIT_USAGE
    assert "secret" not in e.value.message


def test_geoweaver_port_cannot_point_off_host(monkeypatch):
    monkeypatch.setenv("GEOWEAVER_PORT", "80@evil.example:443")
    with pytest.raises(AgentError) as e:
        discovery.resolve_base_url()
    assert e.value.error == "bad_port"


def test_cookie_jar_never_sent_over_plain_http(tmp_path, monkeypatch):
    jar = tmp_path / "cookies.txt"
    jar.write_text("# Netscape HTTP Cookie File\nood.example\tFALSE\t/\tFALSE\t0\tsid\tabc\n")
    c = AgentClient("http://ood.example/Geoweaver", cookie_jar=str(jar))
    with pytest.raises(AgentError) as e:
        c.health()
    assert e.value.error == "insecure_transport"


# ----------------------------------------------------------------------------- SEC-008 ids

@pytest.mark.parametrize("bad", ["../tokens", "a/b", "..", "x?y", "%2e%2e", "", "a" * 200])
def test_ids_cannot_escape_their_path_segment(server, bad):
    c = AgentClient(server, token=TOKEN)
    _Stub.calls.clear()
    with pytest.raises(AgentError) as e:
        c.get_process(bad)
    assert e.value.error == "bad_request" and not _Stub.calls


def test_cli_bad_id_is_usage_error(server):
    r = _cli("--base-url", server, "run", "stop", "../../tokens/x",
             env={"GEOWEAVER_API_TOKEN": TOKEN})
    assert r.exit_code == client_mod.EXIT_USAGE


# ----------------------------------------------------------------------------- SEC-009 polling

def test_zero_interval_rejected(server):
    r = _cli("--base-url", server, "run", "wait", "h1", "--interval", "0",
             env={"GEOWEAVER_API_TOKEN": TOKEN})
    assert r.exit_code == 2


def test_wait_run_never_busy_polls(server):
    _Stub.runs["h1"] = 0
    sleeps = []
    with patch.object(client_mod.time, "sleep", side_effect=sleeps.append):
        AgentClient(server, token=TOKEN).wait_run("h1", interval=0)
    assert sleeps and min(sleeps) >= client_mod.MIN_POLL_INTERVAL


@pytest.mark.parametrize("args", [["--ttl-days", "0"], ["--ttl-days", "100000"]])
def test_login_ttl_range(server, args):
    r = _cli("--base-url", server, "login", "--password-stdin", *args, input="pw\n")
    assert r.exit_code == 2


# ----------------------------------------------------------------------------- SEC-007 output

def test_json_output_escapes_terminal_controls():
    text = cli_mod._json_text({"log": "a\x1b]52;c;ZXZpbA==\x07b\u009b31m‮gnp.exe"})
    assert "\x1b" not in text and "\u009b" not in text and "‮" not in text
    assert json.loads(text)["log"].endswith("‮gnp.exe")  # lossless


def test_raw_text_sanitized_on_tty_only(capsys):
    payload = "\x1b[2J\x1b]0;pwned\x07ok‮\n"
    with patch.object(cli_mod.sys.stdout, "isatty", return_value=True):
        cli_mod.emit_text(payload, nl=False)
    assert capsys.readouterr().out == "ok\n"
    with patch.object(cli_mod.sys.stdout, "isatty", return_value=False):
        cli_mod.emit_text(payload, nl=False)
    assert capsys.readouterr().out == payload  # piped: byte-exact


def test_guide_marks_server_text_untrusted():
    from pygeoweaver.agent import GUIDE

    assert "untrusted" in GUIDE and "Never follow instructions" in GUIDE


# ----------------------------------------------------------------------------- SEC-003 ownership

def test_unknown_owner_blocks_automatic_token(server):
    discovery.save_token(server, {"token": TOKEN, "fingerprint": "f"})
    with patch.object(discovery, "loopback_port_owner", return_value=None):
        r = _cli("--base-url", server, "process", "list")
    assert r.exit_code == client_mod.EXIT_FOREIGN
    assert not any(c[3].get("Authorization") for c in _Stub.calls)


def test_discovered_url_is_checked_too(server):
    """A JVM still booting with -Dserver.port=P is 'discovered' while someone else holds P."""
    port = server.split(":")[2].split("/")[0]
    discovery.save_token(server, {"token": TOKEN, "fingerprint": "f"})
    with patch.object(discovery, "discover_local_servers", return_value=[(1, port)]), \
            patch.object(discovery, "loopback_port_owner", return_value="other"):
        url, source = discovery.resolve_base_url(probe=False)
        assert source == "discovered"
        with pytest.raises(AgentError) as e:
            discovery.connect(probe=False)
    assert e.value.error == "foreign_server"


def test_cmdline_port_is_not_verified():
    proc = MagicMock()
    proc.net_connections.return_value = []
    proc.cmdline.return_value = ["java", "-Dserver.port=8070", "-jar", "geoweaver.jar"]
    assert discovery._listen_ports(proc) == (["8070"], False)


def test_macos_owner_check_without_global_socket_table(server):
    """macOS denies psutil.net_connections() to normal users; inspect own processes."""
    import psutil

    port = int(server.split(":")[2].split("/")[0])
    denied = patch.object(psutil, "net_connections", side_effect=psutil.AccessDenied())
    with denied, patch.object(discovery, "_verified_own_ports", return_value=frozenset()):
        assert discovery.loopback_port_owner(port) == "me"  # the stub server is this process
        with patch.object(discovery, "_own_process_listens", return_value=False):
            assert discovery.loopback_port_owner(port) == "other"
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        free_port = free.getsockname()[1]
        free.close()
        assert discovery.loopback_port_owner(free_port) == "none"


def test_localhost_is_pinned_to_ipv4():
    """SEC-015: `localhost` may resolve to ::1 first, where another account could listen."""
    assert AgentClient("http://localhost:8070/Geoweaver").base_url == \
        "http://127.0.0.1:8070/Geoweaver"
    assert discovery.resolve_base_url("http://LOCALHOST:9/Geoweaver")[0] == \
        "http://127.0.0.1:9/Geoweaver"


def test_ipv6_listener_of_another_account_is_foreign(monkeypatch):
    import psutil

    addr = lambda ip: MagicMock(ip=ip, port=7777)  # noqa: E731
    conns = [MagicMock(status="LISTEN", laddr=addr("127.0.0.1"), pid=os.getpid()),
             MagicMock(status="LISTEN", laddr=addr("::1"), pid=None)]
    with patch.object(psutil, "net_connections", return_value=conns), \
            patch.object(discovery, "_verified_own_ports", return_value=frozenset()):
        assert discovery.loopback_port_owner(7777, "127.0.0.1") == "me"
        assert discovery.loopback_port_owner(7777, "::1") == "other"
    conns[0].laddr = addr("::")  # wildcard: reachable from both
    conns[1].laddr = addr("127.0.0.1")
    with patch.object(psutil, "net_connections", return_value=conns), \
            patch.object(discovery, "_verified_own_ports", return_value=frozenset()):
        assert discovery.loopback_port_owner(7777, "127.0.0.1") == "other"


def test_windows_listener_of_another_user_is_foreign(monkeypatch):
    """SEC-016: Windows reports pids for every user's sockets; compare user names."""
    import psutil

    monkeypatch.delattr(discovery.os, "getuid")
    conn = MagicMock(status="LISTEN", laddr=MagicMock(ip="0.0.0.0", port=7778), pid=4321)
    other = MagicMock()
    other.username.return_value = "HOST\\bob"
    me = MagicMock()
    me.username.return_value = "HOST\\alice"
    procs = {4321: other, None: me}
    with patch.object(psutil, "net_connections", return_value=[conn]), \
            patch.object(psutil, "Process", side_effect=lambda pid=None: procs[pid]), \
            patch.object(discovery, "_verified_own_ports", return_value=frozenset()):
        assert discovery.loopback_port_owner(7778) == "other"
        other.username.return_value = "HOST\\alice"
        assert discovery.loopback_port_owner(7778) == "me"
        other.username.side_effect = psutil.AccessDenied()
        assert discovery.loopback_port_owner(7778) == "other"


def test_other_loopback_address_is_not_verified():
    """SEC-021: our JVM on 127.0.0.2:P does not make 127.0.0.1:P ours."""
    assert not discovery._reaches(MagicMock(ip="127.0.0.2", port=5), "5", "127.0.0.1")
    assert discovery._reaches(MagicMock(ip="0.0.0.0", port=5), "5", "127.0.0.1")


def test_log_not_truncated_before_owner_check(tmp_path):
    """SEC-022: a log owned by someone else is rejected without being truncated."""
    log = tmp_path / "x.log"
    log.write_text("keep")
    with patch.object(discovery.os, "getuid", return_value=os.getuid() + 1):
        with pytest.raises(AgentError):
            discovery.open_private_log(str(log), "wb")
    assert log.read_text() == "keep"
    with discovery.open_private_log(str(log), "wb") as f:
        f.write(b"new")
    assert log.read_text() == "new"


def test_symlinked_log_owned_by_me_is_allowed(tmp_path):
    """SEC-018: ~/geoweaver.log -> /scratch/... must keep working."""
    real = tmp_path / "scratch.log"
    link = tmp_path / "geoweaver.log"
    os.symlink(real, link)
    with discovery.open_private_log(str(link), "wb") as f:
        f.write(b"x")
    assert real.read_bytes() == b"x" and stat.S_IMODE(real.stat().st_mode) == 0o600


def test_nothing_listening_is_not_foreign():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert not discovery.is_foreign_loopback(f"http://127.0.0.1:{port}/Geoweaver")


# ----------------------------------------------------------------------------- SEC-010 store

def test_config_dir_mode_tightened(tmp_path, monkeypatch):
    d = tmp_path / "cfg2"
    d.mkdir(mode=0o777)
    os.chmod(d, 0o777)
    monkeypatch.setenv("GEOWEAVER_AGENT_CONFIG_DIR", str(d))
    discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": "t"})
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE((d / "agent-tokens.json").stat().st_mode) == 0o600


def test_config_dir_owned_by_someone_else_refused(tmp_path, monkeypatch):
    d = tmp_path / "cfg3"
    d.mkdir()
    monkeypatch.setenv("GEOWEAVER_AGENT_CONFIG_DIR", str(d))
    with patch.object(discovery.os, "getuid", return_value=os.getuid() + 1):
        with pytest.raises(AgentError) as e:
            discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": "t"})
    assert e.value.error == "insecure_config_dir"


def test_store_readable_by_others_is_fixed_and_foreign_store_ignored():
    discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": "t"})
    path = discovery._store_path()
    os.chmod(path, 0o644)
    assert discovery.resolve_token("http://127.0.0.1:1/Geoweaver")[0] == "t"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with patch.object(discovery.os, "getuid", return_value=os.getuid() + 1):
        assert discovery.resolve_token("http://127.0.0.1:1/Geoweaver") == (None, None)


def test_store_write_does_not_follow_planted_symlink(tmp_path):
    discovery.save_token("http://127.0.0.1:1/Geoweaver", {"token": "t"})
    victim = tmp_path / "victim"
    victim.write_text("keep")
    with patch.object(discovery.os, "getpid", return_value=4242), \
            patch.object(discovery.os, "urandom", return_value=b"\0\0\0\0"):
        os.symlink(victim, discovery._store_path() + ".4242.00000000.tmp")
        with pytest.raises(OSError):
            discovery.save_token("http://127.0.0.1:2/Geoweaver", {"token": "u"})
    assert victim.read_text() == "keep"


# ----------------------------------------------------------------------------- SEC-001/2/5/11

def test_child_env_drops_agent_secrets(monkeypatch):
    monkeypatch.setenv("GEOWEAVER_API_TOKEN", "secret")
    monkeypatch.setenv("GEOWEAVER_OOD_COOKIE_JAR", "/x")
    monkeypatch.setenv("GEOWEAVER_AGENT_ALLOW_SECOND_SERVER", "1")
    monkeypatch.setenv("AWS_PROFILE", "science")
    env = discovery.agent_child_env()
    assert "GEOWEAVER_API_TOKEN" not in env and "GEOWEAVER_OOD_COOKIE_JAR" not in env
    assert env["GEOWEAVER_AGENT_CONFIG_DIR"] and env["AWS_PROFILE"] == "science"
    jvm = discovery.agent_child_env(jvm=True)
    assert not any(k.startswith("GEOWEAVER_AGENT_") for k in jvm)


def test_start_child_runs_outside_agent_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "untrusted"
    (repo / "pygeoweaver").mkdir(parents=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GEOWEAVER_API_TOKEN", "secret")
    with patch.object(ensure.subprocess, "Popen") as popen:
        ensure._spawn_start(18099, os.path.join(discovery.private_config_dir(), "s.log"))
    kw = popen.call_args.kwargs
    assert kw["cwd"] == discovery.config_dir() and kw["cwd"] != str(repo)
    assert "GEOWEAVER_API_TOKEN" not in kw["env"]
    log = os.path.join(discovery.config_dir(), "s.log")
    assert stat.S_IMODE(os.stat(log).st_mode) == 0o600


def test_start_child_ignores_planted_module_in_cwd(tmp_path):
    """End to end with `python -m` (as `_spawn_start` runs it): modules resolve from the
    private config dir, not from the agent's cwd."""
    import subprocess
    import sys

    repo = tmp_path / "untrusted"
    (repo / "pygeoweaver").mkdir(parents=True)
    marker = tmp_path / "pwned"
    (repo / "pygeoweaver" / "__init__.py").write_text(f"open({str(marker)!r}, 'w').close()\n")
    cmd = [sys.executable, "-m", "pygeoweaver.agent.client"]  # importable, no side effects
    with patch.object(ensure.subprocess, "Popen") as popen:
        ensure._spawn_start(18099, os.path.join(discovery.private_config_dir(), "s.log"))
    subprocess.run(cmd, cwd=popen.call_args.kwargs["cwd"], capture_output=True)
    assert not marker.exists()
    subprocess.run(cmd, cwd=repo, capture_output=True)
    assert marker.exists()  # the hazard is real when cwd is the untrusted repo


def test_jvm_starts_in_home_with_private_log_and_clean_env(tmp_path, monkeypatch):
    from pygeoweaver import server as server_mod

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GEOWEAVER_API_TOKEN", "secret")
    monkeypatch.chdir(tmp_path)
    ok = MagicMock(status_code=200)
    with patch.object(server_mod, "check_java_exists", return_value="/usr/bin/java"), \
            patch.object(server_mod, "get_safe_datasource_url_for_start", return_value=None), \
            patch.object(server_mod.subprocess, "Popen") as popen, \
            patch.object(server_mod.requests, "get", return_value=ok), \
            patch.object(server_mod, "is_geoweaver_http_ready", return_value=True), \
            patch.object(server_mod.time, "sleep"):
        server_mod.start_on_mac_linux(exit_on_finish=False)
    kw = popen.call_args.kwargs
    assert kw["cwd"] == str(tmp_path)
    assert "GEOWEAVER_API_TOKEN" not in kw["env"]
    assert stat.S_IMODE((tmp_path / "geoweaver.log").stat().st_mode) == 0o600


# ----------------------------------------------------------------------------- SEC-012 lock

def test_lock_release_never_removes_a_successor_lock(tmp_path):
    """SEC-020: if our lock was broken and someone else holds the path, leave theirs."""
    base = str(tmp_path / "y.lock")
    with locking._excl_lock(base, 1, "t"):
        os.unlink(base + ".excl")
        with open(base + ".excl", "w") as f:
            f.write("successor")
    assert open(base + ".excl").read() == "successor"


def test_stale_lock_break_never_removes_a_fresh_lock(tmp_path):
    path = str(tmp_path / "x.lock.excl")
    stale = f"999999999@{socket.gethostname()}#aa"
    with open(path, "w") as f:
        f.write(stale)
    assert locking._excl_stale(path) == stale
    # Another waiter already replaced it with a fresh lock (Linux may even reuse the inode).
    os.unlink(path)
    with open(path, "w") as f:
        f.write(f"{os.getpid()}@{socket.gethostname()}#bb")
    assert locking._excl_stale(path) is None  # holder alive
    locking._break_stale(path, stale)
    assert os.path.exists(path)
    with open(path) as f:
        assert f.read().endswith("#bb")
    locking._break_stale(path, locking._read_lock(path))
    assert not os.path.exists(path)


# ----------------------------------------------------------------------------- SEC-006 downloads

def _tar_with(member_name, tmp_path, linkname=None):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(member_name)
        if linkname:
            info.type, info.linkname = tarfile.SYMTYPE, linkname
            tar.addfile(info)
        else:
            data = b"x"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return archive


@pytest.mark.parametrize("use_filter", [True, False])
@pytest.mark.parametrize("member,link", [("../escape.txt", None), ("/abs.txt", None),
                                         ("jdk/evil", "../../../etc")])
def test_tar_extraction_blocks_traversal(tmp_path, use_filter, member, link):
    archive = _tar_with(member, tmp_path, link)
    dest = tmp_path / "dest"
    with tarfile.open(archive, "r:gz") as tar:
        if use_filter:
            try:  # the "data" filter raises, or re-roots absolute names inside dest
                jdk_utils._safe_extractall(tar, str(dest))
            except tarfile.TarError:
                pass
        else:
            with patch.object(jdk_utils, "tarfile", wraps=tarfile) as tf:
                del tf.data_filter
                with pytest.raises(RuntimeError):
                    jdk_utils._safe_extractall(tar, str(dest))
    # Nothing but the archive and dest may exist next to dest.
    assert sorted(p.name for p in tmp_path.iterdir()) in (["evil.tar.gz"],
                                                          ["dest", "evil.tar.gz"])
    if dest.exists():
        for root, dirs, files in os.walk(dest):
            for name in files + dirs:
                full = os.path.realpath(os.path.join(root, name))
                assert full.startswith(str(dest.resolve()))


@pytest.mark.parametrize("use_filter", [True, False])
def test_tar_symlink_chain_cannot_escape(tmp_path, use_filter):
    """SEC-017: d -> ., d/e -> .., e/pwned.txt passes a naive realpath check."""
    archive = tmp_path / "chain.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, link in [("d", "."), ("d/e", "..")]:
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, link
            tar.addfile(info)
        info = tarfile.TarInfo("e/pwned.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    dest = tmp_path / "dest"
    with tarfile.open(archive, "r:gz") as tar:
        if use_filter:
            with pytest.raises(tarfile.TarError):
                jdk_utils._safe_extractall(tar, str(dest))
        else:
            with patch.object(jdk_utils, "tarfile", wraps=tarfile) as tf:
                del tf.data_filter
                with pytest.raises(RuntimeError):
                    jdk_utils._safe_extractall(tar, str(dest))
    assert not (tmp_path / "pwned.txt").exists()


def test_fallback_extractor_keeps_internal_relative_links(tmp_path):
    """Temurin archives contain links like legal/a/X -> ../b/X; they must still extract."""
    archive = tmp_path / "jdk.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("jdk/legal/b/X")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
        info = tarfile.TarInfo("jdk/legal/a/X")
        info.type, info.linkname = tarfile.SYMTYPE, "../b/X"
        tar.addfile(info)
    dest = tmp_path / "dest"
    with tarfile.open(archive, "r:gz") as tar, \
            patch.object(jdk_utils, "tarfile", wraps=tarfile) as tf:
        del tf.data_filter
        jdk_utils._safe_extractall(tar, str(dest))
    assert (dest / "jdk/legal/a/X").read_text() == "x"


def test_download_rejects_bad_digest_and_http(tmp_path):
    target = tmp_path / "jdk.tar.gz"

    def fake_fetch(url, dest):
        with open(dest, "wb") as f:
            f.write(b"tampered")

    with patch.object(jdk_utils, "_fetch", side_effect=fake_fetch):
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            jdk_utils.download_file("https://x/jdk.tar.gz", str(target), sha256="0" * 64)
    assert not target.exists() and not list(tmp_path.glob("*.part"))
    with pytest.raises(RuntimeError, match="non-https"):
        jdk_utils._fetch("http://x/jdk.tar.gz", str(target))


@pytest.mark.skipif(os.getenv("PYGEOWEAVER_NETWORK_TESTS") != "1",
                    reason="set PYGEOWEAVER_NETWORK_TESTS=1 (CI does)")
def test_pinned_digests_match_publishers():
    import urllib.request

    from pygeoweaver import h2_utils

    def published(url):
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode().split()[0].lower()

    base = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/"
    for name, digest in jdk_utils.TEMURIN_SHA256.items():
        assert published(base + name + ".sha256.txt") == digest, name
    for ver, digest in h2_utils.H2_JAR_SHA256.items():
        url = f"https://repo1.maven.org/maven2/com/h2database/h2/{ver}/h2-{ver}.jar.sha256"
        assert published(url) == digest, ver


def test_download_has_an_overall_deadline():
    out = io.BytesIO()
    ticks = iter([0, 0, 5000])
    with patch.object(jdk_utils.time, "monotonic", side_effect=lambda: next(ticks)):
        with pytest.raises(RuntimeError, match="longer than"):
            jdk_utils.copy_with_deadline([b"a", b"b", b"c"], out, "https://x", deadline_s=10)


def test_every_managed_jdk_archive_has_a_pinned_digest():
    from pygeoweaver.constants import GEOWEAVER_MANAGED_JDK17_VERSION as v

    ver = v.replace("-", "_")
    for arch, ext in [("jdk_x64_mac_hotspot", "tar.gz"), ("jdk_aarch64_mac_hotspot", "tar.gz"),
                      ("jdk_x64_linux_hotspot", "tar.gz"), ("jdk_aarch64_linux_hotspot", "tar.gz"),
                      ("jdk_x64_windows_hotspot", "zip"), ("jdk_x86-32_windows_hotspot", "zip")]:
        url = f"https://github.com/adoptium/x/OpenJDK17U-{arch}_{ver}.{ext}"
        assert len(jdk_utils.pinned_jdk_sha256(url)) == 64
    with pytest.raises(RuntimeError):
        jdk_utils.pinned_jdk_sha256("https://x/OpenJDK17U-unknown.tar.gz")
