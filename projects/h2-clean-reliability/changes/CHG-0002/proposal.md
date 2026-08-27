# CHG-0002 — Proposal (Stage 1)

## Problem

`gw stop` blocks on automatic H2 maintenance (often a full rebuild for DBs ≥ 1GB) under a spinner that looks like a hang. Ctrl+C runs heavy recover inside a signal handler and races the Halo spinner, producing logging errors and a process that is hard to terminate.

## Evidence

- Code: `server.py` stop paths always call `maintain_h2_database_on_stop()` when `compact_h2=True` (default).
- Code: `_needs_rebuild` → `rebuild_h2_database_safely` on stop for size ≥ `H2_AUTO_REBUILD_THRESHOLD_MB` (1024) or `pending_rebuild`.
- Code: `h2_maintenance_guard` SIGINT handler calls `recover_from_interrupted_maintenance()` before re-raise.
- User report: endless `Maintaining H2 database safely...`, Ctrl+C → `--- Logging error ---`, hard to kill.
- Prior ops context: multi-GB `gw.mv.db` on Hopper-class installs.

## Proposed solution (smallest effective)

### Policy (locked)

| Command / path | Default behavior |
| --- | --- |
| `gw stop` | Stop Geoweaver JVMs only. **No** rebuild. **No** compact. Print one-line H2 size warning when size ≥ rebuild threshold (point to `gw cleanh2db`). |
| `gw stop --maintain-h2` | Optional: compact only, hard timeout **≤ 60s**. On timeout: warn, exit stop successfully, do **not** escalate to rebuild. |
| `gw start` / `prepare_h2_database_for_start` | **No** size-based automatic rebuild. May **recover/verify** interrupted maintenance (markers / incomplete promote). Oversized DB: warn + suggest `gw cleanh2db`. |
| `gw cleanh2db` | Remains the explicit full rebuild path (CHG-0001 semantics). |
| `force_restart` | Stop **without** default maintenance (same as new stop default). |

### Interrupt

- SIGINT/SIGTERM in `h2_maintenance_guard`: set `interrupted_maintenance=True`, release lock, re-raise. **No** recover, rebuild, or compact in the handler.
- Do **not** set `pending_rebuild` on bare interrupt; incomplete rebuild is detected via existing in-progress / promote markers.
- Ensure Halo/`get_spinner` context exits on the main thread (no logging from signal path beyond best-effort flag write if needed — prefer main-thread finally).
- Best-effort: terminate H2 subprocess / process group on interrupt or compact timeout (MEDIUM-002).

### API / CLI

- Add `gw stop --maintain-h2` (and/or env documented in help). Default maintenance **off**.
- Rename or deprecate misleading `compact_h2=True` default → `maintain_h2=False` (keep thin compatibility wrapper if needed).
- Fix `stop_command` docstring/help.

### Messaging

- Default stop after JVM down: if size ≥ threshold, stdout:

  `H2 database is N MB (≥ threshold M MB). Run: gw cleanh2db`

- Do not show “Maintaining H2…” spinner when no maintenance runs.

## Alternatives considered

| Alternative | Why not selected |
| --- | --- |
| Keep rebuild-on-stop; only improve spinner progress | Still blocks stop for hours; wrong lifecycle semantics |
| Default compact-on-stop with short timeout | Still surprises users; partial COMPACT risk; prefer opt-in |
| Move size rebuild to start only | Relocates hang (critique CRITICAL-003); rejected as default |
| Only document `H2_AUTO_MAINTENANCE=false` | Undiscoverable; spinner still appears; does not fix interrupt |

## Architecture impact

- **Modules:** `h2_utils.py` (policy + guard), `server.py` (stop/start wiring), `__main__.py` (CLI), tests, brief README note.
- **No DB schema / Geoweaver JAR changes.**
- **State:** `interrupted_maintenance` for deferred start recover; avoid interrupt→`pending_rebuild` coupling.
- **Security boundary:** unchanged; avoid logging secrets.
- **Monitoring:** stdout warnings; logger phase lines for opt-in maintain only.

## Data impact

- No schema migration.
- Stop no longer mutates H2 by default (rollback-friendly).
- Users who depended on stop-time rebuild must run `gw cleanh2db` (changelog note).

## Failure modes

| Failure | Expected behavior |
| --- | --- |
| Large DB on stop | Warn; exit 0 after JVM stop |
| Opt-in compact timeout | Warn; stop succeeds; start verifies |
| Ctrl+C during opt-in maintain | Exit promptly; lock released; recover deferred to start if markers require it |
| Orphan Java after interrupt | Best-effort kill; else start may see lock — document |
| Incomplete promote from prior CHG-0001 run | Start recover (fail-closed) still applies |

## Testing plan

1. Oversized DB stop → `rebuild_h2_database_safely` **not** called; warning on stdout.
2. Default stop → `compact_h2_database` **not** called.
3. `--maintain-h2` + mocked `TimeoutExpired` → stop returns; no rebuild scheduled.
4. SIGINT in guard → recover **not** called from handler; lock released; `KeyboardInterrupt` propagates.
5. Interrupt must not force `pending_rebuild` for compact-only path.
6. Start with incomplete promote / in-progress markers still recovers (existing recover tests + regression).
7. Rewrite `test_h2_interrupt_safety.py` tests that require recover-in-handler / interrupt→`pending_rebuild`.
8. `gw stop --help` documents new behavior (Click test or string assert).

## Rollout

- Patch release of pygeoweaver (bump version in `pyproject.toml` when implementing).
- Changelog: breaking behavior note — stop no longer auto-rebuilds/compacts by default.
- Rollback: revert package version / restore previous defaults if needed.
- No feature flag required beyond CLI/env already planned.

## Acceptance criteria

1. Default `gw stop` never calls `rebuild_h2_database_safely`.
2. Default `gw stop` never calls `compact_h2_database` (unless product later re-approves default compact with ≤60s — **not** in this CHG default).
3. Size ≥ threshold → stdout remediation mentions `gw cleanh2db`.
4. Default `gw start` does not size-rebuild; may recover interrupted state.
5. Signal handler does not call `recover_from_interrupted_maintenance`.
6. Conflicting interrupt tests updated; new stop-without-rebuild tests pass.
7. Stop help/docstring accurate.

## Critique conditions incorporated

This proposal locks the Stage 2 conditions from `pre-implementation-critique.md`: CRITICAL-001/002/003, HIGH-001/002/003/004 (default maintain off; start no size-rebuild; interrupt light; rewrite tests; CLI matrix).
