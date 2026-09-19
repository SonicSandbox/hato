# -*- coding: utf-8 -*-
u"""
What the last run found, written down so a window can show it.

    lastrun.save(rows, summary)        # every run, whoever started it
    rows, summary, when = lastrun.load()

===========================================================================
🚨 WRITTEN BY THE RUN, NOT BY THE WINDOW
===========================================================================

Sonic, 2026-09-18: *"once it runs automatically (from the tray or so) the UI
doesn't update it. I opened it, then dragged a video into a folder, it worked
but the ui didn't update -- it was until i hit run."*

⭐ THE WINDOW WAS SAVING ITS OWN RUNS AND ONLY ITS OWN. A run started from the
tray, from the scheduler, or from a terminal wrote subtitles to disk and left
no trace the window could read -- so a person watching the window saw nothing
happen while hato was working perfectly two processes away. **The disconnect
was not a refresh bug; it was a memory only one of three callers wrote to.**

⛔ So it lives HERE, in hato proper, and `hato/commands/run.py` writes it at
the end of every run. The window is now purely a reader that watches the file.
⚠ Which also means the 3 a.m. scheduled run is visible at breakfast -- the
case nobody would have tested by hand.

===========================================================================
⛔ NEVER RAISES, IN EITHER DIRECTION
===========================================================================

A run that cannot write this file has still done its job: the subtitles are
beside the videos. And a truncated or hand-edited file is *no memory*, not a
window that will not open. Both directions fail to an empty answer.

⛔ AND IT HOLDS NO SECRET. These are hato's own result objects -- filenames,
verdicts, counts. The key is never in one.
"""
from __future__ import print_function

import json
import os
import time
from pathlib import Path

from hato import paths


def save(rows, summary, path=None):
    u"""Write down what this run found. -> the path, or None.

    🚨 TEMP-PLUS-RENAME. `open(path,'w')` truncates the moment it opens, so a
    raise mid-write would leave zero bytes -- which the next launch reads as
    *no previous run* rather than as a broken one.
    """
    target = Path(path) if path is not None else paths.last_run_path()
    payload = {u"rows": list(rows or ()), u"summary": dict(summary or {}),
               u"saved_at": time.strftime(u"%Y-%m-%dT%H:%M:%S")}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + u".new-%d" % os.getpid())
        with open(str(temp), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(str(temp), str(target))
        return target
    except (OSError, TypeError, ValueError):
        return None                          # ⛔ never fails a run


def load(path=None):
    u"""-> (rows, summary, saved_at). Empty when there is nothing to remember."""
    target = Path(path) if path is not None else paths.last_run_path()
    try:
        with open(str(target), encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return [], {}, u""
    if not isinstance(payload, dict):
        return [], {}, u""
    rows = payload.get(u"rows")
    summary = payload.get(u"summary")
    return (list(rows) if isinstance(rows, list) else [],
            dict(summary) if isinstance(summary, dict) else {},
            payload.get(u"saved_at") or u"")


def stamp(path=None):
    u"""-> the file's mtime, or 0.0 when there is none.

    ⭐ HOW A WINDOW NOTICES SOMEBODY ELSE'S RUN. It polls this and reloads when
    it changes -- which costs a `stat` and needs no channel between two
    processes that were never meant to know about each other.
    """
    target = Path(path) if path is not None else paths.last_run_path()
    try:
        return os.path.getmtime(str(target))
    except OSError:
        return 0.0


__all__ = ["load", "save", "stamp"]
