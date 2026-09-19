# -*- coding: utf-8 -*-
"""
The state DB -- what hato has tried, and what jimaku did not have
(spec/02-data-model.md §The state DB, RUNBOOK 1b).

    db = StateDB()                              per-user app data; HATO_CACHE relocates it
    db.refused(video_hash, lang, entry, filename, size, last_modified)
                                                never re-download a refused candidate
    db.synced(video_hash, lang)                 the latest CONFIDENT row -- where the synced
                                                file went, and where its original is kept
    db.negative(video_hash, lang)               (kind, retry_after, reason) while fresh
    db.blacklisted(video_hash)                  the person said never fetch this one
    db.skip_reason(video_hash, lang, force=)    ⭐ the ONE question the fetch loop asks
    db.record_attempt(...)  db.record_not_found(...)  db.record_present(...)
    db.blacklist_add(...)   db.blacklist_remove(...)  db.blacklist_list()
    db.stats()                                  for `hato state --stat`

⭐ THE FILESYSTEM IS CANONICAL; THIS DB IS ADVISORY. It only ever PREVENTS work --
a refused candidate not downloaded again, a show not asked about again -- and is
never the reason a file gets written. It never looks at, creates or deletes a
subtitle: `synced()` hands back its row even when the file it names is gone,
because what that means is the fetch loop's call (RUNBOOK 4b), and the disk wins
there. If a bug here claims something exists that does not, the worst outcome
is a skipped fetch -- never an overwrite.

⛔ ONE ACCESSOR OVER THE RECORDS. This class is the only code that opens the
SQLite file. tests/test_state.py fails if another hato module imports sqlite3
and names the state DB.

⭐ REFUSALS ARE PER (VIDEO x CANDIDATE), not per subtitle. Timing is deterministic
for a PAIR: a subtitle refused against the wrong episode may be exactly right for
another video, and a global blacklist would lock it out for ever. Before a
download a candidate is (entry, filename, size, last_modified) from jimaku's file
list, so `refused()` answers without downloading; a re-upload is a new candidate.

⚠ "NO SUBTITLE TRACK" IS NEVER A REFUSAL (ruled 2026-09-17). A REFUSED row must
name its candidate, so a refusal cannot be recorded for a video that had nothing
to refuse.

⭐ THE BLACKLIST IS THE PERSON'S INSTRUCTION, NOT THE TOOL'S JUDGEMENT (RUNBOOK
1c). ⛔ `--force` does NOT override it: force overrules what hato decided -- a
refusal, a negative -- and a blacklist was decided by the person at the keyboard.
`skip_reason` therefore checks it FIRST and before `force` is even looked at, so
the ordering is a property of the code rather than of whoever calls it. Removing
the row is the way back, from the CLI or the window.

⚠ FAIL OPEN, CHOSEN DELIBERATELY (doctrine/robustness). Every way this store can be
unusable degrades to "the DB was deleted" -- which spec/06-edge-cases.md §7 says
must work: more downloads, never a wrong write. A CORRUPT file is moved aside and
a fresh one started; one that cannot be moved, cannot be opened, or was written
by a newer hato leaves this run with an in-memory DB. Each says so, in one
sentence, in `.notes`.
"""
import os
import sqlite3
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hato import paths

CONFIDENT = "CONFIDENT"
REFUSED = "REFUSED"
ERROR = "ERROR"
NOT_FOUND = "NOT_FOUND"
OUTCOMES = (CONFIDENT, REFUSED, ERROR, NOT_FOUND)

#: Soft negative -- the entry exists, no file for this episode yet.
#: ⭐ AMENDED 2026-09-17 (Sonic), 7 -> 1: a just-aired episode is exactly the case
#: to keep checking, and it costs ONE `files` call per day per show that still has
#: a gap (the resolution is cached for ever). A show with nothing missing costs
#: nothing at all. Configurable per StateDB -- see the constructor.
SOFT_DAYS = 1
#: Hard negative -- no entry matched at all. The show may still be added later.
HARD_DAYS = 30
SOFT = "soft"
HARD = "hard"

#: ⚠ BUMPED 1 -> 2 for the blacklist table. An older file is migrated by the
#: CREATE ... IF NOT EXISTS pass in `_prepare`; a NEWER one is left untouched.
SCHEMA_VERSION = 2
_BUSY_SECONDS = 5.0
_NEXT_RETRIES_SHOWN = 10

Attempt = namedtuple("Attempt", (
    "id video_hash video_path lang jimaku_entry jimaku_filename jimaku_size "
    "jimaku_last_modified subtitle_hash outcome reason output_path kept_path "
    "negative_kind retry_after attempted_at"))
Negative = namedtuple("Negative", "kind retry_after reason")
Blacklisted = namedtuple("Blacklisted", "video_hash video_path added_at note")
#: What `skip_reason` answers with. `kind` is "blacklist" or "negative".
Skip = namedtuple("Skip", "kind reason retry_after")

_PRESENT_COLUMNS = ("video_hash", "lang", "video_path", "recorded_at")
_BLACKLIST_COLUMNS = Blacklisted._fields

# ⭐ The schema refuses what the accessor refuses. The accessor's checks give the
# readable message; these are what still hold if a later edit adds a write path
# that forgets them (doctrine/robustness: a rule that can be a constraint is one).
# ⚠ SQLite passes a CHECK that evaluates to NULL, so every nullable column is
# tested with IS NOT NULL before its length.
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS attempts (
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
    )""",
    """CREATE INDEX IF NOT EXISTS attempts_by_video
        ON attempts (video_hash, lang, jimaku_entry, jimaku_filename)""",
    """CREATE TABLE IF NOT EXISTS present (
        video_hash   TEXT NOT NULL CHECK (length(video_hash) > 0),
        lang         TEXT NOT NULL CHECK (length(lang) > 0),
        video_path   TEXT,
        recorded_at  TEXT NOT NULL,
        PRIMARY KEY (video_hash, lang)
    )""",
    # ⭐ The blacklist (spec/02-data-model.md §Question 3). Keyed on the hash, so it
    # survives a rename; `video_path` is advisory, for display only. ⚠ NOT per
    # language: "this video doesn't need subs" is about the video, not about ja.
    """CREATE TABLE IF NOT EXISTS blacklist (
        video_hash   TEXT NOT NULL PRIMARY KEY CHECK (length(video_hash) > 0),
        video_path   TEXT,
        added_at     TEXT NOT NULL,
        note         TEXT NOT NULL DEFAULT ''
    )""",
)

_SELECT = ", ".join(Attempt._fields)
_INSERT = "INSERT INTO attempts (%s) VALUES (%s)" % (
    ", ".join(Attempt._fields[1:]), ", ".join(":" + f for f in Attempt._fields[1:]))

# The latest row per (video x language) decides whether a negative still stands:
# anything found or tried since supersedes it.
_ACTIVE_NEGATIVES = """
    SELECT a.retry_after, a.negative_kind, a.video_path, a.lang, a.reason, a.jimaku_entry
    FROM attempts AS a
    JOIN (SELECT max(id) AS id FROM attempts GROUP BY video_hash, lang) AS latest
      ON latest.id = a.id
    WHERE a.outcome = 'NOT_FOUND' AND a.retry_after > :now
    ORDER BY a.retry_after, a.id"""


class _Corrupt(Exception):
    """The file is not a usable SQLite database. Move it aside."""


class _Unusable(Exception):
    """The file could not be opened at all. Leave it; keep no state this run."""


class _TooNew(Exception):
    """A newer hato wrote it. Leave it untouched; keep no state this run."""


# ---------------------------------------------------------------------------
# values
# ---------------------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc)


def _stamp(moment):
    # Fixed width in UTC, so text order IS time order -- SQL compares these as text.
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _moment(text):
    return None if text is None else datetime.fromisoformat(text)


def _text(value):
    return "" if value is None else str(value).strip()


def _required(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string, got %r" % (name, value))
    return value.strip()


def _optional(value):
    if value is None:
        return None
    text = os.fspath(value) if isinstance(value, os.PathLike) else str(value)
    return text or None


def _lang(value):
    return _required("lang", value).lower()


def _days(name, value, fallback):
    """A retry window, in whole days. ⚠ bool is an int: `soft_days=True` is not 1."""
    if value is None:
        return fallback
    if type(value) is not int or value < 1:
        raise ValueError("%s must be a whole number of days, at least 1, got %r -- 0 would "
                         "re-ask jimaku about the same gap on every run of the day" % (name, value))
    return value


def _entry(value):
    if value is None:
        return None
    if type(value) is int:                  # ⚠ bool is an int: True is not entry 1
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError("jimaku_entry must be jimaku's integer entry id, got %r" % (value,))


def _size(value):
    if value is None:
        return None
    if type(value) is int and value >= 0:
        return value
    raise ValueError("jimaku_size must be the byte count from jimaku's file list, got %r" % (value,))


def _last_modified(value):
    if value is None or isinstance(value, str):
        return value
    raise ValueError("jimaku_last_modified must be jimaku's last_modified string, passed "
                     "verbatim, got %r" % (value,))


def _blacklisted(row):
    values = list(row)
    values[_BLACKLIST_COLUMNS.index("added_at")] = _moment(row[_BLACKLIST_COLUMNS.index("added_at")])
    return Blacklisted(*values)


def _attempt(row):
    values = list(row)
    values[Attempt._fields.index("retry_after")] = _moment(row[Attempt._fields.index("retry_after")])
    values[Attempt._fields.index("attempted_at")] = _moment(row[Attempt._fields.index("attempted_at")])
    return Attempt(*values)


# ---------------------------------------------------------------------------
# the accessor
# ---------------------------------------------------------------------------

class StateDB(object):
    """The only way into the state DB. Usable as a context manager."""

    def __init__(self, path=None, now=None, soft_days=None, hard_days=None):
        """`soft_days` / `hard_days` override the negative-cache windows.

        ⭐ Kept configurable (RUNBOOK 1c) so the window's Retry and a future
        config key change one number in one place -- ⛔ never a literal at a call
        site, which is how two callers come to disagree about when a retry is due.
        """
        self.path = Path(path) if path is not None else paths.state_db_path()
        self._now = now if now is not None else _utcnow
        self.retry_days = {SOFT: _days("soft_days", soft_days, SOFT_DAYS),
                           HARD: _days("hard_days", hard_days, HARD_DAYS)}
        #: One human sentence per thing worth telling the person running hato.
        self.notes = []
        #: False when this run fell back to an in-memory DB (see the module doc).
        self.persistent = True
        self.journal_mode = None
        self._conn = None
        self._open()

    def __repr__(self):
        return "<hato StateDB %s%s>" % (self.path, "" if self.persistent else " (in memory)")

    # -- opening, and what happens when it goes wrong ---------------------------

    def _open(self):
        try:
            self._conn = self._connect()
            return
        except _TooNew as exc:
            return self._in_memory(
                "The state DB at %s was written by a newer hato (schema %s; this one reads %d), "
                "so it was left untouched and this run keeps no state." % (self.path, exc, SCHEMA_VERSION))
        except _Unusable as exc:
            return self._in_memory(
                "The state DB at %s could not be opened (%s), so this run keeps no state and "
                "may repeat some downloads." % (self.path, exc))
        except _Corrupt as exc:
            problem = exc
        self._set_aside_and_start_fresh(problem)

    def _connect(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=_BUSY_SECONDS, isolation_level=None)
        except (OSError, sqlite3.Error) as exc:
            raise _Unusable(exc)
        try:
            self._prepare(conn)
        except BaseException as exc:
            conn.close()
            if type(exc) is sqlite3.DatabaseError:
                # Exactly DatabaseError is SQLITE_CORRUPT or SQLITE_NOTADB -- measured
                # 2026-09-17: "file is not a database", "database disk image is
                # malformed". Its subclasses (locked, I/O, constraint) are not corruption.
                raise _Corrupt(exc)
            if isinstance(exc, sqlite3.Error):
                raise _Unusable(exc)
            raise
        return conn

    def _prepare(self, conn):
        # ⚠ quick_check FIRST. A file with a valid header and damaged pages still
        # answers `PRAGMA user_version` -- measured -- and fails only later, mid-run.
        check = conn.execute("PRAGMA quick_check(1)").fetchone()
        if not check or check[0] != "ok":
            raise _Corrupt("integrity check reported %r" % (check[0] if check else None,))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise _TooNew(version)
        self.journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        conn.execute("PRAGMA synchronous=NORMAL")
        if version < SCHEMA_VERSION:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA:
                    conn.execute(statement)
                conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        for table, wanted in (("attempts", Attempt._fields), ("present", _PRESENT_COLUMNS),
                              ("blacklist", _BLACKLIST_COLUMNS)):
            have = set(row[1] for row in conn.execute("PRAGMA table_info(%s)" % table))
            missing = [c for c in wanted if c not in have]
            if missing:
                raise _Corrupt("table %s has no %s" % (table, ", ".join(missing)))

    def _set_aside_and_start_fresh(self, problem):
        try:
            aside = self._move_aside()
        except OSError as exc:
            return self._in_memory(
                "The state DB at %s is unreadable (%s) and could not be moved aside (%s), so "
                "this run keeps no state." % (self.path, problem, exc))
        try:
            self._conn = self._connect()
        except (_Corrupt, _Unusable, _TooNew) as exc:
            return self._in_memory(
                "The state DB at %s was unreadable (%s) and was moved aside to %s, but a fresh "
                "one could not be started (%s), so this run keeps no state."
                % (self.path, problem, aside.name, exc))
        self.notes.append("The state DB was unreadable (%s), so it was moved aside to %s and a "
                          "fresh one started." % (problem, aside.name))

    def _move_aside(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        aside = self.path.with_name("%s.corrupt-%s" % (self.path.name, stamp))
        n = 1
        while aside.exists():
            n += 1
            aside = self.path.with_name("%s.corrupt-%s-%d" % (self.path.name, stamp, n))
        os.replace(str(self.path), str(aside))
        for tail in ("-wal", "-shm", "-journal"):
            side = Path(str(self.path) + tail)
            if side.exists():
                try:
                    os.replace(str(side), str(aside) + tail)
                except OSError:
                    # Only the evidence is lost: SQLite discards a stale WAL beside a
                    # new, empty DB instead of replaying it (measured 2026-09-17).
                    pass
        return aside

    def _in_memory(self, note):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        self._prepare(conn)
        self._conn = conn
        self.persistent = False
        self.notes.append(note)

    def _run(self, op):
        """Every read and write goes through here, so corruption found MID-RUN is
        handled exactly like corruption found at open: set aside, start fresh,
        and the operation is tried once more against the fresh store."""
        if self._conn is None:
            raise ValueError("this StateDB is closed")
        try:
            return op(self._conn)
        except sqlite3.DatabaseError as exc:
            if type(exc) is not sqlite3.DatabaseError or not self.persistent:
                raise
            problem = exc
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
        self._conn = None
        self._set_aside_and_start_fresh(problem)
        return op(self._conn)

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # -- the clock ---------------------------------------------------------------

    def _clock(self):
        moment = self._now()
        if not isinstance(moment, datetime) or moment.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime, got %r" % (moment,))
        return moment.astimezone(timezone.utc)

    # -- writes -------------------------------------------------------------------

    def _insert(self, row):
        return self._run(lambda conn: conn.execute(_INSERT, row).lastrowid)

    def record_attempt(self, *, video_hash, video_path, lang, jimaku_entry, jimaku_filename,
                       jimaku_size, jimaku_last_modified, subtitle_hash, outcome, reason="",
                       output_path=None, kept_path=None):
        """Record one candidate tried against one video. -> the row id.

        Refused loudly, with ValueError: an unknown outcome · a NOT_FOUND (use
        `record_not_found`, which gives it a kind and a retry date) · a
        non-CONFIDENT row with no reason · a CONFIDENT row with no output_path
        (spec/03-permissions.md: CONFIDENT is not WRITTEN) · a REFUSED row that
        does not name its candidate.
        """
        if outcome not in OUTCOMES:
            raise ValueError("unknown outcome %r -- one of %s" % (outcome, ", ".join(OUTCOMES)))
        if outcome == NOT_FOUND:
            raise ValueError("a NOT_FOUND is recorded with record_not_found(), which gives it a "
                             "kind and the date it will be retried")
        reason = _text(reason)
        if outcome != CONFIDENT and not reason:
            raise ValueError("a %s row needs a reason -- 'it failed' is not actionable, and the "
                             "reason is what the person running hato reads" % outcome)
        if outcome == CONFIDENT and not _optional(output_path):
            raise ValueError("CONFIDENT with no output_path is an ERROR (spec/03-permissions.md) "
                             "-- record ERROR, saying why nothing was written")
        if outcome == REFUSED and (jimaku_entry is None or not _optional(jimaku_filename)):
            raise ValueError("a REFUSED row must name its candidate (jimaku_entry and "
                             "jimaku_filename): refused() matches on them, so an anonymous refusal "
                             "is downloaded again on every run. A video with no subtitle track is "
                             "a skip, never a refusal")
        return self._insert({
            "video_hash": _required("video_hash", video_hash),
            "video_path": _optional(video_path),
            "lang": _lang(lang),
            "jimaku_entry": _entry(jimaku_entry),
            "jimaku_filename": _optional(jimaku_filename),
            "jimaku_size": _size(jimaku_size),
            "jimaku_last_modified": _last_modified(jimaku_last_modified),
            "subtitle_hash": _optional(subtitle_hash),
            "outcome": outcome,
            "reason": reason,
            "output_path": _optional(output_path),
            "kept_path": _optional(kept_path),
            "negative_kind": None,
            "retry_after": None,
            "attempted_at": _stamp(self._clock()),
        })

    def record_not_found(self, *, video_hash, video_path, lang, kind, reason, jimaku_entry=None):
        """Record that jimaku has nothing for this video. -> when to ask again.

        kind "soft": the entry exists, with no file for this episode -- 1 day, so
        a just-aired episode is looked at again tomorrow. kind "hard": no entry
        matched at all -- 30 days. A soft negative names its entry and a hard one
        cannot, so the two can never be swapped.
        """
        if kind not in self.retry_days:
            raise ValueError("unknown negative kind %r -- 'soft' (the entry exists, no file for "
                             "this episode) or 'hard' (no entry matched)" % (kind,))
        reason = _text(reason)
        if not reason:
            raise ValueError("a NOT_FOUND needs a reason -- with its retry date, it is what tells "
                             "'nothing yet' from 'broken'")
        if kind == SOFT and jimaku_entry is None:
            raise ValueError("a soft negative means the entry EXISTS but has no file for this "
                             "episode -- name the entry, or record a hard negative")
        if kind == HARD and jimaku_entry is not None:
            raise ValueError("a hard negative means NO entry matched, so it cannot name entry %r "
                             "-- that is a soft negative" % (jimaku_entry,))
        now = self._clock()
        retry_after = now + timedelta(days=self.retry_days[kind])
        self._insert({
            "video_hash": _required("video_hash", video_hash),
            "video_path": _optional(video_path),
            "lang": _lang(lang),
            "jimaku_entry": _entry(jimaku_entry),
            "jimaku_filename": None,
            "jimaku_size": None,
            "jimaku_last_modified": None,
            "subtitle_hash": None,
            "outcome": NOT_FOUND,
            "reason": reason,
            "output_path": None,
            "kept_path": None,
            "negative_kind": kind,
            "retry_after": _stamp(retry_after),
            "attempted_at": _stamp(now),
        })
        return retry_after

    def record_present(self, video_hash, video_path, lang):
        """The backfill: the subtitle was already on disk and the DB knew nothing.
        One row per (video x language) however often it is called."""
        row = {"video_hash": _required("video_hash", video_hash), "lang": _lang(lang),
               "video_path": _optional(video_path), "recorded_at": _stamp(self._clock())}
        self._run(lambda conn: conn.execute(
            "INSERT OR IGNORE INTO present (video_hash, lang, video_path, recorded_at) "
            "VALUES (:video_hash, :lang, :video_path, :recorded_at)", row))

    # -- the blacklist ------------------------------------------------------------
    #
    # ⛔ THE ONLY WORK THIS CAN CAUSE IS LESS WORK. Adding a row stops hato fetching
    # for that video; removing one puts it back exactly where it was. Nothing here
    # reads, writes, moves or deletes a file, and nothing here can make one appear.

    def blacklist_add(self, video_hash, video_path=None, note=""):
        """"Never fetch for this video." -> the Blacklisted row.

        Idempotent, and adding again KEEPS THE FIRST added_at -- that is when the
        person said so. A later call may correct the advisory path (the file moved)
        or add a note; an empty note never wipes one that is already there.
        """
        row = {"video_hash": _required("video_hash", video_hash),
               "video_path": _optional(video_path), "note": _text(note),
               "added_at": _stamp(self._clock())}
        self._run(lambda conn: conn.execute(
            "INSERT INTO blacklist (video_hash, video_path, added_at, note) "
            "VALUES (:video_hash, :video_path, :added_at, :note) "
            "ON CONFLICT (video_hash) DO UPDATE SET "
            "  video_path = coalesce(excluded.video_path, blacklist.video_path), "
            "  note = CASE WHEN length(excluded.note) > 0 THEN excluded.note "
            "              ELSE blacklist.note END", row))
        return self.blacklisted(row["video_hash"])

    def blacklist_remove(self, video_hash):
        """Take the video off the blacklist. -> True when a row went.

        ⚠ False is not an error: it means it was never on it. The CLI says which.
        """
        key = {"video_hash": _required("video_hash", video_hash)}
        cursor = self._run(lambda conn: conn.execute(
            "DELETE FROM blacklist WHERE video_hash = :video_hash", key))
        return cursor.rowcount > 0

    def blacklist_list(self):
        """-> every Blacklisted row, oldest first. For `hato blacklist --list`."""
        rows = self._run(lambda conn: conn.execute(
            "SELECT %s FROM blacklist ORDER BY added_at, video_hash"
            % ", ".join(_BLACKLIST_COLUMNS)).fetchall())
        return [_blacklisted(r) for r in rows]

    def blacklisted(self, video_hash):
        """-> the Blacklisted row for this video, or None.

        ⭐ THE LOOKUP THE FETCH LOOP CALLS, before the container is opened
        (spec/02-data-model.md §Question 3) -- so a blacklisted video costs one
        hash and nothing else: no track read, no identification, no request.
        ⛔ It takes no `force`, and no language: see `skip_reason`.
        """
        key = {"video_hash": _required("video_hash", video_hash)}
        row = self._run(lambda conn: conn.execute(
            "SELECT %s FROM blacklist WHERE video_hash = :video_hash"
            % ", ".join(_BLACKLIST_COLUMNS), key).fetchone())
        return _blacklisted(row) if row else None

    # -- reads --------------------------------------------------------------------

    def skip_reason(self, video_hash, lang, force=False):
        """Is there a recorded reason not to work on this video? -> Skip or None.

        🚨 THE BLACKLIST IS CHECKED FIRST, AND `force` IS NOT EVEN LOOKED AT UNTIL
        AFTER IT. `--force` overrules HATO's judgement -- a refusal, a negative it
        recorded itself. A blacklist row is the PERSON's instruction, and overriding
        that is a different thing entirely (spec/02-data-model.md §Question 3). The
        way back is `hato blacklist --remove <video>`, never a flag.

        ⛔ Advisory, like every read here: a Skip only ever means "do less".
        """
        row = self.blacklisted(video_hash)
        if row is not None:
            return Skip("blacklist", "blacklisted%s" % (" -- %s" % row.note if row.note else ""),
                        None)
        if force:
            return None
        negative = self.negative(video_hash, lang)
        if negative is None:
            return None
        return Skip("negative", negative.reason, negative.retry_after)

    def _latest(self, video_hash, lang, only=""):
        sql = ("SELECT %s FROM attempts WHERE video_hash = :video_hash AND lang = :lang %s "
               "ORDER BY id DESC LIMIT 1" % (_SELECT, only))
        key = {"video_hash": _required("video_hash", video_hash), "lang": _lang(lang)}
        row = self._run(lambda conn: conn.execute(sql, key).fetchone())
        return _attempt(row) if row else None

    def refused(self, video_hash, lang, jimaku_entry, jimaku_filename, jimaku_size,
                jimaku_last_modified):
        """Has THIS candidate already been refused for THIS video?

        Its latest verdict for the pair decides: a later CONFIDENT clears a
        refusal, an ERROR does not (an error is not a verdict on the timing).
        Missing values match missing values -- jimaku omits absent keys.
        """
        key = {
            "video_hash": _required("video_hash", video_hash),
            "lang": _lang(lang),
            "entry": _entry(jimaku_entry),
            "filename": _optional(jimaku_filename),
            "size": _size(jimaku_size),
            "last_modified": _last_modified(jimaku_last_modified),
        }
        sql = ("SELECT outcome FROM attempts WHERE video_hash = :video_hash AND lang = :lang "
               "AND jimaku_entry IS :entry AND jimaku_filename IS :filename "
               "AND jimaku_size IS :size AND jimaku_last_modified IS :last_modified "
               "AND outcome IN ('REFUSED', 'CONFIDENT') ORDER BY id DESC LIMIT 1")
        row = self._run(lambda conn: conn.execute(sql, key).fetchone())
        return row is not None and row[0] == REFUSED

    def synced(self, video_hash, lang):
        """-> the latest CONFIDENT Attempt for (video x language), or None.

        ⛔ It does not check that `output_path` still exists. The fetch loop does:
        gone and `kept_path` still there is a zero-network re-sync; gone and no
        kept original is a re-fetch. The disk wins.
        """
        return self._latest(video_hash, lang, "AND outcome = 'CONFIDENT'")

    def negative(self, video_hash, lang):
        """-> Negative(kind, retry_after, reason) while a NOT_FOUND still stands,
        else None. It stands until its retry date, and only while nothing has
        been tried for the video since."""
        row = self._latest(video_hash, lang)
        if row is None or row.outcome != NOT_FOUND:
            return None
        if self._clock() >= row.retry_after:
            return None
        return Negative(row.negative_kind, row.retry_after, row.reason)

    def stats(self):
        """-> row counts by outcome, the backfilled count, and the next retry dates."""
        def op(conn):
            rows = dict((outcome, 0) for outcome in OUTCOMES)
            for outcome, count in conn.execute(
                    "SELECT outcome, count(*) FROM attempts GROUP BY outcome"):
                rows[outcome] = count
            present = conn.execute("SELECT count(*) FROM present").fetchone()[0]
            blacklisted = conn.execute("SELECT count(*) FROM blacklist").fetchone()[0]
            active = conn.execute(_ACTIVE_NEGATIVES, {"now": _stamp(self._clock())}).fetchall()
            return rows, present, blacklisted, active

        rows, present, blacklisted, active = self._run(op)
        return {
            "path": str(self.path),
            "persistent": self.persistent,
            "schema_version": SCHEMA_VERSION,
            "journal_mode": self.journal_mode,
            "rows": rows,
            "present": present,
            "blacklisted": blacklisted,
            "retry_days": dict(self.retry_days),
            "negatives_active": len(active),
            "next_retries": [
                {"retry_after": _moment(r[0]), "kind": r[1], "video_path": r[2], "lang": r[3],
                 "reason": r[4], "jimaku_entry": r[5]}
                for r in active[:_NEXT_RETRIES_SHOWN]],
            "notes": list(self.notes),
        }
