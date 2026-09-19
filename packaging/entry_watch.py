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
import sys

from hato.watch import main

if __name__ == "__main__":
    sys.exit(main())
