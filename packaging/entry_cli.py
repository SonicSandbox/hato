# -*- coding: utf-8 -*-
u"""The frozen CLI's entry script. RUNBOOK 7g.

⚠ PyInstaller freezes SCRIPTS, not entry points, so `pyproject.toml`'s
`hato = "hato.cli:main"` cannot be handed to it directly. This file is that
console script written out, and it must stay a one-liner over `cli.main` --
a second entry point that grew its own behaviour would be a third answer to
every question `hato/__main__.py` already answers.

⭐ THIS IS THE EXE THE OTHER TWO SPAWN, AND IT IS CALLED `hato-cli.exe`.
`gui/run.py::cli_argv()` and `watch.py::run_argv()` both resolve to it beside
the bundle when frozen, because `sys.executable` is then the bundle itself
and `-m hato` would re-enter whichever window launched it.

🚨 ⛔ IT IS NOT `hato.exe`. Sonic ruled 2026-09-18 that `hato.exe` is THE
WINDOW -- the one file a person clicks. Naming this one `hato` again would
mean every automatic run opened a window instead of fetching subtitles.
"""
import sys

from hato.cli import main

if __name__ == "__main__":
    sys.exit(main())
