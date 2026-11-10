# -*- coding: utf-8 -*-
u"""
hato/relations.py -- the anime-relations reader (LAYER 16: 16i from the v2 prototype of
2026-10-11; 16j the weekly refresh).

⭐ Driven by the BUNDLED snapshot for the one fact a check leans on (Frieren S2's rule),
and by literal lines for the shapes: `!`, `~`, `?`, one-episode redirects, overlaps.
⛔ Fail safe is the property: nothing here may raise, whatever the text.
"""
import datetime

import pytest

from hato import relations

FRIEREN = u"- 52991|46474|154587:29-38 -> 59978|49240|182255:1-10!"


def _rules(*lines):
    return relations.parse(u"::rules\n" + u"\n".join(lines) + u"\n")


def test_the_bundled_snapshot_states_frierens_second_season():
    b = relations.for_entry(182255)
    assert b is not None and (b.shift, b.abs_lo, b.abs_hi, b.own_lo, b.own_hi) == (28, 29, 38, 1, 10)


def test_the_first_season_is_not_bridged_by_its_sequels_rule():
    u"""Only the `!` self-rule speaks about an entry's OWN numbers: 154587 maps its 29-38
    AWAY to another entry, which says nothing about how 154587's files count."""
    assert relations.bridge_for(_rules(FRIEREN), 154587) is None


@pytest.mark.parametrize("anilist_id", [None, 0, -5, True, u"182255", 999999999])
def test_an_unknown_or_odd_id_states_nothing(anilist_id):
    assert relations.bridge_for(_rules(FRIEREN), anilist_id) is None


@pytest.mark.parametrize("line", [
    u"- 52991|46474|154587:29-38 -> 59978|49240|182255:1-10",        # no `!`: no self-rule
    u"- 52991|46474|182255:29 -> ~|~|~:1",                          # one episode is a redirect
    u"- ?|?|182255:29-38 -> ?|?|182255:1-12",                       # two lengths
    u"- ?|?|182255:5-20 -> ?|?|182255:1-16",                        # the counts overlap
    u"- ?|?|182255:1-10 -> ?|?|182255:29-38",                       # the wrong way
    u"garbage", u"- 1|2|3:x-y -> 4|5|6:1-2!", u"-", u"",
])
def test_a_rule_that_cannot_say_one_shift_states_nothing(line):
    assert relations.bridge_for(_rules(line), 182255) is None


def test_two_self_rules_for_one_entry_state_nothing():
    u"""`36516 -> 38020` has `21-24 -> 1-4!` AND `25-28 -> 1-4!` in the real file: two
    numbers for one episode, so neither is believed."""
    rules = _rules(u"- ?|?|1:21-24 -> ?|?|9:1-4!", u"- ?|?|1:25-28 -> ?|?|9:1-4!")
    assert relations.bridge_for(rules, 9) is None


def test_tilde_repeats_the_source_and_an_open_range_is_bounded_below_its_start():
    b = relations.bridge_for(_rules(u"- 34572|13209|97940:171-? -> 61967|50024|195604:1-?!"), 195604)
    assert b is not None and (b.shift, b.abs_lo, b.abs_hi, b.own_lo, b.own_hi) == (170, 171, None, 1, 170)
    same = relations.bridge_for(_rules(u"- 58749|48796|177175:17-26 -> ~|~|~:1-10"), 177175)
    assert same is not None and same.shift == 16


def test_rules_outside_the_rules_section_are_not_read():
    text = u"::meta\n- version: 1.3.0\n%s\n::rules\n" % FRIEREN
    assert relations.parse(text) == []


def test_a_missing_or_unreadable_file_reads_as_no_rules(tmp_path):
    assert relations.load(tmp_path / u"absent.txt") == []
    bad = tmp_path / u"bad.txt"
    bad.write_bytes(b"\xff\xfe\x00garbage")
    assert relations.load(bad) == []


def test_the_bridge_reads_numbers_and_guards_the_videos():
    b = relations.bridge_for(_rules(FRIEREN), 182255)
    assert b.offset([29, 30, 31], 2, [5, 6]) == 28           # absolute release, S2 videos
    assert b.offset([1, 2, 3], None, [31, 32]) == -28        # season release, absolute videos
    assert b.offset([29, 38], 2, [31, 32]) == 0              # Netflix S02E31 on S02E31
    assert b.offset([1, 2], 2, [5]) == 0
    assert b.offset([29, 30], None, [5, 6]) is None          # ⛔ a seasonless 5 may be S1's
    assert b.offset([29, 30], 1, [5, 6]) is None             # ⛔ season 1 is never bridged
    assert b.offset([1, 38], 2, [5]) is None                 # a part in both counts says nothing
    assert b.offset([1, 2], 2, [11]) is None                 # a video in neither



# ---------------------------------------------------------------------------
# 16j -- THE WEEKLY REFRESH (Sonic's option 2): at most once in 7 days; a 404, a
# timeout, an HTML page, a short list, an older one, bytes that are not text -> the
# copy hato had stands; a good list -> written whole, then read; the newer of the
# two is the one read; no network -> no call. Every check its own HATO_CACHE, and
# the network is the injected `get` -- ⛔ never a socket.
# ---------------------------------------------------------------------------

#: A rule no snapshot has: AniList 999999's own 13-24 are its 1-12 (shift 12).
NEWER_RULE = u"- 1|2|3:13-24 -> 4|5|999999:1-12!"
DAY = 24 * 3600
T0 = 1800000000.0


def _bundled_text():
    return relations.bundled_path().read_text(encoding="utf-8")


def _list(day=u"2026-11-01", extra=True, text=None):
    text = _bundled_text() if text is None else text
    assert u"- last_modified: 2026-10-11" in text
    text = text.replace(u"- last_modified: 2026-10-11", u"- last_modified: %s" % day)
    if extra:
        text = text.replace(u"::rules\n", u"::rules\n\n" + NEWER_RULE + u"\n", 1)
        assert NEWER_RULE in text
    return text.encode("utf-8")


@pytest.fixture
def cache(monkeypatch, tmp_path):
    u"""Its own HATO_CACHE; this process's read of the list forgotten before and after.
    -> {"logged": [...], "asked": [...], "serve": callable(url) -> bytes}."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / u"data"))
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)    # the injected `get` IS the network
    # ⚠ 16z (Z-C2): a date after tomorrow is no date -- today is pinned at T0's (2027-01-15),
    # so the lists below, dated up to 2027-01-01, never turn "future" as the real days pass
    monkeypatch.setattr(relations, "_today", lambda: datetime.date(2027, 1, 15), raising=False)
    saved = list(relations._LOADED)
    del relations._LOADED[:]
    world = {u"logged": [], u"asked": [], u"answer": _list()}

    def get(url):
        world[u"asked"].append(url)
        answer = world[u"answer"]
        if isinstance(answer, Exception):
            raise answer
        return answer

    world[u"run"] = lambda now=T0: relations.refresh(now, get=get, log=world[u"logged"].append)
    yield world
    del relations._LOADED[:]
    relations._LOADED.extend(saved)


def _leftovers():
    folder = relations.cached_path().parent
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(u".tmp")) \
        if folder.is_dir() else []


def test_a_good_list_is_written_whole_then_read(cache):
    assert relations.for_entry(999999) is None               # the snapshot has no such rule
    assert cache[u"run"]() == u"taken"
    assert cache[u"asked"] == [relations.REFRESH_URL] and cache[u"logged"] == []
    assert relations.cached_path().read_bytes() == _list()
    assert _leftovers() == [], u"a temp was left beside the list"
    stamp = relations.load_stamp()
    assert (stamp[u"outcome"], stamp[u"last_modified"], stamp[u"tried_at"]) == (
        u"taken", u"2026-11-01", T0)
    assert relations.current_text()[1] == u"cached"
    # ⭐ THEN READ -- by this process too, with no restart: the new rule speaks
    b = relations.for_entry(999999)
    assert b is not None and b.shift == 12, b
    assert relations.for_entry(182255).shift == 28            # and the old ones still do


@pytest.mark.parametrize("bad", [u"404", u"timeout", u"html", u"ten-rules", u"older", u"bytes"])
def test_what_is_turned_away_leaves_the_copy_hato_had(cache, bad):
    u"""The first week takes a good list; a week later the server sends something
    else. The good copy stays on disk byte for byte and stays the one read; one log
    line says why, and nothing louder."""
    assert cache[u"run"]() == u"taken"
    good = relations.cached_path().read_bytes()
    cache[u"answer"] = {
        u"404": relations.RefreshError(u"answered 404", answered=True),
        u"timeout": relations.RefreshError(u"ReadTimeout", answered=False),
        u"html": b"<!DOCTYPE html><html><body>Moved</body></html>",
        u"ten-rules": (u"::meta\n- version: 1.3.0\n- last_modified: 2026-12-01\n::rules\n"
                       + u"".join(u"- %d|%d|%d:13-24 -> %d|%d|%d:1-12!\n" % ((i,) * 6)
                                  for i in range(1, 11))).encode("utf-8"),
        u"older": _list(day=u"2026-01-01"),
        u"bytes": b"\xff\xfe\x00 not text",
    }[bad]
    assert cache[u"run"](now=T0 + 8 * DAY) == u"kept"
    assert relations.cached_path().read_bytes() == good, bad
    del relations._LOADED[:]
    assert relations.current_text()[1] == u"cached" and relations.for_entry(999999).shift == 12
    assert len(cache[u"logged"]) == 1 and u"stands" in cache[u"logged"][0], cache[u"logged"]
    assert _leftovers() == []


@pytest.mark.parametrize("bad", [u"html", u"ten-rules", u"older"])
def test_with_nothing_cached_a_turned_away_list_leaves_the_bundled_one(cache, bad):
    cache[u"answer"] = {u"html": b"<html></html>", u"older": _list(day=u"2026-01-01"),
                        u"ten-rules": _list(text=u"::meta\n- version: 1.3.0\n"
                                                 u"- last_modified: 2026-10-11\n::rules\n"
                                                 + NEWER_RULE + u"\n")}[bad]
    assert cache[u"run"]() == u"kept"
    assert not relations.cached_path().exists()
    assert relations.current_text()[1] == u"bundled" and relations.for_entry(999999) is None


def test_it_is_due_at_seven_days_not_six(cache):
    assert cache[u"run"]() == u"taken"
    assert cache[u"run"](now=T0 + 6 * DAY + 23 * 3600) == u"not-due"
    assert len(cache[u"asked"]) == 1, u"asked again inside the week"
    assert cache[u"run"](now=T0 + 7 * DAY) == u"taken"
    assert len(cache[u"asked"]) == 2
    # ⚠ a clock set back is owed, not trusted
    assert cache[u"run"](now=T0) == u"taken" and len(cache[u"asked"]) == 3


def test_no_answer_at_all_tries_again_the_next_day_not_the_next_hour(cache):
    cache[u"answer"] = relations.RefreshError(u"ConnectionError", answered=False)
    assert cache[u"run"]() == u"kept"
    assert cache[u"run"](now=T0 + 3600) == u"not-due"
    assert cache[u"run"](now=T0 + DAY) == u"kept" and len(cache[u"asked"]) == 2
    cache[u"answer"] = relations.RefreshError(u"answered 404", answered=True)
    assert cache[u"run"](now=T0 + 2 * DAY) == u"kept"
    assert cache[u"run"](now=T0 + 8 * DAY) == u"not-due", u"a served 404 waits the week"


def test_the_newer_of_the_two_copies_is_the_one_read(cache):
    u"""The cached copy wins only when it is a good list AND strictly newer than the
    snapshot this release carries -- an older hato's copy left in the cache after an
    update to a release with a newer snapshot never shadows it."""
    path = relations.cached_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(_list(day=u"2026-10-11"))                   # the same day: bundled
    assert relations.current_text()[1] == u"bundled"
    path.write_bytes(_list(day=u"2026-10-10", extra=True))       # older: bundled
    assert relations.current_text()[1] == u"bundled"
    path.write_bytes(_list(day=u"2026-10-12"))                   # newer: cached
    assert relations.current_text()[1] == u"cached"
    path.write_bytes(b"::meta\n- version: 1.3.0\n- last_modified: 2027-01-01\n::rules\n")
    assert relations.current_text()[1] == u"bundled", u"a newer but empty list was read"


def test_with_the_network_off_nothing_is_asked(cache, monkeypatch):
    u"""HATO_NO_NETWORK=1 (the suite's, and a person's): no request, not even a
    refused one -- `requests.get` is never reached -- and nothing is written."""
    import requests
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a) or 1 / 0)
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    assert relations.refresh(T0, log=cache[u"logged"].append) == u"offline"
    with pytest.raises(relations.RefreshError):
        relations.fetch()
    assert calls == [] and cache[u"logged"] == []
    assert not relations.stamp_path().exists() and not relations.cached_path().exists()


# ---------------------------------------------------------------------------
# 16n -- the fix round for 16j's first adversarial pass (ADVERSARY 2026-10-31, R1-R3,
# R9, R10): judged against the copy hato READS NOW; a stamp whatever fails after a
# fetch; an overall deadline on a trickling server.
# ---------------------------------------------------------------------------

def test_16n_F1_a_download_older_than_the_cached_copy_keeps_it(cache):
    u"""R1: a list newer than the bundled one but OLDER than the cached copy hato reads
    replaced it -- and hato read the older list."""
    cache[u"answer"] = _list(day=u"2026-11-15")
    assert cache[u"run"]() == u"taken"
    newest = relations.cached_path().read_bytes()
    cache[u"answer"] = _list(day=u"2026-11-01")              # > 2026-10-11, < 2026-11-15
    assert cache[u"run"](now=T0 + 8 * DAY) == u"kept"
    assert relations.cached_path().read_bytes() == newest, u"an older download replaced the cached copy"
    assert relations.load_stamp()[u"outcome"].startswith(u"kept: older than")
    assert len(cache[u"logged"]) == 1 and u"stands" in cache[u"logged"][0], cache[u"logged"]


def test_16n_F1_a_good_cached_copy_is_read_when_the_bundled_one_is_unreadable(cache, monkeypatch,
                                                                               tmp_path):
    u"""R9: with the bundled copy unreadable (a broken install), a good cached copy was
    ignored -- hato read NO list. `judge` takes None: no share or date test against it."""
    good = _list(day=u"2026-11-01")
    path = relations.cached_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(good)
    monkeypatch.setattr(relations, "bundled_path", lambda: tmp_path / u"absent.txt")
    assert relations.judge(good.decode("utf-8"), None) is None
    text, which = relations.current_text()
    assert which == u"cached" and text == good.decode("utf-8"), which


def test_16n_F1_the_cheap_date_is_tested_before_the_list_is_judged(cache, monkeypatch):
    u"""R10: `current_text` parsed both whole lists on every read, even for a cached copy
    whose date already says it is not the newer one."""
    judged = []
    real = relations.judge
    monkeypatch.setattr(relations, "judge", lambda *a, **k: judged.append(1) or real(*a, **k))
    path = relations.cached_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(_list(day=u"2026-10-01"))                   # older than the bundled one
    assert relations.current_text()[1] == u"bundled"
    assert judged == [], u"an older cached copy was judged before its date was read"
    path.write_bytes(_list(day=u"2026-10-12"))
    assert relations.current_text()[1] == u"cached" and judged == [1]


@pytest.mark.parametrize("where", [u"cache-write", u"judge", u"no-bytes"])
def test_16n_F2_a_failure_after_the_fetch_still_stamps_so_the_next_hour_asks_nothing(
        cache, monkeypatch, where):
    u"""R2: a failure AFTER the fetch (the cache write, `judge`) escaped `_refresh` with
    no stamp written -- every hourly child of the tray fetched again. `answered` is true
    when the server sent bytes (a weekly wait), false when nothing came (a daily one)."""
    if where == u"cache-write":
        real = relations._write_atomic

        def failing(path, data):
            if str(path) == str(relations.cached_path()):
                raise OSError(u"the disk is full")
            return real(path, data)

        monkeypatch.setattr(relations, "_write_atomic", failing)
    elif where == u"judge":
        monkeypatch.setattr(relations, "judge", lambda *a, **k: 1 / 0)
    else:
        cache[u"answer"] = RuntimeError(u"the socket went away")
    assert cache[u"run"]() == u"kept"
    stamp = relations.load_stamp()
    said = {u"cache-write": u"kept: OSError: ", u"judge": u"kept: ZeroDivisionError: ",
            u"no-bytes": u"kept: RuntimeError: the socket went away"}[where]
    assert stamp.get(u"tried_at") == T0 and stamp.get(u"outcome", u"").startswith(said), stamp
    assert stamp[u"answered"] is (where != u"no-bytes"), stamp
    assert cache[u"run"](now=T0 + 3600) == u"not-due" and len(cache[u"asked"]) == 1, \
        u"the next hour fetched again"
    assert not relations.cached_path().exists() and _leftovers() == []
    assert len(cache[u"logged"]) == 1 and u"stands" in cache[u"logged"][0], cache[u"logged"]


def test_16n_F3_a_server_that_trickles_is_cut_off_at_the_overall_deadline(monkeypatch):
    u"""R3: `timeout` is per socket READ -- a server sending a byte every few seconds held
    the tray's child for minutes. The whole fetch has a deadline (no network: a fake
    response, a fake clock)."""
    import requests
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)
    clock, read = [0.0], []

    class Trickle(object):
        u"""⚠ 16z (Z-C3): `fetch` reads one socket read at a time (`raw.read1`), never
        `iter_content` -- whose 1-byte blocks here passed for the wrong reason. The REAL
        drip is `test_16z_C3_the_deadline_holds_against_a_one_byte_drip`."""
        status_code = 200
        headers = {}

        def __init__(self):
            self.raw = self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read1(self, size):
            if len(read) == 10:
                return b""
            clock[0] += 25.0                                    # each byte 25 s apart
            read.append(len(read))
            return b"x"

    monkeypatch.setattr(relations, "_monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Trickle())
    with pytest.raises(relations.RefreshError) as raised:
        relations.fetch()
    assert raised.value.answered is True and u"seconds" in str(raised.value), raised.value
    assert len(read) < 10, u"the whole trickle was read"


# ---------------------------------------------------------------------------
# 16z -- the Opus adversaries (ADVERSARY 2026-10-31, Z-C1..Z-C3): a download cut off
# before its promised length, a date no calendar has or after tomorrow, a drip that
# never filled a 64 KiB block. ⛔ Local sockets only: a socketpair stands in for
# raw.githubusercontent.com, behind a real requests/urllib3 response.
# ---------------------------------------------------------------------------

@pytest.fixture
def served(monkeypatch):
    u"""`requests.get` -> a real `requests.Response` read off a local socketpair. ->
    serve(head, body, drip=None, close_after=None): `head` the status line and headers;
    `drip` (seconds) sends `body` ONE BYTE at a time that far apart -- a real drip, not
    blocks handed over -- until `close_after` seconds; then the server closes."""
    import http.client
    import socket
    import threading
    import time
    import requests
    import urllib3
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)
    world = {u"asked": [], u"sockets": []}

    def serve(head, body, drip=None, close_after=None):
        def get(url, **kw):
            world[u"asked"].append(kw)
            a, b = socket.socketpair()
            world[u"sockets"].extend((a, b))
            a.settimeout(kw.get(u"timeout") or 5)
            b.sendall(head + b"\r\n\r\n")

            def send():
                ends = time.monotonic() + (close_after or 60.0)
                try:
                    if drip is None:
                        b.sendall(body)
                    for i in range(len(body) if drip is not None else 0):
                        if time.monotonic() > ends:
                            break
                        time.sleep(drip)
                        b.sendall(body[i:i + 1])
                except OSError:
                    pass
                finally:
                    b.close()

            threading.Thread(target=send, daemon=True).start()
            resp = http.client.HTTPResponse(a)
            resp.begin()
            # ⚠ urllib3 2.x has no `from_httplib` (CI and the frozen build install 2.8;
            # the dev venv pins 1.26): build the response as each version's pool does,
            # its own defaults kept (2.x enforces the promised length, 1.26 does not)
            if hasattr(urllib3.response.HTTPResponse, "from_httplib"):
                raw = urllib3.response.HTTPResponse.from_httplib(resp, preload_content=False,
                                                                 decode_content=False)
            else:
                raw = urllib3.response.HTTPResponse(
                    body=resp, headers=resp.getheaders(), status=resp.status,
                    version=resp.version, reason=resp.reason, preload_content=False,
                    decode_content=False, original_response=resp)
            r = requests.Response()
            r.raw, r.status_code, r.url = raw, resp.status, url
            r.headers = requests.structures.CaseInsensitiveDict(raw.headers)
            return r

        monkeypatch.setattr(requests, "get", get)

    world[u"serve"] = serve
    yield world
    for s in world[u"sockets"]:
        s.close()


def test_16z_C1_a_download_cut_off_before_its_promised_length_is_refused(served):
    u"""Z-C1: urllib3 1.26 hands back a SHORT body, no error, when the server closes before
    its Content-Length -- 93 % of the rules passed the 90 % test and the last titles'
    rules were gone for a week. A day's wait, as a dropped connection's."""
    whole = _list()
    promised = b"HTTP/1.1 200 OK\r\nContent-Length: %d" % len(whole)
    served[u"serve"](promised, whole[:len(whole) * 93 // 100])
    with pytest.raises(relations.RefreshError) as raised:
        relations.fetch()
    assert u"of %d bytes" % len(whole) in str(raised.value), raised.value
    assert raised.value.answered is False, u"a dropped download waits the week"
    served[u"serve"](promised, whole)                          # the control: whole, taken
    assert relations.fetch() == whole
    assert served[u"asked"][-1][u"headers"][u"Accept-Encoding"] == u"identity"


def test_a_cut_short_body_that_urllib3_RAISES_on_is_a_refresh_error_too(served, monkeypatch):
    u"""1.1.0's CI: urllib3 2.x (the frozen build's; the dev venv pins 1.26) raises its
    OWN ProtocolError(IncompleteRead) from `read1` on a body cut short -- none of the
    errors `fetch` named, so `fetch` broke its word, "Raises RefreshError". Faked here
    on both urllib3s: the error 2.x raises, and a plain one beside it."""
    import urllib3.exceptions as u3
    served[u"serve"](b"HTTP/1.1 200 OK\r\nContent-Length: 30", b"x" * 30)

    def cut(response):
        def read(n):
            raise u3.ProtocolError(u"Connection broken", u3.IncompleteRead(10, 20))
        return read
    monkeypatch.setattr(relations, "_read_some", cut)
    with pytest.raises(relations.RefreshError) as raised:
        relations.fetch()
    assert str(raised.value) == u"cut short: 10 of 30 bytes", raised.value
    assert raised.value.answered is False, u"a dropped download waits the day"

    def broken(response):
        def read(n):
            raise u3.ProtocolError(u"Connection aborted")
        return read
    monkeypatch.setattr(relations, "_read_some", broken)
    served[u"serve"](b"HTTP/1.1 200 OK\r\nContent-Length: 30", b"x" * 30)
    with pytest.raises(relations.RefreshError) as raised:
        relations.fetch()
    assert str(raised.value) == u"ProtocolError" and raised.value.answered is False


def test_16z_C1_a_list_that_ends_inside_a_line_is_turned_away(cache):
    u"""Z-C1, the probe's road (no Content-Length to hold it to): a list cut mid-line is
    turned away -- the text must end on a whole line."""
    lines = _list().decode("utf-8").splitlines(True)
    cut = u"".join(lines[:int(len(lines) * 0.93)])[:-7]
    assert len(relations.parse(cut)) >= relations.MIN_SHARE * len(relations.parse(_bundled_text()))
    cache[u"answer"] = cut.encode("utf-8")
    assert cache[u"run"]() == u"kept"
    assert not relations.cached_path().exists()
    assert len(cache[u"logged"]) == 1 and u"whole line" in cache[u"logged"][0], cache[u"logged"]


@pytest.mark.parametrize("day, taken", [(u"2062-10-25", False), (u"2027-01-17", False),
                                        (u"2027-01-16", True)])
def test_16z_C2_a_date_after_tomorrow_is_refused_on_fetch(cache, day, taken):
    u"""Z-C2: a mistyped future date sorted after every later list and release, and pinned
    that copy for good. Today is 2027-01-15 here (UTC); tomorrow is still a date -- one
    day of slack for a list dated where its author lives."""
    cache[u"answer"] = _list(day=day)
    assert cache[u"run"]() == (u"taken" if taken else u"kept"), cache[u"logged"]
    if not taken:
        assert u"after today" in cache[u"logged"][0], cache[u"logged"]
        assert not relations.cached_path().exists()


def test_16z_C2_a_cached_copy_dated_in_the_future_is_not_newer(cache):
    u"""Z-C2 on READ: a copy already in the cache with a future date (an older hato took
    it) is not "newer" -- the bundled copy is read."""
    path = relations.cached_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(_list(day=u"2062-10-25"))
    assert relations.current_text()[1] == u"bundled"
    path.write_bytes(_list(day=u"2027-01-01"))                   # the control
    assert relations.current_text()[1] == u"cached"


@pytest.mark.parametrize("day", [u"2026-99-99", u"2026-13-01", u"2026-11-31", u"2026-10-32"])
def test_16z_C2_a_date_no_calendar_has_is_no_date(cache, day):
    assert relations._day(u"::meta\n- last_modified: %s\n" % day) is None
    cache[u"answer"] = _list(day=day)
    assert cache[u"run"]() == u"kept"
    assert u"no calendar date" in cache[u"logged"][0], cache[u"logged"]


def test_16z_C3_the_deadline_holds_against_a_one_byte_drip(served, monkeypatch):
    u"""Z-C3: the deadline was looked at only between 64 KiB blocks -- the list is ~49 KB,
    so a byte every few seconds never reached it (F-3's fake handed over 1-byte blocks
    and passed for the wrong reason). A REAL drip, a byte every 0.2 s on a local socket,
    the deadline cut to 1 s: the fetch ends near it, not when the server gives up."""
    import time
    monkeypatch.setattr(relations, "DEADLINE_SECONDS", 1.0)
    whole = _list()
    served[u"serve"](b"HTTP/1.1 200 OK\r\nContent-Length: %d" % len(whole), whole,
                     drip=0.2, close_after=8.0)
    started = time.monotonic()
    with pytest.raises(relations.RefreshError) as raised:
        relations.fetch()
    took = time.monotonic() - started
    assert took < 3.0, u"the drip held the fetch %.1f s past a 1 s deadline" % took
    assert u"seconds" in str(raised.value) and raised.value.answered is True, raised.value
