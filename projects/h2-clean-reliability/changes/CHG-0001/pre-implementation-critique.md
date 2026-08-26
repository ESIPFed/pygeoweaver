# CHG-0001 — Pre-Implementation Critique (Round 1)

## Change critique plan

| Field | Value |
| --- | --- |
| **Critique round** | **1 / minimum 2** (later implementation gate still requires a second adversarial pass after code exists; this PRE-IMPLEMENTATION pass is a single deep design critique) |
| **Workflow** | `full_adversarial` (design/proposal gate before C3 plan / implementation) |
| **Change scope** | Harden `gw cleanh2db` / `rebuild_h2_database_safely` against mid-import interrupt, weak verify, non-atomic promote, and recover blind spots |
| **Active critics** | Lead · Scope/Product · Architecture · Security/Privacy · Reliability/Ops · Quality/Maintainability (AI/Data N/A) |
| **Boundary** | Critique only — **no production code modified**; claims spot-checked against `pygeoweaver/h2_utils.py`, `pygeoweaver/commands/pgw_cleanh2db.py`, `pygeoweaver/__main__.py`, and Geoweaver JPA entities |
| **Delta since last round** | N/A (first round) |
| **Sources** | `changes/CHG-0001/request.md`, `changes/CHG-0001/proposal.md` |

**One-line stance:** Direction (verify-then-promote + inventory gate + fail closed) is right; several design gaps would recreate the Hopper empty-DB failure mode under SIGKILL / empty-but-openable H2 / bad inventory semantics. **Do not Approve for Implementation without conditions.**

---

## Assumption register

| Assumption | Evidence today | Risk if wrong |
| --- | --- | --- |
| “Always succeed / always complete safely” is a safe product goal | `request.md` Desired behavior + gap table framing “always succeed / never lose data” | Implementers optimize for completion over abort → promote-under-uncertainty |
| Inventory SQL `FROM WORKFLOW` / `GWPROCESS` / … matches on-disk H2 identifiers | Geoweaver JPA: `@Entity` classes `Workflow`, `GWProcess`, `History`, `Host` (no explicit `@Table` except `WorkflowCheckpoint`); H2/Hibernate case rules vary | Preflight refuses all cleanups **or** skips gate via error misclassification |
| `rebuilt_count >= pre_count` proves data integrity | Counts only; no FK/graph consistency; open Q on HISTORY drop | Promote “valid” DB that lost join integrity or skipped tables |
| Empty legitimate DB (`pre_count == 0` all tables) is safe to rebuild/promote | Proposal §C.3 allows `pre_count == 0` | Cannot distinguish “legitimately empty” from “already wiped production” without other signals |
| NFS “rename swap” / `promote_state.json` closes SIGKILL window | Current `promote_rebuilt_database` is move-then-copy (`h2_utils.py` ~1257–1293); multi-file H2 set cannot be one atomic rename | Mid-promote empty/partial prod still possible; state file itself may be lost on NFS |
| Export/import retry is always safe | Proposal §B; current code single-shot `subprocess.run(..., timeout=7200)` | Retry into dirty `rebuilt/` or re-export of changing source amplifies corruption |
| Heartbeat/watchdog distinguishes hang vs slow multi-GB import | Proposal §B timeout `0` + heartbeat | False-positive kill wastes hours; false-negative leaves hung Java forever |
| Default work dir change is still a major gap | `pgw_cleanh2db.py` already defaults `work_base_dir` to `get_h2_backup_base_dir()` | Scope spent on already-shipped default while HEAD still has `SELECT 1` + recover fail-open |
| Recover will be fixed alongside promote verify | `recover_from_interrupted_maintenance` uses `verify_h2_database` → `SELECT 1` only (`h2_utils.py` ~229–240) | Empty openable prod → recover clears `.in_progress` and **skips** restore — exact incident class |
| CLI help still describes delete-then-import | Confirmed `__main__.py` cleanh2db help steps 5–6 | Operators follow wrong mental model / distrust upgrade |

---

## 1. Product validity

**Verdict:** Problem is real and high-severity. Framing is partly unsafe.

- Hopper incident (flat `/tmp/geoweaver_h2_temp`, workflows gone) is a credible CRITICAL user outcome; legacy delete-then-import explanation is consistent with that layout.
- Current HEAD (`rebuild_h2_database_safely`) already moved to verify-then-promote — so the **product gap for users on current source** is not “no safe pipeline,” it is **weak verify + non-atomic promote + recover that trusts `SELECT 1` + misleading CLI**. Treating “ship entire A–F package” as one product may delay the fix that stops empty promote.
- **“Always succeed” is an unsafe goal.** Acceptable promise: **fail closed** — abort with production intact (or auto-restored), non-zero exit, recoverable work dir. Success is optional; **non-destruction is mandatory.**
- Success metric “post-rebuild workflow count ≥ pre-rebuild” is necessary but not sufficient (see inventory findings). Open questions on HISTORY skip ratio and critical table set are **product blockers** if left to implementer improvisation.

---

## 2. Architecture

**Verdict:** Keep verify-then-promote; reject complexity that does not close the recover fail-open loop.

- Correct core: inventory → export → import to side dir → strong verify → promote → only then prune/start.
- **Recover and promote must share the same integrity predicate.** Extending only promote-time verify while `recover_from_interrupted_maintenance` still short-circuits on `SELECT 1` leaves the worst path open.
- `promote_state.json` + start hooks + `--resume` + version banner + docs is a large surface. Minimal critical architecture: **(1)** inventory gate, **(2)** recover uses same gate / refuses to clear markers when inventory empty vs backup, **(3)** promote never leaves “openable empty” without restore, **(4)** fix CLI help. Atomic rename is secondary and may be a mirage on multi-file NFS.
- Touching `server.py` start/stop for promote repair is justified **only** if incomplete promote detection is tested; otherwise cleanh2db-only repair leaves `gw start` as the path that boots empty UI.

---

## 3. Security / privacy

**Verdict:** No major new remote attack surface; local footguns remain.

- Maintenance remains local file + JDBC with default credentials already in tree (`GEOWEAVER_DEFAULT_DB_PASSWORD`); proposal correctly marks rotation out of scope — **Accepted residual risk**, document in runbook.
- `--password` on CLI already echoed as masked length in `__main__.py`; ensure inventory/heartbeat logs never print JDBC URLs with embedded secrets or SQL dumps of user workflow code at INFO.
- Registering arbitrary `--temp-dir` into global maintenance state: validate path ownership/permissions; avoid following symlinks into unexpected locations when auto-restoring.
- Supply chain: downloading H2 JAR (`get_h2_jar_path`) unchanged — out of scope but still a trust boundary on HPC.

---

## 4. Reliability

**Verdict:** Highest risk area. Proposal names the right threats but under-specifies fail-closed recover and retry semantics.

- Mid-import interrupt with production untouched is already true **before** promote on HEAD; the lethal windows are **promote move-then-copy** and **recover that accepts empty openable DB**.
- SIGKILL: Python `finally` / SIGINT handlers do not run — design must assume state on disk only. `promote_state.json` helps only if it is fsync’d before each irreversible step and recover reads it **before** trusting production `SELECT 1`.
- Multi-GB imports: 7200s timeout and “retry” without classifying OOM vs lock will burn walltime and disk.

---

## 5. Scalability / cost

**Verdict:** Acceptable if disk and time budgets are explicit; dangerous if silent.

- Safe rebuild already needs ~2× DB + SQL (incident scale: ~1.9G SQL + ~3.5G mv.db). Defaulting to `~/geoweaver/h2_backups` on NFS home can exhaust quota — **preflight free-space check** missing from proposal.
- Retention `H2_BACKUP_RETENTION_COUNT=3` (`h2_utils.py`) can delete the only good `original/` after a “successful” promote that later proves wrong — prune must not run until post-start inventory confirmation or must keep last known-good longer after rebuild.
- Heartbeat logging every 60s is cheap; watchdog kills are expensive (false positive).

---

## 6. Testing

**Verdict:** Proposal test list is directionally right; must add recover-vs-empty and real interrupt cases. Current tests mock `verify_h2_database` heavily (`test/test_h2_interrupt_safety.py`, `test/test_h2_edge_cases.py`) — they will not catch inventory/recover fail-open without new fixtures.

Required before trusting release (not optional polish):

1. Empty rebuilt + `pre_count > 0` → no promote.
2. Production empty-but-`SELECT 1` OK + `original/` with workflows → recover restores, does **not** clear markers early.
3. SIGKILL/simulate after displace, before copy complete → next start/clean restores.
4. Import interrupt → prod counts unchanged.
5. Inventory missing-table / case-fold failure → **refuse** cleanup (fail closed), not skip gate.
6. Retry import: dirty `rebuilt/` wiped between attempts.
7. CLI help regression: must not say remove-original-then-import-into-production.

---

## 7. Operations

**Verdict:** Version banner + runbook help pip-lag users; do not let ops theater replace integrity gates.

- Misleading `__main__.py` help is an ops hazard **today** — cheap fix, should be in minimal ship.
- `--temp-dir` not scanned by `_find_recoverable_work_dirs` (only `get_h2_backup_base_dir()`) — confirmed gap; registration must be durable across crash (home state file), not only in wiped `/tmp`.
- Success path in `pgw_cleanh2db.py` always `start()` after rebuild success — if success is lied about by weak verify, UI comes up empty. Fail path correctly avoids start; keep that invariant.

---

## 8. Maintainability

**Verdict:** Prefer small state machine over overlapping markers (`.in_progress`, `h2_maintenance_state.json`, proposed `promote_state.json`, `--resume`).

- Three persistence mechanisms without a single documented state diagram will rot.
- Close open questions in C3 plan (table list, timeout default, HISTORY ratio) — do not leave as code comments.

---

## Findings

### CRITICAL-001 — “Always succeed” product goal vs fail-closed safety

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Area** | Product / Reliability |
| **Assumption challenged** | “Pygeoweaver must always complete safely” / gap framing “always succeed / never lose data” (`request.md`) is a coherent acceptance criterion |
| **Failure scenario** | Implementers add retries, resume, and promote heuristics to force completion when inventory is ambiguous (parse failure, partial SQL, timeout=0 watchdog flapping), shipping a path that prefers “finished cleanup” over “abort with prod intact” |
| **User or business impact** | Same Hopper outcome: workflows gone; trust destroyed |
| **Evidence available** | `request.md` Desired behavior §1–4 and gap table; proposal acceptance still centers successful cleanup |
| **Evidence missing** | Explicit product rule: **any uncertainty → non-zero exit, no promote, no `start()`** |
| **Required action** | Rewrite success criteria: primary SLO = **production row inventory unchanged on any failure**; secondary = successful shrink. Ban language “always succeed” from plan/README |
| **Verification method** | Review C3 plan + acceptance tests: every failure-mode row ends in prod intact + exit ≠ 0 |
| **Release-blocking** | Yes |
| **Status** | Open |

### CRITICAL-002 — Recover fail-open on empty-but-openable production (`SELECT 1`)

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Area** | Reliability / Architecture |
| **Assumption challenged** | Strengthening promote-time verify alone fixes the incident class; existing recover is adequate |
| **Failure scenario** | Promote displaces prod, copies partial/empty rebuilt that still opens; or legacy empty prod remains. `recover_from_interrupted_maintenance` runs `verify_h2_database` → `SELECT 1` succeeds → **clears `.in_progress` and returns True without restoring `original/`** (`h2_utils.py` ~229–240, verify ~1207–1246) |
| **User or business impact** | Auto-recovery actively abandons the good backup; UI shows empty workflows; manual `/tmp` archaeology required |
| **Evidence available** | `h2_utils.py` recover short-circuit; verify SQL is only `SELECT 1;`; proposal §C upgrades verify for promote but does not mandate recover uses inventory vs `original/` |
| **Evidence missing** | Spec: recover must compare production inventory to `pre_inventory.json` / `original/` inventory before declaring healthy |
| **Required action** | Same integrity predicate for promote **and** recover; if prod inventory ≪ backup inventory → restore `original/` even if `SELECT 1` passes |
| **Verification method** | Integration: plant empty openable prod + `original/` with N workflows + in-progress marker → recover restores N |
| **Release-blocking** | Yes |
| **Status** | Open |

### CRITICAL-003 — Inventory gate edge cases (missing tables, H2 case folding, empty legitimate DB)

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Area** | Data integrity / Product |
| **Assumption challenged** | Fixed SQL against `WORKFLOW`/`GWPROCESS`/`HISTORY`/`HOST` is portable and that `pre_count == 0` is safe |
| **Failure scenario** | (a) H2 stores Hibernate default names differently (`Workflow` vs `WORKFLOW`); `INFORMATION_SCHEMA` vs quoted identifiers → inventory query fails → if mis-handled as “skip gate,” empty promote returns; if hard-fail, all cleanups blocked. (b) Table missing after partial schema → COUNT errors. (c) Production already wiped (`pre_count==0`) while `original/` in an older backup still has data — gate allows promoting empty “success.” (d) `WorkflowCheckpoint` / `Environment` omitted — counts on WORKFLOW pass while checkpoints lost |
| **User or business impact** | Either cleanup brick (availability) or silent data loss (integrity) |
| **Evidence available** | Proposal §A SQL; Geoweaver `Workflow.java` etc. lack `@Table` (default naming); `Checkpoint.java` uses `@Table(name = "WorkflowCheckpoint")`; proposal open Q on table list |
| **Evidence missing** | Empirically captured schema from a real Geoweaver H2 (`SHOW TABLES` / `INFORMATION_SCHEMA.TABLES`); decision table for missing-table vs zero-row; policy when pre-inventory is all zeros but `original/` or SQL has INSERTs |
| **Required action** | Resolve identifiers via `INFORMATION_SCHEMA` (fail closed if critical tables absent when SQL export or file size implies non-empty DB); treat all-zero pre-inventory + large `gw.mv.db` / SQL with INSERTs as **refuse promote**; decide ENVIRONMENT / WorkflowCheckpoint explicitly in C3 |
| **Verification method** | Fixtures: missing table; case-variant names; zeros-with-large-file; zeros-with-small-empty-db |
| **Release-blocking** | Yes |
| **Status** | Open |

### HIGH-001 — NFS / multi-file “atomic rename” claims are oversold

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Area** | Architecture / Reliability |
| **Assumption challenged** | Promote to `.gw_promote_new/` then rename swap (or `promote_state.json`) makes promote atomic on Hopper NFS |
| **Failure scenario** | H2 uses multiple files (`*.mv.db`, `*.trace.db`, …). Even same-directory rename is atomic **per file**, not per set. Cross-dir / NFS `rename` may become copy+unlink. SIGKILL between file renames → mixed generation. State JSON without `fsync` lies about phase |
| **User or business impact** | Empty or hybrid prod DB; hard-to-debug corruption |
| **Evidence available** | Current `promote_rebuilt_database` move-then-copy (`h2_utils.py` ~1271–1274); proposal §D “atomic-ish” hedge |
| **Evidence missing** | NFS test plan; fsync requirements; explicit “multi-file swap cannot be atomic → recover must always be correct” design note |
| **Required action** | Document: **atomicity is best-effort; recover correctness is the real guarantee**. Order: write state→fsync→displace→copy→verify inventory in prod→clear state. Do not market as atomic |
| **Verification method** | Fault-inject kill between displace and copy-complete; assert restore |
| **Release-blocking** | Yes (until recover guarantee specified) |
| **Status** | Open |

### HIGH-002 — Retry can amplify corruption / waste

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Area** | Reliability |
| **Assumption challenged** | Retrying export/import up to N times with backoff is always safer |
| **Failure scenario** | Failed import leaves partial files under `rebuilt/`; retry RunScript into same JDBC path appends/conflicts → weird openable DB with wrong counts that still passes weak checks; retrying export while another process holds lock; retrying after non-transient corruption (disk full) loops 3× for hours |
| **User or business impact** | Longer outages; higher chance of promoting garbage if gate buggy |
| **Evidence available** | Proposal §B; current code no retries; `classify_h2_error` only locked/auth/unknown |
| **Evidence missing** | Classifier for disk-full, OOM, checksum/SQL errors (non-retryable); mandatory `rm -rf rebuilt/*` before each import attempt |
| **Required action** | Retry **only** locked/timeout transient; wipe `rebuilt/` each attempt; never retry auth; cap total wall time |
| **Verification method** | Unit tests on classifier; integration: partial rebuilt then retry yields clean import or abort |
| **Release-blocking** | Yes |
| **Status** | Open |

### HIGH-003 — Heartbeat / watchdog false positives on huge imports

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Area** | Reliability / Operations |
| **Assumption challenged** | Parent heartbeat + optional timeout `0` with watchdog safely represents progress on multi-GB NFS imports |
| **Failure scenario** | RunScript CPU-bound with slow size growth; NFS metadata stall; heartbeat sees “no mv.db growth for M minutes” → kills process group → hours lost; operators disable gates. Or opposite: hung JVM still touches files → watchdog never fires |
| **User or business impact** | Failed maintenance windows; pressure to bypass safety |
| **Evidence available** | Proposal §B; request NFR “hours-long import”; incident SQL ~1.9G |
| **Evidence missing** | Definition of hang (growth vs heartbeat liveness of child PID); default **no kill on heartbeat alone** on HPC |
| **Required action** | Heartbeat is **observability only** by default; killing only on explicit timeout. If watchdog exists, require opt-in env + very high threshold; document false-positive risk |
| **Verification method** | Manual/simulated stall without kill when PID alive; timeout path leaves prod intact |
| **Release-blocking** | Yes (for any default-on kill-on-heartbeat) |
| **Status** | Open |

### HIGH-004 — Scope creep vs minimal critical fix

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Area** | Scope |
| **Assumption challenged** | A–F (inventory, retry, heartbeat, promote_state, resume, version banner, docs, server hooks, temp-dir registry) is the smallest effective change |
| **Failure scenario** | Large patch delays ship; bugs in `--resume` / state machine overshadow inventory gate; “default work dir off `/tmp`” work duplicates existing `pgw_cleanh2db.py` default to `get_h2_backup_base_dir()` |
| **User or business impact** | Users on HEAD remain exposed to empty promote/`SELECT 1` longer; pip legacy users still need upgrade notice (docs-only) |
| **Evidence available** | `pgw_cleanh2db.py` ~59–63 already defaults backup base; proposal §E–F feature bundle; request lists many components |
| **Evidence missing** | Phased MVP: P0 integrity / P1 UX / P2 resume |
| **Required action** | **P0 only for first ship:** inventory gate + recover parity + promote fail-closed + CLI help fix + temp-dir registration in maintenance state. Defer `--resume`, version banner polish, heartbeat watchdog kills, rename-swap experiments |
| **Verification method** | C3 plan with explicit P0/P1 cut line; PR diff limited to P0 |
| **Release-blocking** | Yes (for combined mega-change without phasing) |
| **Status** | Open |

### MEDIUM-001 — `>=` count gate and HISTORY / compaction semantics

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Area** | Product / Data |
| **Assumption challenged** | `rebuilt_count >= pre_count` for all listed tables is the right promote predicate without per-table policy |
| **Failure scenario** | Legitimate export filters or future compaction drops HISTORY rows → permanent cleanup refusal; or WORKFLOW count preserved while edge JSON references missing processes |
| **User or business impact** | False refuse (ops pain) or false accept (subtle breakage) |
| **Evidence available** | Proposal §C.3 and open Q on HISTORY ratio |
| **Evidence missing** | Per-table policy (WORKFLOW/GWPROCESS/HOST strict equality; HISTORY configurable) |
| **Required action** | Close open Q in C3: strict equality for workflow/process/host; HISTORY documented allow-list or forbid drop |
| **Verification method** | Tests for equality vs intentional HISTORY decrease (if allowed) |
| **Release-blocking** | No (must resolve before release, not before coding start if plan locks it) |
| **Status** | Open |

### MEDIUM-002 — Disk / NFS quota preflight missing

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Area** | Scalability / Operations |
| **Assumption challenged** | Users have room for original + rebuilt + SQL on default home NFS |
| **Failure scenario** | Import fails mid-way (disk full); retries amplify; home quota full; confusing errors |
| **Evidence available** | Incident multi-GB sizes; default `~/geoweaver/h2_backups` |
| **Evidence missing** | Preflight: free space ≥ f(size_mv + size_sql estimate) |
| **Required action** | Add free-space check before export; fail closed with message to set `--temp-dir` on large volume |
| **Verification method** | Mock/low-space test or documented manual check |
| **Release-blocking** | No |
| **Status** | Open |

### MEDIUM-003 — Backup prune races with human verification

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Area** | Operations |
| **Assumption challenged** | `prune_old_h2_backups()` immediately after rebuild (`h2_utils.py` ~939) is safe |
| **Failure scenario** | Three rebuilds / auto-maintenance cycles delete the `original/` that still held pre-incident data while user only now notices empty UI |
| **Evidence available** | `H2_BACKUP_RETENTION_COUNT` default 3; prune after success |
| **Evidence missing** | “Do not prune until operator confirms” or keep last successful pre-rebuild longer |
| **Required action** | Defer prune or exclude latest `original/` from retention until next successful verified start |
| **Verification method** | Unit test retention policy |
| **Release-blocking** | No |
| **Status** | Open |

### MEDIUM-004 — CLI/docs lie (confirmed) but are incomplete mitigation

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Area** | Operations / Maintainability |
| **Assumption challenged** | Fixing help/README substantially reduces incident rate for pip-legacy users |
| **Failure scenario** | HPC site still runs old wheel with delete-then-import despite new docs |
| **Evidence available** | `__main__.py` ~529–536 still lists “Remove the original database files” then import; `pgw_cleanh2db.py` docstring already describes safe pipeline — **split brain** |
| **Evidence missing** | Runtime version print + detect legacy behavior — useful but not a substitute for P0 integrity |
| **Required action** | Align help with `pgw_cleanh2db.py` in P0; version/upgrade notice in P1 |
| **Verification method** | Docs/CLI assertion test in proposal |
| **Release-blocking** | No (P0 help fix should still ship) |
| **Status** | Open |

### LOW-001 — Password default disclosed in CLI help

| Field | Value |
| --- | --- |
| **Severity** | Low |
| **Area** | Security |
| **Assumption challenged** | Out-of-scope password rotation means help can keep printing default password string |
| **Failure scenario** | Help text continues advertising default DB password (`__main__.py` ~524) |
| **Impact** | Minor information disclosure (already in constants) |
| **Evidence available** | `__main__.py` option help |
| **Evidence missing** | N/A |
| **Required action** | Say “default from constants” without echoing value in help |
| **Verification method** | Help string review |
| **Release-blocking** | No |
| **Status** | Open |

### LOW-002 — Optional SQL `grep` for INSERT is brittle

| Field | Value |
| --- | --- |
| **Severity** | Low |
| **Area** | Testing / Maintainability |
| **Assumption challenged** | `grep`-level INSERT check is a useful promote gate |
| **Failure scenario** | H2 Script format changes (`INSERT INTO "WORKFLOW"` / COPY / different quoting) → false refuse or false comfort |
| **Evidence available** | Proposal §C.4 optional |
| **Required action** | Prefer inventory SQL over grep; if kept, treat as warning only |
| **Verification method** | Sample real Script output fixture |
| **Release-blocking** | No |
| **Status** | Open |

---

## Targeted challenge responses (required)

### A. “Always succeed” vs fail closed

**Unsafe as stated.** The only acceptable invariant is fail closed: never delete/replace production unless post-rebuild inventory proves critical tables/rows; on doubt, abort. “Always complete” belongs in marketing fiction, not acceptance tests. See CRITICAL-001.

### B. Inventory gate edge cases

Missing tables, H2 case folding, and all-zero pre-inventory on a large/wiped DB are **not** edge polish — they are how the gate fails open or bricks cleanup. Must use schema discovery + fail closed + special case “zeros but evidence of prior data.” See CRITICAL-003.

### C. NFS rename / promote atomicity

Do not rely on rename atomicity for multi-file H2 on NFS. `promote_state` + **inventory-aware recover** is the real mitigation; “atomic-ish” is aspirational. See HIGH-001.

### D. Retry amplifying corruption

Retries without wiping `rebuilt/` and without non-retryable classification are net-negative. See HIGH-002.

### E. Heartbeat / watchdog false positives

Heartbeat for humans: yes. Default watchdog kill on “no growth”: no. See HIGH-003.

### F. Scope creep vs minimal critical fix

P0 = integrity predicate (promote + recover) + help text + temp-dir registration. Defer resume/banner/rename theater. See HIGH-004. Note: default work dir is **already** `~/geoweaver/h2_backups` in `pgw_cleanh2db.py` — do not count it as new safety work.

---

## Spot-check: proposal claims vs code

| Claim | Spot-check result |
| --- | --- |
| Export/import no retries | **True** — single `subprocess.run(..., timeout=7200)` in `rebuild_h2_database_safely` (~870, ~900) |
| Verify is only `SELECT 1` | **True** — `verify_h2_database` (~1236) |
| Promote = move then copy | **True** — `promote_rebuilt_database` (~1271–1274) |
| Recover ignores custom temp roots | **True** — `_find_recoverable_work_dirs` only lists `get_h2_backup_base_dir()` (~187–204) |
| CLI describes delete-then-import | **True** — `__main__.py` cleanh2db help steps 5–6 (~529–536) |
| Default work dir still `/tmp` | **Mostly false for current `clean_h2db`** — defaults to `get_h2_backup_base_dir()` (`pgw_cleanh2db.py` ~59–63); help text still implies temp dir |
| `pgw_cleanh2db` already safe messaging | **Partially true** — module docstring/user prints mention verify-then-promote; Click help contradicts |

---

## Executive judgment

| Field | Value |
| --- | --- |
| **Overall risk** | **High** if implemented as written without recover/inventory hardening; **Medium** if P0 fail-closed scope is enforced |
| **Top failure scenarios** | (1) Empty openable prod + recover clears markers; (2) Inventory SQL case/table miss → skip or false pass; (3) SIGKILL mid multi-file promote; (4) Retry dirty rebuilt; (5) Watchdog kills long NFS import |
| **Minimum safe version** | Inventory (+ schema-aware) gate on promote **and** recover; wipe-on-retry; no default heartbeat-kill; CLI help fix; temp-dir registered in durable state; explicit fail-closed product language |
| **Pre-implementation checklist** | Close CRITICAL-001–003 and HIGH-001–004 in C3 plan text before coding; lock table list and HISTORY policy; add recover empty-DB test to acceptance criteria |

---

## Recommendation

**Approve with Conditions**

Direction (harden verify-then-promote; do not resurrect delete-then-import) is correct. **Do not Approve for Implementation** unconditionally while Critical/High design gaps remain.

**Conditions (must appear in C3 plan before code):**

1. Replace “always succeed” with **fail-closed** SLO (CRITICAL-001).
2. Same inventory integrity predicate for **promote and recover**; never treat `SELECT 1` alone as healthy when backups show data (CRITICAL-002).
3. Specify H2 identifier discovery + missing-table + all-zero/large-file policies (CRITICAL-003).
4. Treat NFS promote as non-atomic; specify fsync’d state + recover tests (HIGH-001).
5. Retry policy: transient only + wipe `rebuilt/` (HIGH-002).
6. Heartbeat observability-only by default (HIGH-003).
7. Phase scope: P0 integrity vs deferred resume/banner/rename (HIGH-004).

**Round-2 requirement:** After implementation, `@change-critique-fleet` must re-review the actual diff; Round 1 must not be treated as a testing green light.

**Handoff:** Back to proposal/C3 authors — revise plan for conditions above; **not** to implementers for coding yet; **not** to testing.
