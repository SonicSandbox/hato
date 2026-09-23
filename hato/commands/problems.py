# -*- coding: utf-8 -*-
u"""List the episodes that still need you -- what hato remembers, checked against the disk.

    hato problems [--json]

⭐ RUNBOOK 8c. Every episode an earlier run could not settle -- a pick waiting
for a person, one jimaku does not have yet, one that went wrong -- whichever run
last looked at it. The state DB proposes; the disk decides (`hato/problems.py`),
so a subtitle that has appeared since takes its episode off this list, and the
DB is not written to say so.

`--json`: one `{"type": "video", "source": "memory", ...}` object per episode --
the same shape a run's `--json` prints -- then one summary object:

    {"type": "problems", "count": N, "lang": "ja",
     "retry_days": {"soft": 1, "hard": 30}, "next_due": "<ISO>" | null}

`next_due` is the soonest retry still in the future. ⚠ Notes about the DB go to
stderr, so stdout stays pure NDJSON.

⛔ READ-ONLY, and it never creates a state DB that is not there -- with none,
nothing needs you. ⛔ The engine's word "refused" never reaches the plain list
(`spec/05-interface.md` §The window: *"when it says 'refused' it's quite
alarming"*): that group reads *needs a pick* and says the timing did not hold.

Exit codes: 0 it ran, whatever it found · 1 a broken config or data location, or
a state DB that could not be read -- its own message on stderr, and under
`--json` one `{"type": "problems", "ok": false, "error": ...}` object. ⛔ Never
exit 0 with an empty list it could not know was empty.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from hato import config, paths, present, problems, report, state
from hato.cache import Cache

EXIT_OK = 0
EXIT_FAILED = 1

#: The three groups of the plain list, in the order a person acts on them.
PICK, WAIT, TROUBLE = u"pick", u"wait", u"trouble"
HEADINGS = (
    (PICK, u"needs a pick %s the timing did not hold for any file hato tried" % report.DASH),
    (WAIT, u"not on jimaku yet"),
    (TROUBLE, u"had a problem"),
)


def register(parser):
    parser.add_argument("--json", action="store_true",
                        help="one JSON object per episode, then a summary object")


def run(args, now=None):
    u"""`now` is for a check's clock; the CLI passes nothing and it is the real one."""
    now = now if now is not None else datetime.now(timezone.utc)
    try:
        cfg = config.load()
        lang = present.language(cfg.lang)    # ⚠ the RESOLVED tag -- `jpn` is `ja`
        path = paths.state_db_path()
    except (config.ConfigError, paths.PathError, present.LanguageUnknown) as exc:
        sys.stderr.write(u"hato: %s\n" % exc)
        return EXIT_FAILED

    rows, notes, readable = [], [], True
    if path.exists():                   # ⛔ never create a DB that is not there
        # ⛔ repair=False: a VIEW never moves a corrupt DB aside -- the next run
        # does, under its lock (ADVERSARY 2026-09-22 F3a).
        with state.StateDB(path, repair=False) as db:
            readable = db.persistent
            if readable:
                rows = problems.open_problems(cfg, db, Cache(), now=now)
            notes = list(db.notes)

    if not readable:
        # 🚨 NOT "NOTHING NEEDS YOU". An unreadable store answered an empty list
        # and exit 0, and the window emptied Needs you over it (A1b). It is a
        # failure, said as one, and the window keeps what it had.
        if args.json:
            print(json.dumps({"type": "problems", "ok": False, "lang": lang,
                              "error": u" ".join(notes)}, ensure_ascii=False, sort_keys=True))
        for note in notes:
            sys.stderr.write(u"hato: %s\n" % note)
        return EXIT_FAILED

    if args.json:
        for note in notes:
            sys.stderr.write(u"hato: %s\n" % note)
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
        print(json.dumps(summary(rows, lang, now), ensure_ascii=False, sort_keys=True))
        return EXIT_OK

    for note in notes:
        print(u"note  %s" % note)
    for line in plain(rows, now):
        print(line)
    return EXIT_OK


# ---------------------------------------------------------------------------
# --json
# ---------------------------------------------------------------------------

def summary(rows, lang, now):
    u"""The object that closes the `--json` stream. -> dict"""
    return {"type": "problems", "ok": True, "count": len(rows), "lang": lang,
            "retry_days": {state.SOFT: state.SOFT_DAYS, state.HARD: state.HARD_DAYS},
            "next_due": next_due(rows, now)}


def _moment(text):
    if not text:
        return None
    moment = datetime.fromisoformat(str(text))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def next_due(rows, now):
    u"""The soonest `retry_after` still in the future, as the row carries it. -> text or None"""
    ahead = []
    for row in rows:
        moment = _moment(row.get(u"retry_after"))
        if moment is not None and moment > now:
            ahead.append((moment, row[u"retry_after"]))
    return min(ahead)[1] if ahead else None


# ---------------------------------------------------------------------------
# the plain list
# ---------------------------------------------------------------------------

def _group(row):
    u"""-> PICK, WAIT or TROUBLE. ⚠ Anything unexpected is TROUBLE: a row in no
    group would be counted in the header and shown nowhere.

    ⚠ A refusal with NOTHING tried is not a pick -- there is no file to pick. A
    name with no episode number is refused before any download and its fix is a
    rename; filed as a pick it read *"the timing did not hold"* over nothing,
    and filed as a wait it sent a person to wait on jimaku (ADVERSARY 2026-09-22
    F20). It is trouble, and its reason is printed.
    """
    outcome = row.get(u"outcome")
    if outcome == state.REFUSED:
        return PICK if row.get(u"tried_before") else TROUBLE
    if outcome == state.NOT_FOUND:
        return WAIT
    return TROUBLE


#: ⛔ The engine's word, and what a person reads instead. ⚠ The same rule as
#: the window's `gui/app.safe` -- a SECOND COPY, kept because this command must
#: not import the window. `test_problems` holds it to the same sentence.
_ENGINE_WORD = re.compile(u"refus\\w*", re.IGNORECASE)
_HUMAN_SENTENCE = u"the timing did not hold"


def _said(reason):
    u"""A trouble row's reason, made safe for the plain list. -> text"""
    text = u" ".join((reason or u"").split())
    return _HUMAN_SENTENCE if _ENGINE_WORD.search(text) else text


def _episode(value):
    if isinstance(value, float) and not value.is_integer():
        return u"%g" % value
    number = int(value)
    return u"%02d" % number if 0 <= number < 100 else u"%d" % number


def label(row):
    u"""*"Sousou no Frieren S2 01"* -- tsubasa's title, else the file's own name."""
    parts = [row.get(u"title") or os.path.splitext(row.get(u"name") or u"")[0]]
    if row.get(u"season") is not None:
        parts.append(u"S%s" % row[u"season"])
    if isinstance(row.get(u"episode"), (int, float)) and not isinstance(row[u"episode"], bool):
        parts.append(_episode(row[u"episode"]))
    return u" ".join(parts)


def _span(seconds):
    u"""⚠ ROUNDED UP, as the window's own countdown is (`gui/run.py`): a wait of
    13h40m that says 13h reads as broken 40 minutes early."""
    if seconds < 60:
        return u"in a moment"
    if seconds < 3600:
        return u"in %dm" % -(-int(seconds) // 60)
    if seconds < 48 * 3600:
        return u"in %dh" % -(-int(seconds) // 3600)
    return u"in %d days" % -(-int(seconds) // 86400)


def when(row, now):
    u"""When hato looks at this episode again. -> text"""
    moment = _moment(row.get(u"retry_after"))
    if moment is None or moment <= now:
        return u"on the next run"
    return _span((moment - now).total_seconds())


def plain(rows, now):
    u"""-> [line]. The three groups, each line the episode, its file and when."""
    if not rows:
        return [u"Nothing needs you."]
    n = len(rows)
    out = [u"%d episode%s need%s you." % (n, u"" if n == 1 else u"s", u"s" if n == 1 else u"")]
    for group, heading in HEADINGS:
        mine = [row for row in rows if _group(row) == group]
        if not mine:
            continue
        out.append(u"")
        out.append(heading)
        names = [label(row) for row in mine]
        width = max(report.cells(name) for name in names)
        for row, name in zip(mine, names):
            tried = u""
            if group == PICK:
                count = len(row.get(u"tried_before") or ())
                tried = u"%d file%s tried %s " % (count, u"" if count == 1 else u"s", report.DOT)
            line = u"  %s   %s   %slooks again %s" % (
                report.pad(name, width), row.get(u"name") or u"", tried, when(row, now))
            if group == TROUBLE and _said(row.get(u"reason")):
                # ⭐ "had a problem" alone tells a person nothing they can act on
                line += u" %s %s" % (report.DOT, _said(row.get(u"reason")))
            out.append(line)
    return out
