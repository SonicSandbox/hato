# -*- coding: utf-8 -*-
u"""Run hato every day at a set time -- the Windows scheduled task. D2.

    from hato import schedule
    task = schedule.read()          what Task Scheduler holds under hato's name
    schedule.is_enabled(task)       will Windows start the daily run?
    schedule.enable(u"03:00")       register it (overwrites -- see below)
    schedule.disable()              take it away
    schedule.note(task)             what the switch must say, or u""

===========================================================================
🚨 THE SWITCH READ ON FOR FIVE DAYS AND NOTHING WAS REGISTERED (D2)
===========================================================================

The title bar said *"runs automatically at 03:00"* over a switch that was on
in every screenshot, and Settings said *"Windows wakes hato at that time"*.
No task existed -- measured 2026-09-22 (`schtasks /query /tn hato` finds
nothing, and not one of 148 recorded attempts is near 03:00). The switch was
drawn from `bool(cfg.schedule)`, which is always true, and turning it off sent
`schedule=off`, which the config refuses by name -- so it could not even be
turned off.

⭐ SO, EXACTLY AS `hato/startup.py`: TASK SCHEDULER IS THE ONLY STATE. There
is no config key saying whether the daily run is on; the switch reads the task
on every open. `schedule` in config.toml is only the TIME to register at.

===========================================================================
🚨 THE BATTERY TRAP -- measured 2026-09-17, and it is the one that ships
===========================================================================

A task registered with the defaults does not start on battery, and one that
never ran reports `Last Result: 0` -- the scheduler's value for *never ran* is
its value for *succeeded*. ⭐ The task is written from XML that says so
outright (`DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries` false,
`StartWhenAvailable` true), and every registration is READ BACK and those
values checked: a hand-made task named hato that lacks them reads as needing
repair, never as fine.

===========================================================================
⭐ IT STARTS A WINDOWLESS PROGRAM, NEVER THE COMMAND LINE
===========================================================================

Task Scheduler runs a console program in a console WINDOW, over whatever the
person is doing -- and with *start when available* the run a sleeping computer
missed at 03:00 happens the moment somebody is using it. So the task starts
the tray watcher's program with `--scheduled` (`hato-watch.exe`, or `pythonw`
and `hato-watch.pyw` from a clone -- `startup.watcher_argv`, the one answer to
*"how does something outside hato start it"*), which runs hato the way the
tray runs it: no console, no busy cursor, and its exit code handed back.

===========================================================================
🚨 schtasks CANNOT SAY A NON-ASCII PATH
===========================================================================

Measured 2026-09-23: `schtasks /query /xml` DECLARES `encoding="UTF-16"` and
writes the console's OEM code page. A command registered under
`...\\Michaël 日本 & co\\...` came back `...\\Michaël ?? &amp; co\\...`. The task
file itself is faithful but is Windows' private store, and PowerShell's export
is faithful but took 2.4 s. ⭐ So schtasks is the only reader, and a command
is compared on its ASCII skeleton (`_same`) -- which can miss a move between
two paths differing only in non-ASCII letters, and can never raise a false
*"switch it off and on"* that switching off and on would not clear.
"""
from __future__ import print_function

import datetime
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from hato import startup
#: ⛔ The contract with `hato/watch.py`'s `main`, which starts the daily run when
#: handed it -- imported, never restated. (`hato.watch` imports only the stdlib
#: at load, so this costs the window nothing.)
from hato.watch import SCHEDULED_FLAG

def escape(text):
    u"""XML's three -- `&` first, then `<` and `>`: what `xml.sax.saxutils.escape`
    does. ⭐ RUNBOOK 13i -- ITS OWN, because that module imports `urllib.request` and
    `http.client` for this one call: 139 ms on every window start, before it shows
    (`settings_from_disk` reads the schedule)."""
    return text.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


#: ⚠ The task's name is its identity. Changing it orphans whatever an older hato
#: registered: a daily run nothing will ever remove, and a switch reading OFF
#: over it. `HATO_TASK_NAME` exists for the suite and the build's own probes.
TASK_NAME = u"hato"

_NS = u"{http://schemas.microsoft.com/windows/2004/02/mit/task}"

#: What `read()` found. `readable` False means a task EXISTS under hato's name and
#: its definition could not be parsed -- it still runs, so it is not "off".
_FIELDS = (u"at", u"enabled", u"command", u"arguments", u"on_battery_ok",
           u"catches_up", u"daily", u"readable")


class ScheduleError(Exception):
    u"""Task Scheduler could not be asked, or refused. The message says why."""


class Task(object):
    u"""The daily run as Task Scheduler reads it back. Plain data."""

    def __init__(self, **values):
        for name in _FIELDS:
            setattr(self, name, values.get(name))

    def __repr__(self):
        return u"Task(%s)" % u", ".join(u"%s=%r" % (n, getattr(self, n)) for n in _FIELDS)


def supported():
    u"""-> True where a scheduled task can be registered at all."""
    return sys.platform.startswith(u"win")


def task_name():
    return os.environ.get(u"HATO_TASK_NAME") or TASK_NAME


def command_argv():
    u"""What the daily task runs. -> [str]

    ⭐ `startup.watcher_argv()` plus one flag -- the login entry and the daily
    run start the same windowless program, resolved in one place.
    """
    return startup.watcher_argv() + [SCHEDULED_FLAG]


def next_start(at, now=None):
    u"""The next moment the clock reads `at`. -> datetime

    🚨 NEVER A MOMENT ALREADY PAST. A task whose start boundary is behind it, with
    *run when available* set, may treat that start as MISSED and run the moment
    it is registered -- so turning the switch on at 14:00 would start a run at
    14:00. ⛔ Today when it is still ahead; otherwise tomorrow.
    """
    now = now or datetime.datetime.now()
    hour, minute = (int(part) for part in at.split(u":"))
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start <= now:
        start += datetime.timedelta(days=1)
    return start


def task_xml(at, argv, now=None):
    u"""The task, as Task Scheduler's own XML. -> text

    ⭐ Every setting the battery trap turns on is written OUT, not left to a
    default: `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` false,
    `StartWhenAvailable` true. ⛔ `WakeToRun` false -- hato never wakes a
    sleeping computer; the run happens when it is next on.
    ⚠ No `UserId`: registered by the person, for the person (measured: it lands
    under their own SID, unelevated). ⚠ No working directory: hato's paths are
    absolute by rule, and Task Scheduler's own choice is the one it must survive.
    """
    arguments = subprocess.list2cmdline(list(argv[1:]))
    return u"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>hato's daily run: finds Japanese subtitles for new videos in your folders. Added by the "runs automatically" switch in hato -- turn it off there.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>%s</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>%s</Command>%s
    </Exec>
  </Actions>
</Task>
""" % (next_start(at, now).strftime(u"%Y-%m-%dT%H:%M:%S"),
       escape(argv[0]),
       (u"\n      <Arguments>%s</Arguments>" % escape(arguments)) if arguments else u"")


def _codec():
    u"""The code page schtasks writes its output in. -> a codec name

    ⚠ The console's OEM page, whatever its XML declares (see the header). A
    double-byte one (cp932) matters: decoded as cp437 every Japanese letter
    would read as two, and every comparison after it would fail.
    """
    try:
        import ctypes
        codec = u"cp%d" % ctypes.windll.kernel32.GetOEMCP()
        u"".encode(codec)
        return codec
    except Exception:                         # noqa: BLE001
        return u"cp437"


def _schtasks(*args):
    u"""Run schtasks.exe. -> (exit code, stdout bytes, stderr bytes)

    ⛔ `HATO_NO_SCHEDULER=1` (the suite sets it) refuses before anything runs:
    a check must never register a real task on the machine it runs on.
    ⚠ Spawned the way the tray spawns a run -- no console, no busy cursor. From
    the window, a console child would flash a black window on every click.
    """
    if os.environ.get(u"HATO_NO_SCHEDULER") == u"1":
        raise ScheduleError(
            u"HATO_NO_SCHEDULER=1 -- Task Scheduler is switched off here, so "
            u"nothing was asked or changed.")
    from hato.watch import no_console_kwargs
    exe = os.path.join(os.environ.get(u"SystemRoot", u"C:\\Windows"),
                       u"System32", u"schtasks.exe")
    if not os.path.isfile(exe):
        exe = u"schtasks.exe"
    try:
        done = subprocess.run([exe] + list(args), capture_output=True,
                              timeout=60, **no_console_kwargs())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScheduleError(u"hato could not reach Task Scheduler (%s)." % exc)
    return done.returncode, done.stdout, done.stderr


def _said(raw):
    u"""What schtasks printed, as a sentence. -> text"""
    text = (raw or b"").decode(_codec(), u"replace").strip()
    # ⚠ Its own full stop goes: the sentence it lands in has one (LOOKED -- the
    # D2 shot read *"(Access is denied.)."*).
    return re.sub(u"^ERROR:\\s*", u"", text).rstrip(u". ") or u"no reason given"


def parse(text):
    u"""schtasks' XML -> a `Task`. ⛔ Never raises: an unparsable definition is
    a task that EXISTS and could not be read (`readable=False`)."""
    body = re.sub(u"^\\s*<\\?xml[^>]*\\?>", u"", text or u"")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        # ⚠ IT EXISTS, and Task Scheduler runs what exists -- so not "off".
        return Task(readable=False, enabled=True)

    def text_of(path, under=None):
        node = (under if under is not None else root).find(_qualified(path))
        return node.text.strip() if node is not None and node.text else None

    triggers = root.find(_qualified(u"Triggers"))
    trigger_nodes = list(triggers) if triggers is not None else []
    calendar = trigger_nodes[0] if len(trigger_nodes) == 1 else None
    if calendar is not None and calendar.tag != _NS + u"CalendarTrigger":
        calendar = None
    at = None
    daily = False
    trigger_on = True
    if calendar is not None:
        match = re.search(u"T(\\d{2}):(\\d{2})", text_of(u"StartBoundary", calendar) or u"")
        at = u"%s:%s" % match.groups() if match else None
        by_day = calendar.find(_qualified(u"ScheduleByDay"))
        daily = by_day is not None and (text_of(u"DaysInterval", by_day) or u"1") == u"1"
        trigger_on = (text_of(u"Enabled", calendar) or u"true") != u"false"
    settings = root.find(_qualified(u"Settings"))

    def setting(name, default):
        value = text_of(name, settings) if settings is not None else None
        return (value or default).lower() == u"true"

    return Task(
        at=at,
        daily=daily,
        # ⚠ ABSENT MEANS ENABLED. Task Scheduler writes `<Enabled>false</Enabled>`
        # only once somebody has disabled it -- measured.
        enabled=setting(u"Enabled", u"true") and trigger_on,
        command=text_of(u"Actions/Exec/Command"),
        arguments=text_of(u"Actions/Exec/Arguments") or u"",
        # ⛔ THE DEFAULTS ARE THE TRAP: absent means DO NOT start on battery.
        on_battery_ok=(not setting(u"DisallowStartIfOnBatteries", u"true")
                       and not setting(u"StopIfGoingOnBatteries", u"true")),
        catches_up=setting(u"StartWhenAvailable", u"false"),
        readable=True)


def _qualified(path):
    return u"/".join(_NS + part for part in path.split(u"/"))


def read():
    u"""What Task Scheduler holds under hato's name. -> `Task`, or None.

    ⚠ None is *"no task"* -- and also *"schtasks could not answer"*: its exit
    code is 1 for both and its message is in the machine's language. ⭐ That
    fails CLOSED: the switch reads OFF, and turning it on then either works or
    says what Task Scheduler said. Never ON over something nobody could see.
    ⛔ Under `HATO_NO_SCHEDULER=1` nothing is asked and the answer is None -- a
    check must not read the developer's own daily run and change its verdict.
    """
    if not supported() or os.environ.get(u"HATO_NO_SCHEDULER") == u"1":
        return None
    code, out, _err = _schtasks(u"/query", u"/tn", task_name(), u"/xml")
    if code != 0:
        return None
    return parse(out.decode(_codec(), u"replace"))


def _same(ours, theirs):
    u"""Is what Task Scheduler READ BACK the text hato would write? -> bool

    ⭐ THE ASCII SKELETON (header): every ASCII character of OURS must come back
    as itself, ignoring case as Windows does; a non-ASCII one of ours may come
    back as anything -- `?`, a best-fit letter, or itself. Counted in UTF-16
    units, which is what schtasks converts, so a letter outside the BMP is two.
    ⛔ ONLY OUR SIDE IS A WILDCARD. An ASCII letter never turns into anything
    else, so a non-ASCII one where ours is ASCII is a different path (`Musik`
    against `Müsik`) -- found when the gate's list was written: a wildcard on
    THEIR side matched it, and a `?` of theirs could never meet an ASCII of ours.
    """
    if theirs is None:
        return False
    raw = ours.encode(u"utf-16-le")
    units = [int.from_bytes(raw[i:i + 2], u"little") for i in range(0, len(raw), 2)]
    if len(units) != len(theirs):
        return False
    for unit, seen in zip(units, theirs):
        if unit > 127:
            continue
        if chr(unit).lower() != seen.lower():
            return False
    return True


def problems(task, argv=None):
    u"""What is wrong with the daily run as registered. -> [sentence]

    ⭐ Each says what to do about it, and for all but the first the answer is
    the same: turning the switch off and on registers hato's own task again.
    """
    if task is None:
        return []
    if not task.readable:
        return [u"hato cannot read its daily run back from Task Scheduler — "
                u"switch it off and on to set it up again."]
    argv = list(argv or command_argv())
    said = []
    if not task.enabled:
        said.append(u"It is switched off in Task Scheduler — switching it on here "
                    u"turns it back on.")
    if not (_same(argv[0], task.command)
            and _same(subprocess.list2cmdline(argv[1:]), task.arguments)):
        said.append(u"The daily run starts a different copy of hato — switch it off "
                    u"and on to point it here.")
    if not task.on_battery_ok:
        said.append(u"The daily run is set not to start on battery — switch it off "
                    u"and on to fix that.")
    if not task.catches_up:
        said.append(u"A daily run the computer is asleep for is skipped — switch it "
                    u"off and on so it runs when the computer is next on.")
    if not (task.daily and task.at):
        said.append(u"The daily run was changed in Task Scheduler — switch it off "
                    u"and on to set it back to every day.")
    return said


def note(task, argv=None):
    u"""The one sentence the switch shows, or u"" when all is well."""
    said = problems(task, argv)
    return said[0] if said else u""


def is_enabled(task=None):
    u"""-> True when Windows will start hato's daily run.

    ⚠ A task switched off in Task Scheduler EXISTS and is not enabled -- the
    same shape as Task Manager's *Disable* in `startup.py`.
    """
    task = read() if task is None else task
    return task is not None and bool(task.enabled)


def enable(at, argv=None, now=None):
    u"""Register the daily run at `at` (HH:MM). -> the task, READ BACK.

    ⛔ OVERWRITES (`/f`): that is what repairs a stale or hand-made task
    instead of leaving two ideas of when hato runs.
    ⭐ READ BACK AFTER THE WRITE. A refusal and a success can look alike; a
    task that is not there afterwards is an error, and one that differs is
    left for `note` to describe.
    """
    from hato import config as _config
    if not supported():
        raise ScheduleError(
            u"a daily run is registered with Windows' Task Scheduler; on this "
            u"system schedule `hato --quiet` with cron or a systemd timer.")
    if not _config.is_clock(at):
        raise ScheduleError(u"%r is not a time — use 24-hour, like 03:00." % (at,))
    argv = list(argv or command_argv())
    # ⚠ A FRESH, UNIQUE file: nothing existing is truncated, and it is removed
    # whatever schtasks says. UTF-16 with its BOM, as Task Scheduler reads it.
    handle, path = tempfile.mkstemp(prefix=u"hato-task-", suffix=u".xml")
    try:
        with os.fdopen(handle, u"w", encoding=u"utf-16") as out:
            out.write(task_xml(at, argv, now))
        code, _out, err = _schtasks(u"/create", u"/tn", task_name(),
                                    u"/xml", path, u"/f")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if code != 0:
        raise ScheduleError(u"Task Scheduler would not add hato's daily run (%s)."
                            % _said(err))
    task = read()
    if task is None:
        raise ScheduleError(u"Task Scheduler said the daily run was added, and "
                            u"it is not there.")
    return task


def disable():
    u"""Remove the daily run. -> True when one was removed.

    ⚠ Absent is SUCCESS: turning off something already off is not an error.
    """
    if not supported():
        return False
    code, _out, err = _schtasks(u"/delete", u"/tn", task_name(), u"/f")
    if code == 0:
        return True
    if read() is None:
        return False
    raise ScheduleError(u"Task Scheduler would not remove hato's daily run (%s)."
                        % _said(err))


def set_enabled(on, at):
    u"""The switch's one call. -> True when the daily run is now on."""
    if on:
        return is_enabled(enable(at))
    disable()
    return False


__all__ = ["SCHEDULED_FLAG", "ScheduleError", "TASK_NAME", "Task", "command_argv",
           "disable", "enable", "is_enabled", "next_start", "note", "parse",
           "problems", "read", "set_enabled", "supported", "task_name", "task_xml"]
