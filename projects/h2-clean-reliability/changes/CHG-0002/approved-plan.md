# CHG-0002 — Approved plan (Stage 3)

| Finding | Priority | Action | Status |
| --- | --- | --- | --- |
| CRITICAL-001 | P0 | Default stop never rebuilds | Implemented |
| CRITICAL-002 | P0 | SIGINT: mark interrupted + release lock only | Implemented |
| CRITICAL-003 | P0 | Start: no size-based rebuild | Implemented |
| HIGH-001 | P0 | Interrupt does not set pending_rebuild | Implemented |
| HIGH-002 | P0 | Compact only via `--maintain-h2`, ≤60s timeout | Implemented |
| HIGH-003 | P0 | CLI `--maintain-h2`, rename maintain default | Implemented |
| HIGH-004 | P0 | Rewrite interrupt tests | Implemented |
| MEDIUM-001 | P1 | Oversized stdout warning | Implemented |
| MEDIUM-002 | P2 | Orphan JVM kill | Deferred |
| MEDIUM-003 | P1 | Minimize overlap with CHG-0001 | Accepted |
| LOW-001 | P1 | Fix stop docstring | Implemented |
| LOW-002 | — | Windows taskkill | Deferred |

Version: **1.3.5**
