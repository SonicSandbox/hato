# -*- coding: utf-8 -*-
u"""The folder run -- walk, skip, fetch, sync, name, keep. The front door.

    hato <folder> [<folder> ...] [flags]
    hato                                  every folder in config.toml

⭐ THIS IS THE WHOLE JOB (`spec/05-interface.md`). The user never runs two
tools: `pipeline.run()` decides, `hato/report.py` renders, and this module is
what joins them to the real client, the real state DB and the run lock.

===========================================================================
⚠ THE RUN LOCK IS HERE AND NOWHERE ELSE
===========================================================================

`pipeline.run()` deliberately takes none -- a library caller may already hold
one (`hato/pipeline.py`). So the CLI takes it, and a second process **exits
cleanly with a message rather than racing** (`06-edge-cases.md` §9).

🚨 AND IT EXITS 0. `10-deployment.md` says the second process *"exits cleanly"*
and also that non-zero means *"it could not run at all"*, and those two readings
disagree on this one case. Built as 0, because the overlap the spec names --
*"a scheduled run overlaps a manual one"* -- is a NORMAL consequence of
scheduling, and a nightly task that goes red every time somebody runs hato by
hand is a false alarm that trains its owner to ignore real ones. The message
says plainly that nothing ran. Recorded in `spec/05-interface.md` for Sonic.

===========================================================================
⭐ THE LOG IS WRITTEN HERE, NOT BY THE `.cmd`
===========================================================================

`05-interface.md`: *there is exactly one config, not three* -- so the launcher
must not parse `config.toml` to find `log.path`, and a batch file cannot rotate
by runs anyway. Every run appends its full PLAIN render under a dated banner and
then trims the file to `log.keep` runs, temp-plus-rename (`LEDGER-HOT.md`).
⛔ A log that cannot be written is a NOTE on the run, never the run's failure.

===========================================================================
⛔ EXIT CODES -- A REFUSAL IS NOT A FAILURE
===========================================================================

    0   it ran. ⛔ Refusals, NOT_FOUNDs, errors on individual videos and a
        lock held by another run are all normal outcomes and must never turn a
        scheduled task red (`10-deployment.md` rule 4)
    1   it could not run: bad config, no key, no readable folder, a crash
    2   usage

⚠ A run that STOPPED early (a 401, an unreachable server) is exit 1: the run was
cut short and the remaining videos were never looked at, which is the one
in-run condition a person must be told about by a red task.
"""
from __future__ import print_function

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from hato import config as config_module, credentials, lastrun, paths, pipeline, \
    present, report
from hato.cache import Cache
from hato.client import JimakuClient, NoRecording, RecordedSession
from hato.kitsu import KitsuClient
from hato.resolution import ResolutionCache
from hato.runlock import LockHeld, LockUnusable, RunLock
from hato.state import StateDB

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: Recorded responses were made with a real key and check none (`hato identify`).
STAND_IN_KEY = u"recorded-responses-need-no-key"

#: The banner every run's log block opens with -- and the rotation marker.
LOG_BANNER = u"=== hato %s ==="
_BANNER_HEAD = u"=== hato "


def register(parser):
    parser.add_argument("folders", nargs="*", metavar="FOLDER",
                        help="folders to scan. With none, config.toml's `folders` are used")
    parser.add_argument("--dry-run", action="store_true",
                        help="identify and plan; download nothing, write nothing")
    parser.add_argument("--json", action="store_true",
                        help="NDJSON, one object per video, then one for the run")
    # ⭐ RUNBOOK 7b. ⛔ OPT-IN, so without it the output is byte-identical to
    # what every existing consumer already reads. The window needs it because
    # every object `--json` emits is built from a FINISHED report -- see the
    # `_progress_emitter` note below.
    parser.add_argument("--progress", action="store_true",
                        help="with --json, also emit {\"type\": \"progress\"} lines "
                             "AS THE RUN HAPPENS, before the per-video objects")
    parser.add_argument("--verbose", action="store_true",
                        help="raw multiples and per-candidate scores as well")
    parser.add_argument("--quiet", action="store_true",
                        help="print nothing; the log is the record (what the scheduler uses)")
    parser.add_argument("--force", action="store_true",
                        help="ignore the state DB -- re-try refusals, re-query negatives. "
                             "⛔ Never overrides a blacklist")
    parser.add_argument("--candidates", type=int, metavar="N",
                        help="how many candidates to try before refusing (default 3)")
    parser.add_argument("--out", metavar="DIR",
                        help="write there instead of beside the video, mirroring the source tree")
    parser.add_argument("--subs-dir", metavar="DIR",
                        help="where the kept originals go. ⛔ Refused inside a scanned folder")
    parser.add_argument("--lang", metavar="CODE", help="default ja")
    parser.add_argument("--no-recurse", action="store_true", help="do not walk subfolders")
    # ⭐ OPT-IN since 2026-09-17 (Sonic): *"there may be bad files downloaded in the
    # zip"*. Unpacking a stranger's archive is the one place hato acts on structure it
    # did not author, so the default is OFF and the flag turns it on for one run.
    parser.add_argument("--archives", action="store_true",
                        help="open archive candidates (.zip/.7z/.rar). Default: off")
    # ⭐ Sonic, 2026-09-17: *"if they have it toggled, it will find another one even if
    # there already is a japanese track on it"* -- for a poor embedded track (an SDH
    # rip) when a fansub file is wanted instead. ⚠ Not wasteful: that embedded track
    # becomes the reference the download is timed against.
    parser.add_argument("--even-if-embedded", action="store_true",
                        help="fetch even for a video that already carries a Japanese "
                             "track. Default: such videos are skipped for free")
    parser.add_argument("--allow-ai", action="store_true",
                        help="allow machine-generated subtitles as candidates")
    parser.add_argument("--no-color", action="store_true",
                        help="never colour, even on a terminal")
    parser.add_argument("--no-log", action="store_true", help="do not write the run log")
    parser.add_argument("--fixtures", metavar="DIR",
                        help="answer every jimaku request from recorded responses under DIR "
                             "instead of the network (no key is read)")


# ---------------------------------------------------------------------------
# ⭐ the one place the run's world is built -- and the suite's seam
# ---------------------------------------------------------------------------

class World(object):
    u"""Everything `pipeline.run()` is handed, plus the things to close.

    ⛔ A SEAM, and a deliberate one. `test_endtoend.py` must drive the REAL
    `cli.main()` -- argument parsing, the lock, the log, the renderer, the exit
    code -- while supplying subtitle bytes and a verdict, because Whitelist 2
    forbids recording a subtitle BODY and the download fixtures are metadata
    only (`07-test-plan.md`). Replacing `build_world` is how it does that, so
    everything else on the path is the product.
    """

    __slots__ = ("client", "db", "resolutions", "kitsu", "cache",
                 "downloader", "engine", "reader")

    def __init__(self, client, db, resolutions, kitsu=None, cache=None,
                 downloader=None, engine=None, reader=None):
        self.client = client
        self.db = db
        self.resolutions = resolutions
        self.kitsu = kitsu
        self.cache = cache
        self.downloader = downloader
        self.engine = engine
        self.reader = reader

    def close(self):
        for owned in (self.db,):
            try:
                owned.close()
            except Exception:                     # ⚠ never the reason a run fails
                pass


def build_world(args):
    u"""-> World. Raises `credentials.KeyMissing` / `paths.PathError` by name."""
    fixtures = Path(args.fixtures).expanduser() if args.fixtures else None
    session = RecordedSession(fixtures) if fixtures is not None else None
    if fixtures is not None:
        key = credentials.Key(STAND_IN_KEY, u"--fixtures")
    else:
        key = credentials.resolve_key()
    return World(client=JimakuClient(key, session),
                 db=StateDB(), resolutions=ResolutionCache(),
                 kitsu=KitsuClient(session), cache=Cache())


# ---------------------------------------------------------------------------
# the log
# ---------------------------------------------------------------------------

def log_text(text, path, keep):
    u"""Append one run's block and trim the file to `keep` runs. -> note or None

    ⚠ APPEND FIRST, TRIM SECOND. The append cannot lose anything (`open(...,'a')`
    never truncates); the trim rewrites, and a rewrite is temp-plus-rename or it
    is a way to lose a log to a `UnicodeEncodeError` halfway through
    (`LEDGER-HOT.md` -- it destroyed a spec file on 2026-09-07).
    """
    path = Path(path)
    block = u"%s\n%s\n" % (LOG_BANNER % datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"),
                           report.strip_ansi(text).rstrip())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(path), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(block + u"\n")
    except (OSError, UnicodeError) as exc:
        return u"the run log at %s could not be written (%s), so this run is not in it." % (
            path, exc)
    try:
        _trim(path, keep)
    except (OSError, UnicodeError) as exc:
        return u"the run log at %s could not be rotated (%s); it will keep growing." % (
            path, exc)
    return None


def _trim(path, keep):
    with open(str(path), encoding="utf-8") as fh:
        text = fh.read()
    blocks = text.split(_BANNER_HEAD)
    # `blocks[0]` is whatever preceded the first banner -- kept only if it has
    # content, so a hand-written note at the top of the log is not eaten.
    head = blocks[0]
    runs = [_BANNER_HEAD + b for b in blocks[1:]]
    if len(runs) <= max(int(keep), 1):
        return
    kept = head + u"".join(runs[-max(int(keep), 1):])
    temp = path.with_name(path.name + u".new")
    with open(str(temp), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(kept)
    os.replace(str(temp), str(path))


# ---------------------------------------------------------------------------
# the terminal
# ---------------------------------------------------------------------------

def wants_colour(args, stream=None):
    u"""⛔ COLOUR ONLY ON A REAL TERMINAL. ANSI in a log file is noise
    (`10-deployment.md` rule 3), and the scheduled run's output is a file."""
    if args.no_color or args.json or os.environ.get("NO_COLOR"):
        return False
    stream = sys.stdout if stream is None else stream
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def terminal_width(stream=None):
    u"""The console's width when there is a console, else the fixed one -- so a
    log file is comparable between runs and between machines."""
    stream = sys.stdout if stream is None else stream
    try:
        if not stream.isatty():
            return report.DEFAULT_WIDTH
    except (AttributeError, ValueError):
        return report.DEFAULT_WIDTH
    try:
        import shutil
        columns = shutil.get_terminal_size((report.DEFAULT_WIDTH, 25)).columns - 1
    except Exception:
        return report.DEFAULT_WIDTH
    return max(report.MIN_WIDTH, min(columns, 120))


def _say(args, text):
    u"""Print to stdout -- unless nobody is reading it, or a MACHINE is.

    🚨 `--json` IS A STREAM WITH A GRAMMAR. `05-interface.md` §*The window*
    spawns `hato --json` and paints the NDJSON; one English sentence in that
    stream is a parse error, and the exit code beside it says the run succeeded.
    Gating on `args.quiet` alone let the lock-held sentence through -- measured
    2026-09-17. ⛔ Nothing reaches stdout in `--json` mode that is not NDJSON.
    """
    if args.quiet or getattr(args, "json", False):
        return
    sys.stdout.write(text if text.endswith(u"\n") else text + u"\n")
    sys.stdout.flush()


def _progress_emitter(args):
    u"""-> a `(dict) -> None` for `pipeline.run(on_progress=)`, or None.

    🚨 THE PART 1 DEFECT THIS CLOSES. `05-interface.md` §*The window* rules
    *"show the process as it does it automatically"*, and every object `--json`
    emits is built from a FINISHED `RunReport` -- `report.ndjson(run_report)`
    runs after `pipeline.run()` returns. So the window could paint a spinner
    and nothing else. The requirement had been checked against a command that
    emits the right objects at the wrong TIME.

    ⭐ OPT-IN, AND THE GRAMMAR IS UNTOUCHED. Without `--progress` this returns
    None, no branch in the pipeline runs, and stdout is byte-identical to the
    run before it. With it, the extra lines are NDJSON like everything else and
    carry `type` so a consumer filters rather than guesses -- which the suite
    already does (`test_json_is_ndjson_that_parses_one_object_per_video`).

    ⚠ A `result` line and the final `video` object describe the SAME video, on
    purpose: the live one is provisional and the final one is authoritative.
    Both go through `report.as_dict`, so they cannot drift into two shapes.

    ⛔ WITHOUT `--json` THERE IS NO STREAM TO PUT THEM IN. `--progress` alone
    would interleave JSON into the human render, so it is refused by
    `_check_progress` before the run starts rather than ignored here.
    """
    if not (args.progress and args.json and not args.quiet):
        return None

    def emit(event):
        result = event.pop("result", None)
        if result is not None:
            obj = report.as_dict(result)
            obj.update(event)
        else:
            obj = dict(event)
        obj["type"] = "progress"
        sys.stdout.write(
            json.dumps(obj, ensure_ascii=False, sort_keys=True) + u"\n")
        # ⛔ FLUSHED EVERY LINE. Unflushed, the pipe buffers ~8 KB and the whole
        # point -- that the line arrives WHILE the work happens -- is lost, in a
        # way no assertion about the finished output could ever see.
        sys.stdout.flush()

    return emit


def _fail(message):
    sys.stderr.write(u"hato: %s\n" % message)
    return EXIT_FAILED


def _usage_fail(message):
    u"""⚠ A FLAG GOT A VALUE IT MAY NOT HAVE -- exit 2, not 1.

    `10-deployment.md` rule 4 reads non-zero as *"it could not run at all"* and
    `hato/cli.py` splits that into 1 (it could not do what was asked) and 2
    (the asking was wrong). A mistyped flag is the second, and a person who ran
    `hato --candidates 0` wants to be told which word was wrong, not that hato
    is broken.
    """
    sys.stderr.write(u"hato: %s\n" % message)
    return EXIT_USAGE


def check_flags(args):
    u"""Everything a FLAG can get wrong, refused before the run. -> message|None

    ===========================================================================
    🚨 THE FLAG AND THE FILE ARE TWO ROADS TO ONE SETTING, AND THEY DISAGREED
    ===========================================================================

    `config.toml` refuses `candidates = 0`, a relative `out`, a relative
    `subs_dir` and `lang = "ja-JP"`, each for a reason `05-interface.md` gives.
    The flags refused none of them, and every one of those reasons is about what
    the value DOES, not about where it was typed. Measured on 2026-09-17:

    * `--candidates 0` -> `fresh[:0]`, nothing tried, and the soft negative that
      records *it asked* written anyway. The corrected run reported *"asked for
      recently and not there yet"* and made ZERO API calls. One digit, one lost
      day. (`--candidates -1` is `fresh[:-1]` -- *all but the last*, silently.)
    * `--subs-dir kept` put the KEPT ORIGINALS -- which hato may never delete --
      into `<cwd>\\kept`. From Task Scheduler that is `%SystemRoot%\\System32`.
    * `--lang ja-JP` was accepted here and refused in the file, and `ja-JP` is
      the one tag `05-interface.md` names as broken on Jellyfin.

    ⛔ The sentences are `hato/config.py`'s own, called and never re-typed.
    """
    if args.candidates is not None and args.candidates < 1:
        return config_module.candidates_refusal(u"--candidates", args.candidates)
    for flag, value in ((u"--out", args.out), (u"--subs-dir", args.subs_dir)):
        # ⚠ The FOLDERS are deliberately not held to this: a person in a
        # terminal types `hato .`, and a scanned folder is read, never written.
        # These two are where hato PUTS things.
        if value and not os.path.isabs(os.path.expanduser(value)):
            return config_module.relative_path_refusal(flag, value)
    if args.lang is not None:
        try:
            config_module.check_lang(args.lang, u"--lang")
            # ⭐ AND TSUBASA'S ANSWER TOO, asked here rather than four frames
            # into the run: `jp` passes the naming rule and resolves to `und`,
            # and `und` matches every untagged subtitle in the library. Asking
            # now costs nothing and spends no key, no lock and no DB handle.
            present.language(args.lang)
        except (config_module.ConfigError, present.LanguageUnknown) as exc:
            return str(exc)
    # ⭐ RUNBOOK 7b. ⛔ REFUSED, NOT IGNORED. `--progress` writes JSON objects,
    # and without `--json` they would land in the middle of the human render --
    # so the flag would appear to work while corrupting the only output there
    # is. `--quiet` is the same question answered the other way: it means
    # nothing reaches stdout, and progress is stdout.
    if args.progress and not args.json:
        return (u"--progress emits JSON lines as the run happens, so it needs "
                u"--json to put them in. Use `--json --progress`.")
    if args.progress and args.quiet:
        return (u"--progress and --quiet contradict each other: --quiet means "
                u"nothing is printed, and progress is something printed.")
    return None


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def run(args):
    # ⭐ FIRST, AND BEFORE ANYTHING IS READ OR OPENED. A flag with a value it
    # may not have is wrong whatever config.toml says, and refusing it here
    # spends no key, no lock, no DB handle and no API call.
    problem = check_flags(args)
    if problem:
        return _usage_fail(problem)

    try:
        cfg = config_module.load()
    except (config_module.ConfigError, paths.PathError) as exc:
        return _fail(str(exc))

    if not args.folders and not cfg.folders:
        # ⭐ Bare `hato` with nothing configured is the one case that is a USAGE
        # mistake rather than a run: the person has not told it what to do, and
        # the commands they were probably looking for are one screen away.
        from hato import cli
        sys.stderr.write(u"hato: no folder to scan -- none was given and `folders` is empty "
                         u"in %s.\n      Pass a folder, or add one to that file.\n\n"
                         % (cfg.path if cfg.path else u"config.toml"))
        sys.stderr.write(cli.usage() + u"\n")
        return EXIT_USAGE

    try:
        settings = pipeline.Settings.from_config(
            cfg,
            folders=[os.path.abspath(os.path.expanduser(f)) for f in args.folders] or None,
            lang=args.lang, out=args.out, subs_dir=args.subs_dir,
            candidates=args.candidates,
            archives=True if args.archives else None,
            skip_embedded=False if args.even_if_embedded else None,
            allow_ai=True if args.allow_ai else None,
            recurse=False if args.no_recurse else None,
            force=args.force, dry_run=args.dry_run)
    except (pipeline.ConfigProblem, paths.PathError) as exc:
        # ⚠ `paths.PathError` TOO, AND THAT IS NOT DEFENSIVE. `cfg.subs_dir` is
        # a lazy property: with `subs_dir` empty it calls `paths.default_subs_dir()`
        # HERE, which is the first thing in a run to read HATO_CACHE. A relative
        # HATO_CACHE was therefore 22 lines of traceback while a relative
        # HATO_CONFIG -- caught above -- was one clean line. Measured 2026-09-17.
        return _fail(str(exc))

    try:
        world = build_world(args)
    except (credentials.KeyMissing, paths.PathError, NoRecording) as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail(u"the run could not be set up: %s" % exc)

    lock = RunLock()
    try:
        try:
            lock.acquire()
        except LockHeld as exc:
            # ⛔ NOT a failure. See the module docstring -- exit 0, and say
            # plainly that nothing ran.
            # 🚨 AND NOT ON STDOUT UNDER `--json`. ⛔ ONE GATE, AND IT IS
            # `_say`'s: a second `if args.json` here would be a branch that
            # agrees with `_say` and hides it, so removing `_say`'s gate would
            # change nothing observable and no check could fail on it. `_say`
            # refuses the line; this puts it where a machine is not parsing.
            _say(args, u"hato: %s" % exc)
            if args.json:
                sys.stderr.write(u"hato: %s\n" % exc)
            sys.stderr.write(u"hato: nothing was scanned and nothing was written.\n")
            return EXIT_OK
        except LockUnusable as exc:
            # ⚠ NOT another run -- the lock itself could not be created or read.
            # `hato/runlock.py` promises *"a message that says what to delete"*,
            # and a raw PermissionError through the scheduled path left the log
            # saying only *"hato exited 1"*. Measured 2026-09-17.
            return _fail(str(exc))
        try:
            run_report = pipeline.run(
                settings, client=world.client, db=world.db,
                resolutions=world.resolutions, kitsu=world.kitsu, cache=world.cache,
                downloader=world.downloader, engine=world.engine, reader=world.reader,
                on_progress=_progress_emitter(args))
        except pipeline.ConfigProblem as exc:
            return _fail(str(exc))
        except Exception as exc:                  # ⚠ a crash is a fault: say so, loudly
            sys.stderr.write(u"hato: the run stopped on an unexpected %s: %s\n%s\n"
                             % (type(exc).__name__, exc, traceback.format_exc()))
            return EXIT_FAILED
        finally:
            lock.release()
    finally:
        world.close()

    if lock.note:
        run_report.notes.append(lock.note)

    # ⭐ EVERY RUN LEAVES A TRACE THE WINDOW CAN READ (RUNBOOK 7i), whoever
    # started it -- the tray, the scheduler, or a terminal. Until this existed
    # only the window wrote one, so a tray-triggered run did its job and the
    # open window showed nothing: *"it worked but the ui didn't update."*
    # ⛔ Never fails a run: the subtitles are already beside the videos.
    lastrun.save([report.as_dict(r) for r in run_report.results],
                 report.run_dict(run_report))

    plain = report.render(run_report, colour=False, verbose=args.verbose,
                          width=report.DEFAULT_WIDTH)
    if not args.no_log:
        note = log_text(plain, cfg.log_path_resolved, cfg.log_keep)
        if note:
            sys.stderr.write(u"hato: %s\n" % note)

    if args.json:
        if not args.quiet:
            for line in report.ndjson(run_report):
                sys.stdout.write(line + u"\n")
            sys.stdout.flush()
    else:
        _say(args, report.render(run_report, colour=wants_colour(args),
                                 verbose=args.verbose, width=terminal_width()))

    if run_report.stopped:
        # ⚠ The ONE in-run condition that is a failure: the run was cut short
        # and the videos after it were never looked at.
        sys.stderr.write(u"hato: the run stopped early: %s\n" % run_report.stopped)
        return EXIT_FAILED
    return EXIT_OK
