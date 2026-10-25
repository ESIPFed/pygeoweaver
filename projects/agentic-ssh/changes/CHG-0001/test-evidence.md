# CHG-0001 test evidence (2026-10-25, macOS 15 / Python 3.14 / Geoweaver 3.0.0)

## Automated
- Round 1: `pytest test -p no:xdist` → 122 passed (98 existing + 23 new + install test).
- After C7 remediation: **131 passed** (98 existing + 32 `test/test_agent.py` + install test).

## Live, isolated Geoweaver 3.0.0 (own user.home, H2, port 18071) — not the user's server
| Acceptance | Result |
| --- | --- |
| A1 latency | `import pygeoweaver` 1.53 s → 0.20 s. `gw agent process list` 0.17 s, `workflow list` 0.14 s, `status` 0.15 s wall (health 3–5 ms). Legacy `gw list workflow`: 3.24 s. |
| A2 lifecycle | process create → run `--wait` Done (log returned); shell process; workflow `--chain` 2 steps Done; failing step → exit 8 with per-step `steps`; idempotent `--key` returns `reusedExisting: true`; `run logs`, `run stop`, `process update`, `process runs`. |
| A3 GUI real-time | Authenticated GUI session (RSA login + `/api/workspace/subscribe` + long-poll) received `process.created` (actor=agent) **190 ms** after the agent command started. |
| A4 non-interrupting | `ensure` vs user's live :8070 ×3 → `action: none` (~10 ms); PID 43077 start time unchanged. Other-port guard refuses second JVM (exit 3). |
| A5 start path | Stopped server: `ensure` started Geoweaver in 6.2 s; JVM ppid=1, own process group (survives SSH hang-up); DB = isolated home. Concurrent `ensure` calls serialized by lock (unit test: exactly one spawn). |
| A6 SSH-like | `env -i HOME PATH`, stdin=/dev/null, new session, no TTY → workflow run `--wait` correct JSON + exit 8. Real `ssh localhost` not possible (no sshd on this Mac); cluster run left to operator. |
| Errors | bad token → exit 4 JSON; unknown run → 5; unreachable → 3. |

Known server-side behavior: a stopped run reports `Failed` (Geoweaver), not `Stopped`.

## After C7 remediation (re-run live, isolated server :18071)
- `process list` 0.20 s, `workflow list` 0.21 s, `status` 0.24 s wall (ownership + discovery checks add ~40 ms); discovery without env 0.89 s with 4 local JVMs probed.
- Workflow run `--wait` Done, exit 0. Plain-HTTP remote → `insecure_transport` exit 4. `--token` argv rejected (exit 2).
- `ensure --base-url :8070` → `action: none`.

## Incident note (not caused by this change)
At 00:19 the user's live JVM 43077 was replaced by 84926. The concurrent Claude session in the
Geoweaver repo ran `cp target/geoweaver.jar ~/geoweaver.jar && kill 43077` and restarted it
(transcript evidence). This change never writes `~/geoweaver.jar`; the pytest suite mocks all start/stop.
