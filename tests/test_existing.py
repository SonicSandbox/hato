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
import _subtitles as subs                                          # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def folder(tmp_path, *names):
    u"""A folder of ZERO-BYTE files. ⛔ A NAMED sidecar is found without opening
    anything, so those checks would pass just as well if the bytes did not exist.
    ⚠ Since 9b one untagged file named for the video IS read -- section 2b writes
    real text into it; here it is empty, which reads as nothing."""
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
        present.language(u"Japanese")           # a NAME, not a code: 2-3 letters only
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


def test_the_country_code_jp_is_read_as_japanese_by_name(tmp_path):
    u"""⭐ RUNBOOK 9c: `.jp.` is Japan's COUNTRY code where a language goes, and
    271 of 17,790 real subtitle names are written that way. tsubasa 0.1.8 reads
    it as `ja` -- the floor in pyproject.toml is 0.1.8 for exactly this -- so a
    `.jp.` sidecar is found by its NAME, with no file read (every casing). On
    0.1.7 the second user's `.jp.srt` read `und`, and hato fetched beside it."""
    for i, name in enumerate((u"Show - 01.jp.srt", u"Show - 01.JP.ass", u"Show - 01.Jp.srt")):
        # ⚠ one folder EACH, not one named for the file: Windows paths ignore
        # case, so `.Jp.srt` landed in `.jp.srt`'s folder and found the old file
        where = folder(tmp_path / str(i), u"Show - 01.mkv", name)     # zero bytes
        found = present.Presence(u"ja").find(where / u"Show - 01.mkv")
        assert found is not None and found.name == name, (name, found)
        assert not found.by_text, u"%s was found by READING it, not by its name" % name


def test_another_language_is_not_the_one_asked_for(tmp_path):
    u"""06 §6: `<video>.en.srt` present, no `.ja` -> **fetch**. The check is per
    (video x language)."""
    where = folder(tmp_path, u"Show - 01.mkv", u"Show - 01.en.srt", u"Show - 01.chi.srt")
    assert present.Presence(u"ja").find(where / u"Show - 01.mkv") is None


def test_an_untagged_sidecar_is_not_the_target_language(tmp_path):
    u"""06 §6: `<video>.srt` is `und`. ⚠ Treated as NOT Japanese and fetched --
    and never overwritten, because the new file takes the `.ja` suffix and both
    coexist. ⭐ Since 9b its TEXT is read first; an empty file says nothing, so
    this is still the fetch it always was (section 2b has the rest)."""
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
# 2b. ⭐ 9b -- a subtitle named for the video that says NO language is READ
# ---------------------------------------------------------------------------
# A second user of 1.0.2: *"It also got subtitles for stuff that already had
# subtitles. Even though the subs were named after the video."* Sonic ruled the
# shape: *"needs to not report falsely ... errs on the side of 'download' than
# not, but does check."* So every check below has the arm that reads as
# Japanese AND the nearest arm that must not.

def beside(tmp_path, name, data, video=u"Show - 01.mkv"):
    u"""The video, and one file beside it holding `data` (bytes)."""
    where = folder(tmp_path, video)
    (where / name).write_bytes(data)
    return where


def look(where, video=u"Show - 01.mkv", lang=u"ja"):
    return present.Presence(lang).find(where / video)


def test_an_untagged_japanese_subtitle_named_for_the_video_is_present(tmp_path):
    u"""⭐ THE REPORT, and what is said about it: found, and `by_text` -- the name
    gave no language and the text did, which is the one thing the skip must be
    able to say out loud."""
    where = beside(tmp_path, u"Show - 01.srt",
                   subs.srt(subs.lines(subs.JA, 300)).encode("utf-8"))
    found = look(where)
    assert found is not None and found.name == u"Show - 01.srt", found
    assert found.by_text is True


def test_every_encoding_a_japanese_subtitle_comes_in_is_read(tmp_path):
    u"""UTF-8 with and without a BOM, UTF-16 by its BOM, and Shift-JIS -- in both
    the formats a person names after a video."""
    body = subs.lines(subs.JA, 300)
    for ext, text in ((u"srt", subs.srt(body)), (u"ass", subs.ass(body))):
        for encoding in (u"utf-8", u"utf-8-sig", u"utf-16", u"cp932"):
            name = u"Show - 01.%s" % ext
            where = beside(tmp_path / (ext + encoding), name, text.encode(encoding))
            found = look(where)
            assert found is not None and found.by_text, (ext, encoding)


def test_an_untagged_english_or_chinese_subtitle_is_still_fetched_beside(tmp_path):
    u"""The fetch the user hit is still right for everything that is not Japanese
    -- including Chinese in the two encodings that could pass for Shift-JIS."""
    cases = ((u"English", subs.srt(subs.lines(subs.EN, 300)).encode("utf-8")),
             (u"Chinese", subs.srt(subs.lines(subs.ZH, 300)).encode("utf-8")),
             (u"Chinese, GBK", subs.srt(subs.lines(subs.ZH, 300)).encode("gbk")))
    for label, data in cases:
        assert look(beside(tmp_path / label, u"Show - 01.srt", data)) is None, label


def test_chinese_in_big5_is_not_read_as_japanese_through_half_width_katakana(tmp_path):
    u"""⚠ Big5 DECODES as Shift-JIS without an error, and most of what comes out is
    HALF-width katakana. Counted as kana, a Chinese file is Japanese. Two arms:
    the bytes really do decode, and the answer is still no."""
    zh_tw = [line.replace(u"没", u"沒").replace(u"准", u"準") for line in subs.ZH]
    data = subs.srt(subs.lines(zh_tw, 300)).encode("big5", errors="ignore")
    decoded = data.decode("cp932")                                  # arm 1: it decodes
    assert any(u"\uff66" <= ch <= u"\uff9d" for ch in decoded), \
        u"the fixture no longer produces half-width katakana -- it tests nothing"
    assert look(beside(tmp_path, u"Show - 01.srt", data)) is None    # arm 2: not Japanese


def test_japanese_with_chinese_beside_it_is_not_confirmed(tmp_path):
    u"""⭐ The nearest wrong answer, measured at 0.45 kana against real files'
    0.68 or more. Both shapes a mixed file comes in; and the CONTROL -- the same
    Japanese alone -- so this cannot pass because the Japanese half fails."""
    ja, zh = subs.lines(subs.JA, 300), subs.lines(subs.ZH, 300)
    one_event = subs.ass([z + u"\\N" + j for z, j in zip(zh, ja)])
    alternating = subs.srt([x for pair in zip(zh, ja) for x in pair])
    for label, text in ((u"one event", one_event), (u"alternating", alternating)):
        name = u"Show - 01.ass" if label == u"one event" else u"Show - 01.srt"
        assert look(beside(tmp_path / label, name, text.encode("utf-8"))) is None, label
    assert look(beside(tmp_path / u"control", u"Show - 01.srt",
                       subs.srt(ja).encode("utf-8"))) is not None


def test_an_english_subtitle_with_a_japanese_song_is_not_japanese(tmp_path):
    u"""Lyrics in kana, forty lines of three hundred: kana-rich where they are,
    and nowhere near the share of LINES real Japanese dialogue has (0.65+)."""
    body = subs.lines(subs.EN, 260) + [u"♪ " + j for j in subs.lines(subs.JA, 40)]
    assert look(beside(tmp_path, u"Show - 01.srt", subs.srt(body).encode("utf-8"))) is None


def test_too_little_to_judge_is_fetched(tmp_path):
    u"""A signs-only file, or a stub, is not a full subtitle (06 §6's forced rule
    in spirit). Two arms at the threshold itself -- and ⚠ one arm that is NOT
    computed from it: a 60-line Japanese file, a signs track's size, must be
    fetched over. Arms derived from the constant move with it, and a mutant
    that set the floor to 10 SURVIVED them (M9b-06, 2026-09-23)."""
    short = subs.srt(subs.lines(subs.JA, present.MIN_LINES - 1)).encode("utf-8")
    enough = subs.srt(subs.lines(subs.JA, present.MIN_LINES)).encode("utf-8")
    signs = subs.srt(subs.lines(subs.JA, 60)).encode("utf-8")
    assert look(beside(tmp_path / u"short", u"Show - 01.srt", short)) is None
    assert look(beside(tmp_path / u"enough", u"Show - 01.srt", enough)) is not None
    assert look(beside(tmp_path / u"signs", u"Show - 01.srt", signs)) is None


def test_drawings_in_an_ass_are_not_dialogue(tmp_path):
    u"""A typeset `.ass` carries vector shapes as events, and their text is
    coordinates. 300 lines of dialogue among 600 of them is 0.33 of the events --
    below the line share -- unless the shapes are set aside, as they must be."""
    text = subs.ass(subs.lines(subs.JA, 300), drawings=600)
    assert look(beside(tmp_path, u"Show - 01.ass", text.encode("utf-8"))) is not None


def test_only_a_text_subtitle_named_exactly_for_the_video_is_read(tmp_path):
    u"""The same Japanese text in four places; only the plain `<video>.<ext>` is
    the video's. ⚠ `Show - 01.nfo` is not a subtitle; `Show - 02.srt` is another
    episode's; `Show - 01.forced.srt` is a flag with no language, which tsubasa
    reads as part of the stem."""
    data = subs.srt(subs.lines(subs.JA, 300)).encode("utf-8")
    for name in (u"Show - 01.nfo", u"Show - 02.srt", u"Show - 01.forced.srt",
                 # ⚠ `.und.` IS read as untagged -- but with a flag it is a forced
                 # sub, and a forced sub is not a full one (06 §6).
                 u"Show - 01.und.forced.srt"):
        assert look(beside(tmp_path / name, name, data)) is None, name
    assert look(beside(tmp_path / u"control", u"Show - 01.srt", data)) is not None
    assert look(beside(tmp_path / u"explicit", u"Show - 01.und.srt", data)) is not None


def test_a_real_shaped_file_with_many_lines_but_no_kana_still_reads(tmp_path):
    u"""⭐ THE REAL LOW END, not the fixture's easy one. The measured minimum was a
    broadcast `.ass` with kana in 0.65 of its lines -- sound cues and music marks
    are lines too. 300 lines of dialogue and 160 without a kana in them is that
    shape. ⚠ And it is what makes the cue numbers and timings matter: counted as
    lines, they would halve the share and fetch over a real Japanese file."""
    body = subs.lines(subs.JA, 300) + [u"♪～", u"（拍手）"] * 80
    found = look(beside(tmp_path, u"Show - 01.srt", subs.srt(body).encode("utf-8")))
    assert found is not None and found.by_text


def test_a_named_japanese_sidecar_is_found_without_reading_anything(tmp_path, monkeypatch):
    u"""⛔ The common case stays free: with `.ja.` beside the video no file is
    read, whatever else is there. ⚠ IN BOTH LISTING ORDERS. The folder is listed
    alphabetically here, and `Show - 01.ja.ass` sorts before `Show - 01.srt` --
    so the named file won before the untagged one was ever seen, and a mutant
    reading every untagged file on sight SURVIVED (M9b-05, 2026-09-23).
    `Show - 01.ass` sorts before `Show - 01.ja.srt`, which is the other order."""

    def read(path):
        raise AssertionError(u"read %s although a named sidecar is there" % path)
    monkeypatch.setattr(present, "reads_as_japanese", read)
    body = subs.lines(subs.JA, 300)
    for untagged, text, named in ((u"Show - 01.srt", subs.srt(body), u"Show - 01.ja.ass"),
                                  (u"Show - 01.ass", subs.ass(body), u"Show - 01.ja.srt")):
        where = beside(tmp_path / untagged, untagged, text.encode("utf-8"))
        (where / named).write_bytes(b"")
        found = look(where)
        assert found is not None and found.name == named and not found.by_text, untagged


def test_only_japanese_text_is_ever_judged(tmp_path, monkeypatch):
    u"""⛔ Another wanted language never reads a file -- 9b judges Japanese and
    nothing else, so asking for English is the name-only answer it always was."""
    where = beside(tmp_path, u"Show - 01.srt",
                   subs.srt(subs.lines(subs.EN, 300)).encode("utf-8"))

    def read(path):
        raise AssertionError(u"read %s for a language 9b does not judge" % path)
    monkeypatch.setattr(present, "reads_as_japanese", read)
    assert look(where, lang=u"en") is None


def test_what_cannot_be_decoded_is_fetched(tmp_path):
    junk = bytes(bytearray(range(256))) * 400
    assert look(beside(tmp_path, u"Show - 01.srt", junk)) is None


def test_a_file_bigger_than_what_is_read_is_never_judged_on_the_part(tmp_path, monkeypatch):
    u"""🚨 ADVERSARY 2026-09-23 (9b): part of a file is a SAMPLE, and a sample lied
    -- a 4.5 MB `[CHS, JPN]` .ass read as Japanese from its first 2 MB (its OP
    karaoke) and not Japanese whole. That shape, scaled down: Japanese first,
    Chinese beside Japanese after. Two arms around the limit -- read whole, it is
    not Japanese; cut, it is NOT JUDGED (fetched), never *"Japanese"* -- and the
    control, the same size of Japanese alone read whole, which is."""
    ja, zh = subs.lines(subs.JA, 300), subs.lines(subs.ZH, 300)
    head = [u"♪ " + j for j in ja]                                   # the karaoke
    mixed = subs.srt(head + [x for pair in zip(zh, ja) for x in pair] * 3).encode("utf-8")
    pure = subs.srt(head + ja * 6).encode("utf-8")
    # ⚠ THE CUT LANDS BETWEEN TWO CUES -- whole characters, whole lines. Cut inside
    # a character, the part fails to DECODE and reads "not Japanese" for that
    # reason instead, and the rule this guards could go unnoticed: M9b-10 SURVIVED
    # exactly that (2026-09-23). The read is `READ_LIMIT + 1` bytes: this part.
    first_part = mixed[:len(mixed) // 4].rsplit(b"\n\n", 1)[0] + b"\n\n"
    assert look(beside(tmp_path / u"part", u"Show - 01.srt", first_part)) is not None, (
        u"the fixture's first part no longer reads as Japanese -- it tests nothing")
    assert look(beside(tmp_path / u"whole", u"Show - 01.srt", mixed)) is None
    monkeypatch.setattr(present, "READ_LIMIT", len(first_part) - 1)
    assert look(beside(tmp_path / u"cut", u"Show - 01.srt", mixed)) is None
    control = pure[:len(first_part) - 1].rsplit(b"\n\n", 1)[0]
    assert look(beside(tmp_path / u"cut-control", u"Show - 01.srt", control)) is not None


def test_an_ass_whose_fonts_come_before_its_events_is_read_whole(tmp_path):
    u"""🚨 ADVERSARY 2026-09-23 (9b): a fansub .ass carries its fonts in `[Fonts]`,
    uuencoded, BEFORE `[Events]` -- 2.4 MB here -- and at a 2 MB limit its dialogue
    was never read: fetched over a Japanese file, every run. Measured: 65 of
    25,153 real subtitles pass 2 MB, the largest 20.7."""
    fonts = u"[Fonts]\nfontname: Kyokasho_0.ttf\n" + (u"M" + u"!" * 60 + u"\n") * 40000
    text = subs.ass(subs.lines(subs.JA, 300))
    events = text.index(u"[Events]")
    data = (text[:events] + fonts + u"\n" + text[events:]).encode("utf-8")
    assert 2 * 1024 * 1024 < len(data) <= present.READ_LIMIT, len(data)
    found = look(beside(tmp_path, u"Show - 01.ass", data))
    assert found is not None and found.by_text


def test_a_video_whose_own_name_ends_in_a_language_is_read_by_its_exact_name(tmp_path):
    u"""🚨 ADVERSARY 2026-09-23 (9b x 9c): `Show.S01E01.JP.srt` beside
    `Show.S01E01.JP.mkv` is the video's own name -- and once tsubasa read `.jp`
    (9c) it parsed as a Japanese tag on `Show.S01E01`: neither the video's named
    sidecar nor untagged, so hato fetched over it. Named exactly for the video
    is untagged, whatever the parse. Arms: Japanese inside -> present by its
    text; English -> fetched; hato's own `.JP.ja.srt` -> present by its NAME."""
    video = u"Show.S01E01.JP.mkv"
    ja = subs.srt(subs.lines(subs.JA, 300)).encode("utf-8")
    en = subs.srt(subs.lines(subs.EN, 300)).encode("utf-8")
    found = look(beside(tmp_path / u"ja", u"Show.S01E01.JP.srt", ja, video=video), video=video)
    assert found is not None and found.by_text, found
    assert look(beside(tmp_path / u"en", u"Show.S01E01.JP.srt", en, video=video),
                video=video) is None
    named = look(beside(tmp_path / u"named", u"Show.S01E01.JP.ja.srt", b"", video=video),
                 video=video)
    assert named is not None and not named.by_text, named


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
