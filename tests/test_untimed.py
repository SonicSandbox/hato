# -*- coding: utf-8 -*-
u"""
LAYER 15 -- the untimed road's pure half: which file a video with NO subtitle track gets,
by its NAME (`hato/untimed.py`), and the sources a name states (`tokens.source_classes`).

⭐ Every rule here was RULED (spec/RUNBOOK.md §LAYER 15, fork 7) and MEASURED: the same
provider was on time 8 of 8, another provider 0 of 14 -- so the tier is what a person is
told, in words, and ⛔ never a number standing where the timing percentage stands.

⛔ WHAT THIS SUITE CANNOT COVER: whether the chosen file IS the episode's -- nothing can,
which is the whole reason the road says NOT TIMED everywhere. `test_pipeline.py` §15
drives the road end to end, with the real tsubasa placing the file.
"""
from datetime import datetime, timedelta, timezone

import pytest

from hato import formats, tokens, untimed

VIDEO = u"[NanakoRaws] Seihantai na Kimi to Boku - 01 (TBS 1080p HEVC AAC).mkv"


class C(object):
    u"""A ranked candidate, as `episodes.Candidate` carries its file."""

    def __init__(self, name):
        self.file = {u"name": name}

    def __repr__(self):
        return u"C(%r)" % self.file[u"name"]


# ---------------------------------------------------------------------------
# the tier
# ---------------------------------------------------------------------------

def test_a_file_named_as_the_video_is_exact():
    u"""jimaku's `[NanakoRaws] … - 01 (TBS 1080p HEVC AAC).ass` IS the video's own name --
    11 of 12 measured. ⚠ Its language tag and flags are tsubasa's to strip."""
    for name in (u"[NanakoRaws] Seihantai na Kimi to Boku - 01 (TBS 1080p HEVC AAC).ass",
                 u"[NanakoRaws] Seihantai na Kimi to Boku - 01 (TBS 1080p HEVC AAC).ja.srt"):
        assert untimed.tier(VIDEO, name) == formats.TIER_EXACT, name


def test_the_same_group_is_the_same_provider_whatever_its_punctuation_or_case():
    for name in (u"[NanakoRaws] Seihantai na Kimi to Boku - 01 (TV 1080p HEVC AAC).ass",
                 u"[Nanako-Raws] Seihantai na Kimi to Boku - 01 (BSN TV 1080p).srt",
                 u"[nanakoraws] seihantai - 01.ass"):
        assert untimed.tier(VIDEO, name) == formats.TIER_SAME, name


def test_a_broadcaster_is_tv_so_tbs_and_tv_are_one_source():
    u"""NanakoRaws' own names say `TBS`, `TV` or `BSN TV` for ONE broadcast (measured)."""
    assert tokens.source_classes(VIDEO) == frozenset([u"TV"])
    for name in (u"x (TV 1080p).ass", u"x (BSN TV 1080p).ass", u"x (AT-X 1440x1080).ass",
                 u"x (WOWOW 1920x1080 x265 AAC).ass", u"x (KIDS 1440x1080 MPEG2).ass"):
        assert tokens.source_classes(name) == frozenset([u"TV"]), name


def test_different_sources_from_one_group_are_another_provider():
    u"""⛔ One group's TV capture and its BD are different cuts and different timing."""
    for name in (u"[NanakoRaws] Seihantai na Kimi to Boku - 01 [BD 1080p].ass",
                 u"[NanakoRaws] Seihantai na Kimi to Boku - 01 [DVDRip].ass",
                 u"[NanakoRaws] Seihantai na Kimi to Boku - 01 [WebRip 1080p].ass"):
        assert untimed.tier(VIDEO, name) == formats.TIER_OTHER, name


def test_a_name_that_states_no_source_never_vetoes():
    assert untimed.tier(VIDEO, u"[NanakoRaws] Seihantai - 01.ass") == formats.TIER_SAME
    assert untimed.tier(u"[NanakoRaws] Seihantai - 01.mkv",
                        u"[NanakoRaws] Seihantai - 01 [BD].ass") == formats.TIER_SAME


def test_another_group_or_none_is_another_provider():
    for name in (u"[SweetSub] Seihantai na Kimi to Boku - 01 [WebRip][1080P][CHS&JPN].ass",
                 u"Seihantai.na.Kimi.to.Boku.S01E01.WEBRip.Netflix.ja[cc].srt",
                 u"Seihantai na Kimi to Boku - 01.ass"):
        assert untimed.tier(VIDEO, name) == formats.TIER_OTHER, name


def test_a_video_with_no_bracketed_group_has_no_provider_and_nothing_is_its_own():
    u"""🚨 15z (B2) -- EDGE 3 AS WRITTEN: *"No bracketed provider in the video's name →
    `same_provider` never matches"*. A file named exactly as such a video was tier
    `exact` -- *"same provider"* with no provider named anywhere. It is `other` now:
    `any_provider` goes on, and says *another provider*."""
    video = u"Boku no Kokoro no Yabai Yatsu - 13 (EX 1920x1080 x264 AAC).mkv"
    assert untimed.provider(video) is None
    assert untimed.tier(video, u"Boku no Kokoro no Yabai Yatsu - 13 (EX 1920x1080 x264 "
                               u"AAC).srt") == formats.TIER_OTHER
    assert untimed.tier(video, u"Boku no Kokoro no Yabai Yatsu - 13 (MX).srt") \
        == formats.TIER_OTHER
    bracketed = u"[G] Boku - 13 (EX).mkv"
    assert untimed.tier(bracketed, u"[G] Boku - 13 (EX).ja.srt") == formats.TIER_EXACT


def test_the_provider_s_own_name_and_a_title_s_tv_state_no_source():
    u"""🚨 15z (B8) -- `[TV Raws]` is a GROUP and `Show (TV)` a TITLE: read as a TV source,
    a BD rip took the TBS capture as the same provider. ⭐ A disc is never a broadcast."""
    assert tokens.source_classes(u"[TV Raws] Show - 01 [BD].mkv") == frozenset([u"BD"])
    assert tokens.source_classes(u"[G] Show (TV) - 01 [BD].mkv") == frozenset([u"BD"])
    assert tokens.source_classes(u"[G] Show - 01 (TBS 1080p).ass") == frozenset([u"TV"])
    assert tokens.source_classes(u"[TV Raws] Show - 01.mkv") == frozenset()
    assert untimed.tier(u"[TV Raws] Show - 01 [BD].mkv",
                        u"[TV Raws] Show - 01 (TBS).ass") == formats.TIER_OTHER
    assert untimed.tier(u"[G] Show (TV) - 01 [BD].mkv",
                        u"[G] Show - 01 (TBS 1080p).ass") == formats.TIER_OTHER
    assert untimed.tier(u"[G] Show - 01 (TV).mkv",
                        u"[G] Show - 01 (BSN TV).ass") == formats.TIER_SAME


def test_full_width_brackets_name_a_provider_and_a_joint_release_is_two():
    u"""⚠ 15z (B13) -- `【NanakoRaws】` and `［NanakoRaws］` read as NO provider, so such a
    video matched nothing under `same_provider`; and `[A&B]` folded to the group `[AB]`."""
    for opened in (u"【NanakoRaws】Show - 01.mkv", u"［NanakoRaws］ Show - 01.mkv",
                   u"[NanakoRaws] Show - 01.mkv"):
        assert untimed.provider(opened) == u"nanakoraws", opened
    assert untimed.provider(u"[A&B] Show - 01.ass") != untimed.provider(u"[AB] Show - 01.ass")
    assert untimed.provider(u"[A & B] Show - 01.ass") == untimed.provider(u"[A&B] x.ass")


def test_a_rename_is_what_some_waits_wait_for():
    u"""⭐ 15z (C9) -- a wait whose fix is the PERSON's (a rename): no episode number in the
    name, or a subtitle name hato could not find again. Read back out of a remembered
    wait's words (`base_of`), so `hato problems` files it as trouble, never *"not on
    jimaku yet"*."""
    from hato import episodes
    from datetime import datetime, timezone
    stops = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    for base in (episodes.NO_EPISODE, untimed.uncountable(u"x.jpn.ass", u"", True)):
        said = untimed.waiting_reason(base, stops)
        assert untimed.is_refusal(untimed.base_of(said)), said
        assert untimed.is_refusal(untimed.base_of(untimed.stopped_reason(base)))
    for base in (untimed.nothing_from(u"[G] x - 01.mkv"), untimed.NO_FIT,
                 untimed.none_reads(2), untimed.UNSURE_SHOW):
        assert not untimed.is_refusal(untimed.base_of(untimed.waiting_reason(base, stops)))


def test_a_group_in_kanji_is_letters_not_nothing():
    u"""⚠ Folded by `isalnum`: stripped to `[0-9a-z]`, every two kanji groups would be one."""
    assert untimed.provider(u"[桜都字幕组] x - 01.ass") == u"桜都字幕组"
    assert untimed.tier(u"[桜都字幕组] x - 01.mkv", u"[喵萌奶茶屋] x - 01.ass") \
        == formats.TIER_OTHER


def test_a_call_sign_is_read_only_inside_a_bracket():
    u"""⛔ `kids`, `ex`, `abc` are ordinary title words: a source only in a group."""
    assert tokens.source_classes(u"Kids.on.the.Slope.S01E01.srt") == frozenset()
    assert tokens.source_classes(u"Show.S01E01.WEBRip.srt") == frozenset([u"WEB"])
    assert tokens.source_classes(u"Show.S01E01.HDTV.srt") == frozenset([u"TV"])


# ---------------------------------------------------------------------------
# choosing
# ---------------------------------------------------------------------------

def test_the_tier_goes_ahead_of_rank_and_rank_orders_within_it():
    ranked = [C(u"[SweetSub] Seihantai - 01.ass"),                 # rank's #1: other
              C(u"[NanakoRaws] Seihantai - 01.srt"),                # same
              C(u"[NanakoRaws] Seihantai na Kimi to Boku - 01 (TBS 1080p HEVC AAC).ass"),
              C(u"[NanakoRaws] Seihantai - 01 v2.ass")]            # same
    got = untimed.choose(ranked, VIDEO, formats.UNTIMED_ANY)
    assert [t for t, _c in got] == [u"exact", u"same", u"same", u"other"], got
    assert got[1][1] is ranked[1] and got[2][1] is ranked[3], u"rank's order within a tier"


def test_same_provider_takes_exact_and_same_only():
    ranked = [C(u"[SweetSub] Seihantai - 01.ass"), C(u"[NanakoRaws] Seihantai - 01.srt")]
    assert [t for t, _c in untimed.choose(ranked, VIDEO, formats.UNTIMED_SAME)] == [u"same"]
    assert untimed.choose(ranked[:1], VIDEO, formats.UNTIMED_SAME) == []


def test_the_field_names_the_tier_and_both_providers_and_no_number():
    field = untimed.as_field(u"other", VIDEO, u"[SweetSub] Seihantai - 01.ass")
    assert field == {u"tier": u"other", u"provider": u"SweetSub",
                     u"video_provider": u"NanakoRaws"}
    assert untimed.tier_words(u"exact") == untimed.tier_words(u"same") == u"same provider"
    assert untimed.tier_words(u"other") == u"another provider"


# ---------------------------------------------------------------------------
# the words of a wait -- fork 13 and fork 14
# ---------------------------------------------------------------------------

def test_a_wait_says_until_when_then_stopped_and_reads_back():
    stops = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    base = untimed.nothing_from(VIDEO)
    assert base == u"nothing from [NanakoRaws] for this episode on jimaku"
    waiting = untimed.waiting_reason(base, stops)
    assert u"looks once a day until" in waiting and waiting.endswith(u"then stops"), waiting
    assert untimed.base_of(waiting) == base
    stopped = untimed.stopped_reason(base)
    assert stopped == u"stopped looking — nothing from [NanakoRaws] for this episode on jimaku"
    assert untimed.base_of(stopped) == base


def test_the_wait_field_is_absolute_and_a_week_long():
    since = datetime(2026, 9, 26, 9, tzinfo=timezone.utc)
    field = untimed.wait_field(u"same_provider", since, u"x")
    assert field[u"since"] == since.isoformat()
    assert field[u"stops"] == (since + timedelta(days=7)).isoformat()
    assert formats.UNTIMED_WAIT_DAYS == 7


def test_no_wait_sentence_names_the_setting_or_another_provider():
    u"""🚨 Fork 14, his constraint: *"it should NOT be recommended"*. A waiting row that
    said what else exists, or which setting takes it, recommends the riskier choice."""
    words = u" ".join([untimed.nothing_from(VIDEO), untimed.NO_PROVIDER,
                       untimed.none_reads(3), untimed.stopped_reason(u"x")]).casefold()
    for forbidden in (u"any provider", u"another provider", u"setting", u"settings",
                      u"fits the episode", u"sweetsub", u"untimed"):
        assert forbidden not in words, forbidden


def test_the_choices_are_off_first_and_off_by_default():
    assert formats.UNTIMED_CHOICES[0] == formats.UNTIMED_OFF
    from hato import config
    assert config.SCHEMA[u"untimed"] == (str, formats.UNTIMED_OFF)
    assert formats.untimed_words(u"same_provider") == u"Download one from the same provider"
    assert formats.untimed_words(u"any_provider") \
        == u"Download one that fits the episode number"
