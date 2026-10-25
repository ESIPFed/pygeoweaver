# CHG-0002 — Release decision (C8)

**Decision: Ship with accepted risk.**

- Full suite: 196 passed, 1 skipped (network digest test; passes locally with `PYGEOWEAVER_NETWORK_TESTS=1`, enabled in CI).
- Independent critic: 3 rounds, final **Approve with conditions**; all conditions met.
- Accepted residual risk (documented): macOS BSD address shadowing; NFS stale-lock link-back race; SEC-014 H2 `-password` argv (pre-existing, default password is public); Geoweaver jar has no pinned digest (the "latest" release changes; HTTPS from GitHub, zip validity checked); server-side rate limiting of `POST /tokens` belongs to the Geoweaver repo.
- Behavior changes for users: `login` on a listener you do not own needs `--token-file`; `--interval` ≥ 0.25; `localhost` → `127.0.0.1`; an unverifiable port owner now fails closed (exit 9); `X-Geoweaver-Agent-Token` is only sent with an OOD cookie jar.
