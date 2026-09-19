# -*- coding: utf-8 -*-
"""
Step 2b -- identification and the resolution cache.

Every jimaku and Kitsu answer is a real capture (tests/fixtures/api/, tests/fixtures/kitsu/)
served by a RecordedSession through the real client -- or, where no capture exists for
the request, a DERIVED stand-in that serves a recorded body for a request it was not
recorded for, and says so in its docstring. ⛔ No fixture is hand-written or edited.

⚠ Recorded responses this step needed and does not have (so those paths run on derived
stand-ins): a jimaku search that finds nothing with anime=true AND anime=false, a jimaku
`search?anilist_id=`, and Kitsu /mappings for any anime but 46474.

Suite `identify`. What it STRUCTURALLY cannot cover: whether jimaku's fuzzy search still
returns these entries in this order, and whether the local scoring picks the right show
for names no capture holds -- a wrong show is caught by the timing verdict (Rule 1).
"""
import json
import os
import random
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict
from urllib.parse import parse_qsl, urlsplit

from hato import cli, credentials, names
from hato import client as jc
from hato import resolution as rs
from hato.kitsu import KitsuClient, KitsuError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
API = FIXTURES / "api"
KITSU = FIXTURES / "kitsu"
FAKE_KEY = "hk_FAKE_identify_suite_key_9876543210"


def body_of(folder, stem):
    return json.loads((folder / (stem + ".json")).read_text(encoding="utf-8"))


def url_of(folder, stem):
    return json.loads((folder / (stem + ".meta.json")).read_text(encoding="utf-8"))["url"]


FRIEREN = body_of(API, "search__query_frieren")
NOTHING = body_of(API, "search__live_action_anime_default")       # a real "matched nothing": []


def client(session):
    return jc.JimakuClient(credentials.Key(FAKE_KEY, "test"), session, sleep=lambda s: None,
                           clock=lambda: 0.0, rng=random.Random(5))


def kitsu(session, slept=None):
    return KitsuClient(session, sleep=(slept.append if slept is not None else lambda s: None),
                       rng=random.Random(5))


@pytest.fixture
def cache(tmp_path):
    return rs.ResolutionCache(tmp_path / "resolution.db")


class DerivedJimaku(object):
    """DERIVED: stands in for JimakuClient.search(), answering from RECORDED bodies the test
    picks -- each served for a request it was never recorded for. Counts like the client."""

    def __init__(self, answer):
        self.answer = answer
        self.metered = 0
        self.searches = []

    def search(self, query=None, *, anime=True, anilist_id=None):
        self.searches.append((query, anime, anilist_id))
        self.metered += 1
        return self.answer(query, anime, anilist_id)


def never(*args):
    raise AssertionError("a search was made: %r" % (args,))


# -- what it costs --------------------------------------------------------------------

def test_a_miss_costs_one_call_and_the_hit_that_follows_costs_zero(cache):
    s = jc.RecordedSession(API)
    c = client(s)
    first = rs.identify("frieren", season=2, client=c, cache=cache)
    assert (first.calls, first.cached, first.resolved.entry_id) == (1, False, 11446), first
    again = rs.identify("frieren", season=2, client=c, cache=cache)
    assert (again.calls, again.cached, again.kitsu_calls) == (0, True, 0), again
    assert again.resolved == first.resolved and len(s.calls) == 1


def test_a_second_run_with_a_new_client_and_a_new_accessor_makes_zero_requests(tmp_path):
    path = tmp_path / "resolution.db"
    rs.identify("frieren", season=2, client=client(jc.RecordedSession(API)),
                cache=rs.ResolutionCache(path))
    later = DerivedJimaku(never)
    ident = rs.identify("frieren", season=2, client=later, cache=rs.ResolutionCache(path))
    assert ident.cached and ident.calls == 0 and later.searches == []
    assert ident.resolved.entry_id == 11446


def test_the_live_action_path_costs_two_calls(cache):
    s = jc.RecordedSession(API)
    ident = rs.identify("Kamen Rider Decade", client=client(s), cache=cache)
    assert ident.calls == 2 and ident.resolved.source == "jimaku anime=false", ident
    assert ident.resolved.entry_id == 33
    assert [call["url"] for call in s.calls] == [url_of(API, "search__live_action_anime_default"),
                                                 url_of(API, "search__anime_false_retry")]


def test_a_first_search_that_matches_makes_no_anime_false_retry(cache):
    s = jc.RecordedSession(API)
    ident = rs.identify("frieren", client=client(s), cache=cache)
    assert ident.calls == 1 and len(s.calls) == 1
    assert "anime=false" not in s.calls[0]["url"]


# -- the season ---------------------------------------------------------------------------

@pytest.mark.parametrize("season,entry", [(2, 11446), (1, 729)])
def test_the_season_picks_the_entry(cache, season, entry):
    """Measured: `query=frieren` returns 729 FIRST and 11446 second. ⚠ Only a
    season a video actually READ decides; `None` is the check below."""
    assert [e["id"] for e in FRIEREN[:2]] == [729, 11446]
    ident = rs.identify("frieren", season=season, client=client(jc.RecordedSession(API)), cache=cache)
    assert ident.resolved.entry_id == entry, ident
    assert not ident.resolved.low_confidence, ident.reason


def test_a_video_with_no_season_never_silently_prefers_the_season_1_entry(tmp_path, cache):
    """🚨 THE DOMINANT ANIME NAMING CONVENTION, resolved silently to the WRONG
    entry and cached for ever. Nothing here is hand-made: the name is the shape
    `spec/08-research.md` records for this very entry, tsubasa reads it, and the
    two entries come out of the recorded `?query=frieren` search.

    `season=None` was folded to 1, so the 2nd-Season entry was halved for
    SEASON_MISMATCH and the season-1 entry -- which has no episode 29 -- won at
    score 1.00 with `low_confidence=False`. The old check parametrised
    `(None, 729)` and asserted exactly that as correct.

    A seasonless name is the ABSOLUTE numbering, which spans every season, so
    BOTH entries must stay at full score, and a pick between two equals must say
    LOW CONFIDENCE (06 §1: *"do not silently pick"*).

    ⭐ DERIVED: the recorded frieren answer, served for the title tsubasa reads
    out of that filename -- no capture was made for `?query=Sousou no Frieren`.
    """
    name = u"[Haruhana] Sousou no Frieren - 29 [WebRip][HEVC-10bit 1080p][JPN].mkv"
    info, = names.read_names([name], tmp_path / "read")
    assert (info.season, info.episode) == (None, 29), info      # the harm is real

    asked = DerivedJimaku(lambda q, anime, anilist: FRIEREN)
    ident = rs.identify(info.title, season=info.season, client=asked, cache=cache)

    by_id = dict((c.id, c) for c in ident.candidates)
    for entry_id in (729, 11446):
        assert by_id[entry_id].season_ok, by_id[entry_id]
        assert by_id[entry_id].score == by_id[entry_id].similarity, by_id[entry_id]
    assert by_id[729].score == by_id[11446].score, ident.candidates[:2]
    assert ident.resolved.low_confidence, ident.reason
    assert u"within" in ident.reason and u"2nd Season" in ident.reason, ident.reason


def test_the_season_doubt_only_speaks_when_the_video_named_a_season(tmp_path):
    """⚠ The other half of the same fold. A video that reads NO season used to
    be told *"nothing matched season 1"* -- a doubt invented out of a season
    nobody read. A video that DID name one still gets it."""
    named = rs.identify("frieren", season=3, client=client(jc.RecordedSession(API)),
                        cache=rs.ResolutionCache(tmp_path / "a.db"))
    assert u"nothing matched season 3" in named.reason, named.reason

    unnamed = rs.identify("frieren", client=client(jc.RecordedSession(API)),
                          cache=rs.ResolutionCache(tmp_path / "b.db"))
    assert u"nothing matched" not in unnamed.reason, unnamed.reason


def test_two_seasons_of_one_show_never_share_a_cached_entry(cache):
    c = client(jc.RecordedSession(API))
    assert rs.identify("frieren", season=2, client=c, cache=cache).resolved.entry_id == 11446
    other = rs.identify("frieren", client=c, cache=cache)
    assert other.calls == 1 and not other.cached and other.resolved.entry_id == 729, other


def test_close_scores_and_a_season_nobody_has_are_LOW_CONFIDENCE(cache):
    ident = rs.identify("frieren", season=3, client=client(jc.RecordedSession(API)), cache=cache)
    assert ident.resolved is not None and ident.resolved.low_confidence, ident
    assert "within" in ident.reason and "season 3" in ident.reason, ident.reason


def test_the_fuzzy_title_doubt_is_reachable_only_for_a_match_no_containment_carried():
    """⚠ THE THIRD DOUBT, and nothing tested it at all. `a fuzzy title match`
    asks `similarity < CONFIDENT`, and `_similarity`'s containment branch starts
    AT `CONFIDENT` (0.75 + 0.2 x q/t) -- so for a query whose tokens are all in
    the title the doubt is unreachable by construction. Here it is, reached by
    the only shape that can: a match the character ratio carried, not containment."""
    contained = rs._similarity(rs._tokens(u"frieren"), rs._tokens(u"Sousou no Frieren"))
    assert contained >= rs.CONFIDENT, contained

    fuzzy = rs._similarity(rs._tokens(u"Sousou Frieren Journey"), rs._tokens(u"Sousou no Frieren"))
    assert rs.MATCH_FLOOR <= fuzzy < rs.CONFIDENT, fuzzy
    top, doubts = rs._choose([rs.Candidate("jimaku", 729, u"Sousou no Frieren", fuzzy, fuzzy,
                                           None, True, True)], None)
    assert top is not None and [d for d in doubts if u"fuzzy title match" in d], doubts


@pytest.mark.parametrize("query,title,ratio", [(u"86", u"Ojamajo Doremi 86", 0.2105),
                                               (u"frieren", u"Sousou no Frieren", 0.5833)])
def test_a_one_token_query_inside_a_title_reads_CONFIDENT_a_RECORDED_LIMIT(query, title, ratio):
    """⚠ A MEASURED LIMIT, pinned rather than papered over. `86` inside
    `Ojamajo Doremi 86` is an unrelated show and scores CONFIDENT -- and so does
    `frieren` inside `Sousou no Frieren`, the query the capture itself records.
    ⛔ The two are the SAME SHAPE: one token of three, the same 0.8167, raw
    character ratios 0.2105 and 0.5833, both under MATCH_FLOOR. So no threshold
    separates them without evidence, and the constants were NOT re-tuned. A wrong
    show is Rule 1's to catch (06 §1). This check goes red the day either number
    moves, and the decision is then Sonic's to make again."""
    q, t = rs._tokens(query), rs._tokens(title)
    assert len(q) == 1 and len(t) == 3
    raw = SequenceMatcher(None, u" ".join(q), u" ".join(t), autojunk=False).ratio()
    assert round(raw, 4) == ratio and raw < rs.MATCH_FLOOR, raw
    assert round(rs._similarity(q, t), 4) == 0.8167 >= rs.CONFIDENT


# -- the empty title and the year ---------------------------------------------------------

@pytest.mark.parametrize("title", ["", "   ", u"　", "!!!", u"・・・", u"​"])
def test_an_empty_title_never_becomes_a_request(tmp_path, title):
    path = tmp_path / "resolution.db"
    later = DerivedJimaku(never)
    with pytest.raises(jc.EmptyQuery):
        rs.identify(title, client=later, cache=rs.ResolutionCache(path))
    assert later.searches == [] and not path.exists()


def test_a_glued_year_leaves_the_query_and_stays_in_the_key(cache):
    s = jc.RecordedSession(API)
    ident = rs.identify("Kimi no Na wa 2016", client=client(s), cache=cache)
    assert [call["url"] for call in s.calls] == [url_of(API, "search__movie")]
    assert ident.resolved.entry_id == 440 and ident.resolved.movie is True, ident
    assert rs.cache_key("Kimi no Na wa 2016") == rs.cache_key("Kimi no Na wa", year=2016)
    assert cache.get(rs.cache_key("Kimi no Na wa", year=2016)) == ident.resolved
    assert cache.get(rs.cache_key("Kimi no Na wa")) is None


@pytest.mark.parametrize("title,query", [("1917", "1917"), ("!!! 2016", "!!! 2016")])
def test_a_year_is_split_off_only_when_a_title_is_left(cache, title, query):
    """DERIVED: the recorded empty answer, served for these queries."""
    asked = DerivedJimaku(lambda q, anime, anilist: NOTHING)
    rs.identify(title, client=asked, cache=cache)
    assert [q for q, _, _ in asked.searches] == [query, query]


def test_the_cache_key_carries_the_season_and_the_year():
    keys = [rs.cache_key("frieren"), rs.cache_key("frieren", 1), rs.cache_key("frieren", 2),
            rs.cache_key("frieren", year=2023), rs.cache_key("frieren", 2, 2023)]
    assert len(set(keys)) == len(keys), keys
    assert rs.cache_key(u"Sousou  no FRIEREN", 2) == rs.cache_key("sousou no frieren", 2)
    gintama = [rs.cache_key("Gintama"), rs.cache_key("Gintama."), rs.cache_key("Gintama'")]
    assert len(set(gintama)) == 3, "punctuation told these seasons apart: %s" % gintama


def test_the_store_refuses_a_key_cache_key_did_not_make(cache):
    resolved = rs.Resolved(729, "Sousou no Frieren", False, 0.8, False, "jimaku", 154587)
    for bad in ("frieren", '["frieren", 2]', json.dumps(["hato-resolution-v0", "frieren", 2, None])):
        with pytest.raises(ValueError):
            cache.get(bad)
        with pytest.raises(ValueError):
            cache.put(bad, resolved)


# -- Kitsu -----------------------------------------------------------------------------------

def reversed_frieren(query, anime, anilist_id):
    """DERIVED: [] for both title searches (the recorded empty answer), then -- for
    `anilist_id=` -- the recorded `query=frieren` body REVERSED, so the entry carrying the
    AniList id is LAST and position would pick the wrong one."""
    return list(reversed(FRIEREN)) if anilist_id is not None else NOTHING


def test_the_kitsu_path_costs_two_kitsu_calls_and_one_more_jimaku_call(cache):
    j = DerivedJimaku(reversed_frieren)
    slept = []
    k = kitsu(jc.RecordedSession(KITSU), slept)
    ident = rs.identify("sousou no friern", client=j, cache=cache, kitsu=k)
    assert ident.resolved is not None, ident.reason
    assert (ident.calls, ident.kitsu_calls) == (3, 2), ident
    assert j.searches == [("sousou no friern", True, None), ("sousou no friern", False, None),
                          (None, True, 154587)]
    assert ident.resolved.source == "kitsu" and ident.resolved.anilist_id == 154587
    assert ident.resolved.entry_id == 729, "position was trusted over the AniList id"
    assert len(slept) == 1 and 1.0 <= slept[0] < 2.0


def test_kitsu_hits_are_scored_locally_so_the_season_picks_the_second_hit(cache):
    """Kitsu's recorded answer lists 46474 first and 49240 (2nd Season) second. For a
    season-2 title the scorer must ask for 49240's mappings -- which were never recorded,
    so the recorded session names exactly what was asked."""
    hits = body_of(KITSU, "kitsu__search_cjk")["data"]
    assert [h["id"] for h in hits[:2]] == ["46474", "49240"]
    j = DerivedJimaku(reversed_frieren)
    with pytest.raises(jc.NoRecording) as exc:
        rs.identify(u"葬送のフリーレン", season=2, client=j, cache=cache,
                    kitsu=kitsu(jc.RecordedSession(KITSU)))
    assert "/anime/49240/mappings" in str(exc.value), str(exc.value)


def test_kitsu_percent_encodes_a_japanese_title_exactly_as_recorded():
    s = jc.RecordedSession(KITSU, stems=["kitsu__search_cjk"])
    hits = kitsu(s).search(u"葬送のフリーレン")
    assert len(hits) == len(body_of(KITSU, "kitsu__search_cjk")["data"])
    (call,) = s.calls
    assert call["url"] == url_of(KITSU, "kitsu__search_cjk")
    assert all(ord(ch) < 128 for ch in call["url"]), call["url"]


def test_kitsu_reads_the_anilist_id_from_the_recorded_mappings():
    recorded = [m["attributes"]["externalId"] for m in body_of(KITSU, "kitsu__mappings")["data"]
                if m["attributes"]["externalSite"] == "anilist/anime"]
    k = kitsu(jc.RecordedSession(KITSU, stems=["kitsu__mappings"]))
    assert k.anilist_id(46474) == int(recorded[0]) and k.calls == 1


class DerivedKitsuSession(object):
    """DERIVED: answers every request with a RECORDED Kitsu body the test picks -- served
    for a request it was not recorded for -- built from the real requests types. Keeps
    every URL exactly as KitsuClient built it."""

    def __init__(self, body):
        self.body = body
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        r = requests.Response()
        r.status_code = 200
        r.headers = CaseInsensitiveDict({"content-type": "application/vnd.api+json"})
        r._content = json.dumps(self.body, ensure_ascii=False).encode("utf-8")
        r._content_consumed = True
        r.url = url
        return r


def test_kitsu_encodes_every_reserved_character_of_a_title(monkeypatch):
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)
    s = DerivedKitsuSession(body_of(KITSU, "kitsu__search_typo"))
    title = u"Fate/stay night & UBW #1+2 = 100%? 葬送"
    kitsu(s).search(title)
    (url,) = s.urls
    assert all(ord(ch) < 128 for ch in url) and urlsplit(url).fragment == "", url
    assert parse_qsl(urlsplit(url).query) == [("filter[text]", title), ("page[limit]", "5")], url


def test_kitsu_paces_its_calls_with_jittered_waits():
    slept = []
    k = kitsu(jc.RecordedSession(KITSU), slept)
    k.search("sousou no friern")
    k.search(u"葬送のフリーレン")
    k.anilist_id(46474)
    assert k.calls == 3 and len(slept) == 2, slept
    assert all(1.0 <= w < 2.0 for w in slept) and len(set(slept)) == 2, "a constant gap: %s" % slept


def test_kitsu_takes_the_anilist_mapping_wherever_it_sits(monkeypatch):
    """DERIVED: the recorded mappings with their order REVERSED, so MyAnimeList's comes first."""
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)
    body = body_of(KITSU, "kitsu__mappings")
    wanted = int(next(m["attributes"]["externalId"] for m in body["data"]
                      if m["attributes"]["externalSite"] == "anilist/anime"))
    flipped = dict(body, data=list(reversed(body["data"])))
    assert flipped["data"][0]["attributes"]["externalSite"] != "anilist/anime"
    assert kitsu(DerivedKitsuSession(flipped)).anilist_id(46474) == wanted


def test_kitsu_honours_the_network_switch(monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")

    class WouldAnswer(object):
        calls = []

        def get(self, *a, **kw):
            self.calls.append(a)
            raise AssertionError("Kitsu was asked while the network was switched off")

    k = kitsu(WouldAnswer())
    with pytest.raises(jc.NetworkDisabled):
        k.search("sousou no friern")
    with pytest.raises(jc.NetworkDisabled):
        k.anilist_id(46474)
    assert WouldAnswer.calls == [] and k.calls == 0


class DerivedKitsu(object):
    """DERIVED: stands in for KitsuClient, serving the recorded typo search's hits for any
    text -- a request they were not recorded for."""

    def __init__(self, fail=None):
        self.calls = 0
        self.fail = fail

    def search(self, text):
        self.calls += 1
        if self.fail:
            raise self.fail
        return body_of(KITSU, "kitsu__search_typo")["data"]

    def anilist_id(self, kitsu_anime_id):
        raise AssertionError("mappings were asked for a hit below the match floor")


def test_kitsus_confident_junk_below_the_match_floor_is_not_a_match(cache):
    j = DerivedJimaku(lambda q, anime, anilist: NOTHING)
    ident = rs.identify("Kamen Rider Decade", client=j, cache=cache, kitsu=DerivedKitsu())
    assert ident.resolved is None and ident.kitsu_calls == 1, ident
    assert "Kitsu search" in ident.reason and "matched nothing" in ident.reason


class OddIdKitsu(DerivedKitsu):
    """DERIVED: the recorded typo search's hits with every id rewritten in FULLWIDTH digits
    (str.isdigit() says yes; they are not Kitsu ids)."""

    def search(self, text):
        self.calls += 1
        hits = body_of(KITSU, "kitsu__search_typo")["data"]
        return [dict(h, id=h["id"].translate(dict((0x30 + i, 0xFF10 + i) for i in range(10))))
                for h in hits]


def test_a_kitsu_id_that_is_not_plain_digits_is_skipped_not_a_crash(cache):
    j = DerivedJimaku(lambda q, anime, anilist: NOTHING)
    ident = rs.identify("sousou no friern", client=j, cache=cache, kitsu=OddIdKitsu())
    assert ident.resolved is None and "matched nothing" in ident.reason, ident


def test_nothing_found_says_why_and_caches_nothing(tmp_path):
    path = tmp_path / "resolution.db"
    j = DerivedJimaku(lambda q, anime, anilist: NOTHING)
    ident = rs.identify("Kamen Rider Decade", client=j, cache=rs.ResolutionCache(path))
    assert ident.resolved is None and ident.calls == 2 and not path.exists()
    assert "anime=false" in ident.reason and ident.reason.count("matched nothing") == 2


def test_a_kitsu_failure_is_reported_and_nothing_is_cached(tmp_path):
    path = tmp_path / "resolution.db"
    j = DerivedJimaku(lambda q, anime, anilist: NOTHING)
    ident = rs.identify("Kamen Rider Decade", client=j, cache=rs.ResolutionCache(path),
                        kitsu=DerivedKitsu(fail=KitsuError("Kitsu answered HTTP 503")))
    assert ident.resolved is None and "Kitsu fallback failed" in ident.reason
    assert not path.exists()


def test_a_rejected_key_stops_identification_and_caches_nothing(tmp_path):
    path = tmp_path / "resolution.db"
    c = client(jc.RecordedSession(API, stems=["search__401_bad_key"]))
    with pytest.raises(jc.KeyRejected):
        rs.identify("frieren", client=c, cache=rs.ResolutionCache(path))
    assert c.metered == 1 and not path.exists()


# -- the resolution cache ----------------------------------------------------------------------

RESOLVED = rs.Resolved(440, "Kimi no Na wa.", True, 1.0, True, "jimaku anime=false", None)


def test_the_resolution_cache_creates_nothing_until_something_is_stored(tmp_path):
    path = tmp_path / "deeper" / "resolution.db"
    store = rs.ResolutionCache(path)
    assert store.get(rs.cache_key("frieren")) is None
    assert not path.parent.exists()


def test_a_stored_resolution_is_read_back_whole_by_a_new_accessor(tmp_path):
    path = tmp_path / "resolution.db"
    rs.ResolutionCache(path).put(rs.cache_key("Kimi no Na wa", year=2016), RESOLVED)
    assert rs.ResolutionCache(path).get(rs.cache_key("Kimi no Na wa", year=2016)) == RESOLVED


def test_the_resolution_cache_lives_under_HATO_CACHE():
    assert rs.ResolutionCache().path.parent == Path(os.environ["HATO_CACHE"])


def test_a_corrupt_cache_is_moved_aside_and_a_fresh_one_started(tmp_path):
    path = tmp_path / "resolution.db"
    path.write_bytes(b"this is not a database" * 64)
    store = rs.ResolutionCache(path)
    key = rs.cache_key("frieren", 2)
    assert store.get(key) is None
    assert len(store.notes) == 1 and "moved aside" in store.notes[0], store.notes
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("resolution.db.corrupt-")]
    store.put(key, RESOLVED)
    assert rs.ResolutionCache(path).get(key) == RESOLVED and store.persistent


def test_a_cache_written_by_a_newer_hato_is_left_untouched(tmp_path):
    path = tmp_path / "resolution.db"
    raw = sqlite3.connect(str(path))
    raw.execute("CREATE TABLE from_the_future (x)")
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    raw.close()
    before = path.read_bytes()
    store = rs.ResolutionCache(path)
    key = rs.cache_key("frieren", 2)
    store.put(key, RESOLVED)
    assert path.read_bytes() == before and not store.persistent
    assert store.get(key) == RESOLVED, "this run should still remember it, in memory"
    assert "newer hato" in store.notes[0]


@pytest.mark.parametrize("fields", [
    dict(entry_id=0), dict(entry_id=True), dict(entry_name="  "), dict(movie="yes"),
    dict(score=1.5), dict(low_confidence=None), dict(source="jimaku?"), dict(anilist_id=-1)])
def test_a_resolution_that_breaks_the_rules_is_refused(fields):
    good = dict(RESOLVED._asdict())
    good.update(fields)
    with pytest.raises(ValueError):
        rs.Resolved(**good)


def test_the_store_schema_refuses_what_the_accessor_refuses(tmp_path):
    path = tmp_path / "resolution.db"
    rs.ResolutionCache(path).put(rs.cache_key("frieren"), RESOLVED)
    raw = sqlite3.connect(str(path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            raw.execute("INSERT INTO resolutions VALUES ('k', 7, 'x', 0, 0.5, 0, 'guessed', NULL, 'now')")
    finally:
        raw.close()


# -- `hato identify` ---------------------------------------------------------------------------------

def run_identify(monkeypatch, capsys, tmp_path, *argv):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    monkeypatch.setitem(cli.COMMANDS, "identify", "hato.commands.identify")
    code = cli.main(["identify"] + list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_hato_identify_prints_the_entry_the_score_and_the_cost(monkeypatch, capsys, tmp_path):
    name = "frieren S2 - 01.mkv"
    code, out, err = run_identify(monkeypatch, capsys, tmp_path, name, "--fixtures", str(FIXTURES))
    assert code == 0, err
    assert "11446  Sousou no Frieren 2nd Season" in out, out
    assert re.search(r"score +\d+ · confident", out), out
    assert "1 API call · 0 Kitsu calls" in out and "stored" in out, out
    code, out, err = run_identify(monkeypatch, capsys, tmp_path, name, "--fixtures", str(FIXTURES))
    assert code == 0 and "0 API calls · 0 Kitsu calls" in out and "hit" in out, out


def test_hato_identify_explain_lists_every_scored_entry(monkeypatch, capsys, tmp_path):
    code, out, _ = run_identify(monkeypatch, capsys, tmp_path, "frieren - 01.mkv", "--fixtures",
                                str(FIXTURES), "--explain", "--no-cache")
    assert code == 0
    for entry in FRIEREN:
        assert re.search(r"^ +\d+ +%d  " % entry["id"], out, re.M), (entry["id"], out)


def test_hato_identify_json_carries_the_entry_and_the_cost(monkeypatch, capsys, tmp_path):
    code, out, _ = run_identify(monkeypatch, capsys, tmp_path, "frieren S2 - 01.mkv", "--fixtures",
                                str(FIXTURES), "--json")
    got = json.loads(out)
    assert code == 0 and got["resolved"]["entry_id"] == 11446 and got["calls"] == 1


def test_hato_identify_refuses_a_name_with_no_title_before_any_request(monkeypatch, capsys, tmp_path):
    code, out, err = run_identify(monkeypatch, capsys, tmp_path, "01.mkv", "--fixtures", str(FIXTURES))
    assert code == 1 and "entire catalogue" in err, (out, err)
    assert not (tmp_path / "store" / "resolution.db").exists()


def test_hato_identify_without_fixtures_honours_the_network_switch(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    monkeypatch.setenv("HATO_JIMAKU_KEY", FAKE_KEY)

    class NoSession(object):
        def __init__(self, *a, **kw):
            raise AssertionError("a real session was built while the network was switched off")

    monkeypatch.setattr(jc.requests, "Session", NoSession)
    code, out, err = run_identify(monkeypatch, capsys, tmp_path, "frieren S2 - 01.mkv")
    assert code == 1 and "HATO_NO_NETWORK" in err, (out, err)
    assert FAKE_KEY not in out + err


# -- forget(): added by the orchestrator at wiring time (RUNBOOK 2b ruling) -------------

def _resolved_frieren():
    return rs.Resolved(11446, "Sousou no Frieren 2nd Season", False, 0.82, False, rs.SOURCE_JIMAKU)


def test_forget_drops_one_show_and_leaves_the_rest(tmp_path):
    store = rs.ResolutionCache(tmp_path / "resolution.db")
    k2, k1 = rs.cache_key("Sousou no Frieren", 2), rs.cache_key("Sousou no Frieren", 1)
    store.put(k2, _resolved_frieren())
    store.put(k1, rs.Resolved(729, "Sousou no Frieren", False, 0.9, False, rs.SOURCE_JIMAKU))
    assert store.forget(k2) is True
    assert store.get(k2) is None, "the forgotten show is still served from the cache"
    assert store.get(k1) is not None, "forget() dropped a show it was not asked to"
    # and a fresh accessor over the same file agrees -- it was really deleted
    assert rs.ResolutionCache(tmp_path / "resolution.db").get(k2) is None
    assert store.forget(k2) is False


def test_forget_on_a_store_that_does_not_exist_creates_nothing(tmp_path):
    store = rs.ResolutionCache(tmp_path / "absent" / "resolution.db")
    assert store.forget(rs.cache_key("Anything", None)) is False
    assert not (tmp_path / "absent").exists()
