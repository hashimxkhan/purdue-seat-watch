# purdue-seat-watch

Watches Purdue's Banner class schedule and notifies you the moment a full
course opens up a seat.

## How it works

Purdue runs classic Ellucian Banner 8. Its normal "Look Up Classes" search
requires a myPurdue login, but Banner also exposes an older, unauthenticated
"unsec" (unsecured) search used for public catalog browsing:

- `bwckschd.p_get_crse_unsec` — search sections by term/subject/course number, no login.
- `bwckschd.p_disp_detail_sched` — per-CRN detail page that includes live
  `Capacity / Actual / Remaining` seat counts, also no login.

Neither endpoint needs credentials, cookies, or JavaScript — they're plain
server-rendered HTML forms. This tool POSTs/GETs them directly and parses the
response tables with BeautifulSoup. No myPurdue account is ever touched.


## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick check (no config needed)

```bash
purdue-seat-watch check --term 202710 --subject CS --course 50200
```

Term codes: Banner encodes Fall under the *next* calendar year, Spring/Summer
under the current one — Fall 2026 is `202710`, Spring 2026 is `202620`,
Summer 2026 is `202630`. (`purdue_seat_watch.term.term_code(year, season)`
computes this if you'd rather not hardcode it.)

## Watching courses continuously

Copy `watches.example.yaml` to `watches.yaml` and edit it:

```yaml
interval_seconds: 60
notifier: macos # or "console"

watches:
  - term: "202710"
    subject: CS
    course_number: "18000" # watches every section found

  - term: "202710"
    subject: CS
    course_number: "50200"
    section: LE1 # watches only this section
```

Then:

```bash
purdue-seat-watch watch watches.yaml       # runs forever, Ctrl+C to stop
purdue-seat-watch watch watches.yaml --once # single pass, useful for testing
```

Notifications are edge-triggered: you're notified when a watched section goes
from 0 remaining (or hasn't been checked yet) to >0. Once a section is known
to be open, it won't re-notify on every poll — but if it closes and reopens
later, you'll get notified again. **On the very first run, any section that's
already open counts as newly opened**, so expect a notification for it right away.

## Running in the background

Nothing here is macOS/launchd-specific except the `macos` notifier — swap in
`console` (or add your own `Notifier` in `notify.py`, e.g. email/webhook) to
run it anywhere. See `notify.py` for the `Notifier` protocol.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Fixtures under `tests/fixtures/` are real captured Banner responses (plus a
couple of hand-edited variants for edge cases like a full course), so the
parser tests run offline and don't depend on Purdue's servers or any
particular semester's data staying available.

## Not affiliated with Purdue

This talks to public, unauthenticated Banner endpoints only. It doesn't log
in, doesn't touch your student account, and isn't produced or endorsed by
Purdue University. Be a reasonable citizen with your polling interval.
