# purdue-seat-watch

Watches Purdue's Banner class schedule and tells you the moment a full
course opens up a seat.

**Live site:** [purdue-seat-watch-production.up.railway.app](https://purdue-seat-watch-production.up.railway.app/)
— sign up with a `@purdue.edu` email and a course/section, get emailed when a seat opens.

This repo actually ships two ways to use it, sharing the same Banner-scraping
core:

1. **The hosted site above** — a multi-user product (FastAPI + Postgres
   + a background poller + email via Resend), hosted on Railway.
2. **A standalone CLI** — for running it yourself, locally, watching your own
   list of courses with no server, no signup, no other users involved.

Pick whichever fits — the sections below cover both.

## How it works

Purdue runs classic Ellucian Banner 8. Its normal "Look Up Classes" search
requires a myPurdue login, but Banner also exposes an older, unauthenticated
search used for public catalog browsing:

- `bwckschd.p_get_crse_unsec` — search sections by term/subject/course number, no login.
- `bwckschd.p_disp_detail_sched` — per-CRN detail page with live `Capacity / Actual / Remaining` seat counts, also no login. **This is the only thing that has to come from Banner** — no other public source has live seat availability.

Neither endpoint needs credentials or cookies — they're plain
server-rendered HTML forms. This tool GETs them directly and parses the
response tables with BeautifulSoup ([banner.py](purdue_seat_watch/banner.py)). No myPurdue account is ever touched.

For everything *except* live seat counts — which sections exist, their CRNs,
meeting days/times, instructors — the hosted site instead queries
[Purdue.io](https://github.com/Purdue-io/PurdueApi) (`api.purdue.io`), a
third-party, open-source catalog mirror ([purdueio.py](purdue_seat_watch/purdueio.py)). This keeps the highest-volume,
bursty traffic (the signup form's live section lookup, firing on every
keystroke from every visitor) off Banner entirely — Banner is only ever hit
for the actual per-CRN seat-count poll, which is slow, predictable, and
unavoidable.

Both usage paths share the edge-triggered "only notify on closed→open" logic
in [watcher.py](purdue_seat_watch/watcher.py) — notifications fire once when a watched section flips from 0
remaining (or unseen) to available, not on every single poll while it stays
open. If it closes and reopens later, you're notified again. **On the very
first check, an already-open section counts as newly opened**, so expect an
immediate notification for it.

---

## Using the hosted site

1. Go to [the live site](https://purdue-seat-watch-production.up.railway.app/).
2. Enter your `@purdue.edu` email, the term (year + season), subject, and course number.
3. Pick a **section** from the list — as you type the subject/course number,
   real sections for that course show up as clickable suggestions, each
   showing its type (Lecture/Lab/etc.), meeting days/time, and instructor
   when available. The picker is click-only by design (the underlying field
   is read-only); there's no way to type a section in manually, since a typo
   or a pasted "CRN-section" string from Purdue's own tools would otherwise
   silently create a subscription that can never match anything.
4. Submit. You'll get an email at that address the moment that section shows
   an open seat.

A few things worth knowing:

- **A specific section is required**, and identified internally by CRN, not
  a human-readable section code. Unlike the CLI (which can watch "every
  section" of a course), the hosted site always watches specific sections —
  this keeps the background poller from hitting Banner once per section of
  every course, for every course anyone's watching.
- **Limits while this is small**: 200 subscribers total, 3 sections watched
  per email address.
- **No unsubscribe UI yet** — if you want to stop watching something, that's
  a manual DB cleanup for now, not a self-service button.
- Not affiliated with Purdue (see below) — it only talks to the public class
  schedule pages above, never your myPurdue account, and never asks for a
  password.

### Self-hosting the full service

The hosted site runs as two processes sharing one Postgres database:

```
purdue_seat_watch/web.py      — FastAPI signup site (the form + /subscribe + a
                                  live /api/sections lookup, backed by Purdue.io,
                                  for the JS widget)
purdue_seat_watch/purdueio.py — client for api.purdue.io: section/meeting-time
                                  lookups that don't need to touch Banner at all
purdue_seat_watch/worker.py   — background poller: coalesces every subscriber's
                                  watched CRNs into one Watch per course, using
                                  watcher.py's crns= bypass so Banner is only
                                  ever hit for the actual seat-count check;
                                  persists seat state in Postgres so a restart
                                  doesn't re-fire stale notifications
purdue_seat_watch/emailer.py  — Resend-backed Notifier, looks up every
                                  subscriber watching a CRN (unique within a
                                  term) and emails each one
purdue_seat_watch/db.py       — SQLAlchemy models (Subscription, SeatState),
                                  Postgres in production, SQLite by default locally
```

**Local dev** (defaults to a local SQLite file, zero setup):

```bash
pip install -e ".[dev,web]"
uvicorn purdue_seat_watch.web:app --reload --port 8000   # terminal 1
python -m purdue_seat_watch.worker                        # terminal 2
```

**Deploying** (this repo is set up for Railway):

- `Dockerfile` — builds the image; Railway auto-detects and uses this over
  its zero-config builder (Railpack), which had trouble reliably installing
  this project's extras and locating console-script entry points at runtime.
- `Procfile` — documents the two process types (`web`, `worker`); on Railway,
  create two services from this repo, and explicitly set the `worker`
  service's Start Command to `python -m purdue_seat_watch.worker` (it
  otherwise defaults to the Dockerfile's `web` `CMD`).
- Add a Postgres database to the Railway project and link its `DATABASE_URL`
  to both services.
- Environment variables the **`worker`** service needs (`web` only needs `DATABASE_URL`):

  | Variable | Example | Notes |
  |---|---|---|
  | `DATABASE_URL` | (from Railway's Postgres) | `postgres://` is auto-rewritten to `postgresql://` |
  | `RESEND_API_KEY` | `re_...` | from resend.com |
  | `EMAIL_FROM` | `Purdue Seat Watch <notify@yourdomain.com>` | needs a verified Resend domain for real delivery; `onboarding@resend.dev` only delivers to your own Resend account email |
  | `POLL_INTERVAL_SECONDS` | `120` | default `90` |
  | `REQUEST_DELAY_SECONDS` | `0.3` | pause between per-section Banner calls within a poll cycle, so a course with many sections doesn't hammer Banner in a tight burst; default `0.3` |

- Set a spend/usage cap in Railway's billing settings before real traffic hits it.

**Upgrading an existing deployment from before the CRN migration?** `Subscription`'s
schema changed (`section` → `crn`, unique constraint now on `email, term, crn`).
There's no Alembic here (deliberate, given the project's size) — `init_db()`
only creates tables that don't exist yet, it won't alter an existing one.
Simplest fix, since this table only ever held disposable signup data anyway:
connect to the Postgres instance and run `DROP TABLE subscriptions;` before
the next deploy — `init_db()` recreates it with the new schema automatically
on the next `web`/`worker` startup. `seat_states` is unaffected, no action needed there.

---

## Running it yourself (CLI)

For personal use — no signup site, no other users, just you watching your
own list of courses locally.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Quick check (no config needed)

```bash
purdue-seat-watch check --term 202710 --subject CS --course 50200
```

Term codes: Banner encodes Fall under the next calendar year, Spring/Summer
under the current one, so Fall 2026 is `202710`, Spring 2026 is `202620`,
Summer 2026 is `202630`. (`purdue_seat_watch.term.term_code(year, season)`
computes this if you'd rather not hardcode it.)

### Watching courses continuously

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

### Running in the background

The `macos` notifier is the only macOS-specific piece, so you can swap in
`console` (or add your own `Notifier` in `notify.py`, e.g. email/webhook) to
run this anywhere. By default, though, `purdue-seat-watch watch` just runs in
the foreground of whatever terminal launched it and stops if that terminal
closes.

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

---

## Tests

```bash
pip install -e ".[dev,web]"
pytest
```

Fixtures under `tests/fixtures/` are real captured Banner responses (plus a
couple of hand-edited variants for edge cases like a full course), so the
parser tests run offline and don't depend on Purdue's servers or any
particular semester's data staying available. The web/worker/db tests run
against a temporary SQLite file, not a real Postgres or live network call.

## Not affiliated with Purdue

This talks to public, unauthenticated Banner endpoints only. It doesn't log
in, doesn't touch your student account, and isn't produced or endorsed by
Purdue University. Be reasonable with your polling interval.
