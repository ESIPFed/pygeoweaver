# CHG-0001 release decision

**Decision: Ship with accepted risk** (open PR; merge after green CI).

- Independent critique: 4 rounds (Revise → Revise → Revise → Approve with conditions); all
  CRITICAL/HIGH closed; round-4 conditions 1–2 fixed, condition 3 delegated to PR CI (Linux).
- Tests: 140 passed locally (macOS, Python 3.14); live isolated Geoweaver 3.0.0 A1–A6 pass.

Accepted residual risks
| Risk | Why accepted |
| --- | --- |
| LOW-034 node-local flock on some NFS mounts | H2 file lock backstops a second boot |
| Ownership check returns "unknown" on macOS/Windows (allowed) | single-user machines; Linux shared nodes are checked |
| Token file on disk (0600) | same trust boundary as `~/h2/gw`; TTL-bound; `logout` revokes |
| No real `ssh` run locally (no sshd); no Windows CI | simulated SSH conditions; mocked Windows lock tests |
| Stopped runs report `Failed` | Geoweaver server behavior, not this client |
