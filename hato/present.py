# -*- coding: utf-8 -*-
u"""
The front half of the read rule: is a subtitle ALREADY THERE, and can this video
be synced at all (spec/03-permissions.md §The read rule, RUNBOOK 4b).

    look = Presence(u"ja")
    if look.find(video, folder=target):     return SKIP(u"subtitle already present")
    answer = read_tracks(video, u"ja")
    answer.kind                             one of the five below

Two questions, and each has its own measured trap.

===========================================================================
🚨 QUESTION 1 -- AND `scan.unpaired(lang=)` IS NOT THE ANSWER TO IT
===========================================================================

`03-permissions.md` carried the equivalence *"`sidecar_exists(video, lang)` is
`scan.unpaired(lang=...)`"* until the build measured it. Re-measured here against
tsubasa 0.1.4, three zero-byte stubs in one folder::

    Alpha Show - 01.mkv · Bravo Tale - 01.mkv · Alpha Show - 01 (1080p).ja.ass
    scan(...).unpaired(lang="ja")  ->  []        # Bravo Tale has NO subtitle

The episode index offers every same-numbered subtitle in the walk -- correctly,
for tsubasa, whose TIMING then decides. But *"no Japanese subtitle was offered"*
is a far weaker fact than *"this video has its Japanese subtitle"*, and in a real
library one show's episode 1 would stop hato ever fetching episode 1 of every
other show, silently and for good.

⭐ SO: PRESENT means the canonical sidecar, BY NAME -- a file **in the target
directory** whose stem equals the video's basename, whose language resolves to
the wanted one, and which is **not forced** (`06-edge-cases.md` §6: *a forced sub
is not a full sub*). That is the one form Plex, Jellyfin and Emby all load, and
⛔ it is found without opening anything. The one exception is question 1c below:
a file named for the video whose name gives NO language is read.

⚠ THE ASYMMETRY THAT DECIDES EVERY CLOSE CALL. A false *present* is a permanent,
silent never-fetch. A false *absent* is one unmetered download and a visible
duplicate that is never overwritten (tsubasa's explicit path supersedes nothing).
So an un-renamed `[Group] Show - 04 [JPN].ja.ass` does **not** count as present,
and the fetched copy is written beside it.

===========================================================================
⭐ QUESTION 1c -- A SUBTITLE NAMED FOR THE VIDEO THAT SAYS NO LANGUAGE (9b)
===========================================================================

A second user of 1.0.2, 2026-09-23: *"It also got subtitles for stuff that already
had subtitles. Even though the subs were named after the video, was made
specifically for that video, and had perfect sync already."* `Show - 01.srt`
names no language, so by name alone it is `und` -- and hato fetched beside it.

⭐ SO THAT ONE FILE IS READ, and only it: no Japanese-NAMED sidecar was found, the
name is the video's exact stem with nothing after it, and the extension is a text
subtitle. Sonic ruled the shape: *"needs to not report falsely ... errs on the side
of 'download' than not, but does check."* So it counts as present only on strong
evidence, measured on 163 real Japanese subtitles against the nearest wrong
answers (RUNBOOK 9b):

    at least MIN_LINES dialogue lines             real: 290 or more
    kana in at least MIN_LINE_SHARE of them        real: 0.65 or more · English
                                                   with a Japanese song: 0.13
    kana at least MIN_KANA_SHARE of kana + kanji   real: 0.68 or more · the same
                                                   lines with Chinese beside
                                                   them: 0.45

⛔ Anything short of that -- undecodable, too short, mixed, a signs-only file, or
too big to read WHOLE (`READ_LIMIT`: part of a file is a sample, and a sample
lied) -- is ABSENT, which is exactly what it was before this read existed. ⛔ Only for
Japanese: any other wanted language is never read. ⚠ Full-width kana only: a
Chinese file in Big5 decodes as Shift-JIS into HALF-width katakana, and counting
those would call it Japanese.

⚠ Why not tsubasa's `naming.normalize.script_of`: it answers CJK-or-Latin for a
TITLE -- kana and kanji alike, half-width katakana included -- so it cannot tell
Chinese from Japanese, and it is not public (`LEDGER-HOT.md`: public names only).
This reads no language from a NAME, so the one-parser rule is not at stake.

===========================================================================
🚨 QUESTION 1b -- UNDER `--out` IT IS THE MIRRORED DIRECTORY, NOT THE VIDEO'S
===========================================================================

Measured at 4a and recorded as a defect for this step: with `--out` set the
previous run's file is in the **mirrored** directory. Look beside the video and
hato re-fetches the same episode every run -- and tsubasa then REFUSES the write
(*"already exists and is not one of the files this run accounted for"*), so the
run reports CONFIDENT, `write_failed`, and no file, for ever. `find()` therefore
takes the folder, and `hato/keep.py` computes it for both sides at once.

===========================================================================
⚠ QUESTION 2 -- THE TRACK READER HAS FOUR ANSWERS, NOT TWO
===========================================================================

`tsubasa.embedded_subs(video)` -- the public reader (RUNBOOK T4). ⛔ Never
`tsubasa.container` (`LEDGER-HOT.md`).

    UNREADABLE  `ok is False`; `.tracks` RAISES. ⭐ ERROR, **before any
                download** -- tsubasa's `sync()` reads the same container, so a
                download would only reach the same ERROR afterwards, and the
                network is metered. Its reason names the fix, verbatim.
    EMBEDDED    a TEXT track in the wanted language -> SKIP. Already there and
                already in sync (06 §6, RULED).
    NO_TRACK    no track at all -> SKIP, ⛔ never a refusal: tsubasa has nothing
                to time against until its audio path exists, and a refusal row
                would blacklist a good subtitle for ever.
    NO_USABLE   tracks, but none text and none bitmap -> the same SKIP. The
                rule's intent, not its letter.
    FETCH       anything else -- including a BITMAP track in the wanted language
                (06 §6: not a text subtitle; tsubasa times against it happily).

===========================================================================
⭐ THE LANGUAGE IN A NAME IS tsubasa's TO READ, NEVER THIS MODULE'S
===========================================================================

`<video>.Japanese.srt` read `und` on tsubasa 0.1.4 and was recorded here as a
defect hato must not fix itself -- a second reader would drift (`LEDGER-HOT.md`).
✅ tsubasa 0.1.5 learned the English display names, and
`test_existing.py::test_the_jellyfin_display_name_is_read_as_japanese` has held
it since 2026-09-17. ⚠ This note said "defect" until 2026-09-23, and it was
repeated as current from here rather than measured. The 9b read above is about
the TEXT of a file whose name says nothing; it reads no language from a name.
"""
import codecs
import os
import re

import tsubasa

#: What tsubasa answers for a name with no readable language.
UND = u"und"

#: ⭐ 9b -- the untagged sidecar that may be READ. Text subtitles only: a `.sub`,
#: `.sup` or `.idx` is an image or a binary index, and has no text to read.
TEXT_FORMATS = frozenset((u"srt", u"ass", u"ssa", u"vtt"))
#: How much of it is read -- and ⛔ A FILE BIGGER THAN THIS IS NOT JUDGED AT ALL.
#: 🚨 Part of a file is a SAMPLE, and a sample can lie: at 2 MB a 4.5 MB
#: `[CHS, JPN]` .ass read as Japanese from its first part -- its karaoke -- and
#: not Japanese whole (ADVERSARY 2026-09-23, 9b). Measured over 25,153 real
#: subtitles: 65 pass 2 MB (embedded fonts, mostly: a 2.4 MB .ass whose [Fonts]
#: came before its [Events] was never read at all), the largest 20.7 MB, ONE
#: past 16 -- which is fetched over, the direction ruled.
READ_LIMIT = 16 * 1024 * 1024
#: ⭐ THE THREE THRESHOLDS, each measured (module docstring, question 1c).
MIN_LINES = 100
MIN_LINE_SHARE = 0.4
MIN_KANA_SHARE = 0.55
#: ⛔ FULL-WIDTH kana and the long-vowel mark only -- see the module docstring on
#: Big5. `・` (U+30FB) is left out: Chinese text uses it as a name separator.
_KANA = re.compile(u"[\u3041-\u3096\u30a1-\u30fa\u30fc]")
_HAN = re.compile(u"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASS_TAG = re.compile(r"\{[^}]*\}")
_HTML_TAG = re.compile(r"<[^>]*>")
#: An `.ass` event in drawing mode is a vector shape, and its text is coordinates.
_DRAWING = re.compile(r"\{[^}]*\\p[1-9]")

#: `read_tracks().kind`. ⚠ Five, and 5a prints a different line for each.
UNREADABLE = u"unreadable"
EMBEDDED = u"embedded"
NO_TRACK = u"no-track"
NO_USABLE = u"no-usable-track"
FETCH = u"fetch"

#: A language tag hato will hand to tsubasa's reader. Kept narrow on purpose:
#: anything with a dot or a separator in it would be read as several tokens.
_TAG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


class LanguageUnknown(ValueError):
    u"""tsubasa's reader cannot resolve this language tag.

    ⛔ Loud, never a silent `und`. `und` matches an UNTAGGED subtitle, and
    `06-edge-cases.md` §6 rules that `<video>.srt` is *not* the target language
    -- so a tag that quietly became `und` would call every untagged sidecar in
    the library present and stop hato ever fetching.
    """


class Found(object):
    u"""The subtitle that is already there. `path` · `name` · `flags` ·
    `by_text` -- True when its NAME said no language and its text was read (9b),
    so whatever reports it can say which of the two answered."""

    __slots__ = ("path", "name", "flags", "by_text")

    def __init__(self, path, name, flags, by_text=False):
        self.path = path
        self.name = name
        self.flags = tuple(flags)
        self.by_text = by_text

    def __repr__(self):
        return "<Found %s>" % self.name


class Tracks(object):
    u"""What the container says. `kind` is one of the five constants above;
    `reason` is a sentence for a person, tsubasa's own when it could not read;
    `tracks` is every track it found (empty when it could not read)."""

    __slots__ = ("kind", "reason", "tracks")

    def __init__(self, kind, reason, tracks=()):
        self.kind = kind
        self.reason = reason
        self.tracks = tuple(tracks)

    @property
    def ok(self):
        return self.kind != UNREADABLE

    def __repr__(self):
        return "<Tracks %s, %d track(s)>" % (self.kind, len(self.tracks))


# ---------------------------------------------------------------------------
# the language, resolved by tsubasa and by nobody else
# ---------------------------------------------------------------------------

def language(tag):
    u"""A wanted language tag -> the code tsubasa resolves it to. -> text

        language(u"jpn") == language(u"ja-JP") == u"ja"

    ⛔ THE RESOLUTION IS TSUBASA'S, through its public `parse_subtitle_name` on
    a throwaway name. hato never maps a language tag itself: `hi` is Hindi, `fo`
    is Faroese and `sdh` is Southern Kurdish, and both reference implementations
    have a live bug in exactly this (`02-data-model.md`). One reader, one answer.
    """
    if not isinstance(tag, str) or not _TAG.match(tag.strip()):
        raise LanguageUnknown(
            u"%r is not a language tag hato can use -- give a 2- or 3-letter "
            u"code such as 'ja' or 'jpn'." % (tag,))
    tag = tag.strip()
    resolved = tsubasa.parse_subtitle_name(u"x.%s.srt" % tag).lang
    if resolved == UND and tag.lower() != UND:
        raise LanguageUnknown(
            u"tsubasa's subtitle-name reader does not recognise the language "
            u"tag %r -- it reads as 'und' (undetermined), and 'und' matches "
            u"every UNTAGGED subtitle in the library, which 06-edge-cases.md "
            u"§6 says is never the target language. Use 'ja'." % (tag,))
    return resolved


# ---------------------------------------------------------------------------
# question 1 -- is it already there?
# ---------------------------------------------------------------------------

class Presence(object):
    u"""Which videos already have their subtitle in a given folder.

    ⭐ ONE DIRECTORY LISTING PER FOLDER PER RUN, not one per video
    (`spec/00-INDEX.md` Rule 4: is every unit of work necessary?). A 1,700-file
    folder answered per video would be 1,700 listings of the same names, and the
    quiet re-run is the commonest thing hato does -- `02-data-model.md` prices it
    at *"N stats + one DB read"*.

    ⚠ `forget(folder)` after something lands there, so the cache can never be
    stale for a later video in the same run.
    """

    def __init__(self, lang):
        self.lang = language(lang)
        self._by_folder = {}

    def __repr__(self):
        return "<Presence lang=%s, %d folder(s) read>" % (self.lang, len(self._by_folder))

    def find(self, video, folder=None):
        u"""Is the wanted language already beside (or mirrored for) `video`?

        -> `Found`, or None. ⛔ A NAMED sidecar is found without opening
        anything. Only when none is there is one UNTAGGED file with the video's
        exact name read (9b, the module docstring's question 1c).

        `folder`
            🚨 the TARGET directory -- the video's own, or `--out`'s mirror of
            it. See the module note; missing it is a permanent never-fetch.
        """
        video = os.fspath(video)
        folder = os.fspath(folder) if folder is not None else os.path.dirname(video)
        stem = os.path.splitext(os.path.basename(video))[0]
        untagged = []
        for name in self._names(folder):
            side = _read(name)
            if side is None:
                continue
            # ⭐ NAMED EXACTLY FOR THE VIDEO IS UNTAGGED, whatever the name parses
            # to. `Show.S01E01.JP.srt` beside `Show.S01E01.JP.mkv` is the video's
            # own name plus an extension -- but once tsubasa read `.jp` (9c) it
            # parsed as a JAPANESE tag on the stem `Show.S01E01`: not the video's
            # named sidecar, not untagged, and fetched over (ADVERSARY 2026-09-23,
            # 9b x 9c). ⚠ No language is read here -- only whether the name IS
            # the video's name; tsubasa still reads every tag (`LEDGER-HOT.md`).
            exact = os.path.splitext(name)[0] == stem
            if not exact:
                if side.stem != stem:
                    continue
                if side.lang == self.lang:
                    if u"forced" in side.flags:
                        # 06 §6: a forced sub is not a full sub. ⚠ The fetched file is
                        # `<stem>.ja.<ext>` and this one `<stem>.ja.forced.<ext>`, so
                        # they are different names and neither disturbs the other.
                        continue
                    return Found(os.path.join(folder, name), name, side.flags)
            # ⚠ `not side.flags`: a flag with no language to its left does not
            # parse as a flag, so this is the plain `<stem>.<ext>` (or `.und.`).
            if (exact or (side.lang == UND and not side.flags)) and side.ext in TEXT_FORMATS:
                untagged.append(name)
        if self.lang != u"ja":
            return None                    # ⛔ only Japanese text is ever judged
        for name in sorted(untagged):
            path = os.path.join(folder, name)
            if reads_as_japanese(path):
                return Found(path, name, (), by_text=True)
        return None

    def forget(self, folder):
        u"""Drop one folder's cached listing -- after a file landed in it."""
        self._by_folder.pop(_folder_key(folder), None)

    def _names(self, folder):
        key = _folder_key(folder)
        names = self._by_folder.get(key)
        if names is None:
            names = self._by_folder[key] = _listing(folder)
        return names


def _folder_key(folder):
    return os.path.normcase(os.path.abspath(os.fspath(folder)))


def _listing(folder):
    u"""Every FILE name directly in `folder`. -> tuple

    ⚠ A folder that is not there is an empty listing, not an error: under
    `--out` the mirrored directory does not exist until the first file lands in
    it, and *"nothing is there yet"* is the right answer, not a crash.
    """
    try:
        with os.scandir(folder) as entries:
            return tuple(e.name for e in entries if not e.is_dir())
    except OSError:
        return ()


def _read(name):
    u"""tsubasa's reading of a sidecar name, or None when it is not one.

    ⚠ Everything in a media folder goes through here -- `.mkv`, `.nfo`, a
    stray `.txt`. A name tsubasa cannot take apart is simply not a sidecar.
    """
    try:
        return tsubasa.parse_subtitle_name(name)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ⭐ question 1c -- does an untagged subtitle's TEXT say Japanese? (9b)
# ---------------------------------------------------------------------------

def reads_as_japanese(path):
    u"""Is this subtitle file, beyond reasonable doubt, Japanese dialogue? -> bool

    ⭐ FALSE IS THE SAFE ANSWER and every doubt returns it: the caller then
    fetches, exactly as hato did before this existed. True needs all three
    measured thresholds (the module docstring, question 1c).

    ⚠ Reads at most `READ_LIMIT` bytes and writes nothing -- and a file bigger
    than that is a doubt: part of a file is judged never (see `READ_LIMIT`).
    """
    try:
        with open(os.fspath(path), "rb") as handle:
            data = handle.read(READ_LIMIT + 1)
    except OSError:
        return False
    truncated = len(data) > READ_LIMIT
    if truncated:
        return False
    text = _decode(data)
    if text is None:
        return False
    lines = _dialogue(text, os.path.splitext(os.fspath(path))[1][1:].lower())
    if len(lines) < MIN_LINES:
        return False
    with_kana = sum(1 for line in lines if _KANA.search(line))
    kana = sum(len(_KANA.findall(line)) for line in lines)
    han = sum(len(_HAN.findall(line)) for line in lines)
    return (with_kana >= MIN_LINE_SHARE * len(lines)
            and kana >= MIN_KANA_SHARE * (kana + han))


def _decode(data):
    u"""The text, or None when no encoding reads it strictly.

    ⭐ A byte-order mark decides first; then UTF-8, then Shift-JIS (cp932), the
    two a Japanese subtitle is actually found in. ⛔ Never `errors="replace"`:
    a guessed decoding is how a Chinese file would come to look Japanese.
    ⚠ Always a WHOLE file now -- a part is never judged -- so no character can
    arrive cut in two.
    """
    if data.startswith(codecs.BOM_UTF8):
        candidates = (u"utf-8-sig",)
    elif data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        candidates = (u"utf-16",)
    else:
        candidates = (u"utf-8", u"cp932")
    for encoding in candidates:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _dialogue(text, ext):
    u"""The lines a person would read, tags and timings stripped. -> [text]

    `.ass`/`.ssa`: the text field of each `Dialogue:` event, drawings skipped.
    Anything else: every line that is not blank, a cue number, a timing or a
    WebVTT header.
    """
    out = []
    if ext in (u"ass", u"ssa"):
        for raw in text.splitlines():
            if not raw[:9].lower().startswith(u"dialogue:"):
                continue
            parts = raw.split(u",", 9)
            if len(parts) < 10 or _DRAWING.search(parts[9]):
                continue
            line = _ASS_TAG.sub(u"", parts[9])
            line = line.replace(u"\\N", u" ").replace(u"\\n", u" ").replace(u"\\h", u" ")
            if line.strip():
                out.append(line.strip())
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.isdigit() or u"-->" in line:
            continue
        if line.upper().startswith((u"WEBVTT", u"NOTE", u"STYLE", u"REGION")):
            continue
        line = _ASS_TAG.sub(u"", _HTML_TAG.sub(u"", line)).strip()
        if line:
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# question 2 -- can this video be synced at all?
# ---------------------------------------------------------------------------

def read_tracks(video, lang, reader=None):
    u"""What is inside the container. -> `Tracks`

    `lang`
        the wanted language, resolved through `language()`.
    `reader`
        ⛔ A SEAM, the same shape as `port.sync(engine=)`: the real
        `tsubasa.embedded_subs` is the default, so it is never *code that never
        runs here*, and a suite that must decide what a container holds passes
        its own. ⚠ Whatever it returns must answer `.ok` BEFORE `.tracks` --
        tsubasa's own `.tracks` raises when `ok` is False, deliberately
        (*"an unread video is not a video with no tracks"*).
    """
    wanted = language(lang)
    reader = tsubasa.embedded_subs if reader is None else reader
    answer = reader(os.fspath(video))
    if not answer.ok:
        # ⭐ ERROR, before any download. tsubasa's reason names the fix (it is
        # usually "install ffmpeg"), so it is carried verbatim rather than
        # paraphrased -- 03-permissions.md §The hand-back path.
        return Tracks(UNREADABLE, answer.reason or
                      u"the container could not be read, and tsubasa gave no "
                      u"reason -- which is itself the fault")
    tracks = tuple(answer.tracks)
    for track in tracks:
        if track.text and track.lang == wanted:
            return Tracks(EMBEDDED,
                          u"an embedded %s text track is already there (track %s, %s) -- "
                          u"already in sync, so nothing was fetched"
                          % (wanted, track.index, track.codec), tracks)
    if not tracks:
        return Tracks(NO_TRACK,
                      u"no subtitle track in the video -- can't sync yet",
                      tracks)
    if not any(track.text or track.bitmap for track in tracks):
        return Tracks(NO_USABLE,
                      u"no usable subtitle track -- can't sync yet (%d track(s), "
                      u"none tsubasa can time against: %s)"
                      % (len(tracks), u", ".join(sorted(set(
                          t.codec or u"unknown codec" for t in tracks)))),
                      tracks)
    return Tracks(FETCH, u"", tracks)


__all__ = ["UND", "UNREADABLE", "EMBEDDED", "NO_TRACK", "NO_USABLE", "FETCH",
           "TEXT_FORMATS", "READ_LIMIT", "MIN_LINES", "MIN_LINE_SHARE",
           "MIN_KANA_SHARE", "LanguageUnknown", "Found", "Tracks", "language",
           "Presence", "reads_as_japanese", "read_tracks"]
