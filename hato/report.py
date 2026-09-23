# -*- coding: utf-8 -*-
u"""
The ruled CLI output (spec/RUNBOOK.md 5a, `spec/05-interface.md` §*The CLI output*).

    text = report.render(run_report, colour=sys.stdout.isatty())
    for line in report.ndjson(run_report):  print(line)

⛔ THE TWO MODES WERE RULED ON 2026-09-07 AND ARE NOT REDESIGNED HERE. This
module reproduces them; it decides nothing about them. Where the mock is silent
the choice is written down in this docstring and a defect is recorded in
`spec/05-interface.md` -- never invented quietly.

===========================================================================
⭐ THE SIX PROPERTIES THAT ARE NOT NEGOTIABLE, AND WHERE EACH LIVES
===========================================================================

1. **Problems first.** `_rows()` emits problems, then skips, then successes,
   for the WHOLE RUN -- not per show. ⚠ With two shows a per-show grouping
   would put show 2's only problem below show 1's nineteen successes, which is
   the exact thing the rule forbids. The show name becomes a column instead.
2. **Evidence on every line.** A success carries `96% · locked`; a skip carries
   the sentence naming the kind; a problem carries the pipeline's reason, which
   `VideoResult` already refuses to leave empty.
3. **`old -> new` shown.** Every written file names its output.
4. ⭐ **The identify block on every run**, including a run that spent nothing --
   then it says so (*"no API call needed"*) rather than being omitted.
5. ⭐ **The API-call count on every run**, per show AND in the summary line.
   `--json` carries it in a final `{"type": "run"}` object (see `ndjson`).
6. **A retry date on every NOT_FOUND.** `_retry_note` appends one when the
   pipeline's reason does not already carry it, and says *"nothing was
   recorded"* on a dry run, where there is no date because no row was written.

===========================================================================
🚨 THE THREE TRAPS THIS MODULE IS THE LAST LINE AGAINST
===========================================================================

1. ⛔ **No raw confidence multiple in the default output.** *"4.6x chance"* is
   an internal decision statistic and means nothing to a person
   (`05-interface.md`). It appears under `--verbose` and in `--json`, and
   `test_endtoend.py` asserts the default output carries no `x`-multiple.
2. ⛔ **Colour degrades when stdout is not a TTY.** Lines are built PLAIN and
   painted last, so "no colour" is the absence of a step rather than a branch
   that can be got wrong -- and every width is measured on the plain text.
3. 🚨 **"Nothing was written" is TWO sentences and they may never collapse
   into one.** `nothing_written()` returns the dry-run sentence or the
   write-failed sentence, never a shared one. `tsubasa` returns
   `CONFIDENT, output_path=None` for both, and a user told *"dry run"* when a
   write really failed stops looking for the file (`hato/port.py`).

===========================================================================
⚠ EAST ASIAN WIDTH, BECAUSE THE TITLES ARE JAPANESE
===========================================================================

`cells()` measures display columns, not characters. A right-aligned stat padded
by `len()` runs a Japanese header a further column off the screen for every
kanji in it -- tsubasa's 3c shipped fifty green checks over exactly that. And
when a left half does not leave room, the stat goes on its own line rather than
pushing the line past `width`.

===========================================================================
⚠ WHAT THE RULED MOCK SAYS THAT THE ENGINE NO LONGER DOES
===========================================================================

The Mode A mock reads `96% · certain`. **`certain` was removed from tsubasa's
closed confidence vocabulary on 2026-09-09** -- it is a substring of
`uncertain`, which re-armed a real defect. The four words are `locked`,
`strong`, `fair`, `uncertain`. This module prints `result.verdict_word`
verbatim, so the shape is the mock's and the word is the engine's. Recorded in
`spec/05-interface.md`.
"""
import json
import os
import re
import unicodedata

from hato import pipeline, port

#: The line width the ruled mocks sit inside. ⚠ A caller with a real terminal
#: passes its own; a log file always gets this one, so a log is comparable
#: between runs and between machines.
DEFAULT_WIDTH = 92
MIN_WIDTH = 64

#: ⭐ How many per-show alignment notes a normal run prints. MEASURED 2026-09-17 on a
#: real library, which is the only place this was ever going to show up: **9 videos
#: produced 272 lines.** Every release that could not be placed gets its own honest
#: three-line explanation, and One Piece's entry alone carries 2,018 files — so the
#: one line a person needed sat under sixty they did not. ⛔ The detail is not wrong
#: and is not deleted: `--verbose` prints every note, and `hato align --explain` is
#: built to answer exactly this question. A report nobody reads to the end reports
#: nothing.
NOTE_CAP = 3

#: The markers. ⭐ `⊘` (no subtitle track) was added to the ruled output on
#: 2026-09-17 and is the one this project most needs to keep distinct from a
#: refusal: it is a skip, before any download (`LEDGER-HOT.md`).
PROBLEM = u"✗"          # ✗
OK = u"✓"               # ✓
FLAGGED = u"⚑"          # ⚑
WARN = u"⚠"             # ⚠
ARROW = u"→"            # →
HOOK = u"↳"             # ↳
DOWN = u"↓"             # ↓
REUSED = u"↻"           # ↻
DOT = u"·"              # ·
DASH = u"—"             # —
ELLIPSIS = u"…"         # …
SUB = u"⤷"              # ⤷

#: skip kind -> (marker, the sentence). ⚠ The sentence is per KIND, not per
#: video: the rows are collapsed onto one line and a per-video reason could not
#: be shown on it. The per-video reason is in `--json` and `--verbose`.
SKIPS = (
    (pipeline.PRESENT, u"⊙", u"subtitle already present " + DASH
     + u" skipped, no request made"),
    (pipeline.NO_TRACK, u"⊘", u"no subtitle track in the video " + DASH
     + u" can't sync yet, nothing downloaded"),
    (pipeline.EMBEDDED, u"⊡", u"a Japanese subtitle is already inside the video "
     + DASH + u" nothing to fetch"),
    (pipeline.BLACKLISTED, u"⊠", u"blacklisted by you " + DASH
     + u" `hato blacklist --remove` puts it back"),
    (pipeline.NEGATIVE, u"⊖", u"asked for recently and not there yet " + DASH
     + u" `--force` asks again now"),
)
SKIP_MARK = dict((kind, mark) for kind, mark, _s in SKIPS)
SKIP_SENTENCE = dict((kind, sentence) for kind, _m, sentence in SKIPS)

#: The problem labels, widest first so the column is stable.
PROBLEM_LABEL = {pipeline.NOT_FOUND: u"NOT FOUND",
                 pipeline.REFUSED: u"REFUSED",
                 pipeline.ERROR: u"ERROR"}

#: ⭐ The summary line's vocabulary and ORDER, taken from the ruled mock:
#: *17 fetched · 3 skipped · 2 can't sync yet · 1 not found · 1 refused*.
#: Everything after those five is a state the mock did not happen to contain.
SUMMARY = (
    (pipeline.CONFIDENT, u"fetched", u"fetched"),
    (pipeline.PRESENT, u"skipped", u"skipped"),
    (pipeline.NO_TRACK, u"can't sync yet", u"can't sync yet"),
    (pipeline.NOT_FOUND, u"not found", u"not found"),
    (pipeline.REFUSED, u"refused", u"refused"),
    (pipeline.ERROR, u"error", u"errors"),
    (pipeline.BLACKLISTED, u"blacklisted", u"blacklisted"),
    (pipeline.EMBEDDED, u"already embedded", u"already embedded"),
    (pipeline.NEGATIVE, u"waiting to retry", u"waiting to retry"),
    (pipeline.PLANNED, u"to fetch", u"to fetch"),
)

#: 🚨 THE TWO SENTENCES. They share no leading words on purpose: a person
#: skimming a log reads the first three and must not have to read further to
#: know whether their file is missing.
DRY_RUN_SENTENCE = u"you asked for a dry run, so nothing was written"
WRITE_FAILED_SENTENCE = u"it could not be written"

_ANSI = re.compile(u"\x1b\\[[0-9;]*m")

#: marker -> SGR. ⛔ Applied to finished PLAIN lines and nowhere else.
_PAINT = {PROBLEM: u"\x1b[31m", OK: u"\x1b[32m", FLAGGED: u"\x1b[33m",
          WARN: u"\x1b[33m", HOOK: u"\x1b[36m"}
_DIM = u"\x1b[2m"
_RESET = u"\x1b[0m"


# ---------------------------------------------------------------------------
# measuring and laying out
# ---------------------------------------------------------------------------

def cells(text):
    u"""Display columns, not characters. ⚠ A kanji is two.

    `05-interface.md`'s mocks are Japanese, and `len()` on them under-counts by
    one column per character -- which is how a right-aligned stat walks off the
    screen and every check still passes.
    """
    total = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in (u"W", u"F") else 1
    return total


def pad(text, want):
    u"""`text` padded to `want` display columns (never truncated)."""
    return text + u" " * max(want - cells(text), 0)


def clip(text, want, left=False):
    u"""`text` cut to `want` columns, with `…` marking where. `left` keeps the
    TAIL, which is what a filename wants -- `…S2 - 03.ja.ass`."""
    if cells(text) <= want:
        return text
    if want <= 1:
        return ELLIPSIS
    if left:
        out = u""
        for ch in reversed(text):
            if cells(out) + cells(ch) > want - 1:
                break
            out = ch + out
        return ELLIPSIS + out
    out = u""
    for ch in text:
        if cells(out) + cells(ch) > want - 1:
            break
        out += ch
    return out + ELLIPSIS


def pair(left, right, width, gap=2):
    u"""`left` ... `right`, right-aligned at `width`. -> [line] (one or two)

    ⚠ TWO LINES WHEN IT DOES NOT FIT, never a line past `width`. A negative pad
    silently becomes zero in most formatters and the stat then sits jammed
    against a title that has already run off the screen.
    """
    if not right:
        return [left.rstrip()]
    room = width - cells(right)
    if cells(left) + gap <= room:
        return [pad(left, room) + right]
    return [left.rstrip(), pad(u"", max(room, 0)) + right]


def wrap(text, width, first=u"", rest=u""):
    u"""Wrap on spaces, measured in COLUMNS. -> [line]

    ⚠ A TOKEN LONGER THAN THE LINE IS BROKEN, not left to run off the screen.
    Found by looking at a real run: an ERROR reason carried an absolute path
    that alone was wider than the line, and the terminal then wrapped it itself
    -- at a column of its choosing and with NO hanging indent, which is strictly
    worse than breaking it here. ⛔ The header does the opposite (it clips with
    `…`) because a header has to stay one line; a reason does not.
    """
    lines, current = [], first
    prefix, opened = first, False
    for word in (text or u"").split():
        candidate = (current + u" " + word) if opened else (current + word)
        if opened and cells(candidate) > width:
            lines.append(current.rstrip())
            current, prefix, opened = rest, rest, False
            candidate = rest + word
        while cells(candidate) > width and cells(word) > width - cells(rest):
            room = width - cells(current if not opened else current + u" ")
            head = clip(word, room + 1) if room > 1 else u""
            head = head[:-1] if head.endswith(ELLIPSIS) else head
            if not head:
                break
            lines.append(((current + u" " if opened else current) + head).rstrip())
            word = word[len(head):]
            current, prefix, opened = rest, rest, False
            candidate = rest + word
        current, opened = candidate, True
    if opened or not lines:
        lines.append(current.rstrip())
    return [ln for ln in lines if ln.strip()] or [prefix.rstrip()]


def strip_ansi(text):
    u"""⛔ Defensive only. Nothing here paints a line it then has to clean."""
    return _ANSI.sub(u"", text)


def paint(text):
    u"""Colour finished PLAIN lines by their marker. ⛔ The LAST step, always."""
    out = []
    for line in text.split(u"\n"):
        stripped = line.lstrip()
        mark = stripped[:1]
        if mark in _PAINT:
            out.append(u"%s%s%s" % (_PAINT[mark], line, _RESET))
        elif mark in SKIP_MARK.values():
            out.append(u"%s%s%s" % (_DIM, line, _RESET))
        else:
            out.append(line)
    return u"\n".join(out)


# ---------------------------------------------------------------------------
# small readings of one result
# ---------------------------------------------------------------------------

def episode(result):
    u"""The episode column. ⚠ Falls back to the filename: a video whose number
    could not be read is exactly the one a person needs named."""
    number = result.episode
    if isinstance(number, (list, tuple)) and number:
        number = number[0]
    if isinstance(number, int) and not isinstance(number, bool):
        return u"%02d" % number if 0 <= number < 100 else u"%d" % number
    return clip(os.path.splitext(result.name)[0], 14, left=True)


def size(nbytes):
    if nbytes >= 1024 * 1024:
        return u"%.1f MB" % (nbytes / (1024.0 * 1024.0))
    if nbytes >= 1024:
        return u"%d KB" % round(nbytes / 1024.0)
    return u"%d B" % nbytes


def clock(seconds):
    u"""`@3:18` -- where a cut file's offset changes."""
    seconds = int(round(seconds))
    return u"%d:%02d" % (seconds // 60, seconds % 60)


def offsets(result):
    u"""`+0.13s`, or `-33.07 / -42.96 @3:18` for a cut file. -> text

    ⚠ tsubasa's `segments` are `(boundary_time_or_None, offset)` and the LAST
    boundary is None -- it runs to the end of the file.
    """
    segments = list(getattr(result, "segments", None) or ())
    if not segments:
        return u""
    if len(segments) == 1:
        return u"%+.2fs" % segments[0][1]
    shifts = u" / ".join(u"%+.2f" % off for _t, off in segments)
    breaks = [t for t, _off in segments if t is not None]
    return u"%s @%s" % (shifts, u",".join(clock(t) for t in breaks)) if breaks else shifts


def verdict(result):
    u"""`96% · locked · 2 segments`. ⛔ Never a bare tick, and ⛔ never the raw
    multiple -- that is `--verbose` and `--json` only."""
    parts = [u"%d%%" % int(round((result.match_rate or 0.0) * 100.0))]
    if result.verdict_word:
        parts.append(result.verdict_word)
    count = len(getattr(result, "segments", None) or ())
    if count > 1:
        parts.append(u"%d segments" % count)
    return (u" %s " % DOT).join(parts)


def flagged(result):
    u"""A written file that carries a caveat -> `⚑` rather than `✓`.

    ⚠ RULED HERE, because the mock shows `⚑` on a two-segment row and says no
    more. A cut file and a runtime check that FAILED are the two things a person
    should look at in a file the tool nonetheless stands behind; everything else
    is `✓`. Recorded in `spec/05-interface.md`.
    """
    if result is None:
        return False
    if len(getattr(result, "segments", None) or ()) > 1:
        return True
    return getattr(result, "runtime_check", u"absent") == u"failed"


def nothing_written(result):
    u"""🚨 THE TWO SENTENCES, AND NEVER A SHARED ONE. -> text or None

    `tsubasa` returns `CONFIDENT` with no `output_path` for BOTH a dry run and a
    write that was attempted and did not land (`hato/port.py`, measured). They
    are different outcomes for the person: one means *there was never going to
    be a file*, the other means *your file is missing and here is why*.
    """
    if result is None or result.outcome != port.CONFIDENT or result.output_path:
        return None
    lead = (WRITE_FAILED_SENTENCE if getattr(result, "write_failed", False)
            else DRY_RUN_SENTENCE)
    return u"%s %s %s" % (lead, DASH, port.why_nothing_was_written(result))


def unwritten_note(video_result):
    u"""The same, looked for on the RESULT and on every attempt under it.

    ⚠ The pipeline folds a write failure into a REFUSED video whose reason says
    *"Best attempt: ... NOT WRITTEN: ..."*, which is true and is not the
    sentence. This lifts it back out so the row carries it in its own words.
    """
    for candidate in [video_result.tsubasa] + [a.tsubasa for a in video_result.attempts or ()]:
        said = nothing_written(candidate)
        if said:
            return said
    return None


def retry_note(result):
    u"""⭐ A RETRY DATE ON EVERY NOT_FOUND -- the property, enforced here.

    The pipeline appends one to its reason when it records a row. On a dry run
    it records nothing, so there is no date and the line says that instead of
    being silent about it.
    """
    if result.retry_after is not None:
        stamp = result.retry_after.strftime(u"%Y-%m-%d")
        if stamp in (result.reason or u""):
            return u""
        return u"will retry after %s" % stamp
    return u"nothing was recorded, so nothing is scheduled (dry run)"


def output_of(result):
    if not result.output_path:
        return u""
    return clip(os.path.basename(result.output_path), 34, left=True)


# ---------------------------------------------------------------------------
# the rows
# ---------------------------------------------------------------------------

def _sort_key(result):
    number = result.episode
    if isinstance(number, (list, tuple)) and number:
        number = number[0]
    if isinstance(number, int) and not isinstance(number, bool):
        return (0, number, result.name)
    return (1, 0, result.name)


def _label_width(results):
    present = set(r.outcome for r in results)
    widths = [cells(PROBLEM_LABEL[o]) for o in present if o in PROBLEM_LABEL]
    return max(widths) if widths else 0


def _problem_rows(results, width, show_col, verbose):
    out, label_w = [], _label_width(results)
    for r in sorted(results, key=_sort_key):
        head = u"  %s  %s%s   %s   " % (PROBLEM, pad(show_col(r), 0),
                                        pad(episode(r), 2), pad(PROBLEM_LABEL[r.outcome], label_w))
        indent = u" " * cells(head)
        reason = r.reason or u""
        if r.outcome == pipeline.NOT_FOUND:
            note = retry_note(r)
            if note:
                reason = u"%s %s %s" % (reason, DASH, note)
        out.extend(wrap(reason, width, first=head, rest=indent))
        said = unwritten_note(r)
        if said:
            out.extend(wrap(said, width, first=indent + WARN + u" ", rest=indent + u"  "))
        if verbose:
            out.extend(_verbose_attempts(r, indent, width))
    return out


def _skip_groups(results, show_col):
    u"""(skip kind, show label) -> [result]. ⭐ THE SHOW IS PART OF THE KEY.

    🚨 FOUND BY LOOKING AT A REAL TWO-SHOW RUN. The rows of a kind are collapsed
    onto ONE line, and the key was the kind alone -- so every show's skips of
    that kind shared a line, and the line carried `show_col(rows[0])`: ONE
    label, the first show's. Measured: `⊙ frieren S1  01 09` where 01 was S2's
    and S1 has no episode 1 skipped. A row that names the wrong show is worse
    than one that names none, because a person acts on it.
    """
    groups, order = {}, []
    for r in results:
        key = (r.skip, show_col(r))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    return groups, order


def _skip_rows(results, width, show_col):
    out = []
    groups, order = _skip_groups(results, show_col)
    known = [kind for kind, _m, _s in SKIPS]
    for kind, mark, sentence in SKIPS:
        for key in [k for k in order if k[0] == kind]:
            rows, label = groups[key], key[1]
            line = sentence
            if kind == pipeline.NEGATIVE:
                dates = sorted(r.retry_after for r in rows if r.retry_after is not None)
                if dates:
                    line = u"%s (the first is due %s)" % (line,
                                                          dates[0].strftime(u"%Y-%m-%d"))
            numbers = u" ".join(episode(r) for r in sorted(rows, key=_sort_key))
            head = u"  %s  %s" % (mark, label)
            block = pad(numbers, 16)
            out.extend(wrap(line, width, first=head + block + u" ",
                            rest=u" " * cells(head + block) + u" "))
    for key in sorted([k for k in order if k[0] not in known], key=lambda k: (str(k[0]), k[1])):
        # ⚠ A skip kind this module has never heard of is NAMED, not dropped.
        rows, label = groups[key], key[1]
        numbers = u" ".join(episode(r) for r in sorted(rows, key=_sort_key))
        head = u"  %s  %s%s " % (WARN, label, pad(numbers, 18))
        out.extend(wrap(u"skipped: %s" % key[0], width, first=head,
                        rest=u" " * cells(head)))
    return out


def _success_rows(results, width, show_col, verbose):
    out = []
    for r in sorted(results, key=_sort_key):
        t = r.tsubasa
        mark = FLAGGED if flagged(t) else OK
        if r.bytes_downloaded:
            got = u"%s %s" % (DOWN, size(r.bytes_downloaded))
        else:
            got = u"%s kept" % REUSED
        left = u"  %s  %s%s   %s   %s   " % (
            mark, show_col(r), pad(episode(r), 2), pad(got, 7),
            pad(offsets(t) if t is not None else u"", 8))
        head = left + pad(verdict(t) if t is not None else u"", 18)
        tail = u"%s %s" % (ARROW, output_of(r))
        if cells(head) + cells(tail) <= width:
            out.append((head + tail).rstrip())
        else:
            # ⚠ The continuation sits under the VERDICT column, as the ruled
            # mock's cut-file row does -- measured from the line that was
            # actually built, never from a re-counted guess at it.
            out.append(head.rstrip())
            out.append(u" " * cells(left) + tail)
        if verbose:
            out.extend(_verbose_attempts(r, u" " * 6, width))
    return out


def _verbose_attempts(result, indent, width=DEFAULT_WIDTH):
    u"""⭐ `--verbose` ONLY: the raw multiple and every candidate's score.

    ⛔ `05-interface.md` forbids the multiple in the default output -- *"4.6x
    chance" is an internal decision statistic and means nothing to a person.*

    🚨 AND IT WRAPS, LIKE EVERY OTHER ROW. These lines appended raw strings and
    never called `wrap`, so `--verbose` printed five lines up to 125 columns
    while the same run without it printed none over 92. ⚠ `--verbose` is what a
    person is told to run when something is wrong -- the one time the output is
    hardest to read is the one time it has to be readable. Measured 2026-09-17;
    it was invisible because the width check passed no flags.
    """
    out = []
    t = result.tsubasa
    if t is not None:
        out.extend(wrap(
            u"%s raw multiple %.2fx (before the floor %.2fx) · runtime check %s · %s"
            % (SUB, getattr(t, "excess_over_chance", 0.0) or 0.0,
               getattr(t, "raw_excess", 0.0) or 0.0,
               getattr(t, "runtime_check", u"absent"),
               getattr(t, "reference", u"") or u"no reference recorded"),
            width, first=indent, rest=indent + u"  "))
    for attempt in result.attempts or ():
        rate = attempt.match_rate
        out.extend(wrap(u"%s %-8s %s %s" % (
            SUB, attempt.outcome,
            u"--" if rate is None else u"%d%%" % int(round(rate * 100.0)),
            clip(attempt.name, 52, left=True)),
            width, first=indent, rest=indent + u"  "))
    return out


# ---------------------------------------------------------------------------
# the show block -- ⭐ printed on EVERY run
# ---------------------------------------------------------------------------

def _show_title(show):
    name = show.resolved.entry_name if show.resolved is not None else (show.title or u"?")
    if show.season is not None:
        return u"%s  S%d" % (name, show.season)
    return name


def _show_cost(show):
    calls = u"no API call needed" if not show.api_calls else _plural(show.api_calls, u"API call")
    if show.files_listed:
        return u"%s %s %d files listed" % (calls, DOT, show.files_listed)
    return calls


def _show_notes(show, width, first, rest, verbose=False):
    u"""A show's alignment notes, capped unless `--verbose`. -> [line]

    ⚠ The hidden ones are COUNTED and the escape hatch is named in the same
    sentence. ⛔ A silent truncation would be worse than the flood it replaces:
    the person could not tell a quiet run from a trimmed one.
    """
    notes = list(show.notes)
    shown = notes if verbose else notes[:NOTE_CAP]
    out = []
    for note in shown:
        out.extend(wrap(note, width, first=first, rest=rest))
    hidden = len(notes) - len(shown)
    if hidden:
        entry = show.resolved.entry_id if show.resolved is not None else None
        where = (u"`hato align --explain <folder> %d`" % entry) if entry else u"`--verbose`"
        out.extend(wrap(u"and %d more release%s nothing could be placed on %s %s prints "
                        u"every one" % (hidden, u"" if hidden == 1 else u"s", DASH, where),
                        width, first=first, rest=rest))
    return out


def _show_block(show, width, verbose=False):
    out = [u"  " + _show_title(show)]
    parsed = u'%s  %s parsed "%s" %s ' % (u"", HOOK, show.title or u"?", ARROW)
    if show.resolved is not None:
        line = parsed + u"jimaku entry %d" % show.resolved.entry_id
        if show.resolved.low_confidence:
            line += u"  (LOW CONFIDENCE)"
        out.append(line)
    elif show.reason:
        out.extend(wrap(u"NO JIMAKU ENTRY %s %s" % (DASH, show.reason), width,
                        first=parsed, rest=u" " * cells(parsed)))
    else:
        out.append(parsed + u"not looked up %s every video was decided for free" % DASH)
    out.extend(pair(u"", _show_cost(show), width))
    out.extend(_show_notes(show, width, first=u"  %s " % WARN, rest=u"    ",
                           verbose=verbose))
    return out


# ---------------------------------------------------------------------------
# the summary line
# ---------------------------------------------------------------------------

def _plural(n, word, many=None):
    return u"%d %s" % (n, word if n == 1 else (many if many else word + u"s"))


def counts_line(report):
    u"""*17 fetched · 3 skipped · 2 can't sync yet · 1 not found · 1 refused*"""
    counts = report.counts()
    parts = []
    for key, one, many in SUMMARY:
        n = counts.pop(key, 0)
        if n:
            parts.append(u"%d %s" % (n, one if n == 1 else many))
    for key, n in counts.items():          # ⚠ never dropped, even if new
        parts.append(u"%d %s" % (n, key))
    return (u" %s " % DOT).join(parts) or u"nothing to do"


def cost_line(report):
    u"""⭐ ON EVERY RUN. `05-interface.md`: *a user who cannot see the cost
    cannot notice a runaway loop -- and it is the first line a bug report
    needs.*"""
    return u"%s %s %.1f s" % (_plural(report.api_calls, u"API call"), DOT, report.seconds)


# ---------------------------------------------------------------------------
# Mode A -- the normal run
# ---------------------------------------------------------------------------

def _header(report, width, suffix=u""):
    u"""⚠ THE FOLDER IS CLIPPED FROM THE LEFT WHEN IT HAS TO BE. A real path can
    be longer than any terminal, and the ruled mock has no answer for that; the
    tail is the part that identifies the folder, and `…` is already this
    output's word for *"shortened here"* (`…S2 - 03.ja.ass`). ⛔ The alternative
    -- a header running off the screen -- is the defect tsubasa's 3c shipped."""
    settings = report.settings
    folders = list(settings.folders)
    shown = folders[0] if len(folders) == 1 else u"%s  (+%d more)" % (folders[0], len(folders) - 1)
    videos = len(report.results)
    right = _plural(videos, u"video")
    if len(folders) > 1:
        right = u"%s %s %s" % (_plural(len(folders), u"folder"), DOT, right)
    room = width - cells(right) - 2 - cells(u"hato  ") - cells(suffix)
    return pair(u"hato  %s%s" % (clip(shown, max(room, 12), left=True), suffix), right, width)


#: The show column: `LABEL_CELLS` of label in a `LABEL_CELLS + 2` field.
LABEL_CELLS = 16


def _label_for(title, season, room, tag=u""):
    u"""A show's label, at most `room` columns. -> text

    🚨 THE SEASON AND THE TAG ARE NEVER CLIPPED AWAY -- ONLY THE TITLE IS. They
    are the whole difference between two shows, and `clip(title + " S2", 16)`
    threw exactly that away: two Japanese titles sharing an eight-character
    prefix came out byte-identical, which is the `frieren S1`/`S2` defect this
    file already fixed once, re-armed by a length nobody measured against a
    Japanese name (a kanji is TWO columns, so 16 columns is 8 characters).
    """
    tail = (u" S%d" % season if season is not None else u"") + tag
    return clip(title, max(room - cells(tail), 2)) + tail


def _show_labels(shows):
    u"""[show] -> [label], all `LABEL_CELLS` wide at most and ⛔ ALL DISTINCT.

    ⚠ Distinctness is the whole job. `render_run` puts problems first for the
    WHOLE run, so a row's only claim to a show is this label -- two shows
    sharing one makes every row of both unattributable, which is the cost that
    ordering was accepted at (`05-interface.md`).
    """
    keys = [(s.title or u"?", s.season) for s in shows]
    labels = [_label_for(t, s, LABEL_CELLS) for t, s in keys]

    members = {}
    for key, label in zip(keys, labels):
        seen = members.setdefault(label, [])
        if key not in seen:
            seen.append(key)
    if all(len(seen) < 2 for seen in members.values()):
        return labels
    # ⚠ STILL AMBIGUOUS -- two DIFFERENT shows clipped to the same columns. An
    # ordinal is ugly and unambiguous, and it comes out of the TITLE's room, not
    # the season's. ⛔ A label that cannot tell two shows apart is not a label.
    out = []
    for key, label in zip(keys, labels):
        seen = members[label]
        if len(seen) > 1:
            title, season = key
            label = _label_for(title, season, LABEL_CELLS,
                               tag=u"#%d" % (seen.index(key) + 1))
        out.append(label)
    return out


def _show_column(report):
    u"""⚠ Empty for a single show -- which is the ruled mock exactly. With more
    than one, the rows are still run-wide (problems first) so each names its
    show, or a problem would be unattributable."""
    shows = [s for s in report.shows if s.results]
    if len(shows) < 2:
        return lambda r: u""
    # ⚠ THE SEASON IS PART OF THE NAME HERE. Found by looking at a real
    # two-show run: `_discover` groups by (title, season), so `frieren S1`
    # and `frieren S2` are two shows whose TITLE is the same word -- and
    # every row in both was labelled "frieren", which is no label at all.
    by_video = {}
    for show, label in zip(shows, _show_labels(shows)):
        for r in show.results:
            by_video[id(r)] = label
    return lambda r: pad(by_video.get(id(r), u""), LABEL_CELLS + 2)


def render_run(report, width=DEFAULT_WIDTH, verbose=False):
    u"""Mode A. -> [line]"""
    width = max(width, MIN_WIDTH)
    show_col = _show_column(report)
    out = _header(report, width)
    for show in report.shows:
        out.append(u"")
        out.extend(_show_block(show, width, verbose=verbose))

    problems = [r for r in report.results if r.outcome in PROBLEM_LABEL]
    skips = [r for r in report.results if r.outcome == pipeline.SKIPPED]
    wins = [r for r in report.results if r.outcome == pipeline.CONFIDENT]
    planned = [r for r in report.results if r.outcome == pipeline.PLANNED]

    # 🚨 PROBLEMS FIRST. Not per show -- for the whole run.
    for block in (_problem_rows(problems, width, show_col, verbose),
                  _skip_rows(skips, width, show_col),
                  _success_rows(wins, width, show_col, verbose)):
        if block:
            out.append(u"")
            out.extend(block)
    if planned:
        out.append(u"")
        out.extend(_plan_rows(planned, width, show_col))

    if report.stopped:
        out.append(u"")
        out.extend(wrap(u"THE RUN STOPPED HERE %s %s Videos after this point were never "
                        u"looked at." % (DASH, report.stopped), width,
                        first=u"  %s  " % PROBLEM, rest=u"      "))
    out.append(u"")
    out.extend(pair(u"  " + counts_line(report), cost_line(report), width, gap=5))
    for note in report.notes:
        out.extend(wrap(note, width, first=u"  %s " % WARN, rest=u"    "))
    if verbose:
        out.extend(_verbose_tail(report, width))
    return out


def _verbose_tail(report, width):
    u"""⚠ IT TOOK `width` AND NEVER USED IT. Three appended raw strings, one of
    them 97 columns on a 92-column page and `settings: %r` as long as the number
    of folders makes it. Wrapped now, like every other row."""
    out = [u"", u"  --verbose"]
    for text in (u"%s bytes downloaded, %s" % (report.bytes_downloaded,
                                               size(report.bytes_downloaded)),
                 u"settings: %r" % (report.settings,),
                 # ⚠ RECORDED, NOT FAKED: `05-interface.md` asks --verbose for
                 # *every API call with its rate-limit headers*, and
                 # `hato/client.py` keeps only the LAST call's. Printing the last
                 # one and saying so beats inventing a log.
                 u"rate-limit headers: only the LAST metered call's are kept by the "
                 u"client (recorded against 5a)"):
        out.extend(wrap(text, width, first=u"    ", rest=u"      "))
    return out


# ---------------------------------------------------------------------------
# Mode B -- --dry-run, the plan
# ---------------------------------------------------------------------------

def _plan_rows(results, width, show_col):
    out = []
    for r in sorted(results, key=_sort_key):
        head = u"  %s  %s%s   " % (WARN, show_col(r), pad(episode(r), 3))
        out.extend(wrap(r.reason or u"", width, first=head, rest=u" " * cells(head)))
    return out


def _identify_row(show, width):
    counts = u"%d vids %s %d subs" % (len(show.videos), DOT, show.files_listed)
    if show.resolved is None:
        # 🚨 TWO DIFFERENT THINGS, and reporting them alike accused the tool of a
        # failure that never happened. MEASURED 2026-09-17 on a real folder: an
        # Erai-raws release already carrying a Japanese track is decided for free,
        # so nothing is ever ASKED about it -- and this row announced *"no jimaku
        # entry matched -- no reason given"*, which reads as *we looked and failed*.
        # ⛔ `no reason given` is the tell: a real failure always carries one
        # (`hato/resolution.py` joins every `why`). Mode A already told them apart;
        # only the --dry-run block did not.
        head = u"  %s  %s  %s " % (WARN if show.reason else OK,
                                   pad(clip(show.title or u"?", 22), 22), ARROW)
        if not show.reason:
            return wrap(u"not looked up %s every video was decided for free" % DASH,
                        width, first=head, rest=u" " * cells(head))
        return wrap(u"no jimaku entry matched %s %s" % (DASH, show.reason),
                    width, first=head, rest=u" " * cells(head))
    mark = WARN if show.resolved.low_confidence else OK
    out = [u"  %s  %s  %s jimaku %s    %s" % (
        mark, pad(clip(show.title or u"?", 22), 22), ARROW,
        pad(u"%d" % show.resolved.entry_id, 5), counts)]
    if show.resolved.low_confidence:
        head = u"         %s LOW CONFIDENCE %s " % (SUB, DASH)
        out.extend(wrap(u'matched "%s" at %d%% %s it will fetch extra candidates and the '
                        u"timing decides"
                        % (show.resolved.entry_name, int(round(show.resolved.score * 100)), DASH),
                        width, first=head, rest=u" " * cells(head)))
    return out


def render_plan(report, width=DEFAULT_WIDTH, verbose=False):
    u"""Mode B -- `--dry-run`. ⛔ Nothing was downloaded, nothing written. -> [line]

    ⚠ A RECORDED DEFECT, NOT A GUESS. The ruled mock's PLAN block also shows
    `~2.1 MB` and `est. 90 s`. Neither can be computed from what
    `pipeline.run()` returns: a PLANNED result carries the first candidate's
    NAME and no size, the file dicts never leave the run, and no timing model
    exists. Printing a made-up megabyte count in a plan a person decides on is
    worse than omitting it, so this prints the estimate it can stand behind and
    `spec/05-interface.md` carries the defect.
    """
    width = max(width, MIN_WIDTH)
    out = _header(report, width, suffix=u"  --dry-run")
    out.append(u"")
    out.extend(pair(u"  IDENTIFY", _plural(report.api_calls, u"API call"), width))
    for show in report.shows:
        out.extend(_identify_row(show, width))
        out.extend(_show_notes(show, width, first=u"       %s " % WARN,
                               rest=u"         ", verbose=verbose))

    counts = report.counts()
    uncertain = sum(1 for show in report.shows
                    if show.resolved is not None and show.resolved.low_confidence
                    for r in show.results if r.outcome == pipeline.PLANNED)
    parts = []
    for key, word in ((pipeline.PLANNED, u"to fetch"),
                      (pipeline.PRESENT, u"already present"),
                      (pipeline.NO_TRACK, u"no subtitle track"),
                      (pipeline.NEGATIVE, u"waiting to retry"),
                      (pipeline.BLACKLISTED, u"blacklisted"),
                      (pipeline.EMBEDDED, u"already embedded"),
                      (pipeline.NOT_FOUND, u"not on jimaku"),
                      (pipeline.REFUSED, u"refused"),
                      (pipeline.ERROR, u"unreadable")):
        n = counts.pop(key, 0)
        if n:
            parts.append(u"%d %s" % (n, word))
    for key, n in counts.items():
        parts.append(u"%d %s" % (n, key))
    if uncertain:
        parts.append(u"%d uncertain" % uncertain)

    listings = sum(1 for show in report.shows
                   if any(r.outcome == pipeline.PLANNED for r in show.results))
    out.append(u"")
    out.extend(pair(u"  PLAN", u"nothing written", width))
    out.extend(wrap((u" %s " % DOT).join(parts) or u"nothing to do", width,
                    first=u"     ", rest=u"     "))
    out.extend(wrap(u"est. %s to apply this %s identification is cached now, and the "
                    u"downloads themselves are unmetered"
                    % (_plural(listings, u"API call"), DASH),
                    width, first=u"     ", rest=u"     "))

    problems = [r for r in report.results if r.outcome in PROBLEM_LABEL]
    if problems:
        out.append(u"")
        out.extend(_problem_rows(problems, width, _show_column(report), verbose))
    if report.stopped:
        out.append(u"")
        out.extend(wrap(u"THE RUN STOPPED HERE %s %s" % (DASH, report.stopped), width,
                        first=u"  %s  " % PROBLEM, rest=u"      "))
    out.append(u"")
    out.append(u"  Run again without --dry-run to apply.")
    for note in report.notes:
        out.extend(wrap(note, width, first=u"  %s " % WARN, rest=u"    "))
    return out


# ---------------------------------------------------------------------------
# the front door
# ---------------------------------------------------------------------------

def render(report, colour=False, verbose=False, width=DEFAULT_WIDTH):
    u"""-> the finished text. ⛔ `colour` is the caller's TTY answer, never ours."""
    lines = (render_plan if report.settings.dry_run else render_run)(
        report, width=width, verbose=verbose)
    text = u"\n".join(lines).rstrip() + u"\n"
    return paint(text) if colour else text


# ---------------------------------------------------------------------------
# --json -- NDJSON, one object per video
# ---------------------------------------------------------------------------

def _plain(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return dict((str(k), _plain(v)) for k, v in value.items())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def tsubasa_dict(result):
    u"""tsubasa's `Result`, ENUMERATED not listed.

    ⛔ `05-interface.md`: the object is passed through *verbatim -- every field,
    not a re-wrapped subset*. A hand-kept list here would quietly stop carrying
    whatever tsubasa adds next, which is the drift `hato/port.py` exists to
    prevent.
    """
    if result is None:
        return None
    out = {}
    for name in sorted(dir(result)):
        if name.startswith("_"):
            continue
        try:
            value = getattr(result, name)
        except Exception as exc:
            out[name] = u"<raises %s: %s>" % (type(exc).__name__, exc)
            continue
        if callable(value):
            continue
        out[name] = _plain(value)
    return out


def as_dict(result):
    u"""One video, as the library returns it (`05-interface.md` §*`Result`
    carries*) plus `skip` and `attempts`."""
    return {
        "type": "video",
        "video": result.video, "name": result.name,
        "title": result.title, "season": result.season, "episode": _plain(result.episode),
        "outcome": result.outcome, "skip": result.skip, "reason": result.reason,
        "jimaku_entry": result.jimaku_entry, "jimaku_filename": result.jimaku_filename,
        "candidates_tried": len(result.attempts or ()),
        "candidates_offered": result.candidates_offered,
        "tsubasa": tsubasa_dict(result.tsubasa),
        "nothing_written": unwritten_note(result),
        "output_path": result.output_path, "kept_path": result.kept_path,
        "api_calls": result.api_calls, "bytes_downloaded": result.bytes_downloaded,
        "retry_after": _plain(result.retry_after),
        "attempts": [{"name": a.name, "outcome": a.outcome, "reason": a.reason,
                      "bytes": a.bytes, "match_rate": a.match_rate,
                      "path": getattr(a, "path", None),
                      "tsubasa": tsubasa_dict(a.tsubasa)}
                     for a in result.attempts or ()],
        # ⭐ RUNBOOK 8d. Candidates from EARLIER runs, never this one's -- what keeps
        # a pick on offer after the run that made it is forgotten. `path` is the
        # file as it is on disk now, or null when it is gone.
        "tried_before": [{"name": t.name, "outcome": t.outcome, "reason": t.reason,
                          "bytes": t.bytes, "match_rate": t.match_rate, "path": t.path,
                          "when": _plain(t.when)}
                         for t in getattr(result, "tried_before", None) or ()],
        # ⭐ RUNBOOK 8f -- the newest episode on offer, in the video's numbering,
        # so the window can say *probably not out yet*. null when nothing says.
        "newest_offered": getattr(result, "newest_offered", None),
    }


def run_dict(report):
    u"""⭐ THE FINAL OBJECT, AND A DELIBERATE EXTENSION TO THE RULED SHAPE.

    `05-interface.md` says *NDJSON, one object per video* AND, three rows above
    it, that the API-call count is shown on **every run** -- *a user who cannot
    see the cost cannot notice a runaway loop.* A stream of video objects has
    nowhere to carry a run's cost, so one final `{"type": "run"}` object does,
    and every object carries `type` so a consumer can filter rather than guess.
    Recorded in `spec/05-interface.md`.
    """
    return {
        "type": "run",
        "api_calls": report.api_calls, "bytes_downloaded": report.bytes_downloaded,
        "seconds": round(report.seconds, 3), "videos": len(report.results),
        "counts": dict(report.counts()), "stopped": report.stopped,
        "dry_run": bool(report.settings.dry_run),
        "folders": list(report.settings.folders), "lang": report.settings.lang,
        "notes": list(report.notes),
        "shows": [{"title": s.title, "season": s.season, "videos": len(s.videos),
                   "entry": s.entry, "reason": s.reason, "api_calls": s.api_calls,
                   "files_listed": s.files_listed, "notes": list(s.notes),
                   "low_confidence": bool(s.resolved.low_confidence) if s.resolved else None}
                  for s in report.shows],
    }


def ndjson(report):
    u"""-> [line]. One object per video, then the run object."""
    lines = [json.dumps(as_dict(r), ensure_ascii=False, sort_keys=True)
             for r in report.results]
    lines.append(json.dumps(run_dict(report), ensure_ascii=False, sort_keys=True))
    return lines


__all__ = ["DEFAULT_WIDTH", "DRY_RUN_SENTENCE", "WRITE_FAILED_SENTENCE",
           "cells", "clip", "pad", "pair", "wrap", "strip_ansi", "paint",
           "episode", "size", "offsets", "verdict", "flagged", "nothing_written",
           "unwritten_note", "retry_note", "counts_line", "cost_line",
           "render", "render_run", "render_plan", "as_dict", "run_dict",
           "tsubasa_dict", "ndjson"]
