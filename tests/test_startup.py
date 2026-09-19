# -*- coding: utf-8 -*-
u"""
Does hato start with Windows, and does it register something that WORKS?

===========================================================================
🚨 NOTHING HERE WRITES TO THE REAL REGISTRY
===========================================================================

⛔ A suite that adds a real login entry would change the developer's machine
and leave it changed -- the same class as the run that once wrote a live pid
into the real per-user store and tripped the runner's isolation guard. Every
check below either reads, or drives an injected fake.

===========================================================================
⭐ THE CHECK THAT MATTERS IS THE SOURCE COMMAND
===========================================================================

`hato` is NOT installed as a distribution -- measured 2026-09-18, `import
hato` raises `ModuleNotFoundError` from any directory but its own. So a login
entry running `pythonw -m hato.watch` would fail at every boot, and fail
INVISIBLY: `pythonw` has no console, so the traceback goes nowhere and the
person sees a feature that simply does not happen.

That is why `hato-watch.pyw` exists at the repository root -- Python puts a
script's own folder on `sys.path`. ⛔ If someone ever "simplifies" the command
back to `-m`, these checks are what says no.
"""
import os
import subprocess
import sys

import pytest

from hato import startup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# the command -- the whole feature is whether this line works at login
# ---------------------------------------------------------------------------

def test_the_launcher_it_names_actually_exists():
    u"""⛔ The one file the source command depends on."""
    assert os.path.isfile(os.path.join(ROOT, u"hato-watch.pyw"))


def test_from_source_it_runs_the_LAUNCHER_never_dash_m(monkeypatch):
    u"""🚨 `-m hato.watch` AT LOGIN IS A SILENT ModuleNotFoundError."""
    monkeypatch.setattr(sys, u"frozen", False, raising=False)
    line = startup.command()
    assert u"hato-watch.pyw" in line
    assert u"-m" not in line.split(), line
    assert u"hato.watch" not in line.replace(u"hato-watch.pyw", u""), line


def test_from_source_the_launcher_path_is_ABSOLUTE(monkeypatch):
    u"""⚠ A login entry runs with a working directory of Windows' choosing, so
    a relative path resolves against somewhere nobody chose."""
    monkeypatch.setattr(sys, u"frozen", False, raising=False)
    line = startup.command()
    tail = line.rsplit(u"hato-watch.pyw", 1)[0]
    assert os.path.isabs(tail.strip().strip(u'"').rstrip(u"\\/") + u"/x")


def test_frozen_it_runs_the_watcher_exe_beside_the_bundle(monkeypatch, tmp_path):
    u"""⛔ NOT `hato.exe` -- that is the WINDOW, and registering it would throw
    a window in somebody's face at every login."""
    monkeypatch.setattr(sys, u"frozen", True, raising=False)
    monkeypatch.setattr(sys, u"executable", str(tmp_path / u"hato.exe"))
    line = startup.command()
    assert u"hato-watch" in line
    assert u"hato-watch.pyw" not in line
    assert u"-m" not in line.split()
    # ⛔ and it must not merely be `hato.exe`, which is the window
    assert not line.strip().strip(u'"').endswith(u"hato.exe"), line


def test_the_command_is_quoted_for_windows(monkeypatch, tmp_path):
    u"""⚠ `list2cmdline` is Windows' own rule. A path with a space that is not
    quoted silently becomes two arguments."""
    spaced = tmp_path / u"Program Folder"
    spaced.mkdir()
    monkeypatch.setattr(sys, u"frozen", True, raising=False)
    monkeypatch.setattr(sys, u"executable", str(spaced / u"hato.exe"))
    line = startup.command()
    assert line.startswith(u'"'), line
    assert subprocess.list2cmdline([line.strip(u'"')]) is not None


def test_python_exe_becomes_pythonw_only_when_it_is_really_there(tmp_path):
    u"""⛔ A guess that misses registers a path to nothing."""
    plain = tmp_path / u"python.exe"
    plain.write_text(u"", encoding=u"utf-8")
    # no pythonw beside it -> leave it alone
    assert startup._windowless(str(plain)) == str(plain)
    (tmp_path / u"pythonw.exe").write_text(u"", encoding=u"utf-8")
    assert startup._windowless(str(plain)).endswith(u"pythonw.exe")


# ---------------------------------------------------------------------------
# the switch's contract
# ---------------------------------------------------------------------------

def test_turning_it_off_when_it_is_already_off_is_NOT_an_error(monkeypatch):
    u"""⚠ A cleaner may have removed the entry already. Raising here would make
    the switch fail for somebody whose machine is in a perfectly fine state."""
    monkeypatch.setattr(startup, u"supported", lambda: False)
    assert startup.disable() is False


def test_set_enabled_reports_what_it_did(monkeypatch):
    calls = []
    monkeypatch.setattr(startup, u"enable", lambda: calls.append(u"on"))
    monkeypatch.setattr(startup, u"disable", lambda: calls.append(u"off"))
    assert startup.set_enabled(True) is True
    assert startup.set_enabled(False) is False
    assert calls == [u"on", u"off"]


def test_off_windows_the_feature_refuses_with_an_INSTRUCTION(monkeypatch):
    u"""⛔ *"Not supported"* is a refusal. It has to say what to do instead."""
    monkeypatch.setattr(startup, u"supported", lambda: False)
    with pytest.raises(startup.StartupError) as caught:
        startup.enable()
    assert u"startup" in str(caught.value).lower()


# ---------------------------------------------------------------------------
# 🚨 the registry is the ONLY state -- there is no config key
# ---------------------------------------------------------------------------

def test_there_is_no_config_key_for_this():
    u"""⛔ A `start_with_windows` in config.toml would be a SECOND answer to a
    question Windows already answers, and the two drift the moment anybody
    edits their startup items in Task Manager -- leaving the switch ON while
    nothing runs."""
    import io

    from hato import config

    with io.open(config.__file__, encoding=u"utf-8") as handle:
        source = handle.read()
    for forbidden in (u"start_with_windows", u"start_with_win",
                      u"run_at_startup", u"launch_at_login"):
        assert forbidden not in source, (
            u"config.py declares %r -- the registry is the only state, see "
            u"hato/startup.py" % forbidden)

    # ⛔ NO `config.load()` HERE. It reads the real per-user config, which
    # would make this check depend on whatever is on the developer's machine
    # -- the environment-coupling that has already cost this project a suite
    # that passed alone and went red in the full run.


def test_is_enabled_is_just_registered_being_there(monkeypatch):
    monkeypatch.setattr(startup, u"registered", lambda: None)
    assert startup.is_enabled() is False
    monkeypatch.setattr(startup, u"registered", lambda: u"anything at all")
    assert startup.is_enabled() is True


def test_a_moved_install_reads_as_STALE(monkeypatch):
    u"""⭐ The entry still exists, so the switch reads ON -- while the thing it
    names may no longer be there. `enable()` overwrites, so the person can
    repair it by toggling."""
    monkeypatch.setattr(startup, u"registered",
                        lambda: u"C:\\somewhere\\else\\hato-watch.exe")
    assert startup.is_stale() is True
    monkeypatch.setattr(startup, u"registered", startup.command)
    assert startup.is_stale() is False
    monkeypatch.setattr(startup, u"registered", lambda: None)
    assert startup.is_stale() is False


# ---------------------------------------------------------------------------
# 🚨 A REGISTRY STAND-IN, BECAUSE THE REAL BODIES HAD ZERO COVERAGE
#
# ⛔ This file's header used to claim "every check below either reads, or
# drives an injected fake." There was no fake. `registered()`, `enable()` and
# `disable()` were never executed at all -- every check monkeypatched them
# away -- so these mutants were all green:
#   · `disable()`'s `except FileNotFoundError: return False` -> `raise`
#   · `enable()` writing REG_EXPAND_SZ instead of REG_SZ
#   · HKEY_CURRENT_USER -> HKEY_LOCAL_MACHINE (needs elevation; fails for
#     every ordinary user)
# ---------------------------------------------------------------------------

class FakeWinreg(object):
    u"""Enough of `winreg` to drive `startup.py` for real."""

    HKEY_CURRENT_USER = u"HKCU"
    HKEY_LOCAL_MACHINE = u"HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_EXPAND_SZ = 2

    class _Handle(object):
        u"""⚠ Remembers WHICH key it opened -- `startup` reads two of them and
        a fake that cannot tell them apart proves nothing about either."""

        def __init__(self, sub):
            self.sub = sub

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def __init__(self, values=None, key_exists=True, fail_with=None,
                 approved=None):
        self.keys = {startup.RUN_KEY: dict(values or {})}
        if approved is not None:
            self.keys[startup.APPROVED_KEY] = {startup.VALUE_NAME: approved}
        self.key_exists = key_exists
        self.fail_with = fail_with
        self.opened_roots = []
        self.kinds = {}

    @property
    def values(self):
        u"""The Run key, which is what most checks mean."""
        return self.keys[startup.RUN_KEY]

    def OpenKey(self, root, sub, reserved=0, access=0):
        self.opened_roots.append(root)
        if self.fail_with:
            raise self.fail_with
        if sub not in self.keys or not self.key_exists:
            raise FileNotFoundError(2, u"no such key")
        return self._Handle(sub)

    def CreateKeyEx(self, root, sub, reserved=0, access=0):
        self.opened_roots.append(root)
        if self.fail_with:
            raise self.fail_with
        self.key_exists = True
        self.keys.setdefault(sub, {})
        return self._Handle(sub)

    def QueryValueEx(self, handle, name):
        holder = self.keys.get(handle.sub, {})
        if name not in holder:
            raise FileNotFoundError(2, u"no such value")
        return holder[name], self.kinds.get(name, self.REG_SZ)

    def SetValueEx(self, handle, name, _reserved, kind, value):
        self.keys.setdefault(handle.sub, {})[name] = value
        self.kinds[name] = kind

    def DeleteValue(self, handle, name):
        holder = self.keys.get(handle.sub, {})
        if name not in holder:
            raise FileNotFoundError(2, u"no such value")
        del holder[name]


@pytest.fixture
def registry(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    return fake


def test_enable_writes_the_command_as_a_plain_string(registry):
    written = startup.enable()
    assert registry.values[startup.VALUE_NAME] == written == startup.command()
    # ⛔ REG_SZ, not REG_EXPAND_SZ: `QueryValueEx` does NOT expand, so an
    # expandable value could never compare equal and would read stale for ever.
    assert registry.kinds[startup.VALUE_NAME] == FakeWinreg.REG_SZ
    # ⛔ AND UNDER HKCU. HKLM needs elevation and fails for an ordinary user.
    assert registry.opened_roots == [FakeWinreg.HKEY_CURRENT_USER]


def test_the_whole_round_trip(registry):
    assert startup.is_enabled() is False
    startup.enable()
    assert startup.is_enabled() is True
    assert startup.is_stale() is False
    assert startup.disable() is True
    assert startup.is_enabled() is False


def test_disabling_an_entry_a_CLEANER_already_removed_is_not_an_error(registry):
    u"""⛔ The docstring promises this. Nothing executed it before."""
    assert startup.disable() is False


def test_a_missing_RUN_KEY_reads_as_not_enabled(monkeypatch):
    fake = FakeWinreg(key_exists=False)
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    assert startup.registered() is None
    assert startup.is_enabled() is False


def test_a_registry_that_REFUSES_is_reported_not_swallowed(monkeypatch):
    fake = FakeWinreg(fail_with=OSError(5, u"access is denied"))
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    with pytest.raises(startup.StartupError):
        startup.registered()
    with pytest.raises(startup.StartupError):
        startup.enable()


def test_enable_OVERWRITES_a_stale_entry_rather_than_doubling_it(registry):
    registry.values[startup.VALUE_NAME] = u"C:\\old\\place\\hato-watch.exe"
    assert startup.is_stale() is True
    startup.enable()
    assert startup.is_stale() is False
    assert len(registry.values) == 1


# ---------------------------------------------------------------------------
# 🚨 TASK MANAGER'S *DISABLE* DOES NOT DELETE THE Run VALUE
#
# It records the decision in StartupApproved\Run and leaves Run alone. Reading
# Run by itself therefore reports hato as starting when it will not -- the
# precise failure this module's header gives as its reason for trusting the
# registry. Found by an adversarial pass that READ the real key.
# ---------------------------------------------------------------------------

def _approval(disabled):
    u"""Windows' 12-byte blob. Low bit of byte 0 carries the decision."""
    return bytes([0x03 if disabled else 0x02]) + b"\x00" * 11


def test_no_opinion_recorded_is_not_a_veto(monkeypatch):
    u"""⚠ The ordinary case: Windows writes nothing here until somebody uses
    Task Manager on the entry. Absent must NOT read as disabled."""
    fake = FakeWinreg(values={startup.VALUE_NAME: u"whatever"})
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    assert startup.approved() is None
    assert startup.is_enabled() is True


def test_an_entry_DISABLED_in_task_manager_is_not_enabled(monkeypatch):
    fake = FakeWinreg(values={startup.VALUE_NAME: u"whatever"},
                      approved=_approval(disabled=True))
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    assert startup.approved() is False
    assert startup.is_enabled() is False, \
        u"the Run value exists, but Windows has switched hato off"


def test_an_entry_approved_in_task_manager_is_enabled(monkeypatch):
    fake = FakeWinreg(values={startup.VALUE_NAME: u"whatever"},
                      approved=_approval(disabled=False))
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    assert startup.approved() is True
    assert startup.is_enabled() is True


def test_an_unreadable_approval_is_NO_OPINION_not_a_guess(monkeypatch):
    u"""⛔ Guessing *disabled* would switch hato off for somebody whose
    registry merely holds a shape this did not expect."""
    fake = FakeWinreg(values={startup.VALUE_NAME: u"whatever"},
                      approved=u"not bytes at all")
    monkeypatch.setitem(sys.modules, u"winreg", fake)
    monkeypatch.setattr(startup, u"supported", lambda: True)
    assert startup.approved() is None
    assert startup.is_enabled() is True


# ---------------------------------------------------------------------------
# ⭐ and the command must name something that EXISTS
# ---------------------------------------------------------------------------

def test_the_registered_command_names_a_file_that_IS_THERE(monkeypatch):
    u"""🚨 A MUTANT SURVIVED EVERY OTHER CHECK HERE. Dropping one
    `os.path.dirname` from `_repo_root()` yields a command that is absolute,
    mentions `hato-watch.pyw`, contains no `-m` -- and names a path that does
    not exist. Every assertion passed; the feature would have been a silent
    no-op at every login.

    ⛔ The other check reads `ROOT/hato-watch.pyw` where ROOT comes from THIS
    file. The two were never joined. This joins them.
    """
    monkeypatch.setattr(sys, u"frozen", False, raising=False)
    line = startup.command()
    target = line.rsplit(u" ", 1)[-1].strip(u'"')
    assert os.path.isfile(target), \
        u"the login command names %r, which is not there" % target


if __name__ == u"__main__":
    raise SystemExit(pytest.main([__file__, u"-q"]))
