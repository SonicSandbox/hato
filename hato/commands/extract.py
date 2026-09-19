# -*- coding: utf-8 -*-
"""Unpack one .zip, .7z or .rar into the working cache and list what came out.

    hato extract <archive> [--into DIR]

Only subtitles come out; junk and nested archives are listed as skipped. An archive
with a member that escapes the folder, a link, or a size past a cap is refused whole,
and nothing is written. Without --into it unpacks into a fresh folder under the
working cache's work/, prints where, and leaves it: the cache is disposable, and
`hato cache --stat` counts the folder. With --into, DIR must be empty or not exist yet.

Exit 0 when it unpacked, 1 when it could not (refused, damaged, no unrar), 2 for an
--into that is a file or not empty.
"""
import os
import sys
import uuid

from hato import archives, paths
from hato import cache as _cache
from hato.commands.cache import human_bytes

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_NAME_COLUMN = 56


def register(parser):
    parser.add_argument("archive", help="the .zip, .7z or .rar to unpack")
    parser.add_argument("--into", metavar="DIR",
                        help="unpack into DIR (created if missing, must be empty) instead of "
                             "a fresh folder in the working cache")


def _fresh_cache_folder(archive):
    """<cache>/work/<archive name>-<8 hex>: the shape Cache.workdir gives its folders, so
    `hato cache --stat` counts it. Not created here -- extract() creates it, and removes
    it again if nothing comes out."""
    label = _cache.safe_name(os.path.basename(archive) or "extract", max_len=_cache.NAME_MIN)
    return _cache.Cache().root / "work" / ("%s-%s" % (label, uuid.uuid4().hex[:8]))


def _row(name, value):
    pad = max(_NAME_COLUMN - len(name), 0)
    return "  %s%s  %s" % (name, " " * pad, value)


def run(args):
    archive = os.path.abspath(args.archive)
    try:
        into = os.path.abspath(args.into) if args.into else _fresh_cache_folder(archive)
    except paths.PathError as exc:
        sys.stderr.write("hato: the cache location is wrong -- %s\n" % exc)
        return EXIT_FAILED

    try:
        size = human_bytes(os.stat(archive).st_size)
    except OSError:
        size = "cannot be read"
    print("archive      %s  (%s)" % (archive, size))

    try:
        found = archives.extract(archive, into)
    except archives.ArchiveUnsupported as exc:
        print("SKIPPED      %s" % exc.reason)
        print("             nothing was extracted")
        return EXIT_FAILED
    except archives.ArchiveError as exc:
        print("ERROR        %s" % exc.reason)
        print("             nothing was extracted")
        return EXIT_FAILED
    except ValueError as exc:
        sys.stderr.write("hato extract: %s\n" % exc)
        return EXIT_USAGE
    except OSError as exc:
        print("ERROR        %s" % exc)
        print("             nothing was extracted")
        return EXIT_FAILED

    print("root         %s" % found.root)
    if not args.into:
        print("             in the working cache -- disposable; `hato cache --stat` counts it")
    print("")
    total = sum(m.size for m in found.members)
    print("subtitles    %d · %s" % (len(found.members), human_bytes(total)))
    # ⚠ Names are the uploader's text: printed escaped, never raw (archives._shown).
    for m in found.members:
        print(_row(archives._shown(m.name), human_bytes(m.size)))
        if m.path.name != m.name.rsplit("/", 1)[-1]:
            print("      -> %s" % archives._shown(m.path.name))
    if found.skipped:
        print("skipped      %d" % len(found.skipped))
        for name, reason in found.skipped:
            print(_row(archives._shown(name), reason))
    for note in found.notes:
        print("note         %s" % note)
    return EXIT_OK
