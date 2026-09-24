# -*- coding: utf-8 -*-
"""
Candidate ranking -- who is TRIED first, never who is right
(spec/02-data-model.md §Candidate ranking, spec/06-edge-cases.md §2, RUNBOOK 3b).

    ranking = rank(alignment.per_video[path], allow_ai=False, seen_groups=frozenset())
    print(explain(ranking))

FILTERS first -- a filter is not a rank, and nothing below can rescue a file it removes:
    AI-generated          unless allow_ai. ⚠ An AI `.ass` is still excluded.
    tagged non-Japanese   timing cannot tell a Chinese subtitle from a Japanese
                          one (orchestrator ruling 5; measured: 1 of 233,877 names)
    a duplicate name      the same file offered twice is tried once
    not the preferred     ⭐ RUNBOOK 9a, RULED 2026-09-23 -- with the fallback OFF
      format              only the preferred kind is ever downloaded. Kept apart
                          in `Ranking.other_format` too, because an episode whose
                          EVERY file is the other kind is on jimaku, and must never
                          be told it is not (`hato/formats.py`)

THE KEY, each part compared only when every part above it is equal:
    1 format      ⭐ the PREFERRED family first -- `.ass` (with `.ssa`) unless the
                  person chose `.srt` (9a). With `.ass` preferred this is the
                  2026-09-17 ruling, above everything, "even if it has chinese":
                  .ass, then .ssa, then .srt, then the rest, and inside "the rest"
                  BY EXTENSION. ⚠ The extension is part of the key and not
                  decoration: without it a .vtt and a .sup shared one rank and
                  were ordered by SIZE, which part 6 says never happens.
    2 language    Japanese only, then untagged, then Japanese plus another language
    3 fit         range, overlap, literal, guess (hato/episodes.py QUALITIES)
    4 coverage    the larger share of its release that fitted -- partial fits only
    5 agreement   ⭐ the offset both sides already name (0, or a literal number)
                  before a re-numbered one. Nothing used this, and a release whose
                  only merit was being the same LENGTH as the folder took #1 from
                  one that covered the folder at its own numbers.
    6 version     the higher release version (`06v2` over `06`)
    7 size        bigger first. ⚠ NEVER across a format or a language class --
                  the dual-language file is ~2x the size BECAUSE it carries a
                  second language, and an .ass carries style headers an .srt does
                  not. Parts 1 and 2 sit above it, so two files only ever reach
                  this comparison when they share both.
    8 seen        a release already seen to succeed for this show
    9 name        a stable last resort: the order never depends on input order

⚠ Rank, then escalate. This picks who goes first; the timing verdict decides who wins.
"""
import functools

from hato import formats, tokens
from hato.episodes import QUALITIES

#: The order with `.ass` preferred -- 1.0.2's, and `rank()`'s default.
FORMAT_ORDER = formats.order(formats.DEFAULT_PREFERENCE)
#: ⚠ "unknown" sits between: 60 of entry 11446's 120 files carry no language tag
#: at all (NanakoRaws, shincaps -- broadcast captions), and on jimaku an untagged
#: file is far likelier Japanese-only than one tagged with a second language.
LANGUAGE_ORDER = ("single-ja", "unknown", "multi")

#: 🚨 ONE NAME PER KEY PART, IN KEY ORDER. `_why` finds the first part where two
#: candidates differ BY POSITION, so a key element added without a name here does
#: not merely go unexplained -- every sentence after it describes the wrong part,
#: and the last one raises `IndexError`. Measured 2026-09-17 when `known` was
#: inserted: four checks went red reading *".ass is tried before .ass"* and
#: *"version 1 is tried before version 1"*. `rank()` now asserts the two agree.
_KEY_PARTS = ("known", "format", "language", "fit", "coverage", "agreement", "version",
              "size", "seen", "name")

_LANGUAGE_WORDS = {"single-ja": u"Japanese-only", "unknown": u"untagged",
                   "multi": u"Japanese + another", "non-ja": u"not Japanese"}
_FIT_WORDS = {"range": u"whole-range", "overlap": u"partial", "literal": u"literal-number",
              "guess": u"unbroken-tie guess", "position": u"by-position guess",
              "movie": u"movie"}
# 🚨 EVERY quality needs a word here, and a missing one is not a cosmetic fault: it
# is a `KeyError` from inside `_why`, which runs on the ordinary --explain path.
# Measured 2026-09-17 -- `position` was added to QUALITIES, this table was not, and
# the whole run died on a real folder. The check that now guards it is in
# `test_rank.py`; prose did not, because both halves read as complete on their own.
assert set(_FIT_WORDS) == set(QUALITIES), sorted(set(QUALITIES) ^ set(_FIT_WORDS))


class Ranked(object):
    """One candidate in its place."""

    __slots__ = ("candidate", "key", "reasons")

    def __init__(self, candidate, key):
        self.candidate = candidate
        self.key = key          # the sort tuple, parts in _KEY_PARTS order
        self.reasons = []       # sentences: why here

    def __repr__(self):
        return "Ranked(%r, %r)" % (self.candidate.name[:48], self.key[:6])


class Ranking(object):
    """`ordered` best first; `excluded` [(Candidate, reason)] in input order;
    `other_format` the excluded ones whose only fault was their FORMAT (9a)."""

    __slots__ = ("ordered", "excluded", "other_format")

    def __init__(self):
        self.ordered = []
        self.excluded = []
        self.other_format = []


@functools.lru_cache(maxsize=8192)
def _facts(name):
    """Every token fact ranking needs, computed once per distinct name (Rule 4)."""
    return (tokens.subtitle_format(name), tokens.language_class(name),
            tokens.version(name), tokens.is_ai(name))


def _format_rank(fmt, order=FORMAT_ORDER):
    """⚠ THE TAIL BUCKET CARRIES ITS EXTENSION. `.vtt` and `.sup` are both
    "everything else", and returning one number for both made them EQUAL on
    part 1 -- so two different formats fell through to part 7 and were ordered
    by SIZE, which part 7's own printed reason says never happens. Measured
    2026-09-17; the capture holds only `.ass` and `.srt`, so no check on it
    could ever have seen it. The extension is a stable, meaningless tie-break
    -- exactly what a bucket with no ruled order should have."""
    if fmt in order:
        return (order.index(fmt), u"")
    return (len(order), fmt or u"")


def _language_rank(language):
    """⚠ A class outside the order sorts after it rather than raising: the filter
    above is what keeps `non-ja` out, and it must be the ONLY thing that does --
    a crash here would hide a missing filter behind a traceback."""
    return LANGUAGE_ORDER.index(language) if language in LANGUAGE_ORDER else len(LANGUAGE_ORDER)


def rank(candidates, *, allow_ai=False, seen_groups=frozenset(),
         prefer=formats.DEFAULT_PREFERENCE, fallback=True):
    """-> Ranking. `candidates`: hato.episodes.Candidate for ONE video.

    `prefer` / `fallback` -- the person's format settings (9a). ⚠ The defaults
    here are 1.0.2's behaviour, every format ranked and none dropped; the RUN
    passes `config.toml`'s, whose fallback default is OFF.
    """
    ranking = Ranking()
    seen_names = set()
    kept = []
    order = formats.order(prefer)
    for cand in candidates:
        name = cand.file["name"]
        fmt, language, version, ai = _facts(name)
        if ai and not allow_ai:
            ranking.excluded.append((cand, u"AI-generated -- the name carries a machine-transcription "
                                           u"marker. Whisper output has plausible timing and hallucinated "
                                           u"text; excluded unless --allow-ai, whatever its format."))
            continue
        if language == "non-ja":
            ranking.excluded.append((cand, u"Tagged with another language and no Japanese -- timing cannot "
                                           u"tell a Chinese subtitle from a Japanese one, so it is never "
                                           u"tried."))
            continue
        if name in seen_names:
            ranking.excluded.append((cand, u"A duplicate: the same file is already a candidate."))
            continue
        seen_names.add(name)
        if not formats.accepts(fmt, prefer, fallback):
            # ⭐ 9a -- AFTER the filters above, so a file that is AI or foreign is
            # never counted as "only in the other format": it would not have
            # been taken in any format.
            ranking.excluded.append((cand, u"Not .%s -- you prefer .%s, and \"%s\" is off "
                                           u"in Settings." % (prefer, prefer,
                                                              formats.fallback_words(prefer))))
            ranking.other_format.append(cand)
            continue
        size = cand.file.get("size")
        key = (# 🚨 A GUESS NEVER OUTRANKS A KNOWN NUMBER, whatever its format.
               # MEASURED 2026-09-17, the moment `position` landed: a by-position
               # guess in `.ass` ranked #1 over files whose OWN number read 3,
               # because format sorted before fit. ⭐ Sonic's ruling -- *".ass above
               # all else, even if it has chinese"* -- was about choosing between
               # candidates for the SAME episode, and it still decides every one of
               # those below. It was never about preferring a guessed episode to a
               # known one: which episode a file IS outranks what format it is in.
               1 if cand.quality in ("guess", "position") else 0,
               _format_rank(fmt, order),
               _language_rank(language),
               QUALITIES.index(cand.quality),
               # ⚠ Coverage says how clean a PARTIAL fit is. ⛔ NOT for a `range`
               # fit: one covers the whole folder by definition, and its coverage is
               # the share of the RELEASE that landed -- so comparing it would try a
               # 2-file release that happens to match your folder's length before a
               # complete one that covers every video at its own numbers. A literal
               # match against one video is always 1/(release size) for the same
               # reason.
               -round(cand.coverage, 6) if cand.quality in ("overlap", "guess") else 0,
               # ⭐ THE NUMBER BOTH SIDES ALREADY NAME, before a re-numbered one.
               0 if cand.offset in (None, 0) else 1,
               -version,
               -(size if isinstance(size, int) else 0),
               0 if cand.group in seen_groups else 1,
               name)
        # ⭐ THE CHECK THAT REPLACES REMEMBERING. `_why` reads the key BY POSITION
        # against `_KEY_PARTS`; one added without the other explains the wrong part
        # and eventually raises. Measured 2026-09-17 -- this is cheaper than the four
        # red checks that found it, and it fires on the first ranked candidate.
        assert len(key) == len(_KEY_PARTS), (len(key), len(_KEY_PARTS), _KEY_PARTS)
        kept.append(Ranked(cand, key))
    kept.sort(key=lambda r: r.key)
    for i, r in enumerate(kept):
        fmt, language, version, ai = _facts(r.candidate.file["name"])
        if ai:
            r.reasons.append(u"AI-generated, and allowed by --allow-ai.")
        if i > 0:
            r.reasons.append(u"Below #%d: %s" % (i, _why(kept[i - 1], r, prefer)))
        if i + 1 < len(kept):
            r.reasons.append(u"Above #%d: %s" % (i + 2, _why(r, kept[i + 1], prefer)))
        if len(kept) == 1:
            r.reasons.append(u"The only candidate.")
    ranking.ordered = kept
    return ranking


def _why(upper, lower, prefer=formats.DEFAULT_PREFERENCE):
    """The sentence for the FIRST key part where `upper` beats `lower`."""
    part = next((i for i, (a, b) in enumerate(zip(upper.key, lower.key)) if a != b), len(_KEY_PARTS) - 1)
    uc, lc = upper.candidate, lower.candidate
    ufmt, ulang, uver, _ = _facts(uc.file["name"])
    lfmt, llang, lver, _ = _facts(lc.file["name"])
    what = _KEY_PARTS[part]
    if what == "known":
        return (u"its number is known, not guessed -- a file whose own numbering places it "
                u"is tried before a %s, whatever format either is in."
                % _FIT_WORDS[lc.quality])
    if what == "format":
        if ufmt not in FORMAT_ORDER and lfmt not in FORMAT_ORDER:
            return (u".%s is tried before .%s -- neither is .ass, .ssa or .srt, so nothing "
                    u"ranks them and the extension decides. ⛔ Never their size." % (ufmt, lfmt))
        if prefer != formats.DEFAULT_PREFERENCE:
            return u".%s is tried before .%s -- you prefer .%s (Settings)." % (ufmt, lfmt, prefer)
        return u".%s is tried before .%s (RULED 2026-09-17: .ass above every other format)." % (ufmt, lfmt)
    if what == "language":
        return u"%s is tried before %s, within .%s." % (_LANGUAGE_WORDS[ulang], _LANGUAGE_WORDS[llang], ufmt)
    if what == "fit":
        return u"a %s fit is tried before a %s fit." % (_FIT_WORDS[uc.quality], _FIT_WORDS[lc.quality])
    if what == "coverage":
        return u"more of its release fitted (%d%% against %d%%)." % (
            round(uc.coverage * 100), round(lc.coverage * 100))
    if what == "agreement":
        return (u"both sides already name the same episode -- a file placed at its own number "
                u"is tried before one re-numbered by %s." % _offset_words(lc.offset))
    if what == "version":
        return u"release version %d is tried before version %d." % (uver, lver)
    if what == "size":
        return (u"bigger (%s B against %s B) -- size is only ever compared between .%s %s files."
                % (_bytes(uc), _bytes(lc), ufmt, _LANGUAGE_WORDS[ulang]))
    if what == "seen":
        return u"its release (%s) has already succeeded for this show." % uc.group
    return u"nothing else separates them, so the name decides and the order is stable."


def _offset_words(offset):
    return u"nothing" if offset in (None, 0) else u"%+d" % offset


def _bytes(cand):
    size = cand.file.get("size")
    return u"{:,}".format(size) if isinstance(size, int) else u"?"


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

def explain(ranking):
    """The `hato rank --explain` rendering: every candidate with its key and the
    reason for its place, then everything the filters removed and why."""
    out = [u"%d candidate%s ranked · %d excluded" % (
        len(ranking.ordered), u"" if len(ranking.ordered) == 1 else u"s", len(ranking.excluded))]
    rows = [(u"#", u"format", u"language", u"fit", u"v", u"size B", u"release", u"file")]
    for i, r in enumerate(ranking.ordered):
        c = r.candidate
        fmt, language, version, _ai = _facts(c.file["name"])
        rows.append((u"%d" % (i + 1), u".%s" % fmt if fmt else u"(none)", _LANGUAGE_WORDS[language],
                     u"%s %d%%" % (c.quality, round(c.coverage * 100)), u"%d" % version, _bytes(c),
                     c.group, c.file["name"]))
    widths = [max(len(row[k]) for row in rows) for k in range(7)]
    right = (0, 4, 5)
    for i, row in enumerate(rows):
        cells = [row[k].rjust(widths[k]) if k in right else row[k].ljust(widths[k]) for k in range(7)]
        out.append(u"  " + u"  ".join(cells) + u"  " + row[7])
        if i:
            for reason in ranking.ordered[i - 1].reasons:
                out.append(u"  " + u" " * (widths[0] + 2) + reason)
    if ranking.excluded:
        out.append(u"")
        out.append(u"EXCLUDED")
        for cand, reason in ranking.excluded:
            out.append(u"  %s" % cand.file["name"])
            out.append(u"      %s" % reason)
    return u"\n".join(out)
