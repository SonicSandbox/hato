# -*- coding: utf-8 -*-
u"""The Layer 13 pass (Z13-2) -- the Needs-you strip under a LARGER system font, in a
process of its own -- run by `test_gui_widgets`.

⛔ The suite's own offscreen platform has NO FONTS on Windows: every size measures alike,
so a check there could never fail (it is how M13-22 was once retired as equivalent).
This process gives offscreen Windows' own fonts (`QT_QPA_FONTDIR`) and an application
font of 12 pt -- what "Make text bigger" changes -- then measures every strip's words
against its button, once the window is on its feet:

    0   every strip's words sit on its button's middle
    1   a strip's words are off its button's middle, or there was no strip to measure
    2   the control failed: this platform measures a 12 pt font no taller than 11 px

The store comes from the parent's environment (the suite's conftest set it).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR",
                          os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtGui import QFont, QFontMetrics                  # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

import test_gui_widgets as fx                                # noqa: E402


def main():
    app = QApplication.instance() or QApplication([])
    big, small = QFont(app.font()), QFont(app.font())
    big.setPointSizeF(12.0)
    small.setPixelSize(11)
    if QFontMetrics(big).height() <= QFontMetrics(small).height():
        print(u"the control failed: a 12 pt font measures %d px here, an 11 px one %d"
              % (QFontMetrics(big).height(), QFontMetrics(small).height()))
        return 2
    app.setFont(big)                                         # before anything is built
    strips = []
    real = fx.gui_app._strip_row

    def spy(box, lead, detail, action, dot=None):
        strips.append((lead, action))
        return real(box, lead, detail, action, dot)

    fx.gui_app._strip_row = spy
    window = fx.make()
    window.show_tab(fx.gui_app.TAB_PICK)
    fx.lay_out(window)
    off = []
    for lead, action in strips:
        # the lead's metrics NOW -- polished, in the sheet's font -- are the ones it paints in
        want = max(0, (action.sizeHint().height() - lead.fontMetrics().height()) // 2)
        if lead.contentsMargins().top() != want:
            off.append(u"%r padded %d, its button's middle is %d"
                       % (lead.text()[:40], lead.contentsMargins().top(), want))
    print(u"strips: %d; off their button's middle: %s" % (len(strips), off))
    return 1 if off or not strips else 0


if __name__ == "__main__":
    sys.exit(main())
