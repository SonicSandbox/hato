# -*- coding: utf-8 -*-
"""Say where the jimaku key comes from, or put one in hato's key file.

    hato key --show [--json]           the SOURCE and the last four characters
    hato key --set-from <file> [--json]  copy a key into <root>/key.txt
    hato key --show --service assrt|opensubtitles --json
                                       set or not, and where (Surasura's read, §7.9)

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

#: ⭐ 09-hato-layer.md §7.9 (b), signed for hato 2026-11-12 -- where a learner sets a Chinese
#: key, in the window's own words (its tab and its card). PROVISIONAL words.
WHERE_TO_SET = u"hato → Settings → Chinese subtitles"


def register(parser):
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--show", action="store_true",
                      help="say whether the key resolves, from where, and its last four "
                           "characters (with --service assrt|opensubtitles --json: only "
                           "whether it is set, and where to set it)")
    what.add_argument("--test", action="store_true", dest="test",
                      help="ask jimaku whether the key actually works. ⚠ Spends "
                           "ONE metered request")
    what.add_argument("--set-from", metavar="FILE", dest="set_from",
                      help="copy the key on that file's last line into hato's "
                           "own key file. Use - to read the key from stdin, so "
                           "it is never written to a second file first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    # ⭐ LAYER 20 -- the Chinese sources' keys, the learner's own. Absent: jimaku's, as ever.
    parser.add_argument("--service", choices=sorted(credentials.SERVICES), default="jimaku",
                        help="which key: jimaku (the default), or assrt / opensubtitles "
                             "for Chinese subtitles")


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
        if isinstance(exc, OSError):
            # ⭐ WHAT FAILED AND WHAT TO DO, not a bare errno: the folder is the
            # thing to fix, and HATO_CACHE / HATO_JIMAKU_KEY are the ways round it.
            # ⚠ "read or written": `--set-from FILE` reads the person's own file
            # first, and the errno's path says which of the two it was.
            exc = (u"a file could not be read or written (%s). Make sure that "
                   u"folder is yours and not read-only -- or set HATO_CACHE to a "
                   u"folder you own, or HATO_JIMAKU_KEY to the key -- and try "
                   u"again." % exc)
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


def _other(args):
    u"""⭐ LAYER 20 -- `--service assrt|opensubtitles`: the same three answers, for a Chinese
    source's key. ⛔ The key is read from stdin or a file, never argv; at most its last four
    characters are ever printed. `--test` spends ONE metered request."""
    service = args.service
    name = credentials.SERVICES[service][0]
    if args.show and args.json:
        return _zh_is_set(service, name)
    if args.show:
        try:
            key = credentials.resolve_key(service=service)
        except (credentials.KeyMissing, paths.PathError) as exc:
            print("%s key   MISSING\n             %s" % (name, exc))
            return EXIT_FAILED
        print("%s key   found, ending %s\n             from %s" % (name, key.hint, key.source))
        return EXIT_OK
    if getattr(args, "test", False):
        from hato.chinese import ChineseClient
        from hato.client import JimakuError, KeyRejected, Unreachable
        try:
            key = credentials.resolve_key(service=service)
        except (credentials.KeyMissing, paths.PathError) as exc:
            return _fail_test(args, u"no key to test", str(exc))
        try:
            said = ChineseClient(**{service: key}).check_key(service)
        except KeyRejected as exc:
            return _fail_test(args, u"%s refused the key" % name, str(exc))
        except Unreachable as exc:
            return _fail_test(args, u"%s could not be reached" % name, str(exc))
        except JimakuError as exc:
            return _fail_test(args, u"the test request failed", str(exc))
        if args.json:
            print(json.dumps({"ok": True, "connected": True, "hint": key.hint,
                              "source": key.source, "said": said}, ensure_ascii=False))
        else:
            print("%s key   %s, ending %s" % (name, said, key.hint))
        return EXIT_OK
    from_stdin = args.set_from == "-"         # the window's road: never a second file
    try:
        if from_stdin:
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")
            key, written = credentials.save_key_value(raw, service=service)
        else:
            key, written = credentials.save_key_from(args.set_from, service=service)
    except (credentials.KeyMissing, paths.PathError, OSError) as exc:
        if not isinstance(exc, (credentials.KeyMissing, paths.PathError)):
            exc = (u"a file could not be read or written (%s). Make sure that folder is yours "
                   u"and not read-only -- or set HATO_CACHE to a folder you own, or %s to the "
                   u"key -- and try again." % (exc, credentials.SERVICES[service][1]))
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("hato: the key was not saved -- %s\n" % exc)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"ok": True, "path": str(written), "hint": key.hint},
                         ensure_ascii=False))
    else:
        print("%s key   saved, ending %s\n             %s" % (name, key.hint, written))
    return EXIT_OK


def _zh_is_set(service, name):
    u"""⭐ 09-hato-layer.md §7.9 (b) -- `--show --service assrt|opensubtitles --json`: would a
    run find this key, and where does the learner set it. One line, always these four fields;
    exit 0 set, 1 not. Surasura's Chinese card reads it before a press, to say *set your keys
    in hato* instead of a run that waits an hour for keys that are not there.

    🚨 NOT ONE CHARACTER OF THE KEY -- not its last four (the terminal and the window keep
    those), not the file's path, not a refusal's words (they may name a path): another
    program reads this, and what it reads can end up in its log. "Set" is what a run would
    take (`resolve_key`): an empty variable or a rich-text file is not set. No network.

    ⚠ SINCE hato 1.4.1. hato 1.3.0 and 1.4.0 answer this same command with `found`, the last
    four and the file's path: a client asks only a hato whose `--version` says 1.4.1 or later
    (§7.9), and reads only a line whose `set` is true or false."""
    try:
        credentials.resolve_key(service=service)
        found = True
    except Exception:                         # noqa: BLE001 -- ⛔ ONE LINE, ALWAYS: a stat
        found = False                         # refused (PermissionError) is not a key either
    print(json.dumps({"service": service, "name": name, "set": found, "where": WHERE_TO_SET},
                     ensure_ascii=False))
    return EXIT_OK if found else EXIT_FAILED


def run(args):
    if getattr(args, "service", "jimaku") != "jimaku":
        return _other(args)
    if args.show:
        return _show(args)
    if getattr(args, "test", False):
        return _test(args)
    return _set_from(args)
