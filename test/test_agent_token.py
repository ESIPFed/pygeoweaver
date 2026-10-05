"""High-coverage tests for gw agent-token (local jar + remote password mint)."""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pygeoweaver.__main__ import geoweaver
from pygeoweaver.commands import pgw_agent_token as mod
from pygeoweaver.commands.pgw_agent_token import (
    AgentTokenResult,
    build_agent_token_command,
    create_agent_token_remote,
    create_or_rotate_agent_token,
    default_token_file_hint,
    format_agent_token_failure,
    format_agent_token_success,
    normalize_base_url,
    parse_agent_token_output,
    run_agent_token_cli,
    tokens_endpoint,
)


SAMPLE_STDOUT = """
Token file: /tmp/gw-workspace/.agent_api_token
Fingerprint: a1b2c3d4e5f6

Export (do not paste into chat logs):
  export GEOWEAVER_API_TOKEN='gwt_0123456789abcdef0123456789abcdef'

Enable in ~/geoweaver/application.properties:
  geoweaver.agent.api-enabled=true
"""


def test_build_agent_token_command_create():
    cmd = build_agent_token_command("/usr/bin/java", "/home/u/geoweaver.jar", create=True)
    assert cmd == ["/usr/bin/java", "-jar", "/home/u/geoweaver.jar", "agent-token", "--create"]


def test_build_agent_token_command_usage_only():
    cmd = build_agent_token_command("java", "geoweaver.jar", create=False)
    assert cmd == ["java", "-jar", "geoweaver.jar", "agent-token"]
    assert "--create" not in cmd


def test_build_agent_token_command_rejects_empty():
    with pytest.raises(ValueError):
        build_agent_token_command("", "jar.jar")
    with pytest.raises(ValueError):
        build_agent_token_command("java", "")


def test_normalize_and_tokens_endpoint():
    assert normalize_base_url("https://gw.example.org/Geoweaver/") == "https://gw.example.org/Geoweaver"
    assert tokens_endpoint("https://gw.example.org/Geoweaver") == (
        "https://gw.example.org/Geoweaver/api/v1/tokens"
    )
    with pytest.raises(ValueError):
        normalize_base_url("not-a-url")
    with pytest.raises(ValueError):
        normalize_base_url("")


def test_parse_agent_token_output_from_export_line():
    token, fp, path = parse_agent_token_output(SAMPLE_STDOUT)
    assert token == "gwt_0123456789abcdef0123456789abcdef"
    assert fp == "a1b2c3d4e5f6"
    assert path.endswith(".agent_api_token")


def test_parse_agent_token_output_fallback_token_without_export():
    raw = "Fingerprint: deadbeefcafe\nsome gwt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa token\n"
    token, fp, path = parse_agent_token_output(raw)
    assert token.startswith("gwt_")
    assert fp == "deadbeefcafe"
    assert path is None


def test_parse_agent_token_output_empty():
    assert parse_agent_token_output("") == (None, None, None)
    assert parse_agent_token_output(None) == (None, None, None)


def test_default_token_file_hint_under_home():
    hint = default_token_file_hint()
    assert hint.endswith("gw-workspace/.agent_api_token") or "gw-workspace" in hint


def test_create_or_rotate_success(monkeypatch):
    monkeypatch.setattr(mod, "download_geoweaver_jar", lambda: None)
    monkeypatch.setattr(mod, "get_java_bin_path", lambda: "java")
    monkeypatch.setattr(mod, "get_geoweaver_jar_path", lambda: "/tmp/geoweaver.jar")

    def fake_run(cmd, capture_output=True, text=True, check=False):
        assert cmd[-1] == "--create"
        return SimpleNamespace(returncode=0, stdout=SAMPLE_STDOUT, stderr="")

    result = create_or_rotate_agent_token(create=True, download_jar=True, run_subprocess=fake_run)
    assert result.ok
    assert result.token.startswith("gwt_")
    assert result.fingerprint == "a1b2c3d4e5f6"
    assert result.returncode == 0
    assert result.mode == "local"


def test_create_or_rotate_skips_download_when_disabled(monkeypatch):
    called = {"dl": False}

    def boom():
        called["dl"] = True
        raise AssertionError("should not download")

    monkeypatch.setattr(mod, "download_geoweaver_jar", boom)
    monkeypatch.setattr(mod, "get_java_bin_path", lambda: "java")
    monkeypatch.setattr(mod, "get_geoweaver_jar_path", lambda: "/tmp/geoweaver.jar")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=SAMPLE_STDOUT, stderr="")

    result = create_or_rotate_agent_token(download_jar=False, run_subprocess=fake_run)
    assert called["dl"] is False
    assert result.ok


def test_create_or_rotate_failure_no_token(monkeypatch):
    monkeypatch.setattr(mod, "download_geoweaver_jar", lambda: None)
    monkeypatch.setattr(mod, "get_java_bin_path", lambda: "java")
    monkeypatch.setattr(mod, "get_geoweaver_jar_path", lambda: "/tmp/geoweaver.jar")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="Unknown command agent-token",
            stderr="error",
        )

    result = create_or_rotate_agent_token(run_subprocess=fake_run)
    assert not result.ok
    assert result.returncode == 1
    assert result.token is None


def test_create_agent_token_remote_success():
    body = json.dumps(
        {
            "token": "gwt_0123456789abcdef0123456789abcdef",
            "fingerprint": "abcd1234",
            "previousTokenInvalidated": False,
        }
    ).encode()

    class FakeResp:
        status = 201

        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=30.0):
        assert req.get_method() == "POST"
        assert req.full_url.endswith("/api/v1/tokens")
        return FakeResp()

    result = create_agent_token_remote(
        "https://gw.example.org/Geoweaver", "secret-pw", urlopen=fake_urlopen
    )
    assert result.ok
    assert result.mode == "remote"
    assert result.token.startswith("gwt_")
    assert result.fingerprint == "abcd1234"


def test_create_agent_token_remote_http_error():
    import urllib.error

    def boom(req, timeout=30.0):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", hdrs=None, fp=io.BytesIO(b'{"error":"forbidden"}')
        )

    result = create_agent_token_remote("https://gw.example.org/Geoweaver", "bad", urlopen=boom)
    assert not result.ok
    assert result.returncode == 403


def test_create_agent_token_remote_missing_password():
    result = create_agent_token_remote("https://gw.example.org/Geoweaver", "")
    assert not result.ok
    assert result.returncode == 2


def test_format_success_and_failure():
    ok = AgentTokenResult(
        returncode=0,
        stdout=SAMPLE_STDOUT,
        stderr="",
        token="gwt_0123456789abcdef0123456789abcdef",
        fingerprint="a1b2c3d4e5f6",
        token_file="/tmp/.agent_api_token",
        mode="local",
    )
    text = format_agent_token_success(ok)
    assert "GEOWEAVER_API_TOKEN=" in text
    assert "GEOWEAVER_BASE_URL=" in text
    assert "a1b2c3d4e5f6" in text
    assert "api-enabled=true" in text
    assert "allow-non-loopback" in text
    assert "--base-url" in text

    ok_no_token = AgentTokenResult(0, "", "", None, None, None)
    text2 = format_agent_token_success(ok_no_token)
    assert "<token from output above>" in text2

    bad = AgentTokenResult(2, "out", "err-details", None, None, None, mode="remote")
    fail = format_agent_token_failure(bad)
    assert "Failed" in fail
    assert "Exit code: 2" in fail
    assert "err-details" in fail
    assert "out" in fail
    assert "Remote mode" in fail


def test_run_agent_token_cli_usage():
    lines = []
    code = run_agent_token_cli(create=False, echo=lines.append)
    assert code == 0
    assert any("Usage" in x for x in lines)
    assert any("agent-token --create" in x for x in lines)
    assert any("base-url" in x for x in lines)


def test_run_agent_token_cli_success(monkeypatch):
    monkeypatch.setattr(
        mod,
        "create_or_rotate_agent_token",
        lambda create=True: AgentTokenResult(
            0, SAMPLE_STDOUT, "", "gwt_0123456789abcdef0123456789abcdef", "fp12", "/t"
        ),
    )
    lines = []
    styles = []

    def style(msg, fg=None):
        styles.append(fg)
        return msg

    code = run_agent_token_cli(create=True, echo=lines.append, style=style)
    assert code == 0
    assert styles == ["green"]
    assert any("GEOWEAVER_API_TOKEN" in x for x in lines)


def test_run_agent_token_cli_remote_prompts(monkeypatch):
    seen = {}

    def fake_remote(base_url, host_password, **kwargs):
        seen["base"] = base_url
        seen["pw"] = host_password
        return AgentTokenResult(
            0, "{}", "", "gwt_0123456789abcdef0123456789abcdef", "fp", None, mode="remote"
        )

    monkeypatch.setattr(mod, "create_agent_token_remote", fake_remote)
    lines = []
    code = run_agent_token_cli(
        create=True,
        echo=lines.append,
        base_url="https://gw.example.org/Geoweaver",
        password=None,
        prompt_password=lambda msg: "typed-secret",
    )
    assert code == 0
    assert seen["pw"] == "typed-secret"
    assert "Geoweaver" in seen["base"]


def test_run_agent_token_cli_failure(monkeypatch):
    monkeypatch.setattr(
        mod,
        "create_or_rotate_agent_token",
        lambda create=True: AgentTokenResult(3, "", "boom", None, None, None),
    )
    lines = []
    code = run_agent_token_cli(create=True, echo=lines.append, style=lambda m, fg=None: m)
    assert code == 3
    assert any("Failed" in x for x in lines)


def test_run_agent_token_cli_failure_zero_exit_without_token(monkeypatch):
    monkeypatch.setattr(
        mod,
        "create_or_rotate_agent_token",
        lambda create=True: AgentTokenResult(0, "no token here", "", None, None, None),
    )
    lines = []
    code = run_agent_token_cli(create=True, echo=lines.append)
    assert code == 1


def test_click_agent_token_usage():
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["agent-token"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "agent-token" in result.output


def test_click_agent_token_create(monkeypatch):
    monkeypatch.setattr(
        "pygeoweaver.__main__.run_agent_token_cli",
        lambda create, echo, style=None, base_url=None, password=None: 0 if create else 1,
    )
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["agent-token", "--create"])
    assert result.exit_code == 0


def test_click_agent_token_remote(monkeypatch):
    seen = {}

    def fake(create, echo, style=None, base_url=None, password=None):
        seen["base_url"] = base_url
        seen["password"] = password
        seen["create"] = create
        return 0

    monkeypatch.setattr("pygeoweaver.__main__.run_agent_token_cli", fake)
    runner = CliRunner()
    result = runner.invoke(
        geoweaver,
        [
            "agent-token",
            "--create",
            "--base-url",
            "https://gw.example.org/Geoweaver",
            "--password",
            "pw",
        ],
    )
    assert result.exit_code == 0
    assert seen["base_url"] == "https://gw.example.org/Geoweaver"
    assert seen["password"] == "pw"


def test_click_agent_token_rotate(monkeypatch):
    seen = {}

    def fake(create, echo, style=None, base_url=None, password=None):
        seen["create"] = create
        return 0

    monkeypatch.setattr("pygeoweaver.__main__.run_agent_token_cli", fake)
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["agent-token", "--rotate"])
    assert result.exit_code == 0
    assert seen["create"] is True


def test_click_agent_token_create_failure_exits(monkeypatch):
    monkeypatch.setattr(
        "pygeoweaver.__main__.run_agent_token_cli",
        lambda create, echo, style=None, base_url=None, password=None: 9,
    )
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["agent-token", "--create"])
    assert result.exit_code == 9


def test_agent_token_result_ok_property():
    assert AgentTokenResult(0, "", "", "gwt_x", None, None).ok
    assert not AgentTokenResult(0, "", "", None, None, None).ok
    assert not AgentTokenResult(1, "", "", "gwt_x", None, None).ok
