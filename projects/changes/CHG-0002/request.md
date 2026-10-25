# CHG-0002 — OOD stuck on “Waiting for GeoWeaver to start…”

Open OnDemand sessions stay in starting (no Connect) after Geoweaver 2.2+/3.0 because:

1. Readiness scripts require HTTP **302** only; Boot 3 often returns **200** (or 301/303).
2. `start.sh` hard-codes port **8070** while OOD allocates `$port` via `GEOWEAVER_PORT`.
3. Agent API `acknowledge-network-risk` Java default `false` can refuse startup on all-interfaces binds used by OOD reverse proxy.

## Desired

Treat 200/301/302/303 as up; honor `GEOWEAVER_PORT`; Geoweaver defaults allow OOD bind with risk ack on.
