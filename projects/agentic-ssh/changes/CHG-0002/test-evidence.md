# CHG-0002 — Test evidence (C5)

`pytest -q test` (macOS, Python 3.12, `.venv-agent`): **185 passed** (was 140; +45 in `test/test_agent_security.py`, 3 existing tests updated to the new behavior).

| Finding | Regression test(s) |
| --- | --- |
| SEC-001 | `test_start_child_runs_outside_agent_cwd`, `test_start_child_ignores_planted_module_in_cwd` (shows the hijack happens with the repo as cwd and not with the config dir) |
| SEC-002 / 005 / 011 | `test_jvm_starts_in_home_with_private_log_and_clean_env`, `test_child_env_drops_agent_secrets` |
| SEC-003 | `test_unknown_owner_blocks_automatic_token`, `test_discovered_url_is_checked_too`, `test_cmdline_port_is_not_verified`, `test_macos_owner_check_without_global_socket_table`, `test_nothing_listening_is_not_foreign` |
| SEC-004 | `test_login_on_foreign_listener_writes_token_file_without_storing` (password not sent without `--token-file`; token absent from output; file 0600), `test_login_refuses_foreign_default_port` |
| SEC-006 | `test_tar_extraction_blocks_traversal` (data filter and fallback; `../`, absolute, symlink), `test_download_rejects_bad_digest_and_http`, `test_every_managed_jdk_archive_has_a_pinned_digest`, JDK cache tests |
| SEC-007 | `test_json_output_escapes_terminal_controls`, `test_raw_text_sanitized_on_tty_only`, `test_guide_marks_server_text_untrusted` |
| SEC-008 | `test_ids_cannot_escape_their_path_segment` (7 cases; no request sent), `test_cli_bad_id_is_usage_error` |
| SEC-009 | `test_zero_interval_rejected`, `test_wait_run_never_busy_polls`, `test_login_ttl_range` |
| SEC-010 | `test_config_dir_mode_tightened`, `test_config_dir_owned_by_someone_else_refused`, `test_store_readable_by_others_is_fixed_and_foreign_store_ignored`, `test_store_write_does_not_follow_planted_symlink` |
| SEC-012 | `test_stale_lock_break_never_removes_a_fresh_lock` |
| SEC-013 | `test_bad_base_urls_rejected` (6 cases), `test_geoweaver_port_cannot_point_off_host`, `test_cookie_jar_never_sent_over_plain_http` |

Live read-only check against the user's own Geoweaver (8070): `gw agent status` → `baseUrlSource: discovered`, healthy, owner `me` via verified socket.
