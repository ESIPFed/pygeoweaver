# CHG-0002 — Pre-implementation critique (C2, independent security lane)

Reviewer: independent security/privacy critic (read-only; did not author the code). Verdict: **Revise**.

| ID | Sev | Finding (short) | Maps to |
| --- | --- | --- | --- |
| SEC-001 | HIGH (confirmed: hijack reproduced) | `python -m` start child runs with agent cwd on `sys.path[0]` | D-01 |
| SEC-002 | HIGH (plausible) | Geoweaver JVM inherits agent cwd → Spring Boot loads `./config/application.properties` from an untrusted repo | new |
| SEC-003 | HIGH | Foreign-port guard off on macOS (`net_connections` AccessDenied → owner unknown → token sent); `discovered` URLs skip the guard, and discovery trusts `-Dserver.port` of a JVM that has not bound (race with another user's server) | new |
| SEC-004 | MEDIUM | `login` on a foreign listener prints the raw token (AI transcript) | D-07 |
| SEC-005 | MEDIUM | Agent secrets in env inherited by starter, JVM and every process Geoweaver runs | D-04 |
| SEC-006 | MEDIUM | Jar/JDK downloads: no timeout (hang while holding the start lock), no integrity check, non-atomic jar write, tar `extractall` without filter | D-10, D-11 |
| SEC-007 | MEDIUM | Raw logs/code to terminal (ESC/OSC, C1 CSI, bidi); JSON `ensure_ascii=False` passes C1/bidi; GUIDE lacks untrusted-data rule | D-12 |
| SEC-008 | LOW | ids quoted with `safe='/'` → `../` path injection | D-02 |
| SEC-009 | LOW | `--interval 0` busy-polls the live server; unbounded log limit / step fan-out | D-08 |
| SEC-010 | LOW | Config dir ownership/mode not enforced; tmp file without O_EXCL/O_NOFOLLOW; log modes | D-06 |
| SEC-011 | LOW | `~/geoweaver.log` 0644 | D-05 |
| SEC-012 | LOW | Stale O_EXCL lock break race (Windows/NFS) → two holders | new |
| SEC-013 | LOW | `GEOWEAVER_PORT="80@evil:443"` goes off-host; no scheme allow-list; userinfo echoed; token duplicated in custom header | D-03 |
| SEC-014 | LOW | H2 `-password` on java argv (pre-existing; default password is the public constant) | new |
