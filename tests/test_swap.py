# -*- coding: utf-8 -*-
u"""
The swapper -- RUNBOOK 11d. `hato/swap.py`, frozen as `hato-update.exe`.

Tested as plain Python under a folder named `ツール置き場`, because hato's people
keep things under Japanese names (surasura's doc: every helper test runs under a
non-ASCII path). The operating system is handed in (`_Ops`): which processes run
from a folder, start one, is its window on screen, what a program says its version
is. One block drives the REAL process listing on Windows, with a real program
copied into a Japanese-named folder.

⭐ Every way out starts hato again -- the window closed itself to hand off -- and
every failure after something moved puts every move back.

⚠ WHAT THIS FILE CANNOT SEE: a real window appearing from a real frozen build, or
the real splash (tests/test_splash.py draws that). The smoke's REHEARSAL drives the
swap on the built bytes (RUNBOOK 11h).
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from _fakewin import Clock as _Clock, Ops as _Ops         # tests/ is on sys.path
from hato import swap

HERE = os.path.dirname(os.path.abspath(__file__))
SWAP_SOURCE = os.path.join(os.path.dirname(HERE), "hato", "swap.py")
NAMES = (u"hato.exe", u"hato-cli.exe", u"hato-watch.exe", u"LICENSE")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _layout(tmp_path, window=True, tray=False, bad_hash=False):
    u"""An install of 1.0.4 (with a person's own file in it) and a staged 1.0.5."""
    base = tmp_path / u"ツール置き場"
    install = base / u"hato"
    (install / u"_internal").mkdir(parents=True)
    (install / u"_internal" / u"python310.dll").write_bytes(b"old runtime")
    for name in NAMES:
        (install / name).write_bytes(b"old " + name.encode())
    (install / u"my notes.txt").write_bytes(b"theirs")
    stage = base / u"stage"
    staged = stage / u"staged" / u"1.0.5" / u"hato"
    (staged / u"_internal").mkdir(parents=True)
    (staged / u"_internal" / u"python310.dll").write_bytes(b"new runtime")
    entries = {u"_internal": u""}
    for name in NAMES + (u"hato-update.exe",):
        data = b"new " + name.encode()
        (staged / name).write_bytes(data)
        entries[name] = _sha(data)
    if bad_hash:
        entries[u"hato.exe"] = u"0" * 64
    pending = {u"format": 1, u"from": u"1.0.4", u"to": u"1.0.5",
               u"install": str(install), u"staged": str(staged),
               u"previous": str(stage / u"previous" / u"1.0.4"),
               u"entries": entries,
               u"old_entries": sorted([u"_internal"] + list(NAMES)),
               u"result": str(stage / u"result.json"), u"window": window, u"tray": tray}
    path = stage / u"pending.json"
    _write(path, pending)
    return install, stage, pending, path


def _write(path, pending):
    path.write_text(json.dumps(pending), encoding="utf-8")


def _old(install):
    return (install / u"hato.exe").read_bytes() == b"old hato.exe" and \
        (install / u"_internal" / u"python310.dll").read_bytes() == b"old runtime"


def _run(path, ops):
    clock = _Clock()
    return swap.run(str(path), quiet=True, ops=ops, clock=clock, sleep=clock.sleep)


def _result(stage):
    return json.loads((stage / u"result.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------

def test_a_swap_puts_the_new_version_in_place_and_keeps_the_old_one(tmp_path):
    install, stage, _pending, path = _layout(tmp_path)
    ops = _Ops()
    assert _run(path, ops) == 0, _result(stage)
    assert (install / u"hato.exe").read_bytes() == b"new hato.exe"
    assert (install / u"hato-update.exe").read_bytes() == b"new hato-update.exe"
    assert (install / u"_internal" / u"python310.dll").read_bytes() == b"new runtime"
    kept = stage / u"previous" / u"1.0.4"
    assert (kept / u"hato.exe").read_bytes() == b"old hato.exe", u"the previous version was not kept"
    assert (kept / u"_internal" / u"python310.dll").read_bytes() == b"old runtime"
    assert _result(stage)[u"status"] == swap.SUCCESS
    assert ops.started == [u"hato.exe"], ops.started
    assert not path.exists(), u"the hand-off was left behind"
    assert not (stage / u"staged" / u"1.0.5").exists(), u"the staged leftovers were kept"


def test_a_persons_own_file_in_the_folder_is_never_moved(tmp_path):
    install, _stage, _pending, path = _layout(tmp_path)
    _run(path, _Ops())
    assert (install / u"my notes.txt").read_bytes() == b"theirs"


def test_the_new_command_line_is_asked_its_version_before_anything_starts(tmp_path):
    u"""Step 4's second half: the renamed-in program RUNS and says it is `to`."""
    _install, _stage, _pending, path = _layout(tmp_path)
    ops = _Ops()
    _run(path, ops)
    assert ops.asked == [u"hato-cli.exe"], ops.asked


def test_only_the_version_before_is_kept(tmp_path):
    u"""ONE previous version (ruled 2026-09-24): the one before it goes."""
    _install, stage, _pending, path = _layout(tmp_path)
    older = stage / u"previous" / u"1.0.3"
    older.mkdir(parents=True)
    (older / u"hato.exe").write_bytes(b"1.0.3")
    _run(path, _Ops())
    assert sorted(os.listdir(str(stage / u"previous"))) == [u"1.0.4"]


def test_going_back_never_deletes_the_version_it_is_going_back_to(tmp_path):
    u"""*Go back*: the folder swapped IN lives among the kept versions."""
    stage = tmp_path / u"stage"
    back = stage / u"previous" / u"1.0.3"
    back.mkdir(parents=True)
    other = stage / u"previous" / u"1.0.2"
    other.mkdir(parents=True)
    swap._clear_older(str(stage / u"previous" / u"1.0.5"), str(back))
    assert back.is_dir() and not other.exists()


def test_a_finished_go_back_keeps_the_version_it_just_put_aside(tmp_path):
    u"""🚨 The tidy after a swap removed the swapped-in folder's PARENT -- for *Go
    back* that is `previous\\`, holding the version the swap had just kept."""
    install, stage, pending, path = _layout(tmp_path)
    back = stage / u"previous" / u"1.0.3"
    shutil.move(pending[u"staged"], str(back))
    pending.update({u"to": u"1.0.3", u"staged": str(back), u"going_back": True,
                    u"previous": str(stage / u"previous" / u"1.0.4")})
    _write(path, pending)
    assert _run(path, _Ops(says=u"1.0.3")) == 0, _result(stage)
    assert _result(stage)[u"going_back"] is True, u"the window could not tell Go back apart"
    assert (install / u"hato.exe").read_bytes() == b"new hato.exe"
    kept = stage / u"previous" / u"1.0.4" / u"hato.exe"
    assert kept.is_file(), u"going back deleted the version it had just kept"
    assert not back.exists(), u"the emptied folder that was swapped in stayed"


@pytest.mark.parametrize("where", [u"the-root", u"outside"])
def test_the_tidy_never_leaves_its_own_folder(tmp_path, where):
    root = tmp_path / u"stage"
    root.mkdir()
    (root / u"result.json").write_text(u"{}", encoding="utf-8")
    other = tmp_path / u"elsewhere" / u"hato"
    other.mkdir(parents=True)
    swap._tidy(str(root), str(root) if where == u"the-root" else str(other))
    assert (root / u"result.json").is_file() and other.is_dir()


def test_it_waits_for_hato_to_finish_closing_first(tmp_path):
    install, stage, _pending, path = _layout(tmp_path)
    seen = []

    def watch(running):
        seen.append((running, (install / u"hato.exe").read_bytes()))

    ops = _Ops(running_for=12, on_poll=watch)     # three seconds of the window closing
    assert _run(path, ops) == 0, _result(stage)
    moved_early = [data for running, data in seen if running and data != b"old hato.exe"]
    assert len(seen) > 12 and not moved_early, u"files moved while hato was still running"
    assert (install / u"hato.exe").read_bytes() == b"new hato.exe"


def test_the_tray_is_proven_by_its_own_pid_file(tmp_path):
    install, stage, pending, path = _layout(tmp_path, window=False, tray=True)
    marker = stage / u"watch.pid"
    pending[u"tray_pid_file"] = str(marker)
    _write(path, pending)

    def writes_pid(proc):
        marker.write_text(u"%d - retries,formats" % proc.pid, encoding="utf-8")

    ops = _Ops(on_start=writes_pid)
    assert _run(path, ops) == 0, _result(stage)
    assert ops.started == [u"hato-watch.exe"]


# ---------------------------------------------------------------------------
# every way out puts hato back
# ---------------------------------------------------------------------------

def test_hato_still_running_changes_nothing_and_starts_it_again(tmp_path):
    install, stage, _pending, path = _layout(tmp_path)
    ops = _Ops(running_for=10 ** 6)
    assert _run(path, ops) == 1
    assert _old(install)
    got = _result(stage)
    assert (got[u"status"], got[u"touched"]) == (swap.FAILED, False), got
    assert ops.started == [u"hato.exe"], u"the person was left with no hato"


def test_an_incomplete_new_version_changes_nothing_and_starts_hato_again(tmp_path):
    install, stage, pending, path = _layout(tmp_path)
    os.remove(os.path.join(pending[u"staged"], u"hato-cli.exe"))
    ops = _Ops()
    assert _run(path, ops) == 1
    assert _old(install)
    assert _result(stage)[u"touched"] is False
    assert ops.started == [u"hato.exe"], u"the person was left with no hato"


@pytest.mark.parametrize("field", [u"install", u"entries", u"old_entries"])
def test_an_incomplete_hand_off_is_refused_and_touches_nothing(tmp_path, field):
    install, stage, pending, path = _layout(tmp_path)
    pending[field] = None
    _write(path, pending)
    ops = _Ops()
    assert _run(path, ops) == 1
    assert _old(install) and ops.polls == 0
    assert field in _result(stage)[u"reason"]


def test_a_file_that_is_not_the_releases_puts_everything_back(tmp_path):
    install, stage, _pending, path = _layout(tmp_path, bad_hash=True)
    ops = _Ops()
    assert _run(path, ops) == 1
    assert _old(install), u"the old version was not put back"
    assert (install / u"my notes.txt").read_bytes() == b"theirs"
    got = _result(stage)
    assert (got[u"status"], got[u"touched"]) == (swap.FAILED, True), got
    assert u"hato.exe" in got[u"reason"]
    assert ops.started == [u"hato.exe"]


@pytest.mark.parametrize("says", [u"1.0.4", None], ids=[u"the-old-version", u"nothing"])
def test_a_new_version_that_does_not_run_is_put_back_before_anything_starts(tmp_path, says):
    install, stage, _pending, path = _layout(tmp_path)
    ops = _Ops(says=says)
    assert _run(path, ops) == 1
    assert _old(install)
    assert u"did not start" in _result(stage)[u"reason"]
    assert ops.started == [u"hato.exe"] and ops.stopped == [], (ops.started, ops.stopped)


@pytest.mark.parametrize("ops, why", [
    (_Ops(visible=False), u"did not open a window"),
    (_Ops(visible=False, dies_after=0), u"closed as it opened"),
    (_Ops(visible=True, dies_after=3), u"closed as it opened")],
    ids=["never-visible", "closes-at-once", "dies-once-open"])
def test_a_new_version_that_does_not_open_is_put_back(tmp_path, ops, why):
    u"""⛔ LEDGER-HOT: never ask whether a spawn SURVIVED -- ask for what a person
    would see. A new window that never shows is a failed update -- and so is one
    that shows and dies a second later."""
    install, stage, _pending, path = _layout(tmp_path)
    assert _run(path, ops) == 1
    assert _old(install)
    assert why in _result(stage)[u"reason"]
    assert ops.started == [u"hato.exe", u"hato.exe"], u"the old version was not started again"
    assert ops.stopped == [1000], u"the new window it started was not stopped"


@pytest.mark.parametrize("left", [None, u"4242 - retries,formats"], ids=[u"no-file", u"stale-file"])
def test_a_tray_that_never_says_it_is_watching_is_put_back(tmp_path, left):
    u"""A pid file the OLD tray left behind names another process: not a proof."""
    install, stage, pending, path = _layout(tmp_path, window=False, tray=True)
    marker = stage / u"watch.pid"
    if left:
        marker.write_text(left, encoding="utf-8")
    pending[u"tray_pid_file"] = str(marker)
    _write(path, pending)
    assert _run(path, _Ops()) == 1
    assert _old(install)
    assert u"never said it was watching" in _result(stage)[u"reason"]


def test_a_window_that_will_not_start_after_the_tray_did_stops_that_tray(tmp_path):
    u"""The tray started, then the window failed to: the tray holds `_internal`, so
    unless it is stopped the renames back cannot happen."""
    install, stage, _pending, path = _layout(tmp_path, window=True, tray=True)
    ops = _Ops(refuse=(u"hato.exe",))
    assert _run(path, ops) == 1
    assert ops.stopped == [1000], u"the new tray was left running: %s" % ops.stopped
    assert _old(install)
    assert u"could not be started again" in _result(stage)[u"reason"]


@pytest.mark.parametrize("fails_at, touched", [(7, True), (1, False)],
                         ids=[u"half-way", u"the-first-move"])
def test_a_rename_that_fails_puts_every_earlier_move_back(tmp_path, monkeypatch, fails_at,
                                                          touched):
    u"""Half way: 5 old entries out and 1 new in, all put back. At the first move:
    nothing moved, and the result must say so -- the window tells *"nothing was
    changed"* from *"put back"* by `touched`."""
    install, stage, _pending, path = _layout(tmp_path)
    real, calls = os.rename, []

    def flaky(source, target):
        calls.append(target)
        if len(calls) == fails_at:
            raise OSError(32, u"in use")
        return real(source, target)

    monkeypatch.setattr(swap.os, "rename", flaky)
    assert _run(path, _Ops()) == 1
    monkeypatch.setattr(swap.os, "rename", real)
    assert _old(install), u"the earlier moves were not put back"
    assert (install / u"LICENSE").read_bytes() == b"old LICENSE"
    assert _result(stage)[u"touched"] is touched


def test_a_listing_that_fails_is_a_result_never_a_crash(tmp_path):
    u"""⛔ `apply` never raises: a result is written and hato starts again."""
    install, stage, _pending, path = _layout(tmp_path)

    class Broken(_Ops):
        def processes_in(self, folder):
            raise OSError(5, u"denied")

    ops = Broken()
    assert _run(path, ops) == 1
    assert _old(install)
    assert u"before changing anything" in _result(stage)[u"reason"]
    assert ops.started == [u"hato.exe"]


def test_a_result_left_by_an_earlier_swap_is_gone_before_the_new_window_opens(tmp_path):
    u"""🚨 MEASURED BY THE REHEARSAL: a failed swap's result, never read (the version
    put back had no window that reads it), was shown by the NEXT swap's new window as
    *"didn't finish"* -- and the success written after it was never seen."""
    install, stage, pending, path = _layout(tmp_path)
    result = stage / u"result.json"
    result.write_text(json.dumps({u"status": u"failed", u"to": u"1.0.5"}), encoding="utf-8")
    seen = []
    _run(path, _Ops(on_start=lambda proc: seen.append(result.exists())))
    assert seen == [False], u"the new window could read an earlier swap's result"
    assert _result(stage)[u"status"] == swap.SUCCESS


def test_what_happened_is_written_in_hato_log(tmp_path):
    u"""⭐ The window's *put back* line says so -- and an install nobody watched (the
    tray's, at night) has no other record. `watch.complain`'s block shape."""
    install, stage, pending, path = _layout(tmp_path, bad_hash=True)
    log = tmp_path / u"hato.log"
    log.write_text(u"=== hato 2026-09-24 03:00:00 ===\na run\n", encoding="utf-8")
    pending[u"log"] = str(log)
    _write(path, pending)
    assert _run(path, _Ops()) == 1
    text = log.read_text(encoding="utf-8")
    assert text.startswith(u"=== hato 2026-09-24"), u"the log was not appended to"
    assert u"=== hato update " in text and u"1.0.4 -> 1.0.5: failed" in text, text
    assert u"hato.exe is not the file the release names" in text


def test_an_unreadable_hand_off_is_refused_without_touching_anything(tmp_path):
    path = tmp_path / u"pending.json"
    path.write_text(u"{broken", encoding="utf-8")
    assert swap.run(str(path), quiet=True, ops=_Ops()) == 2


# ---------------------------------------------------------------------------
# the real process listing, on Windows, under a Japanese-named folder
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not sys.platform.startswith("win"), reason=u"Toolhelp32 is Windows'")
def test_the_real_listing_finds_a_program_running_from_the_folder(tmp_path):
    folder = tmp_path / u"ツール置き場" / u"bin"
    folder.mkdir(parents=True)
    ping = os.path.join(os.environ.get("SystemRoot", u"C:\\Windows"), u"System32", u"PING.EXE")
    copy = folder / u"hato-cli.exe"
    shutil.copy2(ping, str(copy))
    ops = swap.WinOps()
    assert ops.processes_in(str(folder)) == [], u"the control: nothing runs from it yet"
    proc = subprocess.Popen([str(copy), u"-n", u"30", u"127.0.0.1"], stdout=subprocess.DEVNULL)
    try:
        found = ops.processes_in(str(folder))
        assert proc.pid in found, (proc.pid, found)
        assert os.path.realpath(ops.image(proc.pid)) == os.path.realpath(str(copy))
    finally:
        proc.terminate()
        proc.wait(10)
    assert swap.wait_gone(str(folder), ops, 10.0), u"a finished program still counted"


_WINDOW_SCRIPT = u'''
import ctypes, sys, time
from ctypes import wintypes
user32 = ctypes.WinDLL("user32")
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
# WS_POPUP | WS_VISIBLE, a tool window, far off screen: visible to Windows, seen by nobody
hwnd = user32.CreateWindowExW(0x80, "STATIC", sys.argv[1], 0x80000000 | 0x10000000,
                              -12000, -12000, 40, 40, None, None, None, None)
print("ready" if hwnd else "no window", flush=True)
time.sleep(60)
'''


@pytest.mark.skipif(not sys.platform.startswith("win"), reason=u"EnumWindows is Windows'")
def test_only_a_window_titled_hato_is_the_new_window(tmp_path):
    u"""🚨 A new version that dies at start shows the freezer's *"Unhandled
    exception"* dialog -- VISIBLE, and owned by the new process. Asked only
    whether it had a visible window, the swapper took that for the new window
    and kept a version that cannot start."""
    script = tmp_path / u"window.py"
    script.write_text(_WINDOW_SCRIPT, encoding="utf-8")
    ops = swap.WinOps()
    for title, want in ((swap.WINDOW_TITLE, True), (u"Unhandled exception in script", False)):
        proc = subprocess.Popen([sys.executable, str(script), title],
                                stdout=subprocess.PIPE)
        try:
            assert proc.stdout.readline().strip() == b"ready", u"no window was made"
            assert ops.window_visible(proc.pid), u"the control: it IS a visible window"
            assert ops.window_visible(proc.pid, swap.WINDOW_TITLE) is want, title
        finally:
            proc.terminate()
            proc.wait(10)


def test_the_swapper_asks_for_hatos_own_window_by_its_title(tmp_path):
    _install, _stage, _pending, path = _layout(tmp_path)
    ops = _Ops()
    _run(path, ops)
    assert ops.titles and set(ops.titles) == {swap.WINDOW_TITLE}, ops.titles


def _short(path):
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 32768)
    return buf.value if size else None


@pytest.mark.skipif(not sys.platform.startswith("win"), reason=u"8.3 names are Windows'")
def test_the_real_listing_finds_a_program_started_through_its_short_path(tmp_path):
    u"""🚨 MEASURED 2026-09-24, two arms on one process: started through its 8.3
    path, a program reports its image in that spelling, and a listing comparing
    only the long one MISSED it -- which reads as "nothing runs", and the renames
    then meet locked files."""
    folder = tmp_path / u"ツール置き場 long name" / u"bin"
    folder.mkdir(parents=True)
    copy = folder / u"hato-cli.exe"
    shutil.copy2(os.path.join(os.environ.get("SystemRoot", u"C:\\Windows"), u"System32",
                              u"PING.EXE"), str(copy))
    short = _short(copy)
    if not short or short == str(copy):
        pytest.skip(u"this volume makes no 8.3 names, so the case cannot arise here")
    proc = subprocess.Popen([short, u"-n", u"30", u"127.0.0.1"], stdout=subprocess.DEVNULL)
    try:
        ops = swap.WinOps()
        assert u"~" in (ops.image(proc.pid) or u""), u"the control: the image reads short"
        assert proc.pid in ops.processes_in(str(folder)), u"a hato started short was not seen"
    finally:
        proc.terminate()
        proc.wait(10)


# ---------------------------------------------------------------------------
# the splash (hato/splash.py): up for the swap, gone the moment hato is back
# ---------------------------------------------------------------------------

class _Card(object):
    u"""A splash that records WHEN it was asked to go."""

    def __init__(self, clock):
        self.clock, self.closed = clock, []

    def close(self):
        self.closed.append(self.clock())


def test_the_splash_goes_the_moment_the_new_window_shows(tmp_path, monkeypatch):
    u"""⭐ Not after the settle: the card is above everything, and three seconds more
    of it over the window a person is looking at is three seconds of a card saying
    hato is not there yet."""
    _install, _stage, _pending, path = _layout(tmp_path)
    clock = _Clock()
    card = _Card(clock)
    shown = []
    monkeypatch.setattr(swap, "_splash", lambda pending: shown.append(pending) or card)

    class Opens(_Ops):
        asks = 0

        def window_visible(self, pid, title=None):
            self.asks += 1
            if self.asks == 3:
                self.visible_at = clock()
            return self.asks >= 3

    ops = Opens()
    assert swap.run(str(path), quiet=False, ops=ops, clock=clock, sleep=clock.sleep) == 0
    assert shown, u"the control: a swap with a window asked for no splash"
    assert card.closed and card.closed[0] == ops.visible_at, (card.closed, ops.visible_at)
    assert card.closed[0] < clock(), u"the card stayed until the swap was over"


def test_a_swap_that_never_shows_a_window_still_takes_the_splash_down(tmp_path,
                                                                     monkeypatch):
    _install, _stage, _pending, path = _layout(tmp_path, bad_hash=True)
    clock = _Clock()
    card = _Card(clock)
    monkeypatch.setattr(swap, "_splash", lambda pending: card)
    assert swap.run(str(path), quiet=False, ops=_Ops(), clock=clock, sleep=clock.sleep) == 1
    assert card.closed, u"a failed swap left its card on screen"


def test_going_back_says_so_on_the_splash(monkeypatch):
    from hato import splash
    asked = []
    monkeypatch.setattr(splash, "show", lambda version, going_back=False: asked.append(
        (version, going_back)) or u"card")
    assert swap._splash({u"to": u"1.0.3", u"going_back": True}) == u"card"
    assert swap._splash({u"to": u"1.0.5"}) == u"card"
    assert asked == [(u"1.0.3", True), (u"1.0.5", False)], asked

    def broken(version, going_back=False):
        raise RuntimeError(u"no display")

    monkeypatch.setattr(splash, "show", broken)
    assert swap._splash({u"to": u"1.0.5"}) is None, u"a splash that cannot draw raised"


# ---------------------------------------------------------------------------
# ADVERSARY 2026-09-24 (LAYER 11z) -- the swapper's surface, and the seam S3
# ---------------------------------------------------------------------------

class _TrayWrites(_Ops):
    u"""A tray that writes its pid file only a moment after it starts -- the window's
    start and every pid-file write recorded on the clock."""

    def __init__(self, clock, marker, after=1.5, **kw):
        _Ops.__init__(self, **kw)
        self.clock, self.marker, self.after = clock, marker, after
        self.times = {}

    def start(self, path):
        proc = _Ops.start(self, path)
        name = os.path.basename(path)
        self.times.setdefault(name, []).append(self.clock())
        if name == u"hato-watch.exe":
            self.tray = proc
        return proc

    def tick(self):
        tray = getattr(self, "tray", None)
        if tray is not None and u"pid" not in self.times and \
                self.clock() >= self.times[u"hato-watch.exe"][-1] + self.after:
            with open(self.marker, "w", encoding="utf-8") as handle:
                handle.write(u"%d - retries,formats,updates" % tray.pid)
            self.times[u"pid"] = self.clock()


def _ticking(clock, ops):
    def sleep(seconds):
        clock.sleep(seconds)
        ops.tick()
    return sleep


@pytest.mark.parametrize("way", [u"the-update", u"a-way-out"])
def test_the_window_starts_only_once_the_new_tray_has_said_it_is_watching(tmp_path, way):
    u"""🚨 S3 (the seam review; adversary C reproduced it): the window's own start-up
    starts a tray whenever watching is on, guarded only by the pid file a tray writes a
    moment AFTER it starts. Started back to back, both passed -- two watchers, or a
    rollback with the window's tray holding `_internal`. ⭐ The tray first, and the
    window only once the tray has SAID it is watching -- on every way out too."""
    install, stage, pending, path = _layout(tmp_path, tray=True)
    marker = str(tmp_path / u"watch.pid")
    pending[u"tray_pid_file"] = marker
    _write(path, pending)
    clock = _Clock()
    ops = _TrayWrites(clock, marker, running_for=10 ** 6 if way == u"a-way-out" else 0)
    swap.run(str(path), quiet=True, ops=ops, clock=clock, sleep=_ticking(clock, ops))
    assert u"pid" in ops.times, u"the control: the tray never wrote its pid file"
    assert ops.times[u"hato.exe"][0] >= ops.times[u"pid"], \
        u"the window started at %s, before the tray said it was watching at %s" % (
            ops.times[u"hato.exe"][0], ops.times[u"pid"])


def test_a_rollback_stops_whatever_the_new_version_started_before_its_undo(tmp_path):
    u"""🚨 S3's second wall: a process the swapper did NOT start -- the window's own
    tray, the tray's catch-up run -- held `_internal`, and the undo could not move it
    back: a half-swapped folder. Everything running from the install is stopped first."""
    install, stage, pending, path = _layout(tmp_path)

    class Stranger(_Ops):
        swapped = False

        def processes_in(self, folder):
            if not self.swapped:
                self.swapped = (install / u"hato.exe").read_bytes() == b"new hato.exe"
            if not self.swapped:
                return []                    # before the renames: nothing runs there
            return [] if 7777 in self.stopped else [7777]

    ops = Stranger(dies_after=0)                 # the new window dies: a rollback
    assert _run(path, ops) == 1
    assert 7777 in ops.stopped, u"the undo ran with a stranger holding the folder"
    assert _old(install), u"the folder was not put back"


def test_a_person_closing_the_new_window_at_once_is_a_successful_update(tmp_path):
    u"""🚨 C7: a person may close the new window the moment it appears -- that is hato
    WORKING, and the settle put the whole update back as a failure and reopened the old
    window. Only an exit that is not clean (a crash, `qFatal`) is a failure."""
    install, stage, pending, path = _layout(tmp_path)
    assert _run(path, _Ops(dies_after=2, code=0)) == 0
    assert _result(stage)[u"status"] == swap.SUCCESS
    assert (install / u"hato.exe").read_bytes() == b"new hato.exe"
    crashed = _layout(tmp_path / u"crashed")
    assert _run(crashed[3], _Ops(dies_after=2, code=0xC0000409)) == 1, \
        u"the control: a crash in the settle is still put back"


@pytest.mark.parametrize("edit", [
    {u"entries": {u"..\\..\\pwned.txt": u"0" * 64}},
    {u"old_entries": [u"..\\neighbour.txt"]},
    {u"staged": u"OUTSIDE"},
    {u"previous": u"OUTSIDE"},
    {u"install": u"STAGE"}],
    ids=[u"an-escaping-entry", u"an-escaping-old-entry", u"staged-outside",
         u"previous-outside", u"install-overlaps-the-stage"])
def test_a_hand_off_that_reaches_outside_hatos_folders_touches_and_starts_nothing(tmp_path,
                                                                                  edit):
    u"""🚨 B1: the swapper re-trusted a locally written pending.json with no wall of its
    own -- an entry `..\\..\\x` landed OUTSIDE the install, an old entry moved a file from
    above it. It is refused before anything moves, and nothing is started from a folder
    it cannot trust."""
    install, stage, pending, path = _layout(tmp_path)
    neighbour = install.parent / u"neighbour.txt"
    neighbour.write_bytes(b"a neighbour")
    for key, value in edit.items():
        pending[key] = str(tmp_path / u"elsewhere") if value == u"OUTSIDE" else \
            str(stage) if value == u"STAGE" else value
    _write(path, pending)
    ops = _Ops()
    assert _run(path, ops) == 1
    assert _result(stage)[u"touched"] is False and u"outside" in _result(stage)[u"reason"]
    assert ops.started == [], u"programs were started from a hand-off it could not trust"
    assert _old(install) and neighbour.read_bytes() == b"a neighbour"
    assert not (tmp_path / u"pwned.txt").exists()


def test_a_result_or_log_named_outside_the_staging_folder_is_never_touched(tmp_path):
    u"""B1: `result` is REMOVED before a swap and then written; `log` is appended to --
    naming any file, they destroyed or grew it. The result stays beside the hand-off,
    and a log is only ever a hato.log."""
    install, stage, pending, path = _layout(tmp_path)
    victim, other = tmp_path / u"victim.txt", tmp_path / u"notes.txt"
    victim.write_bytes(b"precious")
    other.write_bytes(b"mine")
    pending[u"result"], pending[u"log"] = str(victim), str(other)
    _write(path, pending)
    assert _run(path, _Ops()) == 0
    assert victim.read_bytes() == b"precious" and other.read_bytes() == b"mine"
    assert os.path.isfile(str(path) + u".result"), u"the result went nowhere"


def test_a_pid_file_older_than_the_new_tray_is_not_its_proof(tmp_path):
    u"""B3: the tray was proven by pid ALONE -- a file left from before the start, whose
    pid Windows had since handed to the new tray, read as *watching*. ⭐ Only a file
    written after the start counts."""
    install, stage, pending, path = _layout(tmp_path, tray=True)
    marker = tmp_path / u"watch.pid"
    marker.write_text(u"1000 - retries,formats,updates", encoding="utf-8")   # its pid-to-be
    stale = os.path.getmtime(str(marker)) - 3600
    os.utime(str(marker), (stale, stale))
    pending[u"tray_pid_file"] = str(marker)
    _write(path, pending)
    assert _run(path, _Ops()) == 1
    assert u"never said it was watching" in _result(stage)[u"reason"]
    assert _old(install)


# ---------------------------------------------------------------------------
# ⛔ stdlib + ctypes only -- it must work when everything else is broken
# ---------------------------------------------------------------------------

ALLOWED = {u"argparse", u"ctypes", u"hashlib", u"json", u"os", u"re", u"shutil",
           u"subprocess", u"sys", u"time"}


def _imports(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or u""
            out.update(u"%s.%s" % (base, alias.name) if base == u"hato" else base
                       for alias in node.names)
    return out


def test_the_swapper_imports_nothing_but_the_standard_library():
    u"""⛔ The one hato module it may reach is its own splash (tests/test_splash.py
    holds that one to the same rule)."""
    found = _imports(SWAP_SOURCE)
    assert u"ctypes" in found and u"hato.splash" in found, \
        u"the control: the walk did not find the imports it must -- %s" % sorted(found)
    stray = sorted(n for n in found if n.split(u".")[0] not in ALLOWED
                   and n != u"hato.splash")
    assert stray == [], u"hato/swap.py imports %s" % stray
