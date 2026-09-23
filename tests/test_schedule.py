# -*- coding: utf-8 -*-
u"""
Does the "runs automatically at 03:00" switch register something that RUNS? D2.

===========================================================================
🚨 THE SWITCH READ ON FOR DAYS OVER NO TASK AT ALL
===========================================================================

It was drawn from `bool(cfg.schedule)` -- always true -- and turning it off
sent `schedule=off`, which the config refuses by name. ⭐ Task Scheduler is
now the only state (`hato/schedule.py`), and these checks hold it to that.

===========================================================================
⛔ NOTHING HERE TOUCHES THE REAL TASK SCHEDULER -- except ONE block
===========================================================================

The suite runs with `HATO_NO_SCHEDULER=1` (`run_tests.py`, `conftest.py`), so
`read()` asks nothing and every write refuses. The checks below drive a FAKE
schtasks that stores what it is given and prints it back the way the real one
does -- in the console's code page, which cannot say a Japanese letter. ⭐ Its
fixtures are real output (`tests/fixtures/schtasks/`, recorded 2026-09-23,
the machine's SID and name replaced).

The one exception proves the thing no fake can: that Windows TAKES the task
and KEEPS the battery settings. It opts in under its own task name with a
harmless action, and removes it whatever happens.
"""
import datetime
import os
import re
import sys
import uuid

import pytest

from hato import config, schedule, startup, watch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, u"tests", u"fixtures", u"schtasks")
OURS = [u"C:\\Users\\Someone\\Desktop\\hato 1.0.2\\hato-watch.exe", schedule.SCHEDULED_FLAG]


def _fixture(name):
    with open(os.path.join(FIXTURES, name), u"rb") as handle:
        return handle.read().decode(u"cp437")


# ---------------------------------------------------------------------------
# what the task runs
# ---------------------------------------------------------------------------

def test_the_task_starts_the_watchers_program_with_the_flag_the_watcher_reads():
    u"""⛔ The contract between two modules: `schedule` registers the flag and
    `watch.main` dispatches on it. One string, imported, never restated."""
    argv = schedule.command_argv()
    assert argv[:-1] == startup.watcher_argv()
    assert argv[-1] == watch.SCHEDULED_FLAG == schedule.SCHEDULED_FLAG


def test_frozen_it_runs_hato_watch_never_the_console_cli_or_the_window(monkeypatch, tmp_path):
    u"""🚨 `hato-cli.exe` from Task Scheduler is a console WINDOW over whatever the
    person is doing; `hato.exe` is the window itself."""
    monkeypatch.setattr(sys, u"frozen", True, raising=False)
    monkeypatch.setattr(sys, u"executable", str(tmp_path / u"hato.exe"))
    argv = schedule.command_argv()
    assert os.path.basename(argv[0]) in (u"hato-watch.exe", u"hato-watch")
    assert os.path.dirname(argv[0]) == str(tmp_path)
    assert argv[1:] == [schedule.SCHEDULED_FLAG]


def test_from_source_it_runs_the_launcher_never_dash_m(monkeypatch):
    u"""⛔ A task has no environment and a working directory of Windows' choosing:
    `-m hato.watch` there is a silent ModuleNotFoundError, every night."""
    monkeypatch.setattr(sys, u"frozen", False, raising=False)
    argv = schedule.command_argv()
    assert u"-m" not in argv
    assert os.path.isfile(argv[-2]) and argv[-2].endswith(u"hato-watch.pyw")
    assert os.path.isabs(argv[0])


def test_the_flag_reaches_the_daily_run_and_a_running_tray_does_not_stop_it(monkeypatch):
    u"""⭐ The flag is dispatched BEFORE the one-watcher check: a tray already in
    the tray is no reason to skip anybody's daily run."""
    monkeypatch.setattr(watch, u"watching_pid", lambda: 4242)
    monkeypatch.setattr(watch, u"scheduled_run", lambda spawner=None: 7)
    assert watch.main([schedule.SCHEDULED_FLAG]) == 7


# ---------------------------------------------------------------------------
# the daily run itself -- hato, windowless, and its exit code handed back
# ---------------------------------------------------------------------------

class _Child(object):
    def __init__(self, code, err=b""):
        self.returncode = code
        self._err = err

    def communicate(self):
        return None, self._err


def _popen_recorder(monkeypatch, code=0, err=b"", fail=None):
    seen = {}

    def popen(argv, **kwargs):
        if fail is not None:
            raise fail
        seen[u"argv"], seen[u"kwargs"] = argv, kwargs
        return _Child(code, err)
    monkeypatch.setattr(watch.subprocess, u"Popen", popen)
    return seen


def test_the_daily_run_is_hato_quiet_waiting_and_WINDOWLESS(monkeypatch):
    said = []
    monkeypatch.setattr(watch, u"complain", said.append)
    seen = _popen_recorder(monkeypatch, code=0)
    assert watch.scheduled_run() == 0
    assert seen[u"argv"] == watch.run_argv() + [u"--quiet", u"--wait"]
    if sys.platform.startswith(u"win"):
        # ⛔ the console suppressed, the busy cursor off -- as the tray does it
        assert seen[u"kwargs"][u"creationflags"] & 0x08000000
        assert seen[u"kwargs"][u"startupinfo"].wShowWindow == 0
    assert said == [], u"a run that went well puts nothing in the log from here"


def test_the_daily_run_hands_back_hatos_code_and_LOGS_why(monkeypatch):
    u"""⭐ Nobody reads Task Scheduler's *Last Result*; the log is the record, so
    a run that did not go well says so there, in hato's own words."""
    said = []
    monkeypatch.setattr(watch, u"complain", said.append)
    _popen_recorder(monkeypatch, code=2, err=b"hato: no folder to scan.\n")
    assert watch.scheduled_run() == 2
    assert len(said) == 1 and u"exited 2" in said[0] and u"no folder to scan" in said[0]


def test_a_daily_run_that_cannot_start_is_said_not_raised(monkeypatch):
    u"""⛔ A missing hato-cli.exe (antivirus, a half-finished update) must not
    end in a traceback nobody sees."""
    said = []
    monkeypatch.setattr(watch, u"complain", said.append)
    _popen_recorder(monkeypatch, fail=OSError(2, u"not there"))
    assert watch.scheduled_run() == 1
    assert said and u"could not start" in said[0]


# ---------------------------------------------------------------------------
# the task's own definition
# ---------------------------------------------------------------------------

def test_the_task_is_written_with_the_battery_trap_turned_OFF():
    u"""🚨 Measured 2026-09-17: the default does not start on battery and reports
    `Last Result: 0` for a run that never happened. Written out, not defaulted."""
    xml = schedule.task_xml(u"03:00", OURS)
    for line in (u"<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
                 u"<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>",
                 u"<StartWhenAvailable>true</StartWhenAvailable>",
                 u"<WakeToRun>false</WakeToRun>"):
        assert line in xml
    task = schedule.parse(xml)
    assert task.on_battery_ok is True and task.catches_up is True
    assert task.daily is True and task.at == u"03:00" and task.enabled is True
    assert schedule.problems(task, OURS) == []


def test_the_start_is_NEVER_already_past():
    u"""🚨 A start boundary behind it, with *run when available*, may count as a
    missed run and start the moment the switch is turned on."""
    two_pm = datetime.datetime(2026, 9, 23, 14, 0, 0)
    assert schedule.next_start(u"03:00", two_pm) == datetime.datetime(2026, 9, 24, 3, 0)
    assert schedule.next_start(u"15:00", two_pm) == datetime.datetime(2026, 9, 23, 15, 0)
    assert schedule.next_start(u"14:00", two_pm) == datetime.datetime(2026, 9, 24, 14, 0)
    assert u"2026-09-24T03:00:00" in schedule.task_xml(u"03:00", OURS, now=two_pm)


def test_a_path_with_an_ampersand_a_space_and_japanese_survives_the_xml():
    u"""⚠ `&` in a folder name is legal and is XML's escape character."""
    odd = [u"C:\\Tom & Jerry\\アニメ\\hato-watch.exe", schedule.SCHEDULED_FLAG]
    task = schedule.parse(schedule.task_xml(u"03:00", odd))
    assert task.command == odd[0]
    assert task.arguments == schedule.SCHEDULED_FLAG


# ---------------------------------------------------------------------------
# reading back what Task Scheduler REALLY prints (recorded)
# ---------------------------------------------------------------------------

def test_hatos_own_task_as_task_scheduler_prints_it_reads_as_fine():
    task = schedule.parse(_fixture(u"own-task.xml"))
    assert task.readable and task.enabled and task.daily
    assert task.at == u"03:00"
    assert task.on_battery_ok and task.catches_up
    assert schedule.problems(task, OURS) == []


def test_a_HAND_MADE_task_on_the_defaults_is_the_battery_trap_and_says_so():
    u"""⭐ The README tells people how to schedule hato themselves. A task made
    with schtasks' defaults exists and reads ON -- and will not start on battery,
    and skips a run the computer slept through. It must say so, with the fix."""
    task = schedule.parse(_fixture(u"hand-made-defaults.xml"))
    assert task.enabled is True
    assert task.on_battery_ok is False and task.catches_up is False
    said = u" ".join(schedule.problems(task, OURS))
    assert u"battery" in said and u"asleep" in said
    assert u"different copy of hato" in said          # it runs hato-cli.exe


def test_absent_Enabled_means_enabled_and_a_disabled_task_reads_OFF():
    u"""⚠ Measured: Task Scheduler writes `<Enabled>false</Enabled>` only once
    somebody disables it."""
    base = _fixture(u"own-task.xml")
    assert schedule.parse(base).enabled is True
    off = base.replace(u"<Settings>", u"<Settings>\r\n    <Enabled>false</Enabled>", 1)
    task = schedule.parse(off)
    assert task.enabled is False
    assert schedule.is_enabled(task) is False
    assert u"switched off in Task Scheduler" in schedule.note(task, OURS)
    trigger_off = base.replace(u"<CalendarTrigger>",
                               u"<CalendarTrigger>\r\n      <Enabled>false</Enabled>", 1)
    assert schedule.parse(trigger_off).enabled is False


def test_a_task_changed_to_WEEKLY_in_task_scheduler_is_not_called_daily():
    # ⚠ A pattern, not a literal: schtasks ends its lines `\r\r\n`.
    weekly = re.sub(u"<ScheduleByDay>.*?</ScheduleByDay>",
                    u"<ScheduleByWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>",
                    _fixture(u"own-task.xml"), flags=re.S)
    assert u"ScheduleByWeek" in weekly
    task = schedule.parse(weekly)
    assert task.daily is False
    assert u"changed in Task Scheduler" in schedule.note(task, OURS)


def test_an_unreadable_definition_is_a_task_that_EXISTS():
    u"""⛔ Not "off": it is there, Task Scheduler runs it, and toggling repairs it."""
    task = schedule.parse(u"<Task><not closed")
    assert task.readable is False
    assert schedule.is_enabled(task) is True
    assert u"cannot read" in schedule.note(task, OURS)


# ---------------------------------------------------------------------------
# 🚨 schtasks cannot say a non-ASCII path -- the comparison must survive it
# ---------------------------------------------------------------------------

def test_the_command_is_compared_on_its_ASCII_skeleton():
    u"""Measured 2026-09-23: `Michaël 日本` came back `Michaël ??` under cp437."""
    ours = u"C:\\Micha\u00ebl \u65e5\u672c\\hato-watch.exe"
    assert schedule._same(ours, u"C:\\Micha\u00ebl ??\\hato-watch.exe")
    assert schedule._same(ours, u"c:\\MICHA\u00ebl ??\\HATO-WATCH.EXE")      # case
    assert not schedule._same(ours, u"C:\\Micha\u00ebl ??\\hato-watcH.ex")   # length
    assert not schedule._same(ours, u"D:\\Micha\u00ebl ??\\hato-watch.exe")  # moved
    assert not schedule._same(ours, None)
    # ⚠ a letter outside the BMP is TWO units, and schtasks writes two `?`
    assert schedule._same(u"C:\\\U0001F54A\\x", u"C:\\??\\x")
    # ⛔ ONLY OUR SIDE IS A WILDCARD: an ASCII letter of ours never comes back as
    # anything else, so theirs being non-ASCII there is another folder
    assert not schedule._same(u"C:\\Musik\\x", u"C:\\M\u00fcsik\\x")
    assert not schedule._same(u"C:\\Musik\\x", u"C:\\M?sik\\x")


def test_a_battery_setting_that_is_ABSENT_is_the_schema_default_which_is_the_trap():
    u"""⚠ Task Scheduler's own defaults: no battery start, no catch-up. A task
    whose XML leaves them out must read as the trap, never as fine.

    🚨 ONE AT A TIME. The first version removed all three at once -- and either
    battery default alone then kept the answer "not safe", so a mutant flipping
    ONE of them survived it (M8y-18, the gate's own list). Two guards that back
    each other up witness neither."""
    own = _fixture(u"own-task.xml")

    def without(tag):
        bare = re.sub(u"<%s>[^<]*</%s>" % (tag, tag), u"", own)
        assert tag not in bare, tag
        return schedule.parse(bare)
    assert schedule.parse(own).on_battery_ok is True, u"the control"
    assert without(u"DisallowStartIfOnBatteries").on_battery_ok is False
    assert without(u"StopIfGoingOnBatteries").on_battery_ok is False
    assert schedule.parse(own).catches_up is True, u"the control"
    assert without(u"StartWhenAvailable").catches_up is False


def test_a_JAPANESE_windows_reads_back_a_japanese_path_as_itself(monkeypatch, tmp_path):
    u"""⚠ This machine's page is cp437, where every decoder looks the same. On a
    Japanese Windows the page is cp932: each kanji is TWO bytes, and decoding
    them any other way turns every Japanese install into "a different copy"."""
    jp = [u"C:\\Users\\\u5c71\u7530\\hato\\hato-watch.exe", schedule.SCHEDULED_FLAG]
    scheduler = FakeSchtasks(codec=u"cp932")
    monkeypatch.setattr(schedule, u"_schtasks", scheduler)
    monkeypatch.setattr(schedule, u"_codec", lambda: u"cp932")
    monkeypatch.setattr(schedule, u"supported", lambda: True)
    monkeypatch.setattr(schedule, u"command_argv", lambda: list(jp))
    monkeypatch.delenv(u"HATO_NO_SCHEDULER", raising=False)
    monkeypatch.delenv(u"HATO_TASK_NAME", raising=False)
    monkeypatch.setattr(schedule.tempfile, u"tempdir", str(tmp_path))
    task = schedule.enable(u"03:00")
    assert task.command == jp[0], u"cp932 says it exactly"
    assert schedule.note(task) == u""


def test_the_code_page_is_the_machines_OEM_page(monkeypatch):
    import ctypes

    class _Kernel(object):
        def __init__(self, page):
            self.GetOEMCP = lambda: page

    class _Windll(object):
        def __init__(self, page):
            self.kernel32 = _Kernel(page)
    for page, codec in ((932, u"cp932"), (437, u"cp437"), (850, u"cp850"),
                        (99999, u"cp437")):
        monkeypatch.setattr(ctypes, u"windll", _Windll(page), raising=False)
        assert schedule._codec() == codec, (page, schedule._codec())


def test_task_scheduler_is_asked_WITHOUT_a_console_window(monkeypatch):
    u"""⛔ From the window -- a process with no console -- a console child gets a
    window of its own: a black flash on every click of the switch."""
    seen = {}

    class _Done(object):
        returncode, stdout, stderr = 0, b"", b""

    def run(argv, **kwargs):
        seen[u"argv"], seen[u"kwargs"] = argv, kwargs
        return _Done()
    monkeypatch.delenv(u"HATO_NO_SCHEDULER", raising=False)
    monkeypatch.setattr(schedule.subprocess, u"run", run)
    schedule._schtasks(u"/query", u"/tn", u"hato-never-registered")
    assert seen[u"argv"][0].lower().endswith(u"schtasks.exe")
    if sys.platform.startswith(u"win"):
        assert seen[u"kwargs"][u"creationflags"] & 0x08000000
        assert seen[u"kwargs"][u"startupinfo"].wShowWindow == 0
    assert seen[u"kwargs"].get(u"timeout"), u"a hung Task Scheduler must not hang the window"


def test_every_call_names_the_task_through_task_name():
    u"""🚨 The suite's one real check runs under its OWN name. A call that named
    `TASK_NAME` directly would reach the person's real daily run -- and a check,
    or a mutant, could then delete it. Static, so it costs nothing to run."""
    with open(schedule.__file__, encoding=u"utf-8") as handle:
        text = handle.read()
    # ⚠ The argument AFTER `/tn`, captured whole -- a `[^)]*` stopped at the `)`
    # inside `task_name()` itself (the first draft of this check).
    named = re.findall(u'"/tn",\\s*([A-Za-z_.]+(?:\\(\\))?)', text)
    assert len(named) >= 3, u"query, create and delete should all be found: %r" % named
    assert set(named) == {u"task_name()"}, (
        u"a schtasks call names the task some other way: %r" % named)


def test_a_moved_install_reads_as_a_DIFFERENT_COPY():
    task = schedule.parse(_fixture(u"own-task.xml"))
    elsewhere = [u"C:\\Users\\Someone\\Downloads\\hato 1.0.2\\hato-watch.exe",
                 schedule.SCHEDULED_FLAG]
    assert u"different copy of hato" in schedule.note(task, elsewhere)
    assert schedule.problems(task, OURS) == []
    # ⚠ the right program told to do something else is not the daily run either
    task.arguments = u"--quiet"
    assert u"different copy of hato" in schedule.note(task, OURS)


# ---------------------------------------------------------------------------
# the switch's contract, against a FAKE schtasks
# ---------------------------------------------------------------------------

class FakeSchtasks(object):
    u"""Stores what it is given; prints it back as schtasks does -- in cp437, so
    a Japanese letter comes back `?`, exactly the measured shape."""

    def __init__(self, refuse_create=None, lose_create=False, codec=u"cp437"):
        self.tasks = {}
        self.calls = []
        self.refuse_create = refuse_create
        self.lose_create = lose_create
        self.codec = codec

    def __call__(self, *args):
        self.calls.append(args)
        verb, name = args[0], args[2]
        if verb == u"/query":
            if name not in self.tasks:
                return 1, b"", b"ERROR: The system cannot find the file specified.\r\r\n"
            return 0, self.tasks[name].encode(self.codec, u"replace"), b""
        if verb == u"/create":
            if self.refuse_create:
                return 1, b"", self.refuse_create
            with open(args[args.index(u"/xml") + 1], encoding=u"utf-16") as handle:
                text = handle.read()
            if not self.lose_create:
                self.tasks[name] = text
            return 0, b"SUCCESS", b""
        if verb == u"/delete":
            if self.tasks.pop(name, None) is None:
                return 1, b"", b"ERROR: The system cannot find the file specified.\r\r\n"
            return 0, b"SUCCESS", b""
        if verb == u"/change" and u"/disable" in args:
            self.tasks[name] = self.tasks[name].replace(
                u"<Settings>", u"<Settings>\n    <Enabled>false</Enabled>", 1)
            return 0, b"SUCCESS", b""
        raise AssertionError(u"unexpected schtasks call %r" % (args,))


@pytest.fixture
def fake(monkeypatch, tmp_path):
    scheduler = FakeSchtasks()
    monkeypatch.setattr(schedule, u"_schtasks", scheduler)
    monkeypatch.setattr(schedule, u"supported", lambda: True)
    monkeypatch.setattr(schedule, u"command_argv", lambda: list(OURS))
    monkeypatch.delenv(u"HATO_NO_SCHEDULER", raising=False)
    monkeypatch.delenv(u"HATO_TASK_NAME", raising=False)
    monkeypatch.setattr(schedule.tempfile, u"tempdir", str(tmp_path))
    return scheduler


def test_the_whole_round_trip(fake, tmp_path):
    assert schedule.read() is None and schedule.is_enabled() is False
    task = schedule.enable(u"03:00")
    assert task.at == u"03:00" and schedule.is_enabled(task)
    assert schedule.note(task) == u""
    assert list(fake.tasks) == [u"hato"]
    assert schedule.disable() is True
    assert schedule.read() is None
    # ⚠ the XML handed to schtasks is gone whatever happened
    assert [p.name for p in tmp_path.iterdir()] == []


def test_the_task_carries_hatos_NAME(fake):
    u"""⚠ The name is the identity: another name orphans what 1.0.2 registers."""
    schedule.enable(u"03:00")
    assert fake.calls[0][:3] == (u"/create", u"/tn", u"hato")
    assert u"/f" in fake.calls[0], u"it must OVERWRITE, or a stale task survives"


def test_turning_it_off_when_it_is_already_off_is_NOT_an_error(fake):
    assert schedule.disable() is False


def test_a_task_switched_off_in_task_scheduler_reads_OFF_and_turning_on_repairs_it(fake):
    schedule.enable(u"03:00")
    fake(u"/change", u"/tn", u"hato", u"/disable")
    task = schedule.read()
    assert schedule.is_enabled(task) is False
    assert u"switched off in Task Scheduler" in schedule.note(task)
    assert schedule.set_enabled(True, u"03:00") is True
    assert schedule.note(schedule.read()) == u""


def test_turning_on_OVERWRITES_a_hand_made_task(fake):
    fake.tasks[u"hato"] = _fixture(u"hand-made-defaults.xml")
    assert schedule.note(schedule.read()) != u""
    schedule.enable(u"03:00")
    assert schedule.note(schedule.read()) == u""
    assert len(fake.tasks) == 1


def test_a_time_the_config_refuses_is_refused_BEFORE_windows_is_asked(fake):
    for bad in (u"3:00", u"24:00", u"03:60", u"", u"off"):
        with pytest.raises(schedule.ScheduleError):
            schedule.enable(bad)
    assert fake.calls == []


def test_the_window_the_config_and_the_task_share_ONE_time_test():
    u"""⛔ `schedule=off` was sent by the window and refused by the config, and
    nothing said so. One predicate now answers for all three."""
    for good in (u"00:00", u"03:00", u"23:59"):
        assert config.is_clock(good)
    for bad in (u"3:00", u"24:00", u"03:60", u"off", u"", None, u" 03:00"):
        assert not config.is_clock(bad)


def test_a_refusal_is_said_in_task_schedulers_OWN_words(fake):
    fake.refuse_create = b"ERROR: Access is denied.\r\r\n"
    with pytest.raises(schedule.ScheduleError) as caught:
        schedule.enable(u"03:00")
    assert u"Access is denied" in str(caught.value)
    # ⚠ one full stop, not its and ours (LOOKED: "(Access is denied.).")
    assert u".)" not in str(caught.value), str(caught.value)


def test_a_SUCCESS_that_left_nothing_behind_is_an_error(fake):
    u"""⭐ A refusal and a success can look alike -- so it is read back."""
    fake.lose_create = True
    with pytest.raises(schedule.ScheduleError) as caught:
        schedule.enable(u"03:00")
    assert u"not there" in str(caught.value)


def test_the_suites_switch_refuses_every_write_and_reads_NOTHING(monkeypatch):
    u"""⛔ A check must never register a real task -- nor read the developer's
    own daily run, which would change its verdict on their machine alone.

    🚨 AND THIS CHECK MUST BE SAFE WHEN THE SWITCH IS BROKEN -- a mutant that
    removes it would otherwise register a real daily run. So it asks under a
    name of its own, with a harmless action, and removes it whatever happens."""
    name = u"hato-suite-switch-%d" % os.getpid()
    monkeypatch.setenv(u"HATO_NO_SCHEDULER", u"1")
    monkeypatch.setenv(u"HATO_TASK_NAME", name)
    monkeypatch.setattr(schedule, u"supported", lambda: True)
    harmless = [os.path.join(os.environ.get(u"SystemRoot", u"C:\\Windows"),
                             u"System32", u"cmd.exe"), u"/c", u"rem"]
    try:
        assert schedule.read() is None
        with pytest.raises(schedule.ScheduleError):
            schedule.enable(u"03:00", argv=harmless)
        with pytest.raises(schedule.ScheduleError):
            schedule.disable()
    finally:
        monkeypatch.delenv(u"HATO_NO_SCHEDULER")
        if sys.platform.startswith(u"win"):
            schedule._schtasks(u"/delete", u"/tn", name, u"/f")


def test_off_windows_it_refuses_with_an_INSTRUCTION(monkeypatch):
    monkeypatch.setattr(schedule, u"supported", lambda: False)
    assert schedule.read() is None
    assert schedule.disable() is False
    with pytest.raises(schedule.ScheduleError) as caught:
        schedule.enable(u"03:00")
    assert u"cron" in str(caught.value)


def test_the_suite_itself_runs_with_task_scheduler_switched_OFF():
    u"""⛔ `conftest.py` sets it for every check, however the suite was started.
    Without it, a check that reached `enable` would register a real daily run."""
    assert os.environ.get(u"HATO_NO_SCHEDULER") == u"1"


def test_the_task_name_moves_only_when_told_to(monkeypatch):
    monkeypatch.delenv(u"HATO_TASK_NAME", raising=False)
    assert schedule.task_name() == u"hato"
    monkeypatch.setenv(u"HATO_TASK_NAME", u"hato-probe")
    assert schedule.task_name() == u"hato-probe"


# ---------------------------------------------------------------------------
# ⭐ THE REAL TASK SCHEDULER -- the one thing no fake can prove
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not sys.platform.startswith(u"win"), reason=u"Task Scheduler is Windows'")
def test_the_REAL_task_scheduler_takes_the_task_and_KEEPS_the_battery_settings(monkeypatch):
    u"""🚨 The battery trap was a setting silently not applied. Only Windows can
    say whether it kept what it was given -- so this asks it, under a name of its
    own, with a harmless action and a non-ASCII argument (the measured shape),
    and removes the task whatever happens."""
    name = u"hato-suite-%d-%s" % (os.getpid(), uuid.uuid4().hex[:6])
    monkeypatch.delenv(u"HATO_NO_SCHEDULER", raising=False)
    monkeypatch.setenv(u"HATO_TASK_NAME", name)
    assert schedule.task_name() == name != schedule.TASK_NAME
    harmless = [os.path.join(os.environ.get(u"SystemRoot", u"C:\\Windows"),
                             u"System32", u"cmd.exe"),
                u"/c", u"rem", u"hato suite Micha\u00ebl \u65e5\u672c"]
    try:
        task = schedule.enable(u"04:17", argv=harmless)
        assert (task.at, task.enabled, task.daily) == (u"04:17", True, True)
        assert task.on_battery_ok is True, u"Windows did not keep the battery settings"
        assert task.catches_up is True
        assert schedule.problems(task, harmless) == []

        code, _out, _err = schedule._schtasks(u"/change", u"/tn", name, u"/disable")
        assert code == 0
        off = schedule.read()
        assert schedule.is_enabled(off) is False
        assert u"switched off in Task Scheduler" in schedule.note(off, harmless)

        again = schedule.enable(u"05:30", argv=harmless)
        assert (again.at, again.enabled) == (u"05:30", True)
        assert schedule.disable() is True
        assert schedule.read() is None
        assert schedule.disable() is False
    finally:
        schedule._schtasks(u"/delete", u"/tn", name, u"/f")


if __name__ == u"__main__":
    raise SystemExit(pytest.main([__file__, u"-q"]))
