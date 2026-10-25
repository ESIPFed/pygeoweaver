# CHG-0002 — Proposal (pygeoweaver OOD readiness)

Honor `GEOWEAVER_PORT` for start/probe/stop; treat HTTP 200/301/302/303 as ready; pass `-Dserver.port`. Version **1.4.2**.

Operators must still `export GEOWEAVER_PORT=$port` in the OOD `script.sh` before `gw start`.
