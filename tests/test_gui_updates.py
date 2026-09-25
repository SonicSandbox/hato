# -*- coding: utf-8 -*-
u"""
The window's half of auto-update -- RUNBOOK 11f. Ruled 2026-09-24 (*"I take all your
leans"*): gui-mock/mock-update.html, mechanism A -- the pill, the card, its progress,
the banner after a restart, and Settings -> Updates as the last card.

Two halves, as the rest of the window is tested:

  * `gui/updating.py` -- ⛔ no Qt -- decides every word, asserted with no display;
  * the WINDOW, driven by REAL CLICKS through Qt's event path (D12's lesson: a check
    named for a control that calls the function under it saw nothing for two
    releases). The spawn seam records argv, `quit_app` records instead of quitting,
    and `update.hand_off` / the tray's stop are replaced -- ⛔ nothing here starts a
    swapper, stops a real tray, or quits the suite.

⚠ WHAT THIS FILE CANNOT SEE: how it LOOKS (the shots in `%TEMP%\\hato-11\\shots`,
LOOKED against the mock, 2026-09-24), and a real swap -- the swapper's own suite and
the smoke's rehearsal (11h).
"""
import ast
import os
import time

import pytest

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from hato import update
from hato.gui import app as gui_app
from hato.gui import updating

import test_gui_widgets as fx                        # tests/ is on sys.path

qapp = fx.qapp                                       # the one QApplication fixture
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = u"https://github.com/SonicSandbox/hato/releases/tag/v1.0.5"
NOTES = [u"Needs you shows the time each episode will be looked at again.",
         u"The tray starts faster after Windows signs in."]


def ready(**over):
    answer = {u"type": u"update", u"kind": u"ready", u"version": u"1.0.5",
              u"reason": None, u"notes": list(NOTES), u"critical": False, u"page": PAGE,
              u"zip_url": u"u", u"size": 67400000}
    answer.update(over)
    return answer


def updates(**over):
    u = updating.Updates(current=u"1.0.4", frozen=True)
    u.now = 1000000.0
    for name, value in over.items():
        setattr(u, name, value)
    return u


# ===========================================================================
# the view -- no Qt
# ===========================================================================

def test_nothing_is_offered_that_is_not_newer_than_this_copy():
    u"""🚨 LOOKED 2026-09-24: a saved answer read after an update offered the version
    now running -- *"hato 1.0.5 is out"* beside *"Updated to 1.0.5"*."""
    assert updating.offered(updates(decision=ready())) == u"1.0.5", u"the control"
    for current in (u"1.0.5", u"1.0.6", u""):
        assert updating.offered(updates(decision=ready(), current=current)) is None, current
    assert updating.offered(updates(decision=ready(kind=u"none"))) is None


@pytest.mark.parametrize("fields, want", [
    (dict(decision=ready(), staged=u"1.0.5"), (u"hato 1.0.5 is ready", u"Restart",
                                              updating.TO_CARD)),
    (dict(decision=ready(), staged=u"1.0.5", when_closed=True),
     (u"hato 1.0.5 installs when you close hato", u"Restart now", updating.TO_CARD)),
    (dict(decision=ready(), staged=u"1.0.5", after_run=True),
     (u"hato 1.0.5 installs after this run", u"Details", updating.TO_CARD)),
    (dict(decision=ready(), auto=False), (u"hato 1.0.5 is out", u"Install", updating.TO_CARD)),
    (dict(decision=ready(), downloading=(1, 9)), None),
    (dict(decision=ready(kind=u"tell", reason=u"unsigned")),
     (u"hato 1.0.5 is out", u"Download", updating.TO_CARD)),
    (dict(decision=ready(kind=u"tell", reason=u"source"), frozen=False),
     (u"hato 1.0.5 is out", u"How to update", updating.TO_SETTINGS)),
    (dict(decision=None), None)],
    ids=["staged", "when-closed", "after-run", "manual", "quiet-download", "tell",
         "source", "nothing"])
def test_the_pill_says_what_the_state_is(fields, want):
    assert updating.pill(updates(**fields)) == want


def test_hato_downloads_by_itself_only_when_it_may():
    assert updating.downloads_by_itself(updates(decision=ready())), u"the control"
    for why, fields in ((u"off", dict(auto=False)), (u"turned away", dict(skipped=u"1.0.5")),
                        (u"already here", dict(staged=u"1.0.5")),
                        (u"already fetching", dict(downloading=(0, 0))),
                        (u"from source", dict(frozen=False))):
        assert not updating.downloads_by_itself(updates(decision=ready(), **fields)), why


def test_the_card_asks_the_way_the_state_allows():
    staged = updating.card(updates(decision=ready(), staged=u"1.0.5"))
    assert staged[u"title"] == (u"hato ", u"1.0.5", u" is ready")
    assert staged[u"sub"] == u"You have 1.0.4 · downloaded and checked · 67 MB"
    assert [b[:2] for b in staged[u"buttons"]] == [(u"When I close hato", updating.LATER),
                                                   (u"Restart now", updating.RESTART)]
    fetch = updating.card(updates(decision=ready()))
    assert fetch[u"buttons"][-1][:2] == (u"Download and restart", updating.RESTART)
    busy = updating.card(updates(decision=ready(), staged=u"1.0.5"), running=True)
    assert busy[u"buttons"][-1][0] == u"Restart after this run"
    assert updating.card(updates(decision=ready()))[u"critical"] == u""
    assert updating.card(updates(decision=ready(critical=True)))[u"critical"]


def test_a_page_that_is_not_hatos_own_release_is_never_linked():
    u"""The page comes from GitHub's answer, which the signature does not cover."""
    assert updating.page(updates(decision=ready())) == PAGE, u"the control"
    for hostile in (u"https://evil.example/x", u"javascript:alert(1)",
                    PAGE + u"\" onclick=\"x", u"https://github.com/SonicSandbox/hatoX/r", None):
        assert updating.page(updates(decision=ready(page=hostile))) == update.RELEASES_PAGE, \
            hostile


def test_the_progress_is_four_steps_and_one_bar():
    download = updating.progress(updates(decision=ready(), step=u"download",
                                         downloading=(50, 100)))
    assert download[u"steps"][0] == (u"Downloading 50%", u"now")
    assert [s for _n, s in download[u"steps"][1:]] == [u"todo"] * 3
    assert download[u"bar"] == pytest.approx(0.125)
    install = updating.progress(updates(decision=ready(), staged=u"1.0.5", step=u"install"))
    assert [s for _n, s in install[u"steps"]] == [u"done", u"done", u"now", u"todo"]
    assert 0.4 < install[u"bar"] < 0.8
    assert u"puts 1.0.4 back" in install[u"footer"]


@pytest.mark.parametrize("result, kind, words", [
    (dict(status=u"success", touched=True), u"ok", u"Updated to 1.0.5"),
    (dict(status=u"success", touched=True, going_back=True), u"ok", u"Back on 1.0.5"),
    (dict(status=u"failed", touched=True), u"warn", u"didn't finish"),
    (dict(status=u"failed", touched=False), u"warn", u"didn't start")],
    ids=["updated", "went-back", "put-back", "not-started"])
def test_the_banner_says_what_the_last_swap_came_to(result, kind, words):
    result = dict(result, **{u"from": u"1.0.4", u"to": u"1.0.5",
                             u"at": time.strftime(u"%Y-%m-%dT%H:%M:%S")})
    note = updating.banner(updates(result=result, decision=ready()))
    assert note[u"kind"] == kind and words in note[u"lead"], note
    if kind == u"warn":
        # ⚠ C3b (ADVERSARY 2026-09-24): only a swap that TOUCHED the folder turns its
        # release away -- one that never started must not say it will not try again
        promise = u"won't try 1.0.5 again on its own" in note[u"detail"]
        assert promise == bool(result[u"touched"]), note[u"detail"]
        assert [a for _t, a, _x in note[u"actions"]] == [updating.PAGE, updating.AGAIN]


def test_from_source_there_is_no_switch_and_no_go_back_only_git_pull():
    said = updating.settings(updates(decision=ready(kind=u"tell", reason=u"source"),
                                     frozen=False, kept=u"1.0.3", folder=u"/home/you/hato"))
    assert said[u"auto"] is None and said[u"kept"] is None
    assert said[u"git"] == (u"git pull", u" in /home/you/hato, then start hato again")
    assert said[u"copy"][1] == updating.COPY
    frozen = updating.settings(updates(decision=ready(), kept=u"1.0.3"))
    assert frozen[u"auto"] and frozen[u"kept"][1] == (u"Go back to 1.0.3", updating.ASK_BACK)


def test_a_sentence_from_the_command_reads_in_the_windows_voice():
    assert updating.prose(u"the download stopped -- try again") == \
        u"The download stopped — try again"
    assert updating.prose(None) == u""


def test_the_view_imports_no_toolkit():
    u"""⛔ The split `gui/run.py` makes: every word asserted without a display."""
    with open(os.path.join(fx.GUI_DIR, u"updating.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or u"")
    assert u"hato" in names, u"the control: the walk found hato's own imports"
    assert not [n for n in names if n.startswith(u"PyQt")], names


def test_every_action_the_view_can_hand_over_has_a_handler(qapp, monkeypatch):
    u"""⭐ ONE dispatcher: a button whose action lands nowhere renders perfectly and
    does nothing (doctrine/architecture). Each action is driven; none may raise."""
    window = frame(decision=ready(), staged=u"1.0.5", kept=u"1.0.3")
    for name in (u"restart_to_update", u"go_back", u"try_update_again", u"check_updates"):
        monkeypatch.setattr(window, name, lambda *a, **k: u"handled")
    monkeypatch.setattr(gui_app.QDesktopServices, u"openUrl", lambda url: True)
    for action in updating.ACTIONS:
        window.update_action(action)
    with pytest.raises(ValueError):
        window.update_action(u"no-such-action")


# ===========================================================================
# the window -- real clicks
# ===========================================================================

def frame(**fields):
    u"""A window over fixture rows, no run going, its update state set."""
    window = fx.make()
    window.state.running = False
    u = window.state.updates
    u.current, u.frozen, u.now = u"1.0.4", True, time.time()
    for name, value in fields.items():
        setattr(u, name, value)
    window.quit_calls = []
    window.quit_app = lambda: window.quit_calls.append(u"quit")
    window.render()
    return window


def press(button):
    u"""A real left click on a QPushButton, through Qt's own event path."""
    button.click()                    # QAbstractButton's own press/release/clicked path


def card_buttons(window):
    u"""The open card's buttons, by text. ⚠ `isVisibleTo(window)`: the suite never
    shows a window, so plain `isVisible()` is False for every child of it."""
    card = window.update_veil.card
    assert card is not None and window.update_veil.isVisibleTo(window) \
        and card.isVisibleTo(window), u"no card is on screen"
    return dict((b.text(), b) for b in card.findChildren(QPushButton))


def texts_in(widget):
    return u" ".join(w.text() for w in widget.findChildren(QLabel))


@pytest.fixture
def handed(monkeypatch, tmp_path):
    u"""`update.hand_off` and the tray, recorded -> the calls list."""
    from hato import runlock, watch
    calls = []
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setattr(watch, "stop_running_watcher", lambda: calls.append(u"stop") or 4242)
    monkeypatch.setattr(update, "hand_off",
                        lambda pending, **kw: calls.append((u"hand_off", pending, kw)) or u"p")
    monkeypatch.setattr(runlock, "run_in_flight", lambda path=None: False)
    return calls


def test_clicking_the_pill_opens_the_card(qapp):
    window = frame(decision=ready(), staged=u"1.0.5")
    assert window.update_pill.isVisibleTo(window) and \
        window.update_pill.text.text() == u"hato 1.0.5 is ready"
    fx.click(window.update_pill)
    buttons = card_buttons(window)
    assert u"Restart now" in buttons and u"hato" in texts_in(window.update_veil.card)
    assert u"1.0.5" in texts_in(window.update_veil.card)


def test_restart_now_stops_the_tray_hands_off_and_closes(qapp, handed):
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    press(card_buttons(window)[u"Restart now"])
    kinds = [c if isinstance(c, str) else c[0] for c in handed]
    assert kinds == [u"stop", u"hand_off"], handed
    kw = handed[1][2]
    assert (kw[u"window"], kw[u"tray"], kw[u"quiet"]) == (True, True, False), kw
    assert kw.get(u"current") and kw.get(u"install"), \
        u"the hand-off was never told which copy hands off (11z A3/A6): %s" % kw
    assert window.quit_calls == [u"quit"], u"the window stayed open over the swap"


def test_restart_now_during_a_run_waits_for_its_end(qapp, handed):
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    window.state.running = True
    window.render()
    press(card_buttons(window)[u"Restart after this run"])
    assert handed == [] and window.state.updates.after_run
    assert window.update_pill.text.text() == u"hato 1.0.5 installs after this run"
    window.state.running = False
    window.update_after_run()
    assert [c[0] for c in handed if not isinstance(c, str)] == [u"hand_off"]


def test_when_i_close_hato_installs_quietly_as_the_window_closes(qapp, handed):
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    press(card_buttons(window)[u"When I close hato"])
    assert handed == [] and window.update_veil.card is None
    window.close()
    kw = [c for c in handed if not isinstance(c, str)][0][2]
    assert (kw[u"window"], kw[u"quiet"]) == (False, True), kw


def test_a_failed_hand_off_brings_the_tray_back_and_says_why(qapp, handed, monkeypatch):
    def refuse(pending, **kw):
        raise update.StageError(u"the new version carries no updater")
    monkeypatch.setattr(update, "hand_off", refuse)
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    started = []
    monkeypatch.setattr(window, "start_watcher", lambda: started.append(u"tray"))
    press(card_buttons(window)[u"Restart now"])
    assert started == [u"tray"], u"the stopped tray was not started again"
    assert window.quit_calls == [] and window.state.updates.card == u"ready"
    assert u"The new version carries no updater" in texts_in(window.update_veil.card)


def _pump(until, timeout):
    u"""Qt's own timers, run for real until `until()` or `timeout` s -> until()."""
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return until()


def _really_quits(window, monkeypatch):
    u"""The REAL `quit_app` (the frame records instead), its close recorded."""
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(time.monotonic()) or True)
    window.quit_app = window._quit_app
    return closed


def test_restart_now_keeps_the_window_until_the_splash_covers_it(qapp, handed, monkeypatch):
    u"""⭐ The swapper is a ONEFILE exe: it unpacks itself before it can draw. Closed at
    once, the window left NOTHING on screen for a second or two -- the moment a person
    wonders whether hato just crashed. It stays, saying *Installing*, until the splash
    is up over it."""
    from hato import splash
    up = []
    monkeypatch.setattr(splash, "on_screen", lambda of=None: bool(up))
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    closed = _really_quits(window, monkeypatch)
    press(card_buttons(window)[u"Restart now"])
    assert not _pump(lambda: closed, 0.8), u"the window went before any splash was up"
    assert window.state.updates.card == u"progress" and window.state.updates.step == u"install"
    up.append(True)
    assert _pump(lambda: closed, 2.0), u"the splash is up and the window stayed under it"


def test_with_no_splash_the_window_still_goes_after_its_wait(qapp, handed, monkeypatch):
    u"""⚠ A cap, not a wait: a swapper that cannot draw still swaps -- and it waits for
    this window to close before it moves a byte."""
    from hato import splash
    monkeypatch.setattr(splash, "on_screen", lambda of=None: False)
    monkeypatch.setattr(gui_app.HatoWindow, "SPLASH_WAIT", 0.6)
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    closed = _really_quits(window, monkeypatch)
    started = time.monotonic()
    press(card_buttons(window)[u"Restart now"])
    assert _pump(lambda: closed, 3.0), u"no splash, and the window never went"
    assert closed[0] - started >= 0.6, u"it went before its wait was over"


class _Gone(object):
    u"""A swapper that has already exited."""
    pid = 4321

    def poll(self):
        return 1


def test_a_swapper_that_closed_at_once_leaves_hato_open_and_says_so(qapp, handed,
                                                                    monkeypatch):
    u"""⛔ Nothing else would ever bring hato back -- a quarantined updater, a broken
    hand-off -- so the window stays, its tray comes back, and the card says why,
    with *Restart now* one click away."""
    from hato import splash
    monkeypatch.setattr(splash, "on_screen", lambda of=None: False)
    monkeypatch.setattr(update, "hand_off", lambda pending, **kw: _Gone())
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    closed = _really_quits(window, monkeypatch)
    started = []
    monkeypatch.setattr(window, "start_watcher", lambda: started.append(u"tray"))
    press(card_buttons(window)[u"Restart now"])
    assert _pump(lambda: window.state.updates.card == u"ready", 2.0), \
        u"the card never came back"
    assert not _pump(lambda: closed, 0.4), u"hato closed over an updater that was gone"
    assert started == [u"tray"], u"the tray this window stopped was never started again"
    assert u"could not start" in texts_in(window.update_veil.card)
    assert u"Restart now" in card_buttons(window)


def test_download_and_restart_fetches_first_then_hands_off(qapp, handed):
    window = frame(decision=ready(), auto=False, card=u"ready")
    sent = []
    window.spawn = lambda argv, **kw: sent.append(argv) or None
    press(card_buttons(window)[u"Download and restart"])
    assert sent and sent[-1][-4:] == [u"update", u"--stage", u"--progress", u"--json"], sent
    assert window.state.updates.card == u"progress"
    window._update_progress({u"type": u"progress", u"done": 30, u"total": 100})
    assert u"Downloading 30%" in texts_in(window.update_veil.card)
    window._update_staged(None, [{u"type": u"staged", u"version": u"1.0.5"}])
    assert [c[0] for c in handed if not isinstance(c, str)] == [u"hand_off"]


def test_a_failed_download_is_said_on_the_card_that_asked(qapp):
    window = frame(decision=ready(), auto=False, card=u"progress", step=u"download",
                   downloading=(1, 100))
    window._stage_then_restart = True
    window._update_staged(None, [{u"type": u"error",
                                  u"reason": u"the download stopped -- it was cut"}])
    assert window.state.updates.card == u"ready"
    assert u"The download stopped — it was cut" in texts_in(window.update_veil.card)


def test_the_progress_card_is_painted_in_place_not_rebuilt(qapp):
    window = frame(decision=ready(), card=u"progress", step=u"download", downloading=(0, 100))
    first = window.update_veil.card
    window._update_progress({u"type": u"progress", u"done": 40, u"total": 100})
    assert window.update_veil.card is first, u"the card was rebuilt for a progress line"
    assert window._ucard_bar.fraction == pytest.approx(0.1)


def test_an_automatic_answer_downloads_quietly_and_a_manual_one_does_not(qapp):
    for auto, want in ((True, True), (False, False)):
        window = frame(auto=auto)
        sent = []
        window.spawn = lambda argv, **kw: sent.append(argv) or None
        window._update_checked(None, [ready()])
        staged = any(u"--stage" in argv for argv in sent)
        assert staged == want, (auto, sent)
        assert window.state.updates.card is None, u"a download opened a card by itself"


def test_a_critical_release_opens_its_card_once(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    window = frame(decision=ready(critical=True), staged=u"1.0.5")
    assert window._maybe_open_critical() and window.state.updates.card == u"ready"
    window.state.updates.card = None
    assert not window._maybe_open_critical(), u"it opened a second time"


def test_the_updated_banner_is_shown_and_dismissed_by_its_cross(qapp):
    window = frame(decision=ready(), current=u"1.0.5",
                   result={u"from": u"1.0.4", u"to": u"1.0.5", u"status": u"success",
                           u"at": time.strftime(u"%Y-%m-%dT%H:%M:%S"), u"touched": True})
    pane = window.panes[gui_app.TAB_SUBS].widget()
    assert u"Updated to 1.0.5" in texts_in(pane)
    assert not window.update_pill.isVisibleTo(window), u"it offered the version running"
    cross = [b for b in pane.findChildren(QPushButton) if b.text() == u"✕"
             and b.toolTip() == u"Dismiss"]
    press(cross[0])
    assert u"Updated to 1.0.5" not in texts_in(window.panes[gui_app.TAB_SUBS].widget())


def test_the_put_back_banners_buttons_reach_the_page_and_try_again(qapp, monkeypatch,
                                                                   tmp_path):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    update.skip(u"1.0.5")
    opened = []
    monkeypatch.setattr(gui_app.QDesktopServices, u"openUrl",
                        lambda url: opened.append(url.toString()) or True)
    window = frame(decision=ready(page=u"https://evil.example/x"), skipped=u"1.0.5",
                   result={u"from": u"1.0.4", u"to": u"1.0.5", u"status": u"failed",
                           u"touched": True, u"at": u"2026-09-24T10:00:00"})
    tried = []
    monkeypatch.setattr(window, "restart_to_update", lambda: tried.append(u"again"))
    pane = window.panes[gui_app.TAB_SUBS].widget()
    buttons = dict((b.text(), b) for b in pane.findChildren(QPushButton))
    press(buttons[u"Download it myself"])
    assert opened == [update.RELEASES_PAGE], u"a page not hato's own was opened: %s" % opened
    press(buttons[u"Try again"])
    assert tried == [u"again"] and update.skipped() is None, u"the version stayed turned away"


def settings_card(window):
    window.show_tab(gui_app.TAB_SET)
    cards = [w for w in window.findChildren(gui_app.Styled) if w.objectName() == u"card"]
    for card in cards:
        titles = [l.text() for l in card.findChildren(QLabel) if l.objectName() == u"cardtitle"]
        if titles == [u"UPDATES"]:
            return card
    raise AssertionError(u"no Updates card")


def test_check_now_asks_github_now_not_once_a_day(qapp):
    window = frame(decision={u"type": u"update", u"kind": u"none", u"version": u"1.0.4"})
    sent = []
    window.spawn = lambda argv, **kw: sent.append(argv) or None
    card = settings_card(window)
    press(dict((b.text(), b) for b in card.findChildren(QPushButton))[u"Check now"])
    assert sent and sent[-1][-3:] == [u"update", u"--check", u"--json"], sent


def test_the_automatic_switch_writes_through_the_one_writer(qapp):
    window = frame(decision={u"type": u"update", u"kind": u"none", u"version": u"1.0.4"})
    sent = []
    window.spawn = lambda argv, **kw: sent.append(argv) or None
    settings_card(window)
    press(window.update_switch)
    assert window.state.updates.auto is False
    assert [u"config", u"--set", u"auto_update=false", u"--json"] == sent[-1][-4:], sent
    assert window.state.update_key_in_file is True, \
        u"switched off, the key is in the file -- and an older tray refuses it"


@pytest.mark.parametrize("caps, want", [(None, True),
                                        (frozenset([u"retries", u"formats"]), False),
                                        (frozenset([u"retries", u"formats", u"updates"]), True)],
                         ids=["no-tray", "a-1.0.3-tray", "this-tray"])
def test_a_tray_says_whether_it_reads_the_update_setting(qapp, monkeypatch, caps, want):
    from hato import watch
    monkeypatch.setattr(watch, "watching_capabilities", lambda: caps)
    assert gui_app.HatoWindow.tray_reads_updates() is want


def test_go_back_asks_first_then_hands_off_with_the_current_swapper(qapp, handed,
                                                                    monkeypatch, tmp_path):
    from hato.commands import update as command
    monkeypatch.setattr(command, "install_dir", lambda: str(tmp_path / "install"))
    monkeypatch.setattr(update, "go_back_pending",
                        lambda install, current, root=None: str(tmp_path / "pending.json"))
    window = frame(decision={u"type": u"update", u"kind": u"none", u"version": u"1.0.4"},
                   kept=u"1.0.3")
    card = settings_card(window)
    press(dict((b.text(), b) for b in card.findChildren(QPushButton))[u"Go back to 1.0.3"])
    assert handed == [] and window.state.updates.card == u"back", u"it went back unasked"
    press(card_buttons(window)[u"Go back"])
    kw = [c for c in handed if not isinstance(c, str)][0][2]
    assert kw[u"swapper"] == os.path.join(str(tmp_path / "install"), update.SWAPPER_NAME)
    assert window.quit_calls == [u"quit"]


def test_from_source_the_card_copies_git_pull_and_has_no_switch(qapp):
    window = frame(decision=ready(kind=u"tell", reason=u"source"), frozen=False)
    window.update_switch = None
    card = settings_card(window)
    assert window.update_switch is None, u"a switch was drawn for a checkout"
    press(dict((b.text(), b) for b in card.findChildren(QPushButton))[u"Copy"])
    assert QApplication.clipboard().text() == u"git pull"
    fx.click(window.update_pill)
    assert window.state.tab == gui_app.TAB_SET, u"the source pill did not lead to Settings"


def test_remote_notes_are_shown_as_text_never_markup(qapp):
    u"""⛔ A release's notes come from GitHub: never rich text."""
    window = frame(decision=ready(notes=[u"<b>bold</b> <a href='x'>link</a>"]),
                   staged=u"1.0.5", card=u"ready")
    labels = [l for l in window.update_veil.card.findChildren(QLabel)
              if u"<b>bold</b>" in l.text()]
    assert labels and labels[0].textFormat() == Qt.TextFormat.PlainText, labels


@pytest.mark.parametrize("reads, in_file, want", [
    (False, True, True), (True, True, False), (False, False, False)],
    ids=["old-tray-and-key", "current-tray", "key-not-written"])
def test_an_older_tray_that_would_refuse_the_setting_is_said_with_its_fix(qapp, reads,
                                                                         in_file, want):
    u"""A 1.0.3 tray REFUSES `auto_update` -- written only once switched off -- and
    every run it starts stops at the file. The format card's trap, said the same way."""
    window = frame(decision={u"type": u"update", u"kind": u"none", u"version": u"1.0.4"},
                   auto=not in_file)
    window.state.tray_reads_updates, window.state.update_key_in_file = reads, in_file
    card = settings_card(window)
    restart = [b for b in card.findChildren(QPushButton) if b.text() == u"Restart the tray"]
    assert bool(restart) is want
    if want:
        called = []
        window.restart_watcher = lambda: called.append(u"restart")
        restart = [b for b in settings_card(window).findChildren(QPushButton)
                   if b.text() == u"Restart the tray"]
        press(restart[0])
        assert called == [u"restart"]


def test_the_windows_title_is_the_one_the_swapper_waits_for(qapp):
    u"""⛔ A CONTRACT ACROSS TWO PROGRAMS: the swapper proves an update by a visible
    window with THIS title (a crash dialog is visible too). Retitle the window and
    every update would read as failed, and be put back."""
    from hato import swap
    assert frame().windowTitle() == swap.WINDOW_TITLE


def test_the_result_is_picked_up_when_it_lands_after_the_window_opened(qapp, monkeypatch,
                                                                      tmp_path):
    u"""🚨 THE SWAPPER WRITES ITS RESULT AFTER IT HAS SEEN THIS WINDOW -- so at start
    there is nothing to read, and *"Updated to 1.0.5"* was never going to show. The
    window keeps looking, a `stat` at a time."""
    from hato.commands import update as command
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.setattr(command, "install_dir", lambda: str(install))
    window = frame(current=u"1.0.5")
    window.read_updates(frozen=True)
    assert window.state.updates.result is None, u"the control: nothing yet"
    root = update.stage_root(str(install))
    os.makedirs(str(root))
    update.save_json(os.path.join(str(root), update.RESULT_NAME),
                     {u"from": u"1.0.4", u"to": u"1.0.5", u"status": u"success",
                      u"touched": True, u"at": time.strftime(u"%Y-%m-%dT%H:%M:%S")})
    # ⭐ Through the window's own timer -- the one that follows other runs --
    # not the method under it (D12's lesson).
    window.follow_other_runs(every_ms=60000)
    window._others_timer.timeout.emit()
    window._others_timer.stop()
    assert window.state.updates.result and u"Updated to 1.0.5" in texts_in(
        window.panes[gui_app.TAB_SUBS].widget())


def test_the_switch_reads_the_setting_from_the_disk(qapp, monkeypatch, tmp_path):
    u"""The switch says what `config.toml` says -- ⛔ never a default painted over it."""
    path = tmp_path / u"config.toml"
    path.write_text(u"auto_update = false\n", encoding="utf-8")
    monkeypatch.setenv("HATO_CONFIG", str(path))
    state = gui_app.State()
    assert state.updates.auto is True, u"the control: the default is on"
    gui_app.settings_from_disk(state)
    assert state.updates.auto is False


def test_the_window_reads_the_last_swap_once_and_forgets_it(qapp, monkeypatch, tmp_path):
    from hato.commands import update as command
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.setattr(command, "install_dir", lambda: str(install))
    root = update.stage_root(str(install))
    os.makedirs(str(root))
    update.save_json(os.path.join(str(root), update.RESULT_NAME),
                     {u"from": u"1.0.4", u"to": u"1.0.5", u"status": u"failed",
                      u"touched": True, u"at": u"2026-09-24T10:00:00"})
    update.save_state({u"checked_at": 5.0, u"decision": ready(version=u"0.0.1")})
    window = frame()
    window.read_updates(frozen=True)
    u = window.state.updates
    assert u.result and u.result[u"status"] == u"failed"
    assert not os.path.exists(os.path.join(str(root), update.RESULT_NAME)), \
        u"the result was left to be shown again at every start"
    assert u.skipped == u"1.0.5", u"a failed version is not turned away"
    assert updating.offered(u) is None, u"an old saved answer was offered"
    assert updating.settings(u)[u"rest"].startswith(u" · up to date"), \
        u"an answer about an older version was not read as up to date: %r" \
        % updating.settings(u)[u"rest"]

# ===========================================================================
# ADVERSARY 2026-09-24 (LAYER 11z) -- surface C (the window and the tray) and B2
# ===========================================================================

@pytest.mark.parametrize("url", [
    u"https://github.com/SonicSandbox/hato/../../evil-org/hato/releases/tag/v1.0.5",
    u"https://github.com/SonicSandbox/hato/releases/../../../evil-org/x",
    u"https://github.com/SonicSandbox/hato/%2e%2e/%2e%2e/evil-org/x",
    u"https://github.com/SonicSandbox/hato/releases/tag/v1.0.5?next=//evil.example",
    u"https://github.com/SonicSandbox/hato/issues/1"],
    ids=[u"dot-dot", u"dot-dot-under-releases", u"escaped-dots", u"a-query", u"not-a-release"])
def test_a_page_that_climbs_out_of_hatos_releases_is_never_linked(url):
    u"""C8: a prefix check passed `…/hato/../../evil-org/…`, which resolves to someone
    else's page. The page is unsigned; it must be a path under hato's own releases."""
    assert updating.page(updates(decision=ready(page=url))) == update.RELEASES_PAGE, url


def test_when_i_close_hato_replaces_restart_after_this_run(qapp, handed):
    u"""🚨 C1: *Restart after this run*, then *When I close hato* -- the run's end still
    restarted hato, and the first choice could never be taken back."""
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    window.state.running = True
    window.render()
    press(card_buttons(window)[u"Restart after this run"])
    assert window.state.updates.after_run, u"the control: the run's end was asked for"
    fx.click(window.update_pill)
    press(card_buttons(window)[u"When I close hato"])
    window.state.running = False
    window.update_after_run()
    assert [c for c in handed if not isinstance(c, str)] == [], u"hato restarted anyway"
    assert window.update_pill.text.text() == u"hato 1.0.5 installs when you close hato"


@pytest.mark.parametrize("whose", [u"this-window", u"the-tray"])
def test_when_i_close_hato_never_hands_off_under_a_run(qapp, handed, monkeypatch, whose):
    u"""🚨 C2a: closed with a run going, the quiet hand-off stopped the tray, and the
    swapper waited a minute on the run -- then gave up. The tray installs it once idle."""
    from hato import runlock
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    press(card_buttons(window)[u"When I close hato"])
    if whose == u"this-window":
        window.state.running = True
    else:
        monkeypatch.setattr(runlock, "run_in_flight", lambda path=None: True)
    window.close()
    assert [c for c in handed if not isinstance(c, str)] == [], u"handed off under a run"


def test_go_back_waits_for_a_run_as_restart_now_does(qapp, handed, monkeypatch):
    u"""🚨 C2b: *Go back* during a run handed off at once, and this window's close then
    TERMINATED the run."""
    window = frame(current=u"1.0.5", kept=u"1.0.4", card=u"back")
    window.state.running = True
    window.render()
    wrote = []
    monkeypatch.setattr(update, "go_back_pending",
                        lambda *a, **k: wrote.append(u"pending") or u"goback.json")
    press(card_buttons(window)[u"Go back"])
    assert wrote == [] and [c for c in handed if not isinstance(c, str)] == []
    assert u"once this run has finished" in texts_in(window.update_veil.card)


def test_a_failed_go_back_is_said_as_one_and_try_again_goes_back(qapp, monkeypatch):
    u"""🚨 C5: a failed Go back read *"The update to 1.0.4 didn't finish ... hato won't
    try 1.0.4 again"*, and *Try again* staged the FORWARD release."""
    window = frame(current=u"1.0.5", kept=u"1.0.4",
                   result={u"from": u"1.0.5", u"to": u"1.0.4", u"status": u"failed",
                           u"touched": True, u"going_back": True,
                           u"at": u"2026-09-24T10:00:00"})
    forward = []
    monkeypatch.setattr(window, "restart_to_update", lambda: forward.append(u"forward"))
    pane = window.panes[gui_app.TAB_SUBS].widget()
    words = texts_in(pane)
    assert u"Going back to 1.0.4" in words and u"won't try" not in words, words
    buttons = dict((b.text(), b) for b in pane.findChildren(QPushButton))
    press(buttons[u"Try again"])
    assert forward == [] and window.state.updates.card == u"back", \
        u"Try again did not go back again"


def test_a_downloaded_release_stays_on_offer_when_a_check_could_not_tell(qapp, handed):
    u"""C9: one offline check saved *could not tell* and hid a release already
    downloaded and verified -- no pill, no *Restart now*. ⚠ PRESSED, not only shown:
    M11z-C9c survived the gate while this check stopped at the button's NAME -- the
    button was there and pressing it did nothing (D12's lesson, again; G2)."""
    window = frame(decision={u"type": u"update", u"kind": u"none", u"version": None},
                   staged=u"1.0.5")
    assert window.update_pill.isVisibleTo(window) and \
        u"1.0.5" in window.update_pill.text.text(), window.update_pill.text.text()
    fx.click(window.update_pill)
    press(card_buttons(window)[u"Restart now"])
    assert [c[0] for c in handed if not isinstance(c, str)] == [u"hand_off"], \
        u"Restart now did nothing: %s" % handed


def test_restart_now_waits_for_a_run_the_tray_started(qapp, handed, monkeypatch):
    u"""C10: `_run_is_going` asks the RUN LOCK too -- the fixture pinned it False, so a
    mutant deleting that half survived. A tray's run defers *Restart now* like our own."""
    from hato import runlock
    monkeypatch.setattr(runlock, "run_in_flight", lambda path=None: True)
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    press(card_buttons(window)[u"Restart after this run"])
    assert window.state.updates.after_run
    assert [c for c in handed if not isinstance(c, str)] == [], u"handed off under the run"


def test_the_trays_run_ending_restarts_what_was_asked_for(qapp, handed):
    u"""C10: a run the TRAY started tells this window nothing when it ends -- the hook
    on the timer that follows other runs is what keeps *Restart after this run*."""
    window = frame(decision=ready(), staged=u"1.0.5")
    window.state.updates.after_run = True
    window.follow_other_runs(every_ms=60000)
    window._others_timer.timeout.emit()
    window._others_timer.stop()
    assert [c[0] for c in handed if not isinstance(c, str)] == [u"hand_off"], handed


def test_this_windows_run_ending_restarts_what_was_asked_for(qapp, handed):
    u"""C10: and this window's OWN run's end -- through `_drain`, the way a run ends."""
    window = frame(decision=ready(), staged=u"1.0.5")
    window.state.running = True
    window.state.updates.after_run = True
    window._runner = fx._FinishedRunner(0)
    window._drain()
    assert _pump(lambda: [c for c in handed if not isinstance(c, str)], 2.0), \
        u"the run ended and nothing restarted"


@pytest.mark.parametrize("road", [u"a-check", u"a-download"])
def test_a_critical_release_opens_its_card_by_the_roads_that_find_it(qapp, monkeypatch,
                                                                    tmp_path, road):
    u"""C10: the critical card's callers were witnessed by nothing -- the check called
    `_maybe_open_critical()` directly. Through the check's answer, and the download's
    end, as they happen."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    if road == u"a-check":
        window = frame(decision=None, staged=u"1.0.5", auto=False)
        window._update_checked(None, [ready(critical=True)])
    else:
        window = frame(decision=ready(critical=True), auto=False)
        window._update_staged(None, [{u"type": u"staged", u"version": u"1.0.5"}])
    assert window.state.updates.card == u"ready", road


def test_the_window_opens_a_critical_card_as_it_starts():
    u"""C10: `main()`'s own call, read off the source -- as the tray's tick is."""
    with open(gui_app.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    main = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == u"main"]
    assert len(main) == 1, u"the control: one main()"
    calls = set(ast.unparse(n.func) for n in ast.walk(main[0]) if isinstance(n, ast.Call))
    assert u"window._maybe_open_critical" in calls, sorted(calls)


def test_the_window_asks_for_its_own_updaters_splash(qapp, handed, monkeypatch):
    u"""B2: `on_screen()` matched the CLASS in every process -- another process's splash
    let this window close before its own updater had drawn. It asks about the updater
    it started (the onefile child is that updater's)."""
    from hato import splash
    asked = []
    monkeypatch.setattr(splash, "on_screen", lambda of=None: asked.append(of) or True)

    class Updater(object):
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(update, "hand_off", lambda pending, **kw: Updater())
    window = frame(decision=ready(), staged=u"1.0.5", card=u"ready")
    closed = _really_quits(window, monkeypatch)
    press(card_buttons(window)[u"Restart now"])
    assert _pump(lambda: closed, 2.0) and asked and asked[0] == 4321, asked

