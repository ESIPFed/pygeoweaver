# CHG-0001 pre-implementation critique (adversarial, round 1)

| ID | Finding | Disposition |
| --- | --- | --- |
| HIGH-001 | Storing a Bearer token on disk contradicts Geoweaver docs ("never in a file"). | Accept with mitigation: the SSH agent has no secret store; whoever holds the SSH shell already owns `~/h2/gw` and `~/gw-workspace`. File 0600 in 0700 dir, per base URL, TTL-bound, `gw agent logout` revokes server-side + deletes. Env var override for CI. Document risk. |
| HIGH-002 | Password must never be in argv/process list. | `login` reads via getpass or `--password-stdin` only. |
| HIGH-003 | `ensure` race: two agents start two JVMs on one H2 file → corruption risk. | `fcntl.flock` on `~/.config/geoweaver-agent/ensure.lock`; re-probe after lock. |
| HIGH-004 | Port discovery could hit another user's Geoweaver on a shared login node. | Only scan processes whose uid == caller uid; always probe `/api/v1/health`. |
| MEDIUM-005 | Lazy `__init__` could break `from pygeoweaver import *` and existing tests that patch `pygeoweaver.X`. | `__getattr__` + `__dir__`/`__all__` delegating to `pgw_interface`; run full test suite. |
| MEDIUM-006 | `run wait` busy-polls forever. | `--timeout` + `--interval`, exit code 124 on timeout. |
| MEDIUM-007 | JSON errors must be machine-readable for agents. | stderr JSON `{error, message, status}` + documented exit codes. |
| MEDIUM-008 | Token keyed by base URL breaks on OOD (port changes every job). | Loopback URLs keyed as `loopback` (same user, same `~/h2/gw`); 401 → clear "run gw agent login". |
| LOW-009 | psutil per-process connections may raise AccessDenied on macOS. | Catch and fall back. |

Round 1 verdict: **Revise → approved with conditions above** (no proceed-to-testing on round 1).
