# -*- mode: python ; coding: utf-8 -*-
u"""hato's speech add-on, frozen. RUNBOOK Layer 19a.

    pyinstaller --noconfirm --distpath <dir> --workpath <dir> packaging/hato-speech.spec

⛔ ITS OWN SPEC, ITS OWN FOLDER, NEVER hato's ZIP. The add-on is ~0.2 GB of
runtimes that a person who never makes a subtitle should never download; hato
fetches it only after a yes (19c). One program, `hato-speech.exe`, a console
build: hato reads its NDJSON on stdout and starts it with no window
(`gui/run.py` `no_console_kwargs`).

⚠ TWO ONNX RUNTIMES WOULD COLLIDE. sherpa-onnx carries its own
`sherpa_onnx/lib/onnxruntime.dll`, and the `onnxruntime` package another.
faster-whisper needs the latter only for its own VAD filter, which the engine
never uses (it finds the voice with sherpa-onnx for both models). So
`onnxruntime` is EXCLUDED, and sherpa-onnx's DLLs keep their package-relative
place (`collect_dynamic_libs`).

⛔ NO HTTP LIBRARY: `huggingface_hub` (and what it pulls) is excluded, and
`entry_speech.py` stubs the import.

⭐ `silero_vad.onnx` (MIT, 0.6 MB) and the licence texts are copied in beside
the exe by `packaging/package_speech.py`, never fetched at run time.
"""
import os
from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = os.path.dirname(os.path.abspath(SPECPATH))

a = Analysis(
    [os.path.join(SPECPATH, "entry_speech.py")],
    pathex=[ROOT],
    binaries=collect_dynamic_libs("sherpa_onnx") + collect_dynamic_libs("ctranslate2"),
    datas=[],
    hiddenimports=["sherpa_onnx", "ctranslate2", "faster_whisper", "tokenizers", "av"],
    excludes=["onnxruntime", "huggingface_hub", "requests", "httpx", "urllib3", "tkinter", "PyQt6",
              "matplotlib", "IPython", "pytest", "hato.gui", "hato.update", "hato.client", "tsubasa"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="hato-speech", console=True,
          upx=False, debug=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="hato-speech")
