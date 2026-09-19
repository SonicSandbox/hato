# -*- coding: utf-8 -*-
u"""
hato/present.py -- the front half of the read rule (RUNBOOK 4b).

Two questions, and each is a permanent silent failure when it is answered wrong:

  🚨 *Is the subtitle already there?* A false YES is a never-fetch that nobody
     ever sees. The whole point of this module is that the answer is the
     CANONICAL SIDECAR BY NAME, and not `scan.unpaired(lang=)` -- which the
     check below measures saying *covered* for a video that has nothing.

  ⚠ *Can this video be synced at all?* Four answers, not two. An unreadable
     container is an ERROR **before any download**, because tsubasa's `sync()`
     reads the same container and the network is metered.

⛔ WHAT THESE CHECKS STRUCTURALLY CANNOT COVER: whether tsubasa's language
reader is right. That is tsubasa's own gate. What they DO pin is every reading
hato depends on, so the day one changes, a named check here goes red rather
than a library silently never fetching again.
"""
import os
import sys
from pathlib import Path

import pytest
import tsubasa

from hato import present

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _media                                                      # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def folder(tmp_path, *names):
    u"""A folder of ZERO-BYTE files. ⛔ Nothing here may be opened: every check
    below would pass just as well if the bytes did not exist, which is what
    *"opens nothing"* means."""
    where = tmp_path / "media"
    where.mkdir(parents=True, exist_ok=True)
    for name in names:
        (where / name).write_bytes(b"")
    return where


class Track(object):
    u"""A stand-in for `tsubasa.EmbeddedSubtitle`. ⚠ Only the five fields
    `read_tracks` reads; anything else it grew would be unused here anyway."""

    def __init__(self, lang=u"ja", text=True, bitmap=False, codec=u"S_TEXT/UTF8",
                 index=2, forced=False):
        self.lang, self.text, self.bitmap = lang, text, bitmap
        self.codec, self.index, self.forced = codec, index, forced


class Answer(object):
    u"""A stand-in for `tsubasa.EmbeddedSubtitles`.

    🚨 `.tracks` RAISES when `ok` is False, exactly as the real one does
    (measured: *"an unread video is not a video with no tracks"*). A stub that
    returned `[]` there would let `read_tracks` report *no subtitle track* for a
    container it could not open -- a SKIP where the answer is an ERROR.
    """

    def __init__(self, ok=True, reason=u"", tracks=()):
        self.ok, self.reason, self._tracks = ok, reason, tuple(tracks)

    @property
    def tracks(self):
        if not self.ok:
            raise ValueError(u"nothing is known about the subtitle tracks: %s" % self.reason)
        return self._tracks


def reader_of(answer):
    return lambda video, **kwargs: answer


# ---------------------------------------------------------------------------
# 1. the language, resolved by tsubasa and nobody else
# ---------------------------------------------------------------------------

def test_every_spelling_of_japanese_resolves_to_one_code():
    assert present.language(u"ja") == u"ja"
    assert present.language(u"jpn") == u"ja"
    assert present.language(u"JA") == u"ja"
    assert present.language(u"ja-JP") == u"ja"


def test_the_collision_pairs_both_reference_implementations_get_wrong():
    u"""`02-data-model.md`: `hi` is **Hindi**, `chi` is Chinese and ⛔ not
    hearing-impaired. Pinned here because hato asks tsubasa for them."""
    assert present.language(u"hi") == u"hi"
    assert present.language(u"chi") == u"zh"
    assert present.language(u"fo") == u"fo"


def test_a_tag_that_would_become_und_is_refused_loudly():
    u"""⛔ `und` matches every UNTAGGED subtitle in the library, and 06 §6 rules
    that `<video>.srt` is never the target language. A tag quietly becoming
    `und` would mark the whole library present and stop hato ever fetching."""
    with pytest.raises(present.LanguageUnknown):
        present.language(u"zz")
    with pytest.raises(present.LanguageUnknown):
        present.language(u"Japanese")           # see the defect check below
    with pytest.raises(present.LanguageUnknown):
        present.language(u"ja.forced")          # a dot would be two tokens


def test_und_itself_is_still_askable():
    assert present.language(u"und") == u"und"


# ---------------------------------------------------------------------------
# 2. 🚨 what counts as PRESENT
# ---------------------------------------------------------------------------

def test_the_canonical_sidecar_beside_the_video_is_present(tmp_path):
    where = folder(tmp_path, u"Show - 01.mkv", u"Show - 01.ja.ass")
    found = present.Presence(u"ja").find(where / u"Show - 01.mkv")
    assert found is not None
    assert found.name == u"Show - 01.ja.ass"
    assert Path(found.path).parent == where


def test_a_resolved_spelling_counts_too(tmp_path):
    u"""`.jpn` and `.ja-JP` are the same language and must not be fetched over
    (`05-interface.md` §Naming)."""
    for name in (u"Show - 01.jpn.srt", u"Show - 01.ja-JP.srt", u"Show - 01.ja.sdh.srt"):
        where = folder(tmp_path / name, u"Show - 01.mkv", name)
        assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is not None, name


def test_another_language_is_not_the_one_asked_for(tmp_path):
    u"""06 §6: `<video>.en.srt` present, no `.ja` -> **fetch**. The check is per
    (video x language)."""
    where = folder(tmp_path, u"Show - 01.mkv", u"Show - 01.en.srt", u"Show - 01.chi.srt")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is None


def test_an_untagged_sidecar_is_not_the_target_language(tmp_path):
    u"""06 §6: `<video>.srt` is `und`. ⚠ Treated as NOT Japanese and fetched --
    and never overwritten, because the new file takes the `.ja` suffix and both
    coexist."""
    where = folder(tmp_path, u"Show - 01.mkv", u"Show - 01.srt")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is None


def test_a_forced_subtitle_is_not_a_full_subtitle(tmp_path):
    u"""06 §6, and it is one of the three shapes the orchestrator measured
    `unpaired()` getting wrong."""
    where = folder(tmp_path, u"Show - 02.mkv", u"Show - 02.ja.forced.srt")
    assert present.Presence(u"ja").find(where / u"Show - 02.mkv") is None


def test_an_unrenamed_original_beside_the_video_does_not_count(tmp_path):
    u"""⚠ THE ASYMMETRY, stated as a check. `[Group] Show - 04 [JPN].ja.ass` is
    a Japanese subtitle for this episode by any human reading -- and it is NOT
    what a player loads. A false *present* is permanent and silent; a false
    *absent* is one unmetered download and a visible duplicate."""
    where = folder(tmp_path, u"Show - 04.mkv", u"[Group] Show - 04 [JPN].ja.ass")
    assert present.Presence(u"ja").find(where / u"Show - 04.mkv") is None


def test_a_subtitle_in_another_folder_is_not_present(tmp_path):
    where = folder(tmp_path, u"Show - 01.mkv")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / u"Show - 01.ja.ass").write_bytes(b"")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is None


def test_the_folder_asked_about_is_the_one_read(tmp_path):
    u"""🚨 THE `--out` DEFECT, as a property of this function. Under `--out` the
    previous run's file is in the MIRRORED directory and the video's own folder
    holds nothing -- so `find()` takes the folder and `keep.target_dir()`
    computes it for the present-check and the write alike."""
    where = folder(tmp_path, u"Show - 01.mkv")
    mirrored = tmp_path / "out" / "Season 2"
    mirrored.mkdir(parents=True)
    (mirrored / u"Show - 01.ja.ass").write_bytes(b"")
    look = present.Presence(u"ja")
    assert look.find(where / u"Show - 01.mkv") is None                    # beside it: nothing
    assert look.find(where / u"Show - 01.mkv", mirrored) is not None      # mirrored: there


def test_a_mirrored_folder_that_does_not_exist_yet_is_simply_empty(tmp_path):
    u"""⚠ Under `--out` the mirrored directory does not exist until the first
    file lands in it, and *"nothing is there yet"* is the answer, not a crash."""
    where = folder(tmp_path, u"Show - 01.mkv")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv",
                                        tmp_path / "out" / "never made") is None


def test_junk_in_the_folder_is_ignored_without_an_error(tmp_path):
    where = folder(tmp_path, u"Show - 01.mkv", u"Thumbs.db", u"folder.jpg",
                   u"notes", u"Show - 01.ja.ass")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is not None


# ---------------------------------------------------------------------------
# 3. 🚨 THE MEASUREMENT THIS MODULE EXISTS FOR
# ---------------------------------------------------------------------------

def test_tsubasas_unpaired_says_covered_for_a_video_that_has_nothing(tmp_path):
    u"""🚨 THE PART 1 DEFECT, RE-MEASURED AGAINST THE REAL ENGINE.

    `03-permissions.md` carried *"`sidecar_exists(video, lang)` is
    `scan.unpaired(lang=...)`"*. Against three stubs in one folder the engine
    answers `[]` -- Bravo Tale is *covered* -- by offering Alpha Show's
    subtitle, which is correct for tsubasa (its TIMING then decides) and fatal
    for a fetcher: one show's episode 1 would stop hato fetching episode 1 of
    every other show in the library, silently and for good.

    ⚠ If tsubasa ever narrows `unpaired`, THIS check goes red and not the
    library -- which is the point of pinning a belief rather than holding it.
    """
    where = folder(tmp_path, u"Alpha Show - 01.mkv", u"Bravo Tale - 01.mkv",
                   u"Alpha Show - 01 (1080p).ja.ass")
    assert tsubasa.scan(videos=str(where)).unpaired(lang=u"ja") == []
    assert present.Presence(u"ja").find(where / u"Bravo Tale - 01.mkv") is None


def test_the_same_thing_across_sibling_folders(tmp_path):
    u"""The real library shape: one show's folder answering for another's."""
    root = tmp_path / "lib"
    (root / "Alpha Show").mkdir(parents=True)
    (root / "Bravo Tale").mkdir(parents=True)
    (root / "Alpha Show" / u"Alpha Show - S01E01.mkv").write_bytes(b"")
    (root / "Alpha Show" / u"Alpha Show - S01E01.ja.ass").write_bytes(b"")
    (root / "Bravo Tale" / u"Bravo Tale - S01E01.mkv").write_bytes(b"")
    assert tsubasa.scan(videos=str(root)).unpaired(lang=u"ja") == []
    look = present.Presence(u"ja")
    assert look.find(root / "Bravo Tale" / u"Bravo Tale - S01E01.mkv") is None
    assert look.find(root / "Alpha Show" / u"Alpha Show - S01E01.mkv") is not None


def test_the_jellyfin_display_name_is_read_as_japanese(tmp_path):
    u"""⭐ `06-edge-cases.md` §6: `<video>.Japanese.srt` is recognised, because
    *"Jellyfin and Emby both document it"*.

    🚨 THIS CHECK IS THE ONE THAT WENT RED ON PURPOSE. It was written on
    2026-09-17 asserting the OPPOSITE -- tsubasa read every casing as `und`, so
    hato fetched beside a sidecar that was already Japanese, and the check pinned
    that defect with a note saying *the day tsubasa learns the display name, this
    goes red and the spec row can be un-flagged*. Hours later it did, in a full
    run nobody aimed at it. ⭐ **A check written to fail on good news is how a
    dependency's fix reaches a consumer without anyone remembering to look.**

    ⛔ hato still does not read languages itself -- a second reader here would
    drift from tsubasa's (`LEDGER-HOT.md`). It asks, and now gets the right
    answer. ⚠ Which means hato's tsubasa floor moves: `10-deployment.md`.
    """
    for spelling in (u"Japanese", u"japanese", u"JAPANESE"):
        assert tsubasa.parse_subtitle_name(u"Show - 01.%s.srt" % spelling).lang == u"ja"
    # ⚠ The flag survives the display name -- it did not have to. Both halves of
    # `.Japanese.forced.` are read, and a forced sub is NOT a full one (§6).
    forced = tsubasa.parse_subtitle_name(u"Show - 01.Japanese.forced.srt")
    assert forced.lang == u"ja" and u"forced" in forced.flags

    where = folder(tmp_path, u"Show - 01.mkv", u"Show - 01.Japanese.srt")
    # ⭐ The consequence hato cares about: it is PRESENT now, so no fetch, no
    # duplicate. Before the upstream fix this returned None and hato re-fetched.
    found = present.Presence(u"ja").find(where / u"Show - 01.mkv")
    assert found is not None and found.name == u"Show - 01.Japanese.srt"


# ---------------------------------------------------------------------------
# 4. one listing per folder, not one per video
# ---------------------------------------------------------------------------

def test_a_folder_is_listed_once_however_many_videos_it_holds(tmp_path, monkeypatch):
    u"""⭐ Rule 4 (`spec/00-INDEX.md`): is every unit of work necessary? A
    1,700-file folder answered per video is 1,700 listings of the same names,
    and the quiet re-run is the commonest thing hato does."""
    names = [u"Show - %02d.mkv" % n for n in range(1, 25)]
    where = folder(tmp_path, *names)
    listings = []
    real = present._listing
    monkeypatch.setattr(present, "_listing",
                        lambda f: listings.append(f) or real(f))
    look = present.Presence(u"ja")
    for name in names:
        look.find(where / name)
    assert len(listings) == 1


def test_forget_makes_the_next_look_read_the_folder_again(tmp_path):
    u"""⚠ After a file lands, a later video in the same run must see it."""
    where = folder(tmp_path, u"Show - 01.mkv")
    look = present.Presence(u"ja")
    assert look.find(where / u"Show - 01.mkv") is None
    (where / u"Show - 01.ja.ass").write_bytes(b"")
    assert look.find(where / u"Show - 01.mkv") is None          # still the cached listing
    look.forget(where)
    assert look.find(where / u"Show - 01.mkv") is not None


# ---------------------------------------------------------------------------
# 5. ⚠ the track reader -- FOUR answers
# ---------------------------------------------------------------------------

def test_an_unreadable_container_is_an_error_carrying_tsubasas_own_reason():
    u"""⭐ ERROR, **before any download**. tsubasa's `sync()` reads the same
    container, so a download would only reach the same ERROR afterwards -- and
    the network is metered. Its reason names the fix (usually *install
    ffmpeg*), so it is carried verbatim rather than paraphrased."""
    said = (u"reading Nothing.mp4 needs ffmpeg, which was not found on PATH ... "
            u"then either put it on PATH or set TSUBASA_FFMPEG")
    answer = present.read_tracks(u"Nothing.mp4", u"ja",
                                 reader=reader_of(Answer(ok=False, reason=said)))
    assert answer.kind == present.UNREADABLE
    assert answer.ok is False
    assert answer.reason == said


def test_an_unreadable_container_never_reaches_tracks():
    u"""🚨 The real `.tracks` RAISES when `ok` is False, deliberately. A reader
    answered in the wrong order would turn an ERROR into *no subtitle track*,
    which is a SKIP -- and hato would never try that video again this way."""
    answer = present.read_tracks(u"Nothing.mp4", u"ja",
                                 reader=reader_of(Answer(ok=False, reason=u"broken")))
    assert answer.tracks == ()


def test_an_embedded_japanese_text_track_is_a_skip():
    u"""06 §6, RULED: already there and already in sync -- zero network, zero
    alignment."""
    answer = present.read_tracks(u"x.mkv", u"ja",
                                 reader=reader_of(Answer(tracks=[Track(lang=u"ja")])))
    assert answer.kind == present.EMBEDDED
    assert u"already" in answer.reason


def test_an_embedded_english_track_is_not_the_one_asked_for():
    answer = present.read_tracks(u"x.mkv", u"ja",
                                 reader=reader_of(Answer(tracks=[Track(lang=u"en")])))
    assert answer.kind == present.FETCH


def test_no_track_at_all_is_a_skip_and_says_what_would_change_it():
    u"""⭐ RULED 2026-09-17: a SKIP, never a fifth outcome and ⛔ never a
    refusal -- a refusal row would blacklist a good subtitle for ever,
    including after tsubasa can sync from audio."""
    answer = present.read_tracks(u"raw.mkv", u"ja", reader=reader_of(Answer(tracks=[])))
    assert answer.kind == present.NO_TRACK
    assert u"can't sync yet" in answer.reason


def test_a_track_that_is_neither_text_nor_bitmap_is_the_same_skip():
    u"""⚠ A codec tsubasa's allow-lists do not know. The rule's intent, not its
    letter -- there is nothing to time against either way."""
    answer = present.read_tracks(
        u"x.mkv", u"ja",
        reader=reader_of(Answer(tracks=[Track(lang=u"ja", text=False, bitmap=False,
                                              codec=u"S_SOMETHING_NEW")])))
    assert answer.kind == present.NO_USABLE
    assert u"S_SOMETHING_NEW" in answer.reason


def test_a_bitmap_japanese_track_is_fetched_normally():
    u"""06 §6: PGS/VobSub is **not** a text subtitle. tsubasa times against a
    bitmap track happily, so hato fetches."""
    answer = present.read_tracks(
        u"x.mkv", u"ja",
        reader=reader_of(Answer(tracks=[Track(lang=u"ja", text=False, bitmap=True,
                                              codec=u"S_HDMV/PGS")])))
    assert answer.kind == present.FETCH


def test_a_japanese_bitmap_track_beside_an_english_text_one_is_still_fetched():
    answer = present.read_tracks(
        u"x.mkv", u"ja",
        reader=reader_of(Answer(tracks=[Track(lang=u"en", text=True),
                                        Track(lang=u"ja", text=False, bitmap=True)])))
    assert answer.kind == present.FETCH


# ---------------------------------------------------------------------------
# 6. ⭐ the real reader, on a real container
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def japanese_video(tmp_path_factory):
    u"""A real video with an embedded Japanese TEXT track."""
    return _media.build(tmp_path_factory.mktemp("has-ja"))


@pytest.fixture(scope="module")
def english_video(tmp_path_factory):
    u"""The same, with the track tagged `eng` -- the shape hato FETCHES for."""
    return _media.build(tmp_path_factory.mktemp("has-en"), track_language=u"eng")


def test_the_real_reader_finds_the_japanese_track_and_skips(japanese_video):
    u"""⛔ Through tsubasa's PUBLIC reader (RUNBOOK T4), never
    `tsubasa.container` (`LEDGER-HOT.md`)."""
    answer = present.read_tracks(japanese_video.video, u"ja")
    assert answer.kind == present.EMBEDDED
    assert [t.lang for t in answer.tracks] == [u"ja"]


def test_the_real_reader_reads_a_track_language_it_was_not_asked_about(english_video):
    answer = present.read_tracks(english_video.video, u"ja")
    assert answer.kind == present.FETCH
    assert [t.lang for t in answer.tracks] == [u"en"]
    assert answer.tracks[0].text is True


def test_the_real_reader_on_a_file_that_is_not_a_container(tmp_path):
    u"""⭐ Measured on this machine: no ffmpeg on PATH, so a container the native
    Matroska reader cannot take apart is `ok=False` with a reason naming the
    fix. That is an ERROR before any download, and NOT *no subtitle track*."""
    broken = tmp_path / u"Nothing - 01.mkv"
    broken.write_bytes(b"\x1aE\xdf\xa3" + b"\x00" * 64)
    answer = present.read_tracks(broken, u"ja")
    assert answer.kind == present.UNREADABLE
    assert answer.reason.strip()
    assert u"ffmpeg" in answer.reason
