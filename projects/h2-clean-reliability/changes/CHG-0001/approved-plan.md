# CHG-0001 — Approved plan (C3) + implementation notes

## Decision

**Approve with Conditions (P0 only)** — implement fail-closed integrity, not “always succeed”.

## P0 shipped in pygeoweaver 1.3.4

| Finding | Action | Status |
| --- | --- | --- |
| CRITICAL-001 | Success = fail closed; docs/CLI updated | Done |
| CRITICAL-002 | Recover compares inventory / restores empty-openable prod | Done |
| CRITICAL-003 | Inventory gate + SQL INSERT sanity check | Done (strict WORKFLOW/GWPROCESS/HOST) |
| HIGH-001 | promote_state + post-promote inventory; recover is guarantee | Done |
| HIGH-002 | Retry only locked/timeout; wipe rebuilt/ each import attempt | Done |
| HIGH-003 | Heartbeat log only; kill only on explicit timeout | Done |
| HIGH-004 | Deferred --resume / rename-swap experiments | Deferred |
| MEDIUM-004 | CLI + README fixed | Done |

## Files changed

- `pygeoweaver/h2_utils.py` — inventory, retry, promote_state, recover
- `pygeoweaver/__main__.py` — cleanh2db help
- `README.md` — cleanh2db docs
- `pyproject.toml` — 1.3.4
- `test/test_h2_inventory_gate.py` — new tests

## Test evidence

```
pytest test/test_h2_inventory_gate.py test/test_h2_utils.py test/test_cleanh2db.py \
       test/test_h2_interrupt_safety.py test/test_h2_edge_cases.py -q
# 58 passed
```
