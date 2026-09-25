# -*- coding: utf-8 -*-
u"""The frozen SWAPPER's entry script -- `hato-update.exe`. RUNBOOK 11d · 11h.

    hato-update.exe --pending <pending.json> [--quiet]
    hato-update.exe --selftest <out.json>

⭐ ONEFILE, UNLIKE ITS THREE SIBLINGS. It runs from OUTSIDE the program folder --
the hand-off copies it into the staging root -- while that folder, `_internal`
and all, is renamed away. So it carries its own runtime and leans on nothing it
is about to move.

⛔ IT IMPORTS `hato.swap`, `hato.splash` FOR THE SPLASH, AND NOTHING ELSE OF
hato. `--selftest` writes what this process loaded into a FILE -- a windowed
program has nowhere to print -- and the smoke reads it off the BUILT bytes.
⚠ `console=False`: a console flashing over the desktop mid-update is exactly the
kind of thing the splash is there to replace.
"""
import json
import os
import sys


def selftest(out):
    u"""What the frozen swapper carries, written to `out`. -> 0

    ⭐ `mark`: the splash's own picture of hato, found and read INSIDE the onefile --
    [name, width, height] -- or why not. A spec that forgot the data files would
    otherwise draw a card with a hole where the mark belongs, and nothing would say."""
    import hato.swap                                   # noqa: F401
    mark = u"no splash"
    try:
        import hato.splash                             # noqa: F401
        splash = True
        try:
            path = hato.splash.mark_path(hato.splash.MARK)
            image = hato.splash.read_png(path) if path else None
            mark = [os.path.basename(path), image[0], image[1]] if image else u"no mark"
        except Exception as exc:                       # noqa: BLE001
            mark = u"%s: %s" % (type(exc).__name__, exc)
    except Exception as exc:                           # noqa: BLE001
        splash = u"%s: %s" % (type(exc).__name__, exc)
    loaded = sorted(m for m in sys.modules if m == u"hato" or m.startswith(u"hato."))
    temp = out + u".new"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump({u"hato": loaded, u"splash": splash, u"mark": mark,
                   u"frozen": bool(getattr(sys, u"frozen", False))}, handle)
    os.replace(temp, out)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == u"--selftest":
        return selftest(argv[1])
    from hato import swap
    return swap.main(argv)


if __name__ == "__main__":
    sys.exit(main())
