# -*- coding: utf-8 -*-
"""Sync ONE subtitle against ONE video through the port, and print what tsubasa said.

    hato sync <video> <subtitle> [--out DIR] [--dry-run]

This is RUNBOOK step 4a's Prove command, and it exists to show that the port returns
tsubasa's `Result` **unchanged** -- so it prints every public field the object carries,
enumerated at runtime rather than from a list here. A list would drift the moment
tsubasa adds a field, which is the drift the port exists to prevent.

⛔ It writes through tsubasa (`write=True`) unless --dry-run, exactly as the fetch loop
does. ⚠ The subtitle's name decides the output's language tag: an untagged name makes
tsubasa write `<video>.<ext>` with no tag at all (LEDGER-HOT), so pass the file under the
name hato would keep it as -- `<stem>.ja.srt`.

Exit 0 when the verdict is CONFIDENT, 1 when it is not, 2 for a usage mistake.

⭐ RUNBOOK 8e -- THIS IS ALSO THE WINDOW'S PICK, and it never worked. The window
spawned `hato sync <video> <subtitle> --json`, this command had no `--json`, and
every pick died on a usage error (exit 2) while the window -- which never read the
child -- painted it *"paired"* in green. Measured 2026-09-22.

    --json    one JSON object on stdout: what tsubasa said, and whether a file landed
    --force   ⭐ the PERSON overrides a timing refusal (tsubasa's own `force`: never
              an ERROR). Every candidate the window offers was already refused by
              this same deterministic check, so without it a pick cannot succeed.
              Exit 0 when the file was written, and the answer says it was FORCED.

⭐ AND A FILE THAT LANDS IS COPIED TO surasura, as a run's is (the Layer 14 pass,
Z14-5). The surasura card says *"Every subtitle hato aligns is also copied"* -- and a
pick never was: the next run then skipped the video as present, so surasura never
had it. It is the path a person takes when a download is refused, which is exactly
when *"Download from jimaku anyway"* -- chosen FOR surasura -- needs it.
"""
from __future__ import print_function

import json
import os
import sys

from hato import port

EXIT_OK = 0
EXIT_NOT_CONFIDENT = 1
EXIT_USAGE = 2

_VALUE_COLUMN = 22


def register(parser):
    parser.add_argument("video", help="the video file")
    parser.add_argument("subtitle", help="the subtitle to retime against it")
    parser.add_argument("--out", metavar="DIR",
                        help="write the result into DIR instead of beside the video")
    parser.add_argument("--dry-run", action="store_true",
                        help="measure and report; write nothing")
    parser.add_argument("--force", action="store_true",
                        help="write it even if the timing does not hold -- YOUR call, "
                             "never hato's. Never overrides an ERROR")
    parser.add_argument("--json", action="store_true",
                        help="one JSON object: the verdict, and whether a file was written")


def _fields(result):
    """Every public, non-callable attribute on the Result, in name order.

    ⛔ Enumerated, never listed: `05-interface.md` promises tsubasa's Result is passed
    through *"verbatim ... every field, not a re-wrapped subset"*, and a hand-kept list
    here would quietly stop showing whatever tsubasa adds next.
    """
    out = []
    for name in sorted(dir(result)):
        if name.startswith("_"):
            continue
        try:
            value = getattr(result, name)
        except Exception as exc:                     # a property that raises is a FACT
            out.append((name, u"<raises %s: %s>" % (type(exc).__name__, exc)))
            continue
        if callable(value):
            continue
        out.append((name, value))
    return out


def _row(name, value):
    pad = max(_VALUE_COLUMN - len(name), 0)
    return u"  %s%s  %s" % (name, u" " * pad, value)


def answer(result, video, subtitle, forced_asked, dry_run):
    u"""The one object `--json` prints. -> dict

    ⭐ `written` is a FILE THAT LANDED, and `forced` says whose decision put it
    there. ⛔ Never `written` off the outcome alone: a dry run is CONFIDENT with
    no file, and a forced write is REFUSED with one (measured).
    """
    outcome, reason = port.outcome_and_reason(result)
    landed = bool(result.output_path) and os.path.isfile(result.output_path)
    return {u"type": u"pair", u"video": video, u"subtitle": subtitle,
            u"outcome": outcome, u"reason": reason or u"",
            u"written": landed and (port.wrote(result) or port.forced(result)),
            u"forced": bool(forced_asked) and landed and port.forced(result),
            u"output_path": result.output_path if landed else None,
            u"match_rate": getattr(result, u"match_rate", None),
            u"verdict_word": getattr(result, u"verdict_word", None),
            u"dry_run": bool(dry_run)}


def _refuse(args, message, code):
    u"""A failure BEFORE a verdict. ⚠ Under --json it is still one object on
    stdout, so the window reads a sentence instead of an empty pipe."""
    sys.stderr.write(u"hato sync: %s\n" % message)
    if getattr(args, "json", False):
        print(json.dumps({u"type": u"pair", u"written": False, u"forced": False,
                          u"outcome": u"ERROR", u"reason": message},
                         ensure_ascii=False))
    return code


def configured_out(video):
    u"""Where hato's own runs put `video`'s subtitle, when config sets `out`. -> dir or None

    🚨 ONE SOURCE OF TRUTH (ADVERSARY 2026-09-22 F12 / A25). With `out` set, a
    pick written BESIDE the video lands where no run and no `hato problems`
    looks: the row never settled, and the next run fetched again over the
    person's own choice. ⭐ `keep.target_dir`, asked with the configured folder
    the video sits under -- the question every run asks.

    ⚠ None -- beside the video, as before -- for a video under no configured
    folder, and for a config that will not load: a run there would not start
    either, and a pick is still worth writing.
    """
    from hato import config, keep, paths
    try:
        cfg = config.load()
    except Exception:                                 # noqa: BLE001 -- see the docstring
        return None
    if not cfg.out:
        return None
    for folder in cfg.folders:
        if paths.under_any(video, (folder,)):
            try:
                return str(keep.target_dir(video, folder, cfg.out))
            except ValueError:
                return None
    return None


def configured_surasura():
    u"""The folder surasura reads from, when config names one. -> path or ""

    ⚠ `configured_out`'s rule: a config that will not load copies nothing -- a
    run there would not start either, and the pick itself still stands.
    """
    from hato import config
    try:
        return config.load().surasura_dir or u""
    except Exception:                                 # noqa: BLE001 -- as above
        return u""


def run(args):
    video = os.path.abspath(args.video)
    subtitle = os.path.abspath(args.subtitle)
    for path, what in ((video, "video"), (subtitle, "subtitle")):
        if not os.path.isfile(path):
            return _refuse(args, u"the %s is not a file: %s" % (what, path), EXIT_USAGE)

    out_dir = os.path.abspath(args.out) if args.out else configured_out(video)
    try:
        result = port.sync(video, subtitle, write=not args.dry_run, out_dir=out_dir,
                           force=args.force)
    except port.PortError as exc:
        return _refuse(args, str(exc), EXIT_NOT_CONFIDENT)
    except Exception as exc:                          # tsubasa's own refusals carry the fix
        return _refuse(args, u"%s: %s" % (type(exc).__name__, exc), EXIT_NOT_CONFIDENT)

    said = answer(result, video, subtitle, args.force, args.dry_run)
    said[u"surasura"] = None
    if said[u"written"]:
        # ⭐ Z14-5 -- `keep.surasura_copy`, the run's own copier. ⛔ A copy that fails
        # is NOT a failed pick: the subtitle beside the video is written and correct
        # (the run's rule, `pipeline.py` -- a note, never an error)
        from hato import keep
        try:
            said[u"surasura"] = keep.surasura_copy(said[u"output_path"],
                                                   configured_surasura())
        except OSError as exc:
            said[u"surasura_error"] = u"the surasura copy could not be written: %s" % exc
        if said[u"surasura"] is not None:
            said[u"surasura"] = str(said[u"surasura"])
    if args.json:
        print(json.dumps(said, ensure_ascii=False, sort_keys=True))
        if said[u"written"]:
            return EXIT_OK
        return EXIT_OK if (args.dry_run and said[u"outcome"] == port.CONFIDENT) \
            else EXIT_NOT_CONFIDENT

    print(u"video        %s" % video)
    print(u"subtitle     %s" % subtitle)
    if args.dry_run:
        print(u"mode         --dry-run: measured, nothing written")
    print(u"")
    for name, value in _fields(result):
        print(_row(name, value))
    print(u"")

    outcome, reason = port.outcome_and_reason(result)
    print(u"outcome      %s" % outcome)
    if reason:
        print(u"reason       %s" % reason)
    if said[u"written"]:
        print(u"written      %s%s" % (result.output_path,
                                     u"  (by --force: the timing did not hold)"
                                     if said[u"forced"] else u""))
        if said[u"surasura"]:
            print(u"surasura     %s" % said[u"surasura"])
        elif said.get(u"surasura_error"):
            print(u"surasura     %s" % said[u"surasura_error"])
        return EXIT_OK
    # ⚠ Two shapes, never one sentence: a dry run nobody asked bytes of, and a write
    # that did not land. `03-permissions.md` §the read rule records the difference.
    print(u"written      nothing -- %s" % port.why_nothing_was_written(result))
    return EXIT_OK if outcome == port.CONFIDENT else EXIT_NOT_CONFIDENT
