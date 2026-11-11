# -*- coding: utf-8 -*-
u"""hato's speech add-on (RUNBOOK Layer 19a): a video's or audio file's Japanese speech -> a timed SRT.

⛔ NOT PART OF hato's ZIP. Frozen on its own as `hato-speech.exe` (packaging/hato-speech.spec), which hato downloads
only after the learner's yes and keeps in its data folder (`speech\\addon\\`). ⛔ IT IMPORTS NOTHING OF hato's: numpy,
PyAV (the audio), sherpa-onnx (the voice finder for BOTH models, and the *Fast* model) and faster-whisper /
CTranslate2 (the *More accurate* model) only -- and no network code at all (`entry_speech.py`).

    hato-speech probe
    hato-speech run --model fast|accurate --models DIR --input MEDIA --output FILE.srt
                    [--device auto|cpu] [--gpu DIR] [--threads N]

It answers on stdout, one JSON object a line (NDJSON): `progress` lines, then exactly ONE `result` line, the last thing
it prints. `outcome`:
    made        FILE written whole (temp beside it + rename; never over a file that is there)
    no_speech   nothing heard: no file
    unreadable  no audio it can read: no file
    no_model    the model isn't in DIR
    error       exit 1, the reason in `why` (the trace on stderr)
A cancel is the parent ending the process: the SRT is never half-written (its temp file is removed when it can be;
hato writes FILE in its own cache and places it itself, 19d).

⭐ MEASURED (2026-11-12, the 3900X, the study's CC0 clip, CER kana): Fast 5.5 %, More accurate 3.2 % (RUNBOOK
Layer 19). ⭐ ONE VOICE FINDER (sherpa-onnx's Silero) for both: faster-whisper's own `vad_filter` needs the
`onnxruntime` package, whose `onnxruntime.dll` collides with sherpa-onnx's own in one frozen program.
"""
import argparse
import json
import os
import sys
import time

VERSION = "1.0.0"
PROTOCOL = 1                     # hato reads `probe`'s protocol: another one is an add-on to update
RATE = 16000
MODELS = ("fast", "accurate")
FAST_DIR = "parakeet-ja"         # sherpa-onnx's NeMo Parakeet TDT-CTC 0.6B ja, int8: model.int8.onnx, tokens.txt
ACCURATE_DIR = "whisper-turbo"   # faster-whisper's large-v3-turbo, CTranslate2: model.bin, config.json, tokenizer.json…
FAST_FILES = ("model.int8.onnx", "tokens.txt")
ACCURATE_FILES = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json", "vocabulary.json")
VAD_FILE = "silero_vad.onnx"     # shipped inside the add-on, beside the exe (MIT)
JA_TAGS = ("ja", "jpn", "jp", "japanese")
MAX_HOURS = 4                    # an episode, a film, a long chapter; never a whole audiobook at once (A19-11)
# The cues: one sentence where it can be, never longer than MAX_CUE_S, never across a pause over GAP_S
MAX_CUE_S = 7.0
GAP_S = 0.8
TOKEN_MAX_S = 1.0                # a token whose model gives no end lasts at most this long
ENDS = u"。！？!?"
FAST_SPEECH_S = 8.0              # Parakeet reads one voice region at a time: short ones
WHISPER_SPEECH_S = 30.0          # Whisper reads 30 s windows
WHISPER_SILENCE = 1.0            # measured: 3.2 % at 1.0 s, 3.4 % at 2.0 s (faster-whisper's own), 3.8 % at 0.3 s
SPEECH_PAD = 0.4                 # faster-whisper's own VAD pads each stretch of speech by 400 ms


class Unreadable(Exception):
    pass


class TooLong(Exception):
    u"""Over MAX_HOURS of audio: a 12-hour audiobook is ~3 GB of samples, copied on the way (A19-11)."""


def emit(kind, **fields):
    sys.stdout.write(json.dumps(dict(type=kind, **fields), ensure_ascii=False) + "\n")
    sys.stdout.flush()


# --- the audio ------------------------------------------------------------------------------------------------- #

def pick_stream(streams):
    u"""The audio stream to listen to: the first tagged Japanese, else the first; None when there is none.
    `streams`: (index, language tag or None) in the file's order."""
    streams = list(streams)
    for index, lang in streams:
        if str(lang or "").strip().casefold() in JA_TAGS:
            return index
    return streams[0][0] if streams else None


def read_audio(path, progress=None):
    u"""The file's chosen audio track as 16 kHz mono float32 (numpy). Raises `Unreadable`.

    ⚠ A file cut short (a download that stopped) is listened to as far as it reads; one that reads nothing is
    `Unreadable`."""
    import av
    import numpy as np
    try:
        container = av.open(path)
    except Exception as e:                                   # PyAV raises its own error kinds for every bad file
        raise Unreadable(type(e).__name__)
    try:
        audio = [s for s in container.streams if s.type == "audio"]
        index = pick_stream((s.index, s.metadata.get("language")) for s in audio)
        if index is None:
            raise Unreadable("no audio track")
        stream = next(s for s in audio if s.index == index)
        total = (float(stream.duration * stream.time_base) if stream.duration else
                 (container.duration / 1e6 if container.duration else None))
        if total and total > MAX_HOURS * 3600:
            raise TooLong()
        resampler = av.AudioResampler(format="flt", layout="mono", rate=RATE)
        parts, last = [], 0.0
        try:
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1))
                if frame.time is not None and frame.time > MAX_HOURS * 3600:
                    raise TooLong()                     # a length the container didn't say
                if progress and frame.time is not None and frame.time - last >= 30:
                    last = frame.time
                    progress("reading", frame.time, total)
            for out in resampler.resample(None):
                parts.append(out.to_ndarray().reshape(-1))
        except TooLong:
            raise
        except Exception as e:
            if not parts:
                raise Unreadable(type(e).__name__)
        # ⚠ A19-11: one copy, not three -- the parts let go as soon as they are joined
        samples = np.concatenate(parts).astype(np.float32, copy=False) if parts else np.zeros(0, np.float32)
        del parts
    finally:
        container.close()
    if not len(samples):
        raise Unreadable("no audio in its track")
    return samples


# --- where the voice is ---------------------------------------------------------------------------------------- #

def voice(samples, vad_model, max_speech, min_silence=0.3):
    u"""Silero VAD (sherpa-onnx) -> [(start sample, end sample)] of speech, in order."""
    import sherpa_onnx
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = vad_model
    cfg.silero_vad.min_silence_duration = min_silence
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = max_speech
    cfg.sample_rate = RATE
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=max(60, int(max_speech * 4)))
    win = cfg.silero_vad.window_size
    found = []

    def drain():
        while not vad.empty():
            found.append((vad.front.start, vad.front.start + len(vad.front.samples)))
            vad.pop()
    for i in range(0, len(samples), win):
        vad.accept_waveform(samples[i:i + win])
        drain()
    vad.flush()
    drain()
    return found


def padded(regions, length):
    u"""Each region widened by SPEECH_PAD (never past the audio), overlapping ones joined."""
    pad = int(SPEECH_PAD * RATE)
    out = []
    for a, b in regions:
        a, b = max(0, a - pad), min(length, b + pad)
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# --- the cues -------------------------------------------------------------------------------------------------- #

def cues_from_tokens(pieces):
    u"""Timed pieces -> [(start s, end s, text)].

    `pieces`: (start s, end s, tokens) per voice region (Parakeet) or segment (Whisper), in order; its tokens
    [(start s, end s or None, text)] -- a token's end, when its model gives none, is the next token's start. A cue
    ends at a sentence end, before MAX_CUE_S, or at a gap over GAP_S, and may run on into the next piece."""
    cues = []
    cur = None
    for _start, end, toks in pieces:
        for i, (t, t_end, tok) in enumerate(toks):
            if t_end is None:                   # Parakeet gives starts only: a token lasts until the next one,
                #                                     never past TOKEN_MAX_S (a pause stays a pause)
                t_end = min(toks[i + 1][0] if i + 1 < len(toks) else end, t + TOKEN_MAX_S)
            t_end = min(max(t_end, t), end)
            if cur and (t - cur[1] > GAP_S or t_end - cur[0] > MAX_CUE_S):
                cues.append(cur)
                cur = None
            if cur is None:
                if not tok.strip():
                    continue
                cur = [t, t_end, u""]
            cur[1], cur[2] = t_end, cur[2] + tok
            if tok.strip() and tok.strip()[-1] in ENDS:
                cues.append(cur)
                cur = None
    if cur:
        cues.append(cur)
    out = []
    for s, e, text in cues:
        text = text.replace(chr(0x2581), u" ").strip()      # chr(0x2581): sentencepiece's word mark
        if text:
            out.append((s, max(e, s + 0.3), text))
    return out


def srt_time(x):
    ms = int(round(max(0.0, x) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return u"%02d:%02d:%02d,%03d" % (h, m, s, ms)


def srt(cues):
    u"""Cues -> SRT text. ⛔ NO TEXT OF OURS IN IT (19e): no "made by" line -- a card shows every line it is cut
    from. The `.from-audio` name is the marker. Cues never overlap and never run backwards."""
    lines = []
    last = 0.0
    for n, (s, e, text) in enumerate(cues, 1):
        s = max(s, last)
        e = max(e, s + 0.1)
        last = e
        lines.append(u"%d\n%s --> %s\n%s\n" % (n, srt_time(s), srt_time(e), text))
    return u"\n".join(lines)


def write_whole(path, text):
    u"""Temp beside it, then rename. ⛔ Never over a file that is there (FileExistsError)."""
    if os.path.exists(path):
        raise FileExistsError(path)
    tmp = u"%s.%d.part" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)                     # ⚠ rename, not replace: Windows refuses an existing target
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --- the models ------------------------------------------------------------------------------------------------ #

def vad_path():
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    return os.environ.get("HATO_SPEECH_VAD") or os.path.join(here, VAD_FILE)


def has_model(models, which):
    folder, files = (FAST_DIR, FAST_FILES) if which == "fast" else (ACCURATE_DIR, ACCURATE_FILES)
    return all(os.path.isfile(os.path.join(models, folder, f)) for f in files)


def fast(samples, models, threads, progress):
    import numpy as np
    import sherpa_onnx
    md = os.path.join(models, FAST_DIR)
    rec = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(model=os.path.join(md, "model.int8.onnx"),
                                                      tokens=os.path.join(md, "tokens.txt"),
                                                      num_threads=threads, provider="cpu")
    regions = voice(samples, vad_path(), FAST_SPEECH_S)
    pieces, total = [], len(samples) / RATE
    for a, b in regions:
        st = rec.create_stream()
        st.accept_waveform(RATE, np.ascontiguousarray(samples[a:b]))
        rec.decode_stream(st)
        r = st.result
        toks = [(a / RATE + t, None, tok) for t, tok in zip(r.timestamps, r.tokens)]
        if toks:
            pieces.append((a / RATE, b / RATE, toks))
        progress("listening", b / RATE, total)
    return cues_from_tokens(pieces), "cpu"


def cuda_ready(gpu_dir):
    u"""Is there an NVIDIA card CTranslate2 can use, with NVIDIA's libraries (hato's GPU pack) in `gpu_dir`?"""
    if not gpu_dir or not os.path.isdir(gpu_dir):
        return False
    try:
        os.add_dll_directory(gpu_dir)
        os.environ["PATH"] = gpu_dir + os.pathsep + os.environ.get("PATH", "")
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def accurate(samples, models, threads, progress, device, gpu_dir):
    import numpy as np
    from faster_whisper import WhisperModel
    from faster_whisper.vad import SpeechTimestampsMap
    use = "cuda" if device != "cpu" and cuda_ready(gpu_dir) else "cpu"
    path = os.path.join(models, ACCURATE_DIR)
    model = None
    if use == "cuda":
        try:
            model = WhisperModel(path, device="cuda", compute_type="int8")
        except Exception:                       # a card CTranslate2 can't use after all: the CPU, said in `device`
            use = "cpu"
    if model is None:
        model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=threads)
    # the voice found as faster-whisper's own vad_filter does it -- the speech joined (SPEECH_PAD each side), its
    # times mapped back -- with sherpa-onnx's Silero (the module docstring: no second ONNX Runtime)
    regions = padded(voice(samples, vad_path(), WHISPER_SPEECH_S, WHISPER_SILENCE), len(samples))
    if not regions:
        return [], use
    speech = np.concatenate([samples[a:b] for a, b in regions])
    mapping = SpeechTimestampsMap([{"start": a, "end": b} for a, b in regions], RATE)
    segments, _info = model.transcribe(speech, language="ja", beam_size=5, vad_filter=False,
                                       condition_on_previous_text=False, word_timestamps=True)
    total = len(samples) / RATE
    pieces = []
    for seg in segments:
        s, e = mapping.get_original_time(seg.start), mapping.get_original_time(seg.end, is_end=True)
        words = [(mapping.get_original_time(w.start), mapping.get_original_time(w.end, is_end=True), w.word)
                 for w in (seg.words or [])]
        if not words and seg.text.strip():
            words = [(s, e, seg.text.strip())]
        if words:
            pieces.append((min(s, words[0][0]), max(e, words[-1][1]), words))
        progress("listening", e, total)
    return cues_from_tokens(pieces), use


# --- the command line ------------------------------------------------------------------------------------------ #

def run(args):
    started = time.monotonic()
    if not has_model(args.models, args.model):
        emit("result", outcome="no_model", model=args.model)
        return 0
    last = [0.0]

    def progress(stage, done, total):
        now = time.monotonic()
        if now - last[0] >= 0.5:
            last[0] = now
            emit("progress", stage=stage, done=round(done, 1), total=round(total, 1) if total else None)
    try:
        samples = read_audio(args.input, progress)
    except Unreadable as e:
        emit("result", outcome="unreadable", why=str(e))
        return 0
    except TooLong:
        emit("result", outcome="too_long", hours=MAX_HOURS)
        return 0
    seconds = len(samples) / RATE
    threads = args.threads or max(1, min(8, (os.cpu_count() or 2) - 1))
    if args.model == "fast":
        cues, device = fast(samples, args.models, threads, progress)
    else:
        cues, device = accurate(samples, args.models, threads, progress, args.device, args.gpu)
    took = round(time.monotonic() - started, 1)
    if not cues:
        emit("result", outcome="no_speech", seconds=round(seconds, 1), device=device, model=args.model, took=took)
        return 0
    write_whole(args.output, srt(cues))
    emit("result", outcome="made", cues=len(cues), seconds=round(seconds, 1), device=device, model=args.model,
         took=round(time.monotonic() - started, 1))
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="hato-speech")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    r = sub.add_parser("run")
    r.add_argument("--model", choices=MODELS, required=True)
    r.add_argument("--models", required=True)
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--device", choices=("auto", "cpu"), default="auto")
    r.add_argument("--gpu", default=None)
    r.add_argument("--threads", type=int, default=0)
    args = p.parse_args(argv)
    if args.cmd == "probe":
        emit("probe", version=VERSION, protocol=PROTOCOL, models=list(MODELS))
        return 0
    try:
        return run(args)
    except FileExistsError as e:
        emit("result", outcome="error", why=u"a file is already there: %s" % os.path.basename(str(e)))
        return 1
    except Exception as e:                       # the one line hato shows; the trace on stderr
        import traceback
        traceback.print_exc()
        emit("result", outcome="error", why=(u"%s: %s" % (type(e).__name__, e))[:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())
