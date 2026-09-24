# -*- coding: utf-8 -*-
u"""
Photograph the Layer 9 states of the window -- RUNBOOK 9a -- so they can be LOOKED at.

    python gui-shots/shoot_layer9.py [OUT_DIR]

⚠ SEPARATE FROM `shoot.py` ON PURPOSE, like `shoot_layer8.py`: that one
regenerates the PNGs the README embeds, which describe the RELEASED window; these
describe work not yet released. They go to OUT_DIR (default: a folder under the OS
temp dir), never into this one.

⭐ The same instrument, imported rather than copied (`shoot_layer8.window_over`):
the real platform plugin, 1:1 logical pixels, `WA_DontShowOnScreen`, its own
store. The waiting row is built by the producer `hato problems` uses, carrying the
reason the run really records (`formats.waiting_reason`) -- the wire's shape.
"""
import os
import sys
import tempfile
from datetime import timedelta

import shoot                                                       # noqa: E402  (sets the platform)
import shoot_layer8 as l8                                          # noqa: E402

from PyQt6.QtCore import Qt                                        # noqa: E402
from PyQt6.QtWidgets import QApplication                           # noqa: E402

from hato import formats                                           # noqa: E402
from hato.gui import app as gui_app                                # noqa: E402

import test_gui_widgets as fx                                      # noqa: E402

#: The Settings column is taller than the window; the whole column is the picture.
TALL = 1500


def only_as(episode=5, kinds=(u"srt",), prefer=u"ass", title=u"Ruri no Houseki"):
    u"""A format wait as `hato problems` sends it: NOT_FOUND, the reason the run
    records (`formats.waiting_reason`, EVERY kind jimaku has)."""
    video = u"D:\\Anime\\%s\\[SubsPlease] %s - %02d (1080p).mkv" % (title, title, episode)
    return fx.memory_row(video, u"NOT_FOUND", formats.waiting_reason(list(kinds), prefer, 3),
                         title=title, season=None, episode=episode,
                         jimaku_entry=9921, tried_before=(),
                         retry_after=l8.NOW + timedelta(hours=20))


def only_as_srt(episode=5):
    return only_as(episode)


def main(out_dir):
    os.environ["HATO_CACHE"] = tempfile.mkdtemp(prefix=u"hato-shots-store-")
    application = QApplication.instance() or QApplication([])
    shoot.pin_machine_state()                 # ⛔ not this machine's registry
    os.makedirs(out_dir, exist_ok=True)
    failures = []

    def take(window, name, height=None):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        window.resize(gui_app.WIN_W, height or gui_app.WIN_H)
        shoot.settle(application, window)
        path = os.path.join(out_dir, name + u".png")
        ok = window.grab().save(path)
        print(u"  %-44s %s %s" % (name + u".png", u"ok" if ok else u"FAILED",
                                   os.path.getsize(path) if ok else u""))
        if not ok:
            failures.append(name)

    run_rows = [fx.added(1, rate=0.82), fx.added(2, rate=0.96)]
    memory = [only_as_srt(5), l8.remembered_frieren()]

    # 1-3 -- the Settings card: the defaults · .srt preferred with the fallback on ·
    # the same with an OLDER tray running, which cannot read the file any more
    for name, over in ((u"L9-01-format-card-default", {}),
                       (u"L9-02-format-card-srt-fallback-on",
                        dict(prefer_format=u"srt", format_fallback=True)),
                       # ⚠ A 1.0.2 tray: it keeps retries, so it is not V1's older
                       # tray -- and it cannot read the setting (ADVERSARY 9a-1)
                       (u"L9-03-format-card-older-tray",
                        dict(prefer_format=u"srt", tray_reads_formats=False))):
        window = l8.window_over(run_rows, memory, watching=True)
        for field, value in over.items():
            setattr(window.state, field, value)
        window.show_tab(gui_app.TAB_SET)
        take(window, name, TALL)

    # 4 -- Needs you: an episode only on jimaku as .srt, beside one really not there
    window = l8.window_over(run_rows, memory, watching=True)
    window.show_tab(gui_app.TAB_PICK)
    take(window, u"L9-04-needs-you-only-as-srt")

    # 5 -- the same once the fallback is on: the wait ends at the next run
    window = l8.window_over(run_rows, memory, watching=True)
    window.state.format_fallback = True
    window.show_tab(gui_app.TAB_PICK)
    take(window, u"L9-05-needs-you-settings-take-it")

    # 6 -- ADVERSARY 9a-9: .srt preferred, one episode waiting as .ass and .vtt
    # (blocked) and one recorded as .srt-only before the switch (taken now): TWO
    # lines, and the button names only the blocked kinds
    mixed = [only_as(7, kinds=(u"ass", u"vtt"), prefer=u"srt", title=u"Kusuriya no Hitorigoto"),
             only_as(8, kinds=(u"srt",), prefer=u"ass", title=u"Kusuriya no Hitorigoto"),
             l8.remembered_frieren()]
    window = l8.window_over(run_rows, mixed, watching=True)
    window.state.prefer_format = u"srt"
    window.show_tab(gui_app.TAB_PICK)
    take(window, u"L9-06-needs-you-blocked-and-taken")

    if failures:
        sys.stderr.write(u"FAILED to save: %s\n" % u", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        tempfile.gettempdir(), u"hato-layer9-shots")
    sys.exit(main(target))
