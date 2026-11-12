# -*- coding: utf-8 -*-
u"""
⭐ LAYER 20 -- Chinese subtitles: assrt.net first, OpenSubtitles when it has nothing, on the
learner's own keys, and ONLY for a Chinese run (`hato/chinese.py`, RUNBOOK §LAYER 20).

⛔ ZERO NETWORK. The client is answered from `tests/fixtures/chinese/` through the real
`RecordedSession` (two REAL refusals, the rest SHAPED from each service's documented answer
-- `make_fixtures.py` says which), or, for the shapes no recording holds (a 429, a dropped
connection, a used-up day), from `_Fake` below, which never touches a socket.
"""
import io
import json
import os
from pathlib import Path

import pytest
import requests

import test_endtoend as e2e
from hato import chinese, cli, config, credentials, paths, rank, report, resolution, tokens
from hato.client import (DownloadError, DownloadNotFound, EmptyQuery, KeyRejected,
                         NetworkDisabled, RateLimited, RecordedSession, Unreachable)
from hato.commands import key as key_cmd
from hato.commands import run as run_cmd
from hato.episodes import Candidate

ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / "tests" / "fixtures" / "chinese"
#: the recordings every success needs -- never the two refusals, which share URLs
OK_STEMS = [p.name[:-len(".meta.json")] for p in sorted(ZH.glob("*.meta.json"))
            if "invalid" not in p.name and "yuru" not in p.name]


def key(service, value=u"recorded-but-checks-nothing-ab12"):
    return credentials.Key(value, u"the suite", service)


def client(stems=None, assrt=True, opensubtitles=True, **kw):
    session = RecordedSession(ZH, stems=OK_STEMS if stems is None else stems)
    made = chinese.ChineseClient(assrt=key(chinese.ASSRT) if assrt else None,
                                 opensubtitles=key(chinese.OPENSUBTITLES) if opensubtitles else None,
                                 session=session, sleep=kw.pop("sleep", lambda s: None), **kw)
    return made, session


def entry_files(c, title):
    (entry,) = c.search(title)
    return c.files(entry["id"])


# ---------------------------------------------------------------------------
# a transport for the shapes no recording holds -- never a socket
# ---------------------------------------------------------------------------

class _Resp(object):
    def __init__(self, status, body=b"{}", headers=None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})

    def iter_content(self, _n):
        yield self.content

    def close(self):
        pass


class _Fake(object):
    u"""`answers`: a list of _Resp or exceptions, served in order; every call recorded."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def _next(self, method, url, **kw):
        self.calls.append((method, url, kw))
        got = self.answers.pop(0)
        if isinstance(got, Exception):
            raise got
        return got

    def get(self, url, **kw):
        return self._next("GET", url, **kw)

    def post(self, url, **kw):
        return self._next("POST", url, **kw)


def fake(answers, monkeypatch, **keys):
    monkeypatch.delenv("HATO_NO_NETWORK", raising=False)   # _Fake has no network to refuse
    session = _Fake(answers)
    keys = keys or {"assrt": key(chinese.ASSRT), "opensubtitles": key(chinese.OPENSUBTITLES)}
    waits = []
    return chinese.ChineseClient(session=session, sleep=waits.append, **keys), session, waits


# ===========================================================================
# 1. search: the title itself, with no request
# ===========================================================================

def test_search_answers_the_title_as_one_entry_and_sends_nothing():
    c, session = client()
    (a,) = c.search(u"Sousou no Frieren")
    (b,) = c.search(u"Sousou no Frieren")
    assert a["id"] == b["id"] and type(a["id"]) is int and a["id"] > 0
    assert a["name"] == u"Sousou no Frieren"
    assert session.calls == [] and c.metered == 0, u"a search is never a request"
    assert c.search(anilist_id=154587) == []
    with pytest.raises(EmptyQuery):
        c.search(u"   ")


def test_two_titles_never_share_an_entry_id_even_when_their_hashes_clash():
    taken = {}
    first = chinese._entry_id(u"a title", taken)
    taken[first] = u"a title"
    taken_clash = {first: u"another title"}
    assert chinese._entry_id(u"a title", taken_clash) != first


# ===========================================================================
# 2. assrt.net: members of a pack, one file, and everything left out said
# ===========================================================================

def test_assrt_lists_every_member_of_a_pack_and_the_single_file_with_a_format():
    c, session = client()
    files = entry_files(c, u"Sousou no Frieren")
    names = [f["name"] for f in files]
    assert names == [u"[Nekomoe kissaten] Sousou no Frieren - 01 [WebRip 1080p].cht.ass",
                     u"[Nekomoe kissaten] Sousou no Frieren - 01 [WebRip 1080p].chs.ass",
                     u"[Nekomoe kissaten] Sousou no Frieren - 02 [WebRip 1080p].cht.ass",
                     u"[Nekomoe kissaten] Sousou no Frieren - 02 [WebRip 1080p].chs.ass",
                     u"Sousou.no.Frieren.S01E03.1080p.WEB-DL.srt"]
    assert {f["source"] for f in files} == {u"assrt"}
    assert all(f["size"] is None for f in files), u"assrt.net's `52KB` is not a byte count"
    assert c.metered == 1, u"one page of 5 uploads is one search"
    said = u" ".join(c.notes)
    assert u"1 upload not in Chinese" in said and u"1 upload marked machine-translated" in said
    assert u"2 files in a format tsubasa cannot time" in said, u"the font and the VobSub"
    assert chinese.CREDIT in c.notes, u"assrt.net asks for its credit wherever it is used"


def test_the_token_is_a_header_never_part_of_any_url():
    c, session = client()
    files = entry_files(c, u"Sousou no Frieren")
    c.download(files[1])
    secret = key(chinese.ASSRT).reveal()
    assert all(secret not in call["url"] for call in session.calls)
    api = [call for call in session.calls if "api.assrt.net" in call["url"]]
    assert api and all(call["headers"].get("Authorization") == "Bearer " + secret for call in api)
    link = [call for call in session.calls if "file0.assrt.net" in call["url"]]
    assert link and not any(h.lower() in ("authorization", "api-key")
                            for h in link[0]["headers"]), u"no key ever goes to a download"


def test_a_member_downloads_through_one_detail_answer_reused_for_its_pack():
    c, session = client()
    files = entry_files(c, u"Sousou no Frieren")
    first = c.download(files[1])
    second = c.download(files[3])
    assert u"我们出发吧".encode("utf-8") in first and u"第2集" in second.decode("utf-8")
    details = [call for call in session.calls if "/sub/detail" in call["url"]]
    assert len(details) == 1, u"one pack is one detail call, not one per member"
    assert c.unmetered == 2


def test_a_gbk_srt_comes_back_byte_for_byte_and_tsubasa_reads_it():
    from tsubasa import encoding
    c, _session = client()
    files = entry_files(c, u"Sousou no Frieren")
    body = c.download(files[4])
    assert body == (u"1\r\n00:00:01,000 --> 00:00:03,000\r\n第3集：魔法是很有趣的东西。\r\n"
                    ).encode("gbk"), u"never re-encoded"
    decoded = encoding.sniff_and_decode(body)
    assert decoded.encoding == "gb18030" and u"魔法" in decoded.text


def test_a_single_file_whose_real_name_has_another_extension_is_refused(monkeypatch):
    c, session, _w = fake([
        _Resp(200, {"status": 0, "sub": {"subs": [
            {"id": 700009, "videoname": "Show.S01E01", "subtype": "Subrip(srt)",
             "lang": {"langlist": {"langchs": True}, "desc": u"简"}}]}}),
        _Resp(200, {"status": 0, "sub": {"subs": [
            {"id": 700009, "filename": "Show.S01E01.rar",
             "url": "http://file0.assrt.net/download/700009/x.rar"}]}}),
    ], monkeypatch)
    (f,) = entry_files(c, u"Some Show")
    assert f["name"] == u"Show.S01E01.srt"
    with pytest.raises(DownloadError, match=u"not the .srt its listing said"):
        c.download(f)
    assert len(session.calls) == 2, u"refused before the file was fetched"


def test_a_download_link_off_the_service_an_archive_or_a_page_is_never_kept(monkeypatch):
    for link, body, why in (("https://evil.example/x.srt", b"1", u"not the service's own files"),
                            ("http://file0.assrt.net/x.srt", b"PK\x03\x04rest", u"an archive"),
                            ("http://file0.assrt.net/x.srt", b"<!DOCTYPE html><p>", u"HTML page")):
        c, _s, _w = fake([
            _Resp(200, {"status": 0, "sub": {"subs": [
                {"id": 700010, "videoname": "Show.S01E01", "subtype": "SRT"}]}}),
            _Resp(200, {"status": 0, "sub": {"subs": [
                {"id": 700010, "filename": "Show.S01E01.srt", "url": link}]}}),
            _Resp(200, body)], monkeypatch)
        (f,) = entry_files(c, u"Some Show")
        with pytest.raises(DownloadError, match=why):
            c.download(f)


def test_a_title_too_short_for_assrt_goes_straight_to_opensubtitles(monkeypatch):
    c, session, _w = fake([_Resp(200, {"total_pages": 0, "data": []})], monkeypatch)
    assert entry_files(c, u"龙猫") == []
    assert [call[1] for call in session.calls] == [chinese.OPENSUBTITLES_API + "/subtitles"]
    assert any(u"shorter than the 3 characters" in n for n in c.notes)


# ===========================================================================
# 3. OpenSubtitles: only when assrt.net had nothing
# ===========================================================================

def test_opensubtitles_answers_when_assrt_has_nothing_with_named_files():
    c, session = client()
    files = entry_files(c, u"Bocchi the Rock")
    assert [f["name"] for f in files] == [
        u"Bocchi.the.Rock.S01E01.1080p.WEB-DL.zh-tw.srt",
        u"Bocchi.the.Rock.S01E01.1080p.WEB-DL.zh-cn.srt",
        u"[Lilith-Raws] Bocchi the Rock S01E03.zh-cn.srt"], \
        u"its extensionless name gets its language and .srt; a name with no number gets SxxEyy"
    assert {f["source"] for f in files} == {u"opensubtitles"}
    said = u" ".join(c.notes)
    assert u"assrt.net has no Chinese file" in said
    assert u"1 file in another language" in said and u"1 file machine- or AI-translated" in said
    assert chinese.CREDIT not in c.notes, u"the credit is assrt.net's, said when it listed"
    assert c.provider_of(files[0]["name"]) == u"opensubtitles"


def test_an_opensubtitles_download_is_one_post_then_the_link_with_no_key():
    c, session = client()
    files = entry_files(c, u"Bocchi the Rock")
    body = c.download(files[1])
    assert u"我是后藤一里".encode("utf-8") in body
    post = [call for call in session.calls if call["method"] == "POST"]
    assert len(post) == 1 and post[0]["headers"].get("Api-Key") == key(chinese.OPENSUBTITLES).reveal()
    assert json.loads(post[0]["body"]) == {"file_id": 9100002, "sub_format": "srt"}
    link = session.calls[-1]
    assert link["url"].startswith("https://www.opensubtitles.com/download/")
    assert "Api-Key" not in link["headers"] and "Authorization" not in link["headers"]


def test_a_used_up_day_refuses_every_later_opensubtitles_file_without_a_request(monkeypatch):
    c, session, _w = fake([
        _Resp(200, {"total_pages": 1, "data": [
            {"attributes": {"language": "zh-cn", "files": [
                {"file_id": 1, "file_name": "Show.S01E01"}]}},
            {"attributes": {"language": "zh-cn", "files": [
                {"file_id": 2, "file_name": "Show.S01E02"}]}}]}),
        _Resp(406, {"message": "You have downloaded your allowed 5 subtitles for 24h",
                    "remaining": -1, "reset_time_utc": "2026-11-12T00:00:00.000Z"}),
    ], monkeypatch, opensubtitles=key(chinese.OPENSUBTITLES))
    first, second = entry_files(c, u"A Show")
    with pytest.raises(DownloadError, match=u"used up.*2026-11-12T00:00:00"):
        c.download(first)
    calls = len(session.calls)
    with pytest.raises(DownloadError, match=u"used up"):
        c.download(second)
    assert len(session.calls) == calls, u"the day's quota is known: nothing more was asked"


# ===========================================================================
# 4. a rejected key, a busy service, no answer
# ===========================================================================

def test_a_rejected_assrt_token_is_never_retried_and_opensubtitles_carries_on():
    stems = OK_STEMS + ["assrt__invalid_token", "opensubtitles__search_yuru_empty"]
    c, session = client(stems)
    assert entry_files(c, u"Yuru Camp") == []
    assert any(u"REJECTED the key ending …ab12" in n and u"only OpenSubtitles" in n
               for n in c.notes)
    assert entry_files(c, u"Yuru Camp") == []
    assrt = [call for call in session.calls if "assrt" in call["url"]]
    assert len(assrt) == 1, u"a rejected token is asked nothing more; OpenSubtitles carries on"
    assert len(session.calls) == 3


def test_both_keys_rejected_stops_the_run():
    stems = OK_STEMS + ["assrt__invalid_token", "opensubtitles__invalid_key"]
    c, _session = client(stems)
    with pytest.raises(KeyRejected, match=u"OpenSubtitles REJECTED"):
        entry_files(c, u"Yuru Camp")
    with pytest.raises(KeyRejected):
        entry_files(c, u"Sousou no Frieren")


def test_too_many_requests_waits_then_asks_again_and_stops_past_the_cap(monkeypatch):
    ok = _Resp(200, {"status": 0, "sub": {"subs": []}})
    busy = _Resp(429, b"{}", {"Retry-After": "7"})
    c, session, waits = fake([busy, ok, _Resp(200, {"total_pages": 0, "data": []})], monkeypatch)
    entry_files(c, u"Some Show")
    assert any(7.0 <= w < 9.0 for w in waits), waits
    quota = _Resp(509, {"status": 30900, "errmsg": "you are exceeding request limits"})
    c, session, waits = fake([quota] * 4, monkeypatch, assrt=key(chinese.ASSRT))
    with pytest.raises(RateLimited):
        entry_files(c, u"Some Show")
    assert sum(waits) <= chinese.MAX_RATE_WAIT + 10


def test_assrt_is_paced_for_its_twenty_a_minute(monkeypatch):
    page = {"status": 0, "sub": {"subs": [{"id": n, "videoname": "S.E%02d" % n,
                                           "subtype": "SRT"} for n in range(1, 16)]}}
    c, session, waits = fake([_Resp(200, page), _Resp(200, {"status": 0, "sub": {"subs": []}})],
                             monkeypatch, assrt=key(chinese.ASSRT))
    c._clock = lambda: 1000.0                   # no time passes between the two pages
    entry_files(c, u"Some Show")
    assert len(session.calls) == 2, u"a full page asks for the next"
    assert waits and min(waits) >= chinese.PACE[chinese.ASSRT][0]


def test_six_unanswered_requests_stop_the_run_and_nothing_more_is_sent(monkeypatch):
    down = requests.exceptions.ConnectionError("no route")
    c, session, waits = fake([down] * 6, monkeypatch, assrt=key(chinese.ASSRT))
    with pytest.raises(Unreachable):
        entry_files(c, u"Some Show")
    with pytest.raises(Unreachable):
        entry_files(c, u"Some Show")
    assert len(session.calls) == 6 and len(waits) == 5


def test_no_network_refuses_before_anything_is_sent(monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    c = chinese.ChineseClient(assrt=key(chinese.ASSRT), session=requests.Session())
    (e,) = c.search(u"Some Show")
    with pytest.raises(NetworkDisabled):
        c.files(e["id"])


def test_an_assrt_failure_is_never_reported_as_nothing_there(monkeypatch):
    c, _s, _w = fake([_Resp(500, {"status": 30000, "errmsg": "server is encounting errors"}),
                      _Resp(200, {"total_pages": 0, "data": []})], monkeypatch)
    with pytest.raises(chinese.SourceError, match=u"30000"):
        entry_files(c, u"Some Show")
    assert any(u"OpenSubtitles has no Chinese file" in n for n in c.notes)


def test_a_key_never_prints_whole(monkeypatch):
    k = key(chinese.ASSRT, u"0123456789abcdef0123456789abWXYZ")
    c = chinese.ChineseClient(assrt=k)
    for text in (repr(c), repr(k), u"%s" % k, u"{}".format(k)):
        assert u"0123456789abcdef" not in text and u"WXYZ" in text
    assert u"assrt.net key" in repr(k)
    with pytest.raises(TypeError):
        chinese.ChineseClient(assrt=u"a bare string")
    with pytest.raises(ValueError):
        chinese.ChineseClient()


# ===========================================================================
# 5. the keys: their own files, jimaku's rules
# ===========================================================================

def test_each_chinese_key_has_its_own_file_beside_jimakus(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.delenv("HATO_ASSRT_KEY", raising=False)
    got, where = credentials.save_key_value(u"  assrtToken0123456789abcdefXY12 \n",
                                            service=credentials.ASSRT)
    assert where == tmp_path / "data" / "assrt-key.txt" and got.hint == u"…XY12"
    text = where.read_text(encoding="utf-8")
    assert text.splitlines()[-1] == u"assrtToken0123456789abcdefXY12"
    assert u"assrt.net key, for Chinese subtitles" in text
    assert credentials.resolve_key(service=credentials.ASSRT).hint == u"…XY12"
    assert not (tmp_path / "data" / "key.txt").exists(), u"jimaku's file is never touched"
    with pytest.raises(credentials.KeyMissing, match=u"No OpenSubtitles key"):
        credentials.resolve_key(service=credentials.OPENSUBTITLES)
    monkeypatch.setenv("HATO_OPENSUBTITLES_KEY", u"osKey0000abcd")
    assert credentials.resolve_key(service=credentials.OPENSUBTITLES).source == \
        u"HATO_OPENSUBTITLES_KEY"


def test_hato_keyfile_never_answers_for_a_chinese_key(tmp_path, monkeypatch):
    u"""⛔ HATO_KEYFILE is jimaku's (and the harness's pin): a Chinese key is never read from
    it, so a check can never borrow a real token through it."""
    planted = tmp_path / "planted.txt"
    planted.write_text(u"aRealLookingToken0001\n", encoding="utf-8")
    monkeypatch.setenv("HATO_KEYFILE", str(planted))
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.delenv("HATO_ASSRT_KEY", raising=False)
    with pytest.raises(credentials.KeyMissing):
        credentials.resolve_key(service=credentials.ASSRT)
    assert credentials.resolve_key().hint == u"…0001", u"jimaku's road is unchanged"


def test_hato_key_service_set_from_stdin_shows_only_the_last_four(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.delenv("HATO_OPENSUBTITLES_KEY", raising=False)

    class _Stdin(object):
        buffer = io.BytesIO(b"osConsumerKeyABCDEFGH1234\n")
    monkeypatch.setattr("sys.stdin", _Stdin())
    assert cli.main(["key", "--service", "opensubtitles", "--set-from", "-", "--json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["hint"] == u"…1234" and u"ABCDEFGH" not in out
    assert cli.main(["key", "--service", "opensubtitles", "--show"]) == 0
    shown = capsys.readouterr().out
    assert u"OpenSubtitles key   found, ending …1234" in shown and u"ABCDEFGH" not in shown
    assert (tmp_path / "data" / "opensubtitles-key.txt").is_file()


# ===========================================================================
# 6. ranking: simplified first, and only Chinese
# ===========================================================================

@pytest.mark.parametrize("name, expected", [
    (u"[Nekomoe kissaten] Frieren - 05.chs.ass", "simplified"),
    (u"[Nekomoe kissaten] Frieren - 05.cht.ass", "traditional"),
    (u"Frieren.S01E05.WEB.zh-cn.srt", "simplified"),
    (u"Frieren.S01E05.WEB.zh-tw.srt", "traditional"),
    (u"Show - 05.简体.srt", "simplified"),
    (u"Show - 05.繁體.srt", "traditional"),
    (u"Show - 05.zh.srt", "chinese"),
    (u"[Sakurato] Frieren - 05 [简日双语].ass", "multi"),
    (u"Show - 05.chs&eng.ass", "multi"),
    (u"Show - 05.简繁.ass", "multi"),
    (u"[JPN] Show - 05.ass", "non-zh"),
    (u"Show.S01E05.eng.srt", "non-zh"),
    (u"Show - 05.srt", "unknown"),
])
def test_chinese_class(name, expected):
    assert tokens.chinese_class(name) == expected


def _cands(*names):
    return [Candidate({"name": n, "size": None}, None, u"G", None, u"range", 1.0, u"")
            for n in names]


def test_a_chinese_run_tries_simplified_first_and_never_a_japanese_only_file():
    got = rank.rank(_cands(u"G - 05.cht.ass", u"G - 05.chs.ass", u"[JPN] G - 05.ass",
                           u"G - 05 [简日双语].ass"), lang=u"zh")
    assert [r.candidate.file["name"] for r in got.ordered] == [
        u"G - 05.chs.ass", u"G - 05.cht.ass", u"G - 05 [简日双语].ass"]
    assert [c.file["name"] for c, _why in got.excluded] == [u"[JPN] G - 05.ass"]
    assert u"simplified Chinese is tried before traditional Chinese" in u" ".join(
        got.ordered[0].reasons)
    assert u"simplified Chinese" in rank.explain(got)


def test_a_japanese_run_ranks_exactly_as_before():
    got = rank.rank(_cands(u"G - 05.cht.ass", u"G - 05.ass", u"[JPN] G - 05.ass"))
    assert [r.candidate.file["name"] for r in got.ordered] == [u"[JPN] G - 05.ass", u"G - 05.ass"]
    assert [c.file["name"] for c, _w in got.excluded] == [u"G - 05.cht.ass"]
    assert got.chinese is False


# ===========================================================================
# 7. identify: a Chinese title is never cached under the shared key
# ===========================================================================

class _Cache(object):
    def __init__(self):
        self.asked = []

    def get(self, key):
        self.asked.append(("get", key))
        return resolution.Resolved(11446, u"a JAPANESE resolution", False, 1.0, False, u"jimaku")

    def put(self, key, resolved):
        self.asked.append(("put", key))


def test_a_chinese_title_never_reads_or_writes_the_resolution_cache():
    c, _s = client()
    cache = _Cache()
    ident = resolution.identify(u"Sousou no Frieren", client=c, cache=cache)
    assert cache.asked == [], u"the cached Japanese entry 11446 must never answer"
    assert ident.resolved.source == resolution.SOURCE_CHINESE
    assert ident.resolved.entry_name == u"Sousou no Frieren" and ident.calls == 0
    assert report._CHINESE_WHERE == resolution.SOURCE_CHINESE, u"the report's one word for it"


# ===========================================================================
# 8. the run, end to end, through `cli.main`
# ===========================================================================

class ZhLab(e2e.Lab):
    u"""`test_endtoend`'s laboratory with the Chinese client on recorded answers: the REAL
    downloads (no downloader seam), a stub engine, no Kitsu."""

    def install(self, monkeypatch, stems=None):
        monkeypatch.setenv("HATO_CACHE", str(self.data))
        monkeypatch.setenv("HATO_CONFIG", str(self.config))
        lab = self

        def build_world(args, lang=u"ja"):
            assert config.is_chinese(lang), u"a Japanese run must never reach this world"
            lab.client, _s = client(stems)
            lab.db = e2e.state.StateDB(lab.root / "state.db", now=lambda: e2e.NOW)
            return run_cmd.World(client=lab.client, db=lab.db,
                                 resolutions=resolution.ResolutionCache(lab.root / "res.db"),
                                 kitsu=None, cache=e2e.Cache(lab.root / "cache"),
                                 downloader=None, engine=lab.engine, reader=lab.reader)

        monkeypatch.setattr(run_cmd, "build_world", build_world)
        return self

    def json_rows(self, capsys, *extra):
        code = cli.main(self.argv("--lang", "zh", "--json", *extra))
        out = capsys.readouterr().out
        rows = [json.loads(line) for line in out.splitlines() if line.strip()]
        return code, {os.path.basename(r["video"]): r for r in rows if r.get("type") == "video"}


FRIEREN = [u"[SubsPlease] Sousou no Frieren - %02d (1080p).mkv" % n for n in (1, 2, 3, 4)]


def test_a_chinese_run_finds_assrts_files_times_them_and_names_them_zh(tmp_path, monkeypatch, capsys):
    lab = ZhLab(tmp_path, names=FRIEREN, folder=u"Frieren").install(monkeypatch)
    lab.config.write_text(u"format_fallback = true\n", encoding="utf-8")
    code, rows = lab.json_rows(capsys)
    assert code == 0
    one, two, three, four = (rows[n] for n in FRIEREN)
    assert one["outcome"] == two["outcome"] == three["outcome"] == u"CONFIDENT", rows
    assert one["output_path"].endswith(u"Sousou no Frieren - 01 (1080p).zh.ass")
    assert u".chs." in one["jimaku_filename"], u"simplified first"
    assert three["output_path"].endswith(u".zh.srt"), u"the single .srt, as .srt"
    assert four["outcome"] == u"NOT_FOUND"
    assert u"jimaku" not in four["reason"], four["reason"]
    assert four["retry_after"], u"asked again later, like any NOT_FOUND"


def test_with_the_format_fallback_off_the_srt_waits_and_the_words_name_the_sources(
        tmp_path, monkeypatch, capsys):
    lab = ZhLab(tmp_path, names=FRIEREN[2:3], folder=u"Frieren").install(monkeypatch)
    code, rows = lab.json_rows(capsys)
    (row,) = rows.values()
    assert row["outcome"] == u"NOT_FOUND"
    assert row["reason"].startswith(u"only as .srt on assrt.net or OpenSubtitles"), row["reason"]


def test_opensubtitles_fills_in_when_assrt_has_nothing(tmp_path, monkeypatch, capsys):
    names = [u"Bocchi the Rock - %02d.mkv" % n for n in (1, 2, 3)]
    lab = ZhLab(tmp_path, names=names, folder=u"Bocchi").install(monkeypatch)
    lab.config.write_text(u"format_fallback = true\n", encoding="utf-8")
    code, rows = lab.json_rows(capsys)
    one, two, three = (rows[n] for n in names)
    assert one["outcome"] == three["outcome"] == u"CONFIDENT", rows
    assert one["jimaku_filename"].endswith(u".zh-cn.srt"), u"simplified first, here too"
    assert two["outcome"] == u"NOT_FOUND", u"its only Chinese file is machine-translated"
    assert lab.client.provider_of(one["jimaku_filename"]) == u"opensubtitles"


def test_the_human_report_names_the_sources_not_a_jimaku_entry(tmp_path, monkeypatch, capsys):
    lab = ZhLab(tmp_path, names=FRIEREN[:1], folder=u"Frieren").install(monkeypatch)
    code = cli.main(lab.argv("--lang", "zh"))
    out = capsys.readouterr().out
    assert u"assrt.net / OpenSubtitles" in out and u"jimaku entry" not in out, out


def test_a_chinese_run_with_neither_key_says_how_to_get_both(tmp_path, monkeypatch, capsys):
    media = tmp_path / "Frieren"
    media.mkdir()
    (media / FRIEREN[0]).write_bytes(b"\x1aE\xdf\xa3x")
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "config.toml"))
    for env in ("HATO_ASSRT_KEY", "HATO_OPENSUBTITLES_KEY"):
        monkeypatch.delenv(env, raising=False)
    code = cli.main([str(media), "--lang", "zh"])
    err = capsys.readouterr().err
    assert code == 2, u"an unset key is the asking that was wrong (exit 2), as jimaku's"
    assert u"assrt.net" in err and u"OpenSubtitles" in err and u"--service" in err


def test_a_japanese_run_never_builds_the_chinese_client_or_reads_its_keys(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError(u"a Japanese run touched the Chinese road")
    monkeypatch.setattr(chinese, "build", refuse)
    monkeypatch.setattr(chinese, "ChineseClient", refuse)
    real = credentials.resolve_key
    monkeypatch.setattr(credentials, "resolve_key",
                        lambda start=None, service="jimaku": refuse() if service != "jimaku"
                        else real(start))
    args = type("A", (), {"fixtures": str(ROOT / "tests" / "fixtures")})()
    world = run_cmd.build_world(args)
    assert type(world.client).__name__ == u"JimakuClient" and world.kitsu is not None
    assert not config.is_chinese(u"ja") and config.is_chinese(u"zh") and config.is_chinese(u"ZHO")


def test_a_chinese_pairing_names_its_real_source_and_no_jimaku_entry(tmp_path, monkeypatch, capsys):
    u"""Surasura's hand-off: the record's `subtitle_source.provider` is the source that listed
    the file (an added VALUE of a field Connect does not read, §1), `language` is `zh`, and
    `jimaku_entry_id` is null -- a Chinese run's id is only its title's."""
    import _surasura
    drop = tmp_path / u"Surasura" / u"data" / u"zh" / u"HighPriority" / u"Hato"
    drop.parent.mkdir(parents=True)
    _surasura.install(tmp_path, monkeypatch, drop_folders={u"zh": str(drop)})
    lab = ZhLab(tmp_path, names=FRIEREN[:1], folder=u"Frieren").install(monkeypatch)
    code, rows = lab.json_rows(capsys)
    assert rows[FRIEREN[0]]["outcome"] == u"CONFIDENT", rows
    with e2e.state.StateDB(lab.root / "state.db") as db:
        (pairing,) = db.pairings(u"zh")
    record = pairing.record
    assert record["language"] == u"zh"
    assert record["subtitle_source"]["provider"] == u"assrt"
    assert record["subtitle_source"]["file_name"].endswith(u".chs.ass")
    assert record["jimaku_entry_id"] is None and record["anilist_id"] is None
    assert record["show"]["title"] == u"Sousou no Frieren"


# ===========================================================================
# 9. the words a Chinese run writes are read back
# ===========================================================================

def test_a_chinese_format_wait_is_read_back_and_an_older_one_still_is():
    from hato import formats
    mine = formats.waiting_reason([u"srt"], u"ass", 2, chinese.WHERE)
    assert mine.startswith(u"only as .srt on assrt.net or OpenSubtitles")
    assert formats.only_as(mine) == (u"srt",), u"the retry gate must see the wait end"
    older = formats.waiting_reason([u"srt", u"vtt"], u"ass", 3)
    assert older.startswith(u"only as .srt or .vtt on jimaku") and formats.only_as(older) == (
        u"srt", u"vtt"), u"1.0.3's sentence, unchanged"


def test_an_episode_with_no_chinese_file_names_the_sources_never_an_entry_number():
    from hato import pipeline
    empty = rank.Ranking(chinese=True)
    assert pipeline._unranked_reason(empty, 123456789, u"ass", chinese.WHERE) == \
        u"assrt.net or OpenSubtitles has no Chinese file for this episode"
    assert pipeline._unranked_reason(rank.Ranking(), 11446, u"ass") == \
        u"jimaku entry 11446 has no file for this episode"


def test_hanzi_tags_name_their_script():
    assert tokens.chinese_class(u"Show - 05.简体.srt") == "simplified"
    assert tokens.chinese_class(u"Show - 05.簡體.srt") == "simplified"
    assert tokens.chinese_class(u"Show - 05.繁體.srt") == "traditional"
    assert tokens.chinese_class(u"Show - 05.简英.srt") == "multi"


# ===========================================================================
# 10. the adversarial pass's findings (ADVERSARY-2026-11-11 §Layer 20), each pinned
# ===========================================================================

def test_two_uploads_with_one_name_are_both_tried(monkeypatch):
    sub = lambda n: {"id": n, "videoname": "Frieren.S01E01.1080p.WEB", "subtype": "Subrip(srt)",
                     "lang": {"langlist": {"langchs": True}, "desc": u"简"}}
    c, _s, _w = fake([_Resp(200, {"status": 0, "sub": {"subs": [sub(1), sub(2), sub(3)]}})],
                     monkeypatch, assrt=key(chinese.ASSRT))
    names = [f["name"] for f in entry_files(c, u"Sousou no Frieren")]
    assert names == [u"Frieren.S01E01.1080p.WEB.srt", u"Frieren.S01E01.1080p.WEB (2).srt",
                     u"Frieren.S01E01.1080p.WEB (3).srt"]
    got = rank.rank(_cands(*names), lang=u"zh", fallback=True)
    assert not got.excluded, u"none is dropped as a duplicate"


def test_a_title_no_source_could_search_is_an_error_never_nothing_found(monkeypatch):
    c, session, _w = fake([], monkeypatch, assrt=key(chinese.ASSRT))
    with pytest.raises(chinese.SourceError, match=u"could not be searched.*shorter than"):
        entry_files(c, u"冰菓")
    assert session.calls == []
    c, _s, _w = fake([_Resp(200, {"status": 101, "errmsg": "length of keyword must be longer "
                                                           "than 3"})],
                     monkeypatch, assrt=key(chinese.ASSRT))
    with pytest.raises(chinese.SourceError, match=u"would not search"):
        entry_files(c, u"Some Show")


def test_a_key_that_is_not_plain_ascii_is_refused_and_never_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    with pytest.raises(credentials.KeyMissing, match=u"not plain ASCII"):
        credentials.save_key_value(u"abc​def0123456789", service=credentials.ASSRT)
    monkeypatch.setenv("HATO_ASSRT_KEY", u"ｆｕｌｌｗｉｄｔｈ0123")
    with pytest.raises(credentials.KeyMissing, match=u"not plain ASCII"):
        credentials.resolve_key(service=credentials.ASSRT)
    secret = u"abc​def0123456789zz99"
    c, session, _w = fake([], monkeypatch, assrt=key(chinese.ASSRT, secret))
    with pytest.raises(chinese.SourceError) as caught:
        entry_files(c, u"Some Show")
    assert session.calls == [] and secret not in repr(caught.value)
    assert credentials.save_key_value(u"jimakuékey", destination=tmp_path / "k.txt")[0], \
        u"jimaku's validation is exactly as before"


def test_an_expired_assrt_link_is_asked_again_never_fetched_twice(monkeypatch):
    detail = lambda url: _Resp(200, {"status": 0, "sub": {"subs": [
        {"id": 700011, "filename": "Show.S01E01.srt", "url": url}]}})
    c, session, _w = fake([
        _Resp(200, {"status": 0, "sub": {"subs": [{"id": 700011, "videoname": "Show.S01E01",
                                                   "subtype": "SRT"}]}}),
        detail("http://file0.assrt.net/a/old.srt"), _Resp(404, b""),
        detail("http://file0.assrt.net/a/new.srt"), _Resp(200, b"1\r\n00:00:01,000 --> 00:00:02,000\r\nx\r\n"),
    ], monkeypatch, assrt=key(chinese.ASSRT))
    (f,) = entry_files(c, u"Some Show")
    with pytest.raises(DownloadNotFound):
        c.download(f)
    assert c.download(f).startswith(b"1")
    fetched = [call[1] for call in session.calls if "file0" in call[1]]
    assert fetched == ["http://file0.assrt.net/a/old.srt", "http://file0.assrt.net/a/new.srt"]


def test_a_refused_download_is_not_a_rejected_key(monkeypatch):
    c, session, _w = fake([
        _Resp(200, {"total_pages": 1, "data": [{"attributes": {"language": "zh-cn", "files": [
            {"file_id": 1, "file_name": "Show.S01E01"}]}}]}),
        _Resp(401, {"message": "You must be logged in to download"}),
        _Resp(200, {"total_pages": 0, "data": []}),
    ], monkeypatch, opensubtitles=key(chinese.OPENSUBTITLES))
    (f,) = entry_files(c, u"A Show")
    with pytest.raises(DownloadError, match=u"signed-in account"):
        c.download(f)
    assert entry_files(c, u"Another Show") == [], u"its searches carry on"


def test_a_later_season_is_confident_and_opensubtitles_is_asked_for_it(monkeypatch):
    c, session, _w = fake([_Resp(200, {"total_pages": 0, "data": []})], monkeypatch,
                          opensubtitles=key(chinese.OPENSUBTITLES))
    ident = resolution.identify(u"Sousou no Frieren", season=2, client=c, cache=_Cache())
    assert ident.resolved.score == 1.0 and not ident.resolved.low_confidence, ident.reason
    assert c.files(ident.resolved.entry_id) == []
    assert session.calls[0][2]["params"] == [("languages", u"zh-cn,zh-tw"),
                                             ("query", u"sousou no frieren"),
                                             ("season_number", "2")]
    (one,) = c.search(u"Sousou no Frieren", season=1)
    assert one["id"] != ident.resolved.entry_id, u"a title's seasons are different entries"


def test_a_chinese_run_never_forgets_a_japanese_runs_cached_match(tmp_path, monkeypatch, capsys):
    lab = ZhLab(tmp_path, names=FRIEREN[:1], folder=u"Frieren").install(monkeypatch)
    japanese = resolution.Resolved(11446, u"Sousou no Frieren", False, 1.0, False, u"jimaku")
    resolution.ResolutionCache(lab.root / "res.db").put(
        resolution.cache_key(u"Sousou no Frieren"), japanese)
    lab.decide = lambda base: e2e.refused()
    code, rows = lab.json_rows(capsys)
    assert rows[FRIEREN[0]]["outcome"] == u"REFUSED", rows
    kept = resolution.ResolutionCache(lab.root / "res.db").get(
        resolution.cache_key(u"Sousou no Frieren"))
    assert kept is not None and kept.entry_id == 11446


def test_a_chinese_row_says_where_it_looked_and_carries_no_jimaku_entry(tmp_path, monkeypatch, capsys):
    lab = ZhLab(tmp_path, names=FRIEREN[:1], folder=u"Frieren").install(monkeypatch)
    code, rows = lab.json_rows(capsys)
    row = rows[FRIEREN[0]]
    assert row["source"] == chinese.WHERE and row["jimaku_entry"] is None


# ===========================================================================
# 7.9 -- `hato key --show --service assrt|opensubtitles --json`, the read Surasura makes
# ===========================================================================

#: A key with no run of three characters that the answer's own words could hold.
_ZH_KEY = u"Qz7Kx9Wv3Jm5Lp8Rt2Ny"


def _never_any_of_the_key(said, key=_ZH_KEY):
    u"""No three characters of `key` in a row anywhere in `said` -- not the key, not its end."""
    parts = [key[i:i + 3] for i in range(len(key) - 2)]
    assert not [p for p in parts if p in said], (said, u"a part of the key was printed")


@pytest.mark.parametrize("service, name", [("assrt", u"assrt.net"),
                                           ("opensubtitles", u"OpenSubtitles")])
def test_7_9_key_show_json_says_only_whether_a_chinese_key_is_set_and_where(
        service, name, tmp_path, monkeypatch, capsys):
    u"""⭐ 09-hato-layer.md §7.9 (b), countersigned 2026-11-12: Surasura's Chinese card asks
    this before a press, so it can say *Set your Chinese keys in hato* instead of a run that
    waits an hour, silently, for keys that are not there. ⛔ The answer is set or not and
    where -- never the key, never its last four (the human `--show` keeps those), never the
    file's path. One JSON line, the same four fields set or not."""
    env = credentials.SERVICES[service][1]
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.delenv(env, raising=False)
    shape = {u"service": service, u"name": name, u"where": key_cmd.WHERE_TO_SET}

    # -- nothing set: not set, and where
    assert cli.main(["key", "--show", "--service", service, "--json"]) == 1
    said = capsys.readouterr().out
    assert json.loads(said) == dict(shape, set=False), said
    assert len(said.strip().splitlines()) == 1, said

    # -- saved through the window's road (stdin): set, and still nothing of the key
    class _Stdin(object):
        buffer = io.BytesIO((_ZH_KEY + u"\n").encode("ascii"))
    monkeypatch.setattr("sys.stdin", _Stdin())
    assert cli.main(["key", "--service", service, "--set-from", "-", "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["key", "--show", "--service", service, "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == dict(shape, set=True), said.out
    _never_any_of_the_key(said.out + said.err)

    # -- from the environment (a run reads it the same way): set
    (tmp_path / "data" / ("%s-key.txt" % service)).unlink()
    monkeypatch.setenv(env, _ZH_KEY)
    assert cli.main(["key", "--show", "--service", service, "--json"]) == 0
    said = capsys.readouterr().out
    assert json.loads(said)[u"set"] is True
    _never_any_of_the_key(said)


def test_7_9_a_key_hato_would_not_use_reads_as_not_set(tmp_path, monkeypatch, capsys):
    u"""What a run would refuse is not a key that is set: an empty variable, a rich-text file
    (TextEdit's default) and a pasted label all answer `set: false` -- the card then says to
    set the key, which is the one thing that helps. ⛔ And the refusal's own words, which may
    name a path, stay out of the answer."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HATO_ASSRT_KEY", u"   ")
    assert cli.main(["key", "--show", "--service", "assrt", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)[u"set"] is False
    monkeypatch.delenv("HATO_ASSRT_KEY")
    (tmp_path / "data").mkdir()
    for body in (b"{\rtf1\ansi " + _ZH_KEY.encode("ascii") + b"}\n",
                 (u"API Token: " + _ZH_KEY + u"\n").encode("utf-8")):
        (tmp_path / "data" / "assrt-key.txt").write_bytes(body)
        assert cli.main(["key", "--show", "--service", "assrt", "--json"]) == 1
        said = capsys.readouterr().out
        assert json.loads(said) == {u"service": u"assrt", u"name": u"assrt.net",
                                    u"set": False, u"where": key_cmd.WHERE_TO_SET}, said
        _never_any_of_the_key(said)


def test_7_9_a_key_hato_cannot_read_still_answers_one_line(tmp_path, monkeypatch, capsys):
    u"""⛔ ONE JSON LINE, ALWAYS: a data folder hato cannot use (a relative HATO_CACHE:
    `PathError`) and a key file the system will not let it look at (`PermissionError` from
    a stat) both answer `set: false` -- never a traceback, which would leave the card nothing
    to read."""
    monkeypatch.delenv("HATO_ASSRT_KEY", raising=False)
    monkeypatch.setenv("HATO_CACHE", u"relative-data-folder")
    assert cli.main(["key", "--show", "--service", "assrt", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)[u"set"] is False
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))

    def _refused(service=credentials.JIMAKU, start=None):
        raise PermissionError(13, "Access is denied", str(tmp_path / "data" / "assrt-key.txt"))
    monkeypatch.setattr(credentials, "resolve_key", _refused)
    assert cli.main(["key", "--show", "--service", "assrt", "--json"]) == 1
    said = capsys.readouterr()
    assert json.loads(said.out)[u"set"] is False and said.err == u"", said


def test_the_recordings_generator_still_makes_these_recordings_byte_for_byte(tmp_path):
    u"""`make_fixtures.py` now also writes six-cue bodies elsewhere (connect_e2e's Chinese
    arm). ⛔ Its default must stay THIS folder's recordings, byte for byte -- the e2e's
    recordings are only worth what they share with the ones this suite proves."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(u"hato_zh_make", str(ZH / u"make_fixtures.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(str(tmp_path))
    made = sorted(p.name for p in tmp_path.iterdir())
    assert made == sorted(p.name for p in ZH.glob(u"*.json")), made
    assert [n for n in made if (tmp_path / n).read_bytes() != (ZH / n).read_bytes()] == []
    module.main(str(tmp_path / u"six"), 6)
    six = (tmp_path / u"six" / u"assrt__file_700002.json").read_bytes().decode("gbk")
    assert six.count(u"-->") == 6 and u"(6)" in six, six


def test_7_9_the_human_show_is_unchanged_and_jimakus_json_too(tmp_path, monkeypatch, capsys):
    u"""Only the Chinese `--json` read changed: a person at a terminal still sees the last
    four (the window does too), and jimaku's `--show --json` keeps 1.0's shape."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HATO_ASSRT_KEY", _ZH_KEY)
    monkeypatch.setenv("HATO_JIMAKU_KEY", u"jimakuKeyForTheShow9876")
    assert cli.main(["key", "--show", "--service", "assrt"]) == 0
    assert u"assrt.net key   found, ending …t2Ny" in capsys.readouterr().out
    assert cli.main(["key", "--show", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        u"found": True, u"hint": u"…9876", u"source": u"HATO_JIMAKU_KEY"}
