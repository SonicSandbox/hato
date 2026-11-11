# -*- coding: utf-8 -*-
u"""⭐ RUNBOOK LAYER 19 -- subtitles made from a video's own audio, on this computer.

    status()                          what is installed, what is picked, the sizes
    install(model, gpu=False, ...)    the add-on and the picked model, on the learner's yes
    remove(what=None)                 a model, the NVIDIA pack, or everything (hato's own files only)
    make(paths, model=None, ...)      <video stem>.ja.from-audio.srt beside each video / audio file
    retire(video, kept)               a real subtitle arrived: the one hato made goes to the trash (19f)

⛔ NOTHING HERE RUNS BEFORE A YES. hato's zip holds this module and the small code that offers it; the add-on
(`hato-speech.exe`, `speech_engine.py`) and the models are downloaded only by `install`, which only `hato speech
install` calls -- and that only the window's confirm (with the size, once) or a person typing it.

🚨 EVERY DOWNLOAD IS PINNED HERE -- a URL, its size and its sha256 -- so hato's own signed release vouches for each
byte (no `update.json` change: an older hato never meets a key it can't read). A `.part` resumes after a stop and is
checked whole before anything is unpacked; a wrong sha256 is thrown away and said once.

🚨 ALL OF IT LIVES IN `<data root>/speech/` -- the add-on, the models, the NVIDIA pack, the pick (`choice.json`) and
the record of what hato made (`made.json`). ⛔ Never `config.toml`: Go back to an older hato then reads nothing it
doesn't know (LEDGER-HOT, the NEWER_THAN rule).

⭐ THE MARKER IS THE NAME (19e): `<video stem>.ja.from-audio.srt` -- the mark Surasura (`episode_names.FROM_AUDIO`)
and tsubasa (17e) already read as "made from the audio, this video's episode". ⛔ No text of ours inside the file
(a card shows every line), and ⛔ never registered with Surasura.
"""
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hato import paths

FAST = u"fast"
ACCURATE = u"accurate"
MODELS = (FAST, ACCURATE)
GPU = u"gpu"
ADDON = u"addon"
LANG = u"ja"
MARK = u"from-audio"
SUFFIX = u".%s.%s.srt" % (LANG, MARK)        # <video stem>.ja.from-audio.srt

#: ⭐ The add-on's protocol this hato speaks (`speech_engine.PROTOCOL`).
PROTOCOL = 1

VIDEO_EXTENSIONS = frozenset((u".mkv", u".mp4", u".m4v", u".avi", u".webm", u".mov", u".ts", u".m2ts", u".wmv",
                              u".flv"))
AUDIO_EXTENSIONS = frozenset((u".mp3", u".m4a", u".m4b", u".aac", u".flac", u".ogg", u".opus", u".wav"))

#: One download. `size` and `sha256` are the walls: never a byte past `size`, never used unless both match.
Pin = collections.namedtuple("Pin", "name url size sha256")

_GH = u"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
_HF = u"https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo/resolve/" \
      u"0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/"
_PYPI = u"https://files.pythonhosted.org/packages/"

#: ⭐ THE ADD-ON. Its zip is an asset of hato's own GitHub release; the version, size and sha256 are pinned when the
#: release builds it (RUNBOOK 19, packaging/package_speech.py) -- until then `install` says it isn't published.
ADDON_VERSION = u"1.0.0"
ADDON_PIN = Pin(u"hato-speech-%s-windows-x64.zip" % ADDON_VERSION,
                u"https://github.com/SonicSandbox/hato/releases/download/v1.4.0/"
                u"hato-speech-%s-windows-x64.zip" % ADDON_VERSION, 0, u"")

#: ⭐ THE MODELS (RUNBOOK 19b) -- what each part fetches, and the files it keeps.
PARTS = {
    FAST: dict(folder=u"parakeet-ja", kind=u"tar", keep=(u"model.int8.onnx", u"tokens.txt"), pins=(
        Pin(u"sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8.tar.bz2",
            _GH + u"sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8.tar.bz2", 489389564,
            u"4b0a800ef29f4f4c8667339bf6f60d5bfdc2852ddc9dc5741aea65b6f8d1306b"),)),
    ACCURATE: dict(folder=u"whisper-turbo", kind=u"files", keep=(), pins=(
        Pin(u"model.bin", _HF + u"model.bin", 1617884929,
            u"e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
        Pin(u"config.json", _HF + u"config.json", 2263,
            u"b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e"),
        Pin(u"preprocessor_config.json", _HF + u"preprocessor_config.json", 340,
            u"7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
        Pin(u"tokenizer.json", _HF + u"tokenizer.json", 2710337,
            u"297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd"),
        Pin(u"vocabulary.json", _HF + u"vocabulary.json", 1068114,
            u"c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1"))),
    # ⛔ NVIDIA's libraries are under NVIDIA's EULA: never in a zip of ours, fetched on the learner's machine from
    # PyPI's own wheels (as Anki Miner does), and only `nvidia/*/bin/*.dll` kept
    GPU: dict(folder=u"gpu", kind=u"wheels", keep=(), pins=(
        Pin(u"nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
            _PYPI + u"20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/"
                    u"nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl", 553162896,
            u"623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661"),
        Pin(u"nvidia_cudnn_cu12-9.28.1.4-py3-none-win_amd64.whl",
            _PYPI + u"c7/bd/1d6709d2223e99f04079f16005f8ae6e11a14ee16b5eab6833686cf72fe1/"
                    u"nvidia_cudnn_cu12-9.28.1.4-py3-none-win_amd64.whl", 696300805,
            u"3467aafa9b260e6adf5fbbfc0e21d180133305b42032aa1160be2d3142bb8b09"),
        Pin(u"nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl",
            _PYPI + u"52/de/823919be3b9d0ccbf1f784035423c5f18f4267fb0123558d58b813c6ec86/"
                    u"nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl", 76408187,
            u"72972ebdcf504d69462d3bcd67e7b81edd25d0fb85a2c46d3ea3517666636349"))),
}

#: The walls on what an archive may unpack to (the add-on's zip, the model's tar, a wheel).
MAX_MEMBERS = 20000
MAX_UNPACKED = 4 * 1024 * 1024 * 1024
#: The run's own lock: a folder made from its audio takes an hour, and the daily jimaku run never waits on it.
LOCK_NAME = u"make.lock"


class SpeechError(Exception):
    u"""One sentence a person reads; never a traceback."""


class RangeRefused(Exception):
    u"""The server answered 416 to a resume: the `.part` is not the start of this file (A19-15)."""


# --- where it lives -------------------------------------------------------------------------------------------- #

def root():
    return paths.data_root() / u"speech"


def addon_dir():
    return root() / ADDON


def exe_path():
    return addon_dir() / u"hato-speech" / u"hato-speech.exe"


def models_dir():
    return root() / u"models"


def part_dir(part):
    return root() / GPU if part == GPU else models_dir() / PARTS[part][u"folder"]


def downloads_dir():
    return paths.cache_dir() / u"speech"


def choice_path():
    return root() / u"choice.json"


def made_path():
    return root() / u"made.json"


def _read_json(path, default):
    try:
        with open(str(path), encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    u"""🚨 Temp plus rename (LEDGER-HOT): a write that raises never leaves the file empty."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=u".hato-", suffix=u".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(temporary, str(path))
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


# --- what is there --------------------------------------------------------------------------------------------- #

def installed(part):
    u"""Is `part` (fast · accurate · gpu · addon) whole on disk? Read from the files, never from a record."""
    if part == ADDON:
        return exe_path().is_file() and _read_json(addon_dir() / u"version.json", {}).get(u"version") == ADDON_VERSION
    folder = part_dir(part)
    if part == GPU:
        return folder.is_dir() and any(n.lower().startswith(u"cublas64_") for n in os.listdir(str(folder)))
    names = PARTS[part][u"keep"] or tuple(p.name for p in PARTS[part][u"pins"])
    return all((folder / n).is_file() for n in names)


def download_size(part):
    return sum(p.size for p in PARTS[part][u"pins"])


def disk_size(folder):
    total = 0
    for where, _dirs, files in os.walk(str(folder)):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(where, name))
            except OSError:
                pass
    return total


def picked():
    u"""The model the learner picked (`choice.json`), else the one installed, else Fast."""
    choice = _read_json(choice_path(), {}).get(u"model")
    if choice in MODELS:
        return choice
    return ACCURATE if installed(ACCURATE) and not installed(FAST) else FAST


def pick(model):
    if model not in MODELS:
        raise SpeechError(u"pick fast or accurate")
    _write_json(choice_path(), {u"model": model})


def nvidia_card():
    u"""Does this computer have an NVIDIA card? Read from Windows' own list of display adapters; ⛔ never raises."""
    if not sys.platform.startswith(u"win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}")
    except OSError:
        return False
    found = False
    with key:
        for n in range(64):
            try:
                with winreg.OpenKey(key, winreg.EnumKey(key, n)) as sub:
                    name = winreg.QueryValueEx(sub, u"DriverDesc")[0]
            except OSError:
                if n > 32:
                    break
                continue
            if u"nvidia" in str(name).lower():
                found = True
                break
    return found


def surasura_found():
    u"""⭐ 19g -- is a Surasura there (its tools entry), connected or not? Then the card is quiet: Surasura makes
    these through Anki Miner. ⛔ Never raises."""
    try:
        from hato import connect
        return connect.read_entry().status == u"present"
    except Exception:                                   # noqa: BLE001 -- a quiet card, never a stop
        return False


def status():
    u"""Everything the card and `hato speech status` say. -> dict"""
    parts = {}
    for part in MODELS + (GPU,):
        parts[part] = {u"installed": installed(part), u"download": download_size(part),
                       u"on_disk": disk_size(part_dir(part)) if part_dir(part).is_dir() else 0}
    return {u"type": u"speech", u"addon": {u"installed": installed(ADDON), u"version": ADDON_VERSION,
                                           u"download": ADDON_PIN.size, u"published": bool(ADDON_PIN.sha256),
                                           u"on_disk": disk_size(addon_dir()) if addon_dir().is_dir() else 0},
            u"models": parts, u"picked": picked(), u"nvidia": nvidia_card(), u"surasura": surasura_found(),
            u"held": paths.held_by() is not None}


# --- the downloads --------------------------------------------------------------------------------------------- #

def stream(url, start=0):
    u"""Yield the body of `url` from byte `start` -> (blocks..., with `.resumed` on the first). ⛔ HATO_NO_NETWORK=1
    refuses before a socket exists, as every hato download does (update.stream)."""
    if os.environ.get("HATO_NO_NETWORK") == "1":
        raise SpeechError(u"the network is switched off, so nothing was downloaded")
    try:
        import requests
    except ImportError:
        raise SpeechError(u"requests is not installed, so nothing was downloaded")
    from hato import update
    headers = {u"User-Agent": update.user_agent()}
    if start:
        headers[u"Range"] = u"bytes=%d-" % start
    try:
        with requests.get(url, headers=headers, timeout=30, stream=True) as response:
            if response.status_code == 206 and start:
                yield True                                  # resumed where the .part ends
            elif response.status_code == 416 and start:
                raise RangeRefused()                        # the .part is longer than the file: start again
            elif response.status_code == 200:
                yield False                                 # from the start (a server that ignores Range)
            else:
                raise SpeechError(u"the server answered %d for the download" % response.status_code)
            for block in response.iter_content(1024 * 1024):
                if block:
                    yield block
    except (SpeechError, RangeRefused):
        raise
    except Exception as exc:                            # noqa: BLE001 -- a sentence, never a traceback
        raise SpeechError(u"the download stopped (%s) -- it goes on from there next time" % type(exc).__name__)


def fetch(pin, progress=None, get=None, done_before=0, total=None):
    u"""`pin` -> its verified file in `downloads_dir()`. Resumes a `.part` left by a stop.

    🚨 SIZE AND SHA256 BOTH, BEFORE IT IS USED: a `.part` never grows past `pin.size`, and a whole one whose hash
    isn't the pin's is thrown away and said -- never unpacked."""
    get = stream if get is None else get
    if not pin.sha256 or not pin.size:
        raise SpeechError(u"the speech add-on isn't published yet")
    folder = downloads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / pin.name
    if final.is_file() and final.stat().st_size == pin.size and _sha256(final) == pin.sha256:
        return final
    part = folder / (pin.name + u".part")
    have = part.stat().st_size if part.is_file() else 0
    if have > pin.size:
        part.unlink()
        have = 0
    if have < pin.size:
        blocks = get(pin.url, have)
        try:
            resumed = next(blocks)
        except RangeRefused:                            # ⭐ A19-15: thrown away, then once from nothing
            part.unlink()
            have = 0
            blocks = get(pin.url, 0)
            resumed = next(blocks)
        mode = "ab" if resumed else "wb"
        have = have if resumed else 0
        with open(str(part), mode) as out:
            for block in blocks:
                have += len(block)
                if have > pin.size:
                    break
                out.write(block)
                if progress is not None:
                    progress(done_before + have, total or pin.size)
    if have != pin.size or _sha256(part) != pin.sha256:
        try:
            part.unlink()
        except OSError:
            pass
        raise SpeechError(u"%s didn't match what hato expects -- it was damaged or replaced on the way, so it was "
                          u"thrown away" % pin.name)
    os.replace(str(part), str(final))
    return final


def _sha256(path, chunk=1 << 22):
    digest = hashlib.sha256()
    with open(str(path), "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


# --- unpacking: every member judged before a byte is written (archives' rules) ----------------------------------- #

def _judge(names_sizes, top=None):
    u"""[(name, size, is_link)] -> raises SpeechError on a member that could land outside, a link, or walls."""
    from hato import archives
    if len(names_sizes) > MAX_MEMBERS:
        raise SpeechError(u"the download lists too many files to be what hato expects")
    total = 0
    for name, size, link in names_sizes:
        parts = name.replace(u"\\", u"/").split(u"/")
        if archives.unsafe_name(name) or (top is not None and parts[0] != top):
            raise SpeechError(u"a file in the download would land outside hato's folder, so none of it was unpacked")
        if link:
            raise SpeechError(u"the download holds a link, so none of it was unpacked")
        total += size
    if total > MAX_UNPACKED:
        raise SpeechError(u"the download unpacks to more than hato expects")


def _into(folder, write):
    u"""Unpack under `folder.part`, then rename it into place whole. `write(part_folder)` does the writing.

    ⚠ A19-14 -- the folder already there is RENAMED ASIDE first (`.old`), then removed: a file in it held open (an
    add-on still running, a virus scanner) fails the rename, and the install says so with the old one whole --
    never a half-deleted folder that a new one could not replace."""
    folder = Path(folder)
    part = Path(str(folder) + u".part")
    old = Path(str(folder) + u".old")
    for stale in (part, old):
        if stale.exists():
            shutil.rmtree(str(stale), ignore_errors=True)
    part.mkdir(parents=True)
    try:
        write(part)
        if folder.exists():
            try:
                os.replace(str(folder), str(old))
            except OSError:
                raise SpeechError(u"a file in %s is in use, so nothing was changed -- close what uses it and try "
                                  u"again" % folder.name)
        os.replace(str(part), str(folder))
    except BaseException:
        shutil.rmtree(str(part), ignore_errors=True)
        raise
    shutil.rmtree(str(old), ignore_errors=True)


def _copy_member(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(str(target), "wb") as out:
        shutil.copyfileobj(source, out, 1024 * 1024)


def unpack_zip(zip_path, folder, top=u"hato-speech"):
    u"""The add-on's zip: its one `hato-speech/` folder -> `folder/hato-speech/`."""
    import zipfile
    try:
        archive = zipfile.ZipFile(str(zip_path))
    except (zipfile.BadZipFile, OSError) as exc:
        raise SpeechError(u"the download is not a readable zip (%s)" % type(exc).__name__)
    with archive:
        infos = archive.infolist()
        _judge([(i.filename, i.file_size, (i.external_attr >> 16) & 0o170000 == 0o120000) for i in infos], top=top)

        def write(part):
            for info in infos:
                bits = [b for b in info.filename.replace(u"\\", u"/").split(u"/") if b]
                if info.is_dir():
                    continue
                with archive.open(info) as source:
                    _copy_member(source, part.joinpath(*bits))
        _into(folder, write)


def unpack_tar(tar_path, folder, keep):
    u"""The Fast model's tar.bz2: only the files named in `keep` (wherever they sit in it) -> `folder/`."""
    import tarfile
    try:
        archive = tarfile.open(str(tar_path), "r:*")
    except (tarfile.TarError, OSError) as exc:
        raise SpeechError(u"the download is not a readable archive (%s)" % type(exc).__name__)
    with archive:
        members = archive.getmembers()
        _judge([(m.name, m.size, m.issym() or m.islnk()) for m in members])
        wanted = dict((os.path.basename(m.name), m) for m in members if m.isfile() and
                      os.path.basename(m.name) in keep)
        if set(wanted) != set(keep):
            raise SpeechError(u"the download doesn't hold the model hato expects")

        def write(part):
            for name, member in wanted.items():
                with archive.extractfile(member) as source:
                    _copy_member(source, part / name)
        _into(folder, write)


def unpack_wheels(wheel_paths, folder):
    u"""NVIDIA's wheels: only `nvidia/*/bin/*.dll`, flat -> `folder/`."""
    import zipfile

    def write(part):
        for path in wheel_paths:
            try:
                archive = zipfile.ZipFile(str(path))
            except (zipfile.BadZipFile, OSError) as exc:
                raise SpeechError(u"the download is not a readable zip (%s)" % type(exc).__name__)
            with archive:
                infos = archive.infolist()
                _judge([(i.filename, i.file_size, False) for i in infos])
                for info in infos:
                    bits = info.filename.split(u"/")
                    if (len(bits) == 4 and bits[0] == u"nvidia" and bits[2] == u"bin" and
                            bits[3].lower().endswith(u".dll")):
                        with archive.open(info) as source:
                            _copy_member(source, part / bits[3])
    _into(folder, write)


# --- install / remove ------------------------------------------------------------------------------------------ #

def _refuse_when_held():
    if paths.held_by() is not None:
        raise SpeechError(u"this copy of hato is kept by another program, so it installs nothing itself")


def install(model, gpu=False, progress=None, get=None):
    u"""⭐ 19c -- the add-on (when missing or another version) and `model` (and NVIDIA's pack with `gpu`), each
    downloaded, verified and unpacked whole. -> the list of parts installed now. ⛔ Only ever on a yes."""
    if model not in MODELS:
        raise SpeechError(u"pick fast or accurate")
    _refuse_when_held()
    with _locked():
        return _install(model, gpu, progress, get)


class _locked(object):
    u"""⚠ A19-14 -- install and remove take the make's own lock: never a model replaced under a run using it."""

    def __enter__(self):
        from hato.runlock import LockHeld, RunLock
        self.lock = RunLock(root() / LOCK_NAME)
        try:
            self.lock.acquire()
        except LockHeld:
            raise SpeechError(u"subtitles are being made from audio -- try again when that finishes")
        return self

    def __exit__(self, *exc):
        self.lock.release()
        return False


def _install(model, gpu, progress, get):
    todo = []
    if not installed(ADDON):
        todo.append(ADDON)
    if not installed(model):
        todo.append(model)
    if gpu and not installed(GPU):
        todo.append(GPU)
    pins = [ADDON_PIN if p == ADDON else pin for p in todo for pin in ((ADDON_PIN,) if p == ADDON else
                                                                      PARTS[p][u"pins"])]
    total, done = sum(p.size for p in pins), 0
    for part in todo:
        got = []
        for pin in ((ADDON_PIN,) if part == ADDON else PARTS[part][u"pins"]):
            got.append(fetch(pin, progress=progress, get=get, done_before=done, total=total))
            done += pin.size
        if part == ADDON:
            unpack_zip(got[0], addon_dir())
            _write_json(addon_dir() / u"version.json", {u"version": ADDON_VERSION})
        elif PARTS[part][u"kind"] == u"tar":
            unpack_tar(got[0], part_dir(part), PARTS[part][u"keep"])
        elif PARTS[part][u"kind"] == u"wheels":
            unpack_wheels(got, part_dir(part))
        else:
            def write(folder, got=got):
                for path in got:                        # ⚠ A19-13: moved on one volume, never 1.6 GB twice
                    try:
                        os.replace(str(path), str(folder / path.name))
                    except OSError:
                        shutil.copyfile(str(path), str(folder / path.name))
            _into(part_dir(part), write)
        for path in got:                                    # the downloads were only ever a means
            try:
                path.unlink()
            except OSError:
                pass
    pick(model)
    return todo


def remove(what=None):
    u"""Remove a model (`fast`, `accurate`), NVIDIA's pack (`gpu`), or the add-on and all it downloaded (None).
    -> bytes freed. ⛔ hato's own `speech/` files only: the subtitles it made stay beside the videos.
    ⚠ A19-6 -- `made.json` STAYS, and the pick: 19f must still know which files hato made, so a real subtitle
    found after a Remove still sends hato's own made file to the trash."""
    targets = ([addon_dir(), models_dir(), part_dir(GPU), downloads_dir()] if what is None else [part_dir(what)])
    freed = 0
    with _locked():
        for target in targets:
            if target.is_dir():
                freed += disk_size(target)
                shutil.rmtree(str(target), ignore_errors=True)
    return freed


# --- making them ----------------------------------------------------------------------------------------------- #

def is_media(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def media_under(targets, skip=()):
    u"""Every video and audio file named, or under a folder named, minus the skipped folders. In order, once."""
    from hato import keep
    seen, out = set(), []
    for target in targets:
        target = os.path.abspath(os.fspath(target))
        if os.path.isfile(target):
            found = [target] if is_media(target) else []
        else:
            found = []
            for where, dirs, files in os.walk(target):
                dirs[:] = sorted(d for d in dirs if not d.startswith(u".") and d.lower() != u"$recycle.bin" and
                                 not any(keep.inside(os.path.join(where, d), s) for s in skip))
                found.extend(os.path.join(where, f) for f in sorted(files) if is_media(f))
        for path in found:
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                out.append(path)
    return out


def target_of(media, beside=True):
    u"""Where the made file goes: beside the video, or hato's own folder (`write_beside_video` off, keep.own_dir)."""
    from hato import keep
    stem = os.path.splitext(os.path.basename(media))[0]
    return keep.target_dir(media, None, out=None, beside=beside) / (stem + SUFFIX)


def plan(media_paths, beside=True, presence=None, tracks=None):
    u"""Each file -> (media, target, None to make it, else why not).

    🚨 Two files that would make ONE name (`Show - 01.mkv` + `Show - 01.mp4`) both refuse (LEDGER-HOT: never let
    two videos target one output path) -- ⚠ A19-8: and so does one whose SIBLING shares its stem though the sibling
    isn't in this run (one file picked, the waiting strip's button).
    ⚠ A19-7 -- `present` too when a video carries a Japanese TEXT track inside (`present.read_tracks`, hato's own
    read rule): never an hour of listening for a subtitle it already has. `tracks(video)` -> kind (a seam)."""
    from hato import present
    presence = presence or presence_for()
    tracks = tracks or (lambda video: present.read_tracks(video, LANG).kind)
    out = []
    for media in media_paths:
        target = target_of(media, beside)
        why = None
        # two files making one name always sit in one folder with one stem (hato's own folder is one a video
        # folder): the sibling check refuses both, whether or not the other is in this run
        if sibling_shares_stem(media):
            why = u"clash"
        elif os.path.lexists(str(target)):
            why = u"already"
        elif has_subtitle(media, target, beside, presence):
            why = u"present"
        elif os.path.splitext(media)[1].lower() in VIDEO_EXTENSIONS:
            try:
                if tracks(media) == present.EMBEDDED:
                    why = u"present"
            except Exception:                           # noqa: BLE001 -- an unread container is listened to
                pass
        out.append((media, target, why))
    return out


def presence_for():
    from hato.present import Presence
    return Presence(LANG)


def has_subtitle(media, target, beside, presence):
    u"""Is a real Japanese subtitle there for `media`, by hato's own present-check -- asked AFRESH (its listing of
    the folder forgotten first: A19-9)?"""
    from hato import keep
    presence.forget(str(target.parent))
    also = keep.also_beside(None, beside)
    if also:
        presence.forget(os.path.dirname(media))
    return bool(presence.find(media, folder=str(target.parent)) or (also and presence.find(media)))


def sibling_shares_stem(media):
    u"""A19-8 -- another video or audio file beside `media` with the same stem (normcased): one made name for two."""
    folder, name = os.path.split(media)
    stem = os.path.normcase(os.path.splitext(name)[0])
    try:
        names = os.listdir(folder or u".")
    except OSError:
        return False
    return any(n != name and is_media(n) and os.path.normcase(os.path.splitext(n)[0]) == stem for n in names)


def addon_argv(media, output, model, gpu=True):
    argv = [str(exe_path()), u"run", u"--model", model, u"--models", str(models_dir()),
            u"--input", media, u"--output", output]
    if gpu and model == ACCURATE and installed(GPU):
        argv += [u"--gpu", str(part_dir(GPU))]
    return argv


def _spawn(argv):
    extra = {}
    if sys.platform.startswith(u"win"):
        extra[u"creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            **extra)


def listen(media, output, model, progress=None, should_stop=None, spawn=None, gpu=True):
    u"""Run the add-on on one file. -> its `result` line (dict), or {"outcome": "stopped"}. ⛔ A stop ends the
    process: what it was writing is in hato's cache, never beside the video."""
    process = (spawn or _spawn)(addon_argv(media, output, model, gpu=gpu))
    result = None
    try:
        for raw in process.stdout:
            if should_stop is not None and should_stop():
                process.kill()
                process.wait()
                return {u"outcome": u"stopped"}
            try:
                line = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(line, dict):
                continue
            if line.get(u"type") == u"progress" and progress is not None:
                progress(line)
            elif line.get(u"type") == u"result":
                result = line
        process.wait()
    finally:
        if process.poll() is None:
            process.kill()
    if should_stop is not None and should_stop():
        return {u"outcome": u"stopped"}
    return result or {u"outcome": u"error", u"why": u"the speech add-on stopped without an answer"}


def make(targets, model=None, beside=True, skip=(), progress=None, should_stop=None, spawn=None, now=None,
         tracks=None):
    u"""⭐ 19d -- for each video / audio file: `<stem>.ja.from-audio.srt` made from its own audio. -> rows, one a
    file: {"path", "outcome", "subtitle"?, "why"?}. outcomes: made · present (a real Japanese subtitle is there) ·
    already (a made one is there) · clash · no_speech · unreadable · stopped · error.

    🚨 Placed by temp + rename in the target's own folder, ⛔ never over a file (`keep._place`), and recorded in
    `made.json` (path, sha256, model, when) -- the record 19f reads."""
    from hato import keep
    from hato.runlock import RunLock
    model = model or picked()
    if not installed(ADDON) or not installed(model):
        raise SpeechError(u"install the speech add-on and the %s model first" % (
            u"Fast" if model == FAST else u"More accurate"))
    rows = []
    work = downloads_dir() / u"out"
    work.mkdir(parents=True, exist_ok=True)
    presence = presence_for()
    gpu = [True]                                    # ⚠ A19-10: off for the rest of the run once the card failed
    with RunLock(root() / LOCK_NAME):
        for media, target, why in plan(media_under(targets, skip), beside=beside, presence=presence,
                                       tracks=tracks):
            if should_stop is not None and should_stop():
                rows.append({u"path": media, u"outcome": u"stopped"})
                continue
            if why is not None:
                rows.append({u"path": media, u"outcome": why})
                continue
            temporary = str(work / (u"%d-%d.srt" % (os.getpid(), len(rows))))
            if os.path.exists(temporary):
                os.remove(temporary)

            def told(line, media=media, n=len(rows)):
                if progress is not None:
                    progress(dict(line, path=media, index=n))
            # ⚠ A19-9 -- asked AGAIN just before listening: an hour-long folder run meets a daily run that kept a
            # real subtitle for a later file meanwhile
            if has_subtitle(media, target, beside, presence):
                rows.append({u"path": media, u"outcome": u"present"})
                continue
            answer = listen(media, temporary, model, progress=told, should_stop=should_stop, spawn=spawn,
                            gpu=gpu[0])
            if answer.get(u"outcome") == u"error" and gpu[0] and model == ACCURATE and installed(GPU):
                # ⚠ A19-10 -- a card CUDA can't use after all (a driver too old for NVIDIA's libraries): the CPU,
                # for this file and every file after it in this run
                gpu[0] = False
                if os.path.exists(temporary):
                    os.remove(temporary)
                answer = listen(media, temporary, model, progress=told, should_stop=should_stop, spawn=spawn,
                                gpu=False)
            outcome = answer.get(u"outcome")
            row = {u"path": media, u"outcome": outcome if outcome in (
                u"made", u"no_speech", u"unreadable", u"too_long", u"stopped") else u"error"}
            if outcome == u"made" and os.path.isfile(temporary) and has_subtitle(media, target, beside, presence):
                row = {u"path": media, u"outcome": u"present"}      # A19-9: a real one arrived while it listened
            elif outcome == u"made" and os.path.isfile(temporary):
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    keep._place(temporary, target)
                except FileExistsError:
                    row = {u"path": media, u"outcome": u"already"}
                except OSError as exc:
                    row = {u"path": media, u"outcome": u"error", u"why": u"couldn't be written (%s)" % (
                        exc.strerror or type(exc).__name__)}
                else:
                    row[u"subtitle"] = str(target)
                    _remember(target, model, now)
            elif row[u"outcome"] == u"error":
                row[u"why"] = answer.get(u"why") or u"the speech add-on stopped"
            if os.path.exists(temporary):
                os.remove(temporary)
            rows.append(row)
    return rows


def _remember(target, model, now=None):
    made = _read_json(made_path(), {})
    made[os.path.normcase(os.path.abspath(str(target)))] = {
        u"path": str(target), u"sha256": _sha256(target), u"model": model,
        u"at": int(now if now is not None else time.time())}
    _write_json(made_path(), made)


def made_by_hato(path):
    u"""Did hato make this file, and is it as hato left it? -> bool (19f's only test)."""
    entry = _read_json(made_path(), {}).get(os.path.normcase(os.path.abspath(str(path))))
    if not isinstance(entry, dict) or not os.path.isfile(str(path)):
        return False
    try:
        return _sha256(path) == entry.get(u"sha256")
    except OSError:
        return False


def made_for(video, beside=True):
    u"""The made file's path for `video` (beside it, or hato's own folder), whether or not it is there."""
    return target_of(video, beside)


def retire(video, beside=True, trash=None):
    u"""⭐ 19f (PROVISIONAL) -- a real Japanese subtitle was just kept for `video`: the `.from-audio.srt` hato made
    for it goes to the trash, restorably (`tsubasa.dedupe.trash`). -> its path, or None.

    ⛔ ONLY A FILE hato MADE ITSELF AND NOBODY CHANGED (`made_by_hato`): Surasura's own copies, and any file a person
    edited, stay. ⛔ Never raises: a run that kept its subtitle is never turned into a failure here."""
    try:
        made = made_for(video, beside)
        if not made_by_hato(made):
            return None
        if trash is None:
            from tsubasa import dedupe
            trash_root = str(paths.data_root() / u"trash")
            os.makedirs(trash_root, exist_ok=True)
            moved = dedupe.trash(str(made), trash_root, dry_run=False)
            if not getattr(moved, u"performed", False):
                return None
        else:
            trash(str(made))
        entries = _read_json(made_path(), {})
        entries.pop(os.path.normcase(os.path.abspath(str(made))), None)
        _write_json(made_path(), entries)
        return str(made)
    except Exception:                                   # noqa: BLE001 -- see the docstring
        return None


__all__ = ["FAST", "ACCURATE", "MODELS", "GPU", "SUFFIX", "SpeechError", "status", "installed", "picked", "pick",
           "install", "remove", "make", "plan", "media_under", "target_of", "made_by_hato", "retire",
           "nvidia_card", "surasura_found"]
