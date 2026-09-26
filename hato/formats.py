# -*- coding: utf-8 -*-
u"""
Which subtitle FORMAT a person wants, and whether the other one will do (RUNBOOK 9a).

    formats.accepts(u"srt", prefer=u"ass", fallback=False)   -> False
    formats.order(u"srt")                                    -> ("srt", "ass", "ssa")
    formats.only_as(reason)                                  -> ("srt", "vtt") or None

⭐ RULED BY SONIC, 2026-09-23, from a second user's report (*".srt would be
preferred if possible"*): *"i want setting that asks for preference between the
two, but OFF by default is download if the other type doesn't exist. In other
words, even if you prefer one, if it isn't checked, then it won't download the
other kind."*

  prefer_format    `ass` (the default -- the 2026-09-17 ruling, *".ass above all
                   else"*) or `srt`
  format_fallback  OFF by default: nothing but the preferred kind is downloaded.
                   ON: the preferred kind first, then everything else, in the
                   order 1.0.2 always used -- the other preference, THEN `.vtt`,
                   `.sup` and the rest. ⚠ So its words say *"or another format"*:
                   *"download .srt"* alone promised less than it does (ADVERSARY
                   2026-09-23, 9a #9)

⚠ `.ass` MEANS THE FAMILY. `.ssa` is SubStation Alpha, which `.ass` extends, and
1.0.2 ranked it second for exactly that reason. Everything that is neither
family -- `.vtt`, `.sub`, `.sup` -- is "the other kind" for either preference.

⭐ ONE PLACE FOR THE WORDS TOO. The run records why an episode waits in a sentence
a person reads, and two readers must recognise that sentence afterwards: the
run's own retry gate (so turning the fallback on does not leave the episode
waiting a day) and the window (so it is never shown as *"not on jimaku yet"*,
which would be false -- it IS on jimaku, in the other format). `only_as()` is the
one reader of the sentence `waiting_reason()` writes.

⛔ STANDARD LIBRARY ONLY. The window imports this, and the window never imports
tsubasa or the pipeline.
"""
import re

#: The two a person chooses between, in the order Settings shows them.
PREFERENCES = (u"ass", u"srt")
DEFAULT_PREFERENCE = u"ass"

#: Each preference, as the extensions it covers.
FAMILIES = {u"ass": (u"ass", u"ssa"), u"srt": (u"srt",)}


def order(prefer):
    u"""The format part of the ranking key, preferred family first. -> tuple

    `ass` -> ("ass", "ssa", "srt")   exactly 1.0.2's order
    `srt` -> ("srt", "ass", "ssa")
    """
    first = FAMILIES[prefer]
    rest = tuple(fmt for choice in PREFERENCES if choice != prefer
                 for fmt in FAMILIES[choice])
    return first + rest


def accepts(fmt, prefer, fallback):
    u"""Would a person with these settings take a file in `fmt`? -> bool

    ⛔ With the fallback off only the preferred FAMILY is taken -- not `.vtt`,
    not `.sup`, not the other preference.
    """
    return bool(fallback) or (fmt or u"").lower() in FAMILIES[prefer]


def _as_kinds(kinds):
    u"""⚠ ONE KIND GIVEN BARE IS ONE KIND. `sorted(set(u"srt"))` is three letters,
    and the window's shot script handed a bare string to a writer that now takes
    a list -- *"only as .r, .s or .t"*. Every reader of a kinds argument asks this."""
    return (kinds,) if isinstance(kinds, str) else tuple(kinds or ())


def accepts_any(kinds, prefer, fallback):
    u"""Would these settings take a file in ANY of `kinds`? -> bool

    ⭐ The question a wait is ended by: an episode jimaku has as `.srt` AND
    `.vtt` is taken by a person who now prefers `.srt`, whichever of the two
    there were more of (ADVERSARY 2026-09-23, 9a #4).
    """
    return any(accepts(kind, prefer, fallback) for kind in _as_kinds(kinds))


def fallback_words(prefer):
    u"""The fallback setting, as Settings and every sentence name it. -> text

    ⭐ ONE sentence for the checkbox, the reason a row carries and the button
    that turns it on, so a person reading one can find the others.
    """
    other = [choice for choice in PREFERENCES if choice != prefer][0]
    return u"If there is no .%s, download .%s or another format" % (prefer, other)


def kinds_words(kinds):
    u"""`("srt", "vtt", "sup")` -> `.srt, .sup or .vtt`. Sorted, so one list
    always reads one way -- and `only_as()` reads every shape this writes."""
    kinds = [u".%s" % kind for kind in sorted(set(_as_kinds(kinds)))]
    if len(kinds) < 2:
        return u"".join(kinds)
    return u"%s or %s" % (u", ".join(kinds[:-1]), kinds[-1])


#: 🚨 THE SENTENCE IS ALSO A MARKER -- see the module docstring. Its opening
#: words are matched by `only_as()`; change them in one place and both readers
#: follow, because both call that function.
#: ⚠ EVERY KIND jimaku offers is in it, not the commonest: a wait recorded as
#: *"only as .vtt"* for an episode also offered as `.srt` was never ended by
#: choosing `.srt`, and the window offered *"Download .vtt instead"* to the
#: person who had just chosen it (ADVERSARY 2026-09-23, 9a #4).
_ONLY_AS = u"only as %s on jimaku"
_ONLY_AS_RE = re.compile(r"^only as (\.[a-z0-9]+(?:(?:, | or )\.[a-z0-9]+)*) on jimaku\b")


def waiting_reason(kinds, prefer, count):
    u"""Why an episode waits although jimaku has it. -> text

    `kinds` every format jimaku has it in; `count` how many files that is.
    """
    return (u"%s -- you prefer .%s, and \"%s\" is off in Settings (%d file%s)"
            % (_ONLY_AS % kinds_words(kinds), prefer, fallback_words(prefer), count,
               u"" if count == 1 else u"s"))


def only_as(reason):
    u"""Every format an episode waits in, read back from its reason. -> tuple or None

    ⚠ A reason 1.0.3's first build recorded names ONE kind, and it still reads.
    """
    found = _ONLY_AS_RE.match(reason or u"")
    if not found:
        return None
    return tuple(re.findall(r"\.([a-z0-9]+)", found.group(1)))


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 14c -- a video that already has Japanese subtitles INSIDE it
# ---------------------------------------------------------------------------
# Ruled by Sonic 2026-09-25 (*"I take all your leans. Go"*): ONE choice of three in
# Settings → Subtitle format -- leave them there, download from jimaku anyway, or save
# them beside the video, as a file. Two config keys spell it: `skip_embedded` (read by
# every hato since 1.0.0) and `extract_embedded` (1.0.8). ⭐ Here because the run, the
# window and `hato problems` all have to read the pair ONE way.

#: The choice, as `embedded_choice` answers it.
EMBEDDED_LEAVE = u"leave"
EMBEDDED_FETCH = u"fetch"
EMBEDDED_SAVE = u"save"


def embedded_choice(skip_embedded, extract_embedded):
    u"""The two keys, as the one choice they make. -> leave · fetch · save

    ⭐ `extract_embedded` WINS. The window writes both together; a file saying both
    -- by hand -- asks for the more particular thing, and the run, the window and
    `hato problems` read it alike because all three ask this.
    """
    if extract_embedded:
        return EMBEDDED_SAVE
    return EMBEDDED_LEAVE if skip_embedded else EMBEDDED_FETCH


def of_codec(codec):
    u"""The family a subtitle TRACK comes out as, by its codec. -> `ass`, `srt` or None

    ⚠ ONLY to put the preferred kind first when a video holds several Japanese
    tracks (14c) -- and for a PLAN's guess from the header (14z, C5). ⛔ Never what
    a RUN takes out: that is tsubasa's to say, and it refuses by name whatever it
    does not take.
    """
    word = (codec or u"").upper()
    if u"ASS" in word or u"SSA" in word:
        return u"ass"
    if word in (u"S_TEXT/UTF8", u"S_TEXT/ASCII"):
        return u"srt"
    return None


__all__ = ["PREFERENCES", "DEFAULT_PREFERENCE", "FAMILIES", "order", "accepts",
           "accepts_any", "fallback_words", "kinds_words", "waiting_reason", "only_as",
           "EMBEDDED_LEAVE", "EMBEDDED_FETCH", "EMBEDDED_SAVE", "embedded_choice",
           "of_codec"]
