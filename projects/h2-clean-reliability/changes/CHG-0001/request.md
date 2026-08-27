# CHG-0001 — Request (Stage C0)

## User / business problem

On HPC (Hopper), `gw cleanh2db` **stopped mid H2 import**. Afterwards:

- Geoweaver UI showed **workflows gone**
- Manual recovery was required using leftover files under `/tmp/geoweaver_h2_temp` (`gw_backup.sql` ~1.9G + `gw.mv.db` ~3.5G)
- Users already faced H2 `90020` lock errors; cleanup was attempted as a fix and made data loss worse

Pygeoweaver must **always complete safely** (or fail without destroying production), with **retry** and **protection** so a mid-import interrupt cannot leave an empty production database.

## Current behavior (evidence from code + incident)

### Observed incident artifacts

```
/tmp/geoweaver_h2_temp/
  gw_backup.sql   ~1.9G
  gw.mv.db        ~3.5G
  gw.trace.db
```

This **flat** layout (`geoweaver_h2_temp` with SQL + mv.db at top level) matches the **legacy** `clean_h2db` design (commit `1ccd730` and earlier):

1. Copy DB → `/tmp/.../geoweaver_h2_temp`
2. Export SQL
3. **Delete production `gw*` files**
4. `RunScript` **into production path**
5. Start Geoweaver

If step 4 is interrupted (timeout, Ctrl+C, OOM, SLURM walltime, SSH drop), **production is already empty** while temp still holds the only good copy.

### Current HEAD (post-`3364870`) behavior

`rebuild_h2_database_safely` in `pygeoweaver/h2_utils.py` uses verify-then-promote:

- Import writes to `work_dir/rebuilt/` (not production)
- Promote only after `verify_h2_database`
- Backup under `~/geoweaver/h2_backups/geoweaver_h2_backup_*`

However, remaining gaps still violate “always succeed / never lose data”:

| Gap | Evidence |
| --- | --- |
| No export/import retry | Single `subprocess.run(..., timeout=7200)` |
| Verify is only `SELECT 1` | Empty DB can pass and be promoted |
| Promote window not atomic | `move` production away then `copy` rebuilt — SIGKILL leaves empty prod |
| Custom `--temp-dir` not scanned by recover | Auto-recover only looks at `~/geoweaver/h2_backups` |
| CLI/README still describe delete-then-import | Misleads operators and matches old pip packages |
| Pip users may still run old package | Incident layout strongly suggests pre-rewrite binary |

## Desired behavior

1. **Never delete or replace production** until a rebuilt DB is proven to contain critical tables/rows (at least `WORKFLOW` / `GWPROCESS` / `HISTORY` counts vs pre-export baseline).
2. **Survive interrupt** during export/import: production unchanged; work dir recoverable; clear resume instructions.
3. **Retry** transient failures (lock, timeout, I/O) with bounded backoff.
4. **Idempotent resume**: re-run `cleanh2db` continues or safely aborts without second data loss.
5. **Progress + heartbeat logging** so long imports on multi-GB DBs are not mistaken for hangs.
6. **Default work dir off `/tmp`** (prefer `~/geoweaver/h2_backups` or user-writable large volume) so HPC `/tmp` cleanup / size limits do not kill the job.
7. Docs and CLI text match actual safe pipeline.

## Users affected

- Scientists running Geoweaver via `pygeoweaver` on laptops and HPC
- Operators running `gw cleanh2db` after H2 bloat or lock errors

## Success metrics

- Mid-import kill (SIGINT / simulated timeout) → production `COUNT(*)` on `WORKFLOW` unchanged
- Transient lock failure → automatic retry then success or clean abort with production intact
- Successful cleanup → post-rebuild workflow count ≥ pre-rebuild count (or explicit documented filter)
- Auto-recover finds `original/` after crash when default backup location used
- No reliance on manual `RunScript` for the happy path

## Non-functional requirements

- Correctness / data integrity first over speed
- Works for multi-GB H2 files (hours-long import)
- Safe on NFS home directories (Hopper)
- Observable: phase, %, ETA or bytes, last heartbeat
- Backward compatible CLI flags (`--db-path`, `--temp-dir`, credentials)

## Known constraints

- H2 2.2.x `Script` / `RunScript` tooling
- Geoweaver must be stopped during maintenance
- Default password still in codebase (existing tech debt; out of scope to rotate)
- HPC jobs may hard-kill (`SIGKILL`) with no Python finally

## Components likely affected

- `pygeoweaver/h2_utils.py`
- `pygeoweaver/commands/pgw_cleanh2db.py`
- `pygeoweaver/__main__.py` (help text)
- `pygeoweaver/server.py` (start/stop maintenance hooks)
- `test/test_h2_*.py`, `test/test_cleanh2db.py`
- README / docs

## Risks already known

- CRITICAL: legacy delete-before-import on older installs
- HIGH: weak verify → promote empty DB
- HIGH: promote non-atomic under SIGKILL
- MEDIUM: 2h hard timeout on huge DBs
- MEDIUM: `/tmp` work dirs on HPC

## Explicit non-goals

- Migrating users off H2 to PostgreSQL (recommended separately, not this change)
- Changing Geoweaver Java schema / FK ddl-auto behavior
- Encrypting default DB password in this change
- Full interactive TUI for cleanup

## Stage rule

**No production code changes until C1 proposal + C2 critique + C3 approved plan.**
