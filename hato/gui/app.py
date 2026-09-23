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
        #: ⭐ D2 -- IS THE DAILY RUN REGISTERED? Read from Task Scheduler
        #: (`read_schedule`), never from the config: `bool(cfg.schedule)` said ON
        #: for days over no task at all. ⛔ False until something was read.
        self.auto = False
        #: What the daily run's switch must say about the task it found -- off in
        #: Task Scheduler, another copy's, set not to run on battery. u"" if fine.
        self.auto_note = u""
        #: What the LAST action on it came to, when that was a refusal. ⛔ Not
        #: `auto_note`, which every re-read replaces.
        self.schedule_said = u""
        #: ⛔ Controls vanish where they would be meaningless: no Task Scheduler,
        #: no switch (and an instruction instead).
        self.auto_supported = True
        self.schedule = u"03:00"
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
        # ---- ⭐ RUNBOOK 8e: what hato remembers, and what a pick came to ----
        #: `hato problems --json`'s rows, or None until it has answered. ⭐ The
        #: store that outlives one run -- 4a's first cause was painting Needs
        #: you from `last-run.json` alone, which is a snapshot by design.
        self.remembered = None
        #: monotonic moments the run's rows and the memory last changed, so the
        #: newer of the two decides which copy of a row wins (`needs_you`).
        self.rows_at = 0.0
        self.remembered_at = 0.0
        #: row key -> the file name clicked, while `hato sync` has not answered.
        #: ⛔ Not `picked`: *paired* is said only when a file LANDED (D7).
        self.pick_pending = {}
        #: row key -> (word, why) -- what the last pick on that row came to.
        self.pick_said = {}
        #: row key -> the word of the pick that LANDED -- *paired* or *used*.
        #: ⛔ Not `pick_said`, which a later failed pick overwrites: the row's
        #: colour is what was WRITTEN (ADVERSARY 2026-09-22 A10).
        self.picked_word = {}
        #: the tray watcher is running, so a due retry WILL run (RUNBOOK 8h).
        self.watching = False
        #: ⭐ V1 -- a tray IS running, but an older one that keeps no promise.
        self.old_tray = False
        #: the soft and hard retry windows in days, as `hato problems` reports them.
        self.retry_days = 1
        self.hard_days = 30
        #: ⭐ A1 -- why what hato remembers could not be read, when it could not.
        #: ⛔ The window keeps what it had and SAYS so; it never empties Needs you
        #: over an answer it could not trust.
        self.problems_error = u""
        #: ⭐ The keys a run streamed, and when the last one came -- newer than the
        #: memory video by video, never the whole snapshot (A4).
        self.live_keys = set()
        self.live_at = 0.0
        #: ⭐ A27 -- the memory was emptied ON PURPOSE (a clear): until the next
        #: run, its silence settles nothing.
        self.trust_rows = False
        #: ⚠ INJECTABLE, so a check about "in 14h" does not depend on the wall.
        self.now = None
        # ---- ⭐ RUNBOOK 8g: clearing hato's memory ----
        #: `hato state --clear --json`'s DRY count, or None until it answers.
        self.memory = None
        #: what the last clear came to, in words -- said under the card.
        self.memory_said = u""
        #: ⭐ HANDOFF 4c -- video key -> the retry date the person chose to wait
        #: for (`run.apply_waits`). Kept in hato's folder by the window.
        self.waits = {}

    def daily(self):
        u"""⭐ D2 -- the daily run's time while one is REGISTERED, else None.
        Everything that says who will run a retry asks this, never `schedule`,
        which is only a time and is set whether anything runs at it or not."""
        return self.schedule if self.auto else None

    def clock(self):
        u"""-> now, timezone-aware."""
        from datetime import datetime, timezone
        return self.now if self.now is not None else datetime.now(timezone.utc)

    #: The last moment handed out by `moment()`.
    _moment = 0

    def moment(self):
        u"""The next moment in the window's own order. -> int, strictly rising.

        ⚠ `rows_at`, `remembered_at` and `live_at` are COMPARED -- which copy of a
        row is newer decides what Needs you shows. `time.monotonic()` ticks every
        ~16 ms on Windows, so a row arriving just after the memory answered could
        carry the SAME reading and lose the tie to an older copy. Measured by the
        window's own suite. ⭐ A counter orders them exactly, and that is all
        these ever needed: which came first.
        """
        self._moment += 1
        return self._moment

    # -- identity ----------------------------------------------------------

    @staticmethod
    def key(row):
        u"""A stable id for one row -- its VIDEO. -> unicode

        The video's own path, NORMALISED: `run.problem_key`, the one identity
        the merge, the tally and every per-row store use. ⚠ The raw path was a
        second identity -- two spellings of one video painted two rows under a
        badge of one, and a look-again replaced the wrong one (ADVERSARY
        2026-09-22 A7).
        """
        return gui_run.problem_key(row)

    def in_scope(self, row):
        u"""Could `hato problems` list this video at all? -> bool

        ⚠ Only one under a configured folder and not under a skipped one. A run
        over any other folder -- `hato D:\\Elsewhere` in a terminal -- has
        refusals memory CANNOT list, and their absence settles nothing (A26).
        """
        from hato import paths as _paths
        video = row.get(u"video") or u""
        return bool(video and self.folders and _paths.under_any(video, self.folders)
                    and not _paths.under_any(video, self.skip_folders))

    @staticmethod
    def word(row):
        u"""-> the INTERFACE's word for this row. [X] Never the engine's."""
        return gui_run.outcome_word(row)

    # -- partitions --------------------------------------------------------

    def of(self, word):
        u"""Every row the interface calls `word`, in arrival order."""
        return [row for row in self.rows if self.word(row) == word]

    def problems(self):
        u"""⭐ RUNBOOK 8e -- THE ONE LIST Needs you paints. -> [row]

        The run's problem rows and the remembered ones, merged by
        `run.needs_you`, which decides PER VIDEO: a row a run streamed after the
        memory answered wins, the snapshot wins when it is the newer file, and
        a row the newer memory no longer lists has been settled since -- unless
        the memory could not have listed it.
        """
        live = self.live_keys if self.live_at > self.remembered_at else ()
        merged = gui_run.needs_you(self.rows, self.remembered, live=live,
                                   rows_newer=self.rows_at > self.remembered_at,
                                   in_scope=self.in_scope, trust_rows=self.trust_rows)
        # ⭐ 4c -- and a pick the person chose to wait on is a wait, until its date.
        return gui_run.apply_waits(merged, self.waits, self.clock())

    def picks(self):
        u"""The problems a person can choose a file for, in list order."""
        return [row for row in self.problems()
                if gui_run.problem_kind(row) == gui_run.PICK]

    def unresolved(self):
        u"""Pick rows nobody has settled yet. -> [row]

        [*] THIS is what moves when a pick lands, and it is why the badge and the
        footer cannot be hardcoded: a pick changes the answer without changing a
        single field on the wire. ⚠ A pick still waiting on `hato sync` is NOT
        resolved -- it may yet not line up (D7).
        """
        return [row for row in self.picks() if self.key(row) not in self.picked]

    def tallies(self):
        u"""-> {interface word: n}. The ONE count. Both readers call this.

        `run.tally` partitions the run's rows AND the remembered problems, each
        video once, and leaves out a row a person has already paired -- it is no
        longer waiting on them even though its wire outcome has not moved.
        """
        done = [gui_run.problem_key({u"video": key}) for key in self.picked]
        return gui_run.tally(self.rows, self.problems(), done=done)

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
                           if gui_run.is_skipped(self.word(row))
                           and (row.get(u"title") or u"") == title])
            out.append((title, season, index[ident], skipped))
        return out

    def fully_skipped(self):
        u"""Shows where NOTHING was added -- one quiet line each.

        -> [(title, word, [episode])] . *"visible, but not the focus."*

        🚨 GROUPED BY THE KIND OF SKIP, NOT JUST THE TITLE, AND IT CARRIES THE
        EPISODE NUMBERS. Sonic, 2026-09-19: *"Katanai and tsuihou don't have it
        even though it says its already subbed in the GUI"* and *"for the
        'already subbed' i need the ep # in those titles as well."*

        ⛔ This used to return `(title, count)` and the caller painted every one
        of them *"— already subtitled"*. One of those two shows had downloaded
        three candidates, kept none, and was waiting until tomorrow to try
        again; the other had its subtitles inside the container. Neither had a
        file, and the line said they were done.

        ⚠ One show CAN now produce several lines -- episodes 1-3 finished and 4
        waiting to retry is two different facts about one title, and collapsing
        them is the defect this method just had.
        """
        added_titles = set(title for title, _s, _r, _k in self.shows())
        order = []
        grouped = {}
        for row in self.rows:
            word = self.word(row)
            if not gui_run.is_skipped(word):
                continue
            title = row.get(u"title") or row.get(u"name") or u""
            if title in added_titles:
                continue
            ident = (title, word)
            if ident not in grouped:
                grouped[ident] = []
                order.append(ident)
            grouped[ident].append(row.get(u"episode"))
        return [(title, word, grouped[(title, word)]) for title, word in order]

    def next_unresolved(self, after):
        u"""-> the key of the row that should open as `after` closes, or None.

        Sonic: *"it should only have one open at a time but after selecting
        one, the next one opens as it closes."*
        """
        for row in self.unresolved():
            if self.key(row) != after:
                return self.key(row)
        return None


def episode_tail(episodes):
    u"""*"ep 11"* · *"eps 4, 5, 6"* · *"12 episodes"*. -> text or u""

    ⭐ Sonic asked for the episode number on these lines because two rows of one
    show were otherwise indistinguishable -- the same complaint that put the
    video filename on a *Needs you* row.

    ⚠ `None` is a real value here: a video whose episode could not be parsed
    still skips, and it must not render as *"ep None"*. Past a handful the
    numbers stop helping and the COUNT is the useful fact.
    """
    known = [n for n in episodes if n is not None]
    if not known:
        n = len(episodes)
        return u"" if n <= 1 else u"%d episodes" % n
    known = sorted(set(known))
    if len(known) > 4:
        return u"%d episodes, %s–%s" % (len(known), known[0], known[-1])
    if len(known) == 1:
        return u"ep %s" % known[0]
    return u"eps %s" % u", ".join(str(n) for n in known)


#: 🚨 ONE TOOLTIP PER SKIP, AND EACH ONE HAS TO BE TRUE OF ITS OWN ROW.
#: The single tooltip these replace said *"Every episode already carries a
#: Japanese track, so it is already in sync and nothing was requested"* --
#: painted under EVERY skip, including one that had downloaded three subtitles,
#: kept none of them, and was waiting a day to try again.
#:
#: ⛔ None of these tells a person to change a setting that is not in the
#: window. `skip_embedded` is `config.toml` only, so it is named as a file key
#: and not as a Settings switch.
QUIET_TIPS = {
    gui_run.SKIPPED:
        u"The Japanese subtitle is already sitting beside the video, so "
        u"nothing was requested.",
    gui_run.INSIDE_VIDEO:
        u"The Japanese subtitles are inside the video file itself, so there is "
        u"correctly no separate subtitle beside it — your player will find "
        u"them. To fetch one anyway, set skip_embedded = false in config.toml.",
    gui_run.RETRYING:
        u"hato downloaded subtitles for this and none of them lined up with "
        u"your copy, so nothing was written rather than writing one that is "
        u"out of sync. It will try again on its own.",
    gui_run.CANT_SYNC:
        u"This video has no subtitle track inside it for hato to time a "
        u"download against, so nothing was requested yet.",
    gui_run.ON_SKIP_LIST:
        u"You told hato to skip this one.",
}


def candidates(row):
    u"""The files hato already downloaded for this episode. -> [attempt]

    [X] NEVER THE WHOLE JIMAKU CATALOGUE -- `05-interface.md` §manual pairing.
    ⭐ RUNBOOK 8e: this run's attempts AND the ones remembered from earlier runs
    (`tried_before`), one per file, best first -- `run.candidates_of` decides.
    """
    return gui_run.candidates_of(row)


def candidate_path(attempt):
    u"""Where that candidate sits on disk. -> unicode or None

    tsubasa's `Result.subtitle` is the path it was handed, so an attempt that
    reached the engine carries it. One that never got that far has no path and
    cannot be committed -- and says so rather than committing something else.
    """
    tsu = attempt.get(u"tsubasa") or {}
    return tsu.get(u"subtitle") or attempt.get(u"path") or None


def tray_cost(frozen=None):
    u"""What the tray costs, for the build this window IS. -> (short, detail)

    ⚠ Two measurements, each with its moment -- a number in prose with no moment
    is quoted for ever as though it were a constant (`processes.md`):
      source  13.4 MB, 12.7 of it Python itself (`gui-mock/MEMORY.md`, 2026-09-18)
      exe     30.6 MB against 96 MB for the window (`smoke_standalone.py`,
              2026-09-22) -- every frozen process carries its own CPython
    """
    frozen = getattr(sys, u"frozen", False) if frozen is None else frozen
    if frozen:
        return (u"31 MB",
                u"Measured, not estimated: 30.6 MB resident, against 96 MB for "
                u"this window. Most of it is the Python the program carries with "
                u"it; the watching itself costs under 1 MB. No window toolkit is "
                u"loaded while it watches — the window is a separate program that "
                u"starts when you open it.")
    return (u"13 MB",
            u"Measured, not estimated. 13.4 MB resident — and 12.7 MB of "
            u"that is Python itself, so the watching costs about 0.7 MB. No "
            u"window toolkit is loaded while it watches; the window is a "
            u"separate program that starts when you open it.")


def season_text(season):
    u"""-> *"S2"*, or u"" when there is none.

    🚨 D10 -- THE WIRE CARRIES AN INT. tsubasa reads `S2` as `2`, and every
    fixture in this window's suite wrote the STRING "S2" -- so every picture
    showed "S2" while a real run printed a bare *"2 · 3 added"* beside the show
    and *"· 4"* after a filename, which reads as a count. Found 2026-09-22 by
    the first shot seeded with rows as `hato problems` really emits them.
    """
    if season is None or season == u"" or isinstance(season, bool):
        return u""
    if isinstance(season, int):
        return u"S%d" % season
    return str(season)


def episode_text(episode):
    u"""-> *"01"*, *"04"*, *"1121"*.

    Zero-padded to two, as the ruled design shows -- a column of `1 2 4` reads
    as a list of quantities, `01 02 04` reads as episode numbers. [X] A number
    already wider than two is left alone: One Piece is at 1121 and padding is
    not truncation.
    """
    if episode is None or isinstance(episode, bool):
        return u""
    # ⚠ A HALF EPISODE IS NOT THE WHOLE ONE. `int()` printed 24.5 as "24", so a
    # recap and the episode it sits beside read as two copies of one
    # (ADVERSARY 2026-09-22 A28).
    if isinstance(episode, float) and not episode.is_integer():
        return u"%g" % episode
    try:
        return u"%02d" % int(episode)
    except (TypeError, ValueError):
        return str(episode)


def episode_name(row):
    u"""*"Tsuihou 12"* -- the show and the episode, for a line of names. -> text

    ⚠ Either can be missing: a video tsubasa does not list is named by its file
    and has no number, and it printed *"Show - OVA None"* (ADVERSARY 2026-09-22
    A18).
    """
    parts = [row.get(u"title") or row.get(u"name") or u"",
             episode_text(row.get(u"episode"))]
    return u" ".join(p for p in parts if p)


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
        self._fade = None
        self._ensure_fade().setOpacity(0.0)

    def _ensure_fade(self):
        u"""The opacity effect, made when it is needed. -> the effect"""
        if self._fade is None:
            self._fade = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._fade)
        return self._fade

    def _drop_fade(self):
        u"""🚨 DETACH IT ONCE THE ROW IS OPEN, AND THIS IS A REAL BUG'S FIX.

        Sonic, 2026-09-19, on the published 1.0.0: *"when you hover over the
        options for the episodes in the needs you, the option goes invisible
        while you hover over it."*

        ⛔ A `QGraphicsEffect` CACHES THE SOURCE IT DRAWS. While one is
        attached, a repaint of a DESCENDANT -- which is exactly what
        `#cand:hover` triggers -- can fail to reach the composited result, so
        the stale cache is drawn instead and the card renders as nothing.

        ⭐ MEASURED, not reasoned: hovering a candidate took the card's
        region of the window from **964 bright pixels to 0**. ⚠ And it only
        showed up when the WINDOW was grabbed -- `card.grab()` renders the
        widget directly, bypasses compositing, and reported a perfectly
        healthy card the whole time.

        ⚠ The effect is worth having DURING the fade and nothing afterwards:
        at full opacity it changes no pixel and costs a caching hazard. So it
        goes as soon as the row has settled open, and is remade next time
        something needs to fade.
        """
        if self._fade is not None:
            self.setGraphicsEffect(None)      # ⚠ Qt deletes the old effect
            self._fade = None

    def target_height(self):
        u"""-> the content's OWN height. [X] Never a constant."""
        return max(self.content.sizeHint().height(),
                   self.content.minimumSizeHint().height())

    def is_open(self):
        return self._open

    def set_open(self, open_, animate=True):
        self._open = bool(open_)
        end = self.target_height() if self._open else 0
        self._ensure_fade().setOpacity(1.0 if self._open else 0.0)
        if not animate:
            self._anim.stop()
            self.setMaximumHeight(QWIDGETSIZE_MAX if self._open else 0)
            # ⚠ Opened with no animation, so there is no fade to wait for.
            if self._open:
                self._drop_fade()
            return
        self._anim.stop()
        self._anim.setStartValue(self.height())
        self._anim.setEndValue(end)
        self._anim.start()

    def _settle(self):
        u"""[*] Release the ceiling once open, so later growth is not clipped.

        ⭐ AND DROP THE OPACITY EFFECT. See `_drop_fade` -- leaving it
        attached is what made a hovered candidate render as nothing.
        """
        if self._open:
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            self._drop_fade()


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
        # 🚨 THE FILE, NOT THE SHOW. Sonic, 2026-09-19, on the published
        # 1.0.0: *"i cannot see the actual name of the file in the 'needs
        # you' which makes it impossible to sort. it should show the actual
        # video one."*
        #
        # ⛔ This read `title or name`, and `title` is the SHOW -- so every
        # episode of one series rendered the same sentence and the rows were
        # indistinguishable except by the number in the left column. A tab
        # whose whole job is *"these need a person"* has to say which file.
        #
        # ⚠ MIDDLE elision, not right. A release name carries its group at
        # the front and its episode, resolution and extension at the end;
        # cutting the tail throws away the half that identifies it.
        title = Elide(row.get(u"name") or row.get(u"title") or u"", who,
                      u"who", mode=Qt.TextElideMode.ElideMiddle)
        #: [!] NO STRETCH ON THE TITLE, and the stretch goes AFTER the season.
        #: Given the stretch, the title expanded to the full 560px column and
        #: shoved *"· 3rd Season"* to the far right, 600px from the show it
        #: belongs to -- the same *number-marooned-from-its-subject* fault the
        #: capped measure exists to prevent, rebuilt inside one cell.
        line.addWidget(title, 0)
        season = season_text(row.get(u"season"))
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

    def set_state(self, picked, tried, best_rate, wait=u"", pending=None,
                  word=None, late=False):
        u"""[*] Idle says what was tried; paired NAMES THE FILE IT USED.

        ⭐ RUNBOOK 8e, and each clause is a place this row used to say nothing:
          `wait`     *"retrying in 14h"* -- the automatic path, said out loud (4b)
          `pending`  a pick is with `hato sync` and has not answered; ⛔ not yet
                     *paired* (D7: it used to say so at the click)
          `word`     *paired* when the timing held, *used* when the person's
                     choice was written over a timing refusal (D6)
          `late`     ⭐ 8f -- one past the newest episode on offer: *probably
                     not out yet*, said instead of a best match that is some
                     OTHER episode's
        """
        done = picked is not None
        # ⭐ A FORCED pick is AMBER, not green: the mock's own meaning for amber is
        # *"written, worth a look"*, and a file written over a timing refusal is
        # exactly that. Green says the timing held, and here it did not.
        state = (u"forced" if word == gui_run.FORCED else True) if done else False
        mark(self, u"done", state)
        mark(self.best, u"done", state)
        waiting = bool(late) and not done and not pending
        mark(self, u"late", waiting)
        mark(self.best, u"late", waiting)
        if done:
            self.best.setText(u"%s · %s" % (word or gui_run.PAIRED, picked))
        elif pending:
            # ⚠ No trailing ellipsis: after a middle-elided file name it read as
            # the name being cut off. The verb says it is in flight.
            self.best.setText(u"%s · %s" % (u"using" if gui_run.PICK_OVERRIDES_TIMING
                                            else u"checking", pending))
        else:
            text = (u"probably not out yet · %d tried" % tried if waiting
                    else u"%d tried · best %s" % (tried, rate_text(best_rate)))
            self.best.setText(u"%s · %s" % (text, wait) if wait else text)


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

    def set_usable(self, has_file, row_settled=False):
        u"""Whether a click can do anything. -> bool

        ⛔ A card that cannot be used is INERT and says why -- never a click
        that fails afterwards: `has_file` False is a file hato no longer has
        (ADVERSARY 2026-09-22 A13); `row_settled` is a row whose pick landed or
        is still with `hato sync` (A10, A32).
        """
        usable = bool(has_file) and not row_settled
        self.setEnabled(usable)
        mark(self, u"gone", not has_file)
        if not has_file:
            self.setToolTip(wrap(u"hato no longer has this file — it was cleared "
                                 u"from its downloads, so it cannot be used."))
        return usable


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


class ClearDialog(QDialog):
    u"""⭐ RUNBOOK 8g -- the confirm before hato forgets what it remembers.

    ⛔ HAND-BUILT, like `KeyDialog`, for the same reason: a native message box
    is themed by the toolkit, not by hato, and it arrived white in the middle of
    the app once already. ⛔ IT NAMES WHAT GOES AND WHAT STAYS, in that order,
    and the blacklist -- the person's own instruction -- goes only if they turn
    it on here. Off by default.
    """

    def __init__(self, parent=None, memory=None, blacklisted=0):
        super().__init__(parent)
        self.setWindowTitle(u"Clear hato's memory")
        self.setModal(True)
        self.setStyleSheet(theme.qss())
        self.setMinimumWidth(480)

        box = QVBoxLayout(self)
        box.setContentsMargins(GAP, 16, GAP, 14)
        box.setSpacing(12)
        box.addWidget(label(u"Clear hato's memory?", u"emptylead", self))

        counted = gui_run.memory_summary(memory)
        # ⚠ THE DECISION IN THE BODY'S OWN INK. `paragraph()` is the faint
        # `hint` style, made for asides -- and the first shot of this dialog
        # set what goes and what stays, the only two lines that matter here,
        # in the faintest type on screen. The consequence is the aside.
        for text in (u"Goes: %s." % (counted or u"everything hato has tried"),
                     u"Stays: every subtitle beside your videos, the originals "
                     u"hato kept, your settings and your jimaku key."):
            line = paragraph(text, self)
            line.setObjectName(u"")
            box.addWidget(line)
        box.addWidget(paragraph(
            u"The next run looks at every episode without a subtitle again, and "
            u"finds each show again for a few requests.", self))

        self._blacklist = None
        if blacklisted:
            row = QWidget(self)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(10)
            self._blacklist = Switch(row)
            line.addWidget(self._blacklist)
            line.addWidget(label(
                u"Forget the blacklist too — %d video%s you told hato never to fetch"
                % (blacklisted, u"" if blacklisted == 1 else u"s"), None, row), 1)
            box.addWidget(row)

        row = QWidget(self)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(9)
        line.addStretch(1)
        cancel = button(u"Cancel", row)
        cancel.clicked.connect(self.reject)
        line.addWidget(cancel)
        go = button(u"Clear it", row, accent=True)
        go.clicked.connect(self.accept)
        line.addWidget(go)
        box.addWidget(row)
        cancel.setFocus()                    # ⛔ Enter must not be the destructive one

    def forget_blacklist(self):
        u"""-> True only when the person turned the blacklist switch on."""
        return bool(self._blacklist is not None and self._blacklist.isChecked())


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
        # ⭐ RUNBOOK 8e -- children the window READS (a pick's verdict, what hato
        # remembers, the blacklist). ⚠ `_runner_for` is a seam: the suite
        # replaces it, exactly as it replaces `spawn`.
        self._reading = []
        self._read_timer = None
        self._problems_in_flight = False
        #: ⭐ A2 -- a refresh asked for while one was in flight, owed afterwards
        self._problems_again = False
        #: the run in flight is a `--only` look-again: merge, never replace
        self._targeted = False
        #: the run in flight met another one holding the lock
        self._busy = False
        #: ⭐ A3 -- a full run has not said anything yet, so what is on screen
        #: stays until it does (a run that meets the lock says only "busy")
        self._fresh = False

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

        self.autolabel = label(u"runs automatically at", u"autolabel", bar)
        box.addWidget(self.autolabel)
        self.autotime = label(u"", u"autotime", bar)
        box.addWidget(self.autotime)
        self.auto_switch = Switch(bar)
        # ⚠ Its tooltip is set in `render`: it carries what the task is doing.
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
        self._tally_seps = []
        #: [*] THE TALLIES, ALL FROM `State.tallies()`. The second is the SAME
        #: number the tab badge shows, read from the same call -- which is the
        #: defect the mock recorded against itself. ⭐ added · need you ·
        #: skipped always; waiting and had a problem when there are any -- with
        #: only three, the footer summed to less than the rows on screen
        #: (ADVERSARY 2026-09-22 A15).
        for _ in range(5):
            sep = label(u"·", u"sep", foot)
            self._tally_seps.append(sep)
            box.addWidget(sep)
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

        # 🚨 THE VIDEOS OF THE RUN ON THIS LINE, COUNTED FROM ITS ROWS. This read a
        # `video_total` field nothing in production ever set -- only the suite's
        # fixture did (68) -- so every real window said *"0 videos"* beside *"last
        # run 00:24"* over a run that saw 63 (LOOKED, the 1.0.2 returning-client
        # shot over a copy of Sonic's store). ⭐ Live during a run, as rows arrive.
        videos = len(state.rows)
        self.titlesub.setText(
            u"%d folder%s · %d video%s%s"
            % (len(state.folders), u"" if len(state.folders) == 1 else u"s",
               videos, u"" if videos == 1 else u"s",
               (u" · last run %s" % state.last_run) if state.last_run
               else u""))
        self.autotime.setText(state.schedule)
        self.auto_switch.setChecked(state.auto)
        # ⭐ D2 -- THE SWITCH SAYS WHAT WINDOWS WILL DO, and where Windows cannot
        # do it there is no switch (the Settings card says what to do instead).
        for widget in (self.autolabel, self.autotime, self.auto_switch):
            widget.setVisible(state.auto_supported)
        said = state.schedule_said or state.auto_note
        self.auto_switch.setToolTip(wrap(
            (u"Registers or removes a Windows scheduled task. hato is started at "
             u"that time and exits when it is done, so nothing of it sits running "
             u"in between. If the computer is off or asleep then, it runs as soon "
             u"as it is next on.")
            + (u"\n\n" + said if said else u"")))

        for key, tab in self.tab_buttons.items():
            mark(tab, u"selected", key == state.tab)
        self.tab_buttons[TAB_PICK].set_count(tallies[gui_run.NEEDS_YOU])
        self.body.setCurrentWidget(self.panes[state.tab])

        # 🚨 ONLY THE PANE IN FRONT OF THE PERSON. Sonic, 2026-09-19, on the
        # published 1.0.0: *"while it's running, the settings tab glitches
        # HARD ... they look all glitchy like they're collapsing."*
        #
        # ⛔ ALL THREE USED TO REBUILD ON EVERY RENDER, AND `_drain` RENDERS
        # EVERY 120 ms WHILE A RUN IS IN FLIGHT. So a tab nobody was looking
        # at -- and one they WERE -- was torn down and rebuilt about eight
        # times a second, and every expanding row inside it was recreated at
        # `maximumHeight 0` with `opacity 0.0` and animated open again from
        # scratch. That is the collapsing.
        #
        # ⭐ Switching tabs calls `render()`, which builds whichever pane is
        # now current, so a hidden pane is never stale when it comes forward.
        # ⚠ The badge above is updated separately and still counts while the
        # Needs-you pane is hidden.
        if state.tab == TAB_SUBS:
            self._render_subs()
        elif state.tab == TAB_PICK:
            self._render_pick()
        else:
            self._render_settings()

        self.live_label.setText(footer_status(state))
        self.dot.set_running(state.running)
        need = tallies[gui_run.NEEDS_YOU]
        self.tally_labels[0].setText(u"%d added" % tallies[gui_run.ADDED])
        self.tally_labels[1].setText(
            u"1 needs you" if need == 1 else u"%d need you" % need)
        # ⚠ EVERY skip word, not just `SKIPPED`. Splitting the one word into
        # five turned this from "all the skips" into "only the ones that had a
        # file" without changing a character here -- a silent undercount is a
        # worse failure than a KeyError, and `counts()` pre-seeds every key so
        # there would never have been one.
        # ⛔ And it no longer says they "had them": a retrying row has nothing.
        skipped = sum(tallies[word] for word in set(gui_run.SKIP_WORDS.values()))
        self.tally_labels[2].setText(u"%d skipped" % skipped)
        for index, word, text in ((3, gui_run.NOT_YET, u"%d waiting"),
                                  (4, gui_run.FAILED, u"%d had a problem")):
            count = tallies[word]
            self.tally_labels[index].setText(text % count)
            self.tally_labels[index].setVisible(count > 0)
            self._tally_seps[index].setVisible(count > 0)
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

        # ⭐ FOLDERS BUT NO KEY -- the second thing that stops hato dead, and
        # it used to stop it SILENTLY. ⛔ Only when there is nothing to show:
        # a person who has run before keeps their results on screen, because
        # replacing real rows with a nag would be worse than the nag is worth.
        if not state.key_hint and not state.rows:
            column.addStretch(1)
            column.addWidget(self._no_key())
            column.addStretch(1)
            return

        # 🚨 THE RUN'S OWN NOTES, WHICH THIS WINDOW HAS NEVER SHOWN. Sonic,
        # 2026-09-22, on a file inside a blacklisted folder: *"it noticed it
        # but didn't seem to do anything with it ... But nothing in the UI ever
        # popped up about it."*
        #
        # ⛔ The pipeline writes *"N video(s) were not looked at because they
        # are inside a skipped folder"* into `report.notes` precisely so a skip
        # rule that is too broad cannot be invisible -- and `gui/` had no
        # reference to `notes` anywhere, so the one reader who needed it was
        # the one who never got it. It reached the CLI and stopped there.
        #
        # ⭐ FIRST, not last: a note explains an ABSENCE, and an explanation
        # underneath a long list of what WAS found is read by nobody.
        for note in (state.summary.get(u"notes") or ()):
            if note:
                # ⛔ ENGINE PROSE -- a note can carry an exception's own words.
                column.addWidget(self._quiet(u"note", u"— %s" % safe(note), wraps=True))

        # ⭐ 4b's third clause -- SAY THAT IT HAPPENED. Tsuihou 12 was refused on
        # 19 Sep, retried on its own two days later, and written; nothing
        # anywhere said so, and it was reported as *"it doesn't get subbed."*
        retried = [row for row in state.rows if gui_run.found_on_retry(row)]
        if retried:
            names = u", ".join(episode_name(row) for row in retried[:4])
            more = len(retried) - 4
            # ⚠ NEUTRAL, because it is not always true that they "did not line
            # up": what was tried first may have been a download that FAILED
            # (ADVERSARY 2026-09-22 A22).
            column.addWidget(self._quiet(
                u"found on a retry",
                u"— %s%s. hato tried other files first; a later one lined up "
                u"with your copy." % (names, u" and %d more" % more
                                      if more > 0 else u""),
                wraps=True))                  # ⚠ four names can outgrow the window

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
                # ⚠ "already had subtitles" was true of only one of the five
                # skips. This counts all of them, so it says the thing that IS
                # true of all of them.
                column.addWidget(self._quiet(
                    u"%d other episode%s skipped"
                    % (skipped, u"" if skipped == 1 else u"s"),
                    u"— nothing was requested for them"))

        for title, word, episodes in state.fully_skipped():
            tail = episode_tail(episodes)
            column.addWidget(self._quiet(
                title if not tail else u"%s · %s" % (title, tail),
                u"— %s" % word,
                tip=QUIET_TIPS.get(word, u"Nothing was requested for %d video%s."
                                   % (len(episodes),
                                      u"" if len(episodes) == 1 else u"s"))))

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
        if season_text(season):
            meta.append(season_text(season))
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

    def _quiet(self, lead, tail, tip=None, wraps=False):
        u"""One quiet line, not nineteen pills. *"visible, but not the focus."*

        ⚠ `wraps` for a tail that can outgrow the window. LOOKED, 2026-09-23 --
        a run's note, *"24 video(s) were not looked at because they are inside a
        skipped folder (C:\\...)"*, ran off the right edge with no ellipsis and
        the folder list -- the part the note exists to say -- was silently cut
        mid-path. Qt does not wrap a label unless told to.
        """
        strip = Styled(self.panes[TAB_SUBS].widget(), u"quiet")
        box = QHBoxLayout(strip)
        box.setContentsMargins(PAD, 7, PAD, 12)
        box.setSpacing(8)
        box.addWidget(label(lead, u"hadb", strip), 0, Qt.AlignmentFlag.AlignTop)
        said = label(tail, u"had", strip)
        if wraps:
            said.setWordWrap(True)
            box.addWidget(said, 1)
        else:
            box.addWidget(said)
        if tip:
            box.addWidget(info_dot(tip, strip))
        if not wraps:
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

    def _no_key(self):
        u"""Folders are set, but hato has no key. -> a centred widget

        🚨 THE STATE THAT SHIPPED AS SILENCE. Sonic, 2026-09-19, on the
        published 1.0.0: *"I gave it a new folder to look at, and ran it, it
        doesn't do anything ... I THINK that behavior happened because i
        didn't have the API key in."* He diagnosed it himself, which is the
        part that should not have been necessary.

        ⛔ EVERY request hato makes needs the key, so without one there is no
        run to be had -- this is not a quiet precondition, it is the whole
        difference between working and not. And it is the FIRST thing a new
        person meets, because nobody arrives with a key already set.

        ⭐ So it names the problem, offers the control, and says where to get
        one. *"There then needs to be another button to add the api key with
        instructions to get them there as well."*
        """
        host = QWidget(self.panes[TAB_SUBS].widget())
        box = QVBoxLayout(host)
        box.setContentsMargins(PAD, 0, PAD, 0)
        box.setSpacing(14)

        mark = QLabel(host)
        pixmap = branding.mark_pixmap(96, host.devicePixelRatioF())
        if not pixmap.isNull():
            mark.setPixmap(pixmap)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)

        lead = label(u"No jimaku key yet", u"emptylead", host)
        lead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(lead, 0, Qt.AlignmentFlag.AlignHCenter)

        why = label(u"hato needs a free key from your jimaku.cc account "
                    u"before it can find anything.", u"hint", host)
        why.setAlignment(Qt.AlignmentFlag.AlignCenter)
        why.setWordWrap(True)
        box.addWidget(why, 0, Qt.AlignmentFlag.AlignHCenter)

        add = button(u"Add your jimaku key", host, accent=True)
        add.clicked.connect(self.choose_key)
        box.addWidget(add, 0, Qt.AlignmentFlag.AlignHCenter)

        # ⭐ WHERE TO GET ONE, not merely that one is needed. A refusal that
        # does not say how to satisfy it is a dead end.
        box.addWidget(
            link_label(u"Get a key at jimaku.cc/account",
                       u"https://jimaku.cc/account", u"hint", host),
            0, Qt.AlignmentFlag.AlignHCenter)
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
        now = state.clock()

        # ⭐ A1 -- WHAT hato REMEMBERS COULD NOT BE READ, AND THAT IS SAID. The
        # window used to take a failed `hato problems` for "nothing needs you".
        # ⛔ It keeps what it had, above this line, and says why it is not newer.
        trouble = state.problems_error or state.config_error
        if trouble:
            column.addWidget(self._quiet(
                u"not up to date",
                u"— hato could not read what it remembers: %s" % safe(trouble),
                wraps=True))                  # ⚠ a config error is two sentences and a path

        # ⭐ RUNBOOK 8e -- ONE list: the run's problem rows AND the remembered
        # ones, so a problem episode never disappears because a run looked
        # somewhere else (4a). `run.needs_you` decides which copy of a row wins.
        problems = state.problems()
        rows = [r for r in problems if gui_run.problem_kind(r) == gui_run.PICK]
        for row in rows:
            key = state.key(row)
            attempts = candidates(row)
            best = None
            best_name = None
            for attempt in attempts:
                value = attempt.get(u"match_rate")
                # ⚠ ONLY A FILE hato STILL HAS can be recommended: one whose cached
                # copy is gone cannot be used, and was outlined anyway (A13).
                if value is not None and candidate_path(attempt) \
                        and (best is None or value > best):
                    best = value
                    best_name = attempt.get(u"name")

            said = state.pick_said.get(key)
            picked = state.picked.get(key)
            pending = state.pick_pending.get(key)
            late = gui_run.probably_not_out(row)
            wait = u"" if picked else gui_run.retry_text(row, now, state.watching,
                                                         state.daily())
            head = PickHead(row, host)
            # ⭐ THE WAIT, SAID ON THE ROW THAT STAYS (4b): *"retrying in 14h"*.
            # ⭐ And the colour is the pick that LANDED, never a later one that
            # did not (A10).
            head.set_state(picked, len(attempts), best, wait=wait, pending=pending,
                           word=state.picked_word.get(key) if picked else None, late=late)
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
            # ⚠ NO RECOMMENDATION ON A LATE ROW: every file there is another
            # episode's, and outlining the best of them under "probably not out
            # yet" recommended the thing the sentence says to wait instead of.
            chosen_name = (picked or pending or (None if late else best_name))
            if late and not picked:
                # ⭐ 8f -- SAY WHY IT WAITS, in the body's own ink, above files
                # that are other episodes' -- and keep them one click away.
                why = paragraph(
                    u"Episode %s is probably not out yet — the newest on jimaku is "
                    u"%s%s. The files below were tried and did not line up; you can "
                    u"still use one."
                    % (episode_text(row.get(u"episode")),
                       episode_text(row.get(u"newest_offered")),
                       u" (%s)" % wait if wait else u""), body)
                why.setObjectName(u"")
                why.setFixedWidth(COL_CAND)
                inner.addWidget(why)
            for attempt in attempts:
                card = CandidateCard(attempt, body)
                card.setFixedWidth(COL_CAND)
                card.set_chosen(chosen_name is not None
                                and attempt.get(u"name") == chosen_name)
                # ⛔ INERT WHILE IT CANNOT BE USED, and said on the card:
                #   gone     hato no longer has the file -- the click could only
                #            fail, and it promised a remedy that is not there (A13)
                #   landed   a file is written; tsubasa will not write another over
                #            it, so a second pick could only fail -- and turned the
                #            row green over its failure word (A10)
                #   pending  one pick is with `hato sync`; a second one's answer
                #            was wiped by the first's (A32)
                card.set_usable(bool(candidate_path(attempt)), bool(picked or pending))
                card.clicked.connect(
                    lambda k=key, a=attempt: self.commit_pair(k, a))
                inner.addWidget(card)
            if said and not picked:
                inner.addWidget(self._pick_said(said, body))
            inner.addWidget(self._pick_actions(row, key, body))
            accordion = Accordion(body, host)
            accordion.set_open(state.open_pick == key, animate=False)
            self._accordions[key] = accordion
            column.addWidget(accordion)
            column.addWidget(hrule(host))

        # ⭐ HANDOFF 4c -- the picks the person chose to wait on: said, dated, and
        # one click from being picks again. ⛔ Not folded into "not on jimaku
        # yet": most had files, and those did not line up -- a different fact.
        chosen = [r for r in problems if gui_run.problem_kind(r) == gui_run.WAITING
                  and r.get(u"waiting_by_choice")]
        if chosen:
            strip = Styled(host, u"quiet")
            box = QHBoxLayout(strip)
            box.setContentsMargins(PAD, 14, PAD, 8)
            box.setSpacing(8)
            lead = label(u"%d waiting for the next search" % len(chosen), u"hadb", strip)
            mark(lead, u"kind", u"notfound")
            box.addWidget(lead)
            soonest = min(gui_run.retry_due(r) for r in chosen)
            box.addWidget(label(u"— %s · %s" % (
                u", ".join(episode_name(r) for r in chosen[:4]),
                gui_run.retry_text({u"retry_after": soonest.isoformat()}, now,
                                   state.watching, state.daily())), u"had", strip))
            back = button(u"Show them", strip)
            back.setToolTip(wrap(u"Puts these back as picks now, with every file "
                                 u"hato tried."))
            back.clicked.connect(lambda _c=False, rs=list(chosen): self.show_waited(rs))
            box.addWidget(back)
            box.addStretch(1)
            column.addWidget(strip)

        not_yet = [r for r in problems if gui_run.problem_kind(r) == gui_run.WAITING
                   and not r.get(u"waiting_by_choice")]
        if not_yet:
            names = u", ".join(episode_name(row) for row in not_yet[:4])
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
            # ⭐ THE REAL WAIT, NOT "TOMORROW" (4b). The soonest of them, said the
            # way `retry_text` says it: a promise only when the tray will keep it.
            soonest = min((gui_run.retry_due(r) for r in not_yet
                           if gui_run.retry_due(r) is not None), default=None)
            when = gui_run.retry_text({u"retry_after": soonest.isoformat()},
                                      now, state.watching,
                                      state.daily()) if soonest else u""
            box.addWidget(label(
                u"— %s%s" % (names, u" · %s" % when if when else u""),
                u"had", strip))
            # ⭐ AND THE MANUAL CHOICE, ONE CLICK AWAY -- `05-interface.md`'s
            # *"unless prompted is a Retry on one row"*, which was never built.
            again = button(u"Look again now", strip)
            again.setToolTip(wrap(
                u"Asks jimaku about these episodes now instead of waiting. One "
                u"request per show, and nothing is downloaded unless a new file "
                u"is there."))
            again.clicked.connect(
                lambda _c=False, rs=list(not_yet): self.look_again(rs))
            self._not_while_running(again)
            box.addWidget(again)
            # ⚠ BOTH WAITS. A show jimaku has no entry for at all waits 30 days,
            # and sat under a tooltip saying 24 hours (ADVERSARY 2026-09-22 A17).
            box.addWidget(info_dot(
                u"A just-aired episode usually has no subtitle for hours or "
                u"days. hato waits %s before asking again about an episode jimaku "
                u"has no file for yet — and %s when jimaku has no entry for the "
                u"show at all — rather than burning requests. There is nothing "
                u"to pair in the meantime.%s"
                % (self._window_text(), self._window_text(self.state.hard_days),
                   u"" if state.watching else
                   # ⭐ D2 -- the daily run asks again on its own too.
                   u"\n\nhato is not in the tray, so the daily run at %s asks "
                   u"again — or Look again now." % state.schedule if state.auto else
                   u"\n\nhato is not in the tray, so nothing asks again on its "
                   u"own — the next run does, or Look again now."), strip))
            box.addStretch(1)
            column.addWidget(strip)

        broken = [r for r in problems if gui_run.problem_kind(r) == gui_run.TROUBLE]
        if broken:
            strip = Styled(host, u"quiet")
            box = QVBoxLayout(strip)
            box.setContentsMargins(PAD, 8, PAD, 8)
            box.setSpacing(4)
            lead = label(u"%d had a problem" % len(broken), u"hadb", strip)
            mark(lead, u"kind", u"notrack")
            box.addWidget(lead)
            # ⭐ EACH ONE'S OWN REASON. Since A6 this group holds refusals with
            # nothing to pick -- two videos on one file, a name with no episode
            # number -- and the reason is the only thing that says what to do.
            # One reason under a count of several said it for one of them.
            #: [!] ENGINE PROSE. Through `safe()` before it reaches a widget.
            #: [!] AND IT NEEDS THE STRETCH FACTOR: without one, beside a
            #: trailing stretch, an eliding label is allotted ZERO width and
            #: renders as nothing at all. Present, correct, invisible.
            for row in broken[:4]:
                box.addWidget(Elide(
                    u"— %s: %s" % (episode_name(row) or row.get(u"name") or u"",
                                   safe(row.get(u"reason"), u"see the log")),
                    strip, u"had"), 1)
            if len(broken) > 4:
                box.addWidget(label(u"— and %d more" % (len(broken) - 4), u"had", strip))
            column.addWidget(strip)

        if not rows and not chosen and not not_yet and not broken:
            column.addWidget(self._empty(
                u"Nothing needs you.",
                u"Episodes hato could not settle on its own land here."))
        column.addStretch(1)

    def _window_text(self, days=None):
        u"""A retry window, in words -- the soft one unless told. -> *"24 hours"* / *"3 days"*"""
        days = (self.state.retry_days if days is None else days) or 1
        return u"24 hours" if days == 1 else u"%d days" % days

    def _not_while_running(self, control):
        u"""⛔ A look-again while a run is going did nothing, and said nothing
        (ADVERSARY 2026-09-22 A30). It is disabled, and says why."""
        if self.state.running:
            control.setEnabled(False)
            control.setToolTip(wrap(u"A run is going — this is here again when it "
                                    u"finishes."))

    def _pick_said(self, said, parent):
        u"""What the last pick on this row came to, when it did not land.

        🚨 D7. A pick used to go green at the click and nothing was ever read
        back -- over a child that had died on a usage error. The row now says
        what `hato sync` answered, in hato's own words (`safe`d: the engine's
        reason is verbatim prose and may carry its alarming word).
        """
        word, why = said
        strip = Styled(parent, u"quiet")
        box = QHBoxLayout(strip)
        box.setContentsMargins(0, 2, 0, 0)
        box.setSpacing(6)
        lead = label(u"that one %s" % word, u"hadb", strip)
        mark(lead, u"kind", u"notrack")
        box.addWidget(lead)
        box.addWidget(Elide(u"— %s" % safe(why, u"the timing did not hold"),
                            strip, u"had"), 1)
        return strip

    def _pick_actions(self, row, key, parent):
        strip = Styled(parent, u"acts")
        box = QHBoxLayout(strip)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(9)
        state = self.state
        # ⛔ A ROW WHOSE PICK LANDED, OR IS STILL WITH `hato sync`, IS NOT ASKING.
        # It offered *Wait for it* and *Try 3 more* beside "used", and a click
        # filed a written row as waiting (ADVERSARY 2026-09-22 A9).
        if key in state.picked or key in state.pick_pending:
            box.addWidget(label(u"Written — your pick." if key in state.picked
                                else u"Writing your pick…", u"hint", strip))
            box.addStretch(1)
            return strip
        box.addWidget(label(u"Click one to use it.", u"hint", strip))
        #: [*] BLACKLIST STAYS A BUTTON. It is a DIFFERENT decision and must
        #: not be reachable by the same reflex as choosing a file.
        blacklist = button(u"Blacklist this video", strip)
        blacklist.clicked.connect(lambda _c=False, k=key: self.blacklist(k))
        box.addWidget(blacklist)
        # ⭐ HANDOFF 4c -- *"a button that suggests only for those ones, and is
        # highlighted ... it will search again in 24 hours"*. The automatic path,
        # made explicit: hato searches again on its own at the retry, and this
        # puts the row away until then. HIGHLIGHTED only when the episode is one
        # past the newest on offer; offered, plainly, on every other row.
        # ⛔ Only with a retry STILL AHEAD to wait for -- one already due puts
        # nothing away, and was offered highlighted anyway (A8). A control that
        # would do nothing vanishes (dev-build).
        due = gui_run.retry_due(row)
        if due is not None and due > state.clock():
            late = gui_run.probably_not_out(row)
            wait = button(u"Wait for it", strip, accent=late)
            when = gui_run.retry_text(row, state.clock(), state.watching,
                                      state.daily())
            # ⚠ WITHOUT THE TRAY NOTHING SEARCHES ON ITS OWN, and this promised
            # that something would (A21). ⭐ D2 -- unless the daily run is on.
            wait.setToolTip(wrap(
                (u"hato searches for this episode again on its own (%s). " % when
                 if state.watching or state.auto else
                 u"hato looks again the next time it runs (%s) — it is not in the "
                 u"tray, so nothing runs it on its own before then. " % when)
                + u"This puts the row away until then — if that search finds "
                  u"nothing, it comes back here."))
            wait.clicked.connect(lambda _c=False, r=row: self.wait_for(r))
            box.addWidget(wait)
        # ⭐ ONE OF TWO, AND BOTH NOW DO SOMETHING (D3). "Try 3 more" ran the
        # video's folder with no flag, and for the day after a refusal -- the
        # only time anybody presses it -- the gate said "waiting" and tried
        # nothing. Both are `--retry-now --only <video>` now: the wait is
        # skipped, and a file already refused is still never fetched again.
        # ⚠ "Try 3 more" ONLY WHEN MORE ARE KNOWN TO BE THERE. What hato remembers
        # cannot say how many the entry offers (None), and the button promised
        # three new files where there may be none (A24). Same argv, honest word.
        offered = row.get(u"candidates_offered")
        tried = len(candidates(row))
        if offered is not None and offered > tried:
            more = button(u"Try 3 more candidates", strip)
            more.clicked.connect(lambda _c=False, k=key: self.try_more(k))
        else:
            more = button(u"Look again now", strip)
            more.setToolTip(wrap(
                u"Every file jimaku offered for this episode has been tried. "
                u"This asks again now for anything new, instead of waiting."
                if offered is not None else
                u"Asks jimaku again now for anything new, instead of waiting. A "
                u"file already tried is never downloaded again."))
            more.clicked.connect(
                lambda _c=False, r=row: self.look_again([r]))
        self._not_while_running(more)
        box.addWidget(more)
        box.addWidget(info_dot(
            u"These are the files hato downloaded for this episode — never the "
            u"whole jimaku catalogue. None of them lined up with your copy on "
            u"timing, which is why hato did not choose one for you.\n\n"
            + (u"Clicking one uses it anyway: it is your call, and the row "
               u"will say it was yours."
               if gui_run.PICK_OVERRIDES_TIMING else
               u"Clicking one checks it again against your copy's timing.")
            + u"\n\nhato also looks again on its own after %s." % self._window_text(),
            strip))
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
        stack.addWidget(self._card_memory(holder))
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
        state = self.state
        if state.auto_supported:
            top = QWidget(card)
            line = QHBoxLayout(top)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(10)
            switch = Switch(top)
            switch.setChecked(state.auto)
            switch.clicked.connect(self._toggle_auto)
            line.addWidget(switch)
            line.addWidget(label(u"every day at", None, top))
            self.time_field = QLineEdit(state.schedule, top)
            self.time_field.setObjectName(u"time")
            self.time_field.setFixedWidth(78)
            self.time_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.time_field.editingFinished.connect(self._set_schedule)
            line.addWidget(self.time_field)
            # ⭐ SAY WHEN IT RESOLVES -- derived from the task and the clock. ⛔ This
            # read a `next_run` field nothing ever set; only the suite's fixture
            # did, and the D2 shot showed *"next run in 4 hours"* beside a switch
            # that was OFF.
            when = gui_run.next_run_text(state.daily(), state.clock())
            if when:
                line.addWidget(label(when, u"hint", top))
            line.addStretch(1)
            body.addWidget(top)
        # 🚨 D2 -- THIS SENTENCE WAS A CLAIM ABOUT A TASK NOBODY REGISTERED:
        # *"Windows wakes hato at that time"*, over a switch that did nothing. It
        # now says what Task Scheduler holds -- and when the computer is off at
        # the time, when the run happens instead (`StartWhenAvailable`).
        body.addWidget(paragraph(gui_run.daily_run_text(
            state.auto, state.schedule, state.watch, state.auto_supported), card))
        said = state.schedule_said or state.auto_note
        if said:
            # ⚠ Only when there is something to say, and it says the fix. Styled
            # as the Start-with-Windows row's own note, its sibling (LOOKED: a hue
            # of its own was tried and `NO_TRACK` is a grey -- the faint-labels
            # question is Sonic's, and this joins it rather than answering it).
            body.addWidget(paragraph(said, card))
        # ⭐ 4b -- SONIC ASKED FOR THE INTERVAL TO BE SHOWN HERE. The retry was
        # working and nothing anywhere said it existed, let alone how long it
        # waits. ⚠ The number is hato's own (`hato problems` reports it), never a
        # literal typed into the window.
        retry = QWidget(card)
        line = QHBoxLayout(retry)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(5)
        # ⚠ The Watch row's grammar -- a short bright fact, then a dim
        # qualifier. As one long bright sentence it read as a heading (LOOKED).
        line.addWidget(label(u"Looks again after %s" % self._window_text(),
                             None, retry))
        line.addWidget(label(u"· at an episode it could not settle", u"hint", retry))
        line.addWidget(info_dot(
            u"A subtitle that did not line up with your copy, or an episode "
            u"jimaku has no file for yet, is not asked about again straight "
            u"away — the answer rarely changes within the hour, and every "
            u"question spends a request. After %s it is tried again, and any "
            u"file it has not tried before is fetched.\n\n"
            u"While hato is in the tray this happens on its own at the time "
            u"shown on the row. Without the tray it happens on the next run%s. "
            u"Either way, Look again now on the row does it immediately."
            % (self._window_text(),
               # ⭐ D2 -- the daily run is a run that happens on its own too.
               u" — the daily one at %s, while that is on" % state.schedule
               if state.auto else u""), retry))
        line.addStretch(1)
        body.addWidget(retry)

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
        #: 🚨 AND A CLAIM ABOUT THE BUILD IT IS SHOWN IN. 13.4 MB is the tray run
        #: from SOURCE; the exe's tray carries its own CPython and measured 30.6 MB
        #: (smoke, 2026-09-22) -- 1.0.1 told every exe user "13 MB".
        mb, detail = tray_cost()
        pair.addWidget(label(u"Sits in the tray · %s" % mb, u"hint", second))
        pair.addWidget(info_dot(detail, second))
        pair.addStretch(1)
        column.addWidget(second)
        if self.state.old_tray:
            # ⭐ V1 -- AN OLDER TRAY WATCHES BUT KEEPS NO RETRY DATE, and turning
            # watching on does not replace one that is running. Said where the
            # tray is controlled, with the one action that fixes it.
            third = QWidget(text)
            pair = QHBoxLayout(third)
            pair.setContentsMargins(0, 2, 0, 0)
            pair.setSpacing(8)
            old = label(u"The hato in your tray is an older version — it watches, "
                        u"but does not look again on its own at a retry date.",
                        u"hint", third)
            old.setWordWrap(True)
            pair.addWidget(old, 1)
            restart = button(u"Restart the tray", third)
            restart.clicked.connect(self.restart_watcher)
            pair.addWidget(restart)
            column.addWidget(third)
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
            # ⚠ WRAPPED. Qt does not wrap a label unless told to, and an
            # unwrapped one does not overflow -- it silently truncates. Both
            # strings here are full sentences that say what to do about a
            # problem, so losing their second half loses the instruction.
            said = label(note, u"hint", text)
            said.setWordWrap(True)
            column.addWidget(said)

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
            # ⛔ jimaku's own words, and they can carry the one word this window
            # never says -- *"jimaku refused the key"* reached the card verbatim
            # (ADVERSARY 2026-09-22 A11). Said in hato's words instead.
            status = label(safe(self.state.key_status,
                                u"jimaku did not accept that key"),
                           u"dotok" if self.state.key_ok else u"keybad", card)
            # ⚠ jimaku's words are its to choose -- an HTTP error can outgrow the
            # card, and an unwrapped label cuts it silently (LOOKED, 2026-09-23)
            status.setWordWrap(True)
            body.addWidget(status)
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

    def _card_memory(self, parent):
        u"""⭐ RUNBOOK 8g -- what hato remembers, and a way to make it forget.

        ⛔ NAMES WHAT GOES AND WHAT STAYS BEFORE ANYTHING IS ASKED. The numbers
        are hato's own dry count (`hato state --clear --json`), never a guess
        made here; the confirm names them again.
        """
        card, body = self._card(u"hato's memory", parent)
        line = QWidget(card)
        box = QHBoxLayout(line)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        counted = gui_run.memory_summary(self.state.memory)
        box.addWidget(label(counted or u"What hato tried, and when it looks again.",
                            None if counted else u"hint", line), 1)
        forget = button(u"Clear hato's memory…", line)
        forget.clicked.connect(self.choose_clear)
        box.addWidget(forget)
        body.addWidget(line)
        if self.state.memory_said:
            body.addWidget(label(self.state.memory_said, u"hint", card))
        body.addWidget(paragraph(
            u"Clearing it starts every episode without a subtitle over, as if "
            u"hato were new — each show costs a few requests to find again. "
            u"Stays: every subtitle, the originals hato kept, your settings, "
            u"your key, and the blacklist unless you say otherwise.", card))
        return card

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
            # ⚠ ONE IS NOT "THOSE 1": the ruled mock shows twelve, and at one the
            # same design read *"1 of these are ... Remove those 1"* (found by
            # looking at the Layer 8 shots, 2026-09-23).
            one = len(gone) == 1
            wrapbox.addWidget(label(
                u"1 of these is no longer on this machine" if one else
                u"%d of these are no longer on this machine" % len(gone),
                u"stalelead", text))
            tail = label(
                u"— rotated out of your library. It is keeping a row nobody needs."
                if one else
                u"— rotated out of your library. They are keeping rows "
                u"nobody needs.", u"staletext", text)
            tail.setWordWrap(True)
            wrapbox.addWidget(tail, 1)
            line.addWidget(text, 1)
            sweep = button(u"Remove it" if one else u"Remove those %d" % len(gone), notice)
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
        if entry.get(u"removing"):
            # ⭐ A31 -- going, not gone, until hato's own list says so.
            remove.setEnabled(False)
            remove.setToolTip(wrap(u"Removing — hato is taking it off its list."))
            note.setText(u"removing…")
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
    #: The wall-clock minute last re-rendered for, so dates move on screen (A16).
    _minute_seen = None

    def _anything_dated(self):
        u"""Is anything on screen tied to a date that can pass? -> bool"""
        state = self.state
        # ⭐ D2 -- *"next run in 15h"* is dated too, for as long as the daily run
        # is registered; left alone it would still say 15h in the morning.
        if state.waits or state.auto:
            return True
        return any(r.get(u"retry_after") for r in list(state.rows) + list(state.remembered or ()))

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
            # ⭐ RUNBOOK 8e -- IS SOMETHING THERE TO KEEP THE WAIT? *"retrying in
            # 14h"* is a promise only while a tray that KEEPS it is running (8h,
            # V1); read from the world on every look, never from the Settings tick.
            watching, old = self.tray_is_watching(), self.tray_is_old()
            changed = (int(self.state.queued_in) != was
                       or watching != self.state.watching
                       or old != self.state.old_tray)
            self.state.watching, self.state.old_tray = watching, old
            # ⭐ A DATE PASSES WITH NOTHING ELSE CHANGING (ADVERSARY 2026-09-22
            # A16). An open window held a waited row hidden past its date, and
            # *"retrying in 30m"* read the same five hours later. Once a minute,
            # while anything on screen is dated.
            minute = int(time.time() // 60)
            if minute != self._minute_seen:
                self._minute_seen = minute
                changed = changed or self._anything_dated()
            if changed:
                self.render()
            if self.state.running:
                return                        # ⛔ our own run owns the rows
            stamp = gui_run.last_run_stamp()
            if stamp == self._others_seen:
                return
            self._others_seen = stamp
            # ⭐ A run happened somewhere: whatever it settled or added, the
            # memory is asked again, whether or not its snapshot is usable.
            self.refresh_problems()
            self.refresh_memory()
            rows, summary, saved_at = gui_run.load_last_run()
            if not rows and not summary:
                return
            self.state.rows = rows
            self.state.summary = summary
            self.state.rows_at = self.state.moment()
            self.state.trust_rows = False      # ⭐ A27 -- a newer run's rows now
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

    def _row_for(self, key):
        u"""-> the Needs-you row with this key, from the ONE list, or None.

        ⚠ From `problems()`, not `rows`: since RUNBOOK 8e a row can come from
        what hato remembers and be in no run's rows at all.
        """
        for row in self.state.problems():
            if self.state.key(row) == key:
                return row
        for row in self.state.rows:
            if self.state.key(row) == key:
                return row
        return None

    def pair_argv(self, key, attempt):
        u"""What committing this pair would run. -> [unicode] or None

        [X] `run.argv_for_pair` builds it -- this method only finds the two
        paths. A second argv builder is a second program.
        """
        row = self._row_for(key)
        if row is None:
            return None
        subtitle = candidate_path(attempt)
        video = row.get(u"video")
        if not subtitle or not video:
            return None
        return gui_run.argv_for_pair(video, subtitle,
                                     force=gui_run.PICK_OVERRIDES_TIMING)

    def commit_pair(self, key, attempt):
        u"""[!] THE CLICK IS THE ACTION. No confirm button -- and ⛔ no claim.

        🚨 D7. This painted the row green, *"paired · <name>"*, the moment it was
        clicked, and never read the child -- which had died on a usage error
        (`hato sync` had no `--json`) for every pick ever made. ⭐ Now the click
        starts the pair and the row says *"pairing"*; `finish_pick` says what
        `hato sync` answered, and only a file that LANDED is *paired*.
        """
        # ⛔ ONE PICK AT A TIME, AND NONE OVER ONE THAT LANDED. A second click
        # while the first was with `hato sync` had its answer wiped by the
        # first's (A32); a pick after one landed can only fail -- tsubasa will
        # not write over the file -- and turned the row green over its failure
        # word (A10). The cards are inert then; this holds for any other caller.
        if key in self.state.pick_pending or key in self.state.picked:
            return None
        argv = self.pair_argv(key, attempt)
        if argv is None:
            # ⛔ NOT A SILENT NO-OP: a card whose file is gone says so on its row.
            # ⚠ And says only what is TRUE: a refused file is never downloaded
            # again, so "Look again now fetches it" was a remedy that is not
            # there (ADVERSARY 2026-09-22 A13).
            if self._row_for(key) is not None and attempt.get(u"name"):
                self.state.pick_said[key] = (
                    gui_run.PICK_FAILED,
                    u"hato no longer has that file — it was cleared from its "
                    u"downloads, so it cannot be used")
                self.render()
            return None
        name = attempt.get(u"name") or u""
        self.state.pick_pending[key] = name
        self.state.pick_said.pop(key, None)
        self.render()
        self._animate_accordions()
        self._read(argv, lambda finished, events, k=key, n=name:
                   self._pick_read(k, n, finished, events))
        return argv

    def _pick_read(self, key, name, finished, events):
        answer = {}
        for event in events:
            if isinstance(event, dict) and event.get(u"type") == u"pair":
                answer = event
        code = finished.code if finished is not None else gui_run.EXIT_CANNOT_RUN
        self.finish_pick(key, name, gui_run.pick_verdict(code, answer))

    def finish_pick(self, key, name, verdict):
        u"""Say what a pick came to. -> None

        ⭐ Paired (the timing held) or *used* (the person's choice, written over a
        timing refusal) closes the row green and opens the next one -- Sonic:
        *"after selecting one, the next one opens as it closes."* ⛔ Anything else
        leaves the row OPEN, asking, with hato's reason under the cards.
        """
        word, why, _written = verdict
        self.state.pick_pending.pop(key, None)
        self.state.pick_said[key] = (word, why)
        if word in (gui_run.PAIRED, gui_run.FORCED):
            self.state.picked[key] = name
            self.state.picked_word[key] = word   # ⭐ the colour is what was WRITTEN
            self.state.open_pick = self.state.next_unresolved(key)
            self.refresh_problems()          # the memory will drop it: a file landed
        self.render()
        self._animate_accordions()

    def blacklist(self, key):
        u"""[*] A DIFFERENT DECISION, and deliberately a different gesture.

        [!] THE VIDEO IS A POSITIONAL, NOT A SUBCOMMAND. The first version of
        this built `blacklist add <video>`, inventing an `add` verb the CLI
        does not have -- `hato/commands/blacklist.py` takes the video
        positionally and spells removal `--remove`. The window would have
        handed the child the literal string `add` as the video to blacklist.
        Caught by reading the command's own `register()`, not by a check: the
        suite only asserted that the word *blacklist* appeared.

        ⭐ RUNBOOK 8e: READ to the end, then the blacklist and the problems are
        asked again -- so the card gains the row and Needs you loses it without
        waiting for a run.
        """
        row = self._row_for(key)
        video = (row or {}).get(u"video") or key
        argv = gui_run.cli_argv() + [u"blacklist", video, u"--json"]
        self._read(argv, lambda finished, events, k=key:
                   self._blacklisted(k, finished, events))
        return argv

    def _blacklisted(self, key, finished, events):
        u"""What `hato blacklist` said. ⭐ On success the row goes -- from the
        run's rows too: a clash or a two-episode name is a row hato's memory
        never holds, and it went on asking after the person had decided
        (ADVERSARY 2026-09-22 A19)."""
        answer = next((e for e in events if isinstance(e, dict)
                       and (e.get(u"ok") is not None or u"blacklist" in e)), {})
        if finished is not None and finished.code == gui_run.EXIT_CLEAN \
                and answer.get(u"ok", True):
            self.state.rows = [r for r in self.state.rows if self.state.key(r) != key]
            if self.state.open_pick == key:
                self.state.open_pick = self.state.next_unresolved(key)
            self.render()
        self.refresh_blacklist()
        self.refresh_problems()

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
        # ⛔ NOT CLAIMED AT THE CLICK -- the D7 shape, left in the card D5 made
        # real: the row went and the answer was never read (ADVERSARY 2026-09-22
        # A31). It says it is going; hato's own list, re-read, is the answer.
        entry[u"removing"] = True
        argv = gui_run.cli_argv() + [u"blacklist", u"--remove", target,
                                     u"--json"]
        self._read(argv, lambda _f, _e: self.refresh_blacklist())
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
            # ⛔ Read, then the list asked again -- never dropped at the click (A31).
            entry[u"removing"] = True
            self._read(argv, lambda _f, _e: self.refresh_blacklist())
            sent.append(argv)
        self.render()
        return sent

    def wait_for(self, row):
        u"""⭐ HANDOFF 4c -- *"it will search again in 24 hours"*: the person agrees
        to wait. -> the retry date waited for, or None.

        Kept as the date it was chosen FOR (`run.apply_waits`), so the next run
        that records a new one -- or the date passing -- brings the row back.
        ⚠ Dates already past are dropped as this one is written, so the file
        only ever holds live promises.
        """
        key = gui_run.problem_key(row)
        when = row.get(u"retry_after")
        if not key or not when:
            return None
        now = self.state.clock()
        self.state.waits = dict(
            (k, v) for k, v in self.state.waits.items()
            if (gui_run.retry_due({u"retry_after": v}) or now) > now)
        self.state.waits[key] = when
        gui_run.save_waits(self.state.waits)
        if self.state.open_pick == self.state.key(row):
            self.state.open_pick = self.state.next_unresolved(self.state.key(row))
        self.render()
        self._animate_accordions()
        return when

    def show_waited(self, rows):
        u"""*Show them* -- the chosen waits are picks again, now."""
        for row in rows or ():
            self.state.waits.pop(gui_run.problem_key(row), None)
        gui_run.save_waits(self.state.waits)
        self.render()

    def try_more(self, key):
        u"""*"Try 3 more candidates"* -- three files not yet tried, now.

        🚨 D3. This ran the video's folder with no flag and `--candidates`
        raised by three. Every refusal has just recorded a soft negative, so for
        the day after one -- the only time anybody presses this -- the gate said
        "waiting to retry" and it tried NOTHING. ⭐ `--retry-now --only`: the
        wait is skipped, a file already refused is still never fetched again, so
        three means three NEW ones.
        """
        row = self._row_for(key)
        if row is None or not row.get(u"video"):
            return None
        return self._start_targeted([row], candidates=3)

    def look_again(self, rows):
        u"""⭐ *Look again now* -- ask jimaku about these episodes instead of
        waiting (4b's manual half: *"not soon unless prompted"* was specified as
        a Retry on one row and never built).

        ⚠ ONLY VIDEOS STILL THERE. `hato` refuses a whole `--only` batch over one
        name that is not a file -- so one episode moved away made *Look again
        now* on every waiting one say "could not run" and nothing else
        (ADVERSARY 2026-09-22 A20).
        """
        rows = [r for r in (rows or ()) if r.get(u"video")]
        if not rows:
            return None
        return self._start_targeted(rows)

    def _folder_for(self, video):
        u"""The WATCHED folder a video lives under, else its own. -> path

        ⚠ Not simply `dirname`: a release's numbering is fitted against the whole
        folder's range, and a season folder inside a watched one is still one
        show among its siblings.
        """
        from hato import paths as _paths
        for folder in self.state.folders:
            if _paths.under_any(video, [folder]):
                return folder
        return os.path.dirname(video) or video

    def _start_targeted(self, rows, candidates=None):
        u"""A `--only` run over these rows' videos. -> the argv, or None.

        ⚠ ONLY VIDEOS STILL THERE. `hato` refuses a whole `--only` batch over one
        name that is not a file -- so one episode moved away made *Look again
        now* on every waiting one say "could not run" and nothing else
        (ADVERSARY 2026-09-22 A20).
        """
        videos = [row[u"video"] for row in rows if os.path.isfile(row[u"video"])]
        if not videos:
            self.state.live = (u"not looked at — %s no longer where hato saw %s"
                               % (u"that video is" if len(rows) == 1 else u"those videos are",
                                  u"it" if len(rows) == 1 else u"them"))
            self.render()
            return None
        argv = gui_run.argv_for_retry(videos, [self._folder_for(v) for v in videos],
                                      candidates=candidates)
        return self.start_run(argv=argv, targeted=True)

    # -- children the window READS (RUNBOOK 8e) ------------------------------

    #: How often a child being read is polled. A `poll()`, so it costs nothing.
    READ_MS = 150

    def _read(self, argv, done):
        u"""Start `argv` through the ONE spawn seam and call `done(run, events)`
        once it has exited and both pipes are drained. Never blocks.

        ⚠ The suite's `spawn` returns no process: nothing is read, and a check
        drives `done`'s effect directly (`finish_pick`, `apply_problems`).
        """
        process = self.spawn(argv)
        if process is None or getattr(process, u"stdout", None) is None:
            return None
        runner = gui_run.Runner.adopt(process, argv)
        self._reading.append((runner, done, []))
        if self._read_timer is None:
            self._read_timer = QTimer(self)
            self._read_timer.setInterval(self.READ_MS)
            self._read_timer.timeout.connect(self._poll_reads)
        if not self._read_timer.isActive():
            self._read_timer.start()
        return runner

    def _poll_reads(self):
        still = []
        for runner, done, events in self._reading:
            events.extend(runner.drain())
            finished = runner.finished()
            if finished is None:
                still.append((runner, done, events))
                continue
            events.extend(runner.drain())
            try:
                done(finished, events)
            except Exception as exc:          # noqa: BLE001 -- never take the window down
                sys.stderr.write(u"hato: a child's answer could not be used: %s\n" % exc)
        self._reading = still
        if not still and self._read_timer is not None:
            self._read_timer.stop()

    def refresh_problems(self):
        u"""⭐ RUNBOOK 8c/8e -- ask hato what still needs a person.

        `hato problems --json`: the state DB, filtered by the disk. This is the
        store that outlives one run, and why a problem episode no longer
        disappears when a run looks somewhere else (4a).

        ⛔ One at a time -- and a request made while one is in flight is QUEUED,
        never dropped. Dropped, a run's own refresh was lost to one started a
        moment earlier, whose answer (the DB before the run) then landed newer
        than the run's rows and settled its new refusals (ADVERSARY 2026-09-22 A2).
        """
        if self._problems_in_flight:
            self._problems_again = True
            return None
        self._problems_in_flight = True
        #: ⭐ The answer describes the DB as it was when ASKED, so that is its
        #: moment -- not when it arrived, which made a stale answer newer (A2).
        asked = self.state.moment()
        runner = self._read(gui_run.argv_for_problems(),
                            lambda finished, events: self._problems_read(
                                finished, events, asked))
        if runner is None:
            self._problems_in_flight = False
        return runner

    def _problems_read(self, finished, events, asked=None):
        u"""⛔ ONLY A CLEAN ANSWER REPLACES WHAT IS ON SCREEN: exit 0 and a summary
        that says `ok`. A broken config exits 1, and an unreadable store used to
        answer an empty list -- both were taken for *"nothing needs you"*, and
        Needs you was emptied over an answer hato itself said was wrong
        (ADVERSARY 2026-09-22 A1). ⭐ The window keeps what it had and says why."""
        self._problems_in_flight = False
        summary = {}
        for event in events:
            if isinstance(event, dict) and event.get(u"type") == u"problems":
                summary = event
        if finished is not None and finished.code == gui_run.EXIT_CLEAN \
                and summary.get(u"ok") is True:
            self.state.problems_error = u""
            self.apply_problems(finished.rows, summary, asked=asked)
        else:
            self.state.problems_error = (
                (summary.get(u"error") if summary else u"")
                or (finished.said if finished is not None else u"")
                or u"it did not answer")
            self.render()
        if self._problems_again:
            self._problems_again = False
            self.refresh_problems()

    def apply_problems(self, rows, summary=None, asked=None):
        u"""Take what `hato problems` said. -> None

        `asked` -- the moment the question went out (`State.moment`, see
        `refresh_problems`); now, when a caller already holds the answer.
        """
        self.state.remembered = list(rows or ())
        self.state.remembered_at = asked if asked is not None else self.state.moment()
        windows = (summary or {}).get(u"retry_days") or {}
        for name, attr in ((u"soft", u"retry_days"), (u"hard", u"hard_days")):
            days = windows.get(name)
            if isinstance(days, int) and not isinstance(days, bool) and days > 0:
                setattr(self.state, attr, days)
        self.render()

    def refresh_blacklist(self):
        u"""D5 -- load the blacklist hato actually holds. It never was."""
        return self._read(gui_run.argv_for_blacklist(), self._blacklist_read)

    # -- ⭐ RUNBOOK 8g: clearing hato's memory ----------------------------------

    def refresh_memory(self):
        u"""Ask hato what a clear WOULD take -- the card's numbers. ⛔ A dry
        count takes no lock, so asking can never stall a run."""
        return self._read(gui_run.argv_for_clear(), self._memory_read)

    def _memory_read(self, finished, events):
        for event in events:
            if isinstance(event, dict) and event.get(u"type") == u"clear" \
                    and event.get(u"ok") and event.get(u"dry_run"):
                self.state.memory = event
                self.render()
                return

    def choose_clear(self):
        u"""*Clear hato's memory…* -- confirm first, then clear. ⛔ Cancel runs nothing."""
        dialog = ClearDialog(self, self.state.memory, len(self.state.blacklist))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        self.state.memory_said = u"Clearing…"
        self.render()
        return self._read(gui_run.argv_for_clear(yes=True,
                                                 blacklist=dialog.forget_blacklist()),
                          self._memory_cleared)

    def _memory_cleared(self, finished, events):
        u"""Say what the clear came to -- ⛔ never "cleared" over a refusal."""
        answer = next((e for e in events if isinstance(e, dict)
                       and e.get(u"type") == u"clear"), None)
        if answer is not None and answer.get(u"ok") and not answer.get(u"dry_run"):
            self.state.memory_said = (u"Cleared — every episode without a subtitle "
                                      u"is looked at again on the next run.")
            # ⭐ A27 -- the memory is empty BECAUSE IT WAS CLEARED. Until the next
            # run, its silence settles nothing: the episodes on screen still
            # have no subtitle, and Needs you emptied over them.
            self.state.trust_rows = True
        elif answer is not None and answer.get(u"busy"):
            self.state.memory_said = (u"A run is going, so nothing was cleared — try "
                                      u"again when it finishes.")
        else:
            self.state.memory_said = u"hato could not clear its memory: %s" % (
                safe((answer or {}).get(u"error")) or u"it did not answer")
        self.render()
        self.refresh_memory()
        self.refresh_problems()
        self.refresh_blacklist()

    def _blacklist_read(self, finished, events):
        for event in events:
            if isinstance(event, dict) and u"blacklist" in event:
                self.state.blacklist = gui_run.blacklist_entries(event)
                self.render()
                return

    def _toggle_auto(self):
        u"""⭐ D2 -- register or remove the daily run, then READ IT BACK.

        🚨 IT REGISTERED NOTHING, AND COULD NOT BE TURNED OFF. On it flipped a
        flag; off it sent `hato config --set schedule=off`, which the config
        refuses by name, and the window never read the refusal.
        ⛔ ASKS WINDOWS what the state is rather than trusting the switch, as
        `_toggle_startup` does -- the switch was drawn when the window opened.
        """
        from hato import schedule as _schedule
        said = u""
        try:
            task = _schedule.read()
            _schedule.set_enabled(not _schedule.is_enabled(task), self.state.schedule)
        except _schedule.ScheduleError as exc:
            said = u"%s" % exc
        read_schedule(self.state)
        self.state.schedule_said = safe(said) if said else u""
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

    @staticmethod
    def tray_is_watching():
        u"""-> True when the tray watcher is really running.

        ⭐ A MEASURED SWITCH (`build-ui.md`): the pid AND its start stamp, via
        `watch.watching_pid` -- never the Settings tick, which says what was
        asked for and not what is running. It decides whether *"retrying in
        14h"* is a promise (RUNBOOK 8h) or only the date the retry becomes due.
        """
        try:
            from hato import watch as _watch
            caps = _watch.watching_capabilities()
            # 🚨 A TRAY THAT KEEPS NO PROMISE IS NOT ONE. Sonic's 1.0.1 tray writes
            # the same pid file and has no retry clock, so after an upgrade the
            # window promised retries nothing would keep (ADVERSARY 2026-09-22 V1).
            return caps is not None and u"retries" in caps
        except Exception:                     # noqa: BLE001 -- a guess must not crash
            return False

    @staticmethod
    def tray_is_old():
        u"""-> True when a tray IS running and is one that keeps no retry promise.

        ⭐ V1 -- turning watching on does not replace a running tray, so the
        window says so and offers to restart it (`restart_watcher`).
        """
        try:
            from hato import watch as _watch
            caps = _watch.watching_capabilities()
            return caps is not None and u"retries" not in caps
        except Exception:                     # noqa: BLE001
            return False

    def restart_watcher(self):
        u"""⭐ V1 -- replace an older tray with this build's. -> the argv, or None."""
        self.stop_watcher()
        argv = self.start_watcher()
        self.state.old_tray = False
        self.render()
        return argv

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
        u"""A new time: kept in the config, and -- ⭐ D2 -- given to the task.

        ⛔ A time the config would refuse is refused HERE, in words, and the
        field put back. It used to go to `hato config --set`, be refused there,
        and nothing said so. 🚨 And a registered task runs at the time it was
        registered at: without re-registering, the header would say 04:30 while
        Windows went on starting hato at 03:00.
        """
        from hato import config as _config
        from hato import schedule as _schedule
        value = self.time_field.text().strip()
        if not value or value == self.state.schedule:
            return
        if not _config.is_clock(value):
            self.state.schedule_said = (u"%s is not a time — use 24-hour, like "
                                        u"03:00." % value)
            self.time_field.setText(self.state.schedule)
            self.render()
            return
        self.state.schedule = value
        self.state.schedule_said = u""
        self.spawn(gui_run.argv_for_config(u"--set", u"schedule=%s" % value))
        if self.state.auto:
            said = u""
            try:
                _schedule.enable(value)
            except _schedule.ScheduleError as exc:
                said = u"%s" % exc
            read_schedule(self.state)
            self.state.schedule_said = safe(said) if said else u""
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

    def start_run(self, argv=None, targeted=False):
        u"""Spawn `hato --json --progress` and paint what comes back.

        [X] `run.Runner` owns the process, the two reader threads and the
        parse; this method owns a timer that drains it.

        ⭐ `targeted` (RUNBOOK 8e): a `--only` look-again. Its rows REPLACE their
        own videos' rows and leave every other row where it is -- a look-again
        on one episode must not empty the Subtitles tab.
        """
        if self.state.running or (not self.state.folders and not targeted):
            return None

        # 🚨 NO KEY IS A REFUSAL, NOT A RUN. Sonic, 2026-09-19, on the
        # published 1.0.0: *"I gave it a new folder to look at, and ran it, it
        # doesn't do anything ... I THINK that behavior happened because i
        # didn't have the API key in."*
        #
        # ⛔ Every request hato makes needs the key, so a keyless run cannot
        # do anything at all -- and spawning one produced a child that wrote
        # its explanation to a stderr this window does not read, exited, and
        # left the footer saying "done". A person cannot tell that apart from
        # "there was nothing to fetch".
        #
        # ⭐ Refused HERE, before anything is spawned, so the reason is the
        # thing on screen rather than an exit code nobody sees.
        if not self.state.key_hint:
            self.state.live = u"no jimaku key — add one in Settings"
            self.state.tab = TAB_SUBS
            self.render()
            return None

        argv = argv if argv is not None else gui_run.argv_for(self.state.folders,
                                                              progress=True)
        self.state.running = True
        self._targeted = bool(targeted)
        self._busy = False
        # 🚨 NOTHING IS CLEARED AT THE CLICK (ADVERSARY 2026-09-22 A3). A run that
        # meets another's lock says only "busy" -- and the Subtitles tab, the
        # footer and the picks had already been emptied under it, with *"last
        # run"* set for a run that looked at nothing. The old rows go when the
        # new run first SAYS something (`_begin_fresh`).
        # ⛔ And a look-again leaves `rows_at` alone: it is new about its own
        # videos only (`live_keys`), never about the whole snapshot (A4).
        self._fresh = not targeted
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

    def _begin_fresh(self):
        u"""⭐ A3 -- a full run has started SAYING things: now the old run's rows go."""
        self._fresh = False
        self.state.rows = []
        self.state.summary = {}
        self.state.picked = {}
        self.state.pick_said = {}
        self.state.picked_word = {}
        self.state.trust_rows = False          # its rows are the newest word now

    def _finished_line(self, finished):
        u"""What the footer says about a run that has ended. -> text

        🚨 EXIT 1 IS A RUN THAT STOPPED -- a 401, a server gone, a crash -- and it
        was painted *done*, with the reason nowhere (ADVERSARY 2026-09-22 A12).
        ⚠ Exit 2 says what `hato` said (A20); a look-again says what it cost,
        which the footer's run total never includes (A23). ⛔ Every word hato
        did not compose goes through `safe()`.
        """
        if self._busy:
            return u"hato was already running — try again when it finishes"
        if finished.could_not_run:
            said = safe(finished.said)
            return u"could not run — %s" % said if said else u"could not run"
        if finished.stopped:
            why = (finished.summary or {}).get(u"stopped")
            why = why if isinstance(why, str) and why else finished.said
            return u"stopped — %s" % safe(why) if why else u"stopped early"
        if self._targeted:
            calls = (finished.summary or {}).get(u"api_calls")
            spent = seconds_text((finished.summary or {}).get(u"seconds"))
            if isinstance(calls, int) and not isinstance(calls, bool):
                return u"done · looked again: %d API call%s%s" % (
                    calls, u"" if calls == 1 else u"s", (u" · " + spent) if spent else u"")
        return u"done"

    def _drain(self):
        if self._runner is None:
            return
        for event in self._runner.drain():
            kind = event.get(u"type")
            if kind in (u"video", u"run") and self._fresh:
                self._begin_fresh()
            if kind == u"video":
                key = self.state.key(event)
                if self._targeted:
                    # ⭐ A LOOK-AGAIN REPLACES ITS OWN ROW and nothing else.
                    self.state.rows = [r for r in self.state.rows
                                       if self.state.key(r) != key] + [event]
                    self.state.picked.pop(key, None)
                    self.state.picked_word.pop(key, None)
                else:
                    self.state.rows.append(event)
                    self.state.rows_at = self.state.moment()
                # ⭐ A4 -- newer than the memory for THIS video, not for all of them
                self.state.live_keys.add(key)
                self.state.live_at = self.state.moment()
            elif kind == u"run":
                if not self._targeted:
                    self.state.summary = event
            elif kind == u"busy":
                # ⭐ RUNBOOK 8e. Another run held the lock: this one looked at
                # nothing. It used to finish as "done" over an empty list.
                self._busy = True
            elif kind == u"progress":
                #: [!] ENGINE-WRITTEN, so it goes through `safe()` like every
                #: other field hato did not compose itself.
                self.state.live = safe(event.get(u"name")
                                       or event.get(u"stage")) \
                    or self.state.live
        finished = self._runner.finished()
        if finished is not None:
            self.state.running = False
            ran = not self._busy and not finished.could_not_run
            if not self._targeted and ran and not self._fresh:
                self.state.summary = finished.summary or self.state.summary
            self.state.live = self._finished_line(finished)
            if not self._targeted and ran and not self._fresh:
                # ⚠ Only a run that RAN is the last run (A3).
                self.state.last_run = time.strftime(u"%H:%M")
            self._targeted = False
            self._fresh = False
            # ⭐ AND ASK AGAIN WHAT STILL NEEDS A PERSON -- the run may have
            # settled some and added others, in folders this window never ran.
            self.refresh_problems()
            self.refresh_memory()            # 8g: the card's numbers moved too
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


def read_schedule(state):
    u"""⭐ D2 -- THE DAILY RUN'S SWITCH, READ FROM TASK SCHEDULER. -> state

    A MEASURED SWITCH (`workflows/build-ui.md`): its position comes from the
    world on every open, never from a stored flag. `bool(cfg.schedule)` read ON
    for days over no task at all. ⭐ And the TIME shown is the task's own when
    one exists -- the header must say when Windows will actually start hato.
    ⚠ A read that fails reads OFF, with what went wrong said beside the switch.
    """
    from hato import schedule as _schedule
    state.auto_supported = _schedule.supported()
    try:
        task = _schedule.read()
    except _schedule.ScheduleError as exc:
        state.auto, state.auto_note = False, safe(u"%s" % exc)
        return state
    state.auto = _schedule.is_enabled(task)
    state.auto_note = safe(_schedule.note(task))
    if task is not None and task.at:
        state.schedule = task.at
    return state


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
        state.surasura_dir = cfg.surasura_dir
    except (_config.ConfigError, paths.PathError) as exc:
        # ⛔ NOT SWALLOWED. A config hato refuses is why the settings look
        # empty, and a window that opened on silent defaults would be telling
        # the person their settings vanished.
        state.config_error = str(exc)
        sys.stderr.write(u"hato: %s\n" % exc)
    # ⭐ D2 -- whether the daily run is ON is Task Scheduler's to say, and the
    # time it runs at is the task's own when one exists. AFTER the config, so the
    # config's time is only the one to register at.
    read_schedule(state)
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
    # ⭐ RUNBOOK 8e -- what hato REMEMBERS needs a person, whichever run last
    # looked (4a), the blacklist it actually holds (D5), and whether the tray is
    # there to keep a promised retry (8h). Read, never assumed.
    window.state.watching = window.tray_is_watching()
    window.state.old_tray = window.tray_is_old()       # V1 -- an older tray keeps nothing
    window.state.waits = gui_run.load_waits()          # 4c -- the waits chosen before
    window.refresh_problems()
    window.refresh_blacklist()
    window.refresh_memory()                  # 8g -- what a clear would take
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
