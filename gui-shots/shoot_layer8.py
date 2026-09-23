# -*- coding: utf-8 -*-
u"""
Photograph the Layer 8 states of the window -- RUNBOOK 8e -- so they can be LOOKED at.

    python gui-shots/shoot_layer8.py [OUT_DIR]

⚠ SEPARATE FROM `shoot.py` ON PURPOSE. That one regenerates the PNGs the README
embeds, which describe the RELEASED window; these describe work not yet released.
They go to OUT_DIR (default: a folder under the OS temp dir), never into this one.

⭐ The same instrument as `shoot.py`, imported rather than copied: the REAL platform
plugin (offscreen on Windows loads zero fonts -- every string is tofu), 1:1 logical
pixels, `WA_DontShowOnScreen`. Every row's content is Sonic's own history -- Tsuihou
12's three refused files, Frieren 24 not on jimaku yet -- because a mock's seed data
is shipped content (`build-ui.md`): the picture is the deliverable.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import shoot                                                       # noqa: E402  (sets the platform)

from PyQt6.QtCore import Qt                                        # noqa: E402
from PyQt6.QtWidgets import QApplication                           # noqa: E402

from hato.gui import app as gui_app                                # noqa: E402
from hato.gui import run as gui_run                                # noqa: E402

import test_gui_widgets as fx                                      # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def remembered_tsuihou():
    return fx.remembered(12, due=NOW + timedelta(hours=13, minutes=20))


def remembered_frieren():
    row = fx.remembered(24, files=False, due=NOW + timedelta(hours=9, minutes=5),
                        video=u"D:\\Anime\\Sousou no Frieren S2\\ep24.mkv")
    row.update(title=u"\u846c\u9001\u306e\u30d5\u30ea\u30fc\u30ec\u30f3", season=2,
               name=u"[SubsPlease] Sousou no Frieren S2 - 24 (1080p).mkv",
               reason=u"jimaku entry 11446 has no file for this episode")
    return row


def remembered_from(row, hours=23):
    u"""The same problem as `hato problems` reports it after the run that made it.

    🚨 THE FIRST SHOTS LEFT THIS OUT, AND THE PICTURE LIED: the run's own Re:Zero
    54 row vanished from Needs you, because a memory that does not list a row the
    DB holds is read as "settled since". Real memory lists every problem the DB
    holds, so the shot's must too -- a mock's seed data is shipped content.

    ⚠ BUILT BY THE SAME PRODUCER `hato problems` USES (`fx.memory_row`), never a
    copy of the run's row with fields swapped: that copy kept the run's
    `candidates_offered: 3`, which memory can never know (ADVERSARY 2026-09-22
    A24), and the shot showed *Try 3 more* where the real window says *Look
    again now*.
    """
    tried = tuple(fx._pipeline.Remembered(
        a[u"name"], u"REFUSED", a[u"reason"], a[u"bytes"], a[u"match_rate"],
        (a.get(u"tsubasa") or {}).get(u"subtitle"), NOW - timedelta(hours=24 - hours))
        for a in row.get(u"attempts") or ())
    return fx.memory_row(row[u"video"], row[u"outcome"], row[u"reason"],
                         title=row[u"title"], season=row[u"season"],
                         episode=row[u"episode"], jimaku_entry=row[u"jimaku_entry"],
                         tried_before=tried, retry_after=NOW + timedelta(hours=hours))


def window_over(rows, memory, watching):
    window = fx.make(rows=rows, running=False, live=u"done")
    window.state.now = NOW
    window.state.watching = watching
    window.state.rows_at = window.state.moment()      # the snapshot, then the memory
    window.apply_problems(memory, {u"type": u"problems", u"ok": True,
                                   u"retry_days": {u"soft": 1, u"hard": 30}})
    return window


def main(out_dir):
    # ⛔ ITS OWN STORE. Shot 16 clicks *Wait for it*, which writes the window's
    # waits file -- into the REAL per-user store, without this. A picture must
    # never change what hato remembers.
    os.environ["HATO_CACHE"] = tempfile.mkdtemp(prefix=u"hato-shots-store-")
    application = QApplication.instance() or QApplication([])
    shoot.pin_machine_state()                 # ⛔ not this machine's registry
    os.makedirs(out_dir, exist_ok=True)
    failures = []

    def take(window, name, width=None, height=None):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        window.resize(width or gui_app.WIN_W, height or gui_app.WIN_H)
        shoot.settle(application, window)
        path = os.path.join(out_dir, name + u".png")
        ok = window.grab().save(path)
        print(u"  %-38s %s %s" % (name + u".png", u"ok" if ok else u"FAILED",
                                   os.path.getsize(path) if ok else u""))
        if not ok:
            failures.append(name)

    def open_row(window, key):
        window.state.open_pick = key
        window.render()
        for k, accordion in window._accordions.items():
            accordion.set_open(k == key, animate=False)

    run_rows = [fx.added(1, rate=0.82), fx.added(2, rate=0.96), fx.needs_you(54)]
    memory = [remembered_from(fx.needs_you(54)), remembered_tsuihou(), remembered_frieren()]

    # 1 -- Needs you: a run row AND two remembered ones; the tray is watching
    window = window_over(run_rows, memory, watching=True)
    window.show_tab(gui_app.TAB_PICK)
    take(window, u"L8-01-needs-you-tray-on")

    # 2 -- the same, tray OFF: the wait says when it becomes DUE, not a promise
    off = window_over(run_rows, memory, watching=False)
    off.show_tab(gui_app.TAB_PICK)
    take(off, u"L8-02-needs-you-tray-off")

    # 3 -- the remembered Tsuihou row open: its own files, and the actions
    key = window.state.key(remembered_tsuihou())
    open_row(window, key)
    take(window, u"L8-03-remembered-row-open")

    # 4 -- a pick in flight: "pairing", never "paired" before an answer
    window.spawn = lambda argv, **kw: None
    first = gui_app.candidates(remembered_tsuihou())[0]
    window.commit_pair(key, first)
    open_row(window, key)
    take(window, u"L8-04-pick-pending")

    # 5 -- that pick did not land: the row stays, and says why.
    # ⚠ A FAILURE THIS CARD CAN HAVE. Its file is on disk (it has a path), and a
    # pick overrides timing (`PICK_OVERRIDES_TIMING`), so what stops it is the
    # WRITE -- in tsubasa's own words. The first take paired it with *"hato no
    # longer has that file"*, which only a path-less card can say, and those
    # are not clickable (ADVERSARY 2026-09-22 A13).
    window.finish_pick(key, first[u"name"], (gui_run.PICK_FAILED,
                       u"\u26d4 NOT WRITTEN: [WinError 5] Access is denied: "
                       u"'D:\\Anime\\Tsuihou\\Tsuihou - 12.ja.ass'", None))
    open_row(window, key)
    take(window, u"L8-05-pick-did-not-land")

    # 6 -- a pick written over the timing check: "used", the person's choice
    window.commit_pair(key, first)
    window.finish_pick(key, first[u"name"], (gui_run.FORCED, u"WRITTEN UNDER --force",
                                              u"D:\\x.ja.ass"))
    for k, accordion in window._accordions.items():
        accordion.set_open(window.state.open_pick == k, animate=False)
    take(window, u"L8-06-pick-used")

    # 7 -- Settings: the interval, said where Sonic asked for it
    settings = window_over(run_rows, memory, watching=True)
    settings.show_tab(gui_app.TAB_SET)
    take(settings, u"L8-07-settings-interval")

    # 8 -- Settings lower: the blacklist hato actually holds (D5)
    settings.state.blacklist = gui_run.blacklist_entries({u"blacklist": [
        {u"video_hash": u"v1-a", u"video_path": u"D:\\Anime\\Tetsunabe no Jan\\Tetsunabe no Jan - 01.mkv",
         u"added_at": u"2026-09-17T03:00:00+00:00", u"note": u"a commentary track"},
        {u"video_hash": u"v1-b", u"video_path": u"D:\\Gone\\Frieren S1 - 12.mkv",
         u"added_at": u"2026-08-02T03:00:00+00:00", u"note": u""}]},
        exists=lambda p: u"Gone" not in p)
    settings.render()
    area = settings.panes[gui_app.TAB_SET]
    shoot.settle(application, settings)
    # ⚠ NOT the bottom: at the bottom the card's count and its sweep notice sit
    # above the fold, and the shot shows one struck-out row in an empty box.
    card = [w for w in settings.findChildren(gui_app.QLabel)
            if w.objectName() == u"cardtitle" and u"NEVER" in w.text()]
    if card:
        area.ensureWidgetVisible(card[0], 0, 40)
        area.verticalScrollBar().setValue(
            card[0].mapTo(area.widget(), card[0].rect().topLeft()).y() - 20)
    take(settings, u"L8-08-settings-blacklist")

    # 9 -- Subtitles: found on a retry, said
    found = dict(fx.added(12, title=u"Tsuihou sareta Tensei Juukishi", season=None,
                          name=u"\u8ffd\u653e\u3055\u308c\u305f.S01E12.WEBRip.Netflix.ja[cc].srt"),
                 tried_before=remembered_tsuihou()[u"tried_before"])
    subs = window_over(run_rows[:2] + [found], [], watching=True)
    take(subs, u"L8-09-subtitles-found-on-retry")

    # 10 -- clamped to the smallest size the design was ruled at
    clamped = window_over(run_rows, memory, watching=True)
    clamped.show_tab(gui_app.TAB_PICK)
    take(clamped, u"L8-10-clamped-needs-you", 1024, 620)

    # 11 -- Settings: hato's memory (8g), counted by `hato state --clear --json`
    # over a COPY of Sonic's real store, 2026-09-22 -- his numbers, not a mock's
    counted = {u"type": u"clear", u"ok": True, u"dry_run": True,
               u"cleared": {u"videos": 60, u"attempts": 148, u"present": 0,
                            u"shows": 14, u"waiting": 0}}
    forget = window_over(run_rows, memory, watching=True)
    forget._memory_read(None, [counted])
    forget.show_tab(gui_app.TAB_SET)
    area = forget.panes[gui_app.TAB_SET]
    # ⚠ LAID OUT BEFORE IT IS SCROLLED. The first take of this shot scrolled a
    # window never shown -- every position was 0 -- and photographed the top
    # of Settings, byte-for-byte the size of L8-07. Shot 8 only worked because
    # shot 7 had shown that window first.
    forget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    forget.show()
    forget.resize(gui_app.WIN_W, gui_app.WIN_H)
    shoot.settle(application, forget)
    card = [w for w in forget.findChildren(gui_app.QLabel)
            if w.objectName() == u"cardtitle" and u"MEMORY" in w.text()]
    if card:
        area.verticalScrollBar().setValue(
            card[0].mapTo(area.widget(), card[0].rect().topLeft()).y() - 200)
    take(forget, u"L8-11-settings-memory")

    # 14/15 -- 8f: *probably not out yet*, on Sonic's two real open problems
    # (`hato problems` over a copy of his store, 2026-09-22) -- Iruma-kun S4 23
    # with the three files the slid fit offered it, newest on offer E22; beside
    # it Slime S4 23, where nothing is known about the newest and it stays a pick.
    def tried(name, rate, size, why):
        return {u"name": name, u"outcome": u"REFUSED", u"reason": why, u"bytes": size,
                u"match_rate": rate, u"path": u"C:\\hato\\cache\\%d.ja.ass" % size,
                u"when": u"2026-09-20T01:42:03+00:00"}

    def problem(name, title, tries, newest, hours):
        return {u"type": u"video", u"source": u"memory",
                u"video": u"D:\\Anime\\" + name, u"name": name,
                u"title": title, u"season": 4, u"episode": 23, u"outcome": u"REFUSED",
                u"skip": None, u"reason": u"3 candidate(s) tried, all refused by timing",
                u"jimaku_entry": 11791, u"attempts": [], u"tried_before": tries,
                u"retry_after": (NOW + timedelta(hours=hours)).isoformat(),
                u"newest_offered": newest, u"candidates_offered": None,
                u"output_path": None}

    iruma = problem(
        u"[SubsPlease] Mairimashita! Iruma-kun S4 - 23 (1080p) [1C17B4D8].mkv",
        u"Mairimashita! Iruma kun",
        [tried(u"[NanakoRaws] Mairimashita! Iruma-kun S04E22 (NHK-E TV 1080p HEVC AAC).ass",
               0.28, 82536, u"28% of reference lines matched"),
         tried(u"魔入りました！入間くん.S04E20.第20話.チームデビムス.WEBRip.Amazon.ja-jp[sdh].srt",
               0.32, 41320, u"32% of reference lines matched"),
         tried(u"魔入りました！入間くん.S04E03.第3話.アクドルの真髄.WEBRip.Amazon.ja-jp[sdh].srt",
               0.36, 48154, u"36% matched overall, but 18:00-20:00 wants +14.7 s")],
        22, 13.4)
    slime = problem(
        u"[SubsPlease] Tensei Shitara Slime Datta Ken S4 - 23 (1080p) [6F4604E2].mkv",
        u"Tensei Shitara Slime Datta Ken",
        [tried(u"[shincaps] Tensei Shitara Slime Datta Ken - 94 (AT-X 1440x1080 MPEG2 AAC).ass",
               0.25, 71635, u"25% of reference lines matched"),
         tried(u"[shincaps] Tensei Shitara Slime Datta Ken - 75 (AT-X 1440x1080 MPEG2 AAC).ass",
               0.24, 64105, u"24% of reference lines matched"),
         tried(u"[NanakoRaws] Tensei Shitara Slime Datta Ken S4 - 03 (AT-X 1080p HEVC AAC).ass",
               0.24, 63499, u"24% of reference lines matched")],
        None, 9.1)
    late = window_over([], [iruma, slime], watching=True)
    late.show_tab(gui_app.TAB_PICK)
    take(late, u"L8-14-probably-not-out-yet")
    open_row(late, late.state.key(iruma))
    take(late, u"L8-15-probably-not-out-yet-open")

    # 16 -- after *Wait for it*: the row put away until its search, one click back
    late.wait_for(iruma)
    take(late, u"L8-16-waiting-by-choice")

    # 17-20 -- ⭐ D2: the daily run's switch says what Task Scheduler HOLDS. Its
    # state comes from `read_schedule` in the window; here it is set outright, the
    # four ways Task Scheduler can answer (`tests/test_schedule.py` holds the
    # reading itself to real schtasks output).
    for name, over in (
            (u"L8-17-daily-run-on", dict(auto=True)),
            (u"L8-18-daily-run-off", dict(auto=False)),
            (u"L8-19-daily-run-off-in-task-scheduler", dict(
                auto=False, auto_note=u"It is switched off in Task Scheduler — "
                                      u"switching it on here turns it back on.")),
            (u"L8-20-daily-run-refused", dict(
                auto=False, schedule_said=u"Task Scheduler would not add hato's daily "
                                          u"run (Access is denied)."))):
        daily = window_over(run_rows, memory, watching=False)
        for field, value in over.items():
            setattr(daily.state, field, value)
        daily.show_tab(gui_app.TAB_SET)
        take(daily, name)

    # 21 -- Needs you with NO tray but the daily run ON: every wait says when the
    # daily run keeps it, where L8-02 (neither) can only say when it becomes due
    kept = window_over(run_rows, memory, watching=False)
    kept.state.auto = True
    kept.show_tab(gui_app.TAB_PICK)
    take(kept, u"L8-21-needs-you-daily-run-keeps-it")

    # 12 -- the confirm over his real store: no blacklist, so no switch
    for blacklisted, name in ((0, u"L8-12-clear-confirm"),
                              (2, u"L8-13-clear-confirm-with-blacklist")):
        dialog = gui_app.ClearDialog(None, counted, blacklisted=blacklisted)
        # ⚠ THE SIZE `exec()` GIVES IT, not a hint read before layout: the first
        # take used `sizeHint()`, whose wrapped labels were measured narrower
        # than they render, and the spare height sat between the paragraphs.
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dialog.show()
        dialog.adjustSize()
        shoot.settle(application, dialog)
        take(dialog, name, dialog.width(), dialog.height())

    if failures:
        sys.stderr.write(u"FAILED to save: %s\n" % u", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        tempfile.gettempdir(), u"hato-layer8-shots")
    sys.exit(main(target))
