# CHG-0001 — Engineering proposal (Stage C1)

**Owner:** `@software-fleet` (reliability / DevOps / backend)  
**Boundary:** Design only — no code in this stage.

## Problem

`gw cleanh2db` can abort during H2 SQL import. On the legacy pipeline (and in some remaining HEAD gaps), that leaves production empty or promotes an unverified empty DB. Users must manually finish import from `/tmp/geoweaver_h2_temp`. The product promise “safe cleanup / shrink H2” is broken.

## Evidence

1. Incident: flat `/tmp/geoweaver_h2_temp/{gw_backup.sql,gw.mv.db}` + missing workflows → matches legacy delete-then-import (`1ccd730` lines ~467–539).
2. Current `rebuild_h2_database_safely` (`h2_utils.py`): export/import **no retries**; verify = `SELECT 1` only; promote = move-then-copy; recover ignores non-default temp roots.
3. CLI docstring still says “Remove the original database files” then import (`__main__.py` cleanh2db help).
4. Tests mock rebuild heavily; no real Script/RunScript interrupt or row-count gate tests.

## Proposed solution (smallest effective)

Harden the **existing** verify-then-promote pipeline; do **not** resurrect delete-then-import.

### A. Preflight + inventory (data protection)

Before any export:

1. Resolve DB path; refuse if Geoweaver JVM still holds the file.
2. Snapshot inventory via H2 Shell:

```sql
SELECT 'WORKFLOW' t, COUNT(*) c FROM WORKFLOW
UNION ALL SELECT 'GWPROCESS', COUNT(*) FROM GWPROCESS
UNION ALL SELECT 'HISTORY', COUNT(*) FROM HISTORY
UNION ALL SELECT 'HOST', COUNT(*) FROM HOST;
```

3. Persist inventory JSON next to work dir (`pre_inventory.json`).
4. Refuse cleanup if inventory query fails (treat as locked/corrupt — recover path, not delete).

### B. Export / import with retry + heartbeat

| Step | Change |
| --- | --- |
| Export | Retry up to N (default 3) on lock/timeout/transient I/O; exponential backoff |
| Import | Same retries; increase/configurable timeout (`H2_IMPORT_TIMEOUT_SECONDS`, default ≥ 7200, allow 0 = no timeout with heartbeat watchdog) |
| Heartbeat | Parent process logs every 60s: phase, SQL size, rebuilt mv.db size, elapsed |
| Child kill | On timeout: terminate Java process group; leave production untouched |

### C. Strong verification before promote (release gate)

Replace sole `SELECT 1` with:

1. File non-empty + openable
2. Re-run same inventory SQL on **rebuilt** DB
3. Pass only if for each critical table: `rebuilt_count >= pre_count` (or `pre_count == 0`)
4. Optional: `grep`-level check that `gw_backup.sql` contains `INSERT INTO` for `WORKFLOW` when `pre_count > 0`
5. Fail → **do not promote**; print path to `original/` and SQL; exit non-zero

### D. Atomic-ish promote + SIGKILL resilience

1. Promote to `production_dir/.gw_promote_new/` then **rename swap** where filesystem allows; if rename-across-dir unsafe on NFS, keep move/copy but:
2. Write `promote_state.json` (`phase=displaced|copying|done`) before each step
3. On start/stop/clean: if `promote_state` incomplete → restore from `original/` **before** starting Geoweaver
4. Prefer default `work_base_dir = ~/geoweaver/h2_backups` (never `/tmp` unless user forces `--temp-dir` **and** we register that path into maintenance state for recover)

### E. Resume / always-safe CLI UX

```
gw cleanh2db [--db-path] [--temp-dir] [--force] [--resume]
```

- Default: if incomplete work dir exists for this `db_path`, resume import/verify/promote instead of starting fresh wipe of work dir
- On any failure: production unchanged (or auto-restored); print exact restore command
- Never call `start()` after failed cleanup
- Version banner: print pygeoweaver version + “safe rebuild pipeline” so HPC users know if they still run legacy delete-import

### F. Docs + migration notice

- Fix README / `__main__.py` help to describe verify-then-promote
- Add runbook: if workflows empty after cleanup, restore from `h2_backups/*/original` or `/tmp/geoweaver_h2_temp`
- Recommend `pip install -U pygeoweaver` for users still on delete-then-import

## Alternatives considered

| Alternative | Why not |
| --- | --- |
| Only document “don’t Ctrl+C” | Does not survive HPC walltime / OOM |
| Switch everyone to PostgreSQL now | Correct long-term but out of scope; users need H2 fix now |
| Keep `SELECT 1` verify | Does not prevent empty promote (user’s core failure mode) |
| Re-introduce in-place import to “save disk” | Recreates CRITICAL delete-before-import hazard |
| Full Dockerized maintenance sidecar | Unnecessary complexity for this CLI |

## Architecture impact

- **Modules:** `h2_utils.py` (core), `pgw_cleanh2db.py`, `server.py` start recovery, `__main__.py`, tests, README
- **DB:** No Geoweaver schema change; temporary rebuilt files only
- **APIs:** CLI compatible; new optional flags `--resume`, env timeouts
- **Security:** No new attack surface beyond existing local file/DB access; avoid logging passwords
- **Monitoring:** Structured phase logs + inventory counts

## Data impact

- Production replaced only after inventory gate
- Backups retained (`H2_BACKUP_RETENTION_COUNT`)
- Rollback = copy `original/` back (automated on incomplete promote)
- Historical data: counts must not drop across successful cleanup

## Failure modes

| Failure | Expected behavior |
| --- | --- |
| Export lock / 90020 | Retry → abort, prod intact |
| Import timeout | Retry with same SQL → abort, prod intact |
| SIGINT mid-import | Guard recover; prod intact |
| SIGKILL mid-promote | On next `gw start` / `cleanh2db`, detect incomplete promote → restore `original/` |
| Empty rebuilt passes open | **Blocked** by inventory gate |
| `/tmp` wiped mid-job | If work dir gone and prod intact → OK; if legacy empty prod → runbook restore from remaining SQL if any |

## Testing plan

- Unit: inventory parse, retry classifier, promote_state machine
- Integration (tmp H2 fixture with N workflows): interrupt import → prod count unchanged
- Integration: force rebuilt empty → promote refused
- Integration: incomplete promote_state → auto restore
- Regression: successful clean shrinks file, counts equal
- Docs test: CLI help does not say “remove original then import into production”

## Rollout plan

1. Ship pygeoweaver patch release (e.g. 1.3.4+)
2. Changelog: CRITICAL safety fix for cleanh2db
3. No feature flag required (safer default)
4. Rollback = previous package version (warn if still legacy delete-import)

## Acceptance criteria

1. Killing import after export leaves production workflow count unchanged.
2. Rebuilt DB with zero workflows while pre_count > 0 never promotes.
3. Export/import retry at least once on classified lock errors.
4. Incomplete promote auto-restores on next maintenance entry.
5. Default work dir under `~/geoweaver/h2_backups`; `--temp-dir` registered for recover.
6. CLI/README match safe pipeline.
7. Automated tests cover (1)(2)(4).

## Implementation sketch (for C3 planning — not executed yet)

1. Add `capture_table_inventory()` / `assert_inventory_ok(pre, post)`
2. Wrap export/import in `run_h2_tool_with_retry(...)`
3. Extend `verify_h2_database(..., expected_inventory=)`
4. Add `promote_state` + start-time repair
5. Update `clean_h2db` messaging + version print
6. Expand tests in `test_h2_interrupt_safety.py` / new `test_h2_inventory_gate.py`
7. Doc sync

## Open questions for critique

- Exact critical tables list (include `WORKFLOW_CHECKPOINT`? `ENVIRONMENT`?)
- Should import timeout default to “no limit + heartbeat” on HPC?
- Minimum acceptable ratio if compaction legitimately drops some skipped history rows?
