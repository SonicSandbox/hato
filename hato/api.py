# -*- coding: utf-8 -*-
u"""
The public library API -- `spec/05-interface.md` §*The library API*, built as it
is written there. surasura and any future caller consume THIS; the CLI is a thin
wrapper over the same `pipeline.run()` underneath.

    from hato import scan, identify, fetch, Result

    # Discovery -- filesystem + cache only. ZERO network. Never writes.
    plan = scan(u"/media/anime/s2")
    plan = scan([u"/media/a", u"/media/b"], lang=u"ja")

    # Identification -- cached; costs API calls only for unresolved shows.
    # Still writes nothing into the media folders.
    plan = identify(plan)

    # Acquisition + alignment -- the only call that downloads or writes.
    results = fetch(plan, write=True)          # -> list[Result]

⭐ A FACADE, NOT A SECOND IMPLEMENTATION. `hato/pipeline.py` already does all of
this work and `hato/commands/run.py` already assembles the world it needs; this
module joins them for a caller who is not a command line. ⛔ Nothing here
decides anything about a subtitle: no ranking, no alignment, no naming, no
second filename parser (`LEDGER-HOT.md`). If a rule appears to be missing here,
it is in the pipeline, and that is where it stays.

===========================================================================
⛔ THE THREE CONSTRAINTS INHERITED FROM TSUBASA -- AND WHAT ENFORCES EACH
===========================================================================

1. **Never assumes it owns a directory. Takes paths OR iterables of paths.**
   `_folders()` -- and 🚨 a bare `str` is ONE path, never six characters. That
   is the classic bug in this shape and `tests/test_api.py` pins it.
2. **Ignores non-video files silently.** Inherited whole: discovery is
   `tsubasa.scan()`, which answers with videos. Junk is expected input.
3. **Returns structured results. Prints nothing. Writes nothing unless told.**
   ⭐ `write` defaults to **False**, which is `--dry-run`: identified, planned,
   costed, and not one byte written. Nothing in this module prints.

===========================================================================
⚠ WHAT "ZERO NETWORK" AND "WRITES NOTHING" MEAN EXACTLY
===========================================================================

`scan()` builds no client, reads no key and makes no request -- so a caller with
no jimaku key at all can still discover a library. What it writes: nothing, in
the media folders or anywhere else.

`identify()` spends metered calls only for shows the resolution cache does not
already hold, and it WRITES THAT CACHE -- hato's own store under `HATO_CACHE`,
which is the whole reason a second call is free. ⛔ It writes nothing in the
media folders, downloads nothing, and touches no subtitle.

`fetch(plan, write=True)` is the only call that reaches the media folders, and
even then the media folder sees exactly one filesystem operation per success --
tsubasa's write (`spec/03-permissions.md`).

===========================================================================
⚠ WHO OWNS THE CLIENT, THE DB AND THE CACHES
===========================================================================

`World` (`hato/commands/run.py`) is the one place a run's world is built, and it
is a deliberate seam. Pass `world=` and it is YOURS: this module never closes
it, and a long-lived caller holding one open pays the setup once. Pass nothing
and each call builds its own and closes it before returning, so a library caller
leaks no handle by forgetting to.

⛔ NO RUN LOCK IS TAKEN, exactly as `pipeline.run()` takes none: a library caller
may already hold one (`hato/runlock.py`, `06-edge-cases.md` §9). The CLI holds
it because it is the process that owns the machine for that minute.
"""
import os

from hato import keep as _keep, pipeline as _pipeline
from hato import config as _config
from hato.commands import run as _run_command
from hato.pipeline import BLACKLISTED, CONFIDENT, ConfigProblem, EMBEDDED, \
    ERROR, NEGATIVE, NOT_FOUND, NO_TRACK, PLANNED, PRESENT, REFUSED, SKIPPED
from hato.resolution import identify as _identify_show

#: ⭐ The names `05-interface.md` §*`Result` carries* publishes, in its order.
#: Once hato is tagged these are a permanent compatibility promise, so they are
#: written down once, here, and `tests/test_api.py` checks the class against
#: this tuple rather than against a list somebody retyped.
SPEC_FIELDS = (u"video", u"outcome", u"reason", u"jimaku_entry",
               u"jimaku_filename", u"candidates_tried", u"tsubasa",
               u"output_path", u"kept_path", u"api_calls",
               u"bytes_downloaded", u"retry_after")

#: The settings a caller may lay over `config.toml`. ⚠ `None` means *not given*,
#: so the file's value (or the documented default) wins -- the same rule
#: `pipeline.Settings.from_config` applies to the CLI's flags, and the reason a
#: library caller and `hato <folder>` cannot disagree about a default.
_OVERRIDES = (u"lang", u"out", u"subs_dir", u"candidates", u"archives",
              u"allow_ai", u"recurse", u"skip_embedded", u"extract_embedded")


# ---------------------------------------------------------------------------
# paths in
# ---------------------------------------------------------------------------

def _one_path(value):
    u"""-> an absolute str. ⛔ Refuses bytes loudly rather than passing it on."""
    if isinstance(value, bytes):
        # ⛔ `os.fspath` would hand back bytes, `os.path.abspath` would keep
        # them, and tsubasa's scanner would fail four frames away on something
        # that reads like an internal fault. Refused here, by name.
        raise TypeError(
            u"hato takes text paths, not bytes: %r. Decode it first "
            u"(a Japanese path decoded as cp1252 is the failure this refuses)."
            % (value,))
    return os.path.abspath(os.path.expanduser(os.fspath(value)))


def _folders(given):
    u"""A path, or an iterable of paths -> [str], or None for *not given*.

    🚨 A BARE `str` IS ONE PATH. `list("D:/Anime")` is nine folders named `D`,
    `:`, `/`, ... -- the classic bug in every API that accepts "one or many",
    and it fails as *"no such folder"* nine times instead of scanning once.
    `os.PathLike` is here for the same reason: a `pathlib.Path` is iterable in
    spirit and must not be walked either.
    """
    if given is None:
        return None
    if isinstance(given, (str, bytes, os.PathLike)):
        given = [given]
    else:
        try:
            given = list(given)
        except TypeError:
            raise TypeError(
                u"hato takes a folder, or an iterable of folders -- got %s (%r). "
                u"A str, a pathlib.Path, or any iterable of either."
                % (type(given).__name__, given))
    return [_one_path(one) for one in given]


# ---------------------------------------------------------------------------
# what a run produced -- one video
# ---------------------------------------------------------------------------

class Result(object):
    u"""One video's single outcome, as `05-interface.md` publishes it.

    ⭐ `tsubasa` IS TSUBASA'S OWN `Result`, PASSED THROUGH UNCHANGED -- not
    re-wrapped, not summarised. A caller that already understands tsubasa
    understands this, and the two can never disagree about what a run did.

    `outcome`
        `CONFIDENT` · `REFUSED` · `ERROR` · `NOT_FOUND` -- and ⚠ two more the
        spec's list does not name, both of which a real run produces:
        `SKIPPED` (decided before anything was fetched -- `skip` says which of
        *present · blacklisted · embedded · no-track · negative*) and
        `PLANNED`, which is every result of `fetch(plan)` without `write=True`.
    `candidates_tried`
        how many candidates were downloaded and retimed for this video. ⚠ This
        is the spec's name for `len(VideoResult.attempts)`; `candidates_offered`
        is how many the entry held, which is usually larger -- ⚠ or None when
        this run never listed the entry: a video skipped while it waits for its
        retry, and every row `hato problems` remembers.
    `api_calls`
        ⚠ ALWAYS 0, and it is not a bug here: metered calls are spent per SHOW
        (one search and one file listing serve every video of it), so no
        per-video number exists to report. The real figures are
        `Results.api_calls` for the run and `ShowReport.api_calls` per show.
        Recorded against `05-interface.md` -- see `SPEC_FIELDS`.
    """

    __slots__ = (u"video", u"name", u"title", u"season", u"episode", u"outcome",
                 u"skip", u"reason", u"jimaku_entry", u"jimaku_filename",
                 u"candidates_tried", u"candidates_offered", u"attempts",
                 u"tsubasa", u"output_path", u"kept_path", u"api_calls",
                 u"bytes_downloaded", u"retry_after", u"wrote", u"taken_from",
                 u"not_taken")

    def __init__(self, result):
        u"""`result` is a `pipeline.VideoResult`."""
        self.video = result.video
        self.name = result.name
        self.title = result.title
        self.season = result.season
        self.episode = result.episode
        self.outcome = result.outcome
        self.skip = result.skip
        self.reason = result.reason
        self.jimaku_entry = result.jimaku_entry
        self.jimaku_filename = result.jimaku_filename
        # ⚠ The spec's name for the pipeline's `attempts`. `hato/report.py`'s
        # `as_dict` derives it the same way -- ⛔ never a second count kept in
        # parallel, which is how two numbers about one run start disagreeing.
        self.attempts = tuple(result.attempts or ())
        self.candidates_tried = len(self.attempts)
        self.candidates_offered = result.candidates_offered
        self.tsubasa = result.tsubasa
        self.output_path = result.output_path
        self.kept_path = result.kept_path
        self.api_calls = result.api_calls
        self.bytes_downloaded = result.bytes_downloaded
        self.retry_after = result.retry_after
        # ⭐ TAKEN, NOT RE-DERIVED. `VideoResult.wrote` owns what "it landed"
        # means; a second copy of that expression here is a second thing to
        # keep in step with tsubasa's `write_failed`.
        self.wrote = result.wrote
        # ⭐ 14z (A-8) -- the track a subtitle was taken out of the video from, and why
        # one the setting asked to take out was downloaded for: what every row says.
        self.taken_from = getattr(result, "taken_from", None)
        self.not_taken = getattr(result, "not_taken", None)
        if self.outcome != CONFIDENT and not (self.reason or u"").strip():
            # ⛔ `05-interface.md`: *"`reason` is never empty on a non-confident
            # outcome."* A constructor invariant at the published boundary, not
            # a rule a caller is asked to trust: *"it failed"* is not actionable
            # and a BLANK is worse (`03-permissions.md` §the hand-back path).
            raise ValueError(
                u"a %s result for %s reached the library API with no reason, and "
                u"05-interface.md says a non-confident outcome always carries one"
                % (self.outcome, self.name))

    def __repr__(self):
        return "<hato.Result %s %s%s>" % (
            self.outcome, self.name, u" (%s)" % self.skip if self.skip else u"")


class Results(list):
    u"""`list[Result]` -- and the run's own facts, which a bare list cannot hold.

    ⭐ IT IS A REAL `list`: indexing, iteration, `len`, slicing and `== [...]`
    all behave, which is what `05-interface.md`'s `results: list[Result]` says.
    The attributes are additions, and 🚨 one of them is not optional:

    `stopped`
        the sentence that ended the run early (a 401, an unreachable server), or
        None. ⛔ Without it a truncated run and a complete one are the same
        short list, and *"nothing else was even looked at"* is unsayable.
    """

    def __init__(self, results, report):
        list.__init__(self, results)
        #: `pipeline.RunReport`, verbatim -- the shows, the notes, the settings.
        self.report = report

    @property
    def api_calls(self):
        u"""Metered jimaku calls this run spent. ⭐ On every run, because it is a
        shared resource and a caller who cannot see the cost cannot notice a
        runaway loop (`05-interface.md`)."""
        return self.report.api_calls

    @property
    def bytes_downloaded(self):
        return self.report.bytes_downloaded

    @property
    def seconds(self):
        return self.report.seconds

    @property
    def stopped(self):
        return self.report.stopped

    @property
    def notes(self):
        return list(self.report.notes)

    @property
    def shows(self):
        u"""[`pipeline.ShowReport`] -- what each show resolved to, and what it cost."""
        return list(self.report.shows)

    def counts(self):
        u"""outcome -> how many. ⚠ Skips are counted by their KIND."""
        return self.report.counts()

    def __repr__(self):
        return "<hato.Results %d video(s), %d API call(s)%s>" % (
            len(self), self.api_calls, ", STOPPED" if self.stopped else "")


# ---------------------------------------------------------------------------
# what was asked for
# ---------------------------------------------------------------------------

class Plan(object):
    u"""What `scan()` found and `identify()` learned. Handed to `fetch()`.

    ⚠ `identify()` FILLS THIS IN AND RETURNS THE SAME OBJECT, so
    `plan = identify(plan)` and `identify(plan)` leave exactly one plan in
    existence. ⛔ Deliberate: two copies of a plan, one of them stale, is a
    defect with nothing to catch it.
    """

    __slots__ = (u"settings", u"shows", u"lang", u"notes", u"identified",
                 u"api_calls", u"kitsu_calls", u"world", u"fixtures")

    def __init__(self, settings, shows, lang, notes, world=None, fixtures=None):
        #: `pipeline.Settings` -- config.toml with the caller's arguments over it.
        self.settings = settings
        #: [`pipeline.ShowReport`], grouped by the title, season and YEAR tsubasa
        #: read -- never by folder (`06-edge-cases.md` §1).
        self.shows = list(shows)
        #: The language tag tsubasa RESOLVED, which is what the present-check
        #: matches on. ⚠ Not necessarily the string that was asked for.
        self.lang = lang
        #: Folders that could not be scanned, and anything else a person should
        #: read. ⛔ One unusable folder never ends a scan over five others.
        self.notes = list(notes)
        self.identified = False
        self.api_calls = 0
        self.kitsu_calls = 0
        #: A `commands.run.World`, if the caller supplied one. ⛔ Never built by
        #: `scan()`: that would read a jimaku key for a call that makes no request.
        self.world = world
        #: Recorded-response directory for `--fixtures`-style offline runs, or None.
        self.fixtures = fixtures

    @property
    def videos(self):
        u"""Every video discovered, as absolute paths. -> [str]"""
        return [str(video.path) for show in self.shows for video, _root in show.videos]

    @property
    def unresolved(self):
        u"""The shows `identify()` still has no jimaku entry for. -> [ShowReport]

        ⚠ Before `identify()` has run that is all of them, which is the honest
        answer: nothing has been asked.
        """
        return [show for show in self.shows if show.resolved is None]

    def __repr__(self):
        return "<hato.Plan %d show(s), %d video(s)%s>" % (
            len(self.shows), len(self.videos),
            ", identified" if self.identified else "")


# ---------------------------------------------------------------------------
# the world, and the settings
# ---------------------------------------------------------------------------

class _Offline(object):
    u"""⛔ A CLIENT THAT CANNOT MAKE A CALL, handed to discovery.

    ⭐ Structural, not remembered (`doctrine/robustness`): *"scan() makes ZERO
    network calls"* is not a promise this module keeps by being careful -- the
    only client discovery has refuses to search, list or download, by name. If a
    future discovery step reaches for the network it fails here, loudly, in the
    suite, instead of spending somebody's metered budget in production.
    """

    metered = 0
    unmetered = 0

    def _refuse(self, what):
        raise AssertionError(
            u"scan() must make ZERO network calls (spec/05-interface.md) and "
            u"something asked it to %s. Discovery is filesystem and cache only; "
            u"identify() and fetch() are the calls that may spend quota." % what)

    def search(self, *args, **kwargs):
        self._refuse(u"search jimaku")

    def files(self, *args, **kwargs):
        self._refuse(u"list an entry's files")

    def download(self, *args, **kwargs):
        self._refuse(u"download a subtitle")


class _WorldArgs(object):
    u"""The one field `commands.run.build_world` reads. ⚠ If it ever reads a
    second, this raises `AttributeError` by name rather than quietly building a
    different world than the CLI does."""

    __slots__ = ("fixtures",)

    def __init__(self, fixtures):
        self.fixtures = fixtures


def _world(fixtures=None):
    u"""-> `commands.run.World`. ⛔ The CLI's own assembly, called and never
    re-typed: the key resolution, the client, the state DB, the resolution
    cache, Kitsu and the working cache all come from `build_world`, so a library
    caller and `hato <folder>` can never be looking at different stores."""
    return _run_command.build_world(_WorldArgs(fixtures))


def _replace(settings, **changes):
    u"""A `Settings` with some fields changed. -> `pipeline.Settings`

    ⚠ Enumerated from `Settings.__slots__` rather than from a list typed here:
    a field added there flows through without an edit, and if one is ever added
    that the constructor does not accept, this fails loudly on the next call
    instead of silently dropping it. `tests/test_api.py` pins the round trip.
    """
    values = dict((name, getattr(settings, name)) for name in settings.__slots__)
    values.update(changes)
    return _pipeline.Settings(**values)


def _settings(folders, given):
    u"""config.toml, with the caller's arguments over it. -> `pipeline.Settings`"""
    overrides = dict((name, given.get(name)) for name in _OVERRIDES)
    if overrides.get(u"skip_embedded") is not None \
            and overrides.get(u"extract_embedded") is None:
        # ⭐ 14z (C-7) -- `skip_embedded` GIVEN ALONE MEANS WHAT IT DID BEFORE 1.0.8:
        # leave, or download anyway -- never the file's *save*, which wins over it.
        # Measured: `scan(skip_embedded=True)` WROTE `.ja.srt` into the media folder
        # because config.toml said save. As `--even-if-embedded` does.
        overrides[u"extract_embedded"] = False
    return _pipeline.Settings.from_config(
        _config.load(), folders=folders, force=bool(given.get(u"force")),
        dry_run=True, **overrides)


# ---------------------------------------------------------------------------
# ⭐ 1. scan -- filesystem + cache only
# ---------------------------------------------------------------------------

def scan(folders=None, *, lang=None, out=None, subs_dir=None, candidates=None,
         archives=None, allow_ai=None, recurse=None, skip_embedded=None,
         extract_embedded=None, force=False, world=None, fixtures=None):
    u"""Discover the videos under `folders`. -> `Plan`

    ⛔ FILESYSTEM AND CACHE ONLY. Zero network, no key read, nothing written.

        plan = scan(u"/media/anime/s2")
        plan = scan([u"/media/a", u"/media/b"], lang=u"ja")

    `folders`
        a path, or an iterable of paths. ⛔ With none, `config.toml`'s `folders`
        are used -- and a run with neither is a `ConfigProblem`, never a silent
        scan of nothing.
    `lang` · `out` · `subs_dir` · `candidates` · `archives` · `allow_ai` ·
    `recurse` · `skip_embedded` · `extract_embedded`
        `config.toml`'s settings, overridden for this plan. ⚠ `None` means *not
        given*: the file's value, or the documented default, wins.
    `world`
        a `commands.run.World` you own and will close. ⛔ `scan()` never touches
        it and never builds one -- see the module note.

    ⛔ Raises `ConfigProblem` for anything that means the run cannot start: no
    folder, a `subs_dir` or an `out` inside a folder being scanned, a language
    tsubasa cannot resolve, no readable folder at all. ⭐ ONE exception type for
    every startup refusal (`LEDGER.md` §interface) -- a handler that has to know
    four is decoration.
    """
    given = dict(lang=lang, out=out, subs_dir=subs_dir, candidates=candidates,
                 archives=archives, allow_ai=allow_ai, recurse=recurse,
                 skip_embedded=skip_embedded, extract_embedded=extract_embedded,
                 force=force)
    settings = _settings(_folders(folders), given)
    # ⛔ BOTH DOORS, BEFORE ANYTHING IS SCANNED, and these are `hato/keep.py`'s
    # own sentences -- ⛔ never re-typed here. A `subs_dir` inside a scanned
    # folder makes the kept originals candidates for the videos beside them; an
    # `--out` inside one puts hato's finished files in the tree under the
    # videos' own basenames, where a later `tsubasa <folder>` supersedes them
    # into the trash (measured 2026-09-17, `LEDGER-HOT.md`).
    # ⚠ `pipeline.run()` asks again at `fetch()`, which is what actually guards
    # the write. This is the same question asked at the caller's FIRST call, so
    # a plan that can never be fetched is refused before the discovery cost.
    try:
        _keep.check_subs_dir(settings.subs_dir, settings.folders)
        _keep.check_out_dir(settings.out, settings.folders)
    except _keep.InsideScan as exc:
        raise ConfigProblem(str(exc))
    # ⭐ THE PIPELINE'S OWN DISCOVERY, not a second copy of it. Grouping by the
    # title, season and year tsubasa read; a video found under two given folders
    # counted once; a folder that cannot be scanned recorded as a note; and the
    # two-videos-one-output-file check that has to happen before the run.
    # ⚠ `_Run._discover` is private and this is the one private thing here:
    # the alternative is a second grouping implementation, and this project's
    # whole reason for existing is that two copies of a parsing rule drift.
    walker = _pipeline._Run(settings, client=_Offline(), db=None, resolutions=None,
                            kitsu=None, cache=None, downloader=None, engine=None,
                            reader=None, clock=None)
    shows = walker._discover()
    return Plan(settings, shows, walker.lang, walker.report.notes,
                world=world, fixtures=fixtures)


# ---------------------------------------------------------------------------
# ⭐ 2. identify -- cached; a metered call only for an unresolved show
# ---------------------------------------------------------------------------

def identify(plan, *, world=None):
    u"""Resolve each show to a jimaku entry. -> the same `Plan`, filled in

    ⭐ CACHED. A show the resolution cache already holds costs nothing, so a
    second `identify()` over the same plan makes ZERO calls -- which is what
    makes this cheap to call before deciding whether to fetch at all.

    ⛔ Writes nothing in the media folders and downloads nothing. ⚠ It DOES
    write hato's own resolution cache; that is the caching above.

    🚨 A 401, an unreachable server or a rate limit RAISES (`client.KeyRejected`,
    `Unreachable`, `RateLimited`, `NetworkDisabled`). ⛔ Never swallowed as a
    per-show reason: a failed request still spends quota, so a bad key would
    burn the whole budget silently, one show at a time (`LEDGER-HOT.md`).
    Anything that is one SHOW's problem -- a 5xx on its search, a title with no
    letter in it, a response nobody recorded -- lands in `show.reason` and the
    rest of the plan carries on.

    ⚠ Shows identified before a raise KEEP their resolutions: the plan is filled
    in as it goes, so a caller that catches and retries does not pay twice.
    """
    own = world is None and plan.world is None
    world = world if world is not None else (plan.world or _world(plan.fixtures))
    before, kitsu_before = world.client.metered, _kitsu_calls(world)
    try:
        for show in plan.shows:
            spent = world.client.metered
            try:
                # ⚠ `year=` IS NOT OPTIONAL. tsubasa DROPS a bracketed year, so
                # without it `Hunter x Hunter (1999)` and `(2011)` are one show
                # under one cache key for ever (`06-edge-cases.md` §1). It was
                # dead in production once; ⛔ it is not dead here.
                found = _identify_show(show.title, season=show.season,
                                       year=show.year, client=world.client,
                                       cache=world.resolutions, kitsu=world.kitsu)
            except _pipeline._STOPPERS:
                # ⛔ FIRST, and it re-raises. These are subclasses of the
                # per-show family below, so the order is the behaviour.
                raise
            except _pipeline._SHOW_FAILURES as exc:
                show.reason = str(exc)
                show.api_calls += world.client.metered - spent
                continue
            show.resolved = found.resolved
            show.reason = found.reason
            show.api_calls += world.client.metered - spent
            if found.resolved is not None:
                # ⭐ The runners-up, kept because they cost nothing here and are
                # the only thing that lets a fetch move past an entry that holds
                # none of this folder's episodes (`pipeline._escalate`).
                show.alternates = [c for c in found.candidates
                                   if c.accepted and c.id != found.resolved.entry_id]
    finally:
        plan.api_calls = world.client.metered - before
        plan.kitsu_calls = _kitsu_calls(world) - kitsu_before
        plan.identified = True
        if own:
            world.close()
    return plan


def _kitsu_calls(world):
    return getattr(world.kitsu, "calls", 0) if world.kitsu is not None else 0


# ---------------------------------------------------------------------------
# ⭐ 3. fetch -- the only call that downloads or writes
# ---------------------------------------------------------------------------

def fetch(plan, write=False, *, world=None):
    u"""Fetch, retime and place a subtitle for every video that needs one.

    -> `Results` (a `list[Result]`, plus the run's own cost and `stopped`)

    `write`
        ⛔ **False by default** -- *"writes nothing unless told"*. Off, this is
        the plan: every show identified, every video decided, every candidate
        costed, and ⛔ nothing downloaded, nothing written, no row recorded.
        Every result comes back `PLANNED` or as the skip that made it free.
        ⭐ On, it is the whole job: `<video stem>.ja.<ext>` beside the video (or
        under `out=`, mirroring the source tree), the original kept in
        `subs_dir`, and one row per attempt in the state DB.

    ⚠ `identify()` is OPTIONAL. This resolves whatever is still unresolved from
    the same cache, so `scan()` -> `fetch()` is a complete, correct two-step.

    ⛔ A refusal, a NOT_FOUND and an error on one video are NORMAL outcomes and
    never raise: every video comes back with exactly one outcome and a reason
    (`spec/03-permissions.md`). What raises is a run that cannot start --
    `ConfigProblem` -- and 🚨 a run cut short mid-way sets `results.stopped`
    rather than losing the results it already had.
    """
    settings = _replace(plan.settings, dry_run=not write)
    own = world is None and plan.world is None
    world = world if world is not None else (plan.world or _world(plan.fixtures))
    try:
        # ⛔ `hato/commands/run.py`'s own call, argument for argument. The seams
        # (`downloader`, `engine`, `reader`) ride along so a caller that already
        # has bytes, a verdict or a track list can supply them -- which is what
        # the suite does, and what `World` exists for.
        report = _pipeline.run(
            settings, client=world.client, db=world.db,
            resolutions=world.resolutions, kitsu=world.kitsu, cache=world.cache,
            downloader=world.downloader, engine=world.engine, reader=world.reader,
            extractor=world.extractor)
    finally:
        if own:
            world.close()
    return Results([Result(one) for one in report.results], report)


__all__ = ["scan", "identify", "fetch", "Result", "Results", "Plan",
           "ConfigProblem", "SPEC_FIELDS",
           "CONFIDENT", "REFUSED", "ERROR", "NOT_FOUND", "SKIPPED", "PLANNED",
           "PRESENT", "BLACKLISTED", "EMBEDDED", "NO_TRACK", "NEGATIVE"]
