# -*- mode: python ; coding: utf-8 -*-
u"""hato, frozen. RUNBOOK 7g.

    pyinstaller --noconfirm --distpath <dir> --workpath <dir> packaging/hato.spec

===========================================================================
🚨 ONE SPEC, **THREE** EXECUTABLES, ONE `COLLECT`
===========================================================================

hato is three processes and the frozen names are a CONTRACT, not a
preference -- each is hard-coded in code that already shipped:

    hato.exe         THE WINDOW     `watch.py::open_window`
    hato-cli.exe     the CLI        `gui/run.py::cli_argv`, `watch.py::run_argv`
    hato-watch.exe   the tray       `watch.py::watch_argv`

🚨 `hato.exe` IS THE WINDOW, AND THAT IS A RULING. Sonic, 2026-09-18: *"i
don't want it 'gui', i want it to be hato as the main one ... i can just
click on hato.exe and it will handle everything else."* ⛔ So the CLI is
`hato-cli.exe`, and anything that means *"run a scan"* must spawn THAT --
spawning `hato.exe` opens a second window instead.

⚠ ONE BINARY CANNOT DO BOTH JOBS. `console` is compiled into the executable:
a console build flashes a terminal on every launch of the window, and a
windowed build has no valid stdout, so `--version` would print nowhere and
the window could not read its child's output. Three files, one of which a
person ever clicks.

Each of those resolves a SIBLING of `sys.executable`, because when frozen
`sys.executable` is the bundle and `-m hato` would re-enter whichever
window launched it. ⛔ **Ship any one of them alone and the other two break
at the first spawn.**

⛔ AND THREE SEPARATE `pyinstaller` RUNS INTO ONE `--distpath` IS NOT THE
SAME THING -- each `COLLECT` writes `_internal/`, the last one wins, and the
losers' payloads are gone. Three `Analysis` objects and ONE `COLLECT` is the
only arrangement where all three binaries share a payload containing all
three's imports. (Inherited from tsubasa's spec, which paid for it.)

===========================================================================
🚨 THE DYNAMIC COMMAND TABLE -- THE ONE THAT WOULD HAVE SHIPPED BROKEN
===========================================================================

`hato/cli.py` dispatches EVERY subcommand through
`importlib.import_module(COMMANDS[name])`. ⛔ PyInstaller's static analysis
cannot see an import built from a dict at runtime, so a frozen `hato-cli.exe`
would carry none of them and fail on every single subcommand --
`hato run`, `hato key`, `hato config`, all of them -- while `hato --version`
worked perfectly and the build looked fine.

⭐ **DERIVED FROM THE TABLE, NEVER HAND-LISTED.** Reading `COMMANDS` itself
means a command added later is frozen automatically. A hand-written copy
here would be a second list to keep in step, and the failure it produces is
silent until somebody runs that one command.

===========================================================================
⚠ tsubasa's HOOK IS NOT REGISTERED ON THIS MACHINE -- POINT AT IT
===========================================================================

tsubasa ships `tsubasa/__pyinstaller/hook-tsubasa.py`, which collects its
alias table and decoration vocabulary. It is meant to be found through a
`pyinstaller40` entry point -- and MEASURED 2026-09-18, it is not: the only
entry points registered here are numpy, hooks-contrib and yt_dlp, because
tsubasa is installed from a source checkout.

⛔ Without that hook hato's bundle loses tsubasa's data files, and tsubasa's
own spec records exactly what that costs: the build *"still runs and exits
0"* while settled-by-name accuracy falls from **80.0% to 51.4%**. A silent
quality collapse that no exit code reports.

⭐ So `hookspath` points at tsubasa's own hook directory rather than this
file re-declaring its patterns. ⚠ tsubasa's hook is covered by tsubasa's
`test_packaging.py`; a hand-written copy here would drift out from under
that check silently -- which is the mistake its own comment warns about.

===========================================================================
⚠ `--onedir`, NEVER `--onefile`
===========================================================================

onefile unpacks the whole payload to a temp directory on every launch -- and
hato launches itself constantly: the tray spawns a run, the window spawns a
run, the tray spawns the window. Three processes each paying an unpack is
the worst possible shape for this program.

===========================================================================
🚨 PyQt6 IS EXCLUDED FROM TWO OF THE THREE, AND THAT IS THE WHOLE POINT
===========================================================================

`hato/watch.py` exists as a separate process for one measured reason: a
ctypes tray is 13.4 MB resident against 30.6 MB for a Qt one, for as long as
the machine is on. ⛔ If the watcher's or the CLI's Analysis pulls Qt into
its PYZ, that saving is gone and the third executable is pure cost.

⚠ The Qt BINARIES still sit in the shared `_internal/` -- that is disk, not
memory, and disk is shared by the one COLLECT. What matters is that neither
of those two entry points can IMPORT Qt, and a check in `tests/test_watch.py`
already asserts the watcher module imports no toolkit.
"""
import os

from PyInstaller.utils.hooks import collect_data_files

HERE = os.path.abspath(SPECPATH)                          # noqa: F821

# ===========================================================================
# 🚨 THE EXECUTABLE'S ICON IS A WIN32 RESOURCE, NOT THE WINDOW'S ICON
# ===========================================================================
#
# `gui/branding.set_window_icon` handles the title bar, Alt-Tab and the
# taskbar button -- at runtime, from PNGs inside the package. ⛔ It does
# NOTHING for what Explorer, the Start menu and a pinned shortcut show: that
# image is compiled into the binary and read before Python starts.
#
# ⭐ RESOLVED THROUGH THE PACKAGE (`hato.__file__`), never from this
# directory -- the same rule `branding.py` states for all three hosts.
#
# ⚠ NEVER FATAL. An icon that cannot be found is a plainer executable, not a
# reason to stop; `smoke_standalone.py` asserts the icon separately rather
# than trusting this to have worked.
try:
    from hato.gui import branding as _branding
    ICON = _branding.ico_path()
    if not os.path.isfile(ICON):
        ICON = None
except Exception:                                         # noqa: BLE001
    ICON = None

# ⭐ DERIVED FROM THE DISPATCH TABLE. See the header -- this is the line that
# stops every subcommand shipping dead.
from hato.cli import COMMANDS, RUN_MODULE                  # noqa: E402

COMMAND_MODULES = sorted(set(COMMANDS.values()) | {RUN_MODULE})

# ⚠ tsubasa's own hook directory. It is not registered as an entry point on
# this machine -- see the header. Reading it, never editing it.
try:
    import tsubasa as _tsubasa
    TSUBASA_HOOKS = os.path.join(os.path.dirname(_tsubasa.__file__),
                                 "__pyinstaller")
    if not os.path.isdir(TSUBASA_HOOKS):
        TSUBASA_HOOKS = None
except Exception:                                         # noqa: BLE001
    TSUBASA_HOOKS = None

HOOKSPATH = [TSUBASA_HOOKS] if TSUBASA_HOOKS else []

# ⭐ hato's OWN data -- the icon exports the window loads by size. hato ships
# no `__pyinstaller` hook of its own (nothing else freezes hato; it is the
# front door, not a library), so this is declared here and
# `smoke_standalone.py` counts the files in the bundle rather than trusting
# it.
HATO_DATA = collect_data_files("hato", includes=["data/*.png", "data/*.ico"])

# ⚠ `numpy` belt-and-braces, mirroring tsubasa's hook: its import is deferred
# into the two align modules, and a frozen app that lost it imports cleanly,
# passes a self-check, and raises on the first alignment.
COMMON_HIDDEN = COMMAND_MODULES + ["numpy"]

#: Optional archive support. ⚠ Guarded extras -- `hato/archives.py` degrades
#: with a stated reason when they are absent, so a missing one is a smaller
#: feature set, never a failure.
for _name in ("py7zr", "rarfile"):
    try:
        __import__(_name)
        COMMON_HIDDEN.append(_name)
    except Exception:                                     # noqa: BLE001
        pass

#: ⚠ Pruned. ⛔ NOTHING UNDER `numpy` IS EXCLUDED -- it is tsubasa's one hard
#: dependency and excluding a submodule trades megabytes for a crash on some
#: path nobody exercised.
EXCLUDE = [
    "scipy", "matplotlib", "pandas", "PIL", "IPython", "notebook",
    "PySide2", "PySide6", "PyQt5", "tkinter",
    "pytest", "_pytest", "pluggy", "sphinx", "docutils",
]

#: ⛔ Qt is excluded from the CLI and the WATCHER. See the header: this is
#: the 13.4-vs-30.6 MB argument expressed as a build.
NO_QT = EXCLUDE + ["PyQt6"]


def _analysis(script, excludes):
    return Analysis(                                      # noqa: F821
        [os.path.join(HERE, script)],
        pathex=[],
        binaries=[],
        datas=HATO_DATA,
        hiddenimports=COMMON_HIDDEN,
        hookspath=HOOKSPATH,
        hooksconfig={},
        runtime_hooks=[],
        excludes=excludes,
        noarchive=False,
    )


cli = _analysis("entry_cli.py", NO_QT)
watch = _analysis("entry_watch.py", NO_QT)
gui = _analysis("entry_gui.py", EXCLUDE)

cli_pyz = PYZ(cli.pure, cli.zipped_data)                  # noqa: F821
watch_pyz = PYZ(watch.pure, watch.zipped_data)            # noqa: F821
gui_pyz = PYZ(gui.pure, gui.zipped_data)                  # noqa: F821

cli_exe = EXE(                                            # noqa: F821
    cli_pyz, cli.scripts, [],
    exclude_binaries=True,
    # ⛔ `hato-cli`, because `hato.exe` is THE WINDOW -- see the header.
    name="hato-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # ⛔ TRUE, AND IT IS NOT A DETAIL. This is the command line. A console app
    # with no console has nowhere to print, and `--version` -- the one thing a
    # person is asked to run when they report a bug -- would produce nothing.
    # ⚠ It is also the child the window PIPES: the window reads its stdout.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

watch_exe = EXE(                                          # noqa: F821
    watch_pyz, watch.scripts, [],
    exclude_binaries=True,
    name="hato-watch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # ⛔ FALSE. A tray process with a console attached for its whole life is
    # the one packaging detail every user can see -- and this one is resident
    # for as long as the machine is on.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

gui_exe = EXE(                                            # noqa: F821
    gui_pyz, gui.scripts, [],
    exclude_binaries=True,
    # ⭐ THE ONE A PERSON CLICKS. Sonic's ruling, 2026-09-18.
    name="hato",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

# ⭐ ONE COLLECT, ALL THREE EXECUTABLES, ONE FOLDER. This is the contract at
# the top of this file expressed as a build: the three exes land as siblings,
# which is exactly where each one looks for the other two.
coll = COLLECT(                                           # noqa: F821
    cli_exe, cli.binaries, cli.datas,
    watch_exe, watch.binaries, watch.datas,
    gui_exe, gui.binaries, gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="hato",
)
