# -*- coding: utf-8 -*-
u"""
The tray watcher. RUNBOOK 7f.

    python -m hato.watch              watch config.toml's folders
    python -m hato.watch --once D:\\A  watch one folder, print instead of running

===========================================================================
🚨 THIS IS A SEPARATE PROCESS FROM THE WINDOW, AND THE NUMBER IS WHY
===========================================================================

Sonic: *"it needs to be SO SO SO small in memory while it watches. As in I
want it to take basically 0 resources if possible. so basically in the tray
and also so so small so it takes up basically nothing so it can sit there but
also be useful."*

Measured (`gui-mock/MEMORY.md`, RSS via psutil, this machine, Python 3.10.0):

    bare python -- the interpreter alone            12.7 MB
    + a real watch handle and buffer (ctypes)       13.4 MB
    + the tray and window APIs resolved as well     13.4 MB
    PyQt6 QApplication + QSystemTrayIcon            30.6 MB

⭐ **The watching costs 0.7 MB. Everything else is Python itself** -- that is
the floor, not something to tune. So the watcher must NOT be the window: a
resident Qt tray is 2.3x the cost, and every megabyte of it is a toolkit doing
nothing while nobody is looking.

⛔ **NEVER import a GUI toolkit here. NEVER import `hato.pipeline`.** The tray
icon is `ctypes` over shell32, and the run is a SUBPROCESS -- so hato's own
pipeline is only ever in memory while a run is actually happening, and it
exits on its own.

⚠ `hato.config` IS imported, deliberately. ⛔ "Never write a second reader" is
the same rule as "never write a second filename parser": the schema, the
refusals and the path rules live in one module and a watcher with its own idea
of `folders` is two programs disagreeing about one file.

===========================================================================
🚨 EVERY ctypes FUNCTION DECLARES argtypes AND EVERY RETURN IS CHECKED
===========================================================================

`gui-mock/MEMORY.md` records the measurement that made this a rule: a
hand-rolled `GetProcessMemoryInfo` was called **without `argtypes`**, so the
pointer was mis-marshalled, the call wrote nothing into the struct, and the
zeroed struct printed as `0.0 MB` -- which was read as *"basically 0
resources"*, exactly the answer being hoped for. ⛔ **An instrument that fails
towards the answer you want.** Declaring `argtypes` and checking the return
turned `0.0` into `13.84` on the first try.

===========================================================================
⚠ THE SETTLE DELAY EARNS ITS KEEP TWICE
===========================================================================

Sonic ruled **1 minute**. It debounces a burst of filesystem events into one
run -- and it is also what lets a still-downloading file finish before hato
opens it.

⚠ **Say the seasonal caveat plainly wherever this is offered:** for a season
still airing, the subtitle is published hours to days after the episode, so a
run fired on arrival finds nothing **and** records a miss that holds the retry
until tomorrow. For a finished show it works.

⛔ **OFF BY DEFAULT.** Watching needs something resident; with it off, nothing
of hato is in memory between runs.
"""
from __future__ import print_function

import json
import os
import subprocess
import sys
import threading
import time

#: Sonic's ruling. Seconds of quiet after the last change before hato runs.
SETTLE_SECONDS = 60.0

#: Video extensions worth waking for. ⚠ A subtitle landing beside a video is
#: not a reason to run -- that is usually hato's OWN output, and reacting to it
#: is how a watcher spins.
VIDEO_SUFFIXES = (u".mkv", u".mp4", u".avi", u".m4v", u".mov", u".webm",
                  u".ts", u".m2ts", u".wmv", u".flv", u".ogm", u".mpg",
                  u".mpeg", u".rmvb", u".asf", u".divx")


def is_interesting(name):
    u"""Is this filename worth waking hato for? -> bool

    ⚠ THERE WAS A LIST OF DOWNLOAD SUFFIXES HERE AND IT CAUGHT NOTHING.
    Removed 2026-09-18 after mutant M7f-03 SURVIVED. Every partial-download
    marker a downloader writes -- `.part`, `.crdownload`, `.!ut`, `.!qB`,
    `.aria2`, `.tmp` -- is appended AFTER the extension, so the video-suffix
    test below already rejects all of them. Measured, not reasoned: the list
    did not include `.!qB` or `.aria2` and those were rejected too, which is
    the tell that the suffix check was doing the whole job and the list was
    a false sense of coverage.

    ⭐ AND THE THING IT CLAIMED TO PROTECT AGAINST IS PROTECTED ELSEWHERE. A
    downloader that writes the FINAL name and grows the file in place defeats
    any name-based test, and always did. What handles that is `SettleTimer` --
    one minute of quiet after the last write, which is Sonic's ruling and the
    reason he gave for it.

    ⛔ hato's own `<video>.ja.ass` output is rejected here too, and that one is
    load-bearing: waking for the subtitle hato just wrote is how a watcher
    spins, every run triggering the next.
    """
    return name.lower().endswith(VIDEO_SUFFIXES)


def is_interesting_arrival(name, root=None, isdir=None):
    u"""Is this notification worth waking hato for, name OR folder? -> bool

    ⭐ A FOLDER DRAGGED IN REPORTS ONCE, UNDER ITS OWN NAME. Sonic,
    2026-09-18: *"i just moved another folder with filess in a folder into the
    folder and it doesn't see it ... The auto watcher sees it when I copy the
    files themselves into the main folder. And when i hit run it catches
    them."* All three halves of that report are one cause.

    🚨 THIS IS A PROPERTY OF THE OPERATING SYSTEM, NOT OF THE FILTER. Moving a
    directory inside one volume is a single rename: Windows reports the
    DIRECTORY and says nothing about the files under it, because none of them
    were touched. ⛔ `bWatchSubtree` does not help -- there is nothing further
    to report. A cross-volume COPY is the opposite case and always worked,
    because every file is genuinely created and each video fires
    `is_interesting` on its own. That asymmetry is the whole bug report.

    ⛔ So the name-only test is right for files and BLIND for folders, and the
    blindness is total -- no timer touch, no pending record, nothing drawn.
    Sonic: *"Still sits idle. doesn't even show that it saw it."* ⚠ An
    invisible miss is indistinguishable from a broken feature, which is the
    second time that exact sentence has been earned on this watcher.

    ⚠ `isdir` is injected so this is checkable with no filesystem at all, and
    the probe runs ONLY for a name the suffix test already rejected -- one
    `stat` on events hato was about to throw away, never on the hot path.

    ⭐ hato's own `<video>.ja.ass` output stays rejected, and that is still
    load-bearing: it is a file, so the probe answers False and the watcher
    cannot spin on its own output.
    """
    if not name:
        return False
    if is_interesting(name):
        return True
    if root is None:
        return False
    probe = os.path.isdir if isdir is None else isdir
    try:
        return bool(probe(os.path.join(root, name)))
    except (OSError, ValueError):
        # ⚠ A name that raced its own deletion, or one this filesystem will
        # not even let us ask about. Not a reason to wake, not a reason to die.
        return False


class SettleTimer(object):
    u"""Collapse a burst of changes into one run, once things go quiet.

    ⭐ THE WHOLE POLICY OF THE WATCHER LIVES HERE, AND IT TAKES A CLOCK. The
    Win32 half below is thin and needs a real filesystem; this is where the
    decisions are, so this is what the suite drives -- with a fake clock, so a
    check about a 60-second delay does not take 60 seconds.

        timer = SettleTimer(60.0, clock=fake.time, fire=runs.append)
        timer.touch("a.mkv"); fake.advance(59); timer.poll()   # nothing yet
        fake.advance(2);      timer.poll()                     # -> fires once
    """

    def __init__(self, settle=SETTLE_SECONDS, clock=time.monotonic, fire=None):
        self.settle = float(settle)
        self.clock = clock
        self.fire = fire
        self._due = None
        self._pending = []
        self._lock = threading.Lock()

    @property
    def waiting(self):
        with self._lock:
            return list(self._pending)

    def touch(self, name=None):
        u"""A change arrived. ⭐ RESETS the countdown -- it is quiet we are
        waiting for, not elapsed time since the first event. A season copied in
        over ten minutes is ONE run, not ten."""
        with self._lock:
            self._due = self.clock() + self.settle
            if name is not None and name not in self._pending:
                self._pending.append(name)

    def poll(self):
        u"""Call often. -> the names it fired for, or [] if it is not time.

        ⚠ THE PENDING LIST IS CLEARED BEFORE `fire` RUNS, not after. A run
        takes minutes, and a change arriving DURING it must start a fresh
        countdown rather than be swallowed by the batch already in flight.
        """
        with self._lock:
            if self._due is None or self.clock() < self._due:
                return []
            names, self._pending, self._due = self._pending, [], None
        if self.fire is not None:
            self.fire(names)
        return names


def run_argv():
    u"""How to run hato from here. -> [str]

    ⚠ The same three-host problem `hato/gui/run.py` solves, and for the same
    reason -- but ⛔ NOT imported from there: that module is the WINDOW's, and
    importing it would drag the window's dependencies into the 13 MB process
    this file exists to keep small.
    """
    override = os.environ.get("HATO_CLI")
    if override:
        return [override]
    if getattr(sys, u"frozen", False):
        # 🚨 `hato-cli.exe`, NOT `hato.exe` -- see `gui/run.py::cli_argv`.
        # Sonic ruled 2026-09-18 that `hato.exe` is THE WINDOW, the one thing
        # a person clicks. ⛔ Spawning it here would open a window instead of
        # running a scan, which is the opposite of what a tray watcher wants.
        return [os.path.join(os.path.dirname(sys.executable),
                             u"hato-cli.exe" if sys.platform.startswith("win")
                             else u"hato-cli")]
    return [sys.executable, u"-m", u"hato"]


def watch_argv():
    u"""How to START a watcher from somewhere else. -> [str]

    ⭐ HERE, NOT IN THE WINDOW. The three-host problem (source, frozen, an
    override) is this module's own knowledge, and the window had a hand-rolled
    version of it that was simply WRONG when frozen: it reduced to whatever
    `run_argv` returns -- the COMMAND LINE -- so turning the tray on would have
    run a scan and exited instead of leaving anything in the tray.

    ⚠ The three frozen names, since they are easy to get the wrong way round
    (ruled by Sonic 2026-09-18):

        hato.exe        THE WINDOW -- the one thing a person clicks
        hato-cli.exe    the command line, spawned for every run
        hato-watch.exe  this, the resident tray watcher
    """
    argv = run_argv()
    if len(argv) == 1:                        # frozen: a sibling exe
        return [os.path.join(os.path.dirname(argv[0]),
                             u"hato-watch.exe"
                             if sys.platform.startswith("win")
                             else u"hato-watch")]
    return [argv[0], u"-m", u"hato.watch"]


def gui_spawn_kwargs():
    u"""Popen keywords for starting a WINDOW. -> dict

    🚨 NOT `no_console_kwargs`, AND THE DIFFERENCE IS THE WHOLE BUG. Sonic,
    twice: *"it's in the tray but can't see the UI. both the tray click and
    hato shortcut doesn't work."*

    ⭐ `STARTF_USESHOWWINDOW` WITH `wShowWindow` LEFT AT ITS DEFAULT IS
    `SW_HIDE`. Windows hands that to the new process as the `nCmdShow` for its
    FIRST window, and Qt honours it -- so the window was created as a real
    native window and never shown. Measured in a controlled pair, 2026-09-18:
    with those keywords **0 visible windows**, without them **1**.

    ⚠ IT ONLY EVER HAPPENED FROM THE TRAY, which is why it looked haunted: a
    shortcut goes through Explorer, which passes `SW_SHOWNORMAL`. And the
    invisible window then HOLDS the single-instance name, so the shortcut stops
    working too -- one cause, both symptoms.

    ⛔ `CREATE_NO_WINDOW` is kept: it suppresses a CONSOLE, which a GUI has no
    use for, and it does not touch the window's own visibility.
    """
    if not sys.platform.startswith("win"):
        return {}
    startupinfo = subprocess.STARTUPINFO()
    # 🚨 `SW_SHOWNORMAL` EXPLICITLY, and that is the whole point. Using
    # STARTF_USESHOWWINDOW with `wShowWindow` left at its default means
    # SW_HIDE, which is what made a tray-opened window build itself, go native,
    # and never appear. Naming the value is what makes this safe to keep.
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 1                       # SW_SHOWNORMAL
    # ⭐ And no "application starting" pointer for a window the person just
    # asked for -- see `hato/gui/run.py`'s note.
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_FORCEOFFFEEDBACK", 0x80)
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            "startupinfo": startupinfo}


def no_console_kwargs():
    u"""⛔ A tray process has no console, so each child would allocate one and
    flash it over whatever the person is doing. -> dict

    ⚠ FOR A CONSOLE CHILD ONLY -- see `gui_spawn_kwargs`. Passing these to a
    GUI child hides its window.
    """
    if not sys.platform.startswith("win"):
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    # 🚨 SET IT ON PURPOSE. `wShowWindow` defaults to 0, which IS `SW_HIDE` --
    # correct here and catastrophic for a window, and that silent default cost
    # two rounds on `open_window`. ⛔ Leaving it implicit is how the next person
    # copies this function into a GUI spawn and loses the same two rounds.
    startupinfo.wShowWindow = 0                                     # SW_HIDE
    # ⭐ AND NO BUSY CURSOR ON THE AUTOMATIC PATH EITHER. Sonic, 2026-09-18:
    # *"if it has the cursor think when it downloads, it shouldn't."* The flag
    # went into the window's spawner and `gui_spawn_kwargs` and was reported as
    # *"both spawn paths"* -- ⛔ THERE WERE THREE, and this is the one the TRAY
    # uses, so it is the one nearly every real download goes through. Found by
    # the adversarial pass, 2026-09-18 (F-C01).
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_FORCEOFFFEEDBACK", 0x80)
    return {"creationflags": flags, "startupinfo": startupinfo}


def spawn_run(folders, spawner=None):
    u"""Start a hato run over `folders`, detached. -> the Popen, or None.

    ⛔ NOT WAITED ON, and nothing is read back. The watcher's whole job is to
    be small and asleep; holding pipes open for a run that takes minutes would
    make it the parent of the thing it was supposed to avoid being.
    ⚠ hato's own run lock handles two runs meeting -- the second exits 0 saying
    nothing was scanned, which is the documented behaviour and not an error.
    """
    if not folders:
        return None
    from hato import paths as _paths
    argv = run_argv() + [u"--quiet"] + [os.path.abspath(f) for f in folders]
    # ⛔ `paths.child_env`, never a local copy. The copy that used to be here
    # omitted PYTHONPATH, so a tray started from a shortcut spawned a run that
    # died on `ModuleNotFoundError` before it printed anything.
    env = _paths.child_env()
    if spawner is not None:                 # the suite's seam
        return spawner(argv, env)
    return subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **no_console_kwargs())


# ---------------------------------------------------------------------------
# the Win32 half -- thin, and every call checked
# ---------------------------------------------------------------------------

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = -1

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
FILE_NOTIFY_CHANGE_SIZE = 0x00000008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

WATCH_FLAGS = (FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME |
               FILE_NOTIFY_CHANGE_SIZE | FILE_NOTIFY_CHANGE_LAST_WRITE)

#: ⭐ 64 KiB, and it is the documented ceiling rather than a guess: the buffer
#: for ReadDirectoryChangesW on a network path may not exceed 64 KB, and the
#: call fails outright above it. Overflow is not fatal -- the call returns zero
#: bytes and we treat that as "something changed, we do not know what", which
#: is exactly enough to start the settle timer.
BUFFER_BYTES = 64 * 1024


def _kernel32():
    u"""-> the DLL with every function's argtypes declared, or raise.

    🚨 `argtypes` ON EVERY ONE. Without them ctypes guesses at marshalling, and
    a 64-bit HANDLE silently truncated to a C int is the shape of the
    `GetProcessMemoryInfo` failure that rendered total failure as `0.0 MB`.
    """
    import ctypes
    from ctypes import wintypes

    dll = ctypes.WinDLL("kernel32", use_last_error=True)

    dll.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    dll.CreateFileW.restype = wintypes.HANDLE

    dll.ReadDirectoryChangesW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ctypes.c_void_p]
    dll.ReadDirectoryChangesW.restype = wintypes.BOOL

    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL

    dll.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    dll.CancelIoEx.restype = wintypes.BOOL

    return dll, ctypes, wintypes


def parse_notifications(buffer, nbytes):
    u"""The FILE_NOTIFY_INFORMATION chain -> [filename].

    ⭐ TAKES BYTES AND RETURNS NAMES, so it needs no Windows and no handle --
    which is what lets the trap below be a check on every platform rather than
    a Windows-only one that never runs on CI.

    ⚠ `FileNameLength` IS IN BYTES AND THE NAME IS UTF-16. Reading it as a
    character count takes half the name, which silently turns every
    `frieren S2 - 01.mkv` into `frieren S` and makes `is_interesting` false for
    every file there is -- a watcher that never fires, with nothing in any log.
    """
    out = []
    offset = 0
    while True:
        if offset + 12 > nbytes:
            break
        next_entry = int.from_bytes(buffer[offset:offset + 4], "little")
        name_bytes = int.from_bytes(buffer[offset + 8:offset + 12], "little")
        start = offset + 12
        raw = bytes(buffer[start:start + name_bytes])
        try:
            out.append(raw.decode("utf-16-le"))
        except UnicodeDecodeError:
            pass                            # ⚠ a truncated tail, not a reason to stop
        if not next_entry:
            break
        offset += next_entry
    return out


class DirectoryWatcher(object):
    u"""One folder, watched on its own thread. Windows only.

    ⚠ `ReadDirectoryChangesW` BLOCKS until something changes, and that is the
    design: waiting costs nothing, and the 0.7 MB the watching costs is the
    handle and the buffer. ⛔ It is the MEASUREMENT script that must not block
    -- `gui-mock/MEMORY.md` records a first attempt that called this
    synchronously in a child whose only job was to report its own RSS, and
    every child sat for ever having measured nothing.
    """

    def __init__(self, folder, on_change, recurse=True):
        self.folder = os.path.abspath(folder)
        self.on_change = on_change
        self.recurse = recurse
        self._stop = threading.Event()
        self._thread = None
        self._handle = None
        self.error = None

    def start(self):
        if not sys.platform.startswith("win"):
            raise RuntimeError(
                "hato's watcher uses ReadDirectoryChangesW and is Windows-only. "
                "On another platform, run hato from cron or a systemd timer "
                "instead -- a scheduled run scans the folders and finds "
                "whatever is new.")
        self._thread = threading.Thread(target=self._loop, name="hato-watch")
        self._thread.daemon = True
        self._thread.start()
        return self

    def _loop(self):
        dll, ctypes, wintypes = _kernel32()
        handle = dll.CreateFileW(
            self.folder, FILE_LIST_DIRECTORY,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
        # 🚨 CHECKED. An unopenable folder -- renamed, unplugged, permission
        # denied -- would otherwise be an invalid handle passed to every later
        # call, each failing silently, and a watcher that reports nothing for
        # ever while looking exactly like one with nothing to report.
        if handle == INVALID_HANDLE_VALUE or handle is None:
            self.error = ctypes.WinError(ctypes.get_last_error())
            return
        self._handle = handle
        buffer = ctypes.create_string_buffer(BUFFER_BYTES)
        returned = wintypes.DWORD(0)
        try:
            while not self._stop.is_set():
                ok = dll.ReadDirectoryChangesW(
                    handle, buffer, BUFFER_BYTES, bool(self.recurse),
                    WATCH_FLAGS, ctypes.byref(returned), None, None)
                if self._stop.is_set():
                    return
                if not ok:
                    self.error = ctypes.WinError(ctypes.get_last_error())
                    return
                if returned.value == 0:
                    # ⚠ BUFFER OVERFLOW, not "nothing happened". Too many
                    # changes to describe -- which is still a change, and the
                    # settle timer needs no detail to do its job.
                    self.on_change(None)
                    continue
                for name in parse_notifications(buffer, returned.value):
                    self.on_change(name)
        finally:
            dll.CloseHandle(handle)
            self._handle = None

    def stop(self):
        u"""⚠ `CancelIoEx` AS WELL AS THE FLAG. The thread is parked inside a
        blocking call and will not look at an Event until something changes --
        so without cancelling the I/O, a watcher on a quiet folder never exits
        and the tray icon outlives its process."""
        self._stop.set()
        handle = self._handle
        if handle is not None:
            try:
                dll, ctypes, _ = _kernel32()
                dll.CancelIoEx(handle, None)
            except Exception:               # noqa: BLE001 -- shutting down anyway
                pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# the program
# ---------------------------------------------------------------------------

def open_window():
    u"""Start the window as its OWN process. -> the Popen, or None.

    ⛔ NOT `from hato.gui import main`. Importing the window here would load Qt
    into the watcher and take it from 13.4 MB to 30.6 -- permanently, for the
    whole time it sits in the tray, which is the one thing this module exists
    to avoid. A check asserts this file imports no toolkit; spawning is how the
    tray can still open a window without becoming one.
    """
    argv = run_argv()
    if len(argv) == 1:                        # frozen: the window sits beside
        # ⭐ `hato.exe` IS THE WINDOW. Sonic, 2026-09-18: *"i want it to be
        # hato as the main one ... i can just click on hato.exe and it will
        # handle everything else."* The command line is `hato-cli.exe`, which
        # is what `run_argv` above returns -- so this takes its FOLDER and
        # names the window.
        exe = os.path.join(os.path.dirname(argv[0]),
                           u"hato.exe" if sys.platform.startswith("win")
                           else u"hato")
        argv = [exe]
    else:
        argv = [argv[0], u"-m", u"hato.gui"]
    from hato import paths as _paths
    # 🚨 THE ENVIRONMENT IS WHY THIS DID NOTHING FOR A WHOLE ROUND. See
    # `paths.child_env` -- the copy that lived here had no PYTHONPATH.
    try:
        # ⛔ `gui_spawn_kwargs`, NEVER `no_console_kwargs`. The latter carries
        # STARTF_USESHOWWINDOW with wShowWindow = SW_HIDE, which Windows hands
        # to the child as the nCmdShow for its FIRST window -- so the window
        # was built, native, and never shown. Measured; see that function.
        return subprocess.Popen(argv, env=_paths.child_env(),
                                **gui_spawn_kwargs())
    except OSError:
        return None                           # ⛔ a tray that cannot open a
                                              # window is still a working tray


def complain(message):
    u"""Report a refusal where somebody can actually find it. -> None

    🚨 A DETACHED `pythonw.exe` HAS NO STANDARD STREAMS AT ALL. Measured on
    this machine 2026-09-18: started from a Windows Run key -- or by any
    hidden, handle-less launch -- **both `sys.stdout` and `sys.stderr` are
    `None`**, and `sys.stderr.write(...)` raises `AttributeError`.

    ⛔ THAT MADE *"Start with Windows"* CRASH AT EVERY LOGIN, on the most
    ordinary first-run order there is: switch it on, have not added a folder
    yet, and `main()` tries to say *"no folder to watch"* and dies saying it.
    No console, nothing in the tray, no exit code anybody sees -- the exact
    failure shape `packaging/entry_watch.py` states the rule against, broken
    four times in one function.

    ⭐ SO THE LOG IS THE CHANNEL, NOT THE STREAM. It is the durable record and
    it is what this project's own scheduling advice already points people at:
    *"read hato's own log, never the scheduler's result code."* The stream is
    written too, when there is one.

    ⚠ NOTHING HERE MAY RAISE. A reporter that can fail is a second way to die
    while explaining the first.
    """
    try:
        stream = sys.stderr
        if stream is not None:
            stream.write(message)
            stream.flush()
    except Exception:                         # noqa: BLE001
        pass
    try:
        from hato import paths as _paths
        path = _paths.default_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(path), "a", encoding="utf-8") as handle:
            handle.write(u"=== hato watcher %s ===\n%s"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:                         # noqa: BLE001
        pass


def main(argv=None):
    u"""`python -m hato.watch` -- sit in the tray and run hato when a video
    lands. -> an exit code.

    ⛔ OFF BY DEFAULT is a SETTINGS decision, not this module's: reaching this
    function means somebody asked for it. What is enforced here is that it
    costs what it was measured to cost.
    """
    from hato import config as _config        # ⚠ the ONE reader, never a second
    from hato import tray as _tray

    # 🚨 ONE WATCHER, AND ONLY ONE. Sonic, 2026-09-18: *"it's an issue if we
    # have multiple hato in the tray."* It is worse than untidy: two watchers
    # on one folder both fire on the same file, and the two runs then race for
    # hato's run lock -- so one of them reports that nothing was scanned, every
    # time, for ever.
    # ⭐ The pid file already knows, and it knows HONESTLY: `watching_pid`
    # checks the pid AND its creation stamp, so a tray killed by a reboot or
    # Task Manager leaves a file that does not count as a running watcher.
    # ⚠ `HATO_ALLOW_MANY=1` is the way round it, because Sonic asked for one:
    # *"during testing it could be useful to have more."*
    existing = watching_pid()
    if existing and not os.environ.get("HATO_ALLOW_MANY"):
        complain(
            u"hato: already watching (pid %d). Only one tray watcher runs at a "
            u"time -- two would both fire on the same file and then race each "
            u"other for the run lock. Use its tray menu to stop it, or set "
            u"HATO_ALLOW_MANY=1 if you are deliberately testing.\n" % existing)
        return 0                              # ⛔ NOT a failure: the job is done
    try:
        cfg = _config.load()
    except Exception as exc:                  # noqa: BLE001
        complain(u"hato: the watcher could not read its settings -- "
                 u"%s\n" % exc)
        return 2
    # ⭐ `paths.under_any`, the SAME function the pipeline uses -- not a copy.
    # ⛔ Importing `hato.pipeline` here to reach it would undo the entire reason
    # this is a separate process, so the shared answer lives in `paths`, which
    # imports nothing but the stdlib.
    from hato import paths as _paths
    folders = [f for f in cfg.folders
               if not _paths.under_any(f, cfg.skip_folders)]
    if not folders:
        complain(
            u"hato: no folder to watch. Add one in Settings, or in "
            u"config.toml's `folders`.\n")
        return 2

    def go(names):
        # ⭐ The wait is over, so stop advertising it BEFORE the run starts --
        # otherwise the window shows a countdown and a running run at once.
        clear_pending()
        return spawn_run(folders)

    timer = SettleTimer(SETTLE_SECONDS, fire=go)

    def arrived(name, root=None):
        u"""Something landed. ⚠ Only reset the countdown for real work.

        ⭐ `root` is the folder THIS watcher owns. Without it a notification is
        a bare relative name, and a folder dragged in cannot be told from a
        file worth ignoring -- see `is_interesting_arrival`.
        """
        if name is not None and not is_interesting_arrival(name, root):
            return
        timer.touch(name)
        # 🚨 WALL CLOCK ON THE WIRE, MONOTONIC IN THE TIMER. `SettleTimer` runs
        # on `time.monotonic`, which is meaningless in another process -- so
        # what gets written down is *now + whatever is left*, in ordinary time.
        # ⛔ Writing the monotonic value would give the window a countdown
        # measured from that machine's boot.
        write_pending(time.time() + SETTLE_SECONDS,
                      [n for n in timer.waiting if n])
    watchers = []
    for folder in folders:
        watcher = DirectoryWatcher(
            folder,
            # ⭐ BOUND PER FOLDER. `arrived` needs this watcher's root to tell a
            # dragged-in FOLDER from a file worth ignoring. ⛔ The default
            # argument is what binds THIS folder -- a bare closure over `folder`
            # would hand every watcher the last one in the loop.
            on_change=lambda name, root=folder: arrived(name, root),
            recurse=cfg.recurse)
        try:
            watchers.append(watcher.start())
        except RuntimeError as exc:
            complain(u"hato: %s\n" % exc)
            return 2

    # ⚠ AFTER the folders are known and the watchers are up -- a pid file
    # written before that would advertise a watcher that then exits, and the
    # window would show "watching" for a process that is already gone.
    write_pid_file()

    # 🚨 ONE CATCH-UP RUN THE MOMENT WATCHING STARTS. Sonic, 2026-09-18:
    # *"video is there and setting is checked, but the auto-finder isn't doing
    # it. It works when i run it though."*
    #
    # ⭐ THE WATCHER WAS RIGHT AND THE DESIGN WAS INCOMPLETE. A filesystem
    # watcher fires on CHANGES; his video had been sitting in the folder for
    # twelve days, so there was nothing to react to -- measured from its
    # timestamp. Nothing was broken, and nothing was going to happen either.
    #
    # ⛔ *"Watch for new videos and run"* is a promise about new arrivals, and
    # a person who ticks it plainly means *"and deal with what is already
    # here."* Watching alone makes turning it on do nothing at all until the
    # next download, which is indistinguishable from a broken feature -- and
    # was reported as one.
    #
    # ⚠ It costs what a scheduled run costs, and no more: an episode that
    # already has a Japanese subtitle is skipped before any request, and a show
    # already identified is free.
    spawn_run(folders)

    icon = _tray.Tray(
        u"hato -- watching %d folder%s" % (len(folders),
                                           u"" if len(folders) == 1 else u"s"),
        icon_path=_ico_path(),
        items=[(u"Open hato", open_window),
               (u"Run now", lambda: spawn_run(folders)),
               None,
               (u"Stop watching", None)],
        on_activate=open_window)
    try:
        icon.run(on_tick=timer.poll)
    finally:
        for watcher in watchers:
            watcher.stop()
        # ⛔ A tray that has gone must not leave a countdown behind: the window
        # would show a run coming that nothing will ever start.
        clear_pending()
        clear_pid_file()
    return 0


# ---------------------------------------------------------------------------
# is one already watching?
# ---------------------------------------------------------------------------
# ⭐ REUSED, NOT RE-DERIVED. `hato/runlock.py` already solves "is the process
# that wrote this file still running" with the pid AND its creation stamp --
# because a pid is recycled, and a night-old pid can belong to some other
# program by morning. ⛔ Writing a second answer here is this project's single
# most expensive documented habit.

def pid_file_path():
    u"""-> the file a running watcher records itself in."""
    from hato import paths
    return paths.data_root() / u"watch.pid"


def watching_pid():
    u"""-> the pid of the watcher that is actually running, or None.

    ⚠ A STALE FILE IS NOT A RUNNING WATCHER. A tray process killed by a reboot,
    Task Manager or a crash leaves its file behind, and a window that believed
    it would refuse to start one for ever -- the toggle would look on and
    nothing would be watching.
    """
    from hato import runlock
    try:
        raw = pid_file_path().read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    try:
        pid = int(raw[0])
    except ValueError:
        return None
    stamp = raw[1] if len(raw) > 1 else None
    # 🚨 COMPARED AS TEXT ON BOTH SIDES, and this was a real defect until
    # 2026-09-18. `runlock._process_start` returns an OPAQUE creation stamp --
    # an integer on Windows -- and a file can only hold text. Handing the
    # string straight to `_process_alive` compared `int != str`, which is true
    # for every live process, so **every watcher read as dead**: single-instance
    # could never fire and the window's toggle-off could never find the one it
    # was meant to stop. Caught by the positive half of the check; the negative
    # half was green throughout, because "not running" was the only answer it
    # ever gave.
    # 🚨 AND "NOT RUNNING" WAS NARROWER THAN IT LOOKED. `_process_start` folds
    # FOUR outcomes into one `None`: "gone", "exited", "denied", and a process
    # that IS running whose creation time could not be read. ⛔ The other half
    # of this project's liveness logic, `runlock._process_alive`, takes the
    # OPPOSITE view of the last two -- so the same pid read dead here and alive
    # there. Two functions disagreeing about whether a process exists is how
    # single-instance stops refusing and two watchers end up in the tray.
    #
    # ⚠ Found by the adversarial pass, 2026-09-18 (F-B09): the earlier stamp
    # fix closed the INSTANCE of this bug, not the CLASS. A process we are not
    # allowed to inspect is still a process.
    state, created = runlock._query(pid)
    if state in ("gone", "exited"):
        return None                          # genuinely not running
    if state == "running" and created is not None \
            and stamp and stamp != u"-" and str(created) != stamp:
        return None                          # the pid belongs to something else now
    return pid


def write_pid_file():
    u"""Record this process as the watcher. -> the path, or None."""
    from hato import runlock
    path = pid_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = runlock._process_start(os.getpid())
        temp = path.with_name(path.name + ".new-%d" % os.getpid())
        temp.write_text(u"%d %s" % (os.getpid(), stamp or u"-"),
                        encoding="utf-8")
        os.replace(str(temp), str(path))     # ⛔ never truncate-in-place
        return path
    except OSError:
        return None                          # ⛔ not a reason to refuse to watch


def clear_pid_file():
    u"""⚠ Best effort. A file left behind is handled by `watching_pid`."""
    try:
        pid_file_path().unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# ⭐ the pending run, so the WAIT is visible
# ---------------------------------------------------------------------------
# 🚨 SONIC, 2026-09-18: *"I don't think the auto fetch works if its in a
# folder."* It worked -- measured end to end. What he hit was the SETTLE
# MINUTE, during which nothing anywhere said a run was coming.
#
# ⭐ AN INVISIBLE WAIT IS INDISTINGUISHABLE FROM BROKEN. The delay is right and
# is his own ruling; what was missing is that it was silent. The watcher writes
# down when the run is due and the window reads it -- the same shape as the
# last-run memory, and for the same reason: two processes that were never meant
# to know about each other, one file between them.

def pending_path():
    u"""-> the file naming when a settling run is due."""
    from hato import paths
    return paths.data_root() / u"watch-pending.json"


def write_pending(due_at, names=()):
    u"""Say a run is coming, and when. -> the path, or None."""
    path = pending_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + u".new-%d" % os.getpid())
        temp.write_text(
            json.dumps({u"due_at": float(due_at), u"names": list(names)[:20]}),
            encoding="utf-8")
        os.replace(str(temp), str(path))     # ⛔ never truncate in place
        return path
    except (OSError, TypeError, ValueError):
        return None                          # ⛔ never a reason not to watch


def clear_pending():
    u"""The run has started (or been abandoned). ⚠ Best effort."""
    try:
        pending_path().unlink()
    except OSError:
        pass


def read_pending():
    u"""-> (seconds_remaining, names). `(0.0, [])` when nothing is coming.

    ⛔ NEVER RAISES, and a stale file reads as nothing: a tray killed mid-wait
    would otherwise leave the window counting down for ever to a run that will
    never happen.
    """
    try:
        payload = json.loads(pending_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0, []
    if not isinstance(payload, dict):
        return 0.0, []
    try:
        left = float(payload.get(u"due_at") or 0.0) - time.time()
    except (TypeError, ValueError):
        return 0.0, []
    if left <= 0:
        return 0.0, []
    names = payload.get(u"names")
    return left, list(names) if isinstance(names, list) else []


def _ico_path():
    u"""-> the tray icon, or None. ⛔ Resolved WITHOUT importing the gui
    package, which would pull Qt in through its `__init__`."""
    try:
        import hato
        path = os.path.join(os.path.dirname(os.path.abspath(hato.__file__)),
                            u"data", u"hato.ico")
        return path if os.path.isfile(path) else None
    except Exception:                         # noqa: BLE001
        return None


__all__ = ["BUFFER_BYTES", "SETTLE_SECONDS", "VIDEO_SUFFIXES",
           "DirectoryWatcher", "SettleTimer", "clear_pid_file",
           "clear_pending", "gui_spawn_kwargs",
           "is_interesting", "is_interesting_arrival",
           "main", "no_console_kwargs", "open_window",
           "pending_path", "read_pending", "write_pending",
           "parse_notifications", "pid_file_path", "run_argv", "spawn_run",
           "watch_argv", "watching_pid", "write_pid_file"]


if __name__ == "__main__":                    # pragma: no cover
    sys.exit(main())
