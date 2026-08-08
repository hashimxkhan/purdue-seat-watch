from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotifyEvent:
    """Structured context alongside title/message, for notifiers that need to look up
    who cares about this specific section (e.g. querying subscribers by course/section)."""

    term: str
    subject: str
    course_number: str
    section_code: str
    crn: str
    remaining: int
    capacity: int


class Notifier(Protocol):
    def notify(self, title: str, message: str, *, event: NotifyEvent | None = None) -> None: ...


class ConsoleNotifier:
    """Prints to stdout. Always works; useful as a fallback and in tests."""

    def notify(self, title: str, message: str, *, event: NotifyEvent | None = None) -> None:
        print(f"[NOTIFY] {title}: {message}")


class MacOSNotifier:
    """Fires a native notification via osascript. macOS only."""

    def __init__(self, sound: str = "Glass"):
        self.sound = sound

    def notify(self, title: str, message: str, *, event: NotifyEvent | None = None) -> None:
        script = (
            f"display notification {_applescript_string(message)} "
            f"with title {_applescript_string(title)} "
            f"sound name {_applescript_string(self.sound)}"
        )
        subprocess.run(["osascript", "-e", script], check=False)


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_NOTIFIERS = {
    "console": ConsoleNotifier,
    "macos": MacOSNotifier,
}


def build_notifier(name: str) -> Notifier:
    try:
        return _NOTIFIERS[name]()
    except KeyError as exc:
        supported = ", ".join(sorted(_NOTIFIERS))
        raise ValueError(f"Unknown notifier {name!r}; expected one of: {supported}") from exc
