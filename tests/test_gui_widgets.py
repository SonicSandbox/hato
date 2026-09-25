# -*- coding: utf-8 -*-
u"""
The window's widgets -- RUNBOOK 7c, `spec/05-interface.md` §The window.

The window is built against FIXTURE NDJSON and asserted on widget state. No
child process is ever started: `HatoWindow.spawn` is the one place a process
could begin and every check here replaces it with a recorder, so *"what does
this click commit"* is answered by an argv, not by a run.

===========================================================================
[!] WHAT THIS FILE IS STRUCTURALLY BLIND TO
===========================================================================

State assertions cannot see a render bug. In this project's own history:
status chips overflowed their column so the episode number vanished from
exactly the row that needed attention; a 900px gap opened between a filename
and its match rate; fifty green checks sat over a header running off the
screen. Every one of those passed every assertion that existed.

So `gui-shots/shoot.py` photographs every tab and every state, and the shots
are LOOKED AT. These checks pin what a picture cannot: that the count in two
places is one number, that a click commits the pair it names, and that the
engine's vocabulary never escapes.

===========================================================================
OFFSCREEN
===========================================================================

`QT_QPA_PLATFORM=offscreen` is set BEFORE PyQt6 is imported -- afterwards is
too late, the platform plugin is chosen at import. Verified on this machine:
PyQt6 6.11.0, Python 3.10.0, and `widget.grab().save(path)` writes a real PNG.
"""
import ast
import inspect
import os
import re
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent, QMouseEvent, QPalette
from PyQt6.QtWidgets import (QApplication, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)

from hato.gui import app as gui_app
from hato.gui import branding, theme
from hato.gui import run as gui_run

HERE = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.join(os.path.dirname(HERE), "hato", "gui")

#: ⛔ THIS FILE'S LIBRARY IS A WINDOWS ONE -- its videos live under `D:\Anime\...`.
#: On POSIX a backslash is a FILENAME character, so none of them sits under the
#: folders the fixture configures, and every rule that asks "is this video inside a
#: watched folder" answers differently. Measured on the first CI run of 1.0.2
#: (2026-09-23): six checks red on ubuntu and macOS, the product right on each. They
#: run on Windows -- locally, in the mutation gate, and in CI's three Windows jobs.
WINDOWS_LIBRARY = pytest.mark.skipif(
    not os.name == "nt",
    reason="the fixture library is D:\\Anime\\...; on POSIX a backslash is a filename character")


# ---------------------------------------------------------------------------
# one QApplication for the whole module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


# ---------------------------------------------------------------------------
# fixtures -- the shapes `run.py` reads, with `mock2.html`'s real content
# ---------------------------------------------------------------------------

def tsu(match_rate=0.82, verdict=u"locked", segments=((None, -33.07),),
        subtitle=None):
    return {u"video": u"D:\\Anime\\x.mkv", u"subtitle": subtitle or u"",
            u"outcome": u"CONFIDENT", u"match_rate": match_rate,
            u"verdict_word": verdict, u"segments": [list(s) for s in segments],
            u"reference_kind": u"text track", u"runtime_check": u"held",
            u"write_failed": False, u"lang": u"ja", u"lang_tag": u"ja"}


def added(episode=1, title=u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3",
          season=2, rate=0.82, name=None, entry=11446):
    u"""One CONFIDENT row that really was written. [!] `output_path` is what
    makes it *added*: a CONFIDENT row with no path is a dry run.

    \u26a0 `season` IS AN INT, as the wire carries it -- every fixture here used to
    write the STRING "S2", and the released window printed a bare *"\u00b7 4"* that
    no picture had ever shown (D10; ADVERSARY 2026-09-22's fixture findings)."""
    filename = name or (u"[NanakoRaws] Sousou no Frieren S2 - %02d "
                        u"(NTV 1080p).ass" % episode)
    return {u"type": u"video",
            u"video": u"D:\\Anime\\Sousou no Frieren S2\\ep%02d.mkv" % episode,
            u"name": u"ep%02d.mkv" % episode, u"title": title,
            u"season": season, u"episode": episode, u"outcome": u"CONFIDENT",
            u"skip": None, u"reason": u"", u"jimaku_entry": entry,
            u"jimaku_filename": filename, u"candidates_tried": 1,
            u"candidates_offered": 3, u"tsubasa": tsu(rate),
            u"nothing_written": None,
            u"output_path": u"D:\\Anime\\Sousou no Frieren S2\\ep%02d.ja.ass"
                            % episode,
            u"kept_path": u"C:\\hato\\subs\\ep%02d.ja.ass" % episode,
            u"api_calls": 2, u"bytes_downloaded": 38912, u"retry_after": None,
            u"attempts": []}


#: \u26a0 ONE POOL PER SHOW, AND THAT IS NOT TIDINESS -- IT IS THE PICTURE.
#: `needs_you` took a single hard-coded Re:Zero pool, so the FRIEREN row was
#: built from `pool[:1]` and the screenshot sent for review showed a Frieren
#: episode whose only candidate was an `[Erai-raws] Re Zero 3rd - 54` file at
#: 57% -- where the ruled mock has its own NanakoRaws file at 31%.
#: \ud83d\udea8 Every check still passed: they assert the row's SHAPE, and the shape was
#: right. Found by opening the PNG.
#: \u2b50 `build-ui.md` names this exactly: *a mock's seed data is shipped content,
#: because the picture is the deliverable* -- and the sibling case it records
#: is a seed that printed the literal word "chosen" where a filename belongs.
REZERO_POOL = [
    (u"[Erai-raws] Re Zero 3rd - 54 [1080p][Multiple Subtitle].ass", 0.57, 29696),
    (u"[SubsPlease] Re Zero kara Hajimeru Isekai Seikatsu S3 - 54.srt", 0.41, 22528),
    (u"Re.Zero.S03E54.1080p.WEB.ja[cc].srt", 0.38, 19456)]
FRIEREN_POOL = [
    (u"[NanakoRaws] Sousou no Frieren S2 - 03 (NTV 1080p HEVC).ass", 0.31, 36864)]


def needs_you(episode=54,
              title=u"Re:\u30bc\u30ed\u304b\u3089\u59cb\u3081\u308b\u7570\u4e16\u754c\u751f\u6d3b",
              season=3, how_many=3, pool=None):
    u"""One REFUSED row -- which the interface calls *needs a pick*.

    [!] The engine's `reason` DELIBERATELY carries the alarming word, because
    that is what the real engine writes and the whole point of `safe()` is
    that a verbatim field cannot put it on screen.

    \u26a0 `pool` defaults to Re:Zero's. Pass the show's OWN candidates for any
    other row -- see the note on REZERO_POOL.

    \u26a0 THE WIRE'S SHAPE: an INT season, and a retry date -- every refusal of
    files records the soft negative `_all_refused` writes, and a REFUSED row
    with no `retry_after` is one the engine never sends (ADVERSARY 2026-09-22).
    """
    pool = REZERO_POOL if pool is None else pool
    attempts = []
    for name, rate, size in pool[:how_many]:
        attempts.append({
            u"name": name, u"outcome": u"REFUSED",
            u"reason": u"the pair was refused: 57% is under the floor",
            u"bytes": size, u"match_rate": rate,
            u"tsubasa": tsu(rate, verdict=None,
                            subtitle=u"C:\\hato\\subs\\" + name)})
    return {u"type": u"video",
            u"video": u"D:\\Anime\\ReZero S03\\ep%02d.mkv" % episode,
            u"name": u"ep%02d.mkv" % episode, u"title": title,
            u"season": season, u"episode": episode, u"outcome": u"REFUSED",
            u"skip": None,
            u"reason": u"every candidate was refused; the timing did not hold",
            u"jimaku_entry": 9921, u"jimaku_filename": None,
            u"candidates_tried": how_many, u"candidates_offered": how_many,
            u"tsubasa": None, u"nothing_written": u"nothing was written",
            u"output_path": None, u"kept_path": None, u"api_calls": 1,
            u"bytes_downloaded": 71680,
            u"retry_after": u"2026-09-23T12:00:00.123456+00:00",
            u"attempts": attempts}


def skipped(episode=7,
            title=u"\u7247\u7530\u820e\u306e\u304a\u3063\u3055\u3093\u3001\u5263\u8056\u306b\u306a\u308b",
            skip=u"present", **over):
    u"""A SKIP row.

    🚨 `skip` USED TO BE THE SENTENCE *"already has a Japanese subtitle"*, and
    the engine cannot emit that. It emits one of five TOKENS -- `present`,
    `embedded`, `negative`, `no-track`, `blacklisted` (`pipeline.py`) -- and
    every widget check about a skipped row was therefore driving a shape that
    has never come down the wire. It passed only because the reader did
    `if obj.get("skip")`, which any non-empty string satisfies.

    ⛔ That is the fixture holding constant the exact thing the defect varied.
    """
    row = {u"type": u"video",
           u"video": u"D:\\Anime\\Katainaka II\\ep%02d.mkv" % episode,
           u"name": u"ep%02d.mkv" % episode, u"title": title,
           u"season": None, u"episode": episode, u"outcome": u"CONFIDENT",
           u"skip": skip, u"reason": u"",
           u"jimaku_entry": None, u"jimaku_filename": None,
           u"candidates_tried": 0, u"candidates_offered": 0,
           u"tsubasa": None, u"nothing_written": None, u"output_path": None,
           u"kept_path": None, u"api_calls": 0, u"bytes_downloaded": 0,
           u"retry_after": None, u"attempts": []}
    row.update(over)
    return row


def embedded(episode=11, title=u"Katainaka no Ossan Kensei ni Naru"):
    u"""Sonic's real Katainaka row: an Erai-raws [MultiSub], Japanese INSIDE."""
    return skipped(episode=episode, title=title, skip=u"embedded",
                   outcome=u"SKIPPED",
                   reason=u"an embedded ja text track is already there "
                          u"(track 11, S_TEXT/ASS) -- already in sync, so "
                          u"nothing was fetched")


def retrying(episode=12,
             title=u"Tsuihou sareta Tensei Juukishi wa Game Chishiki de Musou suru"):
    u"""Sonic's real Tsuihou row: downloaded 3 of 10, kept none, retries."""
    return skipped(episode=episode, title=title, skip=u"negative",
                   outcome=u"SKIPPED",
                   reason=u"3 of 10 candidate(s) tried, all refused by timing",
                   retry_after=u"2026-09-20T07:03:05.264054+00:00")


def not_yet(episode=24, title=u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3"):
    u"""NOT_FOUND. ⚠ The wire's `retry_after` is a full ISO moment with its zone,
    never a bare date -- a date-only fixture was a shape the engine never sends."""
    return {u"type": u"video",
            u"video": u"D:\\Anime\\Sousou no Frieren S2\\ep%02d.mkv" % episode,
            u"name": u"ep%02d.mkv" % episode, u"title": title,
            u"season": 2, u"episode": episode, u"outcome": u"NOT_FOUND",
            u"skip": None, u"reason": u"nothing on jimaku yet; retry 19 Sep",
            u"jimaku_entry": 11446, u"jimaku_filename": None,
            u"candidates_tried": 0, u"candidates_offered": 0,
            u"tsubasa": None, u"nothing_written": None, u"output_path": None,
            u"kept_path": None, u"api_calls": 1, u"bytes_downloaded": 0,
            u"retry_after": u"2026-09-19T07:03:05.264054+00:00", u"attempts": []}


def broke(episode=1, title=u"Tetsunabe no Jan"):
    u"""ERROR. [!] Its reason carries the engine's word too."""
    return {u"type": u"video",
            u"video": u"D:\\Anime\\Tetsunabe no Jan\\ep%02d.mkv" % episode,
            u"name": u"ep%02d.mkv" % episode, u"title": title,
            u"season": None, u"episode": episode, u"outcome": u"ERROR",
            u"skip": None,
            u"reason": u"the container would not open, so the pair was refused",
            u"jimaku_entry": None, u"jimaku_filename": None,
            u"candidates_tried": 0, u"candidates_offered": 0,
            u"tsubasa": None, u"nothing_written": u"nothing was written",
            u"output_path": None, u"kept_path": None, u"api_calls": 0,
            u"bytes_downloaded": 0, u"retry_after": None, u"attempts": []}


def summary(api_calls=6, seconds=41.2, notes=()):
    return {u"type": u"run", u"api_calls": api_calls, u"seconds": seconds,
            u"videos": 7, u"stopped": False, u"dry_run": False,
            u"folders": [u"D:\\Anime"], u"lang": u"ja", u"notes": list(notes),
            u"shows": []}


FRIEREN = u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3"
REZERO = u"Re:\u30bc\u30ed\u304b\u3089\u59cb\u3081\u308b\u7570\u4e16\u754c\u751f\u6d3b"
KATAINAKA = (u"\u7247\u7530\u820e\u306e\u304a\u3063\u3055\u3093\u3001"
             u"\u5263\u8056\u306b\u306a\u308b")


def rezero_added(episode, rate, verdict=u"locked"):
    row = added(episode, REZERO, 3, rate,
                name=u"[Erai-raws] Re Zero kara Hajimeru Isekai Seikatsu "
                     u"3rd - %d.ass" % episode, entry=9921)
    row[u"tsubasa"][u"verdict_word"] = verdict
    return row


def one_piece(episode=1121, rate=0.79):
    return added(episode, u"ONE PIECE", None, rate,
                 name=u"[Erai-raws] One Piece - %d [1080p]"
                      u"[Multiple Subtitle].ass" % episode, entry=41)


def full_rows():
    u"""The 2026-09-17 test-bed run, in the shapes the wire uses.

    Deliberately the mock's own content: three shows with added rows, one show
    that was wholly skipped, episodes skipped INSIDE an added show, two that
    need a pick, one not on jimaku yet and one that broke -- so a shot
    exercises every branch of the render rather than the easy one.
    """
    strong = added(4, rate=0.91)
    strong[u"tsubasa"][u"verdict_word"] = u"strong"
    weak = rezero_added(55, 0.63, verdict=u"fair")
    return [added(1, rate=0.82), added(2, rate=0.96), strong,
            skipped(11, FRIEREN), skipped(12, FRIEREN), skipped(13, FRIEREN),
            rezero_added(52, 0.80), weak,
            one_piece(),
            needs_you(54),
            needs_you(3, FRIEREN, 2, how_many=1, pool=FRIEREN_POOL),
            skipped(7), skipped(8), not_yet(24), broke(1)]


def test_every_candidate_offered_belongs_to_the_row_that_offers_it():
    u"""🚨 FOUND BY OPENING THE PNG, AND NO CHECK COULD SEE IT.

    `needs_you` carried ONE hard-coded Re:Zero candidate pool, so the Frieren
    row -- built as `pool[:1]` -- offered `[Erai-raws] Re Zero 3rd - 54` at
    57%, where the ruled mock has its own NanakoRaws file at 31%. Every check
    passed, because they all assert the row's SHAPE and the shape was right.

    ⭐ `build-ui.md`: *a mock's seed data is shipped content, because the
    picture is the deliverable.* A screenshot that misreports the product is
    worse than no screenshot -- it is a wrong answer somebody rules on.

    ⚠ The assertion is deliberately about the EPISODE NUMBER rather than the
    show's name: a candidate for a different episode of the right show is the
    same defect wearing better clothes.
    """
    for row in full_rows():
        episode = row.get(u"episode")
        for attempt in row.get(u"attempts") or ():
            assert u"%02d" % episode in attempt[u"name"] \
                or u"%d" % episode in attempt[u"name"], (
                u"%s is offered as a candidate for episode %s, which is not "
                u"its episode -- the picture would show one show's file under "
                u"another show's row" % (attempt[u"name"], episode))


SETTINGS = dict(
    folders=[u"D:\\Anime\\Sousou no Frieren S2", u"D:\\Anime\\ReZero S03",
             u"D:\\Anime\\One Piece", u"D:\\Anime\\Katainaka II",
             u"D:\\Anime\\Tetsunabe no Jan"],
    # ⛔ NO REAL ACCOUNT NAMES IN A FIXTURE. These strings are rendered into
    # the screenshots the README embeds and into a public test file, so they
    # stay invented. Corrected 2026-09-18 after the first push.
    skip_folders=[u"D:\\Downloads\\in progress", u"D:\\Anime\\_incoming"],
    blacklist=[{u"name": u"Tetsunabe no Jan - 01.mkv",
                u"note": u"a commentary track, no subs exist",
                u"when": u"17 Sep", u"gone": False},
               {u"name": u"ONE PIECE - 1089.mkv", u"note": u"recap",
                u"when": u"17 Sep", u"gone": False},
               {u"name": u"Frieren S1 - 12.mkv",
                u"note": u"not on this machine any more",
                u"when": u"2 Aug", u"gone": True},
               {u"name": u"Bocchi the Rock - 07.mkv",
                u"note": u"not on this machine any more",
                u"when": u"28 Jul", u"gone": True}],
    key_hint=u"JyQ", schedule=u"03:00",
    last_run=u"03:00", live=u"Tetsunabe no Jan",
    running=True)


def make(rows=None, **over):
    u"""A window over fixture rows, with `spawn` recording instead of running."""
    settings = dict(SETTINGS)
    # ⚠ THE SUITE'S OWN CLOCK. The rows carry real retry dates now, as the wire
    # does, and a window reading the wall clock would say "retry due" on one day
    # and "retry after 13h" on another -- a check that depends on the date.
    settings.setdefault(u"now", NOW8)
    settings.update(over)
    state = gui_app.build_state_from(
        full_rows() if rows is None else rows, summary(), **settings)
    window = gui_app.HatoWindow(state)
    window.spawned = []
    window.spawn = window.spawned.append
    return window


def click(widget):
    u"""A real left click on a `Clickable`, through Qt's own event path."""
    centre = widget.rect().center()
    for kind in (QMouseEvent.Type.MouseButtonPress,
                 QMouseEvent.Type.MouseButtonRelease):
        event = QMouseEvent(kind, centre.toPointF() if hasattr(centre, "toPointF")
                            else QPoint(centre), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, event)


def source(name):
    with open(os.path.join(GUI_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def lay_out(window, width=gui_app.WIN_W, height=gui_app.WIN_H):
    u"""Give the window a real geometry, so a check can measure one.

    [!] WITHOUT THIS EVERY WIDGET IS AT ITS DEFAULT SIZE and a geometry
    assertion measures nothing. The three checks below exist because three
    layout defects shipped past a hundred green state assertions and were
    caught by opening a PNG; they are only checks at all if the layout has
    actually run.
    """
    window.resize(width, height)
    window.show()
    for _ in range(4):
        window.layout().activate()
        QApplication.processEvents()
    return window


# ===========================================================================
# 0 -- [!] what a control paints when you are not looking
# ===========================================================================

def test_setting_a_switch_does_not_animate_to_its_own_value(qapp):
    u"""🚨 REPORTED BY SONIC, 2026-09-18: *"when i click on settings, the
    toggles go from nothing to what they were toggled. Just slightly visually
    jarring as if it was changing right then."*

    `super().setChecked()` EMITS `toggled`, which starts the slide from wherever
    the knob is -- and on a freshly built tab that is 0. So opening Settings
    played every switch turning itself on: the animation for *a value just
    changed*, used for *here is the value*.

    ⛔ THE ASSERTION IS THAT THE ANIMATION IS STOPPED, not that the knob has
    landed. With the defect the knob is ALSO at 1.0 for this instant -- it is
    set right after the signal -- and the animation then drags it back to 0 on
    its first tick. A check on the position alone is green against the bug.
    """
    from PyQt6.QtCore import QAbstractAnimation

    switch = gui_app.Switch()
    switch.setChecked(True)
    assert switch._travel == 1.0
    assert switch._anim.state() == QAbstractAnimation.State.Stopped, (
        u"the switch is animating to the value it was just told to hold, so "
        u"opening the tab plays it turning itself on")

    # ⭐ And a real INTERACTION still animates -- the fix must not flatten the
    # thing that made it feel alive.
    switch.click()
    assert switch._anim.state() == QAbstractAnimation.State.Running


def test_no_button_in_the_window_is_inert(qapp):
    u"""🚨 THREE BUTTONS SHIPPED DEAD, AND SONIC FOUND THEM (2026-09-18):
    *"nothing happens when i click on add a folder."*

    *Add a folder…*, *Add a folder to skip…* and the key's *Replace* were all
    built, all rendered perfectly, and none was connected to anything. The
    method behind the first one **already existed, was correct, and documented
    itself as "the one Settings' 'Add a folder...' reaches"** -- so the prose
    asserted a wiring that was not there, and 122 checks proved the API
    without ever clicking a button.

    ⭐ `build-ui.md` records this exact failure shipping THREE times in one
    build for the same reason, and its rule is a static wiring check. This is
    that rule for Qt: a control with no connection is not a styling problem or
    a logic problem, it is a control that does nothing, and nothing else in a
    suite notices.

    ⚠ EVERY TAB IS SHOWN FIRST. Settings' widgets do not exist until the tab
    has been rendered once, so a check that skipped that would walk a window
    holding only the buttons that were already fine.

    ⚠ `QAbstractButton`, NOT `QPushButton` -- WIDENED 2026-09-18 AFTER IT MISSED
    ONE. The first version walked push buttons only, so the *"Watch for new
    videos and run"* TICK BOX sailed past it, and Sonic found that one himself:
    *"I didn't see hato enter the windows tray."* A checkbox is a control like
    any other, and the base class covers every kind at once.
    """
    window = make()
    # ⚠ EVERY ROW OPEN (RUNBOOK 13e): a closed row builds no panel now, and the
    # panel's *Open video* is a control this walk must reach
    window.state.open_rows = set(window.state.key(r) for r in window.state.rows)
    for tab in gui_app.TABS:
        window.show_tab(tab)

    inert = []
    for widget in window.findChildren(gui_app.QAbstractButton):
        if widget.receivers(widget.clicked) == 0:
            inert.append(u"%s(%s)" % (type(widget).__name__,
                                      widget.text() or widget.objectName()
                                      or u"no label"))
    # ⚠ AND EVERY TEXT FIELD (RUNBOOK 13j): the blacklist's *"Filter by name or
    # show…"* was built, placed and connected to nothing, and this walk -- buttons
    # only -- sailed past it for as long as the card has existed
    for field in window.findChildren(QLineEdit):
        said = (field.textChanged, field.textEdited, field.editingFinished,
                field.returnPressed)
        if not any(field.receivers(signal) for signal in said):
            inert.append(u"QLineEdit(%s)" % (field.placeholderText()
                                             or field.objectName() or u"no label"))
    assert not inert, (
        u"these controls are rendered and connected to nothing, so using them "
        u"does nothing at all: %s" % u", ".join(sorted(inert)))


def test_a_setting_written_by_the_window_is_there_when_it_reopens(qapp, tmp_path,
                                                                  monkeypatch):
    u"""🚨 THE ROUND TRIP WAS NEVER CLOSED, AND THAT IS WHAT SONIC SAW.

    *"i don't think my settings are being saved."* They were -- every one,
    correctly, through `hato config`. What was missing is the other half:
    `main()` built the window with no arguments, so every session opened on
    DEFAULTS. Add a folder, close, reopen, and it is gone from the list while
    sitting in `config.toml` the whole time.

    ⭐ THE HARDEST SHAPE TO SEE FROM THE INSIDE. The write path was built,
    checked and genuinely working; every check asserted what the window SENT.
    Not one of them asked what a NEW window would show, so the missing loader
    was invisible to a suite that never reopened anything.

    ⚠ This drives the real writer and the real reader -- no stubbing -- so it
    fails if either end breaks, which is the only way a round trip is proved.
    """
    from hato import config as config_module

    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "config.toml"))
    folder = tmp_path / "Anime"
    folder.mkdir()

    cfg = config_module.load()
    config_module.save(config_module.with_changes(
        cfg, folders=[str(folder)], recurse=False, watch=True,
        schedule=u"05:30"))

    fresh = gui_app.settings_from_disk()
    assert [os.path.normcase(f) for f in fresh.folders] == \
        [os.path.normcase(str(folder))]
    assert fresh.recurse is False
    assert fresh.watch is True
    assert fresh.schedule == u"05:30"
    assert not fresh.config_error


def test_a_config_the_reader_refuses_is_reported_not_swallowed(qapp, tmp_path,
                                                               monkeypatch):
    u"""⛔ A window that opened on silent defaults would be telling somebody
    their settings had vanished. The refusal is what explains an empty list."""
    bad = tmp_path / "config.toml"
    bad.write_text(u"candidates = 0\n", encoding="utf-8")
    monkeypatch.setenv("HATO_CONFIG", str(bad))

    fresh = gui_app.settings_from_disk()
    assert fresh.config_error
    assert u"at least 1" in fresh.config_error


def test_a_second_launch_finds_the_first_window_instead_of_stacking(qapp,
                                                                    monkeypatch):
    u"""🚨 SONIC: *"we also need to ensure that only one hato is ever open at a
    time."* He named the tray; the WINDOW had it too, and this session's own
    testing proved it by leaving FIVE stacked window processes behind.

    ⭐ RAISE, DON'T REFUSE. A second launch that merely exits looks like a
    broken shortcut -- you double-click and nothing happens.

    ⚠ The check drives the REAL local socket, so it fails if either half
    breaks: nothing listening must read as *nobody there*, and a listener must
    be found.

    🚨 ON A NAME OF ITS OWN, AND THAT IS A FIX. Written against the product's
    real name it passed alone and went RED in the full run -- because an actual
    hato window was open on this machine and answered. The check was asserting
    a fact about the DESKTOP, not about the code. ⛔ This project has been here
    before: its first public CI run was red on all twelve jobs and not one
    failure was functional. A check that needs the machine to be in a
    particular state is a check that fails for reasons its name does not
    mention.
    """
    from PyQt6.QtNetwork import QLocalServer

    name = u"hato-window-test-%d" % os.getpid()
    monkeypatch.setattr(gui_app, "instance_name", lambda: name)

    QLocalServer.removeServer(name)
    assert gui_app.raise_existing_window(timeout_ms=150) is False, (
        u"something answered when no window was listening")

    window = make()
    server = gui_app.listen_for_second_launch(window)
    assert server is not None, u"the window could not listen at all"
    try:
        assert gui_app.raise_existing_window(timeout_ms=800) is True, (
            u"a running window was not found, so a second launch would stack")
    finally:
        server.close()
        QLocalServer.removeServer(name)


def test_a_name_held_by_something_that_cannot_ANSWER_does_not_swallow_a_launch(
        qapp, monkeypatch):
    u"""🚨 SONIC'S BUG, 2026-09-18: *"close hato... then go to the tray to open
    it, it doesn't do anything... I have to close hato from the tray."*

    A window process was found ALIVE WITH NO WINDOW, still holding the
    single-instance name. Every later launch connected, concluded a window was
    there, and exited -- so nothing opened and nothing said why.

    ⛔ A CONNECTION PROVES THE NAME IS HELD, NOT THAT ANYBODY IS LISTENING.
    This stands up a server that accepts and never replies -- exactly that
    wedged state -- and requires the launch to decide *nobody is there* and
    open its own window. ⭐ The failure becomes a second window, which is
    visible and harmless, instead of silence.

    ⚠ Four attempts failed to reproduce the lingering process on demand, so
    this check does not depend on knowing why it lingered.
    """
    from PyQt6.QtNetwork import QLocalServer

    name = u"hato-window-mute-%d" % os.getpid()
    monkeypatch.setattr(gui_app, "instance_name", lambda: name)
    QLocalServer.removeServer(name)

    mute = QLocalServer()
    # ⛔ Deliberately NO `newConnection` handler: it accepts and never answers.
    assert mute.listen(name), u"the mute server could not take the name"
    try:
        assert gui_app.raise_existing_window(timeout_ms=300) is False, (
            u"a launch believed a wedged process was a live window, so it "
            u"would exit and nothing would open")
    finally:
        mute.close()
        QLocalServer.removeServer(name)


def test_closing_the_window_releases_the_name_for_the_next_launch(qapp,
                                                                  monkeypatch):
    u"""⭐ The other half: the name must be free the moment the window closes,
    so a later launch always opens something."""
    from PyQt6.QtNetwork import QLocalServer

    name = u"hato-window-close-%d" % os.getpid()
    monkeypatch.setattr(gui_app, "instance_name", lambda: name)
    QLocalServer.removeServer(name)

    window = make()
    window._instance_server = gui_app.listen_for_second_launch(window)
    assert gui_app.raise_existing_window(timeout_ms=800) is True

    window.close()
    assert gui_app.raise_existing_window(timeout_ms=300) is False, (
        u"the closed window still holds the name, so the next launch would "
        u"exit and nothing would open")


def test_the_instance_name_is_per_user(qapp):
    u"""⚠ Two people signed into one machine each get their own hato. A shared
    name would have one person's launch raise a window on a desktop they
    cannot see."""
    import getpass
    assert getpass.getuser() in gui_app.instance_name()


def test_the_footer_says_a_queued_run_is_coming(qapp):
    u"""🚨 SONIC REPORTED AUTO-FETCH AS BROKEN AND IT WAS NOT. He dropped a
    video into a watched subfolder and nothing appeared; the whole chain worked
    when measured. What he hit was the settle minute -- his own ruling -- with
    nothing anywhere saying a run was coming.

    ⭐ AN INVISIBLE WAIT IS INDISTINGUISHABLE FROM BROKEN. The delay was right;
    the silence was the defect.
    """
    state = gui_app.State()
    assert gui_app.footer_status(state) == u"idle"

    state.queued_in, state.queued_names = 47.0, [u"D:\\A\\frieren S2 - 01.mkv"]
    line = gui_app.footer_status(state)
    assert u"frieren S2 - 01.mkv" in line, line   # the FILE, not a count
    assert u"47s" in line

    # ⚠ Under five seconds a number that keeps changing reads as noise.
    state.queued_in = 3.0
    assert u"in a moment" in gui_app.footer_status(state)

    # ⛔ A run in progress outranks a queued one -- it is what is happening NOW.
    state.running, state.live = True, u"running — Frieren"
    assert gui_app.footer_status(state) == u"running — Frieren"


def test_several_queued_videos_are_counted_rather_than_listed(qapp):
    state = gui_app.State()
    state.queued_in = 30.0
    state.queued_names = [u"a.mkv", u"b.mkv", u"c.mkv"]
    assert u"3 new videos" in gui_app.footer_status(state)


def test_a_stale_countdown_is_not_shown(qapp, tmp_path, monkeypatch):
    u"""⛔ A tray killed mid-wait leaves its file behind. Believed, the window
    would count down for ever to a run nothing will ever start."""
    from hato import watch

    memory = tmp_path / "watch-pending.json"
    monkeypatch.setattr(watch, "pending_path", lambda: memory)
    watch.write_pending(time.time() - 30.0, [u"old.mkv"])   # already due
    assert watch.read_pending() == (0.0, [])


def test_the_window_picks_up_a_run_it_did_not_start(qapp, tmp_path, monkeypatch):
    u"""🚨 SONIC: *"I dragged a video into a folder, it worked but the ui didn't
    update -- it was until i hit run."* The tray, the scheduler and a terminal
    are all other processes; hato now records every run and the window watches
    that file.

    ⚠ THE TIMER IS DRIVEN BY HAND. A check that slept three seconds to see a
    poll fire would be slow AND flaky; calling the callback directly tests the
    decision, which is the part that can be wrong.
    """
    from hato import lastrun

    memory = tmp_path / "last-run.json"
    monkeypatch.setattr(gui_run, "last_run_stamp",
                        lambda path=None: lastrun.stamp(path=memory))
    monkeypatch.setattr(gui_run, "load_last_run",
                        lambda path=None: lastrun.load(path=memory))

    # ⚠ `running=False` IS THE PRECONDITION, SAID OUT LOUD. The shared fixture
    # defaults to a run in progress, and the window deliberately stands aside
    # then -- so without this the check fails against correct code, which is
    # how it first failed.
    window = make(rows=[], running=False)
    window.follow_other_runs(every_ms=60000)          # ⛔ never fires on its own
    look = window._others_timer.timeout

    lastrun.save([added(7, rate=0.88)], {u"type": u"run", u"api_calls": 2},
                 path=memory)
    look.emit()

    assert [r.get(u"episode") for r in window.state.rows] == [7], (
        u"a run started elsewhere left the window showing nothing")


def test_a_run_this_window_is_painting_is_not_overwritten(qapp, tmp_path,
                                                          monkeypatch):
    u"""⛔ The window's own run paints LIVE rows off the stream. Reloading the
    file underneath it would replace them with a snapshot taken a moment
    earlier -- rows appearing and then vanishing mid-run."""
    from hato import lastrun

    memory = tmp_path / "last-run.json"
    monkeypatch.setattr(gui_run, "last_run_stamp",
                        lambda path=None: lastrun.stamp(path=memory))
    monkeypatch.setattr(gui_run, "load_last_run",
                        lambda path=None: lastrun.load(path=memory))

    window = make(rows=[added(1)])
    window.follow_other_runs(every_ms=60000)
    window.state.running = True

    lastrun.save([added(99)], {u"type": u"run"}, path=memory)
    window._others_timer.timeout.emit()

    assert [r.get(u"episode") for r in window.state.rows] == [1], (
        u"the live run's rows were replaced by a stale snapshot")


def test_a_dry_run_landing_does_not_replace_what_the_window_shows(qapp, tmp_path,
                                                                  monkeypatch):
    u"""🚨 RUNBOOK 8a. hato 1.0.1 writes a dry run's PLAN into the window's
    memory, and one is sitting on Sonic's disk now: its rows are PLANNED, which
    `outcome_word` calls *"something went wrong"*.

    ⚠ THE STAMP MOVES, SO THE WINDOW LOOKS -- and must then keep the real run it
    already has. A dry run is not a run.
    """
    from hato import lastrun

    memory = tmp_path / "last-run.json"
    monkeypatch.setattr(gui_run, "last_run_stamp",
                        lambda path=None: lastrun.stamp(path=memory))
    monkeypatch.setattr(gui_run, "load_last_run",
                        lambda path=None: lastrun.load(path=memory))

    window = make(rows=[added(1)], running=False)
    window.follow_other_runs(every_ms=60000)
    planned = dict(added(99), outcome=u"PLANNED", output_path=None,
                   reason=u"would fetch: 3 candidates offered")
    lastrun.save([planned], {u"type": u"run", u"dry_run": True}, path=memory)
    window._others_timer.timeout.emit()

    assert [r.get(u"episode") for r in window.state.rows] == [1], (
        u"a dry run's plan replaced the last real run on screen")
    assert u"99" not in u" ".join(gui_app.texts(window))


def test_the_surasura_card_is_last_and_carries_its_mark(qapp):
    u"""⭐ SONIC: *"Not everyone's going to want this so I don't want it to be
    the headliner. I want it to be down below in settings."*

    ⚠ The ORDER is the requirement, so the check is on the order -- not merely
    on the card existing, which would stay green if it drifted to the top.

    ⭐ AMENDED 2026-09-24 BY A LATER RULING: the auto-update mock Sonic approved
    (*"I take all your leans"*, gui-mock/mock-update.html state 7, RUNBOOK 11f)
    puts *Updates* after it. surasura stays below every card a person uses day
    to day; only the card about hato itself follows it.
    """
    window = make()
    window.show_tab(gui_app.TAB_SET)

    titles = [w.text() for w in window.findChildren(gui_app.QLabel)
              if w.objectName() == u"cardtitle"]
    assert titles, u"the settings tab built no cards at all"
    assert [t.lower() for t in titles[-2:]] == [u"surasura", u"updates"], (
        u"surasura is not last but for Updates: %s" % u", ".join(titles))

    marks = [w for w in window.findChildren(gui_app.QLabel)
             if w.pixmap() is not None and not w.pixmap().isNull()]
    assert marks, u"the integration card shows no mark"


def test_choosing_a_surasura_folder_saves_it_and_turning_it_off_clears_it(qapp):
    u"""⛔ Empty means off, and the same key carries both -- so there is no
    second setting that could disagree about whether it is on."""
    window = make()
    sent = []
    window.spawn = lambda argv, **kw: sent.append(argv) or None

    window.state.surasura_dir = u""
    window.clear_surasura()
    assert any(u"surasura_dir=" in u" ".join(a) for a in sent)
    assert window.state.surasura_dir == u""


def test_surasura_is_a_real_setting_the_schema_knows(qapp):
    u"""⚠ The window writes `surasura_dir`; a key the schema refuses is
    silently never saved. The general guard covers this too -- this names it,
    because it is the newest one."""
    from hato import config as config_module
    assert u"surasura_dir" in config_module.SCHEMA


def test_the_key_dialog_is_hatos_own_and_hides_what_is_typed(qapp):
    u"""🚨 SONIC, 2026-09-18: *"when you hit add a key for the jimaku key it is
    white and ugly."* It was a `QInputDialog` -- a NATIVE control, themed by Qt
    and not by hato, in the middle of a dark coral app.

    ⭐ Third time this project has paid for the same rule: **a control's
    appearance is decided somewhere you are not looking.** The Windows-blue
    radio, the circular checkbox, and now a white modal.

    ⚠ And the field hides what is typed, because a key is a secret going onto a
    screen somebody may be sharing.
    """
    dialog = gui_app.KeyDialog(None, replacing=False)
    assert dialog.styleSheet(), u"the dialog wears no stylesheet at all"
    fields = dialog.findChildren(gui_app.QLineEdit)
    assert fields, u"the dialog has no field to type a key into"
    assert fields[0].echoMode() == gui_app.QLineEdit.EchoMode.Password
    labels = u" ".join(w.text() for w in dialog.findChildren(gui_app.QLabel)
                       if w.text())
    assert u"jimaku.cc" in labels, u"it never says where to get a key"


def test_the_key_dialog_says_swap_when_one_is_already_set(qapp):
    u"""⭐ *"if there is a key the swap for a different key or something."*"""
    adding = gui_app.KeyDialog(None, replacing=False)
    swapping = gui_app.KeyDialog(None, replacing=True)

    def words(dialog):
        return u" ".join(
            [w.text() for w in dialog.findChildren(gui_app.QLabel) if w.text()]
            + [b.text() for b in dialog.findChildren(gui_app.QPushButton)])

    assert u"Swap" in words(swapping)
    assert u"Swap" not in words(adding)


def test_a_key_that_saves_is_checked_against_jimaku(qapp):
    u"""⭐ SONIC: *"if it works it should test run it to see if connected, and
    show that it is connected just fine."*

    ⚠ A KEY THAT RESOLVES IS NOT A KEY THAT WORKS, and that gap is exactly what
    somebody pasting one is worried about. `hato key --show` answers the first
    question; only jimaku can answer the second.

    ⛔ The check spends ONE metered request and happens on ENTRY only -- never
    on launch, never on render: *"just on the key entry, not another time."*
    """
    window = make()
    sent = []

    class Answer(object):
        def communicate(self, timeout=None):
            return (b'{"ok": true, "connected": true, "hint": "\\u2026ab12"}',
                    b"")

    window.spawn = lambda argv, **kw: sent.append(argv) or Answer()
    ok, message = window.verify_key()

    assert ok is True
    assert u"Connected" in message
    assert sent and sent[0][-3:] == [u"key", u"--test", u"--json"]


def test_a_key_jimaku_refuses_says_so_rather_than_claiming_success(qapp):
    window = make()

    class Answer(object):
        def communicate(self, timeout=None):
            return (b'{"ok": false, "connected": false, '
                    b'"error": "jimaku refused the key"}', b"")

    window.spawn = lambda argv, **kw: Answer()
    ok, message = window.verify_key()
    assert ok is False
    assert u"refused" in message


def test_the_key_itself_never_reaches_a_command_line(qapp):
    u"""🚨 A COMMAND LINE IS READABLE BY EVERY OTHER PROCESS on the machine
    through the process table. The key goes in on STDIN and nowhere else."""
    window = make()
    sent = []
    window.spawn = lambda argv, **kw: sent.append((argv, kw)) or None
    window.set_key(u"supersecretkey99")

    for argv, kwargs in sent:
        assert all(u"supersecretkey99" not in str(part) for part in argv), argv
        assert kwargs.get(u"stdin_text", u"").strip() == u"supersecretkey99"


# ---------------------------------------------------------------------------
# 🚨 the write must LAND before the connection test asks about it
#
# `set_key` used to spawn `hato key --set-from -` and `return True` without
# waiting. `choose_key` then ran `hato key --test`, which reads the KEYSTORE --
# so on the SWAP path the test could read the OLD, still-valid key and report
# "Connected" about a brand-new bad one. Adversarial pass, 2026-09-18.
# ---------------------------------------------------------------------------

def test_an_OPEN_accordion_carries_no_graphics_effect(qapp):
    u"""🚨 THE HOVER BUG, PINNED AT ITS MECHANISM.

    Sonic, 2026-09-19, on the published 1.0.0: *"when you hover over the
    options for the episodes in the needs you, the option goes invisible
    while you hover over it."*

    ⛔ A `QGraphicsEffect` CACHES THE SOURCE IT DRAWS, and this one stayed
    attached for the widget's whole life. A repaint of a DESCENDANT -- which
    is exactly what `#cand:hover` triggers -- never reached the composited
    result, so the stale cache was drawn and the card rendered as nothing.

    ⭐ MEASURED at the time: hovering took the card's region of the window
    from **964 bright pixels to 0**, and back to 964 once the effect was
    dropped. ⚠ The measurement only worked on a grab of the WINDOW --
    `card.grab()` renders the widget directly, bypasses compositing, and
    reported a healthy card throughout.

    ⚠ Pinned structurally rather than by pixels because the open is
    ANIMATED: in a suite no wall-clock time passes, the animation never
    finishes, and a pixel assertion would be measuring a half-open row.
    """
    content = QLabel(u"the candidates live in here")
    accordion = gui_app.Accordion(content)

    assert accordion.graphicsEffect() is not None, \
        u"closed, it needs the effect -- that is what it fades with"

    accordion.set_open(True, animate=False)
    assert accordion.graphicsEffect() is None, (
        u"an open row still carries an opacity effect, so any hover repaint "
        u"inside it can be swallowed by the effect's cache")

    # ⭐ AND IT MUST COME BACK. A fix that permanently removed the effect
    # would pass the line above and lose the fade this widget exists for.
    accordion.set_open(False, animate=False)
    assert accordion.graphicsEffect() is not None, \
        u"it can never fade again"


def test_the_key_dialog_RENDERS_dark_not_merely_carries_a_stylesheet(qapp):
    u"""🚨 THIS SHIPPED, AND THE OLD CHECK WAS GREEN THE WHOLE TIME.

    Sonic, 2026-09-19, on the published 1.0.0: *"the API key window was white
    and ugly on this version."* It was not a frozen-build problem -- it
    reproduces from source and always did.

    ⛔ The sheet sets `color` on every `QWidget` and `background` on ONE
    object name, `#window`. A dialog is a top-level window of its own, so it
    took the light ink and Qt's default light grey: its heading was
    invisible, not merely off-palette.

    ⚠ AND THE CHECK THAT WAS SUPPOSED TO COVER IT asserted the dialog's
    `styleSheet()` was non-empty -- 16,440 characters of one. A stylesheet
    that is present and a stylesheet that WORKS are different claims, and
    only a rendered pixel can tell them apart.
    """
    dialog = gui_app.KeyDialog(None, replacing=False)
    dialog.resize(460, 240)
    image = dialog.grab().toImage()
    assert image.width() > 100 and image.height() > 100, u"nothing rendered"

    # ⚠ A corner, well away from any control, is the dialog's own ground.
    corner = image.pixelColor(6, 6)
    brightness = corner.red() + corner.green() + corner.blue()
    ceiling = sum(int(theme.SURFACE[i:i + 2], 16) for i in (1, 3, 5)) + 90
    assert brightness <= ceiling, (
        u"the dialog's ground renders at %s (sum %d) -- light ink on a light "
        u"ground is how its heading became unreadable"
        % (corner.name(), brightness))


def test_a_key_that_FAILS_to_save_is_not_reported_as_saved(qapp):
    window = make()
    window.state.key_hint = u"…old1"

    class Refused(object):
        returncode = 1

        def communicate(self, timeout=None):
            return (b"", b"hato: the key could not be written\n")

    window.spawn = lambda argv, **kw: Refused()

    assert window.set_key(u"a-brand-new-key-9999") is False
    # ⛔ and the card must still show the OLD hint. Showing the new key's last
    # four would tell the person a key is in place that is not.
    assert window.state.key_hint == u"…old1"


def test_the_window_WAITS_for_the_write_before_it_returns(qapp):
    window = make()
    order = []

    class Written(object):
        returncode = 0

        def communicate(self, timeout=None):
            order.append(u"waited")
            return (b"{}", b"")

    def spawn(argv, **kw):
        order.append(u"spawned")
        return Written()

    window.spawn = spawn

    assert window.set_key(u"key-1234") is True
    assert order == [u"spawned", u"waited"], order


def test_a_failed_save_NEVER_reaches_the_connection_test(qapp, monkeypatch):
    u"""⛔ THE WHOLE POINT. A test that runs after a failed write asks the
    keystore, and the keystore still holds the previous key."""
    window = make()
    tested = []

    class FakeDialog(object):
        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return gui_app.QDialog.DialogCode.Accepted

        def value(self):
            return u"a-new-key-0000"

    monkeypatch.setattr(gui_app, "KeyDialog", FakeDialog)
    monkeypatch.setattr(window, "set_key", lambda *a, **kw: False)
    monkeypatch.setattr(
        window, "verify_key",
        lambda *a, **kw: (tested.append(1), (True, u"Connected"))[1])

    assert window.choose_key() is False
    assert tested == [], "the connection test ran after the write failed"
    assert window.state.key_ok is False


# ---------------------------------------------------------------------------
# the way OUT -- feedback and the repository, on the tab line
# Sonic, 2026-09-18: *"can we add something like this on the right side on the
# settings line? That brings them to the github issues page as well as the
# github?"*
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 🚨 NO KEY IS A REFUSAL, AND IT SHIPPED AS SILENCE
#
# Sonic, 2026-09-19, on the published 1.0.0: *"I gave it a new folder to look
# at, and ran it, it doesn't do anything ... I THINK that behavior happened
# because i didn't have the API key in."*
#
# ⛔ THREE FAULTS STACKED. The CLI exited 1 -- the SAME code as "something
# needs a pick" -- with its explanation on a stderr the window does not read;
# and the window treats only exit 2 as "could not run", so the footer said
# **done** over an empty tab. Nothing anywhere said "no key".
#
# ⚠ AND THE SMOKE TEST DID NOT COVER IT. It asserts the CLI refuses with an
# instruction, which was always true. Nothing asserted what the WINDOW does
# with that refusal -- the seam between them, again.
# ---------------------------------------------------------------------------

def test_a_run_with_no_key_REFUSES_and_says_why(qapp, monkeypatch):
    window = make(running=False, folders=[u"D:\\Anime"])
    window.state.key_hint = None

    started = []
    monkeypatch.setattr(gui_run, u"Runner",
                        lambda **kw: started.append(kw) or _NullRunner())

    assert window.start_run() is None, u"it tried to run without a key"
    assert started == [], u"it started a run that could only fail"
    assert u"key" in gui_app.footer_status(window.state).lower(), \
        u"the footer says %r, which does not mention the key" \
        % gui_app.footer_status(window.state)


def test_with_a_key_a_run_still_starts(qapp, monkeypatch):
    u"""⛔ THE GUARD MUST NOT BE A WALL. A refusal that fired for everybody
    would pass the check above and break the product -- which is the shape of
    a fix that is worse than the bug."""
    window = make(running=False, folders=[u"D:\\Anime"])
    window.state.key_hint = u"…ab12"

    started = []
    monkeypatch.setattr(gui_run, u"Runner",
                        lambda **kw: started.append(kw) or _NullRunner())

    assert window.start_run() is not None
    assert started, u"a run with a key never started"


def test_folders_but_no_key_SHOWS_the_way_to_add_one(qapp):
    u"""*"There then needs to be another button to add the api key with
    instructions to get them there as well."*"""
    window = make(rows=[], folders=[u"D:\\Anime"])
    window.state.key_hint = None
    window.show_tab(gui_app.TAB_SUBS)

    joined = u" ".join(gui_app.texts(window))
    assert u"No jimaku key yet" in joined
    assert u"jimaku.cc/account" in joined, \
        u"it names the problem and not where to solve it"

    adders = [b for b in window.findChildren(QPushButton)
              if u"jimaku key" in b.text()]
    assert adders, u"no control to add one"
    assert adders[0].receivers(adders[0].clicked) > 0, u"the button is inert"


def test_a_missing_key_never_hides_results_already_on_screen(qapp):
    u"""⛔ Somebody who has run before keeps their rows. Replacing real
    results with a nag is worse than the nag is worth."""
    window = make(folders=[u"D:\\Anime"])          # the full fixture rows
    window.state.key_hint = None
    window.show_tab(gui_app.TAB_SUBS)
    assert u"No jimaku key yet" not in u" ".join(gui_app.texts(window))


def test_the_tab_line_offers_feedback_and_the_repository(qapp):
    window = make()
    links = [w for w in window.findChildren(gui_app.QLabel)
             if w.objectName() == u"tablink"]
    assert len(links) == 2, u"expected two links on the tab strip"

    joined = u" ".join(w.text() for w in links)
    assert u"Send feedback" in joined
    assert u"Star on GitHub" in joined
    # ⭐ Asserted against the CONSTANTS, never a second copy of the URL here.
    assert gui_app.ISSUES_URL in joined
    assert gui_app.REPO_URL in joined
    assert gui_app.ISSUES_URL.startswith(gui_app.REPO_URL)


def test_those_links_actually_OPEN(qapp):
    u"""⛔ A themed link that does nothing when clicked is the same defect as
    an inert button, and the button check cannot see it: these are QLabels,
    and that walk is over `QAbstractButton`."""
    links = [w for w in make().findChildren(gui_app.QLabel)
             if w.objectName() == u"tablink"]
    assert links
    for widget in links:
        assert widget.openExternalLinks(), \
            u"the link is styled, placed, and goes nowhere"
        assert widget.textFormat() == Qt.TextFormat.RichText, \
            u"without RichText the anchor renders as literal markup"


def test_a_link_takes_its_colour_from_the_PALETTE_not_the_sheet(qapp):
    u"""🚨 THE FOURTH CONTROL IN THIS WINDOW PAINTED BY SOMETHING OTHER THAN
    THE STYLESHEET -- after the Windows-blue radio, the circular checkbox and
    the separator that drew its own frame.

    ⛔ Qt renders `<a href>` from the palette. A `color:` rule in `theme.py`
    is ignored, and the toolkit's own blue and visited-PURPLE win -- which is
    exactly what Sonic reported on the surasura link (*"the purple used for
    github is too dark"*).
    """
    links = [w for w in make().findChildren(gui_app.QLabel)
             if w.objectName() == u"tablink"]
    assert links
    for widget in links:
        palette = widget.palette()
        for role in (QPalette.ColorRole.Link, QPalette.ColorRole.LinkVisited):
            assert palette.color(role).name().lower() == theme.LINK.lower(), \
                u"%s is not the theme's link colour" % role
    # ⛔ AND THE SHEET MUST NOT PRETEND TO OWN IT. A `color:` on #tablink would
    # read as the thing doing the work and would not be.
    sheet = theme.qss()
    assert u"#tablink" in sheet
    rule = sheet.split(u"#tablink", 1)[1].split(u"}", 1)[0]
    assert u"color" not in rule, \
        u"#tablink sets a colour the palette actually decides"


def test_no_link_in_the_window_is_UNDERLINED(qapp):
    u"""⛔ Sonic, 2026-09-18: *"remove the underlines."* Qt underlines every
    anchor by default and NO palette role turns it off -- it comes only from
    the anchor's own style, which is why `theme.LINK_CSS` exists."""
    assert u"text-decoration:none" in theme.LINK_CSS.replace(u" ", u"")
    window = make()
    anchors = [w for w in window.findChildren(QLabel) if u"<a href" in w.text()]
    assert anchors, u"no links found at all -- this check would pass vacuously"
    for widget in anchors:
        body = widget.text()
        assert u"text-decoration" in body.replace(u" ", u""), \
            u"an anchor with no decoration rule renders underlined: %s" % body


# ---------------------------------------------------------------------------
# ⭐ open the VIDEO from an expanded row
# Sonic, 2026-09-18: *"if you click somewhere on the newly synced subs it opens
# up the file ... Not the sub file but the video file ... simple as a simple
# option. Without messing with the ux."*
# ---------------------------------------------------------------------------

def test_an_expanded_row_offers_to_open_the_video(qapp, tmp_path, monkeypatch):
    u"""🚨 THIS CLICKS THE BUTTON, AND THE FIRST VERSION DID NOT.

    ⛔ It used to assert only that a button existed and had a receiver -- and
    a mutant that handed the SUBTITLE to the shell instead of the video
    SURVIVED it, because `output_path` is truthy too, so a button still
    appeared and the helper's own check never went through this panel at all.
    The seam between the row and the helper was the one thing untested.

    ⭐ So the two paths are given DIFFERENT values and the click is driven.
    """
    video = tmp_path / u"ep01.mkv"
    video.write_text(u"", encoding=u"utf-8")
    subtitle = tmp_path / u"ep01.ja.ass"
    subtitle.write_text(u"", encoding=u"utf-8")

    opened = []
    monkeypatch.setattr(gui_app, u"open_in_player",
                        lambda path: opened.append(path) or True)

    panel = gui_app.detail_panel({u"video": str(video),
                                  u"output_path": str(subtitle)})
    found = [b for b in panel.findChildren(QPushButton)
             if u"Open video" in b.text()]
    assert found, u"no way to open the video"
    assert found[0].receivers(found[0].clicked) > 0, u"the button is inert"

    found[0].click()
    assert opened, u"the button is connected to nothing that opens anything"
    assert opened[0] == str(video), \
        u"the row opened %r -- it must hand over the VIDEO" % opened[0]


def test_a_video_that_is_NOT_ON_DISK_offers_no_button(qapp, tmp_path):
    u"""🚨 THIS CHECK USED TO BE A LIE, AND SO WAS THE CODE IT GUARDED.

    It passed a hand-made row carrying `gone: True` and asserted no button --
    green, and meaningless. ⛔ `report.as_dict()` is the only thing that
    builds a real row and it has NO `gone` key, so in the product the guard
    never evaluated to anything and the button appeared on every row,
    including videos that had been moved or deleted.

    ⭐ The row now asks the DISK, and so does this: a path that is not there
    gets no button, and `gone` is not involved at all.
    """
    missing = tmp_path / u"x.mkv"                # deliberately never created
    panel = gui_app.detail_panel({u"video": str(missing)})
    assert not [b for b in panel.findChildren(QPushButton)
                if u"Open video" in b.text()]

    # ⛔ AND THE OLD FLAG MUST NOT RESURRECT THE BUTTON. A row carrying the
    # fictional key, for a file that IS there, still gets one -- proving the
    # decision comes from the filesystem and not from a key nothing sets.
    real = tmp_path / u"there.mkv"
    real.write_text(u"", encoding=u"utf-8")
    panel = gui_app.detail_panel({u"video": str(real), u"gone": True})
    assert [b for b in panel.findChildren(QPushButton)
            if u"Open video" in b.text()]


def test_opening_hands_the_VIDEO_to_the_shell_never_the_subtitle(qapp, tmp_path,
                                                                 monkeypatch):
    u"""🚨 THE WHOLE POINT OF THE FEATURE. *"Not the sub file but the video
    file."* Handing over `output_path` would open a text editor."""
    video = tmp_path / u"ep01.mkv"
    video.write_text(u"", encoding=u"utf-8")
    seen = []

    class FakeShell(object):
        @staticmethod
        def openUrl(url):
            seen.append(url.toLocalFile())
            return True

    monkeypatch.setattr(gui_app, u"QDesktopServices", FakeShell)
    assert gui_app.open_in_player(str(video)) is True
    assert seen and seen[0].endswith(u"ep01.mkv"), seen
    assert not seen[0].endswith(u".ass")


def test_a_file_that_moved_is_a_quiet_no(qapp, tmp_path):
    u"""⛔ Never raises. The person clicked a convenience, not a command, and a
    dialog saying *"the file you moved is moved"* is noise."""
    assert gui_app.open_in_player(None) is False
    assert gui_app.open_in_player(u"") is False
    assert gui_app.open_in_player(str(tmp_path / u"not-here.mkv")) is False


# ---------------------------------------------------------------------------
# ⭐ start with Windows
# ---------------------------------------------------------------------------

def test_settings_offers_a_start_with_windows_switch(qapp, monkeypatch):
    from hato import startup
    monkeypatch.setattr(startup, u"supported", lambda: True)
    monkeypatch.setattr(startup, u"is_enabled", lambda: False)
    monkeypatch.setattr(startup, u"is_stale", lambda: False)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert u"Start with Windows" in u" ".join(gui_app.texts(window))


def test_where_it_cannot_work_the_switch_is_ABSENT(qapp, monkeypatch):
    u"""⛔ *"Controls vanish when they would be meaningless."* There is no
    login-items registry outside Windows, and a switch that cannot do anything
    is worse than no switch."""
    from hato import startup
    monkeypatch.setattr(startup, u"supported", lambda: False)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert u"Start with Windows" not in u" ".join(gui_app.texts(window))


def _startup_box(window):
    u"""The Check beside *Start with Windows*, found by its own label.

    ⚠ Walks UP from the text to the first ancestor holding exactly one Check,
    so it cannot accidentally return the *Watch for new videos* box.
    """
    for lab in window.findChildren(QLabel):
        if lab.text() != u"Start with Windows":
            continue
        node = lab.parentWidget()
        while node is not None:
            boxes = node.findChildren(gui_app.Check)
            if len(boxes) == 1:
                return boxes[0]
            node = node.parentWidget()
    return None


def test_CLICKING_the_startup_switch_actually_toggles_it(qapp, monkeypatch):
    u"""🚨 NOTHING CLICKED THIS BOX. Disconnect `box.clicked` and all the other
    checks stayed green -- the identical defect this project already shipped
    once, in its own words: *"THIS BUTTON WAS INERT AND SHIPPED."*"""
    from hato import startup
    live = {u"on": False}
    monkeypatch.setattr(startup, u"supported", lambda: True)
    monkeypatch.setattr(startup, u"is_stale", lambda: False)
    monkeypatch.setattr(startup, u"is_enabled", lambda: live[u"on"])
    monkeypatch.setattr(startup, u"set_enabled",
                        lambda on: live.__setitem__(u"on", bool(on)))

    window = make()
    window.show_tab(gui_app.TAB_SET)
    box = _startup_box(window)
    assert box is not None, u"no switch to click"

    box.click()
    assert live[u"on"] is True, u"the switch is connected to nothing"

    window.show_tab(gui_app.TAB_SET)
    _startup_box(window).click()
    assert live[u"on"] is False, u"it turns on but never off"


def test_the_switch_is_DRAWN_the_way_windows_has_it(qapp, monkeypatch):
    u"""⛔ Nothing asserted the drawn state. `setChecked(not on)` survived every
    check -- a switch that is both inert and inverted passed."""
    from hato import startup
    monkeypatch.setattr(startup, u"supported", lambda: True)
    monkeypatch.setattr(startup, u"is_stale", lambda: False)

    monkeypatch.setattr(startup, u"is_enabled", lambda: True)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert _startup_box(window).isChecked() is True

    monkeypatch.setattr(startup, u"is_enabled", lambda: False)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert _startup_box(window).isChecked() is False


def test_a_registry_error_does_not_take_the_window_down(qapp, monkeypatch):
    u"""⚠ Neither the StartupError branch nor the note it writes was covered."""
    from hato import startup
    monkeypatch.setattr(startup, u"supported", lambda: True)
    monkeypatch.setattr(startup, u"is_stale", lambda: False)
    monkeypatch.setattr(startup, u"is_enabled", lambda: False)

    def refuse(_on):
        raise startup.StartupError(u"a policy says no")

    monkeypatch.setattr(startup, u"set_enabled", refuse)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    _startup_box(window).click()                 # must not raise
    assert u"a policy says no" in u" ".join(gui_app.texts(window))


def test_the_switch_reads_WINDOWS_not_a_file_hato_wrote(qapp, monkeypatch):
    u"""🚨 The registry is the only state. If this ever reads a config key
    instead, the switch can show ON while nothing runs."""
    from hato import startup
    asked = []
    monkeypatch.setattr(startup, u"supported", lambda: True)
    monkeypatch.setattr(startup, u"is_stale", lambda: False)
    monkeypatch.setattr(startup, u"is_enabled",
                        lambda: asked.append(1) or True)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert asked, u"the card never asked Windows what the state was"


def test_every_setting_the_window_writes_actually_EXISTS(qapp):
    u"""🚨 THIS CHECK FOUND A DEFECT NOBODY HAD REPORTED, WHILE BEING WRITTEN.

    Sonic reported the tray never appearing. The tick was sending
    `hato config --set watch=true`, `config.py`'s schema refused the key by
    name, and the window never reads a child's exit code -- so the box ticked,
    nothing saved, nothing said so.

    ⭐ Going to write this guard turned up `schedule` doing exactly the same
    thing: the *"every day at 03:00"* time field had never once saved, and
    nobody had noticed because the field keeps showing what you typed.

    ⛔ THE REAL HOLE IS THAT A REFUSED CHILD IS SILENT, and this does not fix
    that -- it makes the one consequence that has bitten twice impossible.
    Static, so it needs no clicking and cannot be fooled by which control
    happened to be exercised.
    """
    import re
    from hato import config as config_module

    source = open(gui_app.__file__, encoding="utf-8").read()
    keys = sorted(set(re.findall(r'--set"\s*,\s*u?"(\w+)=', source)))
    assert keys, (
        u"no `--set` call was found in app.py at all, so this check is "
        u"vacuous -- the pattern it greps for must have changed")
    unknown = [k for k in keys if k not in config_module.SCHEMA]
    assert not unknown, (
        u"the window writes settings config.py's schema refuses by name, so "
        u"they are silently never saved: %s. Known: %s"
        % (u", ".join(unknown), u", ".join(sorted(config_module.SCHEMA))))


def test_the_no_folders_state_offers_the_control_and_not_a_signpost(qapp):
    u"""⭐ SONIC'S RULING, 2026-09-18: the Subtitles tab with no folders shows
    the mark, *No folders selected*, and a button that adds one.

    ⚠ It replaced a line of prose pointing at Settings. A tool that cannot
    start should show the way to start it, not the address of the way.
    """
    window = make(folders=[])
    window.show_tab(gui_app.TAB_SUBS)

    texts = [w.text() for w in window.findChildren(gui_app.QLabel) if w.text()]
    assert any(u"No folders selected" in t for t in texts), texts

    buttons = [b for b in window.findChildren(gui_app.QPushButton)
               if u"Add folders" in b.text()]
    assert buttons, u"the no-folders state has no button to add one"
    assert buttons[0].receivers(buttons[0].clicked) > 0

    # ⛔ And the mark is really there -- an empty state whose picture failed to
    # load is a blank page with one line on it.
    marks = [w for w in window.findChildren(gui_app.QLabel)
             if w.pixmap() is not None and not w.pixmap().isNull()]
    assert marks, u"the no-folders state drew no mark"


def test_no_separator_is_painted_brighter_than_the_theme_allows(qapp):
    u"""🚨 REPORTED BY SONIC OFF A SHIPPED SCREENSHOT, 2026-09-18:
    *"the white border separating each on the needs you tab ... stands out too
    much. Yes it needs to be separated but this is too much."*

    He was exactly right and it was a defect, not a taste call. `hrule()` set
    `QFrame.Shape.HLine`, and **a QFrame with a shape paints its own 3D frame
    from the widget PALETTE, over whatever the stylesheet set** -- so every
    separator was TWO lines: Qt's, at `#e7e9ec` (`--ink`, the brightest token
    there is), stacked on the correct `--line`. Measured off the shipped PNG:
    a row 100% of the window's width at `--ink`.

    ⭐ This asserts the CLASS, not the instance. It does not look for
    `setFrameShape`; it looks at the PIXELS, so any control that paints a
    too-bright full-width rule -- a frame, a splitter handle, a group box, a
    default focus rect -- fails it, whether or not anybody thought of it.

    ⚠ Offscreen is fine HERE even though it has no fonts: a themed QFrame is a
    filled rectangle and renders identically either way. ⛔ It would NOT be
    fine for judging type or layout -- see the note at the top of this file.
    """
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    window.resize(1100, 660)
    image = window.grab().toImage()
    width, height = image.width(), image.height()
    assert width > 200 and height > 200, u"nothing was rendered to inspect"

    ceiling = sum(int(theme.LINE_HI[i:i + 2], 16) for i in (1, 3, 5))
    offenders = []
    for y in range(height):
        counts = {}
        for x in range(0, width, 3):
            rgb = image.pixelColor(x, y).getRgb()[:3]
            counts[rgb] = counts.get(rgb, 0) + 1
        rgb, n = max(counts.items(), key=lambda kv: kv[1])
        # a RULE is a row that is overwhelmingly ONE colour, edge to edge
        if n / float(len(range(0, width, 3))) >= 0.90 and sum(rgb) > ceiling:
            offenders.append((y, u"#%02x%02x%02x" % rgb))
    assert not offenders, (
        u"a full-width rule is painted brighter than --line-hi (%s), which is "
        u"the ceiling for a divider on this theme: %s. A QFrame with a "
        u"frameShape paints its own palette-coloured frame over the "
        u"stylesheet -- see hrule()."
        % (theme.LINE_HI, u", ".join(u"y=%d %s" % o for o in offenders[:6])))


# ===========================================================================
# 1 -- [!] the engine's vocabulary never reaches a person
# ===========================================================================

def test_the_alarming_word_is_nowhere_in_the_built_window(qapp):
    u"""[!] THE CHECK THE WHOLE TAB LAYOUT EXISTS TO PASS.

    `05-interface.md`: *"when it says 'refused' it's quite alarming."* The
    fixtures deliberately carry it in `reason` on two rows and on every
    attempt, because that is what the real engine writes -- so this walks what
    was BUILT, not what this file happens to contain.
    """
    window = make()
    # ⚠ EVERY ROW OPEN (RUNBOOK 13e): a closed row builds no panel now, and the
    # panel carries the engine's words this walk exists to keep out
    window.state.open_rows = set(window.state.key(r) for r in window.state.rows)
    for tab in gui_app.TABS:
        window.show_tab(tab)
        for pick in window.state.of(gui_run.NEEDS_YOU):
            window.state.open_pick = window.state.key(pick)
            window.render()
            for text in gui_app.texts(window):
                assert u"refus" not in text.lower(), \
                    u"the engine's word reached the interface: %r" % text


def test_safe_replaces_every_inflection_with_the_ruled_phrase():
    for before in (u"REFUSED", u"refused", u"the pair was refusing",
                   u"hato refuses this"):
        assert u"refus" not in gui_app.safe(before).lower()
    assert gui_app.safe(u"it was REFUSED") == u"the timing did not hold"


def test_safe_replaces_the_SENTENCE_so_the_result_is_readable():
    u"""[!] SUBSTITUTING THE WORD IN PLACE PRODUCED *"the pair was did not
    hold"* -- caught by reading a shot, not by the check, which was perfectly
    happy because the forbidden word was gone. A sanitiser that emits broken
    English has moved the problem, not solved it."""
    out = gui_app.safe(u"every candidate was refused; the timing did not hold")
    assert out == u"the timing did not hold"
    assert u"was did not" not in out


def test_safe_can_be_given_hatos_own_words_for_the_place_it_is_used():
    assert gui_app.safe(u"it was refused", u"see the log") == u"see the log"
    assert gui_app.safe(u"", u"see the log") == u""


def test_safe_leaves_ordinary_prose_alone():
    u"""[X] A sanitiser that rewrites everything is not a sanitiser."""
    text = u"[Erai-raws] Re Zero 3rd - 54.ass"
    assert gui_app.safe(text) == text


def test_a_row_only_ever_says_one_of_the_five_interface_words():
    u"""`run.interface_words()` is the whole permitted vocabulary."""
    words = gui_run.interface_words()
    assert gui_run.REFUSED not in words
    for row in full_rows():
        assert gui_app.State.word(row) in words


# ===========================================================================
# 2 -- [*] the badge and the footer are ONE number
# ===========================================================================

def _badge_text(window):
    return window.tab_buttons[gui_app.TAB_PICK].badge.text()


def _footer_need(window):
    return window.tally_labels[1].text()


def test_the_badge_and_the_footer_start_agreeing(qapp):
    window = make()
    assert _badge_text(window) == u"2"
    assert _footer_need(window) == u"2 need you"


def test_pairing_one_moves_the_badge_AND_the_footer(qapp):
    u"""[*] THE DEFECT THE MOCK RECORDED AGAINST ITSELF.

    The badge was hardcoded to 2, and so -- separately, in another element --
    was the footer. Pairing an episode left the tab claiming two needed a
    person while the list under it showed one. `State.tallies()` is one call
    and both read it, so a mutant that pins either goes red here.
    """
    window = make()
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    window.state.picked[window.state.key(row)] = u"whatever.ass"
    window.render()
    assert _badge_text(window) == u"1"
    assert _footer_need(window) == u"1 needs you"


def test_pairing_both_takes_the_badge_quiet_rather_than_to_a_garnet_nought(qapp):
    window = make()
    for row in window.state.of(gui_run.NEEDS_YOU):
        window.state.picked[window.state.key(row)] = u"x.ass"
    window.render()
    assert _badge_text(window) == u"0"
    assert _footer_need(window) == u"0 need you"
    badge = window.tab_buttons[gui_app.TAB_PICK].badge
    assert badge.property(u"zero") == u"true"


def test_the_badge_is_not_zero_flagged_while_something_waits(qapp):
    window = make()
    assert window.tab_buttons[gui_app.TAB_PICK].badge.property(u"zero") == u"false"


def test_the_counts_partition_over_every_row(qapp):
    u"""[!] `added + needs_you + errored + skipped == len(rows)`.

    A subset presented as a sibling is how eight files became eleven on the
    one line a person reads at a glance.
    """
    window = make()
    tallies = window.state.tallies()
    picked = len(window.state.picked)
    assert sum(tallies.values()) + picked == len(window.state.rows)


def test_the_added_tally_does_not_climb_on_a_pick(qapp):
    u"""[X] THE WINDOW DECIDES NOTHING. A pick is handed to the engine and the
    engine rules on it; claiming the file was added before it came back is the
    window deciding."""
    window = make()
    before = window.state.tallies()[gui_run.ADDED]
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    window.commit_pair(window.state.key(row), row[u"attempts"][0])
    assert window.state.tallies()[gui_run.ADDED] == before


# ===========================================================================
# 3 -- [!] a candidate click commits THAT pair
# ===========================================================================

def test_clicking_a_candidate_commits_exactly_that_pair(qapp):
    u"""[!] CLICKING IS THE ACTION -- and the argv is the whole claim.

    Asserted against `run.argv_for_pair`, so a second argv builder in `app.py`
    cannot quietly disagree with the one `run.py` owns. Nothing is spawned.
    """
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    key = window.state.key(row)
    attempt = row[u"attempts"][1]           # the SECOND one, not the best
    argv = window.commit_pair(key, attempt)
    expected = gui_run.argv_for_pair(row[u"video"],
                                     gui_app.candidate_path(attempt),
                                     force=gui_run.PICK_OVERRIDES_TIMING)
    assert argv == expected
    assert window.spawned == [expected]


def _pair_in(argv):
    u"""-> (video, subtitle) from a `hato sync` argv, wherever the flags sit."""
    at = argv.index(u"sync")
    return argv[at + 1], argv[at + 2]


def test_the_committed_pair_names_the_file_that_was_clicked(qapp):
    window = make()
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    attempt = row[u"attempts"][2]
    window.commit_pair(window.state.key(row), attempt)
    _video, subtitle = _pair_in(window.spawned[0])
    assert attempt[u"name"] in subtitle
    # ⚠ ABSOLUTISED ON BOTH SIDES. `run.argv_for_pair` calls `abspath` on
    # purpose -- a GUI's working directory is wherever the shortcut pointed --
    # so comparing against the raw fixture value only held on Windows, where
    # these fixture paths are already absolute. On a POSIX runner `abspath`
    # prefixes the checkout, and the two differed. CI found it on the first
    # run that reached Linux.
    assert subtitle == os.path.abspath(gui_app.candidate_path(attempt))


def test_a_relative_candidate_path_is_made_absolute_before_it_is_run(qapp):
    u"""[!] A GUI'S WORKING DIRECTORY IS WHEREVER THE SHORTCUT POINTED -- on
    Windows routinely `C:\\Windows\\System32` -- and hato reads any token
    starting with `-` as a flag, which an absolute path cannot do.
    `run.argv_for_pair` absolutises both paths for exactly that reason.

    [!] THIS CHECK EXISTS BECAUSE A MUTANT SURVIVED. A hand-rolled argv in the
    window that skipped `abspath` was byte-identical to `argv_for_pair` under
    the old fixtures, because every path in them was already absolute -- so
    the check agreed with a defect it was written to catch. A RELATIVE path is
    the only input that can tell the two apart.
    """
    row = needs_you(54)
    row[u"video"] = u"anime/rezero/ep54.mkv"
    row[u"attempts"][0][u"tsubasa"][u"subtitle"] = u"subs/ep54.ja.ass"
    window = make(rows=[row])
    argv = window.commit_pair(window.state.key(row), row[u"attempts"][0])
    assert argv == gui_run.argv_for_pair(u"anime/rezero/ep54.mkv",
                                         u"subs/ep54.ja.ass",
                                         force=gui_run.PICK_OVERRIDES_TIMING)
    video, subtitle = _pair_in(argv)
    assert os.path.isabs(subtitle), u"the subtitle path is still relative"
    assert os.path.isabs(video), u"the video path is still relative"


def test_a_candidate_with_no_file_on_disk_commits_nothing(qapp):
    u"""[X] Better no file than the wrong one -- Rule 1, from the other side."""
    window = make()
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    argv = window.commit_pair(window.state.key(row),
                              {u"name": u"ghost.ass", u"match_rate": 0.9})
    assert argv is None
    assert window.spawned == []
    assert window.state.picked == {}


def test_a_click_on_the_card_reaches_commit(qapp):
    u"""[!] A HANDLER THAT IS NEVER REACHED RENDERS PERFECTLY AND IS INERT.

    This drives Qt's real mouse path rather than calling the method, which is
    the only way to catch a card that was built but never connected.
    """
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    cards = [w for w in window.findChildren(gui_app.CandidateCard)]
    assert cards, u"no candidate cards were built"
    click(cards[0])
    assert len(window.spawned) == 1
    assert u"sync" in window.spawned[0]


def _land(window, row, attempt, word=gui_run.PAIRED):
    u"""The pick's child answered: a file landed. -> the key"""
    key = window.state.key(row)
    window.commit_pair(key, attempt)
    window.finish_pick(key, attempt[u"name"], (word, u"", u"D:\\x.ja.ass"))
    return key


def test_a_click_says_pairing_and_NOT_paired_until_a_file_lands(qapp):
    u"""\ud83d\udea8 D7, measured 2026-09-22. The row went green, *"paired"*, at the CLICK,
    and the child was never read -- it had died on a usage error for every pick
    ever made. \u26d4 A click is not a result."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    attempt = row[u"attempts"][0]
    window.commit_pair(window.state.key(row), attempt)
    assert window.state.picked == {}, u"the click itself was recorded as a pairing"
    heads = window.findChildren(gui_app.PickHead)
    assert not [h for h in heads if h.property(u"done") == u"true"]
    busy = u"using · " if gui_run.PICK_OVERRIDES_TIMING else u"checking · "
    assert busy in u" ".join(h.best.text() for h in heads), u"the row does not say a pick is in flight"
    assert _badge_text(window) == u"2", u"the badge moved before anything landed"


def test_the_row_collapses_to_green_naming_the_file_it_used(qapp):
    u"""[*] A COLLAPSED ROW STILL SAYS WHAT HAPPENED TO IT. That is what makes
    an accordion safe to collapse -- \u2b50 once `hato sync` has said a file landed."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    attempt = row[u"attempts"][0]
    _land(window, row, attempt)
    heads = window.findChildren(gui_app.PickHead)
    done = [h for h in heads if h.property(u"done") == u"true"]
    assert len(done) == 1
    assert done[0].best.text().startswith(u"paired \u00b7 ")
    assert attempt[u"name"] in done[0].best.text()


def test_a_forced_pick_says_it_was_the_persons_choice(qapp):
    u"""D6. Written over a timing refusal, the row says *used*, never *paired* --
    the timing never held, and the row must not say it did."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    _land(window, row, row[u"attempts"][0], word=gui_run.FORCED)
    heads = window.findChildren(gui_app.PickHead)
    assert not [h for h in heads if h.property(u"done") == u"true"], (
        u"a forced pick is painted as if the timing had held")
    forced = [h for h in heads if h.property(u"done") == u"forced"]
    assert forced and forced[0].best.text().startswith(gui_run.FORCED + u" \u00b7 ")


def test_a_pick_that_did_not_land_leaves_the_row_asking(qapp):
    u"""\u2b50 RUNBOOK 7d promised this check and it was never written: *"a refused
    pick leaves the row asking, not claiming."* The row stays, the badge stays,
    and hato's reason is under the cards."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    key = window.state.key(row)
    window.state.open_pick = key
    window.commit_pair(key, row[u"attempts"][0])
    window.finish_pick(key, row[u"attempts"][0][u"name"],
                       (gui_run.PICK_REFUSED, u"31% -- the timing does not hold", None))
    assert key not in window.state.picked and window.state.open_pick == key
    assert _badge_text(window) == u"2"
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert gui_run.PICK_REFUSED in joined, joined
    assert u"refus" not in joined.lower()


def test_the_next_unresolved_row_opens_as_this_one_closes(qapp):
    u"""Sonic: *"after selecting one, the next one opens as it closes."* \u2b50 As it
    closes -- which is when the pair has LANDED, not when it was clicked."""
    window = make()
    rows = window.state.of(gui_run.NEEDS_YOU)
    first, second = window.state.key(rows[0]), window.state.key(rows[1])
    window.state.open_pick = first
    window.render()
    window.commit_pair(first, rows[0][u"attempts"][0])
    assert window.state.open_pick == first, u"it moved on before the answer"
    window.finish_pick(first, rows[0][u"attempts"][0][u"name"],
                       (gui_run.PAIRED, u"", u"D:\\x.ja.ass"))
    assert window.state.open_pick == second


def test_the_last_pick_leaves_nothing_open(qapp):
    u"""\u26a0 Starts with a row OPEN: begun at None, "nothing open" is true before
    anything happens, and the check proved nothing (it did, for a while)."""
    window = make()
    rows = window.state.of(gui_run.NEEDS_YOU)
    window.state.open_pick = window.state.key(rows[0])
    for row in rows:
        _land(window, row, row[u"attempts"][0])
    assert window.state.open_pick is None


def test_only_one_pick_row_is_ever_open(qapp):
    u"""[*] The accordion's open row is a SINGLE VALUE, not a set.

    [!] AND CLICKING THE OPEN ROW AGAIN MUST CLOSE IT. Toggling two different
    rows cannot tell a toggle from a plain assignment -- both leave the second
    row open and only one panel expanded -- so a mutant that replaced the
    toggle with `open_pick = key` SURVIVED. The second half of this check is
    the half that fails.
    """
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    rows = window.state.of(gui_run.NEEDS_YOU)
    first, second = window.state.key(rows[0]), window.state.key(rows[1])
    window._toggle_pick(first)
    window._toggle_pick(second)
    assert window.state.open_pick == second
    assert len([a for a in window._accordions.values() if a.is_open()]) == 1
    window._toggle_pick(second)
    assert window.state.open_pick is None, \
        u"clicking the open row again did not close it"
    assert [a for a in window._accordions.values() if a.is_open()] == []


def test_blacklist_is_a_different_gesture_from_choosing(qapp):
    u"""[*] It must not be reachable by the same reflex as picking a file."""
    window = make()
    row = window.state.of(gui_run.NEEDS_YOU)[0]
    argv = window.blacklist(window.state.key(row))
    assert u"blacklist" in argv
    assert u"sync" not in argv
    assert window.state.picked == {}
    #: [!] AND IT IS THE REAL COMMAND SHAPE. `hato/commands/blacklist.py`
    #: takes the video POSITIONALLY; the first version of this invented an
    #: `add` verb and the window would have asked hato to blacklist a file
    #: literally named "add". Asserting only that the word appeared was what
    #: let that through.
    assert u"add" not in argv
    assert argv[argv.index(u"blacklist") + 1] == row[u"video"]


# ===========================================================================
# 4 -- [X] the accordion has no hard-coded ceiling
# ===========================================================================

def test_the_accordion_animates_to_the_contents_own_height(qapp):
    u"""[X] A CAP MEANS A SCROLLBAR, and with six candidates the case that
    most needs every option visible is the case that scrolls."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    key = window.state.key(window.state.of(gui_run.NEEDS_YOU)[0])
    accordion = window._accordions[key]
    accordion.set_open(True)
    assert accordion._anim.endValue() == accordion.target_height()
    assert accordion.target_height() == accordion.content.sizeHint().height()
    assert accordion.target_height() > 0


def test_a_taller_candidate_list_gets_a_taller_target(qapp):
    u"""The end value is READ, not guessed: three candidates must target more
    than one."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    rows = window.state.of(gui_run.NEEDS_YOU)
    three = window._accordions[window.state.key(rows[0])].target_height()
    one = window._accordions[window.state.key(rows[1])].target_height()
    assert three > one


def test_no_literal_maximum_height_anywhere_in_the_window(qapp):
    u"""[X] The mock's 420px ceiling was a guess and six candidates overflowed
    it. A number here would be the same guess in Python."""
    text = source("app.py")
    #: [X] Zero is not a ceiling, it is *closed*. Any POSITIVE literal is the
    #: 420px guess coming back in Python.
    literal = re.findall(r"setMaximumHeight\(\s*[1-9]\d*\s*\)", text)
    assert literal == [], u"a guessed ceiling is back: %r" % literal
    assert u"QWIDGETSIZE_MAX" in text
    assert u"sizeHint().height()" in text


def test_the_accordion_releases_its_ceiling_once_open(qapp):
    u"""Otherwise later growth -- *"try 3 more candidates"* -- is clipped."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    accordion = list(window._accordions.values())[0]
    accordion.set_open(True)
    accordion._settle()
    assert accordion.maximumHeight() > 10 ** 6


def test_a_closed_accordion_is_flat(qapp):
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    accordion = list(window._accordions.values())[0]
    accordion.set_open(False, animate=False)
    assert accordion.maximumHeight() == 0
    assert not accordion.is_open()


# ===========================================================================
# 5 -- every tab renders with zero rows
# ===========================================================================

@pytest.mark.parametrize("tab", list(gui_app.TABS))
def test_every_tab_renders_with_no_rows_at_all(qapp, tab):
    u"""[!] AN EMPTY LIBRARY IS A REAL STATE and must not look broken --
    and it is THREE states, not one: a settled library, an empty folder, or
    nothing pairable."""
    window = make(rows=[])
    window.show_tab(tab)
    assert window.body.currentWidget() is window.panes[tab]
    assert gui_app.texts(window), u"an empty tab rendered nothing at all"
    assert _badge_text(window) == u"0"


def test_the_window_really_accepts_the_folder_drop_its_copy_promises(qapp,
                                                                     tmp_path):
    u"""[!] THE EMPTY STATE PROMISES THIS IN WORDS. Copy describing a
    capability the build does not have is worse than either shipping it or not
    saying it.

    [!] And `setAcceptDrops` is load-bearing: without it Qt never delivers a
    drag, so the handlers would be present, correct and completely inert.

    ⚠ THIS CHECK WENT RED ON THE 2026-09-18 REDESIGN AND WAS RIGHT TO. The
    no-folders state was rebuilt around the mark and an *Add folders* button,
    and the rewrite dropped the only sentence that told anybody a folder could
    be dropped -- silently removing the discoverability of a feature that still
    worked. The line came back, quiet, under the button. ⛔ The assertion is on
    the word *drop* rather than the old sentence, so the copy can be reworded
    without the capability going quiet again.
    """
    window = make(rows=[], folders=[], running=False)
    assert window.acceptDrops(), u"the window refuses drags outright"
    joined = u" ".join(gui_app.texts(window))
    assert u"drop a folder" in joined

    folder = tmp_path / "Anime"
    folder.mkdir()
    added_now = window.add_folders([str(folder)])
    assert added_now == [os.path.abspath(str(folder))]
    assert os.path.abspath(str(folder)) in window.state.folders
    assert u"--add-folder" in window.spawned[0]
    assert u"config" in window.spawned[0]


def test_a_dropped_FILE_is_ignored_because_hato_watches_folders(qapp,
                                                                tmp_path):
    u"""[X] Guessing which folder a dropped video meant is the window
    deciding."""
    video = tmp_path / "ep01.mkv"
    video.write_bytes(b"not really a video")
    window = make(rows=[], folders=[], running=False)
    assert window.add_folders([str(video)]) == [] or \
        str(video) not in window.state.folders
    assert gui_app.HatoWindow._folders_in(None) == []


def test_adding_a_folder_that_is_already_watched_changes_nothing(qapp):
    window = make(running=False)
    before = list(window.state.folders)
    assert window.add_folders([before[0]]) == []
    assert window.state.folders == before
    assert window.spawned == []


def test_with_no_folders_the_empty_subtitles_tab_says_what_to_do(qapp):
    u"""*"Instruction, not refusal"* -- an unavailable state renders what
    would make it available.

    ⭐ REWRITTEN 2026-09-18 TO ASSERT MORE, NOT LESS. It used to pin the words
    *"No folders yet."* and a pointer to Settings; Sonic ruled the state should
    carry the mark, *No folders selected*, and **the control itself**. A
    signpost to the place where the button lives is worse than the button, so
    the check now requires the button and its wiring -- which the old text
    assertion could never have noticed was missing.
    """
    window = make(rows=[], folders=[])
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window))
    assert u"No folders selected" in joined
    adders = [b for b in window.findChildren(gui_app.QPushButton)
              if u"Add folders" in b.text()]
    assert adders, u"the state names the problem and offers no way out of it"
    assert adders[0].receivers(adders[0].clicked) > 0, u"the button is inert"


def test_with_folders_but_nothing_added_it_does_not_say_there_are_no_folders(qapp):
    window = make(rows=[])
    joined = u" ".join(gui_app.texts(window))
    assert u"Nothing added yet." in joined
    assert u"No folders yet." not in joined


def test_an_empty_needs_you_tab_says_so(qapp):
    window = make(rows=[added(1)])
    window.show_tab(gui_app.TAB_PICK)
    assert u"Nothing needs you." in u" ".join(gui_app.texts(window))


def test_settings_renders_with_no_folders_no_key_and_no_blacklist(qapp):
    window = make(rows=[], folders=[], skip_folders=[], blacklist=[],
                  key_hint=None)
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"FOLDERS" in joined
    assert u"JIMAKU KEY" in joined


# ===========================================================================
# 6 -- [X] no colour literal outside theme.py
# ===========================================================================

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})\b")
RGB = re.compile(r"\b(?:rgba?|QColor)\s*\(\s*\d")


@pytest.mark.parametrize("name", ["app.py", "branding.py", "__main__.py", "updating.py"])
def test_no_colour_literal_outside_theme(name):
    u"""[X] A literal is a SECOND PALETTE that drifts from the measured one.

    The whole point of `gui-mock/theme.css` is that the values were measured,
    not chosen; a hex typed into a widget file is outside that arithmetic and
    nothing will ever re-measure it.
    """
    text = source(name)
    assert HEX.findall(text) == [], \
        u"%s carries a colour literal: %r" % (name, HEX.findall(text))
    assert RGB.findall(text) == [], \
        u"%s builds a colour from numbers: %r" % (name, RGB.findall(text))


def test_every_colour_app_uses_comes_from_theme():
    u"""Every `theme.X` reference in `app.py` must be a real token."""
    text = source("app.py")
    used = set(re.findall(r"theme\.([A-Z_]+)", text))
    # ⚠ The non-colour tokens. `LINK_CSS` is a whole anchor STYLE rather than a
    # colour -- it carries `text-decoration:none`, which no palette role can
    # express, so it cannot live in `colors()`.
    known = set(theme.colors()) | {"FAST", "SLOW", "EASE", "LIFT", "GLOW",
                                   "MARK_PX", "ICON_SIZES", "LINK_CSS"}
    assert used <= known, u"app.py names a token theme.py does not have: %r" \
                          % sorted(used - known)


def test_the_measured_values_are_the_ones_in_the_palette():
    u"""[!] These came out of `color-kit`, not out of taste. A drift here is a
    contrast floor moving without anyone measuring it again."""
    assert theme.ACCENT == u"#f8a890"
    assert theme.REFUSED_FILL == u"#c02040"
    assert theme.REFUSED_TYPE == u"#f8f0e0"
    assert theme.REFUSED_INK == u"#ef4d6d"
    assert theme.OK == u"#7fc8a0"
    assert theme.BG == u"#15171b"


def test_the_deep_garnet_is_only_ever_a_fill(qapp):
    u"""[!] AS TEXT IT MEASURES 2.77 AGAINST A 4.5 FLOOR. Every appearance of
    `REFUSED_FILL` in the sheet must be a `background` or a `border`, never a
    `color:`."""
    for line in theme.qss().splitlines():
        if theme.REFUSED_FILL in line:
            assert not re.search(r"(?<!-)\bcolor\s*:\s*" + theme.REFUSED_FILL,
                                 line), \
                u"the garnet is being used as an ink: %r" % line


def test_the_garnet_appears_in_exactly_two_places(qapp):
    u"""[*] A 2px LEFT EDGE AND THE COUNT BADGE, and nowhere else. Separating
    the failures into their own tab is what removed the need for it to shout;
    a third appearance is the loudness creeping back."""
    sheet = theme.qss()
    blocks = [line for line in sheet.splitlines()
              if theme.REFUSED_FILL in line]
    assert len(blocks) == 2, u"the garnet spread: %r" % blocks


# ===========================================================================
# 7 -- each outcome word reaches the right tab
# ===========================================================================

def test_added_rows_are_on_the_subtitles_tab(qapp):
    window = make(rows=[added(1), added(2)])
    window.show_tab(gui_app.TAB_SUBS)
    rows = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)
    assert len(rows) == 2
    assert window.panes[gui_app.TAB_PICK].findChildren(gui_app.SubRow) == []


def test_a_wholly_skipped_show_is_one_quiet_line_not_a_row_each(qapp):
    u"""*"so that's visible but not the focus"* -- a line, not nineteen pills."""
    window = make(rows=[added(1), skipped(7), skipped(8)])
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    # ⚠ The wording moved 2026-09-19: "already subtitled" was painted under
    # EVERY skip, including ones with no subtitle anywhere. The structural
    # claim -- one line, not a row each -- is what this check is for.
    assert gui_run.SKIPPED in joined, joined
    assert len(window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)) == 1
    # ⭐ And the episodes are named, so two lines of one show differ
    assert u"eps 7, 8" in joined, joined


def test_episodes_skipped_inside_an_added_show_are_counted_under_it(qapp):
    u"""The nineteen that already had subtitles belong to the show they are
    part of, not to a list of their own."""
    title = u"葬送のフリーレン"
    window = make(rows=[added(1), skipped(7, title), skipped(8, title)])
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    # ⚠ Was "2 episodes already had subtitles" -- true of `present` and false
    # of the other four skips this line also counts. The COUNT is the claim.
    assert u"2 other episodes skipped" in joined, joined
    assert u"nothing was requested for them" in joined


def test_needs_you_rows_are_on_the_needs_you_tab_and_nowhere_else(qapp):
    u"""[*] FAILURES LIVE IN THEIR OWN TAB. Being there IS the signal.

    ⚠ EACH TAB IS SHOWN BEFORE IT IS READ. Panes are built lazily now --
    only the visible one is rebuilt on each render, because rebuilding all
    three eight times a second during a run tore the Settings tab apart in
    front of the person. The claim is unchanged; reaching it takes one more
    line.
    """
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    assert len(window.panes[gui_app.TAB_PICK].findChildren(gui_app.PickHead)) == 2
    window.show_tab(gui_app.TAB_SUBS)
    assert window.panes[gui_app.TAB_SUBS].findChildren(gui_app.PickHead) == []


def test_a_needs_you_row_names_the_VIDEO_FILE_not_just_the_show(qapp):
    u"""🚨 SHIPPED UNSORTABLE. Sonic, 2026-09-19, on the published 1.0.0:
    *"i cannot see the actual name of the file in the 'needs you' which makes
    it impossible to sort. it should show the actual video one."*

    ⛔ The row read `title or name`, and `title` is the SHOW -- so every
    episode of one series rendered an identical line and the only thing
    telling two rows apart was the number in the left column.
    """
    title = u"Tsuihou sareta Tensei Juukishi"
    window = make(rows=[needs_you(11, title), needs_you(12, title)])
    window.show_tab(gui_app.TAB_PICK)

    heads = window.panes[gui_app.TAB_PICK].findChildren(gui_app.PickHead)
    assert len(heads) == 2
    shown = [w.full() if hasattr(w, u"full") else w.text()
             for head in heads
             for w in head.findChildren(gui_app.Elide)
             if w.objectName() == u"who"]
    assert len(shown) == 2, shown
    # ⭐ The two rows must not say the same thing.
    assert shown[0] != shown[1], \
        u"both rows read %r -- indistinguishable" % shown[0]
    for text in shown:
        assert u".mkv" in text, u"the row does not name a file: %r" % text


def test_a_skipped_show_says_WHICH_skip_and_names_the_EPISODE(qapp):
    u"""🚨 SHIPPED AS A REASSURING LIE. Sonic, 2026-09-19, on 1.0.1:
    *"Katanai and tsuihou don't have it even though it says its already subbed
    in the GUI"* and *"for the 'already subbed' i need the ep # in those titles
    as well."*

    Neither had a subtitle file. Katainaka is an Erai-raws [MultiSub] whose
    Japanese track is INSIDE the container; Tsuihou downloaded 3 of 10
    candidates, kept none, and is retrying tomorrow. ⛔ Both rendered as the
    single line *"— already subtitled"*, under a tooltip asserting *"every
    episode already carries a Japanese track"*.

    ⚠ The engine sent `skip` correctly the whole time and the CLI printed
    *"1 already present · 1 waiting to retry · 1 already embedded"*. Only the
    window collapsed them."""
    window = make(rows=[embedded(11), retrying(12)])
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))

    # ⭐ THE EPISODE NUMBER, which is what made two rows of one show the same
    assert u"ep 11" in joined, joined
    assert u"ep 12" in joined, joined

    # ⛔ AND THE CLAIM THAT WAS FALSE FOR BOTH OF THEM
    assert u"already subtitled" not in joined, joined

    # ⭐ Two different facts must not read as one word
    assert gui_run.RETRYING in joined, joined
    assert gui_run.INSIDE_VIDEO in joined, joined

    # ⛔ No tooltip may tell a person a retrying video already has a track
    pane = window.panes[gui_app.TAB_SUBS]
    tips = [w.toolTip() for w in pane.findChildren(QWidget) if w.toolTip()]
    for tip in tips:
        if u"carries a Japanese track" in tip:
            raise AssertionError(u"the old blanket tooltip is still painted: %r" % tip)


def test_the_footer_counts_EVERY_skip_not_only_the_ones_with_a_file(qapp):
    u"""⚠ Splitting one skip word into five turned the footer tally from *all
    the skips* into *only the ones that had a file*, without changing a
    character at the read site. `counts()` pre-seeds every key, so there would
    never have been a KeyError to notice -- only a silent undercount.

    ⭐ AMENDED AT RUNBOOK 8e: a RETRYING skip is no longer a skip here. It is
    waiting on something -- a pick, or jimaku -- and it is counted on Needs you,
    once; counted here as well it would be one video in two of the footer's
    three numbers. Every SETTLED kind of skip still counts, and all four are here.
    """
    blocked = skipped(14, skip=u"blacklisted", outcome=u"SKIPPED",
                      reason=u"blacklisted by you")
    raw = skipped(13, skip=u"no-track", outcome=u"SKIPPED",
                  reason=u"no subtitle track in the video")
    window = make(rows=[skipped(7), embedded(11), raw, blocked, retrying(12)])
    window.show_tab(gui_app.TAB_SUBS)
    tally = window.tally_labels[2].text()
    assert tally == u"4 skipped", tally
    assert u"had them" not in tally, u"a retrying row has nothing: %r" % tally


def test_a_run_NOTE_reaches_the_WINDOW_and_not_only_the_terminal(qapp):
    u"""🚨 Sonic, 2026-09-22, on a file inside a blacklisted folder: *"it
    noticed it but didn't seem to do anything with it ... But nothing in the UI
    ever popped up about it."*

    ⛔ The pipeline writes *"N video(s) were not looked at because they are
    inside a skipped folder"* into `report.notes` for exactly this reason --
    its own comment says a skip rule that is too broad would otherwise be
    invisible for as long as nobody went looking. `hato/gui/` had NO reference
    to `notes` anywhere, so the note reached the CLI and stopped there.

    ⚠ The whole risk of `skip_folders` is that it is too broad, and the only
    reader who could act on that was the one who never saw it."""
    note = (u"2 video(s) were not looked at because they are inside a "
            u"skipped folder (D:\\Anime\\Raw).")
    state = gui_app.build_state_from([added(1)], summary(notes=[note]),
                                     **dict(SETTINGS))
    window = gui_app.HatoWindow(state)
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    assert u"skipped folder" in joined, joined
    assert u"D:\\Anime\\Raw" in joined, joined


def test_a_run_note_in_the_engines_words_is_said_in_hatos(qapp):
    u"""ADVERSARY 2026-09-22 (suspected on the window surface, fixed with it): a
    run's notes are ENGINE prose -- one can carry an exception's words or the
    engine's word for a timing refusal -- and they reached the Subtitles tab
    raw, past the one gate every other engine-written field goes through."""
    note = u"2 video(s): every candidate was refused by the timing check"
    state = gui_app.build_state_from([added(1)], summary(notes=[note]),
                                     **dict(SETTINGS))
    window = gui_app.HatoWindow(state)
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    assert u"refus" not in joined.lower(), joined
    assert gui_app._HUMAN_SENTENCE in joined, (
        u"the control: the note went missing rather than being said -- %s" % joined)


def test_a_long_run_note_WRAPS_rather_than_running_off_the_window(qapp):
    u"""🚨 LOOKED, 2026-09-23, over a copy of Sonic's store: *"24 video(s) were not
    looked at because they are inside a skipped folder (C:\\...)"* ran off the
    right edge with no ellipsis, and the folder list -- what the note exists to
    say -- was cut mid-path. Qt does not wrap a label unless told to."""
    folders = u", ".join(u"D:\\Downloads\\a long folder name %d" % i for i in range(6))
    note = (u"24 video(s) were not looked at because they are inside a skipped "
            u"folder (%s)" % folders)
    state = gui_app.build_state_from([added(1)], summary(notes=[note]),
                                     **dict(SETTINGS))
    window = gui_app.HatoWindow(state)
    window.show_tab(gui_app.TAB_SUBS)
    lay_out(window)
    pane = window.panes[gui_app.TAB_SUBS]
    said = [l for l in pane.findChildren(QLabel) if u"skipped folder" in l.text()]
    assert said, u"the note is not on the tab at all"
    right = said[0].mapTo(pane.viewport(), said[0].rect().topRight()).x()
    assert said[0].wordWrap(), u"a note longer than the window is not told to wrap"
    assert right <= pane.viewport().width(), (
        u"the note runs %dpx past the window's edge" % (right - pane.viewport().width()))


def test_EVERY_quiet_line_that_carries_prose_it_did_not_write_wraps(qapp):
    u"""⭐ THE CLASS, NOT THE INSTANCE (the note above was LOOKED, 2026-09-23): a
    config error is two sentences and a path, four found-on-a-retry names outgrow
    the window, and jimaku's words about a key are jimaku's to choose. Each is
    told to wrap -- an unwrapped QLabel does not overflow, it cuts silently."""
    long_error = (u"C:\\Users\\Someone\\AppData\\Local\\hato\\config.toml: schedule = "
                  u"'3:00' must be a 24-hour time such as '03:00'. A value whatever "
                  u"registers the run cannot read would be accepted here and refused "
                  u"somewhere nobody is looking.")
    window = make(config_error=long_error, key_status=u"x" * 400, key_ok=False)
    window.show_tab(gui_app.TAB_PICK)             # ⚠ where "not up to date" is said
    lay_out(window)
    stale = [l for l in window.panes[gui_app.TAB_PICK].findChildren(QLabel)
             if u"could not read what it remembers" in l.text()]
    assert stale and stale[0].wordWrap(), u"the config error is cut, not wrapped"
    window.show_tab(gui_app.TAB_SET)
    said = [l for l in window.panes[gui_app.TAB_SET].findChildren(QLabel)
            if l.objectName() == u"keybad"]
    assert said and said[0].wordWrap(), u"jimaku's words about the key are cut, not wrapped"
    found = [dict(added(n), tried_before=remembered()[u"tried_before"]) for n in (1, 2, 3, 4, 5)]
    retried = make(rows=found, running=False)
    retried.show_tab(gui_app.TAB_SUBS)
    line = [l for l in retried.panes[gui_app.TAB_SUBS].findChildren(QLabel)
            if u"tried other files first" in l.text()]
    assert line and line[0].wordWrap(), u"four found-on-a-retry names are cut, not wrapped"


def test_not_yet_rows_are_a_quiet_line_on_the_needs_you_tab(qapp):
    u"""[*] A NOT_FOUND ROW IS NOT SOMETHING A PERSON CAN PAIR -- there is
    nothing there yet, only a retry date. So it is a line, not a row with
    candidates."""
    window = make(rows=[not_yet(24)])
    window.show_tab(gui_app.TAB_PICK)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert u"not on jimaku yet" in joined
    assert window.panes[gui_app.TAB_PICK].findChildren(gui_app.PickHead) == []


def test_a_broken_row_is_on_the_needs_you_tab_not_among_the_successes(qapp):
    window = make(rows=[added(1), broke(1)])
    window.show_tab(gui_app.TAB_PICK)
    assert u"1 had a problem" in u" ".join(
        gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert len(window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)) == 1


def test_a_confident_row_with_no_written_file_is_not_called_added(qapp):
    u"""[!] A DRY RUN LEAVES `outcome == CONFIDENT` WITH NO `output_path`, and
    the outcome field cannot see the difference. tsubasa's GUI reported
    *"1 synced"* for both until an adversarial pass caught it."""
    dry = added(1)
    dry[u"output_path"] = None
    window = make(rows=[dry])
    assert window.state.tallies()[gui_run.ADDED] == 0
    assert window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow) == []


# ===========================================================================
# the row carries THREE things
# ===========================================================================

def test_a_subtitles_row_carries_exactly_episode_percent_and_the_filename(qapp):
    u"""[*] *"only show the %, the ones that were paired."* Six columns of
    evidence read as noise even when every column was true."""
    window = make(rows=[added(1, rate=0.82)])
    row = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)[0]
    assert row.ep.text() == u"01"
    assert row.pc.text() == u"82%"
    assert row.nm.text().startswith(u"[NanakoRaws]")
    labels = [w for w in row.findChildren(QLabel)]
    visible = [w.text() for w in labels if w.text() and w is not row.chev]
    assert len(visible) == 3, u"the row grew a fourth thing: %r" % visible


def test_the_evidence_is_behind_the_row_not_gone(qapp):
    u"""[*] THE INFORMATION WAS NOT CUT, IT WAS MOVED."""
    window = make(rows=[added(1)])
    key = window.state.key(window.state.rows[0])
    window._toggle_row(key)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    assert u"shifted" in joined and u"verdict" in joined and u"written" in joined
    assert u"locked" in joined


def test_a_row_starts_closed_and_its_detail_is_built_only_when_open(qapp, monkeypatch):
    u"""⭐ RUNBOOK 13e: the evidence behind a row is BUILT only while the row is open.
    Built for every row and hidden, it was ~21 widgets and a `stat` of the video per
    row at every render -- 1,624 widgets and 64 stats at 64 subtitled rows."""
    rows = [added(1), added(2)]
    videos = set(r[u"video"] for r in rows)
    asked = []
    real = gui_app.os.path.isfile
    monkeypatch.setattr(gui_app.os.path, "isfile",
                        lambda path: asked.append(path) or real(path))
    window = make(rows=rows)
    key = window.state.key(window.state.rows[0])
    assert key not in window._details, u"a closed row built its panel"
    assert not [p for p in asked if p in videos], u"a closed row asked the disk: %s" % asked
    window._toggle_row(key)
    assert window._details[key].isVisibleTo(window)
    # ⭐ The Layer 13 pass (Z13-6) -- AND UNDER ITS ROW. A panel built and never
    # placed, or placed at the end of the pane, is "visible to the window" too: both
    # survived every check, and only a picture saw them (Z-E1/Z-E2)
    column = window.pane_layouts[gui_app.TAB_SUBS]
    widget = [w for w in window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)
              if window.state.key(w.row) == key][0]
    assert column.indexOf(window._details[key]) == column.indexOf(widget) + 1, (
        u"the panel is not under its row", column.indexOf(window._details[key]),
        column.indexOf(widget))
    assert list(window._details) == [key], u"opening one row built the others' panels"
    assert [p for p in asked if p in videos] == [rows[0][u"video"]], asked


def test_the_chevron_is_invisible_until_the_pointer_arrives(qapp):
    u"""Eight static markers down a calm list is eight things to look at for
    no information."""
    window = make(rows=[added(1), added(2)])
    rows = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)
    assert rows[0]._chev_fade.opacity() == 0.0
    rows[0].set_expanded(True)
    assert rows[0]._chev_fade.opacity() == 1.0


def test_the_hue_comes_from_the_verdict_word_not_the_percentage(qapp):
    u"""[!] READING THE RULED DESIGN AS A THRESHOLD WAS WRONG. In
    `gui-mock/shots-final`, 91% is AMBER and 79% is GREEN -- no percentage
    rule produces that. It is tsubasa's own confidence ladder, shown:
    `locked` is green and every weaker word is *worth a look*."""
    assert gui_app.tier(added(1, rate=0.79)) == u"ok"              # locked
    strong = added(1, rate=0.91)
    strong[u"tsubasa"][u"verdict_word"] = u"strong"
    assert gui_app.tier(strong) == u"look"
    fair = added(1, rate=0.63)
    fair[u"tsubasa"][u"verdict_word"] = u"fair"
    assert gui_app.tier(fair) == u"look"
    untimed = added(1)
    untimed[u"tsubasa"] = None
    assert gui_app.tier(untimed) == u"none"


def test_a_high_percentage_with_a_weak_verdict_is_still_amber(qapp):
    u"""The exact pair the mock shows: 91%, `strong`, amber."""
    row = added(4, rate=0.91)
    row[u"tsubasa"][u"verdict_word"] = u"strong"
    window = make(rows=[row])
    cell = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)[0].pc
    assert cell.text() == u"91%"
    assert cell.property(u"tier") == u"look"


def test_the_engines_strongest_word_is_the_one_this_file_names():
    u"""[X] A second copy of a vocabulary drifts. `locked` is tsubasa's, and
    if it were ever renamed every row would silently turn amber."""
    import tsubasa.verdict as verdict
    assert gui_app.LOCKED in verdict.CONFIDENCE_WORDS
    assert gui_app.LOCKED == u"locked"


def test_episode_numbers_are_padded_the_way_the_design_shows_them():
    u"""A column of `1 2 4` reads as quantities; `01 02 04` reads as episodes.
    [X] And padding is not truncation -- One Piece is at 1121."""
    assert gui_app.episode_text(1) == u"01"
    assert gui_app.episode_text(54) == u"54"
    assert gui_app.episode_text(1121) == u"1121"
    assert gui_app.episode_text(None) == u""


def test_a_row_that_was_never_timed_shows_a_dash_not_a_zero(qapp):
    u"""[X] `0` IS A REAL ANSWER -- it means *it matched nothing* -- so the
    absent case must not become zero."""
    row = added(1)
    row[u"tsubasa"] = None
    window = make(rows=[row])
    assert window.panes[gui_app.TAB_SUBS].findChildren(
        gui_app.SubRow)[0].pc.text() == u"\u2014"
    assert gui_app.rate_text(0.0) == u"0%"
    assert gui_app.rate_text(None) == u"\u2014"


# ===========================================================================
# [!] every interactive control is themed -- a shape is a claim
# ===========================================================================

@pytest.mark.parametrize("selector", [
    "QCheckBox::indicator", "QRadioButton::indicator", "QComboBox",
    "QLineEdit", "QScrollBar:vertical", "QScrollBar:horizontal",
    "QPushButton", "QToolTip"])
def test_every_native_control_is_styled_explicitly(selector):
    u"""[!] A NATIVE CONTROL IS THEMED BY ITS HOST, NOT BY YOU.

    An unstyled radio paints Windows blue -- the one hue this palette does not
    contain -- inside a panel about *"colours utilised with high integrity"*.
    Caught in the mock by LOOKING at a shot, not by any assertion.

    [!] AND IT ASSERTS A RULE HEAD, NOT A SUBSTRING. `"QComboBox" in qss()` is
    still true after the `QComboBox { ... }` block is deleted, because
    `QComboBox:hover` mentions it -- a check that cannot fail is not a check.
    """
    assert re.search(r"(?m)^" + re.escape(selector) + r"\s*\{", theme.qss()), \
        u"%s has no rule of its own" % selector


@pytest.mark.parametrize("selector", ["QPushButton:focus", "QLineEdit:focus",
                                      "QComboBox:focus"])
def test_focus_is_visible_and_is_the_accent(selector):
    u"""[X] A control that can take focus and does not show it is a control
    nobody can drive from the keyboard."""
    found = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}",
                      theme.qss())
    assert found, u"%s has no rule of its own" % selector
    assert theme.ACCENT in found.group(1)


def test_the_info_marker_is_a_circle_not_a_rounded_square(qapp):
    u"""[!] QT CLAMPS A RADIUS THAT EXCEEDS HALF THE BOX. The dot is 15px and
    the radius said 8, so it drew a rounded SQUARE -- a shape that reads as a
    button rather than as the quiet marker the design uses."""
    found = re.search(r"(?m)^#info\s*\{([^}]*)\}", theme.qss())
    assert found
    radius = re.search(r"border-radius:\s*(\d+)px", found.group(1))
    assert radius, u"#info has no radius at all"
    dot = gui_app.info_dot(u"anything")
    assert dot.width() == dot.height()
    assert int(radius.group(1)) * 2 <= dot.width(), \
        u"a radius Qt will clamp: %spx on a %dpx box" % (radius.group(1),
                                                         dot.width())
    assert int(radius.group(1)) * 2 >= dot.width() - 1, \
        u"a radius too small to be a circle"


def test_the_font_stack_names_a_japanese_face_that_windows_actually_has():
    u"""[!] MEASURED on this machine 2026-09-18: `Segoe UI Variable Text` is
    ABSENT (Windows 10 LTSC 2019) and so is `Meiryo`. Every show title in this
    corpus is Japanese, so a stack naming only fonts that are not installed is
    how the headings become tofu."""
    #: Scoped to the DECLARATION -- a comment mentioning the font is not the
    #: font being requested, and the first version of this check matched one.
    stack = re.search(r"font-family:([^;]*);", theme.qss())
    assert stack, u"no font-family declaration at all"
    stack = stack.group(1)
    assert u"Yu Gothic UI" in stack, \
        u"no installed Japanese face is named in the font stack: %r" % stack
    assert stack.index(u"Segoe UI\"") < stack.index(u"Yu Gothic UI")


def test_the_checkbox_is_square_and_the_radio_is_round():
    u"""[!] A CHECKBOX IS NOT A RADIO. The mock's radio rule caught its one
    checkbox and rendered it as a circle -- a shape that says *pick one of
    these* about a thing that is simply on or off."""
    sheet = theme.qss()
    check = sheet[sheet.index(u"QCheckBox::indicator {"):]
    check = check[:check.index(u"}")]
    radio = sheet[sheet.index(u"QRadioButton::indicator {"):]
    radio = radio[:radio.index(u"}")]
    assert u"border-radius: 4px" in check
    assert u"border-radius: 8px" in radio


def test_the_card_rule_belongs_to_the_card_and_not_to_its_four_words(qapp):
    u"""[!] THE LABEL AND ITS CONTAINER SHARED ONE OBJECT NAME, so one
    `border-bottom` rule drew a long line across the card AND a short one
    under the heading text. Two widgets, one id, two lines.

    The first witness for this was the colour-literal grep, which of course
    said nothing about it -- the mutant SURVIVED and this check replaced it.
    """
    sheet = theme.qss()
    head = re.search(r"(?m)^#cardhead\s*\{([^}]*)\}", sheet)
    title = re.search(r"(?m)^#cardtitle\s*\{([^}]*)\}", sheet)
    assert head and title, u"the card heading lost one of its two rules"
    assert u"border-bottom" in head.group(1), \
        u"the card lost the rule under its heading"
    assert u"border" not in title.group(1).replace(u"border: 0", u""), \
        u"the heading words carry a border of their own: %r" % title.group(1)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    names = set(w.objectName() for w in window.findChildren(QLabel))
    assert u"cardtitle" in names
    #: [X] And the container must not be a QLabel wearing the same id.
    assert not [w for w in window.findChildren(QLabel)
                if w.objectName() == u"cardhead"]


def test_the_switch_and_the_checkbox_are_different_widgets(qapp):
    u"""A switch is on/off over time; a checkbox is on/off now. Same answer,
    different gesture -- and neither may borrow the other's shape."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert window.findChildren(gui_app.Switch)
    assert window.findChildren(gui_app.Check)
    assert not issubclass(gui_app.Check, gui_app.Switch)


def test_the_stylesheet_substitutes_every_token():
    u"""[!] A `%(NAME)s` left in the sheet is a rule Qt silently discards."""
    sheet = theme.qss()
    assert u"%(" not in sheet
    assert theme.ACCENT in sheet and theme.INK in sheet


def test_a_styled_container_paints_its_own_background(qapp):
    u"""[!] A plain `QWidget` IGNORES its stylesheet background. Without the
    `PE_Widget` paintEvent every container rule is inert, and the symptom is
    identical to a sheet that never loaded."""
    assert "PE_Widget" in source("app.py")
    window = make()
    for name in (u"titlebar", u"footer", u"tabstrip"):
        assert window.findChild(gui_app.Styled, name) is not None \
            or window.findChildren(gui_app.Styled), name


# ===========================================================================
# branding -- [X] never raises
# ===========================================================================

def test_every_icon_size_the_window_claims_is_really_on_disk():
    u"""[X] Only the sizes the window uses; the 1024 master stays out."""
    assert branding.available_sizes() == theme.ICON_SIZES
    for size in theme.ICON_SIZES:
        assert os.path.isfile(branding.icon_path(size))


def test_the_masters_are_not_in_the_package():
    folder = branding.data_dir()
    assert not os.path.isfile(os.path.join(folder, "hato-1024.png"))
    assert not os.path.isfile(os.path.join(folder, "hato-512.png"))


def test_the_path_resolves_off_the_package_not_the_repository(monkeypatch,
                                                              tmp_path):
    u"""[!] Three hosts disagree about where the package sits, and resolving
    through the repository shipped a broken release on tsubasa once.

    [!] AND THE CHECK HAS TO MOVE THE WORKING DIRECTORY. Asserting the answer
    from the repo root passes for `os.getcwd()` too, because in a test run the
    repo root IS the working directory -- so the check agreed with the defect.
    A mutant that swapped the package for the cwd SURVIVED until this chdir
    was added. The point of the rule is that the answer does not depend on
    where somebody clicked, so the check has to click somewhere else.
    """
    import hato
    expected = os.path.join(os.path.dirname(os.path.abspath(hato.__file__)),
                            "data")
    assert branding.data_dir() == expected
    monkeypatch.chdir(str(tmp_path))
    assert branding.data_dir() == expected, \
        u"data_dir moved when the working directory did"
    assert os.path.isfile(branding.icon_path(64))


def test_branding_never_raises_when_the_folder_is_gone(qapp, monkeypatch):
    u"""[X] A MISSING ICON IS A PLAINER WINDOW, not a reason the app will not
    open.

    [!] `qapp` IS LOAD-BEARING HERE AND WAS MISSING. Building a `QPixmap` with
    no `QGuiApplication` alive kills the interpreter on Windows -- exit
    0xC0000409, not an exception. It passed for weeks because some earlier
    test in the file had always made the application first; the mutation
    harness runs ONE node id alone and found it in the first pass.
    """
    monkeypatch.setattr(branding, "data_dir", lambda: "Z:\\nowhere")
    assert branding.icon_path(64) is None
    assert branding.ico_path() is None
    assert branding.available_sizes() == ()
    assert branding.best_size(40) is None
    assert branding.mark_pixmap(40).isNull()
    assert branding.app_icon() is not None


def test_the_tray_icon_file_is_on_disk_and_carries_every_real_export():
    u"""RUNBOOK 7f. The tray takes an `HICON`, and `LoadImageW` reads a `.ico`
    in one call -- so one file has to carry every size the shell may ask for.

    🚨 THE FIRST ONE HAD A SINGLE ENTRY AND NOTHING SAID SO. Pillow emits no
    entry larger than the image it is saving, so building it from the 16px
    export produced a valid, plausible, **one-entry** `.ico` -- no error, no
    warning, six sizes missing. ⛔ The entry list alone would not have caught
    the other half either: it cannot tell a real export from a downscale, and
    this pack has no vector source, so a resampled 16 is mush where a drawn one
    is legible. The pixels are what settle it.

    ⚠ READ WITH `struct`, NOT WITH PILLOW. Pillow is BUILD tooling here -- it
    is in no extra and no CI job installs it -- and `doctrine/release` is blunt
    that *"a permanently-red check is one people learn to scroll past"*. The
    ICO directory is a 6-byte header and a 16-byte entry each, so the count and
    the declared sizes need no decoder at all.

    ⚠ The pixel-identity half (that each entry IS the real export rather than a
    downscale) was verified once, by hand, at build time and is recorded in
    `branding.ico_path()`. ⛔ It is not asserted here, because asserting it
    needs a decoder this suite must not depend on.
    """
    import struct

    path = branding.ico_path()
    assert path, u"hato/data/hato.ico is missing -- the tray has no icon"
    with open(path, "rb") as handle:
        blob = handle.read()
    reserved, kind, count = struct.unpack_from("<HHH", blob, 0)
    assert (reserved, kind) == (0, 1), u"%s is not an .ico" % path
    sizes = []
    for index in range(count):
        width, height = struct.unpack_from("<BB", blob, 6 + index * 16)
        sizes.append((width or 256, height or 256))   # 0 means 256 in an ICO
    assert sorted(sizes) == [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)], (
        u"hato.ico carries %d entr(ies) %s. Built from the SMALLEST export it "
        u"silently gets one, because no writer emits an entry larger than the "
        u"image it was given -- base it on the largest and check the output."
        % (count, sorted(sizes)))


def test_a_mark_is_never_upscaled_from_a_smaller_export():
    u"""Asked for 100 device pixels it answers 128, not 64."""
    assert branding.best_size(40) == 48
    assert branding.best_size(100) == 128
    assert branding.best_size(16) == 16
    assert branding.best_size(5000) == 256


def test_the_window_really_gets_a_mark(qapp):
    window = make()
    pixmap = window.mark_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


# ===========================================================================
# the title bar, the footer and the shell
# ===========================================================================

def test_the_tabs_are_in_sonics_priority_order(qapp):
    u"""[X] RULED. *"the view should be in priority."*"""
    window = make()
    order = [b.text() for b in window.findChildren(gui_app.TabButton)]
    assert order == [u"Subtitles", u"Needs you", u"Settings"]
    assert list(gui_app.TABS) == [gui_app.TAB_SUBS, gui_app.TAB_PICK,
                                 gui_app.TAB_SET]


def test_the_title_line_derives_from_the_state(qapp):
    u"""\ud83d\udea8 FROM THE ROWS, NOT A FIELD. This asserted a `video_total` of 68 that only
    this file's fixture ever set; every real window said *"0 videos"* (LOOKED,
    2026-09-23, over a copy of Sonic's store: a run of 63 videos). \u26a0 So the count
    here is the fixture's ROWS, which is what the product reads."""
    window = make()
    rows = len(window.state.rows)
    assert rows > 1, u"the control: a fixture with several rows"
    assert window.titlesub.text() == (
        u"5 folders \u00b7 %d videos \u00b7 last run 03:00" % rows)
    window.state.folders = window.state.folders[:1]
    window.state.rows = window.state.rows[:1]
    window.render()
    assert window.titlesub.text() == u"1 folder \u00b7 1 video \u00b7 last run 03:00"


def test_run_now_is_in_the_title_bar_and_not_buried_in_settings(qapp):
    u"""[*] A CONTROL, NOT A SETTING. *"If a decision's answer will change over
    time, ship a control."* It replaced an option that did nothing."""
    window = make()
    titlebar = window.findChild(gui_app.Styled, u"titlebar")
    assert u"Run now" in [b.text() for b in titlebar.findChildren(QPushButton)]


def test_the_footer_carries_the_credit_and_the_cost(qapp):
    window = make()
    joined = u" ".join(gui_app.texts(window))
    assert u"Created by SonicSandbox" in joined
    assert u"GitHub" in joined
    assert window.right_label.text() == u"6 API calls \u00b7 41.2 s"


def test_the_api_cost_derives_from_the_run_object(qapp):
    u"""*"a user who cannot see the cost cannot notice a runaway loop."*"""
    window = make()
    window.state.summary = summary(api_calls=1, seconds=3.0)
    window.render()
    assert window.right_label.text() == u"1 API call \u00b7 3.0 s"


def test_the_live_dot_stops_when_the_run_does(qapp):
    u"""[X] NO DECORATION THAT DOES NOT REPORT -- a ring pulsing over a
    finished run says *working* about a thing that is not."""
    window = make()
    assert window.dot._anim.state() == window.dot._anim.State.Running
    window.state.running = False
    window.render()
    assert window.dot._anim.state() != window.dot._anim.State.Running


def test_switching_tabs_changes_what_is_shown(qapp):
    window = make()
    for tab in gui_app.TABS:
        window.show_tab(tab)
        assert window.body.currentWidget() is window.panes[tab]
        assert window.tab_buttons[tab].property(u"selected") == u"true"


def test_an_unknown_tab_name_changes_nothing(qapp):
    window = make()
    window.show_tab(u"nonsense")
    assert window.state.tab == gui_app.TAB_SUBS


# ===========================================================================
# settings -- and [X] it writes through the CLI, never the file
# ===========================================================================

def test_every_settings_edit_goes_out_through_hato_config(qapp):
    u"""[X] THE WINDOW NEVER EDITS `config.toml`. `hato/config.py` owns a
    closed schema, and a second writer means two programs disagreeing about
    one file."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    window._remove_folder(window.state.folders[0])
    window._remove_skip(window.state.skip_folders[0])
    window._toggle_recurse()
    assert len(window.spawned) == 3
    for argv in window.spawned:
        assert u"config" in argv and u"--json" in argv
    assert u"--remove-folder" in window.spawned[0]
    assert u"--remove-skip" in window.spawned[1]


def test_removing_a_folder_removes_it_from_the_list_too(qapp):
    u"""⚠ SCOPED TO THE SETTINGS PANE, AND THAT IS THE POINT OF THE CHECK.

    It used to walk the WHOLE window, which also contains the Subtitles rows
    — and those legitimately name files inside the folder that was just
    removed, because they are the last run's results. ⛔ It passed on Windows
    only because those row labels are `Elide` widgets whose text was elided at
    that font width; CI's first Linux run has a narrower default font, more
    text fitted, the full path survived in `.text()`, and the check went red.
    A check that holds because a font is wide enough is not checking anything.
    """
    window = make()
    gone = window.state.folders[0]
    window._remove_folder(gone)
    assert gone not in window.state.folders
    window.show_tab(gui_app.TAB_SET)
    settings = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert gone not in settings, \
        u"the folder is gone from state but still drawn in Settings"


def test_the_schedule_is_a_field_not_a_hardcoded_hour(qapp):
    u"""*"They need to be able to configure the computer timing."*"""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    assert window.time_field.text() == u"03:00"
    window.time_field.setText(u"04:30")
    window._set_schedule()
    assert window.state.schedule == u"04:30"
    assert window.autotime.text() == u"04:30"
    assert u"schedule=04:30" in window.spawned[0]


def test_the_blacklist_offers_to_clean_itself(qapp):
    u"""[*] hato CLEANS IT, NOT THE PERSON. *"it's likely they will not clean
    it as videos get rotated from there."* If you can tell which entries are
    dead, offering to remove them is the feature."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"2 of these are no longer on this machine" in joined
    assert u"Remove those 2" in joined


def test_one_rotated_out_row_is_said_in_the_singular(qapp):
    u"""The ruled mock shows twelve; at ONE the same card read *"1 of these are
    no longer on this machine"* beside *"Remove those 1"* -- found by looking at
    the Layer 8 shots, not by any check."""
    window = make()
    gone = [e for e in window.state.blacklist if e.get(u"gone")]
    assert len(gone) >= 2, u"the control: the fixture holds two rotated-out rows"
    window.state.blacklist = [e for e in window.state.blacklist if not e.get(u"gone")] + gone[:1]
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"1 of these is no longer on this machine" in joined and u"Remove it" in joined, joined
    assert u"Remove those 1" not in joined and u"1 of these are" not in joined, joined


def test_a_rotated_out_row_is_dimmed_and_labelled_never_removed(qapp):
    u"""[X] DEEMPHASISE, DON'T DELETE."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"Frieren S1 - 12.mkv" in joined
    gone = [w for w in window.findChildren(gui_app.Elide)
            if w.property(u"gone") == u"true"]
    assert len(gone) == 2
    assert all(w.font().strikeOut() for w in gone)


def test_the_blacklist_carries_a_date_a_count_and_a_filter(qapp):
    u"""*"ensure you have the day it was blacklisted and do what is possible
    to make that length not a burden."*"""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"4 videos" in joined
    assert u"17 Sep" in joined
    fields = [w for w in window.findChildren(QLineEdit)
              if w.objectName() == u"filter"]
    assert fields and fields[0].placeholderText()


def test_the_key_is_only_ever_shown_as_a_hint(qapp):
    u"""[X] `hato key --show` prints the last four characters and never more."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"set, ending JyQ" in joined
    assert u"never in a config file" in joined


def test_with_no_key_settings_says_what_would_fix_it(qapp):
    window = make(key_hint=None)
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"Add a key" in joined
    assert u"cannot fetch anything" in joined


def test_the_resident_cost_is_stated_because_it_was_measured(qapp):
    u"""[!] A NUMBER IN A UI IS A CLAIM. This line said *"~12 MB"* when nothing
    had measured it."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"13 MB" in joined
    assert u"13.4 MB resident" in joined


def test_the_tray_cost_is_the_one_measured_for_THIS_build(qapp, monkeypatch):
    u"""🚨 A CLAIM ABOUT THE BUILD IT IS SHOWN IN. 1.0.1 told every exe user the
    tray costs 13 MB -- the SOURCE figure. The exe's tray carries its own CPython
    and measured 30.6 MB (smoke, 2026-09-22)."""
    assert gui_app.tray_cost(frozen=False)[0] == u"13 MB"
    short, detail = gui_app.tray_cost(frozen=True)
    assert short == u"31 MB" and u"30.6 MB" in detail, (short, detail)
    monkeypatch.setattr(gui_app.sys, u"frozen", True, raising=False)
    window = make()
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window))
    assert u"Sits in the tray · 31 MB" in joined and u"13 MB" not in joined, joined


# ===========================================================================
# the run -- [X] and exit 1 is not an error
# ===========================================================================

def test_run_now_builds_the_argv_run_py_owns(qapp, monkeypatch):
    u"""[X] `--json` IS NOT A DISPLAY CHOICE -- it is what gives the window an
    outcome field to count instead of prose."""
    window = make(running=False)
    started = {}

    def record(**kw):
        started["argv"] = kw.get("argv")
        return _NullRunner()

    monkeypatch.setattr(gui_run, "Runner", record)
    window.start_run()
    assert started["argv"] == gui_run.argv_for(window.state.folders,
                                               progress=True)
    assert u"--json" in started["argv"]
    assert u"--progress" in started["argv"]


class _NullRunner(object):
    def start(self):
        return self

    def drain(self):
        return []

    def finished(self):
        return None


def test_CLICKING_run_now_starts_the_run_it_names(qapp, monkeypatch):
    u"""🚨 D12 -- 1.0.2 AND 1.0.3 CLOSED THE WINDOW ON THIS CLICK. Sonic,
    2026-09-24, on two machines: *"it crashes gui on 'run' button is clicked
    ... The automatic detection and run still seems to work great."*

    `clicked` carries `checked`, and PyQt hands it to the slot's first
    positional parameter. Layer 8 gave `start_run` an `argv=None`, so every
    click arrived as `start_run(False)`: `Runner(argv=False)`, `list(False)`
    raised out of the slot, and PyQt6 aborts on that -- `0xC0000409` in
    Qt6Core, four times in his own event log. Measured two-arm: the click
    handed `Runner` `False`, the direct call a real command.

    ⛔ The check above is named *"run now builds…"* and calls `start_run()` --
    the function under the button, never the button -- so it was green through
    both releases. This one clicks.
    """
    window = make(running=False)
    started = {}

    def record(**kw):
        started["argv"] = kw.get("argv")
        return _NullRunner()

    monkeypatch.setattr(gui_run, "Runner", record)
    assert window.run_now.isEnabled() and not window.state.running, \
        u"the control: a button that can be clicked, and no run going"
    click(window.run_now)
    assert started, u"clicking Run now started nothing"
    assert started["argv"] == gui_run.argv_for(window.state.folders, progress=True), (
        u"clicking Run now handed the run %r instead of the command for the "
        u"watched folders -- the click's `checked` flag reached `start_run`"
        % (started["argv"],))
    assert window.live_label.text() == u"starting…", \
        u"the footer says %r after the click" % window.live_label.text()


def _defaulted_slots(text):
    u"""Every `….connect(self.<method>)` whose method takes a DEFAULTED
    positional parameter, as `line N: self.m(param)`. -> [text]

    ⚠ The method is looked up in the class the `connect` sits in, then in any
    class of the module (an inherited one). A name found in neither is Qt's own
    (`accept`, `reject`) and has no Python default to fill."""
    tree = ast.parse(text)
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    anywhere = {}
    for cls in classes:
        for item in cls.body:
            if isinstance(item, ast.FunctionDef):
                anywhere.setdefault(item.name, []).append(item)
    found = []
    for cls in classes:
        own = dict((f.name, [f]) for f in cls.body if isinstance(f, ast.FunctionDef))
        for call in ast.walk(cls):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == u"connect" and call.args):
                continue
            target = call.args[0]
            if not (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name) and target.value.id == u"self"):
                continue
            for method in own.get(target.attr) or anywhere.get(target.attr) or ():
                positional = method.args.posonlyargs + method.args.args
                count = len(method.args.defaults)
                defaulted = positional[len(positional) - count:] if count else []
                if defaulted:
                    found.append(u"line %d: self.%s(%s)" % (
                        call.lineno, target.attr, u", ".join(a.arg for a in defaulted)))
    return sorted(set(found))


def test_no_method_wired_to_a_signal_has_a_default_a_click_would_fill():
    u"""🚨 D12'S CLASS, READ OFF THE SOURCE -- so the next button cannot ship it.

    PyQt fills a slot's positional parameters from the signal, and `clicked`,
    `toggled` and `triggered` all carry `checked`. A parameter with a DEFAULT
    was written to be left out; a click fills it anyway, which is how
    `start_run(argv=None)` came to be handed `False`. ⭐ Every
    `.connect(self.<method>)` in every module of `hato/gui/` is read, whatever
    the signal (a method's default is a claim about who calls it, and the
    source cannot say which signals carry nothing). Wire such a method as
    app.py does: `lambda _checked=False: self.method()`.

    ⚠ What this cannot see: a LAMBDA whose own first parameter has a default.
    The file's idiom (`_c=False`, `_checked=False`) guards those on real
    buttons; the lambdas without it sit on `Clickable`s, whose `clicked`
    carries nothing.
    """
    # ⭐ The control, first: the same reader DOES find the shape it hunts.
    shipped = (u"class W(object):\n"
               u"    def build(self):\n"
               u"        self.run_now.clicked.connect(self.start_run)\n"
               u"        self.box.toggled.connect(self._retarget)\n"
               u"    def start_run(self, argv=None, targeted=False):\n"
               u"        pass\n"
               u"    def _retarget(self, on):\n"
               u"        pass\n")
    assert _defaulted_slots(shipped) == [u"line 3: self.start_run(argv, targeted)"], \
        _defaulted_slots(shipped)
    assert u".connect(self." in source("app.py"), \
        u"the control: app.py wires methods to signals"
    found = []
    for name in sorted(os.listdir(GUI_DIR)):
        if name.endswith(u".py"):
            found.extend(u"%s %s" % (name, hit) for hit in _defaulted_slots(source(name)))
    assert found == [], u"a click would fill a parameter meant to be left out: %r" % found


# ===========================================================================
# 10b -- an error inside the window is written down, and the window stays
#
# Sonic, 2026-09-24: *"I want to include the logging in this next update."*
# PyQt6 aborts the process on any exception that leaves a slot, and a windowed
# exe has nowhere to say why -- D12 reached him as a window vanishing four times.
#
# ⚠ EVERY CHECK HERE PUTS A SENTINEL HOOK IN FIRST. Without one, a net that
# failed to install would not FAIL a check -- PyQt would abort the whole suite,
# and an abort prints no FAILED line for anyone to read.
# ===========================================================================

def _sentinel(monkeypatch):
    u"""A hook that is never the answer: it records what reached it. The
    threading hook is put back after the check too."""
    reached = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: reached.append(exc))
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    return reached


def _net_on(window, written):
    net = gui_app.ErrorNet(say=written.append).install()
    net.window = window
    window._error_net = net
    return net


def _settle(rounds=12):
    for _ in range(rounds):
        QApplication.processEvents()
        time.sleep(0.005)


def test_an_error_inside_a_click_is_written_down_and_the_window_stays(qapp, monkeypatch):
    u"""⭐ The window is still there, the traceback is in the log, and the
    footer says so in words -- not the exception's name."""
    window = make(running=False)
    reached = _sentinel(monkeypatch)
    written = []
    net = _net_on(window, written)
    assert sys.excepthook == net.hook and threading.excepthook == net.thread_hook, \
        u"the net did not take over the hooks"

    def broken():
        raise RuntimeError(u"a defect inside a click")

    monkeypatch.setattr(window, "start_run", broken)
    click(window.run_now)
    _settle()
    assert reached == [], u"the net never saw it -- the sentinel did: %r" % (reached,)
    assert written and u"a defect inside a click" in written[0], written
    assert window.live_label.text() == gui_app.ERROR_LINE, window.live_label.text()
    assert u"RuntimeError" not in window.live_label.text()
    assert u"hato.log" in window.live_label.toolTip(), window.live_label.toolTip()


class _Child(object):
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


class _OldRunner(object):
    u"""What `_runner` still holds after `Runner()` raised: the PREVIOUS run."""
    def __init__(self, code):
        self._process = _Child(code)


@pytest.mark.parametrize("previous", [None, 0], ids=["no-earlier-run", "earlier-run-finished"])
def test_a_run_the_error_cut_off_before_its_child_is_over(qapp, monkeypatch, previous):
    u"""🚨 D12's own shape: `running` is set, then `Runner()` raises. With an
    earlier run's object still in `_runner`, a check on the OBJECT alone left
    `running` true -- and Run now dead for the life of the window."""
    window = make(running=False)
    if previous is not None:
        window._runner = _OldRunner(previous)
    _sentinel(monkeypatch)
    written = []
    _net_on(window, written)

    def refuse(**_kw):
        raise TypeError(u"'bool' object is not iterable")

    monkeypatch.setattr(gui_run, "Runner", refuse)
    click(window.run_now)
    _settle()
    assert written, u"nothing was written"
    assert not window.state.running, u"the window still thinks a run is going"
    assert window.live_label.text() == gui_app.ERROR_LINE


def test_a_run_whose_child_is_alive_is_left_to_finish(qapp, monkeypatch):
    u"""The control for the check above: the error was the window's, and a
    child that IS running still owns its run."""
    window = make(running=True)
    window._runner = _OldRunner(None)          # poll() -> None: alive
    _sentinel(monkeypatch)
    net = _net_on(window, [])
    net.hook(RuntimeError, RuntimeError(u"elsewhere"), None)
    _settle()
    assert window.state.running


def test_the_repaint_that_reports_an_error_cannot_loop(qapp, monkeypatch):
    u"""⛔ A repaint that fails while reporting a failure must not report
    itself on every turn of the event loop."""
    window = make(running=False)
    reached = _sentinel(monkeypatch)
    written = []
    net = _net_on(window, written)
    renders = []

    def render():
        renders.append(1)
        raise ValueError(u"the repaint broke")

    monkeypatch.setattr(window, "render", render)
    net.hook(RuntimeError, RuntimeError(u"first"), None)
    _settle(rounds=40)
    assert len(renders) == 1, u"the repaint ran %d times -- it is looping" % len(renders)
    assert reached == []
    assert len(written) == 2 and u"the repaint broke" in written[1], written


def test_the_same_error_again_is_written_once_and_said_each_time(qapp, monkeypatch):
    u"""A timer slot's error repeats every tick: written ONCE. ⚠ But said every
    time -- the footer may have moved on before it came round again."""
    window = make(running=False)
    _sentinel(monkeypatch)
    written = []
    net = _net_on(window, written)
    error = RuntimeError(u"again and again")
    net.hook(RuntimeError, error, None)
    _settle()
    window.state.live = u"done"
    window.render()
    net.hook(RuntimeError, error, None)
    _settle()
    assert len(written) == 1, written
    assert window.live_label.text() == gui_app.ERROR_LINE, window.live_label.text()


def test_a_reader_threads_error_is_written_and_never_painted(qapp, monkeypatch):
    u"""⛔ A thread must never touch Qt, so its error is written and nothing
    else."""
    window = make(running=False)
    _sentinel(monkeypatch)
    written = []
    net = _net_on(window, written)
    window.state.live = u"done"

    class Args(object):
        exc_type, exc_value, exc_traceback = OSError, OSError(u"a pipe broke"), None

    net.thread_hook(Args())
    assert written and u"a pipe broke" in written[0], written
    assert window.state.live == u"done"


def test_the_net_writes_a_window_block_into_the_real_log(qapp, monkeypatch, tmp_path):
    u"""The seam: the net -> `watch.complain` -> hato.log, named for the window
    -- and ⛔ never a digit first, which is how a RUN's block is counted."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    gui_app.ErrorNet().write(u"Traceback: the window's own\n")
    with open(os.path.join(str(tmp_path), "hato.log"), encoding="utf-8") as handle:
        text = handle.read()
    assert re.search(u"^=== hato window \\d{4}-\\d\\d-\\d\\d .* ===\nTraceback: the window's own",
                     text, re.M), text
    assert not re.search(u"^=== hato \\d", text, re.M), u"it would be counted as a run"


def test_main_puts_the_net_up_before_anything_else(qapp):
    u"""Static: the first thing `main()` does, and the window is handed to it
    the moment it exists."""
    text = inspect.getsource(gui_app.main)
    first = text.find(u"ErrorNet().install()")
    assert first != -1, u"main() never installs the net"
    assert first < text.find(u"QApplication.instance()"), u"the net goes up after Qt"
    made = text.find(u"window = HatoWindow()")
    assert made < text.find(u"net.window = window") < text.find(u"settings_from_disk(")


def test_run_now_does_nothing_without_a_folder(qapp):
    u"""[X] `argv_for` RAISES on an empty list, and a window that lets the
    click through would show the traceback instead of the reason."""
    window = make(folders=[], running=False)
    assert window.start_run() is None
    assert not window.state.running


def test_a_second_run_now_while_one_is_going_does_nothing(qapp):
    u"""[X] Two children writing the same folder is the one thing a run lock
    exists to prevent, and the window must not be the thing that arms it."""
    window = make(running=True)
    assert window.start_run() is None
    assert window.spawned == []


def test_a_run_that_STOPPED_says_so_and_why_and_a_pick_is_done(qapp):
    u"""🚨 ADVERSARY 2026-09-22 A12. This check was called *"a finished run with
    exit one is not an error"*, and it pinned the misreading: exit 1 is a run CUT
    SHORT -- a 401, a server gone, a crash -- and was painted *done*, the reason
    nowhere. A run with picks exits 0 and IS done."""
    window = make()
    window.state.running = True
    window._runner = _FinishedRunner(gui_run.EXIT_CLEAN)
    window._drain()
    assert window.state.live == u"done" and not window.state.running
    stopped = dict(summary(), stopped=u"jimaku rejected the key (401) -- 12 videos not looked at")
    window.state.running = True
    window._runner = _FinishedRunner(gui_run.EXIT_STOPPED, summary=stopped)
    window._drain()
    assert window.state.live.startswith(u"stopped — ") and u"401" in window.state.live, (
        window.state.live)
    window.state.running = True
    window._runner = _FinishedRunner(gui_run.EXIT_STOPPED, notes=[
        u"hato: the run stopped on an unexpected RuntimeError: the disk went away"])
    window._drain()
    assert u"the disk went away" in window.state.live, window.state.live


def test_exit_two_says_it_could_not_run_and_what_hato_said(qapp):
    u"""A20 -- "could not run" and nothing more was every reason a person got."""
    window = make()
    window.state.running = True
    window._runner = _FinishedRunner(gui_run.EXIT_CANNOT_RUN, notes=[
        u"hato: --only names D:\\gone.mkv, which is not a file."])
    window._drain()
    assert window.state.live == u"could not run — --only names D:\\gone.mkv, which is not a file.", (
        window.state.live)


class _FinishedRunner(object):
    def __init__(self, code, summary=None, notes=()):
        self.code, self.summary, self.notes = code, summary, list(notes)

    def drain(self):
        return []

    def finished(self):
        return gui_run.Run(self.code, [], self.summary or {u"api_calls": 0}, self.notes,
                           u"\n".join(self.notes))


def test_progress_lines_reach_the_footer_sanitised(qapp):
    window = make()
    window._runner = _EventRunner([{u"type": u"progress",
                                    u"name": u"the pair was REFUSED"}])
    window._drain()
    assert u"refus" not in window.state.live.lower()
    assert u"refus" not in window.live_label.text().lower()


def test_video_objects_off_the_wire_become_rows(qapp):
    window = make(rows=[])
    window._runner = _EventRunner([added(1), summary()])
    window._drain()
    assert len(window.state.rows) == 1
    assert window.state.summary.get(u"api_calls") == 6


class _EventRunner(object):
    def __init__(self, events):
        self.events = list(events)

    def drain(self):
        out, self.events = self.events, []
        return out

    def finished(self):
        return None


# ===========================================================================
# the port itself
# ===========================================================================

def test_the_window_never_reimplements_what_run_py_owns():
    u"""[X] No second argv builder, no second NDJSON parse, no second outcome
    word. `run.py` owns all four and `app.py` calls it."""
    text = source("app.py")
    assert u"json.loads" not in text
    assert u"subprocess.Popen" in text          # exactly one, in `_spawn`
    assert text.count(u"subprocess.Popen") == 1
    # ⚠ `tally` replaced `counts` at RUNBOOK 8e as THE one count: it partitions
    # the run's rows AND the remembered problems. `counts` still exists, in
    # run.py, for the run alone -- the window no longer calls it.
    for owned in (u"argv_for_pair", u"argv_for_config", u"argv_for_retry",
                  u"argv_for_problems", u"outcome_word", u"tally",
                  u"needs_you", u"pick_verdict", u"retry_text", u"match_percent"):
        assert u"gui_run." + owned in text, u"app.py does not call run.py's %s" % owned


def test_importing_the_data_layer_still_costs_no_qt():
    u"""[X] `hato.gui.run` must stay importable on a machine with no display,
    so `hato/gui/__init__.py` may not import the window at module scope."""
    with open(os.path.join(GUI_DIR, "__init__.py"), encoding="utf-8") as handle:
        head = handle.read().split(u"def main")[0]
    assert u"from hato.gui.app" not in head
    assert u"PyQt6" not in source("run.py")
    assert u"PyQt6" not in source("theme.py")


def test_the_module_entry_point_exits_with_the_windows_code():
    u"""[!] A frozen bundle that returns `None` exits 0 no matter what."""
    text = source("__main__.py")
    assert u"sys.exit(main())" in text


def test_group_and_size_read_the_way_the_mock_shows_them():
    assert gui_app.group_of(u"[Erai-raws] Re Zero - 54.ass") == u"Erai-raws"
    assert gui_app.group_of(u"Re.Zero.S03E54.ja[cc].srt") == u"unknown group"
    assert gui_app.kb(29696) == u"29 KB"
    assert gui_app.kb(None) == u""
    assert gui_app.kb(0) == u"0 KB"


def test_a_long_filename_elides_rather_than_pushing_the_row_open(qapp):
    u"""[!] QSS HAS NO `text-overflow`. Without `Elide` a 90-character release
    name pushes the other columns out of the window -- the same class of fault
    that once hid an episode number behind an overflowing chip."""
    long_name = u"[SomeVeryLongReleaseGroupName] " + (u"x" * 120) + u".ass"
    window = make(rows=[added(1, name=long_name)])
    row = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)[0]
    assert row.nm.text() == long_name
    assert row.nm.width() <= gui_app.COL_NAME
    assert row.nm.minimumSizeHint().width() == 0


def test_the_content_column_is_capped_so_a_number_sits_beside_its_subject(qapp):
    u"""[!] A DEFECT FOUND BY LOOKING: stretched across the full width, a
    right-aligned number ended up ~900px from the text it described."""
    assert gui_app.COL_NAME == 640
    window = make(rows=[added(1)])
    window.resize(1600, 700)
    row = window.panes[gui_app.TAB_SUBS].findChildren(gui_app.SubRow)[0]
    row.adjustSize()
    assert row.nm.maximumWidth() <= gui_app.COL_NAME + 1


def test_one_easing_curve_for_the_whole_window():
    u"""[X] ONE accent, ONE curve, ONE distance. A second curve is the first
    step towards effects."""
    curve = gui_app.ease()
    assert 0.0 < curve.valueForProgress(0.5) < 1.0
    assert theme.EASE == ((0.2, 0.7), (0.3, 1.0))
    assert source("app.py").count(u"addCubicBezierSegment") == 1


# ===========================================================================
# [!] THE THREE LAYOUT DEFECTS A HUNDRED STATE ASSERTIONS DID NOT SEE
# ===========================================================================
# Each of these shipped, passed every check that existed, and was caught by
# opening a PNG. They are checks now so the next one is caught by the suite.

def test_no_two_things_in_a_blacklist_row_are_drawn_on_top_of_each_other(qapp):
    u"""[!] MEASURED, 2026-09-18: the note ran to x=630 inside a 576px row
    while the date started at x=490, so *"a commentary track"*, *"17 Sep"* and
    the remove button rendered as one unreadable smear.

    The cause was a size policy: `Ignored` tells Qt the hint is irrelevant and
    the widget may take whatever is going, so the eliding name claimed the row
    and Qt had nothing left for its fixed-width siblings.
    """
    window = lay_out(make())
    window.show_tab(gui_app.TAB_SET)
    lay_out(window)
    rows = [w for w in window.findChildren(gui_app.Styled)
            if w.objectName() == u"blrow"]
    assert rows, u"no blacklist rows were built"
    for row in rows:
        layout = row.layout()
        boxes = [layout.itemAt(i).widget().geometry()
                 for i in range(layout.count())
                 if layout.itemAt(i).widget() is not None]
        assert len(boxes) >= 3
        for left, right in zip(boxes, boxes[1:]):
            assert left.right() <= right.left(), \
                u"two cells overlap: %s then %s" % (left.getRect(),
                                                    right.getRect())
        assert boxes[-1].right() <= row.width(), \
            u"the last cell runs off the row"


def test_an_explanatory_paragraph_wraps_instead_of_being_truncated(qapp):
    u"""[!] MEASURED: *"...nothing sits running in the background. Each run
    finds whatever is new."* rendered as *"...Each run finds"* and stopped --
    no ellipsis, nothing to suggest anything was missing. Qt does not wrap a
    label unless told to, and an unwrapped label does not overflow, it
    silently truncates."""
    window = lay_out(make())
    window.show_tab(gui_app.TAB_SET)
    lay_out(window)
    long_ones = [w for w in window.findChildren(QLabel)
                 if w.objectName() == u"hint" and len(w.text()) > 80]
    assert long_ones, u"no paragraph-length hint was built"
    for widget in long_ones:
        assert widget.wordWrap(), \
            u"this paragraph will be truncated: %r" % widget.text()[:60]
        #: A wrapped label is taller than one line; an unwrapped one is not.
        #
        # 🚨 MEASURED AT A WIDTH THE TEXT CANNOT POSSIBLY FIT IN, not at the
        # design column. CI found this on the first run that reached Linux:
        # `heightForWidth(560)` returned 13 and one line IS 13, because the
        # runner's default font is narrower than this machine's and the
        # paragraph simply fitted. ⛔ The old assertion was really asking
        # *"is this font wide enough"*, which is not the thing the check is
        # named after -- and on a narrow font NOT wrapping is correct.
        metrics = widget.fontMetrics()
        natural = metrics.horizontalAdvance(widget.text())
        narrow = max(120, natural // 3)
        assert widget.heightForWidth(narrow) > metrics.height(), (
            u"an 80+ character paragraph did not wrap even at %dpx, so it "
            u"will be truncated rather than flowed: %r"
            % (narrow, widget.text()[:60]))


COL_HINT = 560


def test_the_count_badge_does_not_sit_on_top_of_its_tab_label(qapp):
    u"""[!] MEASURED: the tab read *"Needs yo(2)"* -- the badge was placed by
    maths that assumed Qt centres the text-plus-badge group, when Qt centres
    the TEXT. Every assertion about the count was green, because the count was
    right."""
    window = lay_out(make())
    tab = window.tab_buttons[gui_app.TAB_PICK]
    text_width = tab.fontMetrics().horizontalAdvance(tab.text())
    text_right = (tab.width() - text_width) / 2.0 + text_width
    assert tab.badge.x() >= text_right, \
        u"the badge overlaps the label by %dpx" % (text_right - tab.badge.x())
    assert tab.badge.x() + tab.badge.width() <= tab.width(), \
        u"the badge runs off the tab"


def test_a_hovered_control_answers_the_pointer(qapp):
    u"""Sonic: *"When hovering over buttons, there is action."* [X] And nothing
    that looks clickable may sit inert."""
    window = make()
    effect = window.run_now.graphicsEffect()
    assert effect is not None
    assert effect.blurRadius() == 0
    #: A REAL `QEnterEvent` through Qt's own path -- a stand-in object would
    #: prove only that the wrapper was called, not that Qt can deliver to it.
    spot = QPointF(2.0, 2.0)
    window.run_now.enterEvent(QEnterEvent(spot, spot, spot))
    #: The glow is ANIMATED, so it is mid-flight here; what this pins is that
    #: the hover reached the effect and gave it somewhere to go.
    assert window.run_now.graphicsEffect() is effect
    assert effect.color().alphaF() > 0


def test_every_clickable_thing_has_a_pointer_cursor(qapp):
    u"""[X] NOTHING THAT LOOKS CLICKABLE MAY SIT INERT -- and the cursor is
    the cheapest promise the window makes."""
    window = make()
    window.show_tab(gui_app.TAB_PICK)
    for widget in window.findChildren(gui_app.Clickable):
        assert widget.cursor().shape() == Qt.CursorShape.PointingHandCursor
    for widget in window.findChildren(QPushButton):
        assert widget.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ===========================================================================
# ⭐ RUNBOOK 8e -- Needs you persists, and every wait says so
# ===========================================================================

from datetime import datetime, timedelta, timezone          # noqa: E402

NOW8 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def remembered(episode=12, due=None, files=True, video=None):
    u"""What `hato problems --json` says about a video no run is showing: Sonic's
    real Tsuihou 12 -- three files tried on 19 Sep, all refused, a retry pending.
    ⚠ Its OWN candidates, never another show's (see REZERO_POOL's note)."""
    tried = [{u"name": u"[NanakoRaws] Tsuihou S01E%02d (CBC TV 1080p).ass" % episode,
              u"outcome": u"REFUSED", u"reason": u"70% matched overall, but the first "
              u"2:00 wants its timing moved about +9.8 s", u"bytes": 78228,
              u"match_rate": 0.70, u"path": u"C:\\hato\\cache\\a.ja.ass",
              u"when": u"2026-09-19T07:03:04+00:00"},
             {u"name": u"[shincaps] Tsuihou - %02d (AT-X 1440x1080).ass" % (episode - 1),
              u"outcome": u"REFUSED", u"reason": u"26% of reference lines matched",
              u"bytes": 100007, u"match_rate": 0.26, u"path": u"C:\\hato\\cache\\b.ja.ass",
              u"when": u"2026-09-19T07:03:05+00:00"}] if files else []
    due = due or NOW8 + timedelta(hours=13, minutes=20)
    # ⚠ `name` IS THE VIDEO'S OWN BASENAME, as `hato problems` builds it -- the
    # fixture's name and path used to name two different files.
    video = video or u"D:\\Anime\\Tsuihou\\[SubsPlease] Tsuihou - %02d (1080p).mkv" % episode
    return {u"type": u"video", u"source": u"memory",
            u"video": video, u"name": os.path.basename(video.replace(u"\\", os.sep)),
            u"title": u"Tsuihou sareta Tensei Juukishi", u"season": None,
            u"episode": episode, u"outcome": u"REFUSED" if files else u"NOT_FOUND",
            u"skip": None, u"reason": u"3 of 10 candidate(s) tried, all refused by timing",
            u"jimaku_entry": 12179, u"attempts": [], u"tried_before": tried,
            u"retry_after": due.isoformat(), u"newest_offered": None,
            u"candidates_offered": None, u"output_path": None}


def remembering(rows, memory, watching=False, **over):
    u"""A window whose memory has ANSWERED, after its rows were loaded -- the
    state a person reopening the window is in a second after it opens."""
    window = make(rows=rows, running=False, **over)
    window.state.now = NOW8
    window.state.watching = watching
    window.state.rows_at = window.state.moment()      # the snapshot, then...
    window.apply_problems(memory, {u"type": u"problems", u"retry_days": {u"soft": 1}})
    return window


def test_a_problem_the_last_run_never_looked_at_is_still_on_needs_you(qapp):
    u"""🚨 4a, THE HEADLINE. `last-run.json` holds only the last run; a run over a
    different folder -- a 3 a.m. one, a terminal -- used to wipe the problem from
    the window. The memory keeps it: the row is there, with its files."""
    window = remembering([added(1)], [remembered()])
    window.show_tab(gui_app.TAB_PICK)
    assert _badge_text(window) == u"1", u"the remembered problem is not counted"
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert u"Tsuihou - 12" in joined, joined
    cards = window.findChildren(gui_app.CandidateCard)
    assert len(cards) == 2, u"the remembered files are not on offer"


def test_the_row_that_stays_says_when_hato_looks_again(qapp):
    u"""🚨 4b -- *"retrying in 14h"* ON A ROW THAT STAYS. ⭐ A promise only when
    the tray is there to keep it (RUNBOOK 8h); without it, when it becomes due."""
    for watching, said in ((True, u"retrying in 14h"), (False, u"retry after 14h")):
        window = remembering([], [remembered()], watching=watching)
        window.show_tab(gui_app.TAB_PICK)
        head, = window.findChildren(gui_app.PickHead)
        assert said in head.best.text(), (watching, head.best.text())


@WINDOWS_LIBRARY
def test_a_row_the_newer_memory_no_longer_lists_has_been_settled(qapp):
    u"""A pick landed or a subtitle appeared since the snapshot: the memory, which
    asks the DISK, is the newer answer."""
    stale = needs_you(54)
    window = remembering([stale], [])
    assert window.state.need_count() == 0
    assert _badge_text(window) == u"0"


def test_look_again_now_runs_those_videos_past_their_wait(qapp, monkeypatch, tmp_path):
    u"""⭐ The manual half of 4b -- *"not soon unless prompted"* was specified as
    a Retry on one row and never built. ⛔ `--retry-now`, never `--force`: a file
    already refused is not fetched again."""
    started = {}

    def record(**kw):
        started[u"argv"] = kw.get(u"argv")
        return _NullRunner()

    monkeypatch.setattr(gui_run, u"Runner", record)
    video = _on_disk(tmp_path, u"ep12.mkv")
    window = remembering([], [remembered(files=False, video=video)])
    window.show_tab(gui_app.TAB_PICK)
    again = [b for b in window.findChildren(QPushButton) if b.text() == u"Look again now"]
    assert again, u"the waiting strip has no Look again now"
    again[0].click()
    argv = started.get(u"argv") or []
    assert u"--retry-now" in argv and u"--force" not in argv
    assert argv[argv.index(u"--only") + 1] == os.path.abspath(video)


def _on_disk(tmp_path, name):
    u"""⚠ A REAL FILE. A look-again now asks only about videos that are still
    there (A20), so a fixture path that exists nowhere is looked at by nobody."""
    path = tmp_path / name
    path.write_bytes(b"\x1aE\xdf\xa3 " + name.encode("utf-8"))
    return str(path)


def test_try_three_more_actually_tries_while_the_wait_stands(qapp, monkeypatch, tmp_path):
    u"""🚨 D3. It ran the folder with no flag, and for the day after a refusal the
    gate said "waiting" and it tried nothing."""
    started = {}
    monkeypatch.setattr(gui_run, u"Runner",
                        lambda **kw: started.update(argv=kw.get(u"argv")) or _NullRunner())
    window = remembering([], [remembered(video=_on_disk(tmp_path, u"ep12.mkv"))])
    key = window.state.key(window.state.picks()[0])
    window.try_more(key)
    argv = started[u"argv"]
    assert u"--retry-now" in argv and argv[argv.index(u"--candidates") + 1] == u"3"


def test_a_look_again_over_videos_no_longer_there_says_so_and_runs_nothing(
        qapp, monkeypatch, tmp_path):
    u"""ADVERSARY 2026-09-22 A20. `hato` refuses a whole `--only` batch over one
    name that is not a file, so one moved episode made *Look again now* on every
    waiting one say "could not run" and nothing more. ⭐ The ones still there are
    looked at; with none there, the window says why and runs nothing."""
    started = []
    monkeypatch.setattr(gui_run, u"Runner",
                        lambda **kw: started.append(kw.get(u"argv")) or _NullRunner())
    here = _on_disk(tmp_path, u"ep12.mkv")
    gone = str(tmp_path / u"ep13.mkv")
    window = remembering([], [remembered(12, files=False, video=here),
                              remembered(13, files=False, video=gone)])
    window.look_again(window.state.problems())
    argv, = started
    assert [argv[i + 1] for i, a in enumerate(argv) if a == u"--only"] == [os.path.abspath(here)]
    window.state.running = False
    window.look_again([remembered(13, files=False, video=gone)])
    assert len(started) == 1 and u"no longer where hato saw it" in window.state.live, (
        window.state.live)


def test_a_look_again_replaces_its_own_row_and_nothing_else(qapp):
    u"""⭐ One row's look-again must not empty the Subtitles tab."""
    window = make(rows=[added(1), needs_you(54)], running=False)
    window.state.running = True
    window._targeted = True
    fixed = dict(added(54), video=needs_you(54)[u"video"])
    window._runner = _EventRunner([fixed])
    window._drain()
    episodes = sorted(r[u"episode"] for r in window.state.rows)
    assert episodes == [1, 54]
    assert [r[u"outcome"] for r in window.state.rows if r[u"episode"] == 54] == [u"CONFIDENT"]


def test_a_run_that_met_another_one_says_so_rather_than_done(qapp):
    window = make(running=True)
    window._runner = _EventRunner([{u"type": u"busy", u"reason": u"another hato run"}])
    window._drain()
    window._runner = _FinishedRunner(gui_run.EXIT_CLEAN)
    window._drain()
    assert u"already running" in window.state.live, window.state.live


def test_settings_says_how_long_hato_waits_before_looking_again(qapp):
    u"""⭐ 4b: *"Sonic asked for the interval shown in Settings."* ⚠ The number is
    hato's own (`hato problems` reports it), not a literal in the window."""
    window = remembering([], [])
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"Looks again after 24 hours" in joined, joined
    window.apply_problems([], {u"retry_days": {u"soft": 3}})
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"Looks again after 3 days" in joined, joined


def test_a_subtitle_found_on_a_retry_says_so(qapp):
    u"""⭐ 4b's third clause -- SAY THAT IT HAPPENED. Tsuihou 12 fetched on its own
    two days after its refusal and nothing anywhere said so."""
    found = dict(added(12), tried_before=remembered()[u"tried_before"])
    window = make(rows=[found, added(1)], running=False)
    window.show_tab(gui_app.TAB_SUBS)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    assert u"found on a retry" in joined, joined
    window = make(rows=[added(1)], running=False)
    window.show_tab(gui_app.TAB_SUBS)
    assert u"found on a retry" not in u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))


def test_the_blacklist_card_shows_the_blacklist_hato_holds(qapp, tmp_path):
    u"""🚨 D5. `state.blacklist` started empty and nothing loaded it -- the card,
    its count and the sweep for rows whose video is gone ran on fixtures alone."""
    there = tmp_path / u"Recap - 07.mkv"
    there.write_bytes(b"x")
    answer = {u"ok": True, u"blacklist": [
        {u"video_hash": u"v1-" + u"a" * 64, u"video_path": str(there),
         u"added_at": u"2026-09-17T03:00:00+00:00", u"note": u"recap"},
        {u"video_hash": u"v1-" + u"b" * 64, u"video_path": str(tmp_path / u"gone.mkv"),
         u"added_at": u"2026-08-02T03:00:00+00:00", u"note": u""}]}
    window = make(blacklist=[], running=False)
    window._blacklist_read(None, [answer])
    names = [(e[u"name"], e[u"gone"]) for e in window.state.blacklist]
    assert names == [(u"Recap - 07.mkv", False), (u"gone.mkv", True)]
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"2 videos" in joined and u"no longer on this machine" in joined, joined


# ===========================================================================
# ⭐ RUNBOOK 8g -- clear hato's memory
# ===========================================================================

#: What `hato state --clear --json` counts over Sonic's real store (2026-09-22:
#: 148 rows over 60 videos; the shows are the resolution cache's).
MEMORY = {u"type": u"clear", u"ok": True, u"dry_run": True,
          u"cleared": {u"videos": 60, u"attempts": 148, u"present": 0, u"shows": 12,
                       u"waiting": 2},
          u"kept": [u"every subtitle beside your videos"], u"notes": []}


def _confirm(answer, blacklist=False):
    u"""A stand-in for the confirm: its answer, and the switch's position."""
    class Confirm(object):
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return answer

        def forget_blacklist(self):
            return blacklist
    return Confirm


def test_the_memory_card_names_what_goes_and_what_stays(qapp):
    u"""⛔ Before anything is asked: the numbers are hato's own dry count."""
    window = make(running=False)
    window._memory_read(None, [MEMORY])
    window.show_tab(gui_app.TAB_SET)
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"60 videos tried · 2 waiting to look again · 12 shows found on jimaku" in joined, (
        joined)
    assert u"Stays: every subtitle" in joined and u"the blacklist unless" in joined
    assert [b for b in window.findChildren(QPushButton)
            if b.text() == u"Clear hato's memory…"], u"the card has no way to clear"


def test_a_real_clears_answer_is_never_taken_for_the_count(qapp):
    u"""⚠ Only a DRY answer is the card's count; a clear that went is 0s."""
    window = make(running=False)
    went = dict(MEMORY, dry_run=False)
    window._memory_read(None, [went])
    assert window.state.memory is None


def test_clearing_asks_first_and_cancel_runs_nothing(qapp, monkeypatch):
    monkeypatch.setattr(gui_app, u"ClearDialog",
                        _confirm(gui_app.QDialog.DialogCode.Rejected))
    window = make(running=False)
    reads = []
    window._read = lambda argv, done: reads.append(argv)
    window.choose_clear()
    assert reads == [], u"a cancelled confirm still ran something: %s" % reads


def test_clearing_takes_the_blacklist_only_when_the_switch_is_on(qapp, monkeypatch):
    for on in (False, True):
        monkeypatch.setattr(gui_app, u"ClearDialog",
                            _confirm(gui_app.QDialog.DialogCode.Accepted, blacklist=on))
        window = make(running=False)
        reads = []
        window._read = lambda argv, done: reads.append(argv)
        window.choose_clear()
        argv, = reads
        assert argv == gui_run.argv_for_clear(yes=True, blacklist=on), argv
        assert u"--yes" in argv and (u"--blacklist" in argv) is on


def test_the_confirm_names_goes_and_stays_and_the_blacklist_starts_off(qapp):
    dialog = gui_app.ClearDialog(None, MEMORY, blacklisted=2)
    words = u" ".join(w.text() for w in dialog.findChildren(QLabel) if w.text())
    assert u"Goes: 60 videos tried" in words and u"Stays: every subtitle" in words, words
    switches = dialog.findChildren(gui_app.Switch)
    assert len(switches) == 1 and not switches[0].isChecked(), (
        u"the blacklist is the person's own instruction -- its switch must start OFF")
    assert dialog.forget_blacklist() is False
    switches[0].setChecked(True)
    assert dialog.forget_blacklist() is True
    assert gui_app.ClearDialog(None, MEMORY, blacklisted=0).findChildren(gui_app.Switch) == []
    faint = [w.text()[:12] for w in dialog.findChildren(QLabel)
             if w.text().startswith((u"Goes:", u"Stays:")) and w.objectName() == u"hint"]
    assert faint == [], (
        u"what goes and what stays -- the only two lines this dialog exists for -- "
        u"are in the faint aside style: %s" % faint)


def _late(newest, episode=12):
    u"""A remembered pick row whose newest episode on offer is `newest`."""
    return dict(remembered(episode), newest_offered=newest)


def test_one_past_the_newest_says_probably_not_out_yet_and_keeps_the_pick(qapp):
    u"""⭐ RUNBOOK 8f (HANDOFF 4c). The row stays, waits in grey instead of asking
    in garnet, says why -- and every file tried is still one click away."""
    window = remembering([], [_late(11)], watching=True)
    window.show_tab(gui_app.TAB_PICK)
    head, = window.findChildren(gui_app.PickHead)
    assert head.best.text().startswith(u"probably not out yet"), head.best.text()
    assert u"retrying in 14h" in head.best.text(), head.best.text()
    assert head.property(u"late") == u"true"
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.render()
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert u"Episode 12 is probably not out yet — the newest on jimaku is 11" in joined, joined
    assert len(window.findChildren(gui_app.CandidateCard)) == 2, u"the pick went away"
    assert [b for b in window.findChildren(QPushButton) if u"Look again" in b.text()
            or u"Try" in b.text()], u"the manual choice is not one click away"


def test_the_highlight_is_only_for_one_past_the_newest(qapp):
    u"""On offer, a gap, or nothing known: an ordinary pick -- and still a pick."""
    for newest in (12, 10, None):
        window = remembering([], [_late(newest)])
        window.show_tab(gui_app.TAB_PICK)
        head, = window.findChildren(gui_app.PickHead)
        assert not head.best.text().startswith(u"probably"), (newest, head.best.text())
        assert head.property(u"late") != u"true", newest
        assert len(window.findChildren(gui_app.CandidateCard)) == 2, newest


def _wait_button(window):
    found = [b for b in window.findChildren(QPushButton) if b.text() == u"Wait for it"]
    return found[0] if found else None


def test_wait_for_it_is_on_every_pick_and_highlighted_only_one_past_the_newest(qapp):
    u"""⭐ HANDOFF 4c: *"It should not always offer this as highlighted, only if it
    seems like the number increment is one higher than the latest option."*"""
    for newest, highlighted in ((11, True), (12, False), (None, False)):
        window = remembering([], [_late(newest)])
        window.show_tab(gui_app.TAB_PICK)
        window.state.open_pick = window.state.key(window.state.picks()[0])
        window.render()
        wait = _wait_button(window)
        assert wait is not None, u"no Wait for it on a pick (newest %r)" % newest
        assert (wait.objectName() == u"btnGo") is highlighted, (newest, wait.objectName())


def test_a_late_row_recommends_no_file(qapp):
    u"""⚠ Every file on a late row is another episode's -- outlining the best of
    them under *probably not out yet* recommended what the sentence says not to."""
    for newest, outlined in ((11, 0), (12, 1)):
        window = remembering([], [_late(newest)])
        window.show_tab(gui_app.TAB_PICK)
        window.state.open_pick = window.state.key(window.state.picks()[0])
        window.render()
        chosen = [c for c in window.findChildren(gui_app.CandidateCard)
                  if c.property(u"chosen") == u"true"]
        assert len(chosen) == outlined, (newest, len(chosen))


def test_waiting_puts_the_row_away_until_its_date_and_show_them_brings_it_back(
        qapp, tmp_path, monkeypatch):
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    window = remembering([], [_late(11)])
    window.show_tab(gui_app.TAB_PICK)
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.render()
    _wait_button(window).click()
    assert window.state.picks() == [] and _badge_text(window) == u"0", (
        u"a row the person chose to wait on still asks for them")
    joined = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert u"1 waiting for the next search" in joined, joined
    assert gui_run.load_waits(), u"the choice was not kept -- it would be undone on reopen"

    again = remembering([], [_late(11)])
    again.state.waits = gui_run.load_waits()
    assert again.state.picks() == [], u"reopened, the wait was forgotten"
    show = [b for b in again.findChildren(QPushButton) if b.text() == u"Show them"]
    again.show_tab(gui_app.TAB_PICK)
    show = [b for b in again.findChildren(QPushButton) if b.text() == u"Show them"]
    assert show, u"no way back to the pick"
    show[0].click()
    assert len(again.state.picks()) == 1 and gui_run.load_waits() == {}


def test_a_row_with_no_retry_offers_no_wait(qapp):
    u"""⛔ Nothing to wait FOR, so the control would do nothing -- it vanishes."""
    window = remembering([], [dict(_late(11), retry_after=None)])
    window.show_tab(gui_app.TAB_PICK)
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.render()
    assert _wait_button(window) is None


def test_a_real_rows_season_reads_as_a_season(qapp):
    u"""🚨 D10. The wire carries tsubasa's INT; every fixture carried "S2". A real
    row printed *"· 4"* after its filename and *"2 · 3 added"* beside its show."""
    assert gui_app.season_text(4) == u"S4" and gui_app.season_text(u"S2") == u"S2"
    assert gui_app.season_text(None) == u"" and gui_app.season_text(True) == u""
    window = remembering([], [dict(_late(11), season=4)])
    window.show_tab(gui_app.TAB_PICK)
    words = [w.text() for w in window.findChildren(QLabel) if w.objectName() == u"whoi"]
    assert u"· S4" in words, words
    subs = make(rows=[dict(added(1), season=2)], running=False)
    subs.show_tab(gui_app.TAB_SUBS)
    meta = [w.text() for w in subs.findChildren(QLabel) if w.objectName() == u"showmeta"]
    assert meta and meta[0].startswith(u"S2 · "), meta


def test_a_finished_run_asks_again_what_a_clear_would_take(qapp):
    u"""The card's numbers are hato's, so a run that moved them is asked about."""
    window = make(running=True)
    asked = []
    window._read = lambda argv, done: asked.append(argv)
    window._runner = _FinishedRunner(gui_run.EXIT_CLEAN)
    window._drain()
    assert gui_run.argv_for_clear() in asked, asked


def test_the_confirm_is_painted_by_hato_not_the_toolkit(qapp):
    u"""⚠ A PIXEL, not the stylesheet's existence -- the check that once passed
    over a white dialog asserted 16,440 characters of sheet (see the key's)."""
    dialog = gui_app.ClearDialog(None, MEMORY, blacklisted=2)
    dialog.resize(480, 260)
    image = dialog.grab().toImage()
    assert image.width() > 100 and image.height() > 100, u"nothing rendered"
    corner = image.pixelColor(6, 6)
    ceiling = sum(int(theme.SURFACE[i:i + 2], 16) for i in (1, 3, 5)) + 90
    assert corner.red() + corner.green() + corner.blue() <= ceiling, corner.name()


def test_a_clear_refused_by_a_run_says_nothing_was_cleared(qapp):
    u"""⛔ Never "cleared" over a refusal."""
    window = make(running=False)
    window._read = lambda argv, done: None
    window._memory_cleared(None, [{u"type": u"clear", u"ok": False, u"busy": True,
                                   u"error": u"a hato run is going"}])
    assert u"nothing was cleared" in window.state.memory_said
    window._memory_cleared(None, [dict(MEMORY, dry_run=False)])
    assert window.state.memory_said.startswith(u"Cleared")
    window._memory_cleared(None, [])
    assert u"could not" in window.state.memory_said


# ===========================================================================
# ⭐ ADVERSARY 2026-09-22 -- the window, driven by rows the CLI's own producer
# built (`report.as_dict`), never a hand-typed shape
# ===========================================================================

from hato import pipeline as _pipeline, report as _report       # noqa: E402


def wire(video, outcome, reason=u"x", **fields):
    u"""A row built by the SAME producer the CLI's `--json` uses."""
    return _report.as_dict(_pipeline.VideoResult(video, outcome, reason, **fields))


def memory_row(video, outcome, reason=u"x", **fields):
    u"""What `hato problems --json` prints -- `problems._row`'s shape."""
    fields.setdefault(u"name", video.replace(u"\\", u"/").rsplit(u"/", 1)[-1])
    fields.setdefault(u"candidates_offered", None)
    row = wire(video, outcome, reason, **fields)
    row[u"source"] = u"memory"
    return row


def rem(name, rate, path=u"C:\\hato\\cache\\x.ja.ass"):
    return _pipeline.Remembered(name, u"REFUSED", u"%s: the timing did not hold" % name,
                                40000, rate, path,
                                datetime(2026, 9, 21, 7, 3, 4, 123456, tzinfo=timezone.utc))


IRUMA = u"D:\\Anime\\Iruma S4\\[SubsPlease] Mairimashita! Iruma-kun S4 - 23 (1080p).mkv"
IRUMA_DUE = NOW8 + timedelta(hours=13, minutes=20)
IRUMA_TRIED = (rem(u"Iruma.S04E03.ja.srt", 0.36, u"C:\\hato\\cache\\a.ja.srt"),
               rem(u"Iruma.S04E20.ja.srt", 0.32, u"C:\\hato\\cache\\b.ja.srt"),
               rem(u"[NanakoRaws] Iruma S04E22.ass", 0.28, u"C:\\hato\\cache\\c.ja.ass"))


def iruma_memory(**over):
    u"""Sonic's own Iruma-kun S4 23, as `hato problems` lists it."""
    fields = dict(title=u"Mairimashita! Iruma-kun", season=4, episode=23, jimaku_entry=777,
                  retry_after=IRUMA_DUE, tried_before=IRUMA_TRIED, newest_offered=22)
    fields.update(over)
    return memory_row(IRUMA, u"REFUSED", u"3 of 3 candidate(s) tried, all refused by timing",
                      **fields)


def iruma_from_a_run():
    u"""The SAME video, as a run inside its retry window emits it -- the
    pipeline's negative skip, which now carries the memory's facts (A5)."""
    return wire(IRUMA, u"SKIPPED", u"3 of 3 candidate(s) tried, all refused by timing",
                skip=u"negative", title=u"Mairimashita! Iruma-kun", season=4, episode=23,
                retry_after=IRUMA_DUE, tried_before=IRUMA_TRIED, newest_offered=22,
                candidates_offered=None)


class Scripted(object):
    u"""A Runner stand-in: hands out `events`, then finishes with `code`."""

    def __init__(self, events, code=0, rows=None, summary=None, notes=()):
        self.events, self.code, self.notes = list(events), code, list(notes)
        self.rows = rows if rows is not None else [e for e in events if e.get(u"type") == u"video"]
        self.summary = summary or next((e for e in events if e.get(u"type") == u"run"), {})

    def start(self):
        return self

    def drain(self):
        out, self.events = self.events, []
        return out

    def finished(self):
        return gui_run.Run(self.code, self.rows, self.summary, self.notes,
                           u"\n".join(self.notes))

    def stop(self):
        pass


def pick_heads(window):
    return window.findChildren(gui_app.PickHead)


def pick_text(window):
    return u" | ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))


def buttons_called(window, text):
    return [b for b in window.findChildren(QPushButton) if b.text() == text]


def test_a_memory_that_could_not_be_read_keeps_needs_you_and_says_why(qapp):
    u"""A1. `hato problems` exits 1 for a broken config and answered an EMPTY list
    for an unreadable store -- and the window took either for "nothing needs
    you". ⭐ Only exit 0 with a summary that says `ok` replaces what is shown."""
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    assert _badge_text(window) == u"1"
    for finished, events, why in (
            (gui_run.Run(1, [], {}, [u"hato: config.toml: candidates must be at least 1"],
                         u""), [], u"candidates must be at least 1"),
            (gui_run.Run(1, [], {}, [], u""),
             [{u"type": u"problems", u"ok": False, u"error": u"The state DB is unreadable"}],
             u"The state DB is unreadable"),
            (gui_run.Run(0, [], {}, [], u""), [], u"it did not answer")):
        window._problems_read(finished, events)
        window.show_tab(gui_app.TAB_PICK)
        assert _badge_text(window) == u"1", (why, u"the problem vanished")
        assert why in pick_text(window) and u"could not read what it remembers" in \
            pick_text(window), pick_text(window)
    window._problems_read(gui_run.Run(0, [], {}, [], u""),
                          [{u"type": u"problems", u"ok": True, u"count": 0}])
    assert window.state.remembered == [] and window.state.problems_error == u"", (
        u"the control: a clean answer is taken, and the notice goes")


def test_an_unreadable_store_reaches_the_window_as_a_failure_through_a_real_child(
        qapp, tmp_path, monkeypatch):
    u"""A1b, the whole chain: a store that cannot be opened -> `hato problems`
    exits 1 with `ok: false` -> the window keeps Needs you and says why."""
    data = tmp_path / u"data"
    (data / u"state.db").mkdir(parents=True)          # a DB that cannot be opened
    (tmp_path / u"config.toml").write_text(u"folders = []\n", encoding="utf-8")
    monkeypatch.setenv(u"HATO_CACHE", str(data))
    monkeypatch.setenv(u"HATO_CONFIG", str(tmp_path / u"config.toml"))
    monkeypatch.delenv(u"HATO_CLI", raising=False)
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    window.spawn = window._spawn
    window.refresh_problems()
    deadline = time.time() + 90
    while window._problems_in_flight and time.time() < deadline:
        window._poll_reads()
        time.sleep(0.05)
    assert not window._problems_in_flight, u"hato problems never answered"
    window.show_tab(gui_app.TAB_PICK)
    assert _badge_text(window) == u"1", u"an unreadable store emptied Needs you"
    assert window.state.problems_error, u"the failure was not said"


@WINDOWS_LIBRARY
def test_a_refresh_asked_for_while_one_is_in_flight_is_queued_and_dated_by_its_asking(qapp):
    u"""A2. The run's own refresh was DROPPED while another was in flight; that
    one's answer -- the DB before the run -- landed newer than the run's rows and
    settled the run's new refusal."""
    old = iruma_memory()
    window = remembering([], [old])
    pending = []
    window._read = lambda argv, done: pending.append((argv, done)) or object()
    window.refresh_problems()                          # e.g. a pick's refresh
    # ⚠ IN A CONFIGURED FOLDER. Outside one, memory could never list the row and
    # A26 keeps it whatever the dates say -- so the first version of this check
    # passed with the answer dated on ARRIVAL, the defect it names (M8zw-06).
    new = wire(u"D:\\Anime\\ReZero S03\\ep55.mkv", u"REFUSED", u"3 tried, none held",
               title=u"Re:Zero", season=3, episode=55, retry_after=IRUMA_DUE,
               candidates_offered=3,
               attempts=(_pipeline.Attempted(u"[Erai-raws] Re Zero 3rd - 55.ass", u"REFUSED",
                                             u"25%", size=70000,
                                             path=u"C:\\hato\\cache\\s.ja.ass"),))
    assert window.state.in_scope(new), u"the control: memory COULD list this row"
    window.state.running = True
    window._runner = Scripted([new, {u"type": u"run", u"api_calls": 3}])
    window._drain()                                    # the run finishes
    asked = [a for a, _d in pending if a[-2:] == [u"problems", u"--json"]]
    assert len(asked) == 1, u"a second refresh went out while one was in flight"
    pending[0][1](gui_run.Run(0, [old], {}, [], u""),
                  [{u"type": u"problems", u"ok": True, u"retry_days": {u"soft": 1}}])
    assert any(r[u"video"] == new[u"video"] for r in window.state.problems()), (
        u"an answer asked BEFORE the run settled the run's own new refusal")
    asked = [a for a, _d in pending if a[-2:] == [u"problems", u"--json"]]
    assert len(asked) == 2, u"the refresh asked for during the first was never sent"


def test_a_run_that_meets_the_lock_leaves_the_last_run_on_screen(qapp, monkeypatch):
    u"""A3. Rows, summary and picks were cleared at the click; the run then said
    only "busy" -- an empty Subtitles tab and "last run 21:42" for a run that
    looked at nothing."""
    window = make(rows=full_rows(), running=False, last_run=u"03:00")
    before, added_before = list(window.state.rows), window.state.tallies()[gui_run.ADDED]
    monkeypatch.setattr(gui_run, u"Runner", lambda **kw: Scripted(
        [{u"type": u"busy", u"reason": u"another hato run holds the lock"}], code=0, rows=[]))
    window.start_run()
    window._timer.stop()
    window._drain()
    assert u"already running" in window.state.live
    assert window.state.rows == before and window.state.last_run == u"03:00"
    assert window.state.tallies()[gui_run.ADDED] == added_before > 0


@WINDOWS_LIBRARY
def test_a_look_again_on_one_row_never_brings_back_a_row_memory_settled(
        qapp, monkeypatch, tmp_path):
    u"""A4. One flag: during a look-again on row Y every stale snapshot row beat
    memory, and a row the person had just paired came back asking."""
    settled = needs_you(54)
    other = remembered(video=_on_disk(tmp_path, u"[SubsPlease] Tsuihou - 12 (1080p).mkv"))
    window = remembering([settled], [other])
    assert _badge_text(window) == u"1"
    monkeypatch.setattr(gui_run, u"Runner", lambda **kw: _NullRunner())
    window.look_again([other])
    window._timer.stop()
    assert window.state.running
    window.show_tab(gui_app.TAB_PICK)
    assert not [r for r in window.state.picks() if r[u"video"] == settled[u"video"]]
    assert _badge_text(window) == u"1"


def test_a_late_rows_copy_from_a_run_still_says_probably_not_out_yet(qapp):
    u"""A5. The run's copy of a late row carried no newest episode and "offered 0":
    while it won, the row turned garnet, OUTLINED another episode's file, and
    *Look again* claimed every file had been tried."""
    window = remembering([], [iruma_memory()])
    window.state.running = True
    window._runner = _EventRunner([iruma_from_a_run()])
    window._drain()
    shown, = window.state.problems()
    assert shown.get(u"source") != u"memory", u"the control: the run's own copy is shown"
    window.state.open_pick = window.state.key(shown)
    window.show_tab(gui_app.TAB_PICK)
    head, = pick_heads(window)
    assert head.best.text().startswith(u"probably not out yet"), head.best.text()
    assert not [c for c in window.findChildren(gui_app.CandidateCard)
                if c.property(u"chosen") == u"true"], u"another episode's file recommended"
    assert _wait_button(window).objectName() == u"btnGo"
    assert buttons_called(window, u"Look again now") and \
        not buttons_called(window, u"Try 3 more candidates")


def test_a_refusal_with_nothing_to_pick_says_its_reason_as_trouble(qapp):
    u"""A6. A two-episode name was painted as a pick over nothing -- "0 tried ·
    best —", *Click one to use it.* -- and its reason, the only actionable
    sentence, was nowhere."""
    two = wire(u"D:\\Anime\\Frieren S2\\frieren S2 - 01-02.mkv", u"REFUSED",
               u"the video holds episodes 1-2 -- one subtitle cannot be split between them. "
               u"Split the file, or pair a subtitle by hand with `hato sync`.",
               title=u"Frieren", season=2, episode=1)
    window = remembering([two], [])
    window.show_tab(gui_app.TAB_PICK)
    assert pick_heads(window) == [], u"a row with nothing to pick is a pick"
    text = pick_text(window)
    assert u"1 had a problem" in text and u"Split the file" in text, text
    assert u"Click one to use it." not in text


def test_two_spellings_of_one_video_are_one_row(qapp):
    u"""A7."""
    a = needs_you(54)
    b = dict(a, video=a[u"video"].lower() if os.name == u"nt" else a[u"video"])
    window = remembering([a, b], [dict(a, source=u"memory")])
    window.show_tab(gui_app.TAB_PICK)
    assert len(pick_heads(window)) == 1 and _badge_text(window) == u"1"


def test_wait_for_it_is_offered_only_for_a_date_still_ahead(qapp):
    u"""A8. With the tray off a retry can be past due; *Wait for it* was offered,
    highlighted, and a click put nothing away."""
    due = NOW8 - timedelta(hours=1)
    window = remembering([], [dict(_late(11), retry_after=due.isoformat())])
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    assert _wait_button(window) is None
    assert buttons_called(window, u"Look again now") or \
        buttons_called(window, u"Try 3 more candidates"), u"the manual choice went too"


def _landed(window, row, word=gui_run.FORCED):
    key = window.state.key(row)
    attempt = gui_run.candidates_of(row)[0]
    window.commit_pair(key, attempt)
    window.finish_pick(key, attempt[u"name"], (word, u"", u"D:\\x.ja.ass"))
    window.state.open_pick = key
    window.show_tab(gui_app.TAB_PICK)
    return key


def test_a_row_whose_pick_landed_offers_no_wait_and_no_second_pick(qapp, tmp_path,
                                                                   monkeypatch):
    u"""A9 + A10. After a pick landed the row still offered *Wait for it* -- which
    filed a written row as waiting -- and a second pick, which cannot land
    (tsubasa will not write over the file) and turned the row green over its
    failure word."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    row = _late(11)
    window = remembering([], [row])
    key = _landed(window, row)
    head, = pick_heads(window)
    assert head.best.text().startswith(u"used · ") and head.property(u"done") == u"forced"
    assert _wait_button(window) is None and not buttons_called(window, u"Look again now")
    cards = window.findChildren(gui_app.CandidateCard)
    assert cards and not any(c.isEnabled() for c in cards), u"a second pick is on offer"
    assert window.commit_pair(key, gui_run.candidates_of(row)[1]) is None
    head, = pick_heads(window)
    assert head.property(u"done") == u"forced", u"the colour is not the pick that landed"


def test_a_second_click_while_a_pick_is_with_hato_sync_is_not_taken(qapp):
    u"""A32. The first answer wiped the second's pending state."""
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    key = window.state.key(row)
    first = window.commit_pair(key, row[u"attempts"][0])
    assert first is not None
    assert window.commit_pair(key, row[u"attempts"][1]) is None
    assert window.state.pick_pending == {key: row[u"attempts"][0][u"name"]}


def test_a_rejected_key_is_said_in_plain_words(qapp):
    u"""A11. *"jimaku refused the key"* reached the key card verbatim."""
    window = make(running=False)
    window.state.key_status, window.state.key_ok = u"jimaku refused the key", False
    window.show_tab(gui_app.TAB_SET)
    words = gui_app.texts(window.panes[gui_app.TAB_SET])
    assert not [w for w in words if u"refus" in w.lower()], words
    assert u"jimaku did not accept that key" in words


def test_a_file_hato_no_longer_has_is_shown_unavailable_and_never_recommended(qapp):
    u"""A13. A candidate whose cached file is gone was offered AND outlined, and a
    click promised a remedy that is not there."""
    base = remembered()
    gone = dict(base, tried_before=[dict(base[u"tried_before"][0], path=None),
                                    base[u"tried_before"][1]])
    window = remembering([], [gone])
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    cards = dict((c.attempt[u"name"], c) for c in window.findChildren(gui_app.CandidateCard))
    missing = cards[gone[u"tried_before"][0][u"name"]]
    kept = cards[gone[u"tried_before"][1][u"name"]]
    assert not missing.isEnabled() and missing.property(u"gone") == u"true"
    assert missing.property(u"chosen") != u"true", u"a file hato does not have was recommended"
    assert kept.isEnabled() and kept.property(u"chosen") == u"true", (
        u"the control: the file hato has is the recommendation")
    window.commit_pair(window.state.key(gone), gone[u"tried_before"][0])
    assert u"Look again now fetches" not in pick_text(window)


def test_a_run_that_settles_a_remembered_problem_counts_it_added(qapp):
    u"""A14. The footer said "0 added · 1 needs you" beside a Subtitles row that
    said added."""
    mem = remembered()
    done = dict(added(12), video=mem[u"video"], title=mem[u"title"])
    window = remembering([], [mem])
    window.state.running = True
    window._runner = _EventRunner([done])
    window._drain()
    assert window.tally_labels[0].text() == u"1 added"
    assert _badge_text(window) == u"0"


def test_the_footer_accounts_for_every_video_on_screen(qapp):
    u"""A15. Three numbers, and waits, "had a problem" and landed picks were in
    none of them -- the footer summed to less than the rows on screen."""
    window = make(running=False)
    shown = [l for l in window.tally_labels if not l.isHidden()]
    total = sum(int(l.text().split()[0]) for l in shown)
    videos = set(window.state.key(r) for r in window.state.rows)
    videos |= set(window.state.key(r) for r in window.state.problems())
    assert total == len(videos), ([l.text() for l in shown], len(videos))
    assert [l.text() for l in shown][3:] == [u"1 waiting", u"1 had a problem"]


def test_an_idle_window_moves_its_dates_on_as_they_pass(qapp, tmp_path, monkeypatch):
    u"""A16. Nothing re-rendered on a date: a waited row stayed hidden, and
    "retrying in 30m" read the same five hours later."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    soon = NOW8 + timedelta(minutes=30)
    window = remembering([], [dict(_late(11), retry_after=soon.isoformat())])
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    _wait_button(window).click()
    assert _badge_text(window) == u"0"
    timer = window.follow_other_runs(every_ms=3600000)
    timer.stop()
    window.state.now = soon + timedelta(hours=5)
    window._minute_seen = -1
    timer.timeout.emit()
    assert _badge_text(window) == u"1", u"the date passed and the window never said so"


def test_the_not_on_jimaku_note_says_both_waits(qapp):
    u"""A17. A show with no entry waits 30 days, under a note saying 24 hours."""
    hard = memory_row(u"D:\\Anime\\Obscure\\ep01.mkv", u"NOT_FOUND", u"no jimaku entry matched",
                      title=u"Obscure", episode=1,
                      retry_after=NOW8 + timedelta(days=29, hours=23))
    window = remembering([], [hard])
    window.apply_problems([hard], {u"type": u"problems", u"ok": True,
                                   u"retry_days": {u"soft": 1, u"hard": 30}})
    window.show_tab(gui_app.TAB_PICK)
    tips = u" ".join(w.toolTip() for w in window.panes[gui_app.TAB_PICK].findChildren(QLabel)
                     if w.toolTip()).replace(u"\n", u" ")
    assert u"24 hours" in tips and u"30 days" in tips, tips


def test_a_name_with_no_number_never_prints_none(qapp):
    u"""A18."""
    row = memory_row(u"D:\\Anime\\Special\\Show - OVA.mkv", u"NOT_FOUND", u"no file yet",
                     title=u"Show - OVA", retry_after=IRUMA_DUE)
    window = remembering([], [row])
    window.show_tab(gui_app.TAB_PICK)
    assert u"None" not in pick_text(window) and u"Show - OVA" in pick_text(window)


def test_blacklisting_a_row_only_the_run_holds_takes_it_off_needs_you(qapp):
    u"""A19. A clash or a two-episode row is never in hato's memory, so after
    the person blacklisted it, it went on asking until the next full run."""
    clash = wire(u"D:\\Anime\\X\\ep06.mkv", u"REFUSED",
                 u"this video and ep06.mp4 would be given the SAME subtitle file",
                 title=u"X", episode=6)
    window = remembering([clash], [])
    key = window.state.key(clash)
    window._read = lambda argv, done: None
    window.blacklist(key)
    window._blacklisted(key, gui_run.Run(0, [], {}, [], u""), [{u"ok": True}])
    assert not [r for r in window.state.problems() if window.state.key(r) == key]


def test_the_wait_says_who_will_search_when_the_tray_is_off(qapp):
    u"""A21. With no tray nothing searches on its own, and the tooltip said it would."""
    window = remembering([], [_late(11)], watching=False)
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    tip = _wait_button(window).toolTip().replace(u"\n", u" ")
    assert u"on its own (" not in tip and u"the next time it runs" in tip, tip


def test_found_on_a_retry_does_not_claim_the_first_files_did_not_line_up(qapp):
    u"""A22. What was tried first can be a download that FAILED."""
    errored = [dict(t, outcome=u"ERROR", match_rate=None, path=None,
                    reason=u"x.ass could not be downloaded: 503")
               for t in remembered()[u"tried_before"]]
    window = make(rows=[dict(added(12), tried_before=errored)], running=False)
    window.show_tab(gui_app.TAB_SUBS)
    text = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SUBS]))
    assert u"found on a retry" in text and u"did not line up with your copy;" not in text


def test_a_look_agains_cost_is_said(qapp):
    u"""A23. What a look-again spent was never said."""
    window = make(running=True)
    window._targeted = True
    window._runner = Scripted([], code=0, rows=[],
                              summary={u"type": u"run", u"api_calls": 9, u"seconds": 12.0})
    window._drain()
    assert window.state.live.startswith(u"done · looked again: 9 API calls"), window.state.live


def test_a_remembered_pick_whose_offer_is_unknown_offers_to_look_again(qapp):
    u"""A24. Memory cannot say how many files the entry offers, and "Try 3 more"
    promised three new ones where there may be none."""
    window = remembering([], [iruma_memory(newest_offered=None)])
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    assert buttons_called(window, u"Look again now") and \
        not buttons_called(window, u"Try 3 more candidates")


def test_a_refusal_outside_the_configured_folders_is_not_settled_by_memory(qapp):
    u"""A26. `hato D:\\Elsewhere` from a terminal: memory can never list it."""
    elsewhere = wire(u"E:\\Elsewhere\\Show - 05.mkv", u"REFUSED", u"3 tried, none held",
                     title=u"Show", episode=5, retry_after=IRUMA_DUE, candidates_offered=3,
                     attempts=(_pipeline.Attempted(u"[G] Show - 05.ass", u"REFUSED", u"40%",
                                                   size=1000, path=u"C:\\hato\\cache\\e.ja.ass"),))
    window = remembering([elsewhere], [])
    assert [r[u"video"] for r in window.state.problems()] == [elsewhere[u"video"]]
    assert _badge_text(window) == u"1"


def test_clearing_the_memory_does_not_empty_needs_you(qapp):
    u"""A27. After a clear, an empty memory "settled" every row on screen."""
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    window._read = lambda argv, done: None
    window._memory_cleared(None, [{u"type": u"clear", u"ok": True, u"dry_run": False}])
    window.apply_problems([], {u"type": u"problems", u"ok": True})
    window.show_tab(gui_app.TAB_PICK)
    assert _badge_text(window) == u"1" and u"Nothing needs you." not in pick_text(window)


def test_a_half_episode_is_not_printed_as_the_whole_one():
    u"""A28."""
    assert gui_app.episode_text(24.5) == u"24.5" and gui_app.episode_text(24.0) == u"24"
    assert gui_app.episode_text(7) == u"07" and gui_app.episode_text(None) == u""


def test_a_blacklist_date_is_the_persons_day():
    u"""A29. Stored in UTC, and shown as UTC's day."""
    added_at = u"2026-09-18T02:30:00+00:00"
    shown = gui_run.blacklist_entries({u"blacklist": [{u"video_hash": u"v1-x",
                                                        u"video_path": u"", u"note": u"",
                                                        u"added_at": added_at}]})[0][u"when"]
    local = datetime.fromisoformat(added_at).astimezone().strftime(u"%d %b").lstrip(u"0")
    assert shown == local, (shown, local)


def test_look_again_is_not_offered_while_a_run_is_going(qapp):
    u"""A30. During a run it did nothing, and said nothing."""
    window = remembering([], [remembered(files=False)])
    window.state.running = True
    window.show_tab(gui_app.TAB_PICK)
    again, = buttons_called(window, u"Look again now")
    assert not again.isEnabled() and u"run is going" in again.toolTip()


def test_removing_a_blacklist_row_reads_hatos_answer(qapp):
    u"""A31. The row was dropped at the click and the answer never read."""
    window = make(running=False)
    entry = window.state.blacklist[0]
    reads = []
    window._read = lambda argv, done: reads.append((argv, done))
    window.unblacklist(entry)
    assert entry in window.state.blacklist and entry.get(u"removing"), (
        u"the row went at the click")
    (argv, done), = reads
    assert u"--remove" in argv
    asked = []
    window.refresh_blacklist = lambda: asked.append(True)
    done(gui_run.Run(0, [], {}, [], u""), [{u"ok": True}])
    assert asked, u"hato's own list was not asked again"


def test_a_long_look_again_goes_in_a_list_file(tmp_path, monkeypatch):
    u"""A33. Past Windows' command-line limit the child could not even start."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path / u"data"))
    videos = [str(tmp_path / (u"Some Long Show Title Number %03d" % i) /
                  (u"[SubsPlease] Some Long Show Title Number %03d - 01 (1080p).mkv" % i))
              for i in range(300)]
    argv = gui_run.argv_for_retry(videos, [str(tmp_path)])
    assert u"--only" not in argv and u"--only-list" in argv
    assert len(u" ".join(argv)) < gui_run.COMMAND_LINE_BUDGET
    listed = open(argv[argv.index(u"--only-list") + 1], encoding="utf-8").read().splitlines()
    assert listed == [os.path.abspath(v) for v in videos]
    short = gui_run.argv_for_retry(videos[:2], [str(tmp_path)])
    assert u"--only-list" not in short and short.count(u"--only") == 2, u"the control"


def test_an_older_tray_is_said_and_can_be_replaced(qapp, monkeypatch):
    u"""V1. A 1.0.1 tray writes the same pid file and keeps no retry promise --
    and turning watching on does not replace a running tray."""
    window = make(running=False, old_tray=True)
    window.show_tab(gui_app.TAB_SET)
    text = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"an older version" in text, text
    calls = []
    monkeypatch.setattr(window, u"stop_watcher", lambda: calls.append(u"stop"))
    monkeypatch.setattr(window, u"start_watcher", lambda: calls.append(u"start"))
    restart, = buttons_called(window, u"Restart the tray")
    restart.click()
    assert calls == [u"stop", u"start"] and not window.state.old_tray


def test_the_alarming_word_is_nowhere_in_a_window_that_remembers(qapp):
    u"""The walk at the top of this file, over what LAYER 8 added -- which it
    never saw: every state it drove was the default fixture's (ADVERSARY
    2026-09-22, the window's checks that passed for the wrong reason).
    Remembered rows carry the engine's reason on every file tried, a refusal
    with nothing to pick shows its reason as trouble, a failed pick shows what
    `hato sync` answered, and a run's notes are engine prose too."""
    clash = wire(u"D:\\Anime\\X\\ep06.mkv", u"REFUSED",
                 u"refused: this video and ep06.mp4 would be given the SAME subtitle file",
                 title=u"X", episode=6)
    mem = remembered()
    window = remembering([needs_you(54), clash], [mem, iruma_memory()], watching=True)
    window.state.summary = dict(window.state.summary or {},
                                notes=[u"1 video(s) were refused by the timing check"])
    window.finish_pick(window.state.key(mem), gui_run.candidates_of(mem)[0][u"name"],
                       (gui_run.PICK_REFUSED, u"REFUSED: 40% of reference lines matched", None))
    walked = 0
    for tab in gui_app.TABS:
        window.show_tab(tab)
        for row in window.state.problems():
            window.state.open_pick = window.state.key(row)
            window.render()
            for text in gui_app.texts(window):
                walked += 1
                assert u"refus" not in text.lower(), (
                    u"the engine's word reached the interface: %r" % text)
    assert walked > 100, u"the walk read almost nothing (%d strings)" % walked


def test_the_window_tells_an_older_tray_from_its_real_pid_file(qapp, tmp_path, monkeypatch):
    u"""V1, the window's half, read off the REAL pid file: this build's tray keeps
    the retry promise, a 1.0.1 tray's file names no capability and keeps none --
    and a promise read off "a tray is running" was the defect."""
    from hato import runlock
    from hato import watch as _watch
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    win = gui_app.HatoWindow
    assert not win.tray_is_watching() and not win.tray_is_old(), u"no tray, no promise"
    _watch.write_pid_file()
    assert win.tray_is_watching() and not win.tray_is_old(), u"this build's tray was not read"
    stamp = runlock._process_start(os.getpid())
    _watch.pid_file_path().write_text(u"%d %s" % (os.getpid(), stamp or u"-"), encoding="utf-8")
    assert not win.tray_is_watching(), u"a 1.0.1 tray was read as keeping retry promises"
    assert win.tray_is_old(), u"a 1.0.1 tray was not recognised as an older one"


@WINDOWS_LIBRARY
def test_a_look_again_is_newer_only_about_its_own_video(qapp):
    u"""A4, through the stream. A look-again at ONE row used to make the whole
    snapshot newer than hato's memory -- so a row the memory had settled since
    (paired, blacklisted) came back asking while the look-again ran."""
    settled, asked = needs_you(54), needs_you(55)
    window = remembering([settled, asked], [dict(asked, source=u"memory")])
    key = window.state.key
    assert [key(r) for r in window.state.problems()] == [key(asked)], (
        u"the control: the memory has settled the other row")
    window.state.running = True
    window._targeted = True
    window._runner = _EventRunner([dict(asked)])
    window._drain()
    assert [key(r) for r in window.state.problems()] == [key(asked)], (
        u"a look-again at one row brought back a row hato had settled: %r"
        % [r[u"video"] for r in window.state.problems()])


def test_a_later_failed_answer_does_not_recolour_the_pick_that_landed(qapp, tmp_path,
                                                                      monkeypatch):
    u"""A10, the colour. A row's colour came from the LAST answer, so a failure
    arriving after a pick had landed painted "still did not line up" over a file
    that was written."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    row = _late(11)
    window = remembering([], [row])
    key = _landed(window, row)
    other = gui_run.candidates_of(row)[1]
    window.finish_pick(key, other[u"name"], (gui_run.PICK_REFUSED, u"26% matched", None))
    head, = pick_heads(window)
    assert head.property(u"done") == u"forced", head.property(u"done")
    assert head.best.text().startswith(u"used · "), head.best.text()


def test_the_windows_moments_never_tie():
    u"""The merge COMPARES moments to decide which copy of a row is newer, and
    `time.monotonic()` repeats one reading for ~16 ms on Windows: a row streamed
    just after the memory answered tied it, and lost."""
    state = gui_app.State()
    seen = [state.moment() for _ in range(2000)]
    assert all(b > a for a, b in zip(seen, seen[1:])), u"two moments tied or went back"


# -- halves of the Layer 8 fixes the M8zw builder found no check could see --------------
#
# ⭐ Each was a mutant that SURVIVED every check near it: the fix was in the code,
# and nothing would have noticed it go. One check each, named for its finding.

def test_a_config_that_will_not_read_is_said_on_needs_you(qapp):
    u"""A1's other door: a broken config.toml sets `config_error`, and Needs you
    kept its rows without saying they are not up to date -- no check had ever
    set it."""
    window = remembering([], [remembered()])
    window.state.config_error = u"config.toml: candidates must be at least 1"
    window.show_tab(gui_app.TAB_PICK)
    text = pick_text(window)
    assert u"not up to date" in text and u"candidates must be at least 1" in text, text


def test_a_look_again_that_finds_the_subtitle_settles_the_row_at_once(qapp):
    u"""A4's feed. A look-again's streamed row is newer than memory for THAT video:
    a CONFIDENT one settles it the moment it arrives. Without the live key the
    stale remembered copy asked on until `hato problems` answered again."""
    mem = remembered()
    window = remembering([], [mem])
    key = window.state.key(mem)
    assert key in [window.state.key(r) for r in window.state.problems()], u"the control"
    window.state.running = True
    window._targeted = True
    window._runner = _EventRunner([dict(added(12), video=mem[u"video"], title=mem[u"title"])])
    window._drain()
    assert key not in [window.state.key(r) for r in window.state.problems()], (
        u"a look-again that FOUND the subtitle left the row asking until memory answered")


def test_every_trouble_row_says_its_own_reason(qapp):
    u"""A6's list: one reason per trouble row, up to four. Every check held exactly
    one trouble row, so a list that said only the first was invisible."""
    one = wire(u"D:\\Anime\\X\\ep06.mkv", u"REFUSED",
               u"this video and ep06.mp4 would be given the SAME subtitle file",
               title=u"X", episode=6)
    two = wire(u"D:\\Anime\\X\\ep07.mkv", u"REFUSED",
               u"the name holds two episodes, 07 and 08", title=u"X", episode=7)
    window = remembering([one, two], [])
    window.show_tab(gui_app.TAB_PICK)
    text = pick_text(window)
    assert u"SAME subtitle file" in text and u"holds two episodes" in text, text


@WINDOWS_LIBRARY
def test_the_windows_one_identity_for_a_row_is_the_normalised_video():
    u"""A7 at the root. The pick in flight, the open row and the waits all key on
    `State.key` -- and every check reached it through a merge that normalises
    again, so a raw-path key would have split them in silence."""
    row = needs_you(54)
    other = dict(row, video=row[u"video"].replace(u"ReZero S03", u"ReZero S03\\x\\.."))
    if os.name == "nt":
        other[u"video"] = other[u"video"].lower()
    assert gui_app.State.key(row) == gui_app.State.key(other), (
        gui_app.State.key(row), gui_app.State.key(other))


@WINDOWS_LIBRARY
def test_a_video_added_under_two_spellings_is_counted_once():
    u"""A7 in the footer: ADDED counts each video once, whatever it is spelled."""
    row = added(1)
    other = dict(row, video=row[u"video"].replace(u"\\ep", u"\\x\\..\\ep"))
    assert gui_run.tally([row, other], [])[gui_run.ADDED] == 1


def test_look_again_on_a_remembered_row_never_claims_every_file_was_tried(qapp):
    u"""A24 / A5, the words on the button. Memory cannot say how many files the
    entry offers, so *"every file jimaku offered has been tried"* is a claim it
    cannot make -- and no check read the tooltip."""
    window = remembering([], [iruma_memory(newest_offered=None)])
    window.state.open_pick = window.state.key(window.state.picks()[0])
    window.show_tab(gui_app.TAB_PICK)
    again, = buttons_called(window, u"Look again now")
    assert u"Every file jimaku offered" not in again.toolTip(), again.toolTip()


def test_a_refusal_in_a_skipped_folder_is_not_settled_by_memory(qapp):
    u"""A26 under a SKIPPED folder: memory never lists a video there either, so
    its silence settles nothing -- the check above covered only a folder outside
    Settings altogether."""
    video = u"D:\\Anime\\ReZero S03\\Extras\\ep05.mkv"
    row = wire(video, u"REFUSED", u"3 tried, none held", title=u"Re:Zero", season=3,
               episode=5, retry_after=IRUMA_DUE, candidates_offered=3,
               attempts=(_pipeline.Attempted(u"[G] Re Zero - 05.ass", u"REFUSED", u"40%",
                                             size=1000, path=u"C:\\hato\\cache\\e.ja.ass"),))
    window = remembering([row], [])
    window.state.skip_folders = [u"D:\\Anime\\ReZero S03\\Extras"]
    assert [r[u"video"] for r in window.state.problems()] == [video], (
        u"a refusal in a skipped folder was settled by a memory that can never list it")


def test_after_a_clear_the_next_run_trusts_memory_again(qapp, tmp_path, monkeypatch):
    u"""A27's other end. A clear makes memory's silence settle nothing -- UNTIL the
    next run, this window's or another process's, whose rows are the newest word.
    Never reset, a row settled after the clear would ask for ever."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    window._read = lambda argv, done: None
    window._memory_cleared(None, [{u"type": u"clear", u"ok": True, u"dry_run": False}])
    assert window.state.trust_rows, u"the control: a clear trusts the run's rows"
    window._fresh = True
    window._begin_fresh()
    assert not window.state.trust_rows, u"this window's next run left the clear's trust"
    window.state.trust_rows = True
    timer = window.follow_other_runs(every_ms=3600000)
    timer.stop()
    gui_run.save_last_run([added(1)], {u"type": u"run", u"dry_run": False})
    timer.timeout.emit()
    assert not window.state.trust_rows, u"another process's run left the clear's trust"


def test_the_sweep_marks_every_gone_row_removing_and_reads_the_answers(qapp):
    u"""A31 for *Remove those N*: going, not gone, until hato's own list says so --
    and painted as going. No check had clicked the sweep or drawn such a row."""
    window = make(running=False)
    reads = []
    window._read = lambda argv, done: reads.append((argv, done))
    gone = [e for e in window.state.blacklist if e.get(u"gone")]
    assert gone, u"the control: the fixture holds rotated-out rows"
    sent = window.remove_stale_blacklist()
    assert len(sent) == len(gone) == len(reads), (len(sent), len(gone), len(reads))
    assert all(e.get(u"removing") and e in window.state.blacklist for e in gone), (
        u"a row went at the click, before hato said so")
    window.show_tab(gui_app.TAB_SET)
    assert u"removing…" in gui_app.texts(window.panes[gui_app.TAB_SET])


def test_a_row_with_a_pick_in_flight_takes_no_second_click(qapp):
    u"""A32, drawn: the cards of a row whose pick is with `hato sync` are disabled
    -- the check above asked the handler, and never rendered the cards."""
    row = needs_you(54)
    window = remembering([row], [dict(row, source=u"memory")])
    window._read = lambda argv, done: None
    key = window.state.key(row)
    window.state.open_pick = key
    assert window.commit_pair(key, row[u"attempts"][0]) is not None, u"the control"
    window.show_tab(gui_app.TAB_PICK)
    cards = window.findChildren(gui_app.CandidateCard)
    assert cards and not any(c.isEnabled() for c in cards), (
        u"a row with a pick in flight still takes a click")


def test_the_windows_poll_notices_an_older_tray(qapp, tmp_path, monkeypatch):
    u"""V1 on a running window: an older tray started after the window opened is
    noticed on the next look. Only `make(old_tray=True)` had ever set it."""
    from hato import runlock
    from hato import watch as _watch
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    window = make(running=False)
    assert not window.state.old_tray, u"the control: no tray yet"
    _watch.pid_file_path().parent.mkdir(parents=True, exist_ok=True)
    stamp = runlock._process_start(os.getpid())
    _watch.pid_file_path().write_text(u"%d %s" % (os.getpid(), stamp or u"-"), encoding="utf-8")
    timer = window.follow_other_runs(every_ms=3600000)
    timer.stop()
    timer.timeout.emit()
    assert window.state.old_tray and not window.state.watching, (
        window.state.old_tray, window.state.watching)


# ---------------------------------------------------------------------------
# ⭐ D2 -- "runs automatically at 03:00" REGISTERS SOMETHING, AND SAYS SO
#
# 🚨 The switch read ON for days over no task at all: it was drawn from
# `bool(cfg.schedule)` -- always true -- and turning it off sent `schedule=off`,
# which the config refuses by name. Task Scheduler is now the only state
# (`hato/schedule.py`); these hold the WINDOW to it. `schedule`'s functions are
# faked here -- `tests/test_schedule.py` holds the module itself to Windows.
# ---------------------------------------------------------------------------

def _task(at=u"03:00", enabled=True, **over):
    from hato import schedule
    values = dict(at=at, enabled=enabled, command=u"x", arguments=u"",
                  on_battery_ok=True, catches_up=True, daily=True, readable=True)
    values.update(over)
    return schedule.Task(**values)


@pytest.fixture
def daily(monkeypatch):
    u"""A Task Scheduler in memory: `live["task"]` is what `read()` finds."""
    from hato import schedule
    live = {u"task": None, u"calls": [], u"refuse": None, u"note": u""}

    def enable(at, argv=None, now=None):
        live[u"calls"].append((u"enable", at))
        if live[u"refuse"]:
            raise schedule.ScheduleError(live[u"refuse"])
        live[u"task"] = _task(at)
        return live[u"task"]

    def disable():
        live[u"calls"].append((u"disable",))
        had, live[u"task"] = live[u"task"], None
        return had is not None

    monkeypatch.setattr(schedule, u"supported", lambda: True)
    monkeypatch.setattr(schedule, u"read", lambda: live[u"task"])
    monkeypatch.setattr(schedule, u"enable", enable)
    monkeypatch.setattr(schedule, u"disable", disable)
    monkeypatch.setattr(schedule, u"note",
                        lambda task, argv=None: live[u"note"] if task else u"")
    return live


def test_the_daily_switch_is_READ_FROM_TASK_SCHEDULER_never_the_config(
        qapp, tmp_path, monkeypatch, daily):
    u"""🚨 THE REGRESSION: a config with a time in it -- every config -- read ON."""
    from hato import config as config_module
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "config.toml"))
    config_module.save(config_module.with_changes(config_module.load(),
                                                  schedule=u"05:30"))
    fresh = gui_app.settings_from_disk()
    assert fresh.schedule == u"05:30"
    assert fresh.auto is False, u"no task exists, and the switch reads ON"

    daily[u"task"] = _task(u"06:15")
    fresh = gui_app.settings_from_disk()
    assert fresh.auto is True
    assert fresh.schedule == u"06:15", u"the header must say when Windows REALLY runs it"


def test_the_switch_REGISTERS_and_REMOVES_the_task_and_never_sends_schedule_off(
        qapp, daily):
    window = make()
    window.state.auto = False
    window.render()
    window.auto_switch.click()
    assert daily[u"calls"] == [(u"enable", u"03:00")], daily[u"calls"]
    assert window.state.auto is True and window.auto_switch.isChecked()

    window.auto_switch.click()
    assert daily[u"calls"][-1] == (u"disable",)
    assert window.state.auto is False and not window.auto_switch.isChecked()
    # ⛔ `schedule=off` is the value the config refuses by name
    sent = [u" ".join(a) for a in window.spawned]
    assert not any(u"schedule=off" in s for s in sent), sent


def test_the_settings_switch_is_the_same_switch(qapp, daily):
    u"""⛔ Two controls for one fact: the Settings one must drive the task too."""
    window = make()
    window.state.auto = False
    window.show_tab(gui_app.TAB_SET)
    card = window.panes[gui_app.TAB_SET].findChildren(gui_app.Switch)
    assert card, u"no switch in Settings"
    card[0].click()
    assert daily[u"calls"] == [(u"enable", u"03:00")]


def test_a_task_off_in_task_scheduler_reads_OFF_with_the_fix_beside_it(qapp, daily):
    u"""⭐ A measured switch that reports two facts says which one is missing."""
    daily[u"task"] = _task(enabled=False)
    daily[u"note"] = (u"It is switched off in Task Scheduler — switching it on here "
                      u"turns it back on.")
    state = gui_app.read_schedule(gui_app.State())
    assert state.auto is False and u"Task Scheduler" in state.auto_note
    window = make(auto=state.auto, auto_note=state.auto_note)
    window.show_tab(gui_app.TAB_SET)
    shown = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"switched off in Task Scheduler" in shown
    assert u"switched off in Task Scheduler" in window.auto_switch.toolTip()


def test_a_REFUSAL_is_said_beside_the_switch_and_the_switch_reads_the_truth(qapp, daily):
    daily[u"refuse"] = (u"Task Scheduler would not add hato's daily run "
                        u"(Access is denied.).")
    window = make()
    window.state.auto = False
    window.render()
    window.auto_switch.click()
    assert window.state.auto is False, u"it says ON over a task that was refused"
    assert u"Access is denied" in window.state.schedule_said
    window.show_tab(gui_app.TAB_SET)
    assert u"Access is denied" in u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))


def test_a_new_time_is_GIVEN_TO_the_registered_task(qapp, daily):
    u"""🚨 Without it the header says 04:30 while Windows starts hato at 03:00."""
    daily[u"task"] = _task(u"03:00")
    window = make(auto=True)
    window.show_tab(gui_app.TAB_SET)
    window.time_field.setText(u"04:30")
    window._set_schedule()
    assert (u"enable", u"04:30") in daily[u"calls"]
    assert u"schedule=04:30" in u" ".join(window.spawned[0])
    assert window.state.schedule == u"04:30" and window.autotime.text() == u"04:30"


def test_a_new_time_with_the_daily_run_OFF_registers_nothing(qapp, daily):
    window = make(auto=False)
    window.show_tab(gui_app.TAB_SET)
    window.time_field.setText(u"04:30")
    window._set_schedule()
    assert daily[u"calls"] == []
    assert u"schedule=04:30" in u" ".join(window.spawned[0])


def test_a_time_the_config_would_refuse_is_refused_IN_WORDS_and_put_back(qapp, daily):
    u"""⛔ It used to go to `hato config --set`, be refused there, and nothing
    said so -- the field went on showing what was typed."""
    window = make(auto=True)
    window.show_tab(gui_app.TAB_SET)
    window.time_field.setText(u"3:00")
    window._set_schedule()
    assert window.spawned == [] and daily[u"calls"] == []
    assert u"is not a time" in window.state.schedule_said
    assert window.state.schedule == u"03:00"
    window.show_tab(gui_app.TAB_SET)
    assert window.time_field.text() == u"03:00"


def test_where_windows_cannot_schedule_the_switch_VANISHES_and_says_what_to_do(qapp):
    window = make(auto_supported=False)
    lay_out(window)
    for widget in (window.autolabel, window.autotime, window.auto_switch):
        assert not widget.isVisible(), u"a switch that can do nothing is drawn"
    window.show_tab(gui_app.TAB_SET)
    shown = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
    assert u"cron" in shown
    assert getattr(window, u"time_field", None) is None, \
        u"Settings draws a time for a run nothing can start"


def test_the_switch_ASKS_WINDOWS_rather_than_trusting_itself(qapp, daily):
    u"""⛔ The switch was drawn when the window opened; the task may have been
    made since -- by hand, or by another window. Flipping a stale switch must do
    what the person sees happen, and that is decided by what exists NOW."""
    window = make(auto=False)
    window.render()
    daily[u"task"] = _task(u"03:00")          # registered after the window drew
    window.auto_switch.click()
    assert daily[u"calls"] == [(u"disable",)], daily[u"calls"]
    assert window.state.auto is False


def test_with_the_daily_run_OFF_nothing_claims_a_retry_WILL_run(qapp):
    u"""The control arm of the one below: no tray, no daily run -- a retry only
    becomes due, and no sentence may promise a run."""
    window = make(auto=False, watching=False)
    window.show_tab(gui_app.TAB_PICK)
    shown = u" ".join(gui_app.texts(window.panes[gui_app.TAB_PICK]))
    assert u"retry after" in shown or u"retry due" in shown, shown[:400]
    assert u"retrying" not in shown


def test_with_the_daily_run_ON_every_sentence_about_who_retries_says_so(qapp):
    u"""⭐ D2 -- the tray was the only thing that ran hato on its own, and three
    sentences said so. Once the daily run is registered, each names it."""
    window = make(auto=True, watching=False)

    def flat(pane):
        # ⚠ `wrap()` breaks a tooltip onto lines wherever it likes
        return u" ".join(u" ".join(gui_app.texts(window.panes[pane])).split())
    window.show_tab(gui_app.TAB_PICK)
    picks = flat(gui_app.TAB_PICK)
    assert u"the daily run at 03:00 asks again" in picks
    # ⭐ EACH SENTENCE ON ITS OWN -- the row's wait and the strip's are separate
    # calls, and one that forgot the daily run would hide behind the other.
    pane = window.panes[gui_app.TAB_PICK]
    rows = [l.text() for l in pane.findChildren(QLabel) if u"tried" in l.text()]
    strips = [l.text() for l in pane.findChildren(QLabel)
              if l.text().startswith(u"— ") and u"retry" in l.text()]
    assert rows and strips, (rows, strips)
    assert all(u"retrying" in t for t in rows), rows
    assert all(u"retrying" in t for t in strips), strips
    window.show_tab(gui_app.TAB_SET)
    assert u"the daily one at 03:00" in flat(gui_app.TAB_SET)


def test_next_run_is_said_ONLY_while_a_daily_run_is_registered(qapp):
    u"""🚨 LOOKED, 2026-09-23: the D2 shot showed *"next run in 4 hours"* beside a
    switch that was OFF -- a fixture's literal in a field nothing real ever set.
    It is derived now, and only from a task that exists."""
    from datetime import timedelta
    two_ahead = (NOW8 + timedelta(hours=2)).astimezone().strftime(u"%H:%M")
    assert gui_run.next_run_text(two_ahead, NOW8) == u"next run in 2h"
    assert gui_run.next_run_text(None, NOW8) == u""
    for auto in (True, False):
        window = make(auto=auto, schedule=two_ahead)
        window.show_tab(gui_app.TAB_SET)
        shown = u" ".join(gui_app.texts(window.panes[gui_app.TAB_SET]))
        assert (u"next run in 2h" in shown) is auto, (auto, shown[:300])
        # ⚠ AND THE MINUTE TICK KEEPS IT TRUE -- asked of a window with nothing
        # else dated on it, or the rows' own retry dates would answer for it
        bare = make(rows=[], auto=auto)
        bare.state.waits, bare.state.remembered = {}, []
        assert bare._anything_dated() is auto, auto


def test_the_card_says_what_task_scheduler_HOLDS():
    u"""🚨 It said *"Windows wakes hato at that time"* over no task at all."""
    on = gui_run.daily_run_text(True, u"03:00", False)
    assert u"Windows starts hato at 03:00 every day" in on
    assert u"next on" in on, u"a run the computer sleeps through: when it happens instead"
    off = gui_run.daily_run_text(False, u"03:00", False)
    assert off.startswith(u"Off") and u"03:00" not in off
    assert u"tray" in gui_run.daily_run_text(False, u"03:00", True)


def test_with_the_daily_run_ON_a_retry_says_WHEN_even_without_the_tray():
    u"""⭐ The frozen rule -- say when it resolves. The daily run keeps a retry at
    the first run on or after its date. ⚠ Zone-proof: the daily time is derived
    from the date in THIS machine's zone, which is the zone Task Scheduler uses."""
    from datetime import timedelta
    due = NOW8 + timedelta(hours=14)
    row = {u"retry_after": due.isoformat()}
    two_after = (due + timedelta(hours=2)).astimezone().strftime(u"%H:%M")
    assert gui_run.retry_text(row, NOW8, False, two_after) == u"retrying in 16h"
    assert gui_run.retry_text(row, NOW8, True, two_after) == u"retrying in 14h"
    assert gui_run.retry_text(row, NOW8, False) == u"retry after 14h"
    # a date already passed waits for the next daily run
    past = {u"retry_after": (NOW8 - timedelta(hours=1)).isoformat()}
    three_ahead = (NOW8 + timedelta(hours=3)).astimezone().strftime(u"%H:%M")
    assert gui_run.retry_text(past, NOW8, False, three_ahead) == u"retrying in 3h"
    assert gui_run.retry_text(past, NOW8, False) == u"retry due"
    # ⚠ a date that falls EXACTLY on the daily time is that run's, not the next day's
    on_the_dot = due.astimezone().strftime(u"%H:%M")
    exact = {u"retry_after": due.replace(second=0, microsecond=0).isoformat()}
    assert gui_run.retry_text(exact, NOW8, False, on_the_dot) == u"retrying in 14h"


def test_the_WAIT_button_stops_saying_nothing_runs_it_once_the_daily_run_is_on(qapp):
    u"""⛔ A21's sentence -- *"nothing runs it on its own"* -- is false once the
    daily run is registered."""
    window = make(auto=True, watching=False)
    window.show_tab(gui_app.TAB_PICK)
    # ⚠ WHITESPACE COLLAPSED: `wrap()` broke the phrase across lines, and the
    # first version of this check -- looking for it whole -- let M8y-74 live.
    tips = [u" ".join(b.toolTip().split()) for b in window.findChildren(QPushButton)
            if b.text() == u"Wait for it"]
    assert tips, u"the fixture shows no Wait button, so this proves nothing"
    assert not any(u"nothing runs it on its own" in t for t in tips), tips


# ===========================================================================
# ⭐ 9a -- the person's format, RULED 2026-09-23
# ===========================================================================
# *"i want setting that asks for preference between the two, but OFF by default
# is download if the other type doesn't exist."* And the frozen rule: a decision
# made on the person's behalf needs a surface -- here, that the episode IS on
# jimaku, in the other format, one click from taking it.

def only_other(episode=12, video=None, kind=u"srt", prefer=u"ass", files=False):
    u"""What `hato problems` says about an episode waiting for its format -- the
    DB's own reason, which `formats.waiting_reason` wrote and `only_as` reads
    back (the WIRE's shape, never a convenient one: LEDGER-HOT). `kind` one
    format or several."""
    from hato import formats
    row = remembered(episode, files=files, video=video)
    kinds = [kind] if isinstance(kind, str) else list(kind)
    row[u"reason"] = formats.waiting_reason(kinds, prefer, 3)
    # ⚠ NOT_FOUND even with files tried before it: `problems._outcome`'s 9a rule,
    # the wire as `hato problems` now sends it (ADVERSARY 2026-09-23 #5).
    row[u"outcome"] = u"NOT_FOUND"
    return row


def _box_beside(pane, words):
    u"""The painted Check whose own row says `words`."""
    for box in pane.findChildren(gui_app.Check):
        if any(words in l.text() for l in box.parent().findChildren(QLabel)):
            return box
    return None


def _flat(pane):
    return u" ".join(u" ".join(gui_app.texts(pane)).split())


def test_the_format_card_shows_the_preference_and_the_fallback_OFF(qapp):
    u"""The defaults, ruled: `.ass`, and the other kind never."""
    window = make()
    window.show_tab(gui_app.TAB_SET)
    pane = window.panes[gui_app.TAB_SET]
    said = _flat(pane)
    assert u"SUBTITLE FORMAT" in said
    assert u"If there is no .ass, download .srt" in said and u"off: waits for .ass" in said
    radios = pane.findChildren(gui_app.Radio)
    assert [r.isChecked() for r in radios] == [True, False], u"the .ass radio is not the chosen one"
    box = _box_beside(pane, u"If there is no .ass")
    assert box is not None and not box.isChecked()


def test_choosing_srt_saves_it_and_the_fallback_names_the_other_way_round(qapp):
    window = make(running=False)
    window.show_tab(gui_app.TAB_SET)
    window.panes[gui_app.TAB_SET].findChildren(gui_app.Radio)[1].click()
    assert window.state.prefer_format == u"srt"
    sent = [u" ".join(a) for a in window.spawned]
    assert any(u"prefer_format=srt" in s for s in sent), sent
    assert u"If there is no .srt, download .ass" in _flat(window.panes[gui_app.TAB_SET])
    # ⚠ The chosen one again changes nothing, and sends nothing.
    before = len(window.spawned)
    window.panes[gui_app.TAB_SET].findChildren(gui_app.Radio)[1].click()
    assert len(window.spawned) == before


def test_the_fallback_box_saves_true_and_then_false(qapp):
    window = make(running=False)
    window.show_tab(gui_app.TAB_SET)
    _box_beside(window.panes[gui_app.TAB_SET], u"If there is no .ass").click()
    assert window.state.format_fallback is True
    _box_beside(window.panes[gui_app.TAB_SET], u"If there is no .ass").click()
    assert window.state.format_fallback is False
    sent = [u" ".join(a) for a in window.spawned]
    assert [s for s in sent if u"format_fallback=" in s] == [
        s for s in sent if u"format_fallback=true" in s or u"format_fallback=false" in s]
    assert u"format_fallback=true" in sent[0] and u"format_fallback=false" in sent[1], sent


def test_an_episode_only_in_the_other_format_is_never_said_not_to_be_on_jimaku(qapp, tmp_path):
    u"""⛔ *"not on jimaku yet"* would be false of it: it IS there, as .srt. Two
    arms -- and the control, an episode jimaku really lacks, still says it."""
    window = remembering([], [only_other(video=_on_disk(tmp_path, u"ep12.mkv"))])
    window.show_tab(gui_app.TAB_PICK)
    said = _flat(window.panes[gui_app.TAB_PICK])
    assert u"only on jimaku as .srt" in said and u"you prefer .ass" in said, said
    assert u"not on jimaku yet" not in said and u"Nothing needs you" not in said, said
    # ⭐ SAY WHEN IT RESOLVES -- LOOKED, 2026-09-23: the first shot of this line
    # said everything but when hato looks again, where its neighbour did.
    assert u"retry after" in said or u"retrying in" in said, said
    assert buttons_called(window, u"Download .srt instead")

    plain = remembering([], [remembered(files=False, video=_on_disk(tmp_path, u"ep13.mkv"))])
    plain.show_tab(gui_app.TAB_PICK)
    said = _flat(plain.panes[gui_app.TAB_PICK])
    assert u"not on jimaku yet" in said and u"only on jimaku" not in said, said


def test_download_instead_turns_the_fallback_on_and_looks_now(qapp, monkeypatch, tmp_path):
    u"""⭐ ONE CLICK AWAY, and it IS the setting: the same checkbox Settings shows,
    then a look-again, so it happens in seconds and not at the next run.

    🚨 AND THE LOOK WAITS FOR THE WRITE (ADVERSARY 2026-09-23 #11): a run reads
    config.toml as it starts. Three arms -- nothing runs while the write is in
    flight; a write that exits 0 starts the look; one that failed starts nothing
    and puts the checkbox back."""
    started = {}
    monkeypatch.setattr(gui_run, u"Runner",
                        lambda **kw: started.update(argv=kw.get(u"argv")) or _NullRunner())
    video = _on_disk(tmp_path, u"ep12.mkv")
    window = remembering([], [only_other(video=video)])
    waiting = []
    window._read = lambda argv, done: waiting.append((argv, done)) or u"in flight"
    window.show_tab(gui_app.TAB_PICK)
    buttons_called(window, u"Download .srt instead")[0].click()
    assert window.state.format_fallback is True
    (argv, done), = waiting
    assert u"format_fallback=true" in u" ".join(argv), argv
    assert not started, u"the look-again started before config.toml was written: %r" % started

    done(gui_run.Run(0, [], {}, [], u""), [])                            # written
    argv = started.get(u"argv") or []
    assert u"--retry-now" in argv and argv[argv.index(u"--only") + 1] == os.path.abspath(video)

    started.clear()
    del waiting[:]
    window = remembering([], [only_other(video=video)])
    window._read = lambda argv, done: waiting.append((argv, done)) or u"in flight"
    window.show_tab(gui_app.TAB_PICK)
    buttons_called(window, u"Download .srt instead")[0].click()
    assert window.state.format_fallback is True, u"the control: the click ticked it"
    (_argv, done), = waiting
    assert done(gui_run.Run(1, [], {}, [u"hato: no"], u""), []) is None   # refused
    assert not started, u"a write that FAILED still looked again: %r" % started
    assert window.state.format_fallback is False, u"the box still says what was never saved"
    assert u"could not be saved" in window.state.live, window.state.live


def test_once_the_settings_take_that_format_the_line_says_so(qapp, tmp_path):
    u"""⚠ The wait ends at the next run once the fallback is on (the gate looks
    past it). Saying *"you prefer .ass"* then would be yesterday's reason -- and
    ⛔ not *"now"* either: LOOKED, *"your settings take it now"* read as a fetch
    already happening."""
    window = remembering([], [only_other(video=_on_disk(tmp_path, u"ep12.mkv"))],
                         format_fallback=True)
    window.show_tab(gui_app.TAB_PICK)
    said = _flat(window.panes[gui_app.TAB_PICK])
    assert u"allowed by your settings now" in said and u"you prefer" not in said, said
    # ⭐ WHEN, truly: the gate looks past this wait at the NEXT run -- ⛔ not the
    # retry date the row still carries, which it no longer waits for.
    assert u"fetched at hato's next run" in said, said
    assert u"retry after" not in said and u"retrying in" not in said, said
    assert buttons_called(window, u"Look again now")
    assert not buttons_called(window, u"Download .srt instead")


def _long_waits(tmp_path):
    u"""Four of each waiting line, with real long titles from Sonic's library."""
    other = [dict(only_other(n, video=_on_disk(tmp_path, u"s%02d.mkv" % n)),
                  title=u"Tensei shitara Slime Datta Ken", season=4) for n in (93, 94, 95, 96)]
    missing = [dict(remembered(n, files=False, video=_on_disk(tmp_path, u"i%02d.mkv" % n)),
                    title=u"Mairimashita! Iruma-kun", season=4) for n in (21, 22, 23, 24)]
    return other + missing


def test_a_long_list_of_names_never_pushes_a_strips_button_off_the_window(qapp, tmp_path):
    u"""🚨 LOOKED, 2026-09-23: four real titles ran the new line past the window --
    its button cut at the edge, its info dot gone -- and the older *"not on jimaku
    yet"* line was one title from the same. Both are `Flowing` now. Measured at a
    narrow width, where both must wrap."""
    window = remembering([], _long_waits(tmp_path))
    window.show_tab(gui_app.TAB_PICK)
    # ⚠ 900 px: narrow enough that the ~1,900 px list MUST wrap, with room for a
    # wider font's lead and button than this machine's (CI runs Linux and macOS).
    lay_out(window, width=900)
    for text in (u"Download .srt instead", u"Look again now"):
        button, = buttons_called(window, text)
        right = button.mapTo(window, button.rect().topRight()).x()
        assert 0 < right <= window.width(), (text, right, window.width())


def test_a_long_list_of_names_flows_across_the_room_it_has(qapp, tmp_path):
    u"""⚠ AND NOT A NARROW COLUMN -- LOOKED, the same hour: a plain wrapped QLabel
    is sized to a heuristic ~80-character column, and four names became five lines
    beside a screen of empty space. Given room for the whole list, the list is
    ONE line.

    ⚠ MEASURED IN A WINDOW WIDE ENOUGH FOR THE SUITE'S FONT. Offscreen, the
    fallback font draws this text 1,936 px wide where the real one is ~1,200 --
    a line COUNT at the ordinary width measured the font, not the layout (it read
    4.4 lines where the real window shows 2)."""
    window = remembering([], _long_waits(tmp_path))
    window.show_tab(gui_app.TAB_PICK)
    # ⚠ 5,000 px, not "wide enough here": CI's Linux and macOS jobs lay this out
    # in fonts wider than Windows' offscreen fallback, which already needs 1,936.
    lay_out(window, width=5000)
    flowing = [w for w in window.panes[gui_app.TAB_PICK].findChildren(gui_app.Flowing)
               if u"Slime" in w.text()]
    assert flowing, u"the strip's list is not a Flowing label"
    label_ = flowing[0]
    margins = label_.contentsMargins()
    lines = ((label_.height() - margins.top() - margins.bottom())
             / float(label_.fontMetrics().lineSpacing()))
    assert lines < 1.5, (u"with room for all of it, the list took %.1f lines "
                         u"(%d px wide of a %d px window)"
                         % (lines, label_.width(), window.width()))


def test_the_format_settings_are_read_back_when_the_window_opens(qapp, tmp_path, monkeypatch):
    u"""⛔ The window READS its settings on open (`settings_from_disk`) -- the round
    trip nobody wrote once before (Sonic, 2026-09-18: *"i don't think my settings
    are being saved"*). Both new ones, from a real file."""
    config = tmp_path / u"config.toml"
    config.write_text(u"prefer_format = 'srt'\nformat_fallback = true\n", encoding="utf-8")
    monkeypatch.setenv(u"HATO_CONFIG", str(config))
    state = gui_app.settings_from_disk()
    assert (state.prefer_format, state.format_fallback) == (u"srt", True)


def test_an_older_tray_is_told_it_cannot_read_a_changed_format_setting(qapp):
    u"""🚨 `config.NEWER_THAN_1_0_2`: an older hato refuses a key it has never heard
    of, so once the format settings leave their defaults every run an old tray
    starts stops at config.toml. Two arms: changed -> said, with the fix;
    untouched -> nothing, because the file is still one it can read."""
    window = make(old_tray=True, prefer_format=u"srt")
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" in _flat(window.panes[gui_app.TAB_SET])
    window = make(old_tray=True)
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" not in _flat(window.panes[gui_app.TAB_SET])


# ---------------------------------------------------------------------------
# ⭐ 9a's adversarial pass, 2026-09-23 -- `ADVERSARY-2026-09-23.md`
# ---------------------------------------------------------------------------

def _tray_says(capabilities):
    u"""A REAL pid file in the suite's HATO_CACHE, for THIS live process -- the
    line a tray writes, `<pid> <stamp> <capabilities>` -- never a flag set on the
    state (the check that let #1 through injected `old_tray=True`)."""
    from hato import runlock
    from hato import watch as _watch
    _watch.pid_file_path().parent.mkdir(parents=True, exist_ok=True)
    stamp = runlock._process_start(os.getpid())
    _watch.pid_file_path().write_text(
        (u"%d %s %s" % (os.getpid(), stamp or u"-", capabilities)).strip(), encoding="utf-8")


def test_a_1_0_2_tray_is_told_it_cannot_read_a_changed_format_setting(
        qapp, tmp_path, monkeypatch):
    u"""🚨 #1 -- 1.0.2 already writes `retries`, so it was taken for this build:
    no note, while every run it started died on `prefer_format`. The second user,
    who asked for `.srt`, is on 1.0.2. Two arms through the window's own poll:
    1.0.2's exact line -> said, with the fix; this build's line -> nothing."""
    monkeypatch.setenv(u"HATO_CACHE", str(tmp_path))
    for line, said in ((u"retries", True), (u"retries,formats", False)):
        _tray_says(line)
        window = make(running=False, prefer_format=u"srt")
        timer = window.follow_other_runs(every_ms=3600000)
        timer.stop()
        timer.timeout.emit()
        assert window.state.old_tray is False, u"1.0.2 keeps retries -- it is not V1's tray"
        assert window.state.tray_reads_formats is (not said), (line, window.state.tray_reads_formats)
        window.show_tab(gui_app.TAB_SET)
        text = _flat(window.panes[gui_app.TAB_SET])
        assert (u"cannot read this setting" in text) is said, (line, text)
        if said:
            assert buttons_called(window, u"Restart the tray"), u"said, but not the fix"


def test_a_format_key_in_the_file_is_said_even_at_its_default(qapp):
    u"""🚨 #1 -- an older hato refuses the KEY, whatever its value: a hand-written
    `prefer_format = 'ass'` stopped 1.0.2's runs as surely as `'srt'`, and the note
    keyed on the VALUE. Two arms: the key in the file -> said; not -> nothing."""
    for in_file in (True, False):
        window = make(tray_reads_formats=False, format_keys_in_file=in_file)
        window.show_tab(gui_app.TAB_SET)
        assert (u"cannot read this setting" in _flat(window.panes[gui_app.TAB_SET])) is in_file


def test_restarting_the_tray_takes_the_format_note_away_at_once(qapp, monkeypatch):
    u"""After *Restart the tray* the tray is this build's, so the note goes now --
    not at the next look. ⛔ Both halves faked, as V1's check does: a real stop
    would signal whatever pid the file names."""
    window = make(running=False, tray_reads_formats=False, prefer_format=u"srt")
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" in _flat(window.panes[gui_app.TAB_SET]), u"the control"
    calls = []
    monkeypatch.setattr(window, u"stop_watcher", lambda: calls.append(u"stop"))
    monkeypatch.setattr(window, u"start_watcher", lambda: calls.append(u"start"))
    restart, = buttons_called(window, u"Restart the tray")
    restart.click()
    assert calls == [u"stop", u"start"]
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" not in _flat(window.panes[gui_app.TAB_SET])


def test_going_back_to_the_defaults_in_the_window_takes_the_format_note_away(qapp):
    u"""The window's writer keeps the format keys in config.toml only away from
    their defaults (`config.dumps`), so once it has rewritten the file the VALUES
    say what is in it: a key the file held when the window opened must not keep
    the note up after the person set both back. Both roads -- the radio, the box."""
    window = make(running=False, tray_reads_formats=False, format_keys_in_file=True,
                  prefer_format=u"srt")
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" in _flat(window.panes[gui_app.TAB_SET]), u"the control"
    window.panes[gui_app.TAB_SET].findChildren(gui_app.Radio)[0].click()     # back to .ass
    window.show_tab(gui_app.TAB_SET)
    assert u"cannot read this setting" not in _flat(window.panes[gui_app.TAB_SET])

    window = make(running=False, tray_reads_formats=False, format_keys_in_file=True)
    for _on_then_off in range(2):
        window.show_tab(gui_app.TAB_SET)
        _box_beside(window.panes[gui_app.TAB_SET], u"If there is no .ass").click()
    window.show_tab(gui_app.TAB_SET)
    assert window.state.format_fallback is False
    assert u"cannot read this setting" not in _flat(window.panes[gui_app.TAB_SET])


def test_whether_the_file_carries_a_format_key_is_read_back_on_open(qapp, tmp_path, monkeypatch):
    u"""The round trip behind the note above: a real file, both arms."""
    config = tmp_path / u"config.toml"
    monkeypatch.setenv(u"HATO_CONFIG", str(config))
    for text, carries in ((u"prefer_format = 'ass'\n", True), (u"recurse = true\n", False)):
        config.write_text(text, encoding="utf-8")
        assert gui_app.settings_from_disk().format_keys_in_file is carries, text


def _quiet_tips(window):
    u"""{a quiet line's lead: its info dot's tooltip}, as PAINTED on the Subtitles
    tab -- whitespace collapsed (a wrapped tooltip hides the phrase)."""
    out = {}
    for strip in window.panes[gui_app.TAB_SUBS].findChildren(gui_app.Styled):
        leads = [w.text() for w in strip.findChildren(QLabel) if w.text()]
        tips = [w.toolTip() for w in strip.findChildren(QWidget) if w.toolTip()]
        if leads and tips:
            out[leads[0]] = u" ".join(tips[0].split())
    return out


def test_a_quiet_wait_never_claims_a_download_that_did_not_happen(qapp):
    u"""🚨 #8 -- *"waiting to retry"* carried one tooltip for every wait: *"hato
    downloaded subtitles for this and none of them lined up"* -- over a FORMAT
    wait, where nothing was downloaded. Three rows, three shows, each line's own
    tooltip: the format wait says the format; the row with tried files (the
    control) keeps the old sentence; a row with none claims nothing."""
    from hato import formats
    files = [{u"name": u"[G] Show - 04 [JPN].ass", u"outcome": u"REFUSED",
              u"reason": u"the timing did not hold", u"bytes": 1000, u"match_rate": 0.4,
              u"path": u"C:\\hato\\cache\\a.ja.ass", u"when": u"2026-09-21T00:00:00+00:00"}]
    rows = [dict(retrying(4, title=u"Format Show"),
                 reason=formats.waiting_reason([u"srt"], u"ass", 3)),
            dict(retrying(5, title=u"Tried Show"), tried_before=files),
            dict(retrying(6, title=u"Bare Show"),
                 reason=u"jimaku entry 1 has no file for this episode")]
    window = make(rows=rows)
    window.show_tab(gui_app.TAB_SUBS)
    tips = _quiet_tips(window)
    by_show = dict((show, [t for lead, t in tips.items() if lead.startswith(show)])
                   for show in (u"Format Show", u"Tried Show", u"Bare Show"))
    assert all(len(t) == 1 for t in by_show.values()), tips
    fmt, tried_tip, bare = (by_show[s][0] for s in (u"Format Show", u"Tried Show", u"Bare Show"))
    downloaded = u"downloaded subtitles for this"
    assert u"only in a format your settings do not take" in fmt and downloaded not in fmt, fmt
    assert downloaded in tried_tip, u"the control: %r" % tried_tip
    assert downloaded not in bare and u"Needs you says why" in bare, bare


def test_a_format_wait_with_files_tried_before_it_is_still_the_format_line(qapp, tmp_path):
    u"""🚨 #5 in the window -- with files refused in an earlier run it was painted
    as a pick (*"2 tried · best 70%"*), never the format or its button."""
    window = remembering([], [only_other(video=_on_disk(tmp_path, u"ep12.mkv"), files=True)])
    window.show_tab(gui_app.TAB_PICK)
    said = _flat(window.panes[gui_app.TAB_PICK])
    assert u"only on jimaku as .srt" in said and buttons_called(window, u"Download .srt instead")
    assert u"tried · best" not in said and u"Click one to use it" not in said, said


def test_a_blocked_and_a_taken_format_wait_are_two_lines_never_one(qapp, tmp_path):
    u"""🚨 #9 -- `.srt` preferred, one episode waiting as `.ass` (blocked) and one
    recorded as `.srt`-only before the switch (taken now). One line said the
    blocked sentence of both -- *"you prefer .srt"* over an episode that IS
    `.srt` -- and its button offered *Download .ass or .srt instead*."""
    rows = [only_other(12, video=_on_disk(tmp_path, u"ep12.mkv"), kind=u"ass", prefer=u"srt"),
            only_other(13, video=_on_disk(tmp_path, u"ep13.mkv"), kind=u"srt", prefer=u"ass")]
    window = remembering([], rows, prefer_format=u"srt")
    window.show_tab(gui_app.TAB_PICK)
    said = _flat(window.panes[gui_app.TAB_PICK])
    assert u"1 episode is only on jimaku as .ass" in said, said
    assert u"1 episode is on jimaku as .srt" in said and u"allowed by your settings now" in said, said
    assert buttons_called(window, u"Download .ass instead")
    offered = [b.text() for b in window.findChildren(QPushButton) if b.text().startswith(u"Download")]
    assert offered == [u"Download .ass instead"], (u"a button offered the chosen kind", offered)
    tip = u" ".join(buttons_called(window, u"Download .ass instead")[0].toolTip().split())
    assert u"download .ass or another format" in tip, (u"#9b: the words under-describe it", tip)

# ===========================================================================
# ⭐ LAYER 13 -- nothing flashes, nothing glitches (RUNBOOK 13a/13b)
# ===========================================================================

class _ShownAsWindow(QObject):
    u"""Every widget SHOWN as a window of its own, other than `window`."""

    def __init__(self, window):
        super().__init__()
        self.window, self.seen = window, []

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Show and isinstance(obj, QWidget)
                and obj.isWindow() and obj is not self.window):
            self.seen.append((type(obj).__name__, obj.width(), obj.height()))
        return False


def test_a_widget_cleared_before_its_queued_show_never_becomes_a_window(qapp):
    u"""🚨 13a: a widget added to a VISIBLE layout is shown LATER -- Qt queues the show.
    Detached by `clear()` before that ran, the queued show made it a WINDOW of its own:
    Sonic's *"bunch of flashing windows"* while updating to 1.0.5 (~50 measured on the
    published 1.0.4, the window's own process)."""
    host = QWidget()
    box = QVBoxLayout(host)
    host.show()
    qapp.processEvents()
    watch = _ShownAsWindow(host)
    qapp.installEventFilter(watch)
    try:
        box.addWidget(QLabel(u"a card", host))           # its show is QUEUED
        gui_app.clear(box)                               # ... and it is detached first
        qapp.processEvents()
        assert watch.seen == [], u"a cleared widget was shown as a window: %s" % watch.seen
        box.addWidget(QLabel(u"the control", host))
        qapp.processEvents()
        assert box.itemAt(0).widget().isVisible(), u"the control: a widget kept is shown"
    finally:
        qapp.removeEventFilter(watch)
        host.hide()


def test_two_renders_in_one_turn_never_show_the_no_key_card_as_a_window(qapp):
    u"""🚨 13a, the way it happened: a pane rebuilt twice before the event loop turned --
    the no-key card (what the published 1.0.4 showed, keyless) flashed as a window of
    its own, ~50 times in one download."""
    window = make(rows=[])
    window.state.key_hint = u""
    window.show()
    qapp.processEvents()
    watch = _ShownAsWindow(window)
    qapp.installEventFilter(watch)
    try:
        for _ in range(5):
            window.render()
            window.render()                             # twice, in one turn
            qapp.processEvents()
        assert watch.seen == [], u"a rebuilt pane showed windows: %s" % watch.seen[:5]
        texts = u" ".join(l.text() for l in window.findChildren(QLabel))
        assert u"No jimaku key yet" in texts, u"the control: the no-key card is the pane"
    finally:
        qapp.removeEventFilter(watch)
        window.hide()


def test_two_renders_in_one_turn_with_rows_on_screen_never_crash_the_window():
    u"""🚨 13a's worst half: with ROWS on screen (each `SubRow` carries a graphics effect)
    the same race SEGFAULTED the window -- 3 of 3, offscreen and on the real platform.
    ⭐ IN A PROCESS OF ITS OWN (`_double_render.py`): a crash here would otherwise take
    every later check of this suite down with it, and the harness could not tell a
    crash from a pass for the wrong reason (M13-03 was first caught that way)."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    # ⭐ `-X faulthandler`: a crash says WHERE, in the message below
    child = subprocess.run([sys.executable, u"-X", u"faulthandler",
                            os.path.join(here, u"_double_render.py")],
                           capture_output=True, timeout=180)
    said = (child.stdout + child.stderr).decode(u"utf-8", u"replace").strip()
    assert child.returncode == 0, (
        u"the window CRASHED (exit %d, 0x%08X)" % (child.returncode,
                                                   child.returncode & 0xFFFFFFFF)
        if child.returncode not in (0, 1) else u"widgets were shown as windows"
    ) + u" -- %s" % said[-400:]
    assert u"rows on screen: 0;" not in said, u"the control: no rows were on screen -- %s" % said


def test_a_runs_ticks_leave_settings_standing_and_its_end_rebuilds_it(qapp):
    u"""🚨 13b -- Sonic's screenshot, 2026-09-25: Settings during a manual run, every card
    collapsed and its title cut through. `_drain` rendered at every tick and Settings was
    torn down and rebuilt eight times a second, caught half laid out. ⚠ The ticks here
    bring NEWS -- rows, as the run's end streams them -- because since 13c a tick of
    progress alone renders nothing at all (the gate showed this check stopped reaching
    the live render when its ticks carried progress only: M13-07). A tick with news
    leaves Settings standing; the run's end rebuilds it."""
    window = make(running=True)
    window.show_tab(gui_app.TAB_SET)
    card = window._ucard
    for n in range(5):
        window._runner = _EventRunner([{u"type": u"progress", u"name": u"show %d" % n},
                                       added(20 + n)])
        window._drain()
        assert window._ucard is card, u"a run's tick with news rebuilt Settings"
    episodes = set(r.get(u"episode") for r in window.state.rows)
    assert episodes >= set(range(20, 25)), u"the control: the ticks brought their rows"
    assert u"show 4" in window.live_label.text(), u"the control: the footer moved"
    window._runner = _FinishedRunner(0)
    window._drain()
    assert window._ucard is not card, u"the run's end did not rebuild Settings"


@pytest.mark.parametrize("tab", [gui_app.TAB_SUBS, gui_app.TAB_PICK])
def test_a_runs_progress_ticks_rebuild_no_pane_and_move_the_footer(qapp, tab):
    u"""🚨 RUNBOOK 13c: mid-run the stream is ONLY progress lines -- the rows arrive at
    the end -- and every tick rebuilt the pane in front: 0.9-2.2 s each at 64 subtitled
    rows, a window frozen for the length of the run (measured, the performance scope)."""
    window = make(running=True)
    window.show_tab(tab)
    kind = gui_app.SubRow if tab == gui_app.TAB_SUBS else gui_app.PickHead
    standing = window.findChildren(kind)[0]
    for n in range(5):
        window._runner = _EventRunner([{u"type": u"progress", u"name": u"show %d" % n}])
        window._drain()
        assert window.findChildren(kind)[0] is standing, u"a progress tick rebuilt the pane"
    window._runner = _EventRunner([])
    window._drain()                                      # a tick with nothing at all
    assert window.findChildren(kind)[0] is standing, u"an empty tick rebuilt the pane"
    assert u"show 4" in window.live_label.text(), u"the footer did not move"
    window._runner = _EventRunner([added(9)])            # NEWS: a row
    window._drain()
    assert window.findChildren(kind)[0] is not standing, u"the control: a row rebuilds"


class _LateLinesRunner(object):
    u"""A run whose last lines are queued only after `finished()` joined its readers --
    the gap `_drain` never read (RUNBOOK 13d)."""

    def __init__(self, late):
        self.late, self.joined = list(late), False

    def drain(self):
        if not self.joined:
            return []
        out, self.late = self.late, []
        return out

    def finished(self):
        self.joined = True
        return gui_run.Run(0, [], {u"api_calls": 0}, [], u"")


def test_a_runs_last_lines_are_read_after_it_finishes(qapp):
    u"""🚨 RUNBOOK 13d: `finished()` joins the reader threads, and what they queued after
    the tick's drain was never read -- 40 rows written, 14 shown (1 of 3, measured); a
    lost `busy` read as "done" and stamped *last run* over a run that scanned nothing."""
    window = make(rows=[], running=True)
    stamped = window.state.last_run
    window._runner = _LateLinesRunner([added(41), {u"type": u"busy"}])
    window._drain()
    assert [r.get(u"episode") for r in window.state.rows] == [41], u"the last row was lost"
    assert u"already running" in window.state.live, window.state.live
    assert window.state.last_run == stamped, u"a run that scanned nothing was stamped"


def test_the_trays_countdown_moves_the_footer_and_rebuilds_nothing(qapp, monkeypatch):
    u"""🚨 RUNBOOK 13g: the tray's countdown changed at every 3-second look, and every
    look rebuilt the pane in front -- ~20 times an arrival, when only the footer's
    words move. Its start and its end still render in full."""
    queue = [(0.0, []), (45.0, [u"a.mkv"]), (42.0, [u"a.mkv"]), (39.0, [u"a.mkv"]),
             (59.0, [u"a.mkv", u"b.mkv"]), (0.0, [])]
    monkeypatch.setattr(gui_run, "pending_run", lambda: queue[0])
    window = make(running=False)                          # the footer counts only while idle
    window._anything_dated = lambda: False                # no minute may render here
    window.follow_other_runs(every_ms=60000)
    window._others_timer.stop()
    look = window._others_timer.timeout
    look.emit()
    queue.pop(0)
    look.emit()                                          # 0 -> 45: it STARTS
    standing = window.findChildren(gui_app.SubRow)[0]
    footer = window.live_label.text()
    for _ in range(2):
        queue.pop(0)
        look.emit()                                      # 45 -> 42 -> 39: it MOVES
        assert window.findChildren(gui_app.SubRow)[0] is standing, u"a tick rebuilt the pane"
    assert window.live_label.text() != footer, u"the footer's countdown stood still"
    queue.pop(0)
    look.emit()                                          # 39 -> 59: it RESTARTS
    # ⭐ The Layer 13 pass (Z13-8) -- a second arrival restarts it, and the footer says
    # so at once: a mutant moving the footer only as the count FELL survived (Z-G1)
    said = window.live_label.text()
    assert u"2 new videos" in said and u"59s" in said, u"the restart went unsaid: %r" % said
    assert window.findChildren(gui_app.SubRow)[0] is standing, u"a restart rebuilt the pane"
    queue.pop(0)
    look.emit()                                          # 59 -> 0: it ENDS
    assert window.findChildren(gui_app.SubRow)[0] is not standing, u"the control: its end"


def test_answers_only_settings_shows_rebuild_nothing_elsewhere(qapp):
    u"""RUNBOOK 13h: hato's memory and its blacklist are shown only in Settings, and
    their answers rebuilt the pane in front anyway -- at every start and every run's
    end. The switch to Settings renders in full."""
    window = make()
    standing = window.findChildren(gui_app.SubRow)[0]
    window._memory_read(None, [MEMORY])
    window._blacklist_read(None, [{u"blacklist": []}])
    assert window.findChildren(gui_app.SubRow)[0] is standing, u"it rebuilt Subtitles"
    assert window.state.memory == MEMORY, u"the answer was not taken"
    window.show_tab(gui_app.TAB_SET)
    card = window._ucard
    window._memory_read(None, [MEMORY])
    assert window._ucard is not card, u"the control: on Settings the answer renders"
    card = window._ucard
    window._blacklist_read(None, [{u"blacklist": []}])
    assert window._ucard is not card, u"the control: ... and the blacklist's"


def test_the_window_starts_with_one_render_not_two(tmp_path):
    u"""RUNBOOK 13h: `check_updates` renders, and `main()` rendered again straight after
    -- every pane-in-front built twice before the window was ever shown.

    ⭐ The Layer 13 pass (Z13-7): the check read `main()`'s TEXT. The double build put
    back through `show_tab`, or the render taken out of `check_updates` -- which
    `main()` now relies on to paint -- both stayed green. `main()` itself now runs,
    in a process of its own (`_start_window.py`), up to the moment it shows the
    window: ONE render, a window that says the folders it loaded, and nothing
    imported on the way that talks to the network (13i's 139 ms, whichever module
    brings it back)."""
    import json
    import subprocess
    folders = [tmp_path / u"Anime A", tmp_path / u"Anime B"]
    for folder in folders:
        folder.mkdir()
    config = tmp_path / u"config.toml"
    config.write_text(u"folders = [%s]" % u", ".join(u"'%s'" % f for f in folders),
                      encoding=u"utf-8")
    child = subprocess.run([sys.executable, u"-X", u"faulthandler",
                            os.path.join(HERE, u"_start_window.py")],
                           capture_output=True, timeout=180,
                           env=dict(os.environ, HATO_CONFIG=str(config)))
    out = child.stdout.decode(u"utf-8", u"replace").strip()
    assert child.returncode == 0, (child.returncode, out[-300:],
                                   child.stderr.decode(u"utf-8", u"replace")[-600:])
    seen = json.loads(out.splitlines()[-1])
    assert seen[u"titlesub"].startswith(u"2 folders"), (
        u"the window was shown before anything painted what it loaded: %r" % seen[u"titlesub"])
    assert seen[u"renders"] == 1, u"main() rendered %d times before showing" % seen[u"renders"]
    assert seen[u"net"] == [], u"the window's start imported %s" % seen[u"net"]


def test_a_mark_repolishes_only_a_polished_widget(qapp, monkeypatch):
    u"""RUNBOOK 13f: a widget not yet polished takes the property, and Qt applies it at
    its first polish -- repolishing it was 516 unpolish/polish pairs per Subtitles build
    at 64 rows. A polished widget is repolished exactly as before."""
    polished = []
    monkeypatch.setattr(gui_app, "repolish", lambda widget: polished.append(widget))
    fresh = QLabel(u"a cell")
    gui_app.mark(fresh, u"tier", u"ok")
    assert polished == [] and fresh.property(u"tier") == u"ok"
    fresh.ensurePolished()
    gui_app.mark(fresh, u"tier", u"look")
    assert polished == [fresh], u"a polished widget was not repolished"
    gui_app.mark(fresh, u"tier", u"look")
    assert polished == [fresh, fresh], u"a repeated value on a live widget was skipped"


def test_the_schedule_module_pulls_in_no_network_library():
    u"""RUNBOOK 13i: one `escape` from `xml.sax.saxutils` imported `urllib.request` and
    `http.client` -- 139 ms on every window start, before it shows. Asked of a fresh
    interpreter: this one has imported everything already."""
    import subprocess
    child = subprocess.run([sys.executable, u"-c",
                            u"import sys, hato.schedule; "
                            u"print(sorted(m for m in ('urllib.request', 'http.client') "
                            u"if m in sys.modules))"],
                           capture_output=True, timeout=120)
    said = child.stdout.decode(u"utf-8", u"replace").strip()
    assert child.returncode == 0 and said == u"[]", (said, child.stderr[-300:])


@pytest.mark.parametrize("text", [u"a & <b> > c", u"&amp;", u"C:\\ツール置き場\\hato-watch.exe",
                                  u"", u"&&<<>>", u"'quotes' \"too\""])
def test_the_schedules_escape_is_xmls(text):
    u"""RUNBOOK 13i: its own three replacements -- `&` first -- exactly what
    `xml.sax.saxutils.escape` does, on the paths a person's folder can hold."""
    from xml.sax.saxutils import escape
    from hato import schedule
    assert schedule.escape(text) == escape(text)

def _bl_rows(window):
    return [w for w in window.findChildren(gui_app.Styled) if w.objectName() == u"blrow"]


def test_the_blacklist_filter_filters_and_a_rebuild_keeps_it(qapp):
    u"""RUNBOOK 13j -- *"Filter by name or show…"* was built and connected to nothing:
    typing did nothing (found by the performance scope). It keeps the rows whose file,
    folder or note holds every word typed -- and a rebuild of Settings keeps the words."""
    window = make()
    window.state.blacklist = [
        {u"name": u"ep01.mkv", u"path": u"D:\\Anime\\Sousou no Frieren\\ep01.mkv",
         u"note": u"", u"when": u"3 Sep", u"gone": False},
        {u"name": u"ep02.mkv", u"path": u"D:\\Anime\\One Piece\\ep02.mkv",
         u"note": u"the wrong cut", u"when": u"4 Sep", u"gone": False}]
    window.show_tab(gui_app.TAB_SET)
    assert len(_bl_rows(window)) == 2, u"the control: both rows are listed"
    window.filter_field.setText(u"frieren")                 # typed
    shown = [r for r in _bl_rows(window) if r.isVisibleTo(window)]
    assert len(shown) == 1 and u"ep01.mkv" in gui_app.texts(shown[0]), u"typing did nothing"
    # ⭐ The Layer 13 pass (Z13-5): a filter keeping rows with ANY word typed, and one
    # blind to capitals, both passed every check (Z-J1, Z-J2)
    window.filter_field.setText(u"frieren recap")
    assert not [r for r in _bl_rows(window) if r.isVisibleTo(window)], (
        u"one word of two kept a row")
    window.filter_field.setText(u"Frieren")
    shown = [r for r in _bl_rows(window) if r.isVisibleTo(window)]
    assert len(shown) == 1 and u"ep01.mkv" in gui_app.texts(shown[0]), u"capitals found nothing"
    window.filter_field.setText(u"wrong cut")               # a note, two words
    shown = [r for r in _bl_rows(window) if r.isVisibleTo(window)]
    assert len(shown) == 1 and u"ep02.mkv" in gui_app.texts(shown[0])
    window.render()                                         # Settings rebuilt
    assert window.filter_field.text() == u"wrong cut", u"a rebuild forgot the words"
    assert len([r for r in _bl_rows(window) if r.isVisibleTo(window)]) == 1
    window.filter_field.setText(u"")
    assert all(r.isVisibleTo(window) for r in _bl_rows(window)), u"clearing it hid rows"


# ===========================================================================
# ⭐ LAYER 13's ADVERSARIAL PASS (13z) -- ADVERSARY-2026-09-25.md, section Z
# ===========================================================================

#: What a stray key could PRESS, by name -- recorded on the class BEFORE a window is
#: built, so the connections its controls make reach the recorder.
_PRESSABLE = (u"_toggle_auto", u"_toggle_watch", u"_toggle_startup", u"set_auto_update",
              u"_toggle_recurse", u"_toggle_fallback", u"start_run")


def _pressed(monkeypatch):
    called = []
    for name in _PRESSABLE:
        monkeypatch.setattr(gui_app.HatoWindow, name,
                            lambda self, *args, _n=name, **kwargs: called.append(_n))
    return called


def _type(qapp, window, text):
    u"""Keys, one at a time, to whatever holds the keyboard -- the way a person types."""
    from PyQt6.QtTest import QTest
    for key in text:
        QTest.keyClick(QApplication.focusWidget() or window, key)
        qapp.processEvents()


def test_typing_in_the_filter_survives_the_minute_and_a_rebuild_and_presses_nothing(
        qapp, monkeypatch):
    u"""🚨 The Layer 13 pass, Z13-1 -- REAL. Typing *"one piece"* into the blacklist's
    filter as Settings was rebuilt -- the minute's look, whenever the daily run is on;
    an answer arriving -- `clear()` hid the field, Qt handed the keyboard to the title
    bar's DAILY-RUN SWITCH, and the Space PRESSED it: the daily run went off and the
    rest of the words were lost (the adversary's p02c). Typed here through the
    minute's look AND through a rebuild of Settings (the memory's answer)."""
    called = _pressed(monkeypatch)
    monkeypatch.setattr(gui_run, "pending_run", lambda: (0.0, []))
    window = make(running=False, auto=True)
    window.show()
    window.activateWindow()
    window.follow_other_runs(every_ms=60000)
    window._others_timer.stop()
    look = window._others_timer.timeout
    look.emit()                                          # the first look settles the minute
    window.show_tab(gui_app.TAB_SET)
    qapp.processEvents()
    try:
        window.filter_field.setFocus(Qt.FocusReason.MouseFocusReason)
        qapp.processEvents()
        assert QApplication.focusWidget() is window.filter_field, u"the control: typing starts there"
        _type(qapp, window, u"one")
        window._minute_seen -= 1
        look.emit()                                      # ... the minute turns
        _type(qapp, window, u" pi")
        card = window._ucard
        window._memory_read(None, [MEMORY])              # ... an answer rebuilds Settings
        assert window._ucard is not card, u"the control: Settings WAS rebuilt"
        _type(qapp, window, u"ece")
        assert called == [], u"the typing PRESSED %s" % called
        assert window.filter_field.text() == u"one piece", window.filter_field.text()
        assert QApplication.focusWidget() is window.filter_field, u"the keyboard left the filter"
    finally:
        window.hide()


def test_a_half_typed_time_outlives_a_rebuild_and_enter_still_judges_it(qapp, daily):
    u"""Z13-1's other half (the adversary's p06 -- it predates Layer 13): *"04:3"*, half
    typed as Settings was rebuilt, was JUDGED. The rebuild's focus-out finished the
    edit -- *"04:3 is not a time"*, *03:00* put back -- and rendered again from inside
    the rebuild's own `clear()`. The words and the keyboard outlive the rebuild; the
    person's own Enter still judges."""
    from PyQt6.QtTest import QTest
    daily[u"task"] = _task(u"03:00")
    window = make(running=False, auto=True)
    window.show()
    window.activateWindow()
    window.show_tab(gui_app.TAB_SET)
    qapp.processEvents()
    try:
        window.time_field.setFocus(Qt.FocusReason.MouseFocusReason)
        window.time_field.selectAll()
        _type(qapp, window, u"04:3")
        card = window._ucard
        window._memory_read(None, [MEMORY])              # an answer rebuilds Settings
        qapp.processEvents()
        assert window._ucard is not card, u"the control: Settings WAS rebuilt"
        assert window.state.schedule_said == u"", (
            u"the rebuild JUDGED a half-typed time: %s" % window.state.schedule_said)
        assert window.time_field.text() == u"04:3", window.time_field.text()
        assert QApplication.focusWidget() is window.time_field, u"the keyboard left the time"
        _type(qapp, window, u"0")
        QTest.keyClick(window.time_field, Qt.Key.Key_Return)
        assert window.state.schedule == u"04:30", u"Enter no longer sets the time"
        assert (u"enable", u"04:30") in daily[u"calls"], daily[u"calls"]
    finally:
        window.hide()


def test_the_keyboard_never_lands_on_the_daily_switch_at_start_or_after_a_rebuild(
        qapp, monkeypatch):
    u"""🚨 The Layer 13 pass. Z13-11: the window OPENED with the keyboard on the title
    bar's daily-run switch -- a Space straight after opening turned the daily run off
    (measured, both platforms). Z13-1: a rebuild hiding a focused BUTTON handed the
    keyboard down the chain to that same switch -- and a rebuild while the window sat
    in the background did it the moment the window came back."""
    called = _pressed(monkeypatch)
    window = make(running=False, auto=True)
    other = QWidget()
    window.show()
    window.activateWindow()
    qapp.processEvents()

    def a_button():
        pane = window.panes[gui_app.TAB_SET]
        return [b for b in pane.findChildren(QPushButton) if b.isVisibleTo(window)][0]
    try:
        assert QApplication.focusWidget() is not window.auto_switch, u"it OPENED on the switch"
        _type(qapp, window, u" ")
        assert called == [], u"a Space at the start pressed %s" % called
        window.show_tab(gui_app.TAB_SET)
        qapp.processEvents()
        button = a_button()
        button.setFocus(Qt.FocusReason.TabFocusReason)   # a person tabbed to it
        assert QApplication.focusWidget() is button, u"the control: a button holds the keys"
        window.render()                                  # an action's rebuild
        qapp.processEvents()
        assert QApplication.focusWidget() is not window.auto_switch, (
            u"a rebuild handed the keyboard to the switch")
        _type(qapp, window, u" ")
        assert called == [], u"a Space after a rebuild pressed %s" % called
        a_button().setFocus(Qt.FocusReason.TabFocusReason)
        other.show()
        other.activateWindow()
        qapp.processEvents()
        assert QApplication.activeWindow() is other, u"the control: hato is in the background"
        window.render()                                  # rebuilt while in the background
        window.activateWindow()
        qapp.processEvents()
        assert QApplication.activeWindow() is window, u"the control: hato is back"
        assert QApplication.focusWidget() is not window.auto_switch, (
            u"coming back, the keyboard was on the switch")
        _type(qapp, window, u" ")
        assert called == [], u"a Space on coming back pressed %s" % called
    finally:
        other.hide()
        window.hide()


def test_a_rebuild_of_settings_keeps_the_page_and_the_lists_place(qapp):
    u"""🚨 The Layer 13 pass, Z13-10 (found measuring the minute's rebuild): EVERY
    rebuild of Settings threw the page back to its top -- any action, *Check now* at
    the very bottom of it, the minute's look -- because the rebuilt page was laid out
    holding nothing before its queued show (1,642 px -> 0, measured on both
    platforms). The blacklist's own list went back to its top with it."""
    window = make(running=False)
    window.state.blacklist = [{u"name": u"Show %02d - 01.mkv" % n, u"note": u"",
                               u"when": u"3 Sep", u"gone": False} for n in range(20)]
    lay_out(window)
    window.show_tab(gui_app.TAB_SET)
    for _ in range(4):
        qapp.processEvents()
    page = window.panes[gui_app.TAB_SET].verticalScrollBar()
    try:
        listing = window._bl_area.verticalScrollBar()
        assert page.maximum() > 0 and listing.maximum() > 0, u"the control: both scroll"
        page.setValue(page.maximum())
        listing.setValue(listing.maximum())
        at, place, card = page.value(), listing.value(), window._ucard
        check = [b for b in window.findChildren(QPushButton)
                 if b.text().startswith(u"Check now")][0]
        check.click()                                    # at the very bottom of the page
        qapp.processEvents()
        assert window._ucard is not card, u"the control: Check now rebuilt Settings"
        assert page.value() == at, u"the page went to %d from %d" % (page.value(), at)
        now = window._bl_area.verticalScrollBar().value()
        assert now == place, u"the list went to %d from %d" % (now, place)
    finally:
        window.hide()


def test_a_look_mid_run_rebuilds_no_settings(qapp, monkeypatch):
    u"""The Layer 13 pass, Z13-3: mid-run, Settings was still rebuilt by the minute's look
    and by the tray's countdown starting and ending -- on a page 13b says stands still
    for a run (the adversary's p08). The run's end rebuilds it."""
    queue = [(0.0, [])]
    monkeypatch.setattr(gui_run, "pending_run", lambda: queue[0])
    window = make(running=True, auto=True)
    window.show_tab(gui_app.TAB_SET)
    window.follow_other_runs(every_ms=60000)
    window._others_timer.stop()
    look = window._others_timer.timeout
    look.emit()
    card = window._ucard
    window._minute_seen -= 1
    look.emit()                                          # a minute passes
    queue[0] = (45.0, [u"a.mkv"])
    look.emit()                                          # the tray's countdown starts
    queue[0] = (0.0, [])
    look.emit()                                          # ... and ends
    assert window._ucard is card, u"a look rebuilt Settings mid-run"
    window._runner = _FinishedRunner(0)
    window._drain()
    assert window._ucard is not card, u"the control: the run's end rebuilds it"


def _words(window):
    u"""Every word the window SHOWS -- tooltips too, whitespace collapsed -- from its
    visible widgets only. -> sorted [unicode]"""
    found = []
    for widget in window.findChildren(QWidget):
        if not widget.isVisibleTo(window):
            continue
        for getter in (u"text", u"toolTip", u"placeholderText"):
            method = getattr(widget, getter, None)
            try:
                value = method() if callable(method) else None
            except TypeError:
                value = None
            if isinstance(value, str) and value:
                found.append(u" ".join(value.split()))
    return sorted(found)


def test_a_minute_moves_the_next_run_in_place_and_says_what_a_rebuild_would(
        qapp, monkeypatch):
    u"""P-F on Settings (the Layer 13 pass): the minute's look rebuilt ALL of Settings to
    move *"next run in 14h"* -- once a minute, for anybody whose daily run is on -- and
    every rebuild took the keyboard, the words half typed and the page's place with it
    (Z13-1, Z13-10). It is repainted in place now. ⭐ And an hour on, the page says
    EXACTLY what a full rebuild says: a dated word left behind is a red here."""
    monkeypatch.setattr(gui_run, "pending_run", lambda: (0.0, []))
    window = make(running=False, auto=True)
    window.show_tab(gui_app.TAB_SET)
    window.follow_other_runs(every_ms=60000)
    window._others_timer.stop()
    look = window._others_timer.timeout
    look.emit()
    card, before = window._ucard, _words(window)
    window.state.now = NOW8 + timedelta(hours=1, minutes=1)
    window._minute_seen -= 1
    look.emit()                                          # an hour and a minute on
    assert window._ucard is card, u"the minute rebuilt Settings"
    moved = _words(window)
    window.render()                                      # what a full rebuild says
    assert window._ucard is not card, u"the control: that one did rebuild"
    rebuilt = _words(window)
    assert moved == rebuilt, u"said in place / said rebuilt: %s" % sorted(
        set(moved) ^ set(rebuilt))
    assert moved != before, u"the control: an hour passed and nothing dated moved"


def test_the_filter_says_what_it_leaves(qapp):
    u"""The Layer 13 pass, Z13-4 (the adversary's pictures): nothing matching was a blank
    186 px box; the heading said *"4 videos"* with one showing; a lone match floated in
    the middle of the box; and *"Remove those 2"* stood over rows the filter hid -- and
    removed them. ⭐ Over an empty list there is no filter at all: it had nothing to do."""
    window = lay_out(make(running=False))
    window.show_tab(gui_app.TAB_SET)
    qapp.processEvents()
    try:
        count, none, notice = window._bl_count, window._bl_none, window._bl_stale
        assert count.text() == u"· 4 videos" and notice.isVisibleTo(window), u"the control"
        assert not none.isVisibleTo(window), u"the control: nothing to say yet"
        window.filter_field.setText(u"zzz")
        assert count.text() == u"· 0 of 4 videos", count.text()
        assert none.isVisibleTo(window) and u"“zzz”" in none.text(), (
            u"nothing matching said nothing")
        assert not notice.isVisibleTo(window), u"the notice stood over rows the filter hides"
        window.filter_field.setText(u"one piece")
        qapp.processEvents()
        shown = [r for r in _bl_rows(window) if r.isVisibleTo(window)]
        assert len(shown) == 1 and count.text() == u"· 1 of 4 videos", count.text()
        assert not none.isVisibleTo(window), u"a match was said to be nothing"
        assert shown[0].height() <= shown[0].sizeHint().height() + 2, (
            u"a lone match was spread over the box: %d px" % shown[0].height())
        window.filter_field.setText(u"")
        assert count.text() == u"· 4 videos" and notice.isVisibleTo(window), count.text()
        window.state.blacklist = []
        window.render()
        assert window.filter_field is None and not [
            f for f in window.findChildren(QLineEdit) if f.objectName() == u"filter"], (
            u"a filter over an empty list")
    finally:
        window.hide()


def test_the_errors_tooltip_goes_when_the_footer_moves_on(qapp):
    u"""The Layer 13 pass, Z13-8 (Z-C3): the footer's *"hato.log is at …"* belongs to
    the error line alone -- a mutant that only ever SET it survived every check."""
    window = make(running=True)
    window.error_caught()
    qapp.processEvents()                                 # its render is queued
    assert u"hato.log is at" in window.live_label.toolTip(), u"the control: the error's tooltip"
    window._runner = _EventRunner([{u"type": u"progress", u"name": u"show 1"}])
    window._drain()                                      # a quiet tick moves the footer on
    assert u"show 1" in window.live_label.text(), u"the control: the footer moved on"
    assert window.live_label.toolTip() == u"", window.live_label.toolTip()


@pytest.mark.skipif(not os.name == "nt", reason=(
    "measures WINDOWS' own fonts (QT_QPA_FONTDIR) under Windows' 'Make text bigger' -- another platform's fonts and text-size setting are another check"))
def test_a_strips_words_sit_on_its_buttons_middle_under_a_larger_system_font():
    u"""🚨 The Layer 13 pass, Z13-2: 13f stopped `mark` polishing a fresh widget, and
    the strip then measured its lead UNPOLISHED -- in the application's font, not the
    sheet's. At Windows' default 9 pt the two pad alike, which is the only reason 64
    shots were identical and M13-22 was retired; at 12 pt ("Make text bigger") the
    words rode 2.5 px high. ⭐ In a process of its own, with real fonts: here, offscreen
    on Windows, every size measures alike and no check could ever fail."""
    import subprocess
    child = subprocess.run([sys.executable, os.path.join(HERE, u"_strip_fonts.py")],
                           capture_output=True, timeout=180)
    said = (child.stdout + child.stderr).decode(u"utf-8", u"replace").strip()
    assert child.returncode == 0, u"exit %d -- %s" % (child.returncode, said[-600:])


def test_a_chevron_never_fades_on_a_row_nobody_can_see():
    u"""🚨 The Layer 13 pass, Z13-9 (it predates Layer 13): the chevron's opacity effect,
    animated on a HIDDEN row -- its pane at the back, or its show still queued --
    crashed the window 8 of 8 when forced, and about 1 run in 36 of a person flicking
    between tabs mid-fade. ⭐ In a process of its own (`_fade_hidden.py`), like 13a's
    crash check: a crash here would take every later check down with it."""
    import subprocess
    child = subprocess.run([sys.executable, u"-X", u"faulthandler",
                            os.path.join(HERE, u"_fade_hidden.py")],
                           capture_output=True, timeout=180)
    said = (child.stdout + child.stderr).decode(u"utf-8", u"replace").strip()
    assert child.returncode == 0, (
        u"the window CRASHED (exit %d, 0x%08X)" % (child.returncode,
                                                   child.returncode & 0xFFFFFFFF)
        if child.returncode not in (0, 1) else u"a fade ran where nobody could see it"
    ) + u" -- %s" % said[-400:]
