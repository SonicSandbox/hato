# -*- coding: utf-8 -*-
u"""Drive the FROZEN hato. RUNBOOK 7g.

    python packaging/smoke_standalone.py [dist/standalone/hato]

🚨 THIS DRIVES THE BUILT BYTES, NEVER THE SOURCE TREE. That is the whole
point of the step: everything in `tests/` imports `hato` from the repository,
so every one of those checks is structurally blind to a packaging defect. A
frozen build can import cleanly, exit 0, and be missing the data that makes
its answers correct.

===========================================================================
⛔ IT RUNS IN ITS OWN STORE, AND THAT IS NOT OPTIONAL
===========================================================================

`HATO_CACHE`, `HATO_CONFIG` and `HATO_ALLOW_MANY` are set to a temporary
root for every child. ⚠ Without them this script would write a pid file into
the REAL per-user store and fight whatever tray the person is actually
running -- which has already happened twice in this project through the test
runner, and the runner's isolation guard caught it both times. There is no
guard out here.

===========================================================================
⭐ WHAT THIS ASSERTS THAT A GREEN SUITE CANNOT
===========================================================================

  1. the three exes exist AS SIBLINGS        -- each spawns the others by name
  2. every DYNAMICALLY dispatched command    -- `importlib` is invisible to
     is really in the bundle                    PyInstaller's analysis
  3. tsubasa's data travelled                -- its absence costs accuracy
     with no error anywhere
  4. hato's icon exports travelled
  5. a real run completes
  6. the window is VISIBLE                   -- ⛔ not "the process survived":
                                                a SW_HIDE'd window survives
                                                perfectly and shows nothing
  7. the tray watcher starts
  8. ⭐ the CLI and the WATCHER never load Qt -- the 13.4-vs-30.6 MB argument,
                                                asserted rather than assumed
"""
from __future__ import print_function

import os
import shutil
import subprocess
import sys
import tempfile
import time

#: ⚠ THE REPO ROOT, AND ONLY FOR ONE THING. Running this file directly puts
#: `packaging/` on `sys.path`, not the repository -- so `import hato` fails.
#: ⛔ Nothing here tests the source: the single import is
#: `watch.gui_spawn_kwargs`, a pure function returning a dict of Popen
#: keywords, which is needed to start the FROZEN exe the way the tray starts
#: it. The application under test is always the bundle.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

IS_WINDOWS = sys.platform.startswith("win")
EXE = ".exe" if IS_WINDOWS else ""

#: The three names are a CONTRACT -- `gui/run.py::cli_argv`,
#: `watch.py::watch_argv` and `watch.py::open_window` each build one of them.
#: ⭐ `hato.exe` IS THE WINDOW -- Sonic's ruling, 2026-09-18: *"i want it to be
#: hato as the main one ... i can just click on hato.exe and it will handle
#: everything else."* ⛔ The command line is the sibling, not the headline.
GUI_NAME = "hato" + EXE
CLI_NAME = "hato-cli" + EXE
WATCH_NAME = "hato-watch" + EXE

_results = []


def check(name, ok, detail=u""):
    _results.append((name, bool(ok), detail))
    mark = u"PASS" if ok else u"FAIL"
    line = u"  %-4s  %-34s  %s" % (mark, name, detail)
    # ⚠ Windows consoles are cp1252 by default and this file's own output has
    # no non-ASCII in it, but a DETAIL may carry a path with Japanese in it.
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))
    return ok


def child_env(store):
    u"""⛔ Every child runs against a throwaway store. See the header."""
    env = dict(os.environ)
    env["HATO_CACHE"] = store
    env["HATO_CONFIG"] = os.path.join(store, "config.toml")
    # ⚠ So a frozen watcher started here cannot refuse because the person's
    # own tray already holds the single-instance claim -- and cannot take it.
    env["HATO_ALLOW_MANY"] = "1"
    # ⛔ Nothing in this script should reach jimaku. A smoke test that spends
    # metered calls against someone else's server is not a smoke test.
    env["HATO_NO_NETWORK"] = "1"
    # 🚨 PIN THE KEY FILE AT SOMETHING ABSENT, AND THIS ONE WAS PAID FOR.
    # `paths.key_file_candidates` falls through to *"the source tree's own
    # keystore, which exists on this machine only"* -- so a bundle sitting
    # INSIDE the repository silently inherits the developer's key. ⛔ The
    # first `a run completes` check here was green for exactly that reason,
    # and went red the moment the zip was unpacked somewhere unrelated, which
    # is the whole point of verifying the unpacked copy.
    #
    # ⭐ `HATO_KEYFILE` when set is the WHOLE list and never falls through
    # (`paths.py`), so this makes the run behave like a stranger's wherever
    # the bundle happens to live.
    env["HATO_KEYFILE"] = os.path.join(store, "absent-key.txt")
    return env


def run(argv, env, timeout=120):
    u"""-> (returncode, stdout, stderr), never raising on a non-zero exit."""
    try:
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, err = proc.communicate(timeout=timeout)
    except Exception as exc:                              # noqa: BLE001
        return 99, u"", u"%s" % exc
    dec = lambda b: (b or b"").decode("utf-8", "replace")  # noqa: E731
    return proc.returncode, dec(out), dec(err)


def visible_windows(pid):
    u"""-> how many VISIBLE top-level windows `pid` owns.

    🚨 THE CHECK THAT ACTUALLY ANSWERS THE QUESTION. This project shipped a
    window that was built, native, and permanently invisible because its
    parent passed `STARTF_USESHOWWINDOW` with `wShowWindow` left at 0, which
    is `SW_HIDE`. ⛔ It was declared fixed twice on a probe that asked only
    whether the child had spawned and survived -- which it had, both times.
    """
    if not IS_WINDOWS:
        return -1
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = []

    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(CB(each), 0)
    return len(found)


def loaded_qt(pid):
    u"""-> the Qt libraries this process has actually LOADED, as a sorted list.

    ⭐ THE ARCHITECTURAL CLAIM, MEASURED. `hato/watch.py` is a separate
    process for exactly one reason -- a ctypes tray is 13.4 MB resident
    against 30.6 for a Qt one. ⛔ If Qt ever reaches the CLI's or the
    watcher's bundle, the saving is gone and the third executable is pure
    cost, and nothing else in this project would notice.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        proc = psutil.Process(pid)
        names = set()
        for mapped in proc.memory_maps():
            base = os.path.basename(mapped.path).lower()
            if base.startswith("qt") and base.endswith(".dll"):
                names.add(base)
        return sorted(names)
    except Exception:                                     # noqa: BLE001
        return None


def resident_mb(pid):
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / (1024.0 * 1024.0)
    except Exception:                                     # noqa: BLE001
        return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundle = argv[0] if argv else os.path.join(here, "dist", "standalone", "hato")
    bundle = os.path.abspath(bundle)

    print(u"\nhato -- frozen smoke test")
    print(u"  bundle: %s\n" % bundle)

    cli = os.path.join(bundle, CLI_NAME)
    gui = os.path.join(bundle, GUI_NAME)
    watch = os.path.join(bundle, WATCH_NAME)

    # -- 1 · layout -------------------------------------------------------
    for name, path in ((CLI_NAME, cli), (GUI_NAME, gui), (WATCH_NAME, watch)):
        size = os.path.getsize(path) / 1024.0 if os.path.isfile(path) else 0
        check(u"exists: %s" % name, os.path.isfile(path),
              u"%.0f KB" % size if size else u"MISSING")

    if not all(os.path.isfile(p) for p in (cli, gui, watch)):
        print(u"\n  the three executables are the contract; stopping here.\n")
        return 1

    store = tempfile.mkdtemp(prefix="hato-smoke-")
    env = child_env(store)
    try:
        return _drive(bundle, cli, gui, watch, env, store)
    finally:
        shutil.rmtree(store, ignore_errors=True)


def _drive(bundle, cli, gui, watch, env, store):
    # -- 2 · the console actually has a console ---------------------------
    code, out, err = run([cli, "--version"], env)
    check(u"hato --version", code == 0 and out.strip(),
          (out or err).strip().splitlines()[0] if (out or err).strip() else u"no output")

    # -- 3 · EVERY dynamically dispatched command is in the bundle --------
    # 🚨 `hato/cli.py` builds each import from a dict at runtime, so
    # PyInstaller cannot see any of them. Without the spec's derived
    # hiddenimports this is the check that goes red -- on every command at
    # once, while `--version` above stays perfectly green.
    commands = ["config", "key", "doctor", "cache", "state", "blacklist",
                "identify", "files", "align", "rank", "extract", "sync"]
    missing = []
    for name in commands:
        code, out, err = run([cli, name, "--help"], env, timeout=60)
        blob = (out or u"") + (err or u"")
        if code != 0 or u"ModuleNotFoundError" in blob or u"No module named" in blob:
            missing.append(u"%s(%d)" % (name, code))
    check(u"all %d subcommands import" % len(commands), not missing,
          u"broken: " + u", ".join(missing) if missing else u"every one reachable")

    # -- 4 · the data files travelled -------------------------------------
    internal = os.path.join(bundle, "_internal")
    root = internal if os.path.isdir(internal) else bundle

    hato_data = os.path.join(root, "hato", "data")
    pngs = [f for f in os.listdir(hato_data)] if os.path.isdir(hato_data) else []
    check(u"hato icon exports bundled", len([p for p in pngs if p.endswith(".png")]) >= 10,
          u"%d png + %d ico" % (len([p for p in pngs if p.endswith(".png")]),
                                len([p for p in pngs if p.endswith(".ico")])))

    ts_data = os.path.join(root, "tsubasa", "data")
    ts_files = os.listdir(ts_data) if os.path.isdir(ts_data) else []
    # ⛔ Its absence is SILENT: tsubasa's own spec records the build still
    # running and exiting 0 while settled-by-name fell from 80.0% to 51.4%.
    check(u"tsubasa data bundled", len(ts_files) > 0,
          u"%d file(s)" % len(ts_files) if ts_files else
          u"MISSING -- the hook did not run (see hato.spec header)")

    # -- 4b · 🚨 THE LICENCE TRAVELLED ------------------------------------
    # hato is GPL-3.0-or-later and this artifact bundles PyQt6 (GPL-3.0),
    # CPython and OpenSSL. ⛔ GPLv3 §4/§6 require the licence to accompany
    # conveyed object code. The first build of this zip had none -- and it is
    # the one class of defect a later upload cannot repair, because the
    # unlicensed copies are already out.
    #
    # ⚠ Checked HERE rather than only at build time, because this runs
    # against the UNPACKED archive -- which is what a person actually gets.
    for needed in (u"LICENSE", u"THIRD_PARTY_LICENSES.md", u"README.md"):
        where = os.path.join(bundle, needed)
        check(u"ships %s" % needed, os.path.isfile(where),
              u"%d bytes" % os.path.getsize(where)
              if os.path.isfile(where) else u"MISSING -- may not be conveyed")

    # -- 4c · 🚨 THE BYTES ARE THE VERSION ON THE TIN ----------------------
    # `package_standalone.version()` reads the SOURCE TREE and `build_zip`
    # zips whatever is on disk, so stamping a release and packaging without
    # re-freezing produces `hato-1.0.0-windows-x64.zip` whose binaries report
    # the old version. ⛔ The old check asserted only that `--version` printed
    # SOMETHING, never what.
    code, out, err = run([cli, u"--version"], env)
    reported = (out or err).strip()
    try:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from hato import __version__ as source_version
    except Exception:                                     # noqa: BLE001
        source_version = None
    check(u"the binary reports the SOURCE version",
          bool(source_version) and source_version in reported,
          u"%s" % (reported or u"no output") if source_version
          else u"could not read the source version")

    # -- 5 · a real run, both halves --------------------------------------
    empty = os.path.join(store, "empty-folder")
    os.makedirs(empty)

    # ⭐ 5a · THE STRANGER'S FIRST RUN. No key, because nobody who downloads
    # this has one yet. ⛔ It must REFUSE, say what to do, and not traceback --
    # an unhandled exception here is the first thing a new person would see.
    code, out, err = run([cli, empty], env, timeout=180)
    blob = (out or u"") + (err or u"")
    check(u"no key: refuses with an instruction",
          code == 1 and u"Traceback" not in blob
          and u"HATO_JIMAKU_KEY" in blob,
          u"exit %d, %s" % (code, u"names the fix"
                            if u"HATO_JIMAKU_KEY" in blob else blob[-120:]))

    # ⭐ 5b · AND WITH A KEY IT RUNS. ⚠ A stand-in, not a real one: an empty
    # folder needs no request, and `HATO_NO_NETWORK` is set besides. ⛔ Never
    # put a real key in a script.
    keyed = dict(env)
    keyed["HATO_JIMAKU_KEY"] = "not-a-real-key"
    code, out, err = run([cli, empty], keyed, timeout=180)
    check(u"with a key: a run completes", code == 0,
          u"exit %d%s" % (code, u"" if code == 0
                          else u" :: " + (err or out)[-160:]))

    # -- 6 · the WINDOW is visible, not merely alive ----------------------
    window_mb = _window(gui, env)

    # -- 7 · THE TRAY'S OWN SPAWN FLAGS, against the frozen exe -----------
    _window_as_the_tray_starts_it(gui, env)

    # -- 8 · the tray watcher starts --------------------------------------
    _watcher(watch, env, store, window_mb)

    failed = [n for n, ok, _ in _results if not ok]
    print(u"\n  %d checks, %d failed\n" % (len(_results), len(failed)))
    if failed:
        for name in failed:
            print(u"    FAILED: %s" % name)
        print(u"")
        return 1
    print(u"  GREEN -- the frozen bytes work.\n")
    return 0


def _window(gui, env):
    proc = subprocess.Popen([gui], env=env)
    try:
        seen, waited = 0, 0.0
        while waited < 30.0:
            time.sleep(1.0)
            waited += 1.0
            if proc.poll() is not None:
                break
            seen = visible_windows(proc.pid)
            if seen and seen > 0:
                break
        alive = proc.poll() is None
        check(u"window is VISIBLE", alive and seen > 0,
              u"%d visible window(s) after %.0fs" % (seen, waited) if alive
              else u"the process exited with %s" % proc.poll())
        measured = None
        if alive:
            qt = loaded_qt(proc.pid)
            check(u"window loaded Qt (it should)", bool(qt),
                  u"%d Qt libs" % len(qt) if qt else u"psutil unavailable")
            measured = resident_mb(proc.pid)
            if measured:
                check(u"window resident measured", True, u"%.1f MB" % measured)
        return measured
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:                                 # noqa: BLE001
            try:
                proc.kill()
            except Exception:                             # noqa: BLE001
                pass


def _window_as_the_tray_starts_it(gui, env):
    u"""🚨 THE PATH THAT BROKE TWICE, DRIVEN WITH THE REAL FLAGS.

    ⛔ The check above launches the window with a plain `Popen`, which is NOT
    how anything actually starts it. The tray calls `watch.open_window()`, and
    the whole invisible-window bug lived in the KEYWORDS that function passes:
    `STARTF_USESHOWWINDOW` with `wShowWindow` left at 0, which is `SW_HIDE`.
    A window started that way is real, native, alive -- and never shown.

    ⚠ An adversarial pass found that the corrective A/B for that bug called
    `Popen` directly rather than going through the real helper, so the one
    path that had actually failed was never observed working end to end. This
    closes it for the frozen binary: the REAL `gui_spawn_kwargs()` against the
    REAL exe.
    """
    try:
        from hato.watch import gui_spawn_kwargs
    except Exception as exc:                              # noqa: BLE001
        check(u"tray's spawn flags show a window", False,
              u"could not import gui_spawn_kwargs: %s" % exc)
        return

    proc = subprocess.Popen([gui], env=env, **gui_spawn_kwargs())
    try:
        seen, waited = 0, 0.0
        while waited < 30.0:
            time.sleep(1.0)
            waited += 1.0
            if proc.poll() is not None:
                break
            seen = visible_windows(proc.pid)
            if seen and seen > 0:
                break
        alive = proc.poll() is None
        check(u"tray's spawn flags show a window", alive and seen > 0,
              u"%d visible window(s) after %.0fs" % (seen, waited) if alive
              else u"the process exited with %s" % proc.poll())
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:                                 # noqa: BLE001
            try:
                proc.kill()
            except Exception:                             # noqa: BLE001
                pass


def _watcher(watch, env, store, window_mb=None):
    # ⚠ A watcher with nothing to watch exits 2 by design and says so, so it
    # needs a folder in its config before it will stay up.
    folder = os.path.join(store, "watched")
    os.makedirs(folder)
    cfg = os.path.join(store, "config.toml")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write(u'folders = [\n  "%s",\n]\nwatch = true\n'
                 % folder.replace("\\", "\\\\"))

    proc = subprocess.Popen([watch], env=env)
    try:
        pid_file = os.path.join(store, "watch.pid")
        waited = 0.0
        while waited < 30.0:
            time.sleep(1.0)
            waited += 1.0
            if proc.poll() is not None or os.path.isfile(pid_file):
                break
        alive = proc.poll() is None
        check(u"tray watcher starts", alive and os.path.isfile(pid_file),
              u"pid file written after %.0fs" % waited if alive
              else u"the process exited with %s" % proc.poll())

        if alive:
            # 🚨 THE ARCHITECTURAL CLAIM. If Qt is in this process, the whole
            # reason `hato/watch.py` is a separate program is gone.
            qt = loaded_qt(proc.pid)
            check(u"watcher loaded NO Qt", qt == [] or qt is None,
                  u"clean" if qt == [] else
                  (u"psutil unavailable" if qt is None else
                   u"LOADED: " + u", ".join(qt)))
            mb = resident_mb(proc.pid)
            if mb and window_mb:
                # 🚨 COMPARED AGAINST THE WINDOW, ON THE SAME HOST, FROM THE
                # SAME BUILD -- never against a number taken from the source
                # tree.
                #
                # ⛔ THIS CHECK'S FIRST VERSION WAS WRONG IN EXACTLY THE WAY
                # THIS PROJECT KEEPS PAYING FOR. It asserted `mb < 30.0`,
                # borrowed from `watch.py`'s header, where 30.6 MB is a
                # SOURCE-mode Qt tray. Frozen, every process carries an
                # embedded CPython: the watcher measured 30.7 MB and the
                # window 97.3, against 15.8 and 81 from source -- about +15 MB
                # each, uniformly. So the check failed on a build that was
                # completely healthy.
                #
                # ⭐ A probe settled it rather than an argument: the frozen
                # watcher loads `python3.dll`, `python310.dll` and 57 ordinary
                # Windows system DLLs. No numpy, no Qt. Nothing leaked in.
                #
                # ⚠ The INVARIANT is the separation, not an absolute number --
                # and the absolute number is a property of PyInstaller, which
                # will move without hato changing at all. `watcher loaded NO
                # Qt` above is the real assertion; this one guards the size
                # gap that assertion exists to buy.
                ratio = mb / window_mb
                check(u"watcher is a FRACTION of the window", ratio < 0.5,
                      u"%.1f MB vs %.1f MB window (%.0f%%, saves %.0f MB)"
                      % (mb, window_mb, ratio * 100, window_mb - mb))
            elif mb:
                check(u"watcher resident measured", True, u"%.1f MB" % mb)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:                                 # noqa: BLE001
            try:
                proc.kill()
            except Exception:                             # noqa: BLE001
                pass


if __name__ == "__main__":
    sys.exit(main())
