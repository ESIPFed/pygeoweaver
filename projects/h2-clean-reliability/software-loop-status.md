# Software loop status — h2-clean-reliability

| Field | Value |
| --- | --- |
| Mode | `feature_change` |
| Active change | **CHG-0002** (`gw stop` H2 maintenance hang / uninterruptible Ctrl+C) |
| Prior change | CHG-0001 — cleanh2db fail-closed (implemented, v1.3.4) |
| Stage | **C0–C2 complete** — stop before Stage 3 / coding |
| Objective | Default `gw stop` returns quickly; no rebuild-on-stop; safe interrupt |

## CHG-0002 stage gate

| Stage | Status |
| --- | --- |
| C0 `request.md` | done |
| C1 `proposal.md` | done (locks: no size-rebuild on stop/start; maintain opt-in; light SIGINT) |
| C2 `pre-implementation-critique.md` | done — **Approve with Conditions** |
| C3 `approved-plan.md` | **next** |
| C4 implementation | blocked until C3 |
| C5 tests / evidence | blocked |
| C6+ verification | blocked |

## CHG-0001 (prior)

| Stage | Status |
| --- | --- |
| C0–C5 | done (58 H2-related tests) |
| C6+ | optional |

## Next coordinator action

1. Stage 3: write `changes/CHG-0002/approved-plan.md` (finding disposition table).
2. Stage 4–5: `@software-fleet` implement + test evidence — **no code until C3**.
3. Then independent Stage 6 verification by `@change-critique-fleet`.
