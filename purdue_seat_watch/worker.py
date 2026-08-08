from __future__ import annotations

import logging
import os
import time

from purdue_seat_watch import banner
from purdue_seat_watch.db import DbSeatStateStore, SessionLocal, get_unique_courses, init_db
from purdue_seat_watch.emailer import EmailNotifier
from purdue_seat_watch.watcher import SeatWatcher, Watch, WatcherConfig

logger = logging.getLogger(__name__)


def build_watcher(interval_seconds: int) -> SeatWatcher:
    courses = get_unique_courses(SessionLocal)
    watches = tuple(Watch(term=t, subject=s, course_number=c) for (t, s, c) in courses)
    config = WatcherConfig(watches=watches, interval_seconds=interval_seconds)
    notifier = EmailNotifier(SessionLocal)
    store = DbSeatStateStore(SessionLocal)
    return SeatWatcher(config, notifier, banner, last_remaining=store)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    init_db()
    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "90"))
    while True:
        watcher = build_watcher(interval)  # rebuilt each cycle so new signups are picked up without a restart
        if watcher.watches:
            watcher.check_once()
        else:
            logger.info("No active subscriptions yet; nothing to poll.")
        time.sleep(interval)


if __name__ == "__main__":
    run()
