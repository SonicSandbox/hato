# -*- coding: utf-8 -*-
u"""
`python -m hato.gui` opens the window.

    python -m hato.gui

[X] NOTHING BUT THE CALL. `hato.gui.main` imports Qt lazily so that
`hato.gui.run` stays importable on a machine with no display; putting any
logic here would be a second entry point to keep in step with the first.

[!] And it exits with `main()`'s code rather than falling off the end, because
a frozen bundle that returns `None` from its entry point exits 0 no matter
what happened -- which is how a run that never started once reported success.
"""
import sys

from hato.gui import main

if __name__ == "__main__":
    sys.exit(main())
