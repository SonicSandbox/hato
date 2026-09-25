# -*- coding: utf-8 -*-
u"""A fake Windows for the swapper (`hato/swap.py`) -- shared by the suites that
drive it: `test_swap.py` (the swapper itself) and `test_update.py` (the seam: what
staging and *Go back* write is what the swapper reads).

    import _fakewin                     # tests/ is on sys.path

`Ops` answers the four questions the swapper asks the operating system -- which
processes run from a folder, start one, is its window on screen, what a program
says its version is -- and records every question, so a check can assert what the
swapper DID, not only what it returned.
"""
import os


class Clock(object):
    u"""Time that moves only when the swapper sleeps -- so a 60 s wait is instant."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Proc(object):
    u"""A started program: alive until it has been polled `dies_after` times."""

    def __init__(self, pid, path, dies_after=None, code=1):
        self.pid, self.path, self.dies_after, self.polled = pid, path, dies_after, 0
        self.code = code

    def poll(self):
        self.polled += 1
        if self.dies_after is not None and self.polled > self.dies_after:
            return self.code
        return None


class Ops(object):
    u"""`running_for` polls say a process still runs from the install folder;
    `visible` answers for any window; a started program dies after `dies_after`
    polls; `says` is what the new hato-cli.exe reports; `refuse` names a program
    that will not start; `on_start` / `on_poll` may act."""

    def __init__(self, running_for=0, visible=True, dies_after=None, says=u"1.0.5",
                 refuse=(), on_start=None, on_poll=None, code=1):
        self.running_for, self.visible, self.dies_after = running_for, visible, dies_after
        self.code = code
        self.says, self.refuse = says, refuse
        self.on_start, self.on_poll = on_start, on_poll
        self.started, self.stopped, self.asked, self.polls = [], [], [], 0

    def processes_in(self, folder):
        self.polls += 1
        running = self.polls <= self.running_for
        if self.on_poll:
            self.on_poll(running)
        return [999] if running else []

    def start(self, path):
        name = os.path.basename(path)
        if name in self.refuse:
            raise OSError(193, u"not a valid application")
        proc = Proc(1000 + len(self.started), path, self.dies_after, self.code)
        self.started.append(name)
        if self.on_start:
            self.on_start(proc)
        return proc

    def window_visible(self, pid, title=None):
        self.titles = getattr(self, "titles", []) + [title]
        return self.visible

    def version(self, path):
        self.asked.append(os.path.basename(path))
        return self.says

    def stop(self, process):
        self.stopped.append(process.pid)

    def stop_pid(self, pid):
        u"""A process the swap did not start, stopped by pid (the rollback's second wall)."""
        self.stopped.append(pid)
