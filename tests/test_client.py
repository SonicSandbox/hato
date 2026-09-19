# -*- coding: utf-8 -*-
"""
Steps 2a and 2c -- the jimaku client, against RECORDED responses.

Every answer here is a real capture from tests/fixtures/api/ (`hato doctor --capture`:
real bytes, real response headers) served through the real requests machinery, or a
DERIVED double built from one -- and each derived double says so, and what it
changed, in its docstring. ⛔ No fixture is hand-written or edited. A subtitle BODY is
never recorded (third-party content), so every download body here is derived.

Suite `client`. What it STRUCTURALLY cannot cover: whether jimaku still answers this
way -- that is `hato doctor` and the opt-in `live` suite -- and a real 429: provoking
one needs more than 25 requests in 60 s, which Whitelist 2 forbids, so the 429 header
set stays UNVERIFIED and its double is derived from a recorded 200.

The network is off twice over (conftest: HATO_NO_NETWORK=1 and a socket guard). A
check that needs the client to send opts in with the `online` fixture -- anything
reaching outside the process is off by default, and switched on only by the block
that tests it. Nothing here ever leaves 127.0.0.1.
"""
import gzip
import io
import json
import random
import socket
import threading
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

import pytest
import requests
from requests.adapters import BaseAdapter, HTTPAdapter
from requests.structures import CaseInsensitiveDict

import conftest
from hato import cli, credentials
from hato import client as jc

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
API = FIXTURES / "api"
FAKE_KEY = "hk_FAKE_client_suite_key_0123456789"
SPEC_LADDER = (5.0, 15.0, 45.0)          # spec/06-edge-cases.md §4 -- not the module's constant


def recorded(stem):
    meta = json.loads((API / (stem + ".meta.json")).read_text(encoding="utf-8"))
    body = (API / (stem + ".json")).read_bytes() if meta["body_kept"] else None
    return meta, body


def step(stem):
    """A recorded answer, unchanged, as one step of a Scripted session."""
    meta, body = recorded(stem)
    return (meta["status"], body, dict(meta["response_headers"]))


def epoch_of(meta):
    """The recorded `date` header as an epoch: the clock a double built on it runs at."""
    return parsedate_to_datetime(meta["response_headers"]["date"]).timestamp()


RECORDED_FILES = json.loads((API / "entries_11446_files.json").read_text(encoding="utf-8"))
FRIEREN_META, FRIEREN_BODY = recorded("search__query_frieren")
DOWNLOAD_META, _ = recorded("download__sample")
SAMPLE_FILE = next(f for f in RECORDED_FILES if f["name"] == DOWNLOAD_META["name"])


def derived_subtitle(size, head=b"\xef\xbb\xbf1\r\n00:00:01,000 --> 00:00:02,000\r\n"):
    """DERIVED: a body of exactly `size` bytes -- a UTF-8 BOM (as the recorded download
    sniffed) then SRT-shaped filler. The real body is never recorded."""
    return (head + b"x" * size)[:size]


def download_step(body):
    """DERIVED: `body` with the REAL headers of the recorded download."""
    return (DOWNLOAD_META["status"], body, dict(DOWNLOAD_META["response_headers"]))


class _ScriptAdapter(BaseAdapter):
    def __init__(self, owner):
        super(_ScriptAdapter, self).__init__()
        self.owner = owner

    def send(self, request, **kw):
        return self.owner._play(request)

    def close(self):
        pass


class Scripted(requests.Session):
    """A real requests.Session whose transport plays a script, one step per request:
    (status, body bytes or a raw file object, headers), or an exception to raise.
    Every request is recorded exactly as requests prepared it. It opens no socket."""

    def __init__(self, *steps):
        super(Scripted, self).__init__()
        self.trust_env = False
        self.steps = list(steps)
        self.calls = []
        adapter = _ScriptAdapter(self)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    def _play(self, request):
        self.calls.append({"url": request.url, "headers": dict(request.headers)})
        if not self.steps:
            raise AssertionError("the script ran out: an unexpected request to %s" % request.url)
        current = self.steps.pop(0)
        if isinstance(current, BaseException):
            raise current
        status, body, headers = current
        r = requests.Response()
        r.status_code = status
        r.headers = CaseInsensitiveDict(headers)
        r.raw = body if hasattr(body, "read") else io.BytesIO(body)
        r.url = request.url
        r.request = request
        return r


class FakeTime(object):
    """The clock only moves when the client sleeps."""

    def __init__(self, now):
        self.now = float(now)
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def make(session, now=None, **kw):
    t = FakeTime(epoch_of(FRIEREN_META) if now is None else now)
    c = jc.JimakuClient(credentials.Key(FAKE_KEY, "test"), session, sleep=t.sleep,
                        clock=t.clock, rng=random.Random(7), **kw)
    return c, t


def waits(c, marker):
    return [w for w, why in c.waits if marker in why]


def shown(text):
    return text.replace(FAKE_KEY, "<the key>")


@pytest.fixture
def online(monkeypatch):
    """This block sends: the kill switch is off for it alone. The socket guard stays."""
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)


# -- the key -------------------------------------------------------------------

def test_the_key_goes_raw_in_Authorization_with_no_Bearer_prefix():
    s = jc.RecordedSession(API, stems=["search__query_frieren"])
    c, _ = make(s)
    c.search("frieren")
    (call,) = s.calls
    assert call["headers"].get("Authorization") == FAKE_KEY, shown(
        "Authorization was %r" % call["headers"].get("Authorization"))


def test_a_search_is_the_recorded_request_and_returns_the_recorded_entries():
    s = jc.RecordedSession(API, stems=["search__query_frieren"])
    c, _ = make(s)
    assert c.search("frieren") == json.loads(FRIEREN_BODY.decode("utf-8"))
    assert s.calls[0]["url"] == FRIEREN_META["url"]
    assert (c.metered, c.unmetered) == (1, 0)


def test_the_key_never_appears_in_an_error_a_repr_or_the_rate_headers(online):
    s = Scripted(step("search__401_bad_key"))
    c, _ = make(s)
    with pytest.raises(jc.KeyRejected) as rejected:
        c.search("frieren")
    dropped = Scripted(*[requests.exceptions.ConnectionError("down")] * 6)
    c2, _ = make(dropped)
    with pytest.raises(jc.Unreachable) as unreachable:
        c2.search("frieren")
    for text in (str(rejected.value), str(unreachable.value), repr(c), repr(c2),
                 json.dumps(c.last_rate_headers)):
        assert FAKE_KEY not in text, shown(text)
    assert FAKE_KEY[-4:] in str(rejected.value), "the 401 should name the key by its last four"


# -- the empty query -------------------------------------------------------------

@pytest.mark.parametrize("query", ["", "   ", None])
def test_an_empty_query_is_refused_before_any_request(online, query):
    s = Scripted(step("search__query_frieren"))        # a session that WOULD answer
    c, _ = make(s)
    with pytest.raises(jc.EmptyQuery):
        c.search(query)
    assert s.calls == [] and c.metered == 0


def test_an_anilist_id_search_sends_no_query_at_all(online):
    """DERIVED: the recorded `query=frieren` answer, served for `anilist_id=154587` --
    a request never recorded. Only what was SENT is asserted."""
    s = Scripted(step("search__query_frieren"))
    c, _ = make(s)
    c.search(anilist_id=154587)
    params = parse_qsl(urlsplit(s.calls[0]["url"]).query, keep_blank_values=True)
    assert params == [("anilist_id", "154587")], s.calls[0]["url"]


def test_anime_false_is_sent_only_when_asked_for_and_matches_the_recorded_retry():
    s = jc.RecordedSession(API, stems=["search__live_action_anime_default",
                                       "search__anime_false_retry"])
    c, _ = make(s)
    assert c.search("Kamen Rider Decade") == []
    assert c.search("Kamen Rider Decade", anime=False)
    assert [call["url"] for call in s.calls] == [
        recorded("search__live_action_anime_default")[0]["url"],
        recorded("search__anime_false_retry")[0]["url"]]


# -- the 401 ---------------------------------------------------------------------

def test_a_401_raises_KeyRejected_and_is_never_retried(online):
    s = Scripted(step("search__401_bad_key"), step("search__query_frieren"))
    c, t = make(s)
    with pytest.raises(jc.KeyRejected) as exc:
        c.search("frieren")
    assert len(s.calls) == 1, "a 401 was retried -- every retry spends quota as well"
    assert c.metered == 1, "a 401 still spends quota, so it is an API call"
    assert t.slept == [] and exc.value.status == 401


def test_after_a_401_every_call_raises_without_touching_the_network(online):
    s = Scripted(step("search__401_bad_key"), step("search__query_frieren"),
                 step("entries_11446_files"), download_step(derived_subtitle(SAMPLE_FILE["size"])))
    c, _ = make(s)
    with pytest.raises(jc.KeyRejected):
        c.search("frieren")
    for later in (lambda: c.search("frieren"), lambda: c.files(11446),
                  lambda: c.download(SAMPLE_FILE)):
        with pytest.raises(jc.KeyRejected):
            later()
    assert len(s.calls) == 1 and c.metered == 1 and c.unmetered == 0, s.calls


# -- the kill switch -------------------------------------------------------------

def test_the_network_switch_refuses_every_call_before_a_session_that_would_answer(monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")          # stated here, never inherited
    s = Scripted(step("search__query_frieren"), step("search__query_frieren"))
    c, _ = make(s)
    for call in (lambda: c.search("frieren"), lambda: c.files(11446),
                 lambda: c.download(SAMPLE_FILE)):
        with pytest.raises(jc.NetworkDisabled):
            call()
    assert s.calls == [] and (c.metered, c.unmetered) == (0, 0)
    monkeypatch.delenv("HATO_NO_NETWORK")               # the control: the same session answers
    assert c.search("frieren") and len(s.calls) == 1


def test_the_network_switch_builds_no_session_of_its_own(monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")

    class NoSession(object):
        def __init__(self, *a, **kw):
            raise AssertionError("a real session was built while the network was switched off")

    monkeypatch.setattr(jc.requests, "Session", NoSession)
    c, _ = make(None)
    with pytest.raises(jc.NetworkDisabled):
        c.search("frieren")


def test_only_a_RecordedSession_is_exempt_from_the_network_switch(monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    c, _ = make(jc.RecordedSession(API, stems=["search__query_frieren"]))
    assert c.search("frieren")
    lookalike = Scripted(step("search__query_frieren"))
    lookalike.directory = API                            # quacks like one; is not one
    c2, _ = make(lookalike)
    with pytest.raises(jc.NetworkDisabled):
        c2.search("frieren")
    assert lookalike.calls == []


def test_nothing_can_be_mounted_over_a_RecordedSession():
    s = jc.RecordedSession(API)
    with pytest.raises(TypeError):
        s.mount("https://", HTTPAdapter())
    assert not isinstance(s.get_adapter("https://jimaku.cc/api/entries/search"), HTTPAdapter)


def test_a_RecordedSession_refuses_what_nothing_recorded_answers():
    s = jc.RecordedSession(API)
    c, _ = make(s)
    with pytest.raises(jc.NoRecording) as exc:
        c.search("sousou no friern")
    assert "query=sousou+no+friern" in str(exc.value) and c.metered == 0
    with pytest.raises(jc.NoRecording) as meta_only:
        s.get("https://jimaku.cc/api/entries/search?query=")
    assert "metadata only" in str(meta_only.value)


def test_the_recorded_401_never_answers_what_its_200_twin_can():
    c, _ = make(jc.RecordedSession(API))                 # both share `search?query=frieren`
    assert c.search("frieren") == json.loads(FRIEREN_BODY.decode("utf-8"))
    c401, _ = make(jc.RecordedSession(API, stems=["search__401_bad_key"]))
    with pytest.raises(jc.KeyRejected):
        c401.search("frieren")


# -- an invalid entry id -----------------------------------------------------------

def test_an_invalid_entry_id_is_a_404_raised_as_EntryNotFound_and_it_spends_quota():
    c, _ = make(jc.RecordedSession(API, stems=["entries_invalid_id_files"]))
    with pytest.raises(jc.EntryNotFound) as exc:
        c.files(999999)
    assert exc.value.status == 404 and "999999" in str(exc.value)
    assert "could not be found" in str(exc.value), "the server's own words are the evidence"
    assert c.metered == 1


# -- 2c: the file list -------------------------------------------------------------

@pytest.mark.parametrize("stem,entry", [("entries_11446_files", 11446), ("entries_movie_flag", 440)])
def test_every_recorded_file_is_returned(stem, entry):
    s = jc.RecordedSession(API, stems=[stem])
    c, _ = make(s)
    listed = c.files(entry)
    fixture = json.loads((API / (stem + ".json")).read_text(encoding="utf-8"))
    assert len(listed) == len(fixture) and listed == fixture
    assert s.calls[0]["url"] == recorded(stem)[0]["url"] and c.metered == 1


def test_episode_is_never_sent_in_any_request(online):
    s = Scripted(step("search__query_frieren"), step("search__anime_false_retry"),
                 step("search__query_frieren"), step("entries_11446_files"),
                 download_step(derived_subtitle(SAMPLE_FILE["size"])))
    c, _ = make(s)
    c.search("frieren")
    c.search("Kamen Rider Decade", anime=False)
    c.search(anilist_id=154587)
    c.files(11446)
    c.download(SAMPLE_FILE)
    urls = [call["url"] for call in s.calls]
    assert len(urls) == 5, urls
    assert [u for u in urls if "episode" in unquote(u).lower()] == []
    with pytest.raises(TypeError):
        c.files(11446, episode=1)


@pytest.mark.parametrize("bad", ["11446?episode=1", "11446/../999", " 11446", "１１４４６",
                                 True, 0, -5, 11446.0, None])
def test_an_entry_id_that_is_not_a_plain_number_never_reaches_a_request(online, bad):
    s = Scripted(step("entries_11446_files"))
    c, _ = make(s)
    with pytest.raises(ValueError):
        c.files(bad)
    assert s.calls == []
    assert len(c.files("11446")) == len(RECORDED_FILES)   # the control: digits are fine


# -- the url guard ------------------------------------------------------------------

_PATH = urlsplit(SAMPLE_FILE["url"]).path
BAD_URLS = [
    ("another host", "https://evil.example" + _PATH, True),
    ("a host that only ends like jimaku", "https://jimaku.cc.evil.example" + _PATH, True),
    ("a host that only starts like jimaku", "https://evil-jimaku.cc" + _PATH, True),
    ("plain http", "http://jimaku.cc" + _PATH, True),
    ("a port", "https://jimaku.cc:8443" + _PATH, True),
    ("user info", "https://someone@jimaku.cc" + _PATH, True),
    ("the path with no host", _PATH, True),
    ("not the download route", "https://jimaku.cc/entry/11446/files/x.srt", True),
    ("a dot segment", "https://jimaku.cc/entry/11446/download/..%2F..%2Fapi%2Fentries", True),
    ("a query string", SAMPLE_FILE["url"] + "?episode=4", True),
    ("another entry's route", "https://jimaku.cc" + _PATH.replace("/entry/11446/", "/entry/729/"), False),
]


@pytest.mark.parametrize("why,url,shape_alone", BAD_URLS, ids=[b[0] for b in BAD_URLS])
def test_a_file_whose_url_is_not_its_entrys_download_route_is_refused(online, why, url, shape_alone):
    """DERIVED: the recorded file list, with ONE file's url changed as named."""
    bad = dict(SAMPLE_FILE, url=url)
    listed = [bad if f is SAMPLE_FILE else f for f in RECORDED_FILES]
    s = Scripted((200, json.dumps(listed, ensure_ascii=False).encode("utf-8"),
                  dict(recorded("entries_11446_files")[0]["response_headers"])))
    c, _ = make(s)
    with pytest.raises(jc.BadFileUrl) as exc:
        c.files(11446)
    assert url in str(exc.value)
    if shape_alone:
        with pytest.raises(jc.BadFileUrl):
            c.download(bad)
    assert len(s.calls) == 1, "a refused url was requested: %s" % s.calls


def test_the_real_file_passes_the_guard_and_downloads(online):
    s = Scripted(download_step(derived_subtitle(SAMPLE_FILE["size"])))
    c, _ = make(s)
    assert len(c.download(SAMPLE_FILE)) == SAMPLE_FILE["size"]
    assert s.calls[0]["url"] == DOWNLOAD_META["url"]


# -- the name guard ------------------------------------------------------------

FILES_META = recorded("entries_11446_files")[0]

NO_NAME = [("absent", None), ("null", None), ("empty", u""), ("blank", u"   "),
           ("a number", 11446), ("a list", [u"a.srt"])]


def without_a_name(kind, value):
    """DERIVED: the recorded SAMPLE_FILE with its `name` broken as named. `absent`
    removes the key -- this server omits optional fields rather than nulling them
    (skip_serializing_if, spec/08-research.md), so absence is the realistic shape."""
    if kind == "absent":
        return {k: v for k, v in SAMPLE_FILE.items() if k != "name"}
    return dict(SAMPLE_FILE, name=value)


@pytest.mark.parametrize("kind,value", NO_NAME, ids=[n[0] for n in NO_NAME])
def test_a_listed_file_with_no_usable_name_is_refused_not_returned(online, kind, value):
    """🚨 files() validated every file's `url` and NOTHING else, so a file with no
    `name` came back intact into callers that index `file["name"]` directly --
    measured 2026-09-17, returning `{'url': ..., 'size': ..., 'last_modified': ...}`
    and `None` for the name. A jimaku file has no episode field: the number, the
    language tag and the name the original is kept under all live in `name`."""
    bad = without_a_name(kind, value)
    listed = [bad if f is SAMPLE_FILE else f for f in RECORDED_FILES]
    s = Scripted((200, json.dumps(listed, ensure_ascii=False).encode("utf-8"),
                  dict(FILES_META["response_headers"])))
    c, _ = make(s)
    with pytest.raises(jc.BadFileName) as exc:
        c.files(11446)
    assert "name" in str(exc.value)
    with pytest.raises(jc.BadFileName):
        c.download(bad)
    assert len(s.calls) == 1, "a file with no name was fetched: %s" % s.calls


def test_the_name_guard_refuses_nothing_the_real_listing_holds(online):
    """The control: every one of the recorded files passes, so the guard above is
    refusing the break and not the shape."""
    s = jc.RecordedSession(API, stems=["entries_11446_files"])
    c, _ = make(s)
    listed = c.files(11446)
    assert len(listed) == len(RECORDED_FILES)
    assert all(isinstance(f["name"], str) and f["name"].strip() for f in listed)
    assert issubclass(jc.BadFileName, jc.JimakuError) and issubclass(jc.BadFileUrl, jc.JimakuError)


# -- rate limits --------------------------------------------------------------------

def test_the_last_metered_answers_rate_headers_are_kept_verbatim():
    meta, _ = recorded("entries_11446_files")
    c, _ = make(jc.RecordedSession(API, stems=["entries_11446_files"]))
    c.files(11446)
    assert c.last_rate_headers == dict((k, v) for k, v in meta["response_headers"].items()
                                       if k.startswith("x-ratelimit-"))
    assert "x-ratelimit-reset-after" not in c.last_rate_headers   # absent outside a 429 -- and fine


def test_metered_calls_are_paced_with_jittered_waits_never_a_constant(online):
    s = Scripted(*[step("search__query_frieren")] * 6)
    c, _ = make(s)
    for _ in range(6):
        c.search("frieren")
    paced = waits(c, "pacing")
    assert len(paced) == 5, c.waits
    assert all(1.0 <= w < 2.0 for w in paced), paced
    assert len(set(paced)) > 1, "a constant delay: %s" % paced


def test_at_remaining_0_the_next_call_waits_for_the_reset_epoch(online):
    """DERIVED: the recorded file-list answer with x-ratelimit-remaining set to 0. `reset`
    stays the recorded integer epoch and the clock runs at the recorded `date`, so the
    reset is exactly as far ahead as it was measured to be."""
    meta, body = recorded("entries_11446_files")
    exhausted = dict(meta["response_headers"], **{"x-ratelimit-remaining": "0"})
    s = Scripted((200, body, exhausted), step("entries_11446_files"), step("entries_11446_files"))
    c, t = make(s, now=epoch_of(meta))
    c.files(11446)
    c.files(11446)
    reset = float(meta["response_headers"]["x-ratelimit-reset"])
    assert len(waits(c, "x-ratelimit-reset")) == 1, c.waits
    assert t.now >= reset, "the next call went out %.1f s BEFORE the reset" % (reset - t.now)
    c.files(11446)                                  # the control: remaining 24 buys no reset wait
    assert len(waits(c, "x-ratelimit-reset")) == 1, c.waits


def exhausted(**changes):
    """DERIVED: the recorded file-list answer with x-ratelimit-remaining set to 0,
    then `changes` applied to its headers -- ⭐ a value of None DELETES the header,
    so a check can vary a header's PRESENCE and not only its value."""
    meta, body = recorded("entries_11446_files")
    headers = dict(meta["response_headers"], **{"x-ratelimit-remaining": "0"})
    for name, value in changes.items():
        if value is None:
            headers.pop(name, None)
        else:
            headers[name] = value
    return (200, body, headers)


RESET_AHEAD = (float(FILES_META["response_headers"]["x-ratelimit-reset"])
               - epoch_of(FILES_META))

UNREADABLE_RESET = [("absent", None), ("empty", u""), ("not a number", u"soon"),
                    ("a word", u"never"), ("infinite", u"inf")]


@pytest.mark.parametrize("why,value", UNREADABLE_RESET, ids=[r[0] for r in UNREADABLE_RESET])
def test_at_remaining_0_an_unreadable_reset_still_waits_the_documented_window(online, why, value):
    """🚨 The reset wait REQUIRED a readable `x-ratelimit-reset`, so `remaining: 0`
    with that header absent, empty or non-numeric bought NO WAIT AT ALL and the
    next request went straight out into a budget known to be gone -- measured
    2026-09-17: reset present -> 1 wait; absent, empty or unparseable -> 0.

    ⚠ Not hypothetical. This API is already measured to OMIT
    `x-ratelimit-reset-after` on 200, 401 and 404, so a rate-limit header that is
    simply not there is the normal case here, not the strange one. ⛔ No check
    varied a header's PRESENCE before this one.
    """
    control = Scripted(exhausted(), step("entries_11446_files"))
    c0, _ = make(control, now=epoch_of(FILES_META))
    c0.files(11446)
    c0.files(11446)
    (measured,) = waits(c0, "x-ratelimit-remaining is 0")
    assert measured < jc.WINDOW, (
        "the control: a readable reset waits for its epoch (%.1f s ahead), not the window"
        % RESET_AHEAD)

    s = Scripted(exhausted(**{"x-ratelimit-reset": value}), step("entries_11446_files"))
    c, t = make(s, now=epoch_of(FILES_META))
    c.files(11446)
    c.files(11446)
    made = waits(c, "x-ratelimit-remaining is 0")
    assert len(made) == 1, (
        "reset %s: the next call went out with NO wait at remaining 0 -- %s" % (why, c.waits))
    assert jc.WINDOW <= made[0] < jc.WINDOW + 1.25, (
        "reset %s: waited %.2f s, not jimaku's documented %.0f s window" % (why, made[0], jc.WINDOW))
    assert len(s.calls) == 2, s.calls


def test_at_remaining_0_a_reset_after_is_obeyed_when_reset_is_missing(online):
    """⭐ Whichever of the two headers arrived. `reset-after` was measured absent
    outside a 429 -- but "absent in this capture" is not "never sent", and obeying
    the one that came is the rule (spec/03-permissions.md)."""
    s = Scripted(exhausted(**{"x-ratelimit-reset": None, "x-ratelimit-reset-after": u"17.5"}),
                 step("entries_11446_files"))
    c, _ = make(s, now=epoch_of(FILES_META))
    c.files(11446)
    c.files(11446)
    (waited,) = waits(c, "x-ratelimit-remaining is 0")
    paced = sum(waits(c, "pacing"))
    assert 17.5 - paced + 0.25 <= waited < 17.5 - paced + 1.25, (waited, paced)
    assert waited < jc.WINDOW, "fell back to the window with a readable reset-after"


def test_a_metered_answer_with_no_rate_limit_headers_leaves_the_budget_unknown(online):
    """⭐ A DECISION, pinned rather than left to be re-argued. With no
    `x-ratelimit-remaining` there is nothing that says the budget is gone: hato
    paces and sends. It does not invent a reset wait, and it does not carry the
    last answer's number forward -- 03-permissions.md: *"Read the headers and obey
    them. Do not model the budget locally and hope."*"""
    bare = {k: v for k, v in FILES_META["response_headers"].items()
            if not k.startswith("x-ratelimit-")}
    body = recorded("entries_11446_files")[1]
    s = Scripted((200, body, bare), (200, body, bare))
    c, _ = make(s, now=epoch_of(FILES_META))
    c.files(11446)
    c.files(11446)
    assert waits(c, "x-ratelimit-remaining is 0") == [], c.waits
    assert len(waits(c, "pacing")) == 1, c.waits
    assert c.last_rate_headers == {}
    assert len(s.calls) == 2


def derived_429(**extra):
    """DERIVED 429. None was captured: provoking one needs more than 25 requests in 60 s,
    which Whitelist 2 forbids. Built from the REAL headers of the recorded `query=frieren`
    200 -- status 429, x-ratelimit-remaining set to 0, plus `extra`. The recorded `reset`
    is kept, 13 s after the recorded `date`, so obeying the wrong header shows."""
    headers = dict(FRIEREN_META["response_headers"], **{"x-ratelimit-remaining": "0"})
    headers.update(extra)
    return (429, b"", headers)


def test_a_429_honours_a_fractional_reset_after_not_the_later_reset(online):
    s = Scripted(derived_429(**{"x-ratelimit-reset-after": "2.379"}), step("search__query_frieren"))
    c, _ = make(s)
    assert c.search("frieren") == json.loads(FRIEREN_BODY.decode("utf-8"))
    (waited,) = waits(c, "429")
    assert 2.379 + 0.25 <= waited < 2.379 + 1.25, waited
    assert sum(w for w, _ in c.waits) == waited, "waited again after honouring reset-after: %s" % c.waits
    assert c.metered == 2, "a 429 spends quota: it is an API call"


def test_a_429_without_reset_after_waits_for_reset(online):
    s = Scripted(derived_429(), step("search__query_frieren"))
    c, _ = make(s)
    c.search("frieren")
    ahead = float(FRIEREN_META["response_headers"]["x-ratelimit-reset"]) - epoch_of(FRIEREN_META)
    (waited,) = waits(c, "429")
    assert ahead + 0.25 <= waited < ahead + 1.25, (waited, ahead)


def test_a_429_asking_past_the_cap_raises_RateLimited_instead_of_waiting(online):
    s = Scripted(derived_429(**{"x-ratelimit-reset-after": "600.5"}), step("search__query_frieren"))
    c, t = make(s)
    with pytest.raises(jc.RateLimited) as exc:
        c.search("frieren")
    assert t.slept == [] and len(s.calls) == 1
    assert "600.5" in str(exc.value)


def test_repeated_429s_stop_at_the_cap_instead_of_waiting_for_ever(online):
    s = Scripted(*[derived_429(**{"x-ratelimit-reset-after": "30.5"})] * 10)
    c, _ = make(s)
    with pytest.raises(jc.RateLimited):
        c.search("frieren")
    waited = waits(c, "429")
    assert len(waited) >= 2 and len(s.calls) == len(waited) + 1, c.waits
    assert sum(waited) <= jc.MAX_RATE_WAIT < sum(waited) + 30.5 + 0.25, (
        "stopped at %.1f s of waiting, with a %.0f s cap" % (sum(waited), jc.MAX_RATE_WAIT))


# -- no answer: the ladder ------------------------------------------------------------

def test_a_request_with_no_answer_is_retried_after_5_15_45_seconds(online):
    s = Scripted(requests.exceptions.ConnectionError("refused"),
                 requests.exceptions.ConnectTimeout("no route"),
                 requests.exceptions.ReadTimeout("silent"), step("search__query_frieren"))
    c, _ = make(s)
    assert c.search("frieren")
    ladder = waits(c, "no answer")
    assert len(ladder) == 3, c.waits
    for waited, rung in zip(ladder, SPEC_LADDER):
        assert rung <= waited < rung * 1.25, (waited, rung)
    assert c.metered == 1, "an attempt that got no answer is not an API call"


def test_the_ladder_waits_are_jittered_not_constant(online):
    s = Scripted(*([requests.exceptions.ConnectionError("down")] * 5 + [step("search__query_frieren")]))
    c, _ = make(s)
    c.search("frieren")
    ladder = waits(c, "no answer")
    rungs = list(SPEC_LADDER) + [SPEC_LADDER[-1]] * 2
    assert len(ladder) == 5 and all(r <= w < r * 1.25 for w, r in zip(ladder, rungs)), ladder
    assert [w for w, r in zip(ladder, rungs) if w != r], "every wait was the bare rung: %s" % ladder
    assert len(set(ladder[2:])) == 3, "the repeated 45 s rung is a constant: %s" % ladder


def test_six_consecutive_unanswered_attempts_stop_the_run_for_good(online):
    s = Scripted(*([requests.exceptions.ConnectionError("down")] * 6 + [step("search__query_frieren")]))
    c, _ = make(s)
    with pytest.raises(jc.Unreachable) as exc:
        c.search("frieren")
    assert len(s.calls) == 6 and len(waits(c, "no answer")) == 5, c.waits
    for later in (lambda: c.search("frieren"), lambda: c.files(11446),
                  lambda: c.download(SAMPLE_FILE)):
        with pytest.raises(jc.Unreachable):
            later()
    assert len(s.calls) == 6, "a request was attempted after the run stopped"
    assert "6 times" in str(exc.value)


def test_an_answer_resets_the_unreachable_count(online):
    down = requests.exceptions.ConnectionError("down")
    s = Scripted(*([down] * 5 + [step("search__query_frieren")] + [down] * 5
                   + [step("search__query_frieren")]))
    c, _ = make(s)
    assert c.search("frieren")
    assert c.search("frieren"), "the count carried over a success"
    assert len(s.calls) == 12


def test_a_server_error_is_an_answer_raised_once_and_never_retried(online):
    """DERIVED 500: the recorded `query=frieren` headers on an empty body -- no 5xx was captured."""
    s = Scripted((500, b"", dict(FRIEREN_META["response_headers"])), step("search__query_frieren"))
    c, _ = make(s)
    with pytest.raises(jc.JimakuError) as exc:
        c.search("frieren")
    assert exc.value.status == 500 and len(s.calls) == 1 and c.metered == 1
    assert not isinstance(exc.value, (jc.Unreachable, jc.KeyRejected))
    assert waits(c, "no answer") == []


def test_an_HTTP_error_answer_also_resets_the_unreachable_count(online):
    """DERIVED 500, as above."""
    down = requests.exceptions.ConnectionError("down")
    s = Scripted(*([down] * 5 + [(500, b"", dict(FRIEREN_META["response_headers"]))] + [down] * 5
                   + [step("search__query_frieren")]))
    c, _ = make(s)
    with pytest.raises(jc.JimakuError):
        c.search("frieren")
    assert c.search("frieren")


def test_the_suites_network_guard_is_never_swallowed_by_the_ladder(online):
    s = Scripted(conftest.NetworkForbidden("the guard"), step("search__query_frieren"))
    c, t = make(s)
    with pytest.raises(conftest.NetworkForbidden):
        c.search("frieren")
    assert t.slept == [] and len(s.calls) == 1


def test_a_redirect_is_refused_never_followed(online):
    """DERIVED 302: the recorded headers plus a Location -- no redirect was ever measured."""
    s = Scripted((302, b"", dict(FRIEREN_META["response_headers"], location="https://evil.example/x")),
                 step("search__query_frieren"))
    c, _ = make(s)
    with pytest.raises(jc.JimakuError) as exc:
        c.search("frieren")
    assert exc.value.status == 302 and len(s.calls) == 1


# -- downloads -----------------------------------------------------------------------

def test_a_download_sends_no_Authorization_even_when_the_session_carries_one(online):
    s = Scripted(download_step(derived_subtitle(SAMPLE_FILE["size"])))
    s.headers["Authorization"] = "SESSION-LEVEL-" + FAKE_KEY
    c, _ = make(s)
    data = c.download(SAMPLE_FILE)
    assert "Authorization" not in s.calls[0]["headers"], shown(str(s.calls[0]["headers"]))
    assert len(data) == SAMPLE_FILE["size"]
    assert (c.metered, c.unmetered) == (0, 1), "a download is unmetered"


def test_an_empty_download_is_an_error(online):
    s = Scripted(download_step(b""))
    c, _ = make(s)
    with pytest.raises(jc.DownloadError) as exc:
        c.download(SAMPLE_FILE)
    assert "EMPTY" in str(exc.value)


def test_a_download_shorter_than_its_listed_size_is_an_error(online):
    s = Scripted(download_step(derived_subtitle(SAMPLE_FILE["size"] - 1)))
    c, _ = make(s)
    with pytest.raises(jc.DownloadError) as exc:
        c.download(SAMPLE_FILE)
    assert "truncated" in str(exc.value) and str(SAMPLE_FILE["size"]) in str(exc.value)


@pytest.mark.parametrize("head", [b"<!DOCTYPE html><html><body>not found",
                                  b"\xef\xbb\xbf  <html><head>", b"\r\n<!doctype HTML>"])
def test_an_HTML_page_served_as_a_subtitle_is_an_error(online, head):
    size = SAMPLE_FILE["size"]
    s = Scripted(download_step((head + b" " * size)[:size]),
                 download_step(derived_subtitle(size, head=b"\xef\xbb\xbf[Script Info]\r\n")))
    c, _ = make(s)
    with pytest.raises(jc.DownloadError) as exc:
        c.download(SAMPLE_FILE)
    assert "HTML" in str(exc.value)
    assert len(c.download(SAMPLE_FILE)) == size          # the control: a subtitle is kept


def test_a_download_that_404s_raises_DownloadNotFound(online):
    """The recorded 404 of the unmetered route -- its status, headers and empty body are
    real. DERIVED: the file dict pointing at it (the probe's route has no listing)."""
    meta, _ = recorded("download__invalid_id")
    s = Scripted((meta["status"], b"", dict(meta["response_headers"])))
    c, _ = make(s)
    with pytest.raises(jc.DownloadNotFound) as exc:
        c.download({"name": "hato-doctor-probe.srt", "url": meta["url"], "size": 1})
    assert exc.value.status == 404 and not isinstance(exc.value, jc.DownloadError)


class CountingBody(io.BytesIO):
    read_bytes = 0

    def read(self, n=-1):
        data = super(CountingBody, self).read(n)
        self.read_bytes += len(data)
        return data


def test_a_download_past_the_cap_is_aborted_not_truncated(online):
    body = CountingBody(derived_subtitle(4 * 1024 * 1024))
    s = Scripted(download_step(body))
    c, _ = make(s, max_download_bytes=100 * 1024)
    with pytest.raises(jc.DownloadError) as exc:
        c.download(dict(SAMPLE_FILE, size=4 * 1024 * 1024))
    assert str(100 * 1024) in str(exc.value)
    assert body.read_bytes <= 100 * 1024 + 64 * 1024, "read %d bytes past the cap" % body.read_bytes


class DroppingBody(io.BytesIO):
    def read(self, n=-1):
        if self.tell() > 0:
            raise requests.exceptions.ConnectionError("the connection dropped mid-body")
        return super(DroppingBody, self).read(min(n, 1024) if n and n > 0 else 1024)


def test_a_connection_dropped_mid_download_is_an_error(online):
    s = Scripted(download_step(DroppingBody(derived_subtitle(SAMPLE_FILE["size"]))))
    c, _ = make(s)
    with pytest.raises(jc.DownloadError) as exc:
        c.download(SAMPLE_FILE)
    assert "dropped" in str(exc.value) and waits(c, "no answer") == []


# -- the real requests stack, on loopback --------------------------------------------

def _route(path_and_query):
    parts = urlsplit(path_and_query)
    return unquote(parts.path), tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))


class _Recordings(BaseHTTPRequestHandler):
    routes = {}
    seen = []

    def do_GET(self):
        type(self).seen.append((self.path, dict(self.headers.items())))
        found = type(self).routes.get(_route(self.path))
        if found is None:
            self.send_response(599)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status, body, headers = found
        headers = dict((k, v) for k, v in headers.items()
                       if k.lower() not in ("transfer-encoding", "content-length", "connection"))
        if headers.get("content-encoding") == "gzip":
            body = gzip.compress(body)                  # honour the recorded encoding on the wire
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Loopback(HTTPAdapter):
    """The real HTTPAdapter, with only the destination moved to 127.0.0.1."""

    def __init__(self, port):
        super(Loopback, self).__init__()
        self.port = port

    def send(self, request, **kw):
        parts = urlsplit(request.url)
        request = request.copy()
        request.url = urlunsplit(("http", "127.0.0.1:%d" % self.port, parts.path, parts.query, ""))
        return super(Loopback, self).send(request, **kw)


@pytest.fixture
def loopback():
    class Handler(_Recordings):
        routes = {}
        seen = []
    for stem in ("search__query_frieren", "entries_11446_files"):
        meta, body = recorded(stem)
        Handler.routes[_route(urlsplit(meta["url"]).path + "?" + urlsplit(meta["url"]).query)] = (
            meta["status"], body, meta["response_headers"])
    Handler.routes[_route(urlsplit(DOWNLOAD_META["url"]).path)] = download_step(
        derived_subtitle(SAMPLE_FILE["size"]))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session = requests.Session()
    session.trust_env = False
    session.mount("https://jimaku.cc/", Loopback(server.server_address[1]))
    try:
        yield session, Handler
    finally:
        session.close()
        server.shutdown()
        server.server_close()


def test_the_real_requests_stack_against_a_loopback_server(online, loopback):
    session, served = loopback
    c, _ = make(session)
    assert c.search("frieren") == json.loads(FRIEREN_BODY.decode("utf-8"))
    assert len(c.files(11446)) == len(RECORDED_FILES)
    assert len(c.download(SAMPLE_FILE)) == SAMPLE_FILE["size"], "the gzip body was not decoded"
    paths = [p for p, _ in served.seen]
    assert paths[:2] == ["/api/entries/search?query=frieren", "/api/entries/11446/files"], paths
    api = [h for p, h in served.seen if p.startswith("/api/")]
    downloads = [h for p, h in served.seen if p.startswith("/entry/")]
    assert len(api) == 2 and len(downloads) == 1, paths
    assert all(h.get("Authorization") == FAKE_KEY for h in api), shown(str(api))
    assert "Authorization" not in downloads[0], shown(str(downloads[0]))
    assert [p for p in paths if "episode" in unquote(p).lower()] == []
    assert (c.metered, c.unmetered) == (2, 1)


def test_a_connection_that_drops_on_loopback_climbs_the_ladder_to_the_stop(online):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    stop = threading.Event()

    def drop():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            conn.close()                                # no HTTP answer, ever

    threading.Thread(target=drop, daemon=True).start()
    session = requests.Session()
    session.trust_env = False
    session.mount("https://jimaku.cc/", Loopback(listener.getsockname()[1]))
    try:
        c, _ = make(session)
        with pytest.raises(jc.Unreachable):
            c.search("frieren")
        assert len(waits(c, "no answer")) == 5 and c.metered == 0, c.waits
    finally:
        stop.set()
        listener.close()
        session.close()


# -- `hato files` ----------------------------------------------------------------------

def run_files(monkeypatch, capsys, *argv):
    monkeypatch.setitem(cli.COMMANDS, "files", "hato.commands.files")
    code = cli.main(["files"] + list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_hato_files_lists_every_recorded_name_and_size(monkeypatch, capsys):
    code, out, err = run_files(monkeypatch, capsys, "11446", "--fixtures", str(FIXTURES))
    assert code == 0, err
    for f in RECORDED_FILES:
        assert "%s  %s" % (format(f["size"], ","), f["name"]) in out, f["name"]
    assert "%d files" % len(RECORDED_FILES) in out and "1 API call" in out


def test_hato_files_json_is_the_list_exactly_as_recorded(monkeypatch, capsys):
    """Every field of every file, as recorded. ⚠ Measured: jimaku returns BOTH recorded
    lists already in code-point name order, so no capture can tell its order from a
    sorted one -- the order is not what this checks."""
    movie = json.loads((API / "entries_movie_flag.json").read_text(encoding="utf-8"))
    code, out, _ = run_files(monkeypatch, capsys, "440", "--fixtures", str(FIXTURES), "--json")
    assert code == 0 and json.loads(out) == movie


def test_hato_files_for_an_entry_that_does_not_exist_exits_1_and_says_so(monkeypatch, capsys):
    code, out, err = run_files(monkeypatch, capsys, "999999", "--fixtures", str(FIXTURES))
    assert code == 1 and "no entry 999999" in err and "404" in err, (out, err)


def test_hato_files_without_fixtures_honours_the_network_switch(monkeypatch, capsys):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    monkeypatch.setenv("HATO_JIMAKU_KEY", FAKE_KEY)

    class NoSession(object):
        def __init__(self, *a, **kw):
            raise AssertionError("a real session was built while the network was switched off")

    monkeypatch.setattr(jc.requests, "Session", NoSession)
    code, out, err = run_files(monkeypatch, capsys, "11446")
    assert code == 1 and "HATO_NO_NETWORK" in err, (out, err)
    assert FAKE_KEY not in out + err


# -- the key file: where a secret may never be written ---------------------------------
# ⚠ Its sibling -- `.git` as a DIRECTORY -- is
# `test_the_key_is_refused_into_a_git_working_tree_and_nothing_is_written` in
# tests/test_wiring.py, with the rest of the credentials checks. This one is here
# only because test_wiring.py was another fixer's file in the pass that found the
# gap; ⭐ move it back beside its sibling when the two are in one pair of hands.

def test_the_key_is_refused_into_a_BARE_git_repository_too(tmp_path):
    """🚨 `_refuse_a_repo` looked for a `.git` entry and nothing else, so a BARE
    repository ACCEPTED the write (measured 2026-09-17: the file was created).
    A bare repo IS the git directory -- `HEAD`, `objects/` and `refs/` at the top
    level, no `.git` anywhere -- and it is what `git clone --bare`, `git init
    --bare` and every server-side repository are. "Never inside a repository" was
    implemented as a statement about one layout.
    """
    bare = tmp_path / "vault.git"
    (bare / "objects" / "pack").mkdir(parents=True)
    (bare / "refs" / "heads").mkdir(parents=True)
    (bare / "HEAD").write_text(u"ref: refs/heads/main\n", encoding="utf-8")
    (bare / "config").write_text(u"[core]\n\tbare = true\n", encoding="utf-8")
    source = tmp_path / "pasted.txt"
    source.write_text(FAKE_KEY + u"\n", encoding="utf-8")

    destination = bare / "data" / "key.txt"
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.save_key_from(source, destination)
    assert "git" in str(err.value) and str(bare) in str(err.value)
    assert FAKE_KEY not in str(err.value), "the refusal echoed the key back"
    assert not destination.exists() and not destination.parent.exists()

    # the control: an ordinary folder is written, so what was refused is the
    # repository and not something about the path
    plain = tmp_path / "outside" / "key.txt"
    key, written = credentials.save_key_from(source, plain)
    assert written == plain and plain.is_file() and key.reveal() == FAKE_KEY


def test_a_folder_that_only_half_looks_like_a_bare_repo_is_not_refused(tmp_path):
    """The other control: `HEAD` + `objects/` + `refs/` together are a repository;
    any one of them alone is a folder with an unlucky name, and refusing it would
    make the guard something a person has to work around."""
    source = tmp_path / "pasted.txt"
    source.write_text(FAKE_KEY + u"\n", encoding="utf-8")
    for n, missing in enumerate(("HEAD", "objects", "refs")):
        folder = tmp_path / ("nearly-%d" % n)
        (folder / "objects").mkdir(parents=True)
        (folder / "refs").mkdir(parents=True)
        (folder / "HEAD").write_text(u"ref: refs/heads/main\n", encoding="utf-8")
        target = folder / missing
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        destination = folder / "data" / "key.txt"
        key, written = credentials.save_key_from(source, destination)
        assert written == destination and key.reveal() == FAKE_KEY, missing
