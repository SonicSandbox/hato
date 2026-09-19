# -*- coding: utf-8 -*-
"""
⭐ LIVE -- OPT-IN. Excluded from the default run by hato.config.json
(`"default": false`), never by discipline (spec/07-test-plan.md).

    python run_tests.py live

It spends 2 metered jimaku calls and 1 unmetered download against someone
else's server, with the REAL key. It is the half the recorded suites cannot
answer: does jimaku still answer the way the fixtures say it did?

What it structurally cannot cover: anything the doctor does not ask.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "api"

pytestmark = pytest.mark.skipif(
    os.environ.get("HATO_LIVE") != "1",
    reason="LIVE suite: runs only as `python run_tests.py live`, which sets HATO_LIVE=1")


def test_the_live_api_still_answers_the_way_the_fixtures_say():
    proc = subprocess.run([sys.executable, "-m", "hato", "doctor", "--json"], cwd=str(ROOT),
                          env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=300)
    assert proc.stdout, proc.stderr.decode("utf-8", "replace")
    got = json.loads(proc.stdout.decode("utf-8"))
    lines = {l["label"]: l for l in got["lines"]}
    assert got["exit_code"] == 0, json.dumps(got, ensure_ascii=False, indent=1)
    assert lines["search"]["text"].startswith("HTTP 200")
    assert "x-ratelimit-limit: 25" in lines["rate limit"]["text"], lines["rate limit"]
    recorded = json.loads((FIXTURES / "entries_11446_files.json").read_text(encoding="utf-8"))
    keys = sorted({k for f in recorded for k in f})
    assert "keys: %s" % ", ".join(keys) in lines["files"]["extra"], (
        "the file-list shape changed since the capture -- re-capture, and read the diff")
    assert got["metered_calls"] == 2
