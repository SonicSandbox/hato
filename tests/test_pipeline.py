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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import tsubasa

from hato import cache as cache_module, client as client_module, credentials, keep, \
    pipeline, port, present, resolution, state
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

    # -- driving -----------------------------------------------------------

    def settings(self, **overrides):
        values = dict(folders=[self.media], lang=u"ja", subs_dir=self.subs,
                      candidates=3)
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
            reader=None if self.use_real_engine else self.reader)
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


def test_a_movie_entry_offers_every_file_to_the_one_film(tmp_path):
    u"""06 §3, RULED: ⛔ skip episode matching entirely."""
    lab = Lab(tmp_path, names=[u"Kimi no Na wa.mkv"])
    report = lab.run(candidates=1)

    assert report.shows[0].resolved.movie is True
    assert report.results[0].candidates_offered == len(
        json.loads((FIXTURES / "api" / "entries_movie_flag.json").read_text(encoding="utf-8")))


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
