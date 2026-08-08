from unittest.mock import patch

import pytest

from purdue_seat_watch.notify import ConsoleNotifier, MacOSNotifier, build_notifier


def test_console_notifier_prints(capsys):
    ConsoleNotifier().notify("Title", "Message")
    out = capsys.readouterr().out
    assert "Title" in out
    assert "Message" in out


def test_macos_notifier_invokes_osascript():
    with patch("purdue_seat_watch.notify.subprocess.run") as mock_run:
        MacOSNotifier().notify("Seat open", "3 seats available")

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert "Seat open" in args[2]
    assert "3 seats available" in args[2]


def test_macos_notifier_escapes_quotes_safely():
    with patch("purdue_seat_watch.notify.subprocess.run") as mock_run:
        MacOSNotifier().notify('Title with "quotes"', "fine")

    script = mock_run.call_args[0][0][2]
    assert '\\"quotes\\"' in script


def test_build_notifier_known_names():
    assert isinstance(build_notifier("console"), ConsoleNotifier)
    assert isinstance(build_notifier("macos"), MacOSNotifier)


def test_build_notifier_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown notifier"):
        build_notifier("carrier-pigeon")
