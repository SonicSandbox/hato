# -*- coding: utf-8 -*-
u"""
hato/pipeline.py -- the fetch loop (RUNBOOK 4b), against the REAL client driven
off the REAL captures in `tests/fixtures/api/`.

⛔ ZERO NETWORK. Every metered call below goes through `requests` itself and is
answered from a response `hato doctor --capture` recorded; the socket layer is
armed to refuse anything else (`conftest.py`). So the call COUNTS asserted here
are the counts a real run makes -- which is the only way *"a warm re-run costs
zero metered calls"* means anything.

⚠ THE ONE THING THAT CANNOT COME FROM A CAPTURE IS THE SUBTITLE'S BYTES.
Whitelist 2 forbids mirroring subtitle content, so the download fixtures are
metadata only (`07-test-plan.md`) and the `downloader=` seam supplies bytes. The
metered half -- search, files, the URLs, the counts -- is the real thing.

⭐ THE LAST SECTION RUNS THE WHOLE LOOP WITH THE REAL tsubasa, on a video ffmpeg
really built, twice. Everything above it believes a stub about what a verdict is;
that section does not.

⛔ WHAT THIS SUITE STRUCTURALLY CANNOT COVER: whether jimaku still answers this
way (that is `hato doctor` and the `live` suite), and whether the top-ranked
candidate is actually the right subtitle -- only the timing verdict knows.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import tsubasa

from hato import archives, cache as cache_module, client as client_module, config, \
    credentials, formats, keep, pipeline, port, present, resolution, state
from hato import report as report_module
from hato.cache import Cache

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _media                                                      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
#: The recorded entry. ⛔ Never a hardcoded 120: derive from the file itself.
ENTRY = 11446
FILES = json.loads((FIXTURES / "api" / "entries_11446_files.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# the laboratory
# ---------------------------------------------------------------------------

class Track(object):
    def __init__(self, lang=u"en", text=True, bitmap=False, codec=u"S_TEXT/UTF8", index=2):
        self.lang, self.text, self.bitmap = lang, text, bitmap
        self.codec, self.index, self.forced = codec, index, False


class Answer(object):
    u"""`tsubasa.EmbeddedSubtitles`, and ⛔ `.tracks` raises when `ok` is False
    exactly as the real one does."""

    def __init__(self, ok=True, reason=u"", tracks=None):
        self.ok, self.reason = ok, reason
        self._tracks = (Track(),) if tracks is None else tuple(tracks)

    @property
    def tracks(self):
        if not self.ok:
            raise ValueError(u"could not be read: %s" % self.reason)
        return self._tracks


class TakenOut(object):
    u"""`tsubasa.ExtractedSubtitle`, for the checks that decide what a track comes out
    as without a container (RUNBOOK 14c). ⭐ It WRITES when asked, as tsubasa does --
    `<stem>.<lang>.<ext>` in `out_dir`, else beside the video, temp-plus-rename, and
    ⛔ never over a file that is there -- so the present-check after it is the real
    one. `ext` defaults to the codec's own family (`.ass` stays `.ass`)."""

    def __init__(self, video, track, ok=True, reason=u"", ext=None, codec=None,
                 cues=412, lang=u"ja", fails_to_write=u"", writes_as=None, notes=()):
        self.video = video
        self.ok = ok
        self.reason = u"" if ok else reason
        self.index = getattr(track, "index", track)
        self.codec = codec or getattr(track, "codec", u"") or u""
        self.ext = (ext or formats.of_codec(self.codec) or u"ass") if ok else u""
        self.cues = cues if ok else 0
        self.lang = lang
        self.data = u"taken out of %s\n" % os.path.basename(video) if ok else u""
        self.data = self.data.encode("utf-8")
        self.output_path = None
        self.write_failed = False
        self.notes = tuple(notes)
        self._fails = fails_to_write
        #: ⭐ 14z (A-5) -- the name tsubasa wrote it under when it had to change it
        self._as = writes_as

    def write(self, out_dir):
        stem = os.path.splitext(os.path.basename(self.video))[0]
        folder = out_dir or os.path.dirname(self.video)
        target = os.path.join(folder, self._as or u"%s.%s.%s" % (stem, self.lang, self.ext))
        if self._fails or os.path.lexists(target):
            self.write_failed = True
            self.reason = self._fails or (u"%s is already there -- nothing was written "
                                          u"over it" % os.path.basename(target))
            return
        os.makedirs(folder, exist_ok=True)
        # ⚠ 14z (A-1) -- ONE temporary name, `x` mode: never `mkstemp`, which in a folder
        # that denies adding a file tries 2^31 names -- a witness that HANGS instead of
        # failing, under the very mutant it exists to catch.
        temporary = os.path.join(folder, u".taken-%d" % os.getpid())
        try:
            with open(temporary, "xb") as fh:
                fh.write(self.data)
        except OSError as exc:
            self.write_failed = True
            self.reason = u"%s could not be written: %s" % (os.path.basename(target), exc)
            return
        os.replace(temporary, target)
        self.output_path = target


class Blind(object):
    u"""A client that finds nothing.

    ⚠ THE ONE SHAPE NO CAPTURE HOLDS. Every recorded search resolves to
    something (`query=frieren` alone returns 15 entries), so *"jimaku has no
    entry for this show at all"* -- the hard negative, 30 days -- cannot be
    driven from the fixtures. Everything else about the run is the real thing.
    """

    def __init__(self, inner):
        self._inner, self.metered = inner, 0

    def search(self, query=None, **kwargs):
        self.metered += 1
        return []

    def files(self, entry_id):
        return self._inner.files(entry_id)

    def download(self, item):
        return self._inner.download(item)


def videos_named(*names):
    return list(names)


def episodes_up_to(count, pattern=u"frieren S2 - %02d.mkv"):
    return [pattern % n for n in range(1, count + 1)]


class Lab(object):
    u"""One run's world: a folder of stub videos, a real client over recorded
    responses, a real state DB and resolution cache in a temp dir, and the three
    seams (`downloader`, `engine`, `reader`).

    ⚠ EVERY STUB VIDEO CARRIES DISTINCT BYTES. The state DB is keyed on the
    head+tail hash, so ten zero-byte files would be ONE video to it -- one
    refusal would blacklist the whole folder and every check here would pass
    while measuring nothing.
    """

    def __init__(self, tmp_path, names=None, stems=None, blind=False):
        self.root = Path(tmp_path)
        self.media = self.root / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        for name in (episodes_up_to(10) if names is None else names):
            (self.media / name).write_bytes(b"\x1aE\xdf\xa3" + name.encode("utf-8"))
        self.subs = self.root / "subs"
        self.out = self.root / "out"
        self.now = [datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)]
        self.db = state.StateDB(self.root / "state.db", now=lambda: self.now[0])
        self.resolutions = resolution.ResolutionCache(self.root / "resolution.db")
        self.cache = Cache(self.root / "cache")
        self.session = client_module.RecordedSession(FIXTURES, stems=stems)
        self.real = client_module.JimakuClient(
            credentials.Key(u"recorded-responses-need-no-key", u"the suite"),
            self.session, sleep=lambda seconds: None)
        self.client = Blind(self.real) if blind else self.real
        #: every jimaku filename the loop asked for the bytes of
        self.downloads = []
        #: video basename -> Answer. The default is an ENGLISH text track, which
        #: is the shape hato fetches for.
        self.tracks = {}
        #: candidate name -> `port.stub_engine` keyword arguments.
        self.decide = lambda name: {}
        self.use_real_engine = False
        #: ⭐ 14c -- video basename -> how its track comes out (`TakenOut`'s
        #: keywords, plus `refuse`: {track index: reason}); and every extraction
        #: asked for, as (name, track index, write, out_dir)
        self.takes = {}
        self.extracted = []

    def second_root(self, folder, *names):
        u"""⭐ A SECOND SCANNED ROOT, which `Lab` could not express until
        2026-09-17 -- and *"one root, one folder, unique stems"* is exactly the
        fixture shape that let two videos targeting ONE output file survive every
        check in this file. -> the folder.

        ⚠ THE BYTES CARRY THE FOLDER NAME as well as the file's. The state DB is
        keyed on the head+tail hash, so `A/Show - 01.mkv` and `B/Show - 01.mkv`
        written with identical bytes would be ONE video to it -- and a check about
        two videos colliding would be measuring one.
        """
        where = self.root / folder
        where.mkdir(parents=True, exist_ok=True)
        for name in names:
            (where / name).write_bytes(
                b"\x1aE\xdf\xa3" + (folder + u"/" + name).encode("utf-8"))
        return where

    # -- the seams ---------------------------------------------------------

    def reader(self, video, **kwargs):
        return self.tracks.get(os.path.basename(video), Answer())

    def download(self, item):
        self.downloads.append(item["name"])
        return (u"1\n00:00:01,000 --> 00:00:02,000\n%s\n" % item["name"]).encode("utf-8")

    def engine(self, pairs, **kwargs):
        (video, subtitle), = list(pairs)
        return port.stub_engine(**self.decide(os.path.basename(subtitle)))(pairs, **kwargs)

    def extractor(self, video, track, write=False, out_dir=None):
        name = os.path.basename(video)
        index = getattr(track, "index", track)
        self.extracted.append((name, index, write, out_dir))
        how = dict(self.takes.get(name, {}))
        refused = how.pop("refuse", {})
        if index in refused:
            how.update(ok=False, reason=refused[index])
        got = TakenOut(video, track, **how)
        if write and got.ok:
            got.write(out_dir)
        return got

    # -- driving -----------------------------------------------------------

    def settings(self, **overrides):
        # ⚠ `format_fallback=True`, SAID OUT LOUD. Every check here but section 9a's
        # is about something else -- the cap, a film, an archive -- and was written
        # when every format was tried. The product default is OFF (RUNBOOK 9a), so
        # these would otherwise be measuring the format rule by accident: three
        # went red the moment it landed. 9a's own checks pass it explicitly.
        values = dict(folders=[self.media], lang=u"ja", subs_dir=self.subs,
                      candidates=3, format_fallback=True)
        values.update(overrides)
        return pipeline.Settings(**values)

    def run(self, **overrides):
        before = self.metered
        self.spent = None
        # ⚠ `on_progress` is a `run()` argument, not a SETTING -- passed through
        # to `Settings(**values)` it is a TypeError about an unexpected keyword.
        on_progress = overrides.pop("on_progress", None)
        report = pipeline.run(
            self.settings(**overrides), on_progress=on_progress,
            client=self.client, db=self.db,
            resolutions=self.resolutions, cache=self.cache,
            downloader=self.download,
            engine=None if self.use_real_engine else self.engine,
            reader=None if self.use_real_engine else self.reader,
            extractor=None if self.use_real_engine else self.extractor)
        self.spent = self.metered - before
        return report

    # -- reading it back ---------------------------------------------------

    @property
    def metered(self):
        return self.client.metered

    def hash_of(self, name):
        return cache_module.video_hash(self.media / name)

    def names_in(self, folder):
        folder = Path(folder)
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def kept(self):
        subs = Path(self.subs)
        return sorted(p.name for p in subs.rglob("*") if p.is_file())

    def rows(self):
        return self.db.stats()["rows"]

    def by_name(self, report):
        return dict((r.name, r) for r in report.results)

    def forget_videos(self):
        u"""Remove every subtitle beside the videos -- the user deleted them."""
        for p in self.media.iterdir():
            if p.suffix.lower() in (u".ass", u".srt"):
                p.unlink()


def only(report, outcome):
    return [r for r in report.results if r.outcome == outcome]


# ---------------------------------------------------------------------------
# 1. ⭐ the four outcomes
# ---------------------------------------------------------------------------

def test_a_confident_run_writes_keeps_and_records(tmp_path):
    u"""The happy path, end to end through the stub engine: every video gets a
    file, every file's original is kept, and every row is in the DB."""
    lab = Lab(tmp_path)
    report = lab.run()

    confident = only(report, pipeline.CONFIDENT)
    assert len(confident) == 10
    assert all(r.wrote for r in confident)
    assert all(Path(r.output_path).is_file() for r in confident)
    assert all(Path(r.kept_path).is_file() for r in confident)
    assert lab.rows()[pipeline.CONFIDENT] == 10
    assert report.api_calls == 2          # search + files, ⛔ and no more
    assert len(lab.downloads) == 10


def test_a_refusal_states_what_was_measured_and_what_would_change_it(tmp_path):
    u"""`03-permissions.md` §the hand-back path: what was measured, why it fell
    short, what would change it. ⛔ *"It failed"* is not acceptable output."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: dict(outcome=port.REFUSED,
                                   reason=u"31% match -- the timing does not hold",
                                   match_rate=0.31)
    report = lab.run(candidates=2)

    refused = only(report, pipeline.REFUSED)
    assert len(refused) == 2
    assert u"31%" in refused[0].reason
    assert u"--candidates" in refused[0].reason or u"hato sync" in refused[0].reason
    assert refused[0].retry_after is not None
    assert len(refused[0].attempts) == 2
    assert lab.rows()[pipeline.REFUSED] == 4        # 2 videos x 2 candidates


def test_a_refusal_is_recorded_with_its_file_and_how_close_it_came(tmp_path):
    """⭐ RUNBOOK 8b. What lets a refused candidate be OFFERED again after this run
    is forgotten: the content hash finds the downloaded file in the working cache,
    and the rate says how close it came. ⚠ `subtitle_hash` had been passed as None
    since 1b, so tomorrow's run knew a refusal happened and not what it was."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, match_rate=0.31,
                                   reason=u"31% match -- the timing does not hold")
    lab.run(candidates=2)

    rows = lab.db.candidates(lab.hash_of(u"frieren S2 - 01.mkv"), u"ja")
    assert len(rows) == 2
    for row in rows:
        assert row.match_rate == pytest.approx(0.31)
        assert row.subtitle_hash and len(row.subtitle_hash) == 64
        found = lab.cache.find(row.subtitle_hash, keep.download_name(row.jimaku_filename, u"ja"))
        assert found is not None and found.is_file(), (
            u"%s was recorded, but the file it names is not where the cache would put "
            u"it -- a person could not be offered it again" % row.jimaku_filename)


def test_an_error_names_the_video_and_writes_nothing(tmp_path):
    u"""⛔ An unreadable container is an ERROR **before any download** -- tsubasa
    reads the same container, so a download would only reach the same ERROR
    afterwards, and the network is metered."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.tracks[u"frieren S2 - 01.mkv"] = Answer(
        ok=False, reason=u"reading it needs ffmpeg, which was not found on PATH")
    report = lab.run()

    bad = lab.by_name(report)[u"frieren S2 - 01.mkv"]
    assert bad.outcome == pipeline.ERROR
    assert u"ffmpeg" in bad.reason
    assert u"nothing was downloaded" in bad.reason
    assert u"frieren S2 - 01" not in u" ".join(lab.downloads)
    assert lab.rows()[pipeline.ERROR] == 0          # ⛔ and no candidate to record it against


def test_not_found_is_never_an_error_and_carries_a_retry_date(tmp_path):
    u"""⭐ *"jimaku has no episode 11"* is a normal, expected, recurring state
    that resolves itself when someone uploads one. 🚨 `subsync` was bitten twice
    by exactly this class of confusion."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 24.mkv"])
    report = lab.run()

    missing, = report.results
    assert missing.outcome == pipeline.NOT_FOUND
    assert u"episode 24" in missing.reason
    assert missing.retry_after is not None
    # ⚠ Case-folded deliberately: the sentence was `-- will retry after` until the
    # run-on fix of 2026-09-17 made it its own sentence, `Will retry after`. What
    # this check is FOR is that the date is stated, not where the capital sits.
    assert u"retry after" in missing.reason.lower()
    assert lab.rows()[pipeline.NOT_FOUND] == 1
    assert lab.rows()[pipeline.ERROR] == 0          # 🚨 never conflated with a fault
    assert lab.downloads == []


def test_confident_with_no_file_on_disk_is_an_ERROR_not_a_success(tmp_path):
    u"""⛔ CONFIDENT IS NOT WRITTEN. tsubasa really returns this: the
    destination exists and this run did not account for it, so it aligned and
    wrote nothing. A user told a subtitle was written stops looking for it.

    🚨 THIS CHECK WAS PINNING THE DEFECT ITS OWN NAME DESCRIBES, until 2026-09-17.
    It said ERROR in the name and asserted REFUSED in the body, with a comment
    excusing it -- so the fetch loop minting a failed WRITE as a timing REFUSAL
    was green, in the one check written to catch it. The `attempts[0]` assertions
    below were all correct and all beside the point: what a person is TOLD is the
    video's outcome, and *"refused, none held (100% match)"* is a sentence that
    contradicts itself.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(writes=False)
    report = lab.run(candidates=1)

    one, = report.results
    assert one.outcome == pipeline.ERROR         # ⛔ NOT REFUSED. The pair aligned
    assert u"NOT WRITTEN" in one.reason          # and tsubasa's words name the fix
    assert one.attempts[0].outcome == pipeline.ERROR
    assert u"NOT WRITTEN" in one.attempts[0].reason
    assert one.attempts[0].tsubasa.write_failed is True
    assert one.attempts[0].tsubasa.outcome == port.CONFIDENT     # ⚠ tsubasa still says so
    assert one.retry_after is None               # ⛔ and it is not silenced for a day
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]


def test_a_blocked_write_is_never_recorded_as_a_timing_negative(tmp_path):
    u"""🚨 THE HALF OF THE DEFECT A PERSON ACTUALLY FEELS. A failed write was
    reported as *"all candidates refused by timing"* AND recorded as a soft
    negative under that reason -- so the next run skipped the video with a false
    reason and it stayed quiet for a day **even once the disk was fixed**.

    ⚠ The fixture varies the one thing the old one held constant: it runs TWICE,
    with the obstruction removed in between. One run could never show that the
    video had been silenced.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(writes=False)
    first = lab.run(candidates=1)

    assert first.results[0].outcome == pipeline.ERROR
    assert lab.rows()[pipeline.NOT_FOUND] == 0      # ⛔ no negative of any kind
    assert lab.rows()[pipeline.REFUSED] == 0        # ⛔ and it was never a refusal
    assert lab.rows()[pipeline.ERROR] == 1          # ⭐ recorded as what it was
    lab.downloads = []

    lab.decide = lambda name: {}                    # the disk is fixed, same day
    second = lab.run(candidates=1)

    assert second.results[0].outcome == pipeline.CONFIDENT, second.results[0].reason
    assert len(lab.downloads) == 1                  # ⛔ never skipped as "no source"


def test_a_blocked_write_does_not_burn_the_other_candidates(tmp_path):
    u"""⛔ The destination is the SAME destination for every candidate, so
    escalating cannot help -- it only spends bandwidth to reach the identical
    ERROR, and (measured) ends in a refusal sentence quoting a 100% match."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(writes=False)

    report = lab.run(candidates=5)

    assert len(lab.downloads) == 1                  # ⛔ one, not five
    assert len(report.results[0].attempts) == 1
    assert report.results[0].outcome == pipeline.ERROR


def test_every_video_ends_as_exactly_one_result(tmp_path):
    u"""⛔ *"Every video resolves to exactly one outcome. There is no fifth, and
    no silent success."*"""
    lab = Lab(tmp_path, names=episodes_up_to(12) + [u"Kimi no Na wa.mkv"])
    report = lab.run()
    assert len(report.results) == 13
    assert len(set(r.video for r in report.results)) == 13
    assert all(r.outcome in (pipeline.CONFIDENT, pipeline.REFUSED, pipeline.ERROR,
                             pipeline.NOT_FOUND, pipeline.SKIPPED, pipeline.PLANNED)
               for r in report.results)
    assert all(r.reason.strip() or r.outcome == pipeline.CONFIDENT for r in report.results)


# ---------------------------------------------------------------------------
# 2. escalation, and the cap
# ---------------------------------------------------------------------------

def test_a_refused_candidate_escalates_to_the_next_one(tmp_path):
    u"""⚠ Rank, then escalate. Ranking picks who goes first; the timing verdict
    decides who wins. Downloads are unmetered, so escalation costs bandwidth."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: (dict(outcome=port.REFUSED, reason=u"18% match",
                                    match_rate=0.18) if u"NanakoRaws" in name else {})
    report = lab.run()

    one, = report.results
    assert one.outcome == pipeline.CONFIDENT
    assert len(lab.downloads) == 2
    assert u"NanakoRaws" in lab.downloads[0]        # ⚠ ranked first, and refused
    assert u"NanakoRaws" not in one.jimaku_filename
    assert [a.outcome for a in one.attempts] == [pipeline.REFUSED, pipeline.CONFIDENT]


def test_the_cap_is_what_stops_the_escalation(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"nothing holds",
                                   match_rate=0.2)
    report = lab.run(candidates=2)

    assert len(lab.downloads) == 2
    assert report.results[0].candidates_offered > 2       # ⚠ more were OFFERED
    assert len(report.results[0].attempts) == 2


def test_a_low_confidence_identification_raises_the_cap(tmp_path):
    u"""⭐ 06 §1 says a LOW CONFIDENCE identification *"raises the candidate
    cap"* and never said by how much. Ruled for 4b: `candidates + 2`.

    ⚠ The low confidence is REAL here, not injected: `Kimi no Na wa S05` asks
    for season 5 and jimaku's entry has no season, so `hato/resolution.py`
    halves the score and says so.
    """
    lab = Lab(tmp_path, names=[u"Kimi no Na wa S05 - 01.mkv"])
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"nope", match_rate=0.1)
    report = lab.run(candidates=1)

    assert report.shows[0].resolved.low_confidence is True
    assert len(lab.downloads) == 1 + pipeline.LOW_CONFIDENCE_EXTRA


def test_a_movie_entry_offers_every_subtitle_to_the_one_film(tmp_path):
    u"""06 §3, RULED: ⛔ skip episode matching entirely. ⚠ Every SUBTITLE: the
    entry's `.sup.7z` is not one (ADVERSARY 2026-09-23 #10)."""
    lab = Lab(tmp_path, names=[u"Kimi no Na wa.mkv"])
    report = lab.run(candidates=1)

    listed = json.loads((FIXTURES / "api" / "entries_movie_flag.json").read_text(encoding="utf-8"))
    packs = [f for f in listed if archives.is_archive(f["name"])]
    assert packs, u"the recorded movie entry is expected to carry an archive"
    assert report.shows[0].resolved.movie is True
    assert report.results[0].candidates_offered == len(listed) - len(packs)
    assert not [n for n in lab.downloads if archives.is_archive(n)], lab.downloads


# ---------------------------------------------------------------------------
# 3. ⛔ a refusal is never downloaded twice
# ---------------------------------------------------------------------------

def test_a_refused_candidate_is_never_downloaded_again(tmp_path):
    u"""⛔ *Never re-download the same file.* It failed on its timing, and timing
    is deterministic -- a second attempt costs bandwidth to reach the identical
    verdict. The identity is `(entry, filename, size, last_modified)` from the
    LIST, so the check costs no request at all.

    ⚠ The clock is moved on two days so the soft negative the first run recorded
    has expired -- otherwise the second run would skip before it ever got here,
    which is the OTHER protection and is checked separately below.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1)
    lab.run(candidates=2)
    first = list(lab.downloads)
    assert len(first) == 2

    lab.now[0] += timedelta(days=2)
    lab.downloads = []
    report = lab.run(candidates=2)

    assert len(lab.downloads) == 2
    assert not set(lab.downloads) & set(first)          # ⛔ two NEW candidates
    assert report.results[0].outcome == pipeline.REFUSED


def test_when_every_candidate_has_been_refused_nothing_is_downloaded_at_all(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1)
    offered = lab.run(candidates=99).results[0].candidates_offered
    assert len(lab.downloads) == offered

    lab.now[0] += timedelta(days=2)
    lab.downloads = []
    report = lab.run(candidates=99)

    assert lab.downloads == []
    assert report.results[0].outcome == pipeline.REFUSED
    assert u"already been fetched and refused" in report.results[0].reason


def test_a_re_upload_is_a_new_candidate(tmp_path, monkeypatch):
    u"""⚠ The identity carries the size and `last_modified`, so a file jimaku
    replaced under the same name is tried again rather than written off."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1)
    lab.run(candidates=1)
    tried = lab.downloads[0]

    reuploaded = [dict(f, size=(f["size"] or 0) + 1) if f["name"] == tried else f
                  for f in FILES]
    monkeypatch.setattr(lab.client, "files", lambda entry_id: reuploaded)
    lab.now[0] += timedelta(days=2)
    lab.downloads = []
    lab.run(candidates=1)

    assert lab.downloads == [tried]


# ---------------------------------------------------------------------------
# 4. 🚨 the quiet re-run
# ---------------------------------------------------------------------------

def test_a_warm_re_run_costs_zero_metered_calls(tmp_path):
    u"""🚨 `02-data-model.md`'s cost model: *N stats + one DB read. Zero network
    calls.* A folder whose subtitles are all present makes no request at all --
    identification is never even reached."""
    lab = Lab(tmp_path)
    lab.run()
    assert lab.spent == 2

    report = lab.run()

    assert lab.spent == 0
    assert report.api_calls == 0
    assert len(only(report, pipeline.SKIPPED)) == 10
    assert set(r.skip for r in report.results) == {pipeline.PRESENT}
    assert report.shows[0].resolved is None            # ⛔ never identified


def test_a_warm_re_run_opens_no_container_either(tmp_path):
    u"""⭐ The loop was reordered so the cheapest check runs first. A reader that
    is never called is what makes that true."""
    lab = Lab(tmp_path)
    lab.run()
    opened = []
    lab.reader = lambda video, **kwargs: opened.append(video) or Answer()

    lab.run()

    assert opened == []


def test_the_present_check_is_not_overridden_by_force(tmp_path):
    u"""⛔ `--force` ignores the state DB. The filesystem is canonical for *does
    a subtitle exist*, and a present file is the disk, not the DB."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.run()
    lab.downloads = []

    report = lab.run(force=True)

    assert lab.downloads == []
    assert set(r.skip for r in report.results) == {pipeline.PRESENT}


def test_under_out_the_present_check_looks_in_the_mirrored_directory(tmp_path):
    u"""🚨 THE DEFECT MEASURED AT 4a, CLOSED IN THE LOOP. With `--out` set the
    earlier output is in the MIRRORED directory; looking beside the video would
    make hato re-fetch every episode on every run, and tsubasa would then refuse
    the write for ever (CONFIDENT, `write_failed`, no file)."""
    lab = Lab(tmp_path, names=episodes_up_to(3))
    first = lab.run(out=lab.out)
    assert len(only(first, pipeline.CONFIDENT)) == 3
    assert all(Path(r.output_path).parent == lab.out for r in first.results)
    assert lab.names_in(lab.media) == sorted(episodes_up_to(3))    # ⛔ nothing beside them
    lab.downloads = []

    second = lab.run(out=lab.out)

    assert lab.spent == 0
    assert lab.downloads == []
    assert set(r.skip for r in second.results) == {pipeline.PRESENT}


# ---------------------------------------------------------------------------
# 5. ⭐ the deleted subtitle, re-synced with zero network
# ---------------------------------------------------------------------------

def test_a_deleted_subtitle_is_re_synced_from_its_kept_original(tmp_path):
    u"""`02-data-model.md` §Canonicity: *DB says synced, file is gone -> re-sync
    from the kept original if it is still in `subs_dir` -- zero network.*
    06 §6: *the user deleted a subtitle on purpose -- it comes back next run.
    Documented, not a bug.*"""
    lab = Lab(tmp_path, names=episodes_up_to(3))
    lab.run()
    kept_before = lab.kept()
    lab.forget_videos()
    lab.downloads = []

    report = lab.run()

    assert lab.spent == 0                       # ⛔ ZERO metered calls
    assert lab.downloads == []                  # ⛔ and nothing downloaded
    assert len(only(report, pipeline.CONFIDENT)) == 3
    assert all(Path(r.output_path).is_file() for r in report.results)
    assert lab.kept() == kept_before            # ⛔ and nothing was kept twice


def test_a_re_sync_tells_the_present_check_its_file_landed(tmp_path, monkeypatch):
    u"""⚠ THE TWO WRITE PATHS MUST AGREE. `_candidates` calls `look.forget()` on
    the folder it wrote into, so a LATER video decided against the same folder
    cannot be answered from a listing taken before the write. `_resync` writes
    into exactly the same folder and did not.

    ⭐ It matters across SHOWS, and under `--out` a whole library can mirror into
    one directory -- the case finding 2 is about. The asymmetry is the defect: one
    of two identical writes telling the cache and the other not is a bug waiting
    for the day the second one is the one that matters, and it is not the kind of
    thing anyone re-derives later.
    """
    forgotten = []
    real = present.Presence.forget
    monkeypatch.setattr(present.Presence, "forget",
                        lambda self, folder: forgotten.append(str(folder)) or real(self, folder))
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.run()
    lab.forget_videos()
    lab.downloads, forgotten[:] = [], []

    report = lab.run()                      # both re-synced from their kept originals

    assert len(only(report, pipeline.CONFIDENT)) == 2
    assert lab.downloads == []              # ⛔ really the re-sync path, not a re-fetch
    assert [os.path.normcase(f) for f in forgotten] == \
        [os.path.normcase(str(lab.media))] * 2


def test_without_a_kept_original_a_deleted_subtitle_is_fetched_again(tmp_path):
    u"""⚠ The other half of the canonicity row -- and the reason kept originals
    are never deleted."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.run()
    lab.forget_videos()
    for kept in Path(lab.subs).rglob("*.srt"):
        kept.unlink()
    for kept in Path(lab.subs).rglob("*.ass"):
        kept.unlink()
    lab.downloads = []

    report = lab.run()

    assert len(lab.downloads) == 1
    assert report.results[0].outcome == pipeline.CONFIDENT


# ---------------------------------------------------------------------------
# 6. ⭐ the skips that cost nothing
# ---------------------------------------------------------------------------

def test_a_video_with_no_subtitle_track_makes_no_request_and_records_nothing(tmp_path):
    u"""⭐ RULED 2026-09-17. ⛔ Never a refusal: a refusal row would blacklist a
    good subtitle for ever, including after tsubasa can sync from audio."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.tracks[u"frieren S2 - 01.mkv"] = Answer(tracks=[])

    report = lab.run()

    assert report.results[0].outcome == pipeline.SKIPPED
    assert report.results[0].skip == pipeline.NO_TRACK
    assert u"can't sync yet" in report.results[0].reason
    assert lab.spent == 0
    assert lab.downloads == []
    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}


def test_an_embedded_japanese_text_track_is_a_skip(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.tracks[u"frieren S2 - 01.mkv"] = Answer(tracks=[Track(lang=u"ja")])

    report = lab.run()

    assert report.results[0].skip == pipeline.EMBEDDED
    assert lab.spent == 0


def test_the_toggle_fetches_even_for_a_video_that_already_has_a_japanese_track(tmp_path):
    u"""⭐ RULED 2026-09-17 (Sonic): *"a toggle in settings, that if they have it
    toggled, it will find another one even if there already is a japanese track
    on it"*. `skip_embedded=False`.

    ⚠ Why anyone would: an embedded track can be a poor one -- an SDH rip, a
    broadcast burn-in, a machine translation -- and a fansub `.ass` may be the
    one wanted. ⭐ And it is not wasteful: that embedded track is exactly what
    `sync()` times the download against, so the reference is the same rip.

    ⛔ The DEFAULT must stay the free skip (`01-scope.md` launch 16), which is
    why both halves are asserted here rather than only the new one.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.tracks[u"frieren S2 - 01.mkv"] = Answer(tracks=[Track(lang=u"ja")])

    default = lab.run()
    assert default.results[0].skip == pipeline.EMBEDDED
    assert lab.spent == 0, u"the default must still cost nothing"

    toggled = lab.run(skip_embedded=False)

    one = toggled.results[0]
    assert one.skip != pipeline.EMBEDDED, u"the toggle did not reach the read rule"
    assert one.outcome == pipeline.CONFIDENT
    assert one.output_path, u"CONFIDENT is not WRITTEN -- it must carry the file"
    assert lab.spent > 0, u"it has to identify the show to fetch anything"


def test_a_blacklisted_video_is_skipped_before_the_container_is_opened(tmp_path):
    u"""`02-data-model.md` §Question 3: it may only ever PREVENT work, and it is
    checked before the container is opened -- so it costs one hash and nothing
    else."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.db.blacklist_add(lab.hash_of(u"frieren S2 - 01.mkv"),
                         note=u"a recap, it will never have subs")
    opened = []
    real_reader = lab.reader
    lab.reader = lambda video, **kwargs: opened.append(os.path.basename(video)) or real_reader(video)

    report = lab.run()

    black = lab.by_name(report)[u"frieren S2 - 01.mkv"]
    assert black.skip == pipeline.BLACKLISTED
    assert u"a recap" in black.reason
    assert u"frieren S2 - 01.mkv" not in opened     # ⛔ never opened
    assert u"frieren S2 - 02.mkv" in opened


def test_force_does_not_override_the_blacklist(tmp_path):
    u"""⚠ `--force` overrules HATO's judgement -- a refusal, a negative it
    recorded itself. A blacklist is the PERSON's instruction, and overriding
    that is a different thing entirely. `hato blacklist --remove` is the way
    back, never a flag."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.db.blacklist_add(lab.hash_of(u"frieren S2 - 01.mkv"))

    report = lab.run(force=True)

    assert report.results[0].skip == pipeline.BLACKLISTED
    assert lab.downloads == []
    assert lab.spent == 0


def test_removing_the_blacklist_row_puts_the_video_back(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.db.blacklist_add(lab.hash_of(u"frieren S2 - 01.mkv"))
    lab.run()
    assert lab.db.blacklist_remove(lab.hash_of(u"frieren S2 - 01.mkv")) is True

    report = lab.run()

    assert report.results[0].outcome == pipeline.CONFIDENT


# ---------------------------------------------------------------------------
# 7. ⚠ BOTH negatives are consulted -- hard AND soft
# ---------------------------------------------------------------------------

def test_a_soft_negative_stops_the_entry_being_re_listed_the_same_day(tmp_path):
    u"""⚠ Checking only the hard negative re-lists the entry's files every run
    for an episode jimaku does not have yet -- the exact cost the negative cache
    exists to stop."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 11.mkv"])
    first = lab.run()
    assert first.results[0].outcome == pipeline.NOT_FOUND
    assert lab.spent == 2

    report = lab.run()

    assert lab.spent == 0
    assert report.results[0].skip == pipeline.NEGATIVE
    assert report.results[0].retry_after is not None


def test_the_soft_negative_expires_after_a_day(tmp_path):
    u"""⭐ AMENDED 2026-09-17 (Sonic), 7 days -> 1: *a just-aired episode is
    exactly the case to keep checking.*"""
    lab = Lab(tmp_path, names=[u"frieren S2 - 11.mkv"])
    lab.run()
    lab.now[0] += timedelta(days=1, minutes=1)

    lab.run()

    assert lab.spent == 1          # the resolution is cached for ever: files only


def test_a_hard_negative_is_recorded_when_no_entry_matches_at_all(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1), blind=True)
    first = lab.run()

    assert first.results[0].outcome == pipeline.NOT_FOUND
    assert u"no jimaku entry matched" in first.results[0].reason
    assert lab.downloads == []

    report = lab.run()
    assert lab.spent == 0                                  # ⛔ not asked again
    assert report.results[0].skip == pipeline.NEGATIVE
    assert lab.rows()[pipeline.NOT_FOUND] == 1             # ⛔ and not recorded twice


def test_force_re_queries_a_negative(tmp_path):
    lab = Lab(tmp_path, names=[u"frieren S2 - 11.mkv"])
    lab.run()

    report = lab.run(force=True)

    assert lab.spent == 1                                  # files again; resolution cached
    assert report.results[0].outcome == pipeline.NOT_FOUND


def test_every_candidate_refused_records_a_soft_negative(tmp_path):
    u"""⚠ Without that row, a video whose every candidate has been refused
    re-lists the entry on every run to learn nothing new -- one metered call per
    run, for good."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1)
    lab.run(candidates=1)

    report = lab.run(candidates=1)

    assert lab.spent == 0
    assert report.results[0].skip == pipeline.NEGATIVE
    assert u"refused by timing" in report.results[0].reason


# ---------------------------------------------------------------------------
# 7b. ⭐ RUNBOOK 8d -- a refused episode keeps its candidates on offer
# ---------------------------------------------------------------------------

def refuse_everything(lab, rate=0.31):
    lab.decide = lambda name: dict(outcome=port.REFUSED, match_rate=rate,
                                   reason=u"%d%% match -- the timing does not hold"
                                          % round(rate * 100))


def test_a_run_inside_the_retry_window_still_offers_yesterdays_candidates(tmp_path):
    u"""🚨 4a's SECOND CAUSE (`pipeline.py`, the negative skip). A run inside the
    retry window answered SKIPPED/negative with a reason and a date and NONE of the
    files that had just been refused -- so a row a person could pick from became a
    quiet *"waiting to retry"*, and the pick was gone. Sonic *"never got to"* pick
    Tsuihou.

    ⛔ And it must still cost nothing: no request, no download.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    first = lab.run(candidates=2)
    refused, = first.results
    tried = sorted(a.name for a in refused.attempts)
    assert len(tried) == 2 and refused.tried_before == ()

    lab.downloads = []
    again = lab.run(candidates=2)

    waiting, = again.results
    assert waiting.skip == pipeline.NEGATIVE
    assert lab.spent == 0 and lab.downloads == [], "remembering cost a request"
    assert sorted(t.name for t in waiting.tried_before) == tried, (
        u"the run inside the retry window forgot the candidates a person could pick")
    for t in waiting.tried_before:
        assert t.match_rate == pytest.approx(0.31)
        assert t.path and os.path.isfile(t.path), u"%s is offered with no file" % t.name
    wire = report_module.as_dict(waiting)
    assert sorted(t[u"name"] for t in wire[u"tried_before"]) == tried
    assert wire[u"attempts"] == [], u"`attempts` must keep meaning THIS run"


def test_after_the_window_an_episode_with_nothing_new_still_offers_the_old_ones(tmp_path):
    u"""🚨 D4 (RUNBOOK 8d). Once every offered candidate has been refused, the
    retry after the window downloads nothing -- correctly -- and came back
    REFUSED with ZERO attempts, so the pick row it made had nothing to pick."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    first = lab.run(candidates=99)
    everything = sorted(a.name for a in first.results[0].attempts)
    lab.now[0] += timedelta(days=1, minutes=1)

    lab.downloads = []
    later = lab.run(candidates=99)

    stuck, = later.results
    assert stuck.outcome == pipeline.REFUSED and stuck.attempts == ()
    assert lab.downloads == []
    assert sorted(t.name for t in stuck.tried_before) == everything, (
        u"every candidate had been refused, and the row offered none of them")


def test_a_fresh_refusal_keeps_this_runs_files_and_earlier_ones_apart(tmp_path):
    u"""⭐ `attempts` is THIS run, `tried_before` is every earlier one -- the counts,
    the report and the byte total all read `attempts` that way, and a pick row
    shows both."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    first = lab.run(candidates=2)
    before = set(a.name for a in first.results[0].attempts)
    lab.now[0] += timedelta(days=1, minutes=1)

    second = lab.run(candidates=2)

    row, = second.results
    now = set(a.name for a in row.attempts)
    assert row.outcome == pipeline.REFUSED and len(now) == 2
    assert set(t.name for t in row.tried_before) == before
    assert not now & before, u"a file tried in this run was listed as tried before"


def test_a_success_after_refusals_says_what_was_tried_before(tmp_path):
    u"""⭐ The retry worked -- and the only way a person could learn that is if the
    success still carries what was refused on the way (RUNBOOK 8e says it)."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    first = lab.run(candidates=2)
    before = sorted(a.name for a in first.results[0].attempts)
    lab.now[0] += timedelta(days=1, minutes=1)
    lab.decide = lambda name: {}                      # the next candidate holds

    second = lab.run(candidates=2)

    found, = second.results
    assert found.outcome == pipeline.CONFIDENT and found.wrote
    assert sorted(t.name for t in found.tried_before) == before


def test_a_video_moved_while_it_waits_is_remembered_where_it_is_now(tmp_path):
    u"""⭐ RUNBOOK 8e. The skip inside the retry window records nothing, so a
    video moved while it waited kept its OLD path in the state DB -- and the
    problems view, which asks the disk, dropped it. ⛔ And a dry run, which
    writes nothing, does not correct it either."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    lab.run(candidates=2)
    video_hash = lab.hash_of(u"frieren S2 - 01.mkv")
    moved = lab.media / u"sub" / u"frieren S2 - 01.mkv"
    moved.parent.mkdir()
    os.replace(str(lab.media / u"frieren S2 - 01.mkv"), str(moved))

    lab.run(candidates=2, dry_run=True)
    before, = [p for p in lab.db.problems(u"ja") if p.video_hash == video_hash]
    assert before.video_path != str(moved), u"a dry run wrote to the state DB"

    lab.run(candidates=2)
    after, = [p for p in lab.db.problems(u"ja") if p.video_hash == video_hash]
    assert os.path.normcase(after.video_path) == os.path.normcase(str(moved)), (
        u"the problem still names the place the video left")


def test_look_again_now_tries_the_next_files_inside_the_retry_window(tmp_path):
    u"""🚨 D3, TWO ARMS. The window's *Try 3 more candidates* ran the video's folder
    with no flag at all, and every refusal has just recorded a soft negative -- so
    for the 24 hours after one, the only time anybody presses it, the gate said
    "waiting to retry" and NOTHING was tried.

    ⭐ `retry_now` looks past the WAIT and nothing else: the files already refused
    are still never downloaded again.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    refuse_everything(lab)
    first = lab.run(candidates=2)
    refused_once = set(a.name for a in first.results[0].attempts)

    lab.downloads = []
    plain = lab.run(candidates=2)                       # arm A: what the button did
    assert plain.results[0].skip == pipeline.NEGATIVE and lab.downloads == []

    again = lab.run(candidates=2, retry_now=True)       # arm B: look again now
    row, = again.results
    assert len(lab.downloads) == 2, u"looking again tried nothing"
    assert not set(lab.downloads) & refused_once, (
        u"a file already refused for this video was downloaded again")
    assert set(a.name for a in row.attempts) == set(lab.downloads)
    assert set(t.name for t in row.tried_before) == refused_once


def test_look_again_now_still_honours_the_blacklist(tmp_path):
    u"""⛔ It overrules hato's own WAIT; the blacklist is the person's instruction."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.db.blacklist_add(lab.hash_of(u"frieren S2 - 01.mkv"), note=u"not wanted")
    report = lab.run(retry_now=True)
    assert report.results[0].skip == pipeline.BLACKLISTED and lab.downloads == []


def test_only_keeps_the_run_to_the_named_video(tmp_path):
    u"""⭐ `only` -- one row's *Look again now* must not become a run over the
    whole folder (which is what the old button did)."""
    lab = Lab(tmp_path, names=episodes_up_to(3))
    report = lab.run(only=[lab.media / u"frieren S2 - 02.mkv"])
    assert [r.name for r in report.results] == [u"frieren S2 - 02.mkv"]
    assert all(u"S2 - 02" in name for name in lab.downloads)


def test_one_video_is_offered_what_the_whole_folder_would_offer_it(tmp_path):
    u"""🚨 `only` MUST NOT SHRINK THE ALIGNMENT. A release's numbering is fitted
    against the FOLDER's range (entry 11446 numbers season 2 as 29-38); filtered
    at discovery, one video alone has no range at all -- *"the known soft spot"*
    -- and *Look again now* would be offered less than the run that refused it."""
    lab = Lab(tmp_path)
    five = u"frieren S2 - 05.mkv"
    whole = lab.by_name(lab.run(dry_run=True))[five]
    alone = lab.by_name(lab.run(dry_run=True, only=[lab.media / five]))[five]
    assert whole.candidates_offered > 1
    assert alone.candidates_offered == whole.candidates_offered, (
        u"one video alone was offered %d files where the folder's run offers %d"
        % (alone.candidates_offered, whole.candidates_offered))


def test_a_video_that_cannot_be_numbered_stops_re_listing_the_entry(tmp_path):
    u"""⚠ A WARM RE-RUN IS NOT ZERO METERED CALLS -- MEASURED [2, 1, 1, 1].

    `frieren S2.mkv` is a film sitting in a season folder: `episodes.align`
    refuses it because no episode number can be read, `_candidates` returned
    REFUSED **with no row of any kind**, and so the next run listed the entry's
    files all over again to reach the identical refusal. One metered call per
    run, for good -- the exact cost the negative cache exists to stop, and the
    only video shape in the whole suite that reaches this branch.

    ⚠ Every other warm-re-run check uses videos that SUCCEED, whose present-check
    then answers for them. A video that can never succeed was never re-run.
    """
    lab = Lab(tmp_path, names=[u"frieren S2.mkv"])
    spent = []
    for _ in range(4):
        report = lab.run()
        spent.append(lab.spent)

    assert spent == [2, 0, 0, 0]                 # ⛔ was [2, 1, 1, 1]
    assert report.results[0].skip == pipeline.NEGATIVE
    assert u"No episode number was read" in report.results[0].reason
    assert lab.rows()[pipeline.NOT_FOUND] == 1   # ⛔ and recorded exactly once


def test_the_first_run_on_an_unnumberable_video_still_says_what_would_change_it(tmp_path):
    u"""⛔ A soft negative is only allowed to make hato do LESS. The person must
    still be told what was refused and when it will be looked at again."""
    lab = Lab(tmp_path, names=[u"frieren S2.mkv"])

    one, = lab.run().results

    assert one.outcome == pipeline.REFUSED
    assert u"No episode number was read" in one.reason
    assert one.retry_after is not None
    assert one.retry_after.strftime(u"%Y-%m-%d") in one.reason
    assert lab.downloads == []                   # ⛔ nothing was fetched for it


# ---------------------------------------------------------------------------
# 8. 🚨 what the run may and may not send
# ---------------------------------------------------------------------------

def test_episode_is_never_in_any_request_url(tmp_path):
    u"""🚨 `LEDGER-HOT.md`: the server runs anitomy over each filename and
    SILENTLY DROPS every file it cannot parse a number from -- and it costs one
    metered call per episode instead of one per show."""
    lab = Lab(tmp_path, names=episodes_up_to(12))
    lab.run()
    assert lab.session.calls
    assert not [c for c in lab.session.calls if u"episode" in c["url"]]


def test_the_whole_file_list_is_asked_for_once_per_show(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(12))
    report = lab.run()
    listings = [c for c in lab.session.calls if u"/files" in c["url"]]
    assert len(listings) == 1
    assert report.shows[0].files_listed == len(FILES)


def test_a_401_stops_the_whole_run_at_once(tmp_path):
    u"""🚨 A rejected request still spends quota, so a bad key burns the budget
    silently. Fail loud, fail once, stop the run."""
    lab = Lab(tmp_path, names=episodes_up_to(10), stems=["search__401_bad_key"])

    report = lab.run()

    assert report.stopped is not None
    assert u"401" in report.stopped
    assert lab.spent == 1                     # ⛔ ONE call, not ten
    assert lab.downloads == []
    assert report.results == []


def test_a_show_that_fails_does_not_end_the_run(tmp_path):
    u"""⚠ *A season folder holds two different shows -- group videos by parsed
    title, resolve each independently* (06 §1). Here the second show's file list
    was never captured, so it fails on its own and the first still finishes."""
    lab = Lab(tmp_path, names=episodes_up_to(2) + [u"Kamen Rider Decade - 01.mkv"])

    report = lab.run()

    assert len(report.shows) == 2
    assert len(only(report, pipeline.CONFIDENT)) == 2
    bad = lab.by_name(report)[u"Kamen Rider Decade - 01.mkv"]
    assert bad.outcome == pipeline.ERROR
    assert report.stopped is None


def test_the_live_action_retry_is_what_finds_a_tokusatsu_show(tmp_path):
    u"""06 §1: the `anime` flag gates BEFORE the ID match and defaults true, so
    a live-action entry returns `[]` until it is asked with `anime=false`."""
    lab = Lab(tmp_path, names=[u"Kamen Rider Decade - 01.mkv"])
    report = lab.run()
    assert report.shows[0].resolved.entry_id == 33
    assert report.shows[0].resolved.source == u"jimaku anime=false"
    assert len([c for c in lab.session.calls if u"anime=false" in c["url"]]) == 1


# ---------------------------------------------------------------------------
# 9. --dry-run
# ---------------------------------------------------------------------------

def test_a_dry_run_identifies_and_lists_and_does_nothing_else(tmp_path):
    u"""⭐ Ruled for 4b: *identification includes the file listing* -- <= 2
    metered calls per show, each at most once per run. ⛔ Nothing downloaded,
    nothing written, no row recorded."""
    lab = Lab(tmp_path, names=episodes_up_to(12))

    report = lab.run(dry_run=True)

    assert lab.spent == 2
    assert lab.downloads == []
    assert lab.names_in(lab.media) == sorted(episodes_up_to(12))
    assert lab.kept() == []
    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}
    planned = [r for r in report.results if r.outcome == pipeline.PLANNED]
    assert len(planned) == 12
    assert all(u"would fetch" in r.reason for r in planned)
    assert all(r.candidates_offered > 0 for r in planned)


def test_a_dry_run_after_a_real_one_plans_nothing(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.run()

    report = lab.run(dry_run=True)

    assert lab.spent == 0
    assert set(r.skip for r in report.results) == {pipeline.PRESENT}


def test_a_dry_run_says_it_would_re_sync_from_the_kept_original(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.run()
    lab.forget_videos()

    report = lab.run(dry_run=True)

    assert report.results[0].outcome == pipeline.PLANNED
    assert u"would re-sync" in report.results[0].reason
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]


# ---------------------------------------------------------------------------
# 10. ⛔ what the run refuses to start on
# ---------------------------------------------------------------------------

def test_subs_dir_inside_a_scanned_folder_stops_the_run_before_anything_is_scanned(tmp_path):
    lab = Lab(tmp_path)
    with pytest.raises(pipeline.ConfigProblem) as caught:
        lab.run(subs_dir=lab.media / "subs")
    assert u"subs_dir" in str(caught.value)
    assert lab.metered == 0


def test_out_inside_a_scanned_folder_stops_the_run_before_anything_is_written(tmp_path):
    u"""🚨 THE SAME RULE, AND IT WAS ONLY ENFORCED FOR `subs_dir`.

    `hato D:\\Anime --out D:\\Anime\\Subs` was accepted, and the finished files
    hato writes there carry the VIDEOS' OWN BASENAMES -- so a later
    `tsubasa D:\\Anime` reads them as those videos' subtitles and supersedes them
    into the trash. Measured: `superseded = [...\\Subs\\frieren S2 - 01.ja.ass]`.

    ⚠ `test_the_kept_originals_really_would_be_offered_as_candidates` in
    `test_write.py` measured the mechanism -- for `subs/` only. One door was
    bolted and the other was not even latched.
    """
    lab = Lab(tmp_path)
    with pytest.raises(pipeline.ConfigProblem) as caught:
        lab.run(out=lab.media / "Subs")
    assert u"--out" in str(caught.value)
    assert lab.metered == 0
    assert lab.names_in(lab.media) == sorted(episodes_up_to(10))   # ⛔ nothing written


def test_a_scanned_folder_inside_out_stops_the_run_too(tmp_path):
    u"""⚠ The other direction reaches the same tree, so it is refused the same
    way -- the rule is about the WALK, not about which path was typed."""
    lab = Lab(tmp_path)
    with pytest.raises(pipeline.ConfigProblem):
        lab.run(out=lab.root)               # media/ lives under it


def test_a_settings_built_by_hand_with_no_subs_dir_says_so(tmp_path):
    u"""⚠ `Settings.from_config` fills `subs_dir` in; `Settings(folders=[...])`
    built by a library caller does not, and `check_subs_dir(None, …)` then raised
    a bare `TypeError` out of `os.fspath` -- an interpreter fault where a
    sentence naming the missing setting belongs."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    with pytest.raises(pipeline.ConfigProblem) as caught:
        lab.run(subs_dir=None)
    assert u"subs_dir" in str(caught.value)
    assert u"from_config" in str(caught.value)      # ⭐ and it names the way out
    assert lab.metered == 0


def test_a_language_tsubasa_cannot_resolve_is_a_config_problem_not_a_traceback(tmp_path):
    u"""⚠ `hato/config.py` takes any string for `lang`; tsubasa decides what
    resolves. `present.LanguageUnknown` came out of `_Run.__init__`, BEFORE
    `go()`'s conversion, so the one handler every caller was told to use missed
    it and a typo in config.toml was a stack trace."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    with pytest.raises(pipeline.ConfigProblem) as caught:
        lab.run(lang=u"Japanese")
    assert u"Japanese" in str(caught.value)
    assert lab.metered == 0


def test_a_folder_that_is_not_there_is_named_and_not_a_crash(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    report = lab.run(folders=[lab.media, tmp_path / "gone"])
    assert len(report.results) == 1
    assert any(u"gone" in note for note in report.notes)


def test_no_usable_folder_at_all_is_a_config_problem(tmp_path):
    lab = Lab(tmp_path)
    with pytest.raises(pipeline.ConfigProblem):
        lab.run(folders=[tmp_path / "gone"])


def test_a_video_holding_two_episodes_is_refused_and_never_guessed(tmp_path):
    u"""⛔ RULED: two subtitle files cannot cleanly become one, and a wrong
    guess writes a half-wrong file. ⚠ No DB row: a REFUSED row must name the
    candidate it refused, and there is none."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01-02.mkv", u"frieren S2 - 03.mkv"])
    report = lab.run()

    two = lab.by_name(report)[u"frieren S2 - 01-02.mkv"]
    assert two.outcome == pipeline.REFUSED
    assert u"one subtitle cannot be split" in two.reason
    assert lab.rows()[pipeline.REFUSED] == 0


def test_the_blacklist_is_read_before_hatos_own_two_episode_refusal(tmp_path):
    u"""⛔ THE PERSON'S INSTRUCTION COMES FIRST. `03-permissions.md` §*The read
    rule* puts the blacklist SECOND, right after the present-check; the
    episode-span refusal is hato's own judgement and had been slipped in above
    it because it costs nothing.

    🚨 The visible consequence: a video the person had blacklisted came back as
    HATO's refusal, so `hato blacklist --list` and the run disagreed about the
    same file and the note the person wrote was never shown back to them.

    ⚠ Every existing blacklist check used a plainly-numbered episode -- the one
    name shape that cannot reach the reordered branch.
    """
    lab = Lab(tmp_path, names=[u"frieren S2 - 01-02.mkv"])
    lab.db.blacklist_add(lab.hash_of(u"frieren S2 - 01-02.mkv"),
                         note=u"a double bill, I have the singles")

    report = lab.run()

    one, = report.results
    assert one.outcome == pipeline.SKIPPED
    assert one.skip == pipeline.BLACKLISTED
    assert u"a double bill" in one.reason               # ⭐ the person's own note
    assert u"cannot be split" not in one.reason
    assert len(lab.db.blacklist_list()) == 1            # and --list agrees with the run
    assert lab.spent == 0


# ---------------------------------------------------------------------------
# 10b. 🚨 TWO VIDEOS MAY NEVER TARGET ONE FILE
# ---------------------------------------------------------------------------
#
# Measured 2026-09-17. Run 1: A is written and tsubasa refuses B's write over it.
# ⛔ RUN 2: BOTH report *"subtitle already present"* -- and B's "subtitle" is A's
# file, a different release's timing, silently, for ever. `_gate` decides every
# video before anything is written, so `look.forget()` cannot save B.
#
# ⚠ EVERY CHECK ABOVE USES ONE ROOT, ONE FOLDER AND UNIQUE STEMS, which is
# precisely the fixture that cannot express any of the three reachable shapes.

def test_two_roots_flattening_onto_one_out_file_are_both_refused(tmp_path):
    u"""SHAPE 1, and the one that needs no odd naming at all: `mirrored_dir`
    returns `out` ITSELF for a video sitting in the root, so two roots given on
    one command line both flatten onto it.

    ⭐ THE SECOND RUN IS THE POINT. Without the refusal it reported two tidy
    SKIPPED-already-present lines over one file.
    """
    lab, other_root = lab_pair(tmp_path)

    first = lab.run(folders=[lab.media, other_root], out=lab.out)

    both = first.results
    assert len(both) == 2
    assert [r.outcome for r in both] == [pipeline.REFUSED, pipeline.REFUSED]
    assert all(u"SAME subtitle file" in r.reason for r in both)
    assert lab.downloads == []
    assert lab.names_in(lab.out) == []               # ⛔ nothing was written at all

    second = lab.run(folders=[lab.media, other_root], out=lab.out)

    # ⛔ NEVER "subtitle already present": there is no file, and if there were it
    # would be the other video's.
    assert [r.outcome for r in second.results] == [pipeline.REFUSED, pipeline.REFUSED]
    assert not [r for r in second.results if r.skip == pipeline.PRESENT]


def test_each_refusal_names_the_other_video(tmp_path):
    u"""⚠ *"It failed"* is not actionable. The person has two files and must be
    told WHICH two, or the sentence is a riddle."""
    lab, other_root = lab_pair(tmp_path)
    report = lab.run(folders=[lab.media, other_root], out=lab.out)

    by_root = dict((str(Path(r.video).parent), r) for r in report.results)
    mine = by_root[str(lab.media)]
    theirs = by_root[str(other_root)]
    assert u"frieren S2 - 01.mkv" in mine.reason
    assert u"frieren S2 - 01.mkv" in theirs.reason
    assert u"hato sync" in mine.reason               # ⭐ and what would change it


def test_two_roots_sharing_a_subpath_under_out_are_both_refused(tmp_path):
    u"""SHAPE 2: `--out` mirrors *the tree below the scanned root*, on purpose --
    `D:/Anime` and `E:/Downloads/Anime` are meant to merge per show. Two roots
    that both hold `S2/` therefore both mirror onto `out/S2/`."""
    lab = Lab(tmp_path, names=[])
    a = lab.second_root(os.path.join(u"lib-a", u"S2"), u"frieren S2 - 01.mkv")
    b = lab.second_root(os.path.join(u"lib-b", u"S2"), u"frieren S2 - 01.mkv")

    report = lab.run(folders=[a.parent, b.parent], out=lab.out)

    assert len(report.results) == 2
    assert all(r.outcome == pipeline.REFUSED for r in report.results)
    assert all(u"SAME subtitle file" in r.reason for r in report.results)
    assert all(os.path.join(u"out", u"S2") in r.reason for r in report.results)
    assert lab.spent == 0                            # ⛔ decided before identification


def test_watching_a_run_does_not_change_what_it_does(tmp_path):
    u"""RUNBOOK 7b. ⛔ Opt-in and inert: the same run, watched and unwatched,
    reaches the same outcomes and spends the same number of API calls."""
    plain = Lab(tmp_path / "a", names=episodes_up_to(2))
    quiet = plain.run()

    watched_lab = Lab(tmp_path / "b", names=episodes_up_to(2))
    events = []
    loud = watched_lab.run(on_progress=events.append)

    assert [r.outcome for r in loud.results] == [r.outcome for r in quiet.results]
    assert loud.api_calls == quiet.api_calls
    assert events, "progress was asked for and none arrived"


def test_progress_arrives_WHILE_the_run_happens_not_after_it(tmp_path):
    u"""🚨 THE CHECK THIS STEP EXISTS FOR, and the one shape that would have
    caught the original defect.

    `--json` already emitted the right objects -- built from a FINISHED report,
    every line written after `pipeline.run()` returned. A check that merely
    asserts *"a progress line exists"* is green against exactly that, which is
    how the requirement came to be marked verified while the window had nothing
    to paint.

    ⭐ SO THE ASSERTION IS ABOUT ORDER, against one log both the callback and a
    real seam write into: some WORK must happen after some progress. Buffered to
    the end, every progress entry sits after every download and the first half
    of this fails.
    """
    lab = Lab(tmp_path, names=episodes_up_to(3))
    lab.decide = lambda name: {}
    log = []
    real_download = lab.download

    def watched_download(item):
        log.append(u"work")
        return real_download(item)

    lab.download = watched_download
    lab.run(on_progress=lambda event: log.append(u"progress:" + event["phase"]))

    assert u"work" in log, "the fixture downloaded nothing, so it proves nothing"
    first_work = log.index(u"work")
    # ⛔ THE DECISIVE HALF. Under buffering there is no progress before any work.
    assert any(entry.startswith(u"progress") for entry in log[:first_work])
    # ...and the run really did keep reporting as it went, rather than once.
    assert any(entry.startswith(u"progress") for entry in log[first_work:])


def test_a_run_decided_entirely_at_the_gate_still_reports_every_video(tmp_path):
    u"""🚨 FOUND BY LOOKING AT A REAL RUN, NOT BY A CHECK (2026-09-18).

    The `result` report sat in the candidate loop, which is ONE of the seven
    callers of `_keep_result`. So a run where every video was settled at the
    gate -- already subtitled, blacklisted, no track, waiting on a retry --
    emitted `start`, `found` and then NOTHING until the run object, and the
    window's footer would have sat silent through the whole of it.

    ⭐ THAT IS THE COMMONEST RUN THERE IS: a library where nothing new has
    arrived. Every check was green, because the fixture behind them only holds
    videos that need fetching.
    """
    lab = Lab(tmp_path, names=episodes_up_to(3))
    for name in episodes_up_to(3):
        lab.db.blacklist_add(lab.hash_of(name), note=u"settled")

    events = []
    report = lab.run(on_progress=events.append)

    assert all(r.skip == pipeline.BLACKLISTED for r in report.results)
    assert lab.spent == 0                       # ⛔ nothing was fetched at all
    results = [e for e in events if e[u"phase"] == u"result"]
    videos = [e for e in events if e[u"phase"] == u"video"]
    assert len(results) == 3
    assert sorted(e[u"name"] for e in videos) == sorted(episodes_up_to(3))


def test_every_progress_event_says_which_phase_it_is(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: {}
    events = []
    lab.run(on_progress=events.append)
    assert events, "no progress at all"
    assert all(u"phase" in e for e in events)
    phases = {e[u"phase"] for e in events}
    assert {u"start", u"found", u"show", u"video", u"result"} <= phases


def test_a_progress_callback_that_raises_cannot_change_what_the_run_does(tmp_path):
    u"""⛔ A report, never a decision. A window whose pipe has closed must not
    be able to stop a run that is part-way through writing files."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: {}
    clean = lab.run()

    lab2 = Lab(tmp_path / "b", names=episodes_up_to(2))
    lab2.decide = lambda name: {}

    def explode(event):
        raise RuntimeError("the window went away")

    broken = lab2.run(on_progress=explode)
    assert [r.outcome for r in broken.results] == [r.outcome for r in clean.results]
    assert broken.stopped is None


def test_the_surasura_copy_follows_a_real_run(tmp_path):
    u"""RUNBOOK 7h -- the SEAM, and the half a unit test cannot see.

    ⭐ There are TWO success paths in this pipeline (a fresh download and a
    re-sync from a kept original), so the copy lives in `_keep_result`, the one
    funnel every outcome passes through. Copying in either path alone is the
    seam defect this project keeps paying for -- and it would look completely
    correct from inside whichever one was chosen.
    """
    drop = tmp_path / "Downloads"
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: {}

    report = lab.run(surasura_dir=str(drop))

    written = [r for r in report.results if r.wrote]
    assert written, u"the fixture wrote nothing, so this proves nothing"
    landed = sorted(p.name for p in (drop / u"Hato").iterdir())
    assert landed == sorted(os.path.basename(r.output_path) for r in written)
    # ⛔ A COPY. The file beside the video is the one a player loads.
    assert all(os.path.isfile(r.output_path) for r in written)


def test_a_video_that_already_had_a_subtitle_is_not_copied(tmp_path):
    u"""⛔ *"each successful run's subtitles"* -- not the whole library.

    A PRESENT row carries an `output_path` too, so a copy keyed on that alone
    would ship every already-subtitled episode on every run, for ever. The
    guard is `result.skip`.
    """
    drop = tmp_path / "Downloads"
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mkv"])
    (lab.media / u"frieren S2 - 01.ja.srt").write_text(u"1\n", encoding="utf-8")

    report = lab.run(surasura_dir=str(drop))

    assert report.results[0].skip == pipeline.PRESENT
    assert not (drop / u"Hato").exists(), (
        u"an already-subtitled episode was copied, so a settled library would "
        u"be re-shipped on every run")


def test_the_integration_writes_nothing_when_no_folder_is_chosen(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: {}
    lab.run()
    assert not (tmp_path / u"Hato").exists()


def test_a_video_inside_a_skipped_folder_is_never_looked_at(tmp_path):
    u"""RUNBOOK 7e -- the SEAM, and it is the half a unit test cannot see.

    ⭐ `_under_any` is checked exhaustively in `test_config_write.py` and
    `Settings` is checked to carry the list. Neither says the SCAN consults it,
    and a setting stored but not honoured is the documented failure *"offered
    Sonic a setting that did nothing"* (HANDOFF.md §7) -- which is invisible
    from either side of the join.
    """
    lab = Lab(tmp_path, names=[])
    watched = lab.second_root(u"lib", u"frieren S2 - 01.mkv")
    incoming = lab.second_root(os.path.join(u"lib", u"_incoming"),
                               u"frieren S2 - 02.mkv")

    report = lab.run(folders=[watched], skip_folders=[incoming])

    assert [os.path.basename(r.video) for r in report.results] == \
        [u"frieren S2 - 01.mkv"]
    # ⛔ AND IT IS SAID OUT LOUD. Dropped silently, a skip rule that is too
    # broad is indistinguishable from a folder that was empty.
    assert any(u"skipped folder" in note for note in report.notes)


def test_a_folder_whose_name_merely_starts_the_same_is_not_skipped(tmp_path):
    u"""🚨 THE PREFIX TRAP, at the seam rather than in the helper. A
    `startswith` test says `_incoming2` is inside `_incoming`, so skipping one
    folder would silently take a DIFFERENT library out of every run."""
    lab = Lab(tmp_path, names=[])
    watched = lab.second_root(u"lib", u"frieren S2 - 01.mkv")
    skipped = lab.second_root(os.path.join(u"lib", u"_incoming"),
                              u"frieren S2 - 02.mkv")
    lab.second_root(os.path.join(u"lib", u"_incoming2"), u"frieren S2 - 03.mkv")

    report = lab.run(folders=[watched], skip_folders=[skipped])

    kept = sorted(os.path.basename(r.video) for r in report.results)
    assert kept == [u"frieren S2 - 01.mkv", u"frieren S2 - 03.mkv"]


def test_two_encodes_of_one_episode_in_one_folder_are_both_refused(tmp_path):
    u"""SHAPE 3, and it needs no `--out` and no second root -- just the ordinary
    library of somebody who kept both encodes. ⛔ `Show - 01.ja.ass` answers
    *present* for `Show - 01.mp4` too: `hato/present.py` matches a sidecar on its
    STEM, so the extension the download happens to have changes nothing."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mkv", u"frieren S2 - 01.mp4",
                               u"frieren S2 - 02.mkv"])

    report = lab.run()

    by_name = lab.by_name(report)
    assert by_name[u"frieren S2 - 01.mkv"].outcome == pipeline.REFUSED
    assert by_name[u"frieren S2 - 01.mp4"].outcome == pipeline.REFUSED
    assert u"frieren S2 - 01.mp4" in by_name[u"frieren S2 - 01.mkv"].reason
    # ⭐ AND THE REST OF THE FOLDER IS UNTOUCHED: this is a per-video refusal, not
    # a reason to stop working.
    assert by_name[u"frieren S2 - 02.mkv"].outcome == pipeline.CONFIDENT
    assert lab.names_in(lab.media) == sorted(
        [u"frieren S2 - 01.mkv", u"frieren S2 - 01.mp4", u"frieren S2 - 02.mkv",
         Path(by_name[u"frieren S2 - 02.mkv"].output_path).name])


def test_a_second_encode_is_never_told_the_first_ones_file_is_its_own(tmp_path):
    u"""🚨 THE MEASURED SYMPTOM, AND THE REASON THE CLASH IS ASKED **BEFORE** THE
    PRESENT-CHECK.

    The person ran hato, got `frieren S2 - 01.ja.ass` for their `.mkv`, and later
    added a second encode. `hato/present.py` matches a sidecar on its STEM, so
    that file answers *present* for the `.mp4` as well -- and the run printed
    *"SKIPPED -- subtitle already present"* over a subtitle belonging to a
    different release, whose timing is not the `.mp4`'s, silently and for ever.

    ⚠ FOUND BY BREAKING THE FIX, not by writing it: moving the clash below the
    present-check left every other check in this section green, because a clash
    refused from the first run means no file is ever written for either video and
    the present-check has nothing to be poisoned by. The file has to be there
    ALREADY -- which is exactly how a person reaches this.
    """
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mkv"])
    lab.run()                                       # the ordinary first run
    written = [n for n in lab.names_in(lab.media) if n.endswith((u".ass", u".srt"))]
    assert written, "the first run is expected to have written a sidecar"
    (lab.media / u"frieren S2 - 01.mp4").write_bytes(b"\x1aE\xdf\xa3a second encode")
    lab.downloads = []

    report = lab.run()

    added = lab.by_name(report)[u"frieren S2 - 01.mp4"]
    assert added.outcome == pipeline.REFUSED
    assert added.skip is None                       # ⛔ NOT "subtitle already present"
    assert u"SAME subtitle file" in added.reason
    assert u"frieren S2 - 01.mkv" in added.reason
    assert lab.downloads == []
    # ⛔ And the file that IS the .mkv's stays exactly where it was.
    assert [n for n in lab.names_in(lab.media) if n.endswith((u".ass", u".srt"))] == written


def test_a_clash_records_nothing_at_all(tmp_path):
    u"""⛔ No attempt row -- like the two-episode refusal there is no candidate to
    name -- and ⛔ no negative: jimaku has the episode, and the day the person
    renames one file both videos must work immediately."""
    lab, other_root = lab_pair(tmp_path)
    lab.run(folders=[lab.media, other_root], out=lab.out)

    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}

    # the person renames one of them -- and nothing has to expire first
    (other_root / u"frieren S2 - 01.mkv").rename(other_root / u"frieren S2 - 07.mkv")
    report = lab.run(folders=[lab.media, other_root], out=lab.out)

    assert len(only(report, pipeline.CONFIDENT)) == 2


def lab_pair(tmp_path):
    u"""One episode of one show, sitting in TWO scanned roots. ⚠ Distinct bytes
    per root: the state DB is keyed on the head+tail hash."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mkv"])
    return lab, lab.second_root(u"lib-b", u"frieren S2 - 01.mkv")


def test_the_archives_the_loop_does_not_open_are_named_out_loud(tmp_path):
    u"""⚠ A RECORDED DEFECT, not a silent gap: `06-edge-cases.md` §5 and
    `config.archives` both say an entry offering an archive is unpacked, and
    RUNBOOK 3c built the extractor -- but the read rule 4b implements verbatim
    has no step that opens one. ⭐ Entry 440 (the recorded movie) carries a real
    `.7z`, so this is measured rather than staged."""
    lab = Lab(tmp_path, names=[u"Kimi no Na wa.mkv"])
    report = lab.run(candidates=1)
    archives = [f for f in json.loads(
        (FIXTURES / "api" / "entries_movie_flag.json").read_text(encoding="utf-8"))
        if f["name"].lower().endswith((u".zip", u".7z", u".rar"))]
    assert archives, "the recorded movie entry is expected to carry an archive"
    assert any(u"were NOT opened" in note for note in report.shows[0].notes)


# ---------------------------------------------------------------------------
# 11. the resolution cache is dropped when every video was refused
# ---------------------------------------------------------------------------

def test_a_show_whose_every_video_was_refused_is_identified_again_next_time(tmp_path):
    u"""⭐ RUNBOOK 2b's ruling: a show whose every attempted video ended REFUSED
    was probably identified WRONG, and a resolution cached *"for ever"* would
    never get another chance."""
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1)
    lab.run(candidates=1)

    assert lab.resolutions.get(resolution.cache_key(u"frieren", 2)) is None

    lab.now[0] += timedelta(days=2)
    lab.run(candidates=1)
    assert lab.spent == 2                 # ⚠ the search was paid for again


def test_a_blocked_write_does_not_drop_the_shows_resolution(tmp_path):
    u"""⚠ THE SAME LINE AS THE TIMING-REFUSAL DEFECT, ONE LEVEL UP. *"Every video
    tried on this show was refused"* counted every video with an ATTEMPT -- so a
    blocked write, at 100% match with the identification obviously right, dropped
    the cached resolution and printed *"refused by timing"* over a video that was
    not refused and not about timing. It also cost a metered search on the next
    run to learn the same entry id.

    ⭐ FOUND BY RENDERING THE REPORT AND READING IT, not by an assertion -- the
    check above it was green and measuring the video, which was correct by then.
    """
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.decide = lambda name: dict(writes=False)
    report = lab.run(candidates=1)

    assert report.results[0].outcome == pipeline.ERROR
    assert lab.resolutions.get(resolution.cache_key(u"frieren", 2)) is not None
    assert not [n for n in report.shows[0].notes if u"refused by timing" in n]

    lab.decide = lambda name: {}
    lab.run(candidates=1)
    assert lab.spent == 1                 # ⛔ files only; the search was NOT paid again


def test_a_show_with_one_success_keeps_its_resolution(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(2))
    lab.decide = lambda name: ({} if u"- 01" in name or u"29" in name
                               else dict(outcome=port.REFUSED, reason=u"no", match_rate=0.1))
    lab.run(candidates=1)
    assert lab.resolutions.get(resolution.cache_key(u"frieren", 2)) is not None


class ListForAnyEntry(object):
    u"""DERIVED: the real client, except that the RECORDED file list of entry
    11446 answers `files()` for an entry it was never recorded for.

    ⚠ THE CAPTURE HOLDS ONE ENTRY'S FILES, and the shape below needs the
    resolution to land on a DIFFERENT entry while a real file list comes back --
    which is exactly the defect: a seasonless video resolves to the season-1
    entry, whose list holds nothing for it. Everything metered is still the real
    client over the real recording.
    """

    def __init__(self, inner):
        self._inner = inner
        self.entries = []

    @property
    def metered(self):
        return self._inner.metered

    def search(self, query=None, **kwargs):
        return self._inner.search(query, **kwargs)

    def files(self, entry_id):
        self.entries.append(entry_id)
        return self._inner.files(ENTRY)

    def download(self, item):
        return self._inner.download(item)


class OneArchiveOnTheEntry(ListForAnyEntry):
    u"""DERIVED: the entry offers ONE batch archive and nothing else.

    The real shape behind `--archives`: a show whose subtitles exist only inside a
    season pack, which is how most of One Piece's 36 archives are published.
    """

    def __init__(self, inner, blob, name=u"Show 01-12 [batch].zip"):
        ListForAnyEntry.__init__(self, inner)
        self.blob, self.name, self.fetched = blob, name, []

    def files(self, entry_id):
        self.entries.append(entry_id)
        return [{"name": self.name, "size": len(self.blob),
                 "url": u"https://jimaku.cc/entry/11446/download/%s" % self.name,
                 "last_modified": u"2026-01-01T00:00:00Z"}]

    def download(self, item):
        self.fetched.append(item.get("name"))
        return self.blob


def test_an_archive_is_opened_only_when_the_setting_is_on(tmp_path):
    u"""⭐ RULED 2026-09-17 (Sonic): *"are we concerned about auto-doing that?
    there may be bad files downloaded in the zip. How about adding it in settings,
    a toggle and if so, it will. default off"*.

    ⛔ OFF is the default and it must be a real refusal, not a quiet one: the
    archive is named, the flag is named, and **nothing is downloaded or opened**.
    ⭐ ON, its members are candidates like any other -- ⚠ and the timing verdict
    still decides, so opening an archive never means trusting what came out of it.
    """
    import io
    import zipfile

    member = u"[Grp] frieren S2 - 03 (1080p) [ABCD].ja.srt"
    body = (u"1\n00:00:01,000 --> 00:00:03,000\n%s\n\n" % (u"日本語")).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, body)
    blob = buf.getvalue()

    lab = Lab(tmp_path, names=[u"frieren S2 - 03.mkv"])
    lab.client = OneArchiveOnTheEntry(lab.real, blob)
    # ⚠ Bytes come from the `downloader=` seam, NOT from the client -- the client
    # serves metadata only (`07-test-plan.md`). My first version staged the zip on
    # the client and the run happily "downloaded" the lab's synthetic subtitle
    # bytes under the archive's name, so extraction failed for a reason that had
    # nothing to do with archives.
    plain = lab.download

    def download(item):
        if item["name"] == lab.client.name:
            lab.downloads.append(item["name"])
            return blob
        return plain(item)

    lab.download = download

    off = lab.run(archives=False)                     # the ruled default
    assert off.results[0].outcome != pipeline.CONFIDENT
    assert lab.downloads == [], u"OFF must not download the archive at all"
    show, = off.shows
    assert [n for n in show.notes if u"--archives" in n], show.notes

    # ⚠ `force=True`, and the reason is worth knowing: the OFF run above recorded a
    # soft negative ("no release places a file on this episode"), so simply turning
    # the setting on does NOT retroactively re-ask -- the negative is consulted
    # first and the video is skipped until it expires. That is the documented
    # meaning of a negative, and `--force` is the documented way to ask now.
    on = lab.run(archives=True, force=True)

    one = on.results[0]
    assert lab.client.name in lab.downloads, (
        u"ON it has to actually fetch the pack",
        on.shows[0].notes, one.outcome, one.skip, one.reason)
    assert one.outcome == pipeline.CONFIDENT, one.reason
    assert one.jimaku_filename == member
    assert one.output_path and os.path.exists(one.output_path)


#: Marks a file as coming from the WRONG entry, so the stub engine can refuse it
#: by name. ⚠ The names still carry the capture's own episode numbers, which is
#: what makes them ALIGN -- an entry that offers nothing is a different defect.
WRONG_SEASON = u"WRONG-SEASON "


class WrongSeasonThenRight(ListForAnyEntry):
    u"""DERIVED: every other entry answers with the capture's files RENAMED.

    They align exactly as the real ones do -- same numbers -- so the run gets a
    full set of candidates and refuses every one of them on timing. That is the
    shape measured live: entry 332 (season 1) offering five candidates per video
    for episodes it does not have.
    """

    def files(self, entry_id):
        self.entries.append(entry_id)
        real = self._inner.files(ENTRY)
        if entry_id == ENTRY:
            return real
        return [dict(f, name=WRONG_SEASON + f["name"]) for f in real]


class ListsOnlyForTheRealEntry(ListForAnyEntry):
    u"""DERIVED: every other entry answers with an EMPTY list.

    ⚠ This is the shape the live run hit and the capture cannot hold on its own:
    the search scores several entries of one show, the winner is the wrong
    season, and only the runner-up has the episodes.
    """

    def files(self, entry_id):
        self.entries.append(entry_id)
        return self._inner.files(ENTRY) if entry_id == ENTRY else []


def test_an_entry_that_holds_nothing_escalates_to_the_next_one_the_search_scored(tmp_path):
    u"""🚨 MEASURED LIVE AGAINST THE REAL API, 2026-09-17: `Re Zero kara Hajimeru
    Isekai Seikatsu - 52` resolved to **entry 332, season 1** -- 138 files, none
    in the 52-62 range -- and the run stopped there reporting that nothing could
    be placed, **with the other entries already scored and in hand.** jimaku keeps
    one entry per season, so the next candidate is usually the right one.

    ⭐ The cost is one metered call, once: a working alternate REPOINTS the
    resolution cache, so the next run goes straight to it.
    """
    lab = Lab(tmp_path, names=[u"frieren - 31.mkv"])     # seasonless -> every entry ties
    lab.client = ListsOnlyForTheRealEntry(lab.real)

    report = lab.run(candidates=1)

    show, = report.shows
    assert show.resolved.low_confidence is True, show.reason
    assert show.resolved.entry_id == ENTRY, u"it never moved off the entry that held nothing"
    assert lab.client.entries[0] != ENTRY, u"the wrong entry has to be tried FIRST, or this proves nothing"
    assert [n for n in show.notes if u"held nothing for any video" in n], show.notes
    assert report.results[0].outcome == pipeline.CONFIDENT

    # ⭐ THE COST CLAIM, and it is the half that makes escalation affordable.
    spent_first = lab.spent
    lab.run(candidates=1)
    assert lab.spent < spent_first, u"the repointed cache must make the second run cheaper"


def test_an_entry_whose_every_candidate_is_refused_escalates_to_the_next_entry(tmp_path):
    u"""🚨 THE COMMONER SHAPE, AND IT LOOKS LIKE SUCCESS UNTIL THE VERDICTS COME
    BACK. Measured on a real library 2026-09-17: `Re Zero … - 52/54/55`
    (seasonless names, absolute numbers) resolved to **entry 332, season 1**,
    which offered five candidates per video -- from the wrong season. All fifteen
    were refused by timing, correctly. Nothing wrong was written and nothing right
    either, with the right entry one metered call away.

    ⭐ Re-run live after this landed: entry 332 → **7615, "3rd Season"**, and all
    three episodes were written at 80%, 57% and 63%.

    ⛔ The replacement only happens if the alternate WINS one -- swapping refusals
    for refusals would only hide the first entry's reasons.
    """
    lab = Lab(tmp_path, names=[u"frieren - 31.mkv"])
    # ⚠ THE STAGING IS THE WHOLE CHECK, and my first attempt got it wrong: I gave
    # the wrong entry an EMPTY list, which fires `_escalate` (offers nothing) --
    # a different path that was already covered. The shape here has to be an entry
    # that offers plenty and is wrong about all of it.
    lab.client = WrongSeasonThenRight(lab.real)
    lab.decide = lambda name: (
        {"outcome": port.REFUSED, "reason": u"the timing does not hold"}
        if name.startswith(WRONG_SEASON) else {"outcome": port.CONFIDENT})

    report = lab.run(candidates=2)

    show, = report.shows
    assert show.resolved.entry_id == ENTRY, show.reason
    assert [n for n in show.notes if u"refused by timing" in n], show.notes
    assert report.results[0].outcome == pipeline.CONFIDENT
    assert lab.resolutions.get(
        resolution.cache_key(u"frieren")).entry_id == ENTRY


def _escalating_lab(tmp_path):
    u"""Two videos on a wrong entry; the right one wins 31 and refuses 32."""
    lab = Lab(tmp_path, names=[u"frieren - 31.mkv", u"frieren - 32.mkv"])
    lab.client = WrongSeasonThenRight(lab.real)
    lab.decide = lambda name: (
        {"outcome": port.CONFIDENT}
        if not name.startswith(WRONG_SEASON) and (u"- 31" in name or u"[31]" in name)
        else {"outcome": port.REFUSED, "reason": u"the timing does not hold"})
    return lab


def test_an_alternate_entrys_files_are_recorded_under_that_entry(tmp_path):
    u"""ADVERSARY 2026-09-22 F13. The alternate's files were RECORDED under the
    FIRST entry's id -- `_candidates` read the entry off a `show.resolved` not yet
    moved -- so the refusal check, which keys on the entry, never found them,
    and a later *Look again* downloaded files already refused for the video."""
    lab = _escalating_lab(tmp_path)
    report = lab.run(candidates=2)
    show, = report.shows
    assert show.resolved.entry_id == ENTRY, u"the control: the alternate won for 31"
    entries = sorted(set(e for (e,) in lab.db._conn.execute(
        "SELECT jimaku_entry FROM attempts WHERE jimaku_filename NOT LIKE ?",
        (WRONG_SEASON + u"%",))))
    assert entries == [ENTRY], (
        u"the right entry's files were recorded under entr%s %s, not %d"
        % (u"y" if len(entries) == 1 else u"ies", entries, ENTRY))
    refused_32 = [n for (n,) in lab.db._conn.execute(
        "SELECT jimaku_filename FROM attempts WHERE video_path LIKE '%32.mkv' "
        "AND outcome = 'REFUSED' AND jimaku_filename NOT LIKE ?", (WRONG_SEASON + u"%",))]
    assert refused_32, u"the control: 32 refused the right entry's files in run 1"
    del lab.downloads[:]
    lab.run(candidates=2, retry_now=True, only=[str(lab.media / u"frieren - 32.mkv")])
    again = [n for n in lab.downloads if n in refused_32]
    assert again == [], (
        u"--retry-now downloaded %d file(s) already refused for this video: %s"
        % (len(again), again))


def test_an_alternate_that_wins_nothing_leaves_the_show_on_its_entry(tmp_path):
    u"""ADVERSARY 2026-09-22 F13, the other half. The alternate is the entry only
    WHILE its files are tried; when it wins nothing the show goes back to the
    entry it was on -- or the rest of the run (its note, its negative, the next
    alternate's *"instead of"*) names an entry that was only ever tried."""
    lab = _escalating_lab(tmp_path)
    lab.decide = lambda name: {"outcome": port.REFUSED, "reason": u"the timing does not hold"}
    report = lab.run(candidates=2)
    show, = report.shows
    assert ENTRY in lab.client.entries, u"the control: the alternate entry was tried"
    assert show.resolved.entry_id != ENTRY, (
        u"an alternate that won nothing was left as the show's entry (%d)" % ENTRY)


def test_a_first_ever_success_on_an_alternate_entry_is_not_found_on_a_retry(tmp_path):
    u"""ADVERSARY 2026-09-22 F14. What a video tried in EARLIER runs was read again
    for the alternate's pass -- after this run had recorded the first entry's
    refusals -- so a first run's success said *"found on a retry"*."""
    lab = _escalating_lab(tmp_path)
    report = lab.run(candidates=2)
    won = lab.by_name(report)[u"frieren - 31.mkv"]
    assert won.outcome == pipeline.CONFIDENT, u"the control: the alternate won 31"
    assert won.tried_before == (), (
        u"the first run ever carried %d earlier file(s) -- the window would say *found on "
        u"a retry*: %s" % (len(won.tried_before), [t.name for t in won.tried_before]))


def test_a_low_confidence_show_whose_entry_held_nothing_is_identified_again(tmp_path):
    u"""🚨 THE EPISODE NUMBER IS EVIDENCE ABOUT THE ENTRY, and it was in hand and
    unused. `_forget` fired only when a video had been ATTEMPTED and refused --
    so a show that attempts NOTHING, because its entry holds nothing for any of
    its videos, kept a wrong resolution in the one store the spec keeps *"for
    ever"*. Every later run then served it from cache and answered NOT FOUND.

    ⭐ An entry that can hold none of your episodes is evidence against itself.
    """
    lab = Lab(tmp_path, names=[u"frieren - 141.mkv"])
    lab.client = ListForAnyEntry(lab.real)
    report = lab.run(candidates=1)

    show, = report.shows
    assert show.resolved.low_confidence is True, show.reason   # the harm is real
    assert lab.downloads == [] and report.results[0].outcome == pipeline.NOT_FOUND
    assert lab.resolutions.get(resolution.cache_key(u"frieren")) is None
    assert [n for n in show.notes if u"evidence against itself" in n], show.notes

    lab.now[0] += timedelta(days=2)
    lab.run(candidates=1)
    # ⚠ AMENDED 2026-09-17, and the extra call IS the point. This was 2 -- search +
    # files. `_escalate` now also tries the runner-up entry the search had already
    # scored, because an entry that holds nothing for any video is exactly when the
    # next one is worth a look (measured live: Re:Zero 52-55 stopped on the season 1
    # entry with the alternates in hand and unused). Here no alternate holds
    # anything either, so the resolution is still dropped -- the cost is one metered
    # call for the chance, bounded by `ALTERNATE_ENTRIES`, and paid once per show
    # because a working alternate repoints the cache.
    assert lab.spent == 3, u"search + files + one escalation attempt"
    assert lab.resolutions.get(resolution.cache_key(u"frieren")) is None


def test_a_confident_show_that_found_nothing_keeps_its_resolution(tmp_path):
    u"""⚠ THE OTHER ARM, and the reason the rule is not just *"nothing found"*.
    06 §2's ordinary case -- *"entry has 1-8, folder has 1-12"* -- is NOT_FOUND
    with a retry date, not an error and not evidence about the entry. Dropping
    the resolution there would buy the identical answer with a metered call."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 141.mkv"])
    report = lab.run(candidates=1)

    show, = report.shows
    assert show.resolved.low_confidence is False and show.resolved.entry_id == ENTRY
    assert report.results[0].outcome == pipeline.NOT_FOUND
    assert lab.resolutions.get(resolution.cache_key(u"frieren", 2)) is not None
    assert not [n for n in show.notes if u"evidence against itself" in n], show.notes

    lab.now[0] += timedelta(days=2)
    lab.run(candidates=1)
    assert lab.spent == 1                 # ⛔ files only; the search was NOT paid again


# ---------------------------------------------------------------------------
# 11b. ⭐ the year reaches the cache key
# ---------------------------------------------------------------------------

def test_two_shows_that_differ_only_by_their_year_never_share_a_resolution(tmp_path):
    u"""🚨 06 §1: *"Two shows normalize to the same cache key -- include the
    parsed season/year in the key. A collision would serve the wrong entry from
    cache forever."* Nothing passed `year=`. `hato/tokens.py`'s `year()` was
    written for exactly this (4,872 bracketed-year names measured) and had no
    caller, so the parameter `cache_key` carries and the store CHECKs was dead
    in production.

    ⚠ The harm is proved first: tsubasa DROPS the bracketed year, so both names
    read one title and one season.
    """
    names_ = [u"frieren S2 - 01 (1999).mkv", u"frieren S2 - 01 (2011).mkv"]
    lab = Lab(tmp_path, names=names_)
    read = dict((i.name, i) for i in tsubasa.scan(videos=str(lab.media)).videos)
    assert len({(v.title, v.season) for v in read.values()}) == 1, read   # the harm is real

    report = lab.run(candidates=1)

    assert sorted(s.year for s in report.shows) == [1999, 2011], report.shows
    # ⚠ TWO searches, not one -- plus the ONE file list both shows share, because
    # `_entry_files` caches per entry for the run.
    assert len(report.shows) == 2 and lab.spent == 3
    for year in (1999, 2011):
        assert lab.resolutions.get(resolution.cache_key(u"frieren", 2, year)) is not None
    assert lab.resolutions.get(resolution.cache_key(u"frieren", 2)) is None


def test_a_folder_where_only_some_names_carry_a_year_is_still_one_show(tmp_path):
    u"""⚠ THE COST OF THE FIX, kept at zero. A year is only allowed to SPLIT a
    show when it tells two apart -- a release where some names carry one and
    some do not is one show, and splitting it would double the metered calls and
    align each half against half a folder."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01 (2011).mkv", u"frieren S2 - 02.mkv"])
    report = lab.run(candidates=1)

    show, = report.shows
    assert show.year == 2011 and len(show.videos) == 2
    assert lab.spent == 2                              # one search, one file list


# ---------------------------------------------------------------------------
# 12. the settings 5a will hand in
# ---------------------------------------------------------------------------

def a_config(tmp_path, text=u""):
    from hato import config
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return config.load(path)


def test_config_supplies_the_defaults_and_the_cli_wins_over_it(tmp_path):
    u"""⭐ *One config, read identically by the CLI, the `.cmd` and the
    scheduler* -- and the flags a person typed win over it. This is the seam 5a
    calls, so it is checked here rather than assumed there."""
    cfg = a_config(tmp_path, u'folders = ["%s"]\ncandidates = 5\nallow_ai = true\n'
                             % str(tmp_path / "lib").replace("\\", "/"))
    settings = pipeline.Settings.from_config(cfg)
    assert settings.folders == (str(tmp_path / "lib"),)
    assert (settings.candidates, settings.allow_ai, settings.lang) == (5, True, u"ja")

    over = pipeline.Settings.from_config(cfg, folders=[tmp_path / "other"],
                                         candidates=1, force=True)
    assert over.folders == (str(tmp_path / "other"),)
    assert (over.candidates, over.force, over.allow_ai) == (1, True, True)


def test_no_folder_anywhere_is_a_config_problem_naming_the_file(tmp_path):
    u"""⛔ Never a run over nothing that reports success."""
    with pytest.raises(pipeline.ConfigProblem) as caught:
        pipeline.Settings.from_config(a_config(tmp_path))
    assert u"config.toml" in str(caught.value)


def test_an_empty_subs_dir_in_config_means_the_documented_default(tmp_path):
    u"""⚠ `subs_dir = ""` is *use `<root>\\subs`*, and `HATO_CACHE` has moved the
    root -- so this proves a test run cannot reach the real one."""
    cfg = a_config(tmp_path, u'folders = ["%s"]\n' % str(tmp_path).replace("\\", "/"))
    settings = pipeline.Settings.from_config(cfg)
    assert settings.subs_dir == str(cfg.subs_dir_resolved)
    assert os.environ["HATO_CACHE"] in settings.subs_dir


# ---------------------------------------------------------------------------
# 13. ⭐ THE REAL ENGINE, THE REAL READER, A REAL VIDEO
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_video(tmp_path_factory):
    u"""A real video whose only subtitle track is ENGLISH -- which is exactly
    the shape hato fetches Japanese for. ⛔ Built in pytest's temp dir; the
    helper refuses the vault outright.

    🚨 `count=67` IS LOAD-BEARING AND IS NOT A TASTE. The harness points
    `TSUBASA_CACHE` at ONE temp root for the whole run, and tsubasa's results DB
    keys a record on the SUBTITLE's content -- MEASURED 2026-09-17: two syncs of
    completely different videos against the same cue text wrote the SAME record
    file, the second overwriting the first. With `_media`'s defaults this
    suite's download would be byte-identical to `test_port.py`'s, so whichever
    ran first claimed the record and *"the store gained exactly one record"*
    went red **in the other suite's file** -- the hardest kind of failure to
    read. A distinct cue count gives a distinct body. `07-test-plan.md` carries
    the rule.
    """
    return _media.build(tmp_path_factory.mktemp("endtoend"),
                        stem=u"frieren S2 - 01", track_language=u"eng", count=67)


def real_lab(built, tmp_path):
    lab = Lab(tmp_path, names=[])
    shutil.copyfile(str(built.video), str(lab.media / built.video.name))
    lab.use_real_engine = True
    body = _media.srt(built.starts, shift=built.shift).encode("utf-8")
    lab.download = lambda item: (lab.downloads.append(item["name"]) or body)
    return lab


def test_the_whole_loop_against_the_real_tsubasa(real_video, tmp_path):
    u"""🚨 THE CHECK THE WHOLE STEP EXISTS FOR.

    Everything above this line believes a stub about what a verdict is. This one
    runs the real client over real captures, the real track reader over a real
    container, and the real `tsubasa.sync()` over a real video -- and asserts the
    four things `03-permissions.md` Whitelist 1 promises a person: the finished
    file is `<video stem>.ja.<ext>` beside the video, the original is kept under
    a `.ja` name in `subs_dir`, ⛔ nothing else appears in the media folder, and
    the next run costs nothing.

    ⚠ The candidate's NAME is jimaku's (an `.ass`) while its BYTES are the
    fixture's SubRip -- Whitelist 2 forbids recording a subtitle body. tsubasa
    reads the content, not the extension (measured), and writes it back in the
    format it came in.
    """
    lab = real_lab(real_video, tmp_path)

    report = lab.run(candidates=1)

    one, = report.results
    assert one.outcome == pipeline.CONFIDENT, one.reason
    assert one.wrote is True
    assert one.tsubasa.verdict_word in (u"locked", u"solid", u"fair", u"uncertain")
    assert one.tsubasa.reference_kind == u"text track"
    assert one.tsubasa.offset == pytest.approx(-real_video.shift, abs=0.5)

    written = Path(one.output_path)
    assert written.parent == lab.media
    assert written.name == u"frieren S2 - 01.ja.ass"
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.ja.ass", u"frieren S2 - 01.mkv"]

    kept = Path(one.kept_path)
    assert kept.is_file()
    assert tsubasa.parse_subtitle_name(kept.name).lang == u"ja"
    assert kept.parent.name == report.shows[0].resolved.entry_name
    assert report.api_calls == 2
    assert report.bytes_downloaded > 0


def test_the_second_real_run_asks_jimaku_nothing(real_video, tmp_path):
    u"""⭐ THE LOOP CLOSED, with nothing stubbed: what tsubasa wrote is what the
    present-check reads, so the second run never opens the container either."""
    lab = real_lab(real_video, tmp_path)
    lab.run(candidates=1)
    lab.downloads = []

    report = lab.run(candidates=1)

    assert lab.spent == 0
    assert lab.downloads == []
    assert report.results[0].skip == pipeline.PRESENT
    assert present.Presence(u"ja").find(lab.media / u"frieren S2 - 01.mkv") is not None


def test_the_real_run_under_out_mirrors_and_leaves_the_media_folder_alone(real_video, tmp_path):
    lab = real_lab(real_video, tmp_path)

    report = lab.run(candidates=1, out=lab.out)

    assert report.results[0].outcome == pipeline.CONFIDENT, report.results[0].reason
    assert Path(report.results[0].output_path).parent == lab.out
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]

    second = lab.run(candidates=1, out=lab.out)
    assert lab.spent == 0
    assert second.results[0].skip == pipeline.PRESENT


def test_a_real_write_that_cannot_land_is_an_ERROR_and_silences_nothing(real_video, tmp_path):
    u"""🚨 THE MEASURED SHAPE, WITH NOTHING STUBBED, AND IT IS THE WHOLE DEFECT.

    A plain FILE is put where the mirrored directory has to go. The real
    `tsubasa.sync()` aligns the pair perfectly and cannot place the result:
    `CONFIDENT`, `write_failed=True`, `match_rate` 1.0, no `output_path`, and a
    reason opening *NOT WRITTEN* that names the file and the fix.

    hato used to mint that as a timing REFUSAL, print *"none held (100% match)"*
    -- a sentence contradicting itself -- and record a soft negative reading
    *"all refused by timing"*, so the video went quiet for a day even once the
    disk was fixed. ⛔ It is an ERROR, it carries tsubasa's words, and it records
    no negative.
    """
    lab = real_lab(real_video, tmp_path)
    # ⚠ The video sits in the scanned root itself, so its mirrored directory IS
    # `--out`. A plain file there is a destination that cannot be made.
    lab.out.write_bytes(b"a file where the mirrored directory has to go")

    report = lab.run(candidates=1, out=lab.out)

    one, = report.results
    assert one.outcome == pipeline.ERROR
    assert u"NOT WRITTEN" in one.reason
    assert one.tsubasa.outcome == port.CONFIDENT       # ⚠ tsubasa is happy with the pair
    assert one.tsubasa.write_failed is True
    assert one.tsubasa.match_rate == pytest.approx(1.0)
    assert one.retry_after is None
    assert lab.rows()[pipeline.NOT_FOUND] == 0        # ⛔ nothing was silenced
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]


def test_both_endings_that_wait_record_the_newest_episode_on_offer(tmp_path):
    u"""⭐ RUNBOOK 8f. The capture's season runs 1-10; episode 11 is one past it.
    Whether it ends NOT_FOUND or all-refused, the newest episode on offer (10)
    is RECORDED with the negative -- `hato problems` reads it from there, after
    the run is gone -- and carried on the row, so the window can say *probably
    not out yet*. ⛔ Nothing is requested or downloaded to know it."""
    lab = Lab(tmp_path, names=episodes_up_to(11))
    refuse_everything(lab)
    report = lab.run(candidates=1)
    rows = lab.by_name(report)

    for name in (u"frieren S2 - 11.mkv", u"frieren S2 - 05.mkv"):
        row = rows[name]
        assert row.outcome in (pipeline.NOT_FOUND, pipeline.REFUSED), (name, row.outcome)
        assert row.newest_offered == 10, (name, row.newest_offered)
        assert report_module.as_dict(row)[u"newest_offered"] == 10, name
        latest, = [p.latest for p in lab.db.problems(u"ja")
                   if p.video_hash == lab.hash_of(name)]
        assert latest.newest_offered == 10, (
            u"%s: the negative did not record it, so the memory would lose it" % name)
    assert pipeline.VideoResult(u"x.mkv", pipeline.CONFIDENT).newest_offered is None


def test_a_not_found_records_the_newest_episode_on_offer(tmp_path):
    u"""⭐ RUNBOOK 8f, the OTHER ending. Episodes 1-10 fit both numberings cleanly
    (0 and +28), and 24 lands on nothing -- a plain NOT_FOUND through
    `_not_found`, which must record the newest on offer too. (24 is fourteen
    past it: recorded, and correctly NOT *probably not out yet*.)"""
    lab = Lab(tmp_path, names=episodes_up_to(10) + [u"frieren S2 - 24.mkv"])
    refuse_everything(lab)
    report = lab.run(candidates=1)
    row = lab.by_name(report)[u"frieren S2 - 24.mkv"]
    assert row.outcome == pipeline.NOT_FOUND and not row.attempts, (
        u"the control: 24 must end NOT_FOUND with nothing tried -- %s, %d tried"
        % (row.outcome, len(row.attempts)))
    assert row.newest_offered == 10, row.newest_offered
    latest, = [p.latest for p in lab.db.problems(u"ja")
               if p.video_hash == lab.hash_of(u"frieren S2 - 24.mkv")]
    assert latest.newest_offered == 10, u"the NOT_FOUND did not record it"


def test_a_run_inside_the_retry_window_carries_the_same_facts_as_hatos_memory(tmp_path):
    u"""ADVERSARY 2026-09-22 A5. The skip a run makes inside the retry window
    reaches the window DURING every run, and it said `candidates_offered: 0`
    with no `newest_offered`: a late episode turned from *"probably not out
    yet"* into a pick with another episode's file OUTLINED, and *Look again*
    claimed every file had been tried. ⭐ The newest on offer is the negative's
    own; how many the entry holds is UNKNOWN -- this run never listed it."""
    lab = Lab(tmp_path, names=episodes_up_to(11))
    refuse_everything(lab)
    first = lab.by_name(lab.run(candidates=1))[u"frieren S2 - 11.mkv"]
    assert first.newest_offered == 10, u"the control: run 1 knew the newest on offer"
    lab.now[0] += timedelta(hours=1)                   # inside the 24-hour wait
    row = lab.by_name(lab.run(candidates=1))[u"frieren S2 - 11.mkv"]
    assert row.skip == pipeline.NEGATIVE, u"the control: run 2 skips it, waiting"
    said = report_module.as_dict(row)
    assert said[u"newest_offered"] == 10, (
        u"the run's copy of a late episode lost *probably not out yet*: %r"
        % said[u"newest_offered"])
    assert said[u"candidates_offered"] is None, (
        u"a run that never listed the entry said it offered %r files"
        % said[u"candidates_offered"])


# ---------------------------------------------------------------------------
# ⭐ 9a -- the person's format, RULED 2026-09-23
# ---------------------------------------------------------------------------
# *"even if you prefer one, if it isn't checked, then it won't download the
# other kind."* The recorded list offers every episode in BOTH formats, so an
# episode offered in one only is made by cutting the list -- everything metered
# is still the real client over the real recording.

class OneFormat(ListForAnyEntry):
    u"""DERIVED: the recorded file list, cut to one format."""

    def __init__(self, inner, ext):
        ListForAnyEntry.__init__(self, inner)
        self.ext = ext

    def files(self, entry_id):
        self.entries.append(entry_id)
        return [f for f in self._inner.files(entry_id)
                if f["name"].lower().endswith(u"." + self.ext)]


def test_with_the_fallback_off_an_episode_only_in_the_other_format_is_not_downloaded(
        tmp_path):
    u"""⛔ NOTHING downloaded, and the reason says it IS on jimaku -- never *"has
    no file for this episode"*, which would be false. A wait all the same: the
    preferred kind may yet be uploaded."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.client = OneFormat(lab.real, u"srt")
    row, = lab.run(format_fallback=False).results

    assert row.outcome == pipeline.NOT_FOUND and lab.downloads == [], (row, lab.downloads)
    assert row.reason.startswith(u"only as .srt on jimaku -- you prefer .ass"), row.reason
    assert u"If there is no .ass, download .srt" in row.reason
    assert u"has no file for this episode" not in row.reason
    assert row.retry_after is not None
    waiting = lab.db.negative(lab.hash_of(u"frieren S2 - 01.mkv"), u"ja")
    assert formats.only_as(waiting.reason) == (u"srt",), waiting.reason


def test_turning_the_fallback_on_takes_it_at_the_next_run_not_tomorrow(tmp_path):
    u"""⭐ THE SWITCH MUST DO SOMETHING. The wait was recorded because every file
    was the other kind; a person who turns the fallback on and is told
    *"tomorrow"* has a setting that did nothing. Two arms, the same hour: left
    off, the wait stands (zero requests); turned on, the .srt is fetched."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.client = OneFormat(lab.real, u"srt")
    lab.run(format_fallback=False)
    lab.now[0] += timedelta(hours=1)

    still, = lab.run(format_fallback=False).results                     # arm 1
    assert still.skip == pipeline.NEGATIVE and lab.downloads == [], still
    assert lab.spent == 0

    taken, = lab.run(format_fallback=True).results                      # arm 2
    assert taken.outcome == pipeline.CONFIDENT, taken.reason
    assert lab.downloads and all(n.endswith(u".srt") for n in lab.downloads), lab.downloads


def test_choosing_the_other_preference_takes_it_too(tmp_path):
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.client = OneFormat(lab.real, u"srt")
    lab.run(format_fallback=False)
    lab.now[0] += timedelta(hours=1)
    taken, = lab.run(prefer_format=u"srt", format_fallback=False).results
    assert taken.outcome == pipeline.CONFIDENT, taken.reason


def test_a_wait_for_anything_else_is_not_ended_by_the_format_setting(tmp_path):
    u"""⛔ Only the format wait is looked past. Episode 24 is not on jimaku at
    all; turning the fallback on changes nothing about that, and must not spend
    a request finding out again."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 24.mkv"])
    first, = lab.run(format_fallback=False).results
    assert first.outcome == pipeline.NOT_FOUND and formats.only_as(first.reason) is None
    lab.now[0] += timedelta(hours=1)
    again, = lab.run(format_fallback=True).results
    assert again.skip == pipeline.NEGATIVE and lab.spent == 0, again


def test_with_the_fallback_off_only_the_preferred_kind_is_ever_tried(tmp_path):
    u"""The whole list, both kinds, every candidate refused: with the fallback off
    only `.ass` files were downloaded; ON -- the control -- the `.srt` ones follow
    them, in 1.0.2's order. And with `.srt` preferred it is `.srt` only."""
    for fallback, prefer, allowed in ((False, u"ass", (u".ass",)),
                                      (True, u"ass", (u".ass", u".srt")),
                                      (False, u"srt", (u".srt",))):
        lab = Lab(tmp_path / (u"%s-%s" % (prefer, fallback)), names=episodes_up_to(1))
        refuse_everything(lab)
        lab.run(candidates=5, prefer_format=prefer, format_fallback=fallback)
        kinds = [os.path.splitext(n)[1] for n in lab.downloads]
        assert kinds and set(kinds) == set(allowed), (prefer, fallback, lab.downloads)
        assert kinds[0] == allowed[0], (prefer, fallback, lab.downloads)


def test_the_plan_never_counts_the_other_format_as_not_on_jimaku(tmp_path):
    u"""`--dry-run`'s summary line. Two arms: only `.srt` on offer -> *"only in the
    other format"*; episode 24, which jimaku really lacks -> *"not on jimaku"*."""
    lab = Lab(tmp_path / u"srt-only", names=episodes_up_to(1))
    def plan_of(report):
        # ⚠ FLAT: the plan wraps, and a phrase split across two indented lines is
        # a check asserting the wrapping as well as the words.
        return u" ".join(u" ".join(report_module.render_plan(report)).split())

    lab.client = OneFormat(lab.real, u"srt")
    plan = plan_of(lab.run(format_fallback=False, dry_run=True))
    assert u"1 only in the other format" in plan and u"not on jimaku" not in plan, plan

    lab = Lab(tmp_path / u"missing", names=[u"frieren S2 - 24.mkv"])
    plan = plan_of(lab.run(format_fallback=False, dry_run=True))
    assert u"1 not on jimaku" in plan and u"other format" not in plan, plan


def test_the_format_settings_reach_the_run_from_config_toml(tmp_path):
    u"""The road a real run takes: `config.toml` -> `Settings.from_config`."""
    cfg = config.parse(u"folders = ['%s']\nprefer_format = 'srt'\nformat_fallback = true\n"
                       % str(tmp_path).replace(u"\\", u"/"))
    s = pipeline.Settings.from_config(cfg)
    assert (s.prefer_format, s.format_fallback) == (u"srt", True)
    s = pipeline.Settings.from_config(config.parse(u"folders = ['%s']\n"
                                                   % str(tmp_path).replace(u"\\", u"/")))
    assert (s.prefer_format, s.format_fallback) == (u"ass", False)


# ---------------------------------------------------------------------------
# ⭐ 9a's adversarial pass, 2026-09-23 -- `ADVERSARY-2026-09-23.md`, one check
# per finding, each shaped as the adversary's own probe was
# ---------------------------------------------------------------------------

class WrongEntryOnlySrt(ListForAnyEntry):
    u"""DERIVED: every other entry answers with the capture's `.srt` files,
    RENAMED -- a wrong season's entry that happens to carry only `.srt`, while
    the right one (the runner-up) carries the `.ass`."""

    def files(self, entry_id):
        self.entries.append(entry_id)
        real = self._inner.files(ENTRY)
        if entry_id == ENTRY:
            return real
        return [dict(f, name=WRONG_SEASON + f["name"]) for f in real
                if f["name"].lower().endswith(u".srt")]


def test_an_entry_offering_only_the_other_format_is_escalated_past(tmp_path):
    u"""🚨 #2a -- with the fallback off the wrong season's `.srt` counted as an
    OFFER: nothing escalated, the wait described the wrong season's files, and
    the wrong entry was still the one cached two days later. Two arms, one
    library: ON (the control) tries the `.srt`, is refused, and moves on; OFF
    now moves on without downloading any of it."""
    for fallback in (True, False):
        lab = Lab(tmp_path / (u"fallback-%s" % fallback), names=[u"frieren - 31.mkv"])
        lab.client = WrongEntryOnlySrt(lab.real)
        lab.decide = lambda name: (
            {"outcome": port.REFUSED, "reason": u"the timing does not hold"}
            if name.startswith(WRONG_SEASON) else {"outcome": port.CONFIDENT})
        report = lab.run(candidates=2, format_fallback=fallback)
        row, = report.results
        show, = report.shows
        assert lab.client.entries[0] != ENTRY, u"the wrong entry has to be tried FIRST"
        assert row.outcome == pipeline.CONFIDENT and row.output_path.endswith(u".ass"), (
            fallback, row.outcome, row.reason)
        assert lab.resolutions.get(resolution.cache_key(u"frieren")).entry_id == ENTRY, fallback
    assert not [n for n in lab.downloads if n.startswith(WRONG_SEASON)], lab.downloads
    assert [n for n in show.notes if u"in a format your settings take" in n], show.notes


class OnlySrtEverywhere(ListForAnyEntry):
    u"""DERIVED: every entry answers with the capture's `.srt` files, nothing else."""

    def files(self, entry_id):
        self.entries.append(entry_id)
        return [f for f in self._inner.files(ENTRY) if f["name"].lower().endswith(u".srt")]


def test_an_alternate_offering_only_the_other_format_is_not_adopted_either(tmp_path):
    u"""#2a's other half: LOOKING at the next entry is right, ADOPTING one that also
    offers only the other format is not -- the cache would be repointed at an entry
    no better than the first. Every entry here has only `.srt`: the run looks,
    adopts nothing, and waits on the entry it identified."""
    lab = Lab(tmp_path, names=[u"frieren - 31.mkv"])
    lab.client = OnlySrtEverywhere(lab.real)
    report = lab.run(format_fallback=False)
    row, = report.results
    show, = report.shows
    first = lab.client.entries[0]
    assert first != ENTRY and ENTRY in lab.client.entries, (
        u"the alternate has to be LOOKED at, or this proves nothing", lab.client.entries)
    assert row.outcome == pipeline.NOT_FOUND and formats.only_as(row.reason) == (u"srt",), (
        row.outcome, row.reason)
    assert lab.resolutions.get(resolution.cache_key(u"frieren")).entry_id == first
    assert not [n for n in show.notes if u"held nothing" in n], show.notes


def _pack(member, body):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, body)
    return buf.getvalue()


ASS_BODY = (u"[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer, Start, End, "
            u"Style, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,日本語\n").encode("utf-8")
SRT_BODY = u"1\n00:00:01,000 --> 00:00:03,000\n日本語\n\n".encode("utf-8")


class ArchiveAndPlain(OneArchiveOnTheEntry):
    u"""DERIVED: one batch archive AND these plain files on the entry."""

    def __init__(self, inner, blob, plain):
        OneArchiveOnTheEntry.__init__(self, inner, blob)
        self.plain = list(plain)

    def files(self, entry_id):
        listed = OneArchiveOnTheEntry.files(self, entry_id)
        return listed + [{"name": n, "size": 1234,
                          "url": u"https://jimaku.cc/entry/11446/download/%s" % n,
                          "last_modified": u"2026-01-01T00:00:00Z"} for n in self.plain]


def _serving(lab):
    u"""The `downloader=` seam hands out the client's archive bytes, and counts
    each time -- ⚠ bytes come from the seam, never from the client."""
    plain = lab.download

    def download(item):
        if item["name"] == lab.client.name:
            lab.downloads.append(item["name"])
            return lab.client.blob
        return plain(item)
    lab.download = download


def test_an_archive_holding_the_preferred_format_is_opened_beside_other_plain_files(tmp_path):
    u"""🚨 #2b -- archives ON, `.ass` preferred: the plain files offer the episode
    only as `.srt`, and the batch archive holds its `.ass`. It was never opened,
    because the video counted as served. Two arms: no plain file (the control,
    opened before and after); a plain `.srt` beside it (opened now)."""
    member = u"[Grp] frieren S2 - 03 (1080p) [ABCD].ja.ass"
    for plain in ([], [u"[Other] frieren S2 - 03 (WEB 1080p).srt"]):
        lab = Lab(tmp_path / (u"plain-%d" % len(plain)), names=[u"frieren S2 - 03.mkv"])
        lab.client = ArchiveAndPlain(lab.real, _pack(member, ASS_BODY), plain)
        _serving(lab)
        row, = lab.run(archives=True, format_fallback=False).results
        assert row.outcome == pipeline.CONFIDENT and row.jimaku_filename == member, (
            plain, row.outcome, row.reason, lab.downloads)
        assert not [n for n in lab.downloads if n.endswith(u".srt")], lab.downloads


def test_an_archive_whose_members_land_nowhere_says_so(tmp_path):
    u"""⚠ The pass now opens an archive for a video the plain files reach in the
    other format -- and `trial` holds those plain files too, so *"is the video in
    it"* was true whatever the archive held, and the note said the archive was
    used. Its only member here carries no episode number: it lands on nothing,
    and the note says exactly that."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 03.mkv"])
    lab.client = ArchiveAndPlain(lab.real, _pack(u"[Grp] Frieren Bonus (1080p).ja.ass", ASS_BODY),
                                 [u"[Other] frieren S2 - 03 (WEB 1080p).srt"])
    _serving(lab)
    report = lab.run(archives=True, format_fallback=False)
    row, = report.results
    show, = report.shows
    assert lab.downloads.count(lab.client.name) == 1, u"the archive has to be OPENED"
    assert [n for n in show.notes if u"none of them lands" in n], show.notes
    assert not [n for n in show.notes if u"was opened because" in n], show.notes
    assert row.outcome == pipeline.NOT_FOUND and formats.only_as(row.reason) == (u"srt",), (
        row.outcome, row.reason)


def test_an_archive_already_in_the_cache_is_not_downloaded_again(tmp_path):
    u"""🚨 #2c -- a video an archive cannot serve comes back at every retry, and
    each retry downloaded the whole archive again to learn the same thing:
    measured 1, 2, 3, 4 over four days. Its only member is `.srt`, `.ass` is
    preferred, the fallback is off: a format wait every day, and ONE download.
    ⭐ The other arm: a re-upload -- new bytes, a new size -- IS fetched."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 03.mkv"])
    lab.client = OneArchiveOnTheEntry(
        lab.real, _pack(u"[Grp] frieren S2 - 03 (1080p) [ABCD].ja.srt", SRT_BODY))
    _serving(lab)
    for day in range(4):
        row, = lab.run(archives=True, format_fallback=False).results
        assert row.outcome == pipeline.NOT_FOUND and formats.only_as(row.reason) == (u"srt",), (
            day, row.outcome, row.skip, row.reason)
        lab.now[0] += timedelta(hours=25)
    assert lab.downloads.count(lab.client.name) == 1, lab.downloads

    lab.client.blob = _pack(u"[Grp] frieren S2 - 03 (1080p) [ABCD] v2.ja.srt", SRT_BODY * 3)
    lab.run(archives=True, format_fallback=False)
    assert lab.downloads.count(lab.client.name) == 2, (u"a re-upload was never fetched",
                                                       lab.downloads)


def test_a_re_sync_never_writes_a_format_the_person_stopped_taking(tmp_path):
    u"""🚨 #3 -- `.ass` written and its original kept; the person chose `.srt` and
    deleted the `.ass`. The next run re-timed the kept `.ass` straight back, and
    the present-check said *already there* from then on. Two arms: the
    preference unchanged is the zero-network re-sync (the control); `.srt`
    preferred is a fetch of the `.srt`."""
    for prefer, kind, fetches in ((u"ass", u".ass", False), (u"srt", u".srt", True)):
        lab = Lab(tmp_path / prefer, names=episodes_up_to(1))
        first, = lab.run(format_fallback=False).results
        assert first.outcome == pipeline.CONFIDENT and first.output_path.endswith(u".ass")
        lab.forget_videos()
        del lab.downloads[:]
        again, = lab.run(prefer_format=prefer, format_fallback=False).results
        assert again.outcome == pipeline.CONFIDENT and again.output_path.endswith(kind), (
            prefer, again.outcome, again.reason, again.output_path)
        assert bool(lab.downloads) is fetches, (prefer, lab.downloads)
        assert all(n.endswith(kind) for n in lab.downloads), lab.downloads


class SrtAndVtt(ListForAnyEntry):
    u"""DERIVED: the capture cut to `.srt`, three of episode 1's renamed `.vtt` --
    an episode jimaku has in TWO kinds, neither of them `.ass`."""

    def files(self, entry_id):
        self.entries.append(entry_id)
        out, n = [], 0
        for f in self._inner.files(ENTRY):
            if not f["name"].lower().endswith(u".srt"):
                continue
            if u"01" in f["name"] and n < 3:
                f, n = dict(f, name=f["name"][:-4] + u".vtt"), n + 1
            out.append(f)
        return out


def test_a_wait_in_two_formats_names_both_and_either_ends_it(tmp_path):
    u"""🚨 #4 -- *"only as .vtt"* over two `.srt` and three `.vtt`: false, and a
    person who then chose `.srt` was still waiting an hour later, at zero
    requests, while the window offered them *Download .vtt instead*."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    lab.client = SrtAndVtt(lab.real)
    first, = lab.run(format_fallback=False).results
    assert first.outcome == pipeline.NOT_FOUND, first
    assert formats.only_as(first.reason) == (u"srt", u"vtt"), first.reason
    assert u"(5 files)" in first.reason, first.reason
    lab.now[0] += timedelta(hours=1)
    taken, = lab.run(prefer_format=u"srt", format_fallback=False).results
    assert taken.outcome == pipeline.CONFIDENT, (taken.skip, taken.reason)
    assert lab.downloads and all(n.endswith(u".srt") for n in lab.downloads), lab.downloads


def test_mode_a_never_calls_a_format_wait_not_found_or_not_there(tmp_path):
    u"""🚨 #7 -- the printed run said *"NOT FOUND"* and *"1 not found"* on the run
    that found it, and *"asked for recently and not there yet -- --force asks
    again now"* inside the wait: it IS there, and `--force` finds the same wait.
    Two arms each time: an episode jimaku really lacks still says so."""
    def text(report):
        return u" ".join(u" ".join(report_module.render_run(report)).split())

    lab = Lab(tmp_path / u"srt-only", names=episodes_up_to(1))
    lab.client = OneFormat(lab.real, u"srt")
    first = text(lab.run(format_fallback=False))
    assert u"OTHER FORMAT" in first and u"1 only in the other format" in first, first
    assert u"NOT FOUND" not in first and u"not found" not in first, first
    lab.now[0] += timedelta(hours=1)
    inside = text(lab.run(format_fallback=False))
    assert u"only in a format your settings do not take" in inside, inside
    assert u"not there yet" not in inside and u"waiting to retry" not in inside, inside

    lab = Lab(tmp_path / u"missing", names=[u"frieren S2 - 24.mkv"])
    first = text(lab.run(format_fallback=False))
    assert u"NOT FOUND" in first and u"1 not found" in first and u"format" not in first, first
    lab.now[0] += timedelta(hours=1)
    inside = text(lab.run(format_fallback=False))
    assert u"not there yet" in inside and u"format" not in inside, inside


def test_a_film_offered_only_as_an_archive_is_never_downloaded_as_a_subtitle(tmp_path):
    u"""🚨 #10 -- a film jimaku has only as its `.sup.7z`: the archive was a
    candidate, downloaded unopened, handed to tsubasa, refused at 0% -- and 9a
    called it *"the other format"*, with a button to download it. Now nothing is
    downloaded, the reason says why, and it is no format wait."""
    class OnlyTheArchive(ListForAnyEntry):
        def files(self, entry_id):
            self.entries.append(entry_id)
            return [f for f in self._inner.files(entry_id) if archives.is_archive(f["name"])]

    lab = Lab(tmp_path, names=[u"Kimi no Na wa.mkv"])
    lab.client = OnlyTheArchive(lab.real)
    report = lab.run(format_fallback=False)
    row, = report.results
    assert report.shows[0].resolved.movie is True
    assert lab.downloads == [], lab.downloads
    assert row.outcome == pipeline.NOT_FOUND and formats.only_as(row.reason) is None, row.reason
    assert u"no subtitle file" in row.reason, row.reason


def test_an_opened_archive_is_never_said_to_be_unopened(tmp_path):
    u"""⚠ Beside 9a: *"1 archive(s) on this entry were NOT opened"* was printed over
    the archive the same run had just opened. Two arms: ON and opened -> not
    said; OFF -> said, naming the key (the existing check holds the words)."""
    member = u"[Grp] frieren S2 - 03 (1080p) [ABCD].ja.ass"
    for on in (True, False):
        lab = Lab(tmp_path / (u"on-%s" % on), names=[u"frieren S2 - 03.mkv"])
        lab.client = OneArchiveOnTheEntry(lab.real, _pack(member, ASS_BODY))
        _serving(lab)
        show, = lab.run(archives=on).shows
        said = [n for n in show.notes if u"were NOT opened" in n]
        assert bool(said) is not on, (on, show.notes)
    assert u"archives = true" in said[0], said


def _failing_downloads(lab, failing):
    plain = lab.download

    def download(item):
        if failing(item["name"]):
            lab.downloads.append(item["name"])
            raise client_module.DownloadError(u"HTTP 503", status=503)
        return plain(item)
    lab.download = download


def test_a_download_that_failed_is_never_called_a_timing_refusal(tmp_path):
    u"""🚨 Beside 9a: every candidate failing to DOWNLOAD read *"N candidates fetched
    and retimed, none held"* and was recorded *"all refused by timing"* -- two
    false sentences, and a day's quiet for files nobody looked at. An ERROR now,
    with NO wait: the next run, the same hour, simply tries again."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _failing_downloads(lab, lambda name: True)
    row, = lab.run(candidates=2).results
    assert row.outcome == pipeline.ERROR, (row.outcome, row.reason)
    assert u"could not be downloaded, so none was timed" in row.reason, row.reason
    assert u"retimed" not in row.reason and u"refused" not in row.reason, row.reason
    assert lab.db.negative(lab.hash_of(u"frieren S2 - 01.mkv"), u"ja") is None
    tried = len(lab.downloads)
    lab.now[0] += timedelta(minutes=5)
    lab.run(candidates=2)
    assert len(lab.downloads) > tried, u"the next run did not try again"


def test_some_failed_downloads_and_some_refusals_are_each_counted_as_what_they_were(tmp_path):
    u"""The mixed case stays a refusal -- the timed file WAS refused -- but neither
    half is called the other."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    first = []

    def fails_first(name):
        if not first:
            first.append(name)
        return name == first[0]
    _failing_downloads(lab, fails_first)
    lab.decide = lambda name: dict(outcome=port.REFUSED, reason=u"no", match_rate=0.2)
    row, = lab.run(candidates=2).results
    assert row.outcome == pipeline.REFUSED, (row.outcome, row.reason)
    assert row.reason.startswith(u"1 candidate fetched and retimed, none held"), row.reason
    assert u"1 more could not be downloaded" in row.reason, row.reason
    waiting = lab.db.negative(lab.hash_of(u"frieren S2 - 01.mkv"), u"ja")
    assert u"1 refused by timing, 1 could not be downloaded" in waiting.reason, waiting.reason


# ---------------------------------------------------------------------------
# ⭐ LAYER 14c -- *"Save them beside the video, as a file"* (RUNBOOK 14c)
# ---------------------------------------------------------------------------
# Ruled by Sonic 2026-09-25 (*"I take all your leans. Go"*): the video's own Japanese
# track TAKEN OUT and written beside it by tsubasa -- hato's only write in a media
# folder is tsubasa's (Whitelist 1) -- never converted, never over a file that is
# there; the row *"taken from the video"*; and a video it cannot be taken out of is
# downloaded for instead, its row saying why.

def _save(lab, name, tracks, **takes):
    u"""`name`'s container holds `tracks`; its extraction comes out as `takes` says."""
    lab.tracks[name] = Answer(tracks=tracks)
    if takes:
        lab.takes[name] = takes


def test_saving_takes_the_japanese_track_out_and_writes_it_beside_the_video(tmp_path):
    u"""⭐ The choice, end to end through the seam: tsubasa asked to WRITE, into the
    folder the present-check reads; the row CONFIDENT with the file and the track
    it came from; ⛔ no request, no download, no row in the state DB -- and the next
    run finds the file and asks nothing at all."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)])

    one, = lab.run(extract_embedded=True, skip_embedded=False).results

    assert one.outcome == pipeline.CONFIDENT, one.reason
    assert one.wrote and one.skip is None
    assert Path(one.output_path) == lab.media / u"frieren S2 - 01.ja.ass"
    assert Path(one.output_path).is_file()
    assert one.taken_from == {u"track": 3, u"codec": u"S_TEXT/ASS", u"format": u"ass",
                              u"name": None, u"events": 412}, one.taken_from
    assert lab.extracted == [(u"frieren S2 - 01.mkv", 3, True, str(lab.media))], lab.extracted
    assert lab.spent == 0 and lab.downloads == []
    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}, (
        u"a subtitle taken out is recorded nowhere but on disk")
    wire = report_module.as_dict(one)
    assert wire[u"taken_from"][u"track"] == 3 and wire[u"not_taken"] is None

    again, = lab.run(extract_embedded=True, skip_embedded=False).results
    assert again.skip == pipeline.PRESENT, (again.outcome, again.reason)
    assert len(lab.extracted) == 1, u"the second run took it out again"


def test_saving_copies_the_file_to_surasura_as_every_written_subtitle_is(tmp_path):
    u"""⭐ Ruled with the choice: *"copied to surasura"* -- the reason anybody asks for
    a file at all. ⛔ Through the one funnel every written subtitle passes."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS")])
    surasura = tmp_path / u"surasura"

    one, = lab.run(extract_embedded=True, surasura_dir=surasura).results

    assert one.wrote, one.reason
    copied = surasura / keep.SURASURA_FOLDER / u"frieren S2 - 01.ja.ass"
    assert copied.is_file(), u"the saved subtitle never reached surasura"
    assert copied.read_bytes() == Path(one.output_path).read_bytes()


def test_a_video_it_cannot_be_taken_out_of_is_downloaded_for_and_says_why(tmp_path):
    u"""⭐ Ruled: *"a video hato cannot take subtitles out of (not MKV) is downloaded for
    instead, and its row says why."* tsubasa's own reason, on the row of the download
    -- through `--json` too, which is what the window reads."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mp4"])
    why = (u"frieren S2 - 01.mp4 is an MP4 file -- its subtitles have no file format of "
           u"their own, so taking them out would mean CONVERTING them")
    _save(lab, u"frieren S2 - 01.mp4", [Track(lang=u"ja", codec=u"S_TEXT/UTF8")],
          ok=False, reason=why)

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.CONFIDENT, one.reason
    assert one.taken_from is None
    assert lab.downloads, u"nothing was downloaded for a video that could not be taken out"
    assert one.not_taken == why, one.not_taken
    assert report_module.as_dict(one)[u"not_taken"] == why


def test_a_download_that_fails_after_it_still_says_why_it_was_downloaded(tmp_path):
    u"""The reason rides on WHICHEVER row the download ends in -- here a refusal,
    which is where a person looks hardest for why hato went to jimaku at all."""
    lab = Lab(tmp_path, names=[u"frieren S2 - 01.mp4"])
    _save(lab, u"frieren S2 - 01.mp4", [Track(lang=u"ja")], ok=False,
          reason=u"not a Matroska (MKV) file")
    refuse_everything(lab)

    one, = lab.run(extract_embedded=True, candidates=1).results

    assert one.outcome == pipeline.REFUSED, (one.outcome, one.reason)
    assert one.not_taken == u"not a Matroska (MKV) file"


def test_a_forced_japanese_track_is_never_taken_out(tmp_path):
    u"""⛔ Signs and songs only, not a whole subtitle (06 §6) -- and saved, it is
    `<video>.ja.forced.<ext>`, which the present-check rightly never counts: every
    later run would take it out again and be refused over its own file. Nothing is
    asked of tsubasa; the video is downloaded for, and says so."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    signs = Track(lang=u"ja", codec=u"S_TEXT/ASS")
    signs.forced = True
    _save(lab, u"frieren S2 - 01.mkv", [signs])

    one, = lab.run(extract_embedded=True).results

    assert lab.extracted == [], u"a forced track was handed to tsubasa to take out"
    assert one.outcome == pipeline.CONFIDENT and lab.downloads, one.reason
    assert u"FORCED" in (one.not_taken or u""), one.not_taken


def test_a_saved_file_that_could_not_be_written_is_an_error_that_records_nothing(tmp_path):
    u"""🚨 `LEDGER-HOT.md`: never turn a failed WRITE into a refusal. The subtitles came
    out; the destination failed -- and a download would be written to the same place.
    ERROR, tsubasa's words, no negative, nothing downloaded -- the next run tries again."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja")],
          fails_to_write=u"frieren S2 - 01.ja.ass could not be written: [Errno 28] "
                         u"No space left on device")

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.ERROR, (one.outcome, one.reason)
    assert u"taken out, but not saved" in one.reason, one.reason
    assert u"No space left" in one.reason, one.reason
    assert one.retry_after is None and lab.downloads == []
    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}


def test_a_dry_run_says_it_would_take_them_out_and_writes_nothing(tmp_path):
    u"""⛔ A dry run writes nothing -- ⭐ 14z (C5) AND READS NOTHING BUT THE HEADER.
    tsubasa's take-out walks the whole file (6.8 s and 216 MB for one 1.45 GB
    episode, cold), so a plan asks it nothing: codec, flag and language are in the
    header, and the lines only the walk can count are not claimed."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS")])

    one, = lab.run(extract_embedded=True, dry_run=True).results

    assert one.outcome == pipeline.PLANNED, (one.outcome, one.reason)
    assert u"would take" in one.reason and u"nothing downloaded" in one.reason, one.reason
    assert one.taken_from and one.taken_from[u"format"] == u"ass"
    assert one.taken_from[u"events"] is None, u"a plan claimed lines only the walk counts"
    assert lab.extracted == [], u"a dry run asked tsubasa to walk the track"
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]


def test_a_file_that_says_both_saves(tmp_path):
    u"""⭐ `formats.embedded_choice`: `extract_embedded` WINS. The window writes both
    keys together; a file saying both -- by hand -- asks for the more particular
    thing, and the run, the window and `hato problems` read it alike."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja")])

    one, = lab.run(extract_embedded=True, skip_embedded=True).results

    assert one.skip is None and one.taken_from, (one.outcome, one.skip, one.reason)
    assert formats.embedded_choice(True, True) == formats.EMBEDDED_SAVE
    assert formats.embedded_choice(True, False) == formats.EMBEDDED_LEAVE
    assert formats.embedded_choice(False, False) == formats.EMBEDDED_FETCH


def test_the_preferred_format_is_taken_out_first(tmp_path):
    u"""Two whole Japanese tracks -- an `.srt` the file marks default, and an `.ass`.
    ⭐ The person's format preference first (Settings → Subtitle format), then the
    file's default: `.ass` preferred takes track 3, `.srt` preferred takes track 2."""
    for prefer, want in ((u"ass", 3), (u"srt", 2)):
        lab = Lab(tmp_path / prefer, names=episodes_up_to(1))
        plain = Track(lang=u"ja", codec=u"S_TEXT/UTF8", index=2)
        plain.default = True
        styled = Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)
        _save(lab, u"frieren S2 - 01.mkv", [plain, styled])
        one, = lab.run(extract_embedded=True, prefer_format=prefer).results
        assert one.taken_from[u"track"] == want, (prefer, one.taken_from)


def test_a_track_tsubasa_refuses_gives_way_to_the_next_one(tmp_path):
    u"""A WebVTT track first and an `.ass` after it: the first is refused by name and
    the second taken out. ⭐ And when every one is refused, the reason on the row is
    the one for the track wanted most."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    vtt = Track(lang=u"ja", codec=u"S_TEXT/WEBVTT", index=2)
    ass = Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)
    _save(lab, u"frieren S2 - 01.mkv", [vtt, ass], refuse={2: u"a WebVTT track"})

    one, = lab.run(extract_embedded=True, prefer_format=u"srt").results

    assert one.taken_from and one.taken_from[u"track"] == 3, (one.outcome, one.reason)
    lab2 = Lab(tmp_path / u"all", names=episodes_up_to(1))
    _save(lab2, u"frieren S2 - 01.mkv", [vtt, ass],
          refuse={2: u"a WebVTT track", 3: u"laced"})
    two, = lab2.run(extract_embedded=True, prefer_format=u"srt").results
    assert two.not_taken == u"a WebVTT track", two.not_taken


def test_under_out_the_file_is_saved_in_the_mirrored_folder(tmp_path):
    u"""⭐ The present-check and the write ask ONE function (`keep.target_dir`): under
    `--out` the file goes to the mirror, the media folder is left alone, and the
    second run finds it there."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja")])

    one, = lab.run(extract_embedded=True, out=lab.out).results

    assert Path(one.output_path).parent == lab.out, one.output_path
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.mkv"]
    assert lab.run(extract_embedded=True, out=lab.out).results[0].skip == pipeline.PRESENT


def test_a_tsubasa_that_cannot_take_them_out_downloads_and_says_so(tmp_path, monkeypatch):
    u"""⚠ A source checkout on a tsubasa from before 0.1.9: the floor is what pip was
    told, not what is on the path. The choice downloads and the row names the fix."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja")])
    monkeypatch.delattr(tsubasa, u"extract_subtitle", raising=False)
    lab.extractor = None

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.CONFIDENT and lab.downloads, one.reason
    assert u"0.1.9 can" in (one.not_taken or u""), one.not_taken


@pytest.fixture(scope="module")
def japanese_video(tmp_path_factory):
    u"""A real video whose only subtitle track is JAPANESE -- `S_TEXT/UTF8`, tagged
    `jpn`. ⚠ Its own cue count (71): see `real_video`'s note on tsubasa's store."""
    return _media.build(tmp_path_factory.mktemp("inside"), stem=u"frieren S2 - 01",
                        track_language=u"jpn", count=71)


def test_saving_with_the_real_tsubasa_takes_the_real_track_out(japanese_video, tmp_path):
    u"""🚨 NOTHING STUBBED: the real reader finds the Japanese track, the real
    `tsubasa.extract_subtitle` takes it out of the real container and writes
    `<video>.ja.srt` -- ⛔ an `.srt` track stays `.srt` -- with every cue the video
    was muxed with, and the second run's present-check finds it and asks nothing."""
    lab = real_lab(japanese_video, tmp_path)

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.CONFIDENT, one.reason
    written = Path(one.output_path)
    assert written == lab.media / u"frieren S2 - 01.ja.srt", written
    assert lab.names_in(lab.media) == [u"frieren S2 - 01.ja.srt", u"frieren S2 - 01.mkv"]
    text = written.read_text(encoding=u"utf-8")
    assert text.count(u"-->") == 71, text[:400]
    for n in (1, 36, 71):
        assert (u"行 %d" % n) in text, n
    assert one.taken_from[u"format"] == u"srt" and one.taken_from[u"events"] == 71
    assert lab.spent == 0 and lab.downloads == []

    again, = lab.run(extract_embedded=True).results
    assert again.skip == pipeline.PRESENT, (again.outcome, again.reason)
    assert lab.spent == 0

def _mode_a(report):
    u"""Mode A, flat -- a phrase split across two wrapped lines is still found."""
    return u" ".join(u" ".join(report_module.render_run(report)).split())


def test_the_printed_run_says_taken_out_of_the_video_and_never_a_percentage(tmp_path):
    u"""⭐ Mode A (ruled): the row says where the subtitle came from -- *taken out ·
    track 3* -- and the file; ⛔ no percentage and no verdict (nothing was timed), and
    the summary never calls it *fetched*: nothing was. ⚠ The ENGINE's counts stay
    CONFIDENT -- `api.py` and `--json` read them as the engine's."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)])
    report = lab.run(extract_embedded=True)
    shown = _mode_a(report)
    assert u"⊡ video taken out · track 3 → frieren S2 - 01.ja.ass" in shown, shown
    assert u"1 taken from the video" in shown and u"fetched" not in shown, shown
    assert u"%" not in shown, shown
    assert dict(report.counts()) == {pipeline.CONFIDENT: 1}, report.counts()


def test_the_printed_run_says_why_a_video_was_not_taken_out(tmp_path):
    u"""⭐ Ruled: *"its row says why"* -- under the download's own row in Mode A, a
    success and a refusal alike."""
    lab = Lab(tmp_path / u"fetched", names=[u"frieren S2 - 01.mp4"])
    _save(lab, u"frieren S2 - 01.mp4", [Track(lang=u"ja")], ok=False, reason=u"an MP4 file.")
    shown = _mode_a(lab.run(extract_embedded=True))
    assert u"could not be taken out (an MP4 file), so jimaku was asked instead" in shown, shown
    assert u"1 fetched" in shown, shown
    lab = Lab(tmp_path / u"refused", names=[u"frieren S2 - 01.mp4"])
    _save(lab, u"frieren S2 - 01.mp4", [Track(lang=u"ja")], ok=False, reason=u"an MP4 file")
    refuse_everything(lab)
    shown = _mode_a(lab.run(extract_embedded=True, candidates=1))
    assert u"REFUSED" in shown and u"could not be taken out (an MP4 file)" in shown, shown


def test_the_plan_counts_a_track_to_take_out_apart_and_it_costs_no_call(tmp_path):
    u"""`--dry-run`: *"1 to take out of the video"*, never *"to fetch"* -- and the
    estimate asks jimaku nothing for it."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS")])
    plan = u" ".join(u" ".join(report_module.render_plan(
        lab.run(extract_embedded=True, dry_run=True))).split())
    assert u"1 to take out of the video" in plan and u"to fetch" not in plan, plan
    assert u"est. 0 API calls" in plan, plan

# ---------------------------------------------------------------------------
# ⭐ 14z -- THE LAYER 14 PASS (ADVERSARY 2026-09-25 §Layer 14, 14z)
# ---------------------------------------------------------------------------
# One check per finding, each with its mutant (`mutants/m14.mjs`, M14-69 onward).

def test_a_forced_only_japanese_track_is_not_the_subtitles_inside(tmp_path):
    u"""⭐ 14z (C1) -- signs and songs only is no whole subtitle (06 §6): *Leave them
    there* left such a video alone for ever. Under the default choice it is fetched
    now -- `present.read_tracks` says FETCH, never EMBEDDED."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    signs = Track(lang=u"ja", codec=u"S_TEXT/ASS")
    signs.forced = True
    _save(lab, u"frieren S2 - 01.mkv", [signs])

    one, = lab.run().results                       # the default: Leave them there

    assert one.skip != pipeline.EMBEDDED, (one.outcome, one.skip, one.reason)
    assert one.outcome == pipeline.CONFIDENT and lab.downloads, one.reason
    kind = present.read_tracks(lab.media / u"frieren S2 - 01.mkv", u"ja",
                               reader=lab.reader).kind
    assert kind == present.FETCH, kind


def test_a_two_episode_file_keeps_its_own_subtitles(tmp_path):
    u"""⭐ 14z (A-3) -- taking a video's own track out splits nothing: *Save them beside
    the video* takes it out, *Leave them there* leaves it (embedded, not refused), and
    only a DOWNLOAD -- one subtitle for two episodes -- is refused. ⛔ No request, any."""
    name = u"frieren S2 - 01-02.mkv"
    for how, settings, want in ((u"save", dict(extract_embedded=True), pipeline.CONFIDENT),
                                (u"leave", dict(), pipeline.SKIPPED),
                                (u"fetch", dict(skip_embedded=False), pipeline.REFUSED)):
        lab = Lab(tmp_path / how, names=[name])
        _save(lab, name, [Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)])
        one, = lab.run(**settings).results
        assert one.outcome == want, (how, one.outcome, one.reason)
        assert lab.spent == 0 and lab.downloads == [], how
        if how == u"save":
            assert one.taken_from and one.taken_from[u"track"] == 3, one.taken_from
        if how == u"leave":
            assert one.skip == pipeline.EMBEDDED, one.skip


def test_an_unreadable_two_episode_file_is_refused_on_its_name(tmp_path):
    u"""⚠ 14z (A-3) -- the name still decides a file whose container cannot be read:
    REFUSED for its two episodes, never an ERROR about its tracks. The launcher's own
    checks drive exactly this shape, and five of them went red the one time it moved."""
    name = u"frieren S2 - 01-02.mkv"
    lab = Lab(tmp_path, names=[name])
    lab.tracks[name] = Answer(ok=False, reason=u"needs ffprobe")

    one, = lab.run().results

    assert one.outcome == pipeline.REFUSED and u"episodes 1-2" in one.reason, (
        one.outcome, one.reason)


def test_a_japanese_picture_track_under_save_says_why(tmp_path):
    u"""⭐ 14z (A-4) -- pictures of text (PGS, VobSub) are no subtitles to take out:
    under *Save them beside the video* the video is downloaded for and its row says
    why. It never reached the take-out to say so, and said nothing anywhere."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    pgs = Track(lang=u"ja", text=False, bitmap=True, codec=u"S_HDMV/PGS", index=3)
    _save(lab, u"frieren S2 - 01.mkv", [pgs])

    one, = lab.run(extract_embedded=True).results

    assert lab.extracted == [], u"a picture track was handed to tsubasa to take out"
    assert one.outcome == pipeline.CONFIDENT and lab.downloads, one.reason
    assert u"pictures" in (one.not_taken or u"") and u"S_HDMV/PGS" in one.not_taken, (
        one.not_taken)
    assert report_module.as_dict(one)[u"not_taken"] == one.not_taken


def test_a_track_still_arriving_is_an_error_and_nothing_is_downloaded(tmp_path):
    u"""⭐ 14z (A-2) -- tsubasa refuses a track with empty stretches: a file still being
    downloaded into. Downloaded for then, jimaku's file stood beside the finished video
    for ever and its own track was never taken out. ERROR, nothing downloaded, nothing
    recorded -- and once the file is whole, the next run takes it out."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)],
          refuse={3: u"an event of track 3 holds empty bytes -- a stretch of the file has "
                     u"not been written yet (a download in progress?) or is damaged, so "
                     u"the track is not all there"})

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.ERROR, (one.outcome, one.reason)
    assert u"not be taken out yet" in one.reason and u"next run" in one.reason, one.reason
    assert lab.downloads == [] and lab.spent == 0 and one.retry_after is None
    assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                          pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}
    lab.takes.clear()                                   # the download has finished
    two, = lab.run(extract_embedded=True).results
    assert two.outcome == pipeline.CONFIDENT and two.taken_from, (two.outcome, two.reason)


def test_the_real_tsubasa_refusing_a_track_not_all_there_is_an_error(japanese_video,
                                                                        tmp_path):
    u"""🚨 THE PROSE PINNED. hato knows a track still arriving by tsubasa's own words
    (`pipeline._UNFINISHED`), so this is the REAL tsubasa over a real file with one
    cue's bytes zeroed -- the shape a download in progress leaves. A reworded refusal
    fails HERE, loudly, instead of downloading for a video still arriving."""
    lab = real_lab(japanese_video, tmp_path)
    video = lab.media / japanese_video.video.name
    data = bytearray(video.read_bytes())
    cue = u"行 36".encode("utf-8")
    at = data.find(cue)
    assert at > 0, u"the cue's text is not stored as it was written"
    data[at:at + len(cue)] = b"\x00" * len(cue)
    video.write_bytes(bytes(data))

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.ERROR, (one.outcome, one.reason)
    assert u"holds empty bytes" in one.reason, one.reason
    assert lab.downloads == [] and lab.spent == 0


def test_a_saved_file_hato_cannot_count_is_an_error_from_the_first_run(tmp_path):
    u"""⭐ 14z (A-5) -- a file hato writes must be one its own present-check COUNTS. A
    video's name past 255 bytes had its stem TRIMMED by tsubasa (its note said so):
    *"taken from the video"* once, then ERROR every run after -- and players would not
    load it either. ERROR from the first run, with tsubasa's note."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    note = u"the name was 259 bytes and the limit is 255, so the stem was trimmed"
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"ja", codec=u"S_TEXT/ASS")],
          writes_as=u"frieren S2 - 0.ja.ass", notes=(note,))

    one, = lab.run(extract_embedded=True).results

    assert one.outcome == pipeline.ERROR, (one.outcome, one.reason)
    assert u"players will not load it" in one.reason and note in one.reason, one.reason
    assert not one.wrote and one.taken_from, one.taken_from


def test_only_a_japanese_track_is_taken_out(tmp_path):
    u"""⭐ 14z (A-9, its A3) -- the language decides first: an English DEFAULT `.ass`
    beside a Japanese `.srt`, `.ass` preferred -- the Japanese one is taken out, and an
    English track is never saved as *"the Japanese subtitles"*."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    english = Track(lang=u"en", codec=u"S_TEXT/ASS", index=2)
    english.default = True
    japanese = Track(lang=u"ja", codec=u"S_TEXT/UTF8", index=3)
    _save(lab, u"frieren S2 - 01.mkv", [english, japanese])

    one, = lab.run(extract_embedded=True, prefer_format=u"ass").results

    assert one.taken_from and one.taken_from[u"track"] == 3, (one.outcome, one.taken_from)
    assert [index for _n, index, _w, _o in lab.extracted] == [3], lab.extracted


def test_saving_with_no_japanese_track_inside_asks_tsubasa_nothing(tmp_path):
    u"""⭐ 14z (A-9, its A5) -- an English track only: nothing Japanese to take out, so
    tsubasa is asked nothing and the row carries no *why* -- it was never the setting's
    case. ⛔ A take-out entered without one said *"a FORCED one"* of a video with none."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    _save(lab, u"frieren S2 - 01.mkv", [Track(lang=u"en", codec=u"S_TEXT/ASS")])

    one, = lab.run(extract_embedded=True).results

    assert lab.extracted == [] and one.not_taken is None, (lab.extracted, one.not_taken)
    assert one.outcome == pipeline.CONFIDENT and lab.downloads, one.reason


def test_a_forced_track_beside_a_whole_one_is_never_the_one_taken_out(tmp_path):
    u"""⛔ 14c's rule where it still decides -- the 14z gate: once a video whose ONLY
    Japanese track is forced stopped reaching the take-out (C1), M14-27 survived. A
    signs-only `.ass` the file marks DEFAULT, the preferred format too, beside a whole
    `.srt`: the whole one is taken out. Saved, the forced one would be `.ja.forced.ass`,
    which the present-check never counts -- taken out again, and refused over itself,
    every run."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    signs = Track(lang=u"ja", codec=u"S_TEXT/ASS", index=2)
    signs.forced = True
    signs.default = True
    whole = Track(lang=u"ja", codec=u"S_TEXT/UTF8", index=3)
    _save(lab, u"frieren S2 - 01.mkv", [signs, whole])

    one, = lab.run(extract_embedded=True, prefer_format=u"ass").results

    assert one.taken_from and one.taken_from[u"track"] == 3, (one.outcome, one.taken_from)
    assert [index for _n, index, _w, _o in lab.extracted] == [3], lab.extracted


def test_the_file_s_default_decides_between_two_of_one_format(tmp_path):
    u"""⭐ 14z (A-9, its A1) -- two Japanese `.ass` tracks: the one the file marks
    DEFAULT is taken out, whatever their order."""
    lab = Lab(tmp_path, names=episodes_up_to(1))
    first = Track(lang=u"ja", codec=u"S_TEXT/ASS", index=2)
    second = Track(lang=u"ja", codec=u"S_TEXT/ASS", index=3)
    second.default = True
    _save(lab, u"frieren S2 - 01.mkv", [first, second])

    one, = lab.run(extract_embedded=True).results

    assert one.taken_from and one.taken_from[u"track"] == 3, one.taken_from


def test_a_plan_says_a_video_that_is_not_an_mkv_goes_to_jimaku(tmp_path):
    u"""⭐ 14z (C5) -- the header decides a plan: a file that does not START as
    Matroska is planned as a download and says why -- without asking tsubasa to read
    a byte of it."""
    lab = Lab(tmp_path, names=[])
    (lab.media / u"frieren S2 - 01.mp4").write_bytes(b"\x00\x00\x00\x20ftypisom" + b"x" * 32)
    _save(lab, u"frieren S2 - 01.mp4", [Track(lang=u"ja", codec=u"S_TEXT/UTF8")])

    one, = lab.run(extract_embedded=True, dry_run=True).results

    assert one.outcome == pipeline.PLANNED and not one.taken_from, (one.outcome, one.reason)
    assert u"not an MKV file" in (one.not_taken or u""), one.not_taken
    assert lab.extracted == []


def test_a_waiting_row_and_a_plan_say_why_it_was_not_taken_out(tmp_path):
    u"""⭐ 14z (A-8) -- the *why* rides every row: a video waiting to retry (Mode A's
    skip lines) and a plan's count. Both said nothing of it."""
    signs = Track(lang=u"ja", codec=u"S_TEXT/ASS")
    signs.forced = True
    fetching = Lab(tmp_path / u"plan", names=episodes_up_to(1))
    _save(fetching, u"frieren S2 - 01.mkv", [signs])
    plan = u" ".join(u" ".join(report_module.render_plan(
        fetching.run(extract_embedded=True, dry_run=True))).split())
    assert u"1 to fetch (1 with Japanese subtitles inside that cannot be taken out)" in plan, (
        plan)

    lab = Lab(tmp_path / u"wait", names=[u"frieren S2 - 24.mkv"])      # jimaku has no 24
    _save(lab, u"frieren S2 - 24.mkv", [signs])
    first, = lab.run(extract_embedded=True).results
    assert first.outcome == pipeline.NOT_FOUND and u"FORCED" in (first.not_taken or u""), (
        first.outcome, first.not_taken)
    waiting = lab.run(extract_embedded=True)
    assert waiting.results[0].skip == pipeline.NEGATIVE, waiting.results[0].skip
    shown = _mode_a(waiting)
    assert u"could not be taken out (its Japanese subtitle track is a FORCED one" in shown, (
        shown)


def test_the_library_result_carries_what_every_row_says():
    u"""⭐ 14z (A-8) -- `hato.api.Result` carries `taken_from` and `not_taken`, as `--json`
    and the window do: a library caller could not tell a subtitle taken out from one
    downloaded, nor why."""
    from hato import api
    taken = pipeline.VideoResult(u"a.mkv", pipeline.CONFIDENT, u"", output_path=u"a.ja.ass",
                                 taken_from={u"track": 3})
    fetched = pipeline.VideoResult(u"b.mp4", pipeline.CONFIDENT, u"")
    fetched.not_taken = u"an MP4 file"
    assert api.Result(taken).taken_from == {u"track": 3} and api.Result(taken).not_taken is None
    assert api.Result(fetched).not_taken == u"an MP4 file"


def _unwritable(folder):
    u"""`folder`, made so THIS user cannot add a file to it -- Windows: an ACL deny of
    add-file and add-folder (`icacls`); elsewhere 0o555. -> a callable that puts it back.
    ⛔ Called in a `finally`: a folder left denied could not even be cleaned up."""
    import subprocess
    folder = str(folder)
    if sys.platform.startswith("win"):
        who = os.environ.get("USERNAME") or os.getlogin()
        subprocess.run([u"icacls", folder, u"/deny", u"%s:(WD,AD)" % who], check=True,
                       stdout=subprocess.DEVNULL)
        return lambda: subprocess.run([u"icacls", folder, u"/remove:d", who], check=True,
                                      stdout=subprocess.DEVNULL)
    if os.geteuid() == 0:
        pytest.skip(u"root writes anywhere: no folder can be made unwritable for it")
    os.chmod(folder, 0o555)
    return lambda: os.chmod(folder, 0o755)


def test_a_folder_that_cannot_be_written_is_an_error_before_any_request(tmp_path):
    u"""🚨 14z (A-1) -- A RUN THAT NEVER ENDED. In a folder whose permissions deny adding a
    file, the writer under tsubasa spun for days (`tempfile.mkstemp` reads ACCESS_DENIED
    as a name taken) -- after two metered calls on the download road, at once under
    *Save*. The folder is asked FIRST: ERROR, tsubasa and jimaku asked nothing, nothing
    recorded. ⚠ The download arm REFUSES every candidate, so a mutant that lets it through
    fails fast rather than writing into the folder."""
    for how, settings, tracks in (
            (u"save", dict(extract_embedded=True), [Track(lang=u"ja", codec=u"S_TEXT/ASS")]),
            (u"fetch", dict(), [Track()])):
        lab = Lab(tmp_path / how, names=episodes_up_to(1))
        _save(lab, u"frieren S2 - 01.mkv", tracks)
        refuse_everything(lab)
        put_back = _unwritable(lab.media)
        try:
            one, = lab.run(**settings).results
        finally:
            put_back()
        assert one.outcome == pipeline.ERROR, (how, one.outcome, one.reason)
        assert u"cannot be written" in one.reason, (how, one.reason)
        assert lab.extracted == [] and lab.downloads == [] and lab.spent == 0, how
        assert lab.rows() == {pipeline.CONFIDENT: 0, pipeline.REFUSED: 0,
                              pipeline.ERROR: 0, pipeline.NOT_FOUND: 0}, how


def test_the_folder_question_asks_and_never_writes(tmp_path):
    u"""⭐ 14z (A-1) -- `paths.cannot_write`: None for a folder that takes a file, and for
    an `--out` mirror not made yet under one; the reason for one that denies it -- and
    the folder is left exactly as it was (it ASKS: the only write in a media folder is
    tsubasa's)."""
    from hato import paths
    open_ = tmp_path / u"open"
    shut = tmp_path / u"shut"
    open_.mkdir()
    shut.mkdir()
    assert paths.cannot_write(open_) is None
    assert paths.cannot_write(open_ / u"mirror" / u"S2") is None
    put_back = _unwritable(shut)
    try:
        said = paths.cannot_write(shut)
        under = paths.cannot_write(shut / u"mirror")
    finally:
        put_back()
    assert said and u"cannot be written" in said and str(shut) in said, said
    assert under and str(shut) in under, under
    assert list(shut.iterdir()) == [] and list(open_.iterdir()) == []


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason=u"Windows names are one name in any case; POSIX's are not")
def test_a_subtitle_named_in_another_case_is_the_video_s_own(tmp_path):
    u"""⭐ 14z (A-6) -- on Windows `Frieren` and `frieren` are one name: a video renamed by
    case only after its subtitle was saved read as having none -- and every run after it
    ended ERROR *"already there"*."""
    lab = Lab(tmp_path, names=[u"Frieren S2 - 01.mkv"])
    (lab.media / u"frieren S2 - 01.ja.ass").write_text(u"x", encoding="utf-8")

    one, = lab.run(extract_embedded=True).results

    assert one.skip == pipeline.PRESENT, (one.outcome, one.skip, one.reason)
    assert lab.extracted == []

