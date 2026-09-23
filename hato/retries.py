# -*- coding: utf-8 -*-
u"""
When hato has promised to look again -- written down so the tray can keep the
promise (RUNBOOK 8h).

    retries.save(db.retry_dues(lang))      # every real run, whoever started it
    dues = retries.load()                  # [epoch seconds], soonest first

===========================================================================
🚨 THE RETRY WORKED, AND NOTHING WAS GOING TO RUN IT
===========================================================================

The 24-hour retry is decided at the gate: a run AFTER the date looks again.
⛔ Nothing started that run. The title bar's *"runs automatically at 03:00"*
switch registered no task (D2, measured 2026-09-22: not one of 148 recorded
attempts is near 03:00), so the retry that fetched a subtitle on 09-21 happened
because a new download woke the tray, and the run it started was past the date.
With nothing arriving, a row promising *"retrying in 14h"* would have waited
for ever. (⭐ D2 is built since, 2026-09-23 -- `hato/schedule.py` registers the
daily run, which keeps a retry at its next start; the tray keeps it sooner.)

⭐ The tray is the one resident process, and it already wakes for arrivals;
this is the file that tells it when to wake for a promise. `watch.RetryClock`
reads it.

===========================================================================
⛔ STDLIB ONLY -- THE WATCHER IMPORTS THIS
===========================================================================

`tests/test_watch.py` walks the watcher's imports, and this module is one of
them: it brings in no toolkit, no pipeline and no state DB. The dates are READ
from the DB by the run (`StateDB.retry_dues`) and handed over.

⛔ NEVER RAISES, IN EITHER DIRECTION -- `lastrun`'s contract. A run that cannot
write this has still done its job, and a broken file is no dates, not a tray
that dies.
"""
from __future__ import print_function

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from hato import paths

#: The most dates kept, soonest first. ⚠ DISTINCT MINUTES (`save` rounds up), so
#: a run's burst of negatives -- recorded seconds apart -- is ONE date, and a
#: library's promises are dozens, not thousands.
KEEP = 1000

#: How many times a rename refused by a reader is tried (`save`).
_REPLACE_TRIES = 20


def _minute_up(stamp):
    u"""Epoch seconds -> the start of the NEXT whole minute (or this one, exactly).

    ⭐ A burst recorded seconds apart becomes one date: microsecond dates never
    deduplicated, a burst past KEEP was cut, and the tray fired mid-burst
    (ADVERSARY 2026-09-22 R4). ⛔ UP, never down: a wake before the date finds
    the negative still standing, and the run passes the video by.
    """
    return math.ceil(stamp / 60.0) * 60.0


def path():
    u"""-> the file every run writes and the tray reads."""
    return paths.data_root() / u"retries-due.json"


def _epoch(value):
    u"""An aware datetime or ISO text -> epoch seconds, or None."""
    try:
        if isinstance(value, datetime):
            moment = value
        else:
            moment = datetime.fromisoformat(str(value))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def save(dues, target=None):
    u"""Write down every date hato has promised to look again. -> the path, or None.

    `dues` -- aware datetimes or ISO text, in any order. 🚨 TEMP-PLUS-RENAME: a
    reader polling this once a second WILL catch a half-written file otherwise.
    ⛔ Never fails a run.
    """
    target = Path(target) if target is not None else path()
    stamps = sorted(set(_minute_up(s) for s in (_epoch(d) for d in (dues or ()))
                        if s is not None))
    payload = {u"due": [datetime.fromtimestamp(s, timezone.utc).isoformat()
                        for s in stamps[:KEEP]],
               u"saved_at": time.strftime(u"%Y-%m-%dT%H:%M:%S")}
    temp = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + u".new-%d" % os.getpid())
        with open(str(temp), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        _replace(temp, target)
        return target
    except (OSError, TypeError, ValueError):
        if temp is not None:
            try:
                os.unlink(str(temp))
            except OSError:
                pass
        return None                          # ⛔ never fails a run


def _replace(temp, target):
    u"""`os.replace`, waiting out a reader. ⚠ WINDOWS refuses to rename over a
    file another process has open, and the tray opens this one once a second
    -- for an instant. A refusal there returned None and the run's dates were
    simply not written (ADVERSARY 2026-09-22 R9)."""
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(str(temp), str(target))
            return
        except PermissionError:
            if attempt == _REPLACE_TRIES - 1:
                raise
            time.sleep(0.05)


def read(target=None):
    u"""-> ([epoch seconds] soonest first, what was wrong with the file or None).

    No file is no dates and nothing wrong -- no promise has been made. ⛔ NEVER
    RAISES: deeply nested JSON raised RecursionError straight past `except
    (OSError, ValueError)`, and the tray, which reads this every tick, died on
    every start (ADVERSARY 2026-09-22 R7). ⚠ And a file that holds something
    other than dates SAYS so: an object, bare numbers or a byte-order mark all
    used to read as "no dates" in silence (R8).
    """
    target = Path(target) if target is not None else path()
    try:
        with open(str(target), encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return [], None
    except Exception as exc:                 # noqa: BLE001 -- see the docstring
        return [], u"%s could not be read (%s: %s)" % (target, type(exc).__name__, exc)
    due = payload.get(u"due") if isinstance(payload, dict) else None
    if not isinstance(due, list):
        return [], u"%s holds no list of dates under \"due\"" % target
    stamps = [_epoch(d) for d in due]
    kept = sorted(s for s in stamps if s is not None)
    if len(kept) != len(stamps):
        return kept, (u"%s holds %d entr%s that %s not a date" % (
            target, len(stamps) - len(kept), u"y" if len(stamps) - len(kept) == 1 else u"ies",
            u"is" if len(stamps) - len(kept) == 1 else u"are"))
    return kept, None


def load(target=None):
    u"""-> [epoch seconds], soonest first. [] when there is nothing, or it is unreadable."""
    return read(target)[0]


__all__ = ["KEEP", "load", "path", "read", "save"]
