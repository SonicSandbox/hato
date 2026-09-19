# -*- coding: utf-8 -*-
"""Show what the state DB remembers: attempts by outcome, and when each NOT FOUND is retried.

    hato state --stat [--json]

The state DB is advisory -- it only ever stops hato repeating work, and deleting
it is always safe (the next run re-derives everything from disk). ⚠ --stat never
creates a DB that is not there. It does open an existing one through the one
accessor, so a corrupt DB is moved aside and a fresh one started, and it says so.
"""
import json
import os
import sys

from hato import paths
from hato import state as _state

EXIT_OK = 0
EXIT_FAILED = 1


def register(parser):
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--stat", action="store_true",
                      help="print row counts by outcome and the next retry dates")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _local(moment):
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _days(n):
    return "%d day%s" % (n, "" if n == 1 else "s")


def _empty(path):
    return {"path": str(path), "exists": False, "persistent": True,
            "schema_version": _state.SCHEMA_VERSION, "journal_mode": None,
            "rows": dict((o, 0) for o in _state.OUTCOMES), "present": 0,
            "blacklisted": 0,
            "retry_days": {_state.SOFT: _state.SOFT_DAYS, _state.HARD: _state.HARD_DAYS},
            "negatives_active": 0, "next_retries": [], "notes": []}


def run(args):
    try:
        path = paths.state_db_path()
    except paths.PathError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("hato: the state DB location is wrong -- %s\n" % exc)
        return EXIT_FAILED

    if path.exists():
        with _state.StateDB(path) as db:
            found = db.stats()
        found["exists"] = True
    else:
        found = _empty(path)

    if args.json:
        out = dict(found, ok=True)
        out["next_retries"] = [dict(r, retry_after=r["retry_after"].isoformat())
                               for r in found["next_retries"]]
        print(json.dumps(out, ensure_ascii=False, sort_keys=True))
        return EXIT_OK

    for note in found["notes"]:
        print("note         %s" % note)
    print("state DB     %s" % found["path"])
    if not found["exists"]:
        print("             none yet -- nothing has been recorded")
    else:
        mode = (found["journal_mode"] or "?").upper()
        kept = "" if found["persistent"] else " · in memory for this run"
        print("             schema %d · %s%s" % (found["schema_version"], mode, kept))
    print("")
    rows = found["rows"]
    print("attempts     %s" % " · ".join("%d %s" % (rows[o], o) for o in _state.OUTCOMES))
    print("backfilled   %d already present when first seen" % found["present"])
    days = found["retry_days"]
    print("blacklist    %d video%s the person said never to fetch  (hato blacklist --list)"
          % (found["blacklisted"], "" if found["blacklisted"] == 1 else "s"))
    print("retry after  %s soft · %s hard" % (_days(days[_state.SOFT]), _days(days[_state.HARD])))
    print("")
    retries = found["next_retries"]
    if not retries:
        print("retry next   nothing waiting -- no NOT FOUND is inside its retry window")
        return EXIT_OK
    first = True
    for r in retries:
        label = "retry next" if first else ""
        first = False
        video = os.path.basename(r["video_path"] or "") or "(video path not recorded)"
        print("%-12s %s   %-4s   %s" % (label, _local(r["retry_after"]), r["kind"], video))
        print("%-12s %s          %s" % ("", " " * 16, r["reason"]))
    hidden = found["negatives_active"] - len(retries)
    if hidden > 0:
        print("%-12s ... and %d more" % ("", hidden))
    return EXIT_OK
