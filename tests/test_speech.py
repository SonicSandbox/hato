# -*- coding: utf-8 -*-
u"""
LAYER 19 -- subtitles made from a video's own audio (`hato/speech.py`, `hato/commands/speech.py`, the add-on's pure
half in `hato/speech_engine.py`).

What a wrong answer would cost:
  * a download used before its size and sha256 are checked -- a replaced model, or an exe, run on someone's machine;
  * an archive member landing outside hato's folder (zip-slip), or a link followed;
  * a made subtitle written over the learner's own file, or half a file left beside a video after a Cancel;
  * a video that has a real Japanese subtitle given a made one too, or two videos making ONE name;
  * the made file going to the trash when hato didn't make it (Surasura's own copy, a file a person edited);
  * any of it starting without the learner's yes, or from a copy another program holds.

⛔ WHAT THIS SUITE CANNOT COVER: what the models hear. The add-on is a stand-in here (`FakeAddon`); the real one
runs in `speech_live` (opt-in: the models are 0.5 and 1.6 GB, never in the repo), and the frozen one in the smoke.
"""
import hashlib
import io
import json
import os
import tarfile
import zipfile

import pytest

from hato import speech, speech_engine
from hato.commands import speech as command

JA = u"1\n00:00:01,000 --> 00:00:03,500\n杜子春は洛陽の西の門の下に立っていた。\n"


@pytest.fixture
def root(tmp_path, monkeypatch):
    u"""A data root of the test's own, nothing installed, no Surasura, no network."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    monkeypatch.delenv("HATO_HELD_BY", raising=False)
    monkeypatch.setattr(speech, "surasura_found", lambda: False)
    from hato import present
    monkeypatch.setattr(present, "read_tracks", lambda video, lang, reader=None: present.Tracks(present.FETCH, u""))
    return tmp_path


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _server(files, cut_at=None):
    u"""A `get` that serves {url: bytes} from a byte offset, honouring Range; `cut_at` drops the connection once."""
    state = {"cut": False, "starts": []}

    def get(url, start):
        state["starts"].append(start)
        data = files[url]
        yield bool(start)
        sent = start
        while sent < len(data):
            if cut_at is not None and not state["cut"] and sent >= cut_at:
                state["cut"] = True
                raise speech.SpeechError(u"the download stopped (ConnectionResetError)")
            yield data[sent:sent + 7]
            sent += 7
    get.state = state
    return get


def _pin(name, data, url=None):
    return speech.Pin(name, url or u"https://example.invalid/" + name, len(data), _sha(data))


# ---------------------------------------------------------------------------
# the pins
# ---------------------------------------------------------------------------

def test_every_model_download_is_pinned_by_https_size_and_sha256():
    u"""19b -- hato's signed release vouches for every byte: a pin without a size or a sha256 would be a download
    nothing checks."""
    for part, spec in speech.PARTS.items():
        for pin in spec["pins"]:
            assert pin.url.startswith(u"https://"), (part, pin)
            assert pin.size > 0 and len(pin.sha256) == 64 and int(pin.sha256, 16) >= 0, (part, pin)
    hosts = {pin.url.split(u"/")[2] for spec in speech.PARTS.values() for pin in spec["pins"]}
    assert hosts == {u"github.com", u"huggingface.co", u"files.pythonhosted.org"}, u"19j: exactly these hosts"
    assert u"/resolve/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/" in speech.PARTS[speech.ACCURATE]["pins"][0].url, \
        u"Hugging Face at a fixed commit, never `main`"
    assert speech.ADDON_PIN.url.startswith(u"https://github.com/SonicSandbox/hato/releases/download/")


def test_an_unpublished_add_on_pin_refuses_before_any_download(root):
    u"""Until the release pins the add-on's sha256, `install` says so -- it never fetches an unchecked exe."""
    if speech.ADDON_PIN.sha256:
        pytest.skip(u"the add-on is pinned")
    with pytest.raises(speech.SpeechError, match=u"isn't published"):
        speech.install(speech.FAST, get=lambda *_a: pytest.fail(u"fetched"))


# ---------------------------------------------------------------------------
# fetch: resumed, checked whole, thrown away when wrong
# ---------------------------------------------------------------------------

def test_a_download_cut_short_resumes_from_its_part_and_is_checked_whole(root):
    data = os.urandom(1000)
    pin = _pin(u"model.bin", data)
    get = _server({pin.url: data}, cut_at=490)
    with pytest.raises(speech.SpeechError):
        speech.fetch(pin, get=get)
    part = speech.downloads_dir() / u"model.bin.part"
    kept = part.stat().st_size
    assert 0 < kept < 1000, u"what came before the cut is kept"
    seen = []
    got = speech.fetch(pin, get=get, progress=lambda done, total: seen.append((done, total)))
    assert got.read_bytes() == data and not part.exists()
    assert get.state["starts"] == [0, kept], u"the second asks from where the part ended"
    assert seen[0][0] > kept and seen[-1] == (1000, 1000), u"its progress goes on from the part"


def test_a_download_whose_sha256_is_wrong_is_thrown_away_and_said(root):
    data = os.urandom(300)
    pin = speech.Pin(u"x.bin", u"https://example.invalid/x.bin", 300, _sha(b"something else"))
    with pytest.raises(speech.SpeechError, match=u"thrown away"):
        speech.fetch(pin, get=_server({pin.url: data}))
    assert not list(speech.downloads_dir().iterdir()), u"no part, no file"


def test_a_download_running_past_its_pinned_size_is_thrown_away(root):
    u"""More bytes than the pin names is another file: never kept, never cut to fit."""
    data = os.urandom(500)
    pin = speech.Pin(u"x.bin", u"https://example.invalid/x.bin", 200, _sha(data[:200]))
    seen = []
    with pytest.raises(speech.SpeechError, match=u"thrown away"):
        speech.fetch(pin, get=_server({pin.url: data}), progress=lambda done, total: seen.append(done))
    assert not list(speech.downloads_dir().iterdir())
    assert seen and max(seen) <= 200, u"never a byte written past the pinned size: %s" % max(seen)


def test_no_network_refuses_before_a_socket(root):
    pin = speech.PARTS[speech.FAST]["pins"][0]
    with pytest.raises(speech.SpeechError, match=u"network is switched off"):
        speech.fetch(pin)


# ---------------------------------------------------------------------------
# unpacking: every member judged before a byte is written
# ---------------------------------------------------------------------------

def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members:
            z.writestr(name, data)
    return buf.getvalue()


@pytest.mark.parametrize("bad", [u"hato-speech/../../evil.dll", u"elsewhere/hato-speech.exe", u"/abs/evil.exe",
                                 u"C:/evil.exe"])
def test_an_add_on_zip_with_a_member_outside_its_folder_unpacks_nothing(root, tmp_path, bad):
    path = tmp_path / "addon.zip"
    path.write_bytes(_zip([(u"hato-speech/hato-speech.exe", b"MZ"), (bad, b"x")]))
    with pytest.raises(speech.SpeechError):
        speech.unpack_zip(path, tmp_path / "addon")
    assert not (tmp_path / "addon").exists() and not (tmp_path / "addon.part").exists()


def test_the_models_tar_gives_only_the_two_files_hato_keeps(root, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as t:
        for name, data in ((u"sherpa/model.int8.onnx", b"onnx"), (u"sherpa/tokens.txt", b"tok"),
                           (u"sherpa/test_wavs/0.wav", b"RIFF")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    path = tmp_path / "m.tar.bz2"
    path.write_bytes(buf.getvalue())
    speech.unpack_tar(path, tmp_path / "parakeet-ja", (u"model.int8.onnx", u"tokens.txt"))
    assert sorted(os.listdir(str(tmp_path / "parakeet-ja"))) == [u"model.int8.onnx", u"tokens.txt"]


def test_a_tar_holding_a_link_unpacks_nothing(root, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        info = tarfile.TarInfo(u"sherpa/model.int8.onnx")
        info.type, info.linkname = tarfile.SYMTYPE, u"C:/Windows/System32/x.dll"
        t.addfile(info)
    path = tmp_path / "m.tar"
    path.write_bytes(buf.getvalue())
    with pytest.raises(speech.SpeechError, match=u"link"):
        speech.unpack_tar(path, tmp_path / "parakeet-ja", (u"model.int8.onnx",))
    assert not (tmp_path / "parakeet-ja").exists()


def test_nvidias_wheels_give_only_their_bin_dlls_flat(root, tmp_path):
    path = tmp_path / "w.whl"
    path.write_bytes(_zip([(u"nvidia/cublas/bin/cublas64_12.dll", b"dll"), (u"nvidia/cublas/include/x.h", b"h"),
                           (u"nvidia/cublas/__init__.py", b""), (u"nvidia_cublas_cu12.dist-info/METADATA", b"m")]))
    speech.unpack_wheels([path], tmp_path / "gpu")
    assert os.listdir(str(tmp_path / "gpu")) == [u"cublas64_12.dll"]


# ---------------------------------------------------------------------------
# install / remove
# ---------------------------------------------------------------------------

def _published(monkeypatch):
    u"""A small add-on zip and a small Fast model, pinned and served locally."""
    addon = _zip([(u"hato-speech/hato-speech.exe", b"MZ"), (u"hato-speech/silero_vad.onnx", b"vad")])
    monkeypatch.setattr(speech, "ADDON_PIN", _pin(u"hato-speech-1.0.0-windows-x64.zip", addon))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as t:
        for name, data in ((u"p/model.int8.onnx", b"onnx"), (u"p/tokens.txt", b"tok")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    tar = buf.getvalue()
    parts = dict(speech.PARTS)
    parts[speech.FAST] = dict(parts[speech.FAST], pins=(_pin(u"p.tar.bz2", tar),))
    monkeypatch.setattr(speech, "PARTS", parts)
    return _server({speech.ADDON_PIN.url: addon, parts[speech.FAST]["pins"][0].url: tar})


def test_install_brings_the_add_on_and_the_picked_model_and_nothing_else(root, monkeypatch):
    get = _published(monkeypatch)
    assert speech.install(speech.FAST, get=get) == [speech.ADDON, speech.FAST]
    assert speech.installed(speech.ADDON) and speech.installed(speech.FAST)
    assert not speech.installed(speech.ACCURATE) and not speech.installed(speech.GPU)
    assert speech.picked() == speech.FAST
    assert not list(speech.downloads_dir().glob(u"*")), u"the downloads were only a means"
    assert speech.install(speech.FAST, get=lambda *_a: pytest.fail(u"fetched again")) == []


def test_a_copy_another_program_holds_installs_nothing(root, monkeypatch):
    monkeypatch.setenv("HATO_HELD_BY", "surasura")
    with pytest.raises(speech.SpeechError, match=u"kept by another program"):
        speech.install(speech.FAST, get=lambda *_a: pytest.fail(u"fetched"))


def test_the_pick_lives_in_speechs_own_folder_never_config_toml(root, monkeypatch):
    u"""⛔ Go back to an older hato reads nothing it doesn't know (LEDGER-HOT): no key in config.toml."""
    speech.pick(speech.ACCURATE)
    assert speech.picked() == speech.ACCURATE
    assert speech.choice_path().parent == speech.root()
    from hato import paths
    config = paths.config_path()[0]
    assert not config.exists() or u"speech" not in config.read_text(encoding="utf-8")


def test_remove_frees_hatos_own_files_and_leaves_every_subtitle_beside_the_videos(root, monkeypatch, tmp_path):
    get = _published(monkeypatch)
    speech.install(speech.FAST, get=get)
    beside = tmp_path / "Anime" / ("Show - 01" + speech.SUFFIX)
    beside.parent.mkdir(parents=True)
    beside.write_text(JA, encoding="utf-8")
    speech._remember(beside, speech.FAST)
    assert speech.remove() > 0
    assert not speech.installed(speech.ADDON) and not speech.installed(speech.FAST)
    assert beside.read_text(encoding="utf-8") == JA
    # ⚠ A19-6 -- the record of what hato made, and the pick, stay: 19f still works after a Remove
    assert speech.made_by_hato(beside) and speech.picked() == speech.FAST


# ---------------------------------------------------------------------------
# plan + make
# ---------------------------------------------------------------------------

def _media(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"\x1a\x45\xdf\xa3 fake")
    return folder


def test_the_made_name_is_the_videos_stem_and_the_from_audio_mark():
    u"""19e -- the marker Surasura and tsubasa already read: `<stem>.ja.from-audio.srt`."""
    assert speech.SUFFIX == u".ja.from-audio.srt"
    assert speech.target_of(u"D:/Anime/Show/Show - 01.mkv").name == u"Show - 01.ja.from-audio.srt"


def test_a_video_with_a_real_japanese_subtitle_is_never_given_a_made_one(root, tmp_path):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    (folder / u"Show - 02.ja.srt").write_text(JA, encoding="utf-8")
    got = {os.path.basename(m): why for m, _t, why in speech.plan(speech.media_under([folder]))}
    assert got == {u"Show - 01.mkv": None, u"Show - 02.mkv": u"present"}


def test_two_videos_that_would_make_one_name_both_refuse(root, tmp_path):
    u"""LEDGER-HOT: never let two videos target one output path -- `Show - 01.mkv` + `Show - 01.mp4`."""
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 01.mp4", u"Show - 02.mkv")
    got = {os.path.basename(m): why for m, _t, why in speech.plan(speech.media_under([folder]))}
    assert got == {u"Show - 01.mkv": u"clash", u"Show - 01.mp4": u"clash", u"Show - 02.mkv": None}


def test_with_save_beside_off_the_made_file_goes_to_hatos_own_folder(root, tmp_path):
    video = str(_media(tmp_path / "Show", u"Show - 01.mkv") / u"Show - 01.mkv")
    target = speech.target_of(video, beside=False)
    from hato import paths
    assert str(target).startswith(str(paths.own_subs_dir())) and target.name == u"Show - 01" + speech.SUFFIX


def test_media_under_takes_videos_and_audio_skips_the_rest_and_skipped_folders(root, tmp_path):
    folder = _media(tmp_path / "Lib", u"a.mkv", u"b.mp3", u"c.srt", u"d.txt")
    _media(folder / "Extras", u"e.mkv")
    _media(folder / ".hidden", u"f.mkv")
    names = [os.path.basename(p) for p in speech.media_under([folder], skip=[str(folder / "Extras")])]
    assert names == [u"a.mkv", u"b.mp3"]


class FakeAddon(object):
    u"""The add-on's process, stood in: NDJSON on stdout, the SRT written where `--output` says (as the real one)."""

    def __init__(self, outcome=u"made", text=JA, lines=3, on_start=None):
        self.outcome, self.text, self.lines, self.on_start = outcome, text, lines, on_start
        self.argvs = []
        self.killed = 0

    def __call__(self, argv):
        self.argvs.append(argv)
        output = argv[argv.index(u"--output") + 1]
        if self.on_start:
            self.on_start(argv)
        out = [json.dumps({u"type": u"progress", u"stage": u"listening", u"done": n, u"total": 3}).encode() + b"\n"
               for n in range(self.lines)]
        if self.outcome == u"made":
            with open(output, "w", encoding="utf-8") as f:
                f.write(self.text)
        if self.outcome is not None:
            out.append(json.dumps({u"type": u"result", u"outcome": self.outcome, u"why": u"boom"}).encode() + b"\n")
        fake = self

        class Process(object):
            stdout = iter(out)

            def wait(self):
                return 0

            def poll(self):
                return 0

            def kill(self):
                fake.killed += 1
        return Process()


@pytest.fixture
def ready(root, monkeypatch):
    u"""The add-on and both models count as installed (no bytes of them here)."""
    monkeypatch.setattr(speech, "installed", lambda part: part in (speech.ADDON, speech.FAST, speech.ACCURATE))
    return root


def _leftovers(folder, video_names):
    return sorted(set(os.listdir(str(folder))) - set(video_names))


def test_make_places_the_made_file_whole_beside_the_video_and_records_it(ready, tmp_path):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    addon = FakeAddon()
    rows = speech.make([folder], model=speech.FAST, spawn=addon)
    made = folder / (u"Show - 01" + speech.SUFFIX)
    assert [r["outcome"] for r in rows] == [u"made"] and rows[0]["subtitle"] == str(made)
    assert made.read_text(encoding="utf-8") == JA, u"⛔ no text of ours in it"
    assert _leftovers(folder, [u"Show - 01.mkv"]) == [made.name], u"nothing else beside the video, no temp"
    assert speech.made_by_hato(made)
    assert addon.argvs[0][addon.argvs[0].index(u"--output") + 1].startswith(str(speech.downloads_dir())), \
        u"the add-on writes into hato's cache, never beside the video"


@pytest.mark.parametrize("outcome", [u"no_speech", u"unreadable", u"error", None])
def test_nothing_is_written_beside_a_video_the_add_on_made_nothing_for(ready, tmp_path, outcome):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    rows = speech.make([folder], model=speech.FAST, spawn=FakeAddon(outcome=outcome))
    assert rows[0]["outcome"] == (outcome or u"error")
    assert _leftovers(folder, [u"Show - 01.mkv"]) == []
    if rows[0]["outcome"] == u"error":
        assert rows[0]["why"]


def test_a_file_that_appears_at_the_name_while_it_listens_is_never_written_over(ready, tmp_path):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    made = folder / (u"Show - 01" + speech.SUFFIX)
    rows = speech.make([folder], model=speech.FAST,
                       spawn=FakeAddon(on_start=lambda _a: made.write_text(u"theirs", encoding="utf-8")))
    assert rows[0]["outcome"] == u"already" and made.read_text(encoding="utf-8") == u"theirs"
    assert not speech.made_by_hato(made)


def test_a_stop_ends_the_add_on_and_leaves_nothing_beside_the_video(ready, tmp_path):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    addon = FakeAddon(lines=5)
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 2                     # mid-way through the first file
    rows = speech.make([folder], model=speech.FAST, spawn=addon, should_stop=should_stop)
    assert [r["outcome"] for r in rows] == [u"stopped", u"stopped"] and addon.killed >= 1
    assert _leftovers(folder, [u"Show - 01.mkv", u"Show - 02.mkv"]) == []


def test_make_without_the_add_on_says_install_first(root, tmp_path):
    with pytest.raises(speech.SpeechError, match=u"install"):
        speech.make([_media(tmp_path / "Show", u"Show - 01.mkv")], model=speech.FAST, spawn=FakeAddon())


def test_the_nvidia_pack_is_handed_to_more_accurate_only_when_installed(ready, monkeypatch):
    argv = speech.addon_argv(u"v.mkv", u"o.srt", speech.ACCURATE)
    assert u"--gpu" not in argv
    monkeypatch.setattr(speech, "installed", lambda part: True)
    assert u"--gpu" in speech.addon_argv(u"v.mkv", u"o.srt", speech.ACCURATE)
    assert u"--gpu" not in speech.addon_argv(u"v.mkv", u"o.srt", speech.FAST)


# ---------------------------------------------------------------------------
# 19f: a real subtitle later
# ---------------------------------------------------------------------------

def test_a_made_file_hato_made_goes_to_the_trash_when_a_real_one_is_kept(ready, tmp_path):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    speech.make([folder], model=speech.FAST, spawn=FakeAddon())
    trashed = []
    video = str(folder / u"Show - 01.mkv")
    assert speech.retire(video, trash=trashed.append) == str(folder / (u"Show - 01" + speech.SUFFIX))
    assert len(trashed) == 1 and not speech.made_by_hato(trashed[0])


def test_a_made_file_someone_changed_or_hato_never_made_stays(ready, tmp_path):
    u"""⛔ Surasura's own copy beside a video carries the same name -- hato never trashes what it didn't make."""
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    speech.make([str(folder / u"Show - 01.mkv")], model=speech.FAST, spawn=FakeAddon())
    (folder / (u"Show - 01" + speech.SUFFIX)).write_text(JA + u"\n2\n00:00:04,000 --> 00:00:05,000\n直した\n",
                                                         encoding="utf-8")
    (folder / (u"Show - 02" + speech.SUFFIX)).write_text(JA, encoding="utf-8")      # Surasura's
    trashed = []
    for n in (u"01", u"02"):
        assert speech.retire(str(folder / (u"Show - %s.mkv" % n)), trash=trashed.append) is None
    assert trashed == []


def test_the_real_trash_is_restorable_and_never_raises(ready, tmp_path, monkeypatch):
    monkeypatch.setenv("TSUBASA_NO_OS_TRASH", "1")          # tsubasa's local trash: a move, never a delete
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    speech.make([folder], model=speech.FAST, spawn=FakeAddon())
    moved = speech.retire(str(folder / u"Show - 01.mkv"))
    assert moved and not os.path.exists(moved)
    kept = [os.path.join(w, f) for w, _d, fs in os.walk(str(tmp_path)) for f in fs if f.endswith(speech.SUFFIX)]
    assert kept and open(kept[0], encoding="utf-8").read() == JA, u"the bytes are in the trash, whole"
    assert speech.retire(str(tmp_path / "nowhere" / "x.mkv")) is None


# ---------------------------------------------------------------------------
# the add-on's pure half
# ---------------------------------------------------------------------------

def test_the_japanese_audio_track_is_listened_to_else_the_first():
    assert speech_engine.pick_stream([(1, u"eng"), (2, u"jpn"), (3, u"ja")]) == 2
    assert speech_engine.pick_stream([(1, u"eng"), (2, None)]) == 1
    assert speech_engine.pick_stream([]) is None


def test_cues_end_at_a_sentence_never_run_past_seven_seconds_or_across_a_pause():
    toks = [(0.0, None, u"杜子春"), (0.5, None, u"は"), (0.8, None, u"立った。"), (1.2, None, u"ある"),
            (5.0, None, u"日"), (5.3, None, u"の")]                  # a 3.8 s pause before 日
    pieces = [(0.0, 6.0, toks)]
    cues = speech_engine.cues_from_tokens(pieces)
    assert [c[2] for c in cues] == [u"杜子春は立った。", u"ある", u"日の"]
    long = [(n * 0.5, None, u"あ") for n in range(30)]               # 15 s of speech, no sentence end
    assert all(e - s <= speech_engine.MAX_CUE_S + 1e-9 for s, e, _t in speech_engine.cues_from_tokens(
        [(0.0, 15.0, long)]))


def test_the_srt_holds_only_what_was_heard_in_order_and_never_overlapping():
    text = speech_engine.srt([(1.0, 3.0, u"一。"), (2.5, 4.0, u"二。"), (4.0, 4.0, u"三。")])
    assert text == (u"1\n00:00:01,000 --> 00:00:03,000\n一。\n\n2\n00:00:03,000 --> 00:00:04,000\n二。\n\n"
                    u"3\n00:00:04,000 --> 00:00:04,100\n三。\n")


def test_the_add_on_never_writes_over_a_file(tmp_path):
    path = tmp_path / "x.srt"
    path.write_text(u"theirs", encoding="utf-8")
    with pytest.raises(FileExistsError):
        speech_engine.write_whole(str(path), JA)
    assert path.read_text(encoding="utf-8") == u"theirs" and os.listdir(str(tmp_path)) == [u"x.srt"]


def test_the_add_ons_answer_for_a_missing_model_is_one_result_line(tmp_path, capsys):
    assert speech_engine.main([u"run", u"--model", u"fast", u"--models", str(tmp_path), u"--input", u"x.mkv",
                               u"--output", str(tmp_path / "o.srt")]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines == [{u"type": u"result", u"outcome": u"no_model", u"model": u"fast"}]


# ---------------------------------------------------------------------------
# the verb
# ---------------------------------------------------------------------------

class Args(object):
    def __init__(self, **k):
        self.__dict__.update(dict(action=u"status", paths=[], model=None, gpu=False, json=True, progress=False,
                                  cancel_file=None, list=None), **k)


def test_status_says_what_is_there_and_each_download_size(root, capsys):
    assert command.run(Args()) == 0
    said = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert said["ok"] and not said["addon"]["installed"] and said["picked"] == speech.FAST
    assert said["models"][speech.FAST]["download"] == 489389564
    assert said["models"][speech.ACCURATE]["download"] == sum(p.size for p in speech.PARTS[speech.ACCURATE]["pins"])


def test_install_and_make_refuse_without_what_they_need(root, capsys):
    assert command.run(Args(action=u"install")) == command.EXIT_USAGE
    assert command.run(Args(action=u"make")) == command.EXIT_USAGE
    assert command.run(Args(action=u"make", paths=[u"x"], model=speech.GPU)) == command.EXIT_USAGE


def test_make_stops_at_the_cancel_file_and_counts_each_outcome(ready, tmp_path, capsys, monkeypatch):
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    cancel = tmp_path / "cancel"
    monkeypatch.setattr(speech, "_spawn", FakeAddon(on_start=lambda _a: cancel.write_text(u"")))
    assert command.run(Args(action=u"make", paths=[str(folder)], model=speech.FAST,
                            cancel_file=str(cancel))) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [ln["outcome"] for ln in lines if ln["type"] == u"speech"] == [u"stopped", u"stopped"]
    assert lines[-1]["counts"] == {u"stopped": 2}
    assert _leftovers(folder, [u"Show - 01.mkv", u"Show - 02.mkv"]) == []


# ---------------------------------------------------------------------------
# the adversary pass (ADVERSARY-2026-11-12.md, A19-*)
# ---------------------------------------------------------------------------

def test_a_416_to_a_resume_throws_the_part_away_and_starts_once_from_nothing(root):
    u"""A19-15 -- a `.part` longer than the server's file (a replaced file): never the same error every try."""
    data = os.urandom(300)
    pin = _pin(u"m.bin", data)
    part = speech.downloads_dir() / u"m.bin.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(os.urandom(120))
    starts = []

    def get(url, start):
        starts.append(start)
        if start:
            raise speech.RangeRefused()
        yield False
        yield data
    assert speech.fetch(pin, get=get).read_bytes() == data and starts == [120, 0]


def test_install_and_remove_wait_for_no_one_while_subtitles_are_being_made(root, monkeypatch):
    u"""A19-14 -- never a model replaced or deleted under a run that is using it: the make's lock refuses."""
    from hato.runlock import RunLock
    get = _published(monkeypatch)
    with RunLock(speech.root() / speech.LOCK_NAME):
        with pytest.raises(speech.SpeechError, match=u"being made from audio"):
            speech.install(speech.FAST, get=get)
        with pytest.raises(speech.SpeechError, match=u"being made from audio"):
            speech.remove()


def test_a_video_with_a_japanese_text_track_inside_is_present(root, tmp_path):
    u"""A19-7 -- hato's own read rule: never an hour of listening for a subtitle the video already carries."""
    from hato import present
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv", u"Show - 03.mp3")
    inside = {u"Show - 01.mkv": present.EMBEDDED}
    got = {os.path.basename(m): why for m, _t, why in speech.plan(
        speech.media_under([folder]), tracks=lambda v: inside.get(os.path.basename(v), present.FETCH))}
    assert got == {u"Show - 01.mkv": u"present", u"Show - 02.mkv": None, u"Show - 03.mp3": None}


def test_one_file_whose_sibling_shares_its_stem_refuses_though_the_sibling_is_not_in_the_run(root, tmp_path):
    u"""A19-8 -- `Show - 01.mp4` picked alone beside `Show - 01.mkv`: one made name would serve both."""
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 01.mp4", u"Show - 02.mkv")
    got = speech.plan([str(folder / u"Show - 01.mp4"), str(folder / u"Show - 02.mkv")])
    assert [(os.path.basename(m), why) for m, _t, why in got] == [(u"Show - 01.mp4", u"clash"),
                                                                 (u"Show - 02.mkv", None)]


def test_a_real_subtitle_that_arrives_while_it_listens_wins(ready, tmp_path):
    u"""A19-9 -- asked again before placing: a daily run kept `Show - 01.ja.srt` meanwhile; nothing made beside it."""
    folder = _media(tmp_path / "Show", u"Show - 01.mkv")
    real = folder / u"Show - 01.ja.srt"
    rows = speech.make([folder], model=speech.FAST,
                       spawn=FakeAddon(on_start=lambda _a: real.write_text(JA, encoding="utf-8")))
    assert [r["outcome"] for r in rows] == [u"present"]
    assert _leftovers(folder, [u"Show - 01.mkv"]) == [real.name]


def test_a_card_cuda_cant_use_falls_back_to_the_cpu_for_the_rest_of_the_run(root, monkeypatch, tmp_path):
    u"""A19-10 -- an error with the NVIDIA pack: that file again on the CPU, and every file after it."""
    monkeypatch.setattr(speech, "installed", lambda part: True)
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    seen = []

    def spawn(argv):
        seen.append(u"--gpu" in argv)
        return FakeAddon(outcome=u"error" if u"--gpu" in argv else u"made")(argv)
    rows = speech.make([folder], model=speech.ACCURATE, spawn=spawn)
    assert [r["outcome"] for r in rows] == [u"made", u"made"] and seen == [True, False, False]


def test_make_reads_its_paths_from_a_list_file_one_a_line(ready, tmp_path, capsys, monkeypatch):
    u"""A19-2 -- the window's few hundred waiting episodes travel in a file, never on a command line."""
    folder = _media(tmp_path / "Show", u"Show - 01.mkv", u"Show - 02.mkv")
    listed = tmp_path / "list.txt"
    listed.write_text(u"%s\n\n%s\n" % (folder / u"Show - 01.mkv", folder / u"Show - 02.mkv"), encoding="utf-8")
    monkeypatch.setattr(speech, "_spawn", FakeAddon())
    assert command.run(Args(action=u"make", list=str(listed), model=speech.FAST)) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [ln["outcome"] for ln in lines if ln["type"] == u"speech"] == [u"made", u"made"]
    assert command.run(Args(action=u"make", list=str(tmp_path / "gone.txt"))) == command.EXIT_USAGE


def test_an_untimed_keep_never_sends_the_made_file_to_the_trash(root, monkeypatch):
    u"""A19-4 -- a Layer 15 file nobody timed never displaces one made from the video's own audio; a timed one
    does, and the run's report says where it went (A19-5)."""
    from types import SimpleNamespace as NS
    from hato import pipeline
    asked = []
    monkeypatch.setattr(speech, "retire", lambda video, beside=True: asked.append(video) or u"x" + speech.SUFFIX)
    for untimed, retired in (({u"tier": u"same-provider"}, False), (None, True)):
        asked[:] = []
        run = NS(_not_taken={}, report=NS(results=[], notes=[]), progress=lambda *a, **k: None, handoff=None,
                 s=NS(write_beside_video=True), where=u"jimaku")          # LAYER 20: the run's source
        result = NS(not_taken=None, video=u"D:/Anime/Show - 01.mkv", wrote=True, skip=None, untimed=untimed,
                    source=None)
        pipeline._Run._keep_result(run, NS(results=[]), result)
        assert bool(asked) is retired
        assert bool(run.report.notes) is retired and (not retired or u"went to the trash" in run.report.notes[0])



@pytest.mark.skipif(os.name != "nt", reason=u"the add-on is Windows-only: its rename is the last wall there")
def test_a_file_that_appears_while_the_add_on_writes_is_never_written_over(tmp_path, monkeypatch):
    u"""M19-10's wall: the check before writing AND the rename after (Windows refuses an existing target) -- a file
    that appears between the two is never replaced, and nothing of the add-on's is left."""
    path = tmp_path / "x.srt"
    real = os.fsync

    def appears(fd):
        real(fd)
        path.write_text(u"theirs", encoding="utf-8")
    monkeypatch.setattr(speech_engine.os, "fsync", appears)
    with pytest.raises(FileExistsError):
        speech_engine.write_whole(str(path), JA)
    assert path.read_text(encoding="utf-8") == u"theirs" and os.listdir(str(tmp_path)) == [u"x.srt"]
