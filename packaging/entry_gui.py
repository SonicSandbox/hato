# -*- coding: utf-8 -*-
u"""The frozen WINDOW's entry script -- it becomes `hato.exe`. RUNBOOK 7g.

⭐ THE HEADLINE BINARY. Sonic, 2026-09-18: *"i don't want it 'gui', i want it
to be hato as the main one ... i can just click on hato.exe and it will
handle everything else."* It does: the window owns folders, settings, the
key, runs, and turning the tray watcher on and off. The other two
executables exist for it to spawn.

🚨 `console=False` IN THE SPEC MEANS THIS PROCESS HAS NO VALID STANDARD
HANDLES. On Windows a windowed app's stdout and stderr are invalid, so a
stray `print()` here can raise -- ⛔ nothing in this file writes to a stream,
and nothing added to it should. The window reads its CHILD's stdout, which is
a pipe it opened itself and is fine.

⚠ `sys.exit(main())`, never falling off the end. A frozen bundle whose entry
point returns `None` exits 0 no matter what happened, which is how a run that
never started once reported success (`hato/gui/__main__.py` records it).
"""
import os
import sys

# 🚨 16l P1 -- BEFORE ANYTHING ELSE. Double-clicked, a `console=False` exe gets
# no handles and Python sets `sys.stdout` / `sys.stderr` to None; the first
# bare `sys.stderr.write` anywhere below then raises AttributeError, with
# nowhere to say so. ⭐ devnull in place of a None stream; ⛔ a stream that
# exists (a console, a pipe, a test's capture) is left alone.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from hato.gui import main  # noqa: E402 -- after the streams, on purpose

if __name__ == "__main__":
    sys.exit(main())
