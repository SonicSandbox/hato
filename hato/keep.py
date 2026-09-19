# -*- coding: utf-8 -*-
u"""
The hand-off to tsubasa, and the original hato keeps (RUNBOOK 4c).

    keep.check_subs_dir(subs_dir, folders)      ⛔ config ERROR at startup
    keep.check_out_dir(out, folders)            ⛔ the same, and for the same reason
    folder = keep.target_dir(video, root, out)  where the finished file goes
    name   = keep.download_name(jimaku_name, u"ja")
    kept   = keep.keep_original(blob, subs_dir, entry_name, name)

⭐ hato WRITES NOTHING INTO A MEDIA FOLDER. Ruled 2026-09-17 (Sonic): tsubasa
writes the synced file, hato keeps the original it was made from. The only
filesystem operation a media folder ever sees from a hato run is tsubasa's one
atomic write of a finished file (`03-permissions.md` Whitelist 1). Everything in
this module writes under `subs_dir`, which lives in hato's own per-user root.

===========================================================================
🚨 THE ORIGINAL CARRIES `.ja` BEFORE ITS EXTENSION. MEASURED, TWICE.
===========================================================================

`LEDGER-HOT.md`: tsubasa's output name is `<video-basename>.<lang>[.flags].<ext>`
with the language **resolved from the original's own name**, and it writes NO
tag at all for `und`. So jimaku's `[Haruhana] … [JPN].ass` handed over as-is
becomes `<video>.ass`; `unpaired(lang="ja")` then reads the video as having no
Japanese subtitle, and **every later run fetches again**.

Re-measured here against tsubasa 0.1.4, every real shape on entry 11446::

    [Haruhana] … [JPN].ass            lang=und   ->  .ja.ass  lang=ja  flags=[]
    [Nekomoe…] … [CHS, JPN].ass       lang=und   ->  .ja.ass  lang=ja  flags=[]
    ….WEBRip.Amazon.ja-jp[sdh].srt    lang=ja    ->  .ja.srt  lang=ja  flags=[]
    ….WEBRip.Netflix.ja[cc].srt       lang=ja    ->  .ja.srt  lang=ja  flags=[]
    Show - 04.ja.forced.srt           forced     ->  .ja.srt  lang=ja  flags=[]

⭐ The last row is the one worth reading twice: appending `.ja` pushes jimaku's
own tag into the STEM, so a `forced` or `sdh` flag on the source can never ride
into the name tsubasa writes -- and a `.forced` output would have been read as
*not present* by `hato/present.py` and re-fetched for ever. `download_name`
asserts the round trip rather than trusting it.

===========================================================================
🚨 TEMP-PLUS-RENAME, AND ⛔ NEVER OVERWRITE
===========================================================================

`open(path,'w')` truncates the moment it opens; a raise after that leaves zero
bytes, and on 2026-09-07 that destroyed `tsubasa/spec/RUNBOOK.md`
(`LEDGER-HOT.md`). Every byte here is written to a temp file in the destination
folder and renamed into place, and the destination is checked immediately
before -- the same shape `hato/archives.py` uses.

⛔ A kept original is NEVER deleted and NEVER overwritten (ruled 2026-09-17).
Same name, same bytes -> the one on disk is reused. Same name, different bytes
-> the new one is kept under a short content-hash suffix and both stay
(`06-edge-cases.md` §8).

===========================================================================
⛔ NEITHER `subs_dir` NOR `--out` MAY SIT INSIDE A SCANNED FOLDER -- MEASURED
===========================================================================

Probe, tsubasa 0.1.4, `scan(videos=<tree>)` over::

    <tree>/S2/Show - 01.mkv
    <tree>/subs/Entry Name/[G] Show - 01 [JPN].ja.ass

`unpaired(lang="ja")` came back **empty**: the kept original in a sibling folder
was offered as the video's subtitle. A `tsubasa <folder>` run over that tree
could then supersede hato's own kept originals. Refused at startup, by name,
before anything is scanned.

🚨 AND `--out` IS THE SAME TRAP, WORSE. MEASURED 2026-09-17, the same probe over::

    <tree>/S2/frieren S2 - 01.mkv
    <tree>/Subs/S2/frieren S2 - 01.ja.ass          # hato's own output, --out <tree>/Subs

`unpaired(lang="ja")` is **empty** again -- and here the mirrored file's stem
already EQUALS the video's basename, so a plain `tsubasa <tree>` run reads it as
that video's subtitle. The adversarial pass took it the last step and ran the
supersede: `hato D:\\Anime --out D:\\Anime\\Subs`, then `tsubasa D:\\Anime`, gave
`superseded = [...\\Subs\\frieren S2 - 01.ja.ass]` -- hato's finished file moved to
the trash by a tool the person ran for an unrelated reason. hato refused this for
`subs_dir` from the first build and accepted it for `--out`, which is the same
rule with one of its two doors left open. `check_out_dir` closes it, at startup,
before a single byte is written.
"""
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import tsubasa

from hato import cache as _cache
from hato.present import language

#: The one temp prefix anything here writes under, so a killed run's leftovers
#: are recognisable. ⚠ Inside `subs_dir` only -- never a media folder.
TEMP_PREFIX = u".hato-keep-"


class InsideScan(ValueError):
    u"""A folder hato puts files in is inside a folder this run would scan (or
    the other way round). ⛔ A config ERROR at startup, never a warning.

    ⚠ ONE BASE FOR BOTH DOORS. `subs_dir` had this rule from the first build and
    `--out` did not, so the second was reachable for months while the first was
    refused by name. A caller catching the base can never again close one door
    and leave the other open.
    """


class SubsDirInsideScan(InsideScan):
    u"""The kept originals would be discovered as candidates for the videos
    beside them."""


class OutDirInsideScan(InsideScan):
    u"""🚨 `--out` points inside a scanned folder, so hato's own finished files
    are in the tree a `tsubasa <folder>` run walks -- and their stems already
    equal the videos' basenames, which is what makes them supersede-able."""


class KeptOriginalProblem(OSError):
    u"""A kept original could not be placed. Carries the real reason."""


class UntaggedOriginal(ValueError):
    u"""The name composed for an original does not read back as the wanted
    language. 🚨 Handing it over would make tsubasa write an untagged file and
    every later run fetch again -- so it raises instead."""


# ---------------------------------------------------------------------------
# ⛔ the startup refusal
# ---------------------------------------------------------------------------

def _norm(path):
    return os.path.normcase(os.path.abspath(os.fspath(path))).rstrip(os.sep) or os.sep


def inside(child, parent):
    u"""Is `child` the same folder as `parent`, or under it? -> bool

    ⚠ Compared as normalised absolute text, never through `commonpath` --
    `commonpath` RAISES on two different Windows drives, and *"D: is not under
    C:"* is an answer, not an error.
    """
    child, parent = _norm(child), _norm(parent)
    return child == parent or child.startswith(parent + os.sep)


def check_subs_dir(subs_dir, folders):
    u"""⛔ Raise `SubsDirInsideScan` if the kept originals would be scanned.

    Both directions: `subs_dir` under a scanned folder, and a scanned folder
    under `subs_dir`. Either way tsubasa's walk reaches the originals -- see the
    measurement in the module note.
    """
    for folder in folders:
        if inside(subs_dir, folder):
            raise SubsDirInsideScan(
                u"subs_dir %s is inside the folder %s, which this run scans. The "
                u"kept originals would be discovered as candidates for the videos "
                u"beside them, and a `tsubasa <folder>` run over that tree could "
                u"supersede them (measured: an original in a sibling folder was "
                u"offered as a video's subtitle). Point --subs-dir somewhere "
                u"outside every scanned folder."
                % (_show(subs_dir), _show(folder)))
        if inside(folder, subs_dir):
            raise SubsDirInsideScan(
                u"the folder %s that this run scans is inside subs_dir %s -- the "
                u"kept originals and the videos would share a tree, with the same "
                u"result. Point --subs-dir somewhere else."
                % (_show(folder), _show(subs_dir)))


def check_out_dir(out, folders):
    u"""⛔ Raise `OutDirInsideScan` if hato's own output would land in the walk.

    🚨 THE SAME RULE AS `check_subs_dir`, AND IT WAS MISSING. `_Run.go()` asked
    only about `subs_dir`, so `hato D:\\Anime --out D:\\Anime\\Subs` was accepted
    and a later `tsubasa D:\\Anime` superseded hato's finished file (module note,
    measured). Both directions, for the same reason as `subs_dir`: what matters
    is whether one tree walk reaches both, not which path was typed.

    `out` of None is *beside the video*, which cannot be "inside a scanned
    folder" in any way that is a mistake -- it is the whole point.
    """
    if not out:
        return
    for folder in folders:
        if inside(out, folder):
            raise OutDirInsideScan(
                u"--out %s is inside the folder %s, which this run scans. The "
                u"finished subtitles hato writes there carry the videos' own "
                u"basenames, so a later `tsubasa %s` run reads them as those "
                u"videos' subtitles and can move them to the trash (measured: "
                u"`superseded` named hato's own output). Point --out somewhere "
                u"outside every scanned folder -- or drop it, and the files are "
                u"written beside their videos, which tsubasa never supersedes."
                % (_show(out), _show(folder), _show(folder)))
        if inside(folder, out):
            raise OutDirInsideScan(
                u"the folder %s that this run scans is inside --out %s -- the "
                u"finished subtitles and the videos would share a tree, with the "
                u"same result. Point --out somewhere else."
                % (_show(folder), _show(out)))


def _show(path):
    return str(Path(os.fspath(path)))


# ---------------------------------------------------------------------------
# where the finished file goes -- ONE answer, used by BOTH sides
# ---------------------------------------------------------------------------

def target_dir(video, root, out=None):
    u"""Where tsubasa will put the finished file. -> Path

    🚨 THE PRESENT-CHECK AND THE WRITE MUST ASK THE SAME FUNCTION. With `--out`
    set, the previous run's file is in the MIRRORED directory; a present-check
    that looked beside the video would never see it, hato would re-fetch the
    same episode every run, and tsubasa would refuse the write for ever
    (measured at 4a). One function, so the two cannot disagree.

    `out` of None means beside the video, and then `root` is not read at all.
    """
    if not out:
        return Path(os.path.dirname(os.path.abspath(os.fspath(video))))
    return mirrored_dir(video, root, out)


def mirrored_dir(video, root, out):
    u"""`--out` mirrors the source tree, it never flattens. -> Path

        ~/Anime/Katainaka S2/ep01.mkv  --out ~/Subs  ->  ~/Subs/Katainaka S2/

    ⛔ Flattening would collide the moment two shows both have an `ep01`
    (`05-interface.md`).

    ⚠ SPEC AMBIGUITY, RECORDED IN `05-interface.md` AND DECIDED HERE. That one
    example does not say whether `~/Anime` or `~/Anime/Katainaka S2` was the
    scanned root, and the two readings give different rules. The rule built is
    **the tree BELOW the scanned root**, `out / relpath(video_dir, root)`,
    because the other reading (keeping the root's own folder name) collides on
    the documented config: `folders = ["D:/Anime", "E:/Downloads/Anime"]` both
    end in `Anime`, so every show of the second would land on the first's.
    Under this rule they merge per show, which is what a person means by
    *"mirroring"*.
    """
    video_dir = os.path.dirname(os.path.abspath(os.fspath(video)))
    root_dir = os.path.abspath(os.fspath(root))
    if os.path.isfile(root_dir):
        root_dir = os.path.dirname(root_dir)
    if not inside(video_dir, root_dir):
        # ⛔ Loud. A relpath starting `..` would put the output OUTSIDE --out,
        # which is the one place a `--out` run is allowed to write.
        raise ValueError(
            u"%s is not inside the scanned folder %s, so its mirrored directory "
            u"under %s cannot be worked out. This is a caller mistake: pass the "
            u"root the video was discovered under."
            % (_show(video_dir), _show(root_dir), _show(out)))
    relative = os.path.relpath(video_dir, root_dir)
    out = Path(os.path.abspath(os.fspath(out)))
    return out if relative == os.curdir else out / relative


# ---------------------------------------------------------------------------
# 🚨 the name the original is handed over under
# ---------------------------------------------------------------------------

def download_name(jimaku_name, lang):
    u"""jimaku's filename -> `<jimaku stem>.<lang>.<ext>`. -> text

    🚨 The whole point of this module. See the measured table in the module
    note: untagged, tsubasa writes `<video>.<ext>`, `unpaired(lang="ja")` reads
    the video as unsubtitled, and every later run fetches again.

    ⭐ THE ROUND TRIP IS ASSERTED, NOT ASSUMED. The composed name is read back
    through tsubasa's own `parse_subtitle_name`, and a reading that is not the
    wanted language raises `UntaggedOriginal`. A rule that can be a constraint
    is one (`doctrine/robustness`); this one has already been got wrong twice.
    """
    wanted = language(lang)
    name = os.path.basename(os.fspath(jimaku_name))
    stem, ext = os.path.splitext(name)
    if not ext or not stem:
        raise UntaggedOriginal(
            u"%r has no stem and extension to put a language tag between, so it "
            u"cannot be handed to tsubasa under a tagged name." % (name,))
    made = u"%s.%s%s" % (stem, wanted, ext)
    back = tsubasa.parse_subtitle_name(made)
    if back.lang != wanted:
        raise UntaggedOriginal(
            u"the original would be handed over as %r, which tsubasa reads as "
            u"language %r and not %r. It would then write the synced file with "
            u"the wrong tag -- or none at all -- and every later run would fetch "
            u"this episode again (LEDGER-HOT.md, measured)."
            % (made, back.lang, wanted))
    return made


# ---------------------------------------------------------------------------
# ⛔ the kept original -- never deleted, never overwritten
# ---------------------------------------------------------------------------

def entry_folder(subs_dir, entry_name):
    u"""`subs_dir/<entry name>` -- the folder one show's originals live in.

    ⚠ Through `cache.safe_name`: a jimaku entry name is uploader-controlled text
    and carries `:` and full-width characters. Mapped to their twins, never
    dropped -- dropping changes the shape of a name.
    """
    return Path(os.fspath(subs_dir)) / _cache.safe_name(str(entry_name) or u"unknown entry")


def keep_original(source, subs_dir, entry_name, name):
    u"""Put the original a synced file was made from into `subs_dir`. -> Path

    ⚠ WRITE FIRST, KEEP SECOND (RUNBOOK 4c). Called only after tsubasa reports a
    file it really wrote, so `subs_dir` holds exactly the originals that were
    USED -- a refused candidate stays in the disposable cache with its identity
    recorded, and is never fetched again.

    ⛔ COPIED, never moved. The cache blob is disposable and may be cleared
    whenever; a move would be one operation with two chances to lose the only
    copy, and hato deletes nothing.

    Same name and the same bytes -> the file already there is reused, and
    nothing is written. Same name, different bytes -> a short content-hash
    suffix, and BOTH are kept (`06-edge-cases.md` §8).
    """
    source = os.fspath(source)
    folder = entry_folder(subs_dir, entry_name)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise KeptOriginalProblem(
            u"the kept-originals folder %s could not be made (%s), so the "
            u"original of the file just written was not kept. The synced file "
            u"is fine; a later run would download this candidate again."
            % (_show(folder), exc))

    digest = _cache.file_hash(source)
    for candidate in _names(name, digest, folder):
        target = folder / candidate
        if target.exists():
            if target.is_file() and _cache.file_hash(str(target)) == digest:
                return target           # ⭐ the same bytes are already kept
            continue                    # ⛔ different bytes: keep both
        _place(source, target)
        return target
    raise KeptOriginalProblem(
        u"every name tried for the original %r in %s is taken by different "
        u"content -- nothing was overwritten." % (name, _show(folder)))


def _names(name, digest, folder):
    u"""The names to try, in order: the plain one, then content-hash suffixes.

    ⚠ The suffix comes from the CONTENT, so the same bytes always land on the
    same alternative name and a re-run reuses it instead of piling up copies.
    """
    budget = _budget(folder)
    yield _cache.safe_name(name, max_len=budget)
    stem, ext = _split(name)
    for n in range(16):
        tag = digest[:8] if n == 0 else hashlib.sha256(
            (u"%s\x00%d" % (digest, n)).encode("utf-8")).hexdigest()[:8]
        yield _cache.safe_name(u"%s~%s%s" % (stem, tag, ext), max_len=budget)


def _split(name):
    u"""(stem, ext) keeping `.ja.ass` and `.ja.forced.srt` whole -- the same
    split `cache.safe_name` uses when it has to truncate."""
    return _cache._split_ext(name)


def _budget(folder):
    u"""The longest filename that keeps folder + name inside MAX_PATH."""
    budget = _cache.NAME_MAX
    if os.name == "nt":
        units = len(str(folder).encode("utf-16-le", "surrogatepass")) // 2
        budget = min(budget, _cache.WIN_PATH_MAX - units - 1)
    return max(budget, _cache.NAME_MIN)


def _place(source, target):
    u"""🚨 Temp-plus-rename into the destination's OWN folder, and ⛔ never over
    a file that is there.

    The temp file is a sibling so the rename is atomic on one volume, and the
    destination is re-checked immediately before it -- the shape
    `hato/archives.py` uses for every member it writes.
    """
    folder = str(target.parent)
    handle, temporary = tempfile.mkstemp(prefix=TEMP_PREFIX, dir=folder)
    try:
        with os.fdopen(handle, "wb") as out:
            with open(source, "rb") as src:
                # ⛔ THE BYTES AS THEY ARE, never decoded and never re-encoded
                # (`LEDGER-HOT.md`): Shift-JIS stays Shift-JIS, a BOM stays, and
                # CRLF stays. A Shift-JIS caption read with errors="replace" had
                # all 346 cues turn to U+FFFD while the ASCII timestamps survived.
                shutil.copyfileobj(src, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if os.path.lexists(str(target)):
            raise FileExistsError(17, u"refusing to overwrite a kept original", str(target))
        os.replace(temporary, str(target))
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


#: ⭐ The subfolder hato drops copies into, inside the directory a person
#: chooses. Sonic: *"it will be in an Hato folder... if I provide the directory
#: for downloads, then it would auto-insert it into the Hato directory there."*
#: ⛔ NEVER the chosen directory itself: somebody will point this at Downloads,
#: and a tool that sprays subtitles loose into Downloads is a tool they turn
#: off. One folder, one owner, trivially deletable.
SURASURA_FOLDER = u"Hato"


def surasura_copy(written, surasura_dir):
    u"""Drop a copy of a finished subtitle where surasura will find it.

    -> the path written, or None when the integration is off.

    ⭐ THE INTEGRATION (RUNBOOK 7h) -- github.com/SonicSandbox/surasura. A
    COPY, and only of a subtitle hato has just aligned: the file beside the
    video stays exactly where tsubasa put it, because that is the one a player
    loads.

    ⚠ IT OVERWRITES, DELIBERATELY, and that is the opposite of every other
    write in this module. `keep_original` and `port._copy_atomically` refuse to
    touch a file that is already there because those live in the USER'S
    folders. This one owns its folder: a re-aligned subtitle is a better answer
    than the one dropped last week, and refusing would quietly leave the stale
    copy as the one surasura reads.

    🚨 TEMP-PLUS-RENAME even so. `open(path,'w')` truncates on open, and a
    raise after that leaves a zero-byte subtitle -- which surasura would read
    as an empty one rather than as a failure.
    """
    if not surasura_dir or not written:
        return None                          # ⛔ empty means off
    source = Path(written)
    if not source.is_file():
        return None
    folder = Path(surasura_dir) / SURASURA_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    handle, temporary = tempfile.mkstemp(prefix=TEMP_PREFIX, dir=str(folder))
    os.close(handle)
    try:
        shutil.copyfile(str(source), temporary)
        os.replace(temporary, str(target))    # ⭐ replaces; see the note above
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    return target


__all__ = ["SURASURA_FOLDER", "TEMP_PREFIX", "InsideScan", "SubsDirInsideScan",
           "OutDirInsideScan",
           "KeptOriginalProblem", "UntaggedOriginal", "inside", "check_subs_dir",
           "check_out_dir", "target_dir", "mirrored_dir", "download_name",
           "entry_folder", "keep_original", "surasura_copy"]
