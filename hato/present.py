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

⭐ SO: PRESENT means the canonical sidecar, BY NAME, and nothing else -- a file
**in the target directory** whose stem equals the video's basename, whose
language resolves to the wanted one, and which is **not forced**
(`06-edge-cases.md` §6: *a forced sub is not a full sub*). That is the one form
Plex, Jellyfin and Emby all load. ⛔ Nothing is opened.

⚠ THE ASYMMETRY THAT DECIDES EVERY CLOSE CALL. A false *present* is a permanent,
silent never-fetch. A false *absent* is one unmetered download and a visible
duplicate that is never overwritten (tsubasa's explicit path supersedes nothing).
So an un-renamed `[Group] Show - 04 [JPN].ja.ass` does **not** count as present,
and the fetched copy is written beside it.

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
🚨 A MEASURED SPEC DEFECT THIS MODULE CANNOT FIX, AND MUST NOT
===========================================================================

`06-edge-cases.md` §6 says `<video>.Japanese.srt` is recognised -- *"Jellyfin and
Emby both document it"*. Measured here on tsubasa 0.1.4, in three casings:
`parse_subtitle_name("Show - 01.Japanese.srt").lang` is **`und`**, and the stem
comes back as `Show - 01.Japanese`. So such a sidecar reads as ABSENT and hato
fetches beside it.

⛔ hato does not fix it: the language reader lives in tsubasa and a second one
here would drift (`LEDGER-HOT.md`). It is recorded in `spec/06-edge-cases.md`,
and it lands on the SAFE side of the asymmetry above -- a duplicate, never a
silent never-fetch.
"""
import os
import re

import tsubasa

#: What tsubasa answers for a name with no readable language.
UND = u"und"

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
    u"""The subtitle that is already there. `path` · `name` · `flags`."""

    __slots__ = ("path", "name", "flags")

    def __init__(self, path, name, flags):
        self.path = path
        self.name = name
        self.flags = tuple(flags)

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

        -> `Found`, or None. ⛔ Opens nothing: names only.

        `folder`
            🚨 the TARGET directory -- the video's own, or `--out`'s mirror of
            it. See the module note; missing it is a permanent never-fetch.
        """
        video = os.fspath(video)
        folder = os.fspath(folder) if folder is not None else os.path.dirname(video)
        stem = os.path.splitext(os.path.basename(video))[0]
        for name in self._names(folder):
            side = _read(name)
            if side is None or side.lang != self.lang:
                continue
            if side.stem != stem:
                continue
            if u"forced" in side.flags:
                # 06 §6: a forced sub is not a full sub. ⚠ The fetched file is
                # `<stem>.ja.<ext>` and this one `<stem>.ja.forced.<ext>`, so
                # they are different names and neither disturbs the other.
                continue
            return Found(os.path.join(folder, name), name, side.flags)
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
           "LanguageUnknown", "Found", "Tracks", "language", "Presence",
           "read_tracks"]
