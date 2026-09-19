# -*- coding: utf-8 -*-
u"""
The window. RUNBOOK 7c, and `spec/05-interface.md` implements `gui-mock/mock2.html`.

    python -m hato.gui

===========================================================================
[!] THE WINDOW DECIDES NOTHING
===========================================================================

It spawns `hato --json --progress` and paints the NDJSON that comes back.
The timing verdict inside the engine is the referee: a wrong subtitle is
refused by the engine, not written, and that stays true when the PERSON is
the one choosing -- a manual pick goes out as `hato sync <video> <subtitle>`
and is checked exactly like hato's own ranking. [X] Nothing in this file
re-decides any of it, re-implements argv building, re-parses NDJSON, or
invents an outcome word. `hato.gui.run` owns all four.

===========================================================================
[*] ONE STATE OBJECT, AND EVERY DISPLAYED VALUE DERIVES FROM IT
===========================================================================

`build-ui` standing rule: *"No static derived text. Every displayed value
derives from one state object."* The mock broke it and recorded the break --
the tab's count badge and the footer's tally were the SAME number, hardcoded
in two places, so pairing an episode left the badge claiming two still needed
a person while the list under it showed one.

So: `State.tallies()` is the ONE derivation and both readers call it. There
is no second count anywhere in this file.

===========================================================================
THE DESIGN IS RULED. THIS IS A PORT, NOT A REDESIGN.
===========================================================================

Sonic approved `gui-mock/mock2.html` on 2026-09-18 -- *"It's perfect."* The
rules that are easiest to lose in a port, each paid for:

  [!] The word "refused" NEVER appears. It is the engine's verdict, and to a
      person who can fix it in two clicks it reads as an accusation. The only
      permitted vocabulary is `run.interface_words()`.
  [*] A Subtitles row is THREE things -- episode, percent, the file it was
      paired with. Six columns of evidence read as noise even when every
      column was true. Everything else is behind the row.
  [*] Failures live in their own tab and are therefore QUIET. Being in that
      tab IS the signal; the deep garnet survives only as a 2px left edge and
      the count badge.
  [*] Clicking a candidate IS "use this pair". No confirm button. One row
      open at a time; on commit it collapses to green NAMING the file it
      used, and the next unresolved row opens.
  [X] The accordion animates to the content's OWN height. A cap means a
      scrollbar, and with six candidates the case that most needs every
      option visible is the case that scrolls.
  Chevrons on hover only. Eight static markers down a calm list is eight
      things to look at for no information.

===========================================================================
[X] NO COLOUR LITERAL IN THIS FILE
===========================================================================

Every colour comes from `hato.gui.theme`, and `test_gui_widgets.py` greps
this file for hex and fails on a hit. A literal here is a second palette that
drifts from the measured one.

===========================================================================
WHAT QSS CANNOT DO, AND HOW IT IS DONE INSTEAD
===========================================================================

[!] A PLAIN `QWidget` DOES NOT PAINT ITS OWN STYLESHEET BACKGROUND -- it
needs a `paintEvent` that draws `PE_Widget`. Without it every container rule
in `theme.qss()` is silently inert, which looks exactly like a stylesheet
that failed to load. `Styled` is that base class and every container here
derives from it.

Qt has no `transition`, so hover and collapse are `QPropertyAnimation`s on
one shared easing curve; no `box-shadow`, so the glow is an animated
`QGraphicsDropShadowEffect`; no `text-overflow: ellipsis`, so long filenames
go through `Elide`, which measures and truncates in `paintEvent`.
"""
from __future__ import print_function

import os
import re
import sys
import textwrap
import time

# ⭐ GUARDED, AND THE GUARD IS WHAT LETS Qt BE AN *EXTRA* RATHER THAN A
# DEPENDENCY (RUNBOOK 7c). The claim an extra makes is *the package installs
# and imports without it*, and hato's CLI does the whole job with no window --
# so making every command-line user install ~70 MB of toolkit would be the tail
# wagging the dog.
#
# ⚠ THE `try` IS LOAD-BEARING IN TWO WAYS. It turns an absent toolkit into an
# instruction naming the fix instead of a traceback about `PyQt6.QtCore`
# (`doctrine/architecture`: instruction, not refusal) -- and
# `tests/test_packaging.py` asserts that anything declared ONLY as an extra is
# never imported bare at module top level, because one unguarded import breaks
# `import hato` for every install without it.
try:
    from PyQt6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation,
                              QRectF, QSize, Qt, QTimer, QUrl,
                              QVariantAnimation, pyqtSignal)
    from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QPainter,
                             QPalette, QPen)
    from PyQt6.QtWidgets import (QAbstractButton, QApplication, QDialog,
                                 QFileDialog,
                                 QFrame,
                                 QGraphicsDropShadowEffect,
                                 QGraphicsOpacityEffect,
                                 QGridLayout, QHBoxLayout,
                                 QLabel, QLineEdit,
                                 QPushButton, QScrollArea, QSizePolicy,
                                 QStackedWidget, QStyle, QStyleOption,
                                 QVBoxLayout, QWIDGETSIZE_MAX, QWidget)
except ImportError as _exc:                               # pragma: no cover
    # ⛔ The message names PyQt6 so `hato.gui.main()` can tell this apart from
    # an ImportError raised INSIDE the window's own code -- sending somebody to
    # install a package that is already there is worse than the raw traceback.
    raise ImportError(
        "hato's window needs PyQt6, which is not installed. "
        "pip install PyQt6 -- hato itself does not need it, and `hato <folder>` "
        "works without a window (%s)" % _exc)

from hato.gui import branding, theme
from hato.gui import run as gui_run

#: ⭐ ONE PLACE, because it is now in three. The repository hato came from --
#: the footer credit, the tab-strip links, and anything later that wants to
#: send a person here. ⛔ A fourth hand-typed copy is a typo nobody notices
#: until a link goes nowhere.
REPO_URL = u"https://github.com/SonicSandbox/hato"
ISSUES_URL = REPO_URL + u"/issues"

#: The three tabs, in Sonic's priority order. *"the view should be in priority"*
TAB_SUBS = u"subs"
TAB_PICK = u"pick"
TAB_SET = u"set"
TABS = (TAB_SUBS, TAB_PICK, TAB_SET)

#: Measures from the mock, in logical pixels. [!] THE CONTENT COLUMN IS CAPPED
#: AND THAT WAS A DEFECT FOUND BY LOOKING: stretched across the full width, a
#: right-aligned number ended up ~900px from the text it described, so the eye
#: had to cross the whole window to connect a filename to its match rate.
COL_EP = 52
COL_PC = 52
COL_NAME = 640
COL_CHEV = 20
COL_WHO = 560
COL_CAND = 618
COL_SET = 604
GAP = 14
PAD = 18
DETAIL_INDENT = 136
CAND_INDENT = 84
WIN_W = 1100
WIN_H = 660


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def ease():
    u"""The one easing curve, from `theme.EASE`. -> QEasingCurve

    [X] ONE curve for the whole window. Sonic asked for *"modern and premium
    and interactable yet also simple and magic"*, and a second curve is the
    first step towards effects.
    """
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    (x1, y1), (x2, y2) = theme.EASE
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2),
                                QPointF(1.0, 1.0))
    return curve


def repolish(widget):
    u"""Make Qt re-evaluate the stylesheet after a dynamic property changed.

    [!] WITHOUT THIS A PROPERTY SELECTOR NEVER FIRES AGAIN after the first
    polish, so `#row[expanded="true"]` would be correct in the sheet, correct
    in the property, and invisible on screen.
    """
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def mark(widget, name, value):
    u"""Set a dynamic property Qt's selectors can see, and repolish."""
    widget.setProperty(name, u"true" if value is True
                       else (u"false" if value is False else value))
    repolish(widget)


def texts(widget):
    u"""Every string this widget tree can put in front of a person. -> [unicode]

    [*] SO A CHECK CAN PROVE A NEGATIVE. `05-interface.md` rules that the word
    *refused* never appears in the interface; the only way to assert that is
    to be able to walk what was actually built, including tooltips.
    """
    found = []
    for child in widget.findChildren(QWidget):
        for getter in (u"text", u"toolTip", u"placeholderText", u"windowTitle"):
            method = getattr(child, getter, None)
            if callable(method):
                try:
                    value = method()
                except Exception:
                    continue
                if value:
                    found.append(value)
    title = widget.windowTitle() if hasattr(widget, u"windowTitle") else u""
    if title:
        found.append(title)
    return found


#: [!] THE ONE WORD THAT MAY NOT REACH A PERSON, and every inflection of it.
#: `spec/05-interface.md`: *"when it says 'refused' it's quite alarming."*
_ENGINE_WORD = re.compile(u"refus\\w*", re.IGNORECASE)
#: What is said instead -- the spec's and the mock's own phrasing. It is the
#: same fact, told as a measurement rather than as a judgement on the person.
_HUMAN_SENTENCE = u"the timing did not hold"


def safe(text, instead=None):
    u"""Engine prose, made safe to put in front of a person. -> unicode

    [!] `reason`, `verdict_word` and the progress line are all written by the
    ENGINE, whose word for *the timing did not hold* is REFUSED. Every string
    hato composes itself can simply avoid it; a field passed through verbatim
    cannot, and *"the subtitle was refused"* arriving in a detail panel is
    exactly the alarm the whole tab layout was redesigned to remove.

    [!] AND IT REPLACES THE SENTENCE, NOT THE WORD. Substituting in place
    produced *"the pair was did not hold"* -- caught by reading a shot, not by
    the check, which was perfectly happy because the forbidden word was gone.
    A sanitiser that emits broken English has moved the problem rather than
    solved it, so when the engine's word appears hato says its OWN sentence.

    [X] Nothing engine-written reaches a widget without coming through here.
    """
    text = (text or u"").strip()
    if not text:
        return u""
    if _ENGINE_WORD.search(text):
        return instead if instead is not None else _HUMAN_SENTENCE
    return text


def wrap(text, width=52):
    u"""A tooltip that wraps. -> unicode

    Qt wraps a RICH-text tooltip at the screen width, which on a wide monitor
    is one very long line; a plain tooltip with newlines in it wraps exactly
    where it is told to. So the wrapping is done here.
    """
    parts = []
    for paragraph in (text or u"").split(u"\n\n"):
        parts.append(textwrap.fill(u" ".join(paragraph.split()), width))
    return u"\n\n".join(parts)


def group_of(filename):
    u"""*"[Erai-raws] Re Zero ...ass"* -> *"Erai-raws"*. -> unicode

    Presentation only -- the ranking that matters happened in the engine.
    """
    name = filename or u""
    if name.startswith(u"[") and u"]" in name:
        return name[1:name.index(u"]")]
    return u"unknown group"


def kb(size_bytes):
    u"""-> *"29 KB"*, or an empty string when nothing was measured.

    [X] `0` IS A REAL ANSWER and must not read as absent, so the two are
    distinguished rather than both falling through to the empty string.
    """
    if size_bytes is None:
        return u""
    try:
        return u"%d KB" % int(round(float(size_bytes) / 1024.0))
    except (TypeError, ValueError):
        return u""


def seconds_text(value):
    u"""-> *"41.2 s"*, or an empty string."""
    try:
        return u"%.1f s" % float(value)
    except (TypeError, ValueError):
        return u""


# ---------------------------------------------------------------------------
# [*] THE STATE -- one object, and everything on screen derives from it
# ---------------------------------------------------------------------------

class State(object):
    u"""Everything the window paints, in one place. No Qt, no widgets.

    [*] `tallies()` IS THE ONLY COUNT. The tab badge and the footer both read
    it, so they cannot disagree -- which is the defect the mock recorded
    against itself and the reason this class exists at all.
    """

    def __init__(self):
        #: The `{"type": "video"}` objects, verbatim off the wire.
        self.rows = []
        #: The final `{"type": "run"}` object, verbatim.
        self.summary = {}
        #: row key -> the subtitle FILENAME a person committed to it.
        #: [X] Not *"chosen"* or any other placeholder: a collapsed row has to
        #: say what happened to it, which is what makes collapsing safe.
        self.picked = {}
        self.tab = TAB_SUBS
        self.open_rows = set()
        #: [*] A SINGLE VALUE, not a set: Needs-you is an accordion.
        self.open_pick = None
        # ---- settings, as `hato config --show --json` reports them ----
        self.auto = True
        self.schedule = u"03:00"
        self.next_run = u""
        self.watch = False
        self.folders = []
        self.skip_folders = []
        self.recurse = True
        self.blacklist = []
        #: ⭐ RUNBOOK 7h. Empty means the integration is off, which is the
        #: default -- most people do not run surasura.
        self.surasura_dir = u""
        self.key_hint = None
        #: ⭐ What jimaku said the last time a key was entered, and whether it
        #: worked. ⛔ Set ONLY on key entry -- Sonic: *"just on the key entry,
        #: not another time."* A status that re-checked on every render would
        #: spend a metered request to tell somebody what they already know.
        self.key_status = u""
        self.key_ok = None
        #: ⛔ Why the settings look empty, when they do. A config hato refuses
        #: is the one reason this window cannot show what is on disk, and
        #: opening on silent defaults would read as "your settings vanished".
        self.config_error = u""
        # ---- the run itself ----
        self.running = False
        #: ⭐ Seconds until a run the TRAY has queued, and what it is waiting
        #: on. 0 means nothing is coming. ⚠ An invisible wait is
        #: indistinguishable from broken -- that is the whole reason this
        #: exists.
        self.queued_in = 0.0
        self.queued_names = []
        self.live = u""
        self.last_run = u""
        self.video_total = 0

    # -- identity ----------------------------------------------------------

    @staticmethod
    def key(row):
        u"""A stable id for one row. -> unicode

        The video's own path: unique on a machine, survives a re-render, and
        is what a manual pair is addressed to anyway.
        """
        return row.get(u"video") or row.get(u"name") or u""

    @staticmethod
    def word(row):
        u"""-> the INTERFACE's word for this row. [X] Never the engine's."""
        return gui_run.outcome_word(row)

    # -- partitions --------------------------------------------------------

    def of(self, word):
        u"""Every row the interface calls `word`, in arrival order."""
        return [row for row in self.rows if self.word(row) == word]

    def unresolved(self):
        u"""Needs-you rows nobody has picked for yet. -> [row]

        [*] THIS is what moves when a candidate is clicked, and it is why the
        badge and the footer cannot be hardcoded: a pick changes the answer
        without changing a single field on the wire.
        """
        return [row for row in self.of(gui_run.NEEDS_YOU)
                if self.key(row) not in self.picked]

    def tallies(self):
        u"""-> {interface word: n}. The ONE count. Both readers call this.

        `run.counts` partitions the raw rows; the needs-you figure is then
        replaced by the LIVE one, because a row a person has already paired is
        no longer waiting on them even though its wire outcome has not moved.
        """
        out = gui_run.counts(self.rows)
        out[gui_run.NEEDS_YOU] = len(self.unresolved())
        return out

    def need_count(self):
        u"""-> the number the badge shows and the footer says. One source."""
        return self.tallies()[gui_run.NEEDS_YOU]

    # -- grouping ----------------------------------------------------------

    def shows(self):
        u"""Added rows, grouped by show, in arrival order.

        -> [(title, season, [row], skipped_in_this_show)]
        """
        order = []
        index = {}
        for row in self.rows:
            if self.word(row) != gui_run.ADDED:
                continue
            ident = (row.get(u"title") or row.get(u"name") or u"",
                     row.get(u"season"))
            if ident not in index:
                index[ident] = []
                order.append(ident)
            index[ident].append(row)
        out = []
        for ident in order:
            title, season = ident
            skipped = len([row for row in self.rows
                           if self.word(row) == gui_run.SKIPPED
                           and (row.get(u"title") or u"") == title])
            out.append((title, season, index[ident], skipped))
        return out

    def fully_skipped(self):
        u"""Shows where NOTHING was added -- one quiet line each.

        -> [(title, n)] . *"visible, but not the focus."*
        """
        added_titles = set(title for title, _s, _r, _k in self.shows())
        order = []
        counted = {}
        for row in self.rows:
            if self.word(row) != gui_run.SKIPPED:
                continue
            title = row.get(u"title") or row.get(u"name") or u""
            if title in added_titles:
                continue
            if title not in counted:
                counted[title] = 0
                order.append(title)
            counted[title] += 1
        return [(title, counted[title]) for title in order]

    def next_unresolved(self, after):
        u"""-> the key of the row that should open as `after` closes, or None.

        Sonic: *"it should only have one open at a time but after selecting
        one, the next one opens as it closes."*
        """
        for row in self.unresolved():
            if self.key(row) != after:
                return self.key(row)
        return None


def candidates(row):
    u"""The files hato already downloaded for this episode. -> [attempt]

    [X] NEVER THE WHOLE JIMAKU CATALOGUE -- `05-interface.md` §manual pairing.
    These are `row["attempts"]`, which is exactly what was tried.
    """
    return list(row.get(u"attempts") or ())


def candidate_path(attempt):
    u"""Where that candidate sits on disk. -> unicode or None

    tsubasa's `Result.subtitle` is the path it was handed, so an attempt that
    reached the engine carries it. One that never got that far has no path and
    cannot be committed -- and says so rather than committing something else.
    """
    tsu = attempt.get(u"tsubasa") or {}
    return tsu.get(u"subtitle") or attempt.get(u"path") or None


def episode_text(episode):
    u"""-> *"01"*, *"04"*, *"1121"*.

    Zero-padded to two, as the ruled design shows -- a column of `1 2 4` reads
    as a list of quantities, `01 02 04` reads as episode numbers. [X] A number
    already wider than two is left alone: One Piece is at 1121 and padding is
    not truncation.
    """
    if episode is None:
        return u""
    try:
        return u"%02d" % int(episode)
    except (TypeError, ValueError):
        return str(episode)


def footer_status(state):
    u"""The one line on the footer that says what hato is doing. -> unicode

    🚨 SONIC THOUGHT AUTO-FETCH WAS BROKEN, AND IT WAS NOT. He dropped a video
    into a watched subfolder, nothing appeared, and he reported it. Measured
    end to end afterwards, the whole chain worked -- what he hit was the
    **settle minute**, his own ruling, during which nothing anywhere said a run
    was coming.

    ⭐ AN INVISIBLE WAIT IS INDISTINGUISHABLE FROM BROKEN. That is the entire
    reason this function exists: the delay was right, the silence was not.

    ⚠ PURE, and takes the state rather than reading anything -- the WORDING is
    the feature here, so it has to be checkable without building a window.
    """
    if state.running:
        return state.live or u"running"
    left = int(round(getattr(state, u"queued_in", 0.0) or 0.0))
    if left > 0:
        names = [n for n in (getattr(state, u"queued_names", None) or ()) if n]
        # ⚠ The FILE, not a count, when there is one: "Frieren S2 - 01.mkv" is
        # what a person just dropped in and is looking for.
        what = os.path.basename(names[0]) if len(names) == 1 else \
            (u"%d new videos" % len(names) if names else u"a new video")
        # ⭐ Under five seconds a number that keeps changing reads as noise.
        when = u"in a moment" if left <= 5 else u"in %ds" % left
        return u"%s arrived — running %s" % (what, when)
    return state.live or u"idle"


def rate_text(value):
    u"""-> *"57%"*, or an em dash when nothing was timed.

    [X] The absent case must not become zero: `0` means *it matched nothing*.
    """
    if value is None:
        return u"—"
    try:
        return u"%d%%" % int(round(float(value) * 100))
    except (TypeError, ValueError):
        return u"—"


#: [*] tsubasa's strongest confidence word. `verdict.py`: *"every part of the
#: episode locks in well."*
LOCKED = u"locked"


def tier(row):
    u"""Which of the two written-and-fine hues this row's number gets.

    -> `"ok"` | `"look"` | `"none"`

    [!] IT IS THE VERDICT WORD, NOT THE PERCENTAGE, and reading the ruled
    design as a threshold was wrong. In `gui-mock/shots-final`, 91% is AMBER
    and 79% is GREEN -- no percentage rule produces that. `theme.css` says
    what the amber means outright: *"written, worth a look: segments /
    runtime check"*, and every row in the mock fits the engine's own ladder:

        locked -> green    strong, fair, uncertain -> amber

    So the hue is tsubasa's confidence ranking, shown; hato re-decides
    nothing. [X] There is no third tier: a row in this tab WAS written, and
    the failure colour belongs to the other tab, where it is an edge.
    """
    tsu = row.get(u"tsubasa") or {}
    word = tsu.get(u"verdict_word")
    if not word:
        return u"none"
    return u"ok" if word == LOCKED else u"look"


# ---------------------------------------------------------------------------
# painted and styled primitives
# ---------------------------------------------------------------------------

class Styled(QWidget):
    u"""A container that actually paints the stylesheet it was given.

    [!] A plain `QWidget` ignores `background`, `border` and `border-radius`
    from QSS. Every rule in `theme.qss()` that targets a container is inert
    without this `paintEvent`, and the symptom -- nothing draws -- is
    indistinguishable from a sheet that never loaded.
    """

    def __init__(self, parent=None, name=None):
        super().__init__(parent)
        if name:
            self.setObjectName(name)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event):
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget,
                                   option, painter, self)


class Elide(QLabel):
    u"""A label that truncates with an ellipsis instead of overflowing.

    [!] QSS HAS NO `text-overflow`, and a subtitle filename is routinely 60
    characters. Without this the name pushes the row's other columns out of
    the window -- the exact fault that once hid an episode number behind an
    overflowing chip, on the one row that needed attention.
    """

    def __init__(self, text=u"", parent=None, name=None,
                 mode=Qt.TextElideMode.ElideRight):
        super().__init__(u"", parent)
        if name:
            self.setObjectName(name)
        self._full = text or u""
        self._mode = mode
        #: [!] `Preferred`, NOT `Ignored`, AND IT WAS A REAL OVERLAP. `Ignored`
        #: tells Qt the size hint is irrelevant and the widget may take
        #: whatever is going -- so an eliding label with `stretch=1` claimed
        #: nearly the whole row and Qt then had nothing left for its
        #: fixed-width siblings and DREW THEM ON TOP OF EACH OTHER. Measured on
        #: a blacklist row 2026-09-18: the note ran to x=630 inside a 576px row
        #: with the date starting at x=490, so *"a commentary track"*, *"17
        #: Sep"* and the remove button rendered as one unreadable smear.
        #: `Preferred` + a zero `minimumSizeHint` is the combination that means
        #: *"this is my natural width, and I am the one that can shrink"*.
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Preferred)

    def setText(self, text):
        self._full = text or u""
        self.setToolTip(u"")
        self.update()
        self.updateGeometry()

    def text(self):
        return self._full

    def sizeHint(self):
        hint = super().sizeHint()
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance(self._full) + 2, hint.height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.WindowText)))
        rect = self.contentsRect()
        shown = self.fontMetrics().elidedText(self._full, self._mode,
                                              rect.width())
        painter.drawText(rect, int(self.alignment()), shown)


class Switch(QAbstractButton):
    u"""The pill switch from the title bar and Settings.

    Painted rather than styled, because Qt has no switch and a `QCheckBox`
    dressed up as one is a control whose SHAPE lies about what it does.
    """

    TRACK_W = 36
    TRACK_H = 20
    KNOB = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.TRACK_W, self.TRACK_H)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._travel = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(theme.SLOW)
        self._anim.setEasingCurve(ease())
        self._anim.valueChanged.connect(self._slide)
        self.toggled.connect(self._retarget)

    def _slide(self, value):
        self._travel = float(value)
        self.update()

    def _retarget(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._travel)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):
        u"""Set the state WITHOUT animating to it.

        🚨 REPORTED BY SONIC, 2026-09-18: *"when i click on settings, the
        toggles go from nothing to what they were toggled. Just slightly
        visually jarring as if it was changing right then."* He is describing
        exactly what it was doing.

        ⛔ `super().setChecked()` EMITS `toggled`, which fires `_retarget`,
        which starts the slide from wherever the knob currently is -- and on a
        freshly-built tab that is 0. So opening Settings played every switch
        turning itself on, which is the animation for *a value just changed*
        being used for *here is the value*.

        ⭐ The animation belongs to the INTERACTION, not to the state. Stopping
        it after the signal has fired, and then placing the knob, is what makes
        the difference between showing a setting and appearing to change one.
        """
        super().setChecked(bool(on))
        self._anim.stop()                  # ⛔ AFTER the signal, or it restarts
        self._travel = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        on = self.isChecked()
        track = QColor(theme.SWITCH_ON if on else theme.LINE)
        edge = QColor(theme.ACCENT_QUIET if (on or self.underMouse())
                      else theme.LINE_HI)
        radius = self.TRACK_H / 2.0
        painter.setPen(QPen(edge, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.TRACK_W - 1,
                                       self.TRACK_H - 1), radius, radius)
        left = 2.0 + self._travel * (self.TRACK_W - self.KNOB - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT if on else theme.INK_DIM))
        painter.drawEllipse(QRectF(left, 3.0, self.KNOB, self.KNOB))


class Check(QAbstractButton):
    u"""A checkbox, painted, with a TICK.

    [!] A CHECKBOX IS NOT A RADIO. In the mock the rule that fixed the native
    blue radios also caught the one checkbox and rendered it as a circle --
    a shape that says *pick one of these* about a thing that is simply on or
    off. Square box, and a tick rather than a dot.
    """

    BOX = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.BOX, self.BOX)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        on = self.isChecked()
        edge = QColor(theme.ACCENT if on else
                      (theme.ACCENT_QUIET if self.underMouse() else theme.LINE_HI))
        painter.setPen(QPen(edge, 1))
        painter.setBrush(QColor(theme.BG))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.BOX - 1, self.BOX - 1),
                                4, 4)
        if not on:
            return
        painter.setPen(QPen(QColor(theme.ACCENT), 2,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline(QPoint(3, 7), QPoint(6, 10), QPoint(11, 4))


class PulseDot(Styled):
    u"""The live dot on the footer. Pulses only while something is running.

    [X] NO DECORATION THAT DOES NOT REPORT -- Sonic's rule, and the reason the
    animation STOPS rather than idling: a ring pulsing over a finished run
    says *working* about a thing that is not.
    """

    def __init__(self, parent=None):
        super().__init__(parent, u"dot")
        self.setFixedSize(16, 16)
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(ease())
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, value):
        self._phase = float(value)
        self.update()

    def set_running(self, running):
        if running and self._anim.state() != QVariantAnimation.State.Running:
            self._anim.start()
        elif not running:
            self._anim.stop()
            self._phase = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        if self._phase:
            ring = QColor(theme.ACCENT)
            ring.setAlphaF(max(0.0, 0.4 * (1.0 - self._phase)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ring)
            radius = 3.0 + 4.0 * self._phase
            painter.drawEllipse(centre, radius, radius)
        painter.setBrush(QColor(theme.ACCENT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, 3.0, 3.0)


def lift(widget):
    u"""Make a control answer the pointer. -> the widget

    Sonic: *"When hovering over buttons, there is action... modern and premium
    and interactable yet also simple and magic."* Qt has no `box-shadow` and
    no `transition`, so the mock's `0 3px 12px -4px` glow becomes a
    `QGraphicsDropShadowEffect` whose blur and offset are ANIMATED on the one
    shared curve. [X] One accent, one distance, one curve.

    [!] The mock's additional `translateY(-1px)` is NOT ported: inside a Qt
    layout a position animation is overwritten by the next layout pass, and a
    lift that flickers reports less than a glow that does not.
    """
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(0)
    effect.setOffset(0, 0)
    glow = QColor(theme.REFUSED_FILL)
    glow.setAlphaF(0.47)
    effect.setColor(glow)
    widget.setGraphicsEffect(effect)

    animation = QVariantAnimation(widget)
    animation.setDuration(theme.FAST)
    animation.setEasingCurve(ease())

    def apply(value):
        effect.setBlurRadius(theme.GLOW * float(value))
        effect.setOffset(0, theme.LIFT * float(value))

    animation.valueChanged.connect(apply)

    def to(target):
        animation.stop()
        animation.setStartValue(effect.blurRadius() / float(theme.GLOW))
        animation.setEndValue(target)
        animation.start()

    original_enter = widget.enterEvent
    original_leave = widget.leaveEvent

    def enter(event):
        to(1.0)
        original_enter(event)

    def leave(event):
        to(0.0)
        original_leave(event)

    widget.enterEvent = enter
    widget.leaveEvent = leave
    return widget


class Accordion(Styled):
    u"""A panel that animates open to the height of whatever is inside it.

    [X] NO CAP, AND THEREFORE NO SCROLLBAR. Sonic: *"the accordion looks ugly
    because you made it have to scroll. It's the white scrollbar and looks so
    bad and is located near the center."*

    The first version of the mock animated to a 420px ceiling, so a list
    taller than the ceiling grew a scrollbar -- and the ceiling was a guess:
    six candidates (`--candidates 3` plus *"try 3 more"*) overflow it, so THE
    ONE CASE WHERE A PERSON MOST NEEDS TO SEE EVERY OPTION IS THE CASE THAT
    SCROLLS.

    [*] So the end value is read from the content's own `sizeHint()` every
    time it opens, and when the animation finishes the ceiling is released to
    Qt's own sentinel so later growth is never clipped. There is no number to
    guess and none to get wrong.
    """

    def __init__(self, content, parent=None):
        super().__init__(parent, u"accordion")
        self.content = content
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(content)
        self._open = False
        self.setMaximumHeight(0)
        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(theme.SLOW)
        self._anim.setEasingCurve(ease())
        self._anim.finished.connect(self._settle)
        self._fade = QGraphicsOpacityEffect(self)
        self._fade.setOpacity(0.0)
        self.setGraphicsEffect(self._fade)

    def target_height(self):
        u"""-> the content's OWN height. [X] Never a constant."""
        return max(self.content.sizeHint().height(),
                   self.content.minimumSizeHint().height())

    def is_open(self):
        return self._open

    def set_open(self, open_, animate=True):
        self._open = bool(open_)
        end = self.target_height() if self._open else 0
        self._fade.setOpacity(1.0 if self._open else 0.0)
        if not animate:
            self._anim.stop()
            self.setMaximumHeight(QWIDGETSIZE_MAX if self._open else 0)
            return
        self._anim.stop()
        self._anim.setStartValue(self.height())
        self._anim.setEndValue(end)
        self._anim.start()

    def _settle(self):
        u"""[*] Release the ceiling once open, so later growth is not clipped."""
        if self._open:
            self.setMaximumHeight(QWIDGETSIZE_MAX)


class Clickable(Styled):
    u"""A container that reports a click, and says so with the cursor."""

    clicked = pyqtSignal()

    def __init__(self, parent=None, name=None):
        super().__init__(parent, name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and \
                self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# small builders
# ---------------------------------------------------------------------------

def label(text, name=None, parent=None):
    widget = QLabel(text, parent)
    if name:
        widget.setObjectName(name)
    return widget


def paragraph(text, parent=None):
    u"""A multi-line explanatory line, WRAPPED. -> QLabel

    [!] QT DOES NOT WRAP A LABEL UNLESS TOLD TO, and the symptom is not an
    overflow -- it is a silent truncation. Measured 2026-09-18: *"Windows
    wakes hato at that time and it exits when it is done -- nothing sits
    running in the background. Each run finds whatever is new."* rendered as
    *"... Each run finds"* and simply stopped, mid-sentence, with no ellipsis
    and nothing to suggest anything was missing. Three more paragraphs in
    Settings were losing their last clause the same way.

    [X] So a paragraph gets this and an inline hint does not: wrapping the
    short ones would break single-line rows that are meant to stay on one
    line.
    """
    widget = QLabel(text, parent)
    widget.setObjectName(u"hint")
    widget.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Policy.Preferred,
                         QSizePolicy.Policy.Minimum)
    return widget


def info_dot(tip, parent=None):
    u"""The circular lowercase i, with its substance on hover.

    `build-ui` standing rule: *"Detail and tooltip fields carry SUBSTANCE --
    the effect, the number, the thing itself."* Commentary does not earn one.
    """
    dot = QLabel(u"i", parent)
    dot.setObjectName(u"info")
    dot.setFixedSize(15, 15)
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dot.setToolTip(wrap(tip))
    dot.setCursor(Qt.CursorShape.WhatsThisCursor)
    return dot


def button(text, parent=None, accent=False):
    btn = QPushButton(text, parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if accent:
        btn.setObjectName(u"btnGo")
    return lift(btn)


def link_label(text, url, name=None, parent=None):
    u"""A label that is one link, themed, opening in the person's browser.

    🚨 Qt PAINTS AN `<a href>` FROM THE PALETTE, NOT THE STYLESHEET. This is
    the fourth control in this window whose appearance is decided somewhere
    other than the sheet -- with the Windows-blue radio, the circular
    checkbox and the separator that drew its own frame. ⛔ A `color:` rule in
    `theme.py` for a link looks correct and is simply ignored, and the toolkit
    ships its own blue and its own visited-purple.

    ⚠ SO BOTH HALVES ARE SET: the inline style covers the rendered anchor and
    the palette covers `Link`/`LinkVisited`. ⛔ `LinkVisited` matters on its
    own -- without it a link a person has already followed turns purple and
    stops matching the theme, which Sonic reported on the surasura link.

    ⭐ Written once, here, because the window now has three of these and the
    palette dance was being copied. `setOpenExternalLinks` is what makes the
    click reach a browser rather than doing nothing at all.
    """
    widget = label(u"<a href=\"%s\" style=\"%s\">%s</a>"
                   % (url, theme.LINK_CSS, text), name, parent)
    widget.setTextFormat(Qt.TextFormat.RichText)
    widget.setOpenExternalLinks(True)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor(theme.LINK))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(theme.LINK))
    widget.setPalette(palette)
    return widget


def open_in_player(path):
    u"""Hand a file to whatever the person opens that kind of file with.

    -> True when the shell accepted it.

    ⭐ Sonic, 2026-09-18: *"if you click somewhere on the newly synced subs it
    opens up the file ... Not the sub file but the video file."* So this takes
    the VIDEO, never `output_path` -- the subtitle is the thing hato made, the
    video is the thing a person wants to watch.

    ⛔ NEVER RAISES, AND NEVER BLOCKS. `openUrl` hands off to the shell and
    returns; hato does not wait for a media player, does not learn which one
    it was, and is not responsible for what it does next.

    ⚠ A MISSING FILE IS A QUIET NO. The video may have been moved or deleted
    since the run -- rows outlive the files they describe. Refusing silently
    is right here: the person clicked a convenience, not a command, and an
    error dialog for *"the file you moved is moved"* is noise.
    """
    if not path:
        return False
    try:
        if not os.path.isfile(path):
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
    except Exception:                         # noqa: BLE001
        return False


def hrule(parent=None):
    u"""A 1px separator in the theme's own `--line`. -> QFrame

    🚨 NO `setFrameShape(HLine)`, AND THAT IS THE WHOLE POINT. Reported by
    Sonic, 2026-09-18: *"the white border separating each on the needs you tab
    ... stands out too much. Yes it needs to be separated but this is too
    much."*

    ⛔ **A QFrame with an HLine shape paints its OWN 3D frame from the widget
    PALETTE, on top of whatever the stylesheet set.** So this drew two stacked
    lines: Qt's, in near-white, above the correct one. Measured off the shipped
    screenshot -- a full row, 100% of the window's width, painted at `--ink`,
    the brightest token in the palette, with `--line` immediately beneath it.

    ⚠ The hex values are deliberately NOT written here: `theme.py` owns every
    literal and a check greps this file for one, without caring whether it sits
    in code or in a comment. That is the check being unfoolable, and it caught
    this docstring.

    ⭐ The fix is not a new value: `--line` is what `gui-mock/mock2.html`
    already specifies (`.pick { border-bottom: 1px solid var(--line) }`) and
    what Sonic approved. Removing the frame shape restores the ruled design;
    the background from `#pickrule` is the entire separator.

    ⚠ SAME CLASS AS THE WINDOWS-BLUE RADIO AND THE CIRCULAR CHECKBOX, and the
    third time this project has paid for it: **a control's appearance is
    decided somewhere you are not looking.** `LEDGER.md` §interface.
    """
    line = QFrame(parent)
    line.setObjectName(u"pickrule")
    line.setFixedHeight(1)
    return line


def clear(layout):
    u"""Empty a layout and delete what was in it.

    [!] `takeAt` alone LEAKS THE WIDGET AND LEAVES IT VISIBLE -- it is removed
    from the layout and re-parented to nothing in particular, so a re-render
    paints the new rows over the old ones.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


# ---------------------------------------------------------------------------
# the tab strip
# ---------------------------------------------------------------------------

class TabButton(QPushButton):
    u"""One tab. The Needs-you one carries the count."""

    def __init__(self, text, parent=None, with_badge=False):
        super().__init__(text, parent)
        self.setObjectName(u"tab")
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge = None
        if with_badge:
            self.badge = QLabel(u"0", self)
            self.badge.setObjectName(u"badge")
            self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.badge.setMinimumWidth(18)
            self.badge.setFixedHeight(18)

    def set_count(self, count):
        u"""[*] The count is PASSED IN, never computed here. One derivation."""
        if self.badge is None:
            return
        self.badge.setText(str(count))
        mark(self.badge, u"zero", count == 0)
        self.badge.adjustSize()
        self._place()

    def _place(self):
        u"""[!] QT CENTRES THE TEXT ALONE, not the text-plus-badge group.

        The first version subtracted the badge from the centring maths, which
        put the badge ON TOP of the label's last character -- the tab read
        *"Needs yo(2)"*. `sizeHint` already widens the button by the badge, so
        the text is centred in the wider button and the badge simply follows
        it. Caught by reading a shot; every assertion about the count was
        green, because the count was right.
        """
        if self.badge is None:
            return
        width = self.fontMetrics().horizontalAdvance(self.text())
        left = (self.width() - width) / 2.0 + width + 7
        left = min(left, self.width() - self.badge.width() - 2)
        self.badge.move(int(left),
                        int((self.height() - self.badge.height()) / 2))

    def sizeHint(self):
        hint = super().sizeHint()
        if self.badge is not None:
            hint.setWidth(hint.width() + self.badge.width() + 7)
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place()


# ---------------------------------------------------------------------------
# tab 1 -- Subtitles
# ---------------------------------------------------------------------------

class SubRow(Clickable):
    u"""[*] THREE THINGS: episode, percent, the file it was paired with.

    *"The run page is too confusing. Hide information, only show the %, the
    ones that were paired."* Six columns of evidence read as noise even when
    every column was true. Offsets, byte counts, segment counts and the
    verdict word all live behind this row.
    """

    def __init__(self, row, parent=None):
        super().__init__(parent, u"row")
        self.row = row
        box = QHBoxLayout(self)
        box.setContentsMargins(PAD - 2, 8, PAD, 8)
        box.setSpacing(GAP)

        self.ep = label(episode_text(row.get(u"episode")), u"ep", self)
        self.ep.setFixedWidth(COL_EP)

        percent = gui_run.match_percent(row)
        self.pc = label(u"—" if percent is None else u"%d%%" % percent,
                        u"pc", self)
        self.pc.setFixedWidth(COL_PC)
        self.pc.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter)
        mark(self.pc, u"tier", tier(row))

        self.nm = Elide(row.get(u"jimaku_filename") or u"", self, u"nm")
        self.nm.setFixedWidth(COL_NAME)

        #: [!] ON HOVER ONLY -- eight static markers down a calm list is eight
        #: things to look at for no information. Qt has no transition, so the
        #: fade is an opacity effect on the shared curve.
        self.chev = label(u"▶", u"chev", self)
        self.chev.setFixedWidth(COL_CHEV)
        self.chev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chev_fade = QGraphicsOpacityEffect(self.chev)
        self._chev_fade.setOpacity(0.0)
        self.chev.setGraphicsEffect(self._chev_fade)
        self._chev_anim = QVariantAnimation(self)
        self._chev_anim.setDuration(theme.FAST)
        self._chev_anim.setEasingCurve(ease())
        self._chev_anim.valueChanged.connect(
            lambda value: self._chev_fade.setOpacity(float(value)))
        self._expanded = False

        for widget in (self.ep, self.pc, self.nm, self.chev):
            box.addWidget(widget)
        box.addStretch(1)

    def _fade_chev(self, target):
        self._chev_anim.stop()
        self._chev_anim.setStartValue(self._chev_fade.opacity())
        self._chev_anim.setEndValue(target)
        self._chev_anim.start()

    def enterEvent(self, event):
        self._fade_chev(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._expanded:
            self._fade_chev(0.0)
        super().leaveEvent(event)

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        mark(self, u"expanded", self._expanded)
        mark(self.chev, u"on", self._expanded)
        self.chev.setText(u"▼" if self._expanded else u"▶")
        self._chev_fade.setOpacity(1.0 if self._expanded else 0.0)


def detail_panel(row, parent=None):
    u"""Everything the row does not show, revealed on click.

    [*] THE INFORMATION WAS NOT CUT, IT WAS MOVED. Every field here was on the
    row in round 1 and the row read as noise; behind a click it reads as
    depth. Values are tsubasa's own, passed through verbatim.
    """
    panel = Styled(parent, u"detail")
    grid = QGridLayout(panel)
    grid.setContentsMargins(DETAIL_INDENT, 2, PAD, 14)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(4)
    grid.setColumnStretch(1, 1)

    tsu = row.get(u"tsubasa") or {}
    lines = []

    segments = tsu.get(u"segments") or ()
    if segments:
        shifts = []
        for segment in segments:
            try:
                start, offset = segment[0], segment[1]
            except (TypeError, IndexError):
                continue
            piece = u"%+.2f s" % float(offset)
            if start:
                piece += u" from %s" % start
            shifts.append(piece)
        if shifts:
            lines.append((u"shifted", u", then ".join(shifts), None))

    verdict = tsu.get(u"verdict_word")
    if verdict:
        tail = u" · %d segments" % len(segments) if len(segments) > 1 else u""
        lines.append((u"verdict", safe(verdict), tail))

    written = row.get(u"output_path")
    if written:
        lines.append((u"written", os.path.basename(written),
                      u", beside the video"))

    kept = row.get(u"kept_path")
    if kept:
        size = kb(row.get(u"bytes_downloaded"))
        lines.append((u"original kept",
                      (size + u", ") if size else u"", u"in hato's own folder"))

    reference = tsu.get(u"reference_kind")
    if reference:
        lines.append((u"checked against", reference, None))

    if not lines:
        lines.append((u"note", safe(row.get(u"reason")) or u"nothing recorded",
                      None))

    for index, (key, value, tail) in enumerate(lines):
        grid.addWidget(label(key, u"detkey", panel), index, 0,
                       Qt.AlignmentFlag.AlignTop)
        strip = QWidget(panel)
        line = QHBoxLayout(strip)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        lead = label(value, u"detval", strip)
        mark(lead, u"lead", tail is not None)
        line.addWidget(lead)
        if tail:
            line.addWidget(label(tail, u"detval", strip))
        line.addStretch(1)
        grid.addWidget(strip, index, 1)

    # ⭐ OPEN THE VIDEO. Sonic, 2026-09-18: *"if you click somewhere on the
    # newly synced subs it opens up the file ... Not the sub file but the
    # video file ... i just want it simple as a simple option. Without messing
    # with the ux."*
    #
    # 🚨 SO IT IS ADDITIVE, AND THAT IS THE WHOLE DESIGN. The row's own click
    # already means *expand*, and stealing it would trade one convenience for
    # a worse one. ⛔ Nor is it a double-click: a second, invisible meaning on
    # the same target is a feature nobody discovers and everybody triggers by
    # accident. It is a plain control, inside the panel the click already
    # opens, where there is room for it.
    #
    # 🚨 A `stat`, AND THE COMMENT THAT USED TO BE HERE WAS FICTION. It said
    # *"`gone` is hato's OWN flag ... computed during the run"* and asserted
    # that as measured fact. ⛔ `report.as_dict()` is the only thing that
    # builds a row and it has no `gone` key at all -- the guard was dead code,
    # true in one hand-made test fixture and nowhere in the product. So the
    # button appeared on every row including videos that had been moved or
    # deleted, and clicking it did nothing and said nothing.
    #
    # ⚠ ONE `stat`, ONLY WHEN A ROW IS EXPANDED. That is a click, not a
    # render loop -- and a row genuinely outlives the file it describes, so
    # the question has to be asked of the disk rather than of the run.
    video = row.get(u"video")
    if video and os.path.isfile(video):
        open_it = button(u"Open video", panel)
        open_it.setObjectName(u"openvid")
        open_it.clicked.connect(
            lambda _checked=False, path=video: open_in_player(path))
        grid.addWidget(open_it, len(lines), 1,
                       Qt.AlignmentFlag.AlignLeft)
    return panel


# ---------------------------------------------------------------------------
# tab 2 -- Needs you
# ---------------------------------------------------------------------------

class PickHead(Clickable):
    u"""The collapsed line of one needs-a-pick row.

    [*] THE GARNET IS A 2px LEFT EDGE AND THAT IS THE WHOLE TREATMENT. In its
    own tab a failure does not have to be findable among nineteen successes.
    Once paired the edge turns green and the line REPORTS WHAT WAS CHOSEN --
    a collapsed row still says what happened to it, which is what makes the
    accordion safe to collapse.
    """

    def __init__(self, row, parent=None):
        super().__init__(parent, u"pickhead")
        self.row = row
        box = QHBoxLayout(self)
        box.setContentsMargins(PAD, 12, PAD, 12)
        box.setSpacing(GAP)

        self.ep = label(episode_text(row.get(u"episode")), u"ep", self)
        self.ep.setFixedWidth(COL_EP)

        who = QWidget(self)
        line = QHBoxLayout(who)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(5)
        title = Elide(row.get(u"title") or row.get(u"name") or u"", who, u"who")
        #: [!] NO STRETCH ON THE TITLE, and the stretch goes AFTER the season.
        #: Given the stretch, the title expanded to the full 560px column and
        #: shoved *"· 3rd Season"* to the far right, 600px from the show it
        #: belongs to -- the same *number-marooned-from-its-subject* fault the
        #: capped measure exists to prevent, rebuilt inside one cell.
        line.addWidget(title, 0)
        season = row.get(u"season")
        if season:
            line.addWidget(label(u"· %s" % season, u"whoi", who))
        line.addStretch(1)
        who.setFixedWidth(COL_WHO)

        self.best = Elide(u"", self, u"best")
        self.best.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)

        box.addWidget(self.ep)
        box.addWidget(who)
        box.addWidget(self.best, 1)

    def set_state(self, picked, tried, best_rate):
        u"""[*] Idle says what was tried; paired NAMES THE FILE IT USED."""
        done = picked is not None
        mark(self, u"done", done)
        mark(self.best, u"done", done)
        if done:
            self.best.setText(u"paired · %s" % picked)
        else:
            self.best.setText(u"%d tried · best %s"
                              % (tried, rate_text(best_rate)))


class CandidateCard(Clickable):
    u"""One file hato already downloaded for this episode.

    [!] CLICKING IT IS THE ACTION. Sonic: *"if they click on one, it should
    count as 'use this pair'."* No confirm button -- that is a second click
    for a decision already made. Safety comes from REVERSIBILITY: the row can
    be reopened and re-picked, and a wrong pick is still refused by the timing
    check rather than written.
    """

    def __init__(self, attempt, parent=None):
        super().__init__(parent, u"cand")
        self.attempt = attempt
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 9, 12, 9)
        box.setSpacing(GAP)

        stack = QWidget(self)
        column = QVBoxLayout(stack)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        name = attempt.get(u"name") or u""
        column.addWidget(Elide(name, stack, u"nm2"))
        size = kb(attempt.get(u"bytes"))
        sub = group_of(name) + ((u" · " + size) if size else u"")
        column.addWidget(label(sub, u"candsub", stack))

        rate = label(rate_text(attempt.get(u"match_rate")), u"rate", self)
        rate.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)

        box.addWidget(stack, 1)
        box.addWidget(rate)
        lift(self)

    def set_chosen(self, chosen):
        mark(self, u"chosen", bool(chosen))


# ---------------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------------

class KeyDialog(QDialog):
    u"""Where a person types the jimaku key.

    🚨 HAND-BUILT, AND THAT IS THE POINT. Sonic, 2026-09-18: *"when you hit add
    a key for the jimaku key it is white and ugly."* It was a `QInputDialog` --
    a native control, themed by Qt and not by hato, sitting in the middle of a
    dark coral app. Same rule as the Windows-blue radio and the circular
    checkbox: **a control's appearance is decided somewhere you are not
    looking**, and the fix is always to own it.

    ⛔ THE VALUE NEVER LEAVES THIS OBJECT except to the caller. It is not put on
    the window's state, not logged, and not passed in an argv -- a command line
    is readable by every other process on the machine.
    """

    def __init__(self, parent=None, replacing=False):
        super().__init__(parent)
        self.setWindowTitle(u"jimaku key")
        self.setModal(True)
        self.setStyleSheet(theme.qss())
        self.setMinimumWidth(460)

        box = QVBoxLayout(self)
        box.setContentsMargins(GAP, 16, GAP, 14)
        box.setSpacing(12)

        lead = label(u"Swap the jimaku key" if replacing
                     else u"Add your jimaku key", u"emptylead", self)
        box.addWidget(lead)

        box.addWidget(paragraph(
            u"Get one at jimaku.cc → Account → Developer Access. hato keeps it "
            u"in its own folder — never in the project, never in a config "
            u"file, and never in a log.", self))

        self._field = QLineEdit(self)
        self._field.setObjectName(u"filter")
        # ⚠ A SECRET BEING TYPED ON A SCREEN SOMEBODY MAY BE SHARING.
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._field.setPlaceholderText(u"paste the key here")
        box.addWidget(self._field)

        row = QWidget(self)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(9)
        line.addStretch(1)
        cancel = button(u"Cancel", row)
        cancel.clicked.connect(self.reject)
        line.addWidget(cancel)
        save = button(u"Swap the key" if replacing else u"Save the key",
                      row, accent=True)
        save.clicked.connect(self.accept)
        line.addWidget(save)
        box.addWidget(row)

        # ⭐ Enter saves. A one-field dialog that needs the mouse is a dialog
        # that gets in the way.
        self._field.returnPressed.connect(self.accept)
        self._field.setFocus()

    def value(self):
        u"""-> what was typed, stripped. ⛔ Never stored anywhere else."""
        return self._field.text().strip()


class HatoWindow(Styled):
    u"""hato's window.

    [X] It decides nothing. `run.py` owns the subprocess, the argv and the
    outcome words; `State` owns every number on screen; this class arranges
    widgets and calls `render()`.
    """

    def __init__(self, state=None, parent=None):
        super().__init__(parent, u"window")
        self.state = state if state is not None else State()
        #: The one place a child process is ever started. Tests replace it and
        #: assert the argv, so a check about what a click COMMITS never has to
        #: spawn anything.
        self.spawn = self._spawn
        self._runner = None
        self._timer = None
        self._accordions = {}
        self._details = {}

        self.setWindowTitle(u"hato")
        self.resize(WIN_W, WIN_H)
        #: [!] WITHOUT THIS THE DROP HANDLERS BELOW ARE NEVER CALLED -- Qt
        #: does not deliver a drag to a widget that has not asked for one, so
        #: the code would be present, correct and completely inert.
        self.setAcceptDrops(True)
        icon = branding.app_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_title())
        outer.addWidget(self._build_tabs())
        outer.addWidget(self._build_body(), 1)
        outer.addWidget(self._build_footer())

        self.setStyleSheet(theme.qss())
        self.render()

    # -- title bar ---------------------------------------------------------

    def _build_title(self):
        bar = Styled(self, u"titlebar")
        box = QHBoxLayout(bar)
        box.setContentsMargins(PAD, 14, PAD, 13)
        box.setSpacing(13)

        self.mark_label = QLabel(bar)
        self.mark_label.setFixedSize(theme.MARK_PX, theme.MARK_PX)
        self.mark_label.setScaledContents(False)
        self.mark_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = branding.mark_pixmap(theme.MARK_PX,
                                      self.devicePixelRatioF())
        if pixmap is not None and not pixmap.isNull():
            self.mark_label.setPixmap(pixmap)
        box.addWidget(self.mark_label)

        names = QWidget(bar)
        column = QVBoxLayout(names)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        wordmark = QWidget(names)
        pair = QHBoxLayout(wordmark)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(0)
        #: [X] TWO LABELS, NOT ONE WITH INLINE HTML. A `<span style="color:...">`
        #: would be a colour literal in this file; QSS colours them instead.
        pair.addWidget(label(u"ha", u"wordmarkHa", wordmark))
        pair.addWidget(label(u"to", u"wordmarkTo", wordmark))
        pair.addStretch(1)
        column.addWidget(wordmark)
        self.titlesub = label(u"", u"titlesub", names)
        column.addWidget(self.titlesub)
        box.addWidget(names)
        box.addStretch(1)

        box.addWidget(label(u"runs automatically at", u"autolabel", bar))
        self.autotime = label(u"", u"autotime", bar)
        box.addWidget(self.autotime)
        self.auto_switch = Switch(bar)
        self.auto_switch.setToolTip(wrap(
            u"Registers or removes the Windows scheduled task. hato is woken "
            u"at that time and exits when it is done, so nothing of it sits "
            u"running in between."))
        self.auto_switch.clicked.connect(self._toggle_auto)
        box.addWidget(self.auto_switch)
        self.run_now = button(u"Run now", bar, accent=True)
        self.run_now.setToolTip(wrap(
            u"Scans every watched folder now for videos with no Japanese "
            u"subtitle, and works through whatever it finds."))
        self.run_now.clicked.connect(self.start_run)
        box.addWidget(self.run_now)
        return bar

    # -- tabs --------------------------------------------------------------

    def _build_tabs(self):
        strip = Styled(self, u"tabstrip")
        box = QHBoxLayout(strip)
        box.setContentsMargins(GAP, 0, GAP, 0)
        box.setSpacing(3)
        self.tab_buttons = {}
        #: [X] THIS ORDER IS RULED. *"the view should be in priority."*
        for key, text, badge in ((TAB_SUBS, u"Subtitles", False),
                                 (TAB_PICK, u"Needs you", True),
                                 (TAB_SET, u"Settings", False)):
            tab = TabButton(text, strip, with_badge=badge)
            tab.clicked.connect(lambda _checked=False, k=key: self.show_tab(k))
            self.tab_buttons[key] = tab
            box.addWidget(tab)

        # ⭐ THE WAY OUT, ON THE SAME LINE AS THE TABS. Sonic, 2026-09-18:
        # *"can we add something like this on the right side on the settings
        # line? That brings them to the github issues page as well as the
        # github?"*
        #
        # ⚠ RIGHT OF THE STRETCH, so they sit hard right whatever the window
        # width, and never crowd the tabs. ⛔ They are LINKS, not tabs -- no
        # `TabButton`, no underline, no badge: a person scanning this row must
        # not read them as a fourth and fifth place to go inside hato.
        box.addStretch(1)
        for text, url in ((u"Send feedback", ISSUES_URL),
                          (u"Star on GitHub", REPO_URL)):
            box.addWidget(link_label(text, url, u"tablink", strip))
            box.addSpacing(14)
        return strip

    # -- panes -------------------------------------------------------------

    def _pane(self, name):
        u"""A scrolling pane. -> (QScrollArea, the QVBoxLayout to fill)"""
        area = QScrollArea(self)
        area.setObjectName(name)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = Styled(area, u"pane")
        column = QVBoxLayout(inner)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        area.setWidget(inner)
        return area, column

    def _build_body(self):
        self.body = QStackedWidget(self)
        self.body.setObjectName(u"body")
        self.panes = {}
        self.pane_layouts = {}
        for key in TABS:
            area, column = self._pane(u"pane_" + key)
            self.panes[key] = area
            self.pane_layouts[key] = column
            self.body.addWidget(area)
        return self.body

    # -- footer ------------------------------------------------------------

    def _build_footer(self):
        foot = Styled(self, u"footer")
        box = QHBoxLayout(foot)
        box.setContentsMargins(PAD, 10, PAD, 10)
        box.setSpacing(13)

        live = QWidget(foot)
        line = QHBoxLayout(live)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(1)
        self.dot = PulseDot(live)
        line.addWidget(self.dot)
        self.live_label = label(u"", u"live", live)
        line.addWidget(self.live_label)
        box.addWidget(live)

        self.tally_labels = []
        #: [*] THREE TALLIES, ALL FROM `State.tallies()`. The middle one is the
        #: SAME number the tab badge shows, and it is read from the same call
        #: -- which is the defect the mock recorded against itself.
        for _ in range(3):
            box.addWidget(label(u"·", u"sep", foot))
            tally = label(u"", u"tally", foot)
            self.tally_labels.append(tally)
            box.addWidget(tally)

        box.addStretch(1)
        #: On the footer line, left of the cost. *"put the created by and
        #: github link to the left of the api calls so its all on one line."*
        credit = label(
            u"Created by SonicSandbox │ "
            u"<a href=\"%s\" style=\"%s\">GitHub</a>"
            % (REPO_URL, theme.LINK_CSS),
            u"credit", foot)
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setOpenExternalLinks(True)
        palette = credit.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(theme.LINK))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(theme.LINK))
        credit.setPalette(palette)
        box.addWidget(credit)

        self.right_label = label(u"", u"right", foot)
        box.addWidget(self.right_label)
        return foot

    # ------------------------------------------------------------------
    # render -- [*] the ONE place state reaches the screen
    # ------------------------------------------------------------------

    def render(self):
        state = self.state
        tallies = state.tallies()            # [*] ONE call. Two readers.

        self.titlesub.setText(
            u"%d folder%s · %d video%s%s"
            % (len(state.folders), u"" if len(state.folders) == 1 else u"s",
               state.video_total, u"" if state.video_total == 1 else u"s",
               (u" · last run %s" % state.last_run) if state.last_run
               else u""))
        self.autotime.setText(state.schedule)
        self.auto_switch.setChecked(state.auto)

        for key, tab in self.tab_buttons.items():
            mark(tab, u"selected", key == state.tab)
        self.tab_buttons[TAB_PICK].set_count(tallies[gui_run.NEEDS_YOU])
        self.body.setCurrentWidget(self.panes[state.tab])

        self._render_subs()
        self._render_pick()
        self._render_settings()

        self.live_label.setText(footer_status(state))
        self.dot.set_running(state.running)
        need = tallies[gui_run.NEEDS_YOU]
        self.tally_labels[0].setText(u"%d added" % tallies[gui_run.ADDED])
        self.tally_labels[1].setText(
            u"1 needs you" if need == 1 else u"%d need you" % need)
        self.tally_labels[2].setText(
            u"%d already had them" % tallies[gui_run.SKIPPED])
        calls = state.summary.get(u"api_calls", 0) or 0
        spent = seconds_text(state.summary.get(u"seconds"))
        self.right_label.setText(
            u"%d API call%s%s" % (calls, u"" if calls == 1 else u"s",
                                  (u" · " + spent) if spent else u""))

    # -- tab 1 -------------------------------------------------------------

    def _render_subs(self):
        column = self.pane_layouts[TAB_SUBS]
        clear(column)
        self._details = {}
        state = self.state

        # ⭐ NO FOLDERS IS ITS OWN STATE, and it is the only one that gets the
        # whole pane. Nothing else can be on this tab -- there is nothing to
        # scan -- so it is centred vertically between two stretches rather
        # than sitting at the top of an empty page.
        if not state.folders:
            column.addStretch(1)
            column.addWidget(self._no_folders())
            column.addStretch(1)
            return

        for title, season, rows, skipped in state.shows():
            column.addWidget(self._show_head(title, season, len(rows), rows))
            for row in rows:
                key = state.key(row)
                widget = SubRow(row, self.panes[TAB_SUBS].widget())
                widget.set_expanded(key in state.open_rows)
                widget.clicked.connect(
                    lambda k=key: self._toggle_row(k))
                column.addWidget(widget)
                panel = detail_panel(row, self.panes[TAB_SUBS].widget())
                panel.setVisible(key in state.open_rows)
                self._details[key] = panel
                column.addWidget(panel)
            if skipped:
                column.addWidget(self._quiet(
                    u"%d episode%s already had subtitles"
                    % (skipped, u"" if skipped == 1 else u"s"),
                    u"— nothing was requested for them"))

        for title, count in state.fully_skipped():
            column.addWidget(self._quiet(
                title, u"— already subtitled",
                tip=u"Every episode already carries a Japanese track, so it "
                    u"is already in sync and nothing was requested. %d video%s."
                    % (count, u"" if count == 1 else u"s")))

        #: [!] ZERO ROWS IS A REAL STATE, AND THREE DIFFERENT ONES -- a settled
        #: library, an empty folder, or nothing pairable. It must not look
        #: broken, so it says which.
        if not state.shows() and not state.fully_skipped():
            # ⚠ `state.folders` is always set by here -- the no-folders case
            # returned above. The branch that used to be here read as though
            # both were possible, which is how a dead condition outlives the
            # thing it was guarding.
            column.addWidget(self._empty(
                u"Nothing added yet.",
                u"Everything hato finds and syncs appears here."))
        column.addStretch(1)

    def _show_head(self, title, season, added, rows):
        head = Styled(self.panes[TAB_SUBS].widget(), u"showhead")
        box = QHBoxLayout(head)
        box.setContentsMargins(PAD, 13, PAD, 7)
        box.setSpacing(9)
        box.addWidget(label(title, u"showtitle", head))
        meta = []
        if season:
            meta.append(str(season))
        meta.append(u"%d added" % added)
        box.addWidget(label(u" · ".join(meta), u"showmeta", head))
        entry = rows[0].get(u"jimaku_entry") if rows else None
        calls = sum(int(row.get(u"api_calls") or 0) for row in rows)
        box.addWidget(info_dot(
            u"Matched to jimaku entry %s. %d API call%s for this show. "
            u"A show is looked up once and then remembered."
            % (entry if entry is not None else u"(none)", calls,
               u"" if calls == 1 else u"s"), head))
        box.addStretch(1)
        return head

    def _quiet(self, lead, tail, tip=None):
        u"""One quiet line, not nineteen pills. *"visible, but not the focus."*"""
        strip = Styled(self.panes[TAB_SUBS].widget(), u"quiet")
        box = QHBoxLayout(strip)
        box.setContentsMargins(PAD, 7, PAD, 12)
        box.setSpacing(8)
        box.addWidget(label(lead, u"hadb", strip))
        box.addWidget(label(tail, u"had", strip))
        if tip:
            box.addWidget(info_dot(tip, strip))
        box.addStretch(1)
        return strip

    def _no_folders(self):
        u"""The first thing a new install shows. -> a centred widget

        ⭐ SONIC, 2026-09-18: *"on the 'subtitles' section, if there are no
        folders then I want, centered in the center, the logo with the text 'no
        folders selected' and a button right there to 'add folders' that would
        add it. That way they can do it from there."*

        ⚠ THIS IS A DIFFERENT STATE FROM *"nothing added yet"*, and conflating
        them is what made the old one useless. A settled library with nothing
        new is a success; a library with no folders at all is a tool that
        cannot start, and the only thing it should show is the way to start it.
        ⛔ Telling somebody to *"add one in Settings"* is a signpost where the
        control itself fits.
        """
        host = QWidget(self.panes[TAB_SUBS].widget())
        box = QVBoxLayout(host)
        box.setContentsMargins(PAD, 0, PAD, 0)
        box.setSpacing(16)

        mark = QLabel(host)
        pixmap = branding.mark_pixmap(96, host.devicePixelRatioF())
        if not pixmap.isNull():
            mark.setPixmap(pixmap)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)

        lead = label(u"No folders selected", u"emptylead", host)
        lead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(lead, 0, Qt.AlignmentFlag.AlignHCenter)

        add = button(u"Add folders", host, accent=True)
        add.clicked.connect(self.choose_folder)
        box.addWidget(add, 0, Qt.AlignmentFlag.AlignHCenter)

        # ⚠ THE DROP IS REAL AND WOULD OTHERWISE BE INVISIBLE. The line this
        # state replaced was the only place the window said a folder could be
        # dropped on it, and an existing check was pinning that sentence -- it
        # went red on the rewrite, which is the check doing its job rather than
        # being in the way. Kept quiet, below the button: a second way in, not
        # a competing instruction.
        drop = label(u"or drop a folder anywhere on this window", u"hint", host)
        drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(drop, 0, Qt.AlignmentFlag.AlignHCenter)
        return host

    def _empty(self, lead, tail):
        strip = Styled(None, u"quiet")
        box = QVBoxLayout(strip)
        box.setContentsMargins(PAD, 24, PAD, 12)
        box.setSpacing(4)
        box.addWidget(label(lead, u"hadb", strip))
        box.addWidget(label(tail, u"had", strip))
        return strip

    def _toggle_row(self, key):
        if key in self.state.open_rows:
            self.state.open_rows.discard(key)
        else:
            self.state.open_rows.add(key)
        self.render()

    # -- tab 2 -------------------------------------------------------------

    def _render_pick(self):
        column = self.pane_layouts[TAB_PICK]
        clear(column)
        self._accordions = {}
        state = self.state
        host = self.panes[TAB_PICK].widget()

        rows = state.of(gui_run.NEEDS_YOU)
        for row in rows:
            key = state.key(row)
            attempts = candidates(row)
            best = None
            best_name = None
            for attempt in attempts:
                value = attempt.get(u"match_rate")
                if value is not None and (best is None or value > best):
                    best = value
                    best_name = attempt.get(u"name")

            head = PickHead(row, host)
            head.set_state(state.picked.get(key), len(attempts), best)
            head.clicked.connect(lambda k=key: self._toggle_pick(k))
            column.addWidget(head)

            body = Styled(host, u"cands")
            inner = QVBoxLayout(body)
            inner.setContentsMargins(CAND_INDENT, 2, PAD, 16)
            inner.setSpacing(6)
            #: [*] BEFORE ANY CLICK, THE OUTLINE IS hato's OWN RANKING -- the
            #: candidate it would have used. The ruled design shows it
            #: outlined, and the hint underneath says *"Click one to use it."*
            #: so the outline reads as a recommendation rather than as a
            #: choice already made. After a pick it moves to the file the
            #: person chose, which is what the shot of that state shows.
            chosen_name = state.picked.get(key) or best_name
            for attempt in attempts:
                card = CandidateCard(attempt, body)
                card.setFixedWidth(COL_CAND)
                card.set_chosen(chosen_name is not None
                                and attempt.get(u"name") == chosen_name)
                card.clicked.connect(
                    lambda k=key, a=attempt: self.commit_pair(k, a))
                inner.addWidget(card)
            inner.addWidget(self._pick_actions(row, key, body))
            accordion = Accordion(body, host)
            accordion.set_open(state.open_pick == key, animate=False)
            self._accordions[key] = accordion
            column.addWidget(accordion)
            column.addWidget(hrule(host))

        not_yet = state.of(gui_run.NOT_YET)
        if not_yet:
            names = u", ".join(
                u"%s %s" % (row.get(u"title") or u"", row.get(u"episode"))
                for row in not_yet[:4])
            strip = Styled(host, u"quiet")
            box = QHBoxLayout(strip)
            box.setContentsMargins(PAD, 14, PAD, 8)
            box.setSpacing(8)
            lead = label(
                u"%d episode%s not on jimaku yet"
                % (len(not_yet), u" is" if len(not_yet) == 1 else u"s are"),
                u"hadb", strip)
            #: [!] `setProperty` ALONE IS INVISIBLE -- a selector that has
            #: already been polished never re-evaluates. `mark` repolishes.
            mark(lead, u"kind", u"notfound")
            box.addWidget(lead)
            box.addWidget(label(
                u"— %s. hato will ask again tomorrow." % names,
                u"had", strip))
            box.addWidget(info_dot(
                u"A just-aired episode usually has no subtitle for hours or "
                u"days. hato waits a day before asking again rather than "
                u"burning requests, and there is nothing to pair in the "
                u"meantime.", strip))
            box.addStretch(1)
            column.addWidget(strip)

        broken = state.of(gui_run.FAILED)
        if broken:
            strip = Styled(host, u"quiet")
            box = QHBoxLayout(strip)
            box.setContentsMargins(PAD, 8, PAD, 8)
            box.setSpacing(8)
            lead = label(u"%d had a problem" % len(broken), u"hadb", strip)
            mark(lead, u"kind", u"notrack")
            box.addWidget(lead)
            #: [!] ENGINE PROSE. Through `safe()` before it reaches a widget.
            #: [!] AND IT NEEDS THE STRETCH FACTOR: added without one, beside a
            #: trailing `addStretch`, the eliding label was allotted ZERO width
            #: and the whole explanation rendered as nothing at all -- the line
            #: read *"1 had a problem"* and stopped. Present, correct, invisible.
            box.addWidget(Elide(
                u"— %s" % safe(broken[0].get(u"reason"), u"see the log"),
                strip, u"had"), 1)
            column.addWidget(strip)

        if not rows and not not_yet and not broken:
            column.addWidget(self._empty(
                u"Nothing needs you.",
                u"Episodes hato could not settle on its own land here."))
        column.addStretch(1)

    def _pick_actions(self, row, key, parent):
        strip = Styled(parent, u"acts")
        box = QHBoxLayout(strip)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(9)
        box.addWidget(label(u"Click one to use it.", u"hint", strip))
        #: [*] BLACKLIST STAYS A BUTTON. It is a DIFFERENT decision and must
        #: not be reachable by the same reflex as choosing a file.
        blacklist = button(u"Blacklist this video", strip)
        blacklist.clicked.connect(lambda _c=False, k=key: self.blacklist(k))
        box.addWidget(blacklist)
        offered = row.get(u"candidates_offered")
        tried = len(candidates(row))
        if offered is None or offered > tried:
            more = button(u"Try 3 more candidates", strip)
            more.clicked.connect(lambda _c=False, k=key: self.try_more(k))
            box.addWidget(more)
        box.addWidget(info_dot(
            u"These are the files hato already downloaded for this episode, "
            u"never the whole jimaku catalogue. Your pick is still checked "
            u"against the video's own timing, so a wrong one is not written "
            u"— and you can reopen this row and pick again.", strip))
        box.addStretch(1)
        return strip

    def _toggle_pick(self, key):
        u"""[*] ONE OPEN AT A TIME. The accordion is a single value."""
        self.state.open_pick = None if self.state.open_pick == key else key
        self._animate_accordions()

    def _animate_accordions(self):
        for key, accordion in self._accordions.items():
            want = self.state.open_pick == key
            if accordion.is_open() != want:
                accordion.set_open(want)

    # -- tab 3 -------------------------------------------------------------

    def _render_settings(self):
        column = self.pane_layouts[TAB_SET]
        clear(column)
        state = self.state
        host = self.panes[TAB_SET].widget()

        holder = Styled(host, u"set")
        stack = QVBoxLayout(holder)
        stack.setContentsMargins(PAD, PAD, PAD, PAD)
        stack.setSpacing(15)

        stack.addWidget(self._card_when(holder))
        stack.addWidget(self._card_folders(holder))
        stack.addWidget(self._card_key(holder))
        stack.addWidget(self._card_skips(holder))
        stack.addWidget(self._card_blacklist(holder))
        # ⭐ LAST, DELIBERATELY. Sonic: *"Not everyone's going to want this so I
        # don't want it to be the headliner. I want it to be down below in
        # settings."* An integration most people will not use sits under the
        # settings everybody does.
        stack.addWidget(self._card_surasura(holder))
        stack.addStretch(1)
        holder.setFixedWidth(COL_SET + 2 * PAD)

        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)
        row = QWidget(host)
        row.setLayout(wrapper)
        wrapper.addWidget(holder)
        wrapper.addStretch(1)
        column.addWidget(row)
        column.addStretch(1)

    def _card(self, title, parent, count=None):
        card = Styled(parent, u"card")
        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        head = Styled(card, u"cardhead")
        line = QHBoxLayout(head)
        line.setContentsMargins(GAP, 11, GAP, 10)
        line.setSpacing(8)
        #: Qt has no `text-transform`, so the string is upper-cased here and
        #: the tracking comes from the font, not the sheet.
        #: [!] `cardtitle`, NOT `cardhead`. The label and its container shared
        #: one object name, so `#cardhead { border-bottom }` drew a rule under
        #: the CARD and a second short one under the four words of the
        #: heading. Two widgets, one id, one border rule, two lines.
        heading = label(title.upper(), u"cardtitle", head)
        font = heading.font()
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        heading.setFont(font)
        line.addWidget(heading)
        if count:
            line.addWidget(label(u"· " + count, u"cardcount", head))
        line.addStretch(1)
        column.addWidget(head)
        inner = Styled(card, u"cardin")
        body = QVBoxLayout(inner)
        body.setContentsMargins(GAP, 13, GAP, 13)
        body.setSpacing(11)
        column.addWidget(inner)
        return card, body

    def _card_when(self, parent):
        card, body = self._card(u"When it runs", parent)
        top = QWidget(card)
        line = QHBoxLayout(top)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        switch = Switch(top)
        switch.setChecked(self.state.auto)
        switch.clicked.connect(self._toggle_auto)
        line.addWidget(switch)
        line.addWidget(label(u"every day at", None, top))
        self.time_field = QLineEdit(self.state.schedule, top)
        self.time_field.setObjectName(u"time")
        self.time_field.setFixedWidth(78)
        self.time_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_field.editingFinished.connect(self._set_schedule)
        line.addWidget(self.time_field)
        if self.state.next_run:
            line.addWidget(label(self.state.next_run, u"hint", top))
        line.addStretch(1)
        body.addWidget(top)
        body.addWidget(paragraph(
            u"Windows wakes hato at that time and it exits when it is done "
            u"— nothing sits running in the background. Each run finds "
            u"whatever is new.", card))

        body.addWidget(hrule(card))
        watch = QWidget(card)
        line = QHBoxLayout(watch)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        box = Check(watch)
        box.setChecked(self.state.watch)
        box.clicked.connect(self._toggle_watch)
        line.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)
        text = QWidget(watch)
        column = QVBoxLayout(text)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        first = QWidget(text)
        pair = QHBoxLayout(first)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(5)
        pair.addWidget(label(u"Watch for new videos and run", None, first))
        pair.addWidget(label(u"· 1 min after one appears", u"hint", first))
        pair.addWidget(info_dot(
            u"The wait lets a download finish before hato reads the file.\n\n"
            u"Best for finished shows. For a season still airing the subtitle "
            u"is published hours to days after the episode, so a run on "
            u"arrival finds nothing and records a miss that holds the retry "
            u"until tomorrow.\n\n"
            u"Watching needs hato in the tray. With this off, nothing of hato "
            u"is in memory between runs.", first))
        pair.addStretch(1)
        column.addWidget(first)
        second = QWidget(text)
        pair = QHBoxLayout(second)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(4)
        #: [!] MEASURED, NOT ESTIMATED. This line said *"~12 MB"* when nothing
        #: had measured it. A number in a UI is a claim.
        pair.addWidget(label(u"Sits in the tray · 13 MB", u"hint", second))
        pair.addWidget(info_dot(
            u"Measured, not estimated. 13.4 MB resident — and 12.7 MB of "
            u"that is Python itself, so the watching costs about 0.7 MB. No "
            u"window toolkit is loaded while it watches; the window is a "
            u"separate program that starts when you open it.", second))
        pair.addStretch(1)
        column.addWidget(second)
        line.addWidget(text, 1)
        body.addWidget(watch)

        # ⭐ START WITH WINDOWS. Sonic, 2026-09-18: *"I want the run at
        # startup. Ensure it's an option in hato as well in settings I can
        # adjust."*
        #
        # ⛔ THE CONTROL VANISHES WHERE IT WOULD BE MEANINGLESS -- there is no
        # login-items registry outside Windows, and a switch that cannot do
        # anything is worse than no switch.
        from hato import startup as _startup
        if _startup.supported():
            body.addWidget(hrule(card))
            body.addWidget(self._startup_row(card))
        return card

    def _startup_row(self, card):
        u"""The *start with Windows* switch. -> QWidget

        🚨 ITS STATE IS READ FROM WINDOWS, NEVER FROM A FILE hato WROTE.
        `hato/startup.py` explains why at length: a `config.toml` key would be
        a second answer to a question the registry already answers, and the
        two drift the moment somebody edits their startup items in Task
        Manager -- leaving this switch ON while nothing runs.

        ⚠ IT REGISTERS THE TRAY WATCHER, NOT THE WINDOW. Starting with the
        computer is about hato working while nobody is looking; throwing a
        window in somebody's face at every login is the opposite of that.
        """
        from hato import startup as _startup
        row = QWidget(card)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)

        try:
            on = _startup.is_enabled()
            stale = _startup.is_stale()
        except _startup.StartupError:
            on, stale = False, False

        box = Check(row)
        box.setChecked(on)
        box.clicked.connect(self._toggle_startup)
        line.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)

        text = QWidget(row)
        column = QVBoxLayout(text)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)

        first = QWidget(text)
        pair = QHBoxLayout(first)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(5)
        pair.addWidget(label(u"Start with Windows", None, first))
        pair.addWidget(label(u"· hato waits in the tray", u"hint", first))
        pair.addWidget(info_dot(
            u"hato adds itself to your own startup items, the same list "
            u"Task Manager shows. Nothing is installed and nothing needs "
            u"administrator rights.\n\n"
            u"It starts the tray watcher, not the window — so hato is "
            u"already watching when you sit down, and you open the window "
            u"from the tray when you want it.\n\n"
            u"Turning this off removes the entry.", first))
        pair.addStretch(1)
        column.addWidget(first)

        # ⚠ Only ever says something when there is something to say. A note
        # that is always present is a note nobody reads.
        note = getattr(self, u"_startup_note", u"")
        if not note and stale:
            note = (u"The startup entry points somewhere else — "
                    u"switch it off and on to repoint it here.")
        if note:
            column.addWidget(label(note, u"hint", text))

        line.addWidget(text, 1)
        return row

    def _toggle_startup(self):
        u"""⛔ ASKS WINDOWS what the state is rather than trusting the switch:
        the box was drawn from the registry and the registry may have changed
        since."""
        from hato import startup as _startup
        self._startup_note = u""
        try:
            _startup.set_enabled(not _startup.is_enabled())
        except _startup.StartupError as exc:
            # ⚠ Reported where the control is, not swallowed and not raised
            # into a traceback the person cannot read.
            self._startup_note = u"%s" % exc
        self.render()

    def _card_folders(self, parent):
        card, body = self._card(u"Folders", parent)
        for folder in self.state.folders:
            body.addWidget(self._path_line(card, folder, dot=True,
                                           on_remove=self._remove_folder))
        if not self.state.folders:
            body.addWidget(paragraph(
                u"None yet — hato has nothing to look at until one is "
                u"added.", card))
        tail = QWidget(card)
        line = QHBoxLayout(tail)
        line.setContentsMargins(0, 3, 0, 0)
        line.setSpacing(8)
        add = button(u"Add a folder…", tail)
        add.clicked.connect(self.choose_folder)
        line.addWidget(add)
        switch = Switch(tail)
        switch.setChecked(self.state.recurse)
        switch.clicked.connect(self._toggle_recurse)
        line.addWidget(switch)
        line.addWidget(label(u"look inside subfolders", u"hint", tail))
        line.addStretch(1)
        body.addWidget(tail)
        return card

    def _card_key(self, parent):
        card, body = self._card(u"jimaku key", parent)
        line = QWidget(card)
        box = QHBoxLayout(line)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        if self.state.key_hint:
            box.addWidget(label(u"●", u"dotok", line))
            box.addWidget(label(u"set, ending %s" % self.state.key_hint,
                                None, line))
        else:
            box.addWidget(label(u"Not set — hato cannot fetch anything "
                                u"until it is.", u"hint", line))
        box.addStretch(1)
        # ⭐ *"if there is a key the swap for a different key or something"* --
        # "Replace" reads like overwriting a file; a swap is what it is.
        key_button = button(u"Swap for a different key" if self.state.key_hint
                            else u"Add a key", line)
        key_button.clicked.connect(self.choose_key)
        box.addWidget(key_button)
        body.addWidget(line)
        # ⭐ WHAT JIMAKU ACTUALLY SAID, and only after a key was entered. A key
        # that RESOLVES is not a key that WORKS, and that is precisely the
        # difference somebody who has just pasted one is worried about.
        if self.state.key_status:
            body.addWidget(label(self.state.key_status,
                                 u"dotok" if self.state.key_ok else u"keybad",
                                 card))
        body.addWidget(paragraph(
            u"Kept in hato's own folder — never in the project and never "
            u"in a config file.", card))
        return card

    def _card_skips(self, parent):
        card, body = self._card(u"Skip these folders", parent)
        for folder in self.state.skip_folders:
            body.addWidget(self._path_line(card, folder, dot=False,
                                           on_remove=self._remove_skip))
        tail = QWidget(card)
        line = QHBoxLayout(tail)
        line.setContentsMargins(0, 2, 0, 0)
        line.setSpacing(8)
        skip = button(u"Add a folder to skip…", tail)
        skip.clicked.connect(self.choose_skip)
        line.addWidget(skip)
        line.addStretch(1)
        body.addWidget(tail)
        body.addWidget(paragraph(
            u"Carved out of the folders above, subfolders included. Useful "
            u"when a watched folder is broad — a Desktop with one work "
            u"directory in it.", card))
        return card

    def _path_line(self, parent, path, dot, on_remove):
        line = QWidget(parent)
        box = QHBoxLayout(line)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        if dot:
            box.addWidget(label(u"●", u"dotok", line))
        box.addWidget(Elide(path, line, u"code"), 1)
        remove = QPushButton(u"✕", line)
        remove.setObjectName(u"x")
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setFixedWidth(22)
        remove.setToolTip(wrap(u"Stop looking at %s." % path))
        remove.clicked.connect(lambda _c=False, p=path: on_remove(p))
        box.addWidget(remove)
        return line

    def _card_surasura(self, parent):
        u"""The surasura integration. ⭐ Last card, and quiet.

        Sonic: *"I want it to have the logo but show that it's an integration
        with it. Again keep it very clean."* So: the mark, one line saying what
        it does, the folder, and a way out. ⛔ No explanation of what surasura
        is -- somebody who does not run it does not need to be taught it, and
        somebody who does already knows.
        """
        card, body = self._card(u"surasura", parent)
        top = QWidget(card)
        line = QHBoxLayout(top)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(11)

        mark = QLabel(top)
        pixmap = branding.surasura_pixmap(28, top.devicePixelRatioF())
        if pixmap is not None and not pixmap.isNull():
            mark.setPixmap(pixmap)
        line.addWidget(mark)

        words = QWidget(top)
        stack = QVBoxLayout(words)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(2)
        stack.addWidget(label(u"Send a copy to surasura", None, words))
        # ⚠ `paragraph`, NOT a `hint` label: a QLabel does not wrap unless told,
        # and a check named for exactly that caught this sentence being cut at
        # "...into a Hato folder".
        stack.addWidget(paragraph(
            u"Every subtitle hato aligns is also copied into a Hato folder "
            u"inside the folder you choose.", words))
        # ⭐ THE WAY TO surasura ITSELF. Somebody reading this card who does not
        # run it has exactly one question -- what is it -- and a link answers
        # that better than a paragraph explaining it here would.
        # ⚠ The colour is INLINE: a widget under the app-wide stylesheet paints
        # links from Qt's palette, not from the sheet, which is how this one
        # came out as Qt's own dark visited-purple.
        link = label(
            u"<a href=\"https://github.com/SonicSandbox/surasura\" "
            u"style=\"%s\">github.com/SonicSandbox/surasura</a>"
            % theme.LINK_CSS, u"credit", words)
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)
        stack.addWidget(link)
        line.addWidget(words, 1)
        body.addWidget(top)

        if self.state.surasura_dir:
            body.addWidget(self._path_line(
                card, os.path.join(self.state.surasura_dir,
                                   u"Hato"),
                dot=True, on_remove=lambda _p: self.clear_surasura()))
        else:
            body.addWidget(label(u"Off — no folder chosen.", u"hint", card))

        tail = QWidget(card)
        row = QHBoxLayout(tail)
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(8)
        pick = button(u"Change folder…" if self.state.surasura_dir
                      else u"Choose a folder…", tail)
        pick.clicked.connect(self.choose_surasura)
        row.addWidget(pick)
        row.addStretch(1)
        body.addWidget(tail)
        return card

    def choose_surasura(self):
        u"""Pick where surasura should find the copies."""
        path = QFileDialog.getExistingDirectory(
            self, u"Choose the folder surasura reads from", u"",
            QFileDialog.Option.ShowDirsOnly)
        if not path:
            return None
        path = os.path.abspath(path)
        self.state.surasura_dir = path
        self.spawn(gui_run.argv_for_config(u"--set", u"surasura_dir=%s" % path))
        self.render()
        return path

    def clear_surasura(self):
        u"""Turn the integration off. ⛔ Nothing already copied is removed --
        those files are surasura's now, not hato's to take back."""
        self.state.surasura_dir = u""
        self.spawn(gui_run.argv_for_config(u"--set", u"surasura_dir="))
        self.render()

    def _card_blacklist(self, parent):
        rows = self.state.blacklist
        card, body = self._card(u"Never fetch for these", parent,
                                count=u"%d video%s" % (len(rows),
                                                       u"" if len(rows) == 1
                                                       else u"s"))
        body.setSpacing(9)
        #: [*] hato CLEANS IT, NOT THE PERSON. Sonic: *"it's likely they will
        #: not clean it as videos get rotated from there."* A blacklist row is
        #: keyed on the video's CONTENT HASH, so hato can tell exactly which
        #: rows point at a video that is no longer on disk -- and those are
        #: precisely the rows that accumulate. If you can tell which entries
        #: are dead, offering to remove them is the feature.
        gone = [row for row in rows if row.get(u"gone")]
        if gone:
            notice = Styled(card, u"stale")
            line = QHBoxLayout(notice)
            line.setContentsMargins(11, 9, 11, 9)
            line.setSpacing(12)
            text = QWidget(notice)
            wrapbox = QHBoxLayout(text)
            wrapbox.setContentsMargins(0, 0, 0, 0)
            wrapbox.setSpacing(4)
            wrapbox.addWidget(label(
                u"%d of these are no longer on this machine" % len(gone),
                u"stalelead", text))
            tail = label(
                u"— rotated out of your library. They are keeping rows "
                u"nobody needs.", u"staletext", text)
            tail.setWordWrap(True)
            wrapbox.addWidget(tail, 1)
            line.addWidget(text, 1)
            sweep = button(u"Remove those %d" % len(gone), notice)
            sweep.clicked.connect(self.remove_stale_blacklist)
            line.addWidget(sweep)
            body.addWidget(notice)

        self.filter_field = QLineEdit(card)
        self.filter_field.setObjectName(u"filter")
        self.filter_field.setPlaceholderText(u"Filter by name or show…")
        palette = self.filter_field.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText,
                         QColor(theme.INK_FAINT))
        self.filter_field.setPalette(palette)
        body.addWidget(self.filter_field)

        if rows:
            listing = Styled(card, u"blist")
            inner = QVBoxLayout(listing)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(0)
            for entry in rows:
                inner.addWidget(self._bl_row(listing, entry))
            #: [!] CAPPED AND SCROLLED, and this ONE cap is deliberate: 34 rows
            #: today and it only grows, so without a ceiling Settings becomes a
            #: scroll marathon to reach anything below it. [X] Not the
            #: accordion's kind of cap -- nothing here is being CHOSEN.
            area = QScrollArea(card)
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(listing)
            area.setFixedHeight(186)
            body.addWidget(area)
        body.addWidget(paragraph(
            u"Your instruction, so nothing overrides it — not even Force. "
            u"Kept by the video's content, so renaming or moving a file does "
            u"not lose its place here.", card))
        return card

    def _bl_row(self, parent, entry):
        row = Styled(parent, u"blrow")
        box = QHBoxLayout(row)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(10)
        name = Elide(entry.get(u"name") or u"", row, u"blcode")
        mark(name, u"gone", bool(entry.get(u"gone")))
        if entry.get(u"gone"):
            font = name.font()
            font.setStrikeOut(True)
            name.setFont(font)
        box.addWidget(name, 1)
        note = Elide(entry.get(u"note") or u"", row, u"blnote")
        note.setFixedWidth(150)
        box.addWidget(note)
        when = label(entry.get(u"when") or u"", u"blwhen", row)
        when.setFixedWidth(46)
        when.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
        box.addWidget(when)
        remove = QPushButton(u"✕", row)
        remove.setObjectName(u"x")
        remove.setFixedWidth(20)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setToolTip(wrap(u"Fetch for this video again."))
        remove.clicked.connect(lambda _c=False, e=entry: self.unblacklist(e))
        box.addWidget(remove)
        return row

    # ------------------------------------------------------------------
    # actions -- every one of them goes out through `hato.gui.run`
    # ------------------------------------------------------------------

    #: How often the window checks whether somebody ELSE ran hato. ⚠ A `stat`,
    #: so it costs nothing; 3 s is well under the time it takes to notice.
    OTHERS_MS = 3000
    #: ⚠ Set before any timer exists, so `_drain` can note our own write even
    #: when nobody asked the window to follow other runs (the suite's case).
    _others_seen = 0.0

    def follow_other_runs(self, every_ms=None):
        u"""Notice runs this window did not start. -> the timer

        🚨 SONIC, 2026-09-18: *"once it runs automatically (from the tray or so)
        the UI doesn't update... I dragged a video into a folder, it worked but
        the ui didn't update -- it was until i hit run."*

        ⭐ THE TRAY, THE SCHEDULER AND A TERMINAL ARE ALL OTHER PROCESSES. hato
        now writes what every run found (`hato/lastrun.py`), so this is just a
        `stat` on that file: when its timestamp moves, somebody ran hato and
        the window reloads. ⛔ No channel between processes that were never
        meant to know about each other.

        ⚠ IT STANDS ASIDE DURING THIS WINDOW'S OWN RUN. That run is painting
        live rows from the stream; reloading the file underneath it would
        replace them with a snapshot taken a moment earlier.
        """
        self._others_seen = gui_run.last_run_stamp()

        def look():
            # ⭐ THE COUNTDOWN IS READ EVEN WHILE WE RUN -- it belongs to the
            # tray, and knowing a second run is queued behind this one is
            # useful rather than confusing.
            was = int(self.state.queued_in)
            self.state.queued_in, self.state.queued_names = gui_run.pending_run()
            if int(self.state.queued_in) != was:
                self.render()
            if self.state.running:
                return                        # ⛔ our own run owns the rows
            stamp = gui_run.last_run_stamp()
            if stamp == self._others_seen:
                return
            self._others_seen = stamp
            rows, summary, saved_at = gui_run.load_last_run()
            if not rows and not summary:
                return
            self.state.rows = rows
            self.state.summary = summary
            if len(saved_at) >= 16:
                self.state.last_run = saved_at[11:16]
            self.render()

        timer = QTimer(self)
        timer.timeout.connect(look)
        timer.start(int(every_ms or self.OTHERS_MS))
        self._others_timer = timer
        return timer

    def closeEvent(self, event):
        u"""Let go of everything this process was holding, then go.

        🚨 SONIC, 2026-09-18: *"close hato... then go to the tray to open it, it
        doesn't do anything, and when i click the shortcut it doesn't. I have to
        close hato from the tray. Then open it again."*

        ⭐ A WINDOW PROCESS WAS FOUND ALIVE WITH NO WINDOW, still holding the
        single-instance name -- so every later launch connected, believed a
        window was there, and exited. Nothing opened and nothing said why.
        ⚠ Four attempts failed to reproduce it on demand, so this does not rely
        on knowing WHY the process lingered: the name is released the moment the
        window closes, and the quit is asked for rather than assumed. Even a
        process that then refuses to die cannot swallow the next launch.

        ⛔ THE TRAY IS NOT TOUCHED. It is a separate process on purpose and must
        outlive this one -- that is the entire 13 MB argument.
        """
        server = getattr(self, "_instance_server", None)
        if server is not None:
            try:
                server.close()
                from PyQt6.QtNetwork import QLocalServer
                QLocalServer.removeServer(instance_name())
            except Exception:                 # noqa: BLE001 -- shutting down
                pass
            self._instance_server = None
        # ⚠ Ask the RUN to stop too: its reader threads are daemons and would
        # not hold the process, but the child would go on writing into pipes
        # nobody is draining.
        runner = getattr(self, "_runner", None)
        if runner is not None:
            try:
                runner.stop()
            except Exception:                 # noqa: BLE001
                pass
        super().closeEvent(event)
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def show_tab(self, key):
        if key in TABS:
            self.state.tab = key
            self.render()

    # -- drag a folder onto it ---------------------------------------------
    # [*] RULED, and it is the folder picker at zero cost (`05-interface.md`:
    # *"Drag a folder onto it"*). [!] IT IS ALSO A PROMISE THE EMPTY STATE
    # ALREADY MAKES -- *"Add one in Settings, or drop a folder on this
    # window."* Copy that describes a capability the build does not have is
    # the worst of the three options, so this is here rather than the sentence
    # being softened.

    def dragEnterEvent(self, event):
        if self._folders_in(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._folders_in(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders = self._folders_in(event.mimeData())
        if not folders:
            return
        event.acceptProposedAction()
        self.add_folders(folders)

    @staticmethod
    def _folders_in(mime):
        u"""-> the DIRECTORIES among what was dropped. [X] Files are ignored.

        hato watches folders; a dropped video would have to become a folder to
        mean anything, and guessing which folder was meant is the window
        deciding.
        """
        if mime is None or not mime.hasUrls():
            return []
        out = []
        for url in mime.urls():
            path = url.toLocalFile()
            if path and os.path.isdir(path):
                out.append(os.path.abspath(path))
        return out

    def add_folders(self, folders):
        u"""Watch these, then look at them. -> the folders actually added

        [X] Written through `hato config`, like every other setting -- the
        window never edits `config.toml` itself.

        [!] AND IT FILTERS HERE, NOT ONLY IN `dropEvent`. The first version put
        the is-a-directory guard on the drop path alone, so this method --
        which is public, and is the one Settings' *"Add a folder..."* reaches
        -- happily added a `.mkv`. A guard on one side of a join is the
        documented seam defect: both callers are correct in isolation and the
        pair is wrong.
        """
        folders = [os.path.abspath(f) for f in folders if f and os.path.isdir(f)]
        fresh = [f for f in folders if f not in self.state.folders]
        if not fresh:
            return []
        flags = []
        for folder in fresh:
            flags.extend([u"--add-folder", folder])
        self.state.folders = list(self.state.folders) + fresh
        self.spawn(gui_run.argv_for_config(*flags))
        self.render()
        self.start_run()
        return fresh

    def add_skips(self, folders):
        u"""Carve these out of the watched folders. -> the ones actually added.

        ⚠ The sibling of `add_folders`, and it filters the same way for the
        same reason -- a guard on one side of a join is the seam defect that
        method's own note records.
        """
        folders = [os.path.abspath(f) for f in folders if f and os.path.isdir(f)]
        fresh = [f for f in folders if f not in self.state.skip_folders]
        if not fresh:
            return []
        flags = []
        for folder in fresh:
            flags.extend([u"--add-skip", folder])
        self.state.skip_folders = list(self.state.skip_folders) + fresh
        self.spawn(gui_run.argv_for_config(*flags))
        self.render()
        return fresh

    def set_key(self, value, timeout=20.0):
        u"""Put a jimaku key in hato's own file. -> True when one was SAVED.

        🚨 THROUGH STDIN, NEVER A FILE AND NEVER argv. `hato key --set-from -`
        exists for this: a GUI field that had to write the secret to a temp
        file first would put a second copy on disk, and a key in `argv` is
        readable by every other process through the process table.
        ⛔ The value is not kept on `self` either -- only the hint hato reads
        back.
        """
        value = (value or u"").strip()
        if not value:
            return False
        process = self.spawn(
            gui_run.cli_argv() + [u"key", u"--set-from", u"-", u"--json"],
            stdin_text=value + u"\n")
        # 🚨 WAIT FOR THE WRITE, AND READ ITS VERDICT. ⛔ This used to spawn and
        # `return True` unconditionally, which was wrong twice over. The card
        # showed a hint for a key that may never have been saved -- and worse,
        # `choose_key` went straight on to `hato key --test`, so on the SWAP
        # path the test could read the OLD, still-valid key from the keystore
        # and report *"Connected"* about a brand-new bad one. ⛔ That is the
        # exact failure this feature exists to prevent. Found by the
        # adversarial pass, 2026-09-18 (F-A02 / F-B05 / F-B10).
        #
        # ⚠ `process` is None when the seam is a check that does not model a
        # child at all -- those checks assert argv, not the write.
        if process is not None:
            try:
                process.communicate(timeout=timeout)
            except Exception:                 # noqa: BLE001
                try:
                    process.kill()
                except Exception:             # noqa: BLE001
                    pass
                return False
            if getattr(process, "returncode", 0):
                return False
        # ⚠ Only the LAST FOUR, and only what hato itself would print. The
        # window never holds the key. ⭐ And only once the write has SUCCEEDED.
        self.state.key_hint = u"…" + value[-4:] if len(value) >= 4 else u""
        self.render()
        return True

    # -- the three controls that ask the person for something --------------
    #
    # 🚨 ALL THREE WERE INERT AND SHIPPED (2026-09-18). The buttons were built,
    # rendered perfectly, and were never connected to anything -- Sonic:
    # *"nothing happens when i click on add a folder."* `add_folders()` already
    # existed, was correct, and even documented itself as *"the one Settings'
    # 'Add a folder...' reaches"*. The prose asserted a wiring that was not
    # there, and 122 checks proved the API without ever clicking a button.
    # ⭐ `build-ui.md` records this exact failure shipping THREE times in one
    # build for the same reason. `test_gui_widgets.py` now walks every
    # QPushButton in the built window and fails on any with no connection.

    def choose_folder(self):
        u"""Ask for a folder to watch, then watch it."""
        path = QFileDialog.getExistingDirectory(
            self, u"Choose a folder of videos for hato to watch", u"",
            QFileDialog.Option.ShowDirsOnly)
        if path:
            self.add_folders([path])

    def choose_skip(self):
        u"""Ask for a folder to leave alone."""
        path = QFileDialog.getExistingDirectory(
            self, u"Choose a folder hato should never look inside", u"",
            QFileDialog.Option.ShowDirsOnly)
        if path:
            self.add_skips([path])

    def verify_key(self, timeout=30.0):
        u"""Ask jimaku whether the saved key works. -> (ok, message)

        ⭐ ONE METERED REQUEST, through `hato key --test`. ⛔ Not on launch and
        not on every render -- Sonic: *"just on the key entry, not another
        time."*
        """
        argv = gui_run.cli_argv() + [u"key", u"--test", u"--json"]
        process = self.spawn(argv)
        try:
            out, _err = process.communicate(timeout=timeout)
        except Exception:                     # noqa: BLE001
            try:
                process.kill()
            except Exception:                 # noqa: BLE001
                pass
            return False, u"the check did not finish"
        # ⛔ `run.py` PARSES. It owns every conversation with the CLI, and
        # decoding the answer here would be the window holding a second opinion
        # about it. ⚠ A check greps this file for the decoder's name and does
        # not care whether the hit is code or a comment -- it caught the first
        # version of this method, and then caught the comment explaining it.
        answer = gui_run.parse_answer(out)
        if not answer:
            return False, u"hato gave an answer this window could not read"
        if answer.get(u"connected"):
            return True, u"Connected — the key works"
        return False, answer.get(u"error") or u"jimaku would not accept it"

    def choose_key(self):
        u"""Ask for the jimaku key, save it, then prove it works.

        ⭐ SONIC, 2026-09-18: *"if it works it should test run it to see if
        connected, and show that it is connected just fine... And if there is a
        key the swap for a different key or something."*

        ⚠ A KEY THAT SAVES IS NOT A KEY THAT WORKS, and the moment somebody
        pastes one is the moment that distinction matters. The check spends one
        metered request and answers the only question they have.

        ⛔ A HAND-BUILT DIALOG, NOT `QInputDialog`. Sonic: *"when you hit add a
        key for the jimaku key it is white and ugly."* A native dialog is themed
        by Qt, not by hato -- the same rule as the Windows-blue radio, and the
        third time this project has paid for it. This one wears the app's own
        sheet.
        """
        dialog = KeyDialog(self, replacing=bool(self.state.key_hint))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        value = dialog.value()
        if not value:
            return None
        if not self.set_key(value):
            # ⛔ NEVER TEST A KEY THAT DID NOT SAVE. `hato key --test` reads the
            # KEYSTORE, not the field -- so testing after a failed write asks
            # about whatever was there before. On the swap path that is the
            # OLD, still-valid key, and the window would report *"Connected"*
            # about a key that never landed. (F-B05.)
            self.state.key_status = u"the key could not be saved"
            self.state.key_ok = False
            self.render()
            return False
        ok, message = self.verify_key()
        self.state.key_status = message
        self.state.key_ok = ok
        self.render()
        return ok

    def pair_argv(self, key, attempt):
        u"""What committing this pair would run. -> [unicode] or None

        [X] `run.argv_for_pair` builds it -- this method only finds the two
        paths. A second argv builder is a second program.
        """
        row = None
        for candidate in self.state.rows:
            if self.state.key(candidate) == key:
                row = candidate
                break
        if row is None:
            return None
        subtitle = candidate_path(attempt)
        video = row.get(u"video")
        if not subtitle or not video:
            return None
        return gui_run.argv_for_pair(video, subtitle)

    def commit_pair(self, key, attempt):
        u"""[!] THE CLICK IS THE ACTION. No confirm button.

        The row collapses to green naming the file it used, the next
        unresolved row opens as this one closes, and `hato sync` is handed the
        explicit pair. [X] The timing verdict still rules and still refuses a
        wrong pair -- a person choosing replaces hato's RANKING, not the
        engine's check.
        """
        argv = self.pair_argv(key, attempt)
        if argv is None:
            return None
        self.state.picked[key] = attempt.get(u"name") or u""
        self.state.open_pick = self.state.next_unresolved(key)
        self.render()
        self._animate_accordions()
        self.spawn(argv)
        return argv

    def blacklist(self, key):
        u"""[*] A DIFFERENT DECISION, and deliberately a different gesture.

        [!] THE VIDEO IS A POSITIONAL, NOT A SUBCOMMAND. The first version of
        this built `blacklist add <video>`, inventing an `add` verb the CLI
        does not have -- `hato/commands/blacklist.py` takes the video
        positionally and spells removal `--remove`. The window would have
        handed the child the literal string `add` as the video to blacklist.
        Caught by reading the command's own `register()`, not by a check: the
        suite only asserted that the word *blacklist* appeared.
        """
        argv = gui_run.cli_argv() + [u"blacklist", key, u"--json"]
        self.spawn(argv)
        return argv

    @staticmethod
    def _blacklist_id(entry):
        u"""What to hand `--remove` for this row. -> str

        ⭐ THE STORED PATH FIRST, and it is what makes a STALE row removable at
        all. `hato blacklist --remove` hashes the file to find the row -- and
        the rows worth cleaning are precisely the ones whose video is no longer
        on disk, so the hash cannot be taken. The command already handles that:
        it falls back to matching the stored `video_path`. ⛔ Hand it the bare
        display name and there is nothing for either route to match.
        """
        return entry.get(u"path") or entry.get(u"name") or u""

    def unblacklist(self, entry):
        u"""Put one video back. -> the argv, or None.

        🚨 THIS BUTTON WAS INERT AND SHIPPED. Every `✕` on a blacklist row was
        built, styled, given a tooltip promising *"Fetch for this video
        again"* -- and connected to nothing. Found by the wiring check, not by
        Sonic, who had only reported the three in the cards above it.
        """
        target = self._blacklist_id(entry)
        if not target:
            return None
        self.state.blacklist = [row for row in self.state.blacklist
                                if row is not entry]
        argv = gui_run.cli_argv() + [u"blacklist", u"--remove", target,
                                     u"--json"]
        self.spawn(argv)
        self.render()
        return argv

    def remove_stale_blacklist(self):
        u"""⭐ SONIC'S RULING: *"the blacklist list may get long... it's likely
        they will not clean it as videos get rotated from there."* So hato
        finds the rows whose video is gone and offers them in ONE action --
        the person never prunes a list by hand.

        ⛔ ONLY the rows hato itself marked gone. A cleanup that took a row it
        was not sure about would be the app deciding something the person did.
        """
        gone = [row for row in self.state.blacklist if row.get(u"gone")]
        if not gone:
            return []
        sent = []
        for entry in gone:
            target = self._blacklist_id(entry)
            if not target:
                continue
            argv = gui_run.cli_argv() + [u"blacklist", u"--remove", target,
                                         u"--json"]
            self.spawn(argv)
            sent.append(argv)
        self.state.blacklist = [row for row in self.state.blacklist
                                if not row.get(u"gone")]
        self.render()
        return sent

    def try_more(self, key):
        u"""*"Try 3 more candidates"* -- one more run of this video alone."""
        row = None
        for candidate in self.state.rows:
            if self.state.key(candidate) == key:
                row = candidate
                break
        if row is None:
            return None
        offered = len(candidates(row)) + 3
        argv = gui_run.argv_for([os.path.dirname(key) or key],
                                candidates=offered, progress=True)
        self.spawn(argv)
        return argv

    def _toggle_auto(self):
        self.state.auto = not self.state.auto
        self.spawn(gui_run.argv_for_config(
            u"--set", u"schedule=%s" % (self.state.schedule
                                        if self.state.auto else u"off")))
        self.render()

    def _toggle_watch(self):
        u"""Turn the tray watcher on or off -- and actually do it.

        🚨 REPORTED BY SONIC, 2026-09-18: *"When i toggled the option and when
        i closed out, i didn't see hato enter the windows tray."* He was right,
        and the tick was broken THREE ways at once:

          1. `watch` was not in `config.py`'s schema, so `--set watch=true` was
             REFUSED by name.
          2. ⛔ The window never reads a child's exit code, so that refusal was
             invisible. The box ticked, nothing was saved, nothing said so.
          3. Nothing started the watcher. Even a saved setting only records an
             intention; `python -m hato.watch` is a PROCESS and somebody has to
             spawn it.

        ⭐ Each of the three alone is enough to make the control a lie, and the
        first two are the documented *"offered Sonic a setting that did
        nothing"* failure. A check now asserts every `--set` key the window
        sends exists in the schema.
        """
        self.state.watch = not self.state.watch
        self.spawn(gui_run.argv_for_config(
            u"--set", u"watch=%s" % (u"true" if self.state.watch else u"false")))
        if self.state.watch:
            self.start_watcher()
        else:
            self.stop_watcher()
        self.render()

    def start_watcher(self):
        u"""Put hato in the tray. -> the argv sent, or None if one is already
        there.

        ⛔ A SEPARATE PROCESS, AND IT OUTLIVES THIS WINDOW. That is the whole
        point of it: the watcher is 13.4 MB of `ctypes` with no toolkit, where
        this window is ~78 MB of Qt. Closing the window must leave the tray
        icon exactly where it was.

        ⚠ AND ONLY ONE. Two watchers on one folder means two runs racing for
        hato's run lock every time a file lands -- so an already-running one is
        left alone rather than doubled.
        """
        from hato import watch as _watch
        if _watch.watching_pid():
            return None
        argv = _watch.watch_argv()
        self.spawn(argv, detached=True)
        return argv

    def stop_watcher(self):
        u"""Take hato out of the tray. -> the pid stopped, or None.

        ⚠ The window cannot hold the watcher's handle: the watcher is meant to
        outlive it, so across sessions there is nothing in memory to stop. The
        pid file is how a later window finds the one that is running -- with
        its creation stamp, because a pid alone is recycled.
        """
        from hato import watch as _watch
        pid = _watch.watching_pid()
        if pid is None:
            return None
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, AttributeError):
            return None
        _watch.clear_pid_file()
        # ⚠ NO `self.render()` HERE, DELIBERATELY. There was an unreachable one
        # after this return -- dead since it was written, and sitting in the
        # method being repaired while the pid-liveness bug was fixed (found by
        # the adversarial pass, 2026-09-18, F-B12). ⛔ Every exit from this
        # function is a bare return, so the CALLER repaints: `_toggle_watch`
        # renders once after calling either half. Adding one here would paint
        # twice on the only path that uses it.
        return pid

    def _toggle_recurse(self):
        self.state.recurse = not self.state.recurse
        self.spawn(gui_run.argv_for_config(
            u"--set", u"recurse=%s" % (u"true" if self.state.recurse
                                       else u"false")))
        self.render()

    def _set_schedule(self):
        value = self.time_field.text().strip()
        if value and value != self.state.schedule:
            self.state.schedule = value
            self.spawn(gui_run.argv_for_config(u"--set",
                                               u"schedule=%s" % value))
            self.render()

    def _remove_folder(self, path):
        self.state.folders = [f for f in self.state.folders if f != path]
        self.spawn(gui_run.argv_for_config(u"--remove-folder", path))
        self.render()

    def _remove_skip(self, path):
        self.state.skip_folders = [f for f in self.state.skip_folders
                                   if f != path]
        self.spawn(gui_run.argv_for_config(u"--remove-skip", path))
        self.render()

    # -- the run -----------------------------------------------------------

    def start_run(self):
        u"""Spawn `hato --json --progress` and paint what comes back.

        [X] `run.Runner` owns the process, the two reader threads and the
        parse; this method owns a timer that drains it.
        """
        if self.state.running or not self.state.folders:
            return None
        argv = gui_run.argv_for(self.state.folders, progress=True)
        self.state.running = True
        self.state.rows = []
        self.state.summary = {}
        self.state.picked = {}
        self.state.live = u"starting…"
        self.render()
        self._runner = gui_run.Runner(argv=argv)
        try:
            self._runner.start()
        except Exception as exc:
            self.state.running = False
            self.state.live = u"could not start — %s" % exc
            self.render()
            return None
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._drain)
        self._timer.start()
        return argv

    def _drain(self):
        if self._runner is None:
            return
        for event in self._runner.drain():
            kind = event.get(u"type")
            if kind == u"video":
                self.state.rows.append(event)
            elif kind == u"run":
                self.state.summary = event
            elif kind == u"progress":
                #: [!] ENGINE-WRITTEN, so it goes through `safe()` like every
                #: other field hato did not compose itself.
                self.state.live = safe(event.get(u"name")
                                       or event.get(u"stage")) \
                    or self.state.live
        finished = self._runner.finished()
        if finished is not None:
            self.state.running = False
            self.state.summary = finished.summary or self.state.summary
            #: [X] EXIT 1 IS NOT AN ERROR -- it means something needs a pick,
            #: which is the whole value proposition. Only exit 2 could not run.
            self.state.live = (u"could not run" if finished.could_not_run
                               else u"done")
            self.state.last_run = time.strftime(u"%H:%M")
            # ⛔ NOT SAVED HERE ANY MORE. `hato` itself writes what every run
            # found (`hato/lastrun.py`), so this window's own run is recorded
            # by the same writer as the tray's and the scheduler's. A save here
            # too would be a second writer racing the first for one file.
            # ⚠ And the poller must not then re-read our own write as somebody
            # else's news.
            self._others_seen = gui_run.last_run_stamp()
            if self._timer is not None:
                self._timer.stop()
        self.render()

    def _spawn(self, argv, stdin_text=None, detached=False):
        u"""The real one. Replaced in tests, which is why it is one method.

        ⚠ `stdin_text` IS HOW THE KEY TRAVELS, and it is the reason this stayed
        one seam rather than gaining a sibling. `hato key --set-from -` reads
        the key from stdin precisely so a GUI field never has to write the
        secret to a temp file first (LEDGER-HOT.md's first rule) -- and a
        second spawn helper would be a second thing every check has to know to
        intercept.

        ⛔ The key is never in `argv`. A command line is visible to every other
        process on the machine through the process table.
        """
        import subprocess
        extra = dict(gui_run.no_console_kwargs())
        if detached:
            # ⛔ NO PIPES ON A DETACHED CHILD. The tray watcher outlives this
            # window by design, and a pipe nobody is reading fills and blocks
            # it -- so the icon would simply stop responding after a while,
            # with nothing to show why.
            streams = dict(stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            # ⚠ Its own process group, so closing the window -- or a Ctrl-C in
            # a console that happened to start it -- does not take the tray
            # down with it.
            if sys.platform.startswith("win"):
                extra["creationflags"] = (
                    extra.get("creationflags", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
        else:
            streams = dict(
                stdin=subprocess.PIPE if stdin_text is not None else None,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # ⛔ ONE `Popen` IN THIS FILE, and a check pins the count. A second
        # call is how the window comes to have two ideas about the environment
        # a child runs in -- which is the drift `gui_run` exists to prevent.
        process = subprocess.Popen(argv, env=gui_run.child_env(),
                                   **streams, **extra)
        if detached:
            return process
        if stdin_text is not None:
            try:
                process.stdin.write(stdin_text.encode("utf-8"))
                process.stdin.close()
            except (OSError, ValueError):
                pass                       # the child is gone; its exit says so
        return process


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_state_from(rows, summary=None, **settings):
    u"""A `State` from a parsed run. Convenient for the suite and for `main`."""
    state = State()
    state.rows = list(rows or ())
    state.summary = dict(summary or {})
    for name, value in settings.items():
        setattr(state, name, value)
    return state


def instance_name():
    u"""The name a running window answers to. -> str

    ⚠ PER USER. Two people signed into one machine each get their own hato, and
    a shared name would have the second one's launch raise the first one's
    window on a desktop they cannot see.
    """
    import getpass
    try:
        who = getpass.getuser()
    except Exception:                         # noqa: BLE001
        who = u"user"
    return u"hato-window-%s" % who


#: What a live window answers with. ⭐ A CONNECTION IS NOT AN ANSWER: a process
#: that is wedged, mid-shutdown, or holding the name without an event loop will
#: still ACCEPT a connection and never act on it. Requiring a byte back is what
#: turns "somebody holds the name" into "a window is really there and heard me".
_ALIVE = b"hato-here"


def raise_existing_window(timeout_ms=400):
    u"""Is a window already open? Raise it. -> True when one answered.

    🚨 SONIC, 2026-09-18: *"we also need to ensure that only one hato is ever
    open at a time."* He named the tray, and the window had the same problem --
    demonstrated five times over by this session's own testing, which left five
    stacked window processes behind.

    ⭐ RAISE, DON'T REFUSE. A second launch that merely exits looks like a
    broken shortcut: you double-click and nothing happens. Bringing the window
    that is already there to the front is what somebody double-clicking
    actually wanted.

    ⚠ A SOCKET, NOT A PID FILE. The watcher can use a pid file because nothing
    needs to talk to it; a window has to be told to come forward, and Qt's
    local socket is the same mechanism on every platform.

    🚨 AND IT DEMANDS AN ANSWER, NOT JUST A CONNECTION. Sonic, 2026-09-18:
    *"go to the tray to open it, it doesn't do anything... I have to close hato
    from the tray. Then open it again."* A window process was found alive with
    NO window and still holding this name -- so every later launch connected,
    believed a window was there, and exited. **Nothing opened, and nothing said
    why.**

    ⛔ A CONNECTION PROVES A NAME IS HELD, NOT THAT ANYBODY IS LISTENING. A
    process that is wedged or mid-shutdown still accepts. Requiring a byte back
    means a launch that cannot raise anything opens its own window instead --
    the failure becomes a second window, which is visible and harmless, rather
    than silence.
    """
    from PyQt6.QtNetwork import QLocalSocket
    socket = QLocalSocket()
    socket.connectToServer(instance_name())
    if not socket.waitForConnected(timeout_ms):
        return False                          # nobody listening: we are first
    try:
        socket.write(b"raise")
        socket.waitForBytesWritten(timeout_ms)
        # ⚠ PUMPED, NOT JUST BLOCKED. `waitForReadyRead` alone services this
        # socket and nothing else, so a window living in THIS process -- which
        # is how the suite drives the handshake -- could never reach its own
        # `newConnection` to answer. Pumping also keeps a second instance
        # responsive while it waits, and it has no window yet to re-enter.
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        application = QApplication.instance()
        while time.monotonic() < deadline:
            if socket.bytesAvailable():
                break
            if application is not None:
                application.processEvents()
            socket.waitForReadyRead(20)
        if not socket.bytesAvailable():
            return False                      # ⛔ holds the name, cannot answer
        return bytes(socket.readAll()).startswith(_ALIVE)
    finally:
        socket.disconnectFromServer()


def listen_for_second_launch(window):
    u"""Answer later launches by coming to the front. -> the server, or None.

    ⚠ `removeServer` FIRST, and only safe because the caller has just proved
    nobody answered: a crashed window leaves its name held, and without this
    every launch after a crash would fail to listen and stack up for ever.
    """
    from PyQt6.QtNetwork import QLocalServer
    QLocalServer.removeServer(instance_name())
    server = QLocalServer(window)
    if not server.listen(instance_name()):
        return None                           # ⛔ not a reason to refuse to open

    def answer():
        connection = server.nextPendingConnection()
        # ⭐ SAY SO, and say it BEFORE raising. The byte is what tells the other
        # launch a real window heard it; without one it cannot tell a listening
        # window from a process that merely still holds the name, and it would
        # exit silently either way.
        if connection is not None:
            connection.write(_ALIVE)
            connection.flush()
            connection.disconnectFromServer()
        window.showNormal()                   # ⚠ un-minimise, not just raise
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(answer)
    return server


def settings_from_disk(state=None):
    u"""Fill a `State`'s settings from what is actually on disk. -> State

    🚨 THE WINDOW NEVER READ ITS OWN SETTINGS BACK. Sonic, 2026-09-18: *"i
    don't think my settings are being saved."* They were -- every one of them,
    correctly, through `hato config`. What was missing is this: `main()` built
    a `HatoWindow()` with no arguments, so every session opened on DEFAULTS.
    Add a folder, close, reopen, and it is gone from the list while sitting in
    `config.toml` the whole time.

    ⭐ THE HARDEST KIND OF BUG TO SEE FROM THE INSIDE: the write path was
    built, checked and working, and the round trip was never once closed.
    `State`'s own comment already said *"settings, as `hato config --show
    --json` reports them"* -- the shape was designed for a loader nobody wrote.

    ⚠ READS BY IMPORT, WRITES BY SUBPROCESS, and that is not two roads into one
    setting. `hato/config.py` is the single schema either way; what the "two
    roads" rule forbids is two WRITERS. A read costs nothing and has no side
    effect, and spawning two processes to open a window would be felt.
    """
    state = State() if state is None else state
    from hato import config as _config
    from hato import credentials, paths
    try:
        cfg = _config.load()
        state.folders = list(cfg.folders)
        state.skip_folders = list(cfg.skip_folders)
        state.recurse = cfg.recurse
        state.watch = cfg.watch
        state.schedule = cfg.schedule
        state.auto = bool(cfg.schedule)
        state.surasura_dir = cfg.surasura_dir
    except (_config.ConfigError, paths.PathError) as exc:
        # ⛔ NOT SWALLOWED. A config hato refuses is why the settings look
        # empty, and a window that opened on silent defaults would be telling
        # the person their settings vanished.
        state.config_error = str(exc)
        sys.stderr.write(u"hato: %s\n" % exc)
    try:
        state.key_hint = credentials.resolve_key().hint
    except Exception:                         # noqa: BLE001
        state.key_hint = None                 # not set yet is a normal state

    # ⭐ AND WHAT THE LAST RUN FOUND. Settings without results meant reopening
    # showed an empty Subtitles tab under a header naming the time of a run
    # whose rows were gone -- which reads as though the run did nothing.
    rows, summary, saved_at = gui_run.load_last_run()
    if rows or summary:
        state.rows = rows
        state.summary = summary
        # ⚠ The time it was SAVED, not `now`. A header that said "last run
        # 15:04" every time the window opened would be inventing a run.
        state.last_run = (saved_at[11:16] if len(saved_at) >= 16
                          else state.last_run)
    return state


def main(argv=None):
    u"""Open the window. -> an exit code."""
    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    # 🚨 ONE WINDOW. ⛔ Before anything is built -- a second instance that got
    # as far as constructing a window would flash one and then have to destroy
    # it. ⚠ `HATO_ALLOW_MANY` is the same escape hatch the watcher has, because
    # Sonic asked for one: *"during testing it could be useful to have more."*
    if not os.environ.get("HATO_ALLOW_MANY") and raise_existing_window():
        return 0
    icon = branding.app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    window = HatoWindow()
    # ⛔ AFTER construction and BEFORE showing: the window paints from `state`,
    # so loading into the one it already has is what makes the round trip real
    # rather than a second state object nobody renders.
    settings_from_disk(window.state)
    # 🚨 A TICKED BOX WHOSE PROCESS IS NOT RUNNING IS A LIE. Sonic, 2026-09-18:
    # *"if they have the hato option for watch for new videos and run, but they
    # close it out. Then reopen hato (its still checked), the tray icon doesn't
    # populate."* The SETTING persisted correctly; nothing acted on it, because
    # only the toggle ever started anything.
    # ⭐ `start_watcher` refuses when one is already there, so this is safe to
    # call on every launch -- it reconciles the world with the setting rather
    # than assuming either.
    if window.state.watch:
        window.start_watcher()
    # ⛔ HELD ON THE WINDOW. A QLocalServer whose only reference is local is
    # collected, the name is released, and the next launch stacks a second
    # window instead of raising this one.
    window._instance_server = listen_for_second_launch(window)
    # ⭐ So a run started from the tray, the scheduler or a terminal shows up
    # here without anybody pressing anything.
    window.follow_other_runs()
    window.render()
    window.show()
    return app.exec()


__all__ = ["Accordion", "CandidateCard", "Check", "Elide", "HatoWindow",
           "KeyDialog",
           "PickHead", "PulseDot", "State", "SubRow", "Switch", "TabButton",
           "TAB_PICK", "TAB_SET", "TAB_SUBS", "TABS", "LOCKED",
           "build_state_from", "candidate_path", "candidates", "ease",
           "episode_text", "footer_status", "group_of", "kb", "lift", "main",
           "paragraph",
           "instance_name", "listen_for_second_launch", "raise_existing_window",
           "rate_text", "safe", "settings_from_disk", "texts", "tier", "wrap"]
