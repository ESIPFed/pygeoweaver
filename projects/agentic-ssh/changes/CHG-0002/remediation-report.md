# CHG-0002 — Remediation report (C7)

| ID | Fix |
| --- | --- |
| SEC-015 | `normalize_loopback` (localhost → 127.0.0.1) for check and request; address-aware `_reaches`; every reachable listener must be ours |
| SEC-016 | `_is_mine`: uid on POSIX, `username()` on Windows; unknown → not mine |
| SEC-017 | Fallback extractor: per-member extraction resolved against the on-disk tree; absolute names rejected (a new test caught `lstrip("/")` + `extract()` writing to `/abs.txt`); modes masked 0o755 |
| SEC-018 | Logs may be symlinks if the target is owned by the user |
| SEC-019 | Tightened tar test; tests for IPv6/localhost, Windows, symlinked log, `-m` cwd; CI network test of pinned digests |
| SEC-020 | Locks carry a random nonce (`pid@host#nonce`); release and stale-break compare content, not inode (Linux CI showed ext4 reuses a freed inode for the next file); Windows `msvcrt.locking` |
| SEC-006(a) | `copy_with_deadline`: 1800 s overall cap for JDK and jar downloads |
| SEC-021 | `_reaches` matches the exact address or a wildcard only (no `127.*` prefix) |
| SEC-022 | Log opened without `O_TRUNC`; `ftruncate` only after the ownership check |

Live end-to-end on an isolated Geoweaver (own HOME + `-Duser.home`, port 18071), started from a directory with a planted `pygeoweaver/` package and `config/application.properties` (`server.port=18999`): JVM cwd = test home, listens on 18071, no agent token in the JVM env or in a run's env, `geoweaver.log` 0600, token store 0600, login prints no token, run Done in ~2 s, JSON escapes an OSC 52 payload, `run logs` byte-exact when piped and sanitized on a TTY; bad id / URL with credentials / `--interval 0` rejected with exit 2.

Test lesson recorded: a test harness started with `python -c` from the planted directory was itself hijacked (cwd on `sys.path`), which confirms SEC-001; harnesses now use `python -P`. A first test JVM read the real `~/geoweaver/.secret` because Java takes `user.home` from the OS account, not `$HOME`; it was stopped before anything ran, and the isolated run used `JAVA_TOOL_OPTIONS=-Duser.home=…`.
