# -*- coding: utf-8 -*-
u"""Subtitles made from a video's own audio, on this computer (RUNBOOK Layer 19).

    hato speech status [--json]
    hato speech install --model fast|accurate [--gpu] [--json] [--progress]
    hato speech remove [--model fast|accurate|gpu] [--json]
    hato speech pick --model fast|accurate [--json]
    hato speech make PATH... [--model fast|accurate] [--json] [--progress] [--cancel-file FILE]

⛔ `install` IS THE ONLY DOOR TO THE NETWORK HERE, and it is a yes: the window asks first, with the size, once
(19h); typed by hand it is the person's own yes. `make` is offline.

⭐ `--json --progress` speaks NDJSON as a run does: `progress` lines, one `speech` row a file (`make`), and the last
line a `result`. `--cancel-file`: the window's Cancel creates it; `make` stops between files and ends the file it
is on (nothing half-made beside a video), as tsubasa's cancel file does.
"""
import json
import os
import sys

from hato import speech

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

ACTIONS = ("status", "install", "remove", "pick", "make")

#: The row words a person reads (PROVISIONAL, 19h), one per outcome.
WORDS = {u"made": u"made from audio", u"present": u"already has Japanese subtitles",
         u"already": u"already made from audio", u"clash": u"two files here would make one subtitle name",
         u"no_speech": u"no speech heard", u"unreadable": u"couldn't read its audio", u"stopped": u"stopped",
         u"error": u"couldn't make it"}


def register(parser):
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("paths", nargs="*", help="make: the videos, audio files or folders")
    parser.add_argument("--model", choices=speech.MODELS + (speech.GPU,), default=None,
                        help="fast (Parakeet) or accurate (Whisper turbo); remove also takes gpu")
    parser.add_argument("--gpu", action="store_true", help="install: NVIDIA's libraries too (an NVIDIA card)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--progress", action="store_true", help="with --json: progress lines as it goes")
    parser.add_argument("--cancel-file", default=None, help="make: stop when this file appears")


def _out(args, obj, text=None):
    if args.json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    elif text:
        sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _gb(n):
    return u"%.1f GB" % (n / 1e9) if n >= 1e8 else u"%d MB" % max(1, round(n / 1e6))


def _status(args):
    found = speech.status()
    lines = [u"add-on: %s" % (u"installed" if found[u"addon"][u"installed"] else u"not installed")]
    for part in speech.MODELS + (speech.GPU,):
        p = found[u"models"][part]
        lines.append(u"%s: %s" % (part, u"installed (%s)" % _gb(p[u"on_disk"]) if p[u"installed"] else
                                  u"not installed (%s to download)" % _gb(p[u"download"])))
    lines.append(u"picked: %s" % found[u"picked"])
    _out(args, dict(found, type=u"result", ok=True), u"\n".join(lines))
    return EXIT_OK


def _install(args):
    if args.model not in speech.MODELS:
        _out(args, {u"type": u"result", u"ok": False, u"error": u"pick --model fast or accurate"},
             u"pick --model fast or accurate")
        return EXIT_USAGE

    def progress(done, total):
        if args.json and args.progress:
            _out(args, {u"type": u"progress", u"stage": u"downloading", u"done": done, u"total": total})
    try:
        parts = speech.install(args.model, gpu=args.gpu, progress=progress)
    except speech.SpeechError as exc:
        _out(args, {u"type": u"result", u"ok": False, u"error": str(exc)}, str(exc))
        return EXIT_FAILED
    _out(args, {u"type": u"result", u"ok": True, u"installed": parts, u"picked": args.model},
         u"installed: %s" % (u", ".join(parts) or u"nothing new"))
    return EXIT_OK


def _remove(args):
    freed = speech.remove(args.model)
    _out(args, {u"type": u"result", u"ok": True, u"freed": freed}, u"freed %s" % _gb(freed))
    return EXIT_OK


def _pick(args):
    if args.model not in speech.MODELS:
        _out(args, {u"type": u"result", u"ok": False, u"error": u"pick --model fast or accurate"},
             u"pick --model fast or accurate")
        return EXIT_USAGE
    speech.pick(args.model)
    _out(args, {u"type": u"result", u"ok": True, u"picked": args.model}, u"picked: %s" % args.model)
    return EXIT_OK


def _make(args):
    if not args.paths:
        _out(args, {u"type": u"result", u"ok": False, u"error": u"name a video, an audio file or a folder"},
             u"name a video, an audio file or a folder")
        return EXIT_USAGE
    if args.model is not None and args.model not in speech.MODELS:
        _out(args, {u"type": u"result", u"ok": False, u"error": u"pick --model fast or accurate"},
             u"pick --model fast or accurate")
        return EXIT_USAGE
    from hato import config
    try:
        cfg = config.load()
        beside, skip = cfg.write_beside_video, cfg.skip_folders
    except Exception:                                       # noqa: BLE001 -- a config hato can't read: defaults
        beside, skip = True, ()
    cancel = args.cancel_file

    def should_stop():
        return bool(cancel) and os.path.exists(cancel)

    def progress(line):
        if args.json and args.progress:
            _out(args, {u"type": u"progress", u"stage": line.get(u"stage"), u"done": line.get(u"done"),
                        u"total": line.get(u"total"), u"path": line.get(u"path")})
    try:
        rows = speech.make(args.paths, model=args.model, beside=beside, skip=skip, progress=progress,
                           should_stop=should_stop)
    except speech.SpeechError as exc:
        _out(args, {u"type": u"result", u"ok": False, u"error": str(exc)}, str(exc))
        return EXIT_FAILED
    except Exception as exc:                                # noqa: BLE001 -- the lock held, a folder gone
        from hato.runlock import LockHeld
        said = (u"subtitles are already being made from audio" if isinstance(exc, LockHeld) else
                u"%s" % type(exc).__name__)
        _out(args, {u"type": u"result", u"ok": False, u"error": said}, said)
        return EXIT_FAILED
    counts = {}
    for row in rows:
        counts[row[u"outcome"]] = counts.get(row[u"outcome"], 0) + 1
        _out(args, dict(row, type=u"speech", words=WORDS[row[u"outcome"]]),
             u"%s — %s" % (os.path.basename(row[u"path"]), WORDS[row[u"outcome"]]))
    failed = counts.get(u"error", 0)
    _out(args, {u"type": u"result", u"ok": not failed, u"counts": counts},
         u"made %d" % counts.get(u"made", 0))
    return EXIT_FAILED if failed else EXIT_OK


def run(args):
    return {"status": _status, "install": _install, "remove": _remove, "pick": _pick, "make": _make}[args.action](args)
