# -*- coding: utf-8 -*-
u"""
The fetch loop (RUNBOOK 4b) -- `spec/03-permissions.md` §*The read rule*, built
as it is written there.

    settings = pipeline.Settings.from_config(config.load(), folders=[...])
    report   = pipeline.run(settings, client=client, db=db, resolutions=cache)

    for r in report.results:
        r.outcome        CONFIDENT · REFUSED · ERROR · NOT_FOUND · SKIPPED · PLANNED
        r.skip           why it was skipped -- present · blacklisted · embedded ·
                         no-track · negative
        r.reason         🚨 never empty except on a plain CONFIDENT

⭐ THE READ RULE, IN ORDER, AND THE ORDER IS THE DESIGN::

    does another video want     REFUSED -- ⛔ BEFORE the present-check: once one of
    the SAME target file?       the two has been written for, *present* is true for
                                BOTH and the loser reads the winner's file as its own
    present in the TARGET dir?  SKIP -- opens nothing, reads no DB, costs N stats
    blacklisted?                SKIP -- ⛔ --force does NOT override it, and ⛔ it is
                                asked BEFORE hato's own episode-span refusal
    two episodes in the name?   REFUSED -- one subtitle cannot be split
    the container's tracks      ok=False -> ERROR before any download
                                a ja TEXT track -> SKIP (already in sync)
                                no track, or none usable -> SKIP, ⛔ never a refusal
    a negative, hard OR soft?   SKIP with its retry date, unless --force
    a kept original, no file?   re-sync -- ZERO network
    ---------------------------- everything above is free; below costs quota ----
    identify the show            <= 1 metered call, cached for ever
    list the entry's files       1 metered call, ⛔ no `episode=`
    align, then rank             pure arithmetic
    drop candidates already refused for THIS video, then try up to the cap
    every one refused            record a SOFT negative, then REFUSED

⛔ NOTE WHAT IS NOT IN THE CANDIDATE LOOP: no metered call at all. A run over a
folder where nothing changed makes ZERO -- it never reaches identification.

===========================================================================
🚨 THE THREE THINGS THIS STEP IS MOST LIKELY TO GET WRONG. ALL MEASURED.
===========================================================================

1. **The present-check looks in the TARGET directory.** Under `--out` the
   previous run's file is in the MIRRORED directory, never beside the video.
   Miss it and hato re-fetches every run and tsubasa refuses the write for ever
   (CONFIDENT, `write_failed`, no file). `keep.target_dir()` is the ONE answer,
   asked by the present-check and by the write alike.
2. **The original carries `.ja` before its extension.** Untagged, tsubasa writes
   `<video>.ass` with no tag and `unpaired(lang="ja")` reads that as no Japanese
   subtitle. `keep.download_name()` composes it and asserts the round trip.
3. ⛔ **CONFIDENT is not WRITTEN, and "nothing written" is TWO shapes.**
   `port.wrote()` is the only success test here; `port.why_nothing_was_written()`
   carries tsubasa's own words. A dry run (`write_failed False`) and a write that
   did not land (`write_failed True`) are different sentences and 5a prints them
   apart -- `result.tsubasa` is passed through so it can.

===========================================================================
⛔ THE DB MAY NEVER BE THE REASON A FILE GETS WRITTEN
===========================================================================

`02-data-model.md`: the filesystem is canonical; the state DB is advisory and
only ever PREVENTS work. The one place a row leads to a write is the kept-original
re-sync -- and there the file on disk is stat'ed first, the timing verdict still
decides, and tsubasa refuses a destination it did not account for. A bug in the
DB costs a skipped fetch, never an overwrite.

===========================================================================
⚠ WHAT THIS STEP DELIBERATELY DOES NOT DO
===========================================================================

* ⛔ **It prints nothing.** 5a renders `report`; the library API returns it.
* ⛔ **It takes no run lock.** One run at a time is the CLI's to hold
  (`hato/runlock.py`, 06 §9), because a library caller may already hold one.
* ⚠ **It does not open archives.** See `_archive_note` -- a recorded defect.
"""
import os
import time
from collections import OrderedDict

import tsubasa

from hato import archives, cache as _cache, client as _client, episodes, formats, \
    keep, paths, port, present, rank, tokens
from hato.cache import Cache
from hato.resolution import Resolved, cache_key, identify

#: The outcomes. The first four are `03-permissions.md`'s and `hato/state.py`'s;
#: the last two are shapes a RUN has and a stored attempt does not.
CONFIDENT = u"CONFIDENT"
REFUSED = u"REFUSED"
ERROR = u"ERROR"
NOT_FOUND = u"NOT_FOUND"
#: Decided before anything was fetched. ⭐ *"No subtitle track" is a SKIP, not a
#: fifth outcome* (ruled 2026-09-17) -- and so is every other row below.
SKIPPED = u"SKIPPED"
#: `--dry-run`: what the run WOULD do. ⛔ Nothing downloaded, nothing written,
#: no row recorded.
PLANNED = u"PLANNED"

#: `VideoResult.skip`.
PRESENT = u"present"
BLACKLISTED = u"blacklisted"
EMBEDDED = u"embedded"
NO_TRACK = u"no-track"
NEGATIVE = u"negative"

#: ⭐ A LOW CONFIDENCE identification *"raises the candidate cap"* (06 §1); by how
#: much was never said, and this is the value ruled for 4b. The timing verdict
#: still decides -- a higher cap only buys more chances to be refused.
LOW_CONFIDENCE_EXTRA = 2

#: ⭐ How many runner-up entries `_escalate` may try when the chosen one holds
#: nothing for any video. Each costs ONE metered `files` call, and the cache is
#: repointed at whichever works, so the price is paid once per show, ever.
#: ⛔ Bounded so a title nobody has cannot walk the catalogue at 25 calls/60 s.
ALTERNATE_ENTRIES = 2

#: ⭐ How many batch archives a show may open when `--archives` is on. ONE: they are
#: the most expensive thing on an entry (One Piece's run to hundreds of megabytes for
#: a single episode), and a second one is unlikely to hold what the first did not.
ARCHIVES_PER_SHOW = 1

#: ⚠ These stop the WHOLE run, not one show: a 401 still spends quota, and six
#: consecutive unanswered requests mean the network is gone.
_STOPPERS = (_client.KeyRejected, _client.Unreachable, _client.RateLimited,
             _client.NetworkDisabled)
#: ⚠ Anything one SHOW can fail on, leaving the others to run. `NoRecording` is
#: in here because `--fixtures` serves recorded responses and a request nobody
#: captured is that show's problem, not the run's -- `hato identify` already
#: treats the two alike, and it is a LookupError rather than a JimakuError.
_SHOW_FAILURES = (_client.JimakuError, _client.NoRecording)


class ConfigProblem(Exception):
    u"""The run cannot start. ⛔ Raised before anything is scanned or asked."""


class _Stop(Exception):
    u"""Internal: the run ends here. Carries the sentence a person reads."""


# ---------------------------------------------------------------------------
# what a run was asked for
# ---------------------------------------------------------------------------

class Settings(object):
    u"""One run's inputs, with the CLI's flags already laid over config.toml.

    ⭐ Built here rather than in `hato/config.py` because *"CLI over config"* is
    a property of a RUN, and `config.py`'s schema is closed -- an unknown key
    there is refused by name (`05-interface.md`), which is what makes a typo
    impossible to mistake for a setting that took.
    """

    __slots__ = ("folders", "skip_folders", "lang", "out", "subs_dir",
                 "candidates", "archives",
                 "allow_ai", "recurse", "force", "dry_run", "skip_embedded",
                 "surasura_dir", "retry_now", "only", "prefer_format",
                 "format_fallback", "extract_embedded")

    def __init__(self, folders, lang=u"ja", out=None, subs_dir=None, candidates=3,
                 # ⚠ `archives=False`, matching `config.py`'s schema. It was True
                 # here while the config default was False -- so a library caller
                 # (`Settings(folders=[...])`) got archives ON, against the 2026-09-17
                 # ruling, and only the CLI road obeyed it. Found because a check
                 # written to prove the OFF path was quietly running the ON one.
                 archives=False, allow_ai=False, recurse=True, force=False,
                 # ⚠ `[]`, NOT `()`, AND A CHECK REQUIRES IT. `test_api.py`'s
                 # defaults guard asserts every Settings default EQUALS
                 # `config.py`'s schema default, because `archives` once shipped
                 # True here and False there -- so a library caller got archives
                 # ON against the ruling and only the CLI road obeyed it.
                 # ⛔ Never mutated: the line below copies it into a tuple.
                 dry_run=False, skip_embedded=True, skip_folders=[],
                 surasura_dir="", retry_now=False, only=(),
                 # ⭐ 9a -- `config.py`'s defaults, as the guard above requires.
                 prefer_format=formats.DEFAULT_PREFERENCE, format_fallback=False,
                 # ⭐ 14c -- and its default too.
                 extract_embedded=False):
        self.folders = tuple(os.path.abspath(os.fspath(f)) for f in folders)
        # ⭐ RUNBOOK 7e. Subtrees carved OUT of `folders` -- Sonic: *"someone
        # might say 'desktop' and then not want a certain folder checked on
        # desktop."* ⛔ It is applied to what the scan FOUND, not to the roots:
        # a skip is usually a folder inside a watched one, so filtering roots
        # would silently do nothing at all -- which is the failure this setting
        # was added to avoid, rebuilt one level down.
        self.skip_folders = tuple(os.path.abspath(os.fspath(f))
                                  for f in (skip_folders or ()))
        self.lang = lang
        self.out = os.path.abspath(os.fspath(out)) if out else None
        self.subs_dir = os.path.abspath(os.fspath(subs_dir)) if subs_dir else None
        self.candidates = candidates
        self.archives = archives
        self.allow_ai = allow_ai
        self.recurse = recurse
        self.force = force
        self.dry_run = dry_run
        # ⭐ RULED 2026-09-17 (Sonic): a toggle for *"if they have it toggled, it will
        # find another one even if there already is a japanese track on it"*. Default
        # TRUE -- an embedded Japanese track is a subtitle, in sync, for free (01-scope
        # launch 16). ⚠ Off, the video is fetched for anyway, and that embedded track
        # becomes the REFERENCE tsubasa times the download against: the best reference
        # there is, because it is the same rip.
        self.skip_embedded = skip_embedded
        # ⭐ RUNBOOK 7h. Empty means OFF, which is the default -- most people do
        # not run surasura, and a run that quietly wrote files somewhere new
        # would be a surprise rather than a feature.
        self.surasura_dir = (os.path.abspath(os.fspath(surasura_dir))
                             if surasura_dir else u"")
        # ⭐ RUNBOOK 8e -- *Look again now* on one row (D3). `retry_now` ignores
        # the WAITING PERIOD and nothing else: a blacklist still stands and a file
        # already refused for the video is still never downloaded again -- which
        # is exactly where it differs from `force`. `only` keeps the run to the
        # named videos inside the folders it was given.
        self.retry_now = bool(retry_now)
        self.only = tuple(os.path.abspath(os.fspath(v)) for v in (only or ()))
        # ⭐ RUNBOOK 9a (`hato/formats.py`). ⛔ With the fallback OFF -- the
        # default, ruled -- nothing but the preferred kind is ever downloaded.
        if prefer_format not in formats.PREFERENCES:
            raise ValueError(u"prefer_format must be one of %s, got %r"
                             % (u", ".join(formats.PREFERENCES), prefer_format))
        self.prefer_format = prefer_format
        self.format_fallback = bool(format_fallback)
        # ⭐ RUNBOOK 14c (Sonic, 2026-09-25) -- a video's own Japanese track TAKEN
        # OUT and saved beside it, as a file. ⚠ It wins over `skip_embedded`
        # (`formats.embedded_choice`).
        self.extract_embedded = bool(extract_embedded)

    @classmethod
    def from_config(cls, cfg, **given):
        u"""config.toml, with anything the caller passes winning over it.

        ⚠ `None` means *not given*, so `--force` off and `folders` unset are
        told apart from `folders = []` in the file.
        """
        def pick(name, fallback):
            value = given.get(name)
            return fallback if value is None else value

        folders = pick("folders", cfg.folders)
        if not folders:
            raise ConfigProblem(
                u"no folder to scan: none was given on the command line and "
                u"`folders` is empty in %s. Add one, or pass a folder."
                % (cfg.path if cfg.path else u"config.toml"))
        return cls(folders=folders,
                   skip_folders=pick("skip_folders", cfg.skip_folders),
                   lang=pick("lang", cfg.lang),
                   out=pick("out", cfg.out or None),
                   subs_dir=pick("subs_dir", cfg.subs_dir_resolved),
                   candidates=pick("candidates", cfg.candidates),
                   archives=pick("archives", cfg.archives),
                   allow_ai=pick("allow_ai", cfg.allow_ai),
                   recurse=pick("recurse", cfg.recurse),
                   force=bool(given.get("force")),
                   dry_run=bool(given.get("dry_run")),
                   skip_embedded=pick("skip_embedded", cfg.skip_embedded),
                   surasura_dir=pick("surasura_dir", cfg.surasura_dir),
                   retry_now=bool(given.get("retry_now")),
                   only=given.get("only") or (),
                   prefer_format=pick("prefer_format", cfg.prefer_format),
                   format_fallback=pick("format_fallback", cfg.format_fallback),
                   extract_embedded=pick("extract_embedded", cfg.extract_embedded))

    def __repr__(self):
        return "<Settings %d folder(s), lang=%s%s%s>" % (
            len(self.folders), self.lang, ", --out" if self.out else "",
            ", --dry-run" if self.dry_run else "")


# ---------------------------------------------------------------------------
# what a run produced
# ---------------------------------------------------------------------------

class Attempted(object):
    u"""One candidate, tried. `tsubasa` is tsubasa's `Result` or None (the
    download never got that far).

    ⭐ `path` and `digest` (RUNBOOK 8b): where the downloaded file sits in the
    working cache, and its content hash. The digest is what the state DB keeps
    so the SAME file can be offered to a person after this run is forgotten;
    the path is what a pick hands to `hato sync`. Both None when nothing was
    downloaded.
    """

    __slots__ = ("name", "outcome", "reason", "tsubasa", "bytes", "path", "digest")

    def __init__(self, name, outcome, reason, result=None, size=0, path=None, digest=None):
        self.name = name
        self.outcome = outcome
        self.reason = reason
        self.tsubasa = result
        self.bytes = size
        self.path = path
        self.digest = digest

    @property
    def match_rate(self):
        return getattr(self.tsubasa, "match_rate", None)

    def __repr__(self):
        return "<Attempted %r %s>" % (self.name[:48], self.outcome)


class Remembered(object):
    u"""⭐ RUNBOOK 8d. A candidate tried in an EARLIER run, read back from the state
    DB -- so a person can still be offered it after that run is forgotten.

    ⛔ Deliberately not an `Attempted`: `attempts` means *tried in this run*, and
    the counts, the report and the byte total all read it that way. `path` is the
    downloaded file as it sits now (`keep.remembered_file`), or None when it is
    gone; `when` is when it was tried.
    """

    __slots__ = ("name", "outcome", "reason", "bytes", "match_rate", "path", "when")

    def __init__(self, name, outcome, reason, size, match_rate, path, when):
        self.name = name
        self.outcome = outcome
        self.reason = reason
        self.bytes = size
        self.match_rate = match_rate
        self.path = path
        self.when = when

    def __repr__(self):
        return "<Remembered %r %s>" % (self.name[:48], self.outcome)


class VideoResult(object):
    u"""One video's single outcome. ⛔ Every video gets exactly one; there is no
    fifth, and no silent success (`03-permissions.md`).

    The fields `05-interface.md` §*`Result` carries* names, plus `skip` (which
    of the five skips) and `attempts` (what was tried, for the hand-back path).
    ⭐ `tsubasa` is tsubasa's own `Result`, passed through unchanged -- so 5a can
    tell a dry run from a write that did not land, which is `write_failed`.
    """

    __slots__ = ("video", "name", "title", "season", "episode", "outcome", "skip",
                 "reason", "jimaku_entry", "jimaku_filename", "attempts",
                 "candidates_offered", "tsubasa", "output_path", "kept_path",
                 "api_calls", "bytes_downloaded", "retry_after", "tried_before",
                 "newest_offered", "taken_from", "not_taken")

    def __init__(self, video, outcome, reason=u"", **fields):
        self.video = str(getattr(video, "path", video))
        self.name = getattr(video, "name", os.path.basename(self.video))
        self.title = getattr(video, "title", u"")
        self.season = getattr(video, "season", None)
        self.episode = getattr(video, "episode", None)
        self.outcome = outcome
        self.skip = None
        self.reason = reason
        self.jimaku_entry = None
        self.jimaku_filename = None
        self.attempts = ()
        self.candidates_offered = 0
        self.tsubasa = None
        self.output_path = None
        self.kept_path = None
        self.api_calls = 0
        self.bytes_downloaded = 0
        self.retry_after = None
        #: ⭐ RUNBOOK 8d -- `Remembered` candidates from earlier runs, never this
        #: one's. What keeps a pick on offer after the run that made it is gone.
        self.tried_before = ()
        #: ⭐ RUNBOOK 8f -- the newest episode the entry's releases offer, in this
        #: video's numbering (`episodes.newest_offered`), or None.
        self.newest_offered = None
        #: ⭐ RUNBOOK 14c -- the track this subtitle was TAKEN OUT of the video
        #: from: `{track, codec, format, name, events}`. None for a download.
        self.taken_from = None
        #: ⭐ 14c -- why the Japanese subtitles inside could not be taken out,
        #: when the setting asked and the video was downloaded for instead.
        self.not_taken = None
        for key, value in fields.items():
            setattr(self, key, value)
        if outcome != CONFIDENT and not (self.reason or u"").strip():
            # `03-permissions.md` §the hand-back path: *"it failed" is not
            # actionable and is not acceptable output.* Caught here rather than
            # printed as a blank line by 5a.
            raise ValueError("a %s result for %s needs a reason" % (outcome, self.name))

    @property
    def wrote(self):
        return self.outcome == CONFIDENT and bool(self.output_path)

    def __repr__(self):
        return "<%s %s%s>" % (self.outcome, self.name,
                              u" (%s)" % self.skip if self.skip else u"")


class ShowReport(object):
    u"""One show, as the run saw it -- the block 5a prints above its videos."""

    __slots__ = ("title", "season", "year", "videos", "resolved", "reason", "api_calls",
                 "files_listed", "results", "notes", "alternates")

    def __init__(self, title, season, videos, year=None):
        self.title = title
        self.season = season
        #: ⭐ `tokens.year` of the videos' names, or None. Part of the resolution
        #: cache key: tsubasa drops a bracketed year, so without it
        #: `Hunter x Hunter (1999)` and `(2011)` are one show for ever (06 §1).
        self.year = year
        self.videos = videos
        self.resolved = None        # resolution.Resolved, or None
        self.reason = u""           # what identification said, always
        self.api_calls = 0
        self.files_listed = 0
        self.results = []
        self.notes = []
        #: ⭐ The other entries the search scored, kept so a LOW CONFIDENCE pick that
        #: holds nothing can be escalated past (`_escalate`). Measured live
        #: 2026-09-17: Re:Zero episodes 52-55 resolved to the SEASON 1 entry, which
        #: has nothing in that range, and the run stopped there with the alternates
        #: already in hand and unused.
        self.alternates = []

    @property
    def entry(self):
        return self.resolved.entry_id if self.resolved else None

    def __repr__(self):
        return "<ShowReport %r s=%r y=%r %d video(s)>" % (self.title, self.season, self.year,
                                                          len(self.videos))


class RunReport(object):
    u"""Everything one run decided. ⛔ Prints nothing; 5a renders it."""

    __slots__ = ("settings", "shows", "results", "api_calls", "bytes_downloaded",
                 "seconds", "notes", "stopped")

    def __init__(self, settings):
        self.settings = settings
        self.shows = []
        self.results = []
        self.api_calls = 0
        self.bytes_downloaded = 0
        self.seconds = 0.0
        self.notes = []
        #: 🚨 The sentence that ended the run early (a 401, an unreachable
        #: server), or None. Videos after it were never looked at.
        self.stopped = None

    def counts(self):
        u"""outcome -> how many. ⚠ Skips are counted by their KIND, because
        *already present* and *no subtitle track* are different lines in the
        ruled output and a single `SKIPPED` total would hide both."""
        out = OrderedDict()
        for r in self.results:
            key = r.skip if r.outcome == SKIPPED else r.outcome
            out[key] = out.get(key, 0) + 1
        return out

    def __repr__(self):
        return "<RunReport %d video(s), %d API call(s)%s>" % (
            len(self.results), self.api_calls, ", STOPPED" if self.stopped else "")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def run(settings, *, client, db, resolutions, kitsu=None, cache=None,
        downloader=None, engine=None, reader=None, clock=None, on_progress=None,
        extractor=None):
    u"""Walk the folders and do the read rule for every video. -> `RunReport`

    `client` · `db` · `resolutions`
        a `JimakuClient`, a `StateDB` and a `ResolutionCache`. ⛔ Handed in, never
        built here: the CLI owns their lifetimes and the suite owns their roots.
    `downloader`
        ⛔ A SEAM. `(file dict) -> bytes`, defaulting to `client.download`.
        ⚠ It exists because Whitelist 2 forbids recording a subtitle BODY -- the
        download fixtures are metadata only (`07-test-plan.md`), so a suite that
        must reach the sync step has no recorded bytes to serve and supplies its
        own. The metered half is still the real client against real captures.
    `engine` · `reader`
        the seams `port.sync` and `present.read_tracks` already carry, passed
        through so a suite can decide a verdict or a track list without opening
        a container. Both default to the real tsubasa.
    `extractor`
        ⭐ RUNBOOK 14c -- `tsubasa.extract_subtitle` by default: the same kind of
        seam, so a suite can say what a track comes out as without a container.
    `on_progress`
        ⭐ RUNBOOK 7b. `(dict) -> None`, called AS THE WORK HAPPENS. ⛔ `None` by
        default, and then no branch below it runs at all.

        🚨 A PART 1 DEFECT THIS EXISTS TO CLOSE. `05-interface.md` §The window
        rules *"show the process as it does it automatically"* -- and every
        object `--json` emits is built from a FINISHED `RunReport`, so a shell
        over the CLI could paint a spinner and nothing else. The requirement had
        been marked verified against a command that emits the right objects at
        the wrong time.

        ⛔ NOTHING HERE MAY DECIDE ANYTHING. A progress call is a report; a
        callback that raises must not change what the run does, which is why
        every call is wrapped.
    """
    return _Run(settings, client, db, resolutions, kitsu, cache, downloader,
                engine, reader, clock, on_progress, extractor).go()


class _Run(object):

    def __init__(self, settings, client, db, resolutions, kitsu, cache,
                 downloader, engine, reader, clock, on_progress=None,
                 extractor=None):
        self._progress = on_progress
        self._done = 0
        self.s = settings
        self.client = client
        self.db = db
        self.resolutions = resolutions
        self.kitsu = kitsu
        self.cache = cache if cache is not None else Cache()
        self.download = downloader if downloader is not None else client.download
        self.engine = engine
        self.reader = reader
        #: ⭐ RUNBOOK 14c -- `tsubasa.extract_subtitle`, or a suite's own. ⚠ None on
        #: a tsubasa from before 0.1.9: the choice then downloads, and says why.
        self.extractor = (extractor if extractor is not None
                          else getattr(tsubasa, u"extract_subtitle", None))
        self.clock = clock if clock is not None else time.time
        self.report = RunReport(settings)
        try:
            self.look = present.Presence(settings.lang)
        except present.LanguageUnknown as exc:
            # ⚠ `hato/config.py` accepts any string for `lang`; tsubasa decides
            # what resolves. A tag it cannot read came out of HERE, four frames
            # from a caller that had already been told every startup refusal is
            # a ConfigProblem -- so the CLI's one handler missed it and a typo in
            # config.toml was a traceback. ⛔ The conversion cannot live in
            # `go()`: nothing runs before the language is resolved.
            raise ConfigProblem(str(exc))
        self.lang = self.look.lang
        self._files = {}            # entry id -> [file dict], one listing per run
        self._relisted = set()      # entry ids whose stale listing was refreshed
        self._hashes = {}           # path -> video hash, so 128 KiB is read ONCE
        self._clashes = {}          # video key -> why two videos target one file
        #: video hash -> what it tried in EARLIER runs, read once (`_candidates`)
        self._earlier = {}
        #: ⭐ 14c -- video key -> why its Japanese subtitles could not be taken
        #: out, for the row of the download that happened instead
        self._not_taken = {}
        #: ⭐ 14z (A-1) -- folder key -> why it cannot take a file, or None: asked once
        self._unwritable = {}

    # -- the whole run ------------------------------------------------------

    def progress(self, phase, **fields):
        u"""Report what is happening NOW. -> None  (RUNBOOK 7b)

        ⛔ A REPORT, NEVER A DECISION. Nothing the callback does may change what
        the run does -- so it is wrapped, and a callback that raises costs the
        progress line and nothing else. A window whose pipe has closed must not
        be able to stop a run that is part-way through writing files.

        ⛔ NO SECRET AND NO SUBTITLE BODY EVER GOES THROUGH HERE. Only names
        that already appear in the final NDJSON.
        """
        if self._progress is None:
            return
        try:
            fields["phase"] = phase
            self._progress(fields)
        except Exception:
            self._progress = None      # ⚠ once, not once per video

    def go(self):
        started = self.clock()
        before = self.client.metered
        # ⛔ BEFORE ANYTHING IS SCANNED, AND BOTH DOORS. A subs_dir inside a
        # scanned folder makes the kept originals candidates for the videos
        # beside them; an `--out` inside one puts hato's OWN finished files in
        # the tree, under the videos' own basenames, where a later
        # `tsubasa <folder>` supersedes them into the trash (measured -- see
        # `hato/keep.py`). Only the first was checked, for months.
        if not self.s.subs_dir:
            # ⚠ `Settings.from_config` always fills this in; `Settings(folders=…)`
            # built by hand does not, and `check_subs_dir(None, …)` then raised a
            # bare TypeError out of `os.fspath` -- a library caller's reasonable
            # mistake reported as an interpreter fault.
            raise ConfigProblem(
                u"no subs_dir: hato keeps the original of every file it has "
                u"tsubasa write, and there is nowhere to put them. Pass "
                u"subs_dir=, or build the settings with "
                u"`Settings.from_config(config.load(), folders=[...])`, which "
                u"fills in the per-user default.")
        try:
            keep.check_subs_dir(self.s.subs_dir, self.s.folders)
            keep.check_out_dir(self.s.out, self.s.folders)
        except keep.InsideScan as exc:
            # ⚠ One exception for 5a to catch, with the message kept whole. The
            # BASE class, so a third folder gaining the rule is caught here too.
            raise ConfigProblem(str(exc))
        self.progress(u"start", folders=len(self.s.folders))
        try:
            shows = self._discover()
            self.progress(u"found", shows=len(shows),
                          videos=sum(len(s.videos) for s in shows))
            for show in shows:
                self._show(show)
        except _Stop as stop:
            self.report.stopped = str(stop)
        self.report.api_calls = self.client.metered - before
        self.report.bytes_downloaded = sum(r.bytes_downloaded for r in self.report.results)
        self.report.seconds = self.clock() - started
        self.report.notes.extend(self.db.notes)
        self.report.notes.extend(getattr(self.resolutions, "notes", ()) or ())
        return self.report

    # -- discovery ----------------------------------------------------------

    def _discover(self):
        u"""-> [ShowReport], each carrying `(video, root)` pairs.

        ⭐ Grouped by the title and season TSUBASA read, never by folder: *"a
        season folder holds two different shows -- group videos by parsed title
        and resolve each independently"* (06 §1). ⚠ And a video found under two
        given folders is one video, decided once.

        🚨 AND BY THE YEAR, which nothing used to read. 06 §1 rules it:
        *"Two shows normalize to the same cache key -> include the parsed
        season/year in the key. A collision would serve the wrong entry from
        cache forever."* tsubasa DROPS a bracketed year -- measured, both
        `Hunter x Hunter (1999)` and `Hunter x Hunter (2011)` read the title
        `Hunter x Hunter` with no season -- so without it the two are ONE show,
        identified once, cached under one key for ever, and `_forget` drops
        both at once. `hato/tokens.py`'s `year()` was written for exactly this
        (4,872 bracketed-year names measured) and had no caller.

        ⚠ THE YEAR IS ONLY ALLOWED TO SPLIT A SHOW WHEN IT TELLS TWO APART.
        A folder where some names carry a year and some do not is ONE release,
        not two shows; splitting on that would double the metered calls and
        align each half against half a folder. So a (title, season) group takes
        the single year its names agree on, and is split only when its names
        carry SEVERAL different ones -- which is the collision itself.
        """
        seen, shows, usable, skipped = set(), OrderedDict(), 0, 0
        for root in self.s.folders:
            try:
                found = tsubasa.scan(videos=root, recurse=self.s.recurse).videos
            except Exception as exc:
                # ⚠ One unusable folder must not end a run over five others --
                # but a run where NONE was usable is a ConfigProblem below.
                self.report.notes.append(
                    u"%s could not be scanned (%s: %s), so it was left out."
                    % (root, type(exc).__name__, exc))
                continue
            usable += 1
            for video in found:
                # ⭐ RUNBOOK 7e -- the skipped folders, applied to what was
                # FOUND. ⛔ Before `seen`, so a video reachable from two roots
                # cannot be admitted by whichever root was walked first.
                if _under_any(video.path, self.s.skip_folders):
                    skipped += 1
                    continue
                key = _key(video.path)
                if key in seen:
                    continue
                seen.add(key)
                show_key = ((video.title or u"").casefold(), video.season)
                shows.setdefault(show_key, []).append(
                    (video, root, tokens.year(video.name)))
        if skipped:
            # ⛔ A SKIPPED VIDEO IS SAID OUT LOUD. Dropped silently it is
            # indistinguishable from a video that was never there, so a skip
            # rule that is too broad -- the whole risk of this setting -- would
            # be invisible for exactly as long as nobody went looking.
            self.report.notes.append(
                u"%d video(s) were not looked at because they are inside a "
                u"skipped folder (%s)."
                % (skipped, u", ".join(self.s.skip_folders)))
        if not usable:
            raise ConfigProblem(
                u"none of the %d folder(s) given could be scanned: %s"
                % (len(self.s.folders), u"; ".join(self.report.notes) or u"no reason given"))
        for show in self._by_year(shows):
            self.report.shows.append(show)
        found = list(self.report.shows)
        self._clashes = self._find_clashes(found)
        return found

    def _by_year(self, grouped):
        u"""{(title, season): [(video, root, year)]} -> [ShowReport].

        ⭐ The year splits a group ONLY when its names carry several -- see
        `_discover`. A group whose names all agree (or say nothing) stays one
        show and carries that year into its cache key, so the same folder
        scanned again, and the `(1999)` folder beside the `(2011)` one, key
        apart. ⚠ Videos with no year join the show of the only year seen; they
        are the same release, minus a token.
        """
        out = []
        for (_folded, season), items in grouped.items():
            years = sorted(set(y for _v, _r, y in items if y is not None))
            for year in (years if len(years) > 1 else [years[0] if years else None]):
                mine = [(v, r) for v, r, y in items
                        if len(years) <= 1 or y == year]
                if not mine:
                    continue
                show = ShowReport(mine[0][0].title or u"", season, [], year=year)
                show.videos.extend(mine)
                out.append(show)
            if len(years) > 1:
                nameless = [(v, r) for v, r, y in items if y is None]
                if nameless:
                    show = ShowReport(nameless[0][0].title or u"", season, [], year=None)
                    show.videos.extend(nameless)
                    show.notes.append(
                        u"These videos carry no year while their siblings carry %s, so "
                        u"they are identified on their own -- a bracketed year is dropped "
                        u"by the parser and two shows under one key would serve the wrong "
                        u"entry from cache for ever (06-edge-cases.md §1)."
                        % u" and ".join(u"%d" % y for y in years))
                    out.append(show)
        return out

    def _find_clashes(self, shows):
        u"""⭐ TWO VIDEOS MAY NEVER TARGET ONE FILE. -> {video key: the sentence}

        🚨 MEASURED 2026-09-17, three reachable shapes, all of which end the same
        way: run 1 writes for A and tsubasa refuses B's write over it; ⛔ **run 2
        reports BOTH as "subtitle already present", and B's "subtitle" is A's
        file** -- a different release's timing, silently, for ever. `_gate` decides
        every video before anything is written, so `look.forget()` cannot save B.

            two roots on one command line with `--out`   `mirrored_dir` returns
                `out` itself for a video in the root, so both roots flatten onto it
            two roots sharing a relative subpath         `A/S2/` and `B/S2/` both
                mirror to `out/S2/`
            no `--out` at all                            `Show - 01.mkv` and
                `Show - 01.mp4` in one folder

        ⚠ THE KEY IS (TARGET FOLDER, VIDEO STEM) AND NOT THE FINISHED FILENAME,
        which is not known until a candidate has been downloaded -- and it would be
        the wrong question anyway: `hato/present.py` matches a sidecar on its STEM,
        so `Show - 01.ja.ass` answers *present* for `Show - 01.mp4` however the
        extensions fall. Two videos on one stem in one folder cannot be told apart
        by the check that decides whether to fetch, so neither may be fetched for.

        ⛔ Refused, not resolved. hato cannot know which video the person meant,
        and picking one silently condemns the other to a wrong subtitle it will
        never be told about.
        """
        by_target, clashes = OrderedDict(), {}
        for show in shows:
            for video, root in show.videos:
                path = str(video.path)
                try:
                    folder = keep.target_dir(path, root, self.s.out)
                except ValueError:
                    continue                # ⚠ `_gate` reports this one as an ERROR
                key = (os.path.normcase(os.path.abspath(os.fspath(folder))),
                       os.path.normcase(os.path.splitext(os.path.basename(path))[0]))
                by_target.setdefault(key, []).append((str(folder), path))
        for pairs in by_target.values():
            if len(pairs) < 2:
                continue
            for folder, path in pairs:
                others = [p for _f, p in pairs if p != path]
                target = os.path.join(
                    folder, u"%s.%s.<ext>"
                    % (os.path.splitext(os.path.basename(path))[0], self.lang))
                clashes[_key(path)] = (
                    u"this video and %s would be given the SAME subtitle file (%s), "
                    u"so neither is fetched. They are different files and their "
                    u"timing is not the same, but only one file can be written -- and "
                    u"from the next run on, the one left out would be told the other's "
                    u"subtitle is its own. Scan them separately, give one its own "
                    u"--out, or rename one; `hato sync <video> <subtitle>` pairs "
                    u"either by hand."
                    % (u" and ".join(os.path.basename(p) for p in others), target))
        return clashes

    # -- one show -----------------------------------------------------------

    def _show(self, show):
        needing = []
        # ⭐ RUNBOOK 8e -- `only`: the run was asked about particular videos (the
        # window's *Look again now*). ⚠ Applied HERE, after discovery and not in
        # it: the show keeps every sibling in `show.videos`, because `_align` fits
        # a release's numbering against the whole folder's range -- filtered at
        # discovery, one video alone has no range at all ("the known soft spot").
        wanted = set(_key(v) for v in self.s.only) if self.s.only else None
        for video, root in show.videos:
            if wanted is not None and _key(video.path) not in wanted:
                continue
            decided = self._gate(video, root)
            if decided is None:
                needing.append((video, root))
            else:
                # ⭐ ANNOUNCED EVEN THOUGH THE WORK WAS INSTANT. A settled
                # library is decided ENTIRELY here, and without this the window
                # would go quiet from "found" to the end of the run -- on the
                # very run that is most common.
                self._done += 1
                self.progress(u"video", name=os.path.basename(str(video.path)),
                              video=str(video.path), title=show.title,
                              done=self._done)
                self._keep_result(show, decided)
        if not needing:
            return                          # ⭐ zero metered calls for this show
        self.progress(u"show", title=show.title, season=show.season,
                      videos=len(needing))

        before = self.client.metered
        try:
            if not self._identify(show, needing):
                return
            if show.resolved is None:
                for video, _root in needing:
                    self._keep_result(show, self._not_found(
                        video, u"no jimaku entry matched this show -- %s" % show.reason,
                        entry=None, hard=True))
                return
            files = self._entry_files(show.resolved.entry_id)
        except _client.EntryNotFound as exc:
            self._forget(show, u"jimaku no longer has that entry, so its cached resolution "
                               u"was dropped -- the next run identifies this show again.")
            for video, _root in needing:
                self._keep_result(show, self._not_found(
                    video, u"%s -- the cached resolution was dropped, so the next run "
                           u"looks this show up again" % exc, entry=None, hard=True))
            return
        except _SHOW_FAILURES as exc:
            for video, _root in needing:
                self._keep_result(show, VideoResult(
                    video, ERROR, u"the entry's file list could not be read: %s" % exc,
                    jimaku_entry=show.resolved.entry_id))
            return
        finally:
            show.api_calls += self.client.metered - before
        show.files_listed = len(files)

        alignment = self._align(show, files, [v for v, _r in show.videos])
        alignment, files = self._escalate(show, needing, alignment, files)
        alignment, files = self._archives_pass(show, needing, alignment, files)
        self._archive_note(show, files)
        seen_groups, refused, confident, offered = set(), 0, 0, 0
        results = []
        for video, root in needing:
            self._done += 1
            self.progress(u"video", name=os.path.basename(str(video.path)),
                          video=str(video.path), title=show.title,
                          done=self._done)
            result = self._candidates(show, alignment, video, root, seen_groups)
            results.append((video, root, result))
            if result.attempts and result.outcome == REFUSED:
                refused += 1
            if result.outcome == CONFIDENT:
                confident += 1
            # ⚠ ANY FILE, IN ANY FORMAT -- deliberately not `_takes` (9a). This
            # count decides whether a LOW CONFIDENCE entry is evidence against
            # itself, and an entry holding your episodes in the other format is
            # evidence FOR itself: dropping it would re-identify, for a metered
            # call a day, a show whose entry is right (ADVERSARY 2026-09-23 #2).
            if str(video.path) in alignment.per_video:
                offered += 1
        # ⭐ THE SECOND ESCALATION, measured on a real library 2026-09-17. The first
        # one fires when an entry offers NOTHING; this one fires when it offers only
        # WRONG things. `Re Zero … - 52/54/55` (seasonless, absolute) resolved to the
        # season 1 entry, which happily offered five candidates per video -- all from
        # the wrong season, all refused by timing. Nothing bad was written and nothing
        # good was either, and the run stopped with the right entry one call away.
        if refused and not confident:
            retried = self._retry_on_another_entry(show, results, seen_groups)
            if retried is not None:
                results, refused, confident = retried, 0, 1
        for _video, _root, result in results:
            self._keep_result(show, result)
        if not offered and show.resolved.low_confidence and not show.resolved.movie:
            # 🚨 THE EPISODE NUMBER IS EVIDENCE ABOUT THE ENTRY, and it was in
            # hand and unused. Measured 2026-09-17: an absolute-numbered
            # season-2 video (`… Frieren - 29 …`, season=None episode=29) can tie
            # the season-1 entry with the season-2 one -- LOW CONFIDENCE, so the
            # pick is a hypothesis -- and the season-1 entry has no episode 29.
            # ⭐ AN ENTRY THAT CAN HOLD NONE OF YOUR EPISODES IS EVIDENCE AGAINST
            # ITSELF. Without this the show attempts nothing, so the rule below
            # (`refused and not confident`) never fires and the wrong entry stays
            # cached FOR EVER -- the one store the spec says is kept for ever.
            #
            # ⚠ LOW CONFIDENCE ONLY. A confident identification that holds
            # nothing is 06 §2's ordinary *"entry has 1-8, folder has 9-12"* --
            # NOT_FOUND with a retry date, not an error, and re-identifying it
            # would buy the same answer with a metered call. And the negative
            # cache those NOT_FOUND rows just wrote is what stops the next run
            # paying for this one, so dropping the resolution costs nothing
            # until the row expires.
            self._forget(show, u"this show's entry held nothing for any of its videos and "
                               u"the identification was LOW CONFIDENCE, so its cached "
                               u"resolution was dropped -- an entry that can hold none of "
                               u"your episodes is evidence against itself, and the next run "
                               u"identifies the show again.")
        elif refused and not confident:
            # ⭐ RUNBOOK 2b's ruling: a show whose every attempted video ended
            # REFUSED was probably identified WRONG, and a resolution cached
            # "for ever" would never get another chance. Dropping it costs one
            # metered call on the next run; keeping it costs correctness.
            #
            # ⚠ REFUSED, NOT MERELY "SOMETHING WAS TRIED". This counted every
            # video with an attempt, so a blocked WRITE -- 100% match, the
            # identification obviously right -- dropped the show's resolution AND
            # printed *"every video tried on this show was refused by timing"*
            # over a video that was not refused and not about timing. An ERROR is
            # evidence about the disk or the download, never about which entry
            # this show is. Found by RENDERING the report, not by an assertion.
            self._forget(show, u"Every video tried on this show was refused by timing, so its "
                               u"cached resolution was dropped -- the next run identifies it "
                               u"again.")

    def _keep_result(self, show, result):
        # ⭐ RUNBOOK 14c -- a video the setting asked to TAKE OUT, downloaded for
        # instead: whichever row it ends in says why, so it is the funnel's job.
        if result.not_taken is None:
            result.not_taken = self._not_taken.get(_key(result.video))
        show.results.append(result)
        self.report.results.append(result)
        # ⭐ THE ONE FUNNEL (RUNBOOK 7b). Every outcome -- decided at the gate,
        # not found, errored, or ruled by timing -- passes through here, so
        # reporting it here is the only version that cannot miss a path.
        # ⚠ It was in the candidate loop instead, which is ONE of seven callers:
        # a run where every video was decided at the gate emitted no per-video
        # progress at all. Found by LOOKING at a real run; every check was green
        # (2026-09-18), because the fixture behind them only covers videos that
        # need fetching.
        self.progress(u"result", result=result)
        # ⭐ THE surasura DROP (RUNBOOK 7h), from the ONE funnel every outcome
        # passes through -- there are two separate success paths (a fresh
        # download and a re-sync from a kept original) and copying in either
        # one alone is the seam defect this project keeps paying for.
        # ⛔ `result.skip` EXCLUDES a subtitle that was already there. A PRESENT
        # row carries an `output_path` too, and copying those would ship the
        # whole library on every run instead of *"each successful run's
        # subtitles"*.
        if self.s.surasura_dir and result.wrote and not result.skip:
            try:
                keep.surasura_copy(result.output_path, self.s.surasura_dir)
            except OSError as exc:
                # ⛔ NOT a failed video. The subtitle beside the video is
                # written and correct; a full disk or a missing drive on the
                # INTEGRATION's folder must not turn a success into an error.
                self.report.notes.append(
                    u"the surasura copy of %s could not be written: %s"
                    % (os.path.basename(result.output_path or u""), exc))

    def _forget(self, show, why):
        u"""Drop this show's cached resolution. `why` is the sentence for the report.

        ⚠ THE KEY MUST BE THE ONE `_identify` STORED UNDER -- title, season AND
        year. It was built without the year, so on a show whose name carries one
        this dropped nothing at all, silently.
        """
        try:
            dropped = self.resolutions.forget(cache_key(show.title, show.season, show.year))
        except (_client.EmptyQuery, ValueError, TypeError):
            # ⚠ A title that cannot make a key was never cached under one, so
            # there is nothing to drop. ⛔ Never a reason for a run to fail:
            # this only ever makes the NEXT run pay a metered call.
            return
        if dropped:
            show.notes.append(why)

    # -- the free half of the read rule, per video --------------------------

    def _gate(self, video, root):
        u"""Everything decidable without spending quota. -> VideoResult or None.

        🚨 THE ORDER IS THE DESIGN and it is not an accident of writing: the
        cheapest check first, so a folder whose subtitles are all present never
        opens a container and never reads the DB.
        """
        path = str(video.path)
        clash = self._clashes.get(_key(path))
        if clash is not None:
            # ⛔ BEFORE THE PRESENT-CHECK, and that placement is the whole fix.
            # Once one of two videos sharing a target has been written for, the
            # present-check answers *already present* for BOTH -- so asking it
            # first would report the defect as a success on every later run.
            # A dict lookup; cheaper than the directory listing below.
            # ⛔ No row: like the two-episode refusal there is no candidate to
            # name, and this is not a verdict on any subtitle.
            return VideoResult(video, REFUSED, clash)
        try:
            folder = keep.target_dir(path, root, self.s.out)
        except ValueError as exc:
            return VideoResult(video, ERROR, str(exc))

        found = self.look.find(path, folder)
        if found is not None:
            # ⛔ NOT overridden by --force: the filesystem is canonical for
            # "does a subtitle exist", and --force overrules the DB, not the disk.
            # ⚠ AND NOTHING IS HASHED HERE, so nothing is backfilled either --
            # RUNBOOK 1b's ruling: the present-skip path never hashes just to
            # write a row that changes no decision. That is what makes a quiet
            # re-run cost "N stats and one DB read" and not N x 128 KiB.
            # ⭐ 9b -- WHICH OF THE TWO ANSWERED is said, because only one of them
            # is a guess about a file the person made: its name gives no language
            # and its text was read.
            said = (u"subtitle already present (%s -- its name gives no language; "
                    u"its text is Japanese)" % found.name if found.by_text
                    else u"subtitle already present (%s)" % found.name)
            return VideoResult(video, SKIPPED, said, skip=PRESENT,
                               output_path=str(found.path))

        try:
            video_hash = self._hash(path)
        except OSError as exc:
            return VideoResult(video, ERROR, u"the video could not be read: %s" % exc)
        if not self.s.dry_run:
            # ⭐ RUNBOOK 8e -- a video moved while it waited keeps a path the disk
            # no longer has, and `hato problems` (filtered by the disk) dropped
            # it: 4a's failure in a new shape. One UPDATE, and only when the
            # recorded path is wrong. ⛔ Never on a dry run, which writes nothing.
            self.db.note_path(video_hash, path)

        # ⛔ THE BLACKLIST IS THE PERSON'S INSTRUCTION, and `--force` does not
        # override it. `03-permissions.md` §*The read rule* puts it SECOND, right
        # after the present-check, and it is second here.
        #
        # ⚠ IT USED TO SIT BELOW THE EPISODE-SPAN REFUSAL, which cost nothing and
        # so looked like the cheaper thing to ask first. Measured: a video whose
        # NAME holds two episodes came back as HATO's refusal even when the person
        # had blacklisted it, so `hato blacklist --list` and the run disagreed
        # about the same video. The person's instruction is not a cost question.
        # The price of getting it right is one 128 KiB hash for a double-episode
        # file, which every other video in the folder pays anyway.
        row = self.db.blacklisted(video_hash)
        if row is not None:
            return VideoResult(video, SKIPPED,
                               u"blacklisted by you%s -- `hato blacklist --remove` puts it back"
                               % (u" (%s)" % row.note if row.note else u""),
                               skip=BLACKLISTED)

        span = tokens.episode_span(video.name)
        tracks = present.read_tracks(path, self.lang, reader=self.reader)
        # ⚠ 14z (A-3) -- A TWO-EPISODE NAME STILL DECIDES AN UNREADABLE FILE: refused
        # on its name, as it always was, below -- never an ERROR about its container.
        if tracks.kind == present.UNREADABLE and not span:
            # ⭐ ERROR, BEFORE ANY DOWNLOAD. tsubasa's `sync()` reads the same
            # container, so a download would only reach the same ERROR
            # afterwards -- and the network is metered. Its reason names the fix.
            return VideoResult(video, ERROR,
                               u"the video's subtitle tracks could not be read, so nothing "
                               u"was downloaded: %s" % tracks.reason)
        choice = formats.embedded_choice(self.s.skip_embedded, self.s.extract_embedded)
        if tracks.kind == present.EMBEDDED and choice == formats.EMBEDDED_SAVE:
            # ⭐ RUNBOOK 14c -- taken out and saved beside the video. One it cannot
            # be taken out of falls through and is downloaded for, as below.
            taken = self._take_out(video, path, folder, tracks)
            if taken is not None:
                return taken
        elif choice == formats.EMBEDDED_SAVE:
            # ⭐ 14z (C1, A-4) -- A JAPANESE TRACK THAT IS NOT A WHOLE TEXT ONE -- signs
            # only, or pictures of text -- is no subtitles to take out: downloaded for,
            # and its row says why (ruled). It never reached `_take_out` to say so.
            why = _not_whole(tracks.tracks, self.lang)
            if why:
                self._not_taken[_key(path)] = why
        if tracks.kind == present.EMBEDDED and choice == formats.EMBEDDED_LEAVE:
            # ⭐ The toggle (Sonic, 2026-09-17). ON (the default) this is a free
            # skip: the subtitle is already there and already in sync. OFF, we fall
            # through and fetch -- and ⚠ the embedded track is then the REFERENCE
            # `sync()` times the download against, which is the strongest reference
            # there is: same rip, same cuts, same frame rate.
            return VideoResult(video, SKIPPED, tracks.reason, skip=EMBEDDED)
        if span:
            # ⛔ RULED (06 §2): two subtitle files cannot cleanly become one, and
            # a wrong guess writes a half-wrong file.
            #
            # ⚠ A DEFECT THIS BUILD MEASURED, and the reason the refusal is HERE
            # rather than left to `episodes.align` (which has its own): tsubasa
            # reads `frieren S2 - 01-02.mkv` as title **"frieren 02"**, so the
            # video lands in a SHOW OF ITS OWN, is identified on its own -- one
            # metered call, and on a wrong title -- and align's refusal is never
            # reached. It came back ERROR, which `03-permissions.md` says must
            # never be conflated with a refusal. Decided on the name, before any
            # of that. Recorded in spec/06-edge-cases.md §2.
            # ⭐ 14z (A-3) -- AND BELOW THE VIDEO'S OWN SUBTITLES, never above them.
            # Taking a video's own track out splits nothing, yet a two-episode file
            # whose track was to be SAVED was refused every run -- and under *Leave
            # them there* it read as refused, not embedded. Still before any request.
            return VideoResult(
                video, REFUSED,
                u"the video holds episodes %s -- one subtitle cannot be split between "
                u"them, so it is refused rather than guessed. Split the file, or pair a "
                u"subtitle by hand with `hato sync`."
                % u"-".join(str(n) for n in (span[0], span[-1])))
        if tracks.kind in (present.NO_TRACK, present.NO_USABLE):
            # ⛔ NEVER A REFUSAL. A refusal row is keyed on a candidate and would
            # blacklist a good subtitle for ever -- including after tsubasa can
            # sync from audio. Nothing is recorded at all.
            return VideoResult(video, SKIPPED, tracks.reason, skip=NO_TRACK)

        # ⚠ HARD *OR* SOFT, unexpired. Checking only the hard one re-lists the
        # entry's files every run for an episode jimaku does not have yet -- the
        # cost the negative cache exists to stop. ⭐ `skip_reason` asks the
        # blacklist FIRST and does not look at `force` until after it, so the
        # ordering above stays true even if this were the only call.
        # ⭐ `retry_now` (RUNBOOK 8e, D3) looks past the WAIT and nothing else --
        # `skip_reason` still asks the blacklist first, and `_candidates` still drops
        # every file already refused, because only `force` reaches that filter.
        # 🚨 The window's "Try 3 more candidates" ran without either, so for the 24
        # hours after a refusal -- the only time anybody presses it -- the gate
        # answered "waiting to retry" and it tried nothing at all.
        skip = self.db.skip_reason(video_hash, self.lang,
                                   force=self.s.force or self.s.retry_now)
        if skip is not None and skip.kind == "negative":
            # ⭐ 9a -- A WAIT FOR ONE KIND ENDS WHEN THE PERSON TAKES THE OTHER.
            # It was recorded because every file was the other format; turning
            # the fallback on (or changing the preference) is the person saying
            # *take it* -- and a switch that still answered "tomorrow" would read
            # as a setting that did nothing. ⛔ Only that wait: any other
            # negative stands exactly as before.
            # ⚠ ANY of the kinds it waits in -- an episode on jimaku as `.srt` and
            # `.vtt` is taken by choosing `.srt` (ADVERSARY 2026-09-23 #4).
            waited_for = formats.only_as(skip.reason)
            if waited_for and formats.accepts_any(waited_for, self.s.prefer_format,
                                                  self.s.format_fallback):
                skip = None
        if skip is not None and skip.kind == "negative":
            # 🚨 RUNBOOK 8d -- THE SECOND CAUSE OF 4a. This line decided correctly
            # and said nothing useful: a reason and a date, and none of the files
            # that were refused yesterday. So a run inside the retry window turned
            # a row a person could pick from into a quiet *"waiting to retry"*, and
            # the pick was gone -- *"never got to"* pick Tsuihou. ⭐ The skip still
            # skips; it now carries what it is waiting on. ⛔ Zero requests.
            # 🚨 AND THE SAME FACTS AS WHAT HATO REMEMBERS. This copy of the row
            # reaches the window DURING every run, and it said `candidates_offered:
            # 0` with no `newest_offered`: a late episode turned from *"probably
            # not out yet"* into a pick with another episode's file OUTLINED, and
            # *Look again* claimed every file had been tried (ADVERSARY 2026-09-22
            # A5). The newest episode on offer is the negative's own; how many the
            # entry holds is UNKNOWN -- this run never listed it.
            return VideoResult(video, SKIPPED, skip.reason, skip=NEGATIVE,
                               retry_after=skip.retry_after,
                               tried_before=self._remembered(video_hash),
                               newest_offered=skip.newest_offered,
                               candidates_offered=None)
        if skip is not None:
            # ⚠ Reached only if the check above were ever removed: `skip_reason`
            # asks the blacklist FIRST and does not look at `force` until after
            # it, so the person's instruction survives a caller getting it wrong.
            return VideoResult(video, SKIPPED, skip.reason, skip=BLACKLISTED)

        # ⭐ 14z (A-1) -- EVERYTHING BELOW WRITES beside the video: a re-sync, or the
        # download road once this returns None. So the folder is asked FIRST -- one that
        # cannot take a file hung the run for days inside the writer, and only after two
        # metered calls. ⛔ An ERROR, nothing recorded: it is the disk, not the subtitles,
        # and the next run asks again. ⚠ Not on a dry run, which writes nothing.
        cannot = None if self.s.dry_run else self._cannot_write(folder)
        if cannot:
            return VideoResult(video, ERROR, u"nothing was downloaded: %s" % cannot)
        synced = self.db.synced(video_hash, self.lang)
        if synced is not None and synced.kept_path and os.path.isfile(synced.kept_path):
            # ⭐ THE DISK WON: the DB says synced and the present-check above
            # says the file is gone. Re-syncing from the kept original costs
            # ZERO network (`02-data-model.md` §Canonicity).
            # 🚨 9a -- ONLY IN A FORMAT THE PERSON STILL TAKES. Measured: `.ass`
            # written, the person chose `.srt` and deleted it, and the next run
            # re-timed the kept `.ass` straight back -- after which the present-
            # check answered *already there* for good, and the `.srt` they asked
            # for was never fetched (ADVERSARY 2026-09-23 #3). Otherwise it falls
            # through to an ordinary fetch; the kept original stays kept.
            kept_as = tokens.subtitle_format(os.path.basename(synced.kept_path))
            if formats.accepts(kept_as, self.s.prefer_format, self.s.format_fallback):
                return self._resync(video, root, video_hash, synced)
        return None

    def _cannot_write(self, folder):
        u"""⭐ 14z (A-1) -- `paths.cannot_write`, asked once per folder in a run."""
        key = _key(folder)
        if key not in self._unwritable:
            self._unwritable[key] = paths.cannot_write(folder)
        return self._unwritable[key]

    def _take_out(self, video, path, folder, tracks):
        u"""⭐ RUNBOOK 14c -- the video's own Japanese subtitles, TAKEN OUT and saved
        beside it as a file. -> VideoResult, or None: download for it instead --
        and `_not_taken` keeps why, for its row (ruled: *"a video hato cannot take
        subtitles out of is downloaded for instead, and its row says why"*).

        ⛔ tsubasa WRITES the file (`extract_subtitle(write=True)`): hato's only
        write in a media folder is tsubasa's (`03-permissions.md`, Whitelist 1). Its
        name is tsubasa's -- `<video>.ja.<ext>` -- in the folder the present-check
        asks (`keep.target_dir`, so `--out` is honoured), and ⛔ never over a file
        that is there. ⛔ Never converted: the track's own format, and its own line
        breaks (Sonic's note, 2026-09-25). ⛔ Nothing recorded in the state DB and
        zero requests: the file beside the video is the whole record, and the next
        run's present-check finds it.
        """
        whole, why = _takeable(tracks.tracks, self.lang, self.s.prefer_format)
        if self.extractor is None:
            # ⚠ A tsubasa from before 0.1.9, on a source checkout: the floor says
            # 0.1.9, and a floor is only what pip was told.
            whole, why = (), _OLD_TSUBASA % getattr(tsubasa, u"__version__", u"?")
        if self.s.dry_run:
            # ⭐ 14z (C5) -- A PLAN READS THE HEADER, NEVER THE TRACK. Taking a track out
            # walks the whole file: 6.8 s and 216 MB for one 1.45 GB episode, cold -- a
            # season 1-3 minutes and 2.5-5 GB read just to PLAN. The header says codec,
            # flag and language in a millisecond; what only the walk finds, the run says.
            track, why_not = _by_header(path, whole)
            if track is None:
                self._not_taken[_key(path)] = why or why_not or u"tsubasa gave no reason"
                return None
            ext = _plan_extension(track.codec)
            return VideoResult(video, PLANNED,
                               u"would take the Japanese subtitles inside the video (track "
                               u"%s, .%s) out and save them beside it -- nothing downloaded"
                               % (track.index, ext),
                               taken_from={u"track": track.index, u"codec": track.codec,
                                           u"format": ext, u"events": None,
                                           u"name": getattr(track, u"name", None) or None})
        cannot = self._cannot_write(folder) if whole else None
        if cannot:
            # ⭐ 14z (A-1) -- asked before tsubasa's writer can spin on it. ⛔ No download
            # instead: it would be saved in the same folder.
            return VideoResult(video, ERROR, u"the Japanese subtitles inside it were not taken "
                                             u"out: %s" % cannot)
        got = track = None
        for track in whole:
            got = self.extractor(path, track, write=True, out_dir=str(folder))
            if got.ok:
                break
            if _unfinished(got.reason):
                # ⭐ 14z (A-2) -- A VIDEO STILL ARRIVING IS NOT ONE WITHOUT SUBTITLES.
                # tsubasa refuses a track with empty stretches -- a file still being
                # downloaded into. Downloaded for then, jimaku's file stood beside the
                # finished video for ever and its own track was never taken out. ⛔ An
                # ERROR, nothing recorded: the next run takes it out once it is whole.
                return VideoResult(video, ERROR, u"the Japanese subtitles inside it could "
                                                 u"not be taken out yet -- %s. Nothing was "
                                                 u"downloaded; the next run tries again."
                                   % got.reason.rstrip(u"."))
            why = why or got.reason                # ⭐ the track wanted most names it
        if got is None or not got.ok:
            self._not_taken[_key(path)] = why or u"tsubasa gave no reason"
            return None
        taken = {u"track": got.index, u"codec": got.codec, u"format": got.ext,
                 u"name": getattr(track, u"name", None) or None, u"events": got.cues}
        said = (u"the Japanese subtitles inside the video (track %s, .%s, %d line%s)"
                % (got.index, got.ext, got.cues, u"" if got.cues == 1 else u"s"))
        if got.write_failed or not got.output_path:
            # 🚨 AN ERROR, NEVER A REFUSAL, AND NOTHING RECORDED (`LEDGER-HOT.md`):
            # what failed is the destination, not the subtitles -- and a download
            # would be written to the same place.
            return VideoResult(video, ERROR, u"%s were taken out, but not saved: %s"
                               % (said, got.reason or u"tsubasa wrote nothing and said "
                                                      u"nothing"),
                               taken_from=taken)
        # ⚠ A file landed in that folder: the listing taken before it is a lie for
        # every later video decided against it (`_resync` says the same).
        self.look.forget(folder)
        if self.look.find(path, folder) is None:
            # ⭐ 14z (A-5) -- A FILE HATO WRITES MUST BE ONE ITS OWN PRESENT-CHECK COUNTS
            # (`LEDGER.md`). A video's name past 255 bytes had its stem TRIMMED by
            # tsubasa -- `got.notes` said so -- and the row said *"taken from the video"*
            # once, then ERROR every run after; players would not load it either.
            return VideoResult(video, ERROR, u"%s were taken out and saved as %s, but "
                                             u"players will not load it with the video%s"
                               % (said, os.path.basename(got.output_path),
                                  u": %s" % u"; ".join(got.notes) if got.notes else u""),
                               taken_from=taken)
        return VideoResult(video, CONFIDENT, u"", output_path=got.output_path,
                           taken_from=taken)

    def _resync(self, video, root, video_hash, row):
        what = (u"the synced subtitle is gone and its original is still kept (%s), so it "
                u"is re-timed from that -- no request was made" % os.path.basename(row.kept_path))
        if self.s.dry_run:
            return VideoResult(video, PLANNED, u"would re-sync: %s" % what,
                               jimaku_entry=row.jimaku_entry,
                               jimaku_filename=row.jimaku_filename)
        result = self._hand_over(video, root, row.kept_path)
        said, why = port.outcome_and_reason(result)
        attempt = Attempted(row.jimaku_filename or os.path.basename(row.kept_path),
                            said, why, result=result)
        if port.wrote(result):
            self._record(video, video_hash, row.jimaku_entry, row.jimaku_filename,
                         row.jimaku_size, row.jimaku_last_modified, CONFIDENT, u"",
                         output_path=result.output_path, kept_path=row.kept_path,
                         subtitle_hash=row.subtitle_hash,
                         match_rate=getattr(result, "match_rate", None))
            # ⚠ THE SAME LINE `_candidates` HAS, AND IT WAS MISSING HERE. A file
            # landed in that folder, so the cached listing taken before it is now
            # a lie for every later video decided against the same folder -- and
            # under `--out` whole shows share one. Two write paths that disagree
            # about whether to tell the present-check is a defect waiting for the
            # day the second one matters.
            self.look.forget(os.path.dirname(result.output_path))
            return VideoResult(video, CONFIDENT, u"", tsubasa=result,
                               output_path=result.output_path, kept_path=row.kept_path,
                               jimaku_entry=row.jimaku_entry, attempts=(attempt,),
                               jimaku_filename=row.jimaku_filename)
        outcome, reason = attempt.outcome, attempt.reason
        reason = u"%s, but %s" % (what, reason)
        if row.jimaku_entry is not None and row.jimaku_filename:
            # ⚠ `kept_path` on a row that is not a success (RUNBOOK 8b): the file this
            # candidate IS lives in subs_dir, not in the working cache, and it is the
            # one thing a person could pick later. `synced()` reads CONFIDENT rows
            # only, so this can never be mistaken for a place to re-sync from.
            self._record(video, video_hash, row.jimaku_entry, row.jimaku_filename,
                         row.jimaku_size, row.jimaku_last_modified, outcome, reason,
                         kept_path=row.kept_path, subtitle_hash=row.subtitle_hash,
                         match_rate=attempt.match_rate)
        return VideoResult(video, outcome, reason, tsubasa=result, attempts=(attempt,),
                           jimaku_entry=row.jimaku_entry,
                           jimaku_filename=row.jimaku_filename)

    # -- identification and the file list -----------------------------------

    def _identify(self, show, needing):
        u"""-> True when identification ran. False means its videos are ERRORs
        and are already recorded (an empty title, a 5xx on the search)."""
        try:
            # ⚠ `year=` IS NOT OPTIONAL HERE. It had never been passed, so the
            # parameter `resolution.cache_key` carries -- and the store CHECKs --
            # was dead in production and two shows collided under one key.
            ident = identify(show.title, season=show.season, year=show.year,
                             client=self.client, cache=self.resolutions, kitsu=self.kitsu)
        except _STOPPERS as exc:
            raise _Stop(str(exc))
        except _SHOW_FAILURES as exc:
            show.reason = str(exc)
            for video, _root in needing:
                self._keep_result(show, VideoResult(
                    video, ERROR, u"this show could not be identified: %s" % exc))
            return False
        show.resolved = ident.resolved
        show.reason = ident.reason
        # ⭐ Keep the runners-up. They cost nothing here -- the search already
        # scored them -- and they are the only thing that lets `_escalate` move
        # past an entry that turns out to hold none of this folder's episodes.
        if ident.resolved is not None:
            show.alternates = [c for c in ident.candidates
                               if c.accepted and c.id != ident.resolved.entry_id]
        return True

    def _entry_files(self, entry_id, stale=False):
        u"""jimaku's whole file list for the entry. ⛔ No `episode=`, ever.

        One listing per entry per run. `stale=True` refreshes it ONCE, which is
        `06-edge-cases.md` §4's answer to a download that 404s -- and only once,
        because a second stale list is a fault, not a race.
        """
        if stale:
            if entry_id in self._relisted:
                return None
            self._relisted.add(entry_id)
        elif entry_id in self._files:
            return self._files[entry_id]
        try:
            listed = self.client.files(entry_id)
        except _STOPPERS as exc:
            raise _Stop(str(exc))
        self._files[entry_id] = listed
        return listed

    def _align(self, show, files, videos):
        with self.cache.workdir(u"align") as work:
            alignment = episodes.align(files, videos, workdir=work,
                                       movie=bool(show.resolved.movie))
        show.notes.extend(alignment.notes)
        return alignment

    def _archive_note(self, show, files):
        u"""⭐ An archive this run did not open is NAMED, never silent.

        ⛔ ONLY WHILE ARCHIVES ARE OFF. With them on, `_archives_pass` says what it
        did with every archive it opened, and one it did not need is not news.
        It used to be said either way -- *"were NOT opened"* printed over the
        archive the same run had just opened, and it still called opening one
        *"a step the spec does not have"* long after RUNBOOK 4d built it
        (ADVERSARY 2026-09-23). ⚠ The window has no archives switch, so the
        sentence names the config key and the flag, not a setting.
        """
        if self.s.archives:
            return
        found = [f["name"] for f in files if archives.is_archive(f.get("name") or u"")]
        if not found:
            return
        show.notes.append(
            u"%d archive(s) on this entry were NOT opened: %s. hato opens one only when "
            u"`archives = true` is in config.toml, or with --archives; `hato extract` "
            u"unpacks one by hand, and `hato sync` pairs it."
            % (len(found), u", ".join(sorted(found)[:3])
               + (u", …" if len(found) > 3 else u"")))

    # -- the candidate loop -------------------------------------------------

    def _escalate(self, show, needing, alignment, files):
        u"""A LOW CONFIDENCE entry that holds NOTHING: try the next one. -> (alignment, files)

        🚨 MEASURED LIVE 2026-09-17, and it is the difference between a subtitle and
        none. `Re Zero kara Hajimeru Isekai Seikatsu - 52` (absolute numbering, so
        `season=None`) ties every entry of the show, and the one that won was **entry
        332, season 1** -- 138 files, not one of them in the 52-62 range. The run
        reported *"nothing could be placed"* and stopped, **with the other entries
        already scored and sitting in hand.** jimaku keeps a separate entry per
        season (Frieren has two), so the next candidate is usually the right one.

        ⚠ The guards, in order, and each one is what keeps this cheap:
          * only when **no video at all** was offered a file -- a partial match is
            06 §2's ordinary *"entry has 1-8, folder has 9-12"*, not a wrong entry
          * only when the pick was **LOW CONFIDENCE** -- a confident entry missing
            an episode is a NOT_FOUND with a retry date, and re-asking buys the
            same answer for a metered call
          * ⛔ never for a movie entry, where every file is a candidate anyway
          * at most `ALTERNATE_ENTRIES`, so a wrong title cannot walk the catalogue

        ⭐ When one works, the resolution cache is REPOINTED at it, so the next run
        goes straight there for zero extra calls -- otherwise every run would pay
        this again, which is the *"constant redundant operations"* failure.

        🚨 9a -- *"offered a file"* means one the person's FORMAT settings take
        (`_takes`). With the fallback off, a wrong season's entry offering only
        `.srt` counted as an offer: nothing was escalated, the wait described the
        wrong season's files, and the wrong entry stayed cached -- two days later
        it was still the one listed (ADVERSARY 2026-09-23 #2a).
        """
        if any(self._takes(alignment, v) for v, _r in needing):
            return alignment, files
        if (show.resolved is None or show.resolved.movie
                or not show.resolved.low_confidence or not show.alternates):
            return alignment, files
        # Said in the note when it is the FORMAT that sent the run elsewhere.
        other_kind = any(str(v.path) in alignment.per_video for v, _r in needing)

        before = self.client.metered
        try:
            for cand in show.alternates[:ALTERNATE_ENTRIES]:
                try:
                    other = self._entry_files(cand.id)
                except _STOPPERS:
                    raise
                except (_client.EntryNotFound,) + _SHOW_FAILURES:
                    continue
                trial = self._align(show, other, [v for v, _r in show.videos])
                if not any(self._takes(trial, v) for v, _r in needing):
                    continue
                was = show.resolved
                # ⚠ `cand.source`, not a word of my own: `Resolved` validates the
                # source against a closed vocabulary, and the escalated entry came
                # from exactly the search that scored it. The fact that it was the
                # RUNNER-UP is provenance for a person, and it goes in the note
                # below -- ⛔ not into a field whose values something else parses.
                show.resolved = Resolved(cand.id, cand.name, False, cand.score,
                                         True, cand.source, None)
                self.resolutions.put(cache_key(show.title, show.season, show.year),
                                     show.resolved)
                show.notes.append(
                    u"Entry %d (%s) held nothing for any video here%s, so the next entry "
                    u"the search scored was tried: %d (%s), which does. That is what this "
                    u"show is now remembered as."
                    % (was.entry_id, was.entry_name,
                       u" in a format your settings take" if other_kind else u"",
                       cand.id, cand.name))
                show.files_listed = len(other)
                return trial, other
        finally:
            show.api_calls += self.client.metered - before
        return alignment, files

    def _takes(self, alignment, video):
        u"""⭐ 9a -- does `alignment` offer `video` a file the person's FORMAT
        settings would take? -> bool

        🚨 NOT *"is it in `per_video`"*, which is what the escalation and the
        archive pass asked: with the fallback off an entry offering only the
        other format answered *yes* to both, so the run stopped at a wrong
        season's entry, and an archive holding the preferred kind was never
        opened (ADVERSARY 2026-09-23 #2). ⚠ Format only -- the rank's other
        filters are not this question's.
        """
        return any(formats.accepts(tokens.subtitle_format(c.file["name"]),
                                   self.s.prefer_format, self.s.format_fallback)
                   for c in alignment.per_video.get(str(video.path)) or ())

    def _archives_pass(self, show, needing, alignment, files):
        u"""⭐ OPT-IN (`--archives`, off by default): open a batch archive. -> (alignment, files)

        RULED 2026-09-17 (Sonic): *"are we concerned about auto-doing that? there
        may be bad files downloaded in the zip. How about adding it in settings, a
        toggle and if so, it will. default off"*. Unpacking a stranger's archive is
        the one place hato acts on structure it did not author, so the person turns
        it on. ⛔ While off, nothing here runs and the archive is named in a note.

        ⚠ A FALLBACK, never the first move: it opens one only for videos that
        plain files could not serve, because a batch archive is the most expensive
        thing on an entry (One Piece's are hundreds of megabytes for one episode).
        ⭐ Extraction lands in the working cache and its members are committed there
        content-addressed, under the same `.ja` name rule every download gets, so
        everything downstream -- ranking, the port, the kept original -- treats a
        member exactly like a download. `extract` already refuses zip-slip, caps
        size and member count, and takes subtitles only (92 checks at 3c).
        """
        if not self.s.archives:
            return alignment, files
        # ⭐ 9a -- WANTED MEANS NOTHING THE PERSON'S FORMAT SETTINGS TAKE. A video the
        # plain files offer only in the OTHER format was left out, so an archive
        # holding the preferred kind was never opened (ADVERSARY 2026-09-23 #2b).
        wanted = [v for v, _r in needing if not self._takes(alignment, v)]
        if not wanted:
            return alignment, files
        packs = [f for f in files if archives.is_archive(f.get("name") or u"")]
        for pack in packs[:ARCHIVES_PER_SHOW]:
            name = pack.get("name") or u"archive"
            # ⭐ ONE ALREADY IN THE WORKING CACHE IS NOT DOWNLOADED AGAIN. A video
            # an archive cannot serve comes back at every retry -- a day, for a
            # wait -- and each retry fetched the whole archive again to learn the
            # same thing: measured 1, 2, 3, 4 downloads over four days (ADVERSARY
            # 2026-09-23 #2c; the same was true of 1.0.2 for an episode the archive
            # lacks). ⚠ `find_named` needs the SIZE jimaku lists to agree too: a
            # re-upload that changes it is downloaded, and a stale copy offers only
            # candidates the timing verdict still judges.
            blob = self.cache.find_named(_cache.safe_name(name), pack.get("size"))
            if blob is None:
                try:
                    blob = self.cache.store(self.download(pack), _cache.safe_name(name))
                except _STOPPERS as exc:
                    raise _Stop(str(exc))
                except (_client.JimakuError, OSError) as exc:
                    show.notes.append(u"%s could not be downloaded, so it was not opened: %s"
                                      % (name, exc))
                    continue
            try:
                with self.cache.workdir(name) as scratch:
                    found = archives.extract(blob, os.path.join(str(scratch), u"out"))
                    members = [
                        {"name": m.name, "size": m.size, "url": pack.get("url"),
                         "last_modified": pack.get("last_modified"),
                         "local": str(self.cache.store_file(
                             m.path, keep.download_name(m.name, self.lang)))}
                        for m in found.members]
            except (archives.ArchiveError, archives.ArchiveUnsupported,
                    keep.UntaggedOriginal, ValueError, OSError) as exc:
                show.notes.append(u"%s was not opened: %s" % (name, exc))
                continue
            if not members:
                show.notes.append(u"%s held no subtitles." % name)
                continue
            trial = self._align(show, list(files) + members,
                                [v for v, _r in show.videos])
            # ⚠ A MEMBER must land -- `local` marks one. A wanted video can now be
            # one the plain files reach in the other format, and `trial` holds those
            # plain files too, so "is it in `per_video`" is true of it whatever the
            # archive held.
            if not any(c.file.get("local") for v in wanted
                       for c in trial.per_video.get(str(v.path)) or ()):
                show.notes.append(u"%s was opened (%d subtitle(s) inside) and none of them "
                                  u"lands on a video here." % (name, len(members)))
                continue
            show.notes.append(u"%s was opened because the plain files offered nothing your "
                              u"settings take: %d subtitle(s) inside, and they are candidates "
                              u"like any other -- the timing verdict still decides."
                              % (name, len(members)))
            return trial, list(files) + members
        return alignment, files

    def _retry_on_another_entry(self, show, results, seen_groups):
        u"""Every attempt REFUSED: try the next entry the search scored. -> results or None

        🚨 MEASURED ON A REAL LIBRARY, 2026-09-17. `_escalate` above catches the
        entry that offers *nothing*; this catches the one that offers only WRONG
        things, which is the commoner shape and looks like success until the
        verdicts come back. Re:Zero episodes 52, 54 and 55 -- seasonless names,
        absolute numbers -- resolved to **entry 332, season 1**, which offered five
        candidates per video from the wrong season. All fifteen were refused by
        timing, correctly. Nothing wrong was written, and nothing right either.

        ⚠ Only when the run has NOTHING to show: one CONFIDENT anywhere means the
        entry is right and those refusals are ordinary bad candidates. ⛔ Only a
        LOW CONFIDENCE pick, never a movie, and never more than
        `ALTERNATE_ENTRIES` -- a title nobody has must not walk the catalogue.

        ⭐ The replacement only happens if the alternate actually WINS one. Swapping
        one set of refusals for another buys nothing and would hide the first
        entry's reasons, which are what a person reads.

        ⚠ The refusal rows the first pass recorded are left alone, deliberately:
        they are keyed per (video × subtitle) and the new entry's files are
        different subtitles. The soft negative is left too -- a written file is
        checked BEFORE any negative (`03-permissions.md`'s read rule), so it can
        never suppress a video this pass just fixed.
        """
        if (show.resolved is None or show.resolved.movie
                or not show.resolved.low_confidence or not show.alternates):
            return None
        stuck = {str(v.path) for v, _r, res in results
                 if res.outcome == REFUSED and res.attempts}
        if not stuck:
            return None

        before = self.client.metered
        try:
            for cand in show.alternates[:ALTERNATE_ENTRIES]:
                try:
                    other = self._entry_files(cand.id)
                except _STOPPERS:
                    raise
                except (_client.EntryNotFound,) + _SHOW_FAILURES:
                    continue
                trial = self._align(show, other, [v for v, _r in show.videos])
                if not any(p in trial.per_video for p in stuck):
                    continue
                # 🚨 THE ALTERNATE IS THE ENTRY WHILE ITS FILES ARE TRIED. `_candidates`
                # reads the entry off `show.resolved`: left on the first one, the
                # alternate's files were RECORDED under the first entry's id -- so
                # the refusal check, which keys on the entry, never found them, and
                # a later *Look again* downloaded files already refused; and a kept
                # original was filed under the wrong show's name (ADVERSARY
                # 2026-09-22 F13). ⭐ Put back when the alternate does not win.
                was = show.resolved
                show.resolved = Resolved(cand.id, cand.name, False, cand.score,
                                         True, cand.source, None)
                fresh, won = [], False
                try:
                    for video, root, old in results:
                        if str(video.path) in stuck and str(video.path) in trial.per_video:
                            new = self._candidates(show, trial, video, root, seen_groups)
                            fresh.append((video, root, new))
                            won = won or new.outcome == CONFIDENT
                        else:
                            fresh.append((video, root, old))
                finally:
                    if not won:
                        show.resolved = was
                if not won:
                    continue
                self.resolutions.put(cache_key(show.title, show.season, show.year),
                                     show.resolved)
                show.files_listed = len(other)
                show.notes.append(
                    u"Every candidate from entry %d (%s) was refused by timing, so the next "
                    u"entry the search scored was tried: %d (%s), which holds this folder's "
                    u"episodes. That is what this show is now remembered as."
                    % (was.entry_id, was.entry_name, cand.id, cand.name))
                return fresh
        finally:
            show.api_calls += self.client.metered - before
        return None

    def _candidates(self, show, alignment, video, root, seen_groups):
        path = str(video.path)
        entry = show.resolved.entry_id
        video_hash = self._hash(path)
        # ⭐ RUNBOOK 8d. Read BEFORE this run records anything, so it is exactly the
        # files tried in EARLIER runs -- every ending below carries it, and a
        # success that follows refusals can say it was found on a retry.
        # ⚠ ONCE PER RUN: `_retry_on_another_entry` asks again for the same video
        # after this run has recorded its first entry's refusals, and a first-ever
        # success then said *"found on a retry"* (ADVERSARY 2026-09-22 F14).
        if video_hash not in self._earlier:
            self._earlier[video_hash] = self._remembered(video_hash)
        earlier = self._earlier[video_hash]
        # ⭐ RUNBOOK 8f -- the newest episode on offer, from the alignment in hand:
        # no request, nothing downloaded. Both endings that WAIT record it.
        newest = episodes.newest_offered(alignment, video)

        if path in alignment.refused:
            # ⚠ Refused on the VIDEO's own name -- in practice *no episode number
            # could be read* (`frieren S2.mkv`, a film sitting in a season folder);
            # a two-episode span never reaches here, `_gate` decides it for free.
            #
            # ⛔ NO ATTEMPT ROW: a REFUSED row must name the candidate it refused,
            # and there is none -- `hato/state.py` says so out loud, and an
            # anonymous refusal would be re-downloaded on every run anyway.
            #
            # ⭐ BUT A SOFT NEGATIVE, WHICH NAMES ONLY THE ENTRY. Without it
            # NOTHING was recorded, so the next run listed the entry's files all
            # over again to reach the identical refusal: measured [2, 1, 1, 1]
            # metered calls over four identical runs of one un-numberable video --
            # one call per run, for good, which is the exact cost the negative
            # cache exists to stop. The video's name will not change on its own,
            # and when the person renames it the hash is the same but the NAME is
            # read fresh, so nothing is lost by waiting a day.
            reason = alignment.refused[path]
            retry = None
            if not self.s.dry_run:
                retry = self.db.record_not_found(
                    video_hash=video_hash, video_path=path, lang=self.lang,
                    kind="soft", jimaku_entry=entry, reason=reason)
                reason = u"%s Nothing new will be listed for it before %s." % (
                    _sentence(reason), retry.strftime(u"%Y-%m-%d"))
            return VideoResult(video, REFUSED, reason, jimaku_entry=entry,
                               retry_after=retry, tried_before=earlier)
        if path in alignment.not_found:
            return self._not_found(video, alignment.not_found[path], entry=entry, hard=False,
                                   tried_before=earlier, newest_offered=newest)

        offered = alignment.per_video.get(path) or []
        ranking = rank.rank(offered, allow_ai=self.s.allow_ai,
                            seen_groups=frozenset(seen_groups),
                            prefer=self.s.prefer_format,
                            fallback=self.s.format_fallback)
        ranked = [r.candidate for r in ranking.ordered]
        if not ranked:
            # ⭐ 9a -- IT IS ON JIMAKU, in the other kind, and the person asked for
            # theirs only. ⛔ Never *"not on jimaku yet"*, which is false. A wait all
            # the same -- their kind may yet be uploaded -- and `formats.only_as()`
            # reads this reason back: the gate looks past the wait once the settings
            # would take ANY of these kinds. ⚠ Every kind, not the commonest: *"only
            # as .vtt"* over two `.srt` and three `.vtt` was false, and choosing `.srt`
            # never ended it (ADVERSARY 2026-09-23 #4).
            kinds = sorted(set(kind for kind in (tokens.subtitle_format(c.file["name"])
                                                 for c in ranking.other_format) if kind))
            if kinds:
                reason = formats.waiting_reason(kinds, self.s.prefer_format,
                                                len(ranking.other_format))
            elif ranking.excluded:
                reason = (u"every one of the %d file(s) the entry offers for this episode "
                          u"was filtered out: %s"
                          % (len(ranking.excluded),
                             u"; ".join(sorted(set(why.rstrip(u".").split(u" -- ")[0]
                                                   for _c, why in ranking.excluded)))))
            else:
                reason = u"jimaku entry %d has no file for this episode" % entry
            return self._not_found(video, reason, entry=entry, hard=False,
                                   tried_before=earlier, newest_offered=newest)

        # ⛔ NEVER RE-DOWNLOAD A REFUSAL. The identity is (entry, filename, size,
        # last_modified) from the LIST, so this costs no request at all -- and a
        # re-upload (size or last_modified changed) is a new candidate.
        fresh = [c for c in ranked
                 if self.s.force or not self.db.refused(
                     video_hash, self.lang, entry, c.file.get("name"),
                     c.file.get("size"), c.file.get("last_modified"))]
        cap = self.s.candidates + (LOW_CONFIDENCE_EXTRA if show.resolved.low_confidence else 0)

        if not fresh:
            # 🚨 D4 (RUNBOOK 8d): this ending passes NO attempts -- nothing was
            # downloaded this run -- so the pick row it made had nothing to pick.
            # Every one of those candidates is in `earlier`, file and all.
            return self._all_refused(video, entry, len(ranked), (), video_hash,
                                     already=True, offered=len(ranked),
                                     tried_before=earlier, newest_offered=newest)
        if self.s.dry_run:
            return VideoResult(
                video, PLANNED,
                u"would fetch: %d candidate%s offered, up to %d tried (%s first)"
                % (len(fresh), u"" if len(fresh) == 1 else u"s", min(cap, len(fresh)),
                   fresh[0].file["name"]),
                jimaku_entry=entry, jimaku_filename=fresh[0].file["name"],
                candidates_offered=len(ranked))

        attempts, downloaded = [], 0
        for cand in fresh[:cap]:
            attempt, blob = self._try(video, root, entry, cand)
            attempts.append(attempt)
            downloaded += attempt.bytes
            if attempt.outcome != CONFIDENT:
                self._record(video, video_hash, entry, cand.file.get("name"),
                             cand.file.get("size"), cand.file.get("last_modified"),
                             attempt.outcome, attempt.reason,
                             subtitle_hash=attempt.digest, match_rate=attempt.match_rate)
                if port.nothing_was_written(attempt.tsubasa):
                    # 🚨 ⛔ A FAILED WRITE IS AN ERROR AND IS NEVER A REFUSAL.
                    # Measured with a file sitting where the mirrored directory
                    # had to go: tsubasa said CONFIDENT, `write_failed`, match
                    # 100% -- the pair ALIGNED -- and the loop carried on to the
                    # next candidate, ran out, and reported REFUSED *"none held
                    # (100% match)"*, which contradicts itself in one sentence.
                    # Worse, it recorded a soft negative reading *"all refused by
                    # timing"*, so run 2 skipped the video with a false reason and
                    # it went quiet for a day EVEN AFTER the disk was fixed.
                    # ⛔ Stop here: the destination is the same destination for
                    # every other candidate, so escalating cannot help, and the
                    # thing to tell the person is tsubasa's own sentence, which
                    # names the file and the fix.
                    return VideoResult(video, ERROR, attempt.reason,
                                       tsubasa=attempt.tsubasa, jimaku_entry=entry,
                                       jimaku_filename=cand.file.get("name"),
                                       attempts=tuple(attempts),
                                       candidates_offered=len(ranked),
                                       bytes_downloaded=downloaded,
                                       tried_before=earlier)
                continue
            # ⚠ WRITE FIRST, KEEP SECOND: `subs_dir` holds exactly the originals
            # that were USED. A refused candidate stays in the disposable cache.
            kept, note = self._keep(show, blob, cand)
            if note:
                show.notes.append(note)
            self._record(video, video_hash, entry, cand.file.get("name"),
                         cand.file.get("size"), cand.file.get("last_modified"),
                         CONFIDENT, u"", output_path=attempt.tsubasa.output_path,
                         kept_path=str(kept) if kept else None,
                         subtitle_hash=attempt.digest, match_rate=attempt.match_rate)
            seen_groups.add(cand.group)
            self.look.forget(os.path.dirname(attempt.tsubasa.output_path))
            # ⭐ `tried_before` on a SUCCESS is how *"it was found on a retry"* gets
            # said at all (RUNBOOK 8e): the files refused in earlier runs, still
            # attached to the run that finally settled it.
            return VideoResult(video, CONFIDENT, u"", tsubasa=attempt.tsubasa,
                               jimaku_entry=entry, jimaku_filename=cand.file["name"],
                               output_path=attempt.tsubasa.output_path,
                               kept_path=str(kept) if kept else None,
                               attempts=tuple(attempts), candidates_offered=len(ranked),
                               bytes_downloaded=downloaded, tried_before=earlier)
        # 🚨 `len(attempts)`, NOT `len(fresh)` -- how many were TRIED, not how many
        # were available. Recorded at 5a's build and fixed here: with `--candidates 1`
        # against 13 offered, the refusal read *"13 candidates fetched and retimed"*
        # when one was, and `offered > tried` (13 > 13) was false, so the line telling
        # the person to raise the cap was withheld from the row that most needed it.
        return self._all_refused(video, entry, len(attempts), tuple(attempts),
                                 video_hash, already=False, offered=len(ranked),
                                 downloaded=downloaded, tried_before=earlier,
                                 newest_offered=newest)

    def _try(self, video, root, entry, cand):
        u"""Fetch ONE candidate and hand it to tsubasa. -> (Attempted, blob path)

        ⛔ Downloaded into the working cache and nowhere else. The media folder
        sees exactly one filesystem operation per success -- tsubasa's.
        """
        name = cand.file["name"]
        try:
            data = self._download(entry, cand)
        except _STOPPERS as exc:
            raise _Stop(str(exc))
        except _SHOW_FAILURES as exc:
            return Attempted(name, ERROR, u"%s could not be downloaded: %s" % (name, exc)), None
        try:
            # 🚨 `<jimaku stem>.ja.<ext>` -- see hato/keep.py. Untagged, tsubasa
            # writes `<video>.ass` and every later run fetches again.
            blob = self.cache.store(data, keep.download_name(name, self.lang))
        except (keep.UntaggedOriginal, OSError) as exc:
            return Attempted(name, ERROR, u"%s could not be kept in the cache: %s"
                             % (name, exc), size=len(data)), None
        result = self._hand_over(video, root, blob)
        outcome, reason = port.outcome_and_reason(result)
        if outcome != CONFIDENT:
            reason = u"%s: %s" % (name, reason)
        return Attempted(name, outcome, reason, result=result, size=len(data),
                         path=str(blob), digest=_cache.content_hash(data)), blob

    def _download(self, entry, cand):
        u"""The unmetered download, with §4's one stale-list retry."""
        local = cand.file.get("local")
        if local:
            # ⭐ An archive member (`_archives_pass`). It is already in the cache,
            # content-addressed, so reading it back and letting `_try` store it
            # again lands on the same path and writes nothing. ⛔ No request.
            with open(local, "rb") as fh:
                return fh.read()
        try:
            return self.download(cand.file)
        except _client.DownloadNotFound:
            pass
        refreshed = self._entry_files(entry, stale=True)
        if refreshed is None:
            raise _client.DownloadError(
                u"it 404'd and the entry's file list had already been refreshed once "
                u"this run -- the file is gone, not stale", status=404)
        again = next((f for f in refreshed if f.get("name") == cand.file.get("name")), None)
        if again is None:
            raise _client.DownloadError(
                u"it 404'd and is no longer on the refreshed file list -- it was removed "
                u"from jimaku", status=404)
        return self.download(again)

    def _hand_over(self, video, root, subtitle):
        u"""⭐ THE ONE PLACE A FILE IS WRITTEN, and tsubasa is what writes it."""
        out_dir = keep.target_dir(str(video.path), root, self.s.out) if self.s.out else None
        return port.sync(str(video.path), str(subtitle), write=True,
                         out_dir=out_dir, engine=self.engine)

    def _keep(self, show, blob, cand):
        try:
            return keep.keep_original(blob, self.s.subs_dir, show.resolved.entry_name,
                                      keep.download_name(cand.file["name"], self.lang)), None
        except (OSError, ValueError) as exc:
            # ⚠ The synced file IS written; only the kept copy failed. Never an
            # ERROR for the video -- that would report a success as a failure.
            return None, (u"the original of %s could not be kept in subs_dir (%s), so a "
                          u"later run would download it again." % (cand.file["name"], exc))

    # -- the two endings that are not a success -----------------------------

    def _all_refused(self, video, entry, tried, attempts, video_hash,
                     already, offered, downloaded=0, tried_before=(), newest_offered=None):
        u"""⚠ Every candidate refused -> a SOFT negative, then REFUSED.

        Without that row a video whose every candidate has been refused re-lists
        the entry on every run to learn nothing new -- one metered call per run,
        for good (`03-permissions.md`, ruled at build time).

        🚨 A DOWNLOAD THAT FAILED WAS NEVER TIMED (ADVERSARY 2026-09-23, beside 9a).
        Every candidate failing to download read *"N candidates fetched and
        retimed, none held"* and was recorded *"all refused by timing"* -- two
        false sentences, and a day of quiet for files nobody had looked at. Now
        that is an ERROR with NO wait, the ruling a failed WRITE already has
        (`LEDGER-HOT.md`): an error is not a verdict (`state.refused`), so the next
        run simply tries again. Some failed and some timed: a refusal still, and
        each half counted as what it was.
        """
        failed = [a for a in attempts if a.outcome == ERROR]
        if attempts and len(failed) == len(attempts):
            return VideoResult(
                video, ERROR,
                u"%d candidate%s could not be downloaded, so none was timed: %s"
                % (len(failed), u"" if len(failed) == 1 else u"s",
                   _sentence(failed[0].reason)),
                jimaku_entry=entry, attempts=attempts, candidates_offered=offered,
                bytes_downloaded=downloaded, tried_before=tried_before)
        timed = tried - len(failed)
        if already:
            reason = (u"all %d candidate%s for this episode have already been fetched and "
                      u"refused by timing -- none was downloaded again. `--force` re-tries "
                      u"them; `hato sync <video> <subtitle>` pairs one by hand."
                      % (tried, u"" if tried == 1 else u"s"))
        else:
            best = _best(attempts)
            reason = (u"%d candidate%s fetched and retimed, none held%s.%s %s"
                      % (timed, u"" if timed == 1 else u"s", _measured(attempts),
                         u" %d more could not be downloaded." % len(failed) if failed else u"",
                         u"Try `--candidates %d` to reach more of the %d offered, or pair one "
                         u"by hand with `hato sync`." % (tried + 2, offered) if offered > tried
                         else u"Pair one by hand with `hato sync <video> <subtitle>`."))
            if best is not None:
                reason = u"%s Best attempt: %s" % (reason, _sentence(best.reason))
        retry = None
        if not self.s.dry_run:
            retry = self.db.record_not_found(
                video_hash=video_hash, video_path=str(video.path), lang=self.lang,
                kind="soft", jimaku_entry=entry, newest_offered=newest_offered,
                reason=(u"%d of %d candidate(s) tried, all refused by timing"
                        % (tried, offered) if not failed else
                        u"%d of %d candidate(s) tried: %d refused by timing, %d could not "
                        u"be downloaded" % (tried, offered, timed, len(failed))))
            reason = u"%s Nothing new will be listed for it before %s." % (
                reason, retry.strftime(u"%Y-%m-%d"))
        best = _best(attempts)
        return VideoResult(video, REFUSED, reason, jimaku_entry=entry, attempts=attempts,
                           candidates_offered=offered, retry_after=retry,
                           bytes_downloaded=downloaded,
                           tsubasa=best.tsubasa if best is not None else None,
                           jimaku_filename=best.name if best is not None else None,
                           tried_before=tried_before, newest_offered=newest_offered)

    def _not_found(self, video, reason, entry, hard, tried_before=(), newest_offered=None):
        u"""⛔ NOT an error. *"jimaku has no episode 7"* is a normal, expected,
        recurring state that resolves itself when someone uploads one -- and it
        is never conflated with a fault (`03-permissions.md`).

        ⚠ A hard negative (no entry matched, 30 days) cannot name an entry and a
        soft one (the entry exists, no file for this episode, 1 day) must --
        `hato/state.py` refuses the two swapped, so they can never be confused.
        """
        retry = None
        if not self.s.dry_run:
            retry = self.db.record_not_found(
                video_hash=self._hash(str(video.path)),
                video_path=str(video.path), lang=self.lang,
                kind="hard" if hard else "soft",
                jimaku_entry=None if hard else entry, reason=reason,
                newest_offered=None if hard else newest_offered)
            # ⚠ `_sentence` first: these reasons already end in a full stop, and
            # ` -- will retry` appended straight on read *"...episode 24. -- will
            # retry after"*. Same class as the refusal's run-on, found the same way.
            reason = u"%s Will retry after %s." % (_sentence(reason),
                                                   retry.strftime(u"%Y-%m-%d"))
        return VideoResult(video, NOT_FOUND, reason, jimaku_entry=entry, retry_after=retry,
                           tried_before=tried_before,
                           newest_offered=None if hard else newest_offered)

    # -- the store ----------------------------------------------------------

    def _hash(self, path):
        u"""The video's head+tail hash, read ONCE per run per video.

        🚨 Never the whole video: head 64 KiB + tail 64 KiB + size, whatever its
        length (`hato/cache.py`). ⚠ Memoised because five DB questions are asked
        about one video and each would otherwise be another 128 KiB read --
        `spec/00-INDEX.md` Rule 4.
        """
        key = _key(path)
        if key not in self._hashes:
            self._hashes[key] = _cache.video_hash(path)
        return self._hashes[key]

    def _remembered(self, video_hash):
        u"""-> (Remembered, ...) every candidate tried for this video since it
        last succeeded, each with its file as it is on disk NOW (RUNBOOK 8d).

        ⛔ Reads only: the state DB and a stat per candidate. No request, and
        nothing is downloaded -- a file that is gone is offered with no path, and
        the window says so rather than committing something else.
        """
        return tuple(
            Remembered(row.jimaku_filename, row.outcome, row.reason,
                       row.jimaku_size or 0, row.match_rate,
                       keep.remembered_file(row, self.lang, self.cache),
                       row.attempted_at)
            for row in self.db.candidates(video_hash, self.lang))

    def _record(self, video, video_hash, entry, filename, size, last_modified,
                outcome, reason, output_path=None, kept_path=None,
                subtitle_hash=None, match_rate=None):
        # ⭐ `subtitle_hash` and `match_rate` (RUNBOOK 8b). The hash was specified in
        # 02-data-model.md and passed as None here since 1b, so a refusal could be
        # REMEMBERED but never OFFERED again: nothing said which downloaded file it
        # was, or how close it came.
        self.db.record_attempt(
            video_hash=video_hash, video_path=str(video.path), lang=self.lang,
            jimaku_entry=entry, jimaku_filename=filename, jimaku_size=size,
            jimaku_last_modified=last_modified, subtitle_hash=subtitle_hash,
            outcome=outcome, reason=reason, output_path=output_path,
            kept_path=kept_path, match_rate=match_rate)


def _key(path):
    u"""One video's identity as a path. ⚠ Normcased: on Windows `D:\\A\\x.mkv`
    and `d:\\a\\X.MKV` are one file, and two roots differing only in case are
    exactly how a person reaches the same tree twice."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


#: ⭐ ONE COPY, IN `paths`, AND THIS IS A NAME FOR IT -- moved 2026-09-18.
#: `hato/watch.py` needs the same answer and is FORBIDDEN to import this
#: module: that separation is the whole reason the tray watcher is 13.4 MB
#: rather than a resident Qt process. ⛔ The alternative was a second copy of
#: the prefix test, which is the one function where a drifted copy silently
#: takes a different library out of every run.
#: ⚠ The alias is kept because callers and a mutant name it; it is a second
#: NAME, never a second implementation.
_under_any = paths.under_any


def _sentence(text):
    u"""End a fragment so the next sentence cannot run into it. -> text

    🚨 FOUND BY LOOKING, 2026-09-17, not by a check: the refusal read *"...the
    timing does not hold Nothing new will be listed for it before 2026-09-18."*
    tsubasa's `reason` is a clause and carries no full stop, and this module
    appends its own sentence straight onto it. Every assertion was green because
    each half was correct; only the rendered line is wrong.
    """
    text = (text or u"").rstrip()
    if not text or text[-1] in u".!?:":
        return text
    return text + u"."


def _takeable(tracks, lang, prefer):
    u"""⭐ RUNBOOK 14c -- the Japanese tracks worth taking out, best first.
    -> (tracks, why there are none)

    ⛔ NEVER A FORCED TRACK: signs and songs only, not a whole subtitle (06 §6) --
    and saved, it is `<video>.ja.forced.<ext>`, which the present-check rightly
    never counts, so every later run would take it out again and be refused over
    its own file. A video whose only Japanese track is forced is downloaded for.
    ⭐ The person's preferred format first (`formats.of_codec`), then the one the
    file marks default, then the file's own order.
    """
    mine = [t for t in tracks if t.text and t.lang == lang]
    whole = [t for t in mine if not getattr(t, u"forced", False)]
    if not whole:
        return (), (u"its Japanese subtitle track is a FORCED one -- signs and songs "
                    u"only, not a whole subtitle")
    return sorted(whole, key=lambda t: (formats.of_codec(t.codec) != prefer,
                                        not getattr(t, u"default", False),
                                        t.index)), u""


#: ⭐ 14c -- a tsubasa with no `extract_subtitle` (a source checkout below the floor).
_OLD_TSUBASA = u"this tsubasa (%s) cannot take subtitles out of a video -- 0.1.9 can"


def _not_whole(tracks, lang):
    u"""⭐ 14z (C1, A-4) -- why a video's Japanese track is no subtitles to take out:
    signs only (forced), or pictures of text. -> words, or u"" when it has none."""
    mine = [t for t in tracks if t.lang == lang]
    if any(t.text and getattr(t, u"forced", False) for t in mine):
        return (u"its Japanese subtitle track is a FORCED one -- signs and songs only, "
                u"not a whole subtitle")
    pictures = [t for t in mine if getattr(t, u"bitmap", False)]
    if pictures:
        return (u"its Japanese subtitles are pictures of text (%s) -- there is nothing "
                u"to take out as a file" % (pictures[0].codec or u"an image track"))
    return u""


def _is_matroska(path):
    u"""⭐ 14z (C5) -- does the file START as Matroska does? -> bool. EBML's four magic
    bytes: tsubasa takes subtitles out of Matroska only."""
    try:
        with open(path, u"rb") as fh:
            return fh.read(4) == b"\x1a\x45\xdf\xa3"
    except OSError:
        return False


def _by_header(path, whole):
    u"""⭐ 14z (C5, C4) -- the track a run would take out, judged from the HEADER.
    -> (track, u"") or (None, why not). ⛔ Four bytes and the track list, never the
    track: for a PLAN, and for what `hato problems` remembers -- the run itself asks
    tsubasa, which walks the file and has the last word."""
    if not whole:
        return None, u""
    if not _is_matroska(path):
        return None, (u"%s is not an MKV file -- subtitles are taken out of MKV only"
                      % os.path.basename(path))
    for track in whole:
        if formats.of_codec(track.codec):
            return track, u""
    return None, (u"tsubasa does not take a %s track out as a file"
                  % (whole[0].codec or u"codec-less"))


def _plan_extension(codec):
    u"""The extension a plan says a track comes out as (`.srt`, `.ass`, `.ssa`)."""
    family = formats.of_codec(codec)
    return u"ssa" if family == u"ass" and u"SSA" in (codec or u"").upper() else family


#: ⭐ 14z (A-2) -- tsubasa's words for a track not all there yet (its `extract`: *"holds
#: empty bytes -- ... (a download in progress?) ... so the track is not all there"*).
#: ⚠ ITS PROSE: the check drives the real tsubasa over a real file with a stretch
#: zeroed, so a reworded refusal fails there, loudly -- not by downloading for a video
#: still arriving.
_UNFINISHED = (u"holds empty bytes", u"not all there")


def _unfinished(reason):
    return any(words in (reason or u"") for words in _UNFINISHED)


def why_not_taken(path, tracks, lang, prefer):
    u"""⭐ 14z (C4) -- why a run would NOT take `path`'s own Japanese subtitles out,
    judged from its header (`_by_header`) -- or u"" when it would, or when there are
    none inside. For what a finished run no longer holds: `hato problems`' rows."""
    if tracks.kind != present.EMBEDDED:
        return _not_whole(tracks.tracks, lang)
    if getattr(tsubasa, u"extract_subtitle", None) is None:
        return _OLD_TSUBASA % getattr(tsubasa, u"__version__", u"?")
    whole, why = _takeable(tracks.tracks, lang, prefer)
    return why if not whole else _by_header(path, whole)[1]

def _best(attempts):
    u"""The attempt that came closest -- what `03-permissions.md` calls the best
    attempt. ⚠ Highest match rate, and an attempt that never measured (a failed
    download) has none and never wins."""
    measured = [a for a in attempts if a.match_rate is not None]
    if not measured:
        return attempts[0] if attempts else None
    return max(measured, key=lambda a: a.match_rate)


def _measured(attempts):
    rates = [a.match_rate for a in attempts if a.match_rate is not None]
    if not rates:
        return u""
    return u" (%s match)" % u", ".join(u"%d%%" % round(r * 100) for r in rates)


__all__ = ["CONFIDENT", "REFUSED", "ERROR", "NOT_FOUND", "SKIPPED", "PLANNED",
           "PRESENT", "BLACKLISTED", "EMBEDDED", "NO_TRACK", "NEGATIVE",
           "LOW_CONFIDENCE_EXTRA", "ConfigProblem", "Settings", "Attempted",
           "Remembered", "VideoResult", "ShowReport", "RunReport", "run", "why_not_taken"]
