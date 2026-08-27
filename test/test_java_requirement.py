"""Tests for Java 17+ requirement messaging."""

from pygeoweaver.jdk_utils import get_java_major_version, print_unsupported_java_warning


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
