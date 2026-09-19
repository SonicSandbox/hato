# -*- coding: utf-8 -*-
u"""
Shelling out to the CLI, and reading what comes back. RUNBOOK 7c.

    runner = Runner([folder], progress=True)
    runner.start()
    for event in runner.drain():      # non-blocking; call it from a timer
        ...
    run = runner.finished()           # None until the child has exited

===========================================================================
⛔ NO QT IN THIS FILE
===========================================================================

Everything here is testable without a display, and that is the point: the
subprocess, the decoding, the parse and the counts are where the failures
live, and a check that needs a window to run is a check that gets skipped on
CI. The painting is looked at; everything under it is asserted.

⚠ Inherited wholesale from `tsubasa/gui/run.py`, which paid for each of the
notes below in a real defect. What differs is hato's grammar: an NDJSON
stream that now also carries `{"type": "progress"}` lines as the run happens
(RUNBOOK 7b), because every `{"type": "video"}` object is built from a
FINISHED report and arrives at the end.

===========================================================================
🚨 THE HEADLINE MUST PARTITION, AND "N ADDED" IS A CLAIM ABOUT FILES
===========================================================================

tsubasa's adversarial pass found a GUI that rebuilt a known defect out of
fields, which is worse than reading it out of prose because every individual
number was right. The rules that came out of it apply here unchanged:

1. **The categories PARTITION.** `added + needs_you + errored + skipped` is
   `len(rows)`, asserted. A subset presented as a sibling is how eight files
   became eleven on the one line a person reads at a glance.
2. **A CONFIDENT row is not a written file.** A dry run breaks that link and
   the outcome field cannot see it. ⛔ Never say *"added"* off `outcome`
   alone -- require an `output_path` too.
3. ⭐ **The engine's vocabulary never reaches the interface.** `05-interface.md`:
   *"when it says 'refused' it's quite alarming."* REFUSED is tsubasa's word
   for *the timing did not hold*; to a person who can fix it in two clicks it
   reads as an accusation. Here it is `NEEDS_YOU`, and `interface_words()`
   exists so a check can prove the engine's word never escapes.

---------------------------------------------------------------------------
🚨 FOUR THINGS ABOUT THE CHILD THAT READ AS FAILURE AND ARE NOT
---------------------------------------------------------------------------

| Looks like | Actually |
| --- | --- |
| **exit 1** | *"something needs a pick"* -- the whole value proposition. ⛔ Only exit **2** means the command could not be run |
| **output on stderr** | `--json` puts NDJSON on stdout and hato's own notes on stderr, deliberately, so a pipe stays pure NDJSON. stderr is an information channel here |
| **zero rows** | could be a settled library, an empty folder, or nothing pairable. ⛔ Three states, one row count |
| **a flagged result** | CONFIDENT, and it repaired a broadcast cut. It belongs with the successes |

---------------------------------------------------------------------------
🚨 AND THE CONSOLE WINDOW
---------------------------------------------------------------------------

A GUI parent has no console, so every child allocates its own -- it flashes
over the app and steals focus. Same fix as `tsubasa/gui/run.py`.
"""
from __future__ import print_function

import json
import os
import subprocess
import sys
import queue
import threading
import time
from pathlib import Path

#: `cli.main`'s exit codes, named. ⛔ 1 is not an error.
EXIT_CLEAN = 0
EXIT_ATTENTION = 1
EXIT_CANNOT_RUN = 2

#: The engine's outcome words, as they arrive on the wire.
CONFIDENT = u"CONFIDENT"
REFUSED = u"REFUSED"
ERROR = u"ERROR"
NOT_FOUND = u"NOT_FOUND"

#: ⭐ What the INTERFACE calls each of them. `05-interface.md`: the word
#: "refused" never appears. A row a person can act on says so.
ADDED = u"added"
NEEDS_YOU = u"needs a pick"
NOT_YET = u"not on jimaku yet"
FAILED = u"something went wrong"
SKIPPED = u"already had one"


def interface_words():
    u"""Every string this module can put in front of a person. -> set

    ⭐ SO A CHECK CAN PROVE A NEGATIVE. `05-interface.md` rules that the word
    *refused* never appears in the interface, and the only way to assert that
    is for the vocabulary to be enumerable rather than scattered through the
    painting code.
    """
    return {ADDED, NEEDS_YOU, NOT_YET, FAILED, SKIPPED}


# ---------------------------------------------------------------------------
# what to run
# ---------------------------------------------------------------------------

def cli_argv():
    u"""How to invoke the CLI from here. -> [str]

    ⭐ ONE PLACE, because there are three hosts and they disagree:

      * from source, `sys.executable` is python and `-m hato` is right;
      * frozen by PyInstaller, `sys.executable` is the BUNDLE -- `-m` would
        re-enter the GUI and open a second window rather than run the CLI, so
        the bundled console entry point beside it is used instead;
      * `HATO_CLI` overrides both, which is how the suite drives a
        deliberately-failing child without inventing a fake process object.
    """
    override = os.environ.get("HATO_CLI")
    if override:
        # 🚨 A PATH MAY BEGIN WITH `[`. Half this corpus's release groups are
        # named `[Erai-raws]`, `[SubsPlease]`, so *"starts with a bracket,
        # therefore JSON"* turns an ordinary directory into a JSONDecodeError
        # raised out of `Runner.__init__`. Try the list form, fall back to the
        # literal, and never let the guess raise.
        if override.startswith("["):
            try:
                loaded = json.loads(override)
            except ValueError:
                return [override]
            if isinstance(loaded, list) and loaded and \
                    all(isinstance(x, str) for x in loaded):
                return list(loaded)
            return [override]
        return [override]
    if getattr(sys, u"frozen", False):
        # 🚨 `hato-cli.exe`, NOT `hato.exe`. RULED BY SONIC 2026-09-18: *"i
        # don't want it 'gui', i want it to be hato as the main one ... i can
        # just click on hato.exe and it will handle everything else."* So
        # `hato.exe` IS THE WINDOW, and the command line is the sibling.
        # ⛔ Pointing this at `hato.exe` would re-enter the GUI and open a
        # second window instead of running a scan.
        exe = os.path.join(os.path.dirname(sys.executable),
                           u"hato-cli.exe" if sys.platform.startswith("win")
                           else u"hato-cli")
        return [exe]
    return [sys.executable, u"-m", u"hato"]


def argv_for(folders, dry_run=False, force=False, candidates=None,
             progress=True):
    u"""The full command for one run. -> [unicode]

    🚨 `--json` IS NOT A DISPLAY CHOICE. It is what gives the window an
    `outcome` field to count instead of prose containing the word *confident*
    next to the word *refused*.

    🚨 **EVERY FOLDER IS MADE ABSOLUTE, AND THAT IS A CORRECTNESS FIX.** A
    GUI's working directory is wherever the shortcut pointed -- on Windows
    routinely `C:\\Windows\\System32`. hato also reads any token starting with
    `-` as a flag, and an absolute path cannot start with one.
    """
    if not folders:
        raise ValueError(
            u"a folder is needed. Add one in Settings, or drop one on the "
            u"window -- hato searches it for videos that have no Japanese "
            u"subtitle yet.")
    argv = list(cli_argv()) + [u"--json"]
    if progress:
        argv.append(u"--progress")
    if dry_run:
        argv.append(u"--dry-run")
    if force:
        argv.append(u"--force")
    if candidates is not None:
        argv.extend([u"--candidates", str(candidates)])
    for folder in folders:
        argv.append(os.path.abspath(os.fspath(folder)))
    return argv


def argv_for_pair(video, subtitle):
    u"""⭐ THE MANUAL PICK (RUNBOOK 7d). -> [unicode]

    `05-interface.md`: *manual pairing is a solved mechanism, not a new one* --
    hato already hands tsubasa an explicit pair, so a person's pick only
    replaces hato's own ranking. ⛔ The timing verdict still rules, and still
    refuses a wrong pair. That is Rule 1 holding even when the person chooses.
    """
    return list(cli_argv()) + [u"sync", os.path.abspath(os.fspath(video)),
                               os.path.abspath(os.fspath(subtitle)), u"--json"]


def argv_for_config(*flags):
    u"""⭐ SETTINGS WRITES THROUGH THE CLI (RUNBOOK 7a). -> [unicode]

    ⛔ The window never edits `config.toml` itself. `hato/config.py` owns a
    closed schema, and a second writer means two programs disagreeing about
    one file.
    """
    return list(cli_argv()) + [u"config"] + [str(f) for f in flags] + [u"--json"]


def no_console_kwargs():
    u"""Popen keywords that stop a console flashing over the app. -> dict

    ⚠ Empty off Windows, where neither exists.
    """
    if not sys.platform.startswith("win"):
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    # 🚨 SET IT ON PURPOSE, AND READ THIS BEFORE REUSING THIS FUNCTION.
    # `wShowWindow` defaults to 0, and 0 IS `SW_HIDE`. Windows hands it to the
    # child as the nCmdShow for its FIRST window -- so these keywords are right
    # for a CONSOLE child and would make a GUI child build a real, native,
    # permanently invisible window. ⛔ That is not hypothetical: it cost two
    # rounds and a wrong root cause given to Sonic as fact. A window child
    # takes `hato.watch.gui_spawn_kwargs`, which sets SW_SHOWNORMAL.
    startupinfo.wShowWindow = 0                                     # SW_HIDE
    # ⭐ AND NO BUSY CURSOR. Sonic, 2026-09-18: *"if it has the cursor think
    # when it downloads, it shouldn't."* hato sets no wait cursor anywhere --
    # what he saw is WINDOWS' OWN "application starting" pointer, which the
    # shell shows for a couple of seconds whenever a process is launched. Every
    # run spawns one, so every run flickered it.
    # ⚠ `STARTF_FORCEOFFFEEDBACK` is the documented way to say *this launch is
    # not something the person is waiting on*. ⛔ It suppresses the feedback
    # only for THIS child; it never touches the cursor globally.
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_FORCEOFFFEEDBACK", 0x80)
    return {"creationflags": flags, "startupinfo": startupinfo}


def child_env(base=None):
    u"""The environment for the child. -> dict

    🚨 `PYTHONIOENCODING` IS LOAD-BEARING AND THE CLI ALONE IS NOT ENOUGH.
    hato reconfigures its own streams to UTF-8, which covers everything it
    prints -- but a traceback from the interpreter, or anything written before
    `main()` is reached, still goes out through the ANSI codepage, and on this
    corpus that means a `UnicodeEncodeError` about a Japanese path swallowing
    the real error.

    ⚠ **AND IT DOES NOTHING WHEN THE CHILD IS FROZEN** -- measured on tsubasa,
    2026-09-17: the PyInstaller bootloader runs Python isolated, so the
    variable is simply ignored. ⭐ It is still set, because it is correct for
    the source path and costs nothing on the frozen one. The parent's
    `errors="replace"` is what makes neither case able to crash the window.

    ⭐ DELEGATED TO `paths.child_env` ON 2026-09-18. A THIRD copy of this lived
    in the tray watcher with the PYTHONPATH half missing, so *"Open hato"* from
    the tray spawned a child that died on `ModuleNotFoundError` before printing
    anything. ⛔ This copy was the CORRECT one -- and being correct is not the
    same as being the only one.
    """
    from hato import paths
    return paths.child_env(base)


# ---------------------------------------------------------------------------
# reading the stream
# ---------------------------------------------------------------------------

def outcome_word(obj):
    u"""One video object -> what the INTERFACE calls its state.

    🚨 A CONFIDENT ROW IS NOT A WRITTEN FILE. A dry run, and a write that
    failed, both leave `outcome == CONFIDENT` with no `output_path` -- and the
    outcome field cannot see either. tsubasa's GUI reported *"1 synced"* for
    both until an adversarial pass caught it.
    """
    if obj.get("skip"):
        return SKIPPED
    outcome = obj.get("outcome")
    if outcome == CONFIDENT:
        return ADDED if obj.get("output_path") else FAILED
    if outcome == REFUSED:
        return NEEDS_YOU
    if outcome == NOT_FOUND:
        return NOT_YET
    return FAILED


def match_percent(obj):
    u"""-> an int 0..100, or None when nothing was timed.

    ⚠ The rate lives on tsubasa's own Result, passed through verbatim. A row
    that was never timed has none, and ⛔ `0` is a real answer that means *it
    matched nothing* -- so the absent case must not become zero.
    """
    tsu = obj.get("tsubasa") or {}
    rate = tsu.get("match_rate")
    if rate is None:
        best = None
        for attempt in obj.get("attempts") or ():
            value = attempt.get("match_rate")
            if value is not None and (best is None or value > best):
                best = value
        rate = best
    if rate is None:
        return None
    return int(round(float(rate) * 100))


def parse_answer(raw):
    u"""The single `--json` object a one-shot command prints. -> dict

    ⭐ HERE, NOT IN THE WINDOW, and a check enforces it. This module owns
    every conversation with the CLI -- the argv going out and the JSON coming
    back -- so that the window holds no second opinion about either. The first
    version of `verify_key` called `json.loads` in `app.py` and the check
    caught it the same minute.

    ⛔ NEVER RAISES. `hato key --test` answers on stdout, but a command that
    died before printing, or printed something else, must not take the window
    down -- the caller reads the empty dict as *"no answer"*.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    for line in reversed((raw or u"").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            answer = json.loads(line)
        except ValueError:
            continue
        return answer if isinstance(answer, dict) else {}
    return {}


def save_last_run(rows, summary, path=None):
    u"""Remember the run the window just painted. -> the path, or None.

    ⭐ SONIC, 2026-09-18: *"it should also have the most recent run stuff, etc
    right?"* It should. Settings load on open; results did not, so reopening
    showed an empty Subtitles tab under a header saying when the last run was.

    ⛔ RE-RUNNING ON OPEN IS THE WRONG ANSWER. A run costs metered requests
    against a 25-per-60s budget, and opening a window is not asking for one.
    Remembering what hato already said costs nothing and is the same rows.

    ⚠ TEMP-PLUS-RENAME. `open(path,'w')` truncates the moment it opens, so a
    raise mid-write would leave a zero-byte file -- and the next launch would
    read that as *no previous run* rather than as a broken one.

    ⛔ Nothing here can hold a secret: these are hato's own output objects,
    which carry filenames and verdicts and never the key.

    ⛔ DELEGATED TO `hato.lastrun` ON 2026-09-18, and the move is the fix. This
    was the WINDOW's memory, so only runs the window started were remembered --
    a tray or scheduled run wrote subtitles and left nothing to read, and the
    open window showed nothing while hato worked two processes away. hato now
    writes it at the end of every run, whoever started it.
    """
    from hato import lastrun
    return lastrun.save(rows, summary, path=path)


def load_last_run(path=None):
    u"""-> (rows, summary, saved_at). Empty when there is nothing to remember.

    ⛔ NEVER RAISES. A truncated or hand-edited file is *no memory*, not a
    window that will not open.
    """
    from hato import lastrun
    return lastrun.load(path=path)


def pending_run():
    u"""-> (seconds_until_a_queued_run, names). `(0.0, [])` when none.

    ⭐ SONIC, 2026-09-18: he thought auto-fetch was broken in subfolders. It
    was not -- what he hit was the SETTLE MINUTE, during which nothing said a
    run was coming. **An invisible wait is indistinguishable from broken.**

    ⚠ The wait belongs to the TRAY, a different process, so this reads the file
    the watcher writes rather than knowing anything itself.
    """
    from hato import watch
    return watch.read_pending()


def last_run_stamp(path=None):
    u"""-> the memory's timestamp, or 0.0.

    ⭐ HOW THE WINDOW NOTICES A RUN IT DID NOT START. A `stat`, polled -- so
    the tray, the scheduler and a terminal all reach the window without any
    channel between processes that were never meant to know about each other.
    """
    from hato import lastrun
    return lastrun.stamp(path=path)


def counts(rows):
    u"""-> {word: n} over every interface word, and it PARTITIONS.

    ⭐ Every key is present even at zero, so a caller cannot read a missing
    key as an absent category, and `sum(counts.values()) == len(rows)` is
    asserted by the suite.
    """
    out = dict((word, 0) for word in interface_words())
    for row in rows:
        out[outcome_word(row)] += 1
    return out


class Run(object):
    u"""What one finished run amounted to."""

    def __init__(self, code, rows, summary, notes, stderr):
        self.code = code
        self.rows = rows
        self.summary = summary or {}
        self.notes = list(notes)
        self.stderr = stderr

    @property
    def could_not_run(self):
        u"""⛔ ONLY exit 2. Exit 1 means something needs a pick, which is the
        tool working."""
        return self.code == EXIT_CANNOT_RUN

    @property
    def counts(self):
        return counts(self.rows)

    @property
    def api_calls(self):
        return self.summary.get("api_calls", 0)

    @property
    def seconds(self):
        return self.summary.get("seconds", 0.0)

    def __repr__(self):
        return "<Run exit=%s rows=%d>" % (self.code, len(self.rows))


class Runner(object):
    u"""One `hato` child, read without blocking the window.

    ⚠ TWO READER THREADS, one per pipe. A single thread reading stdout while
    the child fills stderr deadlocks as soon as stderr's buffer is full -- and
    hato writes its notes there deliberately.
    """

    def __init__(self, folders=None, argv=None, **options):
        self.argv = list(argv) if argv is not None else argv_for(folders, **options)
        self.events = queue.Queue()
        self._process = None
        self._threads = []
        self._stderr = []
        self._rows = []
        self._summary = None
        self._finished = None

    def start(self):
        self._process = subprocess.Popen(
            self.argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=child_env(), **no_console_kwargs())
        for stream, sink in ((self._process.stdout, self._on_stdout),
                             (self._process.stderr, self._on_stderr)):
            thread = threading.Thread(target=self._pump, args=(stream, sink))
            thread.daemon = True            # ⛔ never keeps the app alive
            thread.start()
            self._threads.append(thread)
        return self

    def _pump(self, stream, sink):
        # ⚠ `errors="replace"`, and it is why a mis-encoded byte from a frozen
        # child cannot take the window down with it.
        for raw in iter(stream.readline, b""):
            sink(raw.decode("utf-8", "replace").rstrip(u"\r\n"))
        stream.close()

    def _on_stdout(self, line):
        if not line.strip():
            return
        try:
            obj = json.loads(line)
        except ValueError:
            # ⛔ NOT DISCARDED. Anything on stdout that is not NDJSON is a
            # defect in hato's own grammar (`_say`'s gate), and swallowing it
            # here is how it would stay invisible.
            self.events.put({"type": "unparsed", "line": line})
            return
        kind = obj.get("type")
        if kind == "video":
            self._rows.append(obj)
        elif kind == "run":
            self._summary = obj
        self.events.put(obj)

    def _on_stderr(self, line):
        if line.strip():
            self._stderr.append(line)
            self.events.put({"type": "note", "text": line})

    def drain(self):
        u"""-> every event that has arrived since the last call. Never blocks."""
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def finished(self):
        u"""-> a `Run` once the child has exited and both pipes are drained,
        else None.

        ⚠ THE THREADS MUST BE JOINED, not merely the process polled. A process
        can exit with its last lines still in the pipe, and a window that built
        its table on `poll() is not None` would paint a run that is missing its
        final rows -- intermittently, and more often on a fast machine.
        """
        if self._process is None or self._finished is not None:
            return self._finished
        if self._process.poll() is None:
            return None
        for thread in self._threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                return None
        self._finished = Run(self._process.returncode, self._rows,
                             self._summary, self._stderr, u"\n".join(self._stderr))
        return self._finished

    def stop(self):
        u"""⛔ Ask, do not kill. hato writes files; a killed run can leave a
        temp file it would otherwise have cleaned up. The run lock is released
        on exit, so a killed child would also leave it behind."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()


__all__ = ["ADDED", "NEEDS_YOU", "NOT_YET", "FAILED", "SKIPPED",
           "EXIT_CLEAN", "EXIT_ATTENTION", "EXIT_CANNOT_RUN",
           "Run", "Runner", "argv_for", "argv_for_config", "argv_for_pair",
           "child_env", "cli_argv", "counts", "interface_words",
           "last_run_stamp", "load_last_run", "match_percent", "no_console_kwargs",
           "outcome_word", "parse_answer", "save_last_run"]
