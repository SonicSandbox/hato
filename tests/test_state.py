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
                                     "jimaku 11446 has no file for episode 7", None)
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
    assert db.negative(V1, "ja") == ("hard", start + timedelta(days=30), "no jimaku entry matched",
                                     None)
    clock.advance(seconds=1)
    assert db.negative(V1, "ja") is None, "a hard negative still stands at its 30-day retry date"


def test_the_retry_constants_are_the_specs():
    assert (state.SOFT_DAYS, state.HARD_DAYS) == (1, 30)


def test_a_negative_is_per_video_and_language(db):
    db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="hard", reason="no entry")
    assert db.negative(V1, "ja") is not None
    assert db.negative(V2, "ja") is None and db.negative(V1, "en") is None


def test_anything_tried_since_supersedes_a_negative(db, clock):
    u"""⚠ INSIDE THE WINDOW. This advanced one day when the soft negative lasted
    seven; after Sonic ruled it down to one (2026-09-17) the negative had simply
    EXPIRED by then, so the check passed with supersession deleted -- found by the
    mutation gate, 2026-09-23 (M1b-13 survived)."""
    db.record_not_found(video_hash=V1, video_path=None, lang="ja", kind="soft",
                        reason="no file for episode 1 yet", jimaku_entry=11446)
    assert db.negative(V1, "ja") is not None
    clock.advance(hours=1)
    assert db.negative(V1, "ja") is not None, (
        u"the control: an hour in, the negative still stands on its date alone")
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


# -- RUNBOOK 8b: what a refusal must remember so it can be offered again ---------------

#: The `attempts` table exactly as hato 1.0.1 creates it -- the file Sonic's tray is
#: writing to right now. ⛔ Written out, not derived: the point is the OLD shape.
#: 🚨 VERBATIM from 1.0.1's own `state.py` (the Sep-18 build's archive), CHECKs,
#: index and WAL mode included. The first copy here had none of them -- so every
#: migration check below ran against a file 1.0.1 never made (ADVERSARY
#: 2026-09-22, the data surface's checks that passed for the wrong reason).
_OLD_ATTEMPTS = """CREATE TABLE IF NOT EXISTS attempts (
        id                    INTEGER PRIMARY KEY,
        video_hash            TEXT    NOT NULL CHECK (length(video_hash) > 0),
        video_path            TEXT,
        lang                  TEXT    NOT NULL CHECK (length(lang) > 0),
        jimaku_entry          INTEGER,
        jimaku_filename       TEXT,
        jimaku_size           INTEGER,
        jimaku_last_modified  TEXT,
        subtitle_hash         TEXT,
        outcome               TEXT    NOT NULL
            CHECK (outcome IN ('CONFIDENT', 'REFUSED', 'ERROR', 'NOT_FOUND')),
        reason                TEXT    NOT NULL DEFAULT ''
            CHECK (outcome = 'CONFIDENT' OR length(trim(reason)) > 0),
        output_path           TEXT
            CHECK (outcome <> 'CONFIDENT' OR (output_path IS NOT NULL AND length(output_path) > 0)),
        kept_path             TEXT,
        negative_kind         TEXT
            CHECK (negative_kind IS NULL OR negative_kind IN ('soft', 'hard')),
        retry_after           TEXT,
        attempted_at          TEXT    NOT NULL,
        CHECK (outcome <> 'REFUSED' OR (jimaku_entry IS NOT NULL
               AND jimaku_filename IS NOT NULL AND length(jimaku_filename) > 0)),
        CHECK ((outcome = 'NOT_FOUND') = (negative_kind IS NOT NULL AND retry_after IS NOT NULL))
    )"""
#: ...and the rest of 1.0.1's schema, verbatim too.
_OLD_REST = (
    """CREATE INDEX IF NOT EXISTS attempts_by_video
        ON attempts (video_hash, lang, jimaku_entry, jimaku_filename)""",
    """CREATE TABLE IF NOT EXISTS present (
        video_hash   TEXT NOT NULL CHECK (length(video_hash) > 0),
        lang         TEXT NOT NULL CHECK (length(lang) > 0),
        video_path   TEXT,
        recorded_at  TEXT NOT NULL,
        PRIMARY KEY (video_hash, lang)
    )""",
    """CREATE TABLE IF NOT EXISTS blacklist (
        video_hash   TEXT NOT NULL PRIMARY KEY CHECK (length(video_hash) > 0),
        video_path   TEXT,
        added_at     TEXT NOT NULL,
        note         TEXT NOT NULL DEFAULT ''
    )""",
)
_OLD_COLUMNS = ("video_hash, video_path, lang, jimaku_entry, jimaku_filename, jimaku_size, "
                "jimaku_last_modified, subtitle_hash, outcome, reason, output_path, kept_path, "
                "negative_kind, retry_after, attempted_at")


def _old_db(path):
    """A v2 state DB in 1.0.1's shape, holding one refusal written 1.0.1's way."""
    raw = sqlite3.connect(str(path))
    try:
        # ⚠ As 1.0.1 opens it: WAL, which is what Sonic's file on disk is in.
        assert raw.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        raw.execute(_OLD_ATTEMPTS)
        for statement in _OLD_REST:
            raw.execute(statement)
        raw.execute("INSERT INTO attempts (%s) VALUES (?, ?, 'ja', 11446, ?, 49646, NULL, NULL, "
                    "'REFUSED', 'timing did not hold: 61%% match', NULL, NULL, NULL, NULL, "
                    "'2026-09-17T03:00:00.000000+00:00')" % _OLD_COLUMNS,
                    (V1, "D:/A/ep01.mkv", candidate()["jimaku_filename"]))
        raw.execute("PRAGMA user_version = 2")
        raw.commit()
    finally:
        raw.close()


def test_a_refusal_remembers_which_file_it_was_and_how_close_it_came(db):
    """⭐ The hash finds the downloaded file again; the rate says how close it came.
    ⚠ 02-data-model.md specified `subtitle_hash` and it had been recorded as None
    since 1b -- a refusal could be REMEMBERED but never OFFERED again."""
    attempt(db, subtitle_hash="d" * 64, match_rate=0.57)
    tried, = db.candidates(V1, "ja")
    assert tried.subtitle_hash == "d" * 64
    assert tried.match_rate == pytest.approx(0.57)


@pytest.mark.parametrize("bad", [1.5, -0.01, True, "0.5", float("nan")])
def test_a_match_rate_that_is_not_a_fraction_is_refused(db, bad):
    """⚠ `True` is an int, NaN compares false with everything, and a string is
    somebody's formatting. Each would be read back as a number on a card."""
    exc = accessor_refuses(lambda: attempt(db, match_rate=bad))
    assert "match_rate" in str(exc)


def test_an_older_db_gains_the_new_columns_and_keeps_its_rows(tmp_path, clock):
    """🚨 NO VERSION BUMP, and this is why it is safe. The released 1.0.1 exe writes
    to this same file; `user_version` 3 would make it keep no state at all."""
    path = tmp_path / "state.db"
    _old_db(path)
    with state.StateDB(path, now=clock) as db:
        assert db.persistent and db.notes == [], (
            "a 1.0.1 file was treated as unreadable instead of extended: %s" % db.notes)
        tried, = db.candidates(V1, "ja")
        assert tried.match_rate is None, "an old row gained a rate it never had"
        attempt(db, subtitle_hash="e" * 64, match_rate=0.4, jimaku_filename="new.ass")
    raw = sqlite3.connect(str(path))
    try:
        have = set(r[1] for r in raw.execute("PRAGMA table_info(attempts)"))
        assert {"match_rate", "newest_offered"} <= have
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 2, (
            "the version moved -- the running 1.0.1 exe would now keep no state")
    finally:
        raw.close()


def test_hato_1_0_1_can_still_write_to_the_extended_file(tmp_path, clock):
    """⭐ The other direction, and the one that is running on Sonic's machine: an
    INSERT that names only the OLD columns -- which is every insert 1.0.1 makes --
    must still land, and read back with no rate."""
    path = tmp_path / "state.db"
    with state.StateDB(path, now=clock):
        pass
    raw = sqlite3.connect(str(path))
    try:
        raw.execute("INSERT INTO attempts (%s) VALUES (?, 'D:/A/ep02.mkv', 'ja', 11446, 'x.ass', "
                    "1, NULL, NULL, 'REFUSED', 'the timing did not hold', NULL, NULL, NULL, "
                    "NULL, '2026-09-17T03:00:00.000000+00:00')" % _OLD_COLUMNS, (V2,))
        raw.commit()
    finally:
        raw.close()
    with state.StateDB(path, now=clock) as db:
        tried, = db.candidates(V2, "ja")
        assert tried.jimaku_filename == "x.ass" and tried.match_rate is None


def test_two_openers_of_an_old_file_do_not_race_each_other(tmp_path, clock):
    """🚨 The tray's run and the window's `hato problems` can open a 1.0.1 file at
    the same moment. Both see the columns missing; the second ALTER raises
    *"duplicate column name"*, which `_connect` turns into an IN-MEMORY DB --
    a run that silently keeps no state.

    ⚠ THE RACE IS MADE TO HAPPEN, not hoped for: the first opener holds the write
    lock with its ALTER uncommitted while the second reads the old schema and
    waits. The second must finish AFTER the first commits -- which proves it saw
    the columns missing and waited, rather than arriving late and seeing nothing.
    """
    import threading

    path = tmp_path / "state.db"
    _old_db(path)
    first = sqlite3.connect(str(path), isolation_level=None)
    first.execute("BEGIN IMMEDIATE")
    first.execute("ALTER TABLE attempts ADD COLUMN match_rate REAL")
    outcome = {}

    def second():
        conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        try:
            state.StateDB._add_columns(conn)
            outcome["ok"] = True
        except Exception as exc:                      # noqa: BLE001 -- the evidence
            outcome["error"] = exc
        finally:
            outcome["ended"] = time.monotonic()
            conn.close()

    thread = threading.Thread(target=second)
    thread.start()
    time.sleep(0.5)
    first.execute("ALTER TABLE attempts ADD COLUMN newest_offered INTEGER")
    first.execute("COMMIT")
    committed = time.monotonic()
    first.close()
    thread.join(15)
    assert "error" not in outcome, (
        "the second opener raced the first and failed: %r -- that run would keep no "
        "state at all" % outcome.get("error"))
    assert outcome.get("ok") and outcome["ended"] >= committed, (
        "the second opener finished before the first committed, so the race was never "
        "exercised and this check proved nothing")


def test_candidates_are_the_files_tried_since_the_last_success_one_row_each(db):
    """⭐ What `tried_before` offers again. A file tried BEFORE the last success is
    not a candidate any more -- that episode was settled -- and a file tried twice
    is ONE candidate, carrying its latest verdict."""
    attempt(db, jimaku_filename="a.ass")
    confident(db, jimaku_filename="ok.ass", kept_path="C:/subs/ok.ja.ass")
    attempt(db, jimaku_filename="b.ass", match_rate=0.30)
    attempt(db, jimaku_filename="b.ass", match_rate=0.35)
    attempt(db, jimaku_filename="c.ass", outcome=state.ERROR,
            reason="c.ass could not be downloaded: 503")
    names = [(c.jimaku_filename, c.match_rate) for c in db.candidates(V1, "ja")]
    assert names == [("c.ass", None), ("b.ass", pytest.approx(0.35))]


def test_a_moved_video_has_its_advisory_path_corrected_and_only_then(db):
    """⭐ RUNBOOK 8e. A skip records nothing, so a video moved while it waited
    for a retry kept its OLD path here for ever -- and `hato problems`, filtered
    by the disk, dropped it. ⚠ No write when the path already agrees: a quiet
    re-run must stay a read."""
    attempt(db, video_path="D:/Old/ep01.mkv")          # REFUSED: an open problem
    assert db.note_path(V1, "D:/Old/ep01.mkv") is False
    assert db.note_path(V1, "D:/New/ep01.mkv") is True
    moved, = db.problems("ja")
    assert moved.video_path == "D:/New/ep01.mkv", "the problem still names the old place"
    assert db.note_path(V2, "D:/New/ep02.mkv") is False, "a path was noted for nothing"


def test_problems_are_the_videos_whose_latest_row_is_not_a_success(db):
    """⭐ RUNBOOK 8c. The store that outlives one run.

        V1   refused twice, then its soft negative        a problem, 2 candidates
        V2   only a NOT_FOUND                             a problem, 0 candidates
        V3   refused, then a success                      settled -- absent
        V4   refused, then blacklisted by the person      decided -- absent
    """
    v3, v4 = "v1-" + "3" * 64, "v1-" + "4" * 64
    attempt(db, jimaku_filename="a.ass", match_rate=0.2)
    attempt(db, jimaku_filename="b.ass", match_rate=0.6)
    db.record_not_found(video_hash=V1, video_path="D:/A/ep01.mkv", lang="ja", kind="soft",
                        jimaku_entry=11446, reason="2 of 5 candidate(s) tried, all refused")
    db.record_not_found(video_hash=V2, video_path="D:/A/ep24.mkv", lang="ja", kind="soft",
                        jimaku_entry=11446, reason="jimaku entry 11446 has no file for "
                                                   "this episode", newest_offered=23)
    attempt(db, video_hash=v3, jimaku_filename="c.ass")
    confident(db, video_hash=v3, jimaku_filename="d.ass")
    attempt(db, video_hash=v4, jimaku_filename="e.ass")
    db.blacklist_add(v4, video_path="D:/A/recap.mkv")

    found = dict((p.video_hash, p) for p in db.problems("ja"))
    assert set(found) == {V1, V2}
    assert [c.jimaku_filename for c in found[V1].candidates] == ["b.ass", "a.ass"]
    assert found[V1].latest.outcome == state.NOT_FOUND
    assert found[V2].candidates == [] and found[V2].latest.newest_offered == 23
    assert db.problems("en") == [], "a problem in one language leaked into another"


def test_retry_dues_are_the_dates_the_gate_is_still_waiting_on(db, clock):
    """⭐ RUNBOOK 8h. What the tray wakes for -- each beside a control that stays.

        V1   soft negative, +1 day                            listed
        V2   soft negative at the SAME moment as V1           listed once
        V3   hard negative, +30 days                          listed, last
        V4   negative, then a success                         superseded -- absent
        V5   negative, then blacklisted                       nobody to try -- absent
        V6   a negative in English                            another language -- absent
        V7   recorded after V1's date has passed              V1 is still OWED -- listed
             ...and once V1 is past RETRY_OWED_DAYS           dropped: no run can reach it
    """
    v = dict((n, "v1-" + str(n) * 64) for n in range(3, 8))

    def negative(video_hash, lang="ja", kind="soft"):
        # ⚠ EACH AT ITS OWN MOMENT. Recorded together, every excluded row shared
        # V1's date, and a filter that let them through changed nothing visible.
        clock.advance(minutes=1)
        return db.record_not_found(video_hash=video_hash, video_path=None, lang=lang,
                                   kind=kind, reason="x",
                                   jimaku_entry=11446 if kind == "soft" else None)

    soft = negative(V1)
    same = db.record_not_found(video_hash=V2, video_path=None, lang="ja", kind="soft",
                               jimaku_entry=11446, reason="all refused")
    hard = negative(v[3], kind="hard")
    superseded = negative(v[4])
    confident(db, video_hash=v[4], jimaku_filename="d.ass")
    blacklisted = negative(v[5])
    db.blacklist_add(v[5], video_path="D:/A/recap.mkv")
    english = negative(v[6], lang="en")
    assert soft == same, "the control: two negatives recorded at one moment share a date"
    assert len(set([soft, superseded, blacklisted, english])) == 4, (
        "the control: every excluded row has a date of its own, or excluding it "
        "would be invisible")

    assert db.retry_dues("ja") == [soft, hard], (
        "not every date still ahead, once each, soonest first -- a superseded, "
        "blacklisted or other-language date was kept, or one was lost")
    assert db.retry_dues("en") == [english], "the language filter works one way only"

    clock.advance(days=2)
    fresh = negative(v[7])
    assert db.retry_dues("ja") == [soft, fresh, hard], (
        "a date that PASSED with no run having looked again is still OWED -- dropped, a "
        "run that held the lock across it erased the tray's only reason to run "
        "(ADVERSARY 2026-09-22 R1)")

    clock.advance(days=38)               # V1 and V7 are past the carry; V3 is 10 days past
    assert db.retry_dues("ja") == [hard], (
        "a date past RETRY_OWED_DAYS is one no run could reach, and it is still listed -- "
        "or a passed date inside it was dropped")


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


def test_a_release_that_meets_a_READER_waits_it_out_and_still_removes_the_lock(tmp_path):
    """🚨 MEASURED 2026-09-23 -- the full runner HUNG on this. On Windows a file
    another handle has open cannot be deleted, and a run waiting on the lock reads
    it on every poll. A release that met that read failed silently and left the
    lock: a waiter in the same process polled for three hours (test_endtoend's L1
    check), and one in another took over a live release as "a run that exited".
    ⚠ Windows only has the refusal; elsewhere the delete simply succeeds."""
    import threading
    path = tmp_path / "hato.lock"
    lock = runlock.RunLock(path).acquire()
    reader = open(str(path), "rb")
    closer = threading.Timer(0.2, reader.close)
    closer.start()
    try:
        lock.release()
    finally:
        closer.cancel()
        reader.close()
    assert not path.exists(), "the release met a reader and left the lock behind"


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


def test_run_in_flight_answers_what_acquire_would_and_takes_nothing(tmp_path):
    """⭐ ADVERSARY S01 -- the tray asks this before spawning into a held lock.
    Both halves: a live lock IS a run (the positive a liveness check must
    prove, `processes.md`), and a dead one, or none, is not."""
    path = tmp_path / "hato.lock"
    assert runlock.run_in_flight(path) is False, "no lock at all read as a run"
    lock = runlock.RunLock(path).acquire()
    try:
        assert runlock.run_in_flight(path) is True, "THIS live run's lock read as free"
        assert path.exists(), "asking took the lock away"
    finally:
        lock.release()
    assert runlock.run_in_flight(path) is False
    _write_lock(path, pid=2147483640, started="2026-09-16 03:00:00", proc_start=None,
                token="gone")
    assert runlock.run_in_flight(path) is False, "a dead pid's lock read as a run"
    path.write_bytes(b"{half-written")
    assert runlock.run_in_flight(path) is True, (
        "a lock too new to read is a run STARTING -- acquire treats it so")
    old = time.time() - 3600
    os.utime(str(path), (old, old))
    assert runlock.run_in_flight(path) is False


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


def test_an_unreadable_lock_is_respected_while_fresh_and_taken_over_once_stale(tmp_path,
                                                                              monkeypatch):
    # ⚠ THE MACHINE BOOTED LONG AGO, SAID OUT LOUD. A CI VM starts minutes before
    # the job, so a lock backdated an hour was "written before the last boot" --
    # a different rule, correctly -- and this check went red on the first CI run
    # of 1.0.2 (2026-09-23). The table below fakes the boot for the same reason.
    monkeypatch.setattr(runlock, "_boot_time", lambda: time.time() - 10 * 86400)
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


# -- ADVERSARY 2026-09-22: one judgement, every lock state -----------------------------------

#: A pid this build pretends it may not inspect -- `_query` is replaced for it.
DENIED_PID = 4000321


def _aged(path, seconds):
    moment = time.time() - seconds
    os.utime(str(path), (moment, moment))


def _lock_as(path, how):
    u"""Put the lock in one named state. -> what BOTH answers must be."""
    if how == "none":
        return runlock.FREE
    if how == "this live run":
        _write_lock(path, pid=os.getpid(), started="x",
                    proc_start=runlock._process_start(os.getpid()), token="t")
        return runlock.HELD
    if how == "denied, fresh":
        _write_lock(path, pid=DENIED_PID, started="x", proc_start=1, token="t")
        return runlock.HELD
    if how == "denied, a day old":
        _write_lock(path, pid=DENIED_PID, started="x", proc_start=1, token="t")
        _aged(path, runlock.DENIED_MAX_AGE + 60)
        return runlock.FREE
    if how == "from before the last boot":
        _write_lock(path, pid=os.getpid(), started="x",
                    proc_start=runlock._process_start(os.getpid()), token="t")
        _aged(path, 3 * 86400)
        return runlock.FREE
    if how == "empty, being written":
        path.write_bytes(b"")
        return runlock.HELD
    if how == "unreadable, stamped in the future":
        path.write_bytes(b"{")
        _aged(path, -2 * 86400)
        return runlock.FREE
    if how == "unreadable, stamped a moment ahead":
        # 🚨 CI, 2026-09-23 (Windows, py3.12): a lock written JUST NOW can carry an
        # mtime a few ms ahead of `time.time()`, and was taken over as "from the
        # future" while another run was writing it. Half a second is granularity.
        path.write_bytes(b"")
        _aged(path, -0.5)
        return runlock.HELD
    if how == "nested JSON, being written":
        path.write_bytes(b"[" * 100000 + b"]" * 100000)
        return runlock.HELD
    if how == "nested JSON, an hour old":
        path.write_bytes(b"[" * 100000 + b"]" * 100000)
        _aged(path, 3600)
        return runlock.FREE
    if how == "a folder where the lock goes":
        path.mkdir()
        return runlock.UNUSABLE
    raise AssertionError(how)


def test_the_machines_last_start_is_known_where_the_lock_rule_needs_it():
    u"""L2's rule needs the last boot, and the table below FAKES it in every case
    -- so a `_boot_time` that answered nothing would disarm the rule while every
    lock check stayed green (it did, as a mutant: M8zt-G04). ⭐ Read against a
    second clock: on Windows `time.monotonic()` counts from the same boot."""
    boot = runlock._boot_time()
    if os.name == "nt":
        assert boot is not None, u"the last boot could not be read -- the rule is dead here"
        if u"GetTickCount64" in time.get_clock_info("monotonic").implementation:
            since = time.time() - time.monotonic()
            assert abs(boot - since) < 5.0, (
                u"the last boot read as %r, the monotonic clock says %r" % (boot, since))
    elif os.path.exists("/proc/uptime"):
        assert boot is not None, u"/proc/uptime is there and was not read"
    else:
        pytest.skip(u"this platform offers no uptime to read; the rule is off, by design")
    assert boot < time.time()


@pytest.mark.parametrize("how", [
    "none", "this live run", "denied, fresh", "denied, a day old", "from before the last boot",
    "empty, being written", "unreadable, stamped in the future",
    "unreadable, stamped a moment ahead", "nested JSON, being written",
    "nested JSON, an hour old", "a folder where the lock goes"])
def test_the_tray_and_acquire_read_every_lock_the_same_way(tmp_path, monkeypatch, how):
    u"""ADVERSARY 2026-09-22 L2-L5, one table. The tray asks `lock_state` before
    it spawns; `acquire` decides for the run. Where they disagreed, the tray
    either spawned a run into a lock it would fail on, in silence, or waited on
    one no run held:

        denied, a day old          a dead run's pid reused by a SYSTEM process -- obeyed for ever
        from before the last boot  no run of this session can own it
        stamped in the future      read as "being written" for days
        nested JSON                RecursionError out of the tray's tick
        a folder where it goes     "free" to the tray, LockUnusable to the run
    """
    real_query = runlock._query
    monkeypatch.setattr(runlock, "_query", lambda pid: ("denied", None) if pid == DENIED_PID
                        else real_query(pid))
    if how == "from before the last boot":
        monkeypatch.setattr(runlock, "_boot_time", lambda: time.time() - 86400)
    else:
        monkeypatch.setattr(runlock, "_boot_time", lambda: time.time() - 30 * 86400)
    path = tmp_path / "hato.lock"
    wanted = _lock_as(path, how)
    try:
        said = runlock.lock_state(path)
    except Exception as exc:                          # noqa: BLE001 -- L4 IS a raise
        pytest.fail("asking about a lock that is %s raised %s" % (how, type(exc).__name__))
    assert said == wanted, "the tray reads a lock that is %s as %s" % (how, said)
    try:
        lock = runlock.RunLock(path).acquire()
    except runlock.LockHeld:
        took = runlock.HELD
    except runlock.LockUnusable:
        took = runlock.UNUSABLE
    else:
        took = runlock.FREE
        lock.release()
    assert took == wanted, (
        "a lock that is %s: the tray says %s and acquire does %s" % (how, said, took))


def test_the_last_boot_is_read_from_the_machine():
    boot = runlock._boot_time()
    if boot is None:
        pytest.skip("this platform does not say when it started")
    assert time.time() - 400 * 86400 < boot < time.time(), boot


def test_a_run_asked_to_wait_takes_the_lock_once_it_is_free(tmp_path):
    u"""ADVERSARY 2026-09-22 L1. The tray asks, sees no run, and spawns -- and a
    frozen child needs one to two seconds to reach the lock. A run starting in
    between made it exit having scanned nothing. ⭐ Told to wait, it waits."""
    path = tmp_path / "hato.lock"
    held = runlock.RunLock(path).acquire()
    naps, now = [], [0.0]

    def nap(seconds):
        naps.append(seconds)
        now[0] += seconds
        if len(naps) == 3:
            held.release()                             # the other run finishes

    lock = runlock.RunLock(path).acquire(wait=60.0, poll=2.0, sleep=nap, clock=lambda: now[0])
    try:
        assert lock.held and len(naps) == 3, naps
    finally:
        lock.release()
    held = runlock.RunLock(path).acquire()
    try:
        with pytest.raises(runlock.LockHeld):
            runlock.RunLock(path).acquire(wait=5.0, poll=2.0, sleep=nap, clock=lambda: now[0])
        with pytest.raises(runlock.LockHeld):
            runlock.RunLock(path).acquire(sleep=lambda s: pytest.fail("waited unasked"))
    finally:
        held.release()


def test_a_lock_nothing_will_free_is_never_waited_on(tmp_path):
    path = tmp_path / "hato.lock"
    path.mkdir()
    with pytest.raises(runlock.LockUnusable):
        runlock.RunLock(path).acquire(wait=3600.0, sleep=lambda s: pytest.fail(
            "waited on a lock no run holds -- a folder sits where it goes"))


# -- ⭐ RUNBOOK 8g: clear hato's memory ---------------------------------------------------

def remembering_everything(db):
    """Two videos tried (three rows), a backfill note, one video blacklisted."""
    attempt(db, jimaku_filename="a.ass")
    attempt(db, jimaku_filename="b.ass")
    db.record_not_found(video_hash=V2, video_path="D:/A/ep24.mkv", lang="ja", kind="soft",
                        jimaku_entry=11446, reason="no file for this episode")
    db.record_present("v1-" + "9" * 64, "D:/A/ep01.mkv", "ja")
    db.blacklist_add("v1-" + "8" * 64, video_path="D:/A/recap.mkv", note="a recap")


def counted(db):
    return (sum(db.stats()["rows"].values()), db.stats()["present"], len(db.blacklist_list()))


def test_clear_is_dry_unless_told_and_counts_what_would_go(db):
    """⛔ `doctrine/robustness` §destructive: a destructive tool is DRY by default."""
    remembering_everything(db)
    before = counted(db)
    said = db.clear()
    assert said == {"tables": {"attempts": 3, "present": 1}, "videos": 2}, said
    assert counted(db) == before, "a DRY clear deleted something"


def test_clear_empties_every_table_but_the_blacklist_unless_it_is_named(db):
    remembering_everything(db)
    db.clear(dry_run=False)
    assert counted(db) == (0, 0, 1), (
        "the attempts and notes must go and the person's blacklist must stay: %r"
        % (counted(db),))
    assert db.clear(blacklist=True, dry_run=False)["tables"]["blacklist"] == 1
    assert counted(db) == (0, 0, 0)


def test_clear_is_scoped_by_shape_so_a_table_added_later_is_memory_too(db, tmp_path):
    """⭐ Every table `sqlite_master` lists, not a list somebody remembered -- the
    whole DB is advisory, so next year's table is cleared by this year's code."""
    import sqlite3
    remembering_everything(db)
    raw = sqlite3.connect(str(tmp_path / "state.db"), isolation_level=None)
    try:
        raw.execute("CREATE TABLE later (x INTEGER)")
        raw.execute("INSERT INTO later VALUES (1)")
    finally:
        raw.close()
    said = db.clear(dry_run=False)
    assert said["tables"].get("later") == 1, said
    raw = sqlite3.connect(str(tmp_path / "state.db"))
    try:
        assert raw.execute("SELECT count(*) FROM later").fetchone()[0] == 0
        assert raw.execute("SELECT count(*) FROM blacklist").fetchone()[0] == 1
    finally:
        raw.close()


def _data_root(tmp_path, monkeypatch):
    """A per-user root holding every kind of file hato keeps -- and a library."""
    from hato import resolution, retries
    root = tmp_path / "root"
    monkeypatch.setenv("HATO_CACHE", str(root))
    with state.StateDB(now=Clock(datetime.now(timezone.utc))) as db:
        remembering_everything(db)
        db.record_not_found(video_hash="v1-" + "7" * 64, video_path="D:/A/ep25.mkv",
                            lang="ja", kind="soft", jimaku_entry=11446, reason="not yet")
    resolution.ResolutionCache().put(
        resolution.cache_key(u"Sousou no Frieren", 2),
        resolution.Resolved(11446, u"Sousou no Frieren", False, 0.98, False,
                            resolution.SOURCES[0]))
    retries.save([datetime.now(timezone.utc) + timedelta(days=1)])
    for rel, body in (("config.toml", "folders = []\n"), ("key.txt", "not-a-real-key"),
                      ("last-run.json", "{}"), ("hato.log", "a log"),
                      ("subs/Frieren/x.ja.ass", "[Script Info]"),
                      ("cache/blobs/ab/abc/x.ja.ass", "[Script Info]")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    library = tmp_path / "Anime"
    library.mkdir()
    (library / "ep01.mkv").write_bytes(b"video")
    (library / "ep01.ja.ass").write_text("[Script Info]", encoding="utf-8")
    return root, library


def _files(*roots):
    out = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                out[str(path)] = path.read_bytes()
    return out


def _clear_parse(argv):
    parser = argparse.ArgumentParser(prog="hato state")
    state_cmd.register(parser)
    return parser.parse_args(argv)


def test_state_clear_says_what_would_go_and_changes_nothing_without_yes(
        tmp_path, monkeypatch, capsys):
    root, library = _data_root(tmp_path, monkeypatch)
    before = _files(root, library)
    assert state_cmd.run(_clear_parse(["--clear", "--json"])) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["dry_run"] is True and said["ok"] is True
    assert said["cleared"] == {"videos": 3, "attempts": 4, "present": 1, "shows": 1,
                               "waiting": 2}, said["cleared"]
    assert _files(root, library) == before, "a DRY clear changed a file"
    assert state_cmd.run(_clear_parse(["--clear"])) == 0
    assert "add --yes" in capsys.readouterr().out


def test_state_clear_yes_forgets_the_memory_and_touches_nothing_else(
        tmp_path, monkeypatch, capsys):
    """⛔ No subtitle, no kept original, no setting, no key, no log, no cache."""
    from hato import resolution, retries
    root, library = _data_root(tmp_path, monkeypatch)
    memory = ("state.db", "state.db-wal", "state.db-shm", "resolution.db", "retries-due.json",
              "hato.lock")
    keep = dict((k, v) for k, v in _files(root, library).items()
                if os.path.basename(k) not in memory)

    assert state_cmd.run(_clear_parse(["--clear", "--yes", "--json"])) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["dry_run"] is False and said["cleared"]["attempts"] == 4
    assert "the blacklist (1 video)" in said["kept"], said["kept"]

    after = _files(root, library)
    touched = sorted(k for k in keep if after.get(k) != keep[k])
    assert touched == [], "clearing the memory changed %s" % touched
    with state.StateDB() as db:
        assert counted(db) == (0, 0, 1), "the memory is not empty, or the blacklist went"
    assert resolution.ResolutionCache().get(resolution.cache_key(u"Sousou no Frieren", 2)) is None
    assert not retries.path().exists(), "the tray would still wake for a forgotten promise"


def test_state_clear_takes_the_blacklist_only_when_named(tmp_path, monkeypatch, capsys):
    _data_root(tmp_path, monkeypatch)
    assert state_cmd.run(_clear_parse(["--clear", "--yes", "--blacklist", "--json"])) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["cleared"]["blacklist"] == 1
    assert not [k for k in said["kept"] if "blacklist" in k]
    with state.StateDB() as db:
        assert db.blacklist_list() == []


def test_state_clear_is_refused_while_a_run_holds_the_lock(tmp_path, monkeypatch, capsys):
    """⛔ A run writing rows into a store being emptied -- refused, and nothing goes."""
    root, library = _data_root(tmp_path, monkeypatch)
    before = _files(root, library)
    held = runlock.RunLock()
    held.acquire()
    try:
        code = state_cmd.run(_clear_parse(["--clear", "--yes", "--json"]))
    finally:
        held.release()
    said = json.loads(capsys.readouterr().out)
    assert code == 1 and said["busy"] is True and "nothing was cleared" in said["error"]
    after = dict((k, v) for k, v in _files(root, library).items()
                 if not k.endswith("hato.lock"))
    assert after == dict((k, v) for k, v in before.items() if not k.endswith("hato.lock")), (
        "a clear refused for a running run still changed something")


def test_a_dry_clear_never_takes_the_run_lock(tmp_path, monkeypatch, capsys):
    """⛔ The window asks for the dry count to draw its card. Taking the run lock
    for that would make a tray run starting at that moment exit with *"nothing
    was scanned"* -- so a count answers while a run is going, and takes nothing."""
    _data_root(tmp_path, monkeypatch)
    held = runlock.RunLock()
    held.acquire()
    try:
        code = state_cmd.run(_clear_parse(["--clear", "--json"]))
        mine = json.loads(paths.lock_path().read_text(encoding="utf-8"))["token"]
    finally:
        held.release()
    said = json.loads(capsys.readouterr().out)
    assert code == 0 and said["ok"] is True and said["cleared"]["attempts"] == 4, (
        "a dry count was refused while a run held the lock: %r" % (said,))
    assert mine == held._token, "the dry count took the run's lock over"


def test_state_clear_flags_mean_nothing_without_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    assert state_cmd.run(_clear_parse(["--stat", "--yes"])) == 2
    assert "--clear" in capsys.readouterr().err


# -- ADVERSARY 2026-09-22: a view repairs nothing, and a clear says what it did -------------

GARBAGE = b"this was never a database " * 100


def _damage(path, clock, how):
    """A state DB no reader can use: not a database at all, or damaged pages
    behind a header that still answers."""
    if how == "not a database":
        path.write_bytes(GARBAGE)
        return
    with state.StateDB(path, now=clock) as db:
        for i in range(400):
            attempt(db, jimaku_filename="candidate %04d.ass" % i,
                    reason="timing did not hold " * 10)
    data = bytearray(path.read_bytes())
    for offset in range(2 * 4096, len(data), 3 * 4096):
        data[offset:offset + 256] = b"\xff" * 256
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("how", ["not a database", "damaged pages"])
def test_a_view_leaves_an_unreadable_db_exactly_as_it_is_and_says_it_could_not_read_it(
        tmp_path, clock, how):
    """⛔ `repair=False` is for a VIEW (`hato problems`, a dry `--clear`).
    ADVERSARY 2026-09-22 F3a: the view MOVED the person's DB aside -- at window
    startup, with no run lock. Setting a store aside is a run's job, under its lock."""
    path = tmp_path / "state.db"
    _damage(path, clock, how)
    before = _files(tmp_path)
    with state.StateDB(path, now=clock, repair=False) as db:
        assert db.persistent is False, "a view answered as if it had read the store"
        assert len(db.notes) == 1 and "left exactly as it is" in db.notes[0], db.notes
    after = _files(tmp_path)
    assert after == before, "a VIEW changed the store: %s" % sorted(
        k for k in set(before) | set(after) if before.get(k) != after.get(k))
    with state.StateDB(path, now=clock) as db:         # the control: a RUN does repair
        assert db.persistent and "moved aside" in db.notes[0], db.notes
    assert len(_asides(tmp_path)) == 1


def _unreadable(root, name):
    for tail in ("-wal", "-shm", "-journal"):
        side = root / (name + tail)
        if side.exists():
            side.unlink()
    (root / name).write_bytes(GARBAGE)


@pytest.mark.parametrize("broken", [("state.db",), ("resolution.db",),
                                    ("state.db", "resolution.db")])
def test_a_dry_clear_over_an_unreadable_store_changes_no_file_and_still_answers(
        tmp_path, monkeypatch, capsys, broken):
    """⛔ ADVERSARY 2026-09-22 F2 + F3b. The dry count moved a corrupt store
    aside and then printed *"nothing was changed"* -- or, for the resolution
    cache, crashed on the None its repairing read left behind."""
    root, library = _data_root(tmp_path, monkeypatch)
    for name in broken:
        _unreadable(root, name)
    before = _files(root, library)
    try:
        code = state_cmd.run(_clear_parse(["--clear", "--json"]))
    except Exception as exc:                       # noqa: BLE001 -- the finding IS a crash
        pytest.fail("a DRY clear over an unreadable %s raised %s: %s"
                    % (" and ".join(broken), type(exc).__name__, exc))
    said = json.loads(capsys.readouterr().out)
    assert code == 0 and said["ok"] is True and said["dry_run"] is True, said
    after = _files(root, library)
    assert after == before, "a DRY clear changed %s" % sorted(
        k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert len([n for n in said["notes"] if "left exactly as it is" in n]) == len(broken), (
        "each unreadable store must be named as left for the next run: %r" % said["notes"])
    if broken == ("resolution.db",):
        assert said["cleared"]["attempts"] == 4, (
            "one unreadable store hid what the READABLE one holds: %r" % said["cleared"])


def test_a_real_clear_over_an_unreadable_resolution_cache_still_finishes(
        tmp_path, monkeypatch, capsys):
    """ADVERSARY 2026-09-22 F2, the --yes half: the state DB was emptied, then
    counting the shows crashed (`held + None`) -- so the retry file was never
    deleted and the tray kept waking for promises nobody remembered."""
    from hato import retries
    root, _library = _data_root(tmp_path, monkeypatch)
    _unreadable(root, "resolution.db")
    code = state_cmd.run(_clear_parse(["--clear", "--yes", "--json"]))
    said = json.loads(capsys.readouterr().out)
    assert code == 0 and said["ok"] is True and said["cleared"]["attempts"] == 4, said
    assert not retries.path().exists(), "the tray would still wake for a forgotten promise"
    assert any("moved aside" in n for n in said["notes"]), (
        "a real clear set the resolution cache aside and did not say so: %r" % said["notes"])


def test_a_file_with_no_attempts_table_is_set_aside_not_kept_in_memory_for_ever(
        tmp_path, clock):
    """ADVERSARY 2026-09-22 F6. Adding the new columns ALTERed a table that was
    not there; *"no such table"* is an OperationalError, which reads as UNUSABLE,
    not corrupt -- so every later run kept its state in MEMORY and repeated every
    download, instead of setting the broken file aside once."""
    path = tmp_path / "state.db"
    raw = sqlite3.connect(str(path))
    raw.execute("CREATE TABLE present (video_hash TEXT NOT NULL, lang TEXT NOT NULL, "
                "video_path TEXT, recorded_at TEXT NOT NULL, PRIMARY KEY (video_hash, lang))")
    raw.execute("CREATE TABLE blacklist (video_hash TEXT NOT NULL PRIMARY KEY, "
                "video_path TEXT, added_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '')")
    raw.execute("PRAGMA user_version = %d" % state.SCHEMA_VERSION)
    raw.commit()
    raw.close()
    db = opens_without_crashing(path, clock, "a state DB with no attempts table")
    try:
        assert db.persistent, (
            "a file missing its attempts table is kept IN MEMORY -- every run would repeat "
            "every download: %r" % db.notes)
        assert len(db.notes) == 1 and "moved aside" in db.notes[0], db.notes
        attempt(db)
        assert refused(db) is True
    finally:
        db.close()
    assert len(_asides(tmp_path)) == 1


def test_a_moved_video_has_its_path_corrected_in_every_language_it_waits_in(db):
    """ADVERSARY 2026-09-22 S2. `problems(lang)` reads the latest row PER
    LANGUAGE; correcting only the newest row overall left the other language's
    problem naming the folder the video left -- and the disk check then dropped
    it from Needs you, the one thing 4a says must never happen."""
    for lang in ("ja", "en"):
        db.record_not_found(video_hash=V1, video_path="D:/Old/ep05.mkv", lang=lang,
                            kind="soft", jimaku_entry=11446, reason="not on jimaku yet")
    assert db.note_path(V1, "D:/New/ep05.mkv") is True
    for lang in ("ja", "en"):
        moved, = db.problems(lang)
        assert moved.video_path == "D:/New/ep05.mkv", (
            "the %s problem still names the folder the video left: %s"
            % (lang, moved.video_path))


def test_a_clear_that_took_over_a_dead_runs_lock_says_so(tmp_path, monkeypatch, capsys):
    """ADVERSARY 2026-09-22 F17. A real clear takes the run lock; one left by a
    run that has exited is taken over -- and a run says so. The clear did not."""
    _data_root(tmp_path, monkeypatch)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    _write_lock(paths.lock_path(), pid=child.pid, started="2026-09-16 03:00:00",
                proc_start=None, token="dead")
    code = state_cmd.run(_clear_parse(["--clear", "--yes", "--json"]))
    said = json.loads(capsys.readouterr().out)
    assert code == 0 and said["ok"] is True and said["cleared"]["attempts"] == 4, said
    assert [n for n in said["notes"] if str(child.pid) in n and "no longer running" in n], (
        "the clear took over a dead run's lock and said nothing about it: %r" % said["notes"])
