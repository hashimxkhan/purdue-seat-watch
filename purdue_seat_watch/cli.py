from __future__ import annotations

import argparse
import logging
import sys

from purdue_seat_watch import banner
from purdue_seat_watch.config import ConfigError, load_config
from purdue_seat_watch.notify import build_notifier
from purdue_seat_watch.watcher import SeatWatcher, Watch, WatcherConfig


def _cmd_watch(args: argparse.Namespace) -> int:
    try:
        config, notifier_name = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    notifier = build_notifier(notifier_name)
    watcher = SeatWatcher(config, notifier, banner)

    if args.once:
        watcher.check_once()
        return 0

    print(f"Watching {len(config.watches)} course(s), checking every {config.interval_seconds}s. Ctrl+C to stop.")
    try:
        watcher.run_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    config = WatcherConfig(
        watches=(Watch(term=args.term, subject=args.subject, course_number=args.course, section=args.section),)
    )
    notifier = build_notifier("console")
    watcher = SeatWatcher(config, notifier, banner)
    watcher.check_once()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="purdue-seat-watch")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    watch_parser = subparsers.add_parser("watch", help="run the watcher against a YAML config")
    watch_parser.add_argument("config", help="path to a watch-list YAML file")
    watch_parser.add_argument("--once", action="store_true", help="check once and exit instead of looping")
    watch_parser.set_defaults(func=_cmd_watch)

    check_parser = subparsers.add_parser("check", help="one-off seat check for a single course, no config needed")
    check_parser.add_argument("--term", required=True, help="Banner term code, e.g. 202710")
    check_parser.add_argument("--subject", required=True, help="subject code, e.g. CS")
    check_parser.add_argument("--course", required=True, help="course number, e.g. 50200")
    check_parser.add_argument("--section", default=None, help="optional section code, e.g. LE1")
    check_parser.set_defaults(func=_cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
