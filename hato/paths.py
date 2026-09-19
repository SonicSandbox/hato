# -*- coding: utf-8 -*-
"""
Where hato's things live. ONE module, so nothing else guesses a path.

    data_root()          per-user app data. HATO_CACHE relocates ALL of it
      cache_dir()          the working cache (downloads, archives, refused candidates)
      state_db_path()      the state DB
      key_file_path()      key.txt -- what a stranger fills in (RUNBOOK 1c)
      default_subs_dir()   kept originals, when config.toml leaves subs_dir empty
      default_log_path()   the run log, when config.toml leaves log.path empty
      lock_path()          one run at a time
    config_path()        config.toml. HATO_CONFIG overrides
    keystore_file()      WHICH key file to read, by precedence
    project_config()     hato.config.json -- the SOURCE TREE's config, never shipped

⭐ HATO_CACHE RELOCATES THE WHOLE PER-USER ROOT, not just the cache folder.
spec/CONTEXT.md: "Cache, state DB -- per-user app data; HATO_CACHE overrides", and
spec/07-test-plan.md: the harness sets HATO_CACHE and HATO_CONFIG and "no test may
read or write the real cache, the real DB". If the subs_dir or log defaults ignored
HATO_CACHE, a test writing a kept original would land in the developer's real
%LOCALAPPDATA%\\hato while every check stayed green. One variable, one root.

⛔ EVERY OVERRIDE MUST BE ABSOLUTE. A relative HATO_CACHE resolves against the
working directory, and Task Scheduler starts a process somewhere unexpected
(spec/10-deployment.md) -- the run would silently use a different store than the
terminal does. Refused loudly instead.
"""
import json
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_CONFIG_NAME = "hato.config.json"
#: The key file inside the per-user root. The window writes this same file
#: through this same code (spec/05-interface.md §The window).
KEY_FILENAME = "key.txt"


class PathError(Exception):
    """A location could not be resolved. The message says what would fix it."""


def _is_windows():
    return os.name == "nt"


def _absolute_from_env(var):
    """(Path, var) when `var` is set, else None. ⛔ Relative is refused."""
    raw = os.environ.get(var)
    if raw is None or raw.strip() == "":
        return None
    p = Path(os.path.expanduser(raw.strip()))
    if not p.is_absolute():
        raise PathError(
            "%s must be an absolute path, got %r. A relative path resolves "
            "against the working directory, and a scheduled run starts "
            "somewhere unexpected." % (var, raw))
    return p


# ---------------------------------------------------------------------------
# the per-user data root
# ---------------------------------------------------------------------------

def default_data_root():
    """The REAL per-user root, ignoring HATO_CACHE.

    The runner asks for this to prove a test run left it untouched, so it must
    not follow the override it is checking.
    """
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise PathError(
                "LOCALAPPDATA is not set, so the per-user data folder cannot be "
                "found. Set HATO_CACHE to an absolute folder instead.")
        return Path(base) / "hato"
    # ⛔ NOT ~/.cache. The root holds subs/ -- the kept originals hato must never
    # delete (spec/05-interface.md) -- and ~/.cache is the one directory a user or
    # a cleanup tool may wipe without being asked. Corrected 2026-09-17, RUNBOOK 1c.
    return Path.home() / ".local" / "share" / "hato"


def legacy_data_root():
    """The pre-1c non-Windows root, ONLY when one is still sitting there. -> Path|None

    ⛔ Nothing is migrated automatically (spec/05-interface.md): `hato doctor` says
    so in one line and moves nothing, deletes nothing. Windows never moved, so
    there is nothing to say there; and a relocated root (HATO_CACHE) makes the old
    default noise rather than news.
    """
    try:
        if _is_windows() or _absolute_from_env("HATO_CACHE") is not None:
            return None
    except PathError:
        return None
    old = Path.home() / ".cache" / "hato"
    return old if old.is_dir() else None


def data_root():
    """-> Path. HATO_CACHE when set (absolute), else the per-user default."""
    override = _absolute_from_env("HATO_CACHE")
    return override if override is not None else default_data_root()


def data_root_source():
    """Which rule produced data_root(), in words -- for `config --show`."""
    return "HATO_CACHE" if _absolute_from_env("HATO_CACHE") is not None else "default"


def cache_dir():
    return data_root() / "cache"


def state_db_path():
    return data_root() / "state.db"


def key_file_path():
    """<root>/key.txt -- the ONE file `hato key --set-from` ever writes.

    ⛔ Deliberately NOT HATO_KEYFILE: the destination must be the same place a
    stranger, the window and this machine's next run all look, whatever a stray
    environment variable says.
    """
    return data_root() / KEY_FILENAME


def default_subs_dir():
    return data_root() / "subs"


def default_log_path():
    return data_root() / "hato.log"


def lock_path():
    return data_root() / "hato.lock"


# ---------------------------------------------------------------------------
# config.toml
# ---------------------------------------------------------------------------

def default_config_path():
    """The documented location (spec/05-interface.md), ignoring HATO_CONFIG."""
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise PathError(
                "LOCALAPPDATA is not set, so config.toml cannot be found. Set "
                "HATO_CONFIG to its absolute path instead.")
        return Path(base) / "hato" / "config.toml"
    return Path.home() / ".config" / "hato" / "config.toml"


def config_path():
    """-> (Path, source). source is "HATO_CONFIG" or "default"."""
    override = _absolute_from_env("HATO_CONFIG")
    if override is not None:
        return override, "HATO_CONFIG"
    return default_config_path(), "default"


# ---------------------------------------------------------------------------
# the source tree's own config
# ---------------------------------------------------------------------------

def find_project_config(start=None):
    """Walk UP from `start` (default: this package) to hato.config.json.

    -> Path, or None in an installed package, where there is no source tree.
    """
    here = Path(start).resolve() if start is not None else PACKAGE_DIR
    for d in [here] + list(here.parents):
        candidate = d / PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def project_config(start=None):
    """-> (dict, Path) or (None, None). ⚠ A config that exists and does not
    parse is an error, never a silent None -- that would read as 'installed'."""
    path = find_project_config(start)
    if path is None:
        return None, None
    try:
        with open(str(path), encoding="utf-8") as fh:
            return json.load(fh), path
    except (OSError, ValueError) as exc:
        raise PathError("%s exists but could not be read: %s" % (path, exc))


def tsubasa_checkout(start=None):
    """-> Path of the vault tsubasa checkout named by hato.config.json, or None."""
    cfg, path = project_config(start)
    if not cfg:
        return None
    rel = (cfg.get("tsubasa") or {}).get("checkoutRelative")
    if not rel:
        return None
    return (path.parent / rel).resolve()


def key_file_candidates(start=None):
    """The key FILE's places in order, most specific first: [(Path, source), ...].

    ⛔ HATO_KEYFILE, WHEN SET, IS THE WHOLE LIST -- it never falls through to
    another file, even when it names one that does not exist. That is what keeps a
    test run out of the developer's real keystore: the harness points HATO_KEYFILE
    at a file it knows is absent (spec/07-test-plan.md), and a fall-through would
    quietly read the real key instead.

    Otherwise: <root>/key.txt -- the file a stranger fills in and the window writes
    -- then the source tree's own keystore, which exists on this machine only.
    ⚠ This never reads a file; `credentials` does.
    """
    override = _absolute_from_env("HATO_KEYFILE")
    if override is not None:
        return [(override, "HATO_KEYFILE")]
    found = []
    try:
        found.append((key_file_path(), "key.txt in hato's data folder"))
    except PathError:
        pass                            # no per-user root: the source tree may still have one
    cfg, path = project_config(start)
    rel = ((cfg or {}).get("keystore") or {}).get("fileRelative")
    if rel:
        found.append(((path.parent / rel).resolve(), "keystore (hato.config.json)"))
    return found


def keystore_file(start=None):
    """-> (Path, source) for the key file to READ, or (None, reason).

    Precedence (RUNBOOK 1c): $HATO_JIMAKU_KEY is `credentials`' own first step and
    never reaches here; then HATO_KEYFILE, then <root>/key.txt, then the dev
    keystore. The first candidate that EXISTS wins; when none does, the first one
    is named anyway, so the message tells a stranger where to put the key.
    """
    candidates = key_file_candidates(start)
    for candidate, source in candidates:
        if candidate.is_file():
            return candidate, source
    if candidates:
        return candidates[0]
    return None, ("no HATO_KEYFILE, no per-user data folder, and no source-tree "
                  "keystore path (installed package)")


# ---------------------------------------------------------------------------
# is this path inside one of those folders?
# ---------------------------------------------------------------------------
# ⭐ HERE BECAUSE TWO PROGRAMS NEED IT AND ONE OF THEM MAY NOT IMPORT THE OTHER.
# `pipeline` uses it to drop videos inside a skipped folder; the tray watcher
# uses it to decide which folders to watch at all. ⛔ `hato/watch.py` is
# forbidden to import `hato.pipeline` -- that separation is the entire reason
# the watcher is 13.4 MB instead of a resident Qt process -- and a second copy
# is worse: this is the PREFIX TRAP, where a drifted copy silently takes a
# different library out of every run.
# ⚠ `paths` is the right home precisely because it imports nothing but the
# stdlib, so neither caller pays anything to reach it.

def normalised(path):
    u"""One path's identity. -> str

    ⚠ Normcased: on Windows `D:/A/x.mkv` and `d:/a/X.MKV` are one file, and two
    roots differing only in case are exactly how a person reaches the same tree
    twice. (Written with forward slashes here on purpose -- a backslash in a
    docstring is an escape, and this module has already been broken once by
    one.)
    """
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def last_run_path():
    u"""-> where the window remembers the run it last painted.

    ⚠ IN hato's OWN ROOT, beside the cache and the DB -- never beside the
    media. It is the window's memory, not the user's data, and `HATO_CACHE`
    relocates it with everything else so a test cannot reach the real one.
    """
    return data_root() / u"last-run.json"


def child_env(base=None):
    u"""The environment any hato child needs. -> dict

    🚨 THE THIRD COPY OF THIS WAS WRONG AND IT COST A SILENT FAILURE. Sonic,
    2026-09-18: *"if its in the tray and i hit 'open now' it doesn't open."*
    The tray built its own environment, set the UTF-8 variables and omitted
    `PYTHONPATH` -- so `-m hato.gui` ran with the tray's working directory,
    which for a process started from a shortcut is wherever the shortcut
    pointed, and died instantly with `ModuleNotFoundError: No module named
    'hato'`. ⛔ The spawn only caught `OSError`, so nothing appeared anywhere.
    *"Run now"* from the tray had the identical bug.

    ⭐ ONE COPY, HERE, because the three callers cannot all reach each other:
    the window may import the toolkit, the watcher may not import the window,
    and this module imports nothing but the stdlib. That is exactly why the
    logic drifted in the first place.

    ⚠ `PYTHONIOENCODING` does NOTHING to a frozen child -- measured on tsubasa,
    the PyInstaller bootloader runs Python isolated. It is set anyway because
    it is correct for the source path and costs nothing on the frozen one.
    """
    env = dict(os.environ if base is None else base)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 🚨 A HEADLESS Qt PLATFORM IS NEVER INHERITED BY A CHILD. Measured
    # 2026-09-18, and it is the bug Sonic hit twice: *"it's in the tray but
    # can't see the UI. both the tray click and hato shortcut doesn't work."*
    #
    # ⭐ THE WINDOW WAS RUNNING PERFECTLY THE WHOLE TIME. With
    # `QT_QPA_PLATFORM=offscreen` in its environment it builds every widget,
    # enters its event loop, answers the single-instance socket -- and draws to
    # nowhere. Alive, responsive, 65 MB, and no window. Then it holds the
    # instance name, so every later launch politely stands down in favour of a
    # window nobody can see.
    #
    # ⚠ It reaches a window by INHERITANCE: whatever started the tray passes
    # its environment on, and the tray passes it to every window it opens. One
    # shell with that variable set poisons every hato opened from then on.
    # ⛔ Only the values that make a GUI invisible are dropped -- a deliberate
    # `wayland` or `windows` override is somebody's real choice and is kept.
    if env.get("QT_QPA_PLATFORM", "").strip().lower() in (
            "offscreen", "minimal", "vnc"):
        env.pop("QT_QPA_PLATFORM", None)
    # ⚠ Only from source. A frozen child has no package to find on a path.
    if not getattr(sys, "frozen", False):
        parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (parent + os.pathsep + existing) if existing \
            else parent
    return env


def under_any(path, folders):
    u"""Is `path` inside any of `folders`? -> bool

    🚨 COMPONENT-WISE, NEVER `startswith`. A prefix test says `D:/Anime2` is
    inside `D:/Anime`, so skipping one folder would silently take a DIFFERENT
    library out of every run -- and nothing would report it, because a skipped
    video looks exactly like a video that was never there.
    """
    if not folders:
        return False
    target = normalised(path).split(os.sep)
    for folder in folders:
        parts = normalised(folder).rstrip(os.sep).split(os.sep)
        if len(parts) < len(target) and target[:len(parts)] == parts:
            return True
    return False
