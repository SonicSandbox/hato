# -*- coding: utf-8 -*-
u"""
hato/keep.py -- the hand-off to tsubasa, and the original hato keeps
(RUNBOOK 4c).

🚨 THE ONE THING THIS STEP EXISTS TO PREVENT. Hand tsubasa an untagged original
and it writes `<video>.ass` with no language tag; `unpaired(lang="ja")` -- and
hato's own present-check -- then read that as *no Japanese subtitle*, and every
later run fetches the same episode again, for ever. The check named
`test_an_untagged_original_makes_the_next_run_fetch_again` runs the REAL engine
and measures exactly that, so the trap is a red line and not a paragraph.

⭐ WHAT IS DRIVEN BY THE REAL tsubasa HERE: every check under §5. `07-test-plan.md`
-- *a port tested only through its stub proves the stub* -- and the subject of
this step is the hand-off itself, so a stub could only ever agree with whatever
hato already believed.

⛔ WHAT THESE CHECKS STRUCTURALLY CANNOT COVER: whether a media player actually
loads the result. Measured once by hand, in Sonic's mpv, 2026-09-17.
"""
import io
import os
import shutil
import sys
from pathlib import Path

import pytest
import tsubasa

from hato import cache as cache_module, keep, port, present

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _media                                                      # noqa: E402

FRIEREN = u"[Haruhana] Sousou no Frieren - 29 [WebRip][HEVC-10bit 1080p][JPN].ass"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def a_file(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def names(folder):
    folder = Path(folder)
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def kept_names(subs_dir, entry=u"Sousou no Frieren 2nd Season"):
    return names(keep.entry_folder(subs_dir, entry))


# ---------------------------------------------------------------------------
# 1. ⛔ neither subs_dir nor --out may sit inside a scanned folder
# ---------------------------------------------------------------------------

def test_the_kept_originals_really_would_be_offered_as_candidates(tmp_path):
    u"""⭐ THE MEASUREMENT BEHIND THE REFUSAL, against the real engine. A tree
    holding both the videos and hato's `subs/` answers `unpaired(lang="ja")`
    with `[]`: the kept original in a sibling folder was offered as the video's
    subtitle, and a `tsubasa <folder>` run over that tree could supersede it."""
    tree = tmp_path / "lib"
    a_file(tree / "S2" / u"Show - 01.mkv", b"")
    a_file(tree / "subs" / "Entry" / u"[G] Show - 01 [JPN].ja.ass", b"")
    assert tsubasa.scan(videos=str(tree)).unpaired(lang=u"ja") == []


def test_subs_dir_inside_a_scanned_folder_is_refused(tmp_path):
    with pytest.raises(keep.SubsDirInsideScan) as caught:
        keep.check_subs_dir(tmp_path / "lib" / "subs", [tmp_path / "lib"])
    assert u"subs" in str(caught.value)
    assert u"lib" in str(caught.value)


def test_a_scanned_folder_inside_subs_dir_is_refused_too(tmp_path):
    u"""⚠ The other direction reaches the same tree, and so must be refused the
    same way -- the rule is about the WALK, not about which path was typed."""
    with pytest.raises(keep.SubsDirInsideScan):
        keep.check_subs_dir(tmp_path / "subs", [tmp_path / "subs" / "lib"])


def test_the_same_folder_twice_is_refused(tmp_path):
    with pytest.raises(keep.SubsDirInsideScan):
        keep.check_subs_dir(tmp_path / "lib", [tmp_path / "lib"])


def test_a_sibling_folder_is_fine(tmp_path):
    keep.check_subs_dir(tmp_path / "subs", [tmp_path / "lib", tmp_path / "more"])


def test_hatos_own_out_really_would_be_offered_as_the_videos_subtitle(tmp_path):
    u"""🚨 THE MEASUREMENT BEHIND THE `--out` REFUSAL, against the real engine --
    and the one that was never taken, because the check above it staged `subs/`
    and nothing else.

    ⭐ THIS IS WORSE THAN THE `subs_dir` CASE. A kept original keeps jimaku's own
    name, so tsubasa has to reach for it. hato's `--out` file carries **the
    video's own basename**, which is exactly the name a walk pairs on -- so a
    plain `tsubasa <tree>` run reads it as that video's subtitle. The adversarial
    pass ran the supersede and got hato's finished file named in `superseded`.
    """
    tree = tmp_path / "lib"
    a_file(tree / "S2" / u"frieren S2 - 01.mkv", b"")
    a_file(tree / "Subs" / "S2" / u"frieren S2 - 01.ja.ass", b"")
    assert tsubasa.scan(videos=str(tree)).unpaired(lang=u"ja") == []


def test_out_inside_a_scanned_folder_is_refused(tmp_path):
    with pytest.raises(keep.OutDirInsideScan) as caught:
        keep.check_out_dir(tmp_path / "lib" / "Subs", [tmp_path / "lib"])
    assert u"--out" in str(caught.value)
    assert u"lib" in str(caught.value)


def test_a_scanned_folder_inside_out_is_refused_too(tmp_path):
    u"""⚠ The rule is about the WALK, not about which path was typed."""
    with pytest.raises(keep.OutDirInsideScan):
        keep.check_out_dir(tmp_path / "Subs", [tmp_path / "Subs" / "lib"])


def test_the_same_folder_as_out_is_refused(tmp_path):
    with pytest.raises(keep.OutDirInsideScan):
        keep.check_out_dir(tmp_path / "lib", [tmp_path / "lib"])


def test_a_sibling_out_is_fine_and_so_is_no_out_at_all(tmp_path):
    u"""⛔ `out=None` is *beside the video*, which is the whole point of the
    default and can never be the mistake this rule is about."""
    keep.check_out_dir(tmp_path / "Subs", [tmp_path / "lib", tmp_path / "more"])
    keep.check_out_dir(None, [tmp_path / "lib"])
    keep.check_out_dir(u"", [tmp_path / "lib"])


def test_both_doors_share_one_base_so_neither_can_be_left_unlatched(tmp_path):
    u"""⚠ `subs_dir` carried this rule from the first build and `--out` did not,
    and the caller caught the SUBCLASS -- so adding the second check without the
    base would have raised straight past `pipeline.go()`'s handler."""
    for problem in (keep.SubsDirInsideScan, keep.OutDirInsideScan):
        assert issubclass(problem, keep.InsideScan)
    with pytest.raises(keep.InsideScan):
        keep.check_out_dir(tmp_path / "lib" / "Subs", [tmp_path / "lib"])
    with pytest.raises(keep.InsideScan):
        keep.check_subs_dir(tmp_path / "lib" / "subs", [tmp_path / "lib"])


def test_a_folder_whose_NAME_starts_the_same_is_not_inside_it(tmp_path):
    u"""⚠ `…/library` is not inside `…/lib`. A `startswith` without the
    separator would refuse a perfectly good configuration."""
    keep.check_subs_dir(tmp_path / "library-subs", [tmp_path / "library"])
    assert keep.inside(tmp_path / "library" / "x", tmp_path / "library")


@pytest.mark.skipif(os.name != "nt", reason="Windows drive letters")
def test_two_drives_are_an_answer_and_not_an_error():
    u"""⚠ `os.path.commonpath` RAISES on two different drives; *"D: is not under
    C:"* is an answer. This is why `inside()` compares normalised text."""
    with pytest.raises(ValueError):
        os.path.commonpath([u"C:\\a", u"D:\\a"])
    assert keep.inside(u"D:\\a\\b", u"C:\\a") is False


# ---------------------------------------------------------------------------
# 2. 🚨 --out mirrors, and the present-check uses the SAME answer
# ---------------------------------------------------------------------------

def test_without_out_the_target_is_the_videos_own_folder(tmp_path):
    video = tmp_path / "lib" / "S2" / u"Show - 01.mkv"
    assert keep.target_dir(video, tmp_path / "lib", None) == video.parent


def test_out_mirrors_the_tree_below_the_scanned_root(tmp_path):
    u"""`05-interface.md`: `~/Anime/Katainaka S2/ep01.mkv --out ~/Subs` ->
    `~/Subs/Katainaka S2/ep01.ja.ass`. ⛔ Flattening would collide the moment
    two shows both have an `ep01`."""
    root = tmp_path / "Anime"
    out = tmp_path / "Subs"
    assert keep.target_dir(root / "Katainaka S2" / u"ep01.mkv", root, out) == \
        out / "Katainaka S2"
    assert keep.target_dir(root / "A" / "Season 2" / u"ep01.mkv", root, out) == \
        out / "A" / "Season 2"


def test_a_video_in_the_root_itself_lands_in_out_itself(tmp_path):
    root, out = tmp_path / "Katainaka S2", tmp_path / "Subs"
    assert keep.target_dir(root / u"ep01.mkv", root, out) == out


def test_the_root_may_be_named_as_a_file(tmp_path):
    u"""⚠ `05-interface.md`'s first constraint: *never assumes it owns a
    directory* -- a root may be one video."""
    root = a_file(tmp_path / "Anime" / u"ep01.mkv", b"")
    assert keep.target_dir(root, root, tmp_path / "Subs") == tmp_path / "Subs"


def test_a_video_outside_its_root_is_refused_rather_than_written_outside_out(tmp_path):
    u"""⛔ A relpath starting `..` would put the output OUTSIDE `--out`, which
    is the one place a `--out` run is allowed to write."""
    with pytest.raises(ValueError):
        keep.target_dir(tmp_path / "elsewhere" / u"ep01.mkv", tmp_path / "Anime",
                        tmp_path / "Subs")


def test_the_present_check_finds_the_mirrored_file(tmp_path):
    u"""🚨 THE DEFECT MEASURED AT 4a, CLOSED. With `--out` set the previous
    run's file is in the MIRRORED directory; a present-check looking beside the
    video would never see it, hato would re-fetch the episode every run, and
    tsubasa would refuse the write for ever (CONFIDENT, `write_failed`, no
    file). One function answers for both sides."""
    root, out = tmp_path / "Anime", tmp_path / "Subs"
    video = a_file(root / "Katainaka S2" / u"ep01.mkv", b"")
    a_file(out / "Katainaka S2" / u"ep01.ja.ass", b"")
    look = present.Presence(u"ja")
    assert look.find(video, keep.target_dir(video, root, out)) is not None
    assert look.find(video, keep.target_dir(video, root, None)) is None


# ---------------------------------------------------------------------------
# 3. 🚨 the `.ja` tag, by name
# ---------------------------------------------------------------------------

def test_every_real_jimaku_shape_gains_the_tag_and_reads_back_as_japanese(tmp_path):
    u"""⭐ The five shapes entry 11446 really carries, plus the trap row."""
    for given in (FRIEREN,
                  u"[Nekomoe kissaten&LoliHouse] Frieren - 30 [CHS, JPN].ass",
                  u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3.S02E01.WEBRip.Amazon.ja-jp[sdh].srt",
                  u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3.S02E31.WEBRip.Netflix.ja[cc].srt",
                  u"[NanakoRaws] Sousou no Frieren S2 - 04 (AT-X).srt"):
        made = keep.download_name(given, u"ja")
        back = tsubasa.parse_subtitle_name(made)
        assert back.lang == u"ja", given
        assert made.endswith(u".ja" + os.path.splitext(given)[1]), given


def test_a_forced_or_sdh_tag_on_the_source_cannot_ride_into_the_output(tmp_path):
    u"""🚨 Measured, and it is why the tag is APPENDED rather than replaced.
    `Show - 04.ja.forced.srt` handed over as-is would make tsubasa write
    `<video>.ja.forced.srt` -- which `06-edge-cases.md` §6 says is *not a full
    subtitle*, so hato's own present-check would read the video as unsubtitled
    and fetch it again on every run. Appending pushes the source's tag into the
    STEM, and the flags come back empty."""
    made = keep.download_name(u"Show - 04.ja.forced.srt", u"ja")
    back = tsubasa.parse_subtitle_name(made)
    assert (back.lang, list(back.flags)) == (u"ja", [])
    assert back.stem == u"Show - 04.ja.forced"


def test_the_language_written_is_the_resolved_one(tmp_path):
    assert keep.download_name(u"x.srt", u"jpn") == u"x.ja.srt"
    assert keep.download_name(u"x.srt", u"ja-JP") == u"x.ja.srt"


def test_a_name_with_no_extension_is_refused_rather_than_tagged(tmp_path):
    with pytest.raises(keep.UntaggedOriginal):
        keep.download_name(u"README", u"ja")


def test_only_the_basename_is_read(tmp_path):
    u"""⚠ `05-interface.md`/tsubasa: a directory component must never
    contribute a language token."""
    assert keep.download_name(os.path.join(u"en", u"x.srt"), u"ja") == u"x.ja.srt"


# ---------------------------------------------------------------------------
# 4. ⛔ the kept original: never deleted, never overwritten
# ---------------------------------------------------------------------------

def test_the_original_lands_under_the_entry_name_byte_for_byte(tmp_path):
    body = u"1\n00:00:01,000 --> 00:00:02,000\n\u884c 1\n".encode("utf-8")
    blob = a_file(tmp_path / "cache" / u"x.ja.srt", body)
    kept = keep.keep_original(blob, tmp_path / "subs",
                              u"Sousou no Frieren 2nd Season",
                              keep.download_name(FRIEREN, u"ja"))
    assert kept.read_bytes() == body
    assert kept.parent.name == u"Sousou no Frieren 2nd Season"
    assert kept.name == keep.download_name(FRIEREN, u"ja")
    assert blob.is_file()                       # ⛔ the source is never deleted
    assert names(kept.parent) == [kept.name]    # and nothing else was left behind


def test_the_same_bytes_under_the_same_name_are_reused_not_duplicated(tmp_path):
    blob = a_file(tmp_path / "cache" / u"x.ja.srt", b"same")
    first = keep.keep_original(blob, tmp_path / "subs", u"Entry", u"x.ja.srt")
    second = keep.keep_original(blob, tmp_path / "subs", u"Entry", u"x.ja.srt")
    assert first == second
    assert names(first.parent) == [u"x.ja.srt"]


def test_different_bytes_under_the_same_name_keep_BOTH(tmp_path):
    u"""`06-edge-cases.md` §8: same content hash -> reuse; different content ->
    keep both, the new one under a short hash suffix. ⛔ Never overwrite."""
    old = a_file(tmp_path / "cache" / u"a.ja.srt", b"the first upload")
    new = a_file(tmp_path / "cache2" / u"a.ja.srt", b"a re-upload, different bytes")
    first = keep.keep_original(old, tmp_path / "subs", u"Entry", u"a.ja.srt")
    second = keep.keep_original(new, tmp_path / "subs", u"Entry", u"a.ja.srt")
    assert first != second
    assert first.read_bytes() == b"the first upload"
    assert second.read_bytes() == b"a re-upload, different bytes"
    assert second.name.endswith(u".ja.srt")     # the tag survives the suffix
    assert tsubasa.parse_subtitle_name(second.name).lang == u"ja"
    assert len(names(first.parent)) == 2


def test_the_suffix_comes_from_the_content_so_a_rerun_does_not_pile_up(tmp_path):
    old = a_file(tmp_path / "cache" / u"a.ja.srt", b"one")
    new = a_file(tmp_path / "cache2" / u"a.ja.srt", b"two")
    keep.keep_original(old, tmp_path / "subs", u"Entry", u"a.ja.srt")
    for _ in range(3):
        keep.keep_original(new, tmp_path / "subs", u"Entry", u"a.ja.srt")
    assert len(names(keep.entry_folder(tmp_path / "subs", u"Entry"))) == 2


def test_an_entry_name_windows_refuses_is_mapped_never_dropped(tmp_path):
    u"""`06-edge-cases.md` §8: map to the fullwidth twins, as jimaku-corpus
    does. ⛔ Dropping them changes the shape of a name (`Re:Zero` is not
    `ReZero`)."""
    blob = a_file(tmp_path / "cache" / u"x.ja.srt", b"x")
    kept = keep.keep_original(blob, tmp_path / "subs", u"Re:Zero kara*Hajimeru?",
                              u"x.ja.srt")
    assert kept.parent.name == u"Re\uff1aZero kara\uff0aHajimeru\uff1f"
    assert kept.is_file()


def test_a_failed_copy_leaves_nothing_behind(tmp_path, monkeypatch):
    u"""🚨 Temp-plus-rename: a raise mid-write must leave the folder as it was,
    never a zero-byte or half-written original."""
    blob = a_file(tmp_path / "cache" / u"x.ja.srt", b"x" * 100)

    def explode(src, dst, length=0):
        dst.write(b"partial")
        raise OSError("the disk is full")

    monkeypatch.setattr(shutil, "copyfileobj", explode)
    with pytest.raises(OSError):
        keep.keep_original(blob, tmp_path / "subs", u"Entry", u"x.ja.srt")
    assert names(keep.entry_folder(tmp_path / "subs", u"Entry")) == []


def test_a_kept_original_is_never_written_over_even_in_a_race(tmp_path, monkeypatch):
    u"""⛔ `os.replace` OVERWRITES. The destination is re-checked immediately
    before it -- the shape `hato/archives.py` uses for every member it writes."""
    blob = a_file(tmp_path / "cache" / u"x.ja.srt", b"new")
    target = a_file(keep.entry_folder(tmp_path / "subs", u"Entry") / u"x.ja.srt", b"old")
    real = keep._place

    def sneak(source, destination):
        a_file(destination, b"someone got there first")
        return real(source, destination)

    monkeypatch.setattr(keep, "_place", sneak)
    with pytest.raises(FileExistsError):
        # `x.ja.srt` holds other bytes, so the hash-suffixed name is tried --
        # and something appears on it between the check and the rename.
        keep.keep_original(blob, tmp_path / "subs", u"Entry", u"x.ja.srt")
    assert target.read_bytes() == b"old"


def test_the_bytes_are_copied_and_never_re_encoded(tmp_path):
    u"""🚨 `LEDGER-HOT.md`: sniff the codec, write the same one back. A
    Shift-JIS caption read with `errors="replace"` had all 346 cues turn to
    U+FFFD while the ASCII timestamps survived -- so the tool said CONFIDENT and
    wrote perfect timing with no readable text."""
    shift_jis = u"1\r\n00:00:01,000 --> 00:00:02,000\r\n\u884c\u3044\u304f\u305e\r\n".encode("cp932")
    with_bom = b"\xef\xbb\xbf" + u"1\r\n\u884c\n".encode("utf-8")
    for label, body in ((u"shift-jis", shift_jis), (u"bom+crlf", with_bom)):
        blob = a_file(tmp_path / label / u"x.ja.srt", body)
        kept = keep.keep_original(blob, tmp_path / ("subs-" + label), u"Entry", u"x.ja.srt")
        assert kept.read_bytes() == body, label


# ---------------------------------------------------------------------------
# 5. ⭐ THE REAL HAND-OFF -- tsubasa, on a video ffmpeg really made
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    u"""One real video, built once. Each check below copies it into its own
    folder, so no two writes ever race for the same destination.

    🚨 `count=61` IS LOAD-BEARING AND IS NOT A TASTE. `07-test-plan.md`'s harness
    points `TSUBASA_CACHE` at ONE temp root for the whole run, and tsubasa's
    results DB keys a record on the SUBTITLE's content -- MEASURED 2026-09-17:
    two syncs of completely different VIDEOS against the same cue text wrote the
    SAME record file, the second overwriting the first. Built with `_media`'s
    defaults this suite's subtitle would be byte-identical to `test_port.py`'s,
    so whichever ran first claimed the record and
    `test_port.py::…disturbs_nothing_else`'s *"the store gained exactly one
    record"* went red in the OTHER suite's file. `run_tests.py write port` was
    red; `existing port` green. A distinct cue count gives a distinct body.
    ⚠ Still comfortably over two 120 s buckets, which is what a `held`
    `runtime_check` needs.
    """
    return _media.build(tmp_path_factory.mktemp("write"), stem=u"Kept Show - 01",
                        count=61)


def stage(built, tmp_path, stem=u"Show - 01", original=None, body=None,
          encoding="utf-8", newline=u"\n", bom=b""):
    u"""A media folder holding ONE video, and a cache holding ONE download.

    ⚠ The cue geometry is `_media`'s, re-encoded here only when a check is
    about the encoding. ⛔ The two folders are different on purpose: the media
    folder must see exactly one filesystem operation per success, tsubasa's.
    """
    media, cache = tmp_path / "media", tmp_path / "cache"
    media.mkdir(parents=True, exist_ok=True)
    video = media / (stem + u".mkv")
    shutil.copyfile(str(built.video), str(video))
    text = _media.srt(built.starts, shift=built.shift) if body is None else body
    data = bom + text.replace(u"\n", newline).encode(encoding)
    return video, a_file(cache / (original or keep.download_name(FRIEREN, u"ja")), data)


def test_the_tagged_original_makes_tsubasa_write_a_file_the_next_run_sees(built, tmp_path):
    u"""🚨 THE CHECK THIS STEP EXISTS FOR, the right way round. The original is
    `<jimaku stem>.ja.<ext>`, tsubasa writes `<video>.ja.<ext>`, and hato's own
    present-check finds it -- so the next run skips instead of fetching."""
    video, original = stage(built, tmp_path)
    result = port.sync(video, original)

    assert port.wrote(result) is True
    written = Path(result.output_path)
    assert written.name == u"Show - 01.ja.ass"        # ⭐ jimaku's .ass, kept .ass
    assert written.parent == video.parent
    assert present.Presence(u"ja").find(video) is not None


def test_an_untagged_original_makes_the_next_run_fetch_again(built, tmp_path):
    u"""🚨 THE TRAP, MEASURED. The SAME bytes under jimaku's own name -- no
    `.ja` -- make tsubasa write `<video>.ass` with no tag at all. hato's
    present-check then reads the video as having no Japanese subtitle, and every
    later run fetches the same episode again, for ever.

    ⭐ Both halves are asserted, because only the pair is the defect: the file
    IS written, and it is invisible to the thing that decides whether to fetch.
    """
    video, original = stage(built, tmp_path, original=FRIEREN)
    result = port.sync(video, original)

    assert port.wrote(result) is True
    written = Path(result.output_path)
    assert written.name == u"Show - 01.ass"
    assert tsubasa.parse_subtitle_name(written.name).lang == present.UND
    assert present.Presence(u"ja").find(video) is None       # ← the never-ending fetch


def test_nothing_of_hatos_ever_lands_in_the_media_folder(built, tmp_path):
    u"""🚨 `03-permissions.md`: the media folder sees exactly ONE filesystem
    operation per success. `subsync` shipped the opposite -- it dropped
    `_ref_2.ass` and a 500 KB `.npy` next to the subtitles it was reading,
    inside a corpus its own README marked read-only."""
    video, original = stage(built, tmp_path)
    result = port.sync(video, original)
    kept = keep.keep_original(original, tmp_path / "subs", u"Entry", original.name)

    assert names(video.parent) == sorted([video.name, Path(result.output_path).name])
    assert not [n for n in names(video.parent)
                if n.endswith((u".part", u".tmp")) or n.startswith(u".")]
    assert original.is_file() and kept.is_file()
    assert kept.parent not in (video.parent,)


def test_out_mirrors_and_the_media_folder_is_not_touched_at_all(built, tmp_path):
    u"""⭐ hato computes the mirrored directory and tsubasa is told it -- only
    hato knows the library root."""
    root = tmp_path / "Anime"
    video, original = stage(built, tmp_path / "Anime" / "Katainaka S2")
    out = tmp_path / "Subs"
    folder = keep.target_dir(video, root, out)

    result = port.sync(video, original, out_dir=folder)

    assert Path(result.output_path).parent == out / "Katainaka S2" / "media"
    assert names(video.parent) == [video.name]
    assert present.Presence(u"ja").find(video, folder) is not None


def test_shift_jis_survives_the_whole_hand_off(built, tmp_path):
    u"""`06-edge-cases.md` §8, and `LEDGER-HOT.md`. The cues carry Japanese text
    the ASCII timestamps would have survived without."""
    video, original = stage(built, tmp_path, encoding="cp932")
    before = original.read_bytes()
    result = port.sync(video, original)
    kept = keep.keep_original(original, tmp_path / "subs", u"Entry", original.name)

    written = Path(result.output_path).read_bytes()
    assert written.decode("cp932").count(u"\u884c") == len(built.starts)
    with pytest.raises(UnicodeDecodeError):
        written.decode("ascii")                  # ⚠ it really is Japanese bytes
    assert kept.read_bytes() == before           # ⛔ hato's copy is byte-identical


def test_a_BOM_and_CRLF_survive_the_whole_hand_off(built, tmp_path):
    video, original = stage(built, tmp_path, newline=u"\r\n", bom=b"\xef\xbb\xbf")
    before = original.read_bytes()
    result = port.sync(video, original)
    kept = keep.keep_original(original, tmp_path / "subs", u"Entry", original.name)

    written = Path(result.output_path).read_bytes()
    assert written.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in written
    assert kept.read_bytes() == before


def test_the_kept_original_is_the_file_the_synced_one_was_made_from(built, tmp_path):
    u"""⚠ WRITE FIRST, KEEP SECOND: `subs_dir` holds exactly the originals that
    were USED. Here the whole 4c sequence runs in order, and both files are
    readable afterwards -- `05-interface.md`'s picture, on disk."""
    video, original = stage(built, tmp_path)
    result = port.sync(video, original)
    assert port.wrote(result)
    kept = keep.keep_original(original, tmp_path / "subs",
                              u"Sousou no Frieren 2nd Season", original.name)

    assert kept.read_bytes() == original.read_bytes()
    assert kept_names(tmp_path / "subs") == [keep.download_name(FRIEREN, u"ja")]
    assert io.open(result.output_path, encoding="utf-8").read().count(u"-->") \
        == len(built.starts)


def test_a_second_run_over_the_same_folder_skips_instead_of_writing_again(built, tmp_path):
    u"""⭐ The loop closed: what tsubasa wrote is what the present-check reads,
    so the second run never asks jimaku anything. ⚠ And the file is NOT written
    twice -- tsubasa refuses a destination it did not account for, which is the
    shape `03-permissions.md` measured."""
    video, original = stage(built, tmp_path)
    port.sync(video, original)
    assert present.Presence(u"ja").find(video) is not None

    again = port.sync(video, original)
    assert again.outcome == port.CONFIDENT
    assert port.wrote(again) is False
    assert again.write_failed is True
    assert u"NOT WRITTEN" in port.why_nothing_was_written(again)


# ---------------------------------------------------------------------------
# 6. the name budget
# ---------------------------------------------------------------------------

def test_a_very_long_jimaku_name_still_keeps_its_tag(tmp_path):
    u"""`06-edge-cases.md` §8: truncate the stem with a short hash suffix, never
    silently fail the write -- and ⛔ never lose the `.ja`."""
    long_name = u"[Group] " + (u"\u9577" * 200) + u" - 29 [JPN].ass"
    blob = a_file(tmp_path / "cache" / u"x.ass", b"x")
    kept = keep.keep_original(blob, tmp_path / "subs", u"Entry",
                              keep.download_name(long_name, u"ja"))
    assert kept.is_file()
    assert len(kept.name) <= cache_module.NAME_MAX
    assert tsubasa.parse_subtitle_name(kept.name).lang == u"ja"
    assert kept.name.endswith(u".ja.ass")


# ---------------------------------------------------------------------------
# the surasura integration -- RUNBOOK 7h
# ---------------------------------------------------------------------------

def test_the_copy_lands_in_a_Hato_folder_inside_the_chosen_directory(tmp_path):
    u"""Sonic: *"it will be in an Hato folder... if I provide the directory for
    downloads, then it would auto-insert it into the Hato directory there."*

    The subfolder is the whole courtesy: somebody will point this at Downloads,
    and a tool that sprays subtitles loose into Downloads is a tool they turn
    off within a day.
    """
    written = tmp_path / "media" / "frieren S2 - 01.ja.ass"
    written.parent.mkdir(parents=True)
    written.write_bytes(b"1\ncue\n")
    chosen = tmp_path / "Downloads"

    landed = keep.surasura_copy(written, chosen)

    assert landed == chosen / keep.SURASURA_FOLDER / written.name
    assert landed.read_bytes() == b"1\ncue\n"
    assert written.is_file(), u"a COPY -- the player's file must stay put"


def test_the_integration_is_off_until_a_folder_is_chosen(tmp_path):
    u"""⛔ Empty means off. Most people do not run surasura."""
    written = tmp_path / "x.ja.ass"
    written.write_bytes(b"cue")
    assert keep.surasura_copy(written, u"") is None
    assert keep.surasura_copy(written, None) is None
    assert list(tmp_path.iterdir()) == [written]


def test_a_re_aligned_subtitle_replaces_the_stale_copy(tmp_path):
    u"""⚠ THE OPPOSITE OF EVERY OTHER WRITE IN THIS MODULE, deliberately.
    `keep_original` refuses to touch a file that is there because it lives in
    the USER'S folders; this one owns its folder, and refusing would leave last
    week's copy as the one surasura reads."""
    written = tmp_path / "x.ja.ass"
    chosen = tmp_path / "drop"
    written.write_bytes(b"first")
    keep.surasura_copy(written, chosen)
    written.write_bytes(b"re-aligned, and better")
    landed = keep.surasura_copy(written, chosen)
    assert landed.read_bytes() == b"re-aligned, and better"


def test_a_missing_source_copies_nothing_rather_than_raising(tmp_path):
    assert keep.surasura_copy(tmp_path / "never-written.ass", tmp_path / "d") is None


def test_a_failed_copy_leaves_no_half_file_behind(tmp_path, monkeypatch):
    u"""🚨 A zero-byte subtitle is worse than none: surasura would read it as an
    empty one rather than as a failure."""
    written = tmp_path / "x.ja.ass"
    written.write_bytes(b"cue")
    chosen = tmp_path / "drop"

    def boom(*a, **k):
        raise OSError("the drive went away")

    monkeypatch.setattr(keep.shutil, "copyfile", boom)
    with pytest.raises(OSError):
        keep.surasura_copy(written, chosen)
    assert list((chosen / keep.SURASURA_FOLDER).iterdir()) == []
