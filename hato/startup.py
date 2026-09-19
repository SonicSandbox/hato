# -*- coding: utf-8 -*-
u"""Run hato when Windows starts. RUNBOOK 7h.

    from hato import startup
    startup.is_enabled()      is there a login entry?
    startup.enable()          put one there (overwrites -- see below)
    startup.disable()         take it away

===========================================================================
🚨 WINDOWS IS THE ONLY SOURCE OF TRUTH -- AND IT ANSWERS IN TWO PLACES
===========================================================================

⛔ A `start_with_windows = true` in `config.toml` would be a SECOND answer to
a question Windows already answers, and the two drift the moment anybody
edits their startup items in Task Manager, Settings or a cleaner -- which
people do. hato would then show a switch that was on while nothing ran.

⭐ So `is_enabled()` ASKS WINDOWS, never a file hato wrote.

🚨 BUT THE `Run` VALUE ALONE IS NOT THE ANSWER, and this module claimed it
was. Measured 2026-09-18 on this machine: Task Manager's *Disable* does NOT
delete the Run value -- it records the decision in

    ...\\Explorer\\StartupApproved\\Run

as a binary blob (16 names present here: Discord, Steam, Taiga, …). ⛔ So a
reader of `Run` alone produces the EXACT nightmare the paragraph above names
as its reason for trusting the registry: the switch reads ON while Windows
has quietly turned hato off. Worse, toggling off and on rewrites `Run` and
does NOT clear the approval byte, so the obvious repair does not repair.

⚠ `approved()` reads that second key. `is_enabled()` is the AND of both.

===========================================================================
🚨 IT STARTS THE TRAY WATCHER, NOT THE WINDOW
===========================================================================

The point of starting with Windows is that hato watches folders *without you
doing anything* -- which is the watcher's whole job. ⛔ Registering the window
would throw a window in somebody's face at every login, which is the opposite
of a background tool. The tray's *Open hato* is how the window is reached.

===========================================================================
⚠ WHAT GETS REGISTERED IS NOT THE SAME COMMAND ON BOTH HOSTS
===========================================================================

  frozen   <bundle>/hato-watch.exe          -- absolute, self-contained
  source   pythonw.exe "<repo>/hato-watch.pyw"

⛔ AND THE SOURCE ONE IS NOT `-m hato.watch`. Measured 2026-09-18: `hato` is
not installed as a distribution, so `import hato` fails from any directory
but its own -- and a registry entry runs with a working directory of
Windows' choosing. `-m hato.watch` would raise `ModuleNotFoundError` at every
login, with **no console to print it to**, so nothing whatever would appear.
`hato-watch.pyw` exists precisely because a script's own folder goes on
`sys.path`.
"""
from __future__ import print_function

import os
import subprocess
import sys

#: Where Windows keeps per-user login commands. ⛔ HKEY_CURRENT_USER, never
#: LOCAL_MACHINE: this is one person's preference and needs no elevation.
RUN_KEY = u"Software\\Microsoft\\Windows\\CurrentVersion\\Run"

#: 🚨 Windows' own record of which startup entries a person has switched off.
#: Task Manager and Settings > Startup Apps write here and LEAVE the `Run`
#: value alone, so reading `Run` by itself reports hato as starting when it
#: will not. Measured 2026-09-18: this key exists on this machine and holds
#: 16 names.
APPROVED_KEY = (u"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer"
                u"\\StartupApproved\\Run")

#: ⚠ The value name is the identity of the entry. Changing it orphans whatever
#: an older hato registered, leaving a login command nothing will ever remove.
VALUE_NAME = u"hato"


class StartupError(Exception):
    u"""The login entry could not be read or written. The message says why."""


def supported():
    u"""-> True where a login entry can be registered at all."""
    return sys.platform.startswith(u"win")


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _windowless(executable):
    u"""python.exe -> pythonw.exe. -> str

    ⚠ A console interpreter at login flashes a black window on every boot.
    ⛔ Only swaps when the w-variant is really there; a guess that misses
    would register a path to nothing.
    """
    folder, name = os.path.split(executable)
    if name.lower() == u"python.exe":
        candidate = os.path.join(folder, u"pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return executable


def command():
    u"""The exact command line Windows should run at login. -> str

    ⭐ Quoted by `subprocess.list2cmdline`, which is Windows' own rule -- and
    this path has spaces in it on the machine it was written on. ⛔ Hand-built
    quoting is how a registry entry silently becomes two arguments.
    """
    if getattr(sys, u"frozen", False):
        exe = os.path.join(os.path.dirname(sys.executable),
                           u"hato-watch.exe" if supported() else u"hato-watch")
        return subprocess.list2cmdline([exe])
    return subprocess.list2cmdline(
        [_windowless(sys.executable),
         os.path.join(_repo_root(), u"hato-watch.pyw")])


def registered():
    u"""What Windows would actually run at login. -> str, or None.

    ⚠ Never raises for *"there is no entry"* -- that is an answer, not a
    fault. It raises only when the registry itself cannot be read.
    """
    if not supported():
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None                           # no key, or no value in it
    except OSError as exc:
        raise StartupError(
            u"hato could not read Windows' startup list (%s). "
            u"Start hato yourself, or add it in Task Manager > Startup." % exc)


def approved():
    u"""Has Windows' own startup list turned our entry off? -> True/False/None

    `True` approved · `False` explicitly disabled · `None` no opinion recorded
    (the ordinary case — Windows only writes a byte here once somebody has
    used Task Manager or Settings on this entry).

    ⚠ THE FORMAT IS A BINARY BLOB AND THE FIRST BYTE CARRIES THE DECISION.
    Observed values are `02` and `06` for enabled and `03` for disabled, so
    the low bit is the flag: odd means disabled. ⛔ Anything unreadable is
    reported as `None` — *no opinion* — rather than guessed at, because
    guessing "disabled" would switch hato off for somebody whose registry
    simply holds a shape this did not expect.
    """
    if not supported():
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0,
                            winreg.KEY_READ) as key:
            data, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        return not (data[0] & 0x01)
    except (TypeError, IndexError, KeyError):
        return None


def is_enabled():
    u"""-> True when hato will actually be started by Windows at login.

    🚨 BOTH KEYS. An entry that exists in `Run` but has been switched off in
    Task Manager is NOT enabled, and reporting it as enabled is the precise
    failure this module's header warns about.
    """
    if registered() is None:
        return False
    return approved() is not False


def is_stale():
    u"""-> True when an entry exists but names a DIFFERENT command.

    ⭐ Which happens the moment somebody moves the folder, or switches from
    the clone to the exe. ⛔ The entry still exists, so the switch reads ON
    while the thing it names may no longer be there. `enable()` overwrites,
    so toggling off and on repairs it.
    """
    current = registered()
    return current is not None and current != command()


def enable():
    u"""Register hato's tray watcher to start at login. -> the command written.

    ⛔ OVERWRITES rather than refusing when one already exists: that is what
    makes this repair a stale entry instead of leaving two ideas of where
    hato lives.
    """
    if not supported():
        raise StartupError(
            u"starting with the computer is a Windows feature; on this system "
            u"add hato to your desktop's own startup applications.")
    import winreg
    line = command()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, line)
    except OSError as exc:
        raise StartupError(
            u"hato could not add itself to Windows' startup list (%s)." % exc)
    return line


def disable():
    u"""Remove the login entry. -> True when one was removed.

    ⚠ Absent is SUCCESS. Turning off something already off is not an error,
    and raising here would make the switch fail for a person whose entry a
    cleaner had already taken away.
    """
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StartupError(
            u"hato could not remove itself from Windows' startup list (%s)."
            % exc)


def set_enabled(on):
    u"""The switch's one call. -> True when hato now starts with Windows."""
    if on:
        enable()
        return True
    disable()
    return False


__all__ = ["APPROVED_KEY", "RUN_KEY", "VALUE_NAME", "StartupError",
           "approved", "command", "disable", "enable", "is_enabled",
           "is_stale", "registered", "set_enabled", "supported"]
