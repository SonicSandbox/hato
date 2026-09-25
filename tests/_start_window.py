# -*- coding: utf-8 -*-
u"""The Layer 13 pass (Z13-7) -- `main()` itself, up to the moment it shows the window,
in a process of its own -- run by `test_gui_widgets`.

A FRESH interpreter, so what the window's start IMPORTS is measured; and `main()`'s own
reach -- its error net, its single-instance name -- stays out of the suite's process.
⛔ Nothing is spawned (the one spawn seam returns nothing), the tray is not started, the
single-instance name is not taken, the developer's own window is never raised, and the
event loop is not entered. Prints ONE JSON line on stdout:

    renders    how many renders `main()` asked for after the window was built, before show
    titlesub   what the title bar said at the moment the window was shown
    net        the network modules the start had imported by then

The store and the config come from the parent's environment.
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HATO_ALLOW_MANY"] = "1"             # ⛔ never raise the developer's own window
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hato.gui import app as gui_app              # noqa: E402

NET = (u"urllib.request", u"http.client", u"ssl")


def main():
    seen = {}
    renders = []
    window_class = gui_app.HatoWindow
    real_init, real_render, real_show = (window_class.__init__, window_class.render,
                                         window_class.show)

    def init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        del renders[:]                           # the constructor's own paint is not main()'s

    def render(self, *args, **kwargs):
        renders.append(1)
        return real_render(self, *args, **kwargs)

    def show(self):
        seen.update(renders=len(renders), titlesub=self.titlesub.text(),
                    net=sorted(m for m in NET if m in sys.modules))
        return real_show(self)

    window_class.__init__, window_class.render, window_class.show = init, render, show
    window_class._spawn = lambda self, *args, **kwargs: None      # nothing is started
    window_class.start_watcher = lambda self, *args, **kwargs: None
    gui_app.listen_for_second_launch = lambda window: None        # ⛔ no instance name
    gui_app.QApplication.exec = staticmethod(lambda *args: 0)      # no event loop
    code = gui_app.main([u"hato"])
    print(json.dumps(seen))
    return code


if __name__ == "__main__":
    sys.exit(main())
