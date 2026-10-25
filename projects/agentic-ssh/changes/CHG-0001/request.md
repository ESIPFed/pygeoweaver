# CHG-0001 request — fast, agent-native pygeoweaver over SSH

## User problem (verbatim intent)
- pygeoweaver is too slow: waits of >7 s per command are unacceptable.
- Priority: Geoweaver + pygeoweaver must be **AI native / agentic**.
- Deployment: Geoweaver behind firewall / VPN / login wall (Open OnDemand). The AI gets
  **SSH access** to the instance and drives Geoweaver through pygeoweaver.
- The AI must: ensure an active Geoweaver server is running; create / run / manage / monitor
  processes and workflows; **never interrupt** the live instance; changes must appear in the
  Geoweaver GUI **in real time**.

## C0 system understanding (measured 2026-10-24, macOS, Geoweaver 3.0.0 live on :8070)
| Observation | Evidence |
| --- | --- |
| `import pygeoweaver` costs ~1.5 s cold | `python -X importtime`: pandas 0.85 s, pydantic 0.13 s, IPython, halo via `pgw_interface` star imports |
| Every list/run/detail command spawns `java -jar ~/geoweaver.jar <cmd>` | `pgw_list.py`, `pgw_run.py` — a second Spring Boot JVM per call (3.2 s locally; 7 s+ on cluster nodes) |
| Second JVM opens the **same H2 file** as the live server (`AUTO_SERVER=true`) | Contends for DB lock / memory on the live instance; CLI writes bypass the server so the GUI never sees an event |
| `start_on_mac_linux` spawns JVM in caller's session (no `setsid`) | SSH hang-up can SIGHUP the server started by an agent |
| Geoweaver 3.0.0 already ships Agent API `/api/v1` (Bearer) + workspace events to open GUIs | `Geoweaver/docs/agent-api.md`, `AgentApiController.java`; `/api/v1/health` = 0.09 s |
| pygeoweaver has no client for `/api/v1` | `api_call/*` targets legacy, nonexistent paths |

## Root cause
pygeoweaver drives Geoweaver through a cold JVM CLI instead of the already-running server.
