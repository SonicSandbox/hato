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

        def run(self, on_tick=None):
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

@pytest.mark.parametrize("module", ["watch", "tray"])
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
