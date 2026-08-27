"""Tests for H2 safety-backup listing and cleanup."""

import os
from pathlib import Path

from click.testing import CliRunner

from pygeoweaver.__main__ import geoweaver
from pygeoweaver.h2_utils import cleanup_h2_backups, format_bytes, list_h2_backups


def _make_backup(root: Path, name: str, marker: bool = False) -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "original").mkdir()
    (path / "original" / "gw.mv.db").write_bytes(b"x" * 1000)
    if marker:
        (path / ".in_progress").write_text("1")
    return path


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert "KB" in format_bytes(2048)


def test_list_and_cleanup_keep(tmp_path):
    root = tmp_path / "h2_backups"
    root.mkdir()
    older = _make_backup(root, "geoweaver_h2_backup_old")
    newer = _make_backup(root, "geoweaver_h2_backup_new")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    listed = list_h2_backups(str(root))
    assert len(listed) == 2
    assert listed[0]["name"] == "geoweaver_h2_backup_new"

    result = cleanup_h2_backups(keep=1, backup_root=str(root))
    assert len(result["deleted"]) == 1
    assert older.as_posix() in result["deleted"][0] or str(older) in result["deleted"][0]
    assert newer.exists()
    assert not older.exists()


def test_cleanup_skips_in_progress(tmp_path):
    root = tmp_path / "h2_backups"
    root.mkdir()
    busy = _make_backup(root, "geoweaver_h2_backup_busy", marker=True)
    result = cleanup_h2_backups(remove_all=True, backup_root=str(root))
    assert str(busy) in result["skipped_in_progress"]
    assert busy.exists()

    result = cleanup_h2_backups(
        remove_all=True, backup_root=str(root), allow_in_progress=True
    )
    assert not busy.exists()


def test_cleanup_path_must_be_under_root(tmp_path):
    root = tmp_path / "h2_backups"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_text("nope")
    result = cleanup_h2_backups(paths=[str(outside)], backup_root=str(root))
    assert result["deleted"] == []
    assert outside.exists()


def test_cli_list(tmp_path, monkeypatch):
    root = tmp_path / "h2_backups"
    root.mkdir()
    _make_backup(root, "geoweaver_h2_backup_a")
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_cleanh2backups.get_h2_backup_base_dir",
        lambda: str(root),
    )
    monkeypatch.setattr(
        "pygeoweaver.h2_utils.get_h2_backup_base_dir",
        lambda: str(root),
    )
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["cleanh2backups", "--list"])
    assert result.exit_code == 0
    assert "geoweaver_h2_backup_a" in result.output


def test_cli_keep_yes(tmp_path, monkeypatch):
    root = tmp_path / "h2_backups"
    root.mkdir()
    old = _make_backup(root, "geoweaver_h2_backup_old")
    new = _make_backup(root, "geoweaver_h2_backup_new")
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    monkeypatch.setattr(
        "pygeoweaver.commands.pgw_cleanh2backups.get_h2_backup_base_dir",
        lambda: str(root),
    )
    monkeypatch.setattr(
        "pygeoweaver.h2_utils.get_h2_backup_base_dir",
        lambda: str(root),
    )
    runner = CliRunner()
    result = runner.invoke(geoweaver, ["cleanh2backups", "--keep", "1", "-y"])
    assert result.exit_code == 0
    assert new.exists()
    assert not old.exists()
