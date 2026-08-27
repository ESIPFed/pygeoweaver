# CHG-0002 — Pre-Implementation Critique (Stage 2)

## Change critique plan

| Field | Value |
| --- | --- |
| **Critique round** | 1 (Stage 2 design gate; post-impl pre-test gate still requires ≥2 rounds later) |
| **Workflow** | `full_adversarial` (pre-implementation) |
| **Change scope** | `gw stop` must not block on multi-hour H2 rebuild; Ctrl+C must exit promptly |
| **Active critics** | Lead · Scope/Product · Architecture · Security/Privacy · Reliability/Ops · Quality |
| **Boundary** | Critique only — **no production code modified** |
| **Proposal reviewed** | `changes/CHG-0002/proposal.md` (locks start policy + default maintain off) |
| **Repo** | pygeoweaver (`projects/h2-clean-reliability`). Do not confuse with Geoweaver UI CHG folders. |

**One-line stance:** Problem is real; draft→formal proposal direction is sound. Residual risk is relocating hang to start or re-encoding unsafe interrupt via tests. **Approve with Conditions** — conditions are largely closed by the formal proposal; Stage 3 must still disposition findings in `approved-plan.md` before coding.

---

## Assumption register

| Assumption | Evidence | Risk if wrong |
| --- | --- | --- |
| Spinner “Maintaining H2…” is short housekeeping | `server.py` wraps full `maintain_h2_database_on_stop` | Multi-GB rebuild looks like hang |
| `compact_h2=True` means compact only | Calls full auto maintenance including rebuild | Misleading API |
| Size ≥ 1024 MB rebuilds on stop | `_needs_rebuild` + rebuild branch | Hours of wall time |
| SIGINT recover-in-handler is safe | `h2_maintenance_guard` | Logging errors; hard-to-kill process |
| Moving work to start is fine | Same `_needs_rebuild` on start | Hang relocates (CRITICAL-003) |

---

## Findings

### CRITICAL-001 — Stop runs unbounded rebuild under spinner

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Failure scenario** | Multi-GB DB → rebuild on `gw stop` for hours |
| **Required action** | Default stop never calls `rebuild_h2_database_safely`; warn + `gw cleanh2db` |
| **Release-blocking** | Yes |
| **Status** | Open → addressed in proposal policy table |

### CRITICAL-002 — SIGINT handler runs recover

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Failure scenario** | Ctrl+C → recover + Halo race → logging errors / wedge |
| **Required action** | Signal path: mark interrupted + release lock only; no recover/rebuild/compact |
| **Release-blocking** | Yes |
| **Status** | Open → addressed in proposal Interrupt section |

### CRITICAL-003 — Start-time policy can relocate hang

| Field | Value |
| --- | --- |
| **Severity** | Critical |
| **Failure scenario** | Stop fixed; start still size-rebuilds |
| **Required action** | Lock: no default size-based rebuild on start; recover/verify only; rebuild via `cleanh2db` |
| **Release-blocking** | Yes |
| **Status** | Open → **locked in proposal** start row |

### HIGH-001 — Interrupt sets `pending_rebuild`

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Required action** | Do not set `pending_rebuild` on bare interrupt; use in-progress/promote markers |
| **Release-blocking** | Yes |
| **Status** | Open → addressed in proposal |

### HIGH-002 — Compact timeout / default compact

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Required action** | Prefer maintain opt-in; if compact used, ≤60s timeout; no silent escalate to rebuild |
| **Release-blocking** | Yes unless default maintain off |
| **Status** | Open → proposal default maintain **off**; opt-in ≤60s |

### HIGH-003 — Misleading `compact_h2` / no CLI flags

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Required action** | `--maintain-h2`, rename/clarify API, fix stop docstring |
| **Release-blocking** | Yes |
| **Status** | Open → addressed in proposal |

### HIGH-004 — Tests encode unsafe interrupt contract

| Field | Value |
| --- | --- |
| **Severity** | High |
| **Required action** | Rewrite `test_h2_interrupt_safety.py` expectations; add stop-without-rebuild tests |
| **Release-blocking** | Yes |
| **Status** | Open → in proposal testing plan |

### MEDIUM-001 — Progress / stdout warnings

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Required action** | No spinner when no work; stdout warn with size + remediation |
| **Release-blocking** | No (must ship with fix) |
| **Status** | Open → in proposal |

### MEDIUM-002 — Orphan JVM after interrupt

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Required action** | Best-effort process-group kill on interrupt/timeout |
| **Release-blocking** | Conditional if orphan confirmed |
| **Status** | Open → in proposal |

### MEDIUM-003 — Scope collision with CHG-0001

| Field | Value |
| --- | --- |
| **Severity** | Medium |
| **Required action** | Single owner for `h2_utils.py`; minimize recover/promote edits |
| **Release-blocking** | No |
| **Status** | Open |

### LOW-001 — Wrong stop docstring / spinner copy

| Field | Value |
| --- | --- |
| **Severity** | Low |
| **Required action** | Fix help text |
| **Release-blocking** | No |
| **Status** | Open |

### LOW-002 — Windows broad `taskkill`

| Field | Value |
| --- | --- |
| **Severity** | Low |
| **Required action** | Defer |
| **Release-blocking** | No |
| **Status** | Deferred / accepted risk |

---

## Executive judgment

| Field | Value |
| --- | --- |
| **Overall risk** | Medium if proposal policy is implemented as written; High if start rebuild left ambiguous |
| **Verdict** | **Approve with Conditions** |
| **Minimum safe version** | Default stop/start: no size rebuild; interrupt light; maintain opt-in; rewrite interrupt tests; CLI matrix |
| **Testing authorized** | **No** (pre-implementation only) |

## Recommendation

**Approve with Conditions**

Proceed to Stage 3 `approved-plan.md` with finding disposition table, then implement. Do **not** Approve for Implementation without that plan. Formal proposal already locks CRITICAL-003; Stage 3 must assign owners and evidence criteria for HIGH-004 test rewrites and MEDIUM-002 subprocess cleanup.
