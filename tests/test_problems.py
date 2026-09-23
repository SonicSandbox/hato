# -*- coding: utf-8 -*-
"""
Step 8c -- the open-problems view (spec/RUNBOOK.md §Step 8c; HANDOFF.md §4a).

`hato/problems.py` lists every problem the state DB remembers that the DISK still
agrees with, shaped as a run's `{"type": "video"}` row; `hato problems [--json]`
prints it. Sonic: *"a problem episode must never disappear from Needs you"* --
and `last-run.json` is a snapshot of one run by design, so this is the store that
outlives a run.

Everything here is real: a real `StateDB` and a real `Cache` under `tmp_path`,
real stub videos with DISTINCT bytes (the DB is keyed on a head+tail hash, so
identical bytes would be ONE video), real tsubasa for the names. The clock is
injected -- the DB's through `StateDB(now=)`, the command's through `run(now=)`.

The rule each check holds, in one line:

    the DB proposes a problem          listed only while the disk agrees
    a subtitle appears                 the row goes, and NOTHING is written
    blacklisted / gone / elsewhere /   not listed -- each beside a control that
    skipped / another rip              IS, so an empty answer cannot pass
    the outcome                        the latest row's; a NOT_FOUND after tried
                                       files is a pick waiting for its retry
    the plain list                     never says "refused"
    ⛔ zero network                    asserted, not assumed

What this suite structurally cannot cover: the window merging these rows with a
run's (RUNBOOK 8e) -- that is `gui/run.py`'s, and its suite's.
"""
import argparse
import hashlib
import json
import os
import re
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tsubasa

from hato import cache, config, keep, paths, pipeline, present, problems, report, state
from hato.commands import problems as problems_cmd

T0 = datetime(2026, 9, 22, 3, 0, 0, tzinfo=timezone.utc)
ENTRY = 11446
LAST_MODIFIED = "2026-09-01T12:00:00.000Z"


class Clock(object):
    """An injectable `now`. Moves only when told."""

    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class Lab(object):
    """A library, a state DB, a working cache and a config -- all under one tmp_path.

        media/          the configured folder
        media/Old/      a skipped folder inside it
        elsewhere/      outside every configured folder
        data/           the per-user root: state.db and cache/
    """

    def __init__(self, root):
        self.root = root
        self.media = root / "media"
        self.skipped = self.media / "Old"
        self.elsewhere = root / "elsewhere"
        for folder in (self.media, self.skipped, self.elsewhere):
            folder.mkdir(parents=True)
        self.data = root / "data"
        self.clock = Clock()
        self.cache = cache.Cache(self.data / "cache")
        self.db = None
        self.open()

    def open(self):
        self.db = state.StateDB(self.data / "state.db", now=self.clock)

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def config_text(self, out=None):
        # ⚠ json.dumps: a TOML basic string, with a Windows path's backslashes escaped
        lines = ["folders = [%s]" % json.dumps(str(self.media)),
                 "skip_folders = [%s]" % json.dumps(str(self.skipped))]
        if out is not None:
            lines.append("out = %s" % json.dumps(str(out)))
        return "\n".join(lines) + "\n"

    def cfg(self, out=None):
        return config.parse(self.config_text(out))

    def video(self, name, folder=None):
        folder = Path(folder) if folder is not None else self.media
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(("stub video -- %s" % path).encode("utf-8"))    # ⚠ DISTINCT bytes
        return path

    def rows(self, cfg=None):
        return problems.open_problems(cfg if cfg is not None else self.cfg(), self.db, self.cache)


@pytest.fixture
def lab(tmp_path):
    handle = Lab(tmp_path)
    yield handle
    handle.close()


@pytest.fixture
def library(lab, monkeypatch):
    """`lab`, as the COMMAND finds it: its data root and its config file in the environment."""
    config_file = lab.root / "config.toml"
    config_file.write_text(lab.config_text(), encoding="utf-8")
    monkeypatch.setenv("HATO_CACHE", str(lab.data))
    monkeypatch.setenv("HATO_CONFIG", str(config_file))
    return lab


# -- recording what the pipeline records ---------------------------------------------------

def refuse(lab, video, name, rate, keep_file=True, hashed=True, recorded_as=None):
    """One file downloaded and refused by timing, recorded as the pipeline records it.
    -> (the file in the working cache or None, its size)"""
    data = ("subtitle %s, tried against %s" % (name, video.name)).encode("utf-8")
    stored = lab.cache.store(data, keep.download_name(name, "ja")) if keep_file else None
    if stored is not None:
        # ⚠ The file was downloaded when its attempt ran -- at the LAB's moment, not
        # the machine's. A legacy row finds its file by name, size AND "stored no
        # later than the attempt" (F11); a real mtime hours after T0 made the lab a
        # world that cannot happen.
        moment = lab.clock.now.timestamp()
        os.utime(str(stored), (moment, moment))
    lab.db.record_attempt(
        video_hash=cache.video_hash(video), video_path=recorded_as or str(video), lang="ja",
        jimaku_entry=ENTRY, jimaku_filename=name, jimaku_size=len(data),
        jimaku_last_modified=LAST_MODIFIED,
        subtitle_hash=cache.content_hash(data) if hashed else None,
        outcome=state.REFUSED, match_rate=rate,
        reason="%s: refused -- the timing did not hold (%d%% match)" % (name, round(rate * 100)))
    lab.clock.advance(minutes=1)
    return stored, len(data)


def gave_up(lab, video, tried, offered=4, recorded_as=None):
    """The soft negative `_all_refused` records once every file tried was refused."""
    retry = lab.db.record_not_found(
        video_hash=cache.video_hash(video), video_path=recorded_as or str(video), lang="ja",
        kind="soft", jimaku_entry=ENTRY,
        reason="%d of %d candidate(s) tried, all refused by timing" % (tried, offered))
    lab.clock.advance(minutes=1)
    return retry


def not_yet(lab, video, kind="soft", newest=None):
    """jimaku has nothing for it: soft (the entry, no file) or hard (no entry at all)."""
    retry = lab.db.record_not_found(
        video_hash=cache.video_hash(video), video_path=str(video), lang="ja", kind=kind,
        jimaku_entry=ENTRY if kind == "soft" else None, newest_offered=newest,
        reason=("jimaku entry %d has no file for this episode" % ENTRY if kind == "soft"
                else "no jimaku entry matched this show"))
    lab.clock.advance(minutes=1)
    return retry


def went_wrong(lab, video, name):
    """A download that failed -- an ERROR, and no negative after it."""
    lab.db.record_attempt(
        video_hash=cache.video_hash(video), video_path=str(video), lang="ja",
        jimaku_entry=ENTRY, jimaku_filename=name, jimaku_size=4096,
        jimaku_last_modified=LAST_MODIFIED, subtitle_hash=None, outcome=state.ERROR,
        reason="%s could not be downloaded: HTTP 503" % name)
    lab.clock.advance(minutes=1)


def a_problem(lab, name, folder=None):
    """A video with one refused file and the soft negative after it. -> the video"""
    video = lab.video(name, folder)
    refuse(lab, video, "[G] %s [JPN].ass" % os.path.splitext(name)[0], 0.5)
    gave_up(lab, video, 1)
    return video


def names(rows):
    return set(row["name"] for row in rows)


def only(rows):
    assert len(rows) == 1, "expected exactly one open problem, got %d: %s" % (
        len(rows), sorted(names(rows)))
    return rows[0]


def when(text):
    return None if text is None else datetime.fromisoformat(text)


def snapshot(root):
    """Every folder and file under `root`, each file by the hash of its bytes. -> dict"""
    seen = {}
    for folder, _dirs, files in os.walk(str(root)):
        rel = os.path.relpath(folder, str(root))
        seen[rel] = "<dir>"
        for name in files:
            with open(os.path.join(folder, name), "rb") as fh:
                seen[os.path.join(rel, name)] = hashlib.sha256(fh.read()).hexdigest()
    return seen


def changed(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


# -- what is listed, and how it is shaped ---------------------------------------------------

def test_a_refused_episode_is_listed_with_its_files_their_rates_and_its_retry_date(lab):
    video = lab.video("Sousou no Frieren S2 - 01.mkv")
    first, first_size = refuse(lab, video, "[Haruhana] Sousou no Frieren - 29 [JPN].ass", 0.61)
    second, second_size = refuse(lab, video, "[Nekomoe] Sousou no Frieren - 29 [CHS, JPN].ass",
                                 0.35)
    retry = gave_up(lab, video, tried=2)

    row = only(lab.rows())
    assert (row["type"], row["source"]) == ("video", "memory"), (
        "a remembered row must say it is one -- the window merges these with a run's rows "
        "and cannot tell them apart otherwise: %r" % ((row["type"], row["source"]),))
    assert row["outcome"] == "REFUSED", (
        "the soft negative recorded after every file was refused came back %r -- that episode "
        "is a PICK waiting for its retry, and saying anything else hides the files a person "
        "can choose from" % row["outcome"])
    tried = row["tried_before"]
    assert [t["name"] for t in tried] == [
        "[Nekomoe] Sousou no Frieren - 29 [CHS, JPN].ass",
        "[Haruhana] Sousou no Frieren - 29 [JPN].ass"], (
        "the files tried are not all listed, newest first: %s" % [t["name"] for t in tried])
    assert [t["match_rate"] for t in tried] == [pytest.approx(0.35), pytest.approx(0.61)], (
        "a remembered file lost how close it came: %s" % [t["match_rate"] for t in tried])
    assert [t["path"] for t in tried] == [str(second), str(first)], (
        "a remembered file does not point at the file still in the working cache -- a pick "
        "would have nothing to hand over: %s" % [t["path"] for t in tried])
    assert all(os.path.isfile(t["path"]) for t in tried)
    assert [t["bytes"] for t in tried] == [second_size, first_size]
    assert [t["outcome"] for t in tried] == ["REFUSED", "REFUSED"]
    assert when(tried[0]["when"]) == T0 + timedelta(minutes=1)
    assert when(row["retry_after"]) == retry == T0 + timedelta(days=1, minutes=2), (
        "the retry date is missing or wrong (%r) -- *\"retrying in 14h\"* is the whole "
        "point of 4b" % row["retry_after"])
    assert row["reason"] == "2 of 4 candidate(s) tried, all refused by timing"
    assert row["jimaku_entry"] == ENTRY
    assert (row["video"], row["name"]) == (str(video), video.name)
    assert (row["title"], row["season"], row["episode"]) == ("Sousou no Frieren", 2, 1), (
        "the title, season and episode are not tsubasa's reading of the name: %r"
        % ((row["title"], row["season"], row["episode"]),))
    assert row["attempts"] == [] and row["candidates_tried"] == 0, (
        "`attempts` means THIS run, and there is no run here")
    assert (row["skip"], row["api_calls"], row["bytes_downloaded"]) == (None, 0, 0)


def test_a_not_found_episode_is_listed_with_no_files_and_the_newest_episode_offered(lab):
    video = lab.video("[Group] Mairimashita! Iruma-kun S4 - 23 [1080p].mkv")
    retry = not_yet(lab, video, newest=22)

    row = only(lab.rows())
    assert row["outcome"] == "NOT_FOUND", (
        "an episode jimaku has no file for, with nothing ever tried, came back %r -- it has "
        "nothing to pick, so it is *not on jimaku yet*" % row["outcome"])
    assert row["tried_before"] == [], "a NOT_FOUND with nothing tried grew candidates"
    assert when(row["retry_after"]) == retry, "the retry date of a NOT_FOUND is missing"
    assert row["newest_offered"] == 22, (
        "newest_offered was dropped (%r) -- RUNBOOK 8f highlights *probably not out yet* "
        "from it" % row["newest_offered"])
    assert (row["season"], row["episode"]) == (4, 23)


def test_an_episode_whose_last_try_went_wrong_is_an_error_and_a_gone_file_is_still_listed(lab):
    video = lab.video("Tsuihou - 12 (1080p).mkv")
    went_wrong(lab, video, "[NanakoRaws] Tsuihou - 12.ass")

    row = only(lab.rows())
    assert row["outcome"] == "ERROR", (
        "a download that failed came back %r -- it is *had a problem*, not a pick"
        % row["outcome"])
    assert row["retry_after"] is None, "an ERROR records no negative, so it has no retry date"
    assert [(t["name"], t["path"]) for t in row["tried_before"]] == [
        ("[NanakoRaws] Tsuihou - 12.ass", None)], (
        "a file tried whose download never landed must still be LISTED, with no path, so "
        "the person can see it was tried: %r" % row["tried_before"])


def test_a_refusal_with_no_retry_recorded_yet_is_still_a_pick(lab):
    """A run stopped between the refusal and its soft negative: the latest row is REFUSED."""
    video = lab.video("Show - 05.mkv")
    refuse(lab, video, "[G] Show - 05.ass", 0.4)

    row = only(lab.rows())
    assert row["outcome"] == "REFUSED", (
        "a video whose latest row is a refusal came back %r -- it is a pick" % row["outcome"])
    assert row["retry_after"] is None
    assert [t["name"] for t in row["tried_before"]] == ["[G] Show - 05.ass"]


def test_a_row_carries_exactly_a_run_rows_keys_plus_source_and_newest_offered(lab):
    video = lab.video("Sousou no Frieren S2 - 01.mkv")
    refuse(lab, video, "a [JPN].ass", 0.5)
    gave_up(lab, video, 1)
    row = only(lab.rows())

    run_row = report.as_dict(pipeline.VideoResult(
        str(video), pipeline.REFUSED, "a reason",
        tried_before=(pipeline.Remembered("a.ass", "REFUSED", "why", 1, 0.5, None, T0),)))
    assert set(row) == set(run_row) | {"source", "newest_offered"}, (
        "a remembered row is not a run's row plus `source` and `newest_offered` -- the window "
        "merges the two, and a key one has and the other lacks is a merge that drifts. "
        "Missing %s, extra %s" % (sorted(set(run_row) - set(row)),
                                  sorted(set(row) - set(run_row) - {"source", "newest_offered"})))
    assert set(row["tried_before"][0]) == set(run_row["tried_before"][0])


# -- the disk decides ------------------------------------------------------------------------

def test_prove__a_refused_a_waiting_and_a_resolved_episode_list_exactly_the_first_two(lab):
    """RUNBOOK 8c's Prove line, whole: one DB, three episodes, the disk deciding."""
    refused = lab.video("Sousou no Frieren S2 - 11.mkv")
    stored, _size = refuse(lab, refused, "[G] Sousou no Frieren - 11 [JPN].ass", 0.52)
    refused_retry = gave_up(lab, refused, 1)
    waiting = lab.video("Sousou no Frieren S2 - 12.mkv")
    waiting_retry = not_yet(lab, waiting, newest=11)
    resolved = a_problem(lab, "Sousou no Frieren S2 - 10.mkv")
    (resolved.parent / (resolved.stem + ".ja.srt")).write_bytes(
        b"1\r\n00:00:01,000 --> 00:00:02,000\r\n\r\n")

    rows = dict((row["name"], row) for row in lab.rows())
    assert set(rows) == {refused.name, waiting.name}, (
        "expected exactly the refused and the waiting episode -- the resolved one has its "
        "subtitle on disk. Got %s" % sorted(rows))
    assert [(t["name"], t["path"]) for t in rows[refused.name]["tried_before"]] == [
        ("[G] Sousou no Frieren - 11 [JPN].ass", str(stored))], (
        "the refused episode lost the file it could be picked from")
    assert when(rows[refused.name]["retry_after"]) == refused_retry
    assert rows[waiting.name]["tried_before"] == []
    assert when(rows[waiting.name]["retry_after"]) == waiting_retry, (
        "the waiting episode does not say when it is next looked at")


def test_a_subtitle_that_appeared_takes_the_row_off_and_nothing_is_written(lab):
    video = a_problem(lab, "Sousou no Frieren S2 - 03.mkv")
    other = a_problem(lab, "Sousou no Frieren S2 - 04.mkv")
    assert names(lab.rows()) == {video.name, other.name}, "the control: both are problems"

    (video.parent / (video.stem + ".ja.ass")).write_bytes(b"[Script Info]\n")
    lab.close()
    before = snapshot(lab.root)
    lab.open()
    rows = lab.rows()
    lab.close()
    after = snapshot(lab.root)

    assert names(rows) == {other.name}, (
        "an episode whose subtitle now sits beside it is still listed -- the DB says "
        "problem, the disk says resolved, and the DISK is canonical")
    assert after == before, (
        "the view WROTE something -- it is a read, and the state DB may only ever PREVENT "
        "work. Changed: %s" % changed(before, after))


def test_under_out_the_subtitle_is_looked_for_in_the_mirrored_folder(lab):
    out = lab.root / "subs-out"
    show = lab.media / "Frieren S2"
    video = a_problem(lab, "Frieren S2 - 05.mkv", show)
    other = a_problem(lab, "Frieren S2 - 06.mkv", show)
    cfg = lab.cfg(out=out)
    assert names(lab.rows(cfg)) == {video.name, other.name}, "the control: both are problems"

    mirror = out / "Frieren S2"
    mirror.mkdir(parents=True)
    (mirror / (video.stem + ".ja.ass")).write_bytes(b"[Script Info]\n")
    assert names(lab.rows(cfg)) == {other.name}, (
        "with --out set the finished file lives in the MIRRORED folder; looking beside the "
        "video lists an episode that is done, for ever")


def test_a_blacklisted_video_is_not_listed(lab):
    video = a_problem(lab, "Recap - 01.mkv")
    control = a_problem(lab, "Show - 01.mkv")
    lab.db.blacklist_add(cache.video_hash(video), str(video), note="a recap")
    assert names(lab.rows()) == {control.name}, (
        "a video the person blacklisted is listed as needing them -- they already decided")


def test_a_video_that_is_gone_is_not_listed(lab):
    video = a_problem(lab, "Show - 02.mkv")
    control = a_problem(lab, "Show - 03.mkv")
    video.unlink()
    assert names(lab.rows()) == {control.name}, (
        "a video that is no longer on disk is listed -- there is nothing to pick a file for")


def test_a_video_outside_the_configured_folders_is_not_listed(lab):
    video = a_problem(lab, "Show - 04.mkv", lab.elsewhere)
    control = a_problem(lab, "Show - 05.mkv")
    assert names(lab.rows()) == {control.name}, (
        "a video outside every configured folder is listed -- no run of this config would "
        "ever look at it again")


def test_a_video_inside_a_skipped_folder_is_not_listed(lab):
    video = a_problem(lab, "Show - 06.mkv", lab.skipped)
    control = a_problem(lab, "Show - 07.mkv")
    assert names(lab.rows()) == {control.name}, (
        "a video inside a folder the person skips is listed -- the run drops it, so this "
        "would promise a retry that never comes")


def test_a_different_video_at_the_same_path_is_not_listed(lab):
    video = a_problem(lab, "Show - 08.mkv")
    control = a_problem(lab, "Show - 09.mkv")
    video.write_bytes(b"a different rip, saved over the same name")
    assert names(lab.rows()) == {control.name}, (
        "a different video at the same path is listed with the OLD one's files -- a pick "
        "would pair a subtitle timed against another rip. The next run decides it")


def test_a_row_with_no_recorded_path_is_passed_over_not_a_crash(lab):
    control = a_problem(lab, "Show - 10.mkv")
    lab.db.record_not_found(video_hash="v1-" + "e" * 64, video_path=None, lang="ja",
                            kind="hard", reason="no jimaku entry matched")
    try:
        rows = lab.rows()
    except Exception as exc:
        pytest.fail("one row with no recorded path crashed the whole view (%s: %s) -- and "
                    "every other open problem vanished with it" % (type(exc).__name__, exc))
    assert names(rows) == {control.name}, (
        "a row with no recorded path must be passed over, and the rest still listed")


def test_a_file_recorded_without_a_hash_as_1_0_1_did_is_found_by_name_and_size(lab):
    video = lab.video("Show - 11.mkv")
    stored, _size = refuse(lab, video, "[Legacy] Show - 11 [JPN].ass", 0.2, hashed=False)
    gave_up(lab, video, 1)

    row = only(lab.rows())
    assert [t["path"] for t in row["tried_before"]] == [str(stored)], (
        "a refusal recorded before hashes were kept (hato 1.0.1 -- Sonic's own DB) lost its "
        "file: the name and the size find it, and the pick needs it")


def test_the_title_is_tsubasas_even_when_the_db_spells_the_path_differently(lab):
    video = lab.video("Sousou no Frieren S2 - 07.mkv")
    spelled = video.as_posix()                      # forward slashes; tsubasa hands back `\`
    refuse(lab, video, "[G] Frieren - 07 [JPN].ass", 0.3, recorded_as=spelled)
    gave_up(lab, video, 1, recorded_as=spelled)

    row = only(lab.rows())
    assert (row["title"], row["season"], row["episode"]) == ("Sousou no Frieren", 2, 7), (
        "tsubasa's listing was not matched to the DB's path, so the episode lost its title "
        "and number: %r -- one file, two spellings of its path"
        % ((row["title"], row["season"], row["episode"]),))


def test_a_video_tsubasa_does_not_list_is_named_by_its_file_and_given_no_number(lab):
    """A creditless opening is one tsubasa's scan() declines to list."""
    video = a_problem(lab, "Show - NCOP1.mkv")
    row = only(lab.rows())
    assert (row["title"], row["season"], row["episode"]) == ("Show - NCOP1", None, None), (
        "a video tsubasa does not list must be named by its own file and given NO number -- "
        "never guessed: %r" % ((row["title"], row["season"], row["episode"]),))


def test_one_scan_per_folder_not_per_video(lab, monkeypatch):
    for n in (1, 2, 3):
        a_problem(lab, "Show - 2%d.mkv" % n)
    a_problem(lab, "Show - 24.mkv", lab.media / "Sub")
    real, folders = tsubasa.scan, []

    def counting(*args, **kwargs):
        folders.append(kwargs.get("videos"))
        return real(*args, **kwargs)

    monkeypatch.setattr(tsubasa, "scan", counting)
    rows = lab.rows()
    assert len(rows) == 4 and all(row["episode"] for row in rows), "the control: 4, all read"
    assert len(folders) == 2, (
        "tsubasa.scan ran %d times for 4 videos in 2 folders -- ONE per folder "
        "(spec/00-INDEX.md Rule 4: is every unit of work necessary?)" % len(folders))


def test_rows_are_in_title_season_episode_order(lab):
    a_problem(lab, "Beta - 01.mkv", lab.media / "a")
    a_problem(lab, "alpha - 01.mkv", lab.media / "b")
    for name in ("Sousou no Frieren S2 - 01.mkv", "Sousou no Frieren S1 - 10.mkv",
                 "Sousou no Frieren S1 - 2.mkv"):
        a_problem(lab, name)
    assert [row["name"] for row in lab.rows()] == [
        "alpha - 01.mkv", "Beta - 01.mkv", "Sousou no Frieren S1 - 2.mkv",
        "Sousou no Frieren S1 - 10.mkv", "Sousou no Frieren S2 - 01.mkv"], (
        "not in reading order: the title casefolded, then the season, then the episode "
        "as a NUMBER (2 before 10)")


# -- the command ---------------------------------------------------------------------------

def _parse(argv):
    parser = argparse.ArgumentParser(prog="hato problems")
    problems_cmd.register(parser)
    return parser.parse_args(argv)


def populate(lab):
    """One of each kind, at known moments relative to T0 (the command's `now`).

        Sousou no Frieren S2 - 01    2 files refused, retry at T0 + 14h   needs a pick
        Sousou no Frieren S2 - 02    nothing yet, retry at T0 - 1 day     not on jimaku yet
        Unknown Show - 01            no entry at all, retry at T0 + 30d   not on jimaku yet
        Tsuihou - 12 (1080p)         a download failed, no retry date     had a problem
    """
    pick = lab.video("Sousou no Frieren S2 - 01.mkv")
    lab.clock.now = T0 - timedelta(hours=10, minutes=5)
    refuse(lab, pick, "[Haruhana] Sousou no Frieren - 29 [JPN].ass", 0.61)
    refuse(lab, pick, "[Nekomoe] Sousou no Frieren - 29 [CHS, JPN].ass", 0.35)
    lab.clock.now = T0 - timedelta(hours=10)
    gave_up(lab, pick, tried=2)
    past = lab.video("Sousou no Frieren S2 - 02.mkv")
    lab.clock.now = T0 - timedelta(days=2)
    not_yet(lab, past)
    hard = lab.video("Unknown Show - 01.mkv")
    lab.clock.now = T0
    not_yet(lab, hard, kind="hard")
    broken = lab.video("Tsuihou - 12 (1080p).mkv")
    went_wrong(lab, broken, "[NanakoRaws] Tsuihou - 12.ass")
    lab.close()
    return pick, past, hard, broken


def sections(text):
    """{heading: [its lines]} -- a heading is a line that is not indented."""
    out, current = {}, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            current = line
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def section(found, start):
    heading = [h for h in found if h.startswith(start)]
    assert len(heading) == 1, "no single %r group in:\n%s" % (start, "\n".join(found))
    return found[heading[0]]


def test_the_problems_command_has_the_shape_the_cli_loads():
    first = problems_cmd.__doc__.strip().splitlines()[0]
    assert first.startswith("List the episodes that still need you"), first
    assert _parse([]).json is False and _parse(["--json"]).json is True


def test_json_lines_all_parse_carry_the_memory_source_and_a_summary_that_counts_them(
        library, capsys):
    pick, past, hard, broken = populate(library)
    assert problems_cmd.run(_parse(["--json"]), now=T0) == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    try:
        objects = [json.loads(line) for line in lines]
    except ValueError as exc:
        pytest.fail("a --json line does not parse (%s):\n%s" % (exc, captured.out))

    videos = [o for o in objects if o.get("type") == "video"]
    assert [o["type"] for o in objects] == ["video"] * len(videos) + ["problems"], (
        "--json must be one object per episode, then ONE summary object, last")
    assert names(videos) == {pick.name, past.name, hard.name, broken.name}
    assert all(o["source"] == "memory" for o in videos), (
        "a --json row does not say it came from memory: %s" % [o.get("source") for o in videos])
    by_name = dict((o["name"], o["outcome"]) for o in videos)
    assert by_name == {pick.name: "REFUSED", past.name: "NOT_FOUND",
                       hard.name: "NOT_FOUND", broken.name: "ERROR"}, by_name

    summary = objects[-1]
    assert summary["count"] == len(videos) == 4, (
        "the summary counts %r episodes where the stream holds %d" % (summary["count"],
                                                                     len(videos)))
    assert (summary["lang"], summary["retry_days"]) == ("ja", {"soft": 1, "hard": 30})
    assert when(summary["next_due"]) == T0 + timedelta(hours=14), (
        "next_due must be the SOONEST retry still AHEAD -- %r, where the soft retry at "
        "T0+14h is next, T0-1d has passed and T0+30d comes later" % summary["next_due"])


def test_the_plain_list_puts_each_episode_in_its_group_and_says_when_hato_looks_again(
        library, capsys):
    pick, past, hard, broken = populate(library)
    assert problems_cmd.run(_parse([]), now=T0) == 0
    text = capsys.readouterr().out
    found = sections(text)

    assert text.splitlines()[0] == "4 episodes need you.", text
    picks = section(found, "needs a pick")
    assert len(picks) == 1 and pick.name in picks[0], (
        "the refused episode is not under *needs a pick*:\n%s" % text)
    assert "Sousou no Frieren S2 01" in picks[0], picks[0]
    assert picks[0].endswith("2 files tried %s looks again in 14h" % report.DOT), (
        "a pick must say how many files were tried and when hato looks again:\n%s" % picks[0])

    waiting = section(found, "not on jimaku yet")
    line_of = dict((v.name, [l for l in waiting if v.name in l]) for v in (past, hard))
    assert all(len(lines) == 1 for lines in line_of.values()), (
        "the not-found episodes are not under *not on jimaku yet*:\n%s" % text)
    assert line_of[past.name][0].endswith("looks again on the next run"), (
        "a retry date that has PASSED must read *on the next run*, not a countdown:\n%s"
        % line_of[past.name][0])
    assert line_of[hard.name][0].endswith("looks again in 30 days"), line_of[hard.name][0]

    trouble = section(found, "had a problem")
    assert len(trouble) == 1 and broken.name in trouble[0], (
        "the ERROR is not under *had a problem*:\n%s" % text)
    assert trouble[0].endswith("looks again on the next run %s [NanakoRaws] Tsuihou - 12.ass "
                               "could not be downloaded: HTTP 503" % report.DOT), (
        "a trouble row must say what went wrong -- *had a problem* alone is nothing a "
        "person can act on:\n%s" % trouble[0])


def test_the_plain_list_never_says_refused(library, capsys):
    """`spec/05-interface.md` §The window: *"when it says 'refused' it's quite alarming."*"""
    pick, _past, _hard, _broken = populate(library)
    assert problems_cmd.run(_parse([]), now=T0) == 0
    text = capsys.readouterr().out
    assert pick.name in text, (
        "the control: the refused episode is not listed at all, so no word could be "
        "checked:\n%s" % text)
    word = re.search(r"(?i)\w*refus\w*", text)
    assert word is None, (
        "the plain list says %r -- the engine's verdict, read by a person as an accusation. "
        "Say *the timing did not hold*:\n%s" % (word.group(0) if word else "", text))
    assert "the timing did not hold" in text, (
        "a pick must say what happened, in plain words:\n%s" % text)


def test_no_state_db_means_nothing_needs_you_and_none_is_created(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    monkeypatch.setenv("HATO_CACHE", str(root))
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "no-config.toml"))

    assert problems_cmd.run(_parse([]), now=T0) == 0
    assert "Nothing needs you" in capsys.readouterr().out
    assert problems_cmd.run(_parse(["--json"]), now=T0) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line) for line in lines] == [
        {"type": "problems", "ok": True, "count": 0, "lang": "ja",
         "retry_days": {"soft": 1, "hard": 30}, "next_due": None}], lines
    assert not root.exists(), (
        "`hato problems` created %s where there was none -- a read must never create the "
        "store it reads" % sorted(p.name for p in root.rglob("*")))


@pytest.mark.parametrize("broken", ["an unknown key", "a language tsubasa cannot read",
                                    "a relative data folder"])
def test_a_broken_config_exits_1_with_its_own_message(tmp_path, monkeypatch, capsys, broken):
    config_file = tmp_path / "config.toml"
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HATO_CONFIG", str(config_file))
    if broken == "an unknown key":
        config_file.write_text("candiates = 5\n", encoding="utf-8")
        with pytest.raises(config.ConfigError) as said:
            config.load()
    elif broken == "a language tsubasa cannot read":
        config_file.write_text('lang = "jp"\n', encoding="utf-8")
        with pytest.raises(present.LanguageUnknown) as said:
            present.language("jp")
    else:
        monkeypatch.setenv("HATO_CACHE", "relative-data")
        with pytest.raises(paths.PathError) as said:
            paths.state_db_path()

    assert problems_cmd.run(_parse(["--json"]), now=T0) == 1, (
        "a broken setup (%s) must exit 1 -- 0 would tell the window nothing needs you" % broken)
    captured = capsys.readouterr()
    assert str(said.value) in captured.err, (
        "the setup's own message is not on stderr:\n%s" % captured.err)
    assert captured.out == "", "a failed run printed to stdout: %r" % captured.out


def test_zero_network(library, monkeypatch, capsys):
    populate(library)
    reached = []

    def recorder(what):
        def refuse_it(*args, **kwargs):
            reached.append(what)
            raise RuntimeError("the open-problems view reached the network: %s" % what)
        return refuse_it

    monkeypatch.setattr(socket.socket, "connect", recorder("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", recorder("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", recorder("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", recorder("socket.getaddrinfo"))

    library.open()
    rows = library.rows()
    library.close()
    assert len(rows) == 4, "the control: the lab lists its four problems"
    for argv in ([], ["--json"]):
        assert problems_cmd.run(_parse(argv), now=T0) == 0
    capsys.readouterr()
    assert reached == [], (
        "the view made %d network call(s): %s -- it is a read of the DB and the disk, and "
        "nothing else" % (len(reached), reached))


# -- ADVERSARY 2026-09-22 -------------------------------------------------------------------

@pytest.mark.parametrize("argv", [[], ["--json"]])
def test_an_unreadable_state_db_is_a_failure_said_as_one_and_left_exactly_as_it_is(
        library, capsys, argv):
    """ADVERSARY 2026-09-22 F3a + A1b. The view MOVED a corrupt DB aside -- at
    window startup, with no run lock -- then answered *"nothing needs you"* with
    exit 0, and the window emptied Needs you over it. ⛔ Never exit 0 with an
    empty list the view could not know was empty."""
    populate(library)
    path = library.data / "state.db"
    for tail in ("-wal", "-shm"):
        side = Path(str(path) + tail)
        if side.exists():
            side.unlink()
    path.write_bytes(b"this was never a database " * 100)
    before = snapshot(library.data)

    code = problems_cmd.run(_parse(argv), now=T0)
    captured = capsys.readouterr()
    assert code == 1, "an unreadable store answered exit %d -- the window reads 0 as *nothing " \
                      "needs you*" % code
    assert changed(before, snapshot(library.data)) == [], (
        "a READ moved or rewrote the store: %s" % changed(before, snapshot(library.data)))
    assert "left exactly as it is" in captured.err, captured.err
    if argv:
        said = [json.loads(line) for line in captured.out.splitlines()]
        assert len(said) == 1 and said[0]["type"] == "problems" and said[0]["ok"] is False, (
            "--json must end in ONE summary saying it failed, and list no episode: %r" % said)
        assert "left exactly as it is" in said[0]["error"], said[0]
    else:
        assert captured.out == "", "a failed view printed a list: %r" % captured.out


def test_a_file_renamed_by_case_only_is_found_under_the_name_the_disk_holds(lab):
    """ADVERSARY 2026-09-22 F15. The DB keeps the spelling it was given and the
    present-check matches subtitle names case-sensitively -- so a subtitle saved
    beside a case-only rename was never seen, and the episode asked for ever."""
    video = a_problem(lab, "Show - 12.mkv")
    renamed = video.with_name("SHOW - 12.mkv")
    os.rename(str(video), str(renamed))
    row = only(lab.rows())                              # the control: still listed
    assert row["name"] == renamed.name, (
        "a case-only rename is listed under the spelling the disk no longer holds: %r"
        % row["name"])
    renamed.with_name("SHOW - 12.ja.ass").write_text(u"[Script Info]\n", encoding="utf-8")
    assert lab.rows() == [], (
        "a subtitle beside a case-only rename is not seen -- the episode would ask for ever")


def test_a_legacy_row_is_never_handed_a_later_upload_of_the_same_name_and_size(lab):
    """ADVERSARY 2026-09-22 F11. A row 1.0.1 wrote carries no hash, so its file is
    found by name and size -- and a re-timed re-upload keeps BOTH (timestamps are
    fixed width). The re-upload was offered under the old row's verdict."""
    video = lab.video("Show - 13.mkv")
    name = "[Legacy] Show - 13 [JPN].ass"
    tried_at = lab.clock.now.timestamp()
    _gone, size = refuse(lab, video, name, 0.2, hashed=False, keep_file=False)
    gave_up(lab, video, 1)
    original = ("subtitle %s, tried against %s" % (name, video.name)).encode("utf-8")
    reupload = bytes(reversed(original))
    assert len(reupload) == size and reupload != original
    later = lab.cache.store(reupload, keep.download_name(name, "ja"))
    two_days = tried_at + 2 * 86400
    os.utime(str(later), (two_days, two_days))

    row = only(lab.rows())
    assert [t["path"] for t in row["tried_before"]] == [None], (
        "a file downloaded two days AFTER the refusal was offered as the file that was "
        "refused: %s" % row["tried_before"])

    kept = lab.cache.store(original, keep.download_name(name, "ja"))     # the refused one, back
    os.utime(str(kept), (tried_at, tried_at))
    row = only(lab.rows())
    assert [t["path"] for t in row["tried_before"]] == [str(kept)], (
        "with the refused file AND a later upload in the cache, the refused one must be "
        "found -- not an ambiguity, and never the upload: %s" % row["tried_before"])


def test_a_config_that_spells_the_language_jpn_finds_every_problem(library, capsys):
    """ADVERSARY 2026-09-22 F1, the view half. A run records its rows under the
    RESOLVED tag (`jpn` is `ja`); asking the DB with the raw setting found nothing,
    for anybody who wrote the spelling hato's own error message suggests."""
    pick, _past, _hard, _broken = populate(library)
    config_file = library.root / "config.toml"
    config_file.write_text('lang = "jpn"\n' + library.config_text(), encoding="utf-8")
    assert problems_cmd.run(_parse(["--json"]), now=T0) == 0
    said = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    videos = [o for o in said if o["type"] == "video"]
    assert pick.name in names(videos) and len(videos) == 4, (
        "`lang = \"jpn\"` listed %s -- every remembered problem vanished" % sorted(names(videos)))
    assert said[-1]["lang"] == "ja", "the summary must name the tag the rows are kept under"


def test_a_refusal_with_nothing_tried_is_trouble_with_its_reason_never_a_wait(library, capsys):
    """ADVERSARY 2026-09-22 F20. A name with no episode number is refused before
    any download and recorded as a soft negative. Read back as NOT_FOUND it was
    filed under *not on jimaku yet* -- a person waited on jimaku when the fix is a
    rename. As a pick it would read *"the timing did not hold"* over nothing."""
    from hato import episodes
    video = library.video("Show.mkv")
    library.db.record_not_found(video_hash=cache.video_hash(video), video_path=str(video),
                                lang="ja", kind="soft", jimaku_entry=ENTRY,
                                reason=episodes.NO_EPISODE)
    library.close()
    assert problems_cmd.run(_parse([]), now=T0) == 0
    found = sections(capsys.readouterr().out)
    assert not [h for h in found if h.startswith(("not on jimaku yet", "needs a pick"))], (
        "a video with no episode number was filed as a wait or a pick: %r" % found)
    trouble = section(found, "had a problem")
    assert len(trouble) == 1 and video.name in trouble[0], trouble
    assert "No episode number was read from the video" in trouble[0], (
        "the trouble row does not say what is wrong -- the fix is a rename:\n%s" % trouble[0])


def test_a_trouble_reason_carrying_the_engine_word_is_said_in_plain_words(library, capsys):
    """⛔ The plain list never says *refused* -- including inside a reason it now
    prints. The same rule as the window's `gui/app.safe`."""
    video = library.video("Show - 15.mkv")
    went_wrong(library, video, "[G] Show - 15.ass")
    library.db.record_attempt(
        video_hash=cache.video_hash(video), video_path=str(video), lang="ja",
        jimaku_entry=ENTRY, jimaku_filename="[G] Show - 15 v2.ass", jimaku_size=4096,
        jimaku_last_modified=LAST_MODIFIED, subtitle_hash=None, outcome=state.ERROR,
        reason="jimaku refused the download: HTTP 403")
    library.close()
    assert problems_cmd.run(_parse([]), now=T0) == 0
    text = capsys.readouterr().out
    assert video.name in text, "the control: the trouble row is listed:\n%s" % text
    assert re.search(r"(?i)refus", text) is None and "the timing did not hold" in text, text
