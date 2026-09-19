# -*- coding: utf-8 -*-
u"""
A REAL video, built in a temp dir, for the checks that must not be told what a
video is (spec/07-test-plan.md §*A real video, for the tsubasa contract test*).

    from tests import _media            # or: import _media   (tests/ is on sys.path)

    m = _media.build(tmp_path)
    m.video       -> <root>/media/<stem>.mkv    testsrc + silence + a TEXT sub track
    m.subtitle    -> <root>/cache/<stem>.ja.srt the "download": the SAME cues, shifted
    m.starts      -> the reference cue starts, in seconds
    m.shift       -> how far the download is out

⭐ WHY A REAL ONE. `07-test-plan.md`: *the `sync()` port must be exercised
against the REAL `tsubasa.sync()` by at least one contract test -- a port tested
only through its stub proves the stub.* The real engine reads the container,
finds the text track, and aligns against its cue timing; nothing hand-built can
stand in for that, because the thing under test is the hand-off itself.

===========================================================================
⛔ NO MEDIA IS EVER WRITTEN INSIDE TheForge. STRUCTURAL, NOT REMEMBERED.
===========================================================================

The vault auto-commits every few minutes and git history has no undo, so a
300 KB `.mkv` dropped in `tests/` is committed before anyone notices.
`build()` REFUSES a destination inside the vault (`OutsideTheVault`) rather
than trusting each caller to pass a temp path -- `doctrine/robustness`: a rule
that relies on remembering will be forgotten. Called with no destination it
makes its own under `tempfile.gettempdir()` and removes it at exit.

===========================================================================
⚠ ENOUGH CUES FOR A VERDICT. A ONE-CUE FILE IS REFUSED, CORRECTLY.
===========================================================================

tsubasa needs `MIN_ALIGNABLE_CUES` to align at all and TWO 120 s buckets before
`runtime_check` can say `held`, so the default is **75 cues, one every 4 s over
310 s**. MEASURED 2026-09-17 on that default: `CONFIDENT`, word `locked`,
`match_rate` 1.0, `runtime_check` `held`, aligned against
*track 2 (S_TEXT/UTF8, jpn, 75 cues)*. The video is 160x120 at 5 fps: **302 KB,
0.7 s to build, and the whole real sync takes 0.1 s.**

⚠ ffmpeg IS RESOLVED FROM `hato.config.json` (`media.ffmpegRelative`), never
hardcoded, and NEVER from shipping code -- a released hato must not know where
this vault keeps its tools (RUNBOOK 0a). ⛔ A missing ffmpeg is an ERROR here,
not a skip: a contract test that quietly does not run is the exact failure it
exists to prevent.
"""
import atexit
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # the hato project

#: Cue geometry. ⚠ Changing these changes what the verdict can say -- see the
#: measured numbers above before touching them.
CUES = 75
FIRST = 5.0
EVERY = 4.0
SECONDS = 2.0
SHIFT = 7.25
SLACK = 5.0             # video runs a little past the last cue's end


class FfmpegMissing(RuntimeError):
    u"""⛔ Loud, never a skip -- IN THE VAULT. See `ffmpeg()`.

    ⚠ This docstring read *"Loud, never a skip"* without qualification until
    2026-09-17, and outside the vault that was not a rule, it was twelve red
    CI jobs. `ffmpeg()` now raises this only where the bundled copy is
    supposed to exist; elsewhere it falls back to PATH and then skips.
    """


class OutsideTheVault(RuntimeError):
    u"""A destination inside TheForge was refused. See the module note."""


def vault_root():
    u"""The Obsidian vault this project lives in, or the project itself.

    ⚠ Found by walking up for `.obsidian` rather than counting `parents[3]`,
    so moving the project one level does not silently disarm the guard below.
    """
    for folder in [ROOT] + list(ROOT.parents):
        if (folder / ".obsidian").is_dir():
            return folder
    return ROOT


VAULT = vault_root()


def ffmpeg():
    u"""An ffmpeg to build real videos with. -> str

    Three places, in order, and the ORDER is the whole design:

      1. the path `hato.config.json` names (`media.ffmpegRelative`)
      2. ⛔ IN THE VAULT, stop here and RAISE -- never skip
      3. outside the vault: `ffmpeg` on PATH, then skip

    🚨 WHY STEP 2 EXISTS. `spec/07-test-plan.md` requires the tsubasa contract
    test to run, not to be skipped: on Sonic's machine ffmpeg is bundled at
    `Workshop/media-kit/bin/` and is deliberately NOT on PATH, so "ffmpeg is
    not installed" is the wrong conclusion there and a skip would quietly
    retire the only check that drives the real engine.

    🚨 WHY STEP 3 EXISTS, AND IT WAS MEASURED, NOT ANTICIPATED. The public
    repo's FIRST CI run went red on all twelve matrix jobs -- 18 of each job's
    22 failures were this one function, raising because
    `../media-kit/bin/ffmpeg.exe` resolved to `D:\\a\\hato\\media-kit\\...` on a
    GitHub runner. The path is relative to `hato.config.json`, which is correct
    in the vault and meaningless anywhere else. ⭐ A hosted runner usually HAS
    ffmpeg on PATH, so falling back gives real coverage rather than a skip --
    and a skip is only reached when neither place has one.

    ⛔ The vault branch keeps its teeth: there, the configured path exists, so
    step 1 returns and steps 2-3 never run. If it ever goes missing IN the
    vault that is still a hard failure, which is what step 2 is for.
    """
    with io.open(str(ROOT / "hato.config.json"), encoding="utf-8") as handle:
        relative = json.load(handle)["media"]["ffmpegRelative"]
    path = (ROOT / relative).resolve()
    if path.is_file():
        return str(path)

    in_the_vault = VAULT != ROOT
    if in_the_vault:
        raise FfmpegMissing(
            "hato.config.json names media.ffmpegRelative = %r, which resolves "
            "to %s and is not there. This IS the vault (%s), where ffmpeg is "
            "bundled and deliberately off PATH, so the contract test builds a "
            "real video with it and must not be skipped "
            "(spec/07-test-plan.md); point that key at an ffmpeg."
            % (relative, path, VAULT))

    found = shutil.which("ffmpeg")
    if found:
        return found

    import pytest                      # local: keeps this helper importable alone
    pytest.skip(
        "no ffmpeg: %s names media.ffmpegRelative = %r (-> %s, absent) and "
        "there is none on PATH. This tree is not the vault, so the bundled "
        "copy does not exist here. Install ffmpeg to run the tsubasa contract "
        "checks." % (ROOT / "hato.config.json", relative, path))


# ---------------------------------------------------------------------------
# the cues
# ---------------------------------------------------------------------------

def cue_starts(count=CUES, first=FIRST, every=EVERY):
    u"""-> [5.0, 9.0, 13.0, ...]"""
    return [first + every * i for i in range(count)]


def timecode(seconds):
    u"""SRT's `HH:MM:SS,mmm`."""
    milliseconds = int(round(seconds * 1000.0))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return u"%02d:%02d:%02d,%03d" % (hours, minutes, whole, milliseconds)


def srt(starts, seconds=SECONDS, shift=0.0, text=u"行 %d"):
    u"""The cues as SubRip. -> text

    ⚠ The body is Japanese by default and the file is written UTF-8. hato's
    whole domain is Japanese subtitles, and `LEDGER-HOT.md` records Windows
    Python defaulting to cp1252 on the first real one -- so the fixture carries
    characters that would expose it rather than pure ASCII that would not.
    """
    blocks = []
    for index, start in enumerate(starts, 1):
        blocks.append(u"%d\n%s --> %s\n%s\n"
                      % (index, timecode(start + shift),
                         timecode(start + shift + seconds), text % index))
    return u"\n".join(blocks) + u"\n"


def write_srt(path, body):
    u"""🚨 Temp-plus-rename and `encoding='utf-8'` (`LEDGER-HOT.md`, twice)."""
    path = Path(path)
    if not path.parent.is_dir():
        path.parent.mkdir(parents=True)
    temporary = path.with_name(path.name + u".part")
    with io.open(str(temporary), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    os.replace(str(temporary), str(path))
    return path


# ---------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------

class Media(object):
    u"""What `build()` made. Paths, and the numbers a check needs to assert."""

    __slots__ = ("root", "media_dir", "cache_dir", "video", "subtitle",
                 "starts", "shift", "duration", "reference_srt", "owned")

    def __init__(self, root, media_dir, cache_dir, video, subtitle, starts,
                 shift, duration, reference_srt, owned):
        self.root = Path(root)
        #: The "media folder" -- the video, and where tsubasa writes.
        self.media_dir = Path(media_dir)
        #: hato's working cache -- where the download sits. ⛔ A different
        #: folder on purpose: `03-permissions.md` says the media folder sees
        #: exactly ONE filesystem operation per success, tsubasa's write.
        self.cache_dir = Path(cache_dir)
        self.video = Path(video)
        self.subtitle = Path(subtitle)
        self.starts = list(starts)
        self.shift = shift
        self.duration = duration
        #: The reference cues as handed to ffmpeg. ⚠ Kept OUTSIDE both folders
        #: above, so a check can list them and find only what the run put there.
        self.reference_srt = Path(reference_srt)
        self.owned = owned

    def listing(self, folder):
        u"""Names in `folder`, sorted. -> [str]"""
        return sorted(p.name for p in Path(folder).iterdir())

    def cleanup(self):
        if self.owned and self.root.is_dir():
            shutil.rmtree(str(self.root), ignore_errors=True)

    def __repr__(self):
        return "Media(%s, %d cues, shift %+.2fs)" % (self.video.name,
                                                     len(self.starts),
                                                     self.shift)


def _check_destination(dest):
    dest = Path(dest).resolve()
    try:
        dest.relative_to(VAULT)
    except ValueError:
        return dest
    raise OutsideTheVault(
        "refusing to build media at %s: it is inside %s, which auto-commits "
        "every few minutes. Build into the OS temp dir -- pytest's tmp_path, "
        "or _media.build() with no destination (spec/07-test-plan.md)."
        % (dest, VAULT))


def build(dest=None, stem=u"Sample Show - 01", lang=u"ja", ext=u"srt",
          count=CUES, first=FIRST, every=EVERY, seconds=SECONDS, shift=SHIFT,
          width=160, height=120, fps=5, track_language=u"jpn"):
    u"""A real video and a shifted subtitle for it. -> `Media`

    `dest`
        an empty directory OUTSIDE the vault -- pytest's `tmp_path`. None makes
        one under `tempfile.gettempdir()` and removes it at exit.
    `stem`
        the video's basename. The download is named `<stem>.<lang>.<ext>`,
        which is what `03-permissions.md` requires hato to hand tsubasa.
    `shift`
        how far the download's cues are out. ⭐ Positive means the subtitle is
        LATE, so tsubasa's reported offset is about `-shift`.

    ⚠ The subtitle track is muxed as `srt` and tagged `jpn`, so tsubasa reads
    a TEXT track (`S_TEXT/UTF8`) and not a bitmap one -- the reference kind the
    verdict bands were fitted on.
    """
    owned = dest is None
    if owned:
        dest = tempfile.mkdtemp(prefix="hato-media-")
        atexit.register(shutil.rmtree, dest, True)
    root = _check_destination(dest)

    build_dir = root / "build"
    media_dir = root / "media"
    cache_dir = root / "cache"
    for folder in (build_dir, media_dir, cache_dir):
        if not folder.is_dir():
            folder.mkdir(parents=True)

    starts = cue_starts(count, first, every)
    duration = starts[-1] + seconds + SLACK
    reference = write_srt(build_dir / (stem + u".reference.srt"),
                          srt(starts, seconds))
    video = media_dir / (stem + u".mkv")
    _mux(video, reference, duration, width, height, fps, track_language)
    subtitle = write_srt(cache_dir / (u"%s.%s.%s" % (stem, lang, ext)),
                         srt(starts, seconds, shift=shift))
    return Media(root, media_dir, cache_dir, video, subtitle, starts, shift,
                 duration, reference, owned)


def _mux(video, reference, duration, width, height, fps, track_language):
    u"""testsrc + anullsrc + the cues, into one Matroska file.

    ⚠ `-crf 51 -preset ultrafast` on a 160x120 5 fps source keeps a five-minute
    video at about 300 KB. ⛔ Quality is irrelevant here: nothing reads a pixel.
    What is read is the container's subtitle track and its block timestamps.
    """
    command = [
        ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=%dx%d:rate=%d:duration=%.3f"
                             % (width, height, fps, duration),
        "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono:duration=%.3f" % duration,
        "-i", str(reference),
        "-map", "0:v", "-map", "1:a", "-map", "2:s",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "51",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "8k",
        "-c:s", "srt", "-metadata:s:s:0", "language=%s" % track_language,
        "-t", "%.3f" % duration, str(video),
    ]
    done = subprocess.run(command, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if done.returncode != 0 or not Path(video).is_file():
        raise RuntimeError(
            "ffmpeg could not build the test video (exit %d).\n%s"
            % (done.returncode, done.stderr.decode("utf-8", "replace")[:4000]))
    return video
