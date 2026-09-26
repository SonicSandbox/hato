# -*- coding: utf-8 -*-
"""
Step 0b -- `hato doctor`. Asserts the readout's SHAPE and the capture's
SAFETY. Never the live values (spec/RUNBOOK.md 0b).

What this suite STRUCTURALLY cannot cover: whether jimaku's live responses still
look like this. That is `hato doctor` itself, run deliberately, and the opt-in
`live` suite.

The session double is built from the REAL requests types (requests.Response,
CaseInsensitiveDict) -- a fake that disagrees with the real thing about a type
measures the fake (tsubasa LEDGER-HOT).
"""
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from hato import credentials, doctor

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "hk_SECRET_do_not_leak_0123456789LEAK"
SUB_BODY = u"[Script Info]\nTitle: synthetic hato test subtitle\n\n[Events]\n".encode("utf-8")

RATE = {"x-ratelimit-limit": "25", "x-ratelimit-remaining": "24",
        "x-ratelimit-reset": "1758072000.123", "x-ratelimit-reset-after": "59.873"}


def response(status=200, body=b"", headers=None, url="https://jimaku.cc/x"):
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers = CaseInsensitiveDict(headers or {})
    r.url = url
    r.encoding = "utf-8"
    return r


def jbody(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


FILES = [
    {"name": u"[Haruhana] Sousou no Frieren - 29 [WebRip][JPN].ass", "size": 49646,
     "last_modified": "2026-01-01T00:00:00Z",
     "url": "https://jimaku.cc/entry/11446/download/a.ass"},
    {"name": u"[shincaps] Sousou no Frieren - 01.srt", "size": 30000,
     "last_modified": "2026-01-01T00:00:00Z",
     "url": "https://jimaku.cc/entry/11446/download/b.srt"},
]


class FakeSession(object):
    """Routes by URL; records every call and every header it was sent."""

    def __init__(self, overrides=None, catalogue=50, remaining="24", search_body=None):
        self.calls = []
        self.overrides = overrides or {}
        self.catalogue = catalogue
        self.remaining = remaining
        self.search_body = search_body

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.calls.append({"url": url, "params": dict(params or {}),
                           "headers": dict(headers or {}), "kw": dict(kw)})
        params = params or {}
        rate = dict(RATE, **{"x-ratelimit-remaining": self.remaining})
        for pattern, maker in self.overrides.items():
            if pattern in url:
                return maker(url, params, headers)
        if url.endswith("/entries/search"):
            if (headers or {}).get("Authorization") != FAKE_KEY:
                return response(401, b'{"error":"unauthorized"}', rate, url)
            q = params.get("query")
            if q == "":
                return response(200, jbody([{"id": i, "name": "E%d" % i} for i in range(self.catalogue)]), rate, url)
            if q == doctor.LIVE_ACTION_QUERY and params.get("anime") != "false":
                return response(200, b"[]", rate, url)
            if q in doctor.MOVIE_QUERIES:
                return response(200, jbody([{"id": 77, "name": "Kimi no Na wa.",
                                             "flags": {"anime": True, "movie": True}}]), rate, url)
            body = self.search_body if self.search_body is not None else jbody(
                [{"id": 729, "name": "Sousou no Frieren", "flags": {"anime": True, "movie": False}}])
            return response(200, body, rate, url)
        if "/entries/" in url and url.endswith("/files"):
            return response(200, jbody(FILES), rate, url)
        if "/download/" in url:
            return response(200, SUB_BODY, {"content-type": "text/plain"}, url)
        return response(404, b"not found", rate, url)

    @property
    def metered(self):
        return [c for c in self.calls if "/api/" in c["url"]]


class LeaksTheFirstBodyOnly(FakeSession):
    """🚨 The key in the FIRST captured body and NOWHERE else.

    Its point is the site, not the leak: `search__query_frieren` is captured
    inside `except Exception:  # a readout reports, it does not crash`, so a
    CaptureLeak raised there used to be swallowed and the run carried on. A
    session that leaks EVERY search (the one the older check uses) cannot show
    that -- the exception it sees comes from the next, unguarded capture site,
    five metered calls later.
    """

    def __init__(self, **kw):
        FakeSession.__init__(self, **kw)
        self.leaked = 0

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        resp = FakeSession.get(self, url, params=params, headers=headers, timeout=timeout, **kw)
        if not self.leaked and url.endswith("/entries/search"):
            self.leaked += 1
            return response(200, jbody([{"id": 729, "name": FAKE_KEY}]), dict(resp.headers), url)
        return resp


def fake_key():
    return credentials.Key(FAKE_KEY, "test")


def collect(**kw):
    kw.setdefault("key_resolver", fake_key)
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("rng", random.Random(7))
    kw.setdefault("which", lambda name: None)
    return doctor.collect(**kw)


REQUIRED = ["key", "search", "rate limit", "files", "download", "tsubasa",
            "self_check", "track reader", "extractor", "anitopy", "guessit", "unrar",
            "py7zr", "cache",
            "config", "api calls"]


# -- the readout ---------------------------------------------------------------

def test_every_line_is_resolved_or_explicitly_missing():
    ro = collect(session=FakeSession())
    labels = [l.label for l in ro.lines]
    assert labels == REQUIRED, labels
    for line in ro.lines:
        assert line.text.strip(), "the %r line is blank" % line.label
        assert line.state in (doctor.OK, doctor.MISSING, doctor.SKIPPED, doctor.FAILED)
    text = doctor.render(ro)
    for label in REQUIRED:
        assert "  %s" % label in text


def test_a_healthy_readout_exits_0_and_counts_its_calls():
    s = FakeSession()
    ro = collect(session=s)
    assert ro.exit_code == 0, doctor.render(ro)
    assert ro.metered == len(s.metered) == 2, s.calls
    assert ro.unmetered == 1


def test_the_rate_limit_headers_are_shown_verbatim():
    text = doctor.render(collect(session=FakeSession()))
    for name, value in RATE.items():
        assert "%s: %s" % (name, value) in text


def test_the_key_goes_raw_in_Authorization_with_no_Bearer_prefix():
    s = FakeSession()
    collect(session=s)
    for call in s.metered:
        assert call["headers"]["Authorization"] == FAKE_KEY
    assert all("Authorization" not in c["headers"] for c in s.calls if "/download/" in c["url"])


def test_the_file_count_and_keys_come_from_the_response():
    ro = collect(session=FakeSession())
    files = next(l for l in ro.lines if l.label == "files")
    assert "%d files" % len(FILES) in files.text
    assert "keys: last_modified, name, size, url" in files.extra


def test_the_download_picks_the_smallest_subtitle_and_sniffs_it():
    ro = collect(session=FakeSession())
    dl = next(l for l in ro.lines if l.label == "download")
    assert "utf-8" in dl.text and str(len(SUB_BODY)) in dl.text.replace(",", "")
    assert "shincaps" in dl.extra[0]


def test_a_401_stops_every_further_metered_call():
    s = FakeSession(overrides={"/entries/search": lambda u, p, h: response(401, b"{}", RATE, u)})
    ro = collect(session=s)
    assert len(s.metered) == 1, "retried or continued past a 401: %s" % s.calls
    assert ro.key_rejected and ro.exit_code == 1
    text = doctor.render(ro)
    assert "401" in text and "REJECTED" in text
    assert next(l for l in ro.lines if l.label == "files").state == doctor.SKIPPED


def test_a_missing_key_makes_no_metered_call():
    def no_key():
        raise credentials.KeyMissing("no key anywhere")
    s = FakeSession()
    ro = collect(session=s, key_resolver=no_key)
    assert s.metered == [] and ro.metered == 0
    assert ro.lines[0].state == doctor.MISSING
    assert ro.exit_code == 1


def test_the_network_switch_skips_every_network_line_with_its_reason():
    assert os.environ.get("HATO_NO_NETWORK") == "1"
    ro = collect(session=None)
    for label in ("search", "rate limit", "files", "download"):
        line = next(l for l in ro.lines if l.label == label)
        assert line.state == doctor.SKIPPED and "HATO_NO_NETWORK" in line.text, line.text
    assert ro.metered == 0 and ro.exit_code == 1


def test_a_server_error_is_FAILED_not_a_crash():
    s = FakeSession(overrides={"/files": lambda u, p, h: response(500, b"boom", RATE, u)})
    ro = collect(session=s)
    assert next(l for l in ro.lines if l.label == "files").state == doctor.FAILED
    assert ro.exit_code == 1


def test_waits_between_metered_calls_are_jittered_never_constant(tmp_path):
    waits = []
    collect(session=FakeSession(), capture_dir=tmp_path, sleep=waits.append)
    assert len(waits) >= 5
    assert all(1.0 <= w < 2.0 for w in waits), waits
    assert len(set(waits)) > 1, "a constant delay: %s" % waits


def test_the_track_reader_line_names_the_public_function_when_it_exists(monkeypatch):
    import tsubasa
    monkeypatch.setattr(tsubasa, "__all__", list(tsubasa.__all__) + ["embedded_subs"])
    monkeypatch.setattr(tsubasa, "embedded_subs", lambda v: None, raising=False)
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "track reader")
    assert line.state == doctor.OK and "tsubasa.embedded_subs" in line.text


def test_the_track_reader_line_says_missing_and_blocked_when_it_does_not(monkeypatch):
    import tsubasa
    monkeypatch.setattr(tsubasa, "__all__", [n for n in tsubasa.__all__ if n != "embedded_subs"])
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "track reader")
    assert line.state == doctor.MISSING
    assert "embedded_subs" in line.text and "4b" in line.text

def test_the_extractor_line_says_whether_saving_them_beside_the_video_can_work(
        monkeypatch):
    u"""⭐ RUNBOOK 14c -- *Save them beside the video* takes a track out through
    tsubasa's `extract_subtitle` (0.1.9). Two arms: exported -> OK, named; not
    -> MISSING, and what the choice does instead."""
    import tsubasa
    monkeypatch.setattr(tsubasa, "__all__", list(tsubasa.__all__) + ["extract_subtitle"])
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "extractor")
    assert line.state == doctor.OK and "tsubasa.extract_subtitle" in line.text
    monkeypatch.setattr(tsubasa, "__all__",
                        [n for n in tsubasa.__all__ if n != "extract_subtitle"])
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "extractor")
    assert line.state == doctor.MISSING, line.text
    assert "0.1.9" in line.text and "downloads instead" in line.text, line.text


def test_the_config_line_says_refused_when_every_run_would_stop(monkeypatch, tmp_path):
    u"""⭐ 14z (C-3) -- FOUND IS NOT READ: the doctor said *found* beside a file every run
    refused -- a key hato has never heard of, a newer hato's. FAILED, with hato's own
    words; a file hato reads is found, as before."""
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("HATO_CONFIG", str(cfg))
    # ⚠ Not named like a *key*: a key-shaped field is refused by its own rule first
    cfg.write_text(u"a_setting_from_a_newer_hato = true\n", encoding="utf-8")
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "config")
    assert line.state == doctor.FAILED and "REFUSED" in line.text, (line.state, line.text)
    assert any("unknown key" in extra for extra in line.extra), line.extra
    cfg.write_text(u"skip_embedded = true\n", encoding="utf-8")
    line = next(l for l in collect(session=FakeSession()).lines if l.label == "config")
    assert line.state == doctor.OK and "found" in line.text, (line.state, line.text)


def _parser_line(ro, name):
    return next(l for l in ro.lines if l.label == name)


def test_each_optional_parser_is_asked_to_parse_a_name_itself():
    u"""ADVERSARY 2026-09-22 D1. tsubasa's wrapper swallows a parser that raises,
    so a run cannot tell a working guessit from a broken one -- the doctor asks
    the parser directly, with a name it must number."""
    ro = collect(session=FakeSession())
    for name in (u"anitopy", u"guessit"):
        line = _parser_line(ro, name)
        assert line.state == doctor.OK and u"-> episode" in line.text, (name, line.text)


def test_a_parser_that_imports_and_cannot_parse_is_FAILED_with_its_own_words(monkeypatch):
    u"""⭐ The frozen build's failure shape: the import works, the parse raises
    (babelfish's converters left out). tsubasa hides it; this must not."""
    import guessit as _guessit_pkg

    def broken(filename, *a, **k):
        raise ValueError(u"no converter for country code")

    monkeypatch.setattr(_guessit_pkg, u"guessit", broken)
    line = _parser_line(collect(session=FakeSession()), u"guessit")
    assert line.state == doctor.FAILED and u"no converter for country code" in line.text, line.text


def test_a_parser_that_numbers_the_name_wrong_is_FAILED_not_OK(monkeypatch):
    u"""D1's verdict: a parser that answers with the WRONG episode works as badly
    as one that raises -- and every check drove a right answer or a raise, so the
    comparison could be dropped unseen (found by the M8zd builder)."""
    import guessit as _guessit_pkg
    monkeypatch.setattr(_guessit_pkg, u"guessit", lambda filename, *a, **k: {u"episode": 4})
    line = _parser_line(collect(session=FakeSession()), u"guessit")
    assert line.state == doctor.FAILED and line.extra == [u"expected episode 5"], (
        line.state, line.text, line.extra)


def test_a_parser_that_is_not_installed_is_MISSING_not_a_fault(monkeypatch):
    import sys as _sys
    monkeypatch.setitem(_sys.modules, u"guessit", None)
    line = _parser_line(collect(session=FakeSession()), u"guessit")
    assert line.state == doctor.MISSING and u"not importable" in line.text, line.text


def test_optional_archive_tools_are_reported_by_presence():
    ro = collect(session=FakeSession(), which=lambda n: r"C:\tools\unrar.exe" if n == "unrar" else None)
    assert next(l for l in ro.lines if l.label == "unrar").state == doctor.OK
    ro = collect(session=FakeSession())
    assert next(l for l in ro.lines if l.label == "unrar").state == doctor.MISSING


def test_a_folder_left_by_the_old_root_is_named_in_one_line_and_left_alone(tmp_path, monkeypatch):
    """⛔ Nothing is migrated automatically (spec/05-interface.md, RUNBOOK 1c)."""
    old = tmp_path / ".cache" / "hato"
    (old / "subs").mkdir(parents=True)
    kept = old / "subs" / "Show - 01.ja.ass"
    kept.write_text(u"a kept original", encoding="utf-8")
    monkeypatch.setattr(doctor.paths, "legacy_data_root", lambda: old)

    lines = [l for l in collect(session=FakeSession()).lines if l.label == "old folder"]
    assert len(lines) == 1, "the old folder is said once, or not at all"
    assert str(old) in lines[0].text and "left where it is" in lines[0].text
    assert any("Nothing was moved or deleted" in e for e in lines[0].extra), lines[0].extra
    assert kept.read_text(encoding="utf-8") == u"a kept original"
    assert [p.name for p in (old / "subs").iterdir()] == ["Show - 01.ja.ass"]


def test_nothing_is_said_about_an_old_folder_that_is_not_there():
    labels = [l.label for l in collect(session=FakeSession()).lines]
    assert "old folder" not in labels, labels


# -- the capture ---------------------------------------------------------------

def test_capture_writes_bodies_byte_for_byte_with_provenance(tmp_path):
    collect(session=FakeSession(), capture_dir=tmp_path)
    body = (tmp_path / "entries_11446_files.json").read_bytes()
    assert body == jbody(FILES)
    meta = json.loads((tmp_path / "entries_11446_files.meta.json").read_text(encoding="utf-8"))
    for field in ("captured_at", "url", "status", "response_headers", "sha256", "provenance"):
        assert meta.get(field) not in (None, ""), field
    assert meta["url"].endswith("/api/entries/11446/files")
    assert "episode" not in meta["url"], "the files call must never carry episode="


def test_capture_never_writes_the_key_a_request_header_or_a_subtitle_body(tmp_path):
    collect(session=FakeSession(), capture_dir=tmp_path)
    written = [p for p in tmp_path.iterdir() if p.is_file()]
    assert len(written) >= 8, written
    for p in written:
        data = p.read_bytes()
        assert FAKE_KEY.encode() not in data, "the key leaked into %s" % p.name
        assert b"authorization" not in data.lower(), "a request header leaked into %s" % p.name
        assert SUB_BODY not in data and b"synthetic hato test subtitle" not in data, (
            "a downloaded subtitle body was written into %s" % p.name)
    assert not list(tmp_path.glob("*.tmp")), "a temp file survived the rename"


def test_a_capture_that_would_contain_the_key_is_refused_and_nothing_is_written(tmp_path):
    leaky = FakeSession(search_body=jbody([{"id": 1, "name": FAKE_KEY}]))
    with pytest.raises(doctor.CaptureLeak):
        collect(session=leaky, capture_dir=tmp_path)
    assert not (tmp_path / "search__query_frieren.json").exists()
    for p in tmp_path.iterdir():
        assert FAKE_KEY.encode() not in p.read_bytes()


# ⚠ The five codecs are spelled out ON PURPOSE rather than read from
# `doctor.KEY_CODECS`. Parametrising over the constant under test means the
# mutant that shortens the constant DELETES ITS OWN WITNESS -- pytest then
# exits "not found" rather than failing, and a mutation run reads that as a
# kill. Measured on this project 2026-09-17, in `hato/dev/scan.py`.
# `test_the_capture_guard_hunts_every_codec_it_declares` is what ties the two
# lists together, so a SIXTH codec added to the constant cannot go untested.
@pytest.mark.parametrize("codec", ["utf-8", "utf-16-le", "utf-16-be", "cp932", "cp1252"])
def test_a_key_in_any_encoding_is_caught_before_a_capture_is_kept(tmp_path, codec):
    """🚨 THE GUARD WAS UTF-8 ONLY UNTIL 2026-09-17, and that is not a
    theoretical gap: `--capture` writes into `tests/fixtures/api/`, inside a
    vault that auto-commits every ~5 minutes, and git history has no undo. A
    key echoed back in a UTF-16 or Shift-JIS body would have passed the check
    and been committed permanently.

    ⚠ The old check could not fail on this. It planted the key as a `str` in a
    JSON body, so it only ever arrived as UTF-8 -- the one encoding that WAS
    covered. Found by the `hato/dev/scan.py` builder, whose brief said to
    "reuse the doctor's approach".
    """
    planted = FAKE_KEY.encode(codec)
    body = b'{"entries": [{"id": 1, "note": "' + planted + b'"}]}'
    cap = doctor.Capture(str(tmp_path), FAKE_KEY, _Readout())

    with pytest.raises(doctor.CaptureLeak):
        cap._write("would_leak.json", body)

    assert not list(tmp_path.iterdir()), (
        "a refused capture left %r on disk" % [p.name for p in tmp_path.iterdir()])


def test_the_capture_guard_hunts_every_codec_it_declares(tmp_path):
    """The tie between the parametrised check above and the real constant.

    ⛔ Adding a codec to `doctor.KEY_CODECS` without adding a case above makes
    this go red, which is the only thing that stops the constant and its tests
    drifting apart.
    """
    tested = {"utf-8", "utf-16-le", "utf-16-be", "cp932", "cp1252"}
    declared = set(doctor.KEY_CODECS)
    assert declared == tested, (
        "doctor.KEY_CODECS is %s but the parametrised check covers %s -- add the "
        "missing case above, do not parametrise over the constant"
        % (sorted(declared), sorted(tested)))

    needles = doctor.key_needles(FAKE_KEY)
    assert needles, "key_needles() returned nothing for a real key"
    for codec in tested:
        raw = FAKE_KEY.encode(codec)
        assert any(raw == n for n in needles), (
            "%s encoding of the key is not among the %d needle(s) searched for"
            % (codec, len(needles)))


def test_a_clean_body_is_still_written_with_the_guard_armed(tmp_path):
    """⭐ The positive control for the two checks above.

    A guard that refused EVERYTHING would pass every planted-key case. Without
    this, six green "it caught it" results say nothing about whether a capture
    can still happen at all.
    """
    cap = doctor.Capture(str(tmp_path), FAKE_KEY, _Readout())
    target = cap._write("clean.json", jbody([{"id": 1, "name": "Sousou no Frieren"}]))
    assert target.exists(), "a body with no key in it was not written"
    assert not list(tmp_path.glob("*.tmp")), "a temp file survived the rename"


class _Readout(object):
    """The two lists `Capture` appends to. Narrower than the real readout on
    purpose -- these checks are about `_write`, not about the report."""

    def __init__(self):
        self.captured = []
        self.capture_missing = []


def test_a_leak_in_the_FIRST_captured_body_fails_the_WHOLE_capture(tmp_path):
    """🚨 The check above passes for the wrong reason, and did before the fix: its
    session leaks EVERY search, so the CaptureLeak it catches is raised by the
    SECOND capture site -- the unguarded one in `_capture_traps`, five metered
    calls in. Leak only the first body, where the capture sits under
    `except Exception`, and the swallow shows: measured before the fix,
    `CaptureLeak propagated: False`, 11 further metered calls, 21 files written,
    and a second `search` line while the first still read `ok`.
    """
    s = LeaksTheFirstBodyOnly()
    with pytest.raises(doctor.CaptureLeak) as leak:
        collect(session=s, capture_dir=tmp_path)
    assert "search__query_frieren" in str(leak.value)
    assert len(s.metered) == 1, (
        "%d metered call(s) went out AFTER the key leaked: %s"
        % (len(s.metered), [c["url"] for c in s.metered]))
    assert not (tmp_path / "search__query_frieren.json").exists()
    assert not list(tmp_path.glob("entries_*")), (
        "the capture carried on past the leak: %s" % [p.name for p in tmp_path.iterdir()])
    for p in tmp_path.iterdir():
        assert FAKE_KEY.encode() not in p.read_bytes(), p.name


def test_no_generic_handler_can_swallow_a_CaptureLeak():
    """⛔ The structural half of the check above: every network site in doctor.py
    is wrapped in `except Exception`, so the leak must not BE one. A
    re-raise remembered at each `try` is a rule that gets forgotten."""
    assert not issubclass(doctor.CaptureLeak, Exception), (
        "CaptureLeak is an Exception again -- `except Exception:  # a readout "
        "reports, it does not crash` will swallow it at every capture site")
    assert issubclass(doctor.CaptureLeak, BaseException)
    try:
        raise doctor.CaptureLeak("leaked")
    except Exception:                                   # noqa: B902 - the point
        raise AssertionError("a bare `except Exception` caught a CaptureLeak")
    except doctor.CaptureLeak as exc:
        assert str(exc) == "leaked"


@pytest.mark.parametrize("remaining", ["3", "0", "-4"])
def test_no_metered_call_goes_out_once_remaining_is_at_the_floor(tmp_path, remaining):
    """🚨 The floor was asked only by the optional captures. The readout's own
    search, its file listing and the 1.39 MB empty-query catalogue dump never
    asked it, so THREE calls went out at `remaining: 0` and at -4 alike -- and
    the check that was here asserted `<= 3`, which held at every value.
    """
    plenty = FakeSession(remaining="24")
    collect(session=plenty, capture_dir=tmp_path / "plenty")

    s = FakeSession(remaining=remaining)
    ro = collect(session=s, capture_dir=tmp_path / "floor")
    assert len(plenty.metered) > 3, (
        "the control: with budget left the capture makes its calls (%d)" % len(plenty.metered))
    assert len(s.metered) == 1, (
        "kept calling at remaining=%s: %s" % (remaining, [c["url"] for c in s.metered]))
    assert ro.metered == len(s.metered)
    files = next(l for l in ro.lines if l.label == "files")
    assert files.state == doctor.SKIPPED and "x-ratelimit-remaining" in files.text, files.text
    assert any(name == "the rest" for name, _ in ro.capture_missing)
    assert ro.exit_code == 1, "a readout that answered nothing must not exit 0"


def test_the_download_refuses_a_url_that_points_at_another_host():
    """🚨 doctor took `url` from the file dict and prefixed the site only when it
    started with `/`, so a crafted host was fetched and the readout printed
    `download ok HTTP 200` -- jimaku had never heard the request. The client
    refuses the identical dict, and doctor now asks THAT guard."""
    evil = "https://evil.example/entry/11446/download/a.srt"
    s = FakeSession(overrides={"/files": lambda u, p, h: response(
        200, jbody([dict(FILES[1], url=evil)]), RATE, u)})
    ro = collect(session=s)
    dl = next(l for l in ro.lines if l.label == "download")
    assert dl.state == doctor.FAILED, "%s -- %s" % (dl.state, dl.text)
    assert "jimaku.cc" in dl.text and evil in dl.text
    assert not any("evil.example" in c["url"] for c in s.calls), (
        "the readout fetched a host jimaku named: %s" % [c["url"] for c in s.calls])
    assert ro.unmetered == 0


def test_the_download_guard_is_the_clients_own_and_not_a_second_copy():
    from hato import client as jc
    assert doctor.__doc__ and "URL GUARD" in doctor.__doc__
    assert jc.file_url is jc._file_url, "two url guards can disagree; there is one"


def test_a_request_that_never_got_an_answer_is_not_counted_as_an_api_call():
    """The client's stated policy, which doctor had backwards: it counted before
    it sent, so an attempt that never reached jimaku was reported as a metered
    call against someone's quota."""
    def refused(url, params, headers):
        raise requests.exceptions.ConnectionError("no route to host")

    s = FakeSession(overrides={"/entries/search": refused})
    ro = collect(session=s)
    assert next(l for l in ro.lines if l.label == "search").state == doctor.FAILED
    assert len(s.metered) == 2, "the control: two requests were attempted"
    assert ro.metered == 1, "counted an API call that never got an answer"
    assert "1 metered" in next(l for l in ro.lines if l.label == "api calls").text


def test_no_request_doctor_makes_ever_follows_a_redirect(tmp_path):
    """⛔ The client never follows one -- a 3xx could carry the request, and the
    readout's verdict, to another host. doctor passed nothing at all."""
    s = FakeSession()
    collect(session=s, capture_dir=tmp_path)
    assert len(s.calls) > 5
    for call in s.calls:
        assert call["kw"].get("allow_redirects") is False, (
            "%s was sent following redirects" % call["url"])


def test_the_empty_query_is_kept_as_a_count_never_the_catalogue(tmp_path):
    collect(session=FakeSession(catalogue=50), capture_dir=tmp_path)
    assert not (tmp_path / "search__query_empty.json").exists(), "the catalogue was mirrored"
    meta = json.loads((tmp_path / "search__query_empty.meta.json").read_text(encoding="utf-8"))
    assert meta["entries_returned"] == 50 and meta["body_kept"] is False


def test_the_download_is_kept_as_metadata_only(tmp_path):
    collect(session=FakeSession(), capture_dir=tmp_path)
    assert not list(tmp_path.glob("download__*.json")) or all(
        p.name.endswith(".meta.json") for p in tmp_path.glob("download__*.json"))
    meta = json.loads((tmp_path / "download__sample.meta.json").read_text(encoding="utf-8"))
    assert meta["bytes"] == len(SUB_BODY) and meta["body_kept"] is False


def test_the_429_is_recorded_as_not_provoked_with_the_reason(tmp_path):
    ro = collect(session=FakeSession(), capture_dir=tmp_path)
    reasons = dict(ro.capture_missing)
    assert "api__429" in reasons and "Whitelist 2" in reasons["api__429"]


def test_a_full_capture_costs_one_metered_call_per_metered_stem_and_stays_in_the_window(tmp_path):
    """⚠ This check used to be `len(metered) <= 3` at remaining=3 -- and three is
    what happened at EVERY value, including 0, so it could not fail. The floor
    itself is checked above; what belongs here is the price of a full capture,
    against Whitelist 2's 25 requests / 60 s."""
    s = FakeSession(remaining="24")
    ro = collect(session=s, capture_dir=tmp_path)
    metered_stems = [st for st in doctor.CAPTURE_STEMS if not st.startswith("download__")]
    assert len(s.metered) == ro.metered == len(metered_stems), (
        "%d metered calls for %d metered stems: %s"
        % (len(s.metered), len(metered_stems), [c["url"] for c in s.metered]))
    assert ro.metered < 25, "a capture must fit inside jimaku's 25 requests / 60 s window"
    assert not any(name == "the rest" for name, _ in ro.capture_missing), ro.capture_missing


def test_the_bad_key_capture_is_sent_exactly_once_and_last(tmp_path):
    s = FakeSession()
    collect(session=s, capture_dir=tmp_path)
    bad = [c for c in s.metered if c["headers"].get("Authorization") != FAKE_KEY]
    assert len(bad) == 1 and s.metered[-1] is bad[0]


# -- the command, end to end ---------------------------------------------------

def test_the_command_offline_prints_every_line_and_says_why(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "hato", "doctor"], cwd=str(tmp_path),
                          env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)
    text = proc.stdout.decode("utf-8")
    assert proc.returncode == 1, text + proc.stderr.decode("utf-8", "replace")
    body = text.splitlines()[2:]
    for label in REQUIRED:
        assert any(l.startswith("  %s" % label) for l in body), (label, text)
    for l in body:
        assert l.strip(), "a blank line inside the readout:\n%s" % text
    assert "HATO_NO_NETWORK" in text


# -- against the RECORDED capture (tests/fixtures/api/, from `hato doctor --capture`) --

FIXTURES = ROOT / "tests" / "fixtures" / "api"

#: 🚨 THE WRITTEN GAP REGISTER. Stems `hato doctor --capture` writes that
#: tests/fixtures/api/ does NOT hold, each with what would fill it. Anything not
#: named here MUST be present, and anything named here MUST be absent -- so a
#: capture added to the code without re-running the capture turns this suite red,
#: and re-running it forces this list to shrink.
#:
#: ⛔ NOTHING HERE MAY BE HAND-WRITTEN INTO A FIXTURE. A `.meta.json` under that
#: folder says "these are the bytes jimaku sent"; a plausible file built from
#: another recording would make every offline check a check on our own guess. The
#: only fix is one live `hato doctor --capture`.
NOT_YET_CAPTURED = {
    "search__query_sousou_no_frieren":
        "added to doctor by the 2b builder on 2026-09-17; `hato doctor --capture` was "
        "never re-run, so identification still cannot be driven offline from a real "
        "release-name query -- only from `query=frieren`, which no filename produces.",
    "search__no_match":
        "same builder, same un-run capture: the no-match path to the anime=false retry "
        "and the Kitsu fallback has no recorded answer, so its checks run on stand-ins "
        "derived from other recordings.",
}


def recorded(stem):
    meta = json.loads((FIXTURES / (stem + ".meta.json")).read_text(encoding="utf-8"))
    body_path = FIXTURES / (stem + ".json")
    body = body_path.read_bytes() if meta["body_kept"] else None
    return meta, body


class RecordedSession(object):
    """Serves the REAL captured bytes and response headers. A download, whose
    body is never kept, is served as filler of the recorded size and BOM."""

    ROUTES = [("/api/entries/search", "search__query_frieren"),
              ("/api/entries/11446/files", "entries_11446_files")]

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.calls.append(url)
        if "/download/" in url:
            meta, _ = recorded("download__sample")
            filler = b"\xef\xbb\xbf" + b"x" * (meta["bytes"] - 3)
            return response(meta["status"], filler, meta["response_headers"], url)
        for suffix, stem in self.ROUTES:
            if url.endswith(suffix):
                meta, body = recorded(stem)
                return response(meta["status"], body, meta["response_headers"], meta["final_url"])
        raise AssertionError("no recorded response for %s" % url)


def test_the_readout_shape_holds_against_the_recorded_capture():
    ro = collect(session=RecordedSession())
    assert [l.label for l in ro.lines] == REQUIRED
    assert ro.exit_code == 0, doctor.render(ro)
    files = json.loads((FIXTURES / "entries_11446_files.json").read_text(encoding="utf-8"))
    line = next(l for l in ro.lines if l.label == "files")
    assert "%d files" % len(files) in line.text          # derived, never pinned
    keys = sorted({k for f in files for k in f})
    assert "keys: %s" % ", ".join(keys) in line.extra
    meta, _ = recorded("search__query_frieren")
    text = doctor.render(ro)
    for name in doctor.RATE_HEADERS:
        shown = meta["response_headers"].get(name, doctor.MISSING)
        assert "%s: %s" % (name, shown) in text, name


def test_a_capture_run_writes_exactly_the_stems_the_manifest_names(tmp_path):
    """The manifest is DERIVED, not restated: a full capture is run and what it
    wrote is compared to CAPTURE_STEMS, in order. Without this the manifest is a
    second copy of the code that can drift from it -- which is the class of
    defect the check below exists to catch."""
    ro = collect(session=FakeSession(), capture_dir=tmp_path)
    stems = []
    for _, name in ro.captured:
        stem = name[:-len(".meta.json")] if name.endswith(".meta.json") else name[:-len(".json")]
        if stem not in stems:
            stems.append(stem)
    assert stems == list(doctor.CAPTURE_STEMS), (
        "the capture wrote %s\n but CAPTURE_STEMS names %s" % (stems, list(doctor.CAPTURE_STEMS)))


def test_every_stem_the_capture_writes_has_a_fixture_or_a_named_written_gap():
    """🚨 THE FIXTURES AND THE CODE HAD DRIFTED AND NOTHING SAID SO. doctor
    captures `search__query_sousou_no_frieren` and `search__no_match`; neither
    file exists, because the code was written and `hato doctor --capture` was
    never re-run. Every gap is now named, with what would fill it."""
    present = {p.name[:-len(".meta.json")] for p in FIXTURES.glob("*.meta.json")}
    assert set(NOT_YET_CAPTURED) <= set(doctor.CAPTURE_STEMS), (
        "the register names a stem nothing captures: %s"
        % sorted(set(NOT_YET_CAPTURED) - set(doctor.CAPTURE_STEMS)))
    for stem in doctor.CAPTURE_STEMS:
        if stem in NOT_YET_CAPTURED:
            assert stem not in present, (
                "%s HAS been captured now -- delete its entry from NOT_YET_CAPTURED so the "
                "gap register stays a list of real gaps" % stem)
            assert len(NOT_YET_CAPTURED[stem]) > 40, "a gap is named with its reason, or not at all"
            continue
        assert stem in present, (
            "doctor captures %s and tests/fixtures/api/ has no recording of it. Either run "
            "`hato doctor --capture` (one live run), or name the gap in NOT_YET_CAPTURED with "
            "what would fill it. ⛔ Never hand-write the fixture." % stem)
    assert present <= set(doctor.CAPTURE_STEMS), (
        "a fixture no capture writes, so nothing can ever refresh it: %s"
        % sorted(present - set(doctor.CAPTURE_STEMS)))


def test_every_fixture_has_provenance_and_its_body_matches_its_recorded_hash():
    import hashlib
    metas = sorted(FIXTURES.glob("*.meta.json"))
    assert metas, "no recorded fixtures"
    for m in metas:
        meta = json.loads(m.read_text(encoding="utf-8"))
        for field in ("captured_at", "url", "status", "response_headers", "sha256", "provenance"):
            assert meta.get(field) not in (None, ""), "%s has no %s" % (m.name, field)
        body = FIXTURES / m.name.replace(".meta.json", ".json")
        if meta["body_kept"]:
            assert hashlib.sha256(body.read_bytes()).hexdigest() == meta["sha256"], (
                "%s was edited after capture -- re-capture it, never edit it" % body.name)
        else:
            assert not body.exists(), "%s is kept although its meta says it was not" % body.name
    for body in FIXTURES.glob("*.json"):
        if not body.name.endswith(".meta.json"):
            assert (FIXTURES / body.name.replace(".json", ".meta.json")).exists(), body.name


def test_no_fixture_carries_a_request_header_or_a_subtitle_body():
    for p in FIXTURES.iterdir():
        data = p.read_bytes()
        assert b"authorization" not in data.lower(), p.name
        if p.name.startswith("download__"):
            assert p.name.endswith(".meta.json"), "a download body was kept: %s" % p.name


def test_the_recorded_traps_are_what_the_spec_says():
    """Each trap, as MEASURED live -- derived from the capture, not from prose."""
    _, default = recorded("search__live_action_anime_default")
    _, retry = recorded("search__anime_false_retry")
    assert json.loads(default) == [], "anime=true no longer gates a live-action show"
    assert len(json.loads(retry)) > 0
    empty, _ = recorded("search__query_empty")
    _, frieren = recorded("search__query_frieren")
    assert empty["entries_returned"] > 10 * len(json.loads(frieren)), (
        "an empty query no longer returns the catalogue")
    bad_key, _ = recorded("search__401_bad_key")
    assert bad_key["status"] == 401
    invalid, body = recorded("entries_invalid_id_files")
    assert invalid["status"] == 404 and "error" in json.loads(body)
    movie_search, movie_body = recorded("search__movie")
    flagged = [e for e in json.loads(movie_body) if (e.get("flags") or {}).get("movie")]
    assert flagged, "the movie fixture holds no flags.movie entry"


def test_any_tool_rarfile_can_use_counts_not_just_unrar():
    ro = collect(session=FakeSession(), which=lambda n: r"C:\tools\7z.exe" if n == "7z" else None)
    line = next(l for l in ro.lines if l.label == "unrar")
    assert line.state == doctor.OK and "7z.exe" in line.text
    missing = next(l for l in collect(session=FakeSession()).lines if l.label == "unrar")
    assert missing.state == doctor.MISSING and "bsdtar" in " ".join(missing.extra)
