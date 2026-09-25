# -*- coding: utf-8 -*-
u"""The swapper -- RUNBOOK 11d. Frozen ONEFILE as `hato-update.exe`.

    hato-update.exe --pending <pending.json> [--quiet]

⭐ THE NEW VERSION'S OWN COPY RUNS, and from OUTSIDE the program folder: the apply
step copies it out of the staged payload into the staging root. So a fix to the
swapper travels with the release that needs it -- surasura's `updater.exe` could
never update itself -- and it never holds a file it has to move.

Every path it touches is in `pending.json` (`hato.update.stage`): it knows nothing
about where hato keeps anything.

THE ORDER, and what each step's failure does:

  1. every staged entry is there                  else: touch nothing
  2. EVERY process whose program file lives in the install folder has exited --
     the window that handed off, the tray, a run -- within 60 s. Measured
     2026-09-24: `_internal` cannot be renamed while the window OR the tray runs,
     and the window starts the tray itself
                                                  else: touch nothing, start hato again
  3. hato's entries -> previous\\<from>, the staged ones -> in place: RENAMES on one
     volume, instant and atomic each. ⛔ Only the entries pending names move; a
     person's own file in that folder never does
  4. each new file's sha256 is the manifest's, and the new `hato-cli.exe` RUNS and
     says it is `to` -- the only proof an install with nothing to restart gets
  5. the tray again if it was running, the window if it was the window that asked
  6. the window VISIBLE within 20 s. ⛔ LEDGER-HOT: never ask whether a spawn
     SURVIVED -- ask for what a person would see. ⭐ The splash (hato/splash.py)
     goes the moment it shows, not after the settle: a card above everything must
     never sit over the window a person is looking at
                       any failure in 3-6: stop what this started, rename everything
                       back, start the old hato, and say so in result.json
  7. result.json; the staging leftovers removed

⚠ NOT COVERED: the swapper killed DURING the renames (step 3, milliseconds) leaves
the folder half-swapped and pending.json behind. Every other moment is safe: before
3 nothing has moved, after it the new version is complete.

⛔ STDLIB + CTYPES ONLY. It must work when everything else is broken, and a static
check (tests/test_swap.py) holds it to that, as the tray's does.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

#: Seconds. Generous: a run finishing its last video, a slow disk, a cold start.
WAIT_FOR_EXIT = 60.0
WAIT_FOR_WINDOW = 20.0
#: A new window must still be running this long after it first shows.
WINDOW_SETTLE = 3.0
#: hato's window's own title (`HatoWindow`: `setWindowTitle(u"hato")`). ⛔ The proof
#: is a visible window with THIS title: a crash dialog is visible too.
WINDOW_TITLE = u"hato"
WAIT_FOR_TRAY = 15.0
#: With no pid file named to read, a tray still up after this long has started.
TRAY_SETTLE = 3.0
POLL = 0.25

SUCCESS, FAILED = u"success", u"failed"


class SwapError(Exception):
    u"""A step failed after something moved. `str()` is a person's sentence."""


# ---------------------------------------------------------------------------
# the operating system, behind one object -- the checks hand in their own
# ---------------------------------------------------------------------------

class WinOps(object):
    u"""What the swapper asks of Windows: which processes run from a folder, start
    one, is its window on screen, stop one. ctypes only."""

    def _kernel(self):
        import ctypes
        return ctypes.WinDLL("kernel32", use_last_error=True)

    def _pids(self):
        import ctypes
        from ctypes import wintypes

        class ENTRY(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", wintypes.WCHAR * 260)]

        k = self._kernel()
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        snap = k.CreateToolhelp32Snapshot(0x2, 0)        # TH32CS_SNAPPROCESS
        if not snap or snap == wintypes.HANDLE(-1).value:
            return []
        out = []
        try:
            entry = ENTRY()
            entry.dwSize = ctypes.sizeof(ENTRY)
            more = k.Process32FirstW(snap, ctypes.byref(entry))
            while more:
                out.append(int(entry.th32ProcessID))
                more = k.Process32NextW(snap, ctypes.byref(entry))
        finally:
            k.CloseHandle(snap)
        return out

    def image(self, pid):
        u"""-> the full path of `pid`'s program file, or None."""
        import ctypes
        from ctypes import wintypes
        k = self._kernel()
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
        handle = k.OpenProcess(0x1000, False, pid)       # QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if not k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return None
            return buf.value
        finally:
            k.CloseHandle(handle)

    def processes_in(self, folder):
        u"""-> the pids whose program file lives inside `folder`.

        ⚠ ONE FOLDER HAS SEVERAL SPELLINGS. A process started through a short
        (8.3) path reports its image that way, and TEMP is often short-form -- so
        the folder is compared as given AND resolved, and an image carrying a `~`
        is resolved too. A miss here is not harmless: it reads as "nothing runs"
        and the renames then meet locked files."""
        if not sys.platform.startswith("win"):
            return []
        prefixes = set(os.path.normcase(p) + os.sep for p in (
            os.path.abspath(folder), os.path.realpath(folder)))
        mine = os.getpid()
        out = []
        for pid in self._pids():
            if pid in (0, mine):
                continue
            path = self.image(pid)
            if not path:
                continue
            names = set([os.path.normcase(path)])
            if u"~" in path:
                names.add(os.path.normcase(os.path.realpath(path)))
            if any(name.startswith(prefix) for name in names for prefix in prefixes):
                out.append(pid)
        return out

    def start(self, path):
        u"""-> the started process. Its own group, so this process ending never
        takes it along; no console, since both of hato's are windowed programs."""
        return subprocess.Popen([path], cwd=os.path.dirname(path), close_fds=True,
                                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))

    def window_visible(self, pid, title=None):
        u"""True when `pid` owns a VISIBLE top-level window -- titled `title` when
        one is named.

        🚨 THE TITLE IS NOT DECORATION. A new version that dies at start shows the
        freezer's *"Unhandled exception"* dialog: a visible window, owned by that
        process -- and without the title it read as the new window, opened."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        found = []
        CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def each(hwnd, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                if title is None:
                    found.append(hwnd)
                else:
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    if buf.value == title:
                        found.append(hwnd)
            return True

        user32.EnumWindows(CALLBACK(each), 0)
        return bool(found)

    def version(self, path):
        u"""-> the version `<path> --version` reports ('X.Y.Z'), or None. No console:
        a console program started from a windowless one flashes a window."""
        try:
            done = subprocess.run([path, u"--version"], capture_output=True, timeout=60,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return None
        match = re.search(r"hato (\d+\.\d+\.\d+)", done.stdout.decode("utf-8", "replace"))
        return match.group(1) if match else None

    def stop(self, process):
        try:
            if process.poll() is None:
                process.terminate()
                process.wait(10)
        except Exception:                     # noqa: BLE001 -- best effort
            pass

    def stop_pid(self, pid):
        u"""End a process this swap did not start -- only ever one running from the
        install folder being put back (`_swap_or_undo`). ⛔ Best effort."""
        k = self._kernel()
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k.OpenProcess(0x0001, False, pid)           # PROCESS_TERMINATE
        if handle:
            try:
                k.TerminateProcess(handle, 1)
            finally:
                k.CloseHandle(handle)


# ---------------------------------------------------------------------------
# the steps
# ---------------------------------------------------------------------------

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(root, path):
    root, path = os.path.abspath(root), os.path.abspath(path)
    return path == root or path.startswith(root + os.sep)


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.lexists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def wait_gone(install, ops, timeout, clock=time.monotonic, sleep=time.sleep):
    u"""True once nothing runs from `install`; False when `timeout` passes first."""
    deadline = clock() + timeout
    while True:
        if not ops.processes_in(install):
            return True
        if clock() >= deadline:
            return False
        sleep(POLL)


def _clear_older(previous, staged):
    u"""ONE previous version is kept (ruled 2026-09-24): the ones before it go --
    ⛔ never the folder being swapped IN, which for *Go back* lives in there."""
    parent = os.path.dirname(os.path.abspath(previous))
    try:
        names = os.listdir(parent)
    except OSError:
        return                                # none kept yet -- or unreadable: keep them
    for name in names:
        path = os.path.join(parent, name)
        if _inside(path, staged) or _inside(staged, path):
            continue
        _remove(path)


def _swap(pending, moves):
    u"""Step 3 -- the renames. Each done move is recorded for the undo."""
    install, staged, previous = pending[u"install"], pending[u"staged"], pending[u"previous"]
    os.makedirs(previous, exist_ok=True)
    for name in pending[u"old_entries"]:
        source = os.path.join(install, name)
        if os.path.lexists(source):
            os.rename(source, os.path.join(previous, name))
            moves.append((source, os.path.join(previous, name)))
    for name in pending[u"entries"]:
        target = os.path.join(install, name)
        os.rename(os.path.join(staged, name), target)
        moves.append((os.path.join(staged, name), target))


def _verify(pending):
    u"""Step 4 -- each new file is the manifest's, byte for byte."""
    for name, digest in pending[u"entries"].items():
        if digest and sha256(os.path.join(pending[u"install"], name)) != digest:
            raise SwapError(u"%s is not the file the release names" % name)


def _reports(pending, ops):
    u"""Step 4, its second half -- the new program RUNS and says it is `to`.

    ⭐ The one proof an install with nothing to restart gets (the 03:00 run with
    watching off), and the cheapest failure there is: nothing has been started, so
    nothing needs stopping before the renames go back."""
    cli = os.path.join(pending[u"install"], u"hato-cli.exe")
    if u"hato-cli.exe" not in pending[u"entries"]:
        return
    said = ops.version(cli)
    if said != pending.get(u"to"):
        raise SwapError(u"the new version did not start (it said %s)" % (said or u"nothing"))


def _undo(moves):
    u"""Every recorded move, reversed, newest first. -> the moves that FAILED."""
    stuck = []
    for source, target in reversed(moves):
        try:
            os.rename(target, source)
        except OSError:
            stuck.append(target)
    return stuck


def _relaunch(pending, ops, started=None, clock=time.monotonic, sleep=time.sleep):
    u"""Step 5 -- the tray again if it ran, and ONLY ONCE IT HAS SAID IT IS WATCHING,
    the window if it asked. -> `started`, {role: process}; the tray's verdict is
    `_start_tray`'s, for the caller that needs it.

    🚨 IN THAT ORDER, AND WAITED FOR (the seam review S3; ADVERSARY 2026-09-24 C):
    the window's own start-up starts a tray whenever watching is on, guarded only by
    the tray's pid file -- which a tray writes a moment AFTER it starts. Started back
    to back, both trays passed the guard: two watchers, or this tray's proof failed,
    everything was put back, and the WINDOW's tray -- started by nothing this knows
    of -- kept `_internal` locked, so the undo could not move it.
    ⚠ Each is recorded AS IT STARTS: a window that fails to start after the tray did
    must still leave the tray findable, or the way back would wait a minute on a
    tray that holds `_internal` and then fail to move it."""
    started = {} if started is None else started
    if pending.get(u"tray"):
        _start_tray(pending, ops, started, clock, sleep)
    if pending.get(u"window"):
        started[u"window"] = ops.start(os.path.join(pending[u"install"], u"hato.exe"))
    return started


def _start_tray(pending, ops, started, clock=time.monotonic, sleep=time.sleep):
    u"""Start the tray and wait until it SAYS it is watching. -> None, or the reason
    it did not. ⭐ Its own record of itself (`watch.write_pid_file`), when the hand-off
    names it -- written only once it really watches, and only one written AFTER this
    start counts (B3: a stale file whose pid Windows gave to the new tray is not proof)."""
    marker = pending.get(u"tray_pid_file")
    since = time.time()
    tray = started[u"tray"] = ops.start(os.path.join(pending[u"install"], u"hato-watch.exe"))
    deadline = clock() + (WAIT_FOR_TRAY if marker else TRAY_SETTLE)
    while True:
        if tray.poll() is not None:
            return u"the new version's tray closed as it started"
        if marker and _names_pid(marker, tray.pid, since):
            return None
        if clock() >= deadline:
            return u"the new version's tray never said it was watching" if marker else None
        sleep(POLL)


def _quietly(call, *args):
    u"""-> call(*args), or None if it raised. For the steps of a way OUT: none of
    them may stop the next, and none may make `apply` raise."""
    try:
        return call(*args)
    except Exception:                         # noqa: BLE001
        return None


def _restart(pending, ops, clock=time.monotonic, sleep=time.sleep):
    u"""hato again, on a way out -- the tray first, as `_relaunch` always does.
    ⛔ Never raises. -> True when it started."""
    return _quietly(_relaunch, pending, ops, None, clock, sleep) is not None


def _proven(pending, ops, started, clock, sleep, seen=None):
    u"""Step 6 -- what a person would see. -> None, or the reason it is not so.
    `seen()` is called the moment the new window is first on screen. ⚠ The tray was
    proven BEFORE the window started (`_start_tray`); it is asked again here only to
    still be alive."""
    tray, window = started.get(u"tray"), started.get(u"window")
    if window is not None:
        deadline = clock() + WAIT_FOR_WINDOW
        while not ops.window_visible(window.pid, WINDOW_TITLE):
            if window.poll() is not None:
                return u"the new version closed as it opened"
            if clock() >= deadline:
                return u"the new version did not open a window"
            sleep(POLL)
        if seen is not None:
            _quietly(seen)
        # ⭐ AND IT STAYS. A window that opens and dies a second later -- an error
        # at start-up -- is a failed update too. ⚠ Alive, not VISIBLE, for the
        # settle: a person may minimise it the moment it appears.
        settle = clock() + WINDOW_SETTLE
        while clock() < settle:
            code = window.poll()
            if code is not None:
                # ⭐ A PERSON MAY CLOSE IT THE MOMENT IT APPEARS (ADVERSARY 2026-09-24,
                # C7): that is hato working, and it was put back as a failure. Only
                # an exit that is not a clean one is: a crash, `qFatal`'s 0xC0000409.
                return None if code == 0 else u"the new version closed as it opened"
            sleep(POLL)
    if tray is not None and tray.poll() is not None:
        return u"the new version's tray closed as it started"
    return None


def _names_pid(path, pid, since=None):
    u"""True when the tray's pid file names `pid` first (`<pid> <stamp> <caps>`) --
    and, given `since` (wall clock), was written no earlier: a file left from BEFORE
    the start, whose pid Windows has since handed out again, is not proof (B3).
    ⚠ Two seconds of slack: a FAT volume stamps files to the even second."""
    try:
        if since is not None and os.path.getmtime(path) < since - 2.0:
            return False
        with open(path, encoding="utf-8") as handle:
            return handle.read().split()[0] == str(pid)
    except (OSError, IndexError):
        return False


#: ⛔ A plain name -- the manifest's own rule (`update._ENTRY`), held AGAIN here: the
#: swapper re-trusted a locally written pending.json with no wall of its own, and
#: an entry `..\\..\\x` landed outside the install (ADVERSARY 2026-09-24, B1).
_ENTRY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}\Z")


def _strictly_inside(root, path):
    root, path = os.path.abspath(root), os.path.abspath(path)
    return path.startswith(root + os.sep)


def _uncontained(pending, root):
    u"""-> why this hand-off reaches outside what a swap may touch, or None: every
    entry a plain name, the staged and kept folders inside the staging root, and
    that root and the install apart. (`result` and `log` are held by `run`.)"""
    for name in list(pending[u"entries"]) + list(pending[u"old_entries"]):
        if not isinstance(name, str) or not _ENTRY.match(name) or name in (u".", u".."):
            return u"%r is not an entry of hato's folder" % (name,)
    if root is None:
        return None
    for key in (u"staged", u"previous"):
        if not _strictly_inside(root, pending[key]):
            return u"its %s folder is not in the staging folder" % key
    if _inside(root, pending[u"install"]) or _inside(pending[u"install"], root):
        return u"the install and the staging folder overlap"
    return None


#: What the hand-off must carry, and in what shape -- `update.stage` writes it.
_REQUIRED = ((u"install", str), (u"staged", str), (u"previous", str), (u"entries", dict),
             (u"old_entries", list))


def apply(pending, ops=None, clock=time.monotonic, sleep=time.sleep, seen=None,
          root=None):
    u"""The whole swap -> a result dict. ⛔ Never raises. `seen()`: the new window
    is on screen (the splash closes on it). `root`: the staging folder the hand-off
    lives in -- every folder it names must be inside it (B1)."""
    ops = WinOps() if ops is None else ops
    pending = pending if isinstance(pending, dict) else {}
    base = {u"from": pending.get(u"from"), u"to": pending.get(u"to"),
            u"at": time.strftime(u"%Y-%m-%dT%H:%M:%S"),
            u"going_back": bool(pending.get(u"going_back"))}

    def result(status, reason, touched, restarted=True):
        out = dict(base)
        if not restarted:
            reason += u" -- and hato could not be started again"
        out.update(status=status, reason=reason, touched=touched)
        return out

    bad = [key for key, kind in _REQUIRED if not isinstance(pending.get(key), kind)]
    if bad:
        return result(FAILED, u"the hand-off is incomplete (%s)" % u", ".join(bad), False)
    try:
        outside = _uncontained(pending, root)
    except Exception:                         # noqa: BLE001 -- a shape it cannot read
        outside = u"unreadable"
    if outside is not None:
        # ⛔ NOTHING STARTED either: a hand-off that reaches outside hato's folders is
        # not one hato wrote, and its `install` is no place to start programs from
        return result(FAILED, u"the hand-off reaches outside hato's folders (%s), so "
                      u"nothing was changed" % outside, False)
    install, staged = pending[u"install"], pending[u"staged"]
    try:
        # ⚠ WAIT FIRST, even for a refusal: the window closed itself to hand off, so
        # hato is started again on EVERY way out -- and only once the old one is
        # gone, or its single-instance guard would raise a window that is closing.
        if not wait_gone(install, ops, WAIT_FOR_EXIT, clock, sleep):
            return result(FAILED, u"hato was still running, so nothing was changed", False,
                          _restart(pending, ops, clock, sleep))
        missing = [name for name in pending[u"entries"]
                   if not os.path.lexists(os.path.join(staged, name))]
        if missing:
            return result(FAILED, u"the new version is incomplete (%s)" % u", ".join(missing),
                          False, _restart(pending, ops, clock, sleep))
        _clear_older(pending[u"previous"], staged)
    except Exception as exc:                  # noqa: BLE001 -- nothing has moved yet
        return result(FAILED, u"the update stopped before changing anything (%s)"
                      % type(exc).__name__, False, _restart(pending, ops, clock, sleep))
    return _swap_or_undo(pending, ops, clock, sleep, result, seen)


def _swap_or_undo(pending, ops, clock, sleep, result, seen=None):
    u"""Steps 3-6, and the way back from any of them."""
    moves, started = [], {}
    try:
        _swap(pending, moves)
        _verify(pending)
        _reports(pending, ops)
        if pending.get(u"tray"):
            why = _start_tray(pending, ops, started, clock, sleep)
            if why:
                raise SwapError(why)
        if pending.get(u"window"):
            started[u"window"] = ops.start(os.path.join(pending[u"install"], u"hato.exe"))
        why = _proven(pending, ops, started, clock, sleep, seen)
        if why:
            raise SwapError(why)
    except Exception as exc:                  # noqa: BLE001 -- every failure puts hato back
        for process in started.values():
            _quietly(ops.stop, process)
        # ⛔ AND ANYTHING ELSE the new version started from its folder -- the window's
        # own tray, the tray's catch-up run: one left holding `_internal` makes the
        # undo fail half way (the seam review, S3).
        for pid in _quietly(ops.processes_in, pending[u"install"]) or ():
            _quietly(ops.stop_pid, pid)
        _quietly(wait_gone, pending[u"install"], ops, WAIT_FOR_EXIT, clock, sleep)
        stuck = _undo(moves)
        reason = exc.args[0] if isinstance(exc, SwapError) and exc.args else (
            u"a file could not be moved (%s)" % type(exc).__name__)
        if stuck:
            reason += u" -- and %d file(s) could not be put back" % len(stuck)
        return result(FAILED, reason, bool(moves), _restart(pending, ops, clock, sleep))
    return result(SUCCESS, u"ok", True)


def write_result(path, result):
    u"""Temp-plus-rename. ⛔ Never raises: the result is a report, not the work."""
    try:
        temp = path + u".new"
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        os.replace(temp, path)
    except Exception:                         # noqa: BLE001
        pass


def write_log(path, result):
    u"""The result in hato.log as well -- the window's *put back* line says what
    happened is written there, and an install nobody watched (the tray's, at night)
    has no other record. ⭐ `watch.complain`'s block shape, `=== hato update … ===`.
    ⛔ Never raises."""
    # ⛔ B1: appended to, so only ever a file NAMED hato.log -- never whatever a
    # hand-off happens to name
    if not isinstance(path, str) or os.path.basename(path).lower() != u"hato.log":
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(u"=== hato update %s ===\nhato %s -> %s: %s -- %s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"), result.get(u"from"), result.get(u"to"),
                result.get(u"status"), result.get(u"reason")))
    except Exception:                         # noqa: BLE001
        pass


def run(pending_path, quiet=False, ops=None, clock=time.monotonic, sleep=time.sleep):
    u"""Read the hand-off, do the swap, write the result, tidy. -> exit code."""
    try:
        with open(pending_path, encoding="utf-8") as handle:
            pending = json.load(handle)
    except (OSError, ValueError):
        return 2
    if not isinstance(pending, dict):
        return 2
    root = os.path.dirname(os.path.abspath(pending_path))
    result_path = pending.get(u"result")
    # ⛔ B1: it is REMOVED below -- a `result` outside the staging folder is not one
    # hato wrote, and deleting it would delete whatever it names.
    if not isinstance(result_path, str) or not _strictly_inside(root, result_path):
        result_path = pending_path + u".result"
    # 🚨 THE RESULT FILE IS THIS SWAP'S. MEASURED BY THE REHEARSAL, 2026-09-24: a
    # failed swap's result -- never read, because the version put back was one with
    # no window to read it -- was shown by the NEXT swap's new window as
    # "didn't finish", and the success written seconds later was never seen.
    try:
        os.remove(result_path)
    except OSError:
        pass
    splash = None if quiet else _splash(pending)
    try:
        result = apply(pending, ops, clock, sleep,
                       seen=None if splash is None else splash.close, root=root)
    finally:
        if splash is not None:
            _quietly(splash.close)
    write_result(result_path, result)
    write_log(pending.get(u"log"), result)
    if result[u"status"] == SUCCESS:
        _tidy(os.path.dirname(os.path.abspath(pending_path)), pending[u"staged"])
    try:
        os.remove(pending_path)
    except OSError:
        pass
    return 0 if result[u"status"] == SUCCESS else 1


def _tidy(root, staged):
    u"""After a swap, the folder swapped IN holds nothing of hato's: remove it, then
    its parent only if that is now EMPTY. ⛔ Both strictly inside the staging root --
    and ⛔ never the parent wholesale: for *Go back* the folder swapped in lives among
    the kept versions, beside the one this swap just kept."""
    root, staged = os.path.abspath(root), os.path.abspath(staged)
    if staged == root or not _inside(root, staged):
        return
    _remove(staged)
    parent = os.path.dirname(staged)
    if parent != root and _inside(root, parent):
        try:
            os.rmdir(parent)                  # only ever removes an EMPTY folder
        except OSError:
            pass


def _splash(pending):
    u"""The native splash (11e). ⛔ A splash that cannot be drawn never stops the
    update -- it is the one part of this that is decoration."""
    try:
        from hato import splash
        return splash.show(pending.get(u"to") or u"", bool(pending.get(u"going_back")))
    except Exception:                         # noqa: BLE001
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hato-update")
    parser.add_argument("--pending", required=True)
    parser.add_argument("--quiet", action="store_true",
                        help="no splash: nobody is watching (the tray's own install)")
    args = parser.parse_args(argv)
    return run(args.pending, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
