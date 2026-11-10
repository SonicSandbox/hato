# -*- coding: utf-8 -*-
u"""A stand-in Surasura for the suites (LAYER 16): its surasura.json in a tools folder
of the TEST's own, a command line that exists, and a library whose drop folder's
parent exists -- as Surasura 3.0 lays it out (`hato-shapes-v2.md` §1).

    drop = _surasura.install(tmp_path, monkeypatch)            # drops only
    drop = _surasura.install(tmp_path, monkeypatch, register=True)

⛔ Never the real tools folder: HOUSEKI_TOOLS_DIR is moved to `tmp_path` for the test.
"""
from __future__ import unicode_literals

import json
import os


def install(tmp_path, monkeypatch, register=False, cli=None, library=True, **fields):
    u"""-> the drop folder (`<library>/data/ja/HighPriority/Hato`), not made yet.
    `library=False` leaves its parent missing too (an offline library)."""
    tools = tmp_path / u"houseki-tools"
    tools.mkdir(exist_ok=True)
    monkeypatch.setenv("HOUSEKI_TOOLS_DIR", str(tools))
    monkeypatch.delenv("HATO_TOOLS_CLI", raising=False)
    if cli is None:
        cli = tmp_path / u"surasura-cli.cmd"
        cli.write_text(u"@echo off\r\n", encoding="utf-8")
    priority = tmp_path / u"Surasura" / u"data" / u"ja" / u"HighPriority"
    if library:
        priority.mkdir(parents=True, exist_ok=True)
    drop = priority / u"Hato"
    entry = {"schema": 1, "tool": "surasura", "name": "Surasura", "version": "2.9.0.6",
             "cli": str(cli), "app": None, "contract": 1,
             "verbs": ["status", "register"] if register else ["status"],
             "drop_folders": {"ja": str(drop)}, "updated": "2026-10-29T22:00:00Z"}
    entry.update(fields)
    (tools / u"surasura.json").write_text(json.dumps(entry, ensure_ascii=False),
                                          encoding="utf-8")
    return drop


#: A real Japanese subtitle's bytes (CRLF, as jimaku's files are).
JA = (u"1\r\n00:00:01,000 --> 00:00:03,500\r\n葬送のフリーレン\r\n\r\n"
      u"2\r\n00:00:04,000 --> 00:00:06,000\r\n魔王を倒した勇者一行の後日譚\r\n").encode("utf-8")

#: `surasura-cli register`'s answers, as Surasura 3.0 prints them (hato-shapes-v2.md §4).
ANSWERS = {
    u"registered": (0, {"type": "result", "contract": 1, "ok": True, "file_id": 4182,
                        "landed": "arrivals", "tier": "now", "position": 1,
                        "pairing": "new"}),
    u"skipped": (0, {"type": "result", "contract": 1, "ok": True, "file_id": None,
                     "landed": "skipped", "pairing": "new"}),
    u"retry": (3, {"type": "error", "contract": 1, "ok": False, "code": "busy",
                   "message": "Surasura is busy"}),
    u"stopped": (2, {"type": "error", "contract": 1, "ok": False, "code": "not-set-up",
                     "message": "ja is not set up"}),
    u"bad-data": (1, {"type": "error", "contract": 1, "ok": False, "code": "bad-data",
                      "message": "library_path is not inside the library"}),
}


class _Timed(object):
    u"""tsubasa's result for a timed pair, the fields `connect.timing_of` reads."""
    outcome = u"CONFIDENT"
    match_rate = 0.94
    offset = -1.24
    segments = (object(),)
    reference_kind = u"text track"


def kept_pair(tmp_path, episode, show=u"Sousou no Frieren"):
    u"""A video and the subtitle tsubasa wrote beside it, as a kept file is. -> (video,
    subtitle). ⚠ Each video's bytes differ, so each has its own content_key."""
    folder = tmp_path / u"Anime" / show
    folder.mkdir(parents=True, exist_ok=True)
    stem = u"[SubsPlease] %s - %02d (1080p)" % (show, episode)
    video = folder / (stem + u".mkv")
    video.write_bytes(b"\x1aE\xdf\xa3" + bytes((i * episode) % 251 for i in range(4096)))
    sub = folder / (stem + u".ja.srt")
    sub.write_bytes(JA)
    return video, sub


def seed(db, tmp_path, outcomes, show=u"Sousou no Frieren"):
    u"""Pairing rows written by the REAL producer (`connect.Handoff.keep`), one kept file
    per outcome, `register` answered as Surasura answers -- the wire's shape, never a
    row typed here. Outcomes: registered · skipped · retry · stopped · bad-data (needs
    `install(..., register=True)`), dropped (Make cards off), drop-waiting (the library
    offline), expired (a drop that waited 14 days and stopped). -> the drop folder."""
    import json as _json
    from datetime import datetime, timedelta, timezone
    from hato import connect
    link = connect.state("auto")
    if link.state not in (connect.DROPS, connect.REGISTERS):
        raise AssertionError(u"seed() needs an installed Surasura with a library: %s"
                             % (link.state,))
    now = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
    # ⚠ The expired ones first: `retry()` walks every row that waits. ⚠ 16z (Z-A5) -- the
    # stopped ones LAST: a stop on record holds every later call under this surasura.json
    order = sorted(enumerate(outcomes), key=lambda pair: (pair[1] != u"expired",
                                                          pair[1] == u"stopped"))
    for index, outcome in order:
        video, sub = kept_pair(tmp_path, index + 1, show)
        kind = {u"dropped": connect.DROPS, u"drop-waiting": connect.OFFLINE,
                u"expired": connect.OFFLINE}.get(outcome, connect.REGISTERS)
        there = connect.Link(kind, link.entry, None if kind == connect.OFFLINE
                             else link.folder, u"ja", u"auto")
        answer = ANSWERS.get(outcome)

        def call(argv, data, timeout, answer=answer):
            return answer[0], u'{"type":"progress"}\n' + _json.dumps(answer[1]) + u"\n"

        when = now - timedelta(days=20) if outcome == u"expired" else now
        handoff = connect.Handoff(db, u"auto", link=there, now=lambda w=when: w, call=call)
        handoff.keep(video=video, subtitle_path=sub, verdict=connect.TIMED, series=show,
                     timing=connect.timing_of(_Timed(), connect.TIMED),
                     show={"title": show, "season": 1, "episode": index + 1, "movie": False},
                     jimaku_entry_id=11407, anilist_id=154587, tmdb_id=u"tv:209867",
                     source_name=u"[SubsPlease] %s - %02d.srt" % (show, index + 1))
        if outcome == u"expired":
            connect.Handoff(db, u"auto", link=link, now=lambda: now, call=call).retry()
    return link.folder


def dropped(drop):
    u"""Every file under the drop folder, as paths relative to it ('/'-joined)."""
    out = []
    for folder, _dirs, files in os.walk(str(drop)):
        for name in files:
            out.append(os.path.relpath(os.path.join(folder, name), str(drop))
                       .replace(os.sep, u"/"))
    return sorted(out)
