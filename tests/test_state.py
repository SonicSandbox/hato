# -*- coding: utf-8 -*-
"""
Step 1b -- the state DB through its one accessor, and the run lock
(spec/02-data-model.md §The state DB; spec/06-edge-cases.md §7 and §9; RUNBOOK 1b).

The canonicity table, at the only level this layer can see it:

    DB says synced, file gone      the row still names the kept original, so the
                                   loop can re-sync with zero network
    file there, DB knows nothing   backfilled -- one row, however often asked
    DB and disk agree              reading writes nothing
    DB deleted                     everything still works
    DB corrupt                     moved aside, started fresh, said in one sentence

Plus: refusals per (video x candidate), negative expiry at 1 and 30 days, the
blacklist `--force` cannot override, a reason on every non-confident row, WAL,
one accessor, and the run lock.

What this suite STRUCTURALLY cannot cover: the filesystem half of that table --
whether hato really re-syncs, skips or re-fetches. The DB never looks at the
disk; the fetch loop does (RUNBOOK 4b), and those checks are its suite's.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hato import cache, paths, runlock, state
from hato.commands import blacklist as blacklist_cmd
from hato.commands import state as state_cmd

V1 = "v1-" + "a" * 64
V2 = "v1-" + "b" * 64


class Clock(object):
    """An injectable `now`. Starts at a fixed moment; moves only when told."""

    def __init__(self, start=None):
        self.now = start or datetime(2026, 9, 17, 3, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def db(tmp_path, clock):
    handle = state.StateDB(tmp_path / "state.db", now=clock)
    yield handle
    handle.close()


def candidate(**change):
    c = {"jimaku_entry": 11446, "jimaku_filename": "[Haruhana] Sousou no Frieren - 29 [JPN].ass",
         "jimaku_size": 49646, "jimaku_last_modified": "2026-09-01T12:00:00.123Z"}
    c.update(change)
    return c


def attempt(db, video_hash=V1, outcome=state.REFUSED, reason="timing did not hold: 61% match",
            lang="ja", **change):
    fields = {"video_hash": video_hash, "video_path": "D:/Anime/Frieren S2/Frieren S2 - 01.mkv",
              "lang": lang, "subtitle_hash": "c" * 64, "outcome": outcome, "reason": reason,
              "jimaku_entry": 11446, "jimaku_filename": candidate()["jimaku_filename"],
              "jimaku_size": 49646, "jimaku_last_modified": "2026-09-01T12:00:00.123Z"}
    fields.update(change)
    return db.record_attempt(**fields)


def refused(db, video_hash=V1, lang="ja", **change):
    c = candidate(**change)
    return db.refused(video_hash, lang, c["jimaku_entry"], c["jimaku_filename"],
                      c["jimaku_size"], c["jimaku_last_modified"])


def confident(db, video_hash=V1, **change):
    fields = {"reason": "", "output_path": "D:/Anime/Frieren S2/Frieren S2 - 01.ja.ass"}
    fields.update(change)
    return attempt(db, video_hash=video_hash, outcome=state.CONFIDENT, **fields)


def accessor_refuses(record, why="the row was recorded -- nothing refused it"):
    """Run `record`. -> the ValueError the ACCESSOR raised.

    An IntegrityError means the accessor let the row through and only the
    schema's CHECK stopped it: a constraint error where a sentence was owed."""
    try:
        record()
    except ValueError as exc:
        return exc
    except sqlite3.IntegrityError as exc:
        pytest.fail("the accessor let this row through and only the schema's CHECK stopped it "
                    "(%s) -- the person running hato gets a constraint error, not a sentence" % exc)
    pytest.fail(why)


def opens_without_crashing(path, clock, what):
    try:
        return state.StateDB(path, now=clock)
    except Exception as exc:
        pytest.fail("%s crashed the run (%s: %s) -- the DB is advisory: set it aside or keep no "
                    "state, say so in one sentence, and carry on" % (what, type(exc).__name__, exc))


# -- refusals: per (video x candidate) ------------------------------------------------

def test_a_refused_candidate_is_remembered_for_that_video(db):
    assert refused(db) is False, "a fresh DB already reports a refusal"
    attempt(db)
    assert refused(db) is True


def test_a_refusal_is_per_video_never_a_blacklist_of_the_subtitle(db):
    attempt(db, video_hash=V1)
    assert refused(db, video_hash=V1) is True
    assert refused(db, video_hash=V2) is False, (
        "a subtitle refused against one video reads as refused for ANOTHER video. Refusals "
        "are keyed per (video x subtitle): a wrong episode guess must not lock out the file "
        "that is right for a different video")


@pytest.mark.parametrize("change", [
    {"jimaku_size": 49647},
    {"jimaku_last_modified": "2026-09-02T00:00:00.000Z"},
    {"jimaku_filename": "[Haruhana] Sousou no Frieren - 29 [JPN] v2.ass"},
    {"jimaku_entry": 11447},
])
def test_a_reuploaded_or_different_file_is_a_new_candidate(db, change):
    attempt(db)
    assert refused(db) is True
    assert refused(db, **change) is False, "%s makes a different candidate, but it reads as refused" % change


def test_a_refusal_is_per_language(db):
    attempt(db, lang="ja")
    assert refused(db, lang="ja") is True
    assert refused(db, lang="en") is False
    assert refused(db, lang="JA") is True, (
        "a refusal recorded for 'ja' is not found for 'JA' -- language codes must compare case-blind")


def test_a_candidate_listed_without_a_size_or_date_is_still_found(db):
    attempt(db, jimaku_size=None, jimaku_last_modified=None)
    assert refused(db, jimaku_size=None, jimaku_last_modified=None) is True, (
        "a refusal whose candidate had no size or last_modified cannot be found again -- in SQL "
        "NULL never equals NULL -- so that file is downloaded again on every run")
    assert refused(db) is False


def test_the_entry_matches_whether_passed_as_a_number_or_as_text(db):
    attempt(db, jimaku_entry=11446)
    assert refused(db, jimaku_entry="11446") is True


def test_a_later_confident_verdict_clears_a_refusal_but_an_error_does_not(db):
    attempt(db)
    attempt(db, outcome=state.ERROR, reason="download returned HTTP 500")
    assert refused(db) is True, "an ERROR is not a verdict on the timing -- the refusal stands"
    confident(db)
    assert refused(db) is False


# -- what the accessor refuses to record -------------------------------------------------

@pytest.mark.parametrize("outcome", [state.REFUSED, state.ERROR])
@pytest.mark.parametrize("reason", ["", "   ", None])
def test_a_non_confident_row_without_a_reason_is_refused(db, outcome, reason):
    err = accessor_refuses(lambda: attempt(db, outcome=outcome, reason=reason),
                           "a %s row with the reason %r was recorded" % (outcome, reason))
    assert outcome in str(err) and "reason" in str(err), str(err)
    assert db.stats()["rows"][outcome] == 0


def test_a_confident_row_needs_no_reason_but_must_name_the_file_it_wrote(db):
    confident(db)
    err = accessor_refuses(lambda: confident(db, output_path=None),
                           "a CONFIDENT row with no output_path was recorded -- CONFIDENT is not WRITTEN")
    assert "output_path" in str(err)
    assert db.stats()["rows"][state.CONFIDENT] == 1


def test_an_unknown_outcome_is_refused(db):
    err = accessor_refuses(lambda: attempt(db, outcome="MAYBE"), "an outcome called MAYBE was recorded")
    assert "MAYBE" in str(err)
    accessor_refuses(lambda: attempt(db, outcome="confident"),
                     "'confident' was recorded -- the outcomes are the spec's words, exactly")


def test_a_not_found_goes_through_record_not_found_so_it_gets_a_retry_date(db):
    err = accessor_refuses(lambda: attempt(db, outcome=state.NOT_FOUND, reason="nothing there"),
                           "a NOT_FOUND was recorded with no kind and no retry date")
    assert "record_not_found" in str(err)


@pytest.mark.parametrize("missing", [{"jimaku_entry": None}, {"jimaku_filename": None},
                                     {"jimaku_filename": ""}])
def test_a_refusal_must_name_its_candidate_so_no_track_can_never_be_one(db, missing):
    err = accessor_refuses(
        lambda: attempt(db, reason="no subtitle track in the video", **missing),
        "a refusal naming no candidate (%s) was recorded -- refused() can never find it again, "
        "and 'no subtitle track' is a skip, never a refusal" % missing)
    assert "candidate" in str(err)
    assert db.stats()["rows"][state.REFUSED] == 0


def test_the_schema_itself_refuses_what_the_accessor_refuses(db):
    """Past the accessor, on purpose: the constraint is what still holds if a later
    edit adds a write path that forgets the checks."""
    raw = sqlite3.connect(str(db.path))
    stamp = "2026-09-17T03:00:00.000000+00:00"

    def refuses(sql, what):
        try:
            raw.execute(sql, (stamp,))
        except sqlite3.IntegrityError:
            return
        pytest.fail("the schema accepted %s" % what)

    try:
        refuses("INSERT INTO attempts (video_hash, lang, jimaku_entry, jimaku_filename, outcome, "
                "reason, attempted_at) VALUES ('v1-x', 'ja', 1, 'a.ass', 'REFUSED', '   ', ?)",
                "a REFUSED row whose reason is blank")
        refuses("INSERT INTO attempts (video_hash, lang, outcome, reason, attempted_at) "
                "VALUES ('v1-x', 'ja', 'CONFIDENT', '', ?)", "a CONFIDENT row with no output_path")
        refuses("INSERT INTO attempts (video_hash, lang, outcome, reason, attempted_at) "
                "VALUES ('v1-x', 'ja', 'REFUSED', 'no subtitle track', ?)",
                "a REFUSED row naming no candidate")
    finally:
        raw.close()


# -- the negative cache -------------------------------------------------------------------

def test_a_soft_negative_stands_for_exactly_1_day(db, clock):
    """⭐ AMENDED 2026-09-17 (Sonic), 7 -> 1: a just-aired episode is exactly the
    case to keep checking, and it costs one `files` call a day for a show with a gap."""
    start = clock.now
    retry = db.record_not_found(video_hash=V1, video_path="D:/A/Show - 07.mkv", lang="ja",
                                kind="soft", reason="jimaku 11446 has no file for episode 7",
                                jimaku_entry=11446)
    assert retry == start + timedelta(days=1), "a soft negative retries after %s, not 1 day" % (retry - start)
    clock.advance(days=1, seconds=-1)
    assert db.negative(V1, "ja") == ("soft", start + timedelta(days=1),
                                     "jimaku 11446 has no file for episode 7")
    clock.advance(seconds=1)
    assert db.negative(V1, "ja") is None, "a soft negative still stands at its 1-day retry date"


def test_the_retry_windows_are_configurable_in_one_place(tmp_path, clock):
    with state.StateDB(tmp_path / "state.db", now=clock, soft_days=3, hard_days=90) as db:
        start = clock.now
        soft = db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="soft",
                                   reason="no file for episode 7 yet", jimaku_entry=11446)
        hard = db.record_not_found(video_hash=V2, video_path=None, lang="ja", kind="hard",
                                   reason="no jimaku entry matched")
        assert (soft, hard) == (start + timedelta(days=3), start + timedelta(days=90))
        assert db.stats()["retry_days"] == {"soft": 3, "hard": 90}


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "7"])
def test_a_retry_window_that_would_re_ask_every_run_is_refused(tmp_path, bad):
    with pytest.raises(ValueError) as err:
        state.StateDB(tmp_path / "state.db", soft_days=bad)
    assert "soft_days" in str(err.value), str(err.value)


def test_a_hard_negative_stands_for_exactly_30_days(db, clock):
    start = clock.now
    retry = db.record_not_found(video_hash=V1, video_path="D:/A/Random.Show.2019 - 01.mkv",
                                lang="ja", kind="hard", reason="no jimaku entry matched")
    assert retry == start + timedelta(days=30), "a hard negative retries after %s, not 30 days" % (retry - start)
    clock.advance(days=30, seconds=-1)
    assert db.negative(V1, "ja") == ("hard", start + timedelta(days=30), "no jimaku entry matched")
    clock.advance(seconds=1)
    assert db.negative(V1, "ja") is None, "a hard negative still stands at its 30-day retry date"


def test_the_retry_constants_are_the_specs():
    assert (state.SOFT_DAYS, state.HARD_DAYS) == (1, 30)


def test_a_negative_is_per_video_and_language(db):
    db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="hard", reason="no entry")
    assert db.negative(V1, "ja") is not None
    assert db.negative(V2, "ja") is None and db.negative(V1, "en") is None


def test_anything_tried_since_supersedes_a_negative(db, clock):
    db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="soft",
                        reason="no file for episode 1 yet", jimaku_entry=11446)
    assert db.negative(V1, "ja") is not None
    clock.advance(days=1)
    attempt(db)                                  # a file turned up, and was tried
    assert db.negative(V1, "ja") is None, (
        "a negative still stands after a candidate was tried for the video -- anything tried "
        "since supersedes it")


@pytest.mark.parametrize("kind, entry, words", [
    ("soft", None, "name the entry"),
    ("hard", 11446, "soft negative"),
    ("later", None, "unknown negative kind"),
])
def test_a_negative_of_the_wrong_shape_is_refused(db, kind, entry, words):
    err = accessor_refuses(
        lambda: db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind=kind,
                                    reason="nothing there", jimaku_entry=entry),
        "a %r negative naming entry %r was recorded -- soft (1 day) and hard (30 days) could "
        "then be swapped" % (kind, entry))
    assert words in str(err), str(err)


def test_a_negative_needs_a_reason(db):
    accessor_refuses(lambda: db.record_not_found(video_hash=V1, video_path=None, lang="ja",
                                                 kind="hard", reason="  "),
                     "a NOT_FOUND with a blank reason was recorded")


def test_the_clock_must_be_timezone_aware(tmp_path):
    naive = state.StateDB(tmp_path / "state.db", now=lambda: datetime(2026, 9, 17, 3, 0))
    try:
        err = accessor_refuses(
            lambda: naive.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="hard",
                                           reason="no entry"),
            "a naive now() was accepted -- expiry would silently run on the machine's local time")
        assert "timezone-aware" in str(err)
    finally:
        naive.close()


# -- the blacklist (spec/02-data-model.md §Question 3) --------------------------------------

def test_a_blacklisted_video_round_trips_and_carries_why(db, clock):
    added = db.blacklist_add(V1, video_path="D:/A/Concert.mkv", note="concert, no dialogue")
    assert added == (V1, "D:/A/Concert.mkv", clock.now, "concert, no dialogue")
    assert db.blacklisted(V1) == added
    assert db.blacklist_list() == [added]
    assert db.blacklist_remove(V1) is True
    assert db.blacklisted(V1) is None and db.blacklist_list() == []
    assert db.blacklist_remove(V1) is False, "removing a row that is not there is not a removal"


def test_the_blacklist_is_keyed_on_the_hash_so_it_survives_a_rename(db):
    db.blacklist_add(V1, video_path="D:/A/Concert.mkv")
    assert db.blacklisted(V1) is not None
    assert db.blacklisted(V2) is None, "every video read as blacklisted"
    renamed = db.blacklist_add(V1, video_path="E:/Moved/Concert.mkv")
    assert renamed.video_path == "E:/Moved/Concert.mkv", "the advisory path never caught up"
    assert len(db.blacklist_list()) == 1, "a rename made a second row"


def test_adding_twice_keeps_the_moment_the_person_said_so(db, clock):
    first = clock.now
    db.blacklist_add(V1, video_path="D:/A/Concert.mkv", note="no dialogue")
    clock.advance(days=40)
    again = db.blacklist_add(V1)
    assert again.added_at == first, "re-adding moved added_at to %s" % again.added_at
    assert again.note == "no dialogue", "an empty note wiped the reason that was there"
    assert again.video_path == "D:/A/Concert.mkv"


def test_force_does_not_override_a_blacklist_but_does_override_hatos_own_judgement(db, clock):
    """⚠ --force overrules what HATO decided. A blacklist is what the PERSON decided."""
    db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="soft",
                        reason="no file for episode 7 yet", jimaku_entry=11446)
    assert db.skip_reason(V1, "ja").kind == "negative"
    assert db.skip_reason(V1, "ja", force=True) is None, (
        "--force did not clear a negative hato recorded itself")

    db.blacklist_add(V1, video_path="D:/A/Concert.mkv", note="concert, no dialogue")
    for force in (False, True):
        skip = db.skip_reason(V1, "ja", force=force)
        assert skip is not None and skip.kind == "blacklist", (
            "--force=%r skipped past the blacklist. Force overrules the TOOL's judgement; a "
            "blacklist is the PERSON's instruction, and `hato blacklist --remove` is the only "
            "way back (spec/02-data-model.md §Question 3)" % force)
        assert "concert, no dialogue" in skip.reason

    assert db.blacklist_remove(V1) is True
    assert db.skip_reason(V1, "ja", force=True) is None


def test_a_blacklist_row_prevents_work_and_can_never_cause_any(db):
    before = db.stats()
    db.blacklist_add(V1, video_path="D:/A/Concert.mkv")
    after = db.stats()
    assert after["rows"] == before["rows"], "blacklisting recorded an attempt"
    assert after["present"] == before["present"], "blacklisting backfilled a present row"
    assert after["blacklisted"] == 1
    assert db.synced(V1, "ja") is None and db.negative(V1, "ja") is None, (
        "the blacklist answered a question about a FILE -- it may only ever prevent work")
    assert db.skip_reason(V2, "ja") is None, "a video nobody blacklisted was skipped"


def test_a_blacklist_row_needs_a_video_hash(db):
    for bad in (None, "", "   "):
        accessor_refuses(lambda: db.blacklist_add(bad),
                         "a blacklist row with video_hash %r was recorded -- it would match "
                         "nothing, for ever, invisibly" % (bad,))


def test_an_older_db_gains_the_blacklist_table_and_keeps_its_rows(tmp_path, clock):
    """⚠ Schema 1 shipped without it. Opening must migrate, never start fresh."""
    path = tmp_path / "state.db"
    with state.StateDB(path, now=clock) as db:
        attempt(db)
    raw = sqlite3.connect(str(path))
    try:
        raw.execute("DROP TABLE blacklist")
        raw.execute("PRAGMA user_version = 1")
        raw.commit()
    finally:
        raw.close()

    with state.StateDB(path, now=clock) as db:
        assert db.persistent and db.notes == [], (
            "an older DB was treated as unreadable instead of migrated: %s" % db.notes)
        assert db.stats()["rows"][state.REFUSED] == 1, "migrating lost the rows already there"
        assert db.blacklist_list() == []
        db.blacklist_add(V1, video_path="D:/A/Concert.mkv")
        assert db.blacklisted(V1) is not None
    assert sqlite3.connect(str(path)).execute("PRAGMA user_version").fetchone()[0] == 2


# -- synced and the canonicity table ------------------------------------------------------

def test_synced_is_the_latest_confident_row(db):
    assert db.synced(V1, "ja") is None
    attempt(db)
    confident(db, jimaku_filename="b.ja.ass", kept_path="C:/subs/b.ja.ass")
    confident(db, jimaku_filename="c.ja.ass", kept_path="C:/subs/c.ja.ass")
    attempt(db, jimaku_filename="d.ass")          # a later refusal does not hide it
    row = db.synced(V1, "ja")
    assert (row.outcome, row.jimaku_filename, row.kept_path) == (state.CONFIDENT, "c.ja.ass", "C:/subs/c.ja.ass")
    assert row.jimaku_entry == 11446 and row.attempted_at.tzinfo is not None
    assert db.synced(V1, "en") is None and db.synced(V2, "ja") is None


def test_canonicity__db_says_synced_and_the_file_is_gone__the_row_still_names_the_kept_original(tmp_path, db):
    media, subs = tmp_path / "media", tmp_path / "subs"
    media.mkdir()
    subs.mkdir()
    output = media / "Frieren S2 - 01.ja.ass"
    kept = subs / "[Haruhana] Sousou no Frieren - 29 [JPN].ja.ass"
    output.write_bytes(b"the synced copy")
    kept.write_bytes(b"the original")
    confident(db, output_path=output, kept_path=kept)
    output.unlink()                                # the user deleted the synced file
    row = db.synced(V1, "ja")
    assert row is not None, (
        "the DB hid its row because the file is gone. It must never check the disk: without the "
        "row the fetch loop cannot re-sync from the kept original, and pays the network instead")
    assert (row.output_path, row.kept_path) == (str(output), str(kept))
    assert list(media.iterdir()) == [], "the DB wrote into the media folder"
    assert kept.read_bytes() == b"the original"


def test_canonicity__db_says_synced_with_no_kept_original__the_loop_has_nothing_to_resync_from(db):
    confident(db, kept_path=None)
    assert db.synced(V1, "ja").kept_path is None


def test_canonicity__file_present_and_db_knows_nothing__backfilled_once_however_often(db):
    assert db.synced(V1, "ja") is None and db.negative(V1, "ja") is None
    for _ in range(3):
        db.record_present(V1, "D:/Anime/Show - 01.mkv", "ja")
    assert db.stats()["present"] == 1, "the backfill grew the DB on every call"
    db.record_present(V1, "D:/Anime/Show - 01.mkv", "en")
    assert db.stats()["present"] == 2


def test_canonicity__db_and_disk_agree__reading_writes_nothing(db):
    confident(db)
    db.record_not_found(video_hash=V2, video_path=None, lang="ja", kind="hard", reason="no entry")
    wal = Path(str(db.path) + "-wal")

    def on_disk():
        return (db.path.stat().st_size, wal.stat().st_size if wal.exists() else 0)

    before, sizes = db.stats(), on_disk()
    for _ in range(25):
        db.synced(V1, "ja")
        db.negative(V2, "ja")
        refused(db)
        db.stats()
    assert db.stats() == before
    assert on_disk() == sizes, "reading the DB wrote to it"


def test_canonicity__db_deleted__everything_still_works(tmp_path, clock):
    path = tmp_path / "state.db"
    with state.StateDB(path, now=clock) as first:
        attempt(first)
        first.record_not_found(video_hash=V2, video_path=None, lang="ja", kind="hard", reason="no entry")
    for leftover in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if leftover.exists():
            leftover.unlink()
    with state.StateDB(path, now=clock) as again:
        assert again.notes == [] and again.persistent
        assert refused(again) is False and again.negative(V2, "ja") is None
        assert again.synced(V1, "ja") is None
        assert again.stats()["rows"] == dict.fromkeys(state.OUTCOMES, 0)
        attempt(again)
        assert refused(again) is True


def test_a_renamed_video_keeps_its_rows_and_a_replaced_one_starts_fresh(tmp_path, db):
    media = tmp_path / "media"
    media.mkdir()
    video = media / "Frieren S2 - 01.mkv"
    body = bytearray(os.urandom(512 * 1024))
    video.write_bytes(bytes(body))
    before = cache.video_hash(video)
    attempt(db, video_hash=before)
    confident(db, video_hash=before, jimaku_filename="b.ja.ass")

    renamed = media / "[Group] Sousou no Frieren S2 - 01 [1080p].mkv"
    os.replace(str(video), str(renamed))
    after = cache.video_hash(renamed)
    assert after == before
    assert refused(db, video_hash=after) is True and db.synced(after, "ja") is not None

    body[100] ^= 0xFF                              # a different rip
    renamed.write_bytes(bytes(body))
    other = cache.video_hash(renamed)
    assert other != before
    assert refused(db, video_hash=other) is False and db.synced(other, "ja") is None


# -- corruption, and every other way the store can be unusable ------------------------------

def _asides(folder):
    return [p for p in folder.iterdir() if p.name.startswith("state.db.corrupt-")]


def test_a_corrupt_db_is_moved_aside_and_a_fresh_one_started_in_one_sentence(tmp_path, clock):
    path = tmp_path / "state.db"
    garbage = b"this was never a database " * 100
    path.write_bytes(garbage)
    db = opens_without_crashing(path, clock, "a corrupt state DB")
    try:
        assert len(db.notes) == 1, db.notes
        note = db.notes[0]
        asides = _asides(tmp_path)
        assert len(asides) == 1 and asides[0].read_bytes() == garbage, asides
        assert asides[0].name in note and "moved aside" in note and "\n" not in note, note
        assert db.persistent, "a corrupt DB that could be moved aside must be replaced by a real one"
        attempt(db)
        assert refused(db) is True
    finally:
        db.close()
    raw = sqlite3.connect(str(path))
    try:
        assert raw.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert raw.execute("PRAGMA user_version").fetchone() == (state.SCHEMA_VERSION,)
    finally:
        raw.close()


def test_damaged_pages_behind_a_valid_header_are_caught_at_open(tmp_path, clock):
    path = tmp_path / "state.db"
    with state.StateDB(path, now=clock) as db:
        for i in range(400):
            attempt(db, jimaku_filename="candidate %04d.ass" % i, reason="timing did not hold " * 10)
    data = bytearray(path.read_bytes())
    assert len(data) > 12 * 4096, "the fixture DB is too small to damage past its first page"
    for offset in range(2 * 4096, len(data), 3 * 4096):
        data[offset:offset + 256] = b"\xff" * 256
    path.write_bytes(bytes(data))
    db = opens_without_crashing(path, clock, "a state DB with damaged pages")
    try:
        assert len(db.notes) == 1 and "moved aside" in db.notes[0], (
            "damaged pages were not noticed at open, so they would surface mid-run: %r" % db.notes)
        assert refused(db) is False
    finally:
        db.close()
    assert len(_asides(tmp_path)) == 1


def test_a_db_written_by_a_newer_hato_is_left_untouched(tmp_path, clock):
    path = tmp_path / "state.db"
    raw = sqlite3.connect(str(path))
    raw.execute("CREATE TABLE from_the_future (x)")
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    raw.close()
    before = path.read_bytes()
    db = opens_without_crashing(path, clock, "a DB written by a newer hato")
    try:
        assert db.persistent is False and len(db.notes) == 1 and "newer hato" in db.notes[0], (
            "a DB written by a newer hato must be left untouched while this run keeps its state in "
            "memory -- got persistent=%s, notes=%r" % (db.persistent, db.notes))
        attempt(db)
        assert refused(db) is True                 # this run still works, in memory
    finally:
        db.close()
    assert path.read_bytes() == before, "a newer hato's DB was modified"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.db"]


def test_a_corrupt_db_that_cannot_be_moved_aside_does_not_crash_the_run(tmp_path, clock, monkeypatch):
    path = tmp_path / "state.db"
    garbage = b"garbage " * 500
    path.write_bytes(garbage)
    real_replace = os.replace

    def held_open_elsewhere(src, dst, *args, **kwargs):
        if os.path.abspath(str(src)) == os.path.abspath(str(path)):
            raise PermissionError(32, "The process cannot access the file because it is being "
                                      "used by another process")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", held_open_elsewhere)
    db = opens_without_crashing(path, clock, "a corrupt state DB that cannot be moved aside")
    try:
        assert db.persistent is False
        assert len(db.notes) == 1 and "could not be moved aside" in db.notes[0], db.notes
        attempt(db)
        assert refused(db) is True
    finally:
        db.close()
    assert path.read_bytes() == garbage


class _MalformedOnce(object):
    """A connection whose next statement finds the file corrupt, as a disk failing
    mid-run would. Everything after that is the real connection."""

    def __init__(self, conn):
        self._conn, self.tripped = conn, False

    def execute(self, *args):
        if not self.tripped:
            self.tripped = True
            raise sqlite3.DatabaseError("database disk image is malformed")
        return self._conn.execute(*args)

    def close(self):
        self._conn.close()


def test_corruption_found_mid_run_is_recovered_and_the_write_still_lands(tmp_path, clock):
    path = tmp_path / "state.db"
    with state.StateDB(path, now=clock) as db:
        attempt(db, video_hash=V2)
        db._conn = _MalformedOnce(db._conn)
        try:
            attempt(db)
        except sqlite3.DatabaseError as exc:
            pytest.fail("corruption found mid-run crashed the run (%s) -- it must be set aside, "
                        "a fresh DB started, and the write tried again" % exc)
        assert db._conn.__class__ is sqlite3.Connection, "the corrupt connection is still in use"
        assert len(db.notes) == 1 and "moved aside" in db.notes[0], db.notes
        assert refused(db) is True, "the write that met the corruption was lost"
        assert refused(db, video_hash=V2) is False, "the old rows should have gone aside with the file"
    assert len(_asides(tmp_path)) == 1


def test_the_db_is_in_WAL_mode_and_carries_its_schema_version(db):
    assert db.journal_mode == "wal", (
        "the state DB is in %r mode, not WAL -- a reader (hato state --stat) would block the run"
        % db.journal_mode)
    raw = sqlite3.connect(str(db.path))
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone() == ("wal",), (
            "the state DB is not in WAL mode -- a reader (hato state --stat) would block the run")
        assert raw.execute("PRAGMA user_version").fetchone() == (state.SCHEMA_VERSION,)
    finally:
        raw.close()


def test_the_default_db_is_in_the_redirected_per_user_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    with state.StateDB() as db:
        assert db.path == tmp_path / "root" / "state.db"
    assert (tmp_path / "root" / "state.db").exists()


# -- stats ---------------------------------------------------------------------------------

def test_stats_counts_rows_by_outcome_and_lists_the_next_retries_soonest_first(db, clock):
    start = clock.now
    attempt(db)
    attempt(db, jimaku_filename="b.ass")
    attempt(db, outcome=state.ERROR, reason="download returned HTTP 500")
    confident(db, video_hash=V2)
    db.record_not_found(video_hash="v1-" + "1" * 64, video_path="D:/A/Show - 10.mkv", lang="ja",
                        kind="hard", reason="no jimaku entry matched")
    db.record_not_found(video_hash="v1-" + "2" * 64, video_path="D:/A/Show - 11.mkv", lang="ja",
                        kind="soft", reason="no file for episode 11", jimaku_entry=11446)
    clock.now = start - timedelta(days=8)          # expired by `start`
    db.record_not_found(video_hash="v1-" + "3" * 64, video_path="D:/A/Show - 12.mkv", lang="ja",
                        kind="soft", reason="stale", jimaku_entry=11446)
    clock.now = start
    superseded = "v1-" + "4" * 64                  # something was tried since
    db.record_not_found(video_hash=superseded, video_path="D:/A/Show - 13.mkv", lang="ja",
                        kind="soft", reason="superseded", jimaku_entry=11446)
    attempt(db, video_hash=superseded)
    db.record_present(V1, "D:/A/Show - 01.mkv", "ja")

    found = db.stats()
    assert found["rows"] == {state.CONFIDENT: 1, state.REFUSED: 3, state.ERROR: 1, state.NOT_FOUND: 4}
    assert found["present"] == 1
    assert found["negatives_active"] == 2, (
        "stats counts %d negatives as waiting where only Show - 10 and Show - 11 still stand -- an "
        "expired or superseded one is listed: %s"
        % (found["negatives_active"], [r["video_path"] for r in found["next_retries"]]))
    assert [(r["kind"], r["retry_after"], r["video_path"]) for r in found["next_retries"]] == [
        ("soft", start + timedelta(days=1), "D:/A/Show - 11.mkv"),
        ("hard", start + timedelta(days=30), "D:/A/Show - 10.mkv")]
    assert (found["journal_mode"], found["persistent"], found["notes"]) == ("wal", True, [])


def _state_parse(argv):
    parser = argparse.ArgumentParser(prog="hato state")
    state_cmd.register(parser)
    return parser.parse_args(argv)


def test_the_state_command_has_the_shape_the_cli_loads():
    first = state_cmd.__doc__.strip().splitlines()[0]
    assert first.startswith("Show what the state DB remembers"), first
    with pytest.raises(SystemExit):
        _state_parse([])


def test_state_stat_prints_counts_by_outcome_and_the_next_retry_dates(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    with state.StateDB(now=Clock(datetime.now(timezone.utc))) as db:
        attempt(db)
        attempt(db, outcome=state.ERROR, reason="download returned HTTP 500")
        confident(db, video_hash=V2)
        hard = db.record_not_found(video_hash="v1-" + "2" * 64, lang="ja", kind="hard",
                                   video_path="D:/Anime/Random.Show.2019 - 01.mkv",
                                   reason="no jimaku entry matched")
        soft = db.record_not_found(video_hash="v1-" + "1" * 64, lang="ja", kind="soft",
                                   video_path=u"D:/Anime/葬送のフリーレン - 07.mkv",
                                   reason="jimaku 11446 has no file for episode 7", jimaku_entry=11446)
        truth = db.stats()

    assert state_cmd.run(_state_parse(["--stat"])) == 0
    text = capsys.readouterr().out
    line = [l for l in text.splitlines() if l.startswith("attempts")]
    assert len(line) == 1, text
    for outcome, count in truth["rows"].items():
        assert "%d %s" % (count, outcome) in line[0], line[0]
    soft_at = soft.astimezone().strftime("%Y-%m-%d %H:%M")
    hard_at = hard.astimezone().strftime("%Y-%m-%d %H:%M")
    assert soft_at in text, "the soft negative's retry date %s is not shown:\n%s" % (soft_at, text)
    assert hard_at in text, "the hard negative's retry date %s is not shown:\n%s" % (hard_at, text)
    assert text.index(soft_at) < text.index(hard_at), "the soonest retry must come first"
    assert u"葬送のフリーレン - 07.mkv" in text and "jimaku 11446 has no file for episode 7" in text

    assert state_cmd.run(_state_parse(["--stat", "--json"])) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["ok"] is True and shown["rows"] == truth["rows"]
    assert [datetime.fromisoformat(r["retry_after"]) for r in shown["next_retries"]] == [soft, hard]


def test_state_stat_with_no_db_says_so_and_creates_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    assert state_cmd.run(_state_parse(["--stat"])) == 0
    text = capsys.readouterr().out
    assert not (tmp_path / "root").exists(), (
        "`hato state --stat` created a state DB where there was none:\n%s" % text)
    assert "none yet" in text, text


def _blacklist_parse(argv):
    parser = argparse.ArgumentParser(prog="hato blacklist")
    blacklist_cmd.register(parser)
    return parser.parse_args(argv)


def _video(folder, name="Concert - 06.mkv", body=b"not really a video, but it hashes"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(body)
    return path


def test_the_blacklist_command_adds_lists_and_removes_one_video(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    video = _video(tmp_path / "Anime")

    assert blacklist_cmd.run(_blacklist_parse([str(video), "--note", "concert, no dialogue"])) == 0
    text = capsys.readouterr().out
    assert "blacklisted" in text and video.name in text and "concert, no dialogue" in text
    assert "--force" in text, "the one thing a person must know is that --force will not undo it"

    assert blacklist_cmd.run(_blacklist_parse(["--list"])) == 0
    listed = capsys.readouterr().out
    assert str(video) in listed and "concert, no dialogue" in listed

    shown = _json_out(blacklist_cmd, ["--list", "--json"], capsys)
    assert [r["video_path"] for r in shown["blacklist"]] == [str(video)]
    assert shown["blacklist"][0]["video_hash"] == cache.video_hash(video)

    assert blacklist_cmd.run(_blacklist_parse(["--remove", str(video)])) == 0
    assert "removed" in capsys.readouterr().out
    assert _json_out(blacklist_cmd, ["--list", "--json"], capsys)["blacklist"] == []


def test_the_blacklist_command_finds_the_video_again_after_a_rename(tmp_path, monkeypatch, capsys):
    """The hash is the key, so the row is still the same row under a new name."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    video = _video(tmp_path / "Anime")
    assert blacklist_cmd.run(_blacklist_parse([str(video)])) == 0
    capsys.readouterr()
    renamed = video.with_name(u"葬送のフリーレン - 06.mkv")
    video.rename(renamed)
    assert blacklist_cmd.run(_blacklist_parse([str(renamed), "--note", "still the same file"])) == 0
    capsys.readouterr()
    rows = _json_out(blacklist_cmd, ["--list", "--json"], capsys)["blacklist"]
    assert len(rows) == 1 and rows[0]["video_path"] == str(renamed), rows


def test_removing_a_video_that_is_no_longer_there_still_works(tmp_path, monkeypatch, capsys):
    """⚠ A row the person wants off cannot be held hostage by a deleted file."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    video = _video(tmp_path / "Anime")
    assert blacklist_cmd.run(_blacklist_parse([str(video)])) == 0
    capsys.readouterr()
    video.unlink()
    assert blacklist_cmd.run(_blacklist_parse(["--remove", str(video)])) == 0
    assert "removed" in capsys.readouterr().out
    assert _json_out(blacklist_cmd, ["--list", "--json"], capsys)["blacklist"] == []


def test_blacklisting_a_video_that_cannot_be_read_says_so_and_records_nothing(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    missing = tmp_path / "Anime" / "gone.mkv"
    assert blacklist_cmd.run(_blacklist_parse([str(missing)])) == 1
    assert str(missing) in capsys.readouterr().err
    assert _json_out(blacklist_cmd, ["--list", "--json"], capsys)["blacklist"] == []


@pytest.mark.parametrize("argv", [[], ["--note", "why"], ["a.mkv", "--list"],
                                  ["a.mkv", "--remove", "b.mkv"]])
def test_the_blacklist_command_refuses_an_ambiguous_ask(tmp_path, monkeypatch, capsys, argv):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    assert blacklist_cmd.run(_blacklist_parse(argv)) == 2
    assert capsys.readouterr().err.strip(), "a usage error with nothing said"
    assert not (tmp_path / "root").exists(), "a usage error created a state DB"


def test_blacklist_list_creates_no_db_where_there_is_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    assert blacklist_cmd.run(_blacklist_parse(["--list"])) == 0
    assert "empty" in capsys.readouterr().out
    assert not (tmp_path / "root").exists(), "`hato blacklist --list` created a state DB"


def _json_out(module, argv, capsys):
    parser = argparse.ArgumentParser(prog="hato")
    module.register(parser)
    assert module.run(parser.parse_args(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_state_stat_names_the_blacklist_and_the_retry_windows(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    with state.StateDB(now=Clock(datetime.now(timezone.utc))) as db:
        db.blacklist_add(V1, video_path="D:/A/Concert.mkv", note="no dialogue")
    assert state_cmd.run(_state_parse(["--stat"])) == 0
    text = capsys.readouterr().out
    assert "blacklist    1 video" in text, text
    assert "1 day soft · 30 days hard" in text, text
    shown = _json_out(state_cmd, ["--stat", "--json"], capsys)
    assert shown["blacklisted"] == 1 and shown["retry_days"] == {"soft": 1, "hard": 30}


def test_state_stat_on_a_corrupt_db_says_so_in_one_line(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("HATO_CACHE", str(root))
    (root / "state.db").write_bytes(b"garbage " * 100)
    assert state_cmd.run(_state_parse(["--stat"])) == 0
    notes = [l for l in capsys.readouterr().out.splitlines() if l.startswith("note")]
    assert len(notes) == 1 and "moved aside" in notes[0], notes


# -- one accessor over the records ----------------------------------------------------------

_SQLITE_IMPORT = re.compile(r"^\s*(import\s+sqlite3|from\s+sqlite3\s+import)\b", re.M)


def modules_opening_the_state_db(package):
    """Every module under `package`, except the accessor, that imports sqlite3 AND
    names the state DB. A module with its own, different SQLite store is not one;
    nor is one that only prints where the state DB lives."""
    package = Path(package)
    found = []
    for module in sorted(package.rglob("*.py")):
        rel = module.relative_to(package).as_posix()
        if rel == "state.py":
            continue
        text = module.read_text(encoding="utf-8")
        if _SQLITE_IMPORT.search(text) and ("state_db_path" in text or "state.db" in text):
            found.append(rel)
    return found


def test_the_scan_for_a_second_accessor_can_fail(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "commands").mkdir(parents=True)
    (pkg / "state.py").write_text("import sqlite3\npaths.state_db_path()\n", encoding="utf-8")
    (pkg / "commands" / "rogue.py").write_text(
        "import sqlite3\nfrom hato import paths\nsqlite3.connect(str(paths.state_db_path()))\n",
        encoding="utf-8")
    (pkg / "resolution.py").write_text("import sqlite3  # its own store\n", encoding="utf-8")
    (pkg / "doctor.py").write_text("from hato import paths\nprint(paths.state_db_path())\n",
                                   encoding="utf-8")
    assert modules_opening_the_state_db(pkg) == ["commands/rogue.py"]


def test_only_the_accessor_opens_the_state_db():
    offenders = modules_opening_the_state_db(Path(state.__file__).parent)
    assert offenders == [], (
        "%s: imports sqlite3 and names the state DB. One accessor over the records (RUNBOOK 1b) "
        "-- go through hato.state.StateDB" % ", ".join(offenders))


# -- the run lock ----------------------------------------------------------------------------

def _write_lock(path, **info):
    path.write_text(json.dumps(info), encoding="utf-8")


def acquire_or_fail(path, what):
    lock = runlock.RunLock(path)
    try:
        return lock.acquire()
    except runlock.LockHeld as exc:
        pytest.fail("%s was obeyed, so every later run would exit on it: %s" % (what, exc))


def test_the_default_lock_is_in_the_redirected_per_user_root():
    lock = runlock.RunLock()
    assert lock.path == paths.lock_path()
    assert str(lock.path).startswith(os.environ["HATO_TEST_ROOT"])


def test_the_run_lock_is_held_for_the_block_and_gone_after(tmp_path):
    path = tmp_path / "hato.lock"
    with runlock.RunLock(path) as lock:
        assert lock.held and path.is_file()
        info = json.loads(path.read_text(encoding="utf-8"))
        assert info["pid"] == os.getpid() and info["started"]
        assert lock.note is None
    assert not path.exists()


def test_a_second_run_meets_the_lock_and_is_told_who_holds_it_and_what_to_do(tmp_path):
    path = tmp_path / "hato.lock"
    with runlock.RunLock(path):
        started = json.loads(path.read_text(encoding="utf-8"))["started"]
        with pytest.raises(runlock.LockHeld) as err:
            with runlock.RunLock(path):
                pytest.fail("a second run took the lock while the first still held it")
        msg = str(err.value)
        assert "pid %d" % os.getpid() in msg and started in msg, (
            "LockHeld must name the pid and start time of the run holding the lock: %s" % msg)
        assert str(path) in msg and "delete" in msg, (
            "LockHeld must name the lock file to delete when no hato is running: %s" % msg)
        assert (err.value.pid, err.value.started) == (os.getpid(), started)
        assert path.exists(), "the refused run removed a lock it never held"
    assert not path.exists()


def test_a_live_run_whose_creation_time_is_unknown_still_holds_the_lock(tmp_path):
    path = tmp_path / "hato.lock"
    _write_lock(path, pid=os.getpid(), started="2026-09-17 03:00:00", proc_start=None, token="live")
    with pytest.raises(runlock.LockHeld):
        runlock.RunLock(path).acquire()
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == "live"


def test_the_run_lock_is_released_when_the_run_raises(tmp_path):
    path = tmp_path / "hato.lock"
    with pytest.raises(KeyboardInterrupt):
        with runlock.RunLock(path):
            raise KeyboardInterrupt()
    assert not path.exists(), "an interrupted run left its lock behind"
    with runlock.RunLock(path):
        pass


def test_a_lock_left_by_a_run_that_exited_is_taken_over_with_a_note(tmp_path):
    path = tmp_path / "hato.lock"
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    _write_lock(path, pid=child.pid, started="2026-09-16 03:00:00", proc_start=None, token="dead")
    lock = acquire_or_fail(path, "the lock of a run that has exited (pid %d)" % child.pid)
    try:
        assert lock.held
        assert lock.note and str(child.pid) in lock.note and "no longer running" in lock.note, lock.note
        assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    finally:
        lock.release()
    assert not path.exists()


def test_a_lock_naming_a_pid_that_does_not_exist_is_taken_over(tmp_path):
    path = tmp_path / "hato.lock"
    _write_lock(path, pid=2147483640, started="2026-09-16 03:00:00", proc_start=None, token="gone")
    lock = acquire_or_fail(path, "the lock of a pid that does not exist")
    try:
        assert lock.note and "2147483640" in lock.note, lock.note
    finally:
        lock.release()


def test_a_lock_whose_pid_now_belongs_to_another_program_is_taken_over(tmp_path):
    path = tmp_path / "hato.lock"
    mine = runlock._process_start(os.getpid())
    if mine is None:
        pytest.skip("this platform reports no process creation time, so pid reuse cannot be told apart")
    _write_lock(path, pid=os.getpid(), started="2026-09-10 03:00:00", proc_start=mine - 1, token="old")
    lock = acquire_or_fail(path, "a lock whose pid now belongs to a different process")
    try:
        assert lock.note and "no longer running" in lock.note, lock.note
    finally:
        lock.release()


def test_an_unreadable_lock_is_respected_while_fresh_and_taken_over_once_stale(tmp_path):
    path = tmp_path / "hato.lock"
    path.write_bytes(b"")
    try:
        runlock.RunLock(path).acquire()
    except runlock.LockHeld as exc:
        assert "being written" in str(exc), str(exc)
    else:
        pytest.fail("an unreadable lock only moments old was taken over -- another run may be "
                    "writing it at this instant")
    an_hour_ago = time.time() - 3600
    os.utime(str(path), (an_hour_ago, an_hour_ago))
    lock = acquire_or_fail(path, "an unreadable lock an hour old")
    try:
        assert lock.note and "unreadable" in lock.note, lock.note
    finally:
        lock.release()


def test_releasing_never_removes_a_lock_that_is_no_longer_this_runs(tmp_path):
    path = tmp_path / "hato.lock"
    with runlock.RunLock(path):
        _write_lock(path, pid=12345, started="2026-09-17 04:00:00", proc_start=None, token="someone-else")
    assert path.exists(), "releasing removed a lock that belonged to another run"
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == "someone-else"
