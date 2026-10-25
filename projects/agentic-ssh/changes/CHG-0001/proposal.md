# CHG-0001 proposal

1. **Fast package import** — `pygeoweaver/__init__.py` becomes lazy (PEP 562 `__getattr__`);
   `__main__.py` defers heavy command imports to call time. Public API names unchanged.
2. **`pygeoweaver.agent`** (stdlib only: urllib/json) — `AgentClient` for every `/api/v1` endpoint.
   - Base URL resolution: `--base-url` > `GEOWEAVER_BASE_URL` > `GEOWEAVER_PORT` > discovered
     listening port of the caller's own `geoweaver.jar` JVM (psutil) > 8070.
   - Token resolution: `GEOWEAVER_API_TOKEN` > per-base-URL store
     `~/.config/geoweaver-agent/agent-tokens.json` (dir 0700, file 0600) > legacy
     `~/.config/geoweaver-agent/api-token` (written by Geoweaver `gw-ood-login`).
   - Optional OOD cookie jar (`GEOWEAVER_OOD_COOKIE_JAR`, Netscape format).
3. **`gw agent …` CLI** (JSON on stdout, stable exit codes, no spinners/prompts unless asked):
   `status`, `ensure`, `login`, `logout`, `capabilities`, `process list|get|create|update|run|runs`,
   `workflow list|get|create|update|run`, `run get|wait|stop|logs`, `guide`.
4. **`ensure`**: health probe; if down, start Geoweaver **detached** (`start_new_session=True`) under
   an exclusive file lock (no double JVMs from parallel agents); never restarts a healthy server.
5. `gw start` also detaches the JVM from the SSH session (same SIGHUP fix).
6. Docs: `docs/agent-ssh.md` + `gw agent guide` text an AI can read.

Out of scope: rewriting legacy `gw list/run` output formats (kept for back-compat); remote SSH hosts
(Agent API is server-local `100001` by design).
