# CHG-0001 — Fix stale ~/jdk.tar.gz JDK 11 extract (Permission denied)

PyGeoWeaver reused an existing `~/jdk.tar.gz` even when it was a Java 11 archive, then `extractall` into `~/jdk` overwrote locked `jdk-11*` files → `PermissionError` on cluster accounts without sudo.

## Fix (1.4.1)

- Detect archive top-level dir; re-download when mismatched for Temurin 17.
- Move aside other `~/jdk/jdk-*` homes before extract.
- Clearer PermissionError guidance.
