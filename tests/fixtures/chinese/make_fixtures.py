# -*- coding: utf-8 -*-
u"""
⭐ LAYER 20 -- the recordings `tests/test_chinese.py` serves through `RecordedSession`.

    python -I tests/fixtures/chinese/make_fixtures.py     (rewrites this folder's *.json)

🚨 WHAT IS REAL AND WHAT IS SHAPED -- each recording's `provenance` says which:
- REAL: `assrt__invalid_token` and `opensubtitles__invalid_key` are the two services' own
  answers to a deliberately invalid key, recorded 2026-11-11 (status, headers, body), served
  here for the requests the client makes (neither answer depends on the query).
- SHAPED: every success. No real assrt.net token or OpenSubtitles key was available to
  this build (none may be made for it -- the learner's own), so each is built in the WIRE's
  shape (LEDGER-HOT) from the services' own records: assrt.net's API page's example answers
  (https://assrt.net/api/doc, the `sub/search` and `sub/detail` JSON, field for field) and
  OpenSubtitles' answers recorded in subliminal's test cassettes (`subtitles`, `download`:
  extensionless `file_name`, `feature_details`, `remaining`, `reset_time_utc`). The titles,
  ids and file names are this suite's own. ▶ Re-capture with a real key when one exists.
- The subtitle BODIES are this suite's own short lines -- never anyone's subtitle text.

    python -I tests/fixtures/chinese/make_fixtures.py --out DIR --cues 6

⭐ The same recordings with SIX cues a body, into DIR: tsubasa needs five cues to time a file,
so with one nothing can come back CONFIDENT. `connect_e2e`'s Chinese arm (test_20) writes
them to its scratch folder; this folder keeps its one-cue bodies (`tests/test_chinese.py`).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = "2026-11-11T21:00:00+00:00"
SHAPED = (u"SHAPED from the service's documented/recorded answer (see make_fixtures.py) -- "
          u"no real key was available; re-capture with one.")
REAL = u"REAL: the service's own answer to a deliberately invalid key, 2026-11-11."
ASSRT = "https://api.assrt.net/v1"
OS_API = "https://api.opensubtitles.com/api/v1"


#: Where `write` puts the recordings, and how many cues a body carries (`main`'s arguments).
OUT = HERE
#: Each cue's start and end, in seconds: the first is the one-cue bodies' own.
CUE_TIMES = ((1, 3), (5, 7), (9, 11), (14, 16), (19, 21), (25, 27))
CUES = 1


def write(stem, url, status, body, method="GET", post=None, headers=None, provenance=SHAPED,
          note=u""):
    data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    import hashlib
    meta = {"body_kept": True, "bytes": len(data), "captured_at": CAPTURED, "method": method,
            "sha256": hashlib.sha256(data).hexdigest(),
            "url": url, "status": status, "provenance": provenance, "note": note,
            "response_headers": headers or {"content-type": "application/json; charset=utf-8"}}
    if post is not None:
        meta["body"] = post
    with open(os.path.join(OUT, stem + ".json"), "wb") as fh:
        fh.write(data)
    with open(os.path.join(OUT, stem + ".meta.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def search_url(q, pos=0):
    from urllib.parse import urlencode
    return "%s/sub/search?%s" % (ASSRT, urlencode([("q", q), ("cnt", "15"), ("pos", str(pos)),
                                                   ("filelist", "1")]))


def _cues(line):
    u"""-> [(start s, end s, text)]: CUES of them; one cue says `line`, more number theirs."""
    return [(a, b, line if CUES == 1 else u"%s (%d)" % (line, n + 1))
            for n, (a, b) in enumerate(CUE_TIMES[:CUES])]


def ass(line):
    return (u"[Script Info]\r\nScriptType: v4.00+\r\n\r\n[Events]\r\nFormat: Layer, Start, End, "
            u"Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n" + u"".join(
                u"Dialogue: 0,0:00:%02d.00,0:00:%02d.00,Default,,0,0,0,,%s\r\n" % cue
                for cue in _cues(line))).encode("utf-8")


def srt(line, codec="utf-8"):
    return u"\r\n".join(u"%d\r\n00:00:%02d,000 --> 00:00:%02d,000\r\n%s\r\n" % ((n + 1,) + cue)
                         for n, cue in enumerate(_cues(line))).encode(codec)


FRIEREN = u"Sousou no Frieren"
PACK = [u"[Nekomoe kissaten] Sousou no Frieren - %02d [WebRip 1080p].%s.ass" % (n, s)
        for n in (1, 2) for s in (u"cht", u"chs")]
ONE = u"Sousou.no.Frieren.S01E03.1080p.WEB-DL"


def main(out=HERE, cues=1):
    global OUT, CUES
    OUT, CUES = out, cues
    if not os.path.isdir(out):
        os.makedirs(out)
    for name in os.listdir(out):
        if name.endswith(".json"):
            os.remove(os.path.join(out, name))
    # -- assrt.net: a title with a season pack, a single .srt, and four left out ----------
    lang_both = {"langlist": {"langchs": True, "langcht": True}, "desc": u"简 繁"}
    write("assrt__search_frieren", search_url(FRIEREN), 200, {"status": 0, "sub": {
        "action": "search", "keyword": FRIEREN, "result": "succeed", "subs": [
            {"id": 700001, "native_name": u"葬送的芙莉莲 第一季/Sousou no Frieren",
             "videoname": u"Sousou no Frieren S01", "revision": 0, "subtype": "ASS",
             "upload_time": "2026-10-01 20:11:00", "vote_score": 0,
             "release_site": u"喵萌奶茶屋", "lang": lang_both,
             "filelist": [{"f": f, "s": "52KB"} for f in PACK]
                         + [{"f": u"Fonts/FZLanTingHei.ttf", "s": "4MB"}]},
            {"id": 700002, "native_name": u"葬送的芙莉莲 第03集", "videoname": ONE,
             "revision": 0, "subtype": "Subrip(srt)", "upload_time": "2026-10-03 09:02:00",
             "vote_score": 0, "release_site": u"个人",
             "lang": {"langlist": {"langchs": True}, "desc": u"简"}},
            {"id": 700003, "native_name": u"장송의 프리렌", "videoname": u"Frieren.S01E04.KOR",
             "revision": 0, "subtype": "Subrip(srt)", "upload_time": "2026-10-04 10:00:00",
             "vote_score": 0, "lang": {"langlist": {"langkor": True}, "desc": u"韩"}},
            {"id": 700004, "native_name": u"葬送的芙莉莲 BD", "videoname": u"Frieren.S01E04.BD",
             "revision": 0, "subtype": "VobSub", "upload_time": "2026-10-05 10:00:00",
             "vote_score": 0, "lang": {"langlist": {"langchs": True}, "desc": u"简"}},
            {"id": 700005, "native_name": u"葬送的芙莉莲 04", "videoname": u"Frieren.S01E04.MT",
             "revision": 0, "subtype": "Subrip(srt)", "upload_time": "2026-10-06 10:00:00",
             "vote_score": 0, "vote_machine_translate": True,
             "lang": {"langlist": {"langchs": True}, "desc": u"简"}},
        ]}})
    files = "http://file0.assrt.net/onthefly/700001/-/%d/%s?_=1794000000&-=f281c84ea1a1d01280bd105e5f4a0baf&api=1"
    write("assrt__detail_700001", "%s/sub/detail?id=700001" % ASSRT, 200, {"status": 0, "sub": {
        "result": "succeed", "action": "detail", "subs": [{
            "id": 700001, "filename": u"[Nekomoe kissaten] Sousou no Frieren S01.rar",
            "url": "http://file0.assrt.net/download/700001/frieren.rar?_=1794000000&-=0a&api=1",
            "size": 20180, "subtype": "ASS", "down_count": 14, "view_count": 289,
            "upload_time": "2026-10-01 20:11:00", "lang": lang_both,
            "filelist": [{"f": f, "s": "52KB", "url": files % (i + 1, f)}
                         for i, f in enumerate(PACK)]}]}})
    for i, f in enumerate(PACK):
        n = 1 + i // 2
        line = (u"第%d集：我们出发吧，芙莉莲。" if f.endswith(u".chs.ass")
                else u"第%d集：我們出發吧，芙莉蓮。") % n
        write("assrt__file_700001_%d" % (i + 1), files % (i + 1, f), 200, ass(line),
              headers={"content-type": "application/octet-stream"})
    one = "http://file0.assrt.net/download/700002/%s.srt?_=1794000000&-=af6b&api=1" % ONE
    write("assrt__detail_700002", "%s/sub/detail?id=700002" % ASSRT, 200, {"status": 0, "sub": {
        "result": "succeed", "action": "detail", "subs": [{
            "id": 700002, "filename": ONE + u".srt", "url": one, "size": 61,
            "subtype": "Subrip(srt)", "filelist": [], "upload_time": "2026-10-03 09:02:00",
            "lang": {"langlist": {"langchs": True}, "desc": u"简"}}]}})
    # ⭐ GBK on purpose: Chinese .srt files often are, and tsubasa reads them (gb18030)
    write("assrt__file_700002", one, 200, srt(u"第3集：魔法是很有趣的东西。", "gbk"),
          headers={"content-type": "application/octet-stream"})
    # -- assrt.net: nothing for the second title ----------------------------------------
    write("assrt__search_bocchi", search_url(u"Bocchi the Rock"), 200, {"status": 0, "sub": {
        "action": "search", "keyword": u"Bocchi the Rock", "result": "succeed", "subs": []}})
    # -- OpenSubtitles: its own answer for the second title -----------------------------
    def item(sid, lang, file_id, file_name, episode, machine=False):
        return {"id": str(sid), "type": "subtitle", "attributes": {
            "subtitle_id": str(sid), "language": lang, "download_count": 120,
            "hearing_impaired": False, "hd": True, "fps": 23.976, "votes": 0, "ratings": 0.0,
            "from_trusted": False, "foreign_parts_only": False,
            "upload_date": "2026-01-05T00:46:16Z", "ai_translated": False, "nb_cd": 1,
            "machine_translated": machine, "release": file_name, "comments": "",
            "feature_details": {"feature_id": 900000 + episode, "feature_type": "Episode",
                                "year": 2022, "title": u"Episode %d" % episode,
                                "season_number": 1, "episode_number": episode,
                                "parent_title": u"Bocchi the Rock!", "parent_tmdb_id": 119100},
            "files": [{"file_id": file_id, "cd_number": 1, "file_name": file_name}]}}
    write("opensubtitles__search_bocchi",
          "%s/subtitles?languages=zh-cn,zh-tw&query=bocchi+the+rock" % OS_API, 200, {
              "total_pages": 1, "total_count": 5, "per_page": 50, "page": 1, "data": [
                  item(8100001, "zh-tw", 9100001, u"Bocchi.the.Rock.S01E01.1080p.WEB-DL", 1),
                  item(8100002, "zh-cn", 9100002, u"Bocchi.the.Rock.S01E01.1080p.WEB-DL", 1),
                  item(8100003, "zh-cn", 9100003, u"Bocchi.the.Rock.S01E02.1080p.WEB-DL", 2,
                       machine=True),
                  item(8100004, "en", 9100004, u"Bocchi.the.Rock.S01E02.1080p.WEB-DL", 2),
                  item(8100005, "zh-cn", 9100005, u"[Lilith-Raws] Bocchi the Rock", 3),
              ]})
    for file_id, ep in ((9100002, 1), (9100005, 3), (9100001, 1)):
        link = ("https://www.opensubtitles.com/download/4242795DECBF5B771DD91AA50A75%d/subfile/"
                "bocchi-%d.srt" % (file_id, ep))
        write("opensubtitles__download_%d" % file_id, OS_API + "/download", 200, {
            "link": link, "file_name": u"bocchi-%d.srt" % ep, "requests": 1, "remaining": 4,
            "message": u"Your quota will be renewed in 01 hours and 24 minutes "
                       u"(2026-11-11 23:59:59 UTC) ts=1794177337 ",
            "reset_time": u"01 hours and 24 minutes",
            "reset_time_utc": u"2026-11-11T23:59:59.000Z"},
            method="POST", post={"file_id": file_id, "sub_format": "srt"})
        write("opensubtitles__file_%d" % file_id, link, 200,
              srt(u"第%d集：我是后藤一里。" % ep if file_id != 9100001 else u"第1集：我是後藤一里。"),
              headers={"content-type": "application/x-subrip"})
    # -- the two REAL refusals ------------------------------------------------------------
    write("assrt__invalid_token", search_url(u"Yuru Camp"), 400,
          b'{"errmsg":"invalid token","status":20001}',
          headers={"content-type": "application/json"}, provenance=REAL,
          note=u"recorded for /sub/search?q=frieren; the refusal does not depend on the query")
    write("opensubtitles__invalid_key",
          "%s/subtitles?languages=zh-cn,zh-tw&query=yuru+camp" % OS_API, 403,
          b'{\n  "message":"You cannot consume this service",\n'
          b'  "request_id":"4df0334e64613d7579e71d2d1c59b471"\n}',
          headers={"content-type": "application/json; charset=utf-8",
                   "x-content-type-options": "nosniff"}, provenance=REAL,
          note=u"recorded for the same search for `frieren`; the refusal does not depend on it")
    write("opensubtitles__search_yuru_empty",
          "%s/subtitles?languages=zh-cn,zh-tw&query=yuru+camp" % OS_API, 200,
          {"total_pages": 0, "total_count": 0, "per_page": 50, "page": 1, "data": []},
          note=u"shares its URL with the invalid-key recording: a suite picks one (stems=)")
    print("wrote", len([n for n in os.listdir(out) if n.endswith(".meta.json")]), "recordings")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=HERE)
    parser.add_argument("--cues", type=int, default=1, choices=range(1, len(CUE_TIMES) + 1))
    given = parser.parse_args()
    main(given.out, given.cues)
