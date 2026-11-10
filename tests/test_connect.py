# -*- coding: utf-8 -*-
u"""
Surasura Connect (RUNBOOK LAYER 16): the tools file, the effective state, hato.json.

What a wrong answer costs:
  * a state read as `registers` when Surasura is absent or too new -> hato calls a
    command line that is not there, on every kept file, for ever;
  * a hato.json written from a developer's tree, or with no `cli` when switched off
    -> Surasura's back-fill asks the wrong program, or reads "hato can't be asked"
    as "hato is gone" (A1, A7);
  * a hato.json rewritten on every run -> Surasura re-reads it for nothing; one
    written in place -> Surasura reads half a file.

Every check runs in its own tools folder (HOUSEKI_TOOLS_DIR = tmp_path): never the
real one, which on Sonic's desktop holds his real surasura.json.
"""
from __future__ import unicode_literals

import io
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hato import config, connect


@pytest.fixture
def tools(tmp_path, monkeypatch):
    folder = tmp_path / u"houseki-tools"
    folder.mkdir()
    monkeypatch.setenv(connect.TOOLS_DIR_ENV, str(folder))
    monkeypatch.delenv(connect.TOOLS_CLI_ENV, raising=False)
    return folder


def _cli(tmp_path, name=u"surasura-cli.cmd"):
    path = tmp_path / name
    path.write_text(u"@echo off\r\n", encoding="utf-8")
    return str(path)


def _surasura(tools, tmp_path, **fields):
    u"""surasura.json as Surasura 3.0 writes it (hato-shapes-v2.md §1), `fields` over it."""
    entry = {"schema": 1, "tool": "surasura", "name": "Surasura", "version": "2.9.0.6",
             "cli": _cli(tmp_path), "app": None, "contract": 1,
             "verbs": ["status", "register"],
             "drop_folders": {"ja": str(tmp_path / u"data" / u"ja" / u"HighPriority" / u"Hato")},
             "updated": "2026-10-29T22:00:00Z"}
    entry.update(fields)
    (tools / u"surasura.json").write_text(json.dumps(entry, ensure_ascii=False),
                                          encoding="utf-8")
    return entry


# -- the effective state: every row of the table ---------------------------------

def test_off_is_off_whatever_surasura_says(tools, tmp_path):
    _surasura(tools, tmp_path)
    assert connect.state("off").state == connect.OFF


@pytest.mark.parametrize("setting", ["auto", "on"])
def test_no_surasura_json_is_absent(tools, setting):
    assert connect.state(setting).state == connect.ABSENT


@pytest.mark.parametrize("setting", ["auto", "on"])
def test_a_surasura_json_whose_cli_is_gone_is_absent(tools, tmp_path, setting):
    u"""Edge 2: Surasura uninstalled leaves its file; the command line is gone."""
    entry = _surasura(tools, tmp_path)
    os.remove(entry["cli"])
    assert connect.state(setting).state == connect.ABSENT


@pytest.mark.parametrize("field", ["schema", "contract"])
def test_a_newer_schema_or_contract_is_too_new_and_hands_nothing_over(tools, tmp_path, field):
    _surasura(tools, tmp_path, **{field: 2})
    link = connect.state("auto")
    assert link.state == connect.TOO_NEW and link.folder is None


def test_no_folder_for_the_language_is_offline_not_absent(tools, tmp_path):
    u"""v2.1: a language missing from drop_folders is "no hand-off NOW" (a NAS
    library offline, a language not set up) -- never "uninstalled"."""
    _surasura(tools, tmp_path, drop_folders={})
    assert connect.state("auto").state == connect.OFFLINE
    _surasura(tools, tmp_path, drop_folders={"zh": str(tmp_path / u"zh")})
    assert connect.state("auto", "ja").state == connect.OFFLINE
    assert connect.state("auto", "zh").state == connect.REGISTERS


def test_verbs_without_register_drops_only(tools, tmp_path):
    entry = _surasura(tools, tmp_path, verbs=["status"])
    link = connect.state("auto")
    assert (link.state, link.folder) == (connect.DROPS, entry["drop_folders"]["ja"])


def test_verbs_with_register_registers(tools, tmp_path):
    entry = _surasura(tools, tmp_path)
    link = connect.state("on")
    assert (link.state, link.folder) == (connect.REGISTERS, entry["drop_folders"]["ja"])


def test_a_relative_drop_folder_is_no_folder(tools, tmp_path):
    _surasura(tools, tmp_path, drop_folders={"ja": u"data\\ja\\HighPriority\\Hato"})
    assert connect.state("auto").state == connect.OFFLINE


# -- reading the file ----------------------------------------------------------

def test_a_torn_file_is_read_again_after_50_ms(tools, tmp_path, monkeypatch):
    u"""Edge 1: Surasura mid-replace. The first read fails to parse; the second,
    50 ms later, finds the whole file."""
    good = _surasura(tools, tmp_path)
    path = tools / u"surasura.json"
    path.write_bytes(b'{"schema": 1, "tool": "sura')
    real_sleep = time.sleep

    def mend(seconds):
        path.write_text(json.dumps(good), encoding="utf-8")
        real_sleep(seconds)

    monkeypatch.setattr(connect.time, "sleep", mend)
    assert connect.read_entry().status == "present"


def test_a_file_torn_twice_is_absent_this_time(tools, tmp_path):
    _surasura(tools, tmp_path)
    (tools / u"surasura.json").write_bytes(b'{"schema": 1, "tool": "sura')
    assert connect.read_entry().status == "absent"


def test_a_file_over_4_KiB_is_absent(tools, tmp_path):
    _surasura(tools, tmp_path, name=u"S" * 5 * 1024)
    assert os.path.getsize(str(tools / u"surasura.json")) > connect.MAX_BYTES
    assert connect.read_entry().status == "absent"
    # ⚠ and one whose first 4 KiB are a whole entry, padded past the limit: the RULE
    # refuses it, not a parse error that happens to fall on the cut
    path = tools / u"surasura.json"
    path.write_bytes(path.read_bytes()[:0] + json.dumps(
        json.loads(json.dumps({"schema": 1, "tool": "surasura", "cli": _cli(tmp_path),
                               "contract": 1, "verbs": ["status"], "drop_folders": {}})))
        .encode("utf-8") + b" " * 5000)
    assert connect.read_entry().status == "absent"
    _surasura(tools, tmp_path)
    assert connect.read_entry().status == "present", u"the control: the same entry, small"


def test_a_non_object_or_a_string_schema_is_absent(tools, tmp_path):
    (tools / u"surasura.json").write_text(u"[1, 2]", encoding="utf-8")
    assert connect.read_entry().status == "absent"
    _surasura(tools, tmp_path, schema="1")
    assert connect.read_entry().status == "absent"


def test_a_non_ascii_library_path_is_read(tools, tmp_path):
    folder = str(tmp_path / u"ライブラリ" / u"ja" / u"HighPriority" / u"Hato")
    _surasura(tools, tmp_path, drop_folders={"ja": folder})
    assert connect.state("auto").folder == folder


# -- hato.json -------------------------------------------------------------------

def _hato_json(tools):
    return json.loads((tools / u"hato.json").read_text(encoding="utf-8"))


def test_from_source_hato_json_is_written_only_when_HATO_TOOLS_CLI_names_a_cli(
        tools, tmp_path, monkeypatch):
    u"""A7: a developer's tree never takes over the real entry."""
    _surasura(tools, tmp_path)
    assert connect.write_hato_json("auto") is False
    assert not (tools / u"hato.json").exists()
    cli = _cli(tmp_path, u"hato-cli.cmd")
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, cli)
    assert connect.write_hato_json("auto") is True
    entry = _hato_json(tools)
    assert (entry["cli"], entry["app"], entry["verbs"]) == (cli, None, ["pairings"])
    assert (entry["schema"], entry["contract"], entry["tool"]) == (1, 1, "hato")


def test_hato_json_is_rewritten_only_when_a_field_other_than_updated_differs(
        tools, tmp_path, monkeypatch):
    _surasura(tools, tmp_path)
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, _cli(tmp_path, u"hato-cli.cmd"))
    assert connect.write_hato_json("auto") is True
    path = str(tools / u"hato.json")
    before = os.stat(path).st_mtime_ns
    time.sleep(0.02)
    assert connect.write_hato_json("auto") is False, u"the same entry was written again"
    assert os.stat(path).st_mtime_ns == before
    assert connect.write_hato_json("off") is True, u"the control: a changed field is written"


def test_switched_off_hato_json_keeps_its_cli_with_no_verbs(tools, tmp_path, monkeypatch):
    u"""A1 (Surasura confirmed): `"verbs": []`, never deleted, and `cli` kept --
    Surasura's reader drops an entry with no `cli` (tools_entry.py:196)."""
    _surasura(tools, tmp_path)
    cli = _cli(tmp_path, u"hato-cli.cmd")
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, cli)
    connect.write_hato_json("auto")
    connect.write_hato_json("off")
    entry = _hato_json(tools)
    assert (entry["verbs"], entry["cli"]) == ([], cli)


def test_nothing_is_written_with_no_surasura_unless_the_setting_is_a_written_on(
        tools, tmp_path, monkeypatch):
    u"""P14: automatic + no Surasura = nothing; a hand-written `on` announces hato."""
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, _cli(tmp_path, u"hato-cli.cmd"))
    assert connect.write_hato_json("auto") is False
    assert connect.write_hato_json("off") is False
    assert not (tools / u"hato.json").exists()
    assert connect.write_hato_json("on") is True
    assert _hato_json(tools)["verbs"] == ["pairings"]


def test_hato_json_is_utf8_not_escaped_and_leaves_no_temp(tools, tmp_path, monkeypatch):
    _surasura(tools, tmp_path)
    folder = tmp_path / u"鳩のツール"
    folder.mkdir()
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, _cli(folder, u"hato-cli.cmd"))
    connect.write_hato_json("auto")
    data = (tools / u"hato.json").read_bytes()
    assert u"鳩のツール".encode("utf-8") in data and b"\\u" not in data
    assert sorted(os.listdir(str(tools))) == [u"hato.json", u"surasura.json"]


def test_a_crashed_writers_old_temp_is_cleared_and_a_fresh_one_kept(tools, tmp_path,
                                                                     monkeypatch):
    u"""Surasura's A2 note: hato clears its OWN leftovers after a crash."""
    _surasura(tools, tmp_path)
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, _cli(tmp_path, u"hato-cli.cmd"))
    old = tools / u"hato.json.999.1.tmp"
    fresh = tools / u"hato.json.998.1.tmp"
    theirs = tools / u"surasura.json.999.1.tmp"
    for f in (old, fresh, theirs):
        f.write_bytes(b"{")
    hour_ago = time.time() - 2 * connect.STALE_TEMP_SECONDS
    os.utime(str(old), (hour_ago, hour_ago))
    os.utime(str(theirs), (hour_ago, hour_ago))
    connect.write_hato_json("auto")
    assert not old.exists() and fresh.exists() and theirs.exists()


def test_a_replace_held_open_is_retried_then_given_up_with_nothing_left(
        tools, tmp_path, monkeypatch):
    _surasura(tools, tmp_path)
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, _cli(tmp_path, u"hato-cli.cmd"))
    calls = []

    def held(src, dst):
        calls.append(dst)
        raise PermissionError(13, "held open")

    monkeypatch.setattr(connect.os, "replace", held)
    monkeypatch.setattr(connect.time, "sleep", lambda s: None)
    assert connect.write_hato_json("auto") is False
    assert len(calls) == connect.REPLACE_TRIES
    assert sorted(os.listdir(str(tools))) == [u"surasura.json"], u"a temp was left behind"


def test_refresh_never_raises(tools, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(connect, "read_entry", boom)
    assert connect.refresh("auto").state == connect.ABSENT


# -- the shared folder's location -----------------------------------------------

def test_the_tools_folder_is_surasuras_and_the_runners_guard_watches_it(monkeypatch, tmp_path):
    u"""⭐ The tie: hato, Surasura (path_utils.tools_root) and the runner's guard
    must name ONE folder, or the guard watches a dead path and passes for ever."""
    import run_tests
    monkeypatch.delenv(connect.TOOLS_DIR_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / u"Local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / u"share"))
    got = connect.tools_dir()
    assert os.path.normcase(got) == os.path.normcase(str(run_tests.real_tools_dir()))
    if sys.platform == "win32":
        assert got == str(tmp_path / u"Local" / u"Houseki" / u"tools")
    monkeypatch.setenv(connect.TOOLS_DIR_ENV, str(tmp_path / u"elsewhere"))
    assert connect.tools_dir() == str(tmp_path / u"elsewhere")


# -- the setting ----------------------------------------------------------------

def test_automatic_is_never_written_and_off_is(tmp_path):
    cfg = config.parse(u"")
    assert cfg.surasura_connect == "auto"
    assert u"surasura_connect" not in config.dumps(cfg)
    off = config.with_changes(cfg, surasura_connect="off")
    assert u"surasura_connect = 'off'" in config.dumps(off)
    assert config.parse(u'surasura_connect = "on"\n').surasura_connect == "on"


def test_a_bad_surasura_connect_is_refused_by_name():
    with pytest.raises(config.ConfigError) as exc:
        config.parse(u'surasura_connect = "yes"\n')
    assert u"surasura_connect" in str(exc.value)


def test_go_back_to_1_0_9_takes_surasura_connect_away(tmp_path):
    u"""LEDGER-HOT: a key an older hato refuses must be taken away by Go back."""
    path = tmp_path / u"config.toml"
    path.write_text(u'surasura_connect = "off"\nsurasura_dir = "%s"\n'
                    % str(tmp_path / u"old").replace(u"\\", u"\\\\"), encoding="utf-8")
    cfg = config.load(path)
    fresh, words = config.readable_by(cfg, "1.0.9")
    assert fresh.surasura_connect == "auto" and u"surasura_connect" not in config.dumps(fresh)
    assert words and u"Surasura" in words[0]
    assert fresh.surasura_dir == str(tmp_path / u"old"), u"1.0.9's own folder is kept"
    same, none = config.readable_by(cfg, "1.1.0")
    assert same is cfg and none == []


# ===========================================================================
# 16c -- the record and the ledger · 16d -- the drop · 16e -- register
# ===========================================================================

from datetime import datetime, timedelta, timezone   # noqa: E402

import _surasura as fake                              # noqa: E402
from hato import cache, state                         # noqa: E402

JA = u"1\r\n00:00:01,000 --> 00:00:02,000\r\nこんにちは\r\n".encode("utf-8")


class _Tsubasa(object):
    u"""tsubasa's Result, in the WIRE's shape: the fields `connect.timing_of` reads."""
    outcome = u"CONFIDENT"
    match_rate = 0.91
    offset = -1.24
    segments = (object(),)
    reference_kind = u"text track"


def _pair(tmp_path, name=u"Example Show - 05", folder=u"Example Show"):
    shows = tmp_path / u"Shows" / folder
    shows.mkdir(parents=True, exist_ok=True)
    video = shows / (name + u".mkv")
    body = bytes(i % 251 for i in range(300000))
    # one video per name: the default one is the contract's 300,000-byte vector
    video.write_bytes(body if name == u"Example Show - 05" else body + name.encode("utf-8"))
    sub = shows / (name + u".ja.srt")
    sub.write_bytes(JA)
    return video, sub


@pytest.fixture
def db(tmp_path):
    with state.StateDB(tmp_path / u"state.db") as d:
        yield d


def _handoff(db, link, now=None, answers=None, calls=None):
    u"""A Handoff whose `register` is a stub: `answers` is a list of (exit, stdout)."""
    answers = list(answers or [])

    def call(argv, data, timeout):
        if calls is not None:
            calls.append((argv, data))
        return answers.pop(0)

    return connect.Handoff(db, "auto", link=link, now=now, call=call)


def _keep(h, video, sub, **more):
    fields = dict(video=video, subtitle_path=sub, verdict=connect.TIMED,
                  series=u"Example Show", timing=connect.timing_of(_Tsubasa(), "timed"),
                  show={"title": u"Example Show", "season": 1, "episode": 5, "movie": False},
                  jimaku_entry_id=11407, anilist_id=154587, tmdb_id=u"tv:209867",
                  source_name=u"[Example] Example Show 05.srt")
    fields.update(more)
    return h.keep(**fields)


def _ok(**more):
    line = {"type": "result", "contract": 1, "ok": True, "file_id": 4182,
            "landed": "arrivals", "tier": "now", "position": 1, "pairing": "new",
            "content_key": "v1-x"}
    line.update(more)
    return 0, json.dumps(line) + u"\n"


def _err(code, exit_code, **more):
    line = {"type": "error", "contract": 1, "ok": False, "code": code, "message": code}
    line.update(more)
    return exit_code, u'{"type":"progress"}\n' + json.dumps(line) + u"\n"


def _link(tmp_path, monkeypatch, register=False, library=True):
    drop = fake.install(tmp_path, monkeypatch, register=register, library=library)
    return connect.state("auto"), drop


# -- 16c: the record, field by field -------------------------------------------------

def test_a_timed_record_carries_every_field_the_shapes_file_names(tmp_path):
    video, sub = _pair(tmp_path)
    rec = connect.record(video=video, subtitle_path=sub, library_path=tmp_path / u"lib.srt",
                         verdict="timed", timing=connect.timing_of(_Tsubasa(), "timed"),
                         show={"title": u"Example Show", "season": 1, "episode": 5,
                               "movie": False},
                         jimaku_entry_id=11407, anilist_id=154587, tmdb_id=u"tv:209867",
                         paired_at=u"2026-10-14T09:31:07Z")
    assert sorted(rec) == sorted([
        "schema", "content_key", "producer", "producer_version", "language", "video_path",
        "video_size", "subtitle_path", "library_path", "subtitle_sha256", "verdict",
        "untimed_tier", "picked_by", "timing", "show", "jimaku_entry_id", "anilist_id",
        "tmdb_id", "subtitle_source", "paired_at"])
    assert rec["content_key"] == (u"v1-4b07ea24a4bef035d540cdbb9d00020d83e09245e2455baeb"
                                  u"e498315e35e1fbd")
    assert (rec["video_size"], rec["producer"], rec["language"]) == (300000, "hato", "ja")
    assert rec["subtitle_sha256"] == connect.file_sha256(sub)
    assert rec["timing"]["reference"] == "text-track" and rec["timing"]["segments"] == 1
    assert rec["timing"]["offset_s"] == -1.24 and rec["timing"]["tsubasa_version"]
    assert rec["subtitle_source"] == {"provider": "jimaku",
                                      "file_name": os.path.basename(str(sub))}


class _Result(object):
    taken_from = None
    untimed = None


@pytest.mark.parametrize("field,value,forced,want", [
    (None, None, False, ("timed", None)),
    (None, None, True, ("forced", None)),
    ("taken_from", {"track": 2, "name": u"Japanese"}, False, ("extracted", None)),
    ("untimed", {"tier": "same", "provider": u"NanakoRaws"}, False, ("untimed", "same")),
])
def test_the_verdict_comes_from_the_road_never_from_confident(field, value, forced, want):
    u"""⛔ A 14c extraction and a Layer 15 placement are CONFIDENT inside hato; neither
    was timed by tsubasa on this video -- the checks feed exactly those."""
    result = _Result()
    if field:
        setattr(result, field, value)
    assert connect.verdict_of(result, forced) == want
    timing = connect.timing_of(_Tsubasa(), want[0])
    assert (timing is None) is (want[0] in ("extracted", "untimed"))


def test_an_unknown_reference_is_omitted_never_guessed():
    t = _Tsubasa()
    t.reference_kind = u"something new"
    assert "reference" not in connect.timing_of(t, "timed")


@pytest.mark.parametrize("given,want", [
    (u"tv:261692", u"tv:261692"), (u"movie:805652", u"movie:805652"),
    (u"261692", None), (u"tv:abc", None), (7, None)])
def test_tmdb_id_only_in_jimakus_own_shape(tmp_path, given, want):
    video, sub = _pair(tmp_path)
    rec = connect.record(video=video, subtitle_path=sub, library_path=None, verdict="timed",
                         tmdb_id=given)
    assert rec["tmdb_id"] == want


def test_the_resolution_cache_keeps_tmdb_id_and_reads_a_1_0_9_file(tmp_path):
    from hato import resolution
    path = tmp_path / u"resolution.db"
    store = resolution.ResolutionCache(path)
    key = resolution.cache_key(u"frieren")
    store.put(key, resolution.Resolved(11407, u"Frieren", False, 1.0, False, "jimaku",
                                       154587, u"tv:209867"))
    assert store.get(key).tmdb_id == u"tv:209867"
    assert resolution.Resolved(1, u"x", False, 1.0, False, "jimaku", None, u"9").tmdb_id is None


def test_the_canonical_record_is_byte_identical_twice(tmp_path):
    video, sub = _pair(tmp_path)
    rec = connect.record(video=video, subtitle_path=sub, library_path=None, verdict="timed",
                         paired_at=u"2026-10-14T09:31:07Z")
    twin = dict(reversed(list(rec.items())))
    assert state.canonical(rec) == state.canonical(twin)
    text = state.canonical(dict(rec, show={"title": u"葬送のフリーレン"}))
    assert u"葬送のフリーレン" in text and chr(92) + u"u" not in text


def test_a_1_0_9_store_gains_the_tables_and_complete_since_never_moves(tmp_path):
    import sqlite3
    path = tmp_path / u"state.db"
    first = datetime(2026, 10, 30, 1, 2, 3, tzinfo=timezone.utc)
    with state.StateDB(path, now=lambda: first) as d:
        d.record_present(u"v1-abc", u"D:\\a.mkv", u"ja")
    raw = sqlite3.connect(str(path))
    raw.execute("DROP TABLE pairings")
    raw.execute("DROP TABLE meta")                    # as 1.0.9 left it
    raw.commit()
    raw.close()
    later = first + timedelta(days=3)
    with state.StateDB(path, now=lambda: later) as d:
        since = d.complete_since()
        assert since == u"2026-11-02T01:02:03Z"
        assert d.pairings() == [] and d.notes == []
    with state.StateDB(path, now=lambda: later + timedelta(days=9)) as d:
        assert d.complete_since() == since, u"complete_since moved"
    raw = sqlite3.connect(str(path))
    assert raw.execute("PRAGMA user_version").fetchone()[0] == state.SCHEMA_VERSION
    assert raw.execute("SELECT count(*) FROM present").fetchone()[0] == 1
    raw.close()


def test_clearing_hatos_memory_keeps_what_it_told_surasura(db, tmp_path):
    video, sub = _pair(tmp_path)
    db.add_pairing(connect.record(video=video, subtitle_path=sub, library_path=None,
                                  verdict="timed"), "dropped")
    since = db.complete_since()
    said = db.clear(dry_run=False)
    assert "pairings" not in said["tables"] and "meta" not in said["tables"]
    assert len(db.pairings()) == 1 and db.complete_since() == since


def test_a_pairing_row_with_an_unknown_state_is_refused(db, tmp_path):
    u"""Fork 4 changed (Sonic 2026-10-29): no `legacy` rows -- old drops get none."""
    video, sub = _pair(tmp_path)
    rec = connect.record(video=video, subtitle_path=sub, library_path=None, verdict="timed")
    with pytest.raises(ValueError):
        db.add_pairing(rec, "legacy")


# -- 16d: the drop -------------------------------------------------------------------

def test_an_existing_library_gets_the_series_folder_and_the_copy(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    h = _handoff(db, link)
    assert _keep(h, video, sub) == "dropped", h.notes
    copied = drop / u"Example Show" / sub.name
    assert copied.read_bytes() == JA
    row, = db.pairings("ja")
    assert row.record["library_path"] == str(copied) and row.state == "dropped"
    assert sorted(os.listdir(str(copied.parent))) == [sub.name], u"a temp was left behind"


def test_an_offline_library_waits_makes_no_folder_and_is_delivered_next_run(
        db, tmp_path, monkeypatch):
    u"""v2.1: the drop folder is made only when its PARENT exists. Missing, the library
    is offline: recorded with no library_path, delivered by a later run."""
    link, drop = _link(tmp_path, monkeypatch, library=False)
    video, sub = _pair(tmp_path)
    assert _keep(_handoff(db, link), video, sub) == "drop-waiting"
    assert not drop.parent.exists(), u"a folder was invented for an offline library"
    assert db.pairings()[0].record["library_path"] is None
    drop.parent.mkdir(parents=True)                   # the NAS woke up
    _handoff(db, connect.state("auto")).retry()
    row, = db.pairings("ja")
    assert row.state == "dropped" and (drop / u"Example Show" / sub.name).is_file()
    assert "_series" not in row.record


def test_a_drop_that_waits_14_days_stops_with_a_note(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, library=False)
    video, sub = _pair(tmp_path)
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    _keep(_handoff(db, link, now=lambda: start), video, sub)
    drop.parent.mkdir(parents=True)
    h = _handoff(db, connect.state("auto"), now=lambda: start + timedelta(days=14, hours=1))
    h.retry()
    assert db.pairings()[0].state == "stopped" and not drop.exists()
    assert any(u"14 days" in n for n in h.notes), h.notes
    _handoff(db, connect.state("auto"), now=lambda: start + timedelta(days=15)).retry()
    assert db.pairings()[0].state == "stopped", u"a stopped drop was tried again"


def test_a_drop_on_day_13_is_still_delivered(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, library=False)
    video, sub = _pair(tmp_path)
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    _keep(_handoff(db, link, now=lambda: start), video, sub)
    drop.parent.mkdir(parents=True)
    _handoff(db, connect.state("auto"), now=lambda: start + timedelta(days=13)).retry()
    assert db.pairings()[0].state == "dropped"


def test_the_path_budget_cuts_the_series_with_a_hash_and_refuses_what_cannot_fit():
    folder = u"C:\\Users\\Ana\\Surasura\\data\\ja\\HighPriority\\Hato"
    name = u"Example Show - 05.ja.srt"
    series = u"S" * 300
    target = connect.drop_target(folder, series, name, limit=259)
    assert len(target) <= 259 and u"~" in os.path.basename(os.path.dirname(target))
    assert len(os.path.basename(os.path.dirname(target))) >= connect.SERIES_MIN
    other = connect.drop_target(folder, u"S" * 299 + u"T", name, limit=259)
    assert target != other, u"two long series cut to one folder"
    assert connect.drop_target(folder, series, u"n" * 230 + u".ja.srt", limit=259) is None
    assert connect.drop_target(folder, u"Short", name, limit=259) == os.path.join(
        folder, u"Short", name)


def test_a_target_that_cannot_fit_is_a_note_and_no_file(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path, name=u"E" * 200)
    monkeypatch.setattr(connect, "_long_paths", lambda: False)
    h = _handoff(db, link)
    assert _keep(h, video, sub) is None
    assert any(u"too long for Windows" in n for n in h.notes) and not drop.exists()


def test_another_videos_file_of_the_same_name_is_never_overwritten(db, tmp_path, monkeypatch):
    u"""Edge 8: two videos named alike in two folders of one show."""
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    _keep(_handoff(db, link), video, sub)
    video2, sub2 = _pair(tmp_path, folder=u"Example Show (BD)")
    video2.write_bytes(b"another rip" * 100)
    sub2.write_bytes(JA + b"2")
    assert _keep(_handoff(db, link), video2, sub2) == "dropped"
    tag = cache.video_hash(video2).split("-")[1][:6]
    assert (drop / u"Example Show" / sub.name).read_bytes() == JA
    assert (drop / u"Example Show" / (u"Example Show - 05 [%s].ja.srt" % tag)
            ).read_bytes() == JA + b"2"


def test_a_file_hato_never_recorded_is_never_overwritten(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    theirs = drop / u"Example Show" / sub.name
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(b"a person's own file")
    _keep(_handoff(db, link), video, sub)
    assert theirs.read_bytes() == b"a person's own file"
    assert len(fake.dropped(drop)) == 2


def test_a_re_sync_replaces_this_videos_own_earlier_drop(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    _keep(_handoff(db, link), video, sub)
    sub.write_bytes(JA + b"better")
    _keep(_handoff(db, link), video, sub, show=None, jimaku_entry_id=None, anilist_id=None,
          tmdb_id=None)
    assert fake.dropped(drop) == [u"Example Show/" + sub.name]
    assert (drop / u"Example Show" / sub.name).read_bytes() == JA + b"better"
    rec = db.pairings("ja")[0].record
    assert (rec["show"]["title"], rec["jimaku_entry_id"], rec["tmdb_id"]) == (
        u"Example Show", 11407, u"tv:209867"), u"A6: a re-sync's show from its latest pairing"


def test_the_drop_temp_never_ends_in_a_subtitle_ending_and_an_old_one_is_cleared(
        db, tmp_path, monkeypatch):
    u"""A2 (Surasura confirmed): its scans take .txt .md .srt .ass .ssa -- the temp ends
    `.tmp`. And a crashed copy's temp, an hour old, is cleared on the next copy."""
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    folder = drop / u"Example Show"
    folder.mkdir(parents=True)
    old = folder / u".hato-99999.tmp"
    old.write_bytes(b"half")
    hour_ago = time.time() - 2 * connect.STALE_TEMP_SECONDS
    os.utime(str(old), (hour_ago, hour_ago))
    seen = []
    real_replace = os.replace

    def watch(src, dst):
        seen.append(os.path.basename(src))
        return real_replace(src, dst)

    monkeypatch.setattr(connect.os, "replace", watch)
    _keep(_handoff(db, link), video, sub)
    assert seen == [u".hato-%d.tmp" % os.getpid()], seen
    assert not old.exists()


def test_nothing_is_written_outside_the_drop_folder(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    library = drop.parent.parent.parent

    def tree():
        return sorted(os.path.relpath(os.path.join(f, n), str(library))
                      for f, _d, names in os.walk(str(library)) for n in names)

    before = tree()
    _keep(_handoff(db, link), video, sub)
    added = sorted(set(tree()) - set(before))
    assert added == [os.path.join(u"ja", u"HighPriority", u"Hato", u"Example Show", sub.name)]


def test_off_absent_and_too_new_hand_nothing_over_and_record_nothing(db, tmp_path):
    video, sub = _pair(tmp_path)
    for link in (connect.Link(connect.OFF, None, None, "ja", "off"),
                 connect.Link(connect.ABSENT, None, None, "ja", "auto"),
                 connect.Link(connect.TOO_NEW, {}, None, "ja", "auto")):
        h = _handoff(db, link)
        assert _keep(h, video, sub) is None
        assert h.notes == [], u"a hand-off was attempted: %s" % h.notes
    assert db.pairings() == []


# -- 16e: register -------------------------------------------------------------------

def test_the_record_goes_on_stdin_and_never_on_argv(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, register=True)
    video, sub = _pair(tmp_path)
    calls = []
    assert _keep(_handoff(db, link, answers=[_ok()], calls=calls), video, sub) == "registered"
    (argv, data), = calls
    assert argv[1:] == ["register", "--lang", "ja", "--pairing", "-", "--wait", "10"]
    rec = json.loads(data.decode("utf-8"))
    assert rec["library_path"] == str(drop / u"Example Show" / sub.name)
    row, = db.pairings("ja")
    assert (row.state, row.file_id) == ("registered", 4182) and row.registered_at


@pytest.mark.parametrize("answer,want", [
    (_ok(pairing="same", landed="already"), "registered"),
    (_ok(pairing="replaced", landed="already"), "registered"),
    (_ok(file_id=None, landed="skipped", pairing=None, skipped="connect preview off"),
     "skipped"),
    (_err("bad-data", 1), "bad-data"),
    (_err("failed", 1), "retry"),
    (_err("usage", 2), "stopped"),
    (_err("not-set-up", 2), "stopped"),
    (_err("version-skew", 2), "stopped"),
    (_err("busy", 3), "retry"),
    (_err("update-staged", 3), "retry"),
    (_err("settings-unreadable", 3), "retry"),
    (_err("needs-you", 4), "retry"),
    ((9, u"Traceback (most recent call last):"), "retry"),
    ((0, u"not json at all"), "retry"),
])
def test_every_row_of_the_exit_table(db, tmp_path, monkeypatch, answer, want):
    link, drop = _link(tmp_path, monkeypatch, register=True)
    video, sub = _pair(tmp_path)
    assert _keep(_handoff(db, link, answers=[answer]), video, sub) == want
    assert db.pairings("ja")[0].state == want


def test_already_with_a_new_pairing_is_a_success_on_a_first_drop(db, tmp_path, monkeypatch):
    u"""v2.1: Surasura's folder scan can find the file first -- `already` + `new`."""
    link, drop = _link(tmp_path, monkeypatch, register=True)
    video, sub = _pair(tmp_path)
    _keep(_handoff(db, link, answers=[_ok(landed="already", pairing="new", file_id=77)]),
          video, sub)
    row = db.pairings()[0]
    assert (row.state, row.file_id) == ("registered", 77)


def test_after_the_first_exit_2_3_or_4_the_run_makes_no_more_calls(db, tmp_path, monkeypatch):
    u"""A4: one try per pairing per run; the first stop holds the rest to the next run."""
    link, drop = _link(tmp_path, monkeypatch, register=True)
    calls = []
    h = _handoff(db, link, answers=[_err("busy", 3)], calls=calls)
    for n in (1, 2, 3):
        video, sub = _pair(tmp_path, name=u"Example Show - 0%d" % n)
        _keep(h, video, sub)
    assert len(calls) == 1
    assert [p.state for p in db.pairings("ja")] == ["retry", "retry", "retry"]
    h.retry()
    assert len(calls) == 1, u"the run retried in a loop"
    calls2 = []
    _handoff(db, link, answers=[_ok(), _ok(), _ok()], calls=calls2).retry()
    assert len(calls2) == 3 and [p.state for p in db.pairings("ja")] == ["registered"] * 3


def test_bad_data_waits_until_the_file_changes(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, register=True)
    video, sub = _pair(tmp_path)
    _keep(_handoff(db, link, answers=[_err("bad-data", 1)]), video, sub)
    calls = []
    _handoff(db, link, answers=[_ok()], calls=calls).retry()
    assert calls == [], u"bad-data was retried with the same file"
    (drop / u"Example Show" / sub.name).write_bytes(JA + b"fixed")
    _handoff(db, link, answers=[_ok()], calls=calls).retry()
    assert len(calls) == 1


def test_exit_2_waits_for_a_new_updated_and_update_staged_for_a_new_version(
        db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, register=True)
    cli = link.entry["cli"]
    video, sub = _pair(tmp_path)
    _keep(_handoff(db, link, answers=[_err("not-set-up", 2)]), video, sub)
    calls = []
    _handoff(db, connect.state("auto"), answers=[_ok()], calls=calls).retry()
    assert calls == []
    fake.install(tmp_path, monkeypatch, register=True, cli=cli,
                      updated="2026-10-30T08:00:00Z")
    _handoff(db, connect.state("auto"), answers=[_err("update-staged", 3)],
             calls=calls).retry()
    assert len(calls) == 1 and db.pairings()[0].gate == "2.9.0.6"
    _handoff(db, connect.state("auto"), answers=[_ok()], calls=calls).retry()
    assert len(calls) == 1, u"retried before the version changed"
    fake.install(tmp_path, monkeypatch, register=True, cli=cli, version="2.9.0.7")
    _handoff(db, connect.state("auto"), answers=[_ok()], calls=calls).retry()
    assert len(calls) == 2 and db.pairings()[0].state == "registered"


def test_drops_only_never_registers_later(db, tmp_path, monkeypatch):
    u"""Make cards off in Surasura: the back-fill registers it, never hato -- neither a
    file dropped then, nor one waiting to retry when Make cards was switched off."""
    link, drop = _link(tmp_path, monkeypatch)
    video, sub = _pair(tmp_path)
    calls = []
    _keep(_handoff(db, link, calls=calls), video, sub)
    fake.install(tmp_path, monkeypatch, register=True, cli=link.entry["cli"])
    _handoff(db, connect.state("auto"), answers=[_ok()], calls=calls).retry()
    assert calls == [] and db.pairings()[0].state == "dropped"
    video2, sub2 = _pair(tmp_path, name=u"Example Show - 06")
    _keep(_handoff(db, connect.state("auto"), answers=[_err("busy", 3)], calls=calls),
          video2, sub2)
    assert len(calls) == 1
    fake.install(tmp_path, monkeypatch, register=False, cli=link.entry["cli"])
    _handoff(db, connect.state("auto"), answers=[_ok()], calls=calls).retry()
    assert len(calls) == 1, u"a retry was registered while Make cards is off"


def test_a_crashing_register_is_a_retry_and_a_note_never_an_error(db, tmp_path, monkeypatch):
    link, drop = _link(tmp_path, monkeypatch, register=True)
    video, sub = _pair(tmp_path)

    def boom(argv, data, timeout):
        raise OSError("the command line vanished")

    h = connect.Handoff(db, "auto", link=link, call=boom)
    assert _keep(h, video, sub) == "retry" and h.notes


def test_the_real_call_runs_with_no_window_and_reads_stdout_to_its_end(tmp_path):
    u"""`_call_register` itself, against a real child: the record arrives on stdin and
    the answer is stdout's last JSON line."""
    script = tmp_path / u"cli.py"
    script.write_text(
        u"import sys, json\n"
        u"rec = json.loads(sys.stdin.buffer.read().decode('utf-8'))\n"
        u"print(json.dumps({'type': 'progress'}))\n"
        u"print(json.dumps({'type': 'result', 'ok': True, 'echo': rec['k'],"
        u" 'argv': sys.argv[1:]}))\n", encoding="utf-8")
    code, out = connect._call_register([sys.executable, str(script), "register"],
                                       json.dumps({"k": u"鳩"}).encode("utf-8"), 30)
    answer = connect._last_json(out)
    assert code == 0 and answer["echo"] == u"鳩" and answer["argv"] == ["register"]


# -- 16f: hato-cli pairings --json ----------------------------------------------------

def _pairings_cli(data_root, *args):
    u"""The REAL entry point, as Surasura's back-fill starts it: stdin closed."""
    import subprocess
    env = dict(os.environ, HATO_CACHE=str(data_root))
    proc = subprocess.run([sys.executable, "-m", "hato", "pairings"] + list(args),
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=120)
    lines = [json.loads(l) for l in proc.stdout.decode("ascii").splitlines() if l.strip()]
    return proc.returncode, lines, proc.stdout


def _ledger(tmp_path, monkeypatch, register=True):
    u"""A store in `tmp/data` holding: ep5 registered, ep6 dropped, ep7 waiting."""
    data = tmp_path / u"data"
    data.mkdir()
    link, drop = _link(tmp_path, monkeypatch, register=register)
    with state.StateDB(data / u"state.db") as d:
        v5, s5 = _pair(tmp_path, name=u"Example Show - 05")
        _keep(_handoff(d, link, answers=[_ok(file_id=4182)]), v5, s5,
              show={"title": u"葬送のフリーレン", "season": 2, "episode": 5, "movie": False})
        v6, s6 = _pair(tmp_path, name=u"Example Show - 06")
        _keep(_handoff(d, link, answers=[_err("busy", 3)]), v6, s6)
        v7, s7 = _pair(tmp_path, name=u"Example Show - 07")
        offline = connect.Link(connect.OFFLINE, link.entry, None, "ja", "auto")
        _keep(_handoff(d, offline), v7, s7)
    return data, drop


def test_pairings_prints_every_record_field_then_the_result_line(tmp_path, monkeypatch):
    data, drop = _ledger(tmp_path, monkeypatch)
    code, lines, raw = _pairings_cli(data, "--json", "--lang", "ja")
    assert code == 0, raw
    *pairs, result = lines
    assert [p["type"] for p in pairs] == ["pairing", "pairing"], u"a waiting drop was emitted"
    assert result == {"type": "result", "ok": True, "count": 2,
                      "complete_since": result["complete_since"]}
    assert result["complete_since"] and result["complete_since"].endswith("Z")
    five, six = pairs
    assert sorted(five) == sorted(["type", "schema", "content_key", "producer",
        "producer_version", "language", "video_path", "video_size", "subtitle_path",
        "library_path", "subtitle_sha256", "verdict", "untimed_tier", "picked_by", "timing",
        "show", "jimaku_entry_id", "anilist_id", "tmdb_id", "subtitle_source", "paired_at",
        "registered"])
    assert five["registered"]["file_id"] == 4182 and five["registered"]["at"].endswith("Z")
    assert six["registered"] is None
    assert raw.isascii(), u"a frozen child's stdout encoding is not ours to trust"
    assert five["show"]["title"] == u"葬送のフリーレン", u"the escaping lost the title"


def test_pairings_answers_one_line_per_video_the_latest(tmp_path, monkeypatch):
    data, drop = _ledger(tmp_path, monkeypatch)
    with state.StateDB(data / u"state.db") as d:
        row = d.pairings("ja")[0]
        newer = dict(row.record, verdict="untimed", untimed_tier="same", timing=None)
        d.add_pairing(newer, "dropped")
    code, lines, raw = _pairings_cli(data, "--json")
    pairs = [l for l in lines if l["type"] == "pairing"]
    assert len(pairs) == 2
    mine = [p for p in pairs if p["content_key"] == row.content_key][0]
    assert mine["verdict"] == "untimed"
    assert mine["registered"]["file_id"] == 4182, u"the registration was lost to a newer row"


def test_pairings_since_filters_and_a_bad_since_or_no_json_is_usage(tmp_path, monkeypatch):
    data, drop = _ledger(tmp_path, monkeypatch)
    code, lines, raw = _pairings_cli(data, "--json", "--since", "2999-01-01T00:00:00Z")
    assert code == 0 and lines == [{"type": "result", "ok": True, "count": 0,
                                    "complete_since": lines[-1]["complete_since"]}]
    code, lines, raw = _pairings_cli(data, "--json", "--since", "2000-01-01T00:00:00Z")
    assert lines[-1]["count"] == 2
    assert _pairings_cli(data, "--json", "--since", "yesterday")[0] == 2
    assert _pairings_cli(data)[0] == 2


def test_pairings_on_a_store_no_1_1_0_opened_is_empty_and_an_unreadable_one_exits_1(tmp_path):
    empty = tmp_path / u"never"
    empty.mkdir()
    code, lines, raw = _pairings_cli(empty, "--json")
    assert (code, lines) == (0, [{"type": "result", "ok": True, "count": 0,
                                  "complete_since": None}])
    import sqlite3
    old = tmp_path / u"old"                          # a store only 1.0.9 has opened
    old.mkdir()
    with state.StateDB(old / u"state.db"):
        pass
    raw = sqlite3.connect(str(old / u"state.db"))
    raw.execute("DROP TABLE pairings")
    raw.execute("DROP TABLE meta")
    raw.commit()
    raw.close()
    before = (old / u"state.db").read_bytes()
    code, lines, raw_out = _pairings_cli(old, "--json")
    assert (code, lines[-1]["count"], lines[-1]["complete_since"]) == (0, 0, None)
    assert (old / u"state.db").read_bytes() == before, u"a read-only command added tables"
    broken = tmp_path / u"broken"
    broken.mkdir()
    (broken / u"state.db").write_bytes(b"this is not a database" * 100)
    code, lines, raw = _pairings_cli(broken, "--json")
    assert code == 1 and lines[-1]["ok"] is False
    assert (broken / u"state.db").read_bytes() == b"this is not a database" * 100, (
        u"a read-only command moved or repaired the store")


def test_pairings_takes_no_lock_writes_nothing_and_answers_beside_a_writer(tmp_path,
                                                                           monkeypatch):
    u"""⛔ A run in progress never makes Surasura's 60-second wait: the run lock held and
    a write transaction open, `pairings` still answers -- and leaves the store as it was."""
    import sqlite3
    from hato import runlock
    data, drop = _ledger(tmp_path, monkeypatch)
    db_file = data / u"state.db"
    before = {n: os.stat(str(data / n)).st_mtime_ns for n in os.listdir(str(data))}
    writer = sqlite3.connect(str(db_file), timeout=1)
    writer.execute("BEGIN IMMEDIATE")
    try:
        monkeypatch.setenv("HATO_CACHE", str(data))
        held = runlock.RunLock()                      # the real run's lock, on this store
        held.acquire()
        assert held.held and runlock.run_in_flight()
        try:
            started = time.time()
            code, lines, raw = _pairings_cli(data, "--json")
            assert code == 0 and lines[-1]["count"] == 2, raw
            assert time.time() - started < 30
        finally:
            held.release()
    finally:
        writer.execute("ROLLBACK")
        writer.close()
    after = {n: os.stat(str(data / n)).st_mtime_ns for n in os.listdir(str(data))}
    assert {n: after.get(n) for n in before if n.endswith(".db")} == \
        {n: before[n] for n in before if n.endswith(".db")}


def test_pairings_reads_1000_rows_within_a_second(tmp_path, monkeypatch):
    data = tmp_path / u"data"
    data.mkdir()
    video, sub = _pair(tmp_path)
    base = connect.record(video=video, subtitle_path=sub, library_path=tmp_path / u"l.srt",
                          verdict="timed")
    with state.StateDB(data / u"state.db") as d:
        for n in range(1000):
            d.add_pairing(dict(base, content_key=u"v1-%064x" % n), "dropped")
    from hato.commands import pairings as cmd
    import argparse
    import io as _io
    sink = _io.BytesIO()

    class _Out(object):
        buffer = sink

        @staticmethod
        def flush():
            pass

    monkeypatch.setenv("HATO_CACHE", str(data))
    monkeypatch.setattr(cmd.sys, "stdout", _Out())
    started = time.time()
    assert cmd.run(argparse.Namespace(json=True, lang="ja", since=None)) == 0
    took = time.time() - started
    assert sink.getvalue().count(b"\n") == 1001
    assert took <= 1.0, u"1,000 pairings took %.2f s" % took


def test_pairings_reaches_the_frozen_build_through_the_command_table():
    from hato import cli
    assert cli.COMMANDS["pairings"] == "hato.commands.pairings"


# -- 16g: the counts the window's card and the tray's line are drawn from -------------

def test_pairing_counts_are_the_latest_row_per_video_and_expired_apart(tmp_path, monkeypatch):
    u"""`state.pairing_counts`, the ONE accessor both read: the latest row per video
    decides (append-only: a retried video has two rows), and a drop that gave up after
    14 days is EXPIRED, never `stopped` -- it never reached the library, and nothing
    Surasura changes brings it back. Rows from the real producer (`_surasura.seed`)."""
    fake.install(tmp_path, monkeypatch, register=True)
    path = tmp_path / u"state.db"
    with state.StateDB(path) as d:
        fake.seed(d, tmp_path, [u"registered", u"retry", u"retry", u"stopped", u"expired",
                                u"drop-waiting", u"dropped", u"bad-data", u"skipped"])
        # a later run hands one retry over: its latest row is `registered` now
        first = d.pairings(u"ja", states=(u"retry",))[0]
        d.add_pairing(dict(first.record), u"registered", file_id=7,
                      registered_at=u"2026-10-30T10:00:00Z", last_code=u"new")
    counts = state.pairing_counts(path, u"ja")
    assert counts == {u"registered": 2, u"retry": 1, u"stopped": 1, state.EXPIRED: 1,
                      u"drop-waiting": 1, u"dropped": 1, u"bad-data": 1, u"skipped": 1}, counts
    assert state.pairing_counts(path, u"zh") == dict.fromkeys(counts, 0)


def test_pairing_counts_read_a_1_0_9_store_and_no_store_without_writing(tmp_path):
    u"""⛔ READ-ONLY, as `read_pairings`: a store no 1.1.0 has opened counts nothing and
    is byte-identical after (no table added -- Go back's 1.0.9 reads it); no file counts
    nothing and makes none."""
    import sqlite3
    path = tmp_path / u"state.db"
    with state.StateDB(path) as d:
        d.record_present(u"v1-abc", u"D:\a.mkv", u"ja")
    raw = sqlite3.connect(str(path))
    raw.execute("DROP TABLE pairings")
    raw.execute("DROP TABLE meta")                    # as 1.0.9 left it
    raw.commit()
    raw.close()
    before = path.read_bytes()
    assert set(state.pairing_counts(path).values()) == {0}
    assert path.read_bytes() == before, u"counting changed a 1.0.9 store"
    missing = tmp_path / u"none" / u"state.db"
    assert set(state.pairing_counts(missing).values()) == {0}
    assert not missing.parent.exists()


def test_status_never_raises_and_an_unreadable_store_counts_nothing(tmp_path, monkeypatch):
    u"""`connect.status`: Connect is never why the window or the tray stops. A store that
    is not a database reads as no counts ({}), the state still read."""
    fake.install(tmp_path, monkeypatch, register=True)
    bad = tmp_path / u"state.db"
    bad.write_bytes(b"this is not a database at all" * 100)
    found = connect.status(u"auto", db_path=bad)
    assert found.link.state == connect.REGISTERS and found.counts == {} and found.reachable


def test_library_there_is_the_one_test_the_drop_and_the_card_ask(tmp_path):
    u"""v2.1: the drop folder's PARENT decides (`…\\HighPriority`); the folder itself may
    not exist yet. None or an empty name is no library."""
    priority = tmp_path / u"data" / u"ja" / u"HighPriority"
    assert not connect.library_there(str(priority / u"Hato"))
    priority.mkdir(parents=True)
    assert connect.library_there(str(priority / u"Hato"))
    assert not connect.library_there(None) and not connect.library_there(u"")


def test_watched_moves_with_surasura_json_and_the_librarys_reach(tmp_path, monkeypatch):
    u"""The `stat`s the window and the tray look at every tick: surasura.json written,
    rewritten or removed, and its library going out of reach, each move it."""
    drop = fake.install(tmp_path, monkeypatch, register=True)
    found = connect.status(u"auto")
    first = connect.watched(found)
    assert connect.watched(found) == first, u"nothing moved"
    import shutil
    shutil.rmtree(str(drop.parent))                   # HighPriority gone: a NAS asleep
    assert connect.watched(found) != first
    os.remove(os.path.join(connect.tools_dir(), u"surasura.json"))
    assert connect.watched(found)[0] is None


# ===========================================================================
# 16z -- the Opus adversary's rows (ADVERSARY-2026-10-31, Z-A1 … Z-A5)
# ===========================================================================

@pytest.mark.parametrize("answer", ["failed", "crash", "no answer"])
def test_16z_A1_a_file_kept_this_run_is_not_registered_again_by_its_own_retry(
        db, tmp_path, monkeypatch, answer):
    u"""⚠ 16z (Z-A1) -- ONE try per pairing per run (A4): `keep()` left a `retry` row and the
    SAME run's `retry()` (Pipeline.go, after its own files) called `register` for it again.
    ⭐ The next run tries it, once."""
    link, drop = _link(tmp_path, monkeypatch, register=True)
    calls = []

    def call(argv, data, timeout):
        calls.append(argv)
        if answer == "crash":
            raise OSError("timed out")
        return (0, u"") if answer == "no answer" else _err("failed", 1)

    h = connect.Handoff(db, "auto", link=link, call=call)
    video, sub = _pair(tmp_path)
    assert _keep(h, video, sub) == "retry"
    h.retry()
    assert len(calls) == 1, u"register called %d times for one pairing in one run" % len(calls)
    _handoff(db, link, answers=[_ok()], calls=calls).retry()
    assert len(calls) == 2 and db.pairings(u"ja")[0].state == "registered"


def test_16z_A2_the_ceiling_holds_for_a_cli_that_starts_a_child(tmp_path):
    u"""🚨 16z (Z-A2) -- the 30 s ceiling: a `.cmd` cli hands its stdout to the python it
    starts, so killing the cmd alone left the pipe read waiting for the grandchild (8 s for
    a 1 s ceiling). ⭐ The whole process TREE goes, then what is left is read."""
    import subprocess
    script = tmp_path / u"slow.py"
    script.write_text(u"import time; time.sleep(8)\n", encoding="utf-8")
    if sys.platform == "win32":
        cli = tmp_path / u"surasura-cli.cmd"
        cli.write_text(u'@echo off\r\n"%s" "%s"\r\n' % (sys.executable, script),
                       encoding="utf-8")
    else:
        cli = tmp_path / u"surasura-cli"
        cli.write_text(u'#!/bin/sh\n"%s" "%s"\n' % (sys.executable, script), encoding="utf-8")
        cli.chmod(0o755)
    started = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        connect._call_register([str(cli), "register"], b"{}", 1)
    took = time.time() - started
    assert took < 5, u"the ceiling did not hold: %.1f s for a 1 s ceiling" % took


def test_16z_A4_registered_is_only_ever_the_latest_records_own_copy(tmp_path, monkeypatch):
    u"""⚠ 16z (Z-A4) -- `pairings --json`'s `registered` came from ANY earlier registered row
    of the video: a re-sync under another series (another `library_path`) that Surasura has
    not taken claimed the file_id of the copy under the first one. ⭐ Only a registration
    of the latest record's own `library_path` counts."""
    link, drop = _link(tmp_path, monkeypatch, register=True)
    path = tmp_path / u"state.db"
    with state.StateDB(path) as d:
        video, sub = _pair(tmp_path)
        assert _keep(_handoff(d, link, answers=[_ok(file_id=4182)]), video, sub,
                     series=u"Show A") == "registered"
        sub.write_bytes(JA + b"x")
        assert _keep(_handoff(d, link, answers=[_err("busy", 3)]), video, sub,
                     series=u"Show B") == "retry"
    (row, registered), = state.read_pairings(path)[0]
    assert os.path.basename(os.path.dirname(row.record["library_path"])) == u"Show B"
    assert registered is None, (u"the copy under Show B claims the file_id %r of the copy "
                                u"under Show A" % (registered,))
    with state.StateDB(path) as d:                    # the same copy, re-registered later
        sub.write_bytes(JA)
        assert _keep(_handoff(d, link, answers=[_err("busy", 3)]), video, sub,
                     series=u"Show A") == "retry"
    (row, registered), = state.read_pairings(path)[0]
    assert registered is not None and registered[0] == 4182, registered


def test_16z_A5_a_stop_holds_the_next_run_and_a_pick_until_surasura_changes(
        db, tmp_path, monkeypatch):
    u"""⚠ 16z (Z-A5) -- an exit 2 is lifted only by a new `updated`, but only the run that
    met it remembered it: the next run's first file, and every pick, called again. ⭐ The
    stop on record holds every call until surasura.json changes."""
    link, drop = _link(tmp_path, monkeypatch, register=True)
    cli = link.entry["cli"]
    calls = []
    v1, s1 = _pair(tmp_path, name=u"Example Show - 01")
    assert _keep(_handoff(db, link, answers=[_err("not-set-up", 2)], calls=calls),
                 v1, s1) == "stopped"
    h = _handoff(db, connect.state("auto"), answers=[_ok(), _ok()], calls=calls)
    v2, s2 = _pair(tmp_path, name=u"Example Show - 02")
    assert _keep(h, v2, s2) == "retry"
    h.retry()
    assert len(calls) == 1, u"register called again with surasura.json's `updated` unchanged"
    fake.install(tmp_path, monkeypatch, register=True, cli=cli, updated="2026-10-30T08:00:00Z")
    _handoff(db, connect.state("auto"), answers=[_ok(), _ok()], calls=calls).retry()
    assert len(calls) == 3, u"a new `updated` did not lift the stop"
    assert [p.state for p in db.pairings(u"ja")] == ["registered", "registered"]
