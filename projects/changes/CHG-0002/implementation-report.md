# CHG-0002 — Implementation report

## Files changed

- `pygeoweaver/server.py` — readiness helpers, port-aware URL, `-Dserver.port` on start
- `pygeoweaver/start.sh` / `stop.sh` — `GEOWEAVER_PORT`, multi-status ready check
- `test/test_server.py` — unit tests for helpers
- `pyproject.toml` — version 1.4.2

## Deviations

None material.

## Rollback

Pin `pygeoweaver==1.4.1` (or prior). Revert this branch.
