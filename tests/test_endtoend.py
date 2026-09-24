# -*- coding: utf-8 -*-
u"""
RUNBOOK 5a + 5c -- the ruled CLI output, and the launcher.

⭐ EVERYTHING HERE GOES THROUGH `cli.main()` OR THROUGH `hato-run.cmd`. Not
through `report.render()` with a hand-built object: 5a's whole risk is that the
renderer is correct and never reaches a person, and 5c's is an environment a
developer shell does not reproduce. So argument parsing, the config, the run
lock, the log, the exit code and the renderer are all on the path of every check
below.

⛔ ZERO NETWORK. Every metered call is answered from a response `hato doctor
--capture` recorded, and the socket layer refuses anything else (`conftest.py`).

⚠ THE ONE THING THAT CANNOT COME FROM A CAPTURE IS THE SUBTITLE'S BYTES --
Whitelist 2 forbids mirroring subtitle content, so `07-test-plan.md` keeps the
download fixtures as metadata only. `hato.commands.run.build_world` is the seam
that exists for exactly this: the suite replaces it, and everything else on the
path is the product.

⛔ WHAT THIS SUITE STRUCTURALLY CANNOT COVER: a real Task Scheduler execution
(its environment resolves `%LOCALAPPDATA%` and the keystore differently -- the
orchestrator runs it), and a real console, where `isatty()` is true and the
pause is reached by detection rather than by `HATO_RUN_PAUSE`.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hato import cli, client as client_module, credentials, pipeline, port, report, \
    resolution, state
from hato.cache import Cache
from hato.commands import run as run_cmd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
LAUNCHER = ROOT / "hato-run.cmd"
#: The recorded entry -- Sousou no Frieren 2nd Season.
ENTRY = 11446
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

_ANSI = re.compile(u"\x1b\\[[0-9;]*m")


# ---------------------------------------------------------------------------
# the laboratory -- a folder, recorded responses, and the three seams
# ---------------------------------------------------------------------------

class Track(object):
    def __init__(self, lang=u"en", text=True, bitmap=False, codec=u"S_TEXT/UTF8", index=2):
        self.lang, self.text, self.bitmap = lang, text, bitmap
        self.codec, self.index, self.forced = codec, index, False


class Answer(object):
    u"""`tsubasa.EmbeddedSubtitles`; `.tracks` raises when `ok` is False, as the
    real one does."""

    def __init__(self, ok=True, reason=u"", tracks=None):
        self.ok, self.reason = ok, reason
        self._tracks = (Track(),) if tracks is None else tuple(tracks)

    @property
    def tracks(self):
        if not self.ok:
            raise ValueError(u"could not be read: %s" % self.reason)
        return self._tracks


class FakeTTY(object):
    u"""A stdout that claims to be a terminal. ⛔ The ONLY way this suite can
    reach the colour branch: pytest's captured stdout is never one."""

    def __init__(self):
        self.text = u""

    def write(self, chunk):
        self.text += chunk
        return len(chunk)

    def flush(self):
        pass

    def isatty(self):
        return True


class Lab(object):
    u"""One CLI run's world.

    ⚠ EVERY STUB VIDEO CARRIES DISTINCT BYTES -- the state DB is keyed on a
    head+tail hash, and ten zero-byte files would be ONE video to it.
    """

    def __init__(self, tmp_path, names=None, folder=u"Frieren S2"):
        self.root = Path(tmp_path)
        self.media = self.root / folder
        self.media.mkdir(parents=True, exist_ok=True)
        self.names = list(names if names is not None else episodes(1, 6) + [u"frieren S2 - 24.mkv"])
        for name in self.names:
            (self.media / name).write_bytes(b"\x1aE\xdf\xa3" + name.encode("utf-8"))
        self.subs = self.root / "subs"
        self.data = self.root / "data"
        self.config = self.root / "config.toml"
        self.config.write_text(u"", encoding="utf-8")
        self.downloads = []
        self.tracks = {}                       # basename -> Answer
        self.decide = lambda base: {}          # basename -> stub_engine kwargs
        self.db = None
        self.client = None
        #: ⭐ True hands the pipeline the REAL tsubasa for both the container
        #: read and the verdict. Everything above it believes a stub about what
        #: a verdict is; one check must not.
        self.real_tsubasa = False
        self.bytes_for = None                  # (item) -> bytes, overriding the stub

    # -- the folder --------------------------------------------------------

    def present(self, *numbers, **kw):
        ext = kw.pop("ext", u"ja.srt")
        for n in numbers:
            (self.media / (u"frieren S2 - %02d.%s" % (n, ext))).write_text(
                u"1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")

    def no_track(self, *numbers):
        for n in numbers:
            self.tracks[u"frieren S2 - %02d.mkv" % n] = Answer(tracks=())

    # -- the seams ---------------------------------------------------------

    def reader(self, video, **kwargs):
        return self.tracks.get(os.path.basename(video), Answer())

    def download(self, item):
        self.downloads.append(item["name"])
        if self.bytes_for is not None:
            return self.bytes_for(item)
        return (u"1\n00:00:01,000 --> 00:00:02,000\n%s\n" % item["name"]).encode("utf-8")

    def engine(self, pairs, **kwargs):
        (video, _subtitle), = list(pairs)
        return port.stub_engine(**self.decide(os.path.basename(video)))(pairs, **kwargs)

    # -- driving -----------------------------------------------------------

    def install(self, monkeypatch):
        monkeypatch.setenv("HATO_CACHE", str(self.data))
        monkeypatch.setenv("HATO_CONFIG", str(self.config))

        def build_world(args):
            session = client_module.RecordedSession(FIXTURES)
            key = credentials.Key(run_cmd.STAND_IN_KEY, u"the suite")
            self.client = client_module.JimakuClient(key, session, sleep=lambda s: None)
            self.db = state.StateDB(self.root / "state.db", now=lambda: NOW)
            return run_cmd.World(
                client=self.client, db=self.db,
                resolutions=resolution.ResolutionCache(self.root / "resolution.db"),
                kitsu=None, cache=Cache(self.root / "cache"),
                downloader=self.download,
                engine=None if self.real_tsubasa else self.engine,
                reader=None if self.real_tsubasa else self.reader)

        monkeypatch.setattr(run_cmd, "build_world", build_world)
        return self

    def argv(self, *extra):
        return [str(self.media), "--subs-dir", str(self.subs)] + list(extra)

    def cli(self, capsys, *extra):
        u"""-> (exit code, stdout, stderr). THE REAL ENTRY POINT."""
        code = cli.main(self.argv(*extra))
        captured = capsys.readouterr()
        return code, captured.out, captured.err


def episodes(first, last, pattern=u"frieren S2 - %02d.mkv"):
    return [pattern % n for n in range(first, last + 1)]


def confident(match=0.96, offset=0.13, **kw):
    fields = dict(match_rate=match, segments=[(None, offset)], excess_over_chance=4.6)
    fields.update(kw)
    return fields


def refused(match=0.31):
    return dict(outcome=port.REFUSED, match_rate=match,
                reason=u"%d%% match -- the timing does not hold" % round(match * 100))


def normal(lab, monkeypatch):
    u"""The shape the ruled Mode A mock has: one of everything."""
    lab.install(monkeypatch)
    lab.present(1)
    lab.no_track(2)
    lab.decide = lambda base: (
        refused() if base == u"frieren S2 - 03.mkv" else
        confident(match=0.91, verdict_word=u"strong",
                  segments=[(198.0, -33.07), (None, -42.96)])
        if base == u"frieren S2 - 06.mkv" else confident())
    return lab


def rows(text, mark):
    return [line for line in text.split(u"\n") if line.lstrip().startswith(mark)]


def flat(text):
    u"""⚠ The output WRAPS. A phrase check against the raw text asserts the
    wrapping as well as the words, and then a one-word edit anywhere upstream
    turns the check red for the wrong reason."""
    return u" ".join(text.split())


def columns(text):
    u"""Display columns, measured HERE and not by `report.cells`.

    🚨 FOUND BY BREAKING IT. The width check originally asked `report.cells` how
    wide a line was -- the same function the renderer pads with -- so replacing
    it with `len()` made the renderer and the check wrong together and the check
    stayed green. A ruler must not be the thing it is measuring.
    """
    import unicodedata
    return sum(0 if unicodedata.combining(ch)
               else 2 if unicodedata.east_asian_width(ch) in (u"W", u"F") else 1
               for ch in text)


def summary_line(text):
    return [line for line in text.split(u"\n") if u"API call" in line][-1]


#: 🚨 EVERY MARKER THAT OPENS A ROW, INCLUDING THE FIVE SKIPS. The row checks
#: filtered to OK/PROBLEM/FLAGGED, which structurally excluded every collapsed
#: skip line -- so the show label on a skip row was never looked at once, and it
#: was wrong (`hato/report.py` `_skip_rows`). A filter that cannot see a kind of
#: row is a filter that cannot fail on it.
ROW_MARKS = (report.OK, report.PROBLEM, report.FLAGGED, report.WARN) + tuple(
    mark for _k, mark, _s in report.SKIPS)


def labelled_rows(text):
    return [ln for ln in text.split(u"\n") if ln.lstrip()[:1] in ROW_MARKS]


#: A long Japanese title. ⚠ NINE characters is EIGHTEEN display columns, past the
#: sixteen the show column keeps -- so two shows of it are told apart only by
#: what survives the clip.
LONG_TITLE = u"\u9b54\u6cd5\u79d1\u9ad8\u6821\u306e\u52a3\u7b49\u751f"


def two_seasons(tmp_path, monkeypatch, present=False):
    u"""Two seasons of one long-titled show, decided with ZERO network.

    ⭐ A video holding two episodes is refused on its NAME, and a video whose
    subtitle is already beside it is skipped -- both before any request. So this
    fixture reaches the row layout without a recorded response for the title.
    """
    tail = u" - 01.mkv" if present else u" - 01-02.mkv"
    names = [LONG_TITLE + u" S1" + tail, LONG_TITLE + u" S2" + tail]
    lab = Lab(tmp_path, names=names, folder=u"Anime").install(monkeypatch)
    if present:
        for name in names:
            (lab.media / (name[:-3] + u"ja.srt")).write_text(
                u"1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")
    return lab


# ===========================================================================
# 1. ⭐ the ruled output -- Mode A
# ===========================================================================

def test_a_full_run_through_the_cli_renders_the_ruled_shape(tmp_path, monkeypatch, capsys):
    u"""One run, one of every outcome, through `cli.main`. The shape is
    `05-interface.md`'s Mode A: a header, the identify block, problems, skips,
    successes, and the summary with the cost on it."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 0, err
    header = out.split(u"\n\n")[0]
    assert header.startswith(u"hato  ")
    assert lab.media.name in header
    assert u"7 videos" in header
    assert u"Sousou no Frieren 2nd Season" in out          # ⭐ what it thinks the show is
    assert u"jimaku entry %d" % ENTRY in out
    assert rows(out, report.PROBLEM), u"no problem rows rendered:\n%s" % out
    assert rows(out, report.OK), u"no success rows rendered:\n%s" % out
    assert u"subtitle already present" in out
    assert u"no subtitle track in the video" in out
    assert u"API call" in summary_line(out)


def test_problems_sort_above_successes(tmp_path, monkeypatch, capsys):
    u"""🚨 THE NON-NEGOTIABLE ONE. *The one thing needing attention must not sit
    below 19 successes* -- and that is a property of the RUN, not of one show."""
    lab = normal(Lab(tmp_path, names=episodes(1, 12) + [u"frieren S2 - 24.mkv"]), monkeypatch)
    lab.decide = lambda base: refused() if base == u"frieren S2 - 12.mkv" else confident()
    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 0, err
    lines = out.split(u"\n")
    first_problem = min(i for i, ln in enumerate(lines) if ln.lstrip().startswith(report.PROBLEM))
    first_success = min(i for i, ln in enumerate(lines)
                        if ln.lstrip().startswith((report.OK, report.FLAGGED)))
    successes = len([ln for ln in lines if ln.lstrip().startswith(report.OK)])
    assert successes >= 8, u"this check is pointless without a pile of successes to sit above"
    assert first_problem < first_success, out


def test_the_api_call_count_is_on_every_run_including_a_free_one(tmp_path, monkeypatch, capsys):
    u"""⭐ *A user who cannot see the cost cannot notice a runaway loop -- and it
    is the first line a bug report needs.* Including the run that spent
    nothing, which is the one a missing line would be easiest to excuse."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")
    assert re.search(u"\\d+ API calls?", summary_line(out)), out

    free = Lab(tmp_path / "free", names=[u"frieren S2 - 01.mkv"]).install(monkeypatch)
    free.present(1)
    code, out, err = free.cli(capsys)
    assert code == 0, err
    assert u"0 API calls" in summary_line(out), out
    assert u"no API call needed" in out                    # ...and per show, too


def test_the_no_track_line_is_its_own_row_and_is_never_a_refusal(tmp_path, monkeypatch, capsys):
    u"""⭐ The `⊘` row, added to the ruled output 2026-09-17. ⛔ *Never record
    "no subtitle track" as a refusal* (`LEDGER-HOT.md`): a refusal row
    blacklists that subtitle's hash for ever, including after tsubasa can sync
    from audio."""
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.no_track(2, 4)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    no_track = rows(out, u"\u2298")
    assert len(no_track) == 1, out
    assert u"02 04" in no_track[0]
    assert u"can't sync yet, nothing downloaded" in no_track[0]
    assert u"2 can't sync yet" in summary_line(out)
    for line in rows(out, report.PROBLEM):
        assert u"REFUSED" not in line or u"02" not in line.split(u"REFUSED")[0]


def test_every_not_found_carries_a_retry_date(tmp_path, monkeypatch, capsys):
    u"""*Distinguishes "nothing yet" from "broken" without the user having to
    ask.* ⛔ Not optional on any one of them."""
    lab = normal(Lab(tmp_path, names=episodes(1, 6) + [u"frieren S2 - 24.mkv",
                                                       u"frieren S2 - 25.mkv"]), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    missing = [ln for ln in out.split(u"\n") if u"NOT FOUND" in ln]
    assert len(missing) == 2, out
    for chunk in out.split(u"NOT FOUND")[1:]:
        assert re.search(u"20\\d\\d-\\d\\d-\\d\\d", flat(chunk.split(u"\n\n")[0])), chunk


def test_a_dry_run_says_nothing_is_scheduled_instead_of_inventing_a_date(tmp_path, monkeypatch,
                                                                        capsys):
    u"""⚠ `--dry-run` records no row, so there IS no retry date. The line says
    so rather than going quiet -- a missing date would read as a date of
    never."""
    lab = normal(Lab(tmp_path, names=[u"frieren S2 - 24.mkv"]), monkeypatch)
    code, out, err = lab.cli(capsys, "--dry-run")

    assert code == 0, err
    assert u"NOT FOUND" in out
    assert u"nothing was recorded, so nothing is scheduled (dry run)" in flat(out)
    assert not re.search(u"will retry after 20", flat(out)), out


def test_evidence_on_every_success_line_never_a_bare_tick(tmp_path, monkeypatch, capsys):
    u"""*`96% match · locked`, never a bare tick* -- the property, on every row
    the tool stands behind."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    written = rows(out, report.OK) + rows(out, report.FLAGGED)
    assert written
    for line in written:
        assert re.search(u"\\d+%", line), line
        assert any(word in line for word in (u"locked", u"strong", u"fair", u"uncertain")), line
    # ⚠ `old -> new` is the property, and a cut file's row carries its filename
    # on the CONTINUATION line -- so the claim is about the block, not the row.
    for name in lab.names:
        stem = os.path.splitext(name)[0]
        if any(stem in ln for ln in written):
            assert u"%s %s.ja." % (report.ARROW, stem) in flat(out), (stem, out)


def test_a_cut_file_is_flagged_and_shows_both_offsets(tmp_path, monkeypatch, capsys):
    u"""The ruled mock's `⚑` row: `-33.07 / -42.96 @3:18   91% · strong · 2
    segments`. ⚠ A cut file is written and is worth looking at."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    flagged = rows(out, report.FLAGGED)
    assert len(flagged) == 1, out
    assert u"-33.07 / -42.96" in flagged[0]
    assert u"@3:18" in flagged[0]
    assert u"2 segments" in flagged[0]


# ===========================================================================
# 2. 🚨 "nothing was written" is TWO sentences
# ===========================================================================

def test_the_two_nothing_written_sentences_are_never_the_same(tmp_path, monkeypatch, capsys):
    u"""🚨 tsubasa returns `CONFIDENT` with no `output_path` for BOTH a dry run
    and a write that was attempted and did not land. A user told *"dry run"*
    when their write really failed stops looking for the file."""
    assert report.DRY_RUN_SENTENCE != report.WRITE_FAILED_SENTENCE
    assert not report.WRITE_FAILED_SENTENCE.startswith(report.DRY_RUN_SENTENCE[:12])

    # ⛔ No `present()` here: a video whose subtitle is already there never
    # reaches the engine, and the check would pass over a blank page.
    lab = Lab(tmp_path, names=episodes(1, 2)).install(monkeypatch)
    lab.decide = lambda base: dict(writes=False)
    _code, failed_out, _err = lab.cli(capsys, "--candidates", "1")

    assert report.WRITE_FAILED_SENTENCE in flat(failed_out), failed_out
    assert report.DRY_RUN_SENTENCE not in flat(failed_out), failed_out
    assert u"NOT WRITTEN" in flat(failed_out)


def test_a_dry_run_result_says_dry_run_and_not_write_failed(tmp_path, monkeypatch):
    u"""The other half of the same pair, driven at the port so the SHAPE is
    tsubasa's own: `write=False` at the call site, not `writes=False` in the
    engine (`hato/port.py`, both measured against the real engine)."""
    video = tmp_path / "Show - 01.mkv"
    video.write_bytes(b"\x1aE\xdf\xa3x")
    subtitle = tmp_path / "Show - 01.ja.srt"
    subtitle.write_text(u"1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")

    result = port.sync(str(video), str(subtitle), write=False,
                       engine=port.stub_engine(**confident()))
    said = report.nothing_written(result)
    assert said is not None
    assert said.startswith(report.DRY_RUN_SENTENCE)
    assert report.WRITE_FAILED_SENTENCE not in said

    failed = port.sync(str(video), str(subtitle), write=True,
                       engine=port.stub_engine(writes=False, **confident()))
    said_failed = report.nothing_written(failed)
    assert said_failed.startswith(report.WRITE_FAILED_SENTENCE)
    assert report.DRY_RUN_SENTENCE not in said_failed


# ===========================================================================
# 3. ⛔ the raw multiple, and colour
# ===========================================================================

def test_no_raw_confidence_multiple_in_the_default_output(tmp_path, monkeypatch, capsys):
    u"""⛔ *"4.6x chance" is an internal decision statistic and means nothing to
    a person.* `--verbose` and `--json` only."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, plain, _err = lab.cli(capsys, "--candidates", "1")
    assert not re.search(u"\\d\\.\\d+ *[x\u00d7]", plain), plain

    lab2 = normal(Lab(tmp_path / "v"), monkeypatch)
    _code, loud, _err = lab2.cli(capsys, "--candidates", "1", "--verbose")
    assert u"raw multiple" in loud
    assert re.search(u"4\\.60x", loud), loud


def test_colour_is_absent_when_stdout_is_not_a_tty(tmp_path, monkeypatch, capsys):
    u"""⛔ ANSI colour escapes in a log file are noise (`10-deployment.md` rule
    3). pytest's captured stdout is not a terminal, which is the same answer a
    scheduled run's redirected stdout gives."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")
    assert u"\x1b[" not in out, repr(out[:400])


def test_colour_appears_on_a_real_terminal(tmp_path, monkeypatch):
    u"""...and the branch is not dead. ⚠ Without this the check above passes on
    a renderer that can never colour anything."""
    lab = normal(Lab(tmp_path), monkeypatch)
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)
    code = cli.main(lab.argv("--candidates", "1"))
    assert code == 0
    assert u"\x1b[" in fake.text
    assert _ANSI.sub(u"", fake.text).count(report.OK) >= 1


def test_no_color_beats_a_terminal(tmp_path, monkeypatch):
    lab = normal(Lab(tmp_path), monkeypatch)
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)
    assert cli.main(lab.argv("--candidates", "1", "--no-color")) == 0
    assert u"\x1b[" not in fake.text


# ===========================================================================
# 4. --json -- NDJSON
# ===========================================================================

def test_json_is_ndjson_that_parses_one_object_per_video(tmp_path, monkeypatch, capsys):
    u"""*NDJSON, one object per video. The same structure the library returns.*
    Plus the run object -- `hato/report.py` §`run_dict` records why."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1", "--json")

    assert code == 0, err
    objects = [json.loads(line) for line in out.splitlines() if line.strip()]
    videos = [o for o in objects if o["type"] == "video"]
    runs = [o for o in objects if o["type"] == "run"]
    assert len(videos) == len(lab.names)
    assert len(runs) == 1
    assert runs[0]["api_calls"] >= 1
    assert set(videos[0]) >= {"video", "outcome", "reason", "jimaku_entry", "tsubasa",
                              "output_path", "kept_path", "retry_after", "attempts"}
    assert u"\x1b[" not in out


def test_an_untagged_japanese_subtitle_is_said_and_nothing_is_fetched(tmp_path, monkeypatch,
                                                                      capsys):
    u"""⭐ 9b THROUGH THE REAL ENTRY POINT, two arms. A second user: *"It also got
    subtitles for stuff that already had subtitles. Even though the subs were
    named after the video."* `frieren S2 - 01.srt` beside `frieren S2 - 01.mkv`:

      Japanese inside  -> skipped, ZERO downloads, and the reason says the NAME
                          gave no language and the TEXT did
      English inside   -> fetched, exactly as 1.0.2 did -- the arm that proves
                          the first one is not every untagged file skipped
    """
    sys.path.insert(0, str(ROOT / "tests"))
    import _subtitles as subs

    for arm, pool in ((u"japanese", subs.JA), (u"english", subs.EN)):
        lab = Lab(tmp_path / arm, names=[u"frieren S2 - 01.mkv"]).install(monkeypatch)
        (lab.media / u"frieren S2 - 01.srt").write_bytes(
            subs.srt(subs.lines(pool, 300)).encode("utf-8"))
        code, out, err = lab.cli(capsys, "--json")
        video, = [json.loads(line) for line in out.splitlines()
                  if line.strip() and json.loads(line)["type"] == "video"]
        if arm == u"japanese":
            assert video["skip"] == pipeline.PRESENT, video
            assert u"frieren S2 - 01.srt" in video["reason"], video["reason"]
            assert u"its name gives no language; its text is Japanese" in video["reason"]
            assert lab.downloads == [], lab.downloads
        else:
            assert video["skip"] is None and lab.downloads, (video, lab.downloads)


def test_every_run_leaves_a_trace_the_window_can_read(tmp_path, monkeypatch,
                                                      capsys):
    u"""🚨 SONIC, 2026-09-18: *"once it runs automatically (from the tray or
    so) the UI doesn't update... it worked but the ui didn't update."*

    ⭐ THE WINDOW WAS SAVING ITS OWN RUNS AND ONLY ITS OWN. A run started from
    the tray, the scheduler or a terminal wrote subtitles to disk and left
    nothing the window could read -- so somebody watching the window saw
    nothing while hato worked perfectly two processes away. **Not a refresh
    bug: a memory only one of three callers wrote to.**

    ⚠ THIS CHECK IS ON THE CLI, deliberately -- it is the path the tray and the
    scheduler take. A check on the window would have stayed green throughout,
    which is exactly why nothing caught it.
    """
    from hato import lastrun

    lab = normal(Lab(tmp_path), monkeypatch)
    before = lastrun.stamp()
    code, out, err = lab.cli(capsys, "--candidates", "1")
    assert code == 0, err

    rows, summary, saved_at = lastrun.load()
    assert rows, u"a finished run recorded no rows for the window to show"
    assert summary.get(u"type") == u"run"
    assert saved_at, u"nothing recorded WHEN the run happened"
    assert lastrun.stamp() != before, (
        u"the memory's timestamp did not move, so a window watching it would "
        u"never notice this run")


def test_a_dry_run_leaves_the_windows_memory_exactly_as_it_was(tmp_path, monkeypatch,
                                                               capsys):
    u"""🚨 RUNBOOK 8a. `--dry-run` says *"write nothing"* -- and it rewrote
    `last-run.json`, the file the window paints from.

    Measured 2026-09-22: the handoff's own first diagnostic command, run over
    Sonic's real folders, replaced his last real run with 68 rows of *"would
    fetch"*, which the window renders as *"something went wrong"*. ⛔ The command
    a person runs to LOOK must not change what the window shows.

    ⚠ BYTES AND STAMP, not just "rows exist": a snapshot rewritten with the same
    rows would pass a row check and still move the stamp, which is the signal a
    watching window reloads on.
    """
    from hato import lastrun, paths

    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1")
    assert code == 0, err
    memory = paths.last_run_path()
    before = memory.read_bytes()
    stamp = lastrun.stamp()
    assert json.loads(before.decode("utf-8"))[u"summary"].get(u"dry_run") is False

    code, out, err = lab.cli(capsys, "--dry-run")
    assert code == 0, err
    assert memory.read_bytes() == before, (
        u"a dry run rewrote the window's memory -- it now holds the PLAN, not the "
        u"last real run")
    assert lastrun.stamp() == stamp


def test_looking_again_at_one_video_leaves_the_windows_memory_alone(tmp_path, monkeypatch,
                                                                    capsys):
    u"""⭐ RUNBOOK 8e. *Look again now* on one row is `--only <video>`. Written to
    `last-run.json` it would replace the whole library's snapshot with ONE row,
    and the Subtitles tab would forget everything else."""
    from hato import lastrun, paths

    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1")
    assert code == 0, err
    before = paths.last_run_path().read_bytes()

    one = str(lab.media / u"frieren S2 - 03.mkv")
    code, out, err = lab.cli(capsys, "--json", "--retry-now", "--only", one)
    assert code == 0, err
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert [r[u"name"] for r in rows if r[u"type"] == u"video"] == [u"frieren S2 - 03.mkv"]
    assert paths.last_run_path().read_bytes() == before, (
        u"one row's look-again replaced the whole library's memory")


def test_retry_now_on_the_command_line_reaches_the_run(tmp_path, monkeypatch, capsys):
    u"""⭐ RUNBOOK 8e, TWO ARMS, THROUGH `cli.main`. Every pipeline check hands
    `Settings(retry_now=True)` in directly, and the check above asserts the memory
    and the row list -- so a flag the command line parsed and never passed on left
    all of them green, and *Look again now* would have waited out the day exactly
    like the button it replaced (D3). Found by mutant M8e-34 surviving."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1")    # 03 refused: a soft negative
    assert code == 0, err
    one = str(lab.media / u"frieren S2 - 03.mkv")

    del lab.downloads[:]
    code, out, err = lab.cli(capsys, "--json", "--only", one)          # arm A: no flag
    assert code == 0, err
    row, = [json.loads(line) for line in out.splitlines()
            if line.strip() and json.loads(line)[u"type"] == u"video"]
    assert row[u"skip"] == u"negative" and lab.downloads == [], (
        u"the control: inside the wait a plain run must try nothing -- %r, %s"
        % (row[u"skip"], lab.downloads))

    code, out, err = lab.cli(capsys, "--json", "--retry-now", "--only", one)   # arm B
    assert code == 0, err
    assert lab.downloads, (
        u"--retry-now was parsed and never reached the run: inside the wait it "
        u"tried nothing, which is the defect the flag exists to fix")


def test_every_real_run_writes_down_when_it_promised_to_look_again(tmp_path, monkeypatch,
                                                                   capsys):
    u"""⭐ RUNBOOK 8h. The tray wakes for these dates, and nothing else runs hato on
    its own (D2) -- so a run that refused an episode must leave its retry date
    where the tray reads it. ⛔ A dry run writes nothing, this included."""
    from datetime import timedelta
    from hato import retries

    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--dry-run", "--candidates", "1")
    assert code == 0, err
    assert not retries.path().exists(), u"a DRY run wrote the retry dates"

    code, out, err = lab.cli(capsys, "--candidates", "1")    # 03 refused: a soft negative
    assert code == 0, err
    promised = (NOW + timedelta(days=1)).timestamp()
    assert retries.load() == [promised], (
        u"the run did not write down the retry it left waiting: %s" % retries.load())

    retries.path().unlink()
    one = str(lab.media / u"frieren S2 - 05.mkv")
    code, out, err = lab.cli(capsys, "--json", "--only", one)
    assert code == 0, err
    assert retries.load() == [promised], (
        u"a run over ONE video must still write every date the DB holds -- the file "
        u"is the state DB's, not the run's rows")


def test_a_failed_read_of_the_retry_dates_leaves_the_file_alone():
    u"""⛔ None, never []. An EMPTY list written after a failed read would cancel
    every promise already on disk, and the tray would sleep through all of them.
    ⛔ And none from a DB in MEMORY, which holds only this run's rows (F5)."""
    class Cfg(object):
        lang = u"ja"

    class Broken(object):
        persistent = True

        def retry_dues(self, lang):
            raise RuntimeError("database disk image is malformed")

    class Fine(object):
        persistent = True

        def retry_dues(self, lang):
            return []

    class InMemory(Fine):
        persistent = False

    assert run_cmd._retry_dues(Broken(), Cfg()) is None
    assert run_cmd._retry_dues(Fine(), Cfg()) == [], u"the control: a real empty answer"
    assert run_cmd._retry_dues(InMemory(), Cfg()) is None, (
        u"a DB in memory answered for the file -- its dates are this run's alone, and "
        u"they would replace every promise already on disk")


def test_only_naming_something_that_is_not_a_file_is_refused(tmp_path, monkeypatch, capsys):
    u"""⛔ A run that then found nothing to do would exit 0 having looked at
    nothing -- the silent miss `--only` exists to replace."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--only", str(lab.media / u"nope.mkv"))
    assert code == 2 and u"not a file" in err


# -- ADVERSARY 2026-09-22: the tray's file, and the reach of --only ---------------------------

def _promised():
    from datetime import timedelta
    return (NOW + timedelta(days=1)).timestamp()


@pytest.mark.parametrize("spelled", [u"ja", u"jpn"])
def test_the_trays_file_holds_the_promise_however_the_language_is_spelled(
        tmp_path, monkeypatch, capsys, spelled):
    u"""ADVERSARY 2026-09-22 F1, the run half. A run records its rows under the
    RESOLVED tag -- `jpn` is `ja` -- and asked the DB for its dates with the raw
    setting, so under `lang = "jpn"` (the spelling hato's own error message
    suggests) every run emptied the file and the tray kept no promise."""
    from hato import retries
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.config.write_text(u'lang = "%s"\n' % spelled, encoding="utf-8")
    code, out, err = lab.cli(capsys, "--candidates", "1")          # 03 refused
    assert code == 0, err
    assert retries.load() == [_promised()], (
        u"lang = %r: the tray's file holds %r -- the refusal's retry is not in it"
        % (spelled, retries.load()))


@pytest.mark.parametrize("flag", [u"jpn", u"en"])
def test_a_one_off_language_flag_leaves_the_trays_promises_alone(
        tmp_path, monkeypatch, capsys, flag):
    u"""ADVERSARY 2026-09-22 F1c + R3. The tray runs the CONFIGURED language, so
    the file holds that language's dates whatever one run was asked -- a
    `--lang` one-off rewrote it with its own and dropped every other."""
    from hato import retries
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1")          # ja: 03 refused
    assert code == 0, err
    assert retries.load() == [_promised()], u"the control"
    one = str(lab.media / u"frieren S2 - 05.mkv")
    code, out, err = lab.cli(capsys, "--lang", flag, "--only", one)
    assert code == 0, err
    assert retries.load() == [_promised()], (
        u"`--lang %s` for one run rewrote the tray's file to %r" % (flag, retries.load()))


def test_a_run_whose_state_db_is_in_memory_leaves_the_trays_promises_on_disk(
        tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 F5 / R2. A store this build cannot read leaves the run
    keeping its state in MEMORY -- which holds this run's rows and nothing else,
    so its dates replaced every promise on disk with this run's."""
    import sqlite3
    from datetime import timedelta
    from hato import retries
    lab = normal(Lab(tmp_path), monkeypatch)
    raw = sqlite3.connect(str(lab.root / "state.db"))
    raw.execute("PRAGMA user_version = 99")                        # a newer hato's store
    raw.commit()
    raw.close()
    earlier = NOW + timedelta(hours=5)                             # a promise already made
    retries.save([earlier])
    code, out, err = lab.cli(capsys, "--candidates", "1")
    assert code == 0, err
    assert lab.db.persistent is False, u"the control: this run kept its state in memory"
    assert retries.load() == [earlier.timestamp()], (
        u"a run whose state DB was IN MEMORY rewrote the tray's file: %r" % retries.load())


def test_a_date_that_passed_while_nobody_looked_is_still_owed_to_the_tray(
        tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 R1. A run that held the lock across a due date
    rewrote the file with the dates still AHEAD, so the one it had not served
    vanished -- and the tray, correctly waiting for that lock, then had nothing
    to keep. The row read *"retrying now"* for ever."""
    from datetime import timedelta
    from hato import cache as cache_module, retries
    lab = normal(Lab(tmp_path), monkeypatch)
    late = lab.media / u"frieren S2 - 04.mkv"
    with state.StateDB(lab.root / "state.db", now=lambda: NOW - timedelta(hours=25)) as db:
        owed = db.record_not_found(video_hash=cache_module.video_hash(late),
                                   video_path=str(late), lang=u"ja", kind=u"soft",
                                   jimaku_entry=ENTRY, reason=u"not on jimaku yet")
    assert owed < NOW, u"the control: the date passed before this run"
    one = str(lab.media / u"frieren S2 - 05.mkv")                   # the run passes 04 by
    code, out, err = lab.cli(capsys, "--json", "--only", one)
    assert code == 0, err
    assert owed.timestamp() in retries.load(), (
        u"a date no run has kept was dropped from the tray's file: %r" % retries.load())


def test_what_a_run_leaves_behind_is_written_while_it_still_holds_the_lock(
        tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 S1. Written after the release, a run that finished
    first could overwrite the NEXT run's newer answer with its own older one --
    the window's memory of the last run, and the dates the tray keeps."""
    from hato import lastrun, paths, retries
    lab = normal(Lab(tmp_path), monkeypatch)
    held = {}

    def watching(name, real):
        def save(*args, **kwargs):
            lock = paths.lock_path()
            try:
                held[name] = json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
            except (OSError, ValueError, KeyError):
                held[name] = False
            return real(*args, **kwargs)
        return save

    monkeypatch.setattr(lastrun, "save", watching(u"last-run.json", lastrun.save))
    monkeypatch.setattr(retries, "save", watching(u"retries-due.json", retries.save))
    code, out, err = lab.cli(capsys, "--candidates", "1")
    assert code == 0, err
    assert held == {u"last-run.json": True, u"retries-due.json": True}, (
        u"written without the run lock held: %r" % held)


def test_a_list_of_videos_in_a_file_is_read_like_only(tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 A33. The window's *Look again now* over a few hundred
    waiting episodes was a command line Windows refused to start; the list goes
    in a file. ⚠ UTF-8 -- a Japanese path is the commonest line there is -- and a
    list that cannot be read is refused, never run as "every video"."""
    lab = normal(Lab(tmp_path, names=episodes(1, 6) + [u"葬送のフリーレン S2 - 07.mkv"]),
                 monkeypatch)
    listed = tmp_path / u"only.txt"
    wanted = [str(lab.media / u"frieren S2 - 05.mkv"), str(lab.media / u"葬送のフリーレン S2 - 07.mkv")]
    listed.write_text(u"\n".join(wanted) + u"\n\n", encoding="utf-8")
    code, out, err = lab.cli(capsys, "--json", "--only-list", str(listed))
    assert code == 0, err
    names = sorted(json.loads(line)[u"name"] for line in out.splitlines()
                   if json.loads(line).get(u"type") == u"video")
    assert names == sorted(os.path.basename(v) for v in wanted), names
    code, out, err = lab.cli(capsys, "--only-list", str(tmp_path / u"absent.txt"))
    assert code == 2 and u"--only-list could not be read" in err, (code, err)


def test_a_list_file_saved_with_a_byte_order_mark_is_read_whole(tmp_path, monkeypatch, capsys):
    u"""A33, the encoding. Notepad and PowerShell save UTF-8 WITH a byte-order
    mark; read as plain UTF-8 the first line became `\\ufeffD:\\...`, a video no
    walk finds -- and the whole look-again was refused (found by the M8zd
    builder: the list checks ran under PYTHONUTF8 with no mark in the file)."""
    lab = normal(Lab(tmp_path, names=episodes(1, 3)), monkeypatch)
    listed = tmp_path / u"only.txt"
    wanted = str(lab.media / u"frieren S2 - 02.mkv")
    listed.write_bytes(b"\xef\xbb\xbf" + (wanted + u"\n").encode("utf-8"))
    code, out, err = lab.cli(capsys, "--json", "--only-list", str(listed))
    assert code == 0, err
    names = [json.loads(line)[u"name"] for line in out.splitlines()
             if json.loads(line).get(u"type") == u"video"]
    assert names == [u"frieren S2 - 02.mkv"], names


def test_a_list_file_naming_no_video_is_refused_never_run_as_every_video(
        tmp_path, monkeypatch, capsys):
    u"""A33's other edge. A list of blank lines names no video -- and an empty
    `--only` is NO filter at all, so *Look again now* over it ran every video in
    the library."""
    lab = normal(Lab(tmp_path), monkeypatch)
    listed = tmp_path / u"only.txt"
    listed.write_text(u"\n\n   \n", encoding="utf-8")
    code, out, err = lab.cli(capsys, "--only-list", str(listed))
    assert code == 2 and u"names no video" in err, (code, err)


def test_only_a_video_no_walk_of_this_run_could_reach_is_refused(tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 F7. `--only` filters what the walk finds -- so a real
    file outside the folders given, inside a skipped one, or in a subfolder of a
    run that does not look in subfolders, was looked at by nobody, and the run
    exited 0. The same silent miss as a name that is not a file."""
    lab = normal(Lab(tmp_path), monkeypatch)
    elsewhere = tmp_path / u"elsewhere"
    elsewhere.mkdir()
    stray = elsewhere / u"frieren S2 - 03.mkv"
    stray.write_bytes(b"\x1aE\xdf\xa3 another copy")
    code, out, err = lab.cli(capsys, "--only", str(stray))
    assert code == 2 and u"not inside" in err and str(lab.media) in err, (code, err)

    deeper = lab.media / u"Extras"
    deeper.mkdir()
    extra = deeper / u"frieren S2 - 07.mkv"
    extra.write_bytes(b"\x1aE\xdf\xa3 an extra")
    code, out, err = lab.cli(capsys, "--no-recurse", "--only", str(extra))
    assert code == 2 and u"subfolder" in err, (code, err)

    lab.config.write_text(u"skip_folders = [%s]\n" % json.dumps(str(deeper)), encoding="utf-8")
    code, out, err = lab.cli(capsys, "--only", str(extra))
    assert code == 2 and u"skipped folder" in err, (code, err)

    lab.config.write_text(u"", encoding="utf-8")                   # the control: reachable
    code, out, err = lab.cli(capsys, "--json", "--only", str(extra))
    assert code == 0, err
    assert [json.loads(line)[u"name"] for line in out.splitlines()
            if json.loads(line).get(u"type") == u"video"] == [extra.name], out


def test_a_video_with_no_episode_number_is_trouble_in_what_hato_remembers(
        tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 F20, through a REAL run. The run says REFUSED -- the
    name carries no number -- and records a soft negative; read back, `hato
    problems` filed it under *not on jimaku yet*, and a person waited a day on
    jimaku when the fix is a rename."""
    import argparse
    import shutil
    from hato.commands import problems as problems_cmd
    lab = normal(Lab(tmp_path, names=episodes(1, 3) + [u"frieren S2.mkv"]), monkeypatch)
    # ⚠ The view lists only what is under a CONFIGURED folder -- the run's own
    # folder, written where `hato problems` reads it.
    lab.config.write_text(u"folders = [%s]\n" % json.dumps(str(lab.media)), encoding="utf-8")
    code, out, err = lab.cli(capsys, "--json", "--candidates", "1")
    assert code == 0, err
    ran = dict((o[u"name"], o) for o in (json.loads(l) for l in out.splitlines())
               if o.get(u"type") == u"video")
    assert ran[u"frieren S2.mkv"][u"outcome"] == u"REFUSED", ran[u"frieren S2.mkv"]
    lab.data.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(lab.root / "state.db"), str(lab.data / "state.db"))
    parser = argparse.ArgumentParser()
    problems_cmd.register(parser)
    assert problems_cmd.run(parser.parse_args([]), now=NOW) == 0
    text = capsys.readouterr().out
    groups = dict((block.splitlines()[0], block) for block in text.split(u"\n\n")[1:])
    mine = [heading for heading, block in groups.items() if u"frieren S2.mkv" in block]
    assert mine == [u"had a problem"], (
        u"the run said REFUSED (no episode number); what hato remembers filed it under "
        u"%r:\n%s" % (mine, text))
    assert u"No episode number was read from the video" in groups[u"had a problem"], text


def test_a_run_that_meets_another_one_says_so_in_the_stream(tmp_path, monkeypatch, capsys):
    u"""⭐ RUNBOOK 8e. Under `--json` a held lock produced an EMPTY stdout and exit 0,
    which the window read as a finished run -- it said "done" over nothing. It is
    one typed object now, in the grammar the window reads."""
    from hato.runlock import RunLock

    lab = normal(Lab(tmp_path), monkeypatch)
    held = RunLock()
    held.acquire()
    try:
        code, out, err = lab.cli(capsys, "--json")
    finally:
        held.release()
    assert code == 0
    said = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert [o[u"type"] for o in said] == [u"busy"], out
    assert said[0][u"reason"]


def test_a_run_told_to_wait_runs_once_the_other_one_finishes(tmp_path, monkeypatch, capsys):
    u"""ADVERSARY 2026-09-22 L1, through the real entry point. The tray's runs
    carry `--wait`: one meeting another run's lock queues behind it and then
    runs -- where it used to scan nothing, and the arrival it was spawned for
    was never looked at. ⚠ The control is the check above: without it, busy."""
    import threading
    from hato.runlock import RunLock

    lab = normal(Lab(tmp_path), monkeypatch)
    monkeypatch.setattr(run_cmd, "LOCK_POLL_SECONDS", 0.05)
    held = RunLock()
    held.acquire()
    finishes = threading.Timer(0.5, held.release)
    finishes.start()
    try:
        code, out, err = lab.cli(capsys, "--json", "--wait")
    finally:
        finishes.cancel()
        held.release()
    assert code == 0, err
    said = [json.loads(line) for line in out.splitlines() if line.strip()]
    kinds = [o[u"type"] for o in said]
    assert u"busy" not in kinds and kinds.count(u"video") == len(lab.names), (
        u"a run told to wait gave up or scanned part of the folder: %s" % kinds)


def test_progress_lines_arrive_before_the_objects_built_from_the_finished_run(
        tmp_path, monkeypatch, capsys):
    u"""RUNBOOK 7b. The window paints these while the run is happening.

    ⚠ The ORDER in the stream is the half this can see; that the callback fires
    DURING the run is `test_pipeline.py`'s
    `test_progress_arrives_WHILE_the_run_happens_not_after_it`, which is the
    decisive one. Both are needed: a callback that fires on time whose lines
    come out last would be green here and red there, and the reverse for a
    stream in the right order built at the end.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1", "--json", "--progress")

    assert code == 0, err
    objects = [json.loads(line) for line in out.splitlines() if line.strip()]
    kinds = [o["type"] for o in objects]
    progress = [o for o in objects if o["type"] == "progress"]

    assert progress, "--progress emitted nothing"
    assert all("phase" in o for o in progress)
    # ⛔ every progress line is ahead of every object built from the finished run
    assert kinds.index("progress") < kinds.index("video")
    assert max(i for i, k in enumerate(kinds) if k == "progress") < kinds.index("run")
    assert {"start", "found", "video", "result"} <= {o["phase"] for o in progress}
    # a live `result` row carries the three things a row shows
    rows = [o for o in progress if o["phase"] == "result"]
    assert rows and all({"video", "outcome", "episode"} <= set(o) for o in rows)


def test_the_stream_is_unchanged_for_a_consumer_that_did_not_ask_for_progress(
        tmp_path, monkeypatch, capsys):
    u"""⭐ THE CLAIM THAT MAKES 7b SAFE. `--progress` is additive: an existing
    consumer that does not ask for it sees exactly what it saw before.

    ⚠ TWO THINGS ARE EXCLUDED, AND BOTH ARE NAMED RATHER THAN QUIETLY IGNORED:
    each Lab's temp ROOT, which is in the paths, and the run object's
    `seconds`, which is wall-clock and can never repeat. Everything else is
    compared, and the control below fails if the fixture stops being
    reproducible for any OTHER reason -- which is what stops this passing by
    both sides being equally wrong.
    """
    def comparable(text, lab, keep_progress=False):
        root = str(lab.root)
        objects = []
        for line in text.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line.replace(root.replace(u"\\", u"\\\\"), u"<ROOT>"))
            if obj["type"] == "progress" and not keep_progress:
                continue
            obj.pop("seconds", None)          # wall-clock; named in the docstring
            objects.append(obj)
        return objects

    a = Lab(tmp_path / "a")
    before = comparable(
        normal(a, monkeypatch).cli(capsys, "--candidates", "1", "--json")[1], a)
    b = Lab(tmp_path / "b")
    after = comparable(
        normal(b, monkeypatch).cli(capsys, "--candidates", "1", "--json")[1], b)
    # ⛔ The control. Without it this could pass by both sides being equally wrong.
    assert before == after, "the fixture is not reproducible, so the claim below proves nothing"
    assert before, "the fixture emitted no objects at all"

    c = Lab(tmp_path / "c")
    with_flag = normal(c, monkeypatch).cli(
        capsys, "--candidates", "1", "--json", "--progress")[1]
    assert comparable(with_flag, c) == before
    # ...and the flag really did add something, so the equality above is not
    # true merely because nothing happened.
    assert len(comparable(with_flag, c, keep_progress=True)) > len(before)


def test_progress_without_json_is_refused_rather_than_ignored(tmp_path, monkeypatch, capsys):
    u"""⛔ Its lines are JSON. In the human render they would corrupt the only
    output there is, while the flag appeared to work."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--progress")
    assert code == 2
    assert "--json" in err


def test_progress_with_quiet_is_refused(tmp_path, monkeypatch, capsys):
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--json", "--progress", "--quiet")
    assert code == 2
    assert "quiet" in err


def test_no_progress_line_can_carry_the_key(tmp_path, monkeypatch, capsys):
    u"""🚨 LEDGER-HOT.md's first rule, asked of the new channel."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1", "--json", "--progress")
    assert code == 0, err
    assert run_cmd.STAND_IN_KEY not in out
    assert run_cmd.STAND_IN_KEY not in err


def test_how_many_candidates_were_really_tried_is_recoverable(tmp_path, monkeypatch, capsys):
    u"""⚠ A DEFECT RECORDED AT 5a, IN ANOTHER STEP'S FILE.

    `pipeline._all_refused` is handed `len(fresh)` -- the number of candidates
    AVAILABLE -- and prints it as *"N candidates fetched and retimed"*. With
    `--candidates 1` over a 13-file episode the refusal says **13 were fetched**
    when one was, and because it then compares `offered > tried` (13 > 13) it
    ALSO withholds the *"try `--candidates 3`"* line, which is the fix the
    person most needs. `05-interface.md` §*Evidence on every line* is exactly
    what that breaks.

    ⛔ Not repaired here -- the renderer must not rewrite the pipeline's reason
    into a second source of truth. This check pins what IS true and stays green
    when the pipeline is fixed: the measured attempts, and one match rate per
    attempt really made.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.decide = lambda base: refused()
    _code, out, _err = lab.cli(capsys, "--candidates", "1", "--json")

    refusals = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    refusals = [o for o in refusals if o.get("outcome") == pipeline.REFUSED]
    assert refusals
    for row in refusals:
        assert row["candidates_tried"] == 1, row["reason"]
        assert len(row["attempts"]) == 1
        assert len(re.findall(u"\\d+%", row["reason"].split(u"Best attempt")[0])) == 1


def test_json_carries_the_raw_multiple_the_default_output_hides(tmp_path, monkeypatch, capsys):
    u"""⭐ tsubasa's `Result` passed through verbatim, ENUMERATED not listed --
    so `excess_over_chance` is there without anybody having written it down."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1", "--json")
    written = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    ok = [o for o in written if o.get("outcome") == pipeline.CONFIDENT]
    assert ok
    # ⚠ THE CLAIM IS THE PASS-THROUGH, NOT THE ENGINE'S SCORE. This pinned 4.6 and
    # 0.96 -- the ENGINE's numbers for this lab -- and the first CI run of 1.0.2
    # (2026-09-23) read 0.91 on ubuntu py3.10, with tsubasa from PyPI: a check that
    # encoded one machine's engine. ⭐ Raw floats, unrounded, in the engine's ranges.
    raw = ok[0]["tsubasa"]
    for name in ("excess_over_chance", "match_rate"):
        assert isinstance(raw.get(name), float), (name, raw.get(name))
    assert raw["excess_over_chance"] > 1.0
    assert 0.5 < raw["match_rate"] <= 1.0


def test_json_holds_nothing_but_ndjson_when_the_lock_is_held(tmp_path, monkeypatch,
                                                            capsys):
    u"""🚨 ONE ENGLISH SENTENCE IN A STREAM A MACHINE PARSES.

    `_say` gated on `args.quiet` and never on `args.json`, so a second run under
    `--json` wrote *"hato: another hato run is in progress..."* to STDOUT -- a
    parse error beside an exit code that says the run succeeded.
    `05-interface.md` §*The window* spawns exactly `hato --json`, and an overlap
    with a manual run is the normal case it was built for. Measured 2026-09-17.
    """
    from hato import paths, runlock

    lab = normal(Lab(tmp_path), monkeypatch)
    held = runlock.RunLock(paths.lock_path())
    held.acquire()
    try:
        code, out, err = lab.cli(capsys, "--candidates", "1", "--json")
    finally:
        held.release()

    assert code == 0, err
    for line in out.split(u"\n"):
        if line.strip():
            json.loads(line)                       # ⛔ raises on a sentence
    # ...and nothing was lost: the reason is still told, on the other stream.
    assert u"another hato run is in progress" in err
    assert u"nothing was scanned and nothing was written" in err


# ===========================================================================
# 5. Mode B -- the plan
# ===========================================================================

def test_the_plan_identifies_but_writes_nothing(tmp_path, monkeypatch, capsys):
    u"""Mode B. *Identification runs (it is cheap and cached); nothing is
    downloaded, nothing written.*"""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--dry-run")

    assert code == 0, err
    assert u"--dry-run" in out.split(u"\n")[0]
    assert u"IDENTIFY" in out and u"PLAN" in out
    assert u"nothing written" in out
    assert u"Run again without --dry-run to apply." in out
    assert u"to fetch" in out
    assert lab.downloads == []
    assert sorted(p.name for p in lab.media.iterdir()) == sorted(
        lab.names + [u"frieren S2 - 01.ja.srt"])
    assert not lab.subs.exists()


def test_a_show_decided_for_free_is_never_reported_as_a_failed_lookup(
        tmp_path, monkeypatch, capsys):
    u"""🚨 MEASURED ON A REAL FOLDER, 2026-09-17. An Erai-raws release already
    carrying a Japanese track is decided for free -- nothing is ever ASKED about
    it -- and this block announced:

        ⚠  Katainaka no Ossan Ke…  → no jimaku entry matched — no reason given

    which reads as *we looked and failed*, about a show nobody looked up. ⛔ The
    tell was in the sentence: a real failure always carries a reason, because
    `resolution.py` joins every `why` it collected. Mode A had told the two apart
    from the start; only the `--dry-run` block had no branch for it.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    for name in lab.names:
        lab.tracks[name] = Answer(tracks=(Track(lang=u"ja"),))

    code, out, err = lab.cli(capsys, "--dry-run")

    assert code == 0, err
    assert u"not looked up" in out, out
    assert u"no jimaku entry matched" not in out, out
    assert u"no reason given" not in out, out
    # ⭐ And it cost nothing, which is the whole reason it was never asked. Read
    # off the line a PERSON reads, not an attribute of the harness.
    identify = [ln for ln in out.split(u"\n") if u"IDENTIFY" in ln][0]
    assert u"0 API calls" in identify, identify
    assert lab.downloads == [], lab.downloads


def test_the_plan_shows_what_the_run_would_cost(tmp_path, monkeypatch, capsys):
    u"""⭐ The API-call count, in Mode B too -- spent on IDENTIFY and estimated
    for the apply."""
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--dry-run")
    identify = [ln for ln in out.split(u"\n") if u"IDENTIFY" in ln][0]
    assert re.search(u"\\d+ API calls?", identify), identify
    assert re.search(u"est\\. \\d+ API calls?", out), out


# ===========================================================================
# 6. layout -- the things that go wrong silently
# ===========================================================================

@pytest.mark.parametrize("flags", [(), ("--verbose",), ("--dry-run",),
                                   ("--dry-run", "--verbose")])
def test_no_line_runs_past_the_width_even_with_japanese(tmp_path, monkeypatch,
                                                        capsys, flags):
    u"""⚠ A kanji is TWO display columns. Padding measured with `len()` walks a
    Japanese line one column further off the screen per character, and every
    check still passes -- tsubasa shipped fifty green checks over exactly that.

    🚨 AND IT IS ASKED OF EVERY FLAG THAT ADDS LINES. This check passed NO flag
    for its whole life, so it could not see the lines `--verbose` adds -- and
    `_verbose_attempts` and `_verbose_tail` appended raw strings and never
    called `wrap`. Measured 2026-09-17: 0 lines over 92 without the flag, 5
    with it, the widest at 125 columns. ⚠ `--verbose` is what a person is told
    to run when something is wrong, which makes it the one output that most
    has to be readable.
    """
    lab = normal(Lab(tmp_path, folder=u"\u7247\u7530\u820e\u306e\u304a\u3063\u3055\u3093"),
                 monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1", *flags)
    long_lines = [ln for ln in out.split(u"\n") if columns(ln) > report.DEFAULT_WIDTH]
    assert not long_lines, u"\n".join(u"%3d  %s" % (columns(ln), ln) for ln in long_lines)
    assert u"\u7247\u7530\u820e" in out                    # ...and it is still identifiable
    if flags == (u"--verbose",):
        # ...and the flag really did add the lines whose width is in question.
        # (Mode B has no verbose tail -- `render_plan` hands `verbose` to the
        # problem rows alone. Noted, not changed: that is the ruled shape.)
        assert u"raw multiple" in out, out


def test_a_right_aligned_stat_never_collides_with_a_long_left_half():
    u"""⛔ Two lines rather than one line past the width. A negative pad becomes
    zero in most formatters and the stat then sits jammed against a title that
    has already run off the screen."""
    short = report.pair(u"hato  D:\\Anime", u"24 videos", 40)
    assert len(short) == 1
    assert columns(short[0]) == 40
    long = report.pair(u"hato  " + u"x" * 60, u"24 videos", 40)
    assert len(long) == 2
    assert all(columns(ln) <= 60 for ln in long[1:])
    assert long[1].strip() == u"24 videos"


def test_a_token_longer_than_the_line_is_broken_not_left_to_run_off():
    u"""🚨 FOUND BY LOOKING AT A REAL RUN, not by a check. An ERROR reason
    carried an absolute path that alone was wider than the line; the terminal
    then wrapped it itself -- at a column of its choosing and with NO hanging
    indent. ⛔ Breaking it here is strictly better than that."""
    path = u"C:\\Users\\Someone\\Documents\\A Very Deep\\Folder Tree\\that\\keeps\\going" \
           u"\\and\\going\\until\\it\\is\\wider\\than\\any\\terminal\\fixtures"
    lines = report.wrap(u"could not be read: nothing recorded under %s answers the request"
                        % path, 60, first=u"        ", rest=u"        ")
    assert len(lines) > 1
    assert all(columns(ln) <= 60 for ln in lines), lines
    assert all(ln.startswith(u"        ") for ln in lines[1:]), lines
    assert u"".join(ln.strip() for ln in lines).count(u"fixtures") == 1


def test_two_shows_are_told_apart_on_every_row(tmp_path, monkeypatch, capsys):
    u"""🚨 ALSO FOUND BY LOOKING. `_discover` groups by (title, season), so
    `frieren S1` and `frieren S2` are two shows whose TITLE is the same word --
    and every row in both was labelled `frieren`, which is no label at all.

    ⚠ The rows are run-wide because problems come first; a row that cannot name
    its show is therefore unattributable, which is the cost of that ordering and
    the thing that has to be paid for.
    """
    names = [u"frieren S2 - %02d.mkv" % n for n in (1, 2, 3)]
    names += [u"frieren S1 - %02d.mkv" % n for n in (1, 2)]
    lab = Lab(tmp_path, names=names).install(monkeypatch)
    lab.decide = lambda base: confident()
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    assert len([s for s in out.split(u"\n") if s.startswith(u"  ") and u"\u21b3" not in s
                and u"Frieren" in s]) == 2, out
    labelled = labelled_rows(out)
    assert labelled
    assert any(u"frieren S1" in ln for ln in labelled), out
    assert any(u"frieren S2" in ln for ln in labelled), out


def test_two_shows_that_differ_past_the_column_still_get_different_labels(
        tmp_path, monkeypatch, capsys):
    u"""🚨 THE `frieren` DEFECT, RE-ARMED BY A LENGTH NOBODY MEASURED IN COLUMNS.

    The fix above put the season in the label and then ran the whole thing
    through `clip(label, 16)` -- and a kanji is TWO columns, so sixteen columns
    is EIGHT characters. Two seasons of a nine-character Japanese title came out
    byte-identical: the same *no label at all* the check above exists to forbid,
    in the alphabet this project is actually for.

    ⚠ The old check used ASCII names that differ well inside sixteen columns, so
    it could not see this. Measured 2026-09-17.
    """
    lab = two_seasons(tmp_path, monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    rows = labelled_rows(out)
    assert len(rows) == 2, out
    assert rows[0][:24] != rows[1][:24], out
    assert lab.client.metered == 0                 # ⛔ and it cost nothing to prove


def test_a_collapsed_skip_row_names_its_own_show(tmp_path, monkeypatch, capsys):
    u"""🚨 ONE LABEL FOR A GROUP COLLAPSED ACROSS EVERY SHOW.

    The skips of a kind are collapsed onto one line, and the group was keyed on
    the KIND alone -- so two shows' skips shared a line and it carried
    `rows[0]`'s label. Measured 2026-09-17: a row read `frieren S1  01 09` when
    S1 had no episode 1 skipped, and S2's episode was filed under S1.

    ⛔ A row that names the WRONG show is worse than one that names none: a
    person acts on it. ⚠ And the row checks filtered to OK/PROBLEM/FLAGGED,
    which structurally excluded every skip marker -- see `ROW_MARKS`.
    """
    lab = two_seasons(tmp_path, monkeypatch, present=True)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")

    skips = [ln for ln in out.split(u"\n")
             if ln.lstrip().startswith(report.SKIP_MARK[pipeline.PRESENT])]
    assert len(skips) == 2, out                    # one per show, never one for both
    assert skips[0][:24] != skips[1][:24], out
    assert lab.client.metered == 0


def test_east_asian_width_is_measured_not_counted():
    u"""⚠ The numbers are written down HERE, not asked of the thing under test."""
    assert report.cells(u"abc") == 3
    assert report.cells(u"\u7247\u7530\u820e") == 6          # 片田舎
    assert report.cells(u"\u7247\u7530\u820e S2") == 9
    assert report.cells(u"") == 0
    assert report.cells(u"\u7247") != len(u"\u7247")


# ===========================================================================
# 7. the run lock -- ⚠ the CLI's, because `pipeline.run` takes none
# ===========================================================================

def test_a_second_run_exits_cleanly_instead_of_racing(tmp_path, monkeypatch, capsys):
    u"""*Two hato processes at once -- the second exits with a clear message
    rather than racing.* 🚨 And it exits 0: an overlap with a manual run is a
    normal consequence of scheduling, not a fault (`hato/commands/run.py`)."""
    from hato import paths, runlock

    lab = normal(Lab(tmp_path), monkeypatch)
    held = runlock.RunLock(paths.lock_path())
    held.acquire()
    try:
        code, out, err = lab.cli(capsys, "--candidates", "1")
    finally:
        held.release()

    assert code == 0, err
    assert u"another hato run is in progress" in (out + err)
    assert u"nothing was scanned and nothing was written" in err
    assert lab.downloads == []


def test_the_lock_is_released_so_the_next_run_gets_it(tmp_path, monkeypatch, capsys):
    from hato import paths

    lab = normal(Lab(tmp_path), monkeypatch)
    assert lab.cli(capsys, "--candidates", "1")[0] == 0
    assert not Path(paths.lock_path()).exists()
    assert lab.cli(capsys, "--candidates", "1")[0] == 0


# ===========================================================================
# 8. the log
# ===========================================================================

def test_every_run_appends_a_plain_block_to_the_log(tmp_path, monkeypatch, capsys):
    u"""*It writes a log, or a 3am failure is invisible for ever.* ⛔ And never
    with ANSI in it."""
    lab = normal(Lab(tmp_path), monkeypatch)
    assert lab.cli(capsys, "--candidates", "1")[0] == 0

    log = lab.data / "hato.log"
    assert log.is_file(), sorted(p.name for p in lab.data.iterdir())
    text = log.read_text(encoding="utf-8")
    assert text.startswith(u"=== hato ")
    assert u"\x1b[" not in text
    assert u"Sousou no Frieren 2nd Season" in text
    assert u"API call" in text


def test_the_log_rotates_to_log_keep_runs(tmp_path, monkeypatch, capsys):
    u"""`log.keep = N` -- *rotate after N runs*. ⚠ Append first, trim second:
    the append cannot lose anything, and the trim is temp-plus-rename."""
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.config.write_text(u"[log]\nkeep = 2\n", encoding="utf-8")
    for _ in range(4):
        assert lab.cli(capsys, "--candidates", "1")[0] == 0

    text = (lab.data / "hato.log").read_text(encoding="utf-8")
    assert text.count(u"=== hato ") == 2, text[:200]


def test_the_log_is_written_even_when_stdout_is_silenced(tmp_path, monkeypatch, capsys):
    u"""`--quiet` is what the scheduler passes. ⛔ The record must survive it."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1", "--quiet")

    assert code == 0, err
    assert out == u""
    assert u"API call" in (lab.data / "hato.log").read_text(encoding="utf-8")


def test_a_log_that_cannot_be_written_is_a_note_not_a_failure(tmp_path, monkeypatch, capsys):
    u"""⛔ The run happened. A log that could not be written says so and does
    not undo it."""
    lab = normal(Lab(tmp_path), monkeypatch)
    blocked = lab.data / "hato.log"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.mkdir()                      # a directory where the file should be
    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 0, err
    assert u"could not be written" in err
    assert u"API call" in out


# ===========================================================================
# 9. exit codes -- ⛔ a refusal is not a failure
# ===========================================================================

def test_a_run_full_of_refusals_still_exits_zero(tmp_path, monkeypatch, capsys):
    u"""⛔ *Refusals and NOT_FOUNDs are normal outcomes and must not turn a
    scheduled task red.*"""
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.decide = lambda base: refused()
    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 0, err
    assert u"refused" in summary_line(out)


def test_a_bad_config_exits_one(tmp_path, monkeypatch, capsys):
    lab = normal(Lab(tmp_path), monkeypatch)
    lab.config.write_text(u'folders = ["Anime"]\n', encoding="utf-8")
    code, _out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 1
    assert u"relative path" in err


def test_nothing_to_scan_is_a_usage_mistake_and_says_so(tmp_path, monkeypatch, capsys):
    u"""⭐ Bare `hato` with nothing configured. `10-deployment.md` schedules
    `hato --quiet` with no folder, so "no arguments" has to mean *do the job*;
    with nothing configured either, it is the person who has not said what."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code = cli.main([])
    err = capsys.readouterr().err

    assert code == 2
    assert u"no folder to scan" in err
    assert u"commands:" in err                 # the screen they were looking for


def test_a_run_that_stopped_early_exits_one(tmp_path, monkeypatch, capsys):
    u"""⚠ THE ONE IN-RUN CONDITION THAT IS A FAILURE. A 401 stops the whole run
    and the videos after it were never looked at -- a green task would say the
    library is up to date when nothing was checked."""
    lab = normal(Lab(tmp_path), monkeypatch)
    real_run = pipeline.run

    def stopping(settings, **kwargs):
        made = real_run(settings, **kwargs)
        made.stopped = u"jimaku rejected the key (401) -- the run stopped"
        return made

    monkeypatch.setattr(pipeline, "run", stopping)
    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 1
    assert u"THE RUN STOPPED HERE" in out
    assert u"401" in err


# ===========================================================================
# 9b. 🚨 THE FLAGS AND THE FILE ARE TWO ROADS TO ONE SETTING
# ===========================================================================
# `config.toml` refuses each of these by name and the flags refused none of
# them, so a value the file would not take did exactly the damage the file's
# refusal exists to prevent. Every sentence below is `hato/config.py`'s own,
# called and never re-typed -- `hato/commands/run.py` check_flags.

def test_candidates_below_one_is_refused_before_it_can_poison_the_folder(
        tmp_path, monkeypatch, capsys):
    u"""🚨 THE ONE DIGIT THAT TOOK A FOLDER OUT FOR A DAY.

    `--candidates 0` made `fresh[:0]` -- nothing tried, nothing downloaded --
    and the pipeline still wrote the soft negative that records *it asked*. The
    corrected run then reported *"asked for recently and not there yet"* and
    made ZERO API calls.

    ⚠ The second half of this check is the whole point: refusing the flag is
    only worth anything if the state DB was never written.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "0")

    assert code == 2, out + err                    # ⚠ usage, not "it could not run"
    assert u"at least 1" in err and u"--candidates" in err
    assert lab.downloads == []
    # ⭐ AND THE NEXT RUN IS UNHARMED -- nothing was recorded about these videos.
    code, out, err = lab.cli(capsys, "--candidates", "3")
    assert code == 0, err
    assert lab.downloads, out
    assert u"asked for recently" not in out, out


def test_a_negative_candidates_count_is_refused_too(tmp_path, monkeypatch, capsys):
    u"""⚠ `fresh[:-1]` is *all but the last*, silently. A slice takes any integer
    and means something different for each one."""
    lab = normal(Lab(tmp_path), monkeypatch)
    code, _out, err = lab.cli(capsys, "--candidates", "-1")

    assert code == 2
    assert u"at least 1" in err
    assert lab.downloads == []


@pytest.mark.parametrize("flag", ["--out", "--subs-dir"])
def test_a_relative_out_or_subs_dir_is_refused_not_resolved_against_the_cwd(
        tmp_path, monkeypatch, capsys, flag):
    u"""🚨 MEASURED, AND THE WORST OF THESE.

    `--subs-dir kept` put the KEPT ORIGINALS -- the files `05-interface.md` says
    hato may NEVER delete -- in a folder called `kept` under the working
    directory. From Task Scheduler that directory is Windows' own system folder.

    ⛔ The scanned FOLDERS are deliberately not held to this rule: a person in a
    terminal types `hato .`, and a scanned folder is read, never written.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    where = tmp_path / "somewhere"
    where.mkdir()
    monkeypatch.chdir(where)
    code = cli.main([str(lab.media), flag, "kept"])
    captured = capsys.readouterr()

    assert code == 2, captured.out + captured.err
    assert u"relative path" in captured.err and flag in captured.err
    assert list(where.iterdir()) == [], list(where.iterdir())
    assert lab.downloads == []


@pytest.mark.parametrize("tag, why", [
    # ⚠ `zz` since 2026-09-23 -- this row was `jp`, which tsubasa reads as
    # Japanese from 0.1.8 (RUNBOOK 9c). No language in any version.
    (u"zz", u"tsubasa reads it as `und`, which matches every untagged subtitle"),
    (u"jap", u"not a language code and never was"),
    (u"ja-JP", u"correct BCP 47 and broken on Jellyfin"),
    (u"japanese", u"not a 2- or 3-letter code"),
])
def test_a_language_the_file_refuses_is_refused_by_the_flag_too(
        tmp_path, monkeypatch, capsys, tag, why):
    u"""⚠ BOTH ROADS, ONE ANSWER.

    `lang = "ja-JP"` in the file is refused by name and `--lang ja-JP` was waved
    through; `--lang jp` reached four frames into the run before anything said
    so, spending the key, the lock and a DB handle on the way. Refused before
    the run now, at exit 2 -- a mistyped flag is a usage mistake, not *"hato
    could not run"*.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    code, out, err = lab.cli(capsys, "--candidates", "1", "--lang", tag)

    assert code == 2, u"%s: %s" % (why, out + err)
    assert tag in err, err
    assert u"Traceback" not in err
    assert lab.downloads == []


# ===========================================================================
# 9c. ⚠ A SENTENCE WHERE A TRACEBACK USED TO BE
# ===========================================================================
# ⛔ A traceback through the scheduled path is invisible: the launcher's log
# line reads only *"hato exited 1"*, and nobody is watching the console.

def test_a_lock_that_cannot_be_created_is_a_sentence_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    u"""🚨 `runlock.py` promises *"a message that says what to delete"*, and it
    kept that promise only for a lock another RUN holds. A folder sitting where
    the lock file goes -- or a read-only root, or an antivirus holding the
    handle -- raised a raw PermissionError straight out of `os.open`. Measured
    2026-09-17."""
    from hato import paths

    lab = normal(Lab(tmp_path), monkeypatch)
    lock = Path(paths.lock_path())
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.mkdir()                                   # ⚠ a DIRECTORY, where a file goes

    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 1, out + err
    assert u"Traceback" not in err, err
    assert str(lock) in err                        # it names the path...
    assert u"run lock" in err and u"remove it" in err     # ...and what to do with it
    assert lab.downloads == []


def test_a_relative_HATO_CACHE_is_one_line_like_a_relative_HATO_CONFIG(
        tmp_path, monkeypatch, capsys):
    u"""⚠ THE TWO OVERRIDES WERE NOT TREATED ALIKE.

    `run()` caught `paths.PathError` around `config.load()` and not around
    `Settings.from_config` -- and `cfg.subs_dir_resolved` is a lazy property
    that reads HATO_CACHE there. So a relative HATO_CONFIG was one clean line
    and a relative HATO_CACHE was 22 lines of traceback, for the same mistake.
    Measured 2026-09-17.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    monkeypatch.setenv("HATO_CACHE", "relative-dir")

    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 1, out + err
    assert u"Traceback" not in err, err
    assert err.strip().count(u"\n") == 0, err     # ONE line, like the other override
    assert u"HATO_CACHE" in err and u"absolute" in err


# ===========================================================================
# 10. ⭐ the snapshot -- both modes
# ===========================================================================

def _stable(text, lab):
    u"""Everything a second run legitimately changes, replaced by a token: the
    elapsed seconds and the retry dates. ⛔ Nothing else -- a snapshot that
    normalised the output would assert nothing.

    ⚠ THE HEADER IS DROPPED, and only the header. It carries an absolute temp
    path whose LENGTH decides whether the count fits beside it, so a snapshot
    containing it would assert the length of pytest's tmp dir. Its shape is
    checked by `test_a_full_run_...` and `test_a_right_aligned_stat_...`.
    """
    text = text.split(u"\n\n", 1)[1]
    text = re.sub(u"\\d+\\.\\d s", u"<T> s", text)
    text = re.sub(u"20\\d\\d-\\d\\d-\\d\\d", u"<DATE>", text)
    return text.rstrip()


#: \u26a0 "8 offered" SINCE RUNBOOK 9a (2026-09-23), and it was 13: 5 of episode 3's
#: thirteen are `.srt`, which the ruled default -- `.ass` preferred, the other kind
#: never -- no longer offers. Measured whole (a line diff of the full render, not
#: pytest's elided one): that number is the ONLY change.
SNAPSHOT_RUN = u"""\
  Sousou no Frieren 2nd Season  S2
  \u21b3 parsed "frieren" \u2192 jimaku entry 11446
                                                              2 API calls \u00b7 120 files listed

  \u2717  03   REFUSED     1 candidate fetched and retimed, none held (31% match). Try
                      `--candidates 3` to reach more of the 8 offered, or pair one by hand
                      with `hato sync`. Best attempt: [NanakoRaws] Sousou no Frieren S2 - 03
                      (NTV 1080p HEVC AAC).ass: 31% match -- the timing does not hold.
                      Nothing new will be listed for it before <DATE>.
  \u2717  24   NOT FOUND   No release on the entry places a file on episode 24. Will retry after
                      <DATE>.

  \u2299  01               subtitle already present \u2014 skipped, no request made
  \u2298  02               no subtitle track in the video \u2014 can't sync yet, nothing downloaded

  \u2713  04   \u2193 108 B   +0.13s     96% \u00b7 locked      \u2192 frieren S2 - 04.ja.ass
  \u2713  05   \u2193 95 B    +0.13s     96% \u00b7 locked      \u2192 frieren S2 - 05.ja.ass
  \u2691  06   \u2193 95 B    -33.07 / -42.96 @3:18   91% \u00b7 strong \u00b7 2 segments
                                            \u2192 frieren S2 - 06.ja.ass

  3 fetched \u00b7 1 skipped \u00b7 1 can't sync yet \u00b7 1 not found \u00b7 1 refused     2 API calls \u00b7 <T> s"""


SNAPSHOT_PLAN = u"""\
  IDENTIFY                                                                       2 API calls
  \u2713  frieren                 \u2192 jimaku 11446    7 vids \u00b7 120 subs

  PLAN                                                                       nothing written
     4 to fetch \u00b7 1 already present \u00b7 1 no subtitle track \u00b7 1 not on jimaku
     est. 1 API call to apply this \u2014 identification is cached now, and the downloads
     themselves are unmetered

  \u2717  24   NOT FOUND   No release on the entry places a file on episode 24. \u2014 nothing was
                      recorded, so nothing is scheduled (dry run)

  Run again without --dry-run to apply."""


def test_the_snapshot_of_mode_a(tmp_path, monkeypatch, capsys):
    u"""⭐ The whole rendered run, byte for byte. A snapshot is what makes an
    accidental change to the ruled grammar visible instead of plausible.

    ⚠ THE REFUSAL'S PROSE IS THE PIPELINE'S, NOT THIS STEP'S. It used to say
    *"13 candidates fetched and retimed"* for a run that fetched ONE, because
    `_all_refused` was handed the number AVAILABLE -- and, because it then asked
    `offered > tried` (13 > 13), it WITHHELD the line telling the person to raise
    the cap, on the row that most needed it.

    ⭐ **Recorded at 5a, fixed by the orchestrator 2026-09-17, and this snapshot
    is what went red to prove the fix landed** -- exactly the snapshot working.
    Two run-on sentences were fixed with it, both visible only in the rendered
    line: *"does not hold Nothing new will be listed"* and *"episode 24. -- will
    retry"*. ⚠ Every assertion around them was green; only LOOKING showed it.
    """
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--candidates", "1")
    assert _stable(out, lab) == SNAPSHOT_RUN


def test_the_snapshot_of_mode_b(tmp_path, monkeypatch, capsys):
    lab = normal(Lab(tmp_path), monkeypatch)
    _code, out, _err = lab.cli(capsys, "--dry-run")
    assert _stable(out, lab) == SNAPSHOT_PLAN


# ===========================================================================
# 10b. ⭐ ONE RUN ON A REAL VIDEO, THROUGH THE REAL tsubasa
# ===========================================================================

def test_a_real_video_renders_a_real_verdict_not_a_stubbed_one(tmp_path, monkeypatch, capsys):
    u"""⭐ Everything above this believes a stub about what a verdict is.

    A real 75-cue `.mkv` built by ffmpeg, an English track so hato fetches, the
    real `tsubasa.sync()` reading the container and deciding, and the real
    written file on disk -- rendered by 5a. ⚠ The word on the row has to come
    from tsubasa's CLOSED vocabulary, which is the check the ruled mock cannot
    give: its `certain` was removed from that vocabulary on 2026-09-09.

    ⛔ ffmpeg missing is an ERROR here, not a skip (`tests/_media.py`): a
    contract check that quietly does not run is the failure it exists to stop.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    import _media

    # 🚨 THIS CHECK'S OWN tsubasa STORE. `port.sync(results=None)` writes a
    # record into the per-user results DB, and `conftest` points every suite in
    # a run at ONE redirected store -- so this row landed where
    # `test_port.py::...disturbs_nothing_else` counts rows, and (the video being
    # byte-identical bar its name) UPDATED the row that check expects to create.
    # ⛔ Found by running the two suites in one process. A check that only holds
    # while it runs after its neighbour is not holding.
    monkeypatch.setenv("TSUBASA_CACHE", str(tmp_path / "tsubasa-store"))
    made = _media.build(tmp_path / "real", stem=u"frieren S2 - 04", track_language=u"eng")
    lab = Lab(tmp_path / "real", names=[], folder=u"media").install(monkeypatch)
    lab.real_tsubasa = True
    lab.bytes_for = lambda item: made.subtitle.read_bytes()

    code, out, err = lab.cli(capsys, "--candidates", "1")

    assert code == 0, err + out
    written = rows(out, report.OK)
    assert len(written) == 1, out
    row = written[0]
    assert u"04" in row
    assert any(w in row for w in (u"locked", u"strong", u"fair", u"uncertain")), row
    # ⭐ tsubasa's own measurement, not a number this suite chose: the download
    # is `_media.SHIFT` seconds late, so the offset is about -SHIFT.
    shift = re.search(u"([-+]\\d+\\.\\d\\d)s", row)
    assert shift, row
    assert abs(float(shift.group(1)) + _media.SHIFT) < 1.0, row
    # ⭐ AND THE FILE IS REALLY THERE, under the name the row shows.
    name = row.split(report.ARROW)[-1].strip()
    assert (made.media_dir / name).is_file(), made.listing(made.media_dir)
    assert sorted(p.name for p in lab.subs.rglob("*") if p.is_file())


# ===========================================================================
# 11. ⭐ 5c -- the launcher
# ===========================================================================

def launcher_env(work, extra=None):
    env = dict(os.environ)
    env.update(HATO_CACHE=str(work / "data"), HATO_CONFIG=str(work / "config.toml"),
               HATO_NO_NETWORK="1", HATO_JIMAKU_KEY="not-a-real-key",
               HATO_PYTHON=sys.executable, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("HATO_KEYFILE", None)
    env.pop("HATO_RUN_PAUSE", None)
    env.pop("HATO_NO_PAUSE", None)
    env.pop("HATO_RUN_DEBUG", None)
    env.update(extra or {})
    return env


def launch(work, args=(), extra_env=None, cwd=None):
    u"""Run the real `.cmd` in a real `cmd.exe`. -> CompletedProcess (text)."""
    proc = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c", str(LAUNCHER)] + list(args),
                          env=launcher_env(work, extra_env), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=str(cwd if cwd is not None else work), timeout=180)
    proc.out = proc.stdout.decode("utf-8", "replace")
    proc.errors = proc.stderr.decode("utf-8", "replace")
    return proc


def refusing_folder(tmp_path, name="Show S1"):
    u"""⭐ A folder that REFUSES with zero network and zero API calls: a video
    holding two episodes is refused on its NAME, before the hash, the container
    or any request (`hato/pipeline.py` `_gate`). That is what makes *"a refusal
    exits 0"* provable in a suite that may not reach jimaku."""
    work = Path(tmp_path)
    media = work / name
    media.mkdir(parents=True, exist_ok=True)
    (media / (u"%s - 01-02.mkv" % name)).write_bytes(b"\x1aE\xdf\xa3two-episodes")
    (work / "config.toml").write_text(
        u'folders = ["%s"]\n' % str(media).replace(u"\\", u"/"), encoding="utf-8")
    return work, media


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_exits_zero_on_a_refusal(tmp_path):
    u"""🚨 THE ONE THAT MATTERS MOST. ⛔ *Refusals and NOT_FOUNDs are normal
    outcomes and must never turn a scheduled task red* -- a task that goes red
    every night trains its owner to ignore it."""
    work, _media = refusing_folder(tmp_path)
    proc = launch(work)

    assert proc.returncode == 0, proc.out + proc.errors
    assert u"REFUSED" in proc.out
    assert u"1 refused" in proc.out


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_exits_nonzero_only_when_it_could_not_run(tmp_path):
    work, _media = refusing_folder(tmp_path)
    (work / "config.toml").write_text(u'folders = ["Anime"]\n', encoding="utf-8")
    proc = launch(work)

    assert proc.returncode == 1, proc.out + proc.errors
    assert u"relative path" in proc.errors


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_a_dragged_folder_beats_the_config(tmp_path):
    u"""⭐ *Windows passes the path as `%1`* -- the folder picker, at zero cost."""
    work, _media = refusing_folder(tmp_path)
    other = work / "Other S2"
    other.mkdir()
    (other / u"Other S2 - 07-08.mkv").write_bytes(b"\x1aE\xdf\xa3dragged")
    proc = launch(work, [str(other)])

    assert proc.returncode == 0, proc.out + proc.errors
    assert other.name in proc.out.split(u"\n")[0]      # ⚠ a long path is clipped from the left
    assert u"episodes 7-8" in flat(proc.out)
    assert u"Show S1" not in proc.out                  # ⛔ and the config's folder was NOT run


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_does_not_depend_on_the_working_directory(tmp_path):
    u"""⭐ *Task Scheduler starts a process somewhere unexpected.* Run from two
    unrelated directories; the answer must be the same."""
    work, media = refusing_folder(tmp_path)
    elsewhere = Path(tmp_path) / "somewhere else"
    elsewhere.mkdir()

    here = launch(work, [str(media)], cwd=work)
    there = launch(work, [str(media)], cwd=elsewhere)
    root = launch(work, [str(media)], cwd=Path(os.environ.get("SystemRoot", "C:\\Windows")))

    assert here.returncode == there.returncode == root.returncode == 0
    strip = lambda text: re.sub(u"\\d+\\.\\d s", u"<T> s", text)
    assert strip(here.out) == strip(there.out) == strip(root.out)


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_never_pauses_when_output_is_not_a_console(tmp_path):
    u"""🚨 A scheduled run that pauses waits for ever HOLDING THE RUN LOCK, and
    every later run then exits on that lock: hato silently stops working."""
    work, _media = refusing_folder(tmp_path)
    piped = launch(work, extra_env={"HATO_RUN_DEBUG": "1"})

    assert u"Press any key" not in piped.out
    assert u"console=0" in piped.errors
    assert u"pause=" in piped.errors and u"pause=1" not in piped.errors


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_quiet_never_pauses_and_prints_nothing(tmp_path):
    u"""What Task Scheduler passes. ⛔ No prompt, ever -- not one."""
    work, _media = refusing_folder(tmp_path)
    proc = launch(work, ["--quiet"], extra_env={"HATO_RUN_DEBUG": "1"})

    assert proc.returncode == 0, proc.out + proc.errors
    assert proc.out.strip() == u""
    assert u"quiet=1" in proc.errors
    assert u"pause=1" not in proc.errors
    assert (work / "data" / "hato.log").is_file()


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_pause_branch_works_and_does_not_hang(tmp_path):
    u"""⚠ THE BRANCH A HEADLESS SUITE CANNOT REACH BY DETECTION. `HATO_RUN_PAUSE`
    forces the decision -- it is also the escape hatch for an environment where
    the detection is wrong -- and the prompt is the proof the branch ran."""
    work, _media = refusing_folder(tmp_path)
    proc = launch(work, extra_env={"HATO_RUN_PAUSE": "1", "HATO_RUN_DEBUG": "1"})

    assert u"pause=1" in proc.errors
    assert u"Press any key" in proc.out
    assert proc.returncode == 0, proc.out + proc.errors


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_hands_down_no_colour_when_output_is_not_a_console(tmp_path):
    u"""⭐ Rule 3, from the launcher's side: hato decides by its own `isatty`,
    AND the launcher passes `--no-color`. Two mechanisms, one answer -- because
    a log full of `ESC[32m` is the failure nobody notices until they read it."""
    work, _media = refusing_folder(tmp_path)
    proc = launch(work)

    assert u"\x1b[" not in proc.out
    assert u"\x1b[" not in (work / "data" / "hato.log").read_text(encoding="utf-8")
    # 🚨 FOUND BY BREAKING IT: deleting the launcher's half changes NOTHING
    # observable, because hato's own `isatty` already answered. A behavioural
    # check cannot tell two agreeing mechanisms apart, so the launcher's half is
    # pinned where it lives -- in its source -- or it can be removed silently
    # and the rule survives only as long as hato's detection does.
    text = LAUNCHER.read_text(encoding="ascii")
    assert u'if "%CONSOLE%"=="0" set "COLOUR=--no-color"' in text
    assert u"%COLOUR%" in text.split(u"-m hato")[1].split(u"\n")[0]


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_the_launcher_records_a_failure_it_could_not_leave_to_hato(tmp_path):
    u"""*Failures survive to the next time someone looks.* hato writes the run;
    this line covers the exits hato never got to record."""
    work, _media = refusing_folder(tmp_path)
    (work / "config.toml").write_text(u'folders = ["Anime"]\n', encoding="utf-8")
    proc = launch(work)

    assert proc.returncode == 1
    text = (work / "data" / "hato.log").read_text(encoding="utf-8")
    assert u"hato-run.cmd: hato exited 1" in text


def test_the_launcher_is_ascii_only_and_crlf():
    u"""🚨 A non-ASCII byte in a `.cmd` is decoded in the console's codepage,
    not UTF-8, and one mis-decoded character opens a string that breaks the
    parse lines away from where it was written. Measured on this machine for
    `.ps1`; the same decoder is at fault here."""
    raw = LAUNCHER.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, u"non-ASCII bytes at %r" % bad[:5]
    assert b"\r\n" in raw
    assert raw.count(b"\n") == raw.count(b"\r\n"), "a bare LF in a .cmd"


def test_the_launcher_forwards_every_flag_it_is_given(tmp_path):
    u"""⛔ It is a launcher, not a second front end: it adds `--no-color` when
    stdout is not a console and passes everything else through untouched.

    🚨 AND IT FORWARDS THEM QUOTED, NEVER AS `%*`. `%*` is the RAW command-line
    tail: forwarding it re-parses it, so whether a folder called `Tom&Jerry`
    survives depended on whether the CALLER thought to quote it. Pinned in the
    source because a behavioural check cannot tell a quoted forward from a lucky
    one -- see the ampersand check below for the half that can.
    """
    text = LAUNCHER.read_text(encoding="ascii")
    assert u'-m hato%HATO_ARGS% %COLOUR%' in text
    assert u"-m hato %*" not in text
    body = text.split(u":bootlog")[0]
    assert u"%*" not in body, u"the launcher re-expands the raw command-line tail"
    flags = set(re.findall(u'"(--[a-z-]+)"', text))
    assert flags <= {u"--quiet"}, u"the launcher inspects flags it should forward: %s" % flags


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_a_folder_named_with_an_ampersand_is_scanned_whole(tmp_path):
    u"""🚨 ONE WORD, ONE AMPERSAND, AND THE FOLDER IS GONE.

    Windows does not quote a dropped path that has no space in it, so dropping
    `Tom&Jerry` on the launcher makes CMD cut its own command line at the `&`
    BEFORE `%1` exists. Measured 2026-09-17: hato was handed the folder path cut
    short at `Tom`, which nobody named; `Jerry` then ran as a command
    (*"'Jerry' is not recognized..."*) and ITS exit code, 1, was reported for a
    run that had been fine.

    ⚠ THE OLD CHECKS ALL USED A NAME WITH A SPACE IN IT (`Show S1`,
    `Other S2`), and a space is exactly what makes Python -- and Explorer --
    quote the argument. They could not fail on this.
    """
    work, media = refusing_folder(tmp_path, name="Tom&Jerry")
    proc = launch(work, [str(media)])

    assert proc.returncode == 0, proc.out + proc.errors
    assert u"Tom&Jerry" in proc.out.split(u"\n")[0], proc.out
    assert u"1 refused" in proc.out                    # the video really was scanned
    assert u"not recognized" not in proc.errors, proc.errors
    assert proc.errors.strip() == u"", proc.errors


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_a_quoted_ampersand_path_was_never_broken_and_still_is_not(tmp_path):
    u"""⚠ THE OTHER HALF, AND THE ONE A REWRITE COULD BREAK. A caller that quotes
    the path -- Task Scheduler, a script, Explorer when the name has a space --
    always worked. The repair above must not disturb it."""
    work, media = refusing_folder(tmp_path, name="Two Words&Here")
    proc = launch(work, [str(media)])

    assert proc.returncode == 0, proc.out + proc.errors
    assert u"Two Words&Here" in proc.out, proc.out
    assert u"1 refused" in proc.out


@pytest.mark.skipif(os.name != "nt", reason="hato-run.cmd is the Windows launcher")
def test_a_script_that_calls_the_launcher_is_still_running_afterwards(tmp_path):
    u"""🚨 THE REPAIR PATH ENDS WITH `exit`, NOT `exit /b` — and `exit` ends the
    CALLER'S shell, not just this script.

    It has to: the repair only happens when CMD has already cut its own command
    line, and the fragment after the `&` would otherwise run the moment the
    launcher returned. But that makes the flag deciding it dangerous, so it is
    cleared BEFORE the gates that can jump past it — or a variable of that name
    already in the environment would switch it on for every ordinary run.

    ⚠ THIS IS WHY THE CHECK NEEDS A CALLER. Through a plain `cmd /c` the two
    endings are indistinguishable: both give the same exit code and the same
    output. Measured — the first version of this check stayed green with the
    clearing line deleted.
    """
    work, media = refusing_folder(tmp_path)
    wrapper = work / "caller.cmd"
    wrapper.write_text(
        u"@echo off\r\n"
        u'call "%s" "%s"\r\n' % (LAUNCHER, media)
        + u"echo THE-CALLER-IS-STILL-RUNNING\r\n", encoding="ascii")
    proc = subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(wrapper)],
        env=launcher_env(work, {"HATO_REPAIRED": "1", "HATO_FIX1": "1"}),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(work), timeout=180)
    out = proc.stdout.decode("utf-8", "replace")

    assert u"1 refused" in out, out                    # the launcher really ran
    assert u"THE-CALLER-IS-STILL-RUNNING" in out, out  # ...and did not take the caller
    assert proc.returncode == 0, out + proc.stderr.decode("utf-8", "replace")


def test_the_launcher_never_leaves_an_empty_entry_on_pythonpath():
    u"""⚠ AN EMPTY ENTRY IN PYTHONPATH MEANS THE WORKING DIRECTORY, which is the
    launcher's own rule 1 broken by one semicolon: with PYTHONPATH unset,
    `%HATO_HERE%;%PYTHONPATH%` ends in `;` and Python then imports from wherever
    Task Scheduler happened to start it."""
    text = LAUNCHER.read_text(encoding="ascii")
    assert u'set "PYTHONPATH=%HATO_HERE%;%PYTHONPATH%"' in text
    assert u'set "PYTHONPATH=%HATO_HERE%"' in text      # ...the unset branch exists
    assert u"if defined PYTHONPATH" in text
