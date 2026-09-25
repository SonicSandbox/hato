# -*- coding: utf-8 -*-
u"""RUNBOOK 13a's crash, in a process of its own -- run by `test_gui_widgets`.

A window with ROWS on screen (each `SubRow` carries a graphics effect), its pane rebuilt
twice in one turn of the event loop, five times over. With a cleared widget's queued
show landing on it detached, this SEGFAULTED -- 3 of 3, offscreen and on the real
platform -- and a crash inside the suite's own process would take every later check of
the suite down with it. So it runs here, and the parent reads the exit:

    0   nothing was shown as a window of its own, and nothing crashed
    1   widgets were shown as windows of their own (listed on stdout)
    any other   the process died (0xC0000005 is an access violation)

The store comes from the parent's environment (the suite's conftest set it).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QEvent, QObject                     # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget            # noqa: E402

import test_gui_widgets as fx                                # noqa: E402


class ShownAsWindow(QObject):
    def __init__(self, window):
        super().__init__()
        self.window, self.seen = window, []

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Show and isinstance(obj, QWidget)
                and obj.isWindow() and obj is not self.window):
            self.seen.append(u"%s %dx%d" % (type(obj).__name__, obj.width(), obj.height()))
        return False


def main():
    app = QApplication.instance() or QApplication([])
    window = fx.make()
    rows = len(window.findChildren(fx.gui_app.SubRow))
    window.show()
    app.processEvents()
    watch = ShownAsWindow(window)
    app.installEventFilter(watch)
    for _ in range(5):
        window.render()
        window.render()                                      # twice, in one turn
        app.processEvents()
    app.removeEventFilter(watch)
    print(u"rows on screen: %d; shown as windows: %d %s" % (rows, len(watch.seen),
                                                          watch.seen[:5]))
    return 1 if watch.seen else 0


if __name__ == "__main__":
    sys.exit(main())
