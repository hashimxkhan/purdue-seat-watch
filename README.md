# purdue-seat-watch

Watches Purdue's Banner class schedule and notifies you the moment a full
course opens up a seat.

## How it works

Purdue runs classic Ellucian Banner 8. Its normal "Look Up Classes" search
requires a myPurdue login, but Banner also exposes an older, unauthenticated
search used for public catalog browsing:

- `bwckschd.p_get_crse_unsec` — search sections by term/subject/course number, no login.
- `bwckschd.p_disp_detail_sched` — per-CRN detail page that includes live
  `Capacity / Actual / Remaining` seat counts, also no login.

Neither endpoint needs credentials or cookies, they're plain
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

Term codes: Banner encodes Fall under the next calendar year, Spring/Summer
under the current one so Fall 2026 is `202710`, Spring 2026 is `202620`,
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
from 0 remaining (or hasn't been checked yet) to  greater than 0. Once a section is known
to be open, it won't re-notify on every poll but if it closes and reopens
later, you'll get notified again. **On the very first run, any section that's
already open counts as newly opened**, so expect a notification for it right away.

## Running in the background

The `macos` notifier is the only macOS-specific piece so you can just swap in `console`
(or add your own `Notifier` in `notify.py`, e.g. email/webhook) to run this
anywhere. By default, though, `purdue-seat-watch watch` just runs in the
foreground of whatever terminal launched it and stops if that terminal closes.

To have it run persistently in the background on macOS, install it as a
`launchd` agent:

```bash
cp watches.example.yaml watches.yaml   # edit with the courses you want
pip install -e .                       # if you haven't already
scripts/install_launchd.sh
```

> **Don't keep this repo under `~/Downloads`, `~/Desktop`, or `~/Documents`.**
> macOS sandboxes those three folders (TCC); your terminal has been granted
> access for interactive use, but a headless `launchd` agent hasn't, and the
> venv's Python will fail to start with a `PermissionError` on `pyvenv.cfg`.
> Clone/move the repo somewhere else in your home directory (e.g.
> `~/purdue-seat-watch`) before installing the agent. If you do move it after
> the venv already exists, delete and recreate `.venv` — it has the old
> absolute path baked into its shebangs and `pyvenv.cfg`.

This copies `launchd/com.purdueseatwatch.watch.plist.example` to
`~/Library/LaunchAgents/`, points it at this repo's venv and `watches.yaml`,
and `launchctl load`s it. The service then:

- starts automatically on login (`RunAtLoad`) — this persists across
  reboots, so you never need to rerun the install script yourself; the only
  thing that doesn't survive a reboot/sleep is Banner-polling itself, since
  nothing runs while your Mac is off or asleep (there's no cloud component,
  it's local to this machine)
- restarts if it crashes, with a 30s throttle to avoid crash-loops
- logs to `logs/watch.out.log` and `logs/watch.err.log` in this repo — in
  practice nearly everything (including normal per-check status lines) ends
  up in `.err.log`, since Python's `logging` module writes to stderr by
  default; that's expected, not a sign something's broken

To stop and remove it:

```bash
scripts/uninstall_launchd.sh
```

To just check on it manually: `launchctl list | grep purdueseatwatch`
(a real PID in the second column means it's running).

If you're not on macOS, or want something lighter than launchd, running it
under `tmux`/`screen`, or with `nohup purdue-seat-watch watch watches.yaml &`,
works too — it just won't survive a reboot or auto-restart on crash.

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
Purdue University. Be reasonable with your polling interval.
