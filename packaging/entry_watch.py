# -*- coding: utf-8 -*-
u"""The frozen TRAY WATCHER's entry script. RUNBOOK 7g.

🚨 A THIRD EXECUTABLE, AND THE MEMORY ARGUMENT IS WHY. `hato/watch.py`'s
header records the measurement: the ctypes watcher is 13.4 MB resident
against 30.6 for a Qt tray, and it sits there for as long as the machine is
on. ⛔ So this entry point must NEVER reach Qt -- the spec excludes PyQt6
from this Analysis on purpose, and a check asserts the module imports no
toolkit. If that exclusion is ever removed, the separation buys nothing and
the third executable is pure cost.

⚠ `console=False`, like the window: a tray process with a console window
attached for its whole life is the one packaging detail every user can see.
⛔ Nothing here writes to a stream -- those handles are not valid.

⭐ `watch.watch_argv()` resolves to `hato-watch.exe` beside the bundle when
frozen; the window spawns it by that name. The name is a contract, not a
preference.
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

from hato.watch import main  # noqa: E402 -- after the streams, on purpose

if __name__ == "__main__":
    sys.exit(main())
