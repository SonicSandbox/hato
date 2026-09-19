# -*- coding: utf-8 -*-
"""Show where the working cache is, how big it is, and how many entries it holds.

    hato cache --stat [--json]

The working cache holds downloads in flight, refused candidates and extracted
archives -- all disposable. It never holds the subtitles beside your videos, and
never the kept originals (those live in subs_dir). ⚠ --stat creates nothing: a
cache that was never used is reported as not created yet.
"""
import json
import sys

from hato import cache as _cache
from hato import paths

EXIT_OK = 0
EXIT_FAILED = 1


def register(parser):
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--stat", action="store_true",
                      help="print the cache's path, its size on disk and its entry count")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def human_bytes(n):
    for unit, size in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return "%.1f %s" % (float(n) / size, unit)
    return "%d B" % n


def _plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def run(args):
    try:
        found = _cache.Cache().stat()
        source = paths.data_root_source()
    except paths.PathError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("hato: the cache location is wrong -- %s\n" % exc)
        return EXIT_FAILED

    if args.json:
        found = dict(found, ok=True, source=source)
        print(json.dumps(found, ensure_ascii=False, sort_keys=True))
        return EXIT_OK

    where = "HATO_CACHE" if source == "HATO_CACHE" else "default location"
    print("cache        %s  (%s)" % (found["path"], where))
    if not found["exists"]:
        print("             not created yet -- nothing has been cached")
    print("size         %s  (%s bytes)" % (human_bytes(found["bytes"]), format(found["bytes"], ",")))
    print("entries      %d" % found["entries"])
    if found["exists"]:
        loose = []
        if found["partial"]:
            loose.append(_plural(found["partial"], "partial download", "partial downloads"))
        if found["work"]:
            loose.append(_plural(found["work"], "extraction folder", "extraction folders"))
        if loose:
            print("in flight    %s -- or left by a run that was stopped; safe to delete "
                  "when no hato is running" % " · ".join(loose))
        else:
            print("in flight    nothing")
    return EXIT_OK
