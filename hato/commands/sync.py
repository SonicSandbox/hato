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
"""
from __future__ import print_function

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


def run(args):
    video = os.path.abspath(args.video)
    subtitle = os.path.abspath(args.subtitle)
    for path, what in ((video, "video"), (subtitle, "subtitle")):
        if not os.path.isfile(path):
            sys.stderr.write("hato sync: the %s is not a file: %s\n" % (what, path))
            return EXIT_USAGE

    out_dir = os.path.abspath(args.out) if args.out else None
    try:
        result = port.sync(video, subtitle,
                           write=not args.dry_run, out_dir=out_dir)
    except port.PortError as exc:
        sys.stderr.write("hato sync: %s\n" % exc)
        return EXIT_NOT_CONFIDENT
    except Exception as exc:                          # tsubasa's own refusals carry the fix
        sys.stderr.write("hato sync: %s: %s\n" % (type(exc).__name__, exc))
        return EXIT_NOT_CONFIDENT

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
    if port.wrote(result):
        print(u"written      %s" % result.output_path)
    else:
        # ⚠ Two shapes, never one sentence: a dry run nobody asked bytes of, and a write
        # that did not land. `03-permissions.md` §the read rule records the difference.
        print(u"written      nothing -- %s" % port.why_nothing_was_written(result))
    return EXIT_OK if outcome == port.CONFIDENT else EXIT_NOT_CONFIDENT
