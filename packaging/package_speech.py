# -*- coding: utf-8 -*-
u"""The speech add-on's download (RUNBOOK Layer 19a, 19i).

    python packaging/package_speech.py --dist DIR --vad silero_vad.onnx --site-packages SP [--to DIR]

`DIR` is PyInstaller's output for `packaging/hato-speech.spec` (its `hato-speech/` folder inside). Writes
`hato-speech-<version>-windows-x64.zip` with ONE top folder, `hato-speech/`, and prints its size and sha256: the two
numbers `hato/speech.py`'s `ADDON_PIN` must carry before hato's release is stamped.

🚨 IT MUST CARRY ITS LICENCES (GPLv3 §4 and §6, as hato's own zip): `LICENSE` (the add-on is GPL-3.0 as a whole:
PyAV's FFmpeg is built with x264 / x265, GPL-2.0-or-later) and `THIRD_PARTY_LICENSES.md` at its top, and every licence
file the bundled wheels ship under `licenses/<distribution>/`. ⛔ Refused without them.

⛔ NO MODEL IN IT, and nothing of NVIDIA's: the models are downloaded on the learner's yes (19b), NVIDIA's libraries
only on a second yes, never conveyed by hato.

⭐ `--verify` (on by default): the zip is unpacked OUTSIDE the repository and its `hato-speech.exe probe` must answer
protocol 1 -- the download, not the build folder, is what is proven (package_standalone.py's rule).
"""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOP = u"hato-speech"
ALONGSIDE = (u"LICENSE", u"THIRD_PARTY_LICENSES.md")
#: The distributions frozen into the add-on whose own licence files travel with it.
CARRIED = (u"numpy", u"av", u"ctranslate2", u"sherpa_onnx", u"sherpa_onnx_core", u"faster_whisper", u"tokenizers",
           u"tqdm", u"PyYAML", u"pyinstaller")
#: Silero VAD (MIT), the voice finder for both models: sherpa-onnx's release asset, pinned.
VAD_SHA256 = u"9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"
VAD_SIZE = 643854


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def version():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from hato import speech_engine
    return speech_engine.VERSION


def licence_files(site_packages):
    u"""{distribution: [paths]} -- every LICENSE / LICENCE / COPYING / NOTICE file each carried wheel ships."""
    found = {}
    for entry in sorted(os.listdir(site_packages)):
        if not entry.endswith(u".dist-info"):
            continue
        name = entry.split(u"-")[0]
        if name.lower() not in [c.lower() for c in CARRIED]:
            continue
        base = os.path.join(site_packages, entry)
        for where, _dirs, files in os.walk(base):
            for f in files:
                if f.upper().startswith((u"LICEN", u"COPYING", u"NOTICE", u"AUTHORS")):
                    full = os.path.join(where, f)          # its path in the dist-info kept: numpy has 6 LICENSEs
                    found.setdefault(name, []).append((full, os.path.relpath(full, base).replace(os.sep, u"/")))
    return found


def build(dist, vad, site_packages, to):
    bundle = os.path.join(dist, TOP)
    if not os.path.isfile(os.path.join(bundle, u"hato-speech.exe")):
        raise SystemExit(u"⛔ no hato-speech.exe in %s -- build packaging/hato-speech.spec first" % bundle)
    if os.path.getsize(vad) != VAD_SIZE or sha256(vad) != VAD_SHA256:
        raise SystemExit(u"⛔ %s is not the pinned Silero VAD" % vad)
    for name in ALONGSIDE:
        if not os.path.isfile(os.path.join(ROOT, name)):
            raise SystemExit(u"⛔ %s is missing: the add-on would convey code without its licence" % name)
    found = licence_files(site_packages)
    missing = [c for c in (u"numpy", u"av", u"sherpa_onnx", u"faster_whisper", u"tqdm") if c not in found]
    if missing:
        raise SystemExit(u"⛔ no licence file found for %s in %s" % (u", ".join(missing), site_packages))
    os.makedirs(to, exist_ok=True)
    out = os.path.join(to, u"hato-speech-%s-windows-x64.zip" % version())
    part = out + u".part"
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for where, _dirs, files in os.walk(bundle):
            for f in sorted(files):
                full = os.path.join(where, f)
                z.write(full, u"%s/%s" % (TOP, os.path.relpath(full, bundle).replace(os.sep, u"/")))
        z.write(vad, u"%s/silero_vad.onnx" % TOP)
        for name in ALONGSIDE:
            z.write(os.path.join(ROOT, name), u"%s/%s" % (TOP, name))
        for dist_name, paths in sorted(found.items()):
            for path, inside in paths:
                z.write(path, u"%s/licenses/%s/%s" % (TOP, dist_name, inside))
    os.replace(part, out)
    return out


def verify(zip_path):
    u"""Unpacked outside every checkout, its probe answers protocol 1."""
    with tempfile.TemporaryDirectory(prefix=u"hato-speech-verify-") as there:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            assert all(n.startswith(TOP + u"/") for n in names), u"one top folder"
            for need in ALONGSIDE + (u"silero_vad.onnx", u"hato-speech.exe"):
                assert u"%s/%s" % (TOP, need) in names, need
            z.extractall(there)
        exe = os.path.join(there, TOP, u"hato-speech.exe")
        answer = subprocess.run([exe, u"probe"], capture_output=True, timeout=120)
        line = json.loads(answer.stdout.decode("utf-8").strip().splitlines()[-1])
        assert line.get(u"protocol") == 1 and answer.returncode == 0, line
        return line


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dist", required=True)
    p.add_argument("--vad", required=True)
    p.add_argument("--site-packages", required=True)
    p.add_argument("--to", default=os.path.join(ROOT, u"dist"))
    p.add_argument("--no-verify", action="store_true")
    args = p.parse_args(argv)
    out = build(args.dist, args.vad, args.site_packages, args.to)
    said = verify(out) if not args.no_verify else None
    print(json.dumps({u"zip": out, u"size": os.path.getsize(out), u"sha256": sha256(out), u"probe": said},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
