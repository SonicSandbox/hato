# -*- coding: utf-8 -*-
u"""The Layer 13 pass (Z13-9) -- a row's chevron fade and a row nobody can see, in a
process of its own -- run by `test_gui_widgets`: the crash this hunts takes the process.

The chevron fades on an opacity effect. Animated on a HIDDEN row -- its pane at the
back, or its show still queued -- it crashed the window 8 of 8 when forced, and about
1 run in 36 of a person flicking between tabs mid-fade (the adversary's p14/p15). So:
a fade running as its row is hidden ends at once, where it was going; a fade asked of a
row nobody can see is set, not run; and then the adversary's forced shape, 300 times:

    0   no fade ran where nobody could see it, and nothing crashed
    1   a fade ran where nobody could see it (said on stdout)
    any other   the process died (0xC0000005 is an access violation)

The store comes from the parent's environment (the suite's conftest set it).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QEvent, QPointF, QVariantAnimation  # noqa: E402
from PyQt6.QtGui import QEnterEvent                          # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

import test_gui_widgets as fx                                # noqa: E402

RUNNING = QVariantAnimation.State.Running


def enter(app, row):
    app.sendEvent(row, QEnterEvent(QPointF(3, 3), QPointF(3, 3), QPointF(3, 3)))


def main():
    app = QApplication.instance() or QApplication([])
    gui_app = fx.gui_app
    window = fx.make()
    fx.lay_out(window)
    window.show_tab(gui_app.TAB_SUBS)
    app.processEvents()
    row = [r for r in window.findChildren(gui_app.SubRow) if r.isVisible()][0]
    enter(app, row)                                          # the pointer arrives
    if row._chev_anim.state() != RUNNING:
        print(u"the control failed: hovering a row on screen started no fade")
        return 1
    window.show_tab(gui_app.TAB_PICK)                        # ... and its pane goes back
    if row._chev_anim.state() == RUNNING:
        print(u"a fade went on running on a row its tab switch hid")
        return 1
    if row._chev_fade.opacity() != 1.0:
        print(u"a fade stopped by its row hiding did not end where it was going: %s"
              % row._chev_fade.opacity())
        return 1
    app.sendEvent(row, QEvent(QEvent.Type.Leave))            # a fade asked of a hidden row
    if row._chev_anim.state() == RUNNING:
        print(u"a fade was started on a row nobody can see")
        return 1
    if row._chev_fade.opacity() != 0.0:
        print(u"a hidden row's chevron was not set where its fade was going: %s"
              % row._chev_fade.opacity())
        return 1
    for n in range(300):                                     # the adversary's forced shape
        window.show_tab(gui_app.TAB_SUBS)
        app.processEvents()
        window.show_tab((gui_app.TAB_PICK, gui_app.TAB_SET)[n % 2])
        rows = window.panes[gui_app.TAB_SUBS].widget().findChildren(gui_app.SubRow)
        enter(app, rows[n % len(rows)])
        app.processEvents()
    print(u"no fade on a row nobody could see; 300 hovers of a pane at the back, no crash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
