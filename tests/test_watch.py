# -*- coding: utf-8 -*-
"""
The tray watcher -- RUNBOOK 7f, gui-mock/MEMORY.md.

⭐ THE POLICY IS TESTED, THE WIN32 CALLS ARE THIN. Everything that decides
anything -- when to fire, what is worth waking for, what gets spawned -- takes
a clock or a seam and is driven here. What is left needs a real filesystem and
a real Windows, and it is deliberately as small as it can be.

Structurally cannot cover: that `ReadDirectoryChangesW` really delivers an
event for a file copied in by Explorer, and the resident cost. The first needs
a real folder and a real copy; the second is a measurement, in
`gui-mock/MEMORY.md`, and ⛔ it must be re-derived rather than quoted.
"""
import ast
import importlib
import os
import re
import subprocess
import sys
import time

import pytest

from hato import tray, watch


class FakeClock(object):
    u"""⭐ So a check about a SIXTY SECOND delay does not take sixty seconds."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def timer(settle=60.0):
    clock = FakeClock()
    fired = []
    return clock, fired, watch.SettleTimer(settle, clock=clock, fire=fired.append)


# ---------------------------------------------------------------------------
# the settle timer -- the whole policy
# ---------------------------------------------------------------------------

def test_nothing_fires_before_the_settle_time():
    clock, fired, t = timer()
    t.touch(u"frieren S2 - 01.mkv")
    clock.advance(59.0)
    assert t.poll() == []
    assert fired == []


def test_it_fires_once_the_folder_has_been_quiet():
    clock, fired, t = timer()
    t.touch(u"frieren S2 - 01.mkv")
    clock.advance(61.0)
    assert t.poll() == [u"frieren S2 - 01.mkv"]
    assert len(fired) == 1


def test_a_second_change_RESETS_the_countdown(tmp_path):
    u"""⭐ IT IS QUIET WE WAIT FOR, NOT ELAPSED TIME. A season copied in over
    ten minutes must be ONE run, not one per episode -- and each new file has
    to push the deadline out, not be absorbed by a countdown already expiring.
    """
    clock, fired, t = timer()
    t.touch(u"ep01.mkv")
    clock.advance(55.0)
    t.touch(u"ep02.mkv")          # ⭐ pushes it out again
    clock.advance(10.0)           # 65s since the FIRST change
    assert t.poll() == []
    assert fired == []
    clock.advance(55.0)
    assert sorted(t.poll()) == [u"ep01.mkv", u"ep02.mkv"]


def test_a_whole_season_arriving_is_one_run():
    clock, fired, t = timer()
    for n in range(1, 13):
        t.touch(u"ep%02d.mkv" % n)
        clock.advance(5.0)
    clock.advance(61.0)
    t.poll()
    assert len(fired) == 1
    assert len(fired[0]) == 12


def test_polling_again_after_it_fired_does_nothing():
    clock, fired, t = timer()
    t.touch(u"a.mkv")
    clock.advance(61.0)
    t.poll()
    clock.advance(600.0)
    assert t.poll() == []
    assert len(fired) == 1


def test_a_change_during_a_run_starts_a_fresh_countdown():
    u"""⚠ The pending list is cleared BEFORE `fire` runs. A run takes minutes,
    and a file arriving while it is in flight must not be swallowed by the
    batch already being processed -- it would then wait for the NEXT change,
    which for a finished season never comes."""
    clock = FakeClock()
    seen = []

    def slow_run(names):
        seen.append(list(names))
        t.touch(u"arrived-during-the-run.mkv")     # as if copied in mid-run

    t = watch.SettleTimer(60.0, clock=clock, fire=slow_run)
    t.touch(u"first.mkv")
    clock.advance(61.0)
    t.poll()
    assert seen == [[u"first.mkv"]]
    assert t.waiting == [u"arrived-during-the-run.mkv"]
    clock.advance(61.0)
    t.poll()
    assert seen[-1] == [u"arrived-during-the-run.mkv"]


# ---------------------------------------------------------------------------
# what is worth waking for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,want", [
    (u"frieren S2 - 01.mkv", True),
    (u"ONE PIECE - 1121.mp4", True),
    (u"葬送のフリーレン - 01.mkv", True),
    # ⛔ A DOWNLOAD IN PROGRESS.
    (u"frieren S2 - 01.mkv.part", False),
    (u"frieren S2 - 01.mkv.crdownload", False),
    (u"frieren S2 - 01.mkv.!ut", False),
    # ⛔ AND hato's OWN OUTPUT. Waking for the subtitle hato just wrote is how
    # a watcher spins: every run produces one, which triggers the next run.
    (u"frieren S2 - 01.ja.ass", False),
    (u"frieren S2 - 01.ja.srt", False),
    (u"notes.txt", False),
    (u"cover.jpg", False),
])
def test_only_a_finished_video_is_worth_waking_for(name, want):
    assert watch.is_interesting(name) is want


# ---------------------------------------------------------------------------
# 🚨 a FOLDER dragged in -- Sonic, 2026-09-18: *"i just moved another folder
# with filess in a folder into the folder and it doesn't see it ... The auto
# watcher sees it when I copy the files themselves into the main folder."*
#
# ⭐ Moving a directory within one volume is ONE rename. Windows names the
# directory and says nothing about the files under it, because none of them
# were touched -- so the name-only filter rejected the only event there was.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,isdir,want", [
    # a real video still wakes it, with or without a root
    (u"frieren S2 - 01.mkv", False, True),
    # 🚨 THE BUG: a folder dragged in, reported once under its own name
    (u"Yomi no Tsugai", True, True),
    (u"葬送のフリーレン S2", True, True),
    # ⛔ and a plain file still does not
    (u"notes.txt", False, False),
    (u"cover.jpg", False, False),
    # ⛔ hato's OWN output stays rejected -- it is a file, so the probe says no.
    # This is what stops the watcher spinning on the subtitle it just wrote.
    (u"frieren S2 - 01.ja.ass", False, False),
])
def test_a_folder_dragged_in_is_worth_waking_for(name, isdir, want):
    assert watch.is_interesting_arrival(
        name, root=u"C:\\watched", isdir=lambda _p: isdir) is want


def test_without_a_root_it_falls_back_to_the_name_alone():
    u"""⚠ A relative name cannot be probed. Refuse rather than guess."""
    assert watch.is_interesting_arrival(u"Yomi no Tsugai") is False
    assert watch.is_interesting_arrival(u"frieren - 01.mkv") is True


def test_a_video_never_costs_a_filesystem_probe():
    u"""⭐ The stat runs only for names the suffix test already threw away."""
    asked = []

    def probe(path):
        asked.append(path)
        return False

    assert watch.is_interesting_arrival(
        u"frieren - 01.mkv", root=u"C:\\watched", isdir=probe) is True
    assert asked == []


def test_a_name_that_raced_its_own_deletion_is_not_fatal():
    def probe(_path):
        raise OSError(2, "gone")

    assert watch.is_interesting_arrival(
        u"whatever", root=u"C:\\watched", isdir=probe) is False


def test_an_empty_notification_wakes_nothing():
    assert watch.is_interesting_arrival(u"", root=u"C:\\watched") is False
    assert watch.is_interesting_arrival(None, root=u"C:\\watched") is False


def test_an_arrival_inside_a_SKIPPED_SUBFOLDER_does_not_start_a_countdown():
    u"""🚨 Sonic, 2026-09-22: *"it found files in a folder that is inside a
    blacklisted folder ... it noticed it but didn't seem to do anything with
    it. Noticed it in the section at the bottom that indicates what its
    doing."*

    ⛔ `main()` filters whole ROOTS against `skip_folders`. A root that is not
    skipped can hold a subfolder that IS, and an arrival there touched the
    timer and wrote `pending`, so the window advertised a run -- which the
    pipeline then correctly found nothing to do in.

    ⚠ WORSE than an invisible miss: the footer promised something."""
    skip = [u"C:\\watched\\Raw"]
    assert watch.should_wake(u"Raw\\frieren - 01.mkv", root=u"C:\\watched",
                             skip_folders=skip) is False
    # ⭐ and a sibling folder that merely SHARES A PREFIX is not skipped
    assert watch.should_wake(u"RawDump\\frieren - 01.mkv", root=u"C:\\watched",
                             skip_folders=skip) is True
    # ⭐ the ordinary case still wakes
    assert watch.should_wake(u"frieren - 01.mkv", root=u"C:\\watched",
                             skip_folders=skip) is True


def test_should_wake_still_defers_to_the_arrival_filter_and_to_a_sweep():
    u"""⚠ `None` means the watcher asked for a sweep, not that something
    arrived -- it must still wake, or the catch-up run never happens."""
    assert watch.should_wake(None, root=u"C:\\watched", skip_folders=[]) is True
    assert watch.should_wake(u"notes.txt", root=u"C:\\watched",
                             skip_folders=[], isdir=lambda _p: False) is False


def test_each_watcher_is_bound_to_ITS_OWN_folder(tmp_path, monkeypatch):
    u"""🚨 THE WIRING, NOT THE LOGIC.

    ⛔ `is_interesting_arrival` being correct proves nothing if `main` never
    hands it a root -- and this project's most expensive recurring defect is a
    thing that is built, correct, and connected to nothing.

    ⭐ It also pins the late-binding trap: a bare closure over the loop
    variable would give EVERY watcher the last folder, so the second folder
    would answer for the first. Here folder B must NOT recognise a directory
    that exists only under folder A.
    """
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    (a / "Dragged In").mkdir()              # exists under A only

    captured = []

    class FakeWatcher(object):
        def __init__(self, folder, on_change, recurse=True):
            captured.append((folder, on_change))

        def start(self):
            return self

        def stop(self):
            pass

    class FakeCfg(object):
        folders = [str(a), str(b)]
        skip_folders = []
        recurse = True

    class FakeTray(object):
        def __init__(self, *a, **k):
            pass

        def run(self, on_tick=None, on_error=None):
            return 0

    woke = []
    monkeypatch.setattr(watch, "DirectoryWatcher", FakeWatcher)
    monkeypatch.setattr(watch, "spawn_run", lambda *a, **k: None)
    monkeypatch.setattr(watch, "write_pid_file", lambda: None)
    monkeypatch.setattr(watch, "clear_pid_file", lambda: None)
    monkeypatch.setattr(watch, "clear_pending", lambda: None)
    monkeypatch.setattr(watch, "write_pending",
                        lambda due, names=(): woke.append(list(names)))
    monkeypatch.setattr("hato.config.load", lambda *a, **k: FakeCfg())
    monkeypatch.setattr("hato.tray.Tray", FakeTray)

    assert watch.main([]) == 0
    assert len(captured) == 2, "one watcher per folder"

    by_folder = dict(captured)
    # ⭐ A's callback sees the dragged-in folder ...
    by_folder[str(a)](u"Dragged In")
    assert woke == [[u"Dragged In"]]

    # ⛔ ... and B's does not, because B does not contain it. A shared closure
    # would have bound both to the last folder and broken exactly this.
    del woke[:]
    by_folder[str(b)](u"Dragged In")
    assert woke == []


# ---------------------------------------------------------------------------
# 🚨 the FileNameLength trap
# ---------------------------------------------------------------------------

def notification(name, next_entry=0, action=1):
    u"""One FILE_NOTIFY_INFORMATION record, as Windows lays it out."""
    encoded = name.encode("utf-16-le")
    return (next_entry.to_bytes(4, "little") + action.to_bytes(4, "little") +
            len(encoded).to_bytes(4, "little") + encoded)


def test_the_name_length_is_BYTES_not_characters():
    u"""🚨 Read as a character count it takes HALF the name, so every
    `frieren S2 - 01.mkv` becomes `frieren S2 - 0` -- `is_interesting` is then
    false for every file there is, and the watcher never fires, with nothing
    in any log to say why."""
    raw = notification(u"frieren S2 - 01.mkv")
    assert watch.parse_notifications(raw, len(raw)) == [u"frieren S2 - 01.mkv"]


def test_a_japanese_name_survives_the_decode():
    raw = notification(u"葬送のフリーレン - 01.mkv")
    assert watch.parse_notifications(raw, len(raw)) == [u"葬送のフリーレン - 01.mkv"]


def test_several_notifications_chain():
    first = notification(u"a.mkv", next_entry=12 + len(u"a.mkv".encode("utf-16-le")))
    raw = first + notification(u"b.mkv")
    assert watch.parse_notifications(raw, len(raw)) == [u"a.mkv", u"b.mkv"]


def test_a_truncated_buffer_does_not_raise():
    raw = notification(u"frieren S2 - 01.mkv")
    assert watch.parse_notifications(raw, 6) == []


# ---------------------------------------------------------------------------
# what gets spawned
# ---------------------------------------------------------------------------

def test_the_run_is_quiet_and_every_folder_is_absolute(monkeypatch):
    monkeypatch.delenv("HATO_CLI", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    seen = {}
    watch.spawn_run(["Anime"], spawner=lambda argv, env: seen.update(
        argv=argv, env=env))
    assert "--quiet" in seen["argv"]
    assert seen["argv"][-1] == os.path.abspath("Anime")
    assert seen["env"]["PYTHONUTF8"] == "1"


def test_every_run_the_tray_starts_waits_for_the_lock_rather_than_giving_up(monkeypatch):
    u"""ADVERSARY 2026-09-22 L1 + R11. The tray asks whether a run holds the lock
    and THEN spawns; a frozen child needs a second or two to reach it, and a run
    starting in between made the tray's run exit with nothing scanned -- the
    arrival it was for, never looked at. The catch-up run at start is spawned
    without asking at all. ⭐ Every one is told to wait -- in a flag `hato` takes."""
    import argparse
    from hato.commands import run as run_cmd
    monkeypatch.delenv("HATO_CLI", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    seen = {}
    watch.spawn_run(["Anime"], spawner=lambda argv, env: seen.update(argv=argv))
    assert "--wait" in seen["argv"], seen["argv"]
    parser = argparse.ArgumentParser()
    run_cmd.register(parser)
    args = parser.parse_args(seen["argv"][len(watch.run_argv()):])
    assert args.wait is True and args.quiet is True


def test_a_run_that_cannot_be_started_is_said_and_the_tray_lives(tmp_path, monkeypatch):
    u"""ADVERSARY 2026-09-22 C6. `hato-cli.exe` gone -- quarantined by antivirus,
    mid-update -- raised straight out of the tray's message loop."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    monkeypatch.setenv("HATO_CLI", str(tmp_path / u"hato-cli-that-is-gone.exe"))
    monkeypatch.setattr(sys, "stderr", None)
    try:
        started = watch.spawn_run([str(tmp_path)])
    except OSError as exc:
        pytest.fail(u"a missing hato-cli raised %s out of the tray" % type(exc).__name__)
    assert started is None
    assert u"could not be started" in (tmp_path / u"hato.log").read_text(encoding="utf-8"), (
        u"the failure reached nobody")


def test_no_folders_spawns_nothing():
    assert watch.spawn_run([], spawner=lambda argv, env: pytest.fail("spawned")) is None


def test_frozen_it_runs_the_exe_beside_the_bundle(monkeypatch):
    monkeypatch.delenv("HATO_CLI", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join("C:\\app", "hato-watch.exe"))
    argv = watch.run_argv()
    assert len(argv) == 1 and "-m" not in argv


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="a Windows console")
def test_opening_a_WINDOW_never_asks_windows_to_hide_it():
    u"""🚨 THE BUG SONIC HIT TWICE, 2026-09-18. *"it's in the tray but can't see
    the UI. both the tray click and hato shortcut doesn't work."*

    ⭐ `STARTF_USESHOWWINDOW` WITH `wShowWindow` AT ITS DEFAULT IS `SW_HIDE`.
    Windows hands that to the child as the `nCmdShow` for its FIRST window, and
    Qt honours it -- so the window was created as a real native window and
    never shown. Measured in a controlled pair: with those keywords **0**
    visible windows, without them **1**.

    ⚠ IT ONLY HAPPENED FROM THE TRAY. A shortcut goes through Explorer, which
    passes `SW_SHOWNORMAL` -- so the same code was fine one way and haunted the
    other. And the invisible window then HOLDS the single-instance name, which
    is why the shortcut stopped working too: one cause, both symptoms.

    ⛔ The console flag STAYS. It suppresses a console, which a GUI has no use
    for, and does not touch window visibility.

    ⚠ THE ASSERTION IS ON `wShowWindow`, NOT ON THE ABSENCE OF STARTUPINFO.
    The first fix simply dropped STARTUPINFO, which worked -- and then the
    no-busy-cursor flag had to live there, so it came back. Checking for its
    absence would have failed against correct code; checking that the show
    command is SW_SHOWNORMAL is the thing that actually matters, either way.
    """
    import subprocess as sp

    gui = watch.gui_spawn_kwargs()
    assert gui.get("creationflags", 0) & 0x08000000, u"a console would flash"
    info = gui.get("startupinfo")
    if info is not None and (info.dwFlags & sp.STARTF_USESHOWWINDOW):
        assert info.wShowWindow == 1, (
            u"wShowWindow is %d; the default 0 is SW_HIDE, which builds the "
            u"window native and invisible" % info.wShowWindow)


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="spawn flags are a Windows concept; both are {} here")
def test_a_console_child_and_a_window_child_are_spawned_DIFFERENTLY():
    u"""⚠ The two are not interchangeable, and treating them as one is what
    made a window invisible. A CLI child wants its console suppressed; a GUI
    child must not be told how to show itself.

    ⛔ WINDOWS ONLY, and CI found the omission. Both helpers return `{}` off
    Windows -- correctly, because `creationflags` and `STARTUPINFO` do not
    exist there -- so the assertion read `{} != {}` and failed on six jobs.
    Its sibling below already carried this marker; this one did not.
    """
    assert watch.no_console_kwargs() != watch.gui_spawn_kwargs()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="a Windows console")
def test_the_spawned_run_gets_no_console_of_its_own():
    kwargs = watch.no_console_kwargs()
    assert kwargs["creationflags"] & 0x08000000
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW


# ---------------------------------------------------------------------------
# 🚨 the memory discipline, as a STRUCTURAL check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["watch", "tray", "retries"])
def test_the_watcher_imports_no_toolkit_and_no_pipeline(module):
    u"""🚨 THE ARCHITECTURE, AS A CHECK RATHER THAN AN INTENTION.

    `gui-mock/MEMORY.md`: a resident Qt tray is **30.6 MB** against this
    process's **13.4 MB**, and the watching itself costs **0.7 MB** -- the rest
    is the interpreter. The entire reason the watcher is a separate program is
    that it loads neither the toolkit nor hato's pipeline, and an `import` added
    in a hurry would undo that silently, with nothing visible but a number
    nobody re-measures.

    ⭐ Static, not `sys.modules`: another suite in the same process may have
    imported Qt already, which would make a runtime check pass or fail for
    reasons that have nothing to do with this file.

    ⚠ BOTH MODULES, because the tray is the other half of the same process.
    `hato/tray.py` puts the icon up through shell32 and `hato/watch.py` does
    the watching; a `QSystemTrayIcon` in either one costs the same 2.3x and
    would be just as invisible. Parametrised rather than duplicated, so a
    third module in this process is one word to cover.

    ⚠ WALKED WITH `ast`, NOT A REGEX -- and that is a fix, not a preference.
    A regex over `from X import Y` sees only X, so `from hato import gui`
    would have sailed through a check that catches `import hato.gui`. The one
    spelling anybody would actually type was the one it could not see.
    """
    target = importlib.import_module("hato." + module)
    source = open(target.__file__, encoding="utf-8").read()
    # ⚠ `hato.tray` IS NOT BANNED. It is the other half of this same process
    # and is toolkit-free under the same rule, so `watch.main()` importing it
    # is the architecture working, not a leak. What is banned is anything that
    # brings a toolkit or the pipeline in with it.
    banned = ("PyQt6", "PySide6", "tkinter", "customtkinter",
              "hato.pipeline", "hato.client", "hato.gui")
    if module == "retries":
        # ⭐ RUNBOOK 8h -- the file between a run and the tray. The RUN reads the
        # state DB and hands the dates over; the tray's half only reads a file.
        banned += ("hato.state",)

    imported = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            # ⭐ AND WHAT WAS TAKEN OUT OF IT -- `from hato import gui`.
            imported.extend(node.module + "." + alias.name
                            for alias in node.names)

    for name in imported:
        for bad in banned:
            assert not (name == bad or name.startswith(bad + ".")), (
                "hato/%s.py imports %s. The watcher is a separate process "
                "precisely so it loads neither a GUI toolkit nor hato's "
                "pipeline -- see gui-mock/MEMORY.md." % (module, name))


# ---------------------------------------------------------------------------
# the tray's menu -- the half that can be wrong invisibly
# ---------------------------------------------------------------------------

def items():
    opened, ran = [], []
    return ([(u"Open hato", lambda: opened.append(1)),
             (u"Run now", lambda: ran.append(1)),
             None,
             (u"Quit", None)], opened, ran)


def test_a_separator_consumes_no_command_id():
    u"""🚨 THE OFF-BY-ONE NOBODY SEES. Give the separator an id and every item
    after it shifts, so clicking *Quit* runs whatever now holds its number --
    on this menu, a run. The ids and the routing come from ONE function so
    they cannot drift."""
    menu, _opened, _ran = items()
    numbered = tray.menu_commands(menu)
    assert [label for _n, label, _cb in numbered] == \
        [u"Open hato", u"Run now", u"Quit"]
    assert [n for n, _l, _cb in numbered] == [1, 2, 3]


def test_the_first_command_is_not_zero():
    u"""⛔ `TrackPopupMenu` with TPM_RETURNCMD returns 0 for *the menu was
    dismissed*, so an item numbered 0 cannot be told from pressing Escape."""
    assert tray.FIRST_COMMAND >= 1
    menu, _o, _r = items()
    assert all(n >= 1 for n, _l, _cb in tray.menu_commands(menu))


def test_each_command_reaches_its_own_action():
    menu, opened, ran = items()
    tray.dispatch(menu, 1)()
    assert (len(opened), len(ran)) == (1, 0)
    tray.dispatch(menu, 2)()
    assert (len(opened), len(ran)) == (1, 1)


def test_the_item_with_no_callback_is_quit():
    u"""⭐ The menu says what it does; the absence of an action IS the action,
    and the window layer reads `None` as stop."""
    menu, _o, _r = items()
    assert tray.dispatch(menu, 3) is None


def test_a_stray_command_id_is_ignored_rather_than_raising():
    u"""⚠ A WM_COMMAND can arrive for an id this menu never made. Raising
    inside a WNDPROC kills the process with no traceback anybody sees."""
    menu, _o, _r = items()
    assert tray.dispatch(menu, 99) is None
    assert tray.dispatch([], 1) is None


def test_the_notify_struct_declares_its_own_size():
    u"""⚠ `cbSize` IS THE VERSION NEGOTIATION -- shell32 reads it to decide
    which fields exist, so a wrong one is refused or read past."""
    import ctypes
    data = tray.NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(tray.NOTIFYICONDATAW)
    assert data.cbSize == ctypes.sizeof(tray.NOTIFYICONDATAW)
    assert ctypes.sizeof(tray.NOTIFYICONDATAW) > 300   # the Vista+ layout


def test_the_callback_message_is_in_the_application_range():
    u"""⛔ Below WM_APP the number belongs to Windows, and a tray callback that
    collides with a system message is a bug that only shows up on someone
    else's machine."""
    assert tray.WM_TRAY >= 0x8000


@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="the refusal is for the platforms without a tray")
def test_off_windows_the_tray_refuses_with_an_instruction():
    with pytest.raises(tray.TrayError) as exc:
        tray.Tray(u"hato")
    assert "cron" in str(exc.value) or "timer" in str(exc.value)


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="Tray refuses to construct off Windows, by design")
def test_a_long_tooltip_is_cut_to_what_the_field_holds():
    u"""⚠ `szTip` IS 128 WCHARs INCLUDING THE TERMINATOR, and ctypes raises on
    an over-long assignment -- so a show-name longer than the field would take
    the tray down at the moment it was put up, rather than displaying oddly.
    ⛔ Constructing a Tray opens no window and makes no shell call."""
    icon = tray.Tray(u"hato -- " + u"x" * 400)
    assert len(icon.tooltip) <= 127
    import ctypes
    data = tray.NOTIFYICONDATAW()
    data.szTip = icon.tooltip                # must not raise
    assert data.szTip.startswith(u"hato")


# ---------------------------------------------------------------------------
# one watcher, and only one
# ---------------------------------------------------------------------------

def test_a_stale_pid_file_is_not_a_running_watcher(tmp_path, monkeypatch):
    u"""🚨 THE HALF THAT MAKES SINGLE-INSTANCE SAFE. A tray killed by a reboot,
    Task Manager or a crash leaves its file behind. Believed, it would refuse
    to start a watcher FOR EVER -- the toggle would read on and nothing would
    be watching, which is worse than two watchers.

    ⭐ `runlock` already answers this honestly: the pid AND its creation stamp,
    because a night-old pid belongs to some other program by morning.
    """
    path = tmp_path / "watch.pid"
    monkeypatch.setattr(watch, "pid_file_path", lambda: path)

    assert watch.watching_pid() is None, u"no file at all is not a watcher"

    path.write_text(u"999999 12345", encoding="utf-8")
    assert watch.watching_pid() is None, u"a dead pid is not a watcher"

    path.write_text(u"not-a-number", encoding="utf-8")
    assert watch.watching_pid() is None, u"garbage is not a watcher"


def test_this_process_recognises_itself_as_the_watcher(tmp_path, monkeypatch):
    u"""⭐ The positive half. Without it the check above would pass against a
    function that simply always answered None."""
    path = tmp_path / "watch.pid"
    monkeypatch.setattr(watch, "pid_file_path", lambda: path)
    watch.write_pid_file()
    assert watch.watching_pid() == os.getpid()
    watch.clear_pid_file()
    assert watch.watching_pid() is None


def test_the_escape_hatch_for_testing_is_named():
    u"""⚠ Sonic asked for one: *"during testing it could be useful to have
    more."* ⛔ It has to be deliberate, so it is an environment variable and
    not a flag somebody trips over."""
    source = open(watch.__file__, encoding="utf-8").read()
    assert u"HATO_ALLOW_MANY" in source


# ---------------------------------------------------------------------------
# 🚨 NO STANDARD STREAMS -- what a Windows Run key actually hands this process
#
# MEASURED 2026-09-18: a `pythonw.exe` started detached has BOTH `sys.stdout`
# and `sys.stderr` as None, and `sys.stderr.write(...)` raises AttributeError.
# `main()` reported four refusals that way, so "Start with Windows" + no folder
# yet -- the ordinary first-run order -- crashed at EVERY login, with no
# console, nothing in the tray and no exit code anybody sees.
# ---------------------------------------------------------------------------

def test_complain_survives_having_nowhere_to_print(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))      # ⛔ never the real log
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    watch.complain(u"hato: something to say\n")          # must not raise
    log = tmp_path / "hato.log"
    assert log.is_file(), u"with no stream, the LOG is the only channel left"
    assert u"something to say" in log.read_text(encoding="utf-8")


def test_complain_still_writes_the_stream_when_there_is_one(tmp_path,
                                                            monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    said = []

    class Stream(object):
        def write(self, text):
            said.append(text)

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stderr", Stream())
    watch.complain(u"hato: audible\n")
    assert said == [u"hato: audible\n"]


def test_main_REFUSES_CLEANLY_with_no_streams_at_all(tmp_path, monkeypatch):
    u"""🚨 THE LOGIN PATH. No folder configured and nowhere to print: `main`
    must return 2, not raise."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    monkeypatch.setenv("HATO_ALLOW_MANY", "1")
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)

    class FakeCfg(object):
        folders = []
        skip_folders = []
        recurse = True

    monkeypatch.setattr("hato.config.load", lambda *a, **k: FakeCfg())

    assert watch.main([]) == 2
    assert (tmp_path / "hato.log").is_file(), \
        u"the refusal reached nobody at all"


def test_the_settle_default_is_the_one_sonic_ruled():
    u"""⚠ One minute, and it earns its keep twice: it debounces a burst, and
    it lets a still-downloading file finish before hato opens it."""
    assert watch.SETTLE_SECONDS == 60.0


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 8h -- the retry actually happens
# ---------------------------------------------------------------------------
# 🚨 The 24-hour retry is decided at the gate, in a run AFTER the date -- and
# nothing started that run: the 03:00 switch registered no task (D2, built
# since). The tray is the one resident process, so it wakes for every date a
# run wrote down -- sooner than the daily run, which keeps it at its next start.

def retry_clock(dues, coalesce=300.0):
    u"""-> (clock, fired, RetryClock). `dues` is a list the check may change."""
    clock = FakeClock()
    fired = []
    return clock, fired, watch.RetryClock(load=lambda: list(dues), clock=clock,
                                          fire=fired.append, coalesce=coalesce)


def test_a_promised_retry_runs_once_when_it_comes_due():
    dues = [1000.0 + 50000.0]
    clock, fired, retry = retry_clock(dues)
    # ⚠ FAR from the date first: a second before it is inside the coalescing
    # window, which holds a run back anyway -- an early fire would hide there.
    assert retry.poll() == [] and fired == [], u"it fired hours before the date"
    clock.advance(49999.0)
    assert retry.poll() == [] and fired == [], u"it fired before the date"
    clock.advance(2.0)
    assert retry.poll() == [51000.0] and fired == [[51000.0]]
    clock.advance(1.0)
    assert retry.poll() == [] and len(fired) == 1, (
        u"one date started two runs -- a date whose video has gone stays in the "
        u"file, and would start a run every second")


def test_a_date_already_due_when_watching_starts_is_the_catch_up_runs():
    u"""⭐ `main()` starts one catch-up run as watching begins; firing for a date
    it already covers is two runs racing one lock, and the loser says nothing
    was scanned."""
    dues = [900.0, 999.0]                      # both before the clock's 1000
    clock, fired, retry = retry_clock(dues)
    clock.advance(10.0)
    assert retry.poll() == [] and fired == []
    dues.append(1500.0)                        # ⭐ and a later one still fires
    clock.advance(600.0)
    assert fired == [] and retry.poll() == [1500.0]


def test_dates_seconds_apart_are_ONE_run():
    u"""🚨 Sonic's 19 Sep run left three negatives between 07:03:03 and 07:03:05.
    A run fired at :04 finds the :05 video still waiting -- so it would sit until
    the NEXT date. The dates coalesce, and the run starts after the last."""
    dues = [5000.0, 5001.0, 5002.0]
    clock, fired, retry = retry_clock(dues, coalesce=300.0)
    clock.now = 5000.5
    assert retry.poll() == [], u"it fired with two more dates seconds away"
    clock.now = 5002.0
    assert retry.poll() == [5000.0, 5001.0, 5002.0]
    assert fired == [[5000.0, 5001.0, 5002.0]], u"one burst became several runs"


def test_a_far_date_does_not_hold_back_a_due_one():
    dues = [5000.0, 5000.0 + 86400.0]
    clock, fired, retry = retry_clock(dues, coalesce=300.0)
    clock.now = 5000.0
    assert retry.poll() == [5000.0], u"tomorrow's date postponed today's"


def test_a_date_a_later_run_writes_is_kept_too():
    dues = []
    clock, fired, retry = retry_clock(dues)
    clock.advance(100.0)
    assert retry.poll() == []
    dues.append(clock.now + 3600.0)            # a run, an hour later, promises
    clock.advance(3601.0)
    assert len(retry.poll()) == 1 and len(fired) == 1


def test_the_dates_file_round_trips_and_a_broken_one_is_no_dates(tmp_path):
    from datetime import datetime, timedelta, timezone
    from hato import retries

    target = tmp_path / u"retries-due.json"
    base = datetime(2026, 9, 23, 7, 3, 5, tzinfo=timezone.utc)
    later = base + timedelta(days=1)
    assert retries.save([later, base, base + timedelta(seconds=2)], target) == target
    minute = datetime(2026, 9, 23, 7, 4, tzinfo=timezone.utc)
    assert retries.load(target) == [minute.timestamp(), (minute + timedelta(days=1)).timestamp()], (
        u"not every date once each, rounded UP to its minute, soonest first -- dates "
        u"seconds apart are ONE date (R4), and a wake is never EARLY: %r"
        % retries.load(target))
    assert not [p for p in tmp_path.iterdir() if u".new-" in p.name], u"a temp was left"
    target.write_text(u"{not json", encoding="utf-8")
    assert retries.load(target) == []
    assert retries.load(tmp_path / u"absent.json") == []
    assert retries.save([base], tmp_path / u"no-such-dir" / u"x" / u"f.json") is not None
    blocked = tmp_path / u"a-file"
    blocked.write_text(u"x", encoding="utf-8")
    assert retries.save([base], blocked / u"f.json") is None, u"an unwritable place raised"


def test_a_burst_of_promises_is_kept_whole_and_the_file_stays_bounded(tmp_path):
    u"""ADVERSARY 2026-09-22 R4. A first run over a big library promises a date
    per video, and the file was cut at 200 -- the tail was lost, and the tray
    never woke for it. ⚠ 250 is written out, never derived from `KEEP`: a check
    built from the constant would shrink with it."""
    from datetime import datetime, timedelta, timezone
    from hato import retries
    target = tmp_path / u"retries-due.json"
    base = datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc)
    retries.save([base + timedelta(minutes=n) for n in range(250)], target)
    kept = retries.load(target)
    assert len(kept) == 250, u"a burst of 250 promises was cut to %d" % len(kept)
    retries.save([base + timedelta(minutes=n) for n in range(retries.KEEP * 3)], target)
    kept = retries.load(target)
    assert len(kept) == retries.KEEP and kept[0] == base.timestamp(), (
        u"the file is not bounded, or it kept other than the soonest: %d" % len(kept))


#: ⚠ BUILT IN THE CHECK, NOT PASSED AS A PARAMETER: pytest puts the test id in an
#: environment variable, and a 200,000-character id is longer than Windows allows.
_NOT_DATES = {
    u"nested": (lambda: u"[" * 100000 + u"]" * 100000, u"could not be read"),    # R7
    u"an object": (lambda: u'{"due": {"2026-09-23T07:04:00+00:00": 1}}', u"no list of dates"),
    u"bare numbers": (lambda: u"[1000200]", u"no list of dates"),
    u"an epoch": (lambda: u'{"due": [1000200, "2026-09-23T07:04:00+00:00"]}', u"not a date"),
}


@pytest.mark.parametrize("shape", sorted(_NOT_DATES))
def test_a_dates_file_that_is_not_dates_says_so_and_never_raises(tmp_path, shape):
    u"""ADVERSARY 2026-09-22 R7 + R8. Deeply nested JSON raised RecursionError
    past the reader's guard and the tray died on every start; an object, bare
    numbers or a byte-order mark all read as "no dates" in silence."""
    from hato import retries
    body, why = _NOT_DATES[shape][0](), _NOT_DATES[shape][1]
    target = tmp_path / u"retries-due.json"
    target.write_text(body, encoding="utf-8")
    try:
        dues, problem = retries.read(target)
    except Exception as exc:                      # noqa: BLE001 -- the finding IS a raise
        pytest.fail(u"reading a broken dates file raised %s -- the tray reads it every tick"
                    % type(exc).__name__)
    assert problem and why in problem, (dues, problem)
    assert retries.load(target) == dues


def test_a_dates_file_with_a_byte_order_mark_is_read(tmp_path):
    from datetime import datetime, timezone
    from hato import retries
    target = tmp_path / u"retries-due.json"
    target.write_text(u'﻿{"due": ["2026-09-23T07:04:00+00:00"]}', encoding="utf-8")
    due = datetime(2026, 9, 23, 7, 4, tzinfo=timezone.utc).timestamp()
    assert retries.read(target) == ([due], None), retries.read(target)
    assert retries.read(tmp_path / u"absent.json") == ([], None), u"no file is not a problem"


def test_a_rename_refused_by_a_reader_is_waited_out_not_dropped(tmp_path, monkeypatch):
    u"""ADVERSARY 2026-09-22 R9. Windows refuses to rename over a file another
    process holds open -- and the tray opens this one once a second. The refusal
    returned None and the run's dates were simply not written."""
    from datetime import datetime, timezone
    from hato import retries
    target = tmp_path / u"retries-due.json"
    real, refused = os.replace, []

    def held_open(src, dst):
        if len(refused) < 3:
            refused.append(dst)
            raise PermissionError(13, u"The process cannot access the file", dst)
        return real(src, dst)

    monkeypatch.setattr(retries.os, "replace", held_open)
    due = datetime(2026, 9, 23, 7, 4, tzinfo=timezone.utc)
    assert retries.save([due], target) == target, u"a reader's instant dropped the dates"
    assert len(refused) == 3 and retries.load(target) == [due.timestamp()]
    assert not [p for p in tmp_path.iterdir() if u".new-" in p.name], u"a temp was left"


def test_a_reader_is_waited_out_in_TIME_not_in_tries(tmp_path, monkeypatch):
    u"""R9, the wait itself. A reader holds the file for as long as it holds it,
    and twenty tries inside one instant are twenty refusals -- the check above
    counts refusals, so it could not see the wait go. ⭐ On a fake clock that
    only the save's OWN sleep advances: no wait, no time, no write."""
    from datetime import datetime, timezone
    from hato import retries
    target = tmp_path / u"retries-due.json"
    real, now = os.replace, [0.0]

    def held_for_a_moment(src, dst):
        if now[0] < 0.3:                          # the tray holds it for 0.3 s
            raise PermissionError(13, u"The process cannot access the file", dst)
        return real(src, dst)

    monkeypatch.setattr(retries.os, "replace", held_for_a_moment)
    monkeypatch.setattr(retries.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    due = datetime(2026, 9, 23, 7, 4, tzinfo=timezone.utc)
    assert retries.save([due], target) == target, (
        u"the tries were spent inside one instant and the dates were dropped")
    assert now[0] >= 0.3 and retries.load(target) == [due.timestamp()]


def test_the_dates_file_is_read_again_when_a_run_rewrites_it(tmp_path, monkeypatch):
    u"""⚠ Read once a second, so it is cached on (mtime, size) -- and a cache that
    never lets go keeps the dates of the run BEFORE, for as long as the tray lives."""
    from hato import retries

    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    due = watch._DueFile()
    assert due() == [], u"no file is no dates"
    retries.save([u"2026-09-23T07:03:05+00:00"])
    first = due()
    assert len(first) == 1
    retries.save([u"2026-09-23T07:03:05+00:00", u"2026-09-24T07:03:05+00:00"])
    assert len(due()) == 2, u"a date a later run wrote down was never seen"
    retries.path().unlink()
    assert due() == [], u"a deleted file still answered with its old dates"


def test_the_tray_keeps_a_promise_a_run_wrote_down(tmp_path, monkeypatch):
    u"""⭐ THE WIRING, NOT THE LOGIC -- the policy above proves nothing if `main`
    never polls it. A date in the file is due mid-watch: exactly one more run.
    ⭐ And while a run holds the lock it WAITS for it (S01's lesson), then runs."""
    from hato import retries

    monkeypatch.setenv("HATO_CACHE", str(tmp_path / u"data"))
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / u"config.toml"))
    folder = tmp_path / u"A"
    folder.mkdir()
    now = [1000000.0]
    busy = [False]
    monkeypatch.setattr(watch, "wall_clock", lambda: now[0])
    monkeypatch.setattr(watch, "run_in_flight", lambda: busy[0])
    retries.save([u"1970-01-12T13:50:00+00:00"])          # epoch 1000200
    spawned, ticks = [], []

    class FakeWatcher(object):
        def __init__(self, folder, on_change, recurse=True):
            pass

        def start(self):
            return self

        def stop(self):
            pass

    class FakeCfg(object):
        folders = [str(folder)]
        skip_folders = []
        recurse = True

    class FakeTray(object):
        def __init__(self, *a, **k):
            pass

        def run(self, on_tick=None, on_error=None):
            on_tick()                                     # before the date
            ticks.append(len(spawned))
            now[0] = 1000200.0 + 301.0                    # past it, burst settled
            busy[0] = True                                # ...but a run holds the lock
            on_tick()
            ticks.append(len(spawned))
            busy[0] = False
            on_tick()
            on_tick()                                     # ⛔ and not twice
            ticks.append(len(spawned))
            return 0

    monkeypatch.setattr(watch, "DirectoryWatcher", FakeWatcher)
    monkeypatch.setattr(watch, "spawn_run", lambda folders, **k: spawned.append(list(folders)))
    monkeypatch.setattr(watch, "write_pid_file", lambda: None)
    monkeypatch.setattr(watch, "clear_pid_file", lambda: None)
    monkeypatch.setattr(watch, "clear_pending", lambda: None)
    monkeypatch.setattr("hato.config.load", lambda *a, **k: FakeCfg())
    monkeypatch.setattr("hato.tray.Tray", FakeTray)

    assert watch.main([]) == 0
    assert ticks == [1, 1, 2], (
        u"expected the catch-up run, NOTHING while a run held the lock, then ONE run "
        u"once it was free; runs seen at each tick: %s" % ticks)
    assert spawned[-1] == [str(folder)]


def test_a_busy_lock_holds_a_due_retry_without_spending_it():
    dues = [5000.0]
    clock, fired, retry = retry_clock(dues)
    busy = [True]
    retry.busy = lambda: busy[0]
    clock.now = 5400.0
    assert retry.poll() == [] and fired == [], u"it fired into a held lock"
    busy[0] = False
    assert retry.poll() == [5000.0], u"the date was spent while the lock was held"


# ---------------------------------------------------------------------------
# ⭐ ADVERSARY-2026-09-18 S01 and S02 -- two silent losses in the tray
# ---------------------------------------------------------------------------

class TrayWorld(object):
    u"""`watch.main()` against fakes: every watcher, spawn and pending write kept.

    ⚠ `SETTLE_SECONDS` is 0 here, so a touch is due at once and each tick is a
    decision -- the settle minute itself is the timer's own checks' business.
    """

    def __init__(self, tmp_path, monkeypatch, cfg):
        self.watchers, self.stopped, self.spawned, self.pending = [], [], [], []
        self.cfg, self.busy = [cfg], [False]
        self.config = tmp_path / u"config.toml"
        self.config.write_text(u"# one", encoding="utf-8")
        world = self

        class FakeWatcher(object):
            def __init__(self, folder, on_change, recurse=True):
                self.folder, self.on_change, self.recurse = folder, on_change, recurse
                world.watchers.append(self)

            def start(self):
                return self

            def stop(self):
                world.stopped.append(self.folder)

        monkeypatch.setenv("HATO_CACHE", str(tmp_path / u"data"))
        monkeypatch.setenv("HATO_CONFIG", str(self.config))
        monkeypatch.setattr(watch, "DirectoryWatcher", FakeWatcher)
        monkeypatch.setattr(watch, "spawn_run",
                            lambda folders, **k: world.spawned.append(list(folders)))
        monkeypatch.setattr(watch, "write_pid_file", lambda: None)
        monkeypatch.setattr(watch, "clear_pid_file", lambda: None)
        monkeypatch.setattr(watch, "clear_pending", lambda: None)
        monkeypatch.setattr(watch, "write_pending",
                            lambda due, names=(): world.pending.append(list(names)))
        monkeypatch.setattr(watch, "run_in_flight", lambda: world.busy[0])
        monkeypatch.setattr(watch, "SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("hato.config.load", lambda *a, **k: world.load())
        self.monkeypatch = monkeypatch

    def load(self):
        if isinstance(self.cfg[0], Exception):
            raise self.cfg[0]
        return self.cfg[0]

    def run(self, script):
        world = self

        class FakeTray(object):
            def __init__(self, tooltip, *a, **k):
                world.tooltips = [tooltip]
                world.items = list(k.get(u"items") or ())     # the menu, to click

            def set_tooltip(self, text):
                world.tooltips.append(text)

            def run(self, on_tick=None, on_error=None):
                world.on_error = on_error
                script(on_tick)
                return 0
        self.monkeypatch.setattr("hato.tray.Tray", FakeTray)
        return watch.main([])


def _cfg(folders, skip=()):
    class Cfg(object):
        pass
    cfg = Cfg()
    cfg.folders, cfg.skip_folders, cfg.recurse = [str(f) for f in folders], \
        [str(s) for s in skip], True
    return cfg


def test_a_video_arriving_during_a_run_waits_for_the_lock_instead_of_being_lost(
        tmp_path, monkeypatch):
    u"""🚨 S01. It used to clear the countdown and spawn into the held lock; the
    child scanned nothing and exited 0 into a pipe nobody reads, and a finished
    download raises no second event -- lost for ever."""
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    seen = []

    def script(tick):
        world.watchers[0].on_change(u"frieren S2 - 01.mkv")
        world.busy[0] = True
        announced = len(world.pending)
        tick()
        tick()
        seen.append(len(world.spawned))
        seen.append(len(world.pending) - announced)
        world.busy[0] = False
        tick()
        seen.append(len(world.spawned))

    assert world.run(script) == 0
    assert seen[0] == 1 and seen[2] == 2, (
        u"expected the catch-up run, NO run while the lock was held, then the "
        u"arrival's run once it was free -- runs seen: %s" % [seen[0], seen[2]])
    # ⚠ The arrival's OWN write names it too, so "the last write names it" could
    # never fail: each busy tick must say the wait again, or the countdown the
    # window reads has passed and the wait is invisible.
    assert seen[1] == 2 and world.pending[-1] == [u"frieren S2 - 01.mkv"], (
        u"the wait was not re-announced while it waited: %d write(s)" % seen[1])


def test_a_folder_added_in_settings_while_watching_is_watched(tmp_path, monkeypatch):
    u"""🚨 S02. The settings were read once, at start: a folder added later was
    never watched, and the window said "watching". ⭐ The new folder is watched,
    each watcher bound to ITS folder, the catch-up it is owed is run, and the
    NEW skip list is the one applied."""
    a, b = tmp_path / u"A", tmp_path / u"B"
    for folder in (a, b, b / u"Dragged In"):
        folder.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    out = {}

    def script(tick):
        tick()
        start = len(world.watchers)
        world.cfg[0] = _cfg([a, b], skip=[a / u"Old"])
        world.config.write_text(u"# two folders now, and a skip", encoding="utf-8")
        spawned = len(world.spawned)
        tick()
        # ⚠ READ INSIDE THE TRAY'S LIFE: `main()` stops every watcher on the
        # way out, so a list read after it returns always holds A -- green for
        # the wrong reason, which is how this check was first written.
        out[u"stopped"] = list(world.stopped)
        out[u"new"] = world.watchers[start:]
        out[u"caught_up"] = world.spawned[spawned:]
        by_folder = dict((w.folder, w) for w in out[u"new"])
        del world.pending[:]
        by_folder[str(a)].on_change(u"Old\\frieren - 01.mkv")
        out[u"skipped"] = list(world.pending)
        by_folder[str(b)].on_change(u"Dragged In")
        out[u"b_own"] = list(world.pending)
        del world.pending[:]
        by_folder[str(a)].on_change(u"Dragged In")
        out[u"a_not_b"] = list(world.pending)

    assert world.run(script) == 0
    assert [w.folder for w in out[u"new"]] == [str(a), str(b)], (
        u"the watchers did not follow the settings: %s" % [w.folder for w in out[u"new"]])
    assert out[u"stopped"] == [str(a)], (
        u"the old watchers were not stopped before new ones started: %s" % out[u"stopped"])
    assert out[u"caught_up"] == [[str(a), str(b)]], (
        u"a newly watched folder is owed the catch-up the start gets: %s"
        % out[u"caught_up"])
    assert out[u"skipped"] == [], (
        u"an arrival in a folder skipped since start still woke the tray -- the skip "
        u"list in use is the one read at start")
    assert out[u"b_own"] and u"Dragged In" in out[u"b_own"][-1], (
        u"B's watcher does not recognise a folder that exists only under B")
    assert out[u"a_not_b"] == [], u"A's watcher resolved names against B's folder"


def test_a_settings_file_that_will_not_read_changes_nothing(tmp_path, monkeypatch):
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    out = {}

    def script(tick):
        start = len(world.watchers)
        world.cfg[0] = ValueError(u"config.toml line 3: half-written")
        world.config.write_text(u"# mid-write", encoding="utf-8")
        tick()
        out[u"new"] = world.watchers[start:]
        out[u"stopped"] = list(world.stopped)      # ⚠ before `main()`'s own shutdown

    assert world.run(script) == 0
    assert out[u"new"] == [] and out[u"stopped"] == [], (
        u"a settings file that did not parse stopped the watching")


# ---------------------------------------------------------------------------
# ⭐ ADVERSARY 2026-09-22 -- the retry clock's edges, and the tray against the
# REAL settings reader (every check above fakes `config.load`, which is exactly
# how a deleted settings file stayed invisible to them)
# ---------------------------------------------------------------------------

def test_a_wall_clock_set_back_still_keeps_a_later_promise():
    u"""R5. The clock corrected two days back: every promise made after the jump
    sat at or below the mark the tray had already reached, and none was kept."""
    dues = []
    clock, fired, retry = retry_clock(dues)
    clock.now = 2000000.0
    retry.cover()                                     # the tray has been running
    clock.now -= 2 * 86400
    assert retry.poll() == []                         # ⚠ the next tick, a second later
    dues.append(clock.now + 86400)                    # a run promises +1 day, real time
    clock.now += 86400 + 1
    assert retry.poll() == [dues[0]] and fired == [[dues[0]]], (
        u"a promise made after the clock went back was never kept")


def test_a_chain_of_close_dates_holds_the_first_no_longer_than_the_window():
    u"""R6. Dates each a little under the coalescing window apart -- one long run's
    negatives -- held the first for 16 hours, waiting for the chain to end."""
    start = 1000000.0
    dues = [start + 1000 + i * 299.0 for i in range(200)]
    clock, fired, retry = retry_clock(dues, coalesce=300.0)
    clock.now = start
    while not fired and clock.now < start + 200000:
        clock.now += 1.0
        retry.poll()
    assert fired, u"no run at all"
    assert clock.now - dues[0] <= 300.0 + 1.0, (
        u"the first date was held %.1f hours" % ((clock.now - dues[0]) / 3600.0))


def test_the_same_file_problem_is_said_once_and_a_new_one_again(tmp_path, monkeypatch):
    u"""R8. A dates file holding something else read as "no dates" in silence."""
    from hato import retries
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    said = []
    due = watch._DueFile(complain=said.append)
    retries.path().write_text(u'{"due": {"x": 1}}', encoding="utf-8")
    assert due() == [] and len(said) == 1 and u"no list of dates" in said[0], said
    retries.path().write_text(u'{"due": {"y": 22}}', encoding="utf-8")   # another write, same fault
    assert due() == [] and len(said) == 1, u"the same fault was said again: %s" % said
    retries.path().write_text(u'{"due": [1000200]}', encoding="utf-8")
    assert due() == [] and len(said) == 2 and u"not a date" in said[1], said


def test_a_tick_that_raises_is_handed_on_and_never_ends_the_tray():
    u"""R7. One unreadable file raised out of the tick, out of the message loop,
    and the tray died on every start."""
    errors = []

    def boom():
        raise RecursionError(u"maximum recursion depth exceeded while decoding a JSON array")

    assert tray.tick_safely(boom, errors.append) is False
    assert [type(e).__name__ for e in errors] == [u"RecursionError"]
    assert tray.tick_safely(boom, lambda exc: 1 / 0) is False, u"a failing reporter raised"
    assert tray.tick_safely(lambda: None, errors.append) is True and len(errors) == 1


def test_the_tray_says_a_failing_tick_once_in_the_log(tmp_path, monkeypatch):
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))

    def script(tick):
        for _ in range(3):
            world.on_error(RuntimeError(u"the dates file is unreadable"))

    assert world.run(script) == 0
    log = (tmp_path / u"data" / u"hato.log").read_text(encoding="utf-8")
    assert log.count(u"the dates file is unreadable") == 1, log


def test_the_catch_up_owns_what_is_due_so_one_tick_starts_one_run(tmp_path, monkeypatch):
    u"""R10. An arrival settling and a promise coming due in the same second
    started TWO runs; the second met the first's lock."""
    from hato import retries
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    now = [1000000.0]
    monkeypatch.setattr(watch, "wall_clock", lambda: now[0])
    retries.save([u"1970-01-12T13:50:00+00:00"])          # epoch 1000200
    out = {}

    def script(tick):
        n = len(world.spawned)
        world.watchers[0].on_change(u"frieren S2 - 01.mkv")
        now[0] = 1000200.0 + 301.0
        tick()
        out[u"one"] = world.spawned[n:]
        tick()
        out[u"after"] = world.spawned[n:]

    assert world.run(script) == 0
    assert out[u"one"] == [[str(a)]] and out[u"after"] == [[str(a)]], (
        u"one tick, one second: %s run(s), then %s" % (out[u"one"], out[u"after"]))


from hato import config as _config_module  # noqa: E402 -- the REAL reader, kept before any patch
_REAL_LOAD = _config_module.load


class RealConfigWorld(TrayWorld):
    u"""`TrayWorld`, reading a REAL config.toml through the real `config.load` --
    the reader every fake above replaced, and the one a deleted file reaches."""

    def __init__(self, tmp_path, monkeypatch, folders, recurse=True):
        TrayWorld.__init__(self, tmp_path, monkeypatch, _cfg(folders))
        self.write(folders, recurse)

    def load(self):
        return _REAL_LOAD()

    def write(self, folders, recurse=True):
        import json
        self.config.write_text(u"folders = [%s]\nrecurse = %s\n" % (
            u", ".join(json.dumps(str(f)) for f in folders), u"true" if recurse else u"false"),
            encoding="utf-8")


@pytest.mark.parametrize("how", [u"deleted", u"emptied mid-save", u"no folders left"])
def test_a_settings_file_that_names_no_folder_keeps_the_tray_watching(tmp_path, monkeypatch, how):
    u"""C1, against the REAL reader. A deleted or zero-byte config.toml reads as
    the DEFAULTS -- no folders -- and every watcher stopped while the tooltip,
    the pid file and the window all went on saying *"watching"*; a due retry
    then fired a run over nothing."""
    from hato import retries
    a = tmp_path / u"A"
    a.mkdir()
    world = RealConfigWorld(tmp_path, monkeypatch, [a])
    now = [1000000.0]
    monkeypatch.setattr(watch, "wall_clock", lambda: now[0])
    retries.save([u"1970-01-12T13:50:00+00:00"])          # epoch 1000200
    out = {}

    def script(tick):
        tick()
        start = len(world.watchers)
        if how == u"deleted":
            world.config.unlink()
        elif how == u"emptied mid-save":
            world.config.write_bytes(b"")
        else:
            world.write([])
        tick()
        tick()
        out[u"stopped"], out[u"new"] = list(world.stopped), world.watchers[start:]
        n = len(world.spawned)
        now[0] = 1000200.0 + 301.0
        tick()
        out[u"spawned"] = world.spawned[n:]

    assert world.run(script) == 0
    assert out[u"stopped"] == [] and out[u"new"] == [], (
        u"a settings file %s stopped the watching: stopped %s" % (how, out[u"stopped"]))
    assert out[u"spawned"] == [[str(a)]], (
        u"the due retry ran over %s -- a run over nothing" % out[u"spawned"])
    log = (tmp_path / u"data" / u"hato.log").read_text(encoding="utf-8")
    assert log.count(u"name no folder to watch") == 1, log


def test_a_recurse_change_alone_is_applied(tmp_path, monkeypatch):
    u"""C2. Turning "include subfolders" on in Settings was never applied."""
    a = tmp_path / u"A"
    a.mkdir()
    world = RealConfigWorld(tmp_path, monkeypatch, [a], recurse=False)
    out = {}

    def script(tick):
        tick()
        start, n = len(world.watchers), len(world.spawned)
        world.write([a], recurse=True)
        tick()
        out[u"new"] = [(w.folder, w.recurse) for w in world.watchers[start:]]
        out[u"caught_up"] = world.spawned[n:]

    assert world.run(script) == 0
    assert out[u"new"] == [(str(a), True)], out[u"new"]
    assert out[u"caught_up"] == [[str(a)]], (
        u"subfolders watched from now on are owed the catch-up: %s" % out[u"caught_up"])


def test_a_change_saved_while_the_tray_starts_is_read(tmp_path, monkeypatch):
    u"""C3. The window's `hato config --set` landing between the tray's read of
    its settings and its first stamp matched that stamp, and was never read."""
    a, b = tmp_path / u"A", tmp_path / u"B"
    a.mkdir()
    b.mkdir()
    world = RealConfigWorld(tmp_path, monkeypatch, [a])
    first = {u"done": False}

    def starting(self):
        if not first[u"done"]:
            first[u"done"] = True
            time.sleep(0.05)
            world.write([a, b])                       # lands while the watchers start
        return self

    monkeypatch.setattr(watch.DirectoryWatcher, "start", starting)
    out = {}

    def script(tick):
        started = len(world.watchers)                 # A's, from the start
        tick()
        out[u"watched"] = sorted(w.folder for w in world.watchers[started:])

    assert world.run(script) == 0
    assert out[u"watched"] == sorted([str(a), str(b)]), (
        u"the settings on disk name A and B; after the change landed mid-start the tray "
        u"started watchers for %s" % out[u"watched"])


def test_a_watcher_that_dies_is_said_and_reopened_and_its_folder_caught_up(
        tmp_path, monkeypatch):
    u"""C4. A folder deleted, a share dropped: the watcher's thread ended with
    its error set, nobody read it, and nothing was ever watched there again."""
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    monkeypatch.setattr(watch, "REVIVE_SECONDS", 0)
    health = {u"up": True}
    out = {}

    def script(tick):
        for w in world.watchers:
            w.alive = lambda: health[u"up"]
            w.error = u"the folder is gone"
        n, started = len(world.spawned), len(world.watchers)
        health[u"up"] = False
        tick()
        tick()
        # ⚠ A NEW watcher for the folder, not "something was stopped": stopping
        # the dead one and never opening another passed the first version of
        # this check (M8zt-G06).
        out[u"reopened"] = [w.folder for w in world.watchers[started:]]
        for w in world.watchers:
            w.alive = lambda: health[u"up"]
        health[u"up"] = True
        tick()
        out[u"caught_up"] = world.spawned[n:]

    assert world.run(script) == 0
    log = (tmp_path / u"data" / u"hato.log").read_text(encoding="utf-8")
    assert log.count(u"stopped watching") == 1, log
    assert out[u"reopened"] == [str(a)], (
        u"a dead watcher was not reopened on its folder: %r" % out[u"reopened"])
    assert u"watching %s again" % a in log, log
    assert out[u"caught_up"] == [[str(a)]], (
        u"what arrived while it was down raised no event -- owed a catch-up: %s"
        % out[u"caught_up"])


def test_a_dead_watcher_is_reopened_once_per_interval_not_every_tick(tmp_path, monkeypatch):
    u"""C4's pace. A folder that stays gone -- a share that is down for the
    evening -- is tried again every `REVIVE_SECONDS`, not once a second: the
    check above sets the interval to 0, so it could not see the pace go."""
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    monkeypatch.setattr(watch, "REVIVE_SECONDS", 3600)
    out = {}

    def script(tick):
        started = len(world.watchers)
        for _ in range(3):
            for w in world.watchers:                      # the reopened ones die too
                w.alive = lambda: False
                w.error = u"the network share is down"
            tick()
        out[u"reopened"] = len(world.watchers) - started

    assert world.run(script) == 0
    assert out[u"reopened"] == 1, (
        u"a folder that stayed gone was reopened %d times in three ticks" % out[u"reopened"])


def test_a_change_saved_as_the_tray_reads_its_settings_is_read(tmp_path, monkeypatch):
    u"""C3, the order itself. The stamp is taken BEFORE the read, so a save that
    lands just after the read -- before anything is stamped -- still differs from
    it and is read on the first tick. ⚠ The check above lands its save later,
    while the watchers start, which the stamp sees in either order."""
    a, b = tmp_path / u"A", tmp_path / u"B"
    a.mkdir()
    b.mkdir()
    world = RealConfigWorld(tmp_path, monkeypatch, [a])
    reads = []

    def read_then_saved():
        cfg = _REAL_LOAD()
        if not reads:
            world.write([a, b])                           # lands right after the read
        reads.append(cfg)
        return cfg

    world.load = read_then_saved
    out = {}

    def script(tick):
        started = len(world.watchers)
        tick()
        out[u"watched"] = sorted(w.folder for w in world.watchers[started:])

    assert world.run(script) == 0
    assert out[u"watched"] == sorted([str(a), str(b)]), (
        u"a save landing just after the tray read its settings was never read: %r"
        % out[u"watched"])


def test_run_now_owns_the_dates_already_due(tmp_path, monkeypatch):
    u"""R10 through the MENU. *Run now* is a full run, so a promise already due
    is its -- or the retry clock starts a second run a second later, which meets
    the first one's lock. (The catch-up and the settle timer were covered; the
    menu item was a separate door.)"""
    from hato import retries
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    now = [1000000.0]
    monkeypatch.setattr(watch, "wall_clock", lambda: now[0])
    retries.save([u"1970-01-12T13:50:00+00:00"])          # epoch 1000200
    out = {}

    def script(tick):
        run_now = dict((item[0], item[1]) for item in world.items if item)[u"Run now"]
        now[0] = 1000300.0                               # the date has passed
        before = len(world.spawned)
        run_now()
        tick()
        tick()
        out[u"runs"] = len(world.spawned) - before

    assert world.run(script) == 0
    assert out[u"runs"] == 1, (
        u"Run now and a date it had already covered started %d runs" % out[u"runs"])


def test_a_save_no_rename_ever_lands_leaves_no_temp_behind(tmp_path, monkeypatch):
    u"""R9's other end: a reader that never lets go. The save gives up -- None, a
    run never fails over this -- and ⛔ leaves no `.new-` file for every run to
    add another beside."""
    from datetime import datetime, timezone
    from hato import retries
    target = tmp_path / u"retries-due.json"

    def held_for_ever(src, dst):
        raise PermissionError(13, u"The process cannot access the file", dst)

    monkeypatch.setattr(retries.os, "replace", held_for_ever)
    monkeypatch.setattr(retries.time, "sleep", lambda s: None)
    due = datetime(2026, 9, 23, 7, 4, tzinfo=timezone.utc)
    assert retries.save([due], target) is None
    assert not [p.name for p in tmp_path.iterdir() if u".new-" in p.name], (
        u"a save that could not land left its temp file: %s" % sorted(p.name for p in tmp_path.iterdir()))


def test_the_tray_hands_its_message_loop_the_error_reporter(monkeypatch):
    u"""R7's last link. `Tray.run` passes `on_error` to the loop -- every check
    above drives `pump` or a fake tray, so a `run` that dropped it would swallow
    every failing tick in silence and stay green."""
    if not sys.platform.startswith("win"):
        pytest.skip(u"the tray is Windows-only")
    icon = tray.Tray(u"hato")
    seen = {}
    monkeypatch.setattr(icon, "show", lambda: icon)
    monkeypatch.setattr(icon, "close", lambda: None)
    monkeypatch.setattr(icon, "pump", lambda on_tick=None, tick_ms=1000, on_error=None:
                        seen.update(on_tick=on_tick, on_error=on_error))

    def tick():
        pass

    def report(exc):
        pass

    icon.run(on_tick=tick, on_error=report)
    assert seen == {u"on_tick": tick, u"on_error": report}, seen


class _FakeDll(object):
    u"""A Win32 DLL that answers every call with success and records its name."""

    def __init__(self, **answers):
        self.calls, self._answers = [], answers

    def __getattr__(self, name):
        if name.startswith(u"_"):
            raise AttributeError(name)

        def call(*args):
            self.calls.append(name)
            return self._answers.get(name, 1)
        return call


def test_a_new_tooltip_is_handed_to_the_shell(monkeypatch):
    u"""C5's last link: `set_tooltip` must TELL the shell (NIM_MODIFY). Every check
    above records the text on a fake tray, so a tray that kept it to itself --
    the old count on hover, for ever -- stayed green."""
    if not sys.platform.startswith("win"):
        pytest.skip(u"the tray is Windows-only")
    icon = tray.Tray(u"hato -- watching 1 folder")
    shell = _FakeDll()
    icon._shell32, icon._data = shell, tray.NOTIFYICONDATAW()
    assert icon.set_tooltip(u"hato -- watching 2 folders") is True
    assert shell.calls == [u"Shell_NotifyIconW"] and \
        icon._data.szTip == u"hato -- watching 2 folders", (shell.calls, icon._data.szTip)


def test_showing_the_icon_asks_to_hear_when_the_taskbar_comes_back(monkeypatch):
    u"""S-a's first link: the re-add branch fires only on the message Explorer
    broadcasts, and only if `show()` asked for its number. The check above sets
    that number by hand, so a `show()` that never asked stayed green."""
    if not sys.platform.startswith("win"):
        pytest.skip(u"the tray is Windows-only")
    user32 = _FakeDll(RegisterWindowMessageW=49901)
    shell32, kernel32 = _FakeDll(), _FakeDll()
    monkeypatch.setattr(tray, "_dlls", lambda: (user32, shell32, kernel32))
    icon = tray.Tray(u"hato").show()
    assert u"RegisterWindowMessageW" in user32.calls and icon._taskbar_created == 49901, (
        user32.calls, icon._taskbar_created)


def test_the_real_watcher_of_a_folder_that_is_not_there_says_it_is_not_alive(tmp_path):
    if not sys.platform.startswith("win"):
        pytest.skip(u"the watcher is Windows-only")
    watcher = watch.DirectoryWatcher(str(tmp_path / u"not-there"), on_change=lambda n: None)
    watcher.start()
    deadline = time.time() + 5
    while watcher.alive() and time.time() < deadline:
        time.sleep(0.05)
    try:
        assert not watcher.alive() and watcher.error is not None
    finally:
        watcher.stop()
    live = watch.DirectoryWatcher(str(tmp_path), on_change=lambda n: None).start()
    try:
        time.sleep(0.2)
        assert live.alive(), u"the control: a watcher of a real folder is alive"
    finally:
        live.stop()
    assert not live.alive(), u"a stopped watcher still says it is watching"


def test_the_tooltip_follows_the_folders(tmp_path, monkeypatch):
    u"""C5. The tooltip said the folder count read at START."""
    a, b = tmp_path / u"A", tmp_path / u"B"
    a.mkdir()
    b.mkdir()
    world = RealConfigWorld(tmp_path, monkeypatch, [a])

    def script(tick):
        world.write([a, b])
        tick()

    assert world.run(script) == 0
    assert world.tooltips == [u"hato -- watching 1 folder", u"hato -- watching 2 folders"], (
        world.tooltips)


def test_the_pid_file_says_this_tray_keeps_promises_and_an_older_one_does_not(
        tmp_path, monkeypatch):
    u"""V1. A 1.0.1 tray writes the same pid file and keeps NO retry promise, so
    "a tray is running" is not "retrying in 14h"."""
    from hato import runlock
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    assert watch.watching_capabilities() is None, u"no tray, no capabilities"
    watch.write_pid_file()
    assert u"retries" in watch.watching_capabilities()
    stamp = runlock._process_start(os.getpid())
    watch.pid_file_path().write_text(u"%d %s" % (os.getpid(), stamp or u"-"), encoding="utf-8")
    assert watch.watching_capabilities() == frozenset(), (
        u"an older tray's pid file must read as keeping nothing")


def test_a_dates_file_the_tray_cannot_use_is_said_in_the_log(tmp_path, monkeypatch):
    u"""R8, the wiring: `main` hands the dates file's reader the tray's own
    complaint, so a file holding something else is SAID -- once."""
    from hato import retries
    a = tmp_path / u"A"
    a.mkdir()
    world = TrayWorld(tmp_path, monkeypatch, _cfg([a]))
    retries.path().parent.mkdir(parents=True, exist_ok=True)
    retries.path().write_text(u'{"due": {"not": "a list"}}', encoding="utf-8")

    def script(tick):
        tick()
        tick()

    assert world.run(script) == 0
    log = (tmp_path / u"data" / u"hato.log").read_text(encoding="utf-8")
    assert log.count(u"no list of dates") == 1, log


def test_a_lock_that_cannot_be_used_holds_every_run_and_is_said_once(tmp_path, monkeypatch):
    u"""L3. A folder sitting where the lock goes was "free" to the tray and fatal
    to every run it started, each failing into a stderr nobody reads."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path))
    from hato import paths
    paths.lock_path().mkdir(parents=True)
    monkeypatch.setattr(watch, "_LOCK_SAID", [None])
    assert watch.run_in_flight() is True and watch.run_in_flight() is True
    log = (tmp_path / u"hato.log").read_text(encoding="utf-8")
    assert log.count(u"cannot be used") == 1, log
    paths.lock_path().rmdir()
    assert watch.run_in_flight() is False, u"the control: with it gone, runs go"


def test_the_message_loop_survives_a_tick_that_raises(monkeypatch):
    u"""R7, the wiring: `pump` is where a tick's exception used to leave the
    loop. Driven with a message source that sends one timer tick, then quits."""
    if not sys.platform.startswith("win"):
        pytest.skip(u"the tray is Windows-only")
    icon = tray.Tray(u"hato")
    sent = [tray.WM_TIMER if hasattr(tray, "WM_TIMER") else 0x0113, None]

    class User32(object):
        class _Fn(object):
            def __init__(self, fn):
                self.fn = fn

            def __call__(self, *a):
                return self.fn(*a)

        def __init__(self):
            self.SetTimer = self._Fn(lambda *a: 1)
            self.KillTimer = self._Fn(lambda *a: 1)
            self.TranslateMessage = self._Fn(lambda *a: 1)
            self.DispatchMessageW = self._Fn(lambda *a: 0)

            def get(ref, *a):
                kind = sent.pop(0)
                if kind is None:
                    return 0                                  # WM_QUIT
                ref._obj.message = kind
                return 1
            self.GetMessageW = self._Fn(get)

    icon._user32, icon._hwnd = User32(), 1
    errors = []

    def boom():
        raise RecursionError(u"maximum recursion depth exceeded")

    try:
        icon.pump(on_tick=boom, on_error=errors.append)
    except RecursionError:
        pytest.fail(u"a tick that raised took the tray's message loop down")
    assert [type(e).__name__ for e in errors] == [u"RecursionError"]


def test_a_new_taskbar_gets_the_icon_again(monkeypatch):
    u"""Explorer restarted -- a crash, an update -- and the new taskbar had no
    icon: the tray watched on, invisible, with no way to open or stop it.
    (ADVERSARY 2026-09-22, suspected.) ⚠ Only the dispatch is checked here; a
    real Explorer restart is a thing to LOOK at."""
    if not sys.platform.startswith("win"):
        pytest.skip(u"the tray is Windows-only")
    icon = tray.Tray(u"hato")
    calls = []

    class Shell(object):
        def Shell_NotifyIconW(self, what, data):
            calls.append(what)
            return 1

    icon._shell32, icon._user32 = Shell(), None
    icon._data = tray.NOTIFYICONDATAW()
    icon._taskbar_created = 0xC123
    assert icon._on_message(None, 0xC123, 0, 0) == 0
    assert calls == [tray.NIM_ADD], calls


def test_the_tray_process_never_loads_a_toolkit_or_the_pipeline_all_its_life(tmp_path):
    u"""I1. The import check above reads THIS file's import lines -- one level. A
    `from hato import pipeline` inside `config.py` passes it, and the tray is
    30 MB instead of 13. ⭐ Here every call the tray makes in its life is made,
    in a fresh interpreter, and what got loaded is read back."""
    script = tmp_path / u"life.py"
    script.write_text(u"""
import os, sys, tempfile
store = tempfile.mkdtemp()
folder = os.path.join(store, "Anime")
os.makedirs(folder)
with open(os.path.join(store, "config.toml"), "w", encoding="utf-8") as fh:
    fh.write("folders = [%r]\\n" % folder)
os.environ.update(HATO_CACHE=os.path.join(store, "data"),
                  HATO_CONFIG=os.path.join(store, "config.toml"))
before = set(sys.modules)
from hato import watch, config, tray, runlock, retries
config.load()
watch.watching_pid(); watch.write_pid_file(); watch.watching_capabilities()
watch.should_wake(u"frieren - 01.mkv", folder, [os.path.join(folder, "Raw")])
watch.run_in_flight(); watch._DueFile()(); watch.RetryClock().poll()
watch.write_pending(0, [u"x.mkv"]); watch.read_pending(); watch.clear_pending()
watch.spawn_run([folder], spawner=lambda argv, env: None)
watch._ico_path(); watch.no_console_kwargs(); watch.gui_spawn_kwargs()
watch.complain(u"life\\n"); watch.clear_pid_file()
tray.menu_commands([(u"a", None)]); tray.tick_safely(lambda: None)
heavy = sorted(m for m in set(sys.modules) - before
               if m.split(".")[0] in ("PyQt6", "PySide6", "tkinter", "tsubasa", "numpy",
                                      "guessit", "requests")
               or m.startswith(("hato.pipeline", "hato.gui", "hato.client", "hato.state")))
print("HEAVY=" + ",".join(heavy))
""", encoding="utf-8")
    from hato import paths
    proc = subprocess.run([sys.executable, str(script)], env=paths.child_env(),
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    line = [l for l in proc.stdout.splitlines() if l.startswith(u"HEAVY=")]
    assert proc.returncode == 0 and line, (proc.returncode, proc.stdout, proc.stderr)
    assert line[0] == u"HEAVY=", (
        u"the tray's life loaded %s -- a toolkit or the pipeline in the 13 MB process"
        % line[0][len(u"HEAVY="):])
