# Software loop status — agentic-ssh

| Field | Value |
| --- | --- |
| Mode | `feature_change` |
| Active change | **CHG-0002** security audit + hardening of all `gw agent` commands (CHG-0001 shipped in PR #62) |
| Round | 4 (review) |
| Objective | <1 s agent commands; ensure server without interrupting it; live GUI sync |

## CHG-0001 stage gate

| Stage | Status |
| --- | --- |
| C0 `request.md` | done |
| C1 `proposal.md` | done |
| C2 `pre-implementation-critique.md` | done — approved with conditions (HIGH-001..LOW-009) |
| C3 `approved-plan.md` | done (A1–A6) |
| C4 implementation | done — `implementation-report.md` |
| C5 tests | done — `test-evidence.md` (140 passed; live isolated server A1–A6) |
| C6 verification (independent critique) | done — 4 rounds, final **Approve with conditions** |
| C7 remediation | done — `remediation-report.md` (HIGH-010/011/050, CRITICAL-030 …) |
| C8 release decision / PR | **Ship with accepted risk** — `release-decision.md`; PR opened |

## CHG-0002 stage gate (security hardening)

| Stage | Status |
| --- | --- |
| C0 `request.md` | done (threat model) |
| C1 `proposal.md` | done (D-01..D-12) |
| C2 `pre-implementation-critique.md` | done — **Revise** (SEC-001..014) |
| C3 `approved-plan.md` | done (B1–B11) |
| C4 implementation | done — `implementation-report.md` |
| C5 tests | done — `test-evidence.md` (196 passed, 1 network test in CI) |
| C6 verification | done — 3 rounds, final **Approve with conditions** (`verification-report.md`) |
| C7 remediation | done — SEC-015..022 + SEC-006(a) (`remediation-report.md`) |
| C8 release decision | **Ship with accepted risk** — `release-decision.md`; pushed to PR #62 |
