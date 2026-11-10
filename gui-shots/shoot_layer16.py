# -*- coding: utf-8 -*-
u"""
Photograph the SURASURA card -- RUNBOOK 16g -- in each of its states, so they can be
LOOKED at beside `gui-mock/mock-connect.html`.

    python gui-shots/shoot_layer16.py OUT_DIR

⚠ SEPARATE FROM `shoot.py` ON PURPOSE, like `shoot_layer8.py` / `shoot_layer9.py`: these
describe work not yet released. They go to OUT_DIR, never into this folder.

⭐ The same instrument, imported rather than copied (`shoot.settle`, `shoot.pin_machine_
state`): the real platform plugin, 1:1 logical pixels, `WA_DontShowOnScreen`.
⭐ THE WIRE'S SHAPE (LEDGER-HOT): every state is read from what is ON DISK -- a
surasura.json as Surasura 3.0 writes it (`tests/_surasura.install`) and pairing rows
written by the real producer, `connect.Handoff` (`_surasura.seed`) -- through the
window's own reader (`refresh_surasura`). ⛔ Never a Status typed here.
⛔ Each state in its OWN `HATO_CACHE`, `HATO_CONFIG` and `HOUSEKI_TOOLS_DIR`, under
OUT_DIR's scratch sibling: a shot never touches the real store or the real tools folder,
and no path in a picture names the account it was taken on.
"""
import os
import shutil
import sys
import tempfile

import shoot                                                       # noqa: E402  (sets the platform)

from PyQt6.QtCore import Qt                                        # noqa: E402
from PyQt6.QtWidgets import QApplication                           # noqa: E402

from hato.gui import app as gui_app                                # noqa: E402

import _surasura                                                   # noqa: E402
import test_gui_widgets as fx                                      # noqa: E402

#: The judged window (RUNBOOK §LAYER 16: 1100 × 660) and the narrow one.
WIDTHS = (1100, 860)
HEIGHT = 660

#: (name, the setting, how surasura.json reads, the rows the store holds)
STATES = (
    (u"1-cards", u"auto", dict(register=True),
     (u"registered",) * 11 + (u"retry",)),
    (u"2-nocards", u"auto", dict(register=False), (u"dropped",) * 12),
    (u"3-not-installed", u"auto", None, ()),
    (u"4-offline", u"auto", dict(register=True, drop_folders={}), ()),
    (u"5-too-new", u"auto", dict(register=True, contract=2, version=u"3.1.0"), ()),
    (u"6-off", u"off", dict(register=True), ()),
    (u"7-cards-waits", u"auto", dict(register=True),
     (u"registered",) * 9 + (u"retry", u"stopped", u"bad-data", u"drop-waiting",
                             u"expired")),
    (u"8-older-tray-off", u"off", dict(register=True), ()),
)


class _Env(object):
    u"""The two calls `_surasura.install` makes of pytest's monkeypatch, for real."""

    def setenv(self, name, value):
        os.environ[name] = value

    def delenv(self, name, raising=True):
        os.environ.pop(name, None)


def stage(root, setting, fields, outcomes):
    u"""One state's own world under `root`. -> the window, Settings scrolled to the card."""
    from hato import paths, state
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    os.environ["HATO_CACHE"] = os.path.join(root, u"cache")
    os.environ["HATO_CONFIG"] = os.path.join(root, u"config.toml")
    os.environ["HOUSEKI_TOOLS_DIR"] = os.path.join(root, u"houseki-tools")
    os.environ.pop("HATO_TOOLS_CLI", None)
    os.makedirs(os.environ["HOUSEKI_TOOLS_DIR"])
    home = _Path(os.path.join(root, u"Documents"))
    os.makedirs(str(home))
    if outcomes:
        _surasura.install(home, _Env(), register=True)
        paths.data_root().mkdir(parents=True, exist_ok=True)
        with state.StateDB(paths.state_db_path()) as db:
            _surasura.seed(db, home, list(outcomes))
    if fields is not None:
        _surasura.install(home, _Env(), **fields)
    return setting


def _Path(text):
    from pathlib import Path
    return Path(text)


def main(out_dir):
    application = QApplication.instance() or QApplication([])
    shoot.pin_machine_state()                 # ⛔ not this machine's registry
    os.makedirs(out_dir, exist_ok=True)
    scratch = os.path.join(os.environ.get(u"HATO_SHOTS_SCRATCH") or tempfile.gettempdir(),
                           u"hato-16g-shots")
    failures, sizes = [], {}

    def take(window, name, width):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        window.resize(width, HEIGHT)
        shoot.settle(application, window)
        area = window.panes[gui_app.TAB_SET]
        card = fx._surasura_card(window)
        area.verticalScrollBar().setValue(
            card.mapTo(area.widget(), card.rect().topLeft()).y() - 120)
        shoot.settle(application, window)
        if (window.width(), window.height()) != (width, HEIGHT):
            print(u"  %-40s WRONG SIZE %dx%d" % (name, window.width(), window.height()))
            failures.append(name)
        path = os.path.join(out_dir, name + u".png")
        ok = window.grab().save(path)
        size = os.path.getsize(path) if ok else 0
        print(u"  %-40s %s %s" % (name + u".png", u"ok" if ok else u"FAILED", size))
        if not ok:
            failures.append(name)
        sizes.setdefault(size, []).append(name)
        return fx._said(card)

    for name, setting, fields, outcomes in STATES:
        for width in WIDTHS:
            stage(os.path.join(scratch, name), setting, fields, outcomes)
            over = {}
            if name.endswith(u"older-tray-off"):
                over = dict(tray_reads_connect=False)
            window = fx.make(running=False, surasura_connect=setting, **over)
            window.refresh_surasura(render=False)
            window.show_tab(gui_app.TAB_SET)
            # ⚠ MEASURED 2026-10-30, two arms (this branch and its base): the window will
            # not go below 883 px -- its minimum since before Layer 16. The narrow shot
            # is taken at that minimum and NAMED by it, never filed as 860.
            least = window.minimumSizeHint().width()
            if least > width:
                print(u"  (the window's minimum is %d px: %d is shot at %d)"
                      % (least, width, least))
                width = least
            said = take(window, u"L16g-%s-%d" % (name, width), width)
            if width == WIDTHS[0]:
                print(u"      says: %s" % said)
            window.close()
    # ⭐ THE CHEAPEST TRIPWIRE (doctrine/evidence): two DIFFERENT states the same size
    # is a state that never landed
    for size, names in sorted(sizes.items()):
        states = set(n.rsplit(u"-", 1)[0] for n in names)
        if len(states) > 1:
            print(u"  ⚠ the same size (%d bytes): %s" % (size, u", ".join(names)))
    if failures:
        sys.stderr.write(u"FAILED: %s\n" % u", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(u"usage: shoot_layer16.py OUT_DIR\n")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
