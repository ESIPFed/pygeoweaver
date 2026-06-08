"""
Tests for pygeoweaver server start/stop lifecycle.
"""
from unittest.mock import patch

from pygeoweaver import start, stop
from pygeoweaver.server import show


@patch("pygeoweaver.server._wait_for_geoweaver_shutdown", return_value=True)
@patch("pygeoweaver.server.find_geoweaver_processes", return_value=[])
@patch("pygeoweaver.server.maintain_h2_database_on_stop", return_value=True)
@patch("pygeoweaver.server.prepare_h2_database_for_start", return_value=True)
@patch("pygeoweaver.server.check_geoweaver_status", return_value=False)
@patch("pygeoweaver.server.start_on_mac_linux")
@patch("pygeoweaver.server.check_os", return_value=2)
@patch("pygeoweaver.server.download_geoweaver_jar")
@patch("pygeoweaver.server.check_java")
def test_server_start_stop(
    mock_java,
    mock_download,
    mock_os,
    mock_start_mac,
    mock_status,
    mock_prepare,
    mock_maintain,
    mock_find_procs,
    mock_wait_shutdown,
):
    """Start must run H2 prep then platform start; stop must run H2 maintenance."""
    start(exit_on_finish=False)
    mock_prepare.assert_called_once()
    mock_start_mac.assert_called_once_with(
        force_restart=False,
        force_download=False,
        exit_on_finish=False,
    )

    stop(exit_on_finish=False)
    mock_maintain.assert_called()
    mock_wait_shutdown.assert_called()


def test_windows():
    with patch("pygeoweaver.server.check_os", return_value=3):
        with patch("pygeoweaver.server.check_geoweaver_status", return_value=False):
            with patch("pygeoweaver.server.download_geoweaver_jar"):
                with patch("pygeoweaver.server.check_java"):
                    with patch("pygeoweaver.server.prepare_h2_database_for_start", return_value=True):
                        with patch("pygeoweaver.server.start_on_windows") as mock_start_win:
                            start(exit_on_finish=False)
                            mock_start_win.assert_called_once()

                    with patch("pygeoweaver.server.stop_on_windows") as mock_stop_win:
                        stop(exit_on_finish=False)
                        mock_stop_win.assert_called_once()


def test_show_gui():
    with patch("pygeoweaver.webbrowser.open") as mock_browser_open:
        show()
        mock_browser_open.assert_called_once()

        with patch("pygeoweaver.server.check_ipython") as mock_checkipython:
            mock_checkipython.return_value = True
            show()
            mock_browser_open.assert_called_once()
