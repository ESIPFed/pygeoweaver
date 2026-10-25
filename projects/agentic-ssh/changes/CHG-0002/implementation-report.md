# CHG-0002 — Implementation report (C4)

| Step | Files | What changed |
| --- | --- | --- |
| B1 | `agent/ensure.py`, `server.py` | Starter child `cwd=private_config_dir()`; JVM `cwd=~` (mac/linux and Windows) |
| B2 | `agent/discovery.py` | `_listen_ports` returns `(ports, verified)`; `loopback_port_owner` → `me` only for verified own listeners (own JVM cache → global socket table → own-process scan when the table is denied, macOS) and `none`/`other`/`None`; `is_foreign_loopback` fails closed unless `me`/`none`; `connect()` no longer exempts `discovered` |
| B3 | `agent/cli.py` | `login --token-file` (O_EXCL, O_NOFOLLOW, 0600, created before the password is sent, removed on failure); required for a non-own listener; token never printed |
| B4 | `agent/discovery.py` (`agent_child_env`), `ensure.py`, `server.py` | Secrets stripped from starter env; JVM env also drops `GEOWEAVER_AGENT_*` |
| B5 | `jdk_utils.py`, `utils.py`, `h2_utils.py` | `TEMURIN_SHA256` for all six 17.0.13+11 archives (fail closed when missing); `_fetch` https-only with timeout; `download_file` temp + digest + `os.replace`; cached archive re-verified; `_safe_extractall` (`filter="data"` or member/link check); jar via streamed `requests` with timeout, zip check, atomic replace; H2 jar pinned SHA-256 (Maven `.sha256` for overridden versions) |
| B6 | `agent/cli.py`, `agent/__init__.py`, docs | `_json_text` escapes C1/bidi/LS/PS; `emit_text` strips ANSI/OSC/controls on a TTY and writes byte-exact when piped (bypasses `click.echo`'s ANSI rewriting); GUIDE: server text is untrusted |
| B7 | `agent/client.py` | `_seg()` id validation `^[A-Za-z0-9_-]{1,128}$` + `quote(safe="")` |
| B8 | `agent/client.py`, `cli.py` | `MIN_POLL_INTERVAL=0.25` (CLI range + clamp in `wait_run`), log-limit 0..1e6, ttl 1..180, `MAX_STEPS=500` for `--chain` and step fan-out, `--http-timeout` 0.1..600 |
| B9 | `agent/discovery.py`, `locking.py` | `_ensure_private_dir` (owner check, chmod 0700, fail closed); store read via `O_NOFOLLOW` + owner check + fchmod 0600; store write `O_EXCL|O_NOFOLLOW` random tmp; `open_private_log` 0600 for `ensure-start.log`, `~/geoweaver.log` |
| B10 | `agent/locking.py` | `_excl_stale` returns inode; `_break_stale` renames aside, verifies inode, links a wrongly taken fresh lock back |
| B11 | `agent/client.py`, `discovery.py` | `validate_base_url` (http/https, host required, no userinfo/query/fragment, numeric port); `validate_port` for `GEOWEAVER_PORT`; `X-Geoweaver-Agent-Token` only with an OOD cookie jar; cookies trigger the secure-transport guard |

Latency after the change (live own Geoweaver on 8070, read-only): owner check 0.07 s; `gw agent status` 0.77 s wall.
