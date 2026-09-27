# -*- coding: utf-8 -*-
u"""
LAYER 15 -- the subtitle a video with NO subtitle track gets, chosen by its NAME
(spec/RUNBOOK.md §LAYER 15, signed off by Sonic 2026-09-26). Pure functions of names.

    provider(name)                        the `[Group]` a name opens with, folded -- or None
    tier(video_name, file_name)           exact · same · other
    choose(ranked, video_name, choice)    [(tier, candidate)] -- the tiers the choice takes

⭐ THE RULE, AS RULED (fork 7). A tier goes AHEAD of rank's key; within one, rank decides
as it always has (the format first):

    exact   the file's stem -- tsubasa's reading, language and flags off -- IS the video's
            stem (normcase). jimaku's `[NanakoRaws] … - 01 (TBS 1080p HEVC AAC).ass` is the
            video's own name, letter for letter, 11 of 12 measured
    same    both names OPEN with a bracketed group, equal ignoring case and every
            character that is not a letter or a digit (`Nanako-Raws` is `NanakoRaws`) --
            ⛔ unless both names state a source and the two share none
            (`tokens.source_classes`: TV · BD · DVD · WEB). A name that states none never
            vetoes, and a broadcaster is TV (`TBS`, `BSN TV` and `TV` are one broadcast)
    other   everything else -- `any_provider` only

🚨 NONE OF THIS IS TIMING. Measured before it was ruled: the same provider was on time 8 of
8 (+0.00 s, against the video's own captions); another provider 0 of 14 (0.28-2.67 s off).
So the tier is WORDS -- *"same provider"*, *"another provider, may be off"* -- and ⛔ never
a number standing where the timing percentage stands (fork 4).

⛔ No I/O. `tsubasa.parse_subtitle_name` is the one tsubasa call, and it is pure too.
"""
import os
from datetime import timedelta

import tsubasa

from hato import episodes, formats, tokens


def provider(name):
    u"""The group `name` opens with in brackets, folded for comparing -- or None.
    ⚠ Folded by `str.isalnum`, not `[0-9a-z]`: a group written in kanji is letters too,
    and stripping it to nothing would make every two such groups one provider.
    ⚠ 15z (B13): `&` and `+` STAY -- `[A&B]` is two groups releasing together, and folded
    away it was the group `[AB]`."""
    group = tokens.bracketed_group(os.path.basename(name))
    if not group:
        return None
    folded = u"".join(ch for ch in group.casefold() if ch.isalnum() or ch in u"&+")
    return folded or None


def provider_shown(name):
    u"""The group `name` opens with, as it is written there -- `NanakoRaws` -- or None."""
    return tokens.bracketed_group(os.path.basename(name))


def tier(video_name, file_name):
    u"""How a file relates to a video, by their NAMES. -> exact · same · other

    ⚠ `exact` only for a video whose name SAYS its provider (15z, B2): an unbracketed
    `Show - 01.srt` beside `Show - 01.mkv` was *"same provider"* with no provider named
    anywhere -- edge 3 says such a video matches nothing under `same_provider`."""
    video_name = os.path.basename(video_name)
    file_name = os.path.basename(file_name)
    stem = os.path.splitext(video_name)[0]
    mine, theirs = provider(video_name), provider(file_name)
    if mine is not None and (os.path.normcase(tsubasa.parse_subtitle_name(file_name).stem)
                             == os.path.normcase(stem)):
        return formats.TIER_EXACT
    if mine is not None and mine == theirs:
        a, b = tokens.source_classes(video_name), tokens.source_classes(file_name)
        if not (a and b and not (a & b)):
            return formats.TIER_SAME
    return formats.TIER_OTHER


#: 🚨 15z's BLOCKER (B1, C1) -- THE ONLY FITS THIS ROAD TAKES: an episode's number PROVEN
#: across its release (`range`, `overlap`), written the same on both sides (`literal`), or
#: a film (`movie`). ⛔ Never `guess` or `position`: those are hypotheses the alignment
#: offers for TIMING to refuse, and this road has none -- with the provider's episode 01
#: missing, its 02 was placed as 01 and called *"same provider"*.
FITS = (u"range", u"overlap", u"literal", u"movie")


#: ⭐ 15z (B6) -- the fewest dialogue lines a file placed by its name may have and still
#: READ as Japanese (`present.reads_as_japanese`). 9b's 100 is a PRESENCE floor -- a file
#: nobody chose, judged by its text alone -- and a short (a 3-minute episode is ~40 lines)
#: could never be placed under it. Here the file was chosen as the episode's Japanese;
#: the read only turns away the wrong script, and its two measured SHARES still do that.
MIN_LINES = 20


def allowed(choice):
    u"""The tiers `choice` takes (fork 7). -> tuple: `same_provider` the first two,
    `any_provider` all three, `off` none."""
    if choice == formats.UNTIMED_ANY:
        return formats.TIERS
    if choice == formats.UNTIMED_SAME:
        return formats.TIERS[:2]
    return ()


def choose(ranked, video_name, choice):
    u"""rank's order with the TIER put ahead of it. -> [(tier, candidate)], best first

    `ranked`  rank's `ordered` candidates for ONE video, filters already applied (AI,
              tagged non-Japanese, duplicates, the format preference) -- `c.file["name"]`
    `choice`  `same_provider` keeps `exact` and `same`; `any_provider` keeps all three.
    ⚠ Stable: within a tier, rank's order stands (the format first)."""
    takes = allowed(choice)
    tiered = [(tier(video_name, c.file[u"name"]), c) for c in ranked]
    tiered = [pair for pair in tiered if pair[0] in takes]
    tiered.sort(key=lambda pair: formats.TIERS.index(pair[0]))
    return tiered


def as_field(tier_, video_name, file_name):
    u"""The `untimed` a placed row carries (`--json`, NDJSON, `api.Result`). -> dict"""
    return {u"tier": tier_, u"provider": provider_shown(file_name),
            u"video_provider": provider_shown(video_name)}


# ---------------------------------------------------------------------------
# the words for this road's waits -- ⛔ none of them names the setting (fork 14)
# ---------------------------------------------------------------------------

def nothing_from(video_name):
    u"""`same_provider` found nothing from the video's own provider. -> text
    ⚠ No *"yet"*: the same words read before the week is out and after it stopped."""
    shown = provider_shown(video_name)
    return (u"nothing from [%s] for this episode on jimaku" % shown if shown
            else u"nothing from this video's provider for this episode on jimaku")


#: The video's name opens with no bracketed group: `same_provider` has nothing to match.
NO_PROVIDER = (u"this video's name doesn't say which provider it came from, so nothing can "
               u"be matched to it")

#: ⭐ 15z (B1) -- jimaku has files near this episode but none PROVEN to be it: only guesses
#: at its number, which timing would have to settle.
NO_FIT = u"no file on jimaku is numbered for this episode"

#: ⭐ 15z (C1) -- the show's jimaku entry is a LOW-CONFIDENCE match (the timed road checks
#: its guess by timing; this one cannot): the S2 entry's episode 01 was placed beside an S1
#: episode 01, *"same provider"*.
UNSURE_SHOW = (u"jimaku's entry for this show is only a likely match, so nothing is placed "
               u"by its name")


#: ⭐ 15z (B5) -- the opening words of a name hato could not find again; also the MARK
#: `is_refusal` reads, since a remembered wait keeps only its words.
_UNCOUNTABLE = u"its subtitle would have to be named "


def uncountable(name, notes=u"", renamed=True):
    u"""A file hato would place under a name it could not find beside the video again.
    -> text. `renamed`: the name is not the video's own (trimmed to fit) -- the one case a
    shorter video name fixes."""
    return (u"%s%s, a name hato could not find beside the video again%s -- so nothing is "
            u"placed%s" % (_UNCOUNTABLE, name, u" (%s)" % notes if notes else u"",
                           u". A shorter video name fixes it" if renamed else u""))


def is_refusal(base):
    u"""⭐ 15z (C9) -- is what this wait waits for the PERSON's to fix, not jimaku's? -> bool

    A video name with no episode number, or one whose subtitle hato could not find again:
    both are fixed by a rename, and filed under *"not on jimaku yet"* a person waited on
    jimaku for ever (the F20 of 2026-09-22, re-armed on this road)."""
    text = (base or u"").rstrip(u". ")
    return text == episodes.NO_EPISODE.rstrip(u". ") or text.startswith(_UNCOUNTABLE)


def none_reads(count):
    u"""Every file for the episode was downloaded and none reads as Japanese. -> text"""
    return (u"none of the %d file%s for this episode reads as Japanese"
            % (count, u"" if count == 1 else u"s"))


def day(moment):
    u"""`3 Oct` -- a stop date, in the machine's own zone: `formats.untimed_day`, the one
    copy the window says too (it cannot import this module: tsubasa). -> text"""
    return formats.untimed_day(moment)


def looks_until(stops):
    u"""-> *"looks once a day until 3 Oct, then stops"* (fork 13)."""
    return u"looks once a day until %s, then stops" % day(stops)


#: 🚨 THE SENTENCES ARE ALSO MARKERS, as `formats.waiting_reason`'s is: a wait's reason is
#: stored, and `base_of` reads what it waited for back out of it -- so a remembered wait
#: can say *"stopped looking"* the day after it said *"looks once a day"*. Change the
#: words here, and both the writer and the reader follow.
_WAITING = u" · looks once a day until "
_STOPPED = formats.UNTIMED_STOPPED_LEAD


def waiting_reason(base, stops):
    u"""-> *"<what it waits for> · looks once a day until 3 Oct, then stops"*"""
    return u"%s%s%s, then stops" % (base.rstrip(u". "), _WAITING, day(stops))


def stopped_reason(base):
    u"""-> *"stopped looking — <what it waited for>"* (fork 13)."""
    return _STOPPED + base.rstrip(u". ")


def base_of(reason):
    u"""What a wait on this road waits for, read back out of its reason. -> text"""
    text = reason or u""
    if text.startswith(_STOPPED):
        text = text[len(_STOPPED):]
    at = text.find(_WAITING)
    return text[:at] if at >= 0 else text


def wait_field(choice, since, base):
    u"""The `untimed_wait` a waiting row carries. -> dict

    ⭐ ABSOLUTE, so a view taken any day reads it alike (`hato problems` never reads the
    clock): the choice it waits under, when it began, when it STOPS -- a week on (fork
    13) -- and what it waits for, in words none of which names the setting (fork 14)."""
    stops = since + timedelta(days=formats.UNTIMED_WAIT_DAYS)
    return {u"choice": choice, u"since": since.isoformat(), u"stops": stops.isoformat(),
            u"waits_for": base}


def tier_words(tier_):
    u"""`same provider` / `another provider` -- ⛔ never a number (fork 4): the one copy is
    `formats.untimed_tier_words`, which the window reads too. -> text"""
    return formats.untimed_tier_words(tier_)


__all__ = ["provider", "provider_shown", "tier", "choose", "allowed", "FITS", "MIN_LINES",
           "as_field",
           "nothing_from", "NO_PROVIDER", "NO_FIT", "UNSURE_SHOW", "uncountable",
           "is_refusal", "none_reads", "day",
           "looks_until", "waiting_reason", "stopped_reason", "base_of", "wait_field",
           "tier_words"]
