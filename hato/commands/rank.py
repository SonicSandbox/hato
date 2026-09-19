# -*- coding: utf-8 -*-
"""Explain the order one episode's candidates would be tried in, and why.

    hato rank --explain <entry-id> <episode> --files FILE.json [--folder DIR]
                        [--movie] [--allow-ai] [--seen RELEASE ...]

Every candidate with its key -- format, language, fit, version, size, release --
and the reason for its place against the ones either side; then every file the
filters removed, and why (spec/RUNBOOK.md 3b).

Without --folder the episode stands alone: only files whose OWN number reads
<episode> are candidates (the single-video soft spot, 02-data-model.md). With
--folder the entry is first aligned against that folder's videos, so a release
numbering the season differently is offered too.

⚠ Ranking chooses who is tried first. The timing verdict decides who is right.
--files is required until RUNBOOK 2c wires the live path; nothing here makes a
network call.
"""
import os
import sys

from hato.commands.align import (EXIT_FAILED, EXIT_OK, EXIT_USAGE, LIVE_NOT_WIRED,
                                 InputError, load_files, scan_videos)


class _Episode(object):
    """The one video `hato rank` ranks for when no folder is given. It carries a
    number the user typed -- nothing is parsed out of a name."""

    def __init__(self, episode):
        self.episode = episode
        self.season = None
        self.title = u""
        self.name = u"episode %s" % episode
        self.path = u"(episode %s)" % episode
        self.episode_candidates = (episode,)


def register(parser):
    parser.add_argument("--explain", action="store_true", required=True,
                        help="print the ranking in full (the only output this command has)")
    parser.add_argument("entry_id", type=int, help="the jimaku entry id")
    parser.add_argument("episode", type=_episode_number, help="the episode to rank for (13.5 is allowed)")
    parser.add_argument("--files", metavar="FILE.json",
                        help="a recorded file list for the entry (required until RUNBOOK 2c)")
    parser.add_argument("--folder", help="align against this folder's videos first")
    parser.add_argument("--movie", action="store_true",
                        help="the entry is a movie (flags.movie): every file is a candidate")
    parser.add_argument("--allow-ai", action="store_true",
                        help="keep AI-generated subtitles instead of excluding them")
    parser.add_argument("--seen", action="append", default=[], metavar="RELEASE",
                        help="a release already seen to succeed for this show (repeatable)")


def _episode_number(text):
    import argparse
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not an episode number" % text)
    return int(value) if value.is_integer() else value


def run(args):
    from hato import episodes, paths, rank
    from hato.cache import Cache

    if not args.files:
        sys.stderr.write(LIVE_NOT_WIRED + u"\n")
        return EXIT_USAGE
    try:
        files = load_files(args.files, args.entry_id)
        videos = scan_videos(args.folder) if args.folder else [_Episode(args.episode)]
        with Cache().workdir("rank") as work:
            alignment = episodes.align(files, videos, workdir=work, movie=args.movie)
    except (InputError, paths.PathError) as exc:
        sys.stderr.write(u"hato rank: %s\n" % exc)
        return EXIT_FAILED

    chosen = [v for v in alignment.videos if args.movie or v.episode == args.episode]
    if not chosen:
        sys.stderr.write(u"hato rank: no video in %s reads episode %s\n" % (args.folder, args.episode))
        return EXIT_FAILED
    where = os.path.abspath(args.folder) if args.folder else (
        u"no folder -- only files whose own number reads %s are candidates" % args.episode)
    print(u"hato rank · entry %d · episode %s · %s" % (args.entry_id, args.episode, where))
    for video in chosen:
        path = str(video.path)
        print(u"")
        print(u"VIDEO  %s" % video.name)
        if path in alignment.refused:
            print(u"  REFUSED -- %s" % alignment.refused[path])
            continue
        if path in alignment.not_found:
            print(u"  NOT FOUND -- %s" % alignment.not_found[path])
            continue
        ranking = rank.rank(alignment.per_video[path], allow_ai=args.allow_ai,
                            seen_groups=frozenset(args.seen))
        print(rank.explain(ranking))
    if alignment.notes:
        print(u"")
        print(u"NOTES")
        for note in alignment.notes:
            print(u"  - %s" % note)
    return EXIT_OK
