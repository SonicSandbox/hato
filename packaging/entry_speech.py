# -*- coding: utf-8 -*-
u"""`hato-speech.exe` -- the speech add-on's one program (RUNBOOK Layer 19a).

⛔ NO NETWORK CODE IN THE ADD-ON. faster-whisper imports `huggingface_hub` at the
top of its `utils` (for `download_model`, which hato never calls: hato fetches and
verifies the model itself, 19b-c). The frozen add-on leaves it out
(packaging/hato-speech.spec), and this stub stands in for the import, so the
add-on carries no HTTP library at all. ⛔ A call into the stub fails loudly; it
never quietly downloads.
"""
import sys
import types


def _no_hub():
    hub = types.ModuleType("huggingface_hub")

    def _refused(*_a, **_k):
        raise RuntimeError("hato-speech never downloads: hato fetches the model")
    hub.snapshot_download = _refused
    hub.hf_hub_download = _refused
    return hub


if getattr(sys, "frozen", False):
    sys.modules.setdefault("huggingface_hub", _no_hub())

from hato import speech_engine  # noqa: E402

if __name__ == "__main__":
    sys.exit(speech_engine.main())
