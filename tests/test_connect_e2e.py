# -*- coding: utf-8 -*-
u"""
⭐ LAYER 16 -- the hand-off END TO END, against a REAL Surasura: a scratch clone of
public `3.0-dev`, a throwaway root, its own tools folder (RUNBOOK 16a). Opt-in: the
suite `connect_e2e` runs only when named, with the scratch set up --

    C:\\Sonic\\AppData\\hato\\surasura-3.0\\        the clone + its .venv
    C:\\Sonic\\AppData\\hato\\make_root.py          lays out the root, the tools, the wrapper
    C:\\Sonic\\AppData\\hato\\surasura_do.py        Surasura's folder scan and its back-fill

(`HATO_E2E_SURASURA` names another base). ⛔ Never Sonic's real Surasura, library,
%LOCALAPPDATA%\\Houseki\\ or Anki: every Surasura process runs in the scratch root.

What only this proves: Surasura's OWN `register` takes hato's record (its checks,
its copy-hash comparison, its folder rule), and its back-fill reads `pairings`.
"""
from __future__ import unicode_literals

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hato import cache, connect, state  # noqa: E402

BASE = Path(os.environ.get("HATO_E2E_SURASURA") or u"C:\\Sonic\\AppData\\hato")
PY = BASE / u"surasura-3.0" / u".venv" / u"Scripts" / u"python.exe"
TOOLS = BASE / u"tools"
WRAPPER = BASE / u"surasura-cli.cmd"
RESOURCE = BASE / u"surasura-3.0" / u"tests" / u"Test Resources" / u"ja" / u"phrases_sample.srt"

pytestmark = pytest.mark.skipif(
    not (PY.is_file() and (BASE / u"make_root.py").is_file()),
    reason=u"the scratch Surasura is not set up (RUNBOOK 16a)")


def _scratch(*args):
    proc = subprocess.run([str(PY), *[str(a) for a in args]], cwd=str(BASE),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, (args, out[-2000:], proc.stderr.decode("utf-8", "replace")[-2000:])
    return out


def _surasura_cli(*args):
    proc = subprocess.run([str(WRAPPER), *args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=300)
    return proc.returncode, connect._last_json(proc.stdout.decode("utf-8", "replace"))


def _episode(tmp_path, n):
    show = tmp_path / u"Shows" / u"Example Show"
    show.mkdir(parents=True, exist_ok=True)
    video = show / (u"Example Show - %02d.mkv" % n)
    video.write_bytes(bytes(i % 251 for i in range(200000)) + (u"ep%d" % n).encode())
    sub = show / (u"Example Show - %02d.ja.srt" % n)
    sub.write_bytes(RESOURCE.read_bytes() + (u"\n%d\n" % n).encode("utf-8"))
    return video, sub


class _Seen(object):
    u"""The real `register` call, its answers kept."""

    def __init__(self):
        self.answers = []

    def __call__(self, argv, data, timeout):
        code, out = connect._call_register(argv, data, timeout)
        self.answers.append((code, connect._last_json(out)))
        return code, out


def _keep(h, video, sub, n):
    return h.keep(video=video, subtitle_path=sub, verdict=connect.TIMED, series=u"Example Show",
                  show={"title": u"Example Show", "season": 1, "episode": n, "movie": False},
                  jimaku_entry_id=11407, anilist_id=154587, tmdb_id=u"tv:209867",
                  source_name=u"[Example] Example Show %02d.srt" % n,
                  timing={"outcome": "CONFIDENT", "match_rate": 0.9, "offset_s": 0.5,
                          "segments": 1, "reference": "speech-mask",
                          "tsubasa_version": "0.1.10"})


def test_the_hand_off_against_a_real_surasura_3_0(tmp_path, monkeypatch):
    monkeypatch.setenv("HOUSEKI_TOOLS_DIR", str(TOOLS))
    _scratch(u"make_root.py", u"--fresh", u"--connect", u"off")
    with state.StateDB(tmp_path / u"state.db") as db:
        # 1 -- Make cards OFF: surasura.json offers `status` only -> copied, never registered
        link = connect.state("auto")
        assert link.state == connect.DROPS, link
        drop = Path(link.folder)
        v4, s4 = _episode(tmp_path, 4)
        assert _keep(connect.Handoff(db, "auto", link=link), v4, s4, 4) == "dropped"
        assert (drop / u"Example Show" / s4.name).read_bytes() == s4.read_bytes()

        # 2 -- ON: `register` -> 3.0 lands a show never shown in New arrivals
        _scratch(u"make_root.py", u"--connect", u"on")
        link = connect.state("auto")
        assert link.state == connect.REGISTERS, link
        seen = _Seen()
        v5, s5 = _episode(tmp_path, 5)
        assert _keep(connect.Handoff(db, "auto", link=link, call=seen), v5, s5, 5) == \
            "registered", seen.answers
        code, answer = seen.answers[-1]
        assert code == 0 and answer["landed"] == "arrivals" and answer["pairing"] == "new", answer
        five = answer["file_id"]

        # 3 -- the show placed in Current: its next episode follows it there
        code, placed = _surasura_cli(u"place", u"--lang", u"ja", u"--file", str(five),
                                     u"--to", u"now", u"--source", u"tester")
        assert code == 0, placed
        v6, s6 = _episode(tmp_path, 6)
        assert _keep(connect.Handoff(db, "auto", link=link, call=seen), v6, s6, 6) == "registered"
        code, answer = seen.answers[-1]
        assert (answer["landed"], answer.get("rule")) == ("arrivals", "after-show"), answer

        # 4 -- the same record again: `same`, nothing written
        row = db.latest_pairing(cache.video_hash(v6), "ja")
        h = connect.Handoff(db, "auto", link=link, call=seen)
        assert h._register(dict(row.record)) == "registered"
        assert seen.answers[-1][1]["pairing"] == "same", seen.answers[-1]

        # 5 -- Surasura's folder scan finds the copy first: `already` + `new` is a success
        v7, s7 = _episode(tmp_path, 7)
        copy_only = connect.Link(connect.DROPS, link.entry, link.folder, "ja", "auto")
        assert _keep(connect.Handoff(db, "auto", link=copy_only), v7, s7, 7) == "dropped"
        _scratch(u"surasura_do.py", u"scan")
        row = db.latest_pairing(cache.video_hash(v7), "ja")
        assert h._register(dict(row.record)) == "registered", h.notes
        code, answer = seen.answers[-1]
        assert (answer["landed"], answer["pairing"]) == ("already", "new"), answer

        # 6 (16f) -- Surasura's OWN back-fill asks `hato-cli pairings` through hato.json:
        # what hato only dropped (ep4, Make cards off at the time) is registered now, and a
        # file older than `complete_since` that hato has no line for is ONE Needs you entry
        cli = BASE / u"hato-cli.cmd"
        here = Path(__file__).resolve().parent.parent
        cli.write_bytes((u"@echo off\r\nset \"PYTHONPATH=%s\"\r\n\"%s\" -m hato %%*\r\n"
                         % (here, Path(sys.executable))).encode("utf-8"))
        monkeypatch.setenv("HATO_TOOLS_CLI", str(cli))
        assert connect.write_hato_json("auto") is True
        old = drop / u"Old Show - 01.ja.srt"          # a 1.0.x flat drop: fork 4, no line
        old.write_bytes(RESOURCE.read_bytes())
        days_ago = time.time() - 3 * 86400
        os.utime(str(old), (days_ago, days_ago))
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))   # the child `hato-cli` reads this store
    summary = json.loads(_scratch(u"surasura_do.py", u"backfill").strip().splitlines()[-1])
    assert summary["hato"] not in (None, "") and summary["stopped"] is None, summary
    assert summary["new"] >= 1 and summary["refused"] == [], summary
    assert [os.path.basename(p) for p in summary["unpaired"]] == [old.name], summary
    assert summary["need"] in ("raised", "kept"), summary


# -- LAYER 17 (Hato-FIND): Surasura's OWN finder against this hato -------------------------------

FIND = BASE / u"find-e2e"
FIXTURES = Path(__file__).resolve().parent / u"fixtures"


def _mkv(path, title):
    u"""A real, tiny Matroska file with an English text track (the reference a download is
    timed against) -- so hato's real reader says *fetch* and the run searches for it."""
    import shutil
    ffmpeg = shutil.which(u"ffmpeg")
    if ffmpeg is None:
        pytest.skip(u"ffmpeg is not on PATH: no real video to hand Surasura")
    path.parent.mkdir(parents=True, exist_ok=True)
    srt = path.parent / u"_en.srt"
    srt.write_text(u"1\n00:00:01,000 --> 00:00:03,000\nHello there.\n", encoding="utf-8")
    subprocess.run([ffmpeg, u"-loglevel", u"error", u"-y", u"-f", u"lavfi", u"-i",
                    u"color=c=black:s=160x120:d=8", u"-f", u"lavfi", u"-i",
                    u"anullsrc=r=48000:cl=mono", u"-i", str(srt), u"-t", u"8", u"-map", u"0",
                    u"-map", u"1", u"-map", u"2", u"-c:v", u"libx264", u"-preset", u"ultrafast",
                    u"-c:a", u"aac", u"-c:s", u"srt", u"-metadata:s:s:0", u"language=eng",
                    u"-metadata", u"title=%s" % title, str(path)], check=True, timeout=120)
    srt.unlink()
    old = time.time() - 120                    # settled: older than Surasura's half-written wait
    os.utime(str(path), (old, old))
    return path


def test_17_surasuras_own_finder_against_this_hato(monkeypatch):
    u"""⭐ H1-H8 END TO END: Surasura 3.0-dev's `no_subs.find` -- its gate on `find` in
    hato.json, its list file, its command line, its NDJSON reader, its retry dates -- against
    THIS hato, started through a `hato-cli` wrapper in an isolated world: its own data root
    and config, no key, no network (`HATO_NO_NETWORK`), jimaku answered from the recorded
    fixtures (`--fixtures`: hato's network rule). ⛔ Never Sonic's library or hato.

    The scratch library: `frieren S2 - 24.mkv` (jimaku has no episode 24: NOT_FOUND, with
    its retry date) and `Extras/frieren S2 - 26.mkv` in a folder hato's config SKIPS (left
    out: its ERROR row, never a run that failed whole). hato's `write_beside_video` is off,
    and Surasura reads it through `hato-cli config --show --json`."""
    import shutil
    if FIND.exists():
        shutil.rmtree(str(FIND))
    library = FIND / u"library"
    show = library / u"Frieren S2"
    late = _mkv(show / u"frieren S2 - 24.mkv", u"ep24")
    skipped = _mkv(show / u"Extras" / u"frieren S2 - 26.mkv", u"ep26")
    home = FIND / u"hato"
    home.mkdir(parents=True)
    (home / u"config.toml").write_text(
        u"write_beside_video = false\nskip_folders = [%s]\n" % json.dumps(str(skipped.parent)),
        encoding="utf-8")
    wrapper = FIND / u"hato-cli-find.cmd"
    py = Path(sys.executable)
    repo = Path(__file__).resolve().parents[1]
    wrapper.write_bytes((
        u"@echo off\r\n"
        u"set \"PYTHONPATH=%s\"\r\nset \"PYTHONUTF8=1\"\r\nset \"HATO_NO_NETWORK=1\"\r\n"
        u"set \"HATO_CACHE=%s\"\r\nset \"HATO_CONFIG=%s\"\r\nset \"HATO_KEYFILE=%s\"\r\n"
        u"set \"HOUSEKI_TOOLS_DIR=%s\"\r\nset \"HATO_TOOLS_CLI=%%~f0\"\r\n"
        u"if /I \"%%~1\"==\"config\" goto plain\r\n"
        u"\"%s\" -m hato %%* --fixtures \"%s\"\r\nexit /b %%ERRORLEVEL%%\r\n"
        u":plain\r\n\"%s\" -m hato %%*\r\n" % (
            repo, home / u"data", home / u"config.toml", home / u"no-key.txt", TOOLS,
            py, FIXTURES, py)).encode("ascii"))

    _scratch(u"make_root.py", u"--fresh", u"--connect", u"on")
    monkeypatch.setenv("HOUSEKI_TOOLS_DIR", str(TOOLS))
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, str(wrapper))
    # ⛔ THE CONTROL ARM FIRST: 1.1.0's entry (`pairings` only) -- Surasura sends it nothing
    monkeypatch.setattr(connect, u"VERBS", [u"pairings"])
    assert connect.write_hato_json(u"auto"), u"hato.json was not written"
    said = json.loads(_scratch(u"surasura_find.py", str(library)).strip().splitlines()[-1])
    assert said[u"find"] == {u"off": True} and said[u"hato_finds"] is None, said
    assert not (home / u"data" / u"hato.log").exists(), u"a hato with no `find` was started"
    monkeypatch.undo()
    monkeypatch.setenv("HOUSEKI_TOOLS_DIR", str(TOOLS))
    monkeypatch.setenv(connect.TOOLS_CLI_ENV, str(wrapper))
    assert connect.write_hato_json(u"auto"), u"hato.json was not written"
    with open(str(TOOLS / u"hato.json"), encoding="utf-8") as handle:
        assert json.load(handle)[u"verbs"] == list(connect.VERBS)

    said = json.loads(_scratch(u"surasura_find.py", str(library)).strip().splitlines()[-1])
    assert os.path.normcase(said[u"hato_finds"] or u"") == os.path.normcase(str(wrapper)), said
    assert sorted(os.path.normcase(v) for _r, v in said[u"waiting"]) == sorted(
        os.path.normcase(str(p)) for p in (late, skipped)), said[u"waiting"]
    found = said[u"find"]
    assert (found[u"asked"], found[u"not_found"], found[u"failed"]) == (2, 1, 0), found
    outcomes = sorted(r[u"outcome"] for r in said[u"state"][u"hato"].values())
    assert outcomes == [u"ERROR", u"NOT_FOUND"], said[u"state"]
    record = [r for r in said[u"state"][u"hato"].values() if r[u"outcome"] == u"NOT_FOUND"][0]
    assert record[u"retry_at"] > time.time() + 3600, record          # hato's own date, ahead
    assert not said[u"state"].get(u"offline_until"), u"Surasura read the run as failed whole"
    late_rel = [r for r, v in said[u"waiting"] if os.path.normcase(v) == os.path.normcase(str(late))][0]
    assert said[u"notes"][late_rel] and said[u"notes"][late_rel][0], said[u"notes"]
    assert said[u"beside_on"] is False, u"Surasura did not read write_beside_video off"
    assert sorted(os.listdir(str(show))) == [u"Extras", late.name], u"something was written beside"
