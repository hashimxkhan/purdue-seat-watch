from purdue_seat_watch.models import Section, SeatInfo
from purdue_seat_watch.notify import NotifyEvent
from purdue_seat_watch.watcher import SeatWatcher, Watch, WatcherConfig


def _seats(remaining: int, capacity: int = 30) -> SeatInfo:
    return SeatInfo(
        capacity=capacity,
        actual=capacity - remaining,
        remaining=remaining,
        waitlist_capacity=0,
        waitlist_actual=0,
        waitlist_remaining=0,
    )


class FakeBanner:
    """Test double: seat readings are consumed one-by-one per CRN, in order."""

    def __init__(self, sections: list[Section] | None = None, seat_sequences: dict[str, list[SeatInfo]] | None = None):
        self.sections = sections or []
        self._seat_sequences = {crn: list(seq) for crn, seq in (seat_sequences or {}).items()}
        self.search_calls = 0

    def search_sections(self, term, subject, course_number):
        self.search_calls += 1
        return self.sections

    def get_seat_info(self, term, crn):
        queue = self._seat_sequences[crn]
        if len(queue) > 1:
            return queue.pop(0)
        return queue[0]  # keep returning the last value once exhausted


class RecordingNotifier:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.events = []

    def notify(self, title: str, message: str, *, event=None) -> None:
        self.calls.append((title, message))
        self.events.append(event)


def _section(crn: str, section_code: str = "001") -> Section:
    return Section(crn=crn, subject="CS", course_number="50200", section_code=section_code, title="Some Course")


def test_notifies_once_when_seat_opens_up():
    banner = FakeBanner(sections=[_section("111")], seat_sequences={"111": [_seats(0), _seats(8)]})
    notifier = RecordingNotifier()
    watcher = SeatWatcher(WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)), notifier, banner)

    watcher.check_once()  # remaining=0, no notification yet
    assert notifier.calls == []

    watcher.check_once()  # remaining=8, transitioned from closed -> open
    assert len(notifier.calls) == 1
    assert "CS 50200-001" in notifier.calls[0][0]


def test_does_not_renotify_while_still_open():
    banner = FakeBanner(sections=[_section("111")], seat_sequences={"111": [_seats(5), _seats(5), _seats(5)]})
    notifier = RecordingNotifier()
    watcher = SeatWatcher(WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)), notifier, banner)

    watcher.check_once()
    watcher.check_once()
    watcher.check_once()

    assert len(notifier.calls) == 1


def test_renotifies_after_seat_closes_and_reopens():
    banner = FakeBanner(
        sections=[_section("111")],
        seat_sequences={"111": [_seats(8), _seats(0), _seats(3)]},
    )
    notifier = RecordingNotifier()
    watcher = SeatWatcher(WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)), notifier, banner)

    watcher.check_once()  # opens -> notify #1
    watcher.check_once()  # closes -> no notify
    watcher.check_once()  # reopens -> notify #2

    assert len(notifier.calls) == 2


def test_section_filter_only_checks_matching_section():
    banner = FakeBanner(
        sections=[_section("111", "001"), _section("222", "002")],
        seat_sequences={"111": [_seats(0)], "222": [_seats(9)]},
    )
    notifier = RecordingNotifier()
    watch = Watch(term="202710", subject="CS", course_number="50200", section="002")
    watcher = SeatWatcher(WatcherConfig(watches=(watch,)), notifier, banner)

    watcher.check_once()

    assert len(notifier.calls) == 1
    assert "002" in notifier.calls[0][0]


def test_sections_filter_checks_the_union_of_requested_sections():
    banner = FakeBanner(
        sections=[_section("111", "001"), _section("222", "002"), _section("333", "003")],
        seat_sequences={"111": [_seats(0)], "222": [_seats(9)], "333": [_seats(2)]},
    )
    notifier = RecordingNotifier()
    watch = Watch(term="202710", subject="CS", course_number="50200", sections=frozenset({"002", "003"}))
    watcher = SeatWatcher(WatcherConfig(watches=(watch,)), notifier, banner)

    watcher.check_once()

    notified_sections = {event.section_code for event in notifier.events}
    assert notified_sections == {"002", "003"}  # not "001" -- wasn't in the requested set


def test_explicit_crns_skip_the_section_search():
    banner = FakeBanner(seat_sequences={"999": [_seats(1)]})
    notifier = RecordingNotifier()
    watch = Watch(term="202710", subject="CS", course_number="50200", crns=("999",))
    watcher = SeatWatcher(WatcherConfig(watches=(watch,)), notifier, banner)

    watcher.check_once()

    assert banner.search_calls == 0
    assert len(notifier.calls) == 1


def test_notify_receives_a_structured_event():
    banner = FakeBanner(sections=[_section("111")], seat_sequences={"111": [_seats(0), _seats(8)]})
    notifier = RecordingNotifier()
    watcher = SeatWatcher(WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)), notifier, banner)

    watcher.check_once()
    watcher.check_once()

    assert notifier.events == [NotifyEvent(
        term="202710", subject="CS", course_number="50200", section_code="001",
        crn="111", remaining=8, capacity=30,
    )]


def test_last_remaining_store_can_be_injected():
    store: dict[str, int] = {"111": 5}  # pre-seeded as already open, e.g. from a persisted store
    banner = FakeBanner(sections=[_section("111")], seat_sequences={"111": [_seats(5)]})
    notifier = RecordingNotifier()
    watcher = SeatWatcher(
        WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)),
        notifier, banner, last_remaining=store,
    )

    watcher.check_once()

    assert notifier.calls == []  # already open per the injected store, so no edge transition
    assert store["111"] == 5


def test_request_delay_sleeps_between_sections_but_not_before_the_first(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("purdue_seat_watch.watcher.time.sleep", lambda s: sleeps.append(s))

    banner = FakeBanner(
        sections=[_section("111", "001"), _section("222", "002"), _section("333", "003")],
        seat_sequences={"111": [_seats(0)], "222": [_seats(0)], "333": [_seats(0)]},
    )
    notifier = RecordingNotifier()
    watcher = SeatWatcher(
        WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)),
        notifier, banner, request_delay_seconds=0.3,
    )

    watcher.check_once()

    assert sleeps == [0.3, 0.3]  # one fewer than the number of sections checked


def test_a_failing_crn_does_not_stop_other_watches_from_being_checked():
    class FlakyBanner(FakeBanner):
        def get_seat_info(self, term, crn):
            if crn == "bad":
                raise RuntimeError("boom")
            return super().get_seat_info(term, crn)

    banner = FlakyBanner(
        sections=[_section("bad"), _section("good")],
        seat_sequences={"good": [_seats(4)]},
    )
    notifier = RecordingNotifier()
    watcher = SeatWatcher(WatcherConfig(watches=(Watch(term="202710", subject="CS", course_number="50200"),)), notifier, banner)

    watcher.check_once()

    assert len(notifier.calls) == 1
