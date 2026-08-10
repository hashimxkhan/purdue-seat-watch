from __future__ import annotations

import logging
import os
import time

from purdue_seat_watch import banner
from purdue_seat_watch.db import DbSeatStateStore, SessionLocal, get_unique_course_crns, init_db
from purdue_seat_watch.emailer import EmailNotifier
from purdue_seat_watch.watcher import SeatWatcher, Watch, WatcherConfig

logger = logging.getLogger(__name__)


def build_watcher(interval_seconds: int, *, request_delay_seconds: float = 0) -> SeatWatcher:
    course_crns = get_unique_course_crns(SessionLocal)
    # crns= bypasses Banner's section-search entirely (see watcher.resolve_sections) --
    # the worker's only remaining Banner touchpoint is the actual seat-count check,
    # which is unavoidable since live seat data exists nowhere else.
    watches = tuple(
        Watch(term=t, subject=s, course_number=c, crns=tuple(crns))
        for (t, s, c), crns in course_crns.items()
    )
    config = WatcherConfig(watches=watches, interval_seconds=interval_seconds)
    notifier = EmailNotifier(SessionLocal)
    store = DbSeatStateStore(SessionLocal)
    return SeatWatcher(config, notifier, banner, last_remaining=store, request_delay_seconds=request_delay_seconds)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    init_db()
    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "90"))
    request_delay = float(os.environ.get("REQUEST_DELAY_SECONDS", "0.3"))
    while True:
        watcher = build_watcher(interval, request_delay_seconds=request_delay)  # rebuilt each cycle so new signups are picked up without a restart
        if watcher.watches:
            watcher.check_once()
        else:
            logger.info("No active subscriptions yet; nothing to poll.")
        time.sleep(interval)


if __name__ == "__main__":
    run()
