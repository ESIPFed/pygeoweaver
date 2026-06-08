import os

from pygeoweaver.h2_utils import (
    _append_missing_jdbc_params,
    ensure_h2_safe_datasource_url,
    get_safe_datasource_url_for_start,
    resolve_h2_db_path,
)


def test_append_missing_jdbc_params_adds_anti_bloat_settings():
    url = "jdbc:h2:file:/home/user/h2/gw"
    patched, changed = _append_missing_jdbc_params(url, {
        "RETENTION_TIME": "0",
        "AUTO_COMPACT_FILL_RATE": "0",
    })

    assert changed is True
    assert "RETENTION_TIME=0" in patched
    assert "AUTO_COMPACT_FILL_RATE=0" in patched


def test_append_missing_jdbc_params_is_idempotent():
    url = "jdbc:h2:file:/home/user/h2/gw;RETENTION_TIME=0;AUTO_COMPACT_FILL_RATE=0"
    patched, changed = _append_missing_jdbc_params(url, {
        "RETENTION_TIME": "0",
        "AUTO_COMPACT_FILL_RATE": "0",
        "DEFRAG_ALWAYS": "TRUE",
    })

    assert changed is True
    assert patched.count("RETENTION_TIME=0") == 1
    assert "DEFRAG_ALWAYS=TRUE" in patched


def test_ensure_h2_safe_datasource_url_updates_properties(tmp_path, monkeypatch):
    geoweaver_dir = tmp_path / "geoweaver"
    geoweaver_dir.mkdir()
    properties_path = geoweaver_dir / "application.properties"
    properties_path.write_text(
        "spring.datasource.url=jdbc:h2:file:/tmp/gw\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("pygeoweaver.h2_utils.get_home_dir", lambda: str(tmp_path))
    updated = ensure_h2_safe_datasource_url()

    assert updated is True
    content = properties_path.read_text(encoding="utf-8")
    assert "AUTO_COMPACT_FILL_RATE=0" in content
    assert "DEFRAG_ALWAYS=TRUE" in content


def test_get_safe_datasource_url_for_start_without_properties(tmp_path, monkeypatch):
    monkeypatch.setattr("pygeoweaver.h2_utils.get_home_dir", lambda: str(tmp_path))
    url = get_safe_datasource_url_for_start()

    assert url is not None
    assert "jdbc:h2:file:" in url
    assert "AUTO_COMPACT_FILL_RATE=0" in url


def test_resolve_h2_db_path_from_jdbc_url(monkeypatch):
    monkeypatch.setattr(
        "pygeoweaver.h2_utils.get_database_url_from_properties",
        lambda: "jdbc:h2:file:~/h2/gw;MODE=MySQL",
    )

    resolved = resolve_h2_db_path()

    assert os.path.isabs(resolved)
    assert resolved.endswith(os.path.join("h2", "gw"))


def test_promote_rebuilt_database_restores_on_failure(tmp_path):
    production_dir = tmp_path / "production"
    rebuilt_dir = tmp_path / "rebuilt"
    displaced_dir = tmp_path / "displaced"
    original_dir = tmp_path / "original"
    for directory in (production_dir, rebuilt_dir, displaced_dir, original_dir):
        directory.mkdir()

    (original_dir / "gw.mv.db").write_bytes(b"original-data")
    (production_dir / "gw.mv.db").write_bytes(b"original-data")

    from pygeoweaver.h2_utils import promote_rebuilt_database

    promoted = promote_rebuilt_database(
        str(production_dir),
        str(rebuilt_dir),
        str(displaced_dir),
        "gw",
        str(original_dir),
    )

    assert promoted is False
    assert (production_dir / "gw.mv.db").read_bytes() == b"original-data"
    assert (displaced_dir / "gw.mv.db").read_bytes() == b"original-data"


def test_needs_rebuild_uses_threshold(monkeypatch):
    import pygeoweaver.h2_utils as h2_utils

    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    assert h2_utils._needs_rebuild(1024, {}, force=False) is True
    assert h2_utils._needs_rebuild(100, {}, force=False) is False


def test_needs_compact_skips_small_and_huge_databases(monkeypatch):
    import pygeoweaver.h2_utils as h2_utils

    monkeypatch.setattr(h2_utils, "H2_COMPACT_MIN_MB", 50)
    monkeypatch.setattr(h2_utils, "H2_AUTO_REBUILD_THRESHOLD_MB", 1024)
    assert h2_utils._needs_compact(10, {}) is False
    assert h2_utils._needs_compact(2000, {}) is False
    assert h2_utils._needs_compact(200, {}) is True


def test_should_skip_recent_maintenance(monkeypatch):
    import pygeoweaver.h2_utils as h2_utils
    from datetime import datetime

    monkeypatch.setattr(h2_utils, "H2_MAINTENANCE_COOLDOWN_SECONDS", 300)
    state = {"last_maintenance_at": datetime.now().isoformat()}
    assert h2_utils._should_skip_recent_maintenance(state) is True
