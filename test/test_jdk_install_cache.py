"""Tests for safe managed JDK install (stale ~/jdk.tar.gz / jdk-11 trees)."""

import io
import os
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pygeoweaver.jdk_utils import (
    archive_matches_jdk_version,
    archive_top_level_name,
    download_jdk_archive,
    managed_jdk_dir_name,
    move_aside_path,
    prepare_managed_jdk_root,
)


def _make_tar(path: Path, top_dir: str, inner_file: str = "bin/java"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        data = b"#!/bin/sh\n"
        info = tarfile.TarInfo(name=f"{top_dir}/{inner_file}")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def test_managed_jdk_dir_name():
    assert managed_jdk_dir_name("17.0.13-11") == "jdk-17.0.13+11"


def test_archive_matches_rejects_jdk11(tmp_path):
    archive = tmp_path / "jdk.tar.gz"
    _make_tar(archive, "jdk-11.0.18+10")
    assert archive_top_level_name(str(archive)) == "jdk-11.0.18+10"
    assert archive_matches_jdk_version(str(archive), "17.0.13-11") is False


def test_archive_matches_accepts_jdk17(tmp_path):
    archive = tmp_path / "jdk.tar.gz"
    _make_tar(archive, "jdk-17.0.13+11")
    assert archive_matches_jdk_version(str(archive), "17.0.13-11") is True


def test_download_jdk_archive_replaces_stale_jdk11(tmp_path):
    archive = tmp_path / "jdk.tar.gz"
    _make_tar(archive, "jdk-11.0.18+10")

    def fake_retrieve(url, filename):
        _make_tar(Path(filename), "jdk-17.0.13+11")

    with patch("pygeoweaver.jdk_utils.urllib.request.urlretrieve", side_effect=fake_retrieve):
        download_jdk_archive("https://example.invalid/jdk17.tar.gz", str(archive), "17.0.13-11")

    assert archive_matches_jdk_version(str(archive), "17.0.13-11")
    # Original stale file should have been moved aside
    backups = list(tmp_path.glob("jdk.tar.gz.bak.*"))
    assert backups, "expected stale archive to be moved aside"


def test_download_jdk_archive_keeps_matching_cache(tmp_path):
    archive = tmp_path / "jdk.tar.gz"
    _make_tar(archive, "jdk-17.0.13+11")
    mtime_before = archive.stat().st_mtime

    with patch("pygeoweaver.jdk_utils.urllib.request.urlretrieve") as retrieve:
        download_jdk_archive("https://example.invalid/jdk17.tar.gz", str(archive), "17.0.13-11")
        retrieve.assert_not_called()

    assert archive.stat().st_mtime == mtime_before


def test_prepare_managed_jdk_root_moves_aside_jdk11(tmp_path):
    root = tmp_path / "jdk"
    old = root / "jdk-11.0.18+10"
    old.mkdir(parents=True)
    (old / "bin").mkdir()
    (old / "bin" / "java").write_text("old")

    prepare_managed_jdk_root(str(root), "17.0.13-11")

    assert not old.exists()
    backups = list(root.glob("jdk-11.0.18+10.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "bin" / "java").read_text() == "old"


def test_move_aside_path_renames(tmp_path):
    target = tmp_path / "thing"
    target.write_text("x")
    backup = move_aside_path(str(target))
    assert backup is not None
    assert not target.exists()
    assert Path(backup).read_text() == "x"


def test_prepare_raises_when_rename_fails(tmp_path):
    root = tmp_path / "jdk"
    old = root / "jdk-11.0.18+10"
    old.mkdir(parents=True)

    with patch("pygeoweaver.jdk_utils.move_aside_path", side_effect=OSError("denied")):
        with pytest.raises(RuntimeError, match="Cannot move aside old managed JDK"):
            prepare_managed_jdk_root(str(root), "17.0.13-11")
