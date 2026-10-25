# CHG-0002 — Approved plan (C3)

All HIGH and MEDIUM findings are fixed in this change; LOW findings are fixed except SEC-014 (accepted, see bottom).

| Step | Findings | Change |
| --- | --- | --- |
| B1 | SEC-001, SEC-002 | Starter child `cwd=config_dir()` (private 0700); Geoweaver JVM `cwd=~` on all platforms |
| B2 | SEC-003 | Port ownership = `me` only for a **verified** LISTEN socket of one of the user's processes (own JVM scan, then global table, then own-process scan on macOS); `-Dserver.port` fallback never counts as verified; unknown owner fails closed for automatically chosen secrets; `discovered` exemption removed; `loopback:latest` therefore only reaches a verified own listener |
| B3 | SEC-004 | `login` on a non-own listener requires `--token-file PATH` (new file, O_EXCL, 0600); token never printed; checked before the password is sent |
| B4 | SEC-005 | `agent_child_env()` strips `GEOWEAVER_API_TOKEN`, `GEOWEAVER_OOD_COOKIE_JAR`, `GEOWEAVER_AGENT_INSECURE`, `GEOWEAVER_AGENT_ALLOW_FOREIGN` for the starter; JVM env additionally drops all `GEOWEAVER_AGENT_*` |
| B5 | SEC-006 | Jar: `requests` timeout, stream to temp, zip validity check, atomic replace. JDK: urlopen timeout, temp + atomic replace, **pinned SHA-256** for all six Temurin 17.0.13+11 archives (cached archives re-verified), `extractall(filter="data")` or member path check |
| B6 | SEC-007 | JSON output escapes C0/C1/bidi/line-separator chars; raw text (`run logs`, `--code-only`) stripped of control chars when stdout is a TTY; GUIDE + docs: logs/code/server messages are untrusted data |
| B7 | SEC-008 | Ids validated `^[A-Za-z0-9_-]{1,128}$`, quoted `safe=""` |
| B8 | SEC-009 | `--interval` ≥ 0.25 (also clamped in `wait_run`), `--log-limit` 0..1,000,000, `--ttl-days` 1..180, steps capped at 500 |
| B9 | SEC-010, SEC-011 | Config dir must be owned by the user and not group/other-writable (fail closed, tries chmod first); token store tmp `O_EXCL|O_NOFOLLOW` + fchmod; store file chmod 0600 on read; `ensure-start.log` and `~/geoweaver.log` created 0600 |
| B10 | SEC-012 | Stale lock broken by rename + inode check (a fresh lock stolen by mistake is linked back) |
| B11 | SEC-013 | Base URL: http/https only, no userinfo/query/fragment; `GEOWEAVER_PORT` digits 1..65535; `X-Geoweaver-Agent-Token` only sent when an OOD cookie jar is in use; cookie jar subject to the secure-transport guard |

**Accepted risk:** SEC-014 (pre-existing H2 `-password` argv; the default is the public constant in `constants.py`; custom H2 passwords stay visible in `ps` during maintenance). Server-side Agent API hardening (rate limiting of `POST /tokens`) is in the Geoweaver repo and out of scope.
