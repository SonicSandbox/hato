# -*- coding: utf-8 -*-
"""
One hato run at a time (spec/06-edge-cases.md §7 and §9).

    with RunLock():            # paths.lock_path(); HATO_CACHE relocates it
        ...the run...

"Two hato processes at once -- SQLite WAL + a lock file. Second one exits with a
clear message rather than racing." and "Scheduled run overlaps a manual one --
Lock file. Second exits cleanly." A second holder gets LockHeld, whose message
names the pid and start time of the run it met and says what to do.

⭐ EXCLUSIVE CREATE, NOT "CHECK THEN WRITE". The runner's own lock tests for the
file and then writes it, and two processes can both pass the test. Here the
create itself is the test (O_CREAT | O_EXCL): exactly one of two contenders can
succeed, by construction.

⚠ A LOCK LEFT BY A DEAD RUN IS TAKEN OVER, NOT OBEYED FOR EVER. A scheduled run
that is killed leaves its lock behind, and a lock nobody clears means every
later run exits on it -- hato silently stops working until someone looks
(LEDGER.md §delivery). A lock whose pid is no longer running is taken over,
and `.note` says so in one sentence.

⚠ AND A PID IS NOT AN IDENTITY. Windows reuses process ids quickly, so a dead
run's pid can belong to some other program by the next night. The lock records
the process's CREATION time too; a live pid with a different creation time is a
different process, and the lock is stale.

⛔ NEVER STEAL A LIVE LOCK. Every uncertain case -- a lock still being written,
a process that cannot be queried -- is treated as held. Being wrong in that
direction costs one skipped run and a message that says what to delete; being
wrong in the other is two runs racing on one store.

⚠ AND "A MESSAGE THAT SAYS WHAT TO DELETE" IS A PROMISE THIS MODULE KEEPS FOR
EVERY WAY THE LOCK CAN FAIL, not just for a lock another run holds. A lock file
that cannot be created or read for any other reason raises `LockUnusable`,
whose message names the path and what is in the way. It used to be a raw
PermissionError traceback, and on the scheduled path the log then read only
*"hato exited 1"* -- the one line that exists to say what went wrong, saying
nothing (measured 2026-09-17).
"""
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from hato import paths

#: A lock that cannot be read and is younger than this is being written right
#: now by another run, not abandoned by a dead one.
GRACE_SECONDS = 10.0
_ROUNDS = 5


class LockUnusable(Exception):
    """The lock could not be created or read, and NOT because a run holds it.

    🚨 A SEPARATE EXCEPTION, ON PURPOSE. `LockHeld` means *another hato is
    running*, and saying that about a permission error, a read-only folder or a
    directory sitting where the lock file goes would be a lie the person then
    acts on -- they would wait for a run that does not exist. This says what is
    in the way and what to do about it, which is what the module docstring below
    promises and what a raw `PermissionError` traceback never said: the
    scheduled path logged only *"hato exited 1"*. Measured 2026-09-17.
    """

    def __init__(self, path, exc):
        self.path, self.error = Path(path), exc
        Exception.__init__(
            self, "hato's run lock at %s could not be %s (%s: %s). Nothing was "
                  "scanned. Check what is sitting at that path -- a folder with "
                  "that name, or a file hato may not write -- and remove it; or "
                  "set HATO_CACHE to a folder hato can write."
                  % (self.path, "created" if isinstance(exc, OSError) else "used",
                     type(exc).__name__, exc))


class LockHeld(Exception):
    """Another hato run holds the lock. The message says which, and what to do."""

    def __init__(self, path, pid=None, started=None, detail=None):
        self.path, self.pid, self.started = Path(path), pid, started
        if detail is None:
            detail = ("another hato run is in progress (pid %s, started %s)"
                      % (pid if pid is not None else "unknown", started or "at an unknown time"))
        Exception.__init__(
            self, "%s. This run stops rather than race it. Wait for that run to finish; "
                  "if no hato is running, delete %s and start again." % (detail, self.path))


# ---------------------------------------------------------------------------
# is a process still running?
# ---------------------------------------------------------------------------

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    _k32.GetExitCodeProcess.restype = wintypes.BOOL
    _k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    _k32.GetProcessTimes.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.CloseHandle.restype = wintypes.BOOL

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5

    def _query(pid):
        """-> ("gone", None) | ("denied", None) | ("exited", None) | ("running", creation)."""
        handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                return "denied", None       # it exists; it is simply not ours to query
            return "gone", None
        try:
            code = wintypes.DWORD()
            if not _k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return "denied", None
            if code.value != _STILL_ACTIVE:
                return "exited", None       # the object outlives the process while a handle is open
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not _k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                        ctypes.byref(kernel), ctypes.byref(user)):
                return "running", None
            return "running", (created.dwHighDateTime << 32) | created.dwLowDateTime
        finally:
            _k32.CloseHandle(handle)
else:
    def _query(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "gone", None
        except PermissionError:
            return "denied", None
        try:
            with open("/proc/%d/stat" % pid, encoding="utf-8") as fh:
                return "running", int(fh.read().rsplit(")", 1)[1].split()[19])
        except (OSError, ValueError, IndexError):
            return "running", None


def _process_start(pid):
    """-> an opaque creation stamp for a running `pid`, or None."""
    state, created = _query(pid)
    return created if state == "running" else None


def _process_alive(pid, recorded_start):
    """Is the run that wrote a lock (pid + creation stamp) still running?"""
    state, created = _query(pid)
    if state in ("gone", "exited"):
        return False
    if state == "running" and recorded_start is not None and created is not None \
            and created != recorded_start:
        return False                        # the pid now belongs to a different program
    return True


# ---------------------------------------------------------------------------
# the lock
# ---------------------------------------------------------------------------

def _valid_pid(value):
    return type(value) is int and 0 < value <= 0xFFFFFFFF


class RunLock(object):
    """`with RunLock():` -- held for the block, released on the way out, raise or not."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else paths.lock_path()
        #: One sentence when a dead run's lock was taken over; otherwise None.
        self.note = None
        self.held = False
        self._token = None

    def __repr__(self):
        return "<hato RunLock %s%s>" % (self.path, " held" if self.held else "")

    def acquire(self):
        if self.held:
            raise RuntimeError("this RunLock is already held")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LockUnusable(self.path, exc)
        token = uuid.uuid4().hex
        payload = json.dumps({
            "pid": os.getpid(),
            "started": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "proc_start": _process_start(os.getpid()),
            "token": token,
        }).encode("utf-8")
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0))
        for _ in range(_ROUNDS):
            try:
                fd = os.open(str(self.path), flags, 0o644)
            except FileExistsError:
                fd = None
            except OSError as exc:
                # ⚠ EVERY OTHER REASON IS A SENTENCE, NOT A TRACEBACK. A folder
                # sitting where the lock goes, a read-only root, an antivirus
                # holding the handle -- all reached a person as a raw
                # PermissionError through the scheduled path, whose log then read
                # only "hato exited 1" (measured 2026-09-17).
                raise LockUnusable(self.path, exc)
            if fd is None:
                # Outside the except block, so a LockHeld does not arrive wrapped in
                # "during handling of FileExistsError" -- the message is the point.
                self._meet_existing_lock()
                continue
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
            except OSError as exc:
                raise LockUnusable(self.path, exc)
            finally:
                os.close(fd)
            self._token, self.held = token, True
            return self
        raise LockHeld(self.path, detail="the run lock kept changing hands while this run "
                                         "tried to take it")

    def _meet_existing_lock(self):
        """A lock is there. Raise LockHeld if its run is alive; take it over if not."""
        try:
            with open(str(self.path), "rb") as fh:
                raw = fh.read()
            written = os.stat(str(self.path)).st_mtime
        except FileNotFoundError:
            return                          # released between our create and this read
        except OSError as exc:
            # ⚠ A lock we cannot even READ is not a lock held by a run we can
            # name. Same sentence, same path, no traceback.
            raise LockUnusable(self.path, exc)
        try:
            info = json.loads(raw.decode("utf-8"))
            pid, started = info.get("pid"), info.get("started")
            recorded_start = info.get("proc_start")
            if not _valid_pid(pid):
                info = None
        except (ValueError, AttributeError):
            info = None

        if info is None:
            age = time.time() - written
            if age < GRACE_SECONDS:
                raise LockHeld(self.path, detail="another hato run is starting right now "
                                                 "(its lock is still being written)")
            why = ("took over an unreadable run lock last written %s, left by a run that "
                   "did not finish" % datetime.fromtimestamp(written).strftime("%Y-%m-%d %H:%M:%S"))
        else:
            if _process_alive(pid, recorded_start if type(recorded_start) is int else None):
                raise LockHeld(self.path, pid, started)
            why = ("took over the run lock left by pid %s (started %s), which is no longer running"
                   % (pid, started or "at an unknown time"))
        if self._move_aside(raw):
            self.note = why

    def _move_aside(self, seen):
        """Rename the stale lock away, then check it IS the one judged stale.

        ⚠ Rename, not delete: two runs that both judged the same lock stale must
        not both win. Only one rename of a given file can succeed; the loser gets
        FileNotFoundError and simply tries to create the lock again.
        """
        aside = self.path.with_name("%s.stale-%d-%s" % (self.path.name, os.getpid(),
                                                        uuid.uuid4().hex[:8]))
        try:
            os.rename(str(self.path), str(aside))
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise LockUnusable(self.path, exc)     # ⚠ a sentence, never a traceback
        try:
            with open(str(aside), "rb") as fh:
                moved = fh.read()
        except OSError:
            moved = None
        if moved != seen:
            # A live run's fresh lock replaced the stale one between the read and
            # the rename. Put it back and stand down.
            try:
                os.rename(str(aside), str(self.path))
            except OSError:
                pass
            raise LockHeld(self.path, detail="another hato run took the lock at the same "
                                             "moment as this one")
        try:
            os.unlink(str(aside))
        except OSError:
            pass
        return True

    def release(self):
        """Remove the lock -- but only if it is still THIS run's."""
        if not self.held:
            return
        self.held = False
        try:
            with open(str(self.path), "rb") as fh:
                info = json.loads(fh.read().decode("utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(info, dict) and info.get("token") == self._token:
            try:
                os.unlink(str(self.path))
            except OSError:
                pass    # the next run finds a dead pid and takes it over, with a note

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
