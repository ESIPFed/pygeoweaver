# CHG-0002 — Verification report (C6, independent security critic)

| Round | Verdict | New findings |
| --- | --- | --- |
| 1 (pre-implementation) | Revise | SEC-001..SEC-014 (3 HIGH, 4 MEDIUM, 7 LOW) |
| 2 (post-implementation) | Approve with conditions | SEC-015 (MEDIUM, macOS IPv6/localhost), SEC-016 (MEDIUM, Windows ownership), SEC-017..SEC-020 (LOW) |
| 3 (final) | Approve with conditions | SEC-021, SEC-022 (LOW) |

Round-3 status: SEC-001..SEC-020 fixed. Residuals (documented in `docs/agent-ssh.md`): BSD specific-address bind shadowing a wildcard own listener on macOS; stale-lock link-back race on NFS without flock; SEC-014 (H2 `-password` argv, pre-existing). Reviewer conditions: keep the network digest test in CI (done: `PYGEOWEAVER_NETWORK_TESTS=1` in `tests.yml`); track SEC-006(a), SEC-021, SEC-022 (all three fixed in C7 instead, see `remediation-report.md`).
