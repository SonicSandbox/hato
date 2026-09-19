# -*- coding: utf-8 -*-
u"""
Photograph every state of the window, so they can be LOOKED AT.

    python gui-shots/shoot.py

[!] STATE ASSERTIONS ARE STRUCTURALLY BLIND TO RENDER BUGS. In this project's
history: status chips overflowed their column so the episode number vanished
from exactly the row that needed attention; a 900px gap opened between a
filename and its match rate; fifty green checks sat over a header running off
the screen. Every one of those passed every assertion that existed, and every
one was caught by opening the PNG.

So: `tests/test_gui_widgets.py` pins what a picture cannot, and this pins
nothing -- it just makes the pictures.

[!] ABSOLUTE WINDOWS PATHS. A POSIX-looking `/tmp/x.png` handed to Qt from
Git Bash lands somewhere else entirely -- measured 2026-09-18.

The states shot here are the twelve in `gui-mock/shots-final/`, plus the
empty-library states the mock never had.
"""
import os
import sys

#: [!] NOT `offscreen`, AND THIS IS THE WHOLE POINT OF THE FILE. Measured on
#: this machine 2026-09-18: under `QT_QPA_PLATFORM=offscreen` on Windows,
#: `QFontDatabase.families()` returns ZERO families and every glyph renders as
#: a tofu box. The PNG is real, the layout is real, and the typography -- the
#: elision, the overflow, the column alignment, the thing the shot exists to
#: check -- is entirely fictional. Fifty green checks over an unreadable
#: window is precisely the failure this loop exists to catch.
#:
#: [*] So the shooter uses the REAL platform and simply never puts the window
#: on screen: `WA_DontShowOnScreen` lays a widget out completely, with the
#: whole font database, without it ever appearing. The suite keeps `offscreen`
#: because it asserts state and must run where there is no display.
#: [!] SET, NOT POPPED -- and that distinction cost a whole round of shots.
#: `tests/test_gui_widgets.py` does `setdefault("QT_QPA_PLATFORM", "offscreen")`
#: at module scope, which is right for the suite; importing it below therefore
#: puts `offscreen` BACK if this file merely deleted the variable. The shots
#: came out fontless a second time and the give-away was in the metrics: every
#: character was exactly one em wide, so the window measured ~2x too big and
#: reported a minimum-width defect that did not exist.
os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform.startswith("win") \
    else os.environ.get("QT_QPA_PLATFORM_REAL", "xcb")
#: 1:1 logical pixels, so a shot can be compared against `gui-mock/shots-final`
#: directly. This machine is 239.6 dpi / ratio 2.496 and would otherwise
#: produce a 2750px-wide picture of a 1100px window.
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ.setdefault("PYTHONUTF8", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for path in (ROOT, os.path.join(os.path.dirname(ROOT), "tsubasa")):
    if path not in sys.path:
        sys.path.insert(0, path)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from PyQt6.QtCore import Qt                           # noqa: E402
from PyQt6.QtWidgets import QApplication              # noqa: E402

from hato.gui import app as gui_app                   # noqa: E402
from hato.gui import run as gui_run                   # noqa: E402

import test_gui_widgets as fx                         # noqa: E402


def settle(application, window, rounds=6):
    u"""Let the layout finish before the shutter.

    [!] ONE `processEvents` IS NOT ENOUGH. A stylesheet polish, a layout pass
    and a size-hint recalculation are three separate trips through the event
    loop, and photographing after the first one produces a picture of a
    half-built window that looks exactly like a layout bug.
    """
    for _ in range(rounds):
        window.updateGeometry()
        window.layout().activate()
        application.processEvents()


def shoot(application, window, name):
    settle(application, window)
    path = os.path.join(HERE, name + ".png")
    ok = window.grab().save(path)
    print(("  %-34s %s" % (name + ".png", "ok" if ok else "FAILED")))
    return ok


def main():
    application = QApplication.instance() or QApplication([])
    failures = []

    def take(window, name, width=None, height=None):
        #: [*] LAID OUT COMPLETELY, NEVER ON SCREEN.
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        window.resize(width or gui_app.WIN_W, height or gui_app.WIN_H)
        settle(application, window)
        if (window.width(), window.height()) != (width or gui_app.WIN_W,
                                                 height or gui_app.WIN_H):
            #: [!] A WINDOW THAT WILL NOT SHRINK TO ITS RULED SIZE IS A
            #: DEFECT, not a detail -- some child's minimum is holding it open
            #: and the shot would silently be of a different window.
            print("  %-34s WRONG SIZE %dx%d (minimum %dx%d)"
                  % (name, window.width(), window.height(),
                     window.minimumSizeHint().width(),
                     window.minimumSizeHint().height()))
            failures.append(name)
        if not shoot(application, window, name):
            failures.append(name)

    # 1 -- Subtitles, the landing state
    window = fx.make()
    take(window, "01-subtitles")

    # 2 -- Subtitles with two rows opened
    keys = [window.state.key(r) for r in window.state.of(gui_run.ADDED)]
    window.state.open_rows = {keys[0], keys[2]}
    window.render()
    take(window, "02-subtitles-expanded")

    # 3 -- Needs you, nothing opened
    window.state.open_rows = set()
    window.state.open_pick = None
    window.show_tab(gui_app.TAB_PICK)
    take(window, "03-needs-you")

    # 4 -- Needs you, the first row open with three candidates
    picks = [window.state.key(r) for r in window.state.of(gui_run.NEEDS_YOU)]
    window.state.open_pick = picks[0]
    window.render()
    window._animate_accordions()
    window._accordions[picks[0]].set_open(True, animate=False)
    take(window, "04-needs-you-open")

    # 5 -- after choosing: the row collapses green, the next one opens
    window.spawn = lambda argv: None
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    window.commit_pair(window.state.key(row), row["attempts"][0])
    for key, accordion in window._accordions.items():
        accordion.set_open(window.state.open_pick == key, animate=False)
    take(window, "05-pick-after-choosing")

    # 6 -- Settings, the top
    window.show_tab(gui_app.TAB_SET)
    take(window, "06-settings")

    # 7 -- Settings, scrolled to the blacklist
    area = window.panes[gui_app.TAB_SET]
    settle(application, window)
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    take(window, "07-settings-lower")

    # 8 -- clamped to the smallest window the design was ruled at
    window.show_tab(gui_app.TAB_PICK)
    take(window, "08-clamped-needs-you", 1024, 620)

    # 9 -- an empty library, every tab. [!] A real state, three of them.
    blank = fx.make(rows=[])
    take(blank, "09-empty-subtitles")
    blank.show_tab(gui_app.TAB_PICK)
    take(blank, "10-empty-needs-you")

    # 11 -- no folders at all: instruction, not refusal
    fresh = fx.make(rows=[], folders=[], skip_folders=[], blacklist=[],
                    key_hint=None, last_run="", video_total=0, running=False,
                    live="")
    #: [!] AND THE COST GOES WITH IT. The fixture hands every state the same
    #: finished-run summary, so a window that has NEVER RUN was photographed
    #: claiming *"6 API calls - 41.2 s"*. A number in a UI is a claim, and a
    #: shot that carries a false one is worse than no shot.
    fresh.state.summary = {}
    fresh.render()
    take(fresh, "11-first-run-subtitles")
    fresh.show_tab(gui_app.TAB_SET)
    take(fresh, "12-first-run-settings")

    # 13 -- a very long filename, to see the elide rather than assert it
    long_name = ("[SomeExtremelyLongReleaseGroupName] Sousou no Frieren "
                 "Second Season - 01 (NTV 1920x1080 HEVC Main10 AAC "
                 "Dual-Audio Multiple-Subtitle).ass")
    stretched = fx.make(rows=[fx.added(1, name=long_name), fx.added(2)])
    take(stretched, "13-long-filename")

    if failures:
        sys.stderr.write("FAILED to save: %s\n" % ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
