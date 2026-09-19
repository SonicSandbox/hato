# -*- coding: utf-8 -*-
"""Never fetch subtitles for this video -- and the way back.

    hato blacklist <video> [--note "..."]    never fetch for this one
    hato blacklist --remove <video>          undo it
    hato blacklist --list [--json]           what is on it

Sonic, 2026-09-17: *"there is a video in there that doesn't need / won't have
subs, that you could easily blacklist it."*

⚠ `--force` DOES NOT OVERRIDE THE BLACKLIST. `--force` overrules what HATO
decided -- a refusal, a negative it recorded itself. A blacklist row is what the
PERSON decided, and `--remove` is the only way back (spec/02-data-model.md
§Question 3).

⛔ It can only ever PREVENT work. Adding a row downloads nothing, writes nothing
beside the video and deletes nothing; removing one puts the video back exactly
where it was.
"""
import json
import os
import sys

from hato import paths
from hato import state as _state

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def register(parser):
    parser.add_argument("video", nargs="?",
                        help="the video file to blacklist (identified by its content hash, "
                             "so it survives a rename)")
    parser.add_argument("--remove", metavar="VIDEO",
                        help="take a video back off the blacklist")
    parser.add_argument("--list", action="store_true", dest="list_",
                        help="show every blacklisted video")
    parser.add_argument("--note", default="",
                        help="why, in your own words -- shown by --list")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _fail(args, message):
    if args.json:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        sys.stderr.write("hato: %s\n" % message)
    return EXIT_FAILED


def _hash(path):
    """-> the video's hash, or None when the file is not there to be hashed."""
    from hato.cache import video_hash
    try:
        return video_hash(path)
    except OSError:
        return None


def _local(moment):
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _row(row):
    return {"video_hash": row.video_hash, "video_path": row.video_path,
            "added_at": row.added_at.isoformat(), "note": row.note}


def _add(db, args):
    path = os.path.abspath(args.video)
    digest = _hash(path)
    if digest is None:
        return _fail(args, "cannot read %s, so its hash cannot be taken. The blacklist is "
                           "keyed on the video's content (it has to survive a rename), so the "
                           "file has to be there to add it." % path)
    row = db.blacklist_add(digest, video_path=path, note=args.note)
    if args.json:
        print(json.dumps(dict(_row(row), ok=True), ensure_ascii=False))
        return EXIT_OK
    print("blacklisted  %s" % path)
    if row.note:
        print("             %s" % row.note)
    print("             hato will not fetch for this video, and --force does not override it.")
    print("             `hato blacklist --remove %s` undoes it." % os.path.basename(path))
    return EXIT_OK


def _remove(db, args):
    path = os.path.abspath(args.remove)
    digest = _hash(path)
    if digest is not None and db.blacklist_remove(digest):
        gone = [path]
    else:
        # ⚠ The file may be gone, renamed or on an unplugged drive -- and a row a
        # person wants off cannot be held hostage by that. Fall back to the
        # advisory path, which is the only other thing they can name.
        wanted = os.path.normcase(path)
        rows = [r for r in db.blacklist_list()
                if r.video_path and os.path.normcase(r.video_path) == wanted]
        for row in rows:
            db.blacklist_remove(row.video_hash)
        gone = [r.video_path for r in rows]
    if args.json:
        print(json.dumps({"ok": True, "removed": gone}, ensure_ascii=False))
        return EXIT_OK
    if not gone:
        print("blacklist    %s was not on it -- nothing to remove" % path)
        return EXIT_OK
    for where in gone:
        print("removed      %s" % where)
    print("             hato will consider it again on the next run")
    return EXIT_OK


def _list(db, args):
    rows = db.blacklist_list()
    if args.json:
        print(json.dumps({"ok": True, "blacklist": [_row(r) for r in rows]},
                         ensure_ascii=False, sort_keys=True))
        return EXIT_OK
    if not rows:
        print("blacklist    empty -- `hato blacklist <video>` adds one")
        return EXIT_OK
    print("blacklist    %d video%s hato will never fetch for"
          % (len(rows), "" if len(rows) == 1 else "s"))
    for row in rows:
        print("  %s   %s" % (_local(row.added_at), row.video_path or row.video_hash))
        if row.note:
            print("  %s   %s" % (" " * 16, row.note))
    return EXIT_OK


def run(args):
    asked = [bool(args.video), bool(args.remove), bool(args.list_)]
    if sum(asked) != 1:
        sys.stderr.write("hato blacklist: give exactly one of <video>, --remove <video> or "
                         "--list\n")
        return EXIT_USAGE
    if args.note and not args.video:
        sys.stderr.write("hato blacklist: --note belongs with the video being added\n")
        return EXIT_USAGE
    try:
        path = paths.state_db_path()
    except paths.PathError as exc:
        return _fail(args, "the state DB location is wrong -- %s" % exc)
    # ⚠ --list on a machine that has never run must not leave a DB behind, exactly
    # as `hato state --stat` must not (RUNBOOK 1b).
    if args.list_ and not path.exists():
        return _list(_Empty(), args)
    with _state.StateDB(path) as db:
        for note in db.notes:
            print("note         %s" % note)
        if args.video:
            return _add(db, args)
        if args.remove:
            return _remove(db, args)
        return _list(db, args)


class _Empty(object):
    """A state DB that is not there yet -- read-only, and creates nothing."""

    def blacklist_list(self):
        return []
