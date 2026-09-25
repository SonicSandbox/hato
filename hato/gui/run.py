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
🚨 WHAT A RUN'S EXIT CODE MEANS -- AND WHAT THIS FILE USED TO SAY IT MEANT
---------------------------------------------------------------------------

| Exit | Means (`commands/run.py`) |
| --- | --- |
| **0** | it ran -- whether or not anything needs a pick. A held lock is 0 too, said by a `{"type": "busy"}` object |
| **1** | 🚨 it STOPPED: a 401, a server that went away, a crash. ⛔ This table used to say *"exit 1 = something needs a pick"*, and the window painted a run cut short by a rejected key as **done** (ADVERSARY 2026-09-22 A12) |
| **2** | the command could not be run: a usage mistake, no key |

And three things that read as failure and are not:

| Looks like | Actually |
| --- | --- |
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
from collections import OrderedDict
from pathlib import Path

#: `cli.main`'s exit codes, named -- see the table above.
EXIT_CLEAN = 0
EXIT_STOPPED = 1
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

#: 🚨 FIVE SKIPS, AND THEY ARE NOT THE SAME FACT. Sonic, 2026-09-19, on the
#: published 1.0.1: *"Katanai and tsuihou don't have it even though it says
#: its already subbed in the GUI."* Both were true reports of a SKIP and
#: neither meant *"this video has its subtitle"* --
#:
#:   Katainaka   an Erai-raws [MultiSub] rip: the Japanese track is INSIDE the
#:               container, so there is correctly no file beside it
#:   Tsuihou     3 of 10 candidates downloaded, none held on timing, soft
#:               negative recorded, retrying tomorrow. NOTHING is there
#:
#: ⛔ `outcome_word` used to answer `SKIPPED` for all five, so a video that had
#: TRIED AND FAILED rendered identically to one that was finished -- and the
#: quiet line under it said *"already subtitled"* with a tooltip claiming
#: *"every episode already carries a Japanese track."* For Tsuihou every word
#: of that was false.
#:
#: ⭐ THE WORDS ARE THE CLI'S, which has distinguished all four since 4a
#: (`report.py` §SKIP_WORDS) -- the engine always sent `skip`, and only the
#: window threw it away. One vocabulary, two front ends.
SKIPPED = u"already had one"
INSIDE_VIDEO = u"subtitles are inside the video"
RETRYING = u"waiting to retry"
CANT_SYNC = u"can't sync yet"
ON_SKIP_LIST = u"on your skip list"

#: `skip` on the wire -> what a person is told. ⚠ An UNKNOWN skip value falls
#: back to `SKIPPED`, because a new engine skip must never render as a blank.
SKIP_WORDS = {
    u"present": SKIPPED,
    u"embedded": INSIDE_VIDEO,
    u"negative": RETRYING,
    u"no-track": CANT_SYNC,
    u"blacklisted": ON_SKIP_LIST,
}


def is_skipped(word):
    u"""Is this one of the words that means *nothing was requested*? -> bool

    ⭐ The grouping code asks this instead of `== SKIPPED`, so splitting the
    word into five did not silently drop four of them out of every tally.
    """
    return word in set(SKIP_WORDS.values())


def interface_words():
    u"""Every string this module can put in front of a person. -> set

    ⭐ SO A CHECK CAN PROVE A NEGATIVE. `05-interface.md` rules that the word
    *refused* never appears in the interface, and the only way to assert that
    is for the vocabulary to be enumerable rather than scattered through the
    painting code.
    """
    return ({ADDED, NEEDS_YOU, NOT_YET, FAILED} | set(SKIP_WORDS.values())
            | {PAIRED, FORCED, PICK_REFUSED, PICK_FAILED})


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


#: 🚨 RUNBOOK 8e / D6 -- A PERSON'S PICK OVERRIDES A TIMING REFUSAL. ⚠ AWAITING
#: SONIC'S RULING, and this is the one line that reverses it.
#:
#: Measured 2026-09-22, two arms on a real pair (Tsuihou 12 + NanakoRaws E12):
#: every card on *Needs you* is a candidate the timing check ALREADY refused, and
#: `hato sync` runs the same deterministic check -- so without force a pick can
#: never write anything (REFUSED again, 70%, same reason). With tsubasa's own
#: `force` the pair is written and the result still says the timing did not hold.
#: Sonic's words when he ruled the picker: *"if they click on one, it should count
#: as 'use this pair'."* `05-interface.md` glossed that as *"the timing verdict
#: still refuses a wrong pair"* -- a gloss whose premise (*"a pick only replaces
#: hato's ranking"*) the measurement shows is false: ranking had tried them all.
PICK_OVERRIDES_TIMING = True


def argv_for_pair(video, subtitle, force=False):
    u"""⭐ THE MANUAL PICK (RUNBOOK 7d, repaired at 8e). -> [unicode]

    `05-interface.md`: *manual pairing is a solved mechanism, not a new one* --
    hato hands tsubasa an explicit pair. ⭐ `force` is the person overruling a
    timing refusal (see `PICK_OVERRIDES_TIMING`); tsubasa still refuses an
    ERROR, and still refuses to write over a file that is there.

    🚨 `--json` WAS SENT FOR MONTHS TO A COMMAND THAT DID NOT ACCEPT IT. Every pick
    died on a usage error, exit 2, and the window painted it *"paired"*. The check
    that pins the command's side is `test_port.py`'s, which runs THIS argv.
    """
    argv = list(cli_argv()) + [u"sync", os.path.abspath(os.fspath(video)),
                               os.path.abspath(os.fspath(subtitle)), u"--json"]
    if force:
        argv.append(u"--force")
    return argv


#: What a pick came to -- the words `pick_verdict` answers with.
PAIRED = u"paired"
FORCED = u"used"
PICK_REFUSED = u"still did not line up"
PICK_FAILED = u"could not be used"


def pick_verdict(code, answer):
    u"""What `hato sync --json` said about a person's pick. -> (word, why, written)

    ⛔ A PICK IS NOT PAIRED UNTIL A FILE LANDED. `commit_pair` used to paint the row
    green the moment it was clicked and never read the child -- over a child that
    had died on a usage error. `written` comes from the answer, never from the exit
    code alone, and never from the click.
    """
    answer = answer if isinstance(answer, dict) else {}
    why = (answer.get(u"reason") or u"").strip()
    if answer.get(u"written"):
        return (FORCED if answer.get(u"forced") else PAIRED), why, \
            answer.get(u"output_path")
    if not answer or code == EXIT_CANNOT_RUN:
        return PICK_FAILED, why or u"hato could not run the pair", None
    if answer.get(u"outcome") == REFUSED:
        return PICK_REFUSED, why, None
    return PICK_FAILED, why or u"nothing was written", None


def argv_for_retry(video, folder, candidates=None):
    u"""⭐ LOOK AGAIN NOW (RUNBOOK 8e / D3). -> [unicode]

    `video` and `folder` may each be one path or several. `--retry-now` ignores
    the waiting period and nothing else: a file already refused for a video is
    still never downloaded again, and a blacklist still stands. `--only` keeps
    the run to these videos, and such a run leaves the window's memory of the
    last full run alone. ⚠ The FOLDER is the watched one, not the video's own:
    a release's numbering is fitted against the whole folder's range.
    """
    videos = [video] if isinstance(video, (str, os.PathLike)) else list(video)
    folders = [folder] if isinstance(folder, (str, os.PathLike)) else list(folder)
    argv = list(cli_argv()) + [u"--json", u"--progress", u"--retry-now"]
    named = [os.path.abspath(os.fspath(one)) for one in videos]
    for one in named:
        argv.extend([u"--only", one])
    if candidates is not None:
        argv.extend([u"--candidates", str(candidates)])
    seen = []
    for one in folders:
        one = os.path.abspath(os.fspath(one))
        if one not in seen:
            seen.append(one)
    argv += seen
    if len(subprocess.list2cmdline(argv)) <= COMMAND_LINE_BUDGET:
        return argv
    # 🚨 A LONG LIST CANNOT BE A COMMAND LINE. Windows refuses one past 32,767
    # characters, and *Look again now* on every episode not on jimaku yet -- a
    # few hundred in a real library -- could not even start (ADVERSARY
    # 2026-09-22 A33). ⭐ The list goes in a file, `--only-list`, instead.
    listed = only_list_file(named)
    if listed is None:
        return argv                        # ⚠ and the start says why it failed
    out = list(cli_argv()) + [u"--json", u"--progress", u"--retry-now",
                              u"--only-list", listed]
    if candidates is not None:
        out.extend([u"--candidates", str(candidates)])
    return out + seen


#: How long a command line may be before its `--only` list goes in a file.
#: ⚠ Well under Windows' 32,767 characters, so the rest of the line always fits.
COMMAND_LINE_BUDGET = 24000


def only_list_file(videos):
    u"""Write the videos for `--only-list`, one per line. -> the path, or None.

    ⛔ Temp-plus-rename, UTF-8, in hato's own folder -- never a person's.
    """
    from hato import paths
    try:
        target = paths.data_root() / u"window-only-list.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + u".new-%d" % os.getpid())
        with open(str(temp), "w", encoding="utf-8", newline=u"\n") as handle:
            handle.write(u"".join(u"%s\n" % v for v in videos))
        os.replace(str(temp), str(target))
        return str(target)
    except (OSError, ValueError):
        return None


def blacklist_entries(answer, exists=os.path.exists):
    u"""`hato blacklist --list --json` -> the rows the Settings card paints.

    🚨 D5. The card was fed by test fixtures alone: `state.blacklist` started
    empty and nothing ever loaded it, so the count read 0 and the sweep for rows
    whose video has rotated off disk never fired in the product. ⭐ `gone` is a
    stat on the path hato recorded -- the one thing it can check for a video that
    is no longer there to hash.
    """
    from datetime import datetime
    rows = (answer or {}).get(u"blacklist") or ()
    out = []
    for row in rows:
        path = row.get(u"video_path") or u""
        when = u""
        try:
            # ⚠ THE PERSON'S DAY, not UTC's: stored in UTC, an entry added on an
            # evening west of Greenwich was dated the next day (ADVERSARY
            # 2026-09-22 A29).
            moment = datetime.fromisoformat(row.get(u"added_at") or u"")
            if moment.tzinfo is not None:
                moment = moment.astimezone()
            when = moment.strftime(u"%d %b").lstrip(u"0")
        except (TypeError, ValueError, OverflowError, OSError):
            pass
        out.append({u"name": os.path.basename(path) or row.get(u"video_hash", u"")[:12],
                    u"path": path, u"note": row.get(u"note") or u"", u"when": when,
                    u"gone": bool(path) and not exists(path)})
    return out


def argv_for_problems():
    u"""⭐ RUNBOOK 8c -- what still needs a person, from the state DB. -> [unicode]"""
    return list(cli_argv()) + [u"problems", u"--json"]


def argv_for_blacklist():
    u"""D5 -- the blacklist as hato holds it. -> [unicode]"""
    return list(cli_argv()) + [u"blacklist", u"--list", u"--json"]


def argv_for_clear(yes=False, blacklist=False):
    u"""⭐ RUNBOOK 8g -- `hato state --clear`. -> [unicode]

    ⛔ Without `yes` it only COUNTS -- the card's numbers, and what the confirm
    names -- and takes no lock. With it, it clears, under the run lock. The
    blacklist goes only when named.
    """
    argv = list(cli_argv()) + [u"state", u"--clear", u"--json"]
    if yes:
        argv.append(u"--yes")
    if blacklist:
        argv.append(u"--blacklist")
    return argv


def memory_summary(answer):
    u"""What `hato state --clear --json` counted, as one line. -> text, or u"".

    ⭐ Said in what a person recognises -- videos, waits, shows -- never as
    tables and rows. u"" until hato has answered: a count of nothing is not a
    number to show.
    """
    cleared = (answer or {}).get(u"cleared") if isinstance(answer, dict) else None
    if not isinstance(cleared, dict):
        return u""

    def n(key):
        value = cleared.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    videos, waiting, shows = n(u"videos"), n(u"waiting"), n(u"shows")
    return u"%d video%s tried · %d waiting to look again · %d show%s found on jimaku" % (
        videos, u"" if videos == 1 else u"s", waiting, shows, u"" if shows == 1 else u"s")


def argv_for_update(*flags):
    u"""⭐ RUNBOOK 11f -- `hato update`, the ONE implementation the window, the
    tray and a person share. -> [unicode]. `--json` always: the window reads the
    `{"type": "update" | "progress" | "staged" | "error"}` objects, never prose."""
    return list(cli_argv()) + [u"update"] + [str(f) for f in flags] + [u"--json"]


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
    skip = obj.get("skip")
    if skip:
        # ⛔ NOT one word for all five. See SKIP_WORDS: *"already had one"* over
        # a video that downloaded three candidates and kept none is the report
        # that sent Sonic looking for a file that was never written.
        return SKIP_WORDS.get(skip, SKIPPED)
    outcome = obj.get("outcome")
    if outcome == CONFIDENT:
        return ADDED if obj.get("output_path") else FAILED
    if outcome == REFUSED:
        return NEEDS_YOU
    if outcome == NOT_FOUND:
        return NOT_YET
    return FAILED


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 8e -- Needs you, from the run AND from what hato remembers
# ---------------------------------------------------------------------------
#
# 🚨 4a: *"a problem episode must never disappear from Needs you."* It did, for
# two independent reasons, and both are closed upstream: a run inside the retry
# window now carries the files it is waiting on (`tried_before`, RUNBOOK 8d), and
# `hato problems` lists every open problem from the state DB, whichever run last
# looked (8c). What follows is the part that belongs to the window: one list, one
# rule for which copy of a row wins, and one honest sentence about the wait.

#: The three kinds of row Needs you holds.
PICK = u"pick"            # files were tried; a person can choose one
WAITING = u"waiting"      # nothing to choose yet -- hato asks again later
TROUBLE = u"trouble"      # something went wrong; the reason says what


def candidates_of(row):
    u"""Every file tried for this video -- this run's, then earlier runs'. -> [dict]

    ⭐ One per file name (this run's copy wins: it carries tsubasa's whole result),
    best match first, an unmeasured one last. ⛔ Never the jimaku catalogue
    (`05-interface.md` §manual pairing): only what was downloaded and timed.
    """
    seen, out = set(), []
    for item in list(row.get(u"attempts") or ()) + list(row.get(u"tried_before") or ()):
        name = item.get(u"name") or u""
        if name in seen:
            continue
        seen.add(name)
        out.append(item)
    out.sort(key=lambda c: (c.get(u"match_rate") is None, -(c.get(u"match_rate") or 0.0)))
    return out


def problem_kind(row):
    u"""-> PICK, WAITING, TROUBLE, or None when the row needs nobody.

    ⚠ A SKIP CAN NEED A PERSON. `skip: negative` is *waiting to retry*, and since
    RUNBOOK 8d it carries the files it is waiting on -- that is a row a person can
    still pick from, which is the exact row 4a says must never vanish.
    ⭐ And a pick the person chose to WAIT on is a wait (`apply_waits`, 4c).
    """
    if row.get(u"waiting_by_choice"):
        return WAITING
    skip = row.get(u"skip")
    # ⭐ 9a -- A FORMAT WAIT IS A WAIT, whatever was tried before it: files
    # refused in an earlier run made it a pick, and the format line -- and its
    # *Download .srt instead* -- never showed (ADVERSARY 2026-09-23 #5).
    has = bool(candidates_of(row)) and not is_format_wait(row)
    if skip == u"negative":
        return PICK if has else WAITING
    if skip:
        return None
    outcome = row.get(u"outcome")
    if outcome == REFUSED:
        # ⚠ A REFUSAL WITH NOTHING TRIED IS NOT A PICK. Two videos targeting one
        # file, a name holding two episodes, a name with no episode number:
        # refused before any download, so the row read *"0 tried · best —"*
        # over nothing to pick, and hid the one sentence that says what to do
        # (ADVERSARY 2026-09-22 A6). It is trouble, and its reason shows.
        return PICK if has else TROUBLE
    if outcome == NOT_FOUND:
        return PICK if has else WAITING
    if outcome == ERROR:
        return TROUBLE
    return None


def is_format_wait(row):
    u"""⭐ 9a -- is this row waiting because jimaku has it only in a format the
    person's settings do not take? -> bool. ONE reader of the sentence
    (`formats.only_as`), for the classifier and the painter alike."""
    from hato import formats
    return bool(formats.only_as(row.get(u"reason")))


def problem_key(row):
    u"""One video's identity across the run's rows and the remembered ones."""
    path = row.get(u"video") or row.get(u"name") or u""
    return os.path.normcase(os.path.abspath(path)) if path else u""


def _remembered_by_the_db(row):
    u"""Would `hato problems` still list this row if it were unsettled? -> bool

    Anything the state DB holds a row for: a wait, a tried file, a retry date.
    ⛔ NOT a clash, a two-episode name or an unreadable container -- none of those
    records a row, so only the run's own snapshot can show them.
    """
    return bool(row.get(u"skip") == u"negative" or row.get(u"attempts")
                or row.get(u"tried_before") or row.get(u"retry_after"))


def needs_you(rows, remembered=None, live=(), rows_newer=False, in_scope=None,
              trust_rows=False):
    u"""The ONE list Needs you paints. -> [row]

    `rows`         the run's rows: `last-run.json`'s snapshot, with whatever a run
                   has streamed since replacing its own videos' rows
    `remembered`   `hato problems --json`'s rows, or None until it has answered
    `live`         the keys (`problem_key`) a run streamed AFTER the memory
                   answered -- newer than it, video by video
    `rows_newer`   the snapshot itself arrived after the memory answered
    `in_scope`     `(row) -> bool`: could `hato problems` list this video at all?
                   It lists only videos under a configured, unskipped folder
    `trust_rows`   the memory was emptied ON PURPOSE (a clear): its silence
                   settles nothing

    🚨 WHICH COPY WINS IS DECIDED PER VIDEO. It was one flag for the whole list
    (ADVERSARY 2026-09-22), and every way that was wrong reached a person:

      A4   a look-again on ONE row made every stale snapshot row beat memory --
           a row just paired or blacklisted came back asking
      A14  a run SETTLED a remembered problem, and memory's stale copy still
           asked, because the run's rows were filtered to problems first
      A26  a run over a folder not in Settings: memory cannot list it, so its
           absence read as "settled since"
      A27  after *Clear hato's memory*, an empty memory "settled" every row
      A7   two spellings of one video were two rows

    ⭐ The newer copy of a row wins; a newer row that is NO problem settles the
    video. A problem row the newer memory does not list was settled since -- a
    pick landed, a subtitle appeared -- unless the memory could not have held
    it: a clash or a two-episode name records nothing, a video outside the
    configured folders is never listed, and a cleared memory holds nothing.
    """
    run = OrderedDict()
    for row in rows:
        key = problem_key(row)
        if key:
            run[key] = row                  # ⭐ A7: one video, one row, the latest copy
    memory = OrderedDict()
    for row in (remembered or ()):
        if problem_kind(row):
            memory[problem_key(row)] = row
    live = set(live or ())
    out, seen = [], set()
    for key, row in run.items():
        newer = remembered is None or rows_newer or key in live
        kind = problem_kind(row)
        if key in memory:
            seen.add(key)
            if not newer:
                out.append(memory[key])
            elif kind:
                out.append(row)
            continue                        # ⭐ A14: newer, and no problem: settled
        if not kind:
            continue
        if (newer or trust_rows or not _remembered_by_the_db(row)
                or (in_scope is not None and not in_scope(row))):
            out.append(row)
        # else: the newer memory would list it, and does not -- settled since
    out.extend(r for k, r in memory.items() if k not in seen)
    return out


def tally(rows, problems, done=()):
    u"""-> {interface word: n}: THE count behind the badge and the footer.

    🚨 IT PARTITIONS what the window shows -- the run's rows and the remembered
    problems, each VIDEO once. A problem is counted by its KIND: a pick still
    waiting is NEEDS_YOU, a wait NOT_YET, the rest FAILED. ⚠ A retrying skip
    therefore leaves "skipped" -- it is waiting on a person, not settled.
    ⭐ A pick that LANDED (`done`, keys) is ADDED: a subtitle was written. It used
    to be counted nowhere, and the footer's numbers summed to less than the
    rows on screen (ADVERSARY 2026-09-22 A15). Left out, and nothing else: a
    problem row the newer memory says was settled since.
    """
    out = dict((word, 0) for word in interface_words())
    current = OrderedDict((problem_key(r), r) for r in problems)
    done = set(done)
    counted = set()
    for row in rows:
        key = problem_key(row)
        if key in counted:
            continue                        # ⚠ A7: once per video
        counted.add(key)
        if key in current or key in done or problem_kind(row):
            continue                        # counted below, or settled since
        out[outcome_word(row)] += 1
    for key, row in current.items():
        if key in done:
            continue
        kind = problem_kind(row)
        out[NEEDS_YOU if kind == PICK else NOT_YET if kind == WAITING else FAILED] += 1
    out[ADDED] += len(done)
    return out


def retry_due(row):
    u"""-> the aware datetime hato looks again at, or None."""
    text = row.get(u"retry_after")
    if not text:
        return None
    try:
        from datetime import datetime, timezone
        moment = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _span(seconds):
    if seconds < 60:
        return u"in a moment"
    if seconds < 3600:
        return u"in %dm" % -(-int(seconds) // 60)
    if seconds < 48 * 3600:
        return u"in %dh" % -(-int(seconds) // 3600)
    return u"in %d days" % -(-int(seconds) // 86400)


def next_daily(at, after):
    u"""The first moment at or after `after` that the LOCAL clock reads `at`.
    -> an aware datetime

    ⚠ `after` is aware (the retry dates are UTC on the wire) and `at` is the
    wall clock Task Scheduler fires on -- the machine's own zone.
    """
    from datetime import timedelta
    local = after.astimezone()
    hour, minute = (int(part) for part in at.split(u":"))
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start < local:
        start += timedelta(days=1)
    return start


def next_run_text(daily, now):
    u"""*"next run in 15h"* while a daily run is registered, else u"" (D2). -> text

    ⚠ `daily` is `State.daily()` -- the time only while a task EXISTS. A time
    with nothing registered at it has no next run, and saying one is the lie the
    D2 shot caught (*"next run in 4 hours"* beside a switch that was off).
    """
    if not daily:
        return u""
    return u"next run %s" % _span((next_daily(daily, now) - now).total_seconds())


def daily_run_text(on, at, watch, supported=True):
    u"""What the daily run does, in one sentence (D2). -> text

    🚨 It said *"Windows wakes hato at that time"* over a switch that registered
    nothing. ⭐ A pure function of what Task Scheduler was READ to hold, so the
    card cannot claim a run the machine will not make.
    """
    if not supported:
        return (u"hato runs when you press Run now. To run it every day, schedule "
                u"hato --quiet with cron or a systemd timer.")
    if on:
        return (u"Windows starts hato at %s every day and it exits when it is done "
                u"— nothing sits running in between. If the computer is off or "
                u"asleep at that time, it runs when the computer is next on." % at)
    return (u"Off — nothing runs at a set time. hato runs when you press Run now%s."
            % (u", and when the tray sees a new video" if watch else u""))


def retry_text(row, now, watching, daily=None):
    u"""The wait, said honestly. -> text, or u"" when nothing is scheduled.

    🚨 THE RETRY WORKED AND TOLD NOBODY (4b) -- and it only ever happens when
    something RUNS hato after the date. The tray watcher wakes for it (RUNBOOK
    8h), so with the tray on the sentence is a promise: *"retrying in 14h"*.
    ⭐ D2 -- SO DOES THE DAILY RUN, once it is registered: `daily` is its time
    when it is on, and the retry happens at the first one on or after the date.
    ⛔ With neither, nothing runs on its own, so the sentence says when it
    BECOMES due, and the row keeps *Look again now* one click away.

    ⚠ Rounded UP: a sentence that says 13h over a wait of 13h40m is early by 40
    minutes, and early is the direction that reads as broken.
    """
    due = retry_due(row)
    if due is None:
        return u""
    left = (due - now).total_seconds()
    if watching:
        return u"retrying now" if left <= 0 else u"retrying %s" % _span(left)
    if daily:
        start = next_daily(daily, max(due, now))
        return u"retrying %s" % _span((start - now).total_seconds())
    if left <= 0:
        return u"retry due"
    return u"retry %s" % _span(left).replace(u"in ", u"after ", 1)


def waits_path():
    u"""-> where the window keeps the picks a person chose to wait on."""
    from hato import paths
    return paths.data_root() / u"window-waits.json"


def load_waits(path=None):
    u"""-> {video key: the retry date the person chose to wait for}. ⛔ Never raises."""
    import json
    target = path if path is not None else waits_path()
    try:
        with open(str(target), encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return dict((k, v) for k, v in payload.items()
                if isinstance(k, str) and isinstance(v, str) and k and v)


def save_waits(waits, path=None):
    u"""Keep the person's waits. -> the path, or None. ⛔ Temp-plus-rename; never raises."""
    import json
    target = path if path is not None else waits_path()
    try:
        target = os.fspath(target)
        os.makedirs(os.path.dirname(target) or u".", exist_ok=True)
        temp = u"%s.new-%d" % (target, os.getpid())
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(dict(waits or {}), handle, ensure_ascii=False)
        os.replace(temp, target)
        return target
    except (OSError, TypeError, ValueError):
        return None


def apply_waits(rows, waits, now):
    u"""⭐ HANDOFF 4c -- a pick the person chose to wait on becomes a WAIT. -> [row]

    *"a button ... it will search again in 24 hours"* -- the automatic path, made
    explicit. ⭐ HELD EXACTLY AS LONG AS THE RETRY IT WAS CHOSEN FOR: the key maps
    to that date, so a run that records a NEW one -- or the date passing -- puts
    the row back asking, highlighted again if it is still one past the newest.
    ⛔ The rows handed in are never changed; a waited one is a copy.
    """
    out = []
    for row in rows:
        chosen = (waits or {}).get(problem_key(row))
        due = retry_due(row)
        if (chosen and chosen == row.get(u"retry_after") and due is not None
                and due > now and problem_kind(row) == PICK):
            row = dict(row, waiting_by_choice=True)
        out.append(row)
    return out


def probably_not_out(row):
    u"""⭐ RUNBOOK 8f (HANDOFF 4c) -- one past the newest episode on offer? -> bool

    Then it is *probably not out yet*, and the row says so rather than
    presenting some other episode's files as the pick. ⛔ EXACTLY one past, and
    only with both numbers known: a gap of two is a missing episode, not a late
    one, and the window says nothing it cannot back. The pick stays available.
    """
    episode, newest = row.get(u"episode"), row.get(u"newest_offered")

    def whole(value):
        return isinstance(value, int) and not isinstance(value, bool)

    return bool(whole(episode) and whole(newest) and episode == newest + 1)


def found_on_retry(row):
    u"""Was this subtitle found only after earlier files did not line up? -> bool

    ⭐ 4b's third clause, *say that it happened*: the pipeline keeps what was
    refused on the way (`tried_before`) on the success that followed it.
    """
    return bool(row.get(u"outcome") == CONFIDENT and row.get(u"output_path")
                and row.get(u"tried_before"))


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
        u"""Exit 2: the command itself could not be run -- usage, no key."""
        return self.code == EXIT_CANNOT_RUN

    @property
    def stopped(self):
        u"""🚨 Exit 1: the run STOPPED part-way -- a 401, a server gone, a crash.
        ⛔ Not *"something needs a pick"*: a run with picks exits 0 (A12)."""
        return self.code == EXIT_STOPPED

    @property
    def said(self):
        u"""The first thing the child said on stderr, without its `hato:`. -> text"""
        for line in self.notes:
            line = (line or u"").strip()
            if line:
                return line[len(u"hato:"):].strip() if line.startswith(u"hato:") else line
        return u""

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
        return self._read_pipes()

    @classmethod
    def adopt(cls, process, argv=None):
        u"""Read a child somebody else started. -> Runner

        ⭐ RUNBOOK 8e. The window starts every child through ONE seam (`spawn`),
        which the suite replaces; a pick, the remembered problems and the
        blacklist are children it must also READ. Adopting the process keeps
        that one seam, and the two reader threads below still drain both pipes
        -- ⚠ a child printing more than a pipe holds would otherwise block for
        ever, and `hato problems` can.
        """
        runner = cls(argv=list(argv or ()))
        runner._process = process
        return runner._read_pipes()

    def _read_pipes(self):
        for stream, sink in ((self._process.stdout, self._on_stdout),
                             (self._process.stderr, self._on_stderr)):
            if stream is None:
                continue
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
           "INSIDE_VIDEO", "RETRYING", "CANT_SYNC", "ON_SKIP_LIST",
           "SKIP_WORDS", "is_skipped",
           "EXIT_CLEAN", "EXIT_STOPPED", "EXIT_CANNOT_RUN",
           "COMMAND_LINE_BUDGET", "only_list_file",
           "PICK_OVERRIDES_TIMING", "PAIRED", "FORCED", "PICK_REFUSED", "PICK_FAILED",
           "PICK", "WAITING", "TROUBLE",
           "Run", "Runner", "apply_waits", "argv_for", "argv_for_blacklist",
           "argv_for_clear", "argv_for_config", "argv_for_update", "blacklist_entries",
           "load_waits",
           "memory_summary", "save_waits", "waits_path",
           "argv_for_pair", "argv_for_problems", "argv_for_retry",
           "candidates_of", "child_env", "cli_argv", "counts", "found_on_retry",
           "interface_words", "is_format_wait", "last_run_stamp", "load_last_run",
           "match_percent",
           "needs_you", "no_console_kwargs", "outcome_word", "parse_answer",
           "pick_verdict", "probably_not_out", "problem_key", "problem_kind",
           "retry_due", "retry_text",
           "save_last_run", "tally"]
