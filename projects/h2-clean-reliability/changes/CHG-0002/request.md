# CHG-0002 — Request (Stage 0)

## User / business problem

After `gw stop`, the CLI sits indefinitely on Halo spinner text:

```text
Maintaining H2 database safely...
```

Ctrl+C does not cleanly terminate the command. Operators see Python logging failures (`--- Logging error ---` during `logging` emit/flush) and must escalate to hard kill. Stop is supposed to be a fast lifecycle action; instead it becomes an opaque multi-hour (or uninterruptible) maintenance job.

## Current behavior

1. `gw stop` → `stop(exit_on_finish=True)` → `stop_on_mac_linux` / `stop_on_windows` with default `compact_h2=True`.
2. After killing Geoweaver JVMs, stop always enters spinner `"Maintaining H2 database safely..."` and calls `maintain_h2_database_on_stop()` → `run_automatic_h2_maintenance(trigger="stop")`.
3. If H2 size ≥ `H2_AUTO_REBUILD_THRESHOLD_MB` (default **1024**), or `pending_rebuild` is set, stop runs **full** `rebuild_h2_database_safely` (export/import, multi-hour for multi-GB DBs). User DBs ~3.5GB are in this class.
4. Mid-band DBs may run `SHUTDOWN COMPACT` with `subprocess` timeout **3600s**.
5. `h2_maintenance_guard` installs SIGINT/SIGTERM handlers that call `recover_from_interrupted_maintenance()` **inside the signal handler** before raising `KeyboardInterrupt`, while Halo’s spinner thread still writes to the TTY — producing logging flush errors and a hard-to-kill process.
6. CLI: `gw stop` has no flags; `stop_command` docstring incorrectly says “Start the Geoweaver application.” Parameter name `compact_h2` is misleading (it means full auto maintenance, including rebuild).

## Desired behavior

1. **Default `gw stop` returns quickly** after Geoweaver processes are stopped (seconds, not hours), independent of H2 file size.
2. Oversized / bloated H2 is handled by **explicit** maintenance (`gw cleanh2db` or clearly opt-in stop maintenance), with a clear stdout warning when size ≥ threshold.
3. Ctrl+C during any remaining optional maintenance **exits promptly**: release lock, mark interrupted, stop spinner; **no** recover/rebuild/compact in the signal path.
4. Start must **not** silently inherit a multi-hour size-based rebuild as the new hang location (policy must be locked in proposal / approved plan).

## Users affected

- Anyone running `gw stop` / `force_restart` with large H2 files (HPC Hopper, long-lived local installs).
- Operators who interrupt “stuck” stop with Ctrl+C.

## Success metrics

| Metric | Target |
| --- | --- |
| Default `gw stop` wall time after JVM exit | Completes without rebuild; typically &lt; ~30s excluding OS process kill wait |
| Rebuild on default stop | **Never** |
| Ctrl+C during optional maintenance | Process exits; lock released; no recover-in-handler; spinner stops |
| Operator messaging | When size ≥ rebuild threshold, stdout names size, threshold, and `gw cleanh2db` |

## Non-functional requirements

- Reliability: interrupt must not leave an unkillable Python process or opaque lock forever.
- Observability: static Halo text must not imply “short housekeeping” for hour-scale work.
- Backward compatibility: document that stop no longer auto-rebuilds; users who relied on that must run `gw cleanh2db`.
- Security: do not expand logging of DB passwords / JDBC secrets.
- Maintainability: rename or clarify `compact_h2`; fix stop help text.

## Known constraints

- Shared module `pygeoweaver/h2_utils.py` with CHG-0001 cleanh2 safety work — minimize overlap; do not reopen promote/inventory design unless required for interrupt markers.
- Existing tests in `test_h2_interrupt_safety.py` currently **encode** recover-in-SIGINT and `pending_rebuild` on interrupt as success.
- Env escape hatch `H2_AUTO_MAINTENANCE=false` exists but is undiscoverable from `gw stop`.

## Components likely affected

- `pygeoweaver/server.py` — stop / force_restart maintenance defaults
- `pygeoweaver/h2_utils.py` — stop/start maintenance policy, `h2_maintenance_guard` interrupt path
- `pygeoweaver/__main__.py` — `gw stop` flags / help
- `test/test_h2_interrupt_safety.py`, `test/test_server.py`, related H2 tests
- README / docs for stop vs cleanh2db

## Risks already known

- Moving rebuild to start without policy lock relocates the hang.
- Setting `pending_rebuild` on every Ctrl+C forces expensive work later.
- Compact timeout mid-`SHUTDOWN COMPACT` may need start-time verify/recover.
- Orphan H2 Java children after Ctrl+C may hold file locks.

## Explicit non-goals

- Redesigning CHG-0001 verify-then-promote / inventory gate.
- Fixing Windows `taskkill /f /im java.exe` collateral kill (defer).
- Rotating default H2 credentials.
- Geoweaver UI live-log multi-tab streaming (separate Geoweaver change; out of scope here).
- Async background rebuild daemon.

## Out-of-scope confusion note

A prior Geoweaver UI issue (top-level log vs process/side-panel log / multi-tab streaming) is **not** this change. This CHG is pygeoweaver **`gw stop` H2 maintenance hang / uninterruptible CLI** only.
