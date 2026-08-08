from __future__ import annotations

from pathlib import Path

import yaml

from purdue_seat_watch.watcher import Watch, WatcherConfig


class ConfigError(Exception):
    pass


def load_config(path: str | Path) -> tuple[WatcherConfig, str]:
    """Parse a YAML watch-list file. Returns (WatcherConfig, notifier_name)."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level YAML in {path} must be a mapping.")

    watch_specs = raw.get("watches")
    if not watch_specs:
        raise ConfigError(f"{path} must define a non-empty 'watches' list.")

    watches = []
    for i, spec in enumerate(watch_specs):
        try:
            watches.append(
                Watch(
                    term=str(spec["term"]),
                    subject=str(spec["subject"]),
                    course_number=str(spec["course_number"]),
                    section=str(spec["section"]) if spec.get("section") is not None else None,
                    crns=tuple(str(c) for c in spec["crns"]) if spec.get("crns") else None,
                )
            )
        except KeyError as exc:
            raise ConfigError(f"watches[{i}] is missing required field {exc}") from exc

    interval_seconds = int(raw.get("interval_seconds", 60))
    notifier_name = str(raw.get("notifier", "console"))
    return WatcherConfig(watches=tuple(watches), interval_seconds=interval_seconds), notifier_name
