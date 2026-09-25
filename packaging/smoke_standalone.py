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
  6b. ⭐ Run now, PRESSED, runs              -- 1.0.2 and 1.0.3 closed the
                                                window on that press (D12)
                                                while 6 was green
  7. the tray watcher starts
  8. ⭐ the CLI and the WATCHER never load Qt -- the 13.4-vs-30.6 MB argument,
                                                asserted rather than assumed
  11. ⭐ LAYER 11: the onefile swapper       -- carries swap + splash and its
      starts, carries nothing else of hato,     mark, nothing else; an installed
      and the REHEARSAL: a real install         hato updated by the REAL swapper,
      updated both ways                         put back when it cannot start,
                                                and its SPLASH seen on screen,
                                                composed, and gone as the new
                                                window came
"""
from __future__ import print_function

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

#: ⚠ THE REPO ROOT, AND ONLY FOR ONE THING. Running this file directly puts
#: `packaging/` on `sys.path`, not the repository -- so `import hato` fails.
#: ⛔ Nothing here tests the source. Two imports, both DATA:
#: `watch.gui_spawn_kwargs`, a pure function returning a dict of Popen
#: keywords, which is needed to start the FROZEN exe the way the tray starts
#: it; and `cli.COMMANDS`, the list of commands to ask the bundle for. The
#: application under test is always the bundle.
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
#: ⭐ LAYER 11 -- the fourth, onefile: the swapper `hato/update.py` copies out of a
#: staged release by this name (`update.SWAPPER_NAME`).
UPDATE_NAME = "hato-update" + EXE

_results = []


#: Top-level modules in the bundle that are not third-party packages.
_OURS = ("hato", "tsubasa")


def bundled_packages(bundle):
    u"""-> {name: [top-level modules]} for every third-party package the FROZEN
    build carries, read from its own archives -- never from what was declared.

    ⚠ The PYZ inside each executable (PyInstaller's own reader, the build
    environment's) plus the folders and extension modules in `_internal/`.
    A module is named by the distribution that installs it, where the build
    environment knows one, else by itself.
    """
    import importlib.metadata as metadata
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    tops = set()
    for exe in (CLI_NAME, GUI_NAME, WATCH_NAME):
        path = os.path.join(bundle, exe)
        if not os.path.isfile(path):
            continue
        archive = CArchiveReader(path)
        for name, entry in archive.toc.items():
            if not (name.lower().endswith(u".pyz") or (entry and entry[-1] == u"z")):
                continue
            handle, temp = tempfile.mkstemp(suffix=u".pyz")
            try:
                with os.fdopen(handle, "wb") as out:
                    out.write(archive.extract(name))
                tops.update(m.split(u".")[0] for m in ZlibArchiveReader(temp).toc)
            finally:
                os.remove(temp)
    internal = os.path.join(bundle, u"_internal")
    for entry in (os.listdir(internal) if os.path.isdir(internal) else ()):
        if entry.endswith((u".dist-info", u".egg-info")):
            continue
        if os.path.isdir(os.path.join(internal, entry)) or entry.endswith(u".pyd"):
            tops.add(entry.split(u".")[0])
    owners = metadata.packages_distributions()
    stdlib = set(getattr(sys, u"stdlib_module_names", ()))
    out = {}
    for top in sorted(tops):
        if top in stdlib or top in _OURS or top.startswith((u"pyimod", u"pyi_", u"__")):
            continue
        names = owners.get(top) or ([] if top.startswith(u"_") else [top])
        for name in names:
            out.setdefault(name, []).append(top)
    return out


def _archived(exe, module):
    u"""-> True when `module` is inside `exe`'s own PYZ. ⚠ The window imports
    `hato.schedule` inside a function; this asks the bytes whether the freeze
    followed it there, instead of trusting that it did."""
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    try:
        archive = CArchiveReader(exe)
        for name, entry in archive.toc.items():
            if not (name.lower().endswith(u".pyz") or (entry and entry[-1] == u"z")):
                continue
            handle, temp = tempfile.mkstemp(suffix=u".pyz")
            try:
                with os.fdopen(handle, "wb") as out:
                    out.write(archive.extract(name))
                if module in ZlibArchiveReader(temp).toc:
                    return True
            finally:
                os.remove(temp)
    except Exception:                                     # noqa: BLE001 -- a check reports
        return False
    return False


def _daily_run(cli, watch, keyed, store, folder):
    u"""⭐ D2 -- what Windows' daily task runs: `hato-watch.exe --scheduled`.

    ⛔ NOT THROUGH TASK SCHEDULER: a smoke must not register anything on the
    machine it runs on (the build proved the real trigger once, by hand, under a
    task of its own). What only the BYTES can say is asked here -- that the frozen
    watcher takes the flag, finds `hato-cli.exe` beside it, runs a scan over the
    CONFIGURED folders and hands back its exit code, with the log as the record.
    """
    code, out, err = run([cli, "config", "--add-folder", folder], keyed, timeout=120)
    if not check(u"daily run: a folder is configured", code == 0,
                 u"exit %d%s" % (code, u"" if code == 0 else u" :: " + (err or out)[-160:])):
        return
    log = os.path.join(store, "hato.log")
    before = _log_blocks(log)
    code, out, err = run([watch, "--scheduled"], keyed, timeout=300)
    after = _log_blocks(log)
    check(u"daily run: the watcher runs one scan", code == 0 and after == before + 1,
          u"exit %d, %d new log block(s)" % (code, after - before))


def _log_blocks(path):
    u"""-> how many RUN blocks the log holds. ⚠ A run's header is `=== hato
    <timestamp> ===`; the watcher's own complaints are `=== hato watcher ...`,
    and counting those would read a daily run that FAILED as one that scanned."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return len(re.findall(u"^=== hato \\d", handle.read(), re.M))
    except OSError:
        return 0


def _normal(text):
    return re.sub(u"[-_.]+", u"-", text.lower())


def _notices(bundle):
    u"""Every bundled third-party package is named in THIRD_PARTY_LICENSES.md.

    ⚠ The copy that SHIPS -- beside the exes in the unpacked zip -- else, for a
    smoke of `dist/`, the source tree's (and the detail says which).
    """
    shipped = os.path.join(bundle, u"THIRD_PARTY_LICENSES.md")
    notice = shipped if os.path.isfile(shipped) else os.path.join(_ROOT, u"THIRD_PARTY_LICENSES.md")
    try:
        carried = bundled_packages(bundle)
        with open(notice, encoding="utf-8") as handle:
            text = _normal(handle.read())
    except Exception as exc:                  # noqa: BLE001 -- a check reports
        check(u"the notice names what the bytes carry", False,
              u"could not read the payload (%s: %s)" % (type(exc).__name__, exc))
        return
    unnamed = sorted(name for name in carried if not re.search(
        u"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(_normal(name)), text))
    check(u"the notice names what the bytes carry", not unnamed and len(carried) > 10,
          u"%d packages, all named (%s)" % (len(carried), u"shipped copy" if notice == shipped
                                             else u"source copy")
          if not unnamed else u"NOT NAMED: %s" % u", ".join(unnamed))


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
    for name, path in ((CLI_NAME, cli), (GUI_NAME, gui), (WATCH_NAME, watch),
                       (UPDATE_NAME, os.path.join(bundle, UPDATE_NAME))):
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
    # ⭐ READ FROM THE DISPATCH TABLE, as `hato.spec` reads it. A hand copy
    # here went stale at 8c: `problems` -- the command the window calls to
    # fill Needs you -- was frozen and never checked.
    from hato.cli import COMMANDS
    commands = sorted(COMMANDS)
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
    # 🚨 EXIT 2, AND THE NUMBER IS THE POINT. This asserted `code == 1` until
    # 2026-09-19, when a keyless run in the published 1.0.0 was reported as
    # doing nothing at all: exit 1 is *"could not do what was asked"* and is
    # the NORMAL code for a run where something needs a pick, so the window
    # read a keyless run as an ordinary finished one and said "done".
    #
    # ⭐ No key is *"the asking was wrong"* -- the setup is incomplete, hato
    # is not broken. ⚠ This check went red on the first build after the CLI
    # changed, which is the check doing its job: two things disagreed and it
    # said so rather than tracking the code silently.
    check(u"no key: refuses with an instruction",
          code == 2 and u"Traceback" not in blob
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

    # ⭐ 5c · 🚨 D8 -- A NAME ONLY GUESSIT CAN READ. The released 1.0.1 died
    # here, and nothing above could see it: tsubasa asks guessit about a
    # Western-style name its own parsers cannot number, guessit imports
    # babelfish, and babelfish's data files had not travelled -- so the WHOLE
    # FOLDER failed to scan (*"none of the 1 folder(s) given could be
    # scanned"*). Source mode was fine throughout; only the bytes show it.
    western = os.path.join(store, "western-folder")
    os.makedirs(western)
    with open(os.path.join(western, "The.Show.Special.1080p.WEB.x264-GRP.mkv"),
              "wb") as handle:
        handle.write(b"\x1aE\xdf\xa3 a stub, never a real video")
    code, out, err = run([cli, western, "--dry-run"], keyed, timeout=180)
    blob = (out or u"") + (err or u"")
    scanned = u"could not be scanned" not in blob and u"FileNotFoundError" not in blob
    check(u"a name only guessit reads is scanned", scanned and u"Traceback" not in blob,
          u"exit %d" % code if scanned else blob.strip()[-200:])
    for parts in (("babelfish", "data", "iso-3166-1.txt"),
                  ("guessit", "config", "options.json")):
        where = os.path.join(root, *parts)
        check(u"bundled: %s" % u"/".join(parts), os.path.isfile(where),
              u"%d bytes" % os.path.getsize(where) if os.path.isfile(where)
              else u"MISSING -- see hato.spec, D8")

    # ⭐ 5d · 🚨 ADVERSARY 2026-09-22 D1 -- GUESSIT ITSELF, ASKED INSIDE THE BYTES.
    # 5c cannot tell: tsubasa's wrapper swallows a guessit that imports and then
    # raises, so a run's parse is the SAME with guessit or without it -- and a
    # bundle built WITHOUT `collect_submodules` (babelfish's converters, loaded
    # by name on first use) passed every check above. `hato doctor` asks the
    # parser directly, with a name it must number; HATO_NO_NETWORK keeps it free.
    code, out, err = run([cli, "doctor", "--json"], keyed, timeout=180)
    lines = {}
    try:
        lines = dict((l["label"], l) for l in json.loads(out)["lines"])
    except (ValueError, KeyError, TypeError):
        pass
    for parser in (u"guessit", u"anitopy"):
        said = lines.get(parser) or {}
        check(u"%s parses a name inside the frozen build" % parser, said.get("state") == "ok",
              said.get("text") or u"no %s line :: %s" % (parser, (err or out)[-160:]))

    # -- 6 · the WINDOW is visible, not merely alive ----------------------
    window_mb = _window(gui, env)

    # -- 6b · ⭐ D12 -- RUN NOW, PRESSED IN THE BUILT WINDOW --------------
    _run_now(gui, cli)

    # -- 7 · THE TRAY'S OWN SPAWN FLAGS, against the frozen exe -----------
    _window_as_the_tray_starts_it(gui, env)

    # -- 8 · the tray watcher starts --------------------------------------
    _watcher(watch, env, store, window_mb)

    # -- 9 · 🚨 ADVERSARY 2026-09-22 D2 -- WHAT THE BYTES CARRY IS WHAT THE
    # NOTICE NAMES. The notice check in `tests/` reads `pyproject.toml`, which
    # declares fifteen packages; the 1.0.1 download carried some thirty, PyYAML
    # and an LGPL chardet among the unnamed. ⭐ Read from the frozen archives.
    _notices(bundle)

    # -- 10 · ⭐ RUNBOOK D2 -- THE DAILY RUN, AS TASK SCHEDULER STARTS IT ------
    _daily_run(cli, watch, keyed, store, empty)
    check(u"the window carries hato.schedule",
          _archived(gui, u"hato.schedule"),
          u"in %s's archive" % GUI_NAME if _archived(gui, u"hato.schedule")
          else u"MISSING -- the switch would die on its first click")

    # -- 11 · ⭐ LAYER 11 -- THE SWAPPER, AND THE REHEARSAL ------------------
    _swapper(bundle, store)
    _rehearsal(bundle, cli)

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


#: ⭐ D12. The press, as UI Automation makes it: the button's accessible press is
#: `QAbstractButton.click()`, which emits `clicked(checked)` exactly as a mouse
#: does -- and no pointer moves on the desktop the smoke runs on. ⛔ ASCII only,
#: and sent as `-EncodedCommand`, so no shell quoting sits between this file and
#: PowerShell.
_UIA = u"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$Scope = [System.Windows.Automation.TreeScope]
$mine = New-Object System.Windows.Automation.PropertyCondition($AE::ProcessIdProperty, __PID__)
$windows = $AE::RootElement.FindAll($Scope::Children, $mine)
if ('__MODE__' -eq 'read') {
  foreach ($w in $windows) {
    $all = $w.FindAll($Scope::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) { if ($e.Current.Name) { Write-Output ('TEXT ' + $e.Current.Name) } }
  }
  exit 0
}
$named = New-Object System.Windows.Automation.PropertyCondition($AE::NameProperty, '__NAME__')
foreach ($w in $windows) {
  $button = $w.FindFirst($Scope::Descendants, $named)
  if ($button -ne $null) {
    $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Write-Output 'PRESSED'
    exit 0
  }
}
Write-Output 'NOT FOUND'
exit 3
"""


def _uia(pid, mode, name=u"Run now"):
    u"""-> PowerShell's stdout: `PRESSED` / `NOT FOUND` (press), or one `TEXT`
    line per named element (read) -- the words the window is showing."""
    import base64
    script = (_UIA.replace(u"__PID__", str(int(pid))).replace(u"__MODE__", mode)
              .replace(u"__NAME__", name))
    shell = os.path.join(os.environ.get("SystemRoot", u"C:\\Windows"), u"System32",
                         u"WindowsPowerShell", u"v1.0", u"powershell.exe")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    _code, out, _err = run([shell, u"-NoProfile", u"-NonInteractive",
                            u"-EncodedCommand", encoded], dict(os.environ), timeout=60)
    return out or u""


def _run_now(gui, cli):
    u"""⭐ D12 -- RUN NOW, PRESSED IN THE BUILT WINDOW.

    🚨 1.0.2 AND 1.0.3 CLOSED THE WINDOW ON THIS PRESS, on two machines --
    `0xC0000409` in Qt6Core, four times in Sonic's event log -- while every check
    here was green: the window was VISIBLE (6), a run COMPLETED from the command
    line (5b), and nothing ever pressed a control. The fault was a wiring in the
    window's source, so `tests/` catches it now; this is the BUILT BYTES' witness,
    and it drives the whole chain a person does: the press, `hato-cli.exe`
    spawned by the window, the run's own record, and the footer's word.

    ⭐ Its own store, so no other check sees its folder. A stand-in key, as 5b's:
    a keyless window refuses before the press reaches the run, and
    `HATO_NO_NETWORK` means nothing is ever sent. ⭐ Proven two-arm: the 1.0.3
    zip dies on it; the build it was written for survives it.
    """
    if not IS_WINDOWS:
        return
    store = tempfile.mkdtemp(prefix="hato-smoke-run-now-")
    env = child_env(store)
    env["HATO_JIMAKU_KEY"] = "not-a-real-key"
    folder = os.path.join(store, "watched")
    os.makedirs(folder)
    record = os.path.join(store, "last-run.json")
    proc = None
    try:
        code, out, err = run([cli, "config", "--add-folder", folder], env, timeout=120)
        if not check(u"Run now: a folder is configured", code == 0,
                     u"exit %d%s" % (code, u"" if code == 0 else u" :: " + (err or out)[-160:])):
            return
        proc = subprocess.Popen([gui], env=env)
        seen, waited = 0, 0.0
        while waited < 30.0 and not seen:
            time.sleep(1.0)
            waited += 1.0
            if proc.poll() is not None:
                break
            seen = visible_windows(proc.pid)
        pressed = u""
        for _ in range(10):                   # the tree is built after the paint
            if not seen or proc.poll() is not None:
                break
            pressed = _uia(proc.pid, u"press").strip()
            if pressed != u"NOT FOUND":
                break
            time.sleep(1.0)
        said, waited = u"", 0.0
        while pressed == u"PRESSED" and waited < 45.0:
            time.sleep(1.5)
            waited += 1.5
            if proc.poll() is not None:
                break
            if os.path.isfile(record):
                words = [line[5:].strip() for line in _uia(proc.pid, u"read").splitlines()
                         if line.startswith(u"TEXT ")]
                if u"done" in words:
                    said = u"done"
                    break
        died = proc.poll()
        if died is not None:
            detail = u"the WINDOW DIED on the press, exit 0x%08X" % (died & 0xFFFFFFFF)
        elif pressed != u"PRESSED":
            detail = u"could not press it: %s" % (pressed or u"no window to press in")
        elif not os.path.isfile(record):
            detail = u"pressed, and no run wrote its record in %.0fs" % waited
        elif said != u"done":
            detail = u"the run wrote its record; the footer never said done"
        else:
            detail = u"pressed; the run wrote its record, the footer says done"
        check(u"Run now, pressed in the window, runs",
              died is None and pressed == u"PRESSED" and said == u"done"
              and os.path.isfile(record), detail)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except Exception:                             # noqa: BLE001
                try:
                    proc.kill()
                except Exception:                         # noqa: BLE001
                    pass
        shutil.rmtree(store, ignore_errors=True)


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


def _swapper(bundle, store):
    u"""⭐ LAYER 11 -- the fourth executable on the BUILT bytes: it starts, and it
    carries `hato.swap` and the splash and NOTHING else of hato -- it runs from
    outside the folder it empties. ⚠ A windowed program has nowhere to print, so
    `--selftest` writes what it loaded to a file."""
    exe = os.path.join(bundle, UPDATE_NAME)
    out = os.path.join(store, u"swapper-selftest.json")
    code, _out, err = run([exe, u"--selftest", out], child_env(store), timeout=120)
    said = {}
    try:
        with open(out, encoding="utf-8") as handle:
            said = json.load(handle)
    except (OSError, ValueError):
        pass
    loaded = said.get(u"hato") or []
    check(u"the swapper starts, frozen", code == 0 and said.get(u"frozen") is True,
          u"exit %s%s" % (code, u" :: " + err.strip()[-160:] if err.strip() else u""))
    check(u"the swapper carries only swap + splash",
          loaded and set(loaded) <= {u"hato", u"hato.swap", u"hato.splash"},
          u", ".join(loaded) or u"loaded nothing it said")
    check(u"the swapper carries its splash", said.get(u"splash") is True,
          u"%s" % said.get(u"splash"))
    # ⭐ The splash's picture of hato, found INSIDE the onefile: a spec that forgot
    # the data would draw a card with a hole where the mark belongs, silently.
    mark = said.get(u"mark")
    check(u"the swapper's splash finds its mark",
          isinstance(mark, list) and len(mark) == 3 and mark[1] >= 40,
          u"%s" % (mark,))


def _print_window(hwnd, width, height):
    u"""What Windows composed for `hwnd` -> BGRA bytes, top down.
    ⭐ PrintWindow(PW_RENDERFULLCONTENT) reads a LAYERED window's own surface -- a
    plain BitBlt of the screen leaves it out."""
    import ctypes
    from ctypes import wintypes as W
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetDC.restype, user32.GetDC.argtypes = W.HDC, [W.HWND]
    user32.ReleaseDC.argtypes = [W.HWND, W.HDC]
    user32.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
    gdi32.CreateCompatibleDC.restype, gdi32.CreateCompatibleDC.argtypes = W.HDC, [W.HDC]
    gdi32.CreateCompatibleBitmap.restype = W.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype, gdi32.SelectObject.argtypes = W.HANDLE, [W.HDC, W.HANDLE]
    gdi32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p,
                                ctypes.c_void_p, W.UINT]
    gdi32.DeleteObject.argtypes = [W.HANDLE]
    gdi32.DeleteDC.argtypes = [W.HDC]

    class Header(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                    ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                    ("image", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG),
                    ("used", W.DWORD), ("important", W.DWORD)]

    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(mem, bmp)
    buf = ctypes.create_string_buffer(width * height * 4)
    try:
        user32.PrintWindow(hwnd, mem, 2)
        gdi32.SelectObject(mem, old)
        old = None
        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(header), 0)
    finally:
        if old:
            gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)
    return buf.raw


def _png(path, width, height, bgra):
    u"""A capture, as a PNG anyone can open -- stdlib only."""
    import struct
    import zlib
    rows = b"".join(b"\x00" + bytes(bytearray(
        c for i in range(y * width * 4, (y + 1) * width * 4, 4)
        for c in (bgra[i + 2], bgra[i + 1], bgra[i]))) for y in range(height))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(
            ">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _parent_of(pid):
    u"""The process that started `pid` -> its pid, or None."""
    try:
        import psutil
        return psutil.Process(pid).ppid()
    except Exception:                                     # noqa: BLE001
        return None


def _watch_splash(proc, timeout=240.0):
    u"""⭐ 11e ON THE BUILT BYTES. While the swapper runs: when its splash showed
    (s after the hand-off) and whose it is, the card's colour as Windows COMPOSED
    it, when it went, and when the swapper finished. `HATO_SMOKE_SHOTS`: the
    capture is kept there, to be looked at.
    -> {at, pid, pixel, want, gone_at, done_at}"""
    import ctypes
    from ctypes import wintypes as W
    from hato import splash
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.restype = W.HWND
    user32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
    user32.GetWindowThreadProcessId.restype = W.DWORD
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user32.GetDpiForWindow.restype, user32.GetDpiForWindow.argtypes = W.UINT, [W.HWND]
    start = time.monotonic()
    seen = {u"at": None, u"pid": None, u"parent": None, u"pixel": None, u"want": None,
            u"gone_at": None, u"done_at": None}
    while proc.poll() is None and time.monotonic() - start < timeout:
        now = time.monotonic() - start
        hwnd = user32.FindWindowW(splash.CLASS_NAME, None)
        if hwnd and seen[u"at"] is None:
            seen[u"at"] = now
            owner = W.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            seen[u"pid"] = owner.value
            # 🚨 MEASURED 2026-09-24: a ONEFILE exe is TWO processes -- the bootloader
            # Popen started unpacks the runtime and runs the Python code in a CHILD, so
            # the splash belongs to the child. Asked while it is alive.
            seen[u"parent"] = _parent_of(owner.value)
        elif hwnd and seen[u"pixel"] is None and now - seen[u"at"] > 0.4:
            geo = splash.Geometry(user32.GetDpiForWindow(hwnd))
            shot = _print_window(hwnd, geo.width, geo.height)
            x, y = geo.right - 40, geo.top + geo.card_h // 2
            seen[u"pixel"] = tuple(bytearray(shot[(y * geo.width + x) * 4:
                                                  (y * geo.width + x) * 4 + 3]))
            seen[u"want"] = tuple(bytearray(splash._opaque(splash.Card(geo).fill(y))[:3]))
            folder = os.environ.get(u"HATO_SMOKE_SHOTS")
            if folder and os.path.isdir(folder):
                _png(os.path.join(folder, u"frozen-splash.png"), geo.width, geo.height, shot)
        elif not hwnd and seen[u"at"] is not None and seen[u"gone_at"] is None:
            seen[u"gone_at"] = now
        time.sleep(0.05)
    seen[u"done_at"] = time.monotonic() - start
    return seen


def _version_of(cli):
    code, out, _err = run([cli, u"--version"], dict(os.environ), timeout=120)
    found = re.search(r"hato (\d+\.\d+\.\d+)", out or u"")
    return found.group(1) if code == 0 and found else None


def _previous_release(below):
    u"""The newest RELEASED zip older than `below`, from this repository's `dist/`
    -> its path, or None. ⭐ The truest rehearsal installs over what a person has."""
    from hato import update
    folder = os.path.join(_ROOT, u"dist")
    best = None
    for name in (os.listdir(folder) if os.path.isdir(folder) else ()):
        found = re.match(r"^hato-(\d+\.\d+\.\d+)-windows-x64\.zip$", name)
        if found and update.is_newer(below, found.group(1)) and (
                best is None or update.is_newer(found.group(1), best[0])):
            best = (found.group(1), os.path.join(folder, name))
    return best[1] if best else None


def _swap_said(store):
    u"""The swapper's last line in hato.log -- its own reason, in its own words."""
    try:
        with open(os.path.join(store, u"hato.log"), encoding="utf-8") as handle:
            lines = [l.strip() for l in handle if l.strip()]
    except OSError:
        return u"no hato.log"
    said = [l for l in lines if u" -> " in l]
    return said[-1] if said else u"nothing in hato.log"


def _hato_windows(install, swap):
    u"""-> the pids of hato WINDOWS running from `install` (by program file)."""
    ops = swap.WinOps()
    return [pid for pid in ops.processes_in(install)
            if os.path.basename(ops.image(pid) or u"").lower() == GUI_NAME.lower()]


def _stop_all(install, swap):
    u"""Stop what runs from `install` -- ⛔ by the PROGRAM FILE, inside the
    rehearsal's own folder, never by name: the person's own hato may be running."""
    import signal
    ops = swap.WinOps()
    for pid in ops.processes_in(install):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    swap.wait_gone(install, ops, 20.0)


def _rehearsal(bundle, cli):
    u"""⭐ LAYER 11h -- THE REHEARSAL: an installed hato updated by the REAL swapper
    from THIS bundle, on the built bytes, both ways.

    The installed copy is the newest RELEASED zip older than this bundle (what a
    person has), else a copy of this bundle -- every step still runs, only the
    number stays. The payload is this bundle zipped as a release is, staged through
    `hato.update.stage` from a local file: the same manifest, hashes and version
    check a real install makes.

      arm 1  a new version whose WINDOW cannot start -- its Qt removed after staging,
             so its command line still answers -- is PUT BACK, and the old window
             comes back. 🚨 Its crash dialog is a visible window too: the proof is
             hato's own window, by title.
      arm 2  the new version goes in WITH ITS TRAY, its window opens and SAYS it was
             updated, and the old version is kept for Go back. ⭐ Watching is on, so
             the new window's own start-up would start a tray too: exactly ONE tray
             may run afterwards, the one the swapper started and proved first
             (ADVERSARY 2026-09-24, S3). `HATO_ALLOW_MANY` is set here, so a second
             tray would not refuse itself -- it would run, and be counted.

    ⛔ Its own store, under a Japanese-named folder, and every process it started is
    stopped by the program file it runs -- never by name."""
    if not IS_WINDOWS:
        return
    from hato import swap, update
    from hato.dev import signing
    import package_standalone
    version = _version_of(cli)
    if not check(u"rehearsal: the bundle says its version", bool(version),
                 u"%s" % version):
        return
    previous = _previous_release(version)
    work = tempfile.mkdtemp(prefix=u"hato-rehearse-")
    base = os.path.join(work, u"ツール置き場")
    store = os.path.join(work, u"store")
    os.makedirs(store)
    install = os.path.join(base, u"hato")
    saved = dict(os.environ)
    try:
        # ⚠ The swapper, and the window it starts, inherit THIS environment.
        os.environ.update(child_env(store))
        if previous:
            package_standalone.extract(previous, base)
        else:
            shutil.copytree(bundle, install)
        was = _version_of(os.path.join(install, CLI_NAME))
        if not check(u"rehearsal: the installed copy says its version", bool(was),
                     u"%s, from %s" % (was, os.path.basename(previous) if previous
                                       else u"a copy of this bundle")):
            return
        payload = os.path.join(work, u"hato-%s-windows-x64.zip" % version)
        package_standalone.build_zip(bundle, payload)
        # ⚠ `min_from` = what is installed: a release's floor is not what this is
        # about, and a floor above the payload's own number is refused -- measured,
        # the first rehearsal of an unstamped 1.0.3 met the 1.0.4 default.
        manifest = signing.build_manifest(payload, notes=[u"the rehearsal"], min_from=was)
        decision = update.Decision(update.READY, manifest.version, manifest=manifest,
                                   zip_url=u"local", notes=manifest.notes)

        def get(_url):
            with open(payload, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    yield block

        root = update.stage_root(install)

        # -- arm 1 · a new version that cannot start is PUT BACK -------------
        pending = update.stage(decision, was, install, get=get,
                               version_of=update.installed_version)
        with open(pending, encoding="utf-8") as handle:
            staged = json.load(handle)[u"staged"]
        core = os.path.join(staged, u"_internal", u"PyQt6", u"Qt6", u"bin", u"Qt6Core.dll")
        broken = os.path.isfile(core)
        if broken:
            os.remove(core)
        proc = update.hand_off(pending, window=True, tray=False, quiet=True)
        code = proc.wait(240)
        back = _version_of(os.path.join(install, CLI_NAME))
        # ⚠ The swapper starts the old window and goes: nothing proves a version it
        # PUT BACK, so the window gets its own seconds to appear here.
        windows, waited = [], 0.0
        while not windows and waited < 30.0:
            windows = [pid for pid in _hato_windows(install, swap)
                       if visible_windows(pid) > 0]
            if not windows:
                time.sleep(1.0)
                waited += 1.0
        why = _swap_said(store)
        check(u"rehearsal: a version that cannot start is put back",
              broken and code == 1 and back == was and windows,
              u"swapper exit %s · installed says %s (was %s) · %d old window(s) back · %s"
              % (code, back, was, len(windows), why) if broken
              else u"no Qt6Core.dll to break")
        _stop_all(install, swap)

        # -- arm 2 · the new version goes in, with its tray, and says so ------
        from hato import watch
        watched = os.path.join(work, u"watched")
        os.makedirs(watched)
        with open(os.path.join(store, u"config.toml"), "w", encoding="utf-8") as fh:
            fh.write(u"folders = [%s]\nwatch = true\n" % json.dumps(watched))
        pending = update.stage(decision, was, install, get=get,
                               version_of=update.installed_version)
        proc = update.hand_off(pending, window=True, tray=True,
                               tray_pid_file=watch.pid_file_path(), quiet=False)
        card = _watch_splash(proc)
        code = proc.wait(240)
        # ⭐ 11e: drawn by THIS swapper, the card's own colour where no words are, and
        # gone as the new window came -- seconds before the swapper's settle ended
        check(u"rehearsal: the swapper drew its splash",
              card[u"at"] is not None and proc.pid in (card[u"pid"], card[u"parent"])
              and card[u"pixel"]
              and all(abs(a - b) <= 3 for a, b in zip(card[u"pixel"], card[u"want"])),
              u"on screen %s s after the hand-off · by pid %s, started by %s (the swapper "
              u"%s) · composed %s, the card %s"
              % (u"%.1f" % card[u"at"] if card[u"at"] is not None else u"never",
                 card[u"pid"], card[u"parent"], proc.pid, card[u"pixel"], card[u"want"]))
        check(u"rehearsal: the splash went as the new window came",
              card[u"gone_at"] is not None
              and card[u"done_at"] - card[u"gone_at"] >= 2.0,
              u"gone at %s s, the swapper done at %.1f s"
              % (u"%.1f" % card[u"gone_at"] if card[u"gone_at"] is not None else u"never",
                 card[u"done_at"]))
        now = _version_of(os.path.join(install, CLI_NAME))
        opened = [pid for pid in _hato_windows(install, swap) if visible_windows(pid) > 0]
        # ⚠ A READ THAT RETURNED NO TEXT AT ALL IS THE READER FAILING, NOT THE WINDOW:
        # every hato window shows *Run now*. The 1.0.5 smoke failed here once with
        # *"it said: nothing"* -- the control run and two probes all saw the banner --
        # and the message could not say which it was (the Layer 12 pass). It says now.
        said, waited, reads, blank = [], 0.0, 0, 0
        while opened and waited < 20.0 and not any(u"Updated to" in w for w in said):
            time.sleep(1.0)
            waited += 1.0
            said = [line[5:].strip() for line in _uia(opened[0], u"read").splitlines()
                    if line.startswith(u"TEXT ")]
            reads += 1
            blank += 0 if said else 1
        check(u"rehearsal: the new version goes in",
              code == 0 and now == version and opened,
              u"swapper exit %s · installed says %s · %d window(s) open"
              % (code, now, len(opened)))
        check(u"rehearsal: the new window says it was updated",
              any((u"Updated to %s" % version) in w for w in said) if was != version
              else any(u"Updated to" in w for w in said),
              u"it said: %s" % (u" | ".join(w for w in said if u"pdate" in w) or (
                  u"nothing about an update -- %d read(s) of the window, %d with no text at "
                  u"all (the reader failing), the last showing %d text(s)"
                  % (reads, blank, len(said)))))
        check(u"rehearsal: the old version is kept for Go back",
              os.path.isdir(os.path.join(str(root), u"previous", was or u"?")),
              u"%s" % os.path.join(str(root), u"previous", was or u"?"))
        # ⭐ S3, in the built bytes: counted seconds after the window came up
        ops = swap.WinOps()
        trays = [pid for pid in ops.processes_in(install)
                 if os.path.basename(ops.image(pid) or u"").lower() == WATCH_NAME.lower()]
        named = watch.watching_pid()
        check(u"rehearsal: one tray -- the swapper's -- and the new window started none",
              len(trays) == 1 and named == trays[0],
              u"%d tray(s) running from the install %s · the pid file names %s"
              % (len(trays), trays, named))
    except Exception as exc:                  # noqa: BLE001 -- a failure is a FAIL line
        check(u"rehearsal ran to the end", False, u"%s: %s" % (type(exc).__name__, exc))
    finally:
        try:
            _stop_all(install, swap)
        except Exception:                     # noqa: BLE001
            pass
        os.environ.clear()
        os.environ.update(saved)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
