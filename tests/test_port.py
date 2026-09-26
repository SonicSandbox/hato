# -*- coding: utf-8 -*-
u"""
hato/port.py -- the one door to tsubasa (RUNBOOK 4a).

🚨 A PORT EXERCISED ONLY AGAINST ITS OWN STUB IS PROOF OF THE STUB. Everything
below the line marked CONTRACT runs the REAL `tsubasa.sync()` against a real
video built with ffmpeg in a temp dir, and it is not optional: the thing under
test IS the hand-off, and a stub that agrees with a wrong belief about tsubasa
would agree with it for ever.

⭐ WHAT THE STUB CHECKS MAY AND MAY NOT PROVE. They prove the port's own
contract -- one pair in, one `Result` out, unchanged; what hato asks tsubasa
for; and that *CONFIDENT is not WRITTEN*. ⛔ They prove nothing about
ALIGNMENT: the stub measures nothing and says so. The offset, the verdict and
the output's placement are the contract test's, and only its.

⚠ WHAT NONE OF IT COVERS: a real download's encoding (Shift-JIS, BOM, CRLF) --
that is 4c's, where the bytes hato keeps are the subject.
"""
import io
import os
import sys
from pathlib import Path

import pytest
import tsubasa

from hato import port

# ⚠ `hato.state` IS IMPORTED INSIDE THE TWO CHECKS THAT NEED IT, never here.
# Another builder is in that file while this one is being written, and a
# module-level import of a half-saved neighbour errors the WHOLE suite instead
# of the one check that has an opinion about it (`LEDGER.md`: a suite failing
# three different ways is a file being rewritten under you).

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _media                                                   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def pair(tmp_path, stem=u"Show - 01", sub=u"Show - 01.ja.srt", body=u"1\n"):
    u"""Two paths and nothing behind them. ⛔ No container is opened by any
    check that uses this -- the stub engine is what makes that true."""
    media, cache = tmp_path / "media", tmp_path / "cache"
    for folder in (media, cache):
        folder.mkdir(exist_ok=True)
    video = media / (stem + u".mkv")
    video.write_bytes(b"\x1aE\xdf\xa3")          # an EBML header, never read
    subtitle = cache / sub
    subtitle.write_text(body, encoding="utf-8")
    return video, subtitle


def report_of(*results):
    u"""An engine returning exactly these results."""
    return lambda pairs, **kwargs: tsubasa.SyncReport(list(results))


def a_result(video, subtitle, **fields):
    values = dict(outcome=port.CONFIDENT, verdict_word=u"locked",
                  output_path=str(video) + u".ja.srt")
    values.update(fields)
    return tsubasa.Result(str(video), str(subtitle), **values)


def starts_in(srt_text):
    u"""Every cue's start, in seconds, from a SubRip body. -> [float]"""
    out = []
    for line in srt_text.splitlines():
        if u" --> " not in line:
            continue
        clock = line.split(u" --> ")[0].strip().replace(u",", u".")
        hours, minutes, seconds = clock.split(u":")
        out.append(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    return out


def records_in(store_root):
    u"""How many completed syncs tsubasa's results DB holds. -> int"""
    synced = Path(store_root) / "synced"
    if not synced.is_dir():
        return 0
    return len([p for p in synced.rglob("*.json")])


# ---------------------------------------------------------------------------
# 1. tsubasa's Result comes back UNCHANGED
# ---------------------------------------------------------------------------

def test_the_port_returns_the_engines_result_object_itself(tmp_path):
    u"""⛔ Identity, not equality. A re-wrap that copied every field today
    would drop the one tsubasa adds tomorrow, and `05-interface.md` says fields
    are ADDED to `Result`, never renamed -- so the only durable contract is
    *the same object*."""
    video, subtitle = pair(tmp_path)
    mine = a_result(video, subtitle)
    got = port.sync(video, subtitle, engine=report_of(mine))
    assert got is mine


def test_every_field_tsubasa_puts_on_a_result_survives_the_port(tmp_path):
    u"""The RUNBOOK's Prove, field by field: *every field, not a re-wrapped
    subset.* ⚠ Read off `Result.__slots__` rather than a list written here, so
    a field tsubasa adds is covered the day it lands."""
    video, subtitle = pair(tmp_path)
    mine = a_result(video, subtitle, segments=[(None, -7.0), (900.0, -4.5)],
                    match_rate=0.96, raw_excess=5.15, dropped_in_gap=2,
                    dropped_before_zero=1, runtime_check=u"held",
                    notes=[u"a name had to be trimmed"])
    got = port.sync(video, subtitle, engine=report_of(mine))

    assert len(tsubasa.Result.__slots__) > 20        # the shape is really wide
    for field in tsubasa.Result.__slots__:
        assert getattr(got, field) == getattr(mine, field), field
    # The derived half `05-interface.md` lists as "derived, no storage".
    assert got.match_percent == 96
    assert got.offset == -7.0
    assert len(got.segments) == 2                    # ⚠ a cut file has two


def test_the_outcome_words_are_one_vocabulary_across_hato_and_tsubasa():
    u"""⚠ The strings are defined in three places (port, `hato/state.py`,
    tsubasa's internals). Two of them are pinned here; the third is pinned by
    the contract test, against what the engine actually returns."""
    from hato import state
    assert (port.CONFIDENT, port.REFUSED, port.ERROR) == \
           (state.CONFIDENT, state.REFUSED, state.ERROR)
    assert port.ERROR in state.OUTCOMES


# ---------------------------------------------------------------------------
# 2. what hato ASKS tsubasa for
# ---------------------------------------------------------------------------

def test_the_port_hands_tsubasa_exactly_one_explicit_pair(tmp_path):
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert len(calls) == 1
    pairs, _kwargs = calls[0]
    assert pairs == [(str(video), str(subtitle))]


def test_the_real_call_writes(tmp_path):
    u"""⭐ Ruled 2026-09-17: tsubasa places the file; hato never does. ⚠ The
    port's default is the OPPOSITE of tsubasa's own, so it is asserted here."""
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["write"] is True


def test_a_caller_can_still_measure_without_writing(tmp_path):
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, write=False, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["write"] is False


def test_rename_is_on_so_the_output_takes_the_videos_name(tmp_path):
    u"""It is what makes a player auto-load the file, and what
    `unpaired(lang="ja")` reads on the next run."""
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["rename"] is True


def test_dedupe_is_off_so_hato_never_authorises_a_trash(tmp_path):
    u"""`03-permissions.md`: *on this explicit path tsubasa supersedes nothing,
    so nothing is trashed.* hato hands one pair, so the flag decides nothing --
    which is exactly why it costs nothing to make the promise structural."""
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["dedupe"] is False


def test_the_results_db_argument_is_None_and_never_False(tmp_path):
    u"""⭐ THE DELIBERATE CHOICE (see `port.py`'s note), pinned twice.

    `results=None` is *use the real per-user store*; `results=False` is
    *consult and record nothing*. hato passes `None` so a later
    `tsubasa <folder>` over the same library recognises the file hato placed as
    already in sync instead of re-aligning it -- and the explicit-pair path
    RECORDS but never SKIPS, so the store can never answer for a pair hato
    asked about (`pipeline._sync_plan`).

    ⚠ Here the CALL is pinned; the contract test pins the BEHAVIOUR, by
    counting the records the store gained. Both go red if this becomes False.
    """
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    kwargs = calls[0][1]
    assert "results" in kwargs, "the argument must be passed, not defaulted"
    assert kwargs["results"] is None
    assert kwargs["results"] is not False
    assert port.RESULTS is None


def test_out_dir_is_absent_unless_the_caller_mirrors(tmp_path):
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["out_dir"] is None


def test_out_dir_is_passed_through_for_the_mirrored_run(tmp_path):
    u"""`--out` mirrors; only hato knows the library root, so it computes the
    directory and tsubasa is told it (`03-permissions.md` Whitelist 1)."""
    video, subtitle = pair(tmp_path)
    elsewhere = tmp_path / "out" / "Season 2"
    calls = []
    result = port.sync(video, subtitle, out_dir=elsewhere,
                       engine=port.stub_engine(calls=calls))
    assert calls[0][1]["out_dir"] == str(elsewhere)
    assert Path(result.output_path).parent == elsewhere


# ---------------------------------------------------------------------------
# 3. ⛔ CONFIDENT IS NOT WRITTEN
# ---------------------------------------------------------------------------

def test_confident_with_a_file_on_disk_is_the_only_success(tmp_path):
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle, engine=port.stub_engine())
    assert result.outcome == port.CONFIDENT
    assert port.wrote(result) is True
    assert port.outcome_and_reason(result) == (port.CONFIDENT, u"")


def test_confident_with_no_output_path_is_not_a_success(tmp_path):
    u"""🚨 The whole point of `wrote()`. A user told a subtitle was written
    stops looking for it."""
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle, engine=port.stub_engine(writes=False))
    assert result.outcome == port.CONFIDENT       # tsubasa still says confident
    assert result.output_path is None
    assert port.wrote(result) is False


def test_confident_but_unwritten_is_reportable_as_an_ERROR(tmp_path):
    u"""`03-permissions.md`: *CONFIDENT with no `output_path` is an ERROR* --
    and it carries tsubasa's OWN reason, which names what would change it."""
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle, engine=port.stub_engine(writes=False))
    outcome, reason = port.outcome_and_reason(result)
    assert outcome == port.ERROR
    assert reason == result.reason
    assert u"NOT WRITTEN" in reason
    assert result.write_failed is True


def test_a_dry_run_is_confident_and_also_not_written(tmp_path):
    u"""⚠ The other way to reach it, and it is NOT a failed write -- measured
    on the real engine, `write_failed` stays False and the reason says so."""
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle, write=False, engine=port.stub_engine())
    assert result.outcome == port.CONFIDENT
    assert port.wrote(result) is False
    assert result.write_failed is False
    assert u"dry run" in port.why_nothing_was_written(result)
    assert port.outcome_and_reason(result)[0] == port.ERROR
    assert not list(tmp_path.glob("media/*.srt"))


def test_a_refusal_passes_through_with_its_reason_untouched(tmp_path):
    u"""⛔ A refusal is an OUTCOME, not an exception, and hato does not
    paraphrase it."""
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle,
                       engine=port.stub_engine(outcome=port.REFUSED,
                                               reason=u"31% match -- the "
                                                      u"timing does not hold"))
    assert port.outcome_and_reason(result) == \
        (port.REFUSED, u"31% match -- the timing does not hold")
    assert port.wrote(result) is False
    assert result.verdict_word is None            # never a confidence word


def test_an_error_passes_through_with_its_reason_untouched(tmp_path):
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle,
                       engine=port.stub_engine(outcome=port.ERROR,
                                               reason=u"the container could "
                                                      u"not be read"))
    assert port.outcome_and_reason(result) == \
        (port.ERROR, u"the container could not be read")
    assert result.output_path is None


def test_why_nothing_was_written_is_never_an_empty_string(tmp_path):
    u"""`03-permissions.md` §hand-back: *"it failed" is not actionable and is
    not acceptable output.* An engine that gave neither reason nor note is
    itself the fault, and the sentence says so rather than returning ``""``."""
    video, subtitle = pair(tmp_path)
    silent = port.sync(video, subtitle,
                       engine=port.stub_engine(writes=False, reason=u"   "))
    text = port.why_nothing_was_written(silent)
    assert text.strip()
    assert u"gave no reason" in text
    assert str(video) in text

    noted = port.sync(video, subtitle,
                      engine=port.stub_engine(writes=False, reason=u"",
                                              notes=[u"the disk is full"]))
    assert port.why_nothing_was_written(noted) == u"the disk is full"


# ---------------------------------------------------------------------------
# 4. one pair in, one outcome out
# ---------------------------------------------------------------------------

def test_a_report_with_no_results_raises_rather_than_IndexError(tmp_path):
    u"""⛔ `report[0]` would raise four frames from the cause. The message
    names the pair and what the engine said."""
    video, subtitle = pair(tmp_path)
    with pytest.raises(port.PortError) as caught:
        port.sync(video, subtitle, engine=report_of())
    assert u"Show - 01.mkv" in str(caught.value)
    assert u"exactly one outcome" in str(caught.value)


def test_a_settled_video_is_named_as_such_in_the_refusal(tmp_path):
    u"""⭐ The one way `results=None` could have hurt: a store that SETTLED
    hato's pair would return a report with no `Result` at all. The explicit
    path never skips -- but if that ever changes, the port says which surface
    swallowed the answer instead of raising a bare IndexError."""
    video, subtitle = pair(tmp_path)

    def settling(pairs, **kwargs):
        return tsubasa.SyncReport([], settled=[(str(video), u"already synced")])

    with pytest.raises(port.PortError) as caught:
        port.sync(video, subtitle, engine=settling)
    assert u"SETTLED" in str(caught.value)


def test_a_report_with_two_results_raises_rather_than_reporting_the_first(tmp_path):
    video, subtitle = pair(tmp_path)
    twice = a_result(video, subtitle), a_result(video, subtitle)
    with pytest.raises(port.PortError):
        port.sync(video, subtitle, engine=report_of(*twice))


# ---------------------------------------------------------------------------
# 5. the stub seam itself -- ⛔ it may not be laxer than the engine
# ---------------------------------------------------------------------------

def test_the_stub_builds_a_real_tsubasa_result(tmp_path):
    video, subtitle = pair(tmp_path)
    result = port.sync(video, subtitle, engine=port.stub_engine())
    assert isinstance(result, tsubasa.Result)


def test_the_stub_cannot_mint_a_confident_result_without_a_word(tmp_path):
    u"""🚨 `LEDGER.md` §Interface: a GUI painted a run green because *"11
    confident, 1 refused"* contains the word `confident`. tsubasa's constructor
    refuses a bare tick -- and because the stub builds a real `Result`, so does
    the stub."""
    video, subtitle = pair(tmp_path)
    with pytest.raises(ValueError):
        port.sync(video, subtitle, engine=port.stub_engine(verdict_word=None))


def test_the_stub_cannot_mint_an_error_that_wrote_a_file(tmp_path):
    u"""ERROR means never measured, so there was no offset to have written."""
    video, subtitle = pair(tmp_path)
    with pytest.raises(ValueError):
        port.sync(video, subtitle,
                  engine=port.stub_engine(outcome=port.ERROR,
                                          output_path=str(video) + u".ja.srt"))


def test_the_stub_writes_the_file_it_claims_to_have_written(tmp_path):
    u"""⛔ A stub that reported a path and wrote nothing would make every
    later folder-listing check (4c) pass over an empty media folder."""
    video, subtitle = pair(tmp_path, body=u"1\n00:00:01,000 --> 00:00:02,000\nあ\n")
    result = port.sync(video, subtitle, engine=port.stub_engine())
    written = Path(result.output_path)
    assert written.is_file()
    assert written.read_bytes() == subtitle.read_bytes()   # ⛔ never re-encoded
    assert subtitle.is_file()                              # the source stays


def test_the_stub_refuses_an_occupied_destination_exactly_as_the_engine_does(tmp_path):
    u"""🚨 THE STUB OVERWROTE A FILE THE REAL ENGINE REFUSES TO TOUCH.

    `_copy_atomically` called `os.replace` with no existence check, and
    `os.replace` overwrites silently -- so the engine EVERY pipeline check in
    this project runs on destroyed a person's subtitle, and the one shape the
    media folder must never see was unreachable from the suite that drives the
    fetch loop.

    ⭐ The real engine's answer is measured two checks below and in
    `test_write.py::test_a_second_run_over_the_same_folder_skips_instead_of_writing_again`:
    `CONFIDENT`, `write_failed=True`, no `output_path`, reason opening
    `NOT WRITTEN`. The stub now produces exactly that, so a check written
    against it is a check about the engine.
    """
    video, subtitle = pair(tmp_path, body=u"the download\n")
    destination = Path(port.output_name(video, subtitle))
    destination.write_bytes(b"the subtitle that was already there")

    result = port.sync(video, subtitle, engine=port.stub_engine())

    assert result.outcome == port.CONFIDENT          # ⚠ the pair still aligned
    assert result.output_path is None
    assert result.write_failed is True
    assert u"NOT WRITTEN" in port.why_nothing_was_written(result)
    assert port.wrote(result) is False
    assert port.nothing_was_written(result) is True
    assert destination.read_bytes() == b"the subtitle that was already there"
    assert sorted(p.name for p in (tmp_path / "media").iterdir()) == \
        [u"Show - 01.ja.srt", u"Show - 01.mkv"]      # ⛔ and no temp file left


def test_the_stubs_refusal_is_the_same_shape_the_real_engine_returns(tmp_path, real):
    u"""⛔ A STUB PROVES NOTHING UNLESS IT IS PINNED TO THE ENGINE. The two are
    asserted field by field, on ONE occupied destination, so a future tsubasa
    that answers differently turns this red rather than leaving every pipeline
    check believing a shape that no longer happens.

    🚨 THE CUE TEXT IS DELIBERATELY NOT `real.subtitle`'S. `07-test-plan.md`:
    tsubasa's results DB keys a record on the SUBTITLE's CONTENT and the whole
    run shares one `TSUBASA_CACHE`, so a byte-identical body here would land on
    the contract test's own record and take its *"the store gained exactly one
    record"* down with it -- in the other check's file, which is the hardest kind
    of failure to read. ⚠ The TIMING is identical, deliberately: this check is
    about the write, and a subtitle the engine might refuse on its merits would
    measure nothing. (Four cues shorter DID come back REFUSED -- measured.)
    """
    media = tmp_path / "media"
    media.mkdir(exist_ok=True)
    video = media / real.video.name
    video.write_bytes(real.video.read_bytes())
    subtitle = tmp_path / u"a different cut.ja.srt"
    subtitle.write_text(
        _media.srt(real.starts, shift=real.shift, text=u"別の行 %d"),
        encoding="utf-8")
    occupied = Path(port.output_name(video, subtitle))
    occupied.write_bytes(b"the subtitle that was already there")

    engine_says = port.sync(video, subtitle)
    stub_says = port.sync(video, subtitle, engine=port.stub_engine())

    for said in (engine_says, stub_says):
        assert (said.outcome, said.output_path, said.write_failed) == \
            (port.CONFIDENT, None, True)
        assert u"NOT WRITTEN" in said.reason
        assert port.outcome_and_reason(said)[0] == port.ERROR
        assert port.nothing_was_written(said) is True
    assert occupied.read_bytes() == b"the subtitle that was already there"


def test_the_stub_leaves_no_part_file_beside_the_media(tmp_path):
    u"""🚨 Temp-plus-rename, and nothing partial in the media folder -- both
    are `LEDGER-HOT.md` entries, and a stub is where the lazy shape gets
    copied from."""
    video, subtitle = pair(tmp_path)
    port.sync(video, subtitle, engine=port.stub_engine())
    names = sorted(p.name for p in (tmp_path / "media").iterdir())
    assert names == [u"Show - 01.ja.srt", u"Show - 01.mkv"]


# ---------------------------------------------------------------------------
# 6. the name the stub writes to -- pinned against the engine below
# ---------------------------------------------------------------------------

def test_the_output_goes_beside_the_video_under_its_basename(tmp_path):
    video, subtitle = pair(tmp_path, sub=u"[Haruhana] Frieren - 34 [JPN].ja.ass")
    assert port.output_name(video, subtitle) == \
        str(tmp_path / "media" / u"Show - 01.ja.ass")


def test_the_language_written_is_the_RESOLVED_one_not_the_tag(tmp_path):
    u"""⚠ `.jpn.` and `ja-jp` are the same language and must dedupe together
    (`05-interface.md`)."""
    video, subtitle = pair(tmp_path, sub=u"Show - 01.jpn.srt")
    assert Path(port.output_name(video, subtitle)).name == u"Show - 01.ja.srt"


def test_an_untagged_original_is_written_with_NO_language_tag(tmp_path):
    u"""🚨 `LEDGER-HOT.md`, measured twice: tsubasa writes `<video>.<ext>` for
    an `und` source, `unpaired(lang="ja")` then reads the video as having no
    Japanese subtitle, and EVERY LATER RUN FETCHES AGAIN. The stub reproduces
    it rather than smoothing it over -- a stub that invented `.und.` would hide
    the defect from 4c, whose whole job is to prevent it."""
    video, subtitle = pair(tmp_path, sub=u"[Group] Show - 01 [JPN].srt")
    name = Path(port.output_name(video, subtitle)).name
    assert name == u"Show - 01.srt"
    assert u".und." not in name
    assert tsubasa.parse_subtitle_name(name).lang == port.UND


def test_the_computed_name_round_trips_through_tsubasas_own_reader(tmp_path):
    u"""The check that makes the name a claim rather than a guess: whatever the
    port composes must read back as the same language and flags."""
    for given, lang, flags in ((u"Show - 01.ja.srt", u"ja", []),
                               (u"Show - 01.ja.forced.ass", u"ja", [u"forced"]),
                               (u"Show - 01.jpn.srt", u"ja", []),
                               (u"Show - 01.ja[cc].srt", u"ja", [u"cc"])):
        video, subtitle = pair(tmp_path, sub=given)
        back = tsubasa.parse_subtitle_name(
            Path(port.output_name(video, subtitle)).name)
        assert (back.lang, back.flags) == (lang, flags), given


def test_out_dir_moves_the_name_and_nothing_else(tmp_path):
    video, subtitle = pair(tmp_path)
    mirrored = tmp_path / "out" / "Season 2"
    here = Path(port.output_name(video, subtitle))
    there = Path(port.output_name(video, subtitle, out_dir=mirrored))
    assert there.name == here.name
    assert there.parent == mirrored


# ---------------------------------------------------------------------------
# 7. ⭐ THE CONTRACT TEST -- the REAL tsubasa, on a REAL video
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real(tmp_path_factory):
    u"""A real 160x120 video with an embedded Japanese TEXT track, and a
    shifted copy of its cues as the download. ⛔ Built in pytest's temp dir,
    never inside the vault -- `_media.build` refuses the vault outright."""
    return _media.build(tmp_path_factory.mktemp("contract"))


def test_the_real_tsubasa_writes_beside_the_video_and_disturbs_nothing_else(real):
    u"""🚨 THE CHECK THIS WHOLE STEP EXISTS FOR (RUNBOOK 4a).

    Everything above this line believes what the stub says. This one asks the
    engine, on a video ffmpeg really made, and asserts the four things
    `03-permissions.md` Whitelist 1 promises a person: the finished file is
    `<video stem>.ja.<ext>` BESIDE the video, the original is byte-identical
    and still where it was, nothing was trashed, and no other file appeared in
    either folder.
    """
    from hato import state                       # see the note at the imports
    before = real.subtitle.read_bytes()
    store = os.environ["TSUBASA_CACHE"]
    records = records_in(store)

    result = port.sync(real.video, real.subtitle)

    # -- it really measured, and the vocabulary is the one hato speaks --------
    assert result.outcome == port.CONFIDENT
    assert result.outcome in state.OUTCOMES
    assert result.verdict_word in (u"locked", u"solid", u"fair", u"uncertain")
    assert result.reference_kind == u"text track"
    assert result.runtime_check == u"held"          # ⚠ not merely `absent`
    assert result.match_rate > 0.9
    assert result.offset == pytest.approx(-real.shift, abs=0.5)

    # -- CONFIDENT *and* written ---------------------------------------------
    assert port.wrote(result) is True
    assert result.write_failed is False
    written = Path(result.output_path)
    assert written.is_file()

    # -- ⭐ beside the video, under the video's basename ----------------------
    assert written.parent == real.media_dir
    assert written.name == real.video.stem + u".ja.srt"
    # ⭐ AND THE STUB'S NAMER IS PINNED TO THE ENGINE'S ANSWER, here and only
    # here. Every stub-driven check above that reads `output_path` is only
    # worth what this line proves.
    assert str(written) == port.output_name(real.video, real.subtitle)

    # -- the original is untouched, and still in the cache --------------------
    assert real.subtitle.is_file()
    assert real.subtitle.read_bytes() == before
    assert real.subtitle.parent == real.cache_dir

    # -- nothing was trashed --------------------------------------------------
    assert result.superseded == []

    # -- ⛔ and NOTHING else appeared in either folder ------------------------
    assert real.listing(real.media_dir) == sorted([real.video.name, written.name])
    assert real.listing(real.cache_dir) == [real.subtitle.name]

    # -- ⭐ the results= choice, in behaviour: one record, in the redirected
    #    per-user store. `results=False` would leave this at zero.
    assert records_in(store) == records + 1

    # -- and the file is a real subtitle, RETIMED, in the same encoding -------
    # ⚠ Not `"00:00:05,000" in text`. The engine solves the offset to the
    # nearest cue-grid step and landed on -7.125 against a 7.25 shift, so the
    # first cue is at 5.125 -- a check written against the exact string would
    # have been red for the right file. What is asserted is the property:
    # every cue moved back by the SAME amount, to within a frame of where it
    # started. Found by that check going red on a perfect output.
    text = io.open(str(written), encoding="utf-8").read()
    assert text.count(u"-->") == len(real.starts)
    moved = [start - was for start, was in zip(starts_in(text), real.starts)]
    assert len(moved) == len(real.starts)
    assert max(moved) - min(moved) < 0.002              # one uniform offset
    assert moved[0] == pytest.approx(0.0, abs=0.25)     # back where it began


# ---------------------------------------------------------------------------
# 8. the media helper's own guard
# ---------------------------------------------------------------------------

def test_the_media_helper_refuses_to_build_inside_the_vault():
    u"""⛔ The vault auto-commits every few minutes and git history has no
    undo. A 300 KB `.mkv` in `tests/` is committed before anyone notices, so
    the rule is enforced rather than remembered."""
    with pytest.raises(_media.OutsideTheVault):
        _media.build(ROOT / "tests")
    assert not list((ROOT / "tests").glob("*.mkv"))


def test_the_media_helper_builds_outside_the_vault(real):
    u"""The same guard, from the other side: the fixture above really is
    somewhere the vault does not reach."""
    assert _media.VAULT.name == "TheForge"
    with pytest.raises(ValueError):
        real.root.relative_to(_media.VAULT)


def test_the_generated_video_carries_a_japanese_text_track(real):
    u"""⭐ Through tsubasa's PUBLIC track reader (T4), never `tsubasa.container`
    (`LEDGER-HOT.md`). If this goes red the contract test above is aligning
    against something other than what it thinks."""
    tracks = tsubasa.embedded_subs(real.video, lang=u"ja")
    assert tracks.ok is True, tracks.reason
    assert [t.text for t in tracks.tracks] == [True]
    assert real.video.stat().st_size < 2 * 1024 * 1024        # ⚠ keep it tiny


# ---------------------------------------------------------------------------
# 9. ⭐ RUNBOOK 8e -- a person's pick, through the EXACT command the window runs
# ---------------------------------------------------------------------------

def _scattered(media):
    u"""A subtitle as long as the video's cues and sharing no single offset with
    them -- REFUSED by timing, and not an ERROR (a too-long file trips the
    duration guard instead, which force must NOT override)."""
    import random
    rng = random.Random(7)
    wrong = media.cache_dir / (media.video.stem + u".ja.srt")
    span = (media.starts[0], media.starts[-1])
    _media.write_srt(wrong, _media.srt(sorted(rng.uniform(*span) for _ in media.starts)))
    return wrong


def _pick(capsys, video, subtitle, force=False):
    u"""Run the WINDOW'S OWN argv through `cli.main`. -> (exit code, [objects])

    🚨 THE SEAM THAT WAS NEVER TESTED. The window's checks asserted the argv's
    SHAPE and this file asserted the port; nothing ran one through the other, so
    `hato sync ... --json` died on a usage error for every pick ever made while
    both sides were green.
    """
    import json
    from hato import cli
    from hato.gui import run as gui_run
    argv = gui_run.argv_for_pair(video, subtitle, force=force)
    code = cli.main(argv[len(gui_run.cli_argv()):])
    out = capsys.readouterr().out
    return code, [json.loads(line) for line in out.splitlines() if line.strip()]


def test_the_windows_pick_is_a_command_hato_sync_accepts(tmp_path, capsys):
    u"""🚨 D7, measured 2026-09-22: `usage: hato sync ... error: unrecognized
    arguments: --json`, exit 2 -- on every pick the window has ever made."""
    media = _media.build(tmp_path)
    code, said = _pick(capsys, media.video, media.subtitle)
    assert code != 2, u"the window's pick is still a usage error"
    answer, = said
    assert answer[u"type"] == u"pair"
    assert answer[u"written"] is True and answer[u"forced"] is False
    assert Path(answer[u"output_path"]).is_file()
    assert code == 0


def test_a_pick_under_a_configured_out_lands_where_every_run_looks(tmp_path, capsys,
                                                                  monkeypatch):
    u"""ADVERSARY 2026-09-22 F12 / A25. With `out` configured, a pick written
    BESIDE the video is where no run and no `hato problems` looks -- the row
    never settled, and the next run fetched again over the person's choice.
    ⭐ One source of truth: `keep.target_dir` with the configured folder."""
    import json
    from hato import keep
    media = _media.build(tmp_path)
    out = tmp_path / u"Subs"
    config_file = tmp_path / u"config.toml"
    config_file.write_text(u"folders = [%s]\nout = %s\n" % (
        json.dumps(str(media.media_dir)), json.dumps(str(out))), encoding="utf-8")
    monkeypatch.setenv("HATO_CONFIG", str(config_file))

    code, (answer,) = _pick(capsys, media.video, media.subtitle)
    assert code == 0 and answer[u"written"] is True, answer
    wanted = keep.target_dir(media.video, str(media.media_dir), str(out))
    assert Path(answer[u"output_path"]).parent == Path(wanted), (
        u"the pick landed in %s; every run looks for it in %s"
        % (Path(answer[u"output_path"]).parent, wanted))
    beside = [p.name for p in media.media_dir.iterdir() if p.suffix == u".srt"]
    assert beside == [], u"a pick under `out` was ALSO written beside the video: %s" % beside

    config_file.write_text(u"folders = [%s]\n" % json.dumps(str(media.media_dir)),
                           encoding="utf-8")                    # the control: no `out`
    other = _media.build(tmp_path / u"second")
    code, (plain,) = _pick(capsys, other.video, other.subtitle)
    assert Path(plain[u"output_path"]).parent == other.media_dir, plain[u"output_path"]


def test_a_forced_pick_writes_the_file_and_says_whose_decision_it_was(tmp_path, capsys):
    u"""⭐ Two arms on the REAL engine. Without force a refused pair writes nothing
    -- which is why every pick the window offers could never succeed; with it the
    file lands, the outcome stays REFUSED, and the answer says FORCED."""
    media = _media.build(tmp_path)
    wrong = _scattered(media)

    code, (plain,) = _pick(capsys, media.video, wrong, force=False)
    assert plain[u"outcome"] == port.REFUSED and plain[u"written"] is False
    assert code == 1
    assert not (media.media_dir / (media.video.stem + u".ja.srt")).exists()

    code, (forced,) = _pick(capsys, media.video, wrong, force=True)
    assert code == 0
    assert forced[u"written"] is True and forced[u"forced"] is True
    assert forced[u"outcome"] == port.REFUSED, (
        u"a forced write must still say the timing did not hold")
    assert forced[u"reason"].startswith(u"WRITTEN UNDER --force")
    assert Path(forced[u"output_path"]).is_file()


def test_a_pick_that_lands_is_copied_to_surasura_as_a_runs_is(tmp_path, capsys,
                                                             monkeypatch):
    u"""🚨 The Layer 14 pass, Z14-5. The surasura card says *"Every subtitle hato aligns
    is also copied"* -- and a pick never was; the next run skipped the video as
    present, so surasura never had it. A pick is the path a person takes when a
    download is refused: exactly when *"Download from jimaku anyway"*, chosen FOR
    surasura, needs it. Arms: refused without force -- nothing; forced -- copied,
    byte for byte; surasura off -- nothing."""
    import json
    from hato import keep
    media = _media.build(tmp_path)
    wrong = _scattered(media)
    surasura = tmp_path / u"surasura"
    config_file = tmp_path / u"config.toml"
    config_file.write_text(u"surasura_dir = %s\n" % json.dumps(str(surasura)),
                           encoding="utf-8")
    monkeypatch.setenv("HATO_CONFIG", str(config_file))

    code, (refused,) = _pick(capsys, media.video, wrong, force=False)
    assert refused[u"written"] is False and not surasura.exists(), (
        u"a pick that wrote nothing was copied: %s" % refused)
    code, (forced,) = _pick(capsys, media.video, wrong, force=True)
    assert code == 0 and forced[u"written"] is True, forced
    copied = surasura / keep.SURASURA_FOLDER / Path(forced[u"output_path"]).name
    assert copied.is_file(), u"the pick never reached surasura: %s" % forced
    assert copied.read_bytes() == Path(forced[u"output_path"]).read_bytes()
    assert forced[u"surasura"] == str(copied), forced

    config_file.write_text(u"", encoding="utf-8")        # the control: surasura off
    other = _media.build(tmp_path / u"second")
    code, (plain,) = _pick(capsys, other.video, other.subtitle)
    assert plain[u"written"] is True and plain[u"surasura"] is None, plain
    assert [p for p in surasura.rglob(u"*") if p.is_file()] == [copied]


def test_the_stubs_forced_write_is_the_shape_the_engine_returns(tmp_path):
    u"""⭐ Pinned against the measurement above: file landed, outcome REFUSED,
    reason opening "WRITTEN UNDER --force". ⛔ And an occupied destination is
    still refused -- force overrides the timing, never a person's file."""
    video, subtitle = pair(tmp_path)
    engine = port.stub_engine(outcome=port.REFUSED, reason=u"31% match")
    result = port.sync(video, subtitle, engine=engine, force=True)
    assert port.forced(result) and not port.wrote(result)
    assert Path(result.output_path).is_file()
    assert result.reason.startswith(u"WRITTEN UNDER --force")

    again = port.sync(video, subtitle, engine=engine, force=True)
    assert not again.output_path and again.write_failed is True, (
        u"a second forced pick wrote over the first")


def test_the_fetch_loop_never_forces(tmp_path):
    u"""⛔ Only a PERSON may overrule the referee. The port's default is off, and
    the pipeline's one call site passes nothing."""
    video, subtitle = pair(tmp_path)
    calls = []
    port.sync(video, subtitle, engine=port.stub_engine(calls=calls))
    assert calls[0][1]["force"] is False
    source = (ROOT / "hato" / "pipeline.py").read_text(encoding="utf-8")
    assert "force=True" not in source and "force=self" not in source.replace(
        "force=self.s.force or self.s.retry_now", "")
