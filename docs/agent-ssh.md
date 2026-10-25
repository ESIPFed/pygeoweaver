# AI agents over SSH: `gw agent`

Geoweaver often sits behind a firewall, VPN, or a login portal such as Open OnDemand (OOD).
The reliable way to let an AI agent use it is to give the agent an **SSH shell on the
Geoweaver machine** and have it drive Geoweaver with `gw agent …`.

`gw agent` talks to the **already running** Geoweaver over its Agent API
(`http://127.0.0.1:<port>/Geoweaver/api/v1`, Geoweaver 3.0+). It does not start a
second JVM and never opens the H2 database itself. Every create or update is broadcast
by the server to open browsers, so a person watching the Geoweaver GUI sees the agent's
changes as they happen.

| | Legacy `gw list/run/detail` | `gw agent …` |
| --- | --- | --- |
| How | boots `java -jar geoweaver.jar <cmd>` per call | HTTP to the live server |
| Latency (measured, laptop) | 3.2 s (7 s+ on cluster nodes) | 0.14–0.20 s wall, ~5 ms server |
| Touches the live server's H2 file | yes (second JVM) | no |
| GUI sees changes live | no | yes (`process.created` event in ~190 ms) |
| Output | human text | JSON + exit codes |

## One-time setup (human)

```bash
pip install -U pygeoweaver        # on the Geoweaver machine
gw agent ensure                   # starts Geoweaver if it is not running (never restarts it)
gw agent login                    # asks for the Geoweaver GUI password, stores a token
```

`login` mints a Bearer token (default 30 days, max 180) with `POST /api/v1/tokens` and
stores it in `~/.config/geoweaver-agent/agent-tokens.json` (directory 0700, file 0600).
The password is read from the prompt or `--password-stdin`, never from argv. `gw agent logout`
revokes the token on the server and deletes it locally. For CI, set `GEOWEAVER_API_TOKEN`.

> Risk note: the token file lets anyone with this account's shell use the Agent API.
> The same account can already read `~/h2/gw` and `~/gw-workspace`, so the file adds no
> new access for that user. Do not copy the file elsewhere.

## Agent session

```bash
ssh user@geoweaver-host            # or: ssh -J login-node user@compute-node
gw agent ensure && gw agent status
gw agent process create --name fetch --lang python --file fetch.py
gw agent process create --name plot  --lang shell  --code 'echo plotting'
gw agent workflow create --name pipeline --chain <fetch_id>,<plot_id>
gw agent workflow run <wid> --wait --timeout 1800     # exit 0 only if Done
gw agent run get <historyId>                           # status + log tail + per-step results
gw agent run stop <historyId>
gw agent guide                                         # full playbook for the AI
```

Python:

```python
from pygeoweaver.agent import connect
client, info = connect()
pid = client.create_process("hello", "print(42)")["id"]
run = client.wait_run(client.run_process(pid)["historyId"])
```

## Which server?

`--base-url` (anywhere on the command line) > `GEOWEAVER_BASE_URL` > `GEOWEAVER_PORT` >
the listening port of **your own** running `geoweaver.jar` JVM (OOD gives each job a new
port; discovery finds it) > `8070`. `gw agent status` lists other local Geoweavers if more
than one is up.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | ok |
| 1 | other error |
| 3 | server unreachable, or `ensure` refused to start a second JVM |
| 4 | unauthorized (no/expired token, wrong password, login redirect) |
| 5 | not found |
| 6 | other HTTP error |
| 8 | run finished but status is not `Done` |
| 124 | timed out waiting (the run keeps going on the server) |

Errors are JSON on stderr: `{"error": "...", "message": "...", "status": 401}`.

## What `ensure` will and will not do

- Healthy server → returns at once. The JVM is not touched.
- Your Geoweaver JVM exists but is not answering yet → waits for it. Never kills it.
- Your Geoweaver answers on another port → refuses (exit 3) and names that port, so two
  JVMs never share one database.
- Nothing running → starts Geoweaver in its own session (it survives SSH logout), under a
  file lock so parallel agents start only one JVM.
- Remote base URL → never starts anything; SSH to that machine instead.

## Shared nodes and safety

- `/api/v1/health` is public, so pygeoweaver checks who owns a loopback port before sending a
  token it picked automatically. A port held by another account fails with exit 9. If the
  listener really is yours (Docker `-p`, an `ssh -R` tunnel, a service account), pass
  `--base-url` explicitly with `GEOWEAVER_API_TOKEN`, or set `GEOWEAVER_AGENT_ALLOW_FOREIGN=1`.
- Plain `http://` to a non-loopback host is refused for anything carrying a token or password
  (`GEOWEAVER_AGENT_INSECURE=1` overrides). Use https, an SSH tunnel, or run on the host.
- `gw start` and `gw agent ensure` share one per-user lock in `~/.config/geoweaver-agent/`.
  On NFS without lock support it falls back to an `O_EXCL` lock file. If NFS is mounted with
  node-local flock, two login nodes can still race; H2's own file lock then makes the second
  boot fail rather than share the database.

### Geoweaver in Docker or behind an `ssh -R` tunnel

The listening socket then belongs to `docker-proxy` or `sshd` (not your account), so
automatic token handling is off for that port:

```bash
export GEOWEAVER_BASE_URL=http://127.0.0.1:8070/Geoweaver
gw agent login            # prints the token once (not stored) because the port is not yours
export GEOWEAVER_API_TOKEN=...   # from your secret store, not from shell history
gw agent process list
```

The ownership check works on Linux. macOS and Windows do not expose other accounts' sockets
to normal users, so there it cannot tell and allows the call (single-user machines).
