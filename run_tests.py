#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The runner.

    python run_tests.py                        every DEFAULT suite
    python run_tests.py client rank            just those (opt-in suites too)
    python run_tests.py --verify-registration  the self-check alone, no suites
    python run_tests.py --list                 harnesses, suites, excused

Seven properties, each paid for somewhere (doctrine/verification.md,
spec/07-test-plan.md):

  1. ⭐ A TEST NOT IN THE RUNNER DOES NOT EXIST -- AND THE RUNNER PROVES IT. It
     enumerates every harness file on disk and FAILS on any that is neither in a
     suite nor excused in hato.config.json with a written reason. The prose
     version of this rule failed twice on tsubasa's source project.

  2. ZERO CHECKS IS A FAILURE, NOT A PASS. Counts come from pytest's JUnit XML,
     never from regexing "49 passed" out of prose.

  3. A TOOLING FAULT ANNOUNCES ITSELF AS ONE, with its own exit code.

  4. EVERY SUITE'S FULL OUTPUT IS WRITTEN TO DISK, named for the run.

  5. THE RUNNER RUNS ALONE. A lock file makes a second run a refusal.

  6. ⭐ THE PER-USER STORE IS REDIRECTED BY THE RUNNER ITSELF, and teardown is
     VERIFIED, not assumed: HATO_CACHE, HATO_CONFIG, TSUBASA_CACHE and the key
     file all point into one temp dir; afterwards the runner asserts that dir is
     gone AND that the real %LOCALAPPDATA%\\hato is exactly as it was. A test
     run cannot read the real cache, the real DB or the real keystore.

  7. ⛔ THE DEFAULT RUN MAKES ZERO NETWORK CALLS. HATO_NO_NETWORK=1 reaches every
     subprocess; conftest.py adds an in-process socket guard. The `live` suite is
     kept out of the default run by `"default": false` in the config -- by
     configuration, not by discipline -- and runs only when named.

Exit codes:  0 green · 1 a suite failed · 3 tooling fault · 4 orphaned harness
             · 5 isolation fault (a test touched the real per-user store, or
             its temp dir survived teardown)

⚠ PYTHONUTF8=1 is set for every suite. Windows Python defaults to cp1252 and
raised UnicodeDecodeError on the very first real jimaku response (LEDGER-HOT.md).
"""
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_NAME = "hato.config.json"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_TOOLING = 3
EXIT_ORPHAN = 4
EXIT_ISOLATION = 5

# pytest's own codes that do NOT mean "a test failed".
PYTEST_TOOLING_CODES = {2: "interrupted", 3: "internal error",
                        4: "usage error", 5: "no tests collected"}


class ToolingFault(Exception):
    pass


def stderr(msg):
    sys.stdout.flush()
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def rule(title):
    sys.stdout.write("\n%s\n  %s\n%s\n" % ("=" * 74, title, "=" * 74))
    sys.stdout.flush()


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def load_config():
    path = HERE / CONFIG_NAME
    try:
        with open(str(path), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ToolingFault("%s could not be read: %s" % (path, exc))
    test = cfg.get("test")
    if not isinstance(test, dict):
        raise ToolingFault("%s has no `test` section" % path)
    for key in ("harnessDir", "harnessPattern", "runLogDir", "suites"):
        if key not in test:
            raise ToolingFault("%s: test.%s is missing" % (path, key))
    names = [s.get("name") for s in test["suites"]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ToolingFault("%s: duplicate suite name(s): %s" % (path, ", ".join(dupes)))
    for s in test["suites"]:
        if not s.get("name") or not isinstance(s.get("cmd"), list) or not s["cmd"]:
            raise ToolingFault("%s: every suite needs a name and a cmd list: %r" % (path, s))
        if s.get("default", True) is False and not s.get("why"):
            raise ToolingFault("%s: suite %r is kept out of the default run with "
                               "no written reason" % (path, s["name"]))
    return cfg


# --------------------------------------------------------------------------
# 1. the self-check
# --------------------------------------------------------------------------

def harnesses_on_disk(cfg):
    d = HERE / cfg["test"]["harnessDir"]
    pattern = re.compile(cfg["test"]["harnessPattern"])
    if not d.is_dir():
        return []
    return sorted(p.resolve() for p in d.rglob("*.py") if pattern.match(p.name))


def coverage_of(suite, all_harnesses):
    """Which harness files this suite's command runs -- derived from the
    command, never declared beside it (a declaration is a copy that drifts)."""
    covered = set()
    for token in suite["cmd"]:
        candidate = HERE / token
        if not candidate.exists():
            continue
        candidate = candidate.resolve()
        if candidate.is_dir():
            covered.update(h for h in all_harnesses
                           if str(h).startswith(str(candidate) + os.sep))
        elif candidate in all_harnesses:
            covered.add(candidate)
    return covered


#: Folders that hold no source of ours. ⚠ Top-level build outputs and caches only.
NOT_SOURCE = {".git", "__pycache__", ".pytest_cache", "_runs", "dist", "build",
              "node_modules", ".venv", "venv"}


def unparsable(root=None):
    """Every .py under the project that does not PARSE. -> [(path, "line N: why")]

    ⭐ HANDOFF §5: *"a `py_compile` gate before any shell-written `.py` -- the
    heredoc trap has hit five times"* (six, by 2026-09-22). A suite only notices
    a broken file it IMPORTS; `packaging/`, `gui-shots/` and a probe copied in
    are imported by none, so one could sit broken until the day it is needed.
    ⚠ `compile()`, never `py_compile`: that writes a .pyc into the vault.
    """
    root = Path(root) if root is not None else HERE
    bad = []
    for folder, dirs, files in os.walk(str(root)):
        dirs[:] = sorted(d for d in dirs if d not in NOT_SOURCE)
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = Path(folder) / name
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec", dont_inherit=True)
            except SyntaxError as exc:
                bad.append((path, "line %s: %s" % (exc.lineno, exc.msg)))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                bad.append((path, "%s: %s" % (type(exc).__name__, exc)))
    return bad


def self_check(cfg):
    found = harnesses_on_disk(cfg)
    excused = cfg["test"].get("excused", {}) or {}
    harness_dir = cfg["test"]["harnessDir"]

    registered = set()
    for suite in cfg["test"]["suites"]:
        registered |= coverage_of(suite, found)
    excused_paths = {(HERE / harness_dir / name).resolve() for name in excused}
    unexplained = [n for n, why in excused.items() if not str(why).strip()]

    orphans = [h for h in found if h not in registered and h not in excused_paths]

    missing = []
    for suite in cfg["test"]["suites"]:
        for token in suite["cmd"]:
            norm = token.replace("\\", "/")
            if norm.startswith(harness_dir + "/") and norm.endswith(".py"):
                if not (HERE / token).exists():
                    missing.append((suite["name"], token))
    return found, orphans, missing, excused, unexplained


# --------------------------------------------------------------------------
# 2. counting what actually ran
# --------------------------------------------------------------------------

def parse_junit(path):
    if not path.is_file():
        return None
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = fail = err = skip = 0
    for s in suites:
        total += int(s.get("tests", 0))
        fail += int(s.get("failures", 0))
        err += int(s.get("errors", 0))
        skip += int(s.get("skipped", 0))
    return total, fail, err, skip


# --------------------------------------------------------------------------
# 6. isolation
# --------------------------------------------------------------------------

def real_data_root():
    """The per-user root a real run would use, IGNORING every override.

    ⚠ Must track `hato.paths.default_data_root()` exactly. This guard proves a test run
    left the real store alone, so if it names a folder hato no longer uses it watches a
    dead path and passes for ever. It said `~/.cache/hato` after 1c moved the real root
    to `~/.local/share/hato` -- caught by that step's builder, fixed here.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "hato" if base else None
    return Path.home() / ".local" / "share" / "hato"


def real_config_path():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "hato" / "config.toml" if base else None
    return Path.home() / ".config" / "hato" / "config.toml"


def snapshot(root, config):
    """What a test run must leave exactly as it found it.

    Every DIRECTORY's mtime under the real root (creating, deleting or renaming
    any file changes its directory's mtime, and hato writes by temp-plus-rename,
    so every write it can make is visible here) plus each top-level file's size
    and mtime. Directories, not files: the real cache can hold thousands of
    files, and walking them all would make this check the slow part.
    """
    snap = {}
    if root is not None and root.exists():
        for dirpath, dirnames, filenames in os.walk(str(root)):
            st = os.stat(dirpath)
            snap["dir:" + dirpath] = st.st_mtime_ns
            if Path(dirpath) == root:
                for f in filenames:
                    fst = os.stat(os.path.join(dirpath, f))
                    snap["file:" + f] = (fst.st_size, fst.st_mtime_ns)
    else:
        snap["absent:root"] = True
    if config is not None and config.exists():
        cst = config.stat()
        snap["config"] = (cst.st_size, cst.st_mtime_ns)
    return snap


def suite_env(temp_root, suite):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["HATO_TEST_ROOT"] = str(temp_root)
    env["HATO_CACHE"] = str(temp_root / "data")
    env["HATO_CONFIG"] = str(temp_root / "config.toml")
    env["TSUBASA_CACHE"] = str(temp_root / "tsubasa")
    if suite.get("live"):
        env["HATO_LIVE"] = "1"
        env.pop("HATO_NO_NETWORK", None)
    else:
        env.pop("HATO_LIVE", None)
        env["HATO_NO_NETWORK"] = "1"
        # ⛔ No test reads the real keystore.
        env.pop("HATO_JIMAKU_KEY", None)
        env["HATO_KEYFILE"] = str(temp_root / "no-such-key.txt")
    extra = [str(HERE)]
    checkout = checkout_of_tsubasa()
    if checkout is not None:
        extra.append(str(checkout))
    if env.get("PYTHONPATH"):
        extra.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(extra)
    return env


def checkout_of_tsubasa():
    try:
        cfg = load_config()
    except ToolingFault:
        return None
    rel = (cfg.get("tsubasa") or {}).get("checkoutRelative")
    return (HERE / rel).resolve() if rel else None


# --------------------------------------------------------------------------
# 3. running one suite
# --------------------------------------------------------------------------

def run_suite(suite, run_dir, temp_root):
    name = suite["name"]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name)
    log_path = run_dir / ("%s.txt" % safe)
    junit_path = run_dir / ("%s.xml" % safe)

    cmd = [sys.executable] + list(suite["cmd"])
    is_pytest = "pytest" in cmd
    if is_pytest:
        cmd += ["--junitxml=%s" % junit_path, "-p", "no:cacheprovider"]

    rule(name)
    sys.stdout.write("  %s\n\n" % " ".join(cmd[1:]))
    sys.stdout.flush()

    started = time.time()
    proc = subprocess.run(cmd, cwd=str(HERE), env=suite_env(temp_root, suite),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    elapsed = time.time() - started
    output = proc.stdout.decode("utf-8", errors="replace")
    sys.stdout.write(output)
    sys.stdout.flush()

    run_dir.mkdir(parents=True, exist_ok=True)
    with open(str(log_path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("$ %s\n\n%s\nexit=%d  elapsed=%.1fs\n"
                 % (" ".join(cmd), output, proc.returncode, elapsed))

    counts = parse_junit(junit_path) if is_pytest else None
    result = {"name": name, "rc": proc.returncode, "elapsed": elapsed,
              "log": log_path, "counts": counts, "verdict": None, "why": ""}

    if is_pytest and proc.returncode in PYTEST_TOOLING_CODES:
        result["verdict"] = "TOOLING"
        result["why"] = "pytest: %s (exit %d)" % (
            PYTEST_TOOLING_CODES[proc.returncode], proc.returncode)
        return result
    if counts is None:
        result["verdict"] = "TOOLING"
        result["why"] = "no machine-readable result -- the suite produced no report"
        return result
    total, failures, errors, skipped = counts
    if total == 0:
        result["verdict"] = "TOOLING"
        result["why"] = "ZERO checks ran. Exit 0 is not a pass."
        return result
    if failures or errors or proc.returncode != 0:
        result["verdict"] = "FAIL"
        result["why"] = "%d failed, %d errored of %d" % (failures, errors, total)
        return result
    result["verdict"] = "PASS"
    result["why"] = "%d checks%s" % (total, (", %d skipped" % skipped) if skipped else "")
    return result


# --------------------------------------------------------------------------
# timings -- so a long run can say what it will cost before it starts
# --------------------------------------------------------------------------

def _timings_path(cfg):
    return HERE / cfg["test"]["runLogDir"] / "timings.json"


def expected_line(cfg, key):
    try:
        with open(str(_timings_path(cfg)), encoding="utf-8") as fh:
            seen = json.load(fh).get(key, [])
    except (OSError, ValueError):
        return None
    if not seen:
        return None
    last = seen[-5:]
    return "expected ~%.0fs (seen %.0f-%.0fs over %d run%s)" % (
        statistics.median(last), min(last), max(last), len(last),
        "" if len(last) == 1 else "s")


def record_timing(cfg, key, seconds):
    path = _timings_path(cfg)
    try:
        with open(str(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data[key] = (data.get(key, []) + [round(seconds, 1)])[-20:]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(str(tmp), str(path))   # temp-plus-rename, never truncate in place


# --------------------------------------------------------------------------
# the lock
# --------------------------------------------------------------------------

def _pid_running(pid):
    """Is `pid` a live process? Unknown counts as running (never steal on doubt)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259                        # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


class RunLock(object):
    """⚠ EXCLUSIVE CREATE, not check-then-write: two runners started together
    could both pass an `exists()` check and both run (found by the Wave 1
    builder, 2026-09-17). A lock whose pid is no longer running is taken over
    with a note, rather than blocking every later run until someone deletes it."""

    def __init__(self, path):
        self.path = path
        self.held = False

    def _create(self):
        fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": os.getpid(),
                                 "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._create()
        except FileExistsError:
            try:
                info = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                info = {}
            if info and not _pid_running(info.get("pid")):
                print("  note: took over a lock left by a run that is no longer running "
                      "(pid %s, started %s)" % (info.get("pid"), info.get("started")))
                self.path.unlink()
                try:
                    self._create()
                except FileExistsError:
                    stderr("\nAnother run took the lock at the same moment.")
                    raise SystemExit(EXIT_TOOLING)
            else:
                stderr("\nA run is already in flight (pid %s, started %s)."
                       % (info.get("pid", "?"), info.get("started", "?")))
                stderr("  Two runners at once race on shared state and read like a regression.")
                stderr("  If that run is dead: del %s" % self.path)
                raise SystemExit(EXIT_TOOLING)
        self.held = True
        return self

    def __exit__(self, *exc):
        if self.held and self.path.exists():
            self.path.unlink()
        return False


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] if argv is None else list(argv)
    want_list = "--list" in argv
    verify_only = "--verify-registration" in argv
    unknown_flags = [a for a in argv if a.startswith("-")
                     and a not in ("--list", "--verify-registration")]
    if unknown_flags:
        stderr("unknown flag(s): %s" % " ".join(unknown_flags))
        return EXIT_TOOLING
    names = [a for a in argv if not a.startswith("-")]

    try:
        cfg = load_config()
    except ToolingFault as exc:
        stderr("\nTOOLING FAULT -- the project config, not a test\n  %s" % exc)
        return EXIT_TOOLING

    found, orphans, missing, excused, unexplained = self_check(cfg)
    suites = cfg["test"]["suites"]

    if want_list:
        print("harness files on disk (%s/):" % cfg["test"]["harnessDir"])
        for h in found:
            print("  %s" % h.relative_to(HERE))
        print("\nsuites:")
        for s in suites:
            tag = "" if s.get("default", True) else "  [opt-in: %s]" % s.get("why", "")[:60]
            print("  %-16s %s%s" % (s["name"], " ".join(s["cmd"]), tag))
        if excused:
            print("\nexcused:")
            for name, why in excused.items():
                print("  %-24s %s" % (name, why))
        return EXIT_OK

    rule("RUNNER SELF-CHECK  (every harness registered or excused in writing)")
    print("  %d harness file(s) on disk, %d suite(s), %d excused"
          % (len(found), len(suites), len(excused)))
    if missing:
        stderr("\nTOOLING FAULT -- a suite names a harness that does not exist:")
        for suite_name, token in missing:
            stderr("  %-16s -> %s" % (suite_name, token))
        return EXIT_TOOLING
    if unexplained:
        stderr("\nTOOLING FAULT -- excused with no written reason: %s" % ", ".join(unexplained))
        return EXIT_TOOLING
    if orphans:
        stderr("\nORPHANED HARNESS -- on disk, in no suite, with no written excuse:")
        for h in orphans:
            stderr("  %s" % h.relative_to(HERE))
        stderr("\n  A test not in the runner does not exist. Register it under")
        stderr("  test.suites in hato.config.json, or excuse it there WITH THE REASON.")
        return EXIT_ORPHAN
    print("  OK  no orphans")
    broken = unparsable()
    if broken:
        stderr("\nTOOLING FAULT -- a .py file here does not PARSE (a heredoc, a half-edit):")
        for path, why in broken:
            stderr("  %s  %s" % (path.relative_to(HERE), why))
        return EXIT_TOOLING
    print("  OK  every .py parses")
    if verify_only:
        return EXIT_OK

    by_name = {s["name"]: s for s in suites}
    if names:
        unknown = [n for n in names if n not in by_name]
        if unknown:
            stderr("\nTOOLING FAULT -- no such suite: %s. Known: %s"
                   % (", ".join(unknown), ", ".join(sorted(by_name))))
            return EXIT_TOOLING
        chosen = [by_name[n] for n in names]
    else:
        chosen = [s for s in suites if s.get("default", True)]
        skipped = [s for s in suites if not s.get("default", True)]
        for s in skipped:
            print("  opt-in, not run by default: %-10s %s" % (s["name"], s.get("why", "")))

    key = "all-default" if not names else "+".join(sorted(names))
    exp = expected_line(cfg, key)
    print("  running %d suite(s): %s" % (len(chosen), exp or "not timed yet -- this run is the baseline"))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / cfg["test"]["runLogDir"] / stamp
    real_root, real_cfg = real_data_root(), real_config_path()
    before = snapshot(real_root, real_cfg)
    temp_root = Path(tempfile.mkdtemp(prefix="hato-run-"))

    results = []
    started = time.time()
    with RunLock(HERE / cfg["test"]["runLogDir"] / ".run.lock"):
        try:
            for suite in chosen:
                results.append(run_suite(suite, run_dir, temp_root))
        finally:
            shutil.rmtree(str(temp_root), ignore_errors=True)
    total_elapsed = time.time() - started

    # --- verified teardown ---------------------------------------------------
    isolation = []
    if temp_root.exists():
        isolation.append("the run's temp dir survived teardown: %s" % temp_root)
    after = snapshot(real_root, real_cfg)
    if after != before:
        changed = sorted(set(k for k in set(before) | set(after)
                             if before.get(k) != after.get(k)))
        isolation.append("the REAL per-user store changed during the run (%s): %s"
                         % (real_root, "; ".join(changed[:8])))

    rule("SUMMARY")
    worst = EXIT_OK
    for r in results:
        print("  %-8s %-16s %-34s %5.1fs" % (r["verdict"], r["name"], r["why"], r["elapsed"]))
        if r["verdict"] == "TOOLING":
            worst = EXIT_TOOLING
        elif r["verdict"] == "FAIL" and worst == EXIT_OK:
            worst = EXIT_FAILED
    checks = sum((r["counts"] or (0,))[0] for r in results)
    print("\n  %d suite(s), %d checks, %.1fs" % (len(results), checks, total_elapsed))
    print("  logs: %s" % run_dir.relative_to(HERE))

    if isolation:
        for line in isolation:
            stderr("\nISOLATION FAULT -- %s" % line)
        stderr("  A test run must never touch the real cache, DB, subs_dir or config.")
        return EXIT_ISOLATION

    bad = [r for r in results if r["verdict"] != "PASS"]
    if bad:
        print("\n  full output on disk:")
        for r in bad:
            print("    %s" % r["log"].relative_to(HERE))
    else:
        print("\n  GREEN")
        record_timing(cfg, key, total_elapsed)
    if worst == EXIT_TOOLING:
        print("\n  ⚠ TOOLING FAULT -- the harness is broken, which says NOTHING about")
        print("    whether the product works. Fix the harness first.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
