# -*- coding: utf-8 -*-
"""Show what the state DB remembers: attempts by outcome, and when each NOT FOUND is retried.

    hato state --stat [--json]
    hato state --clear [--blacklist] [--yes] [--json]

The state DB is advisory -- it only ever stops hato repeating work, and deleting
it is always safe (the next run re-derives everything from disk). ⚠ --stat never
creates a DB that is not there. It does open an existing one through the one
accessor, so a corrupt DB is moved aside and a fresh one started, and it says so.

⭐ --clear (RUNBOOK 8g) forgets what hato remembers: what it tried, when it
promised to look again, and the shows it found on jimaku. ⛔ DRY UNLESS --yes
(`doctrine/robustness` §destructive): without it the command only says what
would go and what stays. The blacklist goes only with --blacklist. ⛔ Taken
under the RUN LOCK, so it cannot empty the memory under a run that is writing
it. ⛔ No subtitle, no kept original, no setting and no key is ever touched.
"""
import json
import os
import sys

from hato import paths, retries
from hato import state as _state
from hato.resolution import ResolutionCache
from hato.runlock import LockHeld, LockUnusable, RunLock

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def register(parser):
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--stat", action="store_true",
                      help="print row counts by outcome and the next retry dates")
    what.add_argument("--clear", action="store_true",
                      help="forget what hato tried, when it looks again and the shows it "
                           "found -- says what would go, and changes nothing without --yes")
    parser.add_argument("--blacklist", action="store_true",
                        help="with --clear: forget the blacklist too")
    parser.add_argument("--yes", action="store_true",
                        help="with --clear: actually clear it")
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


#: What --clear says stays, whatever happens. ⚠ Words a person reads, in the
#: order they would worry about them.
KEPT = (u"every subtitle beside your videos", u"the originals hato kept",
        u"your settings", u"your jimaku key")


def _clear(args):
    u"""`hato state --clear`. -> an exit code.

    ⛔ Everything is counted and (with --yes) deleted while THIS process holds
    the run lock: a run that started mid-clear would write rows into a store
    being emptied, and one already writing must not have it emptied under it.
    """
    def say(obj, text, code):
        if args.json:
            print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
        else:
            (sys.stdout if code == EXIT_OK else sys.stderr).write(text + u"\n")
        return code

    dry = not args.yes
    try:
        path = paths.state_db_path()
        # ⛔ A DRY COUNT REPAIRS NOTHING: a corrupt file is left for the next run
        # (ADVERSARY 2026-09-22 F2/F3b -- it moved both stores aside, then said
        # "nothing was changed").
        shows = ResolutionCache(repair=not dry)
    except paths.PathError as exc:
        return say({"ok": False, "type": "clear", "error": str(exc)},
                   u"hato: the data location is wrong -- %s" % exc, EXIT_FAILED)

    lock = RunLock()
    # ⛔ ONLY A REAL CLEAR TAKES THE LOCK. The window asks for the dry count to
    # show on its card; holding the run lock for that would make a tray run
    # starting at the same moment exit with "nothing was scanned".
    if not dry:
        try:
            lock.acquire()
        except LockHeld as exc:
            message = (u"a hato run is going (%s), so nothing was cleared -- try again "
                       u"when it finishes." % exc)
            return say({"ok": False, "type": "clear", "busy": True, "error": message},
                       u"hato: " + message, EXIT_FAILED)
        except LockUnusable as exc:
            return say({"ok": False, "type": "clear", "error": str(exc)},
                       u"hato: %s" % exc, EXIT_FAILED)
    try:
        tables, videos, waiting, kept_blacklist, notes = {}, 0, 0, 0, []
        if lock.note:
            notes.append(lock.note)          # ⭐ a dead run's lock taken over, said (F17)
        if path.exists():                    # ⛔ never create a DB to empty it
            with _state.StateDB(path, repair=not dry) as db:
                waiting = db.stats()["negatives_active"]
                gone = db.clear(blacklist=args.blacklist, dry_run=dry)
                tables, videos = gone["tables"], gone["videos"]
                if not args.blacklist:
                    kept_blacklist = len(db.blacklist_list())
                notes.extend(db.notes)
        found = shows.clear(dry_run=dry)
        notes.extend(shows.notes)
        if not dry:
            try:
                retries.path().unlink()      # nothing is promised any more
            except OSError:
                pass
    finally:
        if not dry:
            lock.release()

    cleared = {"videos": videos, "attempts": tables.get("attempts", 0),
               "present": tables.get("present", 0), "shows": found, "waiting": waiting}
    if args.blacklist:
        cleared["blacklist"] = tables.get("blacklist", 0)
    others = dict((k, v) for k, v in tables.items()
                  if k not in ("attempts", "present", "blacklist"))
    if others:
        cleared["other"] = others
    kept = list(KEPT) + ([] if args.blacklist else [
        u"the blacklist (%d video%s)" % (kept_blacklist, u"" if kept_blacklist == 1 else u"s")])
    lines = [u"%s:" % (u"hato would forget" if dry else u"hato forgot"),
             u"  %d video%s it tried (%d tr%s)" % (
                 videos, u"" if videos == 1 else u"s", cleared["attempts"],
                 u"y" if cleared["attempts"] == 1 else u"ies"),
             u"  %d waiting to be looked at again" % waiting,
             u"  %d show%s it found on jimaku -- found again, a few requests each" % (
                 found, u"" if found == 1 else u"s")]
    if args.blacklist:
        lines.append(u"  the blacklist (%d video%s)" % (
            cleared["blacklist"], u"" if cleared["blacklist"] == 1 else u"s"))
    lines.append(u"kept: " + u" · ".join(kept))
    lines.append(u"nothing was cleared -- add --yes to clear it." if dry else
                 u"every episode without a subtitle is looked at again on the next run.")
    for note in notes:
        lines.insert(0, u"note  %s" % note)
    return say({"ok": True, "type": "clear", "dry_run": dry, "cleared": cleared,
                "kept": kept, "notes": notes}, u"\n".join(lines), EXIT_OK)


def run(args):
    if (args.blacklist or args.yes) and not args.clear:
        sys.stderr.write(u"hato: --blacklist and --yes only mean something with --clear.\n")
        return EXIT_USAGE
    if args.clear:
        return _clear(args)
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
