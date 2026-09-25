# -*- coding: utf-8 -*-
u"""Keep hato itself up to date -- RUNBOOK LAYER 11.

    hato update [--check] [--if-due] [--json]    is a newer hato out, and can THIS copy
                                                 take it? (`--if-due`: only once a day;
                                                 otherwise the last answer, no network)
    hato update --stage [--json] [--progress]    download it and prove it, beside this
                                                 copy -- nothing of the person's moves
    hato update --apply [--json]                 install what is staged: the tray stops,
                                                 this command exits, the swapper swaps and
                                                 opens hato again
    hato update --rollback [--json]              the same, putting the KEPT version back

⭐ ONE IMPLEMENTATION, THREE CALLERS: the window drives this through its Runner and
reads the `--progress` stream exactly as it reads a run's; the tray and the 03:00 run
call it too; and a person can type it. `--json` prints one object:

    {"type": "update", "current": "1.0.4", "kind": "none"|"ready"|"tell", "version",
     "reason", "notes", "critical", "page", "zip_url"}

and `--stage --json --progress` streams `{"type": "progress", "stage": "download",
"done": N, "total": M}` before `{"type": "staged", "version", "pending"}`.

⛔ From a checkout, on any OS, this only ever TELLS (`update.check`): updating a
checkout is git's job. ⛔ Nothing here runs at import.

Exit codes: 0 it ran, whatever it found · 1 staging did not finish -- the reason on
stderr and in hato.log (`=== hato update … ===`), and under `--json` one
`{"type": "error", "reason": …}` object · 2 usage.
"""
import json
import os
import sys
import time

from hato import __version__, update

EXIT_OK = 0
EXIT_FAILED = 1

#: What each TELL reason means to a person -- ⛔ never the reason code itself.
TELLS = {
    update.SOURCE: u"You run hato from source, so update it the way you got it: `git pull`.",
    update.PLATFORM: u"The packaged hato is for Windows; update this one the way you "
                     u"installed it.",
    update.FOLDER: u"hato can't write to its own folder, so download the new version "
                   u"yourself.",
    update.UNSIGNED: u"It doesn't carry a signature hato trusts, so hato won't install "
                     u"it -- download it yourself if you trust it.",
    update.UNREADABLE: u"It can't be installed from inside hato -- download it yourself.",
    update.MISMATCH: u"Its files don't agree with each other, so hato won't install it.",
    update.TOO_OLD: u"This copy is too old to update itself -- download it yourself, once; "
                    u"after that, hato updates on its own.",
}


def register(parser):
    parser.add_argument("--check", action="store_true",
                        help="is a newer hato out, and can this copy take it (the default)")
    parser.add_argument("--if-due", action="store_true",
                        help="with --check: ask GitHub only if the last answer is a day old")
    parser.add_argument("--stage", action="store_true",
                        help="download the new version and prove it, beside this copy")
    parser.add_argument("--auto", action="store_true",
                        help="what the tray and the daily run do: once a day, and only when "
                             "updating is automatic, fetch a new release quietly")
    parser.add_argument("--apply", action="store_true",
                        help="install the staged version now: hato closes and opens again")
    parser.add_argument("--rollback", action="store_true",
                        help="put back the version kept before the last update")
    parser.add_argument("--json", action="store_true", help="one JSON object per line")
    parser.add_argument("--progress", action="store_true",
                        help="with --stage --json: stream the download's progress")


def install_dir():
    u"""The program folder this copy runs from -- beside the exe when frozen."""
    return os.path.dirname(os.path.abspath(sys.executable))


def sentence(decision, current):
    u"""-> the plain line for a decision. ⛔ No reason code reaches a person."""
    if decision.kind == update.READY:
        return u"hato %s is ready to install -- you have %s." % (decision.version, current)
    if decision.kind == update.TELL:
        return u"hato %s is out -- you have %s. %s %s" % (
            decision.version, current, TELLS.get(decision.reason, u""), decision.page)
    if decision.version:
        return u"hato %s is up to date." % current
    return u"Could not tell whether a newer hato is out -- GitHub did not answer."


def _say(args, obj, plain):
    if args.json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + u"\n")
    else:
        sys.stdout.write(plain + u"\n")
    sys.stdout.flush()


def _remembered():
    u"""The last decision saved, as a Decision -- no network. -> Decision or None."""
    saved = update.load_state().get(u"decision")
    if not isinstance(saved, dict) or saved.get(u"kind") not in (update.NONE, update.READY,
                                                                 update.TELL):
        return None
    return update.Decision(saved[u"kind"], saved.get(u"version"), saved.get(u"reason"),
                           saved.get(u"notes") or (), saved.get(u"critical") or False,
                           saved.get(u"page") or update.RELEASES_PAGE)


def _check(args, now):
    if args.if_due and not update.due(update.load_state(), now):
        remembered = _remembered()
        if remembered is not None:
            # 🚨 JUDGED AGAIN AGAINST THIS COPY. The answer was made before an
            # update installed: remembered as-is, the new 1.0.5 window would offer
            # "1.0.5 is ready" -- itself -- until the next day's check.
            if remembered.kind != update.NONE and not update.is_newer(
                    remembered.version, __version__):
                return update.Decision(update.NONE, remembered.version,
                                       notes=remembered.notes, page=remembered.page)
            return remembered
    decision = update.check(__version__, install_dir=install_dir())
    _remember(decision, now)
    return decision


def _remember(decision, now):
    u"""Save a check's answer -- ⛔ unless it could not tell (offline, GitHub silent):
    saved, that NONE hid a release already downloaded and verified for a day, and
    *When I close hato* then installed nothing (ADVERSARY 2026-09-24, C9)."""
    if decision.kind == update.NONE and decision.version is None:
        return
    try:
        update.remember(decision, now)
    except OSError:
        pass                                  # ⚠ an unwritable state only costs a re-check


def _fail(args, reason):
    u"""A staging failure: said, and WRITTEN to hato.log (surasura's lesson: a
    windowed build's failure vanished when its dialog closed)."""
    from hato import watch
    watch.complain(u"hato update: %s\n" % reason, who=u"update")
    if args.json:
        sys.stdout.write(json.dumps({u"type": u"error", u"reason": reason},
                                    ensure_ascii=False) + u"\n")
    return EXIT_FAILED


def running_beside(install):
    u"""-> pids of hato programs running from `install`, this one excluded."""
    from hato import swap
    return swap.WinOps().processes_in(install)


def _apply(args):
    u"""`--apply` / `--rollback`: hand off from a terminal.

    ⛔ Frozen Windows only -- a checkout is git's to update. ⛔ REFUSED while hato's
    window or a run is open: the swapper would wait a minute for them and then
    give up, having told nobody. The tray is the one hato program this stops
    itself -- the swapper starts it again, and proves it is watching."""
    from hato import watch
    if not getattr(sys, "frozen", False):
        return _fail(args, TELLS[update.SOURCE])
    if not sys.platform.startswith("win"):
        return _fail(args, TELLS[update.PLATFORM])
    install = install_dir()
    tray = watch.watching_pid()
    others = [pid for pid in running_beside(install) if pid != tray]
    if others:
        return _fail(args, u"close hato's window first, and let any run finish -- the "
                           u"update installs once nothing of hato's is open")
    root = update.stage_root(install)
    try:
        if args.rollback:
            pending = update.go_back_pending(install, __version__, root=root)
            swapper = os.path.join(install, update.SWAPPER_NAME)
        else:
            pending, swapper = os.path.join(str(root), update.PENDING_NAME), None
        with open(pending, encoding="utf-8") as handle:
            version = json.load(handle).get(u"to")
        stopped = watch.stop_running_watcher()
        try:
            update.hand_off(pending, window=True, tray=stopped is not None,
                            tray_pid_file=watch.pid_file_path(), swapper=swapper,
                            current=__version__, install=install)
        except BaseException:
            if stopped is not None:           # ⛔ a failed hand-off never costs the tray
                update.start_detached(watch.watch_argv())
            raise
    except update.StageError as exc:
        return _fail(args, u"%s" % exc)
    except (OSError, ValueError) as exc:
        return _fail(args, u"there is no update ready to install (%s)" % type(exc).__name__)
    _say(args, {u"type": u"applying", u"version": version, u"pending": pending},
         u"hato %s is installing -- hato opens again in a moment." % version)
    return EXIT_OK


def _auto(args, now):
    u"""`--auto` -- the TRAY's and the DAILY RUN's call (RUNBOOK 11g).

    ⛔ SILENT WHEN THERE IS NOTHING TO DO -- from source, switched off, up to date,
    not due: exit 0 and no log line (a daily *nothing new* in hato.log is noise).
    Only a staging FAILURE is written, as `--stage`'s is. ⛔ Never a version turned
    away: one that failed to go in, or one a person went back from.
    ⚠ A READY answer the WINDOW already got today is still fetched: not due would
    otherwise leave it waiting a day for a check of this command's own."""
    from hato import config
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        return EXIT_OK
    try:
        if not config.load().auto_update:
            return EXIT_OK
    except Exception:                         # noqa: BLE001 -- the window says why
        return EXIT_OK
    install = install_dir()
    update.reconcile(install)
    skipped = update.skipped()
    staged = update.staged_version(install, __version__)
    remembered = _remembered()
    state = update.load_state()
    owed = (remembered is not None and remembered.kind == update.READY
            and update.is_newer(remembered.version, __version__)
            and remembered.version not in (skipped, staged)
            and not tried_today(state, remembered.version, now))
    if not owed and not update.due(state, now):
        return EXIT_OK
    decision = update.check(__version__, install_dir=install)
    _remember(decision, now)
    if decision.kind != update.READY or decision.version in (skipped, staged):
        return EXIT_OK
    try:
        update.stage(decision, __version__, install, version_of=update.installed_version)
    except (update.StageError, OSError) as exc:
        # 🚨 ONCE A DAY (ADVERSARY 2026-09-24, A2): the READY answer is remembered
        # BEFORE staging, so a stage that failed the same way every time was owed
        # again an hour later -- 24 downloads of 67 MB a day, 24 log blocks.
        _tried(decision.version, now)
        if isinstance(exc, update.StageError):
            return _fail(args, u"%s" % exc)
        return _fail(args, u"the disk would not take the new version (%s)" % exc)
    return EXIT_OK


def tried_today(state, version, now):
    u"""True when staging `version` already failed within the day."""
    tried = state.get(u"stage_tried")
    if not isinstance(tried, dict) or tried.get(u"version") != version:
        return False
    at = tried.get(u"at")
    return isinstance(at, (int, float)) and not isinstance(at, bool) \
        and 0 <= now - at < update.CHECK_EVERY_SECONDS


def _tried(version, now):
    state = update.load_state()
    state[u"stage_tried"] = {u"version": version, u"at": now}
    try:
        update.save_state(state)
    except OSError:
        pass


def run(args, now=None):
    now = time.time() if now is None else now
    if args.auto:
        return _auto(args, now)
    if args.apply or args.rollback:
        return _apply(args)
    if args.stage:
        decision = update.check(__version__, install_dir=install_dir())
        if decision.kind != update.READY:
            return _fail(args, sentence(decision, __version__))

        def progress(done, total):
            if args.json and args.progress:
                sys.stdout.write(json.dumps({u"type": u"progress", u"stage": u"download",
                                             u"done": done, u"total": total}) + u"\n")
                sys.stdout.flush()

        try:
            pending = update.stage(decision, __version__, install_dir(), progress,
                                   version_of=update.installed_version)
        except update.StageError as exc:
            return _fail(args, u"%s" % exc)
        except OSError as exc:
            return _fail(args, u"the disk would not take the new version (%s)" % exc)
        _say(args, {u"type": u"staged", u"version": decision.version, u"pending": pending},
             u"hato %s is downloaded and checked -- it installs when hato closes." %
             decision.version)
        return EXIT_OK
    decision = _check(args, now)
    obj = dict(decision.as_dict())
    obj.update({u"type": u"update", u"current": __version__})
    _say(args, obj, sentence(decision, __version__))
    return EXIT_OK
