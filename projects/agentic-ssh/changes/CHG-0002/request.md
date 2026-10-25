# CHG-0002 — Security audit and hardening of `gw agent` (request, C0)

**Requester ask (2026-10-25):** "Ensure all these commands are secure and nothing is vulnerable to risks."

**Scope:** every `gw agent` command (status, ensure, capabilities, login, logout, tokens,
process *, workflow *, run *, guide) plus the code they reach: `pygeoweaver/agent/*`,
`server.py` start path, `jdk_utils.py` JDK download/extract, `utils.download_geoweaver_jar`.
Out of scope: the Geoweaver server repo (Agent API server side) — residual risks are noted, not fixed here.

## Threat model
| Actor | Capability |
| --- | --- |
| Other accounts on a shared login / OOD node | Listen on loopback ports, read world-readable files, race on shared dirs |
| Malicious content in the agent's cwd (cloned repo) | Python files picked up via `sys.path[0]` |
| Hostile server responses / run logs / process code | Prompt injection into the AI, terminal control sequences |
| Network attacker (non-loopback base URL) | Read/modify plain HTTP, redirect |
| Compromised download | Malformed archive |

Assets: Agent API token, GUI localhost password, OOD cookies, live Geoweaver availability, user files.
