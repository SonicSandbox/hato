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


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK LAYER 15 -- a video with NO subtitle track, and a file picked by its name
# ---------------------------------------------------------------------------
# Signed off by Sonic 2026-09-26: ONE choice of three in Settings → Subtitle format --
# skip it (the default), download one from the same provider, or one that fits the
# episode number. ⚠ NOT TIMED: nothing inside the video can time it. 🚨 His three
# constraints: *"It should NOT be a default option and it should NOT be recommended and
# it should NOT run over and over and over again forever if there will be no file."*
# ⭐ Here because the run, the window and `hato problems` all read the one key.

#: `untimed`, as config.toml spells it.
UNTIMED_OFF = u"off"
UNTIMED_SAME = u"same_provider"
UNTIMED_ANY = u"any_provider"
#: In the order Settings shows them. ⛔ `off` first, and the default.
UNTIMED_CHOICES = (UNTIMED_OFF, UNTIMED_SAME, UNTIMED_ANY)

#: How sure a name is -- the TIER a placed file was chosen at. ⚠ No number: a name-match
#: percentage would stand where the TIMING percentage stands and read as a measurement
#: (fork 4). Measured: the same provider was on time 8 of 8, another provider 0 of 14.
TIER_EXACT = u"exact"         # the file is named exactly as the video
TIER_SAME = u"same"           # the video's own provider, the same source
TIER_OTHER = u"other"         # anyone else -- `any_provider` only
TIERS = (TIER_EXACT, TIER_SAME, TIER_OTHER)

#: ⭐ Fork 13 -- a wait on this road looks once a day for a WEEK from its first miss,
#: then STOPS. ⛔ Only *Look again now* (one look) or a change of the choice looks again.
UNTIMED_WAIT_DAYS = 7

#: The language code a placed file carries -- the MARK (fork 5): `<video>.jpn.<ext>` for a
#: file nobody timed, beside `<video>.ja.<ext>` for one tsubasa timed. Measured to load in
#: mpv under its defaults and under Sonic's config, and in VLC.
UNTIMED_CODE = u"jpn"

_UNTIMED_WORDS = {
    UNTIMED_OFF: u"Skip it",
    UNTIMED_SAME: u"Download one from the same provider",
    UNTIMED_ANY: u"Download one that fits the episode number",
}


def untimed_words(choice):
    u"""The choice, in the words Settings shows it in. -> text"""
    return _UNTIMED_WORDS.get(choice, choice)


def is_untimed_mark(tag):
    u"""Does a subtitle name's language TAG say "not timed"? -> bool

    ⚠ Only the tag: a file is marked when its name says `.jpn.` AND its bytes are one of
    hato's kept originals -- `pipeline` asks the second half. A person's own `.jpn.` file
    is never marked."""
    return (tag or u"").casefold() == UNTIMED_CODE


#: ⚠ The month by table, never `strftime("%b")`: that follows the C library's locale,
#: which a toolkit may set -- and *"until 3 10月"* is not the day the CLI said.
_MONTHS = (u"Jan", u"Feb", u"Mar", u"Apr", u"May", u"Jun", u"Jul", u"Aug", u"Sep", u"Oct",
           u"Nov", u"Dec")


def untimed_day(moment):
    u"""`3 Oct` -- the day a wait on this road stops, in the machine's own zone. -> text

    ⭐ ONE copy: the run, `hato problems` and the window say the same day."""
    local = moment.astimezone()
    return u"%d %s" % (local.day, _MONTHS[local.month - 1])


def untimed_stopped(stops, next_look, now=None):
    u"""⭐ Fork 13's ONE stop rule, for every reader -- the run's row, `hato problems`, the
    window. -> bool. A wait on this road has STOPPED when it has no next look, when its
    next look falls ON OR PAST its stop, or -- given the clock -- when the stop has passed.
    ⚠ 15z (C2): three readers with three rules said *"waiting"*, *"stopped"* and *"retry
    due"* of one row. Aware datetimes; `stops` None is no wait at all."""
    if stops is None:
        return False
    if next_look is None or next_look >= stops:
        return True
    return now is not None and stops <= now


#: The words a wait on this road opens with once its week is out (`untimed.stopped_reason`
#: writes them). ⭐ Here, so every surface -- the window too -- can read a ROW by them.
UNTIMED_STOPPED_LEAD = u"stopped looking — "


def untimed_row_stopped(reason, stops, next_look, now=None):
    u"""`untimed_stopped` for a ROW -- a run's, or a remembered one. -> bool

    ⚠ A row with NO next look is either stopped or a PLAN's (a dry run records nothing, so
    it starts no wait): its own words say which. Any other row, the one rule above."""
    if (reason or u"").startswith(UNTIMED_STOPPED_LEAD):
        return True
    if next_look is None:
        return False
    return untimed_stopped(stops, next_look, now)


def untimed_starts_over(then, waits_for, choice, prefer, fallback):
    u"""⭐ Does a wait on this road begin again at the next run? -> bool

    The CHOICE changed since it began (fork 13: *"changing the choice starts a new
    week"*), or it waits for a FORMAT the settings now take (9a's rule: that wait ends
    when they take it). ⭐ ONE rule: the run obeys it (`pipeline._starts_over`), and `hato
    problems` and the window say *"looks again on the next run"* by it (15z, C4 and D4:
    both said *"stopped looking"*, and the next run looked)."""
    if then != choice:
        return True
    kinds = only_as(waits_for)
    return bool(kinds and accepts_any(kinds, prefer, fallback))


_TIER_WORDS = {TIER_EXACT: u"same provider", TIER_SAME: u"same provider",
               TIER_OTHER: u"another provider"}


def untimed_tier_words(tier):
    u"""`same provider` / `another provider` -- ⛔ never a number (fork 4). -> text, or u""
    for a tier this build does not know (15z, D10: a window reading a newer tray's row
    said *"its name — chosen by its name"*)."""
    return _TIER_WORDS.get(tier, u"")


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
           "of_codec", "UNTIMED_OFF", "UNTIMED_SAME", "UNTIMED_ANY", "UNTIMED_CHOICES",
           "TIER_EXACT", "TIER_SAME", "TIER_OTHER", "TIERS", "UNTIMED_WAIT_DAYS",
           "UNTIMED_CODE", "untimed_words", "is_untimed_mark", "untimed_day",
           "untimed_tier_words", "untimed_stopped", "UNTIMED_STOPPED_LEAD",
           "untimed_row_stopped", "untimed_starts_over"]
