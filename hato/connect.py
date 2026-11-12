# -*- coding: utf-8 -*-
u"""
Surasura Connect: the hand-off from hato to Surasura (RUNBOOK LAYER 16, 1.1.0).

    entry = connect.read_entry()                  surasura.json, or why it counts as absent
    link  = connect.state(cfg.surasura_connect)   off · absent · too-new · offline · drops · registers
    connect.write_hato_json(cfg.surasura_connect) hato's own entry, for Surasura's back-fill

⭐ THE CONTRACT is Surasura's v2 read with v2.1 (signed 2026-10-29), in Surasura's
planning folder `tracks/tools/work/`: `hato-shapes-v2.md` holds every shape.

⭐ ONE SHARED FOLDER, two small files. Surasura writes `surasura.json` (its command
line, the verbs it offers, the folder per language hato's copies go to); hato writes
`hato.json` (its command line, `"verbs": ["pairings", "find"]`). Neither ever opens the
other's data: Surasura asks `hato-cli pairings --json`, hato calls
`surasura-cli register`. 🚨 Everything Connect-facing exists ONLY when Surasura is
there (Sonic, 2026-10-12): with no `surasura.json` hato behaves as 1.0.9 did, minus
the folder picker. A failed hand-off is a NOTE, never an error.

⛔ Tests never reach the real folder: `HOUSEKI_TOOLS_DIR` moves it, and the runner
sets it for every suite and checks the real one is untouched afterwards.
"""
from __future__ import unicode_literals

import json
import os
import sys
import threading
import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone

#: The shape version and contract version this hato speaks (`hato-shapes-v2.md` §1-2).
SCHEMA = 1
CONTRACT = 1
#: Both files are small by rule (§1): a bigger one is refused, never read or written.
MAX_BYTES = 4096
#: A torn read (Surasura mid-replace) is tried once more after 50 ms (edge 1).
READ_RETRY_WAIT = 0.05
#: `os.replace` is retried for up to 1 s while a reader holds the file open (P9).
REPLACE_TRIES = 11
REPLACE_WAIT = 0.1
#: A leftover temp of ours older than this is a crashed writer's, and is removed.
STALE_TEMP_SECONDS = 3600

#: The variable that names the shared tools folder (Surasura honours the same one).
TOOLS_DIR_ENV = "HOUSEKI_TOOLS_DIR"
#: ⭐ A7 -- from a SOURCE checkout, hato.json is written only when this names the
#: command line to advertise (`app` is then null): the mirror of Surasura's
#: SURASURA_TOOLS_CLI, so a developer's tree never takes over the real entry.
TOOLS_CLI_ENV = "HATO_TOOLS_CLI"

#: ⭐ LAYER 17 (1.1.1) -- the verbs hato offers Surasura while the hand-off is not off.
#: `pairings`: `hato-cli pairings --json` (16f). `find`: the finder's batch run --
#: `hato-cli <folder> --only-list FILE --json --progress --wait --lang L`, one NDJSON
#: `video` object per listed video (`report.as_dict`), then the `run` object. ⛔ Listed
#: only by a hato that keeps that contract (09-hato-layer.md §7): Surasura sends a
#: hato nothing until its entry names `find` (its `no_subs.HATO_VERB`).
VERBS = ["pairings", "find"]

#: The effective states, in the words the card and the tray key off.
OFF, ABSENT, TOO_NEW, OFFLINE, DROPS, REGISTERS = (
    "off", "absent", "too-new", "offline", "drops", "registers")
STATES = (OFF, ABSENT, TOO_NEW, OFFLINE, DROPS, REGISTERS)

#: What `read_entry` found. `entry` is the parsed dict when `status` is "present".
Entry = namedtuple("Entry", "status entry path")
#: What `state` answers. `folder` is `drop_folders[lang]` on drops / registers.
Link = namedtuple("Link", "state entry folder lang setting")


def tools_dir():
    u"""The shared tools folder. -> str

    `HOUSEKI_TOOLS_DIR`, else the system's per-user LOCAL base + `Houseki/tools`:
    Windows `%LOCALAPPDATA%`, macOS `~/Library/Application Support`, elsewhere
    `$XDG_DATA_HOME` (else `~/.local/share`). ⚠ Exactly Surasura's
    `path_utils.tools_root()` -- two tools that disagree here never meet.
    """
    override = os.environ.get(TOOLS_DIR_ENV)
    if override:
        return override
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "Houseki", "tools")


def _read_json(path):
    u"""-> the parsed object, or None when absent. ⚠ Read WHOLE, then parsed; a
    parse error is tried once more after 50 ms (another tool mid-replace), and a
    file over MAX_BYTES is not read at all."""
    for attempt in range(2):
        try:
            with open(path, "rb") as fh:
                data = fh.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return None
            return json.loads(data.decode("utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if attempt == 0:
                time.sleep(READ_RETRY_WAIT)
    return None


def read_entry(tool="surasura"):
    u"""Another tool's entry in the shared folder. -> Entry

    `status`: "present" · "absent" (no file, unreadable twice, not an object, over
    4 KiB, or its `cli` not a file on disk -- an uninstalled Surasura leaves its
    file behind, edge 2) · "too-new" (`schema` or `contract` above what hato
    speaks: a note, treated as absent). Another tool's `version` is a string hato shows
    and never compares. ⭐ hato's OWN entry is the other way round (`hato_entry`): its
    `version` is hato's real version, and a client may compare it (§7.9).
    """
    path = os.path.join(tools_dir(), "%s.json" % tool)
    found = _read_json(path)
    if not isinstance(found, dict):
        return Entry("absent", None, path)
    schema, contract = found.get("schema"), found.get("contract")
    if type(schema) is not int or type(contract) is not int:
        return Entry("absent", None, path)
    if schema > SCHEMA or contract > CONTRACT:
        return Entry("too-new", found, path)
    cli = found.get("cli")
    if not isinstance(cli, str) or not cli or not os.path.isfile(cli):
        return Entry("absent", None, path)
    return Entry("present", found, path)


def drop_folder(entry, lang):
    u"""`drop_folders[lang]` when it is a non-empty absolute path, else None."""
    folders = (entry or {}).get("drop_folders")
    folder = folders.get(lang) if isinstance(folders, dict) else None
    if isinstance(folder, str) and folder and os.path.isabs(folder):
        return folder
    return None


def verbs(entry):
    u"""The verbs an entry offers, as a tuple of strings (anything else dropped)."""
    found = (entry or {}).get("verbs")
    if not isinstance(found, list):
        return ()
    return tuple(v for v in found if isinstance(v, str))


def state(setting, lang="ja", entry=None):
    u"""The effective state of the hand-off for one language. -> Link

    | hato's setting      | surasura.json                     | ->          |
    | off                 | any                               | off         |
    | auto / on           | absent, or its `cli` gone         | absent      |
    |                     | too new                           | too-new     |
    |                     | no folder for the language        | offline     |
    |                     | `verbs` without `register`        | drops       |
    |                     | `verbs` with `register`           | registers   |

    ⚠ OFFLINE is "no hand-off for this language NOW" (v2.1) -- a NAS library out of
    reach, Surasura not set up for it -- never "uninstalled".
    """
    if setting == "off":
        return Link(OFF, None, None, lang, setting)
    found = entry if entry is not None else read_entry()
    if found.status == "too-new":
        return Link(TOO_NEW, found.entry, None, lang, setting)
    if found.status != "present":
        return Link(ABSENT, None, None, lang, setting)
    folder = drop_folder(found.entry, lang)
    if folder is None:
        return Link(OFFLINE, found.entry, None, lang, setting)
    kind = REGISTERS if "register" in verbs(found.entry) else DROPS
    return Link(kind, found.entry, folder, lang, setting)


# ---------------------------------------------------------------------------
# hato.json -- hato's own entry (P9, P14; A1, A7)
# ---------------------------------------------------------------------------

def advertised():
    u"""(cli, app) this process advertises, or None when it writes no entry.

    Frozen: `hato-cli.exe` and `hato.exe` beside the running exe (app None when
    absent; no `.exe` off Windows). ⭐ From source, only `HATO_TOOLS_CLI` (A7).
    """
    if getattr(sys, "frozen", False):
        here = os.path.dirname(os.path.abspath(sys.executable))
        ext = ".exe" if sys.platform == "win32" else ""
        cli = os.path.join(here, "hato-cli" + ext)
        app = os.path.join(here, "hato" + ext)
        return cli, (app if os.path.isfile(app) else None)
    cli = os.environ.get(TOOLS_CLI_ENV)
    if cli:
        return os.path.abspath(cli), None
    return None


def hato_entry(setting, version=None):
    u"""hato's entry as a dict, or None when this process writes none.

    ⭐ A1 (Surasura confirmed 2026-10-29): `verbs` is `VERBS` unless the setting is
    OFF, then `[]` -- and `cli` STAYS filled, because Surasura drops an entry whose
    `cli` is missing rather than reading it as "hato can't be asked".

    ⭐ `version` MAY BE COMPARED (09-hato-layer.md §7.9, Amendment WP2, countersigned for
    hato 2026-11-12): it is `hato.__version__`, read at the call, in `update.parse_version`'s
    one strict X.Y.Z shape, and Surasura hands a Chinese video only to a hato at or past
    1.3.0. ⛔ So a later hato keeps finding Chinese, or says so in a field; and a release is
    X.Y.Z only -- an `rc` / `.post` stamp reads to a client as no version (Japanese only, fail
    closed), and `test_connect`'s §7.9 check refuses it in the tree. The entry names
    the hato that last wrote it -- after *Go back* the newer one, until the kept hato starts
    -- so a client asks `<cli> --version` before relying on it (§3), and that answer is
    `hato X.Y.Z` on one line (`cli.main`).
    """
    found = advertised()
    if found is None:
        return None
    if version is None:
        from hato import __version__ as version
    cli, app = found
    return {
        "schema": SCHEMA,
        "tool": "hato",
        "name": "hato",
        "version": version,
        "cli": cli,
        "app": app,
        "contract": CONTRACT,
        "verbs": [] if setting == "off" else list(VERBS),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _same(old, new):
    u"""True when every field but `updated` matches: nothing to write."""
    if not isinstance(old, dict):
        return False
    return ({k: v for k, v in old.items() if k != "updated"}
            == {k: v for k, v in new.items() if k != "updated"})


def _clear_stale_temps(folder, prefix):
    u"""Remove OUR leftover temps (`prefix` ... `.tmp`) a crashed writer left, once
    they are an hour old. ⛔ Only names hato makes; never anyone else's file."""
    try:
        names = os.listdir(folder)
    except OSError:
        return
    cutoff = time.time() - STALE_TEMP_SECONDS
    for name in names:
        if not (name.startswith(prefix) and name.endswith(".tmp")):
            continue
        path = os.path.join(folder, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def _may_replace(old, new):
    u"""⭐ LAYER 17 (H6) -- may THIS copy replace the entry that is there? -> bool

    A copy another program holds (`paths.held_by`: Surasura's own, fetched for its
    finder) never takes the entry from a hato the person runs themselves: both would
    rewrite it on every run, and Surasura would ask whichever wrote last. So a held
    copy writes only an entry that is absent, its own, or one whose `cli` is gone (an
    uninstalled hato, edge 2). ⭐ The person's own copy always may: theirs wins."""
    from hato import paths
    if not paths.held_by():
        return True
    if not isinstance(old, dict):
        return True
    cli = old.get("cli")
    if not isinstance(cli, str) or not cli or not os.path.isfile(cli):
        return True
    return os.path.normcase(os.path.abspath(cli)) == os.path.normcase(new["cli"])


def write_hato_json(setting, entry=None, version=None):
    u"""Write `hato.json` when a field other than `updated` differs. -> True if written.

    Written while Surasura is there (or the setting is a hand-written `on`, P14);
    with the setting OFF it is REWRITTEN with `"verbs": []` when it exists or
    Surasura does -- never deleted (A1: a file goes only on uninstall). Atomic:
    `hato.json.<pid>.<thread>.tmp` -> flush -> fsync -> `os.replace`, retried for up
    to 1 s while a reader holds it. ⛔ Never a secret; ≤ 4 KiB. A failure is
    returned as False -- the caller logs it; a run never fails on it.
    ⭐ 16z (Z-A7) -- `version`: the hato that will answer (Go back names the kept one).
    """
    folder = tools_dir()
    path = os.path.join(folder, "hato.json")
    found = entry if entry is not None else read_entry()
    exists = os.path.isfile(path)
    if setting == "off":
        if not (exists or found.status == "present"):
            return False
    elif setting != "on" and found.status != "present":
        return False
    new = hato_entry(setting, version)
    if new is None:
        return False
    old = _read_json(path)
    if _same(old, new):
        return False
    if not _may_replace(old, new):
        return False
    data = (json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_BYTES:
        return False
    os.makedirs(folder, exist_ok=True)
    _clear_stale_temps(folder, "hato.json.")
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
    written = False
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(REPLACE_TRIES):
            try:
                os.replace(tmp, path)
                written = True
                break
            except PermissionError:
                if attempt < REPLACE_TRIES - 1:
                    time.sleep(REPLACE_WAIT)
        return written
    finally:
        if not written:
            try:
                os.remove(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# the pairing record v1 (hato-shapes-v2.md §3)
# ---------------------------------------------------------------------------

#: tsubasa's `reference_kind` -> the contract's `reference`. Anything else is
#: OMITTED (Surasura then checks the timing itself) -- never guessed.
REFERENCES = {"text track": "text-track", "bitmap track": "picture-track",
              "speech mask": "speech-mask"}
#: The four verdicts, and the provider names a record carries.
TIMED, FORCED, EXTRACTED, UNTIMED = "timed", "forced", "extracted", "untimed"


def utc_stamp(moment=None):
    u"""ISO-8601 UTC at second precision: `2026-10-14T09:31:07Z`."""
    moment = moment or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path):
    u"""-> the lowercase hex sha256 of a file, read once in 1 MiB blocks."""
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verdict_of(result, forced=False):
    u"""The record's `verdict`, FROM THE ROAD a kept file came by -- ⛔ never from
    CONFIDENT: a 14c extraction and a Layer 15 placement are CONFIDENT inside hato,
    and neither was timed by tsubasa on this video. -> (verdict, untimed_tier)"""
    if getattr(result, "taken_from", None):
        return EXTRACTED, None
    untimed = getattr(result, "untimed", None)
    if untimed:
        tier = untimed.get("tier") if isinstance(untimed, dict) else None
        return UNTIMED, (tier if tier in ("exact", "same", "other") else None)
    return (FORCED if forced else TIMED), None


def timing_of(tsubasa_result, verdict):
    u"""The record's `timing` -- on `timed` / `forced` only, else None."""
    if verdict not in (TIMED, FORCED) or tsubasa_result is None:
        return None
    import tsubasa
    timing = {"outcome": getattr(tsubasa_result, "outcome", None),
              "match_rate": getattr(tsubasa_result, "match_rate", None),
              "offset_s": getattr(tsubasa_result, "offset", None),
              "segments": len(getattr(tsubasa_result, "segments", None) or ()),
              "tsubasa_version": getattr(tsubasa, "__version__", None)}
    reference = REFERENCES.get(getattr(tsubasa_result, "reference_kind", None))
    if reference:
        timing["reference"] = reference
    return timing


def record(*, video, subtitle_path, library_path, verdict, content_key=None,
           subtitle_sha256=None, untimed_tier=None, picked_by="hato", timing=None,
           show=None, jimaku_entry_id=None, anilist_id=None, tmdb_id=None,
           source_provider="jimaku", source_name=None, paired_at=None, lang="ja"):
    u"""The pairing record v1, every field present (`hato-shapes-v2.md` §3). -> dict

    ⭐ ONE FUNCTION FOR EVERY ROAD (a run's download, a re-sync, 14c, Layer 15, the
    window's pick). `content_key` is `cache.video_hash` unchanged; `video_size` one
    `stat`; `subtitle_sha256` the file beside the video, read once (the library copy
    must equal it). `tmdb_id` only in jimaku's own shape (A5).
    """
    from hato import __version__, cache
    video = os.path.abspath(os.fspath(video))
    if verdict not in (TIMED, FORCED, EXTRACTED, UNTIMED):
        raise ValueError("verdict must be timed, forced, extracted or untimed, got %r" % verdict)
    if tmdb_id is not None and not (isinstance(tmdb_id, str) and _TMDB.match(tmdb_id)):
        tmdb_id = None
    return {
        "schema": 1,
        "content_key": content_key or cache.video_hash(video),
        "producer": "hato",
        "producer_version": __version__,
        "language": lang,
        "video_path": video,
        "video_size": os.stat(video).st_size,
        "subtitle_path": os.path.abspath(os.fspath(subtitle_path)),
        "library_path": (os.path.abspath(os.fspath(library_path))
                         if library_path else None),
        "subtitle_sha256": subtitle_sha256 or file_sha256(subtitle_path),
        "verdict": verdict,
        "untimed_tier": untimed_tier if verdict == UNTIMED else None,
        "picked_by": picked_by,
        "timing": timing if verdict in (TIMED, FORCED) else None,
        "show": show,
        "jimaku_entry_id": jimaku_entry_id,
        "anilist_id": anilist_id,
        "tmdb_id": tmdb_id,
        "subtitle_source": {"provider": source_provider,
                            "file_name": source_name or os.path.basename(subtitle_path)},
        "paired_at": paired_at or utc_stamp(),
    }


_TMDB = __import__("re").compile(r"^(tv|movie):[0-9]+$")


# ---------------------------------------------------------------------------
# the drop (16d) and register (16e)
# ---------------------------------------------------------------------------

#: ⭐ A2 (Surasura confirmed 2026-10-29): the copy's temp inside the drop folder.
#: Surasura's scans take only names ending .txt .md .srt .ass .ssa, so the temp must
#: never end in one -- nor in a video, epub or audio ending. `.hato-<pid>.tmp`.
DROP_TEMP_PREFIX = ".hato-"
DROP_TEMP_SUFFIX = ".tmp"
#: A drop whose library is offline is tried again on each run for this long.
DROP_WAIT_DAYS = 14
#: Windows' path limit, unless long paths are on; and the shortest a cut series gets.
WIN_PATH_MAX = 259
SERIES_MIN = 16
#: `register`'s call, and its bounds (P3, P4, P11).
REGISTER_WAIT = 10
REGISTER_TIMEOUT = 30
RECORD_MAX = 64 * 1024


def _long_paths():
    u"""True when Windows' long paths are switched on (or not Windows at all)."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0])
    except OSError:
        return False


def series_name(*, kept_path=None, subs_dir=None, entry_name=None, video=None):
    u"""The per-series folder's name. ⭐ The kept original's own entry folder (a run's
    download and a re-sync keep it in `subs_dir/<entry>`, `keep.entry_folder`); else
    the jimaku entry's name as `keep.entry_folder` names it; else (14c, a pick of a
    file from elsewhere) the video's parent folder's name."""
    from hato import cache
    if kept_path and subs_dir:
        parent = os.path.dirname(os.path.abspath(os.fspath(kept_path)))
        if os.path.normcase(os.path.dirname(parent)) == os.path.normcase(
                os.path.abspath(os.fspath(subs_dir))):
            return os.path.basename(parent)
    if entry_name:
        return cache.safe_name(str(entry_name))
    if video:
        return cache.safe_name(os.path.basename(os.path.dirname(os.path.abspath(video)))
                               or u"hato")
    return u"hato"


def drop_target(folder, series, name, limit=None):
    u"""`folder/series/name` inside the path budget, or None when it cannot fit.

    ⭐ The whole target ≤ 259 characters unless long paths are on: over it, the
    `series` part is cut (never below 16 characters) and given `~` + 6 hex of the
    full name's sha256; still over -> None (the caller notes *"too long for Windows"*).
    """
    import hashlib
    limit = limit if limit is not None else (None if _long_paths() else WIN_PATH_MAX)
    target = os.path.join(folder, series, name)
    if limit is None or len(target) <= limit:
        return target
    tag = u"~" + hashlib.sha256(series.encode("utf-8")).hexdigest()[:6]
    room = limit - len(folder) - len(name) - len(tag) - 2      # two separators
    if room < SERIES_MIN:
        return None
    cut = series[:room].rstrip(u" .") + tag
    target = os.path.join(folder, cut, name)
    return target if len(target) <= limit else None


def library_there(folder):
    u"""⭐ v2.1: the drop folder is made only when its PARENT exists (`…\\HighPriority`):
    missing, the library is offline (a NAS asleep), never a folder to invent. The ONE
    test -- the drop, the window's card and the tray's line all ask it."""
    if not folder:
        return False
    parent = os.path.dirname(os.path.normpath(folder))
    return bool(parent) and os.path.isdir(parent)


def _suffixed(name, content_key):
    u"""`<stem> [<6 hex>]<.ja.ass>` -- edge 8's name for a second video's drop."""
    from hato import cache
    stem, ext = cache._split_ext(name)
    tag = content_key.split("-", 1)[-1][:6]
    return u"%s [%s]%s" % (stem, tag, ext)


class Handoff(object):
    u"""One run's hand-off to Surasura (or one pick's). Read once, used for every
    kept file. ⛔ Never raises into the caller: everything goes to `notes`.

        h = Handoff(db, cfg.surasura_connect, subs_dir=...)
        h.keep(video=..., subtitle_path=..., verdict=..., ...)   after each kept file
        h.retry()                                                once per run

    `call` (a test seam) runs `register`: `call(argv, stdin_bytes, timeout)` ->
    (exit code, stdout text).
    """

    def __init__(self, db, setting, subs_dir=None, link=None, now=None, call=None):
        self.db = db
        self.setting = setting
        self.subs_dir = subs_dir
        self.link = link if link is not None else state(setting)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._call = call or _call_register
        #: ⭐ A4 -- after the first exit 2, 3 or 4 this run, no more calls this run.
        self.halted = None
        #: ⚠ 16z (Z-A5) -- an exit 2 an EARLIER run met holds too, until surasura.json's
        #: `updated` moves: asked once, at the first call (`_stopped`).
        self._asked = False
        #: ⚠ 16z (Z-A1) -- the videos this run already tried: `retry()` leaves them to the
        #: next run (one try per pairing per run, A4).
        self._tried = set()
        self.notes = []
        self.counts = {"dropped": 0, "registered": 0, "waiting": 0}

    @property
    def live(self):
        return self.link.state in (OFFLINE, DROPS, REGISTERS)

    # -- one kept file ------------------------------------------------------------

    def keep(self, *, video, subtitle_path, verdict, series, untimed_tier=None,
             picked_by="hato", timing=None, show=None, jimaku_entry_id=None,
             anilist_id=None, tmdb_id=None, source_provider="jimaku", source_name=None,
             content_key=None):
        u"""Record, copy and (when Surasura offers it) register one kept file.
        -> the state the pairing ends in, or None when Connect is not live."""
        if not self.live:
            return None
        try:
            from hato import cache
            content_key = content_key or cache.video_hash(video)
            self._tried.add(content_key)
            if show is None and jimaku_entry_id is None:
                # ⭐ A6 -- a re-sync: the show and ids from this video's latest pairing
                earlier = self.db.latest_pairing(content_key, self.link.lang)
                if earlier is not None:
                    old = earlier.record
                    show, jimaku_entry_id = old.get("show"), old.get("jimaku_entry_id")
                    anilist_id, tmdb_id = old.get("anilist_id"), old.get("tmdb_id")
            rec = record(video=video, subtitle_path=subtitle_path, library_path=None,
                         verdict=verdict, content_key=content_key,
                         untimed_tier=untimed_tier, picked_by=picked_by, timing=timing,
                         show=show, jimaku_entry_id=jimaku_entry_id, anilist_id=anilist_id,
                         tmdb_id=tmdb_id, source_provider=source_provider,
                         source_name=source_name, paired_at=utc_stamp(self._now()),
                         lang=self.link.lang)
            rec["_series"] = series
            return self._deliver(rec)
        except Exception as exc:                     # noqa: BLE001 -- a note, never an error
            self.notes.append(u"Surasura was not handed %s: %s"
                              % (os.path.basename(os.fspath(subtitle_path)), exc))
            return None

    def _deliver(self, rec):
        u"""Drop `rec`'s file into the library, then register it. -> the row's state."""
        series = rec.pop("_series", None) or u"hato"
        if self.link.state == OFFLINE or not self._library_there():
            rec["library_path"] = None
            self.db.add_pairing(dict(rec, _series=series), "drop-waiting")
            self.counts["waiting"] += 1
            return "drop-waiting"
        target = self._copy(rec, series)
        if target is None:
            return None
        rec["library_path"] = target
        self.counts["dropped"] += 1
        if self.link.state != REGISTERS:
            self.db.add_pairing(rec, "dropped")
            return "dropped"
        return self._register(rec)

    def _library_there(self):
        return library_there(self.link.folder)

    def _copy(self, rec, series):
        u"""The copy, atomically, into `<drop>/<series>/`. -> the target, or None (a note)."""
        name = os.path.basename(rec["subtitle_path"])
        target = drop_target(self.link.folder, series, name)
        if target is None:
            self.notes.append(u"%s was not copied to Surasura: the path is too long for "
                              u"Windows" % name)
            return None
        target = self._free_name(target, rec["content_key"])
        if target is None:
            self.notes.append(u"%s was not copied to Surasura: another file has its name "
                              u"there" % name)
            return None
        folder = os.path.dirname(target)
        os.makedirs(folder, exist_ok=True)
        _clear_stale_temps(folder, DROP_TEMP_PREFIX)
        tmp = os.path.join(folder, "%s%d%s" % (DROP_TEMP_PREFIX, os.getpid(), DROP_TEMP_SUFFIX))
        try:
            import shutil
            with open(rec["subtitle_path"], "rb") as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)   # ⛔ the bytes as they are
                out.flush()
                os.fsync(out.fileno())
            if file_sha256(tmp) != rec["subtitle_sha256"]:
                raise OSError("the copy's bytes differ from the subtitle beside the video "
                              "(it changed while it was copied)")
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return target

    def _free_name(self, target, content_key):
        u"""⭐ Edge 8: replace a file only when the ledger says it is THIS video's earlier
        drop; otherwise ` [<6 hex of content_key>]` -- never over what hato can't
        account for. -> the path to write, or None."""
        for path in (target, os.path.join(os.path.dirname(target),
                                          _suffixed(os.path.basename(target), content_key))):
            if not os.path.lexists(path):
                return path
            mine = self.db.pairing_at(path)
            if mine is not None and mine.content_key == content_key:
                return path
        return None

    # -- register ---------------------------------------------------------------------

    def _stopped(self):
        u"""⚠ 16z (Z-A5) -- this run's stop, else one on record: the latest row of a video
        `stopped` under THIS surasura.json's `updated` (the gate `_retry_one` keeps). An
        exit 2 is lifted only by a new `updated`, so the next run, and every pick, must
        not call again before it. -> the stop's code, or None."""
        if self.halted or self._asked:
            return self.halted
        self._asked = True
        updated = (self.link.entry or {}).get("updated")
        try:
            for row in self.db.pairings(self.link.lang, states=("stopped",)):
                if row.gate != "never" and row.gate == updated:
                    self.halted = row.last_code or "usage"
                    break
        except Exception:                            # noqa: BLE001 -- the call decides
            pass
        return self.halted

    def _register(self, rec):
        if self._stopped():
            self.db.add_pairing(rec, "retry", last_code="deferred")
            return "retry"
        cli = (self.link.entry or {}).get("cli")
        if not isinstance(cli, str) or not os.path.isfile(cli):
            self.db.add_pairing(rec, "dropped")
            return "dropped"
        data = json.dumps(rec, ensure_ascii=False).encode("utf-8")
        if len(data) > RECORD_MAX:
            self.db.add_pairing(rec, "bad-data", last_code="too-big",
                                gate=rec["subtitle_sha256"])
            return "bad-data"
        argv = [cli, "register", "--lang", rec["language"], "--pairing", "-",
                "--wait", str(REGISTER_WAIT)]
        try:
            code, out = self._call(argv, data, REGISTER_TIMEOUT)
        except Exception as exc:                     # noqa: BLE001 -- a crash is `failed`
            code, out = None, u""
            self.notes.append(u"Surasura's command line did not answer: %s" % exc)
        answer = _last_json(out)
        got = answer.get("code") if isinstance(answer, dict) else None
        entry = self.link.entry or {}
        if code == 0 and isinstance(answer, dict) and answer.get("ok") is True:
            if answer.get("landed") == "skipped":
                self.db.add_pairing(rec, "skipped", last_code="skipped")
                return "skipped"
            # ⭐ v2.1: `already` + `pairing: new` is a success, on a first drop too
            self.db.add_pairing(rec, "registered", file_id=answer.get("file_id"),
                                registered_at=utc_stamp(self._now()),
                                last_code=answer.get("pairing") or answer.get("landed"))
            self.counts["registered"] += 1
            return "registered"
        if code == 1 and got == "bad-data":
            self.db.add_pairing(rec, "bad-data", last_code=got, gate=rec["subtitle_sha256"])
            self.notes.append(u"Surasura refused %s's details (%s)"
                              % (os.path.basename(rec["library_path"]),
                                 answer.get("message") or got))
            return "bad-data"
        if code == 2:
            self.halted = got or "usage"
            self.db.add_pairing(rec, "stopped", last_code=self.halted,
                                gate=entry.get("updated"))
            self.notes.append(u"Surasura stopped taking subtitles (%s) until it changes"
                              % self.halted)
            return "stopped"
        if code in (3, 4):
            self.halted = got or ("busy" if code == 3 else "needs-you")
            gate = entry.get("version") if got == "update-staged" else None
            self.db.add_pairing(rec, "retry", last_code=self.halted, gate=gate)
            return "retry"
        self.db.add_pairing(rec, "retry", last_code=got or "failed")
        return "retry"

    # -- the next run's retries ----------------------------------------------------------

    def retry(self):
        u"""Once per run: deliver drops that waited, re-register what is due. Oldest
        first, one try each, never a loop; stops at the first exit 2, 3 or 4 (A4)."""
        if self.link.state not in (DROPS, REGISTERS):
            return
        try:
            due = self.db.pairings(self.link.lang, states=("drop-waiting", "retry",
                                                           "stopped", "bad-data"))
        except Exception as exc:                     # noqa: BLE001
            self.notes.append(u"Surasura's waiting subtitles could not be read: %s" % exc)
            return
        for row in due:
            try:
                self._retry_one(row)
            except Exception as exc:                 # noqa: BLE001
                self.notes.append(u"a waiting subtitle was not handed to Surasura: %s" % exc)

    def _retry_one(self, row):
        if row.content_key in self._tried:
            return                                   # ⚠ 16z (Z-A1): tried this run
        self._tried.add(row.content_key)
        rec = dict(row.record)
        entry = self.link.entry or {}
        if row.state == "drop-waiting":
            since = _parse_stamp(rec.get("paired_at"))
            if since is not None and self._now() - since > timedelta(days=DROP_WAIT_DAYS):
                rec.pop("_series", None)
                self.db.add_pairing(rec, "stopped", last_code="drop-expired",
                                    gate="never")
                self.notes.append(u"%s waited %d days for Surasura's library and stopped"
                                  % (os.path.basename(rec["subtitle_path"]), DROP_WAIT_DAYS))
                return
            if not os.path.isfile(rec["subtitle_path"]):
                return
            if file_sha256(rec["subtitle_path"]) != rec["subtitle_sha256"]:
                return                               # a newer keep carries the new file
            self._deliver(rec)
            return
        if self.link.state != REGISTERS or self._stopped():
            return
        if not rec.get("library_path") or not os.path.isfile(rec["library_path"]):
            return
        if row.state == "stopped" and (row.gate == "never" or row.gate == entry.get("updated")):
            return
        if row.state == "bad-data" and file_sha256(rec["library_path"]) == row.gate:
            return
        if row.state == "retry" and row.gate and row.gate == entry.get("version"):
            return
        self._register(rec)


def _parse_stamp(text):
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _last_json(text):
    u"""stdout's LAST JSON line, as a dict, or None (exit 0 with none = `failed`)."""
    for line in reversed((text or u"").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            found = json.loads(line)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


#: ⚠ 16z (Z-A2) -- after the tree is killed, how long what is left may take to read.
KILLED_READ_WAIT = 2


def _kill_tree(proc):
    u"""⚠ 16z (Z-A2) -- end `proc` AND everything it started. 🚨 A `.cmd` cli hands its
    stdout to the python it starts: killing the cmd alone left that grandchild holding
    the pipe, and the read waited for it (8 s for a 1 s ceiling). Windows: `taskkill /T
    /F` while the parent still stands (the tree is found through it); elsewhere the
    child's own session. ⛔ Never raises."""
    import subprocess
    if sys.platform == "win32":
        taskkill = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32",
                                "taskkill.exe")
        try:
            subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _call_register(argv, data, timeout):
    u"""Run `surasura-cli register`: the record on STDIN (⛔ never argv, which Surasura
    logs), no console window, stdout read to EOF. -> (exit code, stdout text).
    ⚠ 16z (Z-A2) -- past `timeout` the whole process TREE is killed before what is left
    is read (`_kill_tree`), then `subprocess.TimeoutExpired` is raised: the ceiling holds."""
    import subprocess
    windows = sys.platform == "win32"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if windows else 0
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, creationflags=flags,
                            start_new_session=not windows)
    try:
        out, _ = proc.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=KILLED_READ_WAIT)
        except subprocess.TimeoutExpired:
            pass
        raise
    except BaseException:
        _kill_tree(proc)
        raise
    return proc.returncode, out.decode("utf-8", "replace")


def handoff_lang(lang):
    u"""⭐ LAYER 20 -- the `drop_folders` key a run hands over under: `zh` for a Chinese
    run, `ja` for every other (as every hato before 1.3 did, whatever `lang` said)."""
    from hato import config
    return u"zh" if config.is_chinese(lang) else u"ja"


def refresh(setting, lang="ja"):
    u"""Read surasura.json once and keep hato.json in step. -> Link for `lang`.

    🚨 LAYER 20 -- `lang`: until 1.3 this was always `ja`, so a `--lang zh` run (Surasura
    sends one for a Chinese library) would have handed its file to the JAPANESE drop
    folder under `"language": "ja"`. The run passes `handoff_lang(settings.lang)`.

    ⭐ Called at the start of the window, the tray and each run (once per run, once
    per window refresh). ⛔ Never raises: Connect is never why hato fails."""
    try:
        found = read_entry()
    except Exception:
        found = Entry("absent", None, None)
    try:
        write_hato_json(setting, found)
    except Exception:
        pass
    return state(setting, lang, found)


#: ⭐ 16g -- what the window's card and the tray's line are drawn from: the effective
#: state, the pairing counts (`state.pairing_counts`, every PAIRING_STATES + EXPIRED),
#: and whether the library is reachable right now (`library_there`; False off
#: drops / registers). `counts` is {} when the store could not be read.
Status = namedtuple("Status", "link counts reachable")


def status(setting, db_path=None):
    u"""The hand-off as a person is told it. -> Status

    ⭐ `refresh` (surasura.json read once, hato.json kept in step), then the store's
    counts, read-only. ⛔ Never raises: an unreadable store counts nothing."""
    link = refresh(setting)
    try:
        from hato import state as _state
        counts = _state.pairing_counts(db_path, link.lang)
    except Exception:                                # noqa: BLE001 -- a count, never a stop
        counts = {}
    there = link.state in (DROPS, REGISTERS) and library_there(link.folder)
    return Status(link, counts, there)


def watched(found=None):
    u"""What moves a Status besides the setting and the store: surasura.json's stamp
    and whether the library `found` names is reachable. -> a comparable tuple. ⭐ Two
    `stat`s, so the window and the tray look every tick and read only when it moved
    (Surasura installed, its library moved, a NAS back)."""
    try:
        seen = os.stat(os.path.join(tools_dir(), "surasura.json"))
        stamp = (seen.st_mtime_ns, seen.st_size)
    except OSError:
        stamp = None
    folder = found.link.folder if found is not None else None
    return (stamp, library_there(folder) if folder else None)


__all__ = ["SCHEMA", "CONTRACT", "STATES", "OFF", "ABSENT", "TOO_NEW", "OFFLINE", "DROPS",
           "REGISTERS", "Entry", "Link", "Status", "tools_dir", "read_entry", "drop_folder",
           "verbs", "VERBS", "state", "advertised", "hato_entry", "write_hato_json",
           "refresh",
           "library_there", "status", "watched"]
