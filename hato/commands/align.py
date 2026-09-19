# -*- coding: utf-8 -*-
"""Explain which of a jimaku entry's files could be which video in a folder.

    hato align --explain <folder> <entry-id> --files FILE.json [--movie]

Per release: its episode range, the offset it fits the folder at, and how well.
Per video: the file episode each release offers for it. Then what was refused,
what was not found, and every note (spec/RUNBOOK.md 3a).

--files reads a recorded file list -- tests/fixtures/api/entries_11446_files.json
is one. ⚠ Fetching the list live from jimaku is wired after RUNBOOK 2c; until then
--files is required, and nothing here makes a network call. --movie takes the
movie path (the entry's flags.movie), which a recorded file list does not carry.

Exit codes: 0 it ran (a refusal or a NOT FOUND is an outcome) · 1 the input could
not be used · 2 usage, including a missing --files.
"""
import json
import os
import re
import sys

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

LIVE_NOT_WIRED = (u"hato: fetching an entry's file list live is wired after RUNBOOK 2c -- pass "
                  u"--files FILE.json (a recorded list, e.g. tests/fixtures/api/entries_11446_files.json).")


class InputError(Exception):
    """An input the command cannot use. The message says which, and why."""


def register(parser):
    parser.add_argument("--explain", action="store_true", required=True,
                        help="print the alignment in full (the only output this command has)")
    parser.add_argument("folder", help="the folder of videos to align against")
    parser.add_argument("entry_id", type=int, help="the jimaku entry id")
    parser.add_argument("--files", metavar="FILE.json",
                        help="a recorded file list for the entry (required until RUNBOOK 2c)")
    parser.add_argument("--movie", action="store_true",
                        help="the entry is a movie (flags.movie): every file is a candidate")


def load_files(path, entry_id):
    """-> the file dicts in a recorded list. ⚠ When a `.meta.json` sits beside it
    (hato doctor --capture writes one), it must name the same entry -- explaining
    one entry's files as another's is worse than refusing."""
    try:
        with open(path, encoding="utf-8") as fh:
            files = json.load(fh)
    except (OSError, ValueError) as exc:
        raise InputError(u"could not read %s as a JSON file list -- %s" % (path, exc))
    if not isinstance(files, list) or not all(isinstance(f, dict) and f.get("name") for f in files):
        raise InputError(u"%s is not a jimaku file list (a JSON array of objects with a name)" % path)
    meta = re.sub(r"\.json$", "", path) + ".meta.json"
    if os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as fh:
                url = json.load(fh).get("url") or u""
        except (OSError, ValueError):
            url = u""
        m = re.search(r"/entries/(\d+)/files", url)
        if m and int(m.group(1)) != entry_id:
            raise InputError(u"%s was recorded from entry %s, not entry %d" % (path, m.group(1), entry_id))
    return files


def scan_videos(folder):
    import tsubasa
    if not os.path.isdir(folder):
        raise InputError(u"%s is not a folder" % folder)
    return list(tsubasa.scan(videos=folder).videos)


def run(args):
    from hato import episodes, paths
    from hato.cache import Cache

    if not args.files:
        sys.stderr.write(LIVE_NOT_WIRED + u"\n")
        return EXIT_USAGE
    try:
        files = load_files(args.files, args.entry_id)
        videos = scan_videos(args.folder)
        with Cache().workdir("align") as work:
            alignment = episodes.align(files, videos, workdir=work, movie=args.movie)
    except (InputError, paths.PathError) as exc:
        sys.stderr.write(u"hato align: %s\n" % exc)
        return EXIT_FAILED
    print(u"hato align · entry %d · %s" % (args.entry_id, os.path.abspath(args.folder)))
    print(episodes.explain(alignment))
    return EXIT_OK
