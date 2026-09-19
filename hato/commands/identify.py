# -*- coding: utf-8 -*-
"""Which jimaku entry is a video? Prints the entry, its score, and what it cost.

    hato identify "<filename>"                   parse -> resolution cache -> jimaku
    hato identify "<filename>" --fixtures DIR    the same, answered by recorded responses
                                                 (e.g. tests/fixtures) -- no network, no key
    hato identify "<filename>" --explain         ...and every entry it scored
    hato identify "<filename>" --no-cache        neither read nor write the resolution cache
    hato identify "<filename>" --verbose         ...and the last call's rate-limit headers
    hato identify "<filename>" --json

The title and season are read by tsubasa's parser (hato.names), never here.
⚠ A lookup spends metered jimaku calls: 1 for most shows, 2 for live action, 3 plus
2 Kitsu calls when jimaku's own search misses twice. A cached show costs nothing.
"""
import json
import re
import sys
from pathlib import Path

from hato import credentials, paths
from hato.cache import Cache
from hato.client import JimakuClient, JimakuError, NoRecording, RecordedSession
from hato.kitsu import KitsuClient
from hato.names import read_names
from hato.resolution import ResolutionCache, identify

EXIT_OK = 0
EXIT_FAILED = 1

#: Recorded responses were made with a real key and check none. ⛔ The real key is
#: never read for a --fixtures run.
STAND_IN_KEY = "recorded-responses-need-no-key"
_LOW = " -- LOW CONFIDENCE: "
_FOUND_BY = {"jimaku": "jimaku search",
             "jimaku anime=false": "jimaku search, retried with anime=false (live action)",
             "kitsu": "Kitsu -> AniList id -> jimaku search"}


def register(parser):
    parser.add_argument("filename", help="a video's filename (a path is fine; only its name is read)")
    parser.add_argument("--fixtures", metavar="DIR",
                        help="answer from recorded responses under DIR instead of the network")
    parser.add_argument("--explain", action="store_true", help="list every entry that was scored")
    parser.add_argument("--no-cache", action="store_true",
                        help="neither read nor write the resolution cache")
    parser.add_argument("--verbose", action="store_true",
                        help="show the last call's rate-limit headers")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


class _NoCache(object):
    path = None
    notes = ()

    def get(self, key):
        return None

    def put(self, key, resolved):
        pass


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _fail(args, message, client=None, kitsu=None):
    cost = ""
    if client is not None:
        cost = "; %s and %s spent" % (_plural(client.metered, "API call"),
                                      _plural(kitsu.calls if kitsu else 0, "Kitsu call"))
    if args.json:
        print(json.dumps({"ok": False, "error": message,
                          "calls": client.metered if client else 0,
                          "kitsu_calls": kitsu.calls if kitsu else 0}, ensure_ascii=False))
    else:
        sys.stderr.write("hato identify: %s%s\n" % (message, cost))
    return EXIT_FAILED


def _season(season):
    return "no season" if season is None else "season %d" % season


def render(name, info, ident, client, cache, fixtures, explain=False, verbose=False):
    """-> the human-readable report, as lines."""
    out = ["hato identify  %s" % name, ""]
    out.append('  parsed    "%s" · %s' % (info.title, _season(info.season)))
    r = ident.resolved
    if r is None:
        out.append("  entry     NOT FOUND")
        for part in ident.reason.split("; "):
            out.append("            %s" % part)
    else:
        out.append("  entry     %d  %s%s" % (r.entry_id, r.entry_name, "  (movie)" if r.movie else ""))
        out.append("  score     %d · %s" % (round(r.score * 100),
                                            "LOW CONFIDENCE" if r.low_confidence else "confident"))
        if _LOW in ident.reason:
            for part in ident.reason.split(_LOW, 1)[1].split("; "):
                out.append("            %s" % part)
        out.append("  found by  %s" % _FOUND_BY.get(r.source, r.source))
        if r.anilist_id is not None:
            out.append("  anilist   %d" % r.anilist_id)
    out.append("  cost      %s · %s" % (_plural(ident.calls, "API call"),
                                        _plural(ident.kitsu_calls, "Kitsu call")))
    if cache.path is None:
        out.append("  cache     not used (--no-cache)")
    elif ident.cached:
        out.append("  cache     hit -- nothing was asked  (%s)" % cache.path)
    elif r is not None:
        out.append("  cache     stored  (%s)" % cache.path)
    else:
        out.append("  cache     nothing stored -- a miss is never cached")
    for note in cache.notes:
        out.append("  note      %s" % note)
    if fixtures is not None:
        out.append("  served    recorded responses from %s -- nothing left this machine" % fixtures)
    if verbose:
        rate = " · ".join("%s: %s" % kv for kv in sorted(client.last_rate_headers.items()))
        out.append("  rate      %s" % (rate or "no metered call was made"))
    if explain and ident.candidates:
        by_source = []
        for c in ident.candidates:
            if not by_source or by_source[-1][0] != c.source:
                by_source.append((c.source, []))
            by_source[-1][1].append(c)
        for source, group in by_source:
            out.append("")
            out.append("  scored    %s · %s" % (_FOUND_BY.get(source, source), _plural(len(group), "result")))
            width = max(len(str(c.id)) for c in group)
            for c in group:
                if not c.accepted:
                    note = "below the match floor"
                elif not c.season_ok:
                    note = "%s -- not the video's" % _season(c.season)
                else:
                    note = _season(c.season)
                out.append("    %3d  %*s  %-44s  %s" % (round(c.score * 100), width, c.id,
                                                        c.name[:44], note))
    return out


def run(args):
    name = re.split(r"[\\/]", args.filename)[-1]
    try:
        with Cache().workdir("identify") as work:
            info, = read_names([name], work)
    except (paths.PathError, OSError) as exc:
        return _fail(args, "could not read the name %r: %s" % (name, exc))
    if info.skipped:
        return _fail(args, "tsubasa's parser skipped %r: %s" % (name, info.skipped))
    if not info.title:
        return _fail(args, "no title could be read from %r, and an empty query would return "
                           "jimaku's entire catalogue -- nothing was sent. Pass a video's "
                           "filename, extension included." % name)

    fixtures = Path(args.fixtures) if args.fixtures else None
    try:
        session = RecordedSession(fixtures) if fixtures is not None else None
    except NoRecording as exc:
        return _fail(args, str(exc))
    if fixtures is not None:
        key = credentials.Key(STAND_IN_KEY, "--fixtures")
    else:
        try:
            key = credentials.resolve_key()
        except (credentials.KeyMissing, paths.PathError) as exc:
            return _fail(args, str(exc))

    client = JimakuClient(key, session)
    kitsu = KitsuClient(session)
    cache = _NoCache() if args.no_cache else ResolutionCache()
    try:
        ident = identify(info.title, season=info.season, client=client, cache=cache, kitsu=kitsu)
    except (JimakuError, NoRecording) as exc:
        return _fail(args, str(exc), client, kitsu)

    if args.json:
        r = ident.resolved
        print(json.dumps({
            "ok": True, "filename": name, "title": info.title, "season": info.season,
            "resolved": dict(r._asdict()) if r is not None else None,
            "calls": ident.calls, "kitsu_calls": ident.kitsu_calls, "cached": ident.cached,
            "reason": ident.reason, "candidates": [dict(c._asdict()) for c in ident.candidates],
            "cache": str(cache.path) if cache.path is not None else None,
            "notes": list(cache.notes), "fixtures": str(fixtures) if fixtures else None,
            "rate_headers": client.last_rate_headers}, ensure_ascii=False, sort_keys=True))
        return EXIT_OK
    print("\n".join(render(name, info, ident, client, cache, fixtures, args.explain, args.verbose)))
    return EXIT_OK
