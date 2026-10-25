# CHG-0001 implementation report

| Area | Files |
| --- | --- |
| Lazy package import (PEP 562) | `pygeoweaver/__init__.py` |
| Lazy CLI command imports, `agent` group registration | `pygeoweaver/__main__.py` |
| Agent API client (stdlib urllib) | `pygeoweaver/agent/client.py` |
| Base URL / token discovery, token store | `pygeoweaver/agent/discovery.py` |
| Non-interrupting `ensure` (lock, detach, other-port guard) | `pygeoweaver/agent/ensure.py` |
| `gw agent` CLI | `pygeoweaver/agent/cli.py` |
| Playbook + Python API | `pygeoweaver/agent/__init__.py` |
| `gw start` JVM detached (`start_new_session`); own-uid status; strict JVM match | `pygeoweaver/server.py` |
| Docs | `docs/agent-ssh.md`, `README.md` |
| Tests | `test/test_agent.py` (23) |

Defects found and fixed during build (beyond the plan):
- Process match `'geoweaver.jar' in cmdline` matched shells (e.g. `zsh -c "... geoweaver.jar"`);
  `gw stop` could kill them. Now `is_geoweaver_jvm()` requires a `java*` executable + jar/main-class arg.
- Port discovery hit the JVM's H2 TCP port → `http.client.BadStatusLine` crash; now mapped to `unreachable`.
- `check_geoweaver_status()` counted other users' JVMs (`ps aux`) → `gw start` skipped on shared nodes.
- `--base-url` after the subcommand was rejected; leaf commands now accept group options.
- `ensure` waited full timeout when the starter child failed; now fails fast (5 s after child exit).
