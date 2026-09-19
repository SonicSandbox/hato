# -*- coding: utf-8 -*-
"""List every file on one jimaku entry, with its size.

    hato files <entry-id>                   names and sizes (1 metered API call)
    hato files <entry-id> --fixtures DIR    the same, answered by recorded responses
                                            (e.g. tests/fixtures) -- no network, no key
    hato files <entry-id> --verbose         ...and the call's rate-limit headers
    hato files <entry-id> --json            the list exactly as jimaku returned it

⛔ It never sends `episode=` -- jimaku silently drops every file whose name it cannot
parse a number from. The whole list is one call.
"""
import json
import sys
from pathlib import Path

from hato import credentials, paths
from hato.client import JimakuClient, JimakuError, NoRecording, RecordedSession

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: Recorded responses were made with a real key and check none. ⛔ The real key is
#: never read for a --fixtures run.
STAND_IN_KEY = "recorded-responses-need-no-key"


def register(parser):
    parser.add_argument("entry_id", metavar="entry-id", help="jimaku's entry id, e.g. 11446")
    parser.add_argument("--fixtures", metavar="DIR",
                        help="answer from recorded responses under DIR instead of the network")
    parser.add_argument("--verbose", action="store_true",
                        help="show the call's rate-limit headers")
    parser.add_argument("--json", action="store_true", help="the list exactly as jimaku returned it")


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _amount(n):
    if n >= 1024 * 1024:
        return "%.1f MB" % (n / (1024.0 * 1024.0))
    return "%.0f KB" % (n / 1024.0)


def render(entry_id, listed, client, fixtures, verbose=False):
    """-> the human-readable listing, as lines. Sorted by name for a person to read;
    --json keeps jimaku's order."""
    sizes = [f.get("size") for f in listed if type(f.get("size")) is int]
    out = ["hato files  entry %d  ·  %s  ·  %s" % (entry_id, _plural(len(listed), "file"),
                                                  _amount(sum(sizes))), ""]
    shown = [(format(f.get("size"), ",") if type(f.get("size")) is int else "?", f.get("name") or "?")
             for f in sorted(listed, key=lambda f: str(f.get("name") or "").casefold())]
    width = max([len(s) for s, _ in shown] + [1])
    for size, name in shown:
        out.append("  %*s  %s" % (width, size, name))
    out.append("")
    tail = _plural(client.metered, "API call")
    if fixtures is not None:
        tail += " · recorded responses from %s -- nothing left this machine" % fixtures
    out.append("  " + tail)
    if verbose:
        rate = " · ".join("%s: %s" % kv for kv in sorted(client.last_rate_headers.items()))
        out.append("  rate  %s" % (rate or "(none)"))
    return out


def run(args):
    fixtures = Path(args.fixtures) if args.fixtures else None
    client = None
    try:
        session = RecordedSession(fixtures) if fixtures is not None else None
        if fixtures is not None:
            key = credentials.Key(STAND_IN_KEY, "--fixtures")
        else:
            key = credentials.resolve_key()
        client = JimakuClient(key, session)
        listed = client.files(args.entry_id)
    except ValueError as exc:
        sys.stderr.write("hato files: %s\n" % exc)
        return EXIT_USAGE
    except (JimakuError, NoRecording, credentials.KeyMissing, paths.PathError) as exc:
        spent = "; %s spent" % _plural(client.metered, "API call") if client is not None else ""
        sys.stderr.write("hato files: %s%s\n" % (exc, spent))
        return EXIT_FAILED
    if args.json:
        print(json.dumps(listed, ensure_ascii=False))
        return EXIT_OK
    print("\n".join(render(int(args.entry_id), listed, client, fixtures, args.verbose)))
    return EXIT_OK
