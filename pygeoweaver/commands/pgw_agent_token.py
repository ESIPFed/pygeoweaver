"""
Create or rotate the Geoweaver Agent API Bearer token.

Wraps: java -jar ~/geoweaver.jar agent-token --create
Token is written to the path configured in Geoweaver
(default: ~/gw-workspace/.agent_api_token).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

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
    )


def format_agent_token_success(result: AgentTokenResult) -> str:
    """Human-readable success message (token shown once, as Geoweaver CLI does)."""
    lines = [
        "Geoweaver Agent API token ready.",
        f"Token file: {result.token_file or default_token_file_hint()}",
    ]
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
    return "\n".join(lines)


def format_agent_token_failure(result: AgentTokenResult) -> str:
    """Human-readable failure message without guessing secrets."""
    parts = [
        "Failed to create Geoweaver Agent API token.",
        "Requires a Geoweaver jar that includes the `agent-token` command (Agent API).",
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
) -> int:
    """
    CLI entry used by Click. Returns process exit code.
    ``echo`` is click.echo (injectable for tests).
    """
    if not create:
        echo("Usage: gw agent-token --create")
        echo("Create or rotate the Geoweaver Agent API Bearer token file.")
        echo(f"Default token file: {default_token_file_hint()}")
        return 0

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
