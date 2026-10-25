# CHG-0001 approved plan
All C2 findings dispositioned in `pre-implementation-critique.md`. Implement proposal items 1–6
with mitigations HIGH-001..LOW-009. Acceptance:
- A1 `gw agent process list` < 1 s wall on a live server (target ≤ 0.5 s locally).
- A2 Create/run/wait/stop process and workflow end-to-end against live Geoweaver 3.0.0, no restart.
- A3 GUI sync: `/api/workspace/revision` advances after agent create/update.
- A4 `ensure` on healthy server returns without touching the JVM (same PID).
- A5 Existing test suite still passes; new unit tests for client/discovery/token store/CLI.
- A6 Works over SSH (`ssh localhost gw agent …`) non-interactively.
