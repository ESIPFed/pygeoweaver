"""
Create or rotate the Geoweaver Agent API Bearer token.

Two modes:
1) Local jar: java -jar ~/geoweaver.jar agent-token --create
2) Remote HTTP: POST {base}/api/v1/tokens with GUI localhost password
   (works from any machine that can reach a public or private Geoweaver URL)
"""

from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
)

# Printed by Geoweaver AgentTokenCommand
_EXPORT_RE = re.compile(
    r"^\s*export\s+GEOWEAVER_API_TOKEN=['\"]([^'\"]+)['\"]\s*$",
    re.MULTILINE,
)
_TOKEN_LINE_RE = re.compile(r"\b(gwt_[0-9a-fA-F]{32,})\b")
_FINGERPRINT_RE = re.compile(
    r"Fingerprint:\s*([0-9a-fA-F]{8,})",
    re.IGNORECASE,
)
_TOKEN_FILE_RE = re.compile(r"Token file:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class AgentTokenResult:
    """Parsed outcome of a successful agent-token create/rotate."""

    returncode: int
    stdout: str
    stderr: str
    token: Optional[str]
    fingerprint: Optional[str]
    token_file: Optional[str]
    mode: str = "local"  # local | remote

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.token)


def build_agent_token_command(
    java_bin: str,
    jar_path: str,
    *,
    create: bool = True,
) -> List[str]:
    """Build the java -jar agent-token command argv."""
    if not java_bin:
        raise ValueError("java_bin is required")
    if not jar_path:
        raise ValueError("jar_path is required")
    cmd = [java_bin, "-jar", jar_path, "agent-token"]
    if create:
        cmd.append("--create")
    return cmd


def normalize_base_url(base_url: str) -> str:
    """Ensure base URL includes scheme and ends without trailing slash noise for join."""
    if not base_url or not str(base_url).strip():
        raise ValueError("base_url is required")
    u = str(base_url).strip().rstrip("/")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("base_url must be an absolute http(s) URL including host")
    return u


def tokens_endpoint(base_url: str) -> str:
    """Build POST .../api/v1/tokens from GEOWEAVER_BASE_URL."""
    base = normalize_base_url(base_url)
    # base already includes /Geoweaver
    return urljoin(base + "/", "api/v1/tokens")


def parse_agent_token_output(stdout: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract token, fingerprint, and token file path from Geoweaver CLI stdout.

    Prefer the export line; fall back to any gwt_… token in the text.
    """
    if not stdout:
        return None, None, None

    token: Optional[str] = None
    export_match = _EXPORT_RE.search(stdout)
    if export_match:
        token = export_match.group(1).strip()
    else:
        token_match = _TOKEN_LINE_RE.search(stdout)
        if token_match:
            token = token_match.group(1)

    fingerprint = None
    fp_match = _FINGERPRINT_RE.search(stdout)
    if fp_match:
        fingerprint = fp_match.group(1)

    token_file = None
    file_match = _TOKEN_FILE_RE.search(stdout)
    if file_match:
        token_file = file_match.group(1).strip()

    return token, fingerprint, token_file


def default_token_file_hint() -> str:
    """Default Agent API token path used by Geoweaver when unset."""
    return os.path.join(os.path.expanduser("~"), "gw-workspace", ".agent_api_token")


def create_or_rotate_agent_token(
    *,
    create: bool = True,
    download_jar: bool = True,
    run_subprocess=subprocess.run,
) -> AgentTokenResult:
    """
    Download Geoweaver jar if needed, then run agent-token --create/--rotate.

    Returns parsed result. Does not print the raw token to logs beyond what the
    Geoweaver CLI already prints to stdout.
    """
    if download_jar:
        download_geoweaver_jar()

    java_bin = get_java_bin_path()
    jar_path = get_geoweaver_jar_path()
    cmd = build_agent_token_command(java_bin, jar_path, create=create)

    completed = run_subprocess(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    token, fingerprint, token_file = parse_agent_token_output(stdout)
    return AgentTokenResult(
        returncode=getattr(completed, "returncode", 1),
        stdout=stdout,
        stderr=stderr,
        token=token,
        fingerprint=fingerprint,
        token_file=token_file or default_token_file_hint(),
        mode="local",
    )


def create_agent_token_remote(
    base_url: str,
    host_password: str,
    *,
    urlopen=urllib.request.urlopen,
    timeout: float = 30.0,
) -> AgentTokenResult:
    """
    POST /api/v1/tokens with the GUI localhost password. No Bearer required.

    Security: password proves operator knowledge of the Geoweaver host secret.
    """
    if not host_password:
        return AgentTokenResult(
            returncode=2,
            stdout="",
            stderr="hostPassword is required",
            token=None,
            fingerprint=None,
            token_file=None,
            mode="remote",
        )
    endpoint = tokens_endpoint(base_url)
    payload = json.dumps({"hostPassword": host_password}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return AgentTokenResult(
            returncode=e.code,
            stdout=err_body,
            stderr=f"HTTP {e.code} from {endpoint}",
            token=None,
            fingerprint=None,
            token_file=None,
            mode="remote",
        )
    except Exception as e:  # noqa: BLE001 — surface network failures to CLI
        return AgentTokenResult(
            returncode=1,
            stdout="",
            stderr=str(e),
            token=None,
            fingerprint=None,
            token_file=None,
            mode="remote",
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return AgentTokenResult(
            returncode=1,
            stdout=body,
            stderr="Response was not JSON",
            token=None,
            fingerprint=None,
            token_file=None,
            mode="remote",
        )

    token = data.get("token")
    fingerprint = data.get("fingerprint")
    if status not in (200, 201) or not token:
        return AgentTokenResult(
            returncode=status if isinstance(status, int) else 1,
            stdout=body,
            stderr="Token missing in response",
            token=None,
            fingerprint=fingerprint,
            token_file=None,
            mode="remote",
        )
    return AgentTokenResult(
        returncode=0,
        stdout=body,
        stderr="",
        token=token,
        fingerprint=fingerprint,
        token_file=None,
        mode="remote",
    )


def format_agent_token_success(result: AgentTokenResult) -> str:
    """Human-readable success message (token shown once, as Geoweaver CLI does)."""
    lines = [
        "Geoweaver Agent API token ready.",
        f"Mode: {result.mode}",
    ]
    if result.token_file:
        lines.append(f"Token file: {result.token_file}")
    if result.fingerprint:
        lines.append(f"Fingerprint: {result.fingerprint}")
    lines.append("")
    lines.append("Export (do not paste into chat logs):")
    if result.token:
        lines.append(f"  export GEOWEAVER_API_TOKEN='{result.token}'")
    else:
        lines.append("  export GEOWEAVER_API_TOKEN='<token from output above>'")
    lines.append("")
    lines.append("Also set GEOWEAVER_BASE_URL to the reachable Geoweaver URL, for example:")
    lines.append("  export GEOWEAVER_BASE_URL='https://your-host.example/Geoweaver'")
    lines.append("  # or local: export GEOWEAVER_BASE_URL='http://127.0.0.1:8070/Geoweaver'")
    lines.append("")
    lines.append("Enable in ~/geoweaver/application.properties on the server:")
    lines.append("  geoweaver.agent.api-enabled=true")
    lines.append("  geoweaver.agent.allow-localhost-runs=true")
    lines.append("  # Prefer reverse proxy to loopback; if JVM binds public interfaces:")
    lines.append("  # geoweaver.agent.allow-non-loopback=true")
    lines.append("  server.address=127.0.0.1")
    lines.append("")
    lines.append("Remote mint from another machine (GUI localhost password):")
    lines.append("  gw agent-token --create --base-url \"$GEOWEAVER_BASE_URL\"")
    return "\n".join(lines)


def format_agent_token_failure(result: AgentTokenResult) -> str:
    """Human-readable failure message without guessing secrets."""
    parts = [
        "Failed to create Geoweaver Agent API token.",
        f"Mode: {result.mode}",
        "Local mode needs a Geoweaver jar with `agent-token`.",
        "Remote mode needs api-enabled=true and the GUI localhost password.",
        f"Exit code: {result.returncode}",
    ]
    err = (result.stderr or "").strip()
    out = (result.stdout or "").strip()
    if err:
        parts.append(f"stderr: {err[:2000]}")
    if out and not result.token:
        parts.append(f"stdout: {out[:2000]}")
    return "\n".join(parts)


def run_agent_token_cli(
    *,
    create: bool,
    echo,
    style=None,
    base_url: Optional[str] = None,
    password: Optional[str] = None,
    prompt_password=getpass.getpass,
) -> int:
    """
    CLI entry used by Click. Returns process exit code.
    ``echo`` is click.echo (injectable for tests).

    If ``base_url`` is set, uses remote POST /api/v1/tokens with localhost password.
    """
    if not create:
        echo("Usage:")
        echo("  gw agent-token --create")
        echo("  gw agent-token --create --base-url https://host/Geoweaver")
        echo("Create or rotate the Geoweaver Agent API Bearer token.")
        echo(f"Default local token file: {default_token_file_hint()}")
        echo("Remote mode requires the GUI localhost password (prompted if omitted).")
        return 0

    if base_url:
        pw = password
        if not pw:
            pw = prompt_password("Geoweaver localhost password: ")
        result = create_agent_token_remote(base_url, pw or "")
    else:
        result = create_or_rotate_agent_token(create=True)

    if result.ok:
        msg = format_agent_token_success(result)
        if style:
            echo(style(msg, fg="green"))
        else:
            echo(msg)
        return 0

    msg = format_agent_token_failure(result)
    if style:
        echo(style(msg, fg="red"))
    else:
        echo(msg)
    return 1 if result.returncode == 0 else result.returncode
