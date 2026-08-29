"""Tests for Java 17+ requirement and runtime jar channel selection."""

from unittest.mock import patch

from pygeoweaver.constants import (
    GEOWEAVER_JAR_CHANNEL_LATEST,
    GEOWEAVER_JAR_CHANNEL_LEGACY,
    GEOWEAVER_LEGACY_JAR_URL,
    GEOWEAVER_URL,
)
from pygeoweaver.jdk_utils import (
    GeoweaverRuntime,
    ensure_geoweaver_runtime,
    get_java_major_version,
    print_legacy_jar_fallback_message,
    print_unsupported_java_warning,
)


def test_get_java_major_version_parses_current_runtime():
    major = get_java_major_version()
    assert major is None or isinstance(major, int)


def test_print_unsupported_java_warning_mentions_legacy(capsys):
    print_unsupported_java_warning(11)
    out = capsys.readouterr().out
    assert "Unsupported Java version" in out
    assert "17" in out
    assert "2.1.x" in out
    assert "no longer supported" in out.lower() or "no longer" in out


def test_print_legacy_jar_fallback_message(capsys):
    print_legacy_jar_fallback_message(11)
    out = capsys.readouterr().out
    assert "legacy" in out.lower()
    assert "2.1.x" in out
    assert GEOWEAVER_LEGACY_JAR_URL in out


def test_ensure_runtime_uses_legacy_for_unmanaged_old_jdk():
    import pygeoweaver.jdk_utils as jdk_utils

    jdk_utils._runtime_cache = None
    fake = GeoweaverRuntime("java", 11, GEOWEAVER_JAR_CHANNEL_LEGACY, GEOWEAVER_LEGACY_JAR_URL)

    with patch.object(jdk_utils, "find_managed_java_bin", return_value=None), patch.object(
        jdk_utils, "is_java_installed", return_value=True
    ), patch.object(jdk_utils, "get_java_bin_path", return_value="java"), patch.object(
        jdk_utils, "get_java_major_version", return_value=11
    ), patch.object(jdk_utils, "is_pygeoweaver_managed_path", return_value=False), patch.object(
        jdk_utils, "has_managed_jdk_install", return_value=False
    ), patch.object(jdk_utils, "print_legacy_jar_fallback_message"):
        runtime = ensure_geoweaver_runtime(force_recheck=True)

    assert runtime.channel == GEOWEAVER_JAR_CHANNEL_LEGACY
    assert runtime.jar_url == GEOWEAVER_LEGACY_JAR_URL
    assert runtime.major == 11
    jdk_utils._runtime_cache = None
    _ = fake  # silence unused in some linters


def test_ensure_runtime_bumps_managed_old_jdk():
    import pygeoweaver.jdk_utils as jdk_utils

    jdk_utils._runtime_cache = None

    with patch.object(jdk_utils, "find_managed_java_bin", return_value=None), patch.object(
        jdk_utils, "is_java_installed", return_value=True
    ), patch.object(jdk_utils, "get_java_bin_path", return_value="/home/u/jdk/jdk-11/bin/java"), patch.object(
        jdk_utils, "get_java_major_version", side_effect=[11, 17]
    ), patch.object(jdk_utils, "is_pygeoweaver_managed_path", return_value=True), patch.object(
        jdk_utils, "has_managed_jdk_install", return_value=True
    ), patch.object(
        jdk_utils, "_install_and_activate_jdk17", return_value="/home/u/jdk/jdk-17/bin/java"
    ) as install_mock:
        runtime = ensure_geoweaver_runtime(force_recheck=True)

    install_mock.assert_called_once()
    assert runtime.channel == GEOWEAVER_JAR_CHANNEL_LATEST
    assert runtime.jar_url == GEOWEAVER_URL
    assert runtime.managed is True
    assert runtime.major == 17
    jdk_utils._runtime_cache = None


def test_ensure_runtime_latest_when_java17():
    import pygeoweaver.jdk_utils as jdk_utils

    jdk_utils._runtime_cache = None

    with patch.object(jdk_utils, "find_managed_java_bin", return_value=None), patch.object(
        jdk_utils, "is_java_installed", return_value=True
    ), patch.object(jdk_utils, "get_java_bin_path", return_value="java"), patch.object(
        jdk_utils, "get_java_major_version", return_value=17
    ), patch.object(jdk_utils, "is_pygeoweaver_managed_path", return_value=False), patch.object(
        jdk_utils, "has_managed_jdk_install", return_value=False
    ):
        runtime = ensure_geoweaver_runtime(force_recheck=True)

    assert runtime.channel == GEOWEAVER_JAR_CHANNEL_LATEST
    assert runtime.jar_url == GEOWEAVER_URL
    jdk_utils._runtime_cache = None
