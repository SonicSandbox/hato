# -*- coding: utf-8 -*-
"""What hato has handed to Surasura, for Surasura's back-fill (RUNBOOK LAYER 16, P12, P19).

    hato-cli pairings --json [--lang ja] [--since <ISO>]

NDJSON on stdout: one `{"type": "pairing", ...}` line per video and language -- the
pairing record v1 hato made (`hato-shapes-v2.md` §3) plus `registered` (`{file_id, at}`
or null) -- the LATEST pairing only, and only one with a `library_path` (a drop still
waiting for an offline library is not a pairing Surasura can find); then
`{"type": "result", "ok": true, "count": N, "complete_since": "..."}`.

⛔ READ-ONLY: no run lock, nothing written (`state.read_pairings`), so a run in
progress never makes Surasura's 60-second wait. ⚠ ASCII-escaped JSON, written as
bytes: a frozen child's stdout encoding is not ours to trust (LEDGER-HOT).

⭐ Fork 4 changed (Sonic, 2026-10-29): only what hato itself recorded through 1.1.0's
hand-off. Subtitles copied by 1.0.x carry no line; Surasura reads any it finds as
ordinary subtitles and has tsubasa check them.

Exit 0 · 1 the store could not be read · 2 usage.
"""
import json
import sys
from datetime import datetime, timezone

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def register(parser):
    parser.add_argument("--json", action="store_true",
                        help="NDJSON, one line per pairing then a result line (the only form)")
    parser.add_argument("--lang", default=None, help="only this language, e.g. ja")
    parser.add_argument("--since", default=None, metavar="ISO",
                        help="only pairings written at or after this UTC time, "
                             "e.g. 2026-10-14T08:00:00Z")


def _moment(text):
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if moment.utcoffset() is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
                            .encode("ascii") + b"\n")


def run(args):
    from hato import state
    if not args.json:
        sys.stderr.write("hato pairings answers only with --json (it is Surasura's)\n")
        return EXIT_USAGE
    since = None
    if args.since is not None:
        since = _moment(args.since)
        if since is None:
            sys.stderr.write("--since %r is not an ISO time such as 2026-10-14T08:00:00Z\n"
                             % args.since)
            return EXIT_USAGE
    try:
        rows, complete_since = state.read_pairings(lang=args.lang)
    except Exception as exc:                          # noqa: BLE001 -- the store unreadable
        _emit({"type": "error", "ok": False, "code": "failed",
               "message": "hato's ledger could not be read: %s" % exc})
        return EXIT_FAILED
    count = 0
    for pairing, registered in rows:
        record = dict(pairing.record)
        record.pop("_series", None)
        if not record.get("library_path"):
            continue
        if since is not None:
            written = _moment(pairing.written_at)
            if written is None or written < since:
                continue
        line = {"type": "pairing"}
        line.update(record)
        line["registered"] = ({"file_id": registered[0], "at": registered[1]}
                              if registered else None)
        _emit(line)
        count += 1
    _emit({"type": "result", "ok": True, "count": count, "complete_since": complete_since})
    sys.stdout.flush()
    return EXIT_OK
