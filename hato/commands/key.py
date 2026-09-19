# -*- coding: utf-8 -*-
"""Say where the jimaku key comes from, or put one in hato's key file.

    hato key --show [--json]           the SOURCE and the last four characters
    hato key --set-from <file> [--json]  copy a key into <root>/key.txt

⭐ THIS IS THE COMMAND A STRANGER RUNS (RUNBOOK 1c). They save the key from
https://jimaku.cc/account -> Developer Access into any text file, point
`--set-from` at it, and hato keeps it in its own per-user folder from then on.
The window writes the same file through the same code, so the two can never
disagree about where the key lives.

🚨 --show PRINTS THE LAST FOUR CHARACTERS AND NOTHING MORE (LEDGER-HOT.md). The
Key object cannot print more even if asked to, and ⛔ the key is never in
config.toml, never in a log and never in an error message.
"""
import json
import sys

from hato import credentials, paths

EXIT_OK = 0
EXIT_FAILED = 1


def register(parser):
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--show", action="store_true",
                      help="say whether the key resolves, from where, and its last four characters")
    what.add_argument("--test", action="store_true", dest="test",
                      help="ask jimaku whether the key actually works. ⚠ Spends "
                           "ONE metered request")
    what.add_argument("--set-from", metavar="FILE", dest="set_from",
                      help="copy the key on that file's last line into hato's "
                           "own key file. Use - to read the key from stdin, so "
                           "it is never written to a second file first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _looked_in():
    """The places --show would read, in order, for a message that helps."""
    try:
        return ["$HATO_JIMAKU_KEY"] + ["%s  (%s)" % (p, source)
                                       for p, source in paths.key_file_candidates()]
    except paths.PathError as exc:
        return ["$HATO_JIMAKU_KEY", str(exc)]


def _show(args):
    try:
        key = credentials.resolve_key()
    except (credentials.KeyMissing, paths.PathError) as exc:
        if args.json:
            print(json.dumps({"found": False, "reason": str(exc), "looked_in": _looked_in()},
                             ensure_ascii=False))
        else:
            print("jimaku key   MISSING")
            print("             %s" % exc)
            for place in _looked_in():
                print("             looked in %s" % place)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"found": True, "hint": key.hint, "source": key.source},
                         ensure_ascii=False))
    else:
        print("jimaku key   found, ending %s" % key.hint)
        print("             from %s" % key.source)
    return EXIT_OK


def _set_from(args):
    try:
        if args.set_from == "-":
            # ⭐ THE WINDOW'S ROAD (RUNBOOK 7a). `--set-from FILE` would make a
            # GUI key field write the secret to a temp file before hato would
            # take it -- a SECOND copy on disk, against LEDGER-HOT.md's first
            # rule. Through a pipe there is no second copy.
            # ⚠ `.buffer` and an explicit utf-8 decode: stdin's own encoding is
            # cp1252 on Windows by default, and a key is ASCII but a mis-paste
            # is not -- a UnicodeDecodeError here would name the key's bytes.
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")
            key, written = credentials.save_key_value(raw)
        else:
            key, written = credentials.save_key_from(args.set_from)
    except (credentials.KeyMissing, paths.PathError, OSError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("hato: the key was not saved -- %s\n" % exc)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"ok": True, "path": str(written), "hint": key.hint},
                         ensure_ascii=False))
        return EXIT_OK
    print("jimaku key   saved, ending %s" % key.hint)
    print("             %s" % written)
    print("             ⛔ never put the key in config.toml -- hato refuses to read one there")
    return EXIT_OK


def _test(args):
    u"""Ask jimaku whether the key actually works. -> an exit code.

    ⭐ RULED BY SONIC, 2026-09-18: *"for adding a jimaku key, if it works it
    should test run it to see if connected, and show that it is connected just
    fine. Just on the key entry, not another time."*

    ⚠ ONE METERED REQUEST, and that is the whole design. `hato doctor` answers
    a much larger question and spends nine; a person who has just pasted a key
    wants one answer -- does this work -- and the budget is 25 per 60 s.
    ⛔ Not run on every launch: *"just on the key entry"*.

    ⚠ A key that RESOLVES is not a key that WORKS. `--show` proves hato found
    one; only jimaku can say whether it will answer to it, and the difference
    is exactly the case somebody pasting a key is worried about.
    """
    from hato.client import JimakuClient, JimakuError, KeyRejected, Unreachable

    try:
        key = credentials.resolve_key()
    except (credentials.KeyMissing, paths.PathError) as exc:
        return _fail_test(args, u"no key to test", str(exc))

    try:
        JimakuClient(key).search(query=u"frieren")
    except KeyRejected as exc:
        return _fail_test(args, u"jimaku refused the key", str(exc))
    except Unreachable as exc:
        return _fail_test(args, u"jimaku could not be reached", str(exc))
    except JimakuError as exc:
        return _fail_test(args, u"the test request failed", str(exc))

    if args.json:
        print(json.dumps({"ok": True, "connected": True, "hint": key.hint,
                          "source": key.source}, ensure_ascii=False))
        return EXIT_OK
    print("jimaku key   connected -- the key works, ending %s" % key.hint)
    print("             from %s" % key.source)
    return EXIT_OK


def _fail_test(args, headline, detail):
    if args.json:
        print(json.dumps({"ok": False, "connected": False,
                          "error": headline, "detail": detail},
                         ensure_ascii=False))
    else:
        sys.stderr.write(u"hato: %s -- %s\n" % (headline, detail))
    return EXIT_FAILED


def run(args):
    if args.show:
        return _show(args)
    if getattr(args, "test", False):
        return _test(args)
    return _set_from(args)
