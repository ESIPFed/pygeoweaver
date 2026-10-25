# CHG-0001 remediation (C7) — review round 1 findings

| ID | Disposition | Change |
| --- | --- | --- |
| HIGH-010 token to another user's server | **Fixed** | `discovery.loopback_port_owner()` + `check_not_foreign()` in `connect()` and `ensure_server()`; exit 9 `foreign_server`. Linux: unprivileged `net_connections` gives pid=None for other accounts → "other". macOS (single-user laptops) returns unknown → allowed. Tests: `test_token_never_sent_to_another_users_port`. |
| HIGH-011 double JVM via `gw start` / NFS | **Fixed** | New `agent/locking.py` shared by `ensure`, `server.start()` and the token store; `flock` with `O_EXCL` pid@host fallback on `ENOLCK`/`EOPNOTSUPP`; starter child re-checks own JVMs. Tests: `test_lock_falls_back_when_flock_unsupported`, `test_gw_start_takes_the_start_lock`. |
| MEDIUM-012 Windows `uids` | **Fixed** | `uids` attr requested only when `psutil.Process` has it. |
| MEDIUM-013 cleartext secrets | **Fixed** | Token/password/body over `http://` to non-loopback refused (`insecure_transport`), override `GEOWEAVER_AGENT_INSECURE=1`. |
| MEDIUM-014 `--token` in argv | **Fixed** | Option removed; store or `GEOWEAVER_API_TOKEN` only. |
| MEDIUM-015 old Geoweaver → 240 s wait | **Fixed** | `AgentClient.probe()` → `up`/`down`/`no_agent_api`; ensure fails fast with `agent_api_unavailable` (exit 6). |
| MEDIUM-016 `--host-password` hang | **Fixed** | Renamed `--host-password-stdin`; empty password is an error. A never-closed stdin pipe still blocks by design (explicit opt-in). |
| LOW-017 non-JSON errors | **Fixed** | Click usage, OSError, KeyError, ValueError → JSON on stderr. |
| LOW-018 server `steps` | **Fixed** | Server-provided `steps` used when present; log parsing only for 3.0.0 jars. |
| LOW-019 idempotency overstated | **Fixed** | Docs/help say "same token + server uptime". |
| LOW-020 parallel login race | **Fixed** | Store writes under `agent-tokens.lock`. |
| LOW-021 lazy wrapper metadata | **Fixed (partial)** | `__name__`, `__qualname__`, `__doc__` set; signature not copied (accepted). |

## Round 2 findings

| ID | Disposition | Change |
| --- | --- | --- |
| CRITICAL-030 Windows `os.kill(pid,0)` terminates | **Fixed** | `_pid_alive` uses `psutil.pid_exists` on Windows. Test `test_windows_lock_probe_never_calls_os_kill`. |
| MEDIUM-031 lock released before child boots | **Fixed** | Starter child takes `start_lock` (1 h) for the whole start and re-checks own JVMs under it; parent waits outside the lock. Test `test_child_start_rechecks_under_lock`; live: 2 parallel `ensure` → 1 JVM. |
| MEDIUM-032 false "foreign" (sshd -R, docker-proxy, service account) | **Fixed** | Block only automatic choices (default URL or `loopback-latest` token); explicit URL + token → allowed with `warning`; override `GEOWEAVER_AGENT_ALLOW_FOREIGN=1`; discovered URLs skip the check. `ensure` on a foreign-but-up server reports a warning, never starts on a foreign port. |
| LOW-033 900 s stale | **Mitigated** | 3600 s. |
| LOW-034 node-local flock on NFS | **Accepted / documented** | H2 file lock still prevents a second boot on the same DB; documented in docs/agent-ssh.md. |
| LOW-035 repeated scans | **Fixed** | 2 s per-process scan cache; ownership check skipped for discovered URLs. |
| LOW-036 silent `gw start` wait | **Fixed** | Status checked before the lock; prints that it is waiting for the lock. |
| LOW-037 `--host-password-stdin` on TTY | **Fixed** | Always reads stdin. |

Tests: 134 passed (35 agent).

## Round 3 findings

| ID | Disposition | Change |
| --- | --- | --- |
| HIGH-050 GUI password to foreign default port on first login | **Fixed** | `connect(sends_password=True)` for `login`; foreign check runs for any secret (token or password). Test `test_login_refuses_foreign_default_port`. |
| MEDIUM-051 stored token counted as explicit | **Fixed** | Explicit = URL from `--base-url`/`GEOWEAVER_BASE_URL` **and** token from `GEOWEAVER_API_TOKEN` (or password typed for login). Store / OOD tokens blocked on foreign ports. Test `test_stored_token_blocked_on_reused_foreign_port`. |
| MEDIUM-052 false timeout after child exit | **Fixed** | `_wait_up` keeps waiting while an own JVM exists. Test `test_wait_up_keeps_waiting_when_child_exits_but_jvm_boots`. |
| LOW-053 ensure success on foreign default | **Fixed** | Non-explicit URL → exit 9. Test `test_ensure_default_url_on_foreign_server_fails`. |
| LOW-054 lock timeout mismatch | **Fixed** | `gw start` waits up to 3600 s and points to the start log. |
| LOW-055 allow-second double start | **Fixed** | Child re-checks for own JVM on the same port even with the opt-in. |

Tests: 138 passed (39 agent). Live re-check: login, list 0.11 s, workflow run Done, ensure no-op; user's live JVM untouched.

## Round 4 (verdict: Approve with conditions)

| ID | Disposition |
| --- | --- |
| MEDIUM-070 login to foreign listener stored unusable token / overwrote loopback-latest | **Fixed**: token printed once, not stored. Test `test_login_on_foreign_listener_returns_token_without_storing`. |
| LOW-071 `explicit_url` default fail-open | **Fixed**: default `False`. Test `test_ensure_defaults_fail_closed`. |
| LOW-072 failed start waits full timeout with other own JVMs | **Fixed**: early exit unless an own JVM is on the target port. |
| LOW-073 Docker / ssh -R docs | **Fixed**: docs/agent-ssh.md. |
| Condition 3: Linux / Windows run | Linux + Python 3.9 via GitHub Actions on the PR (Docker daemon unavailable locally). Windows: no CI; lock path unit-tested with mocks. |
