# -*- coding: utf-8 -*-
u"""
`hato/api.py` -- the PUBLIC library API (`spec/05-interface.md` §*The library
API*). Once hato is tagged these names are a permanent compatibility promise, so
what this suite mostly proves is that the promise is kept:

  * the four published names exist, and `Result` carries every field the spec
    lists, under exactly the spec's own names -- ⭐ quoted into this file, not
    imported from the module under test, so deleting one cannot make the check
    agree with the deletion
  * ⛔ `scan()` makes ZERO network calls, reads no key and writes nothing --
    with the socket guard PROVEN able to fail in the same check
  * ⛔ `fetch()` writes nothing unless told: `write` defaults to False
  * ⛔ nothing in the API prints a single character
  * 🚨 a bare `str` is ONE folder, never one folder per character
  * ⚠ `Settings`'s defaults and `config.py`'s schema agree -- they have
    disagreed before, and only the CLI road obeyed the ruling (`LEDGER-HOT.md`)

⛔ ZERO NETWORK. The metered half is the REAL client answering from the REAL
captures in `tests/fixtures/api/`, so the call COUNTS asserted here are the
counts a real run makes. The subtitle BYTES come from the `downloader=` seam,
because Whitelist 2 forbids recording a subtitle body (`07-test-plan.md`).

⭐ THE LAST CHECK RUNS THE WHOLE FACADE WITH THE REAL tsubasa, on a video ffmpeg
really built. Everything above it believes a stub about what a verdict is.

⛔ WHAT THIS SUITE STRUCTURALLY CANNOT COVER
  * whether the FETCH LOOP is right. That is `tests/test_pipeline.py`; this
    suite asserts that the facade reaches it and reports it faithfully, and a
    decision made inside `pipeline.run()` is not re-proved here
  * whether jimaku still answers this way (`hato doctor` and the `live` suite)
  * whether `hato.scan` -- the name on the PACKAGE -- is wired. That edit is in
    `hato/__init__.py` and belongs to `tests/test_wiring.py`; this suite drives
    `hato.api` directly, so it stays green either way
  * per-video `api_calls`: there is no per-video number to check, because
    metered calls are spent per SHOW. See `test_the_run_total_is_what_the_client_spent`
"""
import io
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import tsubasa

import conftest
from hato import api, config as config_module, credentials, keep, pipeline, \
    port, resolution, state
from hato import client as client_module
from hato.cache import Cache
from hato.commands import run as run_command
from hato.kitsu import KitsuClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _media                                                      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
API = FIXTURES / "api"

#: ⭐ THE SPEC'S OWN LIST, QUOTED VERBATIM from `05-interface.md` §*`Result`
#: carries*, 2026-09-17. ⛔ NOT imported from `hato/api.py`: a check that reads
#: its expectation out of the thing it is checking agrees with every change,
#: including a deletion. This is the compatibility promise, written down twice
#: on purpose.
#:
#:   `video` · `outcome` (CONFIDENT / REFUSED / ERROR / NOT_FOUND) · `reason` ·
#:   `jimaku_entry` · `jimaku_filename` · `candidates_tried` · `tsubasa` ·
#:   `output_path` · `kept_path` · `api_calls` · `bytes_downloaded` · `retry_after`
SPEC_RESULT_FIELDS = (u"video", u"outcome", u"reason", u"jimaku_entry",
                      u"jimaku_filename", u"candidates_tried", u"tsubasa",
                      u"output_path", u"kept_path", u"api_calls",
                      u"bytes_downloaded", u"retry_after")


# ---------------------------------------------------------------------------
# the bench
# ---------------------------------------------------------------------------

class Track(object):
    u"""A container track, as tsubasa's reader describes one."""

    def __init__(self, lang=u"en", text=True, bitmap=False, codec=u"S_TEXT/UTF8", index=2):
        self.lang, self.text, self.bitmap = lang, text, bitmap
        self.codec, self.index, self.forced = codec, index, False


class Answer(object):
    u"""`tsubasa.EmbeddedSubtitles`, and ⛔ `.tracks` raises when `ok` is False
    exactly as the real one does -- a stub laxer than the engine proves the stub."""

    def __init__(self, ok=True, reason=u"", tracks=None):
        self.ok, self.reason = ok, reason
        self._tracks = (Track(),) if tracks is None else tuple(tracks)

    @property
    def tracks(self):
        if not self.ok:
            raise ValueError(u"could not be read: %s" % self.reason)
        return self._tracks


def episodes_up_to(count, pattern=u"frieren S2 - %02d.mkv"):
    return [pattern % n for n in range(1, count + 1)]


class Bench(object):
    u"""One library caller's world: a folder of stub videos, the REAL client over
    the REAL captures, a real state DB and resolution cache in a temp dir, and
    the three seams `commands.run.World` carries.

    ⚠ EVERY STUB VIDEO CARRIES DISTINCT BYTES. The state DB is keyed on the
    head+tail hash, so ten zero-byte files would be ONE video to it -- one
    refusal would blacklist the whole folder and every check here would pass
    while measuring nothing.
    """

    def __init__(self, tmp_path, names=None, stems=None, client=None, junk=()):
        self.root = Path(tmp_path)
        self.media = self.root / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        for name in (episodes_up_to(3) if names is None else names):
            (self.media / name).write_bytes(b"\x1aE\xdf\xa3" + name.encode("utf-8"))
        for name in junk:
            (self.media / name).write_bytes(b"not a video, and not an error either")
        self.subs = self.root / "subs"
        self.out = self.root / "out"
        self.now = [datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)]
        self.db = state.StateDB(self.root / "state.db", now=lambda: self.now[0])
        self.resolutions = resolution.ResolutionCache(self.root / "resolution.db")
        self.cache = Cache(self.root / "cache")
        self.session = client_module.RecordedSession(FIXTURES, stems=stems)
        self.client = client or client_module.JimakuClient(
            credentials.Key(u"recorded-responses-need-no-key", u"the suite"),
            self.session, sleep=lambda seconds: None)
        #: every jimaku filename the loop asked for the bytes of
        self.downloads = []
        #: video basename -> `Answer`. The default is an ENGLISH text track,
        #: which is the shape hato fetches for.
        self.tracks = {}
        #: candidate name -> `port.stub_engine` keyword arguments.
        self.decide = lambda name: {}
        self.use_real_engine = False
        self.body = None

    # -- the seams ---------------------------------------------------------

    def reader(self, video, **kwargs):
        return self.tracks.get(os.path.basename(video), Answer())

    def download(self, item):
        self.downloads.append(item["name"])
        if self.body is not None:
            return self.body
        return (u"1\n00:00:01,000 --> 00:00:02,000\n%s\n" % item["name"]).encode("utf-8")

    def engine(self, pairs, **kwargs):
        (_video, subtitle), = list(pairs)
        return port.stub_engine(**self.decide(os.path.basename(subtitle)))(pairs, **kwargs)

    def world(self):
        u"""⭐ `commands.run.World` -- the documented seam, built by hand here
        because Whitelist 2 forbids a recorded subtitle body."""
        return run_command.World(
            client=self.client, db=self.db, resolutions=self.resolutions,
            kitsu=KitsuClient(self.session), cache=self.cache,
            downloader=self.download,
            engine=None if self.use_real_engine else self.engine,
            reader=None if self.use_real_engine else self.reader)

    # -- driving -----------------------------------------------------------

    def scan(self, folders=None, **options):
        options.setdefault("subs_dir", str(self.subs))
        options.setdefault("candidates", 1)
        return api.scan(self.media if folders is None else folders,
                        world=self.world(), **options)

    # -- reading it back ---------------------------------------------------

    def names_in(self, folder):
        folder = Path(folder)
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def rows(self):
        return self.db.stats()["rows"]


def snapshot(*folders):
    u"""Every path under `folders`, with its size and mtime. -> dict

    ⚠ An absent folder is recorded as ABSENT rather than skipped, so a folder
    the call CREATES is a difference and not an invisible no-op. That is the
    shape of *"writes nothing"* that can actually fail.
    """
    seen = {}
    for folder in folders:
        folder = Path(folder)
        if not folder.exists():
            seen[str(folder)] = u"ABSENT"
            continue
        for path in sorted(folder.rglob("*")):
            stat = path.stat()
            seen[str(path)] = (path.is_dir(), stat.st_size, stat.st_mtime_ns)
    return seen


def only(results, outcome):
    return [r for r in results if r.outcome == outcome]


# ---------------------------------------------------------------------------
# 1. ⭐ the published shape -- the compatibility promise
# ---------------------------------------------------------------------------

def test_the_four_published_names_exist_and_are_callable():
    u"""`from hato import scan, identify, fetch, Result`. ⛔ `05-interface.md`
    publishes these four; a tag over a module missing one is a broken promise
    that cannot be taken back."""
    for name in (u"scan", u"identify", u"fetch", u"Result"):
        assert hasattr(api, name), (
            u"hato/api.py does not define %s, which spec/05-interface.md "
            u"§The library API publishes as part of the public API" % name)
        assert name in api.__all__, (
            u"%s is defined but missing from hato/api.py's __all__, so "
            u"`from hato.api import *` and the package wiring would not see it" % name)
    for name in (u"scan", u"identify", u"fetch"):
        assert callable(getattr(api, name)), u"hato.api.%s is not callable" % name


def test_Result_carries_every_field_the_spec_names():
    u"""⭐ THE COMPATIBILITY CHECK. Each name is quoted from the spec into this
    file, so a field dropped from `hato/api.py` fails here instead of quietly
    redefining what hato promises."""
    slots = set(api.Result.__slots__)
    missing = [name for name in SPEC_RESULT_FIELDS if name not in slots]
    assert not missing, (
        u"hato.Result is missing %d field(s) spec/05-interface.md §`Result` "
        u"carries names: %s -- these are a published promise, not internals"
        % (len(missing), u", ".join(missing)))


def test_Result_refuses_a_non_confident_outcome_with_no_reason():
    u"""⛔ `05-interface.md`: *`reason` is never empty on a non-confident
    outcome* -- a constructor invariant at the published boundary.

    ⚠ WHY THIS DRIVES THE CONSTRUCTOR DIRECTLY. `pipeline.VideoResult` refuses
    the same thing, so every result a real run produces already carries a
    reason and the invariant here can never fire from a run -- which would make
    it unfalsifiable and therefore worthless. `VideoResult`'s slots are writable,
    so the state is built the way a future pipeline path could: a result whose
    outcome is set AFTER construction.
    """
    late = pipeline.VideoResult(u"D:\\Anime\\frieren S2 - 01.mkv", pipeline.CONFIDENT, u"")
    late.outcome = pipeline.REFUSED
    late.reason = u"   "

    with pytest.raises(ValueError) as refused:
        api.Result(late)

    assert u"reason" in str(refused.value), (
        u"a REFUSED result with a blank reason was refused, but the message "
        u"does not say what was missing: %s" % refused.value)
    assert api.Result(pipeline.VideoResult(
        u"D:\\Anime\\frieren S2 - 01.mkv", pipeline.CONFIDENT, u"")).reason == u"", (
        u"a CONFIDENT result is allowed an empty reason and was refused one -- "
        u"a refusal-only check passes against a constructor that refuses "
        u"everything (doctrine/robustness)")


def test_the_outcome_words_are_importable_so_nobody_compares_a_string_literal():
    u"""⚠ tsubasa's `certain` was a SUBSTRING of `uncertain` and that re-armed a
    real defect for every consumer that string-matched (`LEDGER.md` §Interface).
    A caller must be able to import the word, not retype it."""
    for name in (u"CONFIDENT", u"REFUSED", u"ERROR", u"NOT_FOUND",
                 u"SKIPPED", u"PLANNED"):
        assert name in api.__all__, (
            u"hato.api does not export the outcome word %s, so a caller has to "
            u"compare against a string literal it typed itself" % name)
        assert getattr(api, name) == getattr(pipeline, name), (
            u"hato.api.%s is %r and hato.pipeline.%s is %r -- two spellings of "
            u"one outcome is how a consumer starts disagreeing with the run"
            % (name, getattr(api, name), name, getattr(pipeline, name)))


# ---------------------------------------------------------------------------
# 2. ⛔ paths in -- constraint 1, and the classic bug
# ---------------------------------------------------------------------------

def test_a_bare_string_is_one_folder_not_one_folder_per_character(tmp_path):
    u"""🚨 THE CLASSIC BUG IN THIS SHAPE. `list("D:/Anime")` is nine folders
    named `D`, `:`, `/`, `A`... and it fails as *"no such folder"* nine times
    instead of scanning once.

    ⚠ The first assertion is on the coercion itself, deliberately: taking a str
    apart makes `scan()` raise *"none of the 22 folders given could be
    scanned"*, and a check whose only evidence is an exception from three frames
    down proves less than one that prints the count it found.
    """
    bench = Bench(tmp_path, names=episodes_up_to(2))

    coerced = api._folders(str(bench.media))
    assert coerced == [str(bench.media)], (
        u"a str path was taken apart into %d path(s), first %r -- one folder was "
        u"asked for" % (len(coerced), coerced[:3]))

    plan = bench.scan(str(bench.media))

    assert list(plan.settings.folders) == [str(bench.media)], (
        u"scan() took a str path apart: it recorded %d folder(s) %r for the one "
        u"folder %s" % (len(plan.settings.folders), list(plan.settings.folders)[:4],
                        bench.media))
    assert len(plan.videos) == 2, u"expected 2 videos, got %r" % (plan.videos,)


def test_a_path_a_string_and_an_iterable_all_scan_the_same_videos(tmp_path):
    u"""⛔ Constraint 1: *takes paths OR iterables of paths*, and never assumes
    it owns a directory."""
    bench = Bench(tmp_path, names=episodes_up_to(2))
    each = [bench.scan(bench.media),                       # a pathlib.Path
            bench.scan(str(bench.media)),                  # a str
            bench.scan([bench.media]),                     # a list of one
            bench.scan((str(bench.media),)),               # a tuple
            bench.scan(iter([bench.media]))]               # a generator
    found = [sorted(plan.videos) for plan in each]
    assert all(one == found[0] for one in found), (
        u"the five ways of naming one folder did not agree: %s"
        % u" | ".join(u"%d videos" % len(one) for one in found))
    assert len(found[0]) == 2, u"expected 2 videos, got %r" % (found[0],)


def test_a_bytes_path_is_refused_by_name(tmp_path):
    u"""⛔ Refuse loudly. `os.fspath` would hand bytes straight on and the
    failure would surface four frames away as an internal fault -- and a
    Japanese path decoded as cp1252 is exactly how this arrives."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    with pytest.raises(TypeError) as refused:
        bench.scan(str(bench.media).encode("utf-8"))
    assert u"bytes" in str(refused.value), (
        u"a bytes path was refused, but the message does not say bytes: %s"
        % refused.value)


def test_something_that_is_not_a_path_at_all_is_refused_by_name(tmp_path):
    u"""⚠ `list(7)` raises a bare *'int' object is not iterable*, which says
    nothing about folders. The refusal names what hato takes."""
    Bench(tmp_path, names=episodes_up_to(1))
    with pytest.raises(TypeError) as refused:
        api.scan(7)
    assert u"folder" in str(refused.value), (
        u"scan(7) was refused, but the message never mentions a folder: %s"
        % refused.value)


# ---------------------------------------------------------------------------
# 3. ⛔ scan -- zero network, no key, nothing written
# ---------------------------------------------------------------------------

def test_scan_makes_zero_network_calls_with_the_guard_proven_able_to_fail(tmp_path):
    u"""⛔ *Discovery -- filesystem + cache only. ZERO network.*

    ⭐ THE CONTROL IS IN THE SAME CHECK. `conftest.py` arms the socket layer; a
    check that merely runs under it proves nothing unless the guard can fire, so
    this makes it fire FIRST (`doctrine/evidence`: make the instrument disagree
    with something you already know) and only then runs `scan()` under it.
    """
    with pytest.raises(conftest.NetworkForbidden):
        socket.getaddrinfo(u"jimaku.cc", 443)

    bench = Bench(tmp_path, names=episodes_up_to(3))
    before = bench.client.metered

    plan = bench.scan()

    assert len(plan.videos) == 3
    assert bench.client.metered == before, (
        u"scan() spent %d metered jimaku call(s); spec/05-interface.md says "
        u"discovery is filesystem and cache only"
        % (bench.client.metered - before))
    assert plan.api_calls == 0, (
        u"scan() reported %d API call(s) on the plan" % plan.api_calls)
    assert bench.downloads == [], (
        u"scan() downloaded %r" % (bench.downloads,))


def test_scan_reads_no_jimaku_key_at_all(tmp_path):
    u"""⭐ A caller with NO key can still discover a library.

    The control: the suite's environment has no key, and `resolve_key()` proves
    it by raising -- so if `scan()` built a client the call below would raise
    `KeyMissing` instead of returning a plan.
    """
    with pytest.raises(credentials.KeyMissing):
        credentials.resolve_key()

    bench = Bench(tmp_path, names=episodes_up_to(2))
    plan = api.scan(bench.media, subs_dir=str(bench.subs))     # ⛔ no world at all

    assert len(plan.videos) == 2
    assert plan.world is None


def test_scan_writes_nothing(tmp_path):
    u"""⛔ *Never writes.* Asserted over the media folder, the subs_dir and the
    out dir -- the three places hato can put something -- and an absent folder
    counts as a difference if the call creates it."""
    bench = Bench(tmp_path, names=episodes_up_to(3), junk=(u"notes.txt",))
    where = (bench.media, bench.subs, bench.out)
    before = snapshot(*where)

    bench.scan()

    after = snapshot(*where)
    changed = sorted(set(before) ^ set(after)) or sorted(
        k for k in before if before[k] != after[k])
    assert before == after, (
        u"scan() changed %d path(s) under the media folders, first: %s"
        % (len(changed), changed[:3]))


def test_scan_ignores_non_video_files_silently(tmp_path):
    u"""⛔ Constraint 2: *junk is expected input, not an error.*"""
    bench = Bench(tmp_path, names=episodes_up_to(2),
                  junk=(u"notes.txt", u"cover.jpg", u"frieren S2 - 01.ja.srt",
                        u"Thumbs.db"))

    plan = bench.scan()

    assert sorted(os.path.basename(v) for v in plan.videos) == [
        u"frieren S2 - 01.mkv", u"frieren S2 - 02.mkv"], (
        u"the junk beside the videos was not ignored: %r"
        % ([os.path.basename(v) for v in plan.videos],))
    assert plan.notes == [], u"junk produced a note: %r" % (plan.notes,)


def test_scan_groups_by_title_season_and_year_never_by_folder(tmp_path):
    u"""⭐ Proves the facade uses the PIPELINE's discovery and not a second copy
    of it: tsubasa DROPS a bracketed year, so `(1999)` and `(2011)` would be one
    show under one cache key for ever (`06-edge-cases.md` §1). A re-derived
    grouping would not know that."""
    bench = Bench(tmp_path, names=[u"Hunter x Hunter (1999) - 01.mkv",
                                   u"Hunter x Hunter (2011) - 01.mkv",
                                   u"frieren S2 - 01.mkv"])

    plan = bench.scan()

    years = sorted(show.year for show in plan.shows if show.year is not None)
    assert years == [1999, 2011], (
        u"the two Hunter x Hunter releases were not told apart by year: shows "
        u"came back as %r" % ([(s.title, s.season, s.year) for s in plan.shows],))
    assert len(plan.shows) == 3, (
        u"expected 3 shows (two HxH years + frieren), got %r"
        % ([(s.title, s.season, s.year) for s in plan.shows],))


def test_a_subs_dir_inside_a_scanned_folder_is_refused_at_scan(tmp_path):
    u"""⛔ `LEDGER-HOT.md`: the kept originals would be discovered as candidates
    for the videos beside them, and a `tsubasa <folder>` run could supersede
    them. ⭐ Refused at the caller's FIRST call, not at the write."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    with pytest.raises(pipeline.ConfigProblem) as refused:
        bench.scan(subs_dir=str(bench.media / u"kept"))
    assert u"kept" in str(refused.value).lower() or u"subs" in str(refused.value).lower(), (
        u"a subs_dir inside the scan was refused, but the message does not name "
        u"it: %s" % refused.value)


def test_an_out_inside_a_scanned_folder_is_refused_at_scan(tmp_path):
    u"""🚨 WORSE THAN THE OTHER DOOR, and accepted until 2026-09-17: the files
    under `out` carry the VIDEOS' own basenames, so `tsubasa <folder>` afterwards
    put hato's finished file in the trash."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    with pytest.raises(pipeline.ConfigProblem) as refused:
        bench.scan(out=str(bench.media / u"Subs"))
    assert u"subs" in str(refused.value).lower(), (
        u"an --out inside the scan was refused, but the message does not name "
        u"the folder: %s" % refused.value)


def test_scan_with_no_folder_anywhere_is_a_config_problem(tmp_path):
    u"""⛔ Never a silent scan of nothing. ⭐ And it is `ConfigProblem` -- ONE
    exception type for every startup refusal."""
    Bench(tmp_path, names=episodes_up_to(1))
    with pytest.raises(pipeline.ConfigProblem) as refused:
        api.scan([])
    assert u"folder" in str(refused.value), (
        u"scan([]) was refused without naming the problem: %s" % refused.value)


def test_one_unscannable_folder_does_not_end_a_scan_over_the_others(tmp_path):
    u"""⚠ A run where NONE was usable is a ConfigProblem; one bad folder among
    good ones is a NOTE. Both halves matter -- a scan that dies on a typo is
    unusable for a caller pointing at five roots."""
    bench = Bench(tmp_path, names=episodes_up_to(2))
    missing = bench.root / "not-there"

    plan = bench.scan([bench.media, missing])

    assert len(plan.videos) == 2, (
        u"a missing folder alongside a good one lost the good one's videos: %r"
        % (plan.videos,))
    assert any(u"not-there" in note for note in plan.notes), (
        u"the unscannable folder produced no note; plan.notes = %r" % (plan.notes,))


# ---------------------------------------------------------------------------
# 4. ⭐ identify -- cached, and a metered call only for an unresolved show
# ---------------------------------------------------------------------------

def test_identify_costs_calls_for_an_unresolved_show_and_nothing_for_a_cached_one(tmp_path):
    u"""⭐ *Identification -- cached; costs API calls only for unresolved shows.*

    The second call is the claim. If the resolution cache were bypassed this
    would spend the same call again, every run, for ever.
    """
    bench = Bench(tmp_path, names=episodes_up_to(3))
    plan = bench.scan()

    first = api.identify(plan)
    assert first.api_calls >= 1, (
        u"identifying an unknown show cost %d metered call(s); one search is "
        u"the minimum a resolution can cost" % first.api_calls)
    show, = first.shows
    assert show.resolved is not None, u"the show did not resolve: %s" % show.reason
    assert show.resolved.entry_id > 0

    again = api.identify(bench.scan())
    assert again.api_calls == 0, (
        u"a second identify() of the same show cost %d metered call(s) -- the "
        u"resolution cache is not being read" % again.api_calls)
    assert again.shows[0].resolved.entry_id == show.resolved.entry_id


def test_identify_fills_in_the_same_plan_and_returns_it(tmp_path):
    u"""⚠ `plan = identify(plan)` and `identify(plan)` must leave exactly ONE
    plan in existence. Two copies, one of them stale, is a defect with nothing
    to catch it."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    plan = bench.scan()
    assert plan.identified is False
    assert plan.unresolved == plan.shows        # nothing has been asked yet

    same = api.identify(plan)

    assert same is plan, u"identify() returned a different object: %r" % (same,)
    assert plan.identified is True
    assert plan.unresolved == [], (
        u"the show is still unresolved after identify(): %s" % plan.shows[0].reason)


def test_identify_writes_nothing_in_the_media_folder(tmp_path):
    u"""⛔ *Still writes nothing.* ⚠ hato's own resolution cache IS written --
    that is the caching above -- so this is asserted where it means something:
    the user's folders."""
    bench = Bench(tmp_path, names=episodes_up_to(2))
    plan = bench.scan()
    where = (bench.media, bench.subs, bench.out)
    before = snapshot(*where)

    api.identify(plan)

    assert snapshot(*where) == before, (
        u"identify() touched the media folders: %s"
        % sorted(set(snapshot(*where)) ^ set(before))[:3])
    assert bench.downloads == [], u"identify() downloaded %r" % (bench.downloads,)


def test_identify_raises_past_a_401_instead_of_recording_it_per_show(tmp_path):
    u"""🚨 `LEDGER-HOT.md`: *never retry past a 401. A failed request still
    consumes rate-limit quota, so a bad key burns the whole budget silently.*
    ⛔ Swallowed as one show's reason, a bad key would spend the budget one show
    at a time, quietly. Driven off the REAL captured 401."""
    bench = Bench(tmp_path, stems=["search__401_bad_key"],
                  names=[u"frieren S2 - 01.mkv", u"Hunter x Hunter (2011) - 01.mkv"])
    plan = bench.scan()

    with pytest.raises(client_module.KeyRejected):
        api.identify(plan)

    assert bench.client.metered == 1, (
        u"a 401 was answered and hato went on to spend %d call(s) in total -- it "
        u"must stop at the first" % bench.client.metered)


def test_one_shows_failure_is_that_shows_reason_and_the_rest_still_runs(tmp_path):
    u"""⚠ Anything one SHOW can fail on leaves the others to run. A title with
    no letter or digit in it cannot be sent at all (an empty query returns
    jimaku's entire catalogue), and that is one show's problem."""
    bench = Bench(tmp_path, names=[u"frieren S2 - 01.mkv", u"-.mkv"])
    plan = bench.scan()

    api.identify(plan)

    by_title = dict((show.title, show) for show in plan.shows)
    good = [s for s in plan.shows if s.resolved is not None]
    bad = [s for s in plan.shows if s.resolved is None]
    assert good, u"no show resolved at all; reasons: %r" % (
        [(s.title, s.reason) for s in plan.shows],)
    assert bad, u"the unsendable title resolved anyway: %r" % (list(by_title),)
    assert bad[0].reason, (
        u"a show that could not be identified came back with an EMPTY reason, "
        u"which is not actionable output (spec/03-permissions.md)")


# ---------------------------------------------------------------------------
# 5. ⛔ fetch -- writes nothing unless told
# ---------------------------------------------------------------------------

def test_fetch_writes_nothing_unless_told(tmp_path):
    u"""⛔ CONSTRAINT 3, AND IT IS THE DEFAULT. `fetch(plan)` with no `write=`
    downloads nothing, writes nothing and records nothing -- it is the plan."""
    bench = Bench(tmp_path, names=episodes_up_to(3))
    plan = bench.scan()
    where = (bench.media, bench.subs, bench.out)
    before = snapshot(*where)

    results = api.fetch(plan)

    assert snapshot(*where) == before, (
        u"fetch(plan) with no write= changed the media folders: %s"
        % sorted(set(snapshot(*where)) ^ set(before))[:3])
    assert bench.downloads == [], (
        u"fetch(plan) with no write= downloaded %r" % (bench.downloads,))
    recorded = dict((outcome, n) for outcome, n in bench.rows().items() if n)
    assert recorded == {}, (
        u"fetch(plan) with no write= recorded %r in the state DB" % (recorded,))
    assert results, u"fetch(plan) returned nothing at all"
    assert all(r.outcome == api.PLANNED for r in results), (
        u"a dry fetch returned %r; every result must be PLANNED or a free skip"
        % (sorted(set(r.outcome for r in results)),))


def test_fetch_with_write_true_writes_keeps_and_records(tmp_path):
    u"""⭐ The whole job: a file beside the video, its original kept in
    subs_dir, and a row in the state DB."""
    bench = Bench(tmp_path, names=episodes_up_to(3))

    results = api.fetch(bench.scan(), write=True)

    confident = only(results, api.CONFIDENT)
    assert len(confident) == 3, (
        u"expected 3 confident results, got %r"
        % ([(r.name, r.outcome, r.reason) for r in results],))
    for one in confident:
        assert one.wrote is True, u"%s says CONFIDENT and wrote nothing" % one.name
        assert Path(one.output_path).is_file(), (
            u"%s reported output_path %s, which is not a file"
            % (one.name, one.output_path))
        assert Path(one.kept_path).is_file(), (
            u"%s reported kept_path %s, which is not a file"
            % (one.name, one.kept_path))
        assert tsubasa.parse_subtitle_name(Path(one.kept_path).name).lang == u"ja", (
            u"the kept original %s carries no `ja` tag, so a later run reads the "
            u"video as having no Japanese subtitle and fetches again"
            % Path(one.kept_path).name)
    assert bench.rows()[api.CONFIDENT] == 3, u"rows: %r" % (bench.rows(),)


def test_fetch_returns_a_real_list_of_Result(tmp_path):
    u"""`results: list[Result] = fetch(plan, write=True)`. ⭐ A real `list`:
    indexing, len, iteration and `==` all behave."""
    bench = Bench(tmp_path, names=episodes_up_to(2))

    results = api.fetch(bench.scan(), write=True)

    assert isinstance(results, list), (
        u"fetch() returned %s, and 05-interface.md says list[Result]"
        % type(results).__name__)
    assert len(results) == 2
    assert all(isinstance(r, api.Result) for r in results), (
        u"fetch() returned %r" % (sorted(set(type(r).__name__ for r in results)),))
    assert results[:1] == [results[0]], u"slicing a Results does not behave like a list"


def test_candidates_tried_is_how_many_were_tried_not_how_many_were_offered(tmp_path):
    u"""⚠ THE ONE RENAME. `candidates_tried` is the spec's name for the
    pipeline's `attempts`; `candidates_offered` is how many the entry held, and
    for a real entry it is larger. Conflating them is how *"13 candidates
    fetched"* got printed over one attempt (`hato/pipeline.py`, 5a)."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    bench.decide = lambda name: dict(outcome=port.REFUSED,
                                     reason=u"31% match -- the timing does not hold",
                                     match_rate=0.31)

    one, = api.fetch(bench.scan(candidates=2), write=True)

    assert one.outcome == api.REFUSED, u"%s: %s" % (one.outcome, one.reason)
    assert one.candidates_tried == len(one.attempts) == 2, (
        u"candidates_tried is %r while %d candidate(s) were attempted"
        % (one.candidates_tried, len(one.attempts)))
    assert one.candidates_offered > one.candidates_tried, (
        u"the entry offered %r candidate(s) and %r were tried -- with a cap of 2 "
        u"over a real 120-file entry the offered count must be larger"
        % (one.candidates_offered, one.candidates_tried))


def test_a_non_confident_result_never_carries_an_empty_reason(tmp_path):
    u"""⛔ `05-interface.md`: *`reason` is never empty on a non-confident
    outcome.* Asserted over every shape one run can produce at once."""
    bench = Bench(tmp_path, names=episodes_up_to(3) + [u"frieren S2 - 24.mkv"])
    bench.tracks[u"frieren S2 - 02.mkv"] = Answer(
        ok=False, reason=u"reading it needs ffmpeg, which was not found on PATH")
    bench.decide = lambda name: dict(outcome=port.REFUSED,
                                     reason=u"31% match -- the timing does not hold",
                                     match_rate=0.31)

    results = api.fetch(bench.scan(), write=True)

    shapes = set(r.outcome for r in results)
    assert len(shapes) >= 3, (
        u"this check needs several outcomes to be worth anything and got %r"
        % (sorted(shapes),))
    for one in results:
        if one.outcome == api.CONFIDENT:
            continue
        assert (one.reason or u"").strip(), (
            u"%s came back %s with an empty reason -- 'it failed' is not "
            u"actionable and a blank is worse" % (one.name, one.outcome))


def test_a_refusal_carries_its_retry_date_and_the_measurement(tmp_path):
    u"""`03-permissions.md` §the hand-back path: what was measured, why it fell
    short, what would change it."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    bench.decide = lambda name: dict(outcome=port.REFUSED,
                                     reason=u"31% match -- the timing does not hold",
                                     match_rate=0.31)

    one, = api.fetch(bench.scan(candidates=2), write=True)

    assert one.outcome == api.REFUSED
    assert u"31%" in one.reason, u"the measurement is missing: %s" % one.reason
    assert one.retry_after is not None, (
        u"a refusal with no retry date re-lists the entry on every run to learn "
        u"nothing new")


def test_tsubasa_is_passed_through_unchanged_never_rewrapped(tmp_path):
    u"""⭐ *`tsubasa` is tsubasa's `Result` passed through unchanged, not
    re-wrapped. A caller that already understands tsubasa understands this, and
    the two can never disagree about what a run did.*

    The check is IDENTITY: the object the library hands back is the same object
    the pipeline carried, and its type is tsubasa's.
    """
    bench = Bench(tmp_path, names=episodes_up_to(1))

    results = api.fetch(bench.scan(), write=True)

    one, = results
    inner, = results.report.results
    assert one.tsubasa is inner.tsubasa, (
        u"hato.Result.tsubasa is a different object (%r) from the one the "
        u"pipeline carried (%r) -- something re-wrapped it"
        % (one.tsubasa, inner.tsubasa))
    assert isinstance(one.tsubasa, tsubasa.Result), (
        u"Result.tsubasa is a %s, not a tsubasa.Result"
        % type(one.tsubasa).__name__)
    for field in (u"offset", u"match_rate", u"verdict_word", u"segments"):
        assert hasattr(one.tsubasa, field), (
            u"Result.tsubasa carries no %s, which 05-interface.md names as part "
            u"of what it passes through" % field)


def test_a_run_cut_short_says_so_instead_of_returning_a_short_list(tmp_path):
    u"""🚨 A 401 or an unreachable server ends the run and the videos after it
    were never looked at. ⛔ Without `stopped` a truncated run and a complete
    one are the same short list."""
    bench = Bench(tmp_path, stems=["search__401_bad_key"], names=episodes_up_to(2))

    results = api.fetch(bench.scan(), write=True)

    assert results.stopped, (
        u"the run was cut short by a 401 and results.stopped is %r, so a caller "
        u"cannot tell it apart from a complete run" % (results.stopped,))
    assert results == [], (
        u"nothing should have been decided after the 401, got %r"
        % ([r.name for r in results],))
    assert bench.names_in(bench.media) == sorted(episodes_up_to(2)), (
        u"the stopped run wrote something: %r" % (bench.names_in(bench.media),))


def test_the_run_total_is_what_the_client_spent(tmp_path):
    u"""⭐ *API calls spent, on every run* -- it is a shared metered resource and
    a caller who cannot see the cost cannot notice a runaway loop.

    ⚠ AND THE PER-VIDEO FIELD IS AN INVARIANT, NOT A NUMBER. Metered calls are
    spent per SHOW (one search and one file listing serve every video of it), so
    no per-video figure exists; what must never happen is a per-video total that
    exceeds the run's. Stated this way the check survives the field being given
    a real source later.
    """
    bench = Bench(tmp_path, names=episodes_up_to(3))
    before = bench.client.metered

    results = api.fetch(bench.scan(), write=True)

    spent = bench.client.metered - before
    assert results.api_calls == spent, (
        u"the run reports %d API call(s) and the client really made %d"
        % (results.api_calls, spent))
    assert spent == 2, (
        u"a folder of one show costs one search plus one file listing; this run "
        u"made %d metered call(s)" % spent)
    assert sum(r.api_calls for r in results) <= results.api_calls, (
        u"the per-video api_calls add up to %d, more than the %d the run spent "
        u"-- a per-show cost has been attributed to every video of it"
        % (sum(r.api_calls for r in results), results.api_calls))


def test_bytes_downloaded_comes_from_the_downloader_seam(tmp_path):
    u"""⚠ `LEDGER-HOT.md`: bytes come from the `downloader=` seam, not from the
    client. A run that reports zero bytes over three written files has lost the
    one number a person uses to sanity-check a fetch."""
    bench = Bench(tmp_path, names=episodes_up_to(3))

    results = api.fetch(bench.scan(), write=True)

    assert len(bench.downloads) == 3, u"downloads: %r" % (bench.downloads,)
    assert results.bytes_downloaded > 0, (
        u"three candidates were downloaded through the seam and the run reports "
        u"%r bytes" % (results.bytes_downloaded,))
    assert results.bytes_downloaded == sum(r.bytes_downloaded for r in results), (
        u"the run says %d bytes and the videos add up to %d"
        % (results.bytes_downloaded, sum(r.bytes_downloaded for r in results)))


def test_fetch_needs_no_identify_first(tmp_path):
    u"""⚠ `identify()` is OPTIONAL: `scan()` -> `fetch()` is a complete
    two-step, because the fetch resolves whatever is still unresolved from the
    same cache."""
    bench = Bench(tmp_path, names=episodes_up_to(1))

    results = api.fetch(bench.scan(), write=True)

    one, = results
    assert one.outcome == api.CONFIDENT, u"%s: %s" % (one.outcome, one.reason)
    assert one.jimaku_entry is not None, (
        u"a fetch without identify() never resolved the show")


# ---------------------------------------------------------------------------
# 6. ⛔ prints nothing
# ---------------------------------------------------------------------------

def test_nothing_in_the_library_api_prints_a_character(tmp_path, capsys):
    u"""⛔ Constraint 3: *returns structured results, PRINTS NOTHING.* The CLI
    renders; the library returns. A stray line here lands in the middle of
    somebody else's output -- and `hato --json` is a stream with a grammar, so
    one English sentence in it is a parse error."""
    bench = Bench(tmp_path, names=episodes_up_to(2))
    capsys.readouterr()                     # ⚠ drop anything the bench itself said

    plan = bench.scan()
    api.identify(plan)
    api.fetch(plan)
    api.fetch(plan, write=True)

    printed = capsys.readouterr()
    assert printed.out == u"", (
        u"the library API wrote %d character(s) to stdout, starting %r"
        % (len(printed.out), printed.out[:120]))
    assert printed.err == u"", (
        u"the library API wrote %d character(s) to stderr, starting %r"
        % (len(printed.err), printed.err[:120]))


# ---------------------------------------------------------------------------
# 7. ⚠ the two roads to one setting must agree
# ---------------------------------------------------------------------------

def test_settings_defaults_match_configs_documented_schema():
    u"""⚠ MEASURED, AND IT SHIPPED WRONG ONCE (`LEDGER-HOT.md`): `archives` was
    True in `Settings` and False in `config.py`'s schema, so a library caller
    got archives ON against the 2026-09-17 ruling and only the CLI road obeyed
    it. ⛔ The library API is now the other road, so the agreement is asserted.

    ⚠ `out` and `subs_dir` are the one allowed difference: the schema's *not
    set* is `""` and `Settings`'s is `None`.
    """
    import inspect
    signature = inspect.signature(pipeline.Settings.__init__)
    empty = inspect.Parameter.empty
    unset = {u"out": None, u"subs_dir": None}
    #: ⚠ SETTINGS THAT ARE NOT *RUN* SETTINGS. `pipeline.Settings` is what one
    #: run is told to do; `watch` decides whether a SEPARATE tray process
    #: exists between runs and changes nothing about any run. Forcing it into
    #: the signature would put a field in the library API that the pipeline
    #: has to ignore -- which is how a setting comes to look honoured.
    #: ⛔ Named here rather than skipped silently, so adding a second one is a
    #: decision somebody writes down.
    #: ⭐ `auto_update` (LAYER 11) too: whether hato updates ITSELF, nothing about a run
    #: -- written down here the day it joined the schema, which the full runner caught
    #: (ADVERSARY 2026-09-24, R1)
    not_a_run_setting = {u"watch", u"schedule", u"auto_update"}
    for name, (_kind, schema_default) in sorted(config_module.SCHEMA.items()):
        if name == u"folders":
            continue                        # required on both roads
        if name in not_a_run_setting:
            assert name not in signature.parameters, (
                u"%r is registered as not-a-run-setting and pipeline.Settings "
                u"now takes it -- delete it from that set or from the "
                u"signature, because one of the two is wrong" % name)
            continue
        assert name in signature.parameters, (
            u"config.py's schema has %r and pipeline.Settings has no such "
            u"parameter, so the setting cannot be reached from the library" % name)
        settings_default = signature.parameters[name].default
        assert settings_default is not empty, (
            u"pipeline.Settings requires %r while config.py gives it the default "
            u"%r" % (name, schema_default))
        want = unset.get(name, schema_default)
        assert settings_default == want, (
            u"%s defaults to %r in pipeline.Settings and %r in config.py's "
            u"schema -- two roads to one setting that disagree, which is how a "
            u"ruling ends up obeyed only by the CLI"
            % (name, settings_default, schema_default))


def test_every_settings_field_survives_a_round_trip(tmp_path):
    u"""⭐ `fetch()` rebuilds the plan's `Settings` with `dry_run` flipped, and
    it enumerates the fields from `__slots__` rather than from a list typed in
    `api.py`. If a field is ever added that the constructor does not accept,
    this fails loudly instead of the value being dropped."""
    bench = Bench(tmp_path, names=episodes_up_to(1))
    plan = bench.scan(lang=u"ja", candidates=2, allow_ai=True, recurse=False,
                      archives=True, skip_embedded=False, out=str(bench.out))

    copy = api._replace(plan.settings, dry_run=False)

    for name in pipeline.Settings.__slots__:
        if name == u"dry_run":
            continue
        assert getattr(copy, name) == getattr(plan.settings, name), (
            u"%s changed across a Settings round trip: %r -> %r"
            % (name, getattr(plan.settings, name), getattr(copy, name)))
    assert plan.settings.dry_run is True, (
        u"a plan's settings must default to writing nothing")
    assert copy.dry_run is False


def test_a_setting_given_to_scan_reaches_the_fetch(tmp_path):
    u"""⚠ A knob that is accepted and ignored is worse than one that is refused.
    `--out` is the visible one: the finished file must land in the mirrored
    directory and NOT beside the video."""
    bench = Bench(tmp_path, names=episodes_up_to(1))

    one, = api.fetch(bench.scan(out=str(bench.out)), write=True)

    assert one.outcome == api.CONFIDENT, u"%s: %s" % (one.outcome, one.reason)
    assert Path(one.output_path).parent == bench.out, (
        u"out= was given to scan() and the file landed at %s instead of under %s"
        % (one.output_path, bench.out))
    assert bench.names_in(bench.media) == [u"frieren S2 - 01.mkv"], (
        u"out= was given and something was written beside the video anyway: %r"
        % (bench.names_in(bench.media),))


# ---------------------------------------------------------------------------
# 8. ⭐ the real thing -- the whole facade over the real tsubasa
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_video(tmp_path_factory):
    u"""A real `.mkv` with a real English text track, and a real shifted SubRip
    for it. ⛔ Never inside the vault -- `_media.build` refuses it outright.

    🚨 `count=59` IS LOAD-BEARING AND IS NOT A TASTE. `TSUBASA_CACHE` is ONE
    temp root for the whole run and tsubasa's results DB keys a record on the
    SUBTITLE's content, so two suites whose download shares `_media`'s cue
    geometry write the same record and the second overwrites the first --
    turning a *"the store gained exactly one record"* check red inside ANOTHER
    suite's file (`07-test-plan.md`). Taken: port 75, write 61, pipeline 67,
    and 59 here.
    """
    return _media.build(tmp_path_factory.mktemp("api"), stem=u"frieren S2 - 01",
                        track_language=u"eng", count=59)


def test_the_whole_facade_against_the_real_tsubasa(real_video, tmp_path):
    u"""🚨 THE CHECK THE WHOLE MODULE EXISTS FOR.

    Everything above believes a stub about what a verdict is. This runs the real
    client over real captures, the real track reader over a real container, and
    the real `tsubasa.sync()` over a real video -- through `scan()` ->
    `identify()` -> `fetch(write=True)`, the exact three calls
    `05-interface.md` publishes.

    ⚠ The candidate's NAME is jimaku's (an `.ass`) while its BYTES are the
    fixture's SubRip: Whitelist 2 forbids recording a subtitle body. tsubasa
    reads the content, not the extension, and writes it back as it came.
    """
    bench = Bench(tmp_path, names=[])
    import shutil
    shutil.copyfile(str(real_video.video), str(bench.media / real_video.video.name))
    bench.use_real_engine = True
    bench.body = _media.srt(real_video.starts, shift=real_video.shift).encode("utf-8")

    plan = api.identify(bench.scan())
    results = api.fetch(plan, write=True)

    one, = results
    assert one.outcome == api.CONFIDENT, u"%s: %s" % (one.outcome, one.reason)
    assert one.wrote is True
    assert one.tsubasa.verdict_word in (u"locked", u"strong", u"fair", u"uncertain"), (
        u"tsubasa's verdict word came back %r, which is not one of its four"
        % (one.tsubasa.verdict_word,))
    assert one.tsubasa.offset == pytest.approx(-real_video.shift, abs=0.5), (
        u"the download is %+.2fs out and tsubasa measured %r"
        % (real_video.shift, one.tsubasa.offset))
    written = Path(one.output_path)
    assert written.parent == bench.media
    assert written.name == u"frieren S2 - 01.ja.ass", (
        u"the finished file is named %r" % written.name)
    assert bench.names_in(bench.media) == [u"frieren S2 - 01.ja.ass",
                                           u"frieren S2 - 01.mkv"], (
        u"the media folder holds %r -- it must see exactly one filesystem "
        u"operation per success" % (bench.names_in(bench.media),))
    body = io.open(str(written), encoding="utf-8").read()
    assert u"行 1" in body, (
        u"the written subtitle does not hold the fixture's Japanese text; first "
        u"120 characters: %r" % body[:120])
