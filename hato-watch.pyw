# -*- coding: utf-8 -*-
u"""Start hato's tray watcher from a clone. Double-click it, or let Windows.

    pythonw.exe hato-watch.pyw

🚨 THIS FILE EXISTS FOR ONE REASON: `sys.path[0]` IS THE SCRIPT'S OWN FOLDER.

`hato` is NOT installed as a distribution -- measured 2026-09-18, `import
hato` from any other directory raises `ModuleNotFoundError`. ⛔ So a Windows
startup entry running `pythonw -m hato.watch` would fail at every login, and
fail SILENTLY: a windowed interpreter has no console to print the traceback
to, so the person sees nothing at all and concludes the feature is broken.
That is this project's most expensive failure shape and it has already been
paid for once, in `watch.open_window`.

⭐ Because Python puts a script's own directory on `sys.path`, running THIS
file from anywhere makes `import hato` resolve -- no `PYTHONPATH`, no working
directory, nothing for a registry entry to get wrong.

⚠ `.pyw`, not `.py`: `pythonw.exe` opens no console, and a console flashing
at every login is the one packaging detail every user can see.

⛔ A FROZEN INSTALL DOES NOT USE THIS. There, `hato-watch.exe` is the entry
point and `hato/startup.py` registers that instead.
"""
import os
import sys

# ⚠ Belt as well as braces. `sys.path[0]` is already this folder when Python
# runs a script by path, but an embedding host may not set it -- and being
# wrong here is invisible, so it costs one line to be certain.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from hato.watch import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
