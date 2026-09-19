# -*- coding: utf-8 -*-
u"""
hato's window. RUNBOOK 7c-7e.

    python -m hato.gui          opens it
    from hato.gui import main   the same entry point

===========================================================================
⛔ IMPORTING THIS MUST NOT IMPORT QT
===========================================================================

`hato.gui.run` is the subprocess driver and it is deliberately toolkit-free,
so every check about spawning, decoding, parsing and counting runs on a
machine with no display -- which is every CI runner hato has. A `from .app
import App` at the top of this file would undo that in one line: the suite
would import Qt transitively and skip on any runner without it.

⭐ So the window is reached through `main()`, which imports it when it is
actually wanted, and `hato.gui.run` is importable on its own for ever.

===========================================================================
⛔ THE WINDOW DECIDES NOTHING
===========================================================================

`05-interface.md`: it spawns `hato --json --progress` and paints what comes
back. The timing verdict remains the referee -- a person's manual pick goes
through `hato sync`, which hands tsubasa an explicit pair, and a wrong pick
is refused rather than written. Settings writes through `hato config`, which
owns the only schema. ⛔ Nothing in here re-decides any of it.
"""

__all__ = ["main", "run"]


#: What to say when Qt is not installed. ⭐ AN INSTRUCTION, NOT A REFUSAL
#: (`doctrine/architecture`). A bare ImportError traceback about `PyQt6` tells
#: somebody that hato is broken; this tells them hato is fine and the window
#: needs one more thing, and names it.
NO_QT = (u"hato's window needs PyQt6, which is not installed.\n"
         u"    pip install PyQt6\n"
         u"hato itself does not need it -- `hato <folder>` works without a "
         u"window, and that is why it is an optional extra rather than a "
         u"dependency.")


def main(argv=None):
    u"""Open the window. -> an exit code.

    ⚠ The import is HERE, not at module scope. See the note above -- it is what
    keeps `hato.gui.run` importable, and Qt out of the CLI's process.
    """
    try:
        from hato.gui.app import main as _main
    except ImportError as exc:
        # ⛔ ONLY QT'S ABSENCE. An ImportError raised from INSIDE the window's
        # own code is a real fault, and swallowing it into "install PyQt6"
        # would send somebody to fix a package that is already there.
        if u"PyQt6" not in str(exc):
            raise
        import sys
        sys.stderr.write(NO_QT + u"\n")
        return 2
    return _main(argv)
