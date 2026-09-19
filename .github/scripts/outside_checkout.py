# -*- coding: utf-8 -*-
"""🚨 THE INSTALLED PACKAGE, RUN FROM OUTSIDE EVERY CHECKOUT. Pitfall P6.

    python .github/scripts/outside_checkout.py --forbid-under "$GITHUB_WORKSPACE"

⛔ Run it from a directory that is NOT in the source tree, against a `hato`
installed from a built wheel. It imports `hato` and nothing else of the
project's -- no `hato.dev`, no `conftest`, no test helper -- because everything
it is trying to disprove is *something a checkout supplies*.

Exit 0 when every claim holds; 1 naming the claim that failed and what it saw;
2 when the tool itself could not run.

===========================================================================
🚨 WHAT WENT WRONG, AND IT WENT WRONG IN THE SIBLING PROJECT'S 0.1.0
===========================================================================
Quoted from `PYPI-PUBLISHING-DRAFT-2026-09-16.md`:

  "Every check was green because every check ran inside a checkout. tsubasa
   0.1.0 passed its CI matrix and its release job, and `sync(scan(folder))`
   raised ConfigError for EVERY `pip install` user. Found only by installing
   from PyPI into a clean venv and running the usage examples outside any
   checkout."

  "P6 -- `cache_root()` read the DEVELOPMENT config, present in the vault and,
   via the copy list, in the clone. Every suite, CI job and example ran inside
   a checkout, and the jobs outside one only called the parts that never touch
   the cache."

⭐ hato has the same exposure, in the same shape. `hato.config.json` IS in the
publish clone's copy list, and `hato/paths.py::find_project_config()` is the
equivalent of `cache_root()`.

⭐ AND HATO'S WALK IS NOT THE ONE THE SIBLING'S GUARD CHECKED. That guard was
`test ! -e tsubasa.config.json` in the working directory, and the doc says of
it: "⚠ It checks the working directory only; the walk up the parent folders was
done by hand, once." hato's `find_project_config(start=None)` walks up from
**PACKAGE_DIR** -- the installed package's own folder -- so the chain that
actually matters runs from `site-packages/hato/` to the filesystem root, and the
working directory's chain matters separately because the CLI and the tests pass
`start=` explicitly. ⛔ BOTH CHAINS ARE WALKED HERE, PROGRAMMATICALLY, EVERY
PARENT, AND THE COUNT OF DIRECTORIES WALKED IS PRINTED -- a walk that visited
one directory and a walk that visited nine both "find nothing".

===========================================================================
⭐ AND IT EXERCISES A PATH THAT TOUCHES THE CACHE AND THE CONFIG
===========================================================================
`--version` and `--help` are what the sibling's outside-the-checkout job ran,
and they are precisely the parts that never touch the cache -- which is why
0.1.0 shipped. So this asserts, in process AND through the command line:

    paths.data_root() · cache_dir() · state_db_path() · default_subs_dir()
    · default_log_path() · lock_path() · config.load() · `hato config --show`

with NO `HATO_CACHE` and NO `HATO_CONFIG` set, because the default path is the
one every installed user gets and the overrides are what make a green check
vacuous.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_CLAIM_FAILED = 1
EXIT_FAULT = 2

#: The file that must not be reachable. It is the development runner's config.
DEV_CONFIG = "hato.config.json"
#: Other things whose presence above us would mean we are in a checkout after all.
SOURCE_MARKERS = ("pyproject.toml", os.path.join("hato", "__init__.py"),
                  "run_tests.py", "conftest.py")
#: Overrides that would make every claim below pass for the wrong reason.
FORBIDDEN_ENV = ("HATO_CACHE", "HATO_CONFIG", "HATO_KEYFILE", "HATO_JIMAKU_KEY",
                 "HATO_TEST_ROOT", "PYTHONPATH")


class Fault(Exception):
    """This tool could not run. Exit 2, never a traceback."""


def ascii_only(text):
    """⚠ Every byte this prints is ASCII. A Japanese path in a message must not
    be the thing that kills the reporter -- see `report_failures.py`'s P15."""
    if not isinstance(text, type(u"")):
        text = u"%s" % (text,)
    return text.encode("ascii", "backslashreplace").decode("ascii")


def encode(text):
    """Percent-encode a workflow command's message. ⛔ `%` first, or it eats its
    own escapes. ⚠ And these messages DO carry `%`: a match rate, a path with an
    escaped character, a Windows `%LOCALAPPDATA%`."""
    return (ascii_only(text).replace(u"%", u"%25")
            .replace(u"\r", u"%0D").replace(u"\n", u"%0A"))


class Claims(object):
    """A list of named claims, printed in full whether they held or not.

    ⭐ Same shape as `hato/dev/`'s release tooling, deliberately: a reader
    comparing a CI log against a `python -m hato.dev audit-wheel` log should not
    have to learn two formats. ⛔ Not IMPORTED from there -- `hato.dev` is
    development tooling and may not be in the wheel at all, and this script's
    whole job is to run against what the wheel actually contains.
    """

    def __init__(self):
        self.rows = []

    def ok(self, name, saw):
        self.rows.append((True, name, saw))

    def fail(self, name, saw):
        self.rows.append((False, name, saw))

    def check(self, name, condition, saw):
        (self.ok if condition else self.fail)(name, saw)
        return bool(condition)

    def report(self, subject, stream=None):
        stream = stream or sys.stdout
        failed = [r for r in self.rows if not r[0]]
        stream.write(ascii_only(u"outside-the-checkout guard: %s\n" % subject))
        for good, name, saw in self.rows:
            stream.write(ascii_only(u"  %-4s %-28s %s\n"
                                    % ("ok" if good else "FAIL", name, saw)))
        if failed:
            for _good, name, saw in failed:
                # ⛔ THE ONE CHANNEL READABLE WITHOUT CREDENTIALS (P14).
                # ⚠ NO COLON IN THE TITLE. GitHub splits the command on `::`
                # and reads the properties as a comma-separated `k=v` list, so
                # an unescaped `:` there eats the message. Measured 2026-09-17
                # in `report_failures.py`, where a title reading
                # `failures: no run log` matched no annotation parser at all.
                stream.write(
                    u"::error title=outside-the-checkout %s::%s\n"
                    % (ascii_only(name), encode(saw)))
            stream.write(ascii_only(u"%d of %d claims FAILED\n"
                                    % (len(failed), len(self.rows))))
            return EXIT_CLAIM_FAILED
        stream.write(ascii_only(u"all %d claims hold\n" % len(self.rows)))
        return EXIT_OK


# ---------------------------------------------------------------------------
# the parent walk -- the thing the sibling project did by hand, once
# ---------------------------------------------------------------------------

def walk_up(start):
    """[start, start.parent, ..., root] -- EVERY parent, resolved.

    ⛔ `Path.parents` is the whole chain and `[here] + list(here.parents)` is
    what `hato/paths.py::find_project_config` itself walks. Anything narrower
    here would be a guard that does not cover the mechanism it guards.
    """
    here = Path(start).resolve()
    return [here] + list(here.parents)


def find_above(start, filename):
    """-> (hit or None, directories walked). The count is the DENOMINATOR.

    ⚠ doctrine/verification: "print the denominator in the detail string, so a
    vacuous pass is visible at a glance." A walk that visited ONE directory and
    found nothing is not the same claim as a walk that visited nine.
    """
    chain = walk_up(start)
    for directory in chain:
        candidate = directory / filename
        if candidate.exists():
            return candidate, len(chain)
    return None, len(chain)


def scrubbed_env():
    """The environment an installed user has: no HATO_* override, no PYTHONPATH.

    🚨 PYTHONPATH IS THE ONE PEOPLE FORGET. The sibling project's examples ran
    with `PYTHONPATH="$PWD"`, which is how a job "outside the checkout" imported
    the checkout anyway. `conftest.py` here puts both the hato tree and the
    tsubasa checkout on PYTHONPATH *for every subprocess a test starts*, so a
    leaked value is not hypothetical.
    """
    env = dict(os.environ)
    for name in FORBIDDEN_ENV:
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run(argv, env=None):
    """-> (returncode, combined output). Never raises on a non-zero exit."""
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=300,
                              env=env or scrubbed_env())
    except OSError as exc:
        return None, u"%s: %s" % (type(exc).__name__, exc)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# the claims
# ---------------------------------------------------------------------------

def claim_environment(claims):
    """⭐ THE PRECONDITION, ASSERTED OUT LOUD. Without this every claim below
    could be passing because a harness pointed HATO_CACHE at a temp dir."""
    set_here = [n for n in FORBIDDEN_ENV if os.environ.get(n)]
    return claims.check(
        "env_overrides_absent", not set_here,
        "none of %s is set" % (", ".join(FORBIDDEN_ENV),) if not set_here
        else ("set, so nothing below would be a claim about the DEFAULT paths: "
              + ", ".join("%s=%r" % (n, os.environ[n]) for n in set_here)))


def claim_import(claims, module, forbid_under):
    """`hato` came from an INSTALL, not from the tree beside us.

    ⛔ THE VACUITY GUARD FOR EVERYTHING ELSE IN THIS FILE. doctrine/verification:
    "if the thing I am testing were deleted, and the state around it stayed as it
    is, would this still pass?" If `hato` resolved to the checkout, every claim
    below would be measuring the development tree while reading as green.
    """
    where = Path(module.__file__).resolve()
    if forbid_under:
        forbidden = Path(forbid_under).resolve()
        inside = str(where).startswith(str(forbidden) + os.sep)
        claims.check("imported_from_install", not inside,
                     "hato imported from %s" % where if not inside else
                     "hato imported from %s, which is INSIDE the checkout %s -- "
                     "this whole job is vacuous" % (where, forbidden))
    else:
        claims.ok("imported_from_install",
                  "hato imported from %s (no --forbid-under given)" % where)
    return where


def claim_no_source_above(claims, start):
    """No `hato.config.json` and no source tree in cwd or ANY parent."""
    hit, walked = find_above(start, DEV_CONFIG)
    claims.check("cwd_no_dev_config", hit is None,
                 "walked %d directories from %s upward, no %s"
                 % (walked, start, DEV_CONFIG) if hit is None else
                 "found %s after walking %d directories from %s -- an installed "
                 "hato would read it" % (hit, walked, start))
    strays = []
    for marker in SOURCE_MARKERS:
        found, _n = find_above(start, marker)
        if found is not None:
            strays.append(str(found))
    claims.check("cwd_no_source_tree", not strays,
                 "walked %d directories, none of %s present"
                 % (walked, ", ".join(SOURCE_MARKERS)) if not strays else
                 "a checkout is above us: " + "; ".join(strays))


def claim_no_dev_config_above_package(claims, package_file):
    """🚨 THE CHAIN HATO ACTUALLY WALKS: from the installed package upward.

    `find_project_config(start=None)` starts at `paths.PACKAGE_DIR`, so a
    `hato.config.json` packaged INSIDE the wheel -- or sitting in site-packages,
    or in the venv root -- is read by an installed hato no matter where the user
    is standing. The working directory's chain cannot see that at all.
    """
    package_dir = Path(package_file).resolve().parent
    hit, walked = find_above(package_dir, DEV_CONFIG)
    claims.check("package_no_dev_config", hit is None,
                 "walked %d directories from %s upward, no %s"
                 % (walked, package_dir, DEV_CONFIG) if hit is None else
                 "found %s after walking %d directories from the installed "
                 "package -- find_project_config() starts HERE, so every "
                 "installed user reads it" % (hit, walked))


def claim_find_project_config(claims, paths_module, cwd):
    """The mechanism itself, asked directly, from both start points."""
    try:
        from_package = paths_module.find_project_config()
        from_cwd = paths_module.find_project_config(cwd)
    except Exception as exc:                            # noqa: BLE001
        claims.fail("find_project_config_none",
                    "find_project_config() raised %s: %s" % (type(exc).__name__, exc))
        return
    claims.check("find_project_config_none",
                 from_package is None and from_cwd is None,
                 "None from the package chain and None from %s" % cwd
                 if from_package is None and from_cwd is None else
                 "package chain -> %r, cwd chain -> %r; an installed hato must "
                 "find NEITHER" % (from_package, from_cwd))


def claim_paths_resolve(claims, paths_module, forbid_under):
    """⭐ THE CODE PATH THAT SHIPPED BROKEN. Not `--version`."""
    wanted = ("data_root", "cache_dir", "state_db_path", "default_subs_dir",
              "default_log_path", "lock_path")
    resolved, problems = {}, []
    for name in wanted:
        try:
            value = Path(getattr(paths_module, name)())
        except Exception as exc:                        # noqa: BLE001
            problems.append("%s() raised %s: %s" % (name, type(exc).__name__, exc))
            continue
        resolved[name] = value
        if not value.is_absolute():
            problems.append("%s() -> %s, which is not absolute" % (name, value))
        if forbid_under:
            root = Path(forbid_under).resolve()
            if str(value.resolve()).startswith(str(root) + os.sep):
                problems.append("%s() -> %s, inside the checkout" % (name, value))
    claims.check("cache_paths_resolve", not problems,
                 "data_root=%s and %d more, all absolute and outside the tree"
                 % (resolved.get("data_root"), max(len(resolved) - 1, 0))
                 if not problems else "; ".join(problems))
    source = None
    try:
        source = paths_module.data_root_source()
    except Exception as exc:                            # noqa: BLE001
        claims.fail("data_root_is_the_default",
                    "data_root_source() raised %s: %s" % (type(exc).__name__, exc))
        return
    claims.check("data_root_is_the_default", source == "default",
                 "data_root_source() = %r" % source if source == "default" else
                 "data_root_source() = %r, so this run is NOT measuring the "
                 "path an installed user gets" % source)


def claim_config_loads(claims, cwd):
    """`hato.config.load()` with no config file: documented defaults, no raise.

    🚨 THIS IS THE EXACT SHAPE OF THE 0.1.0 DEFECT. There, the equivalent call
    raised `ConfigError: tsubasa.config.json not found` for every installed user
    while every check stayed green.
    """
    try:
        from hato import config as hato_config
    except Exception as exc:                            # noqa: BLE001
        claims.fail("config_loads",
                    "import hato.config raised %s: %s" % (type(exc).__name__, exc))
        return
    try:
        cfg = hato_config.load()
    except Exception as exc:                            # noqa: BLE001
        claims.fail("config_loads",
                    "config.load() raised %s: %s -- this is P6, and it is what "
                    "shipped" % (type(exc).__name__, exc))
        return
    try:
        as_dict = cfg.as_dict()
    except Exception as exc:                            # noqa: BLE001
        claims.fail("config_loads",
                    "config loaded but as_dict() raised %s: %s"
                    % (type(exc).__name__, exc))
        return
    # ⚠ SHAPE *AND* SUBSTANCE (doctrine/verification): a config object that
    # loaded is the cheap claim; that it carries a resolved data root is the one
    # that breaks.
    root = as_dict.get("data_root")
    claims.check("config_loads", bool(root),
                 "config.load() from %s -> data_root=%s, %d keys"
                 % (cwd, root, len(as_dict)) if root else
                 "config loaded but names no data_root: %r" % (sorted(as_dict),))


def claim_cli(claims, module, cwd):
    """⭐ THE WRAPPER, NOT ONLY THE LIBRARY.

    doctrine/verification: "48 checks imported the driver's functions and proved
    every rule about them -- while the command line built on those functions
    printed a hardcoded wrong value. In every case here, the wrapper was the
    thing that lied."
    """
    script = shutil.which("hato")
    claims.check("console_script_present", bool(script),
                 "hato -> %s" % script if script else
                 "no `hato` on PATH after installing the wheel -- "
                 "[project.scripts] is not wired, and an entry point is a "
                 "string nothing imports at build time (pitfall P4)")
    base = [script] if script else [sys.executable, "-m", "hato"]

    code, output = run(base + ["config", "--show", "--json"])
    payload = None
    if code == 0:
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                except ValueError:
                    payload = None
    good = bool(payload) and payload.get("ok") is True \
        and payload.get("data_root_source") == "default"
    claims.check("cli_config_show", good,
                 "`hato config --show --json` from %s -> data_root=%s (%s)"
                 % (cwd, payload.get("data_root"), payload.get("data_root_source"))
                 if good else
                 "`hato config --show --json` exited %r; first 400 chars: %s"
                 % (code, output[:400].replace("\n", " | ")))

    code, output = run(base + ["--version"])
    expected = "hato %s" % module.__version__
    said = output.strip().splitlines()[0].strip() if output.strip() else ""
    claims.check("cli_version_agrees", code == 0 and said == expected,
                 "`hato --version` -> %r" % said if code == 0 and said == expected
                 else "`hato --version` exited %r and said %r, expected %r"
                      % (code, said, expected))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python .github/scripts/outside_checkout.py",
        description="prove the INSTALLED hato works with no source tree anywhere "
                    "above it (pitfall P6)")
    parser.add_argument("--forbid-under", metavar="DIR",
                        help="the checkout. Nothing may resolve inside it")
    parser.add_argument("--skip-cli", action="store_true",
                        help="library claims only; for a probe run before the "
                             "console script exists")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="ascii", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    cwd = os.getcwd()
    claims = Claims()
    claim_environment(claims)
    claim_no_source_above(claims, cwd)

    try:
        import hato
        from hato import paths as hato_paths
    except Exception as exc:                            # noqa: BLE001
        # ⛔ EXIT 2, AND SAY IT IS A TOOLING FAULT -- a guard that cannot import
        # the thing it guards has proved nothing either way.
        sys.stdout.write(
            u"::error title=outside-the-checkout could not import hato::%s\n"
            % encode(u"%s: %s" % (type(exc).__name__, exc)))
        sys.stdout.write(ascii_only(
            u"TOOLING FAULT: `import hato` failed from %s. Install the wheel "
            u"first.\n" % cwd))
        return EXIT_FAULT

    where = claim_import(claims, hato, args.forbid_under)
    claim_no_dev_config_above_package(claims, where)
    claim_find_project_config(claims, hato_paths, cwd)
    claim_paths_resolve(claims, hato_paths, args.forbid_under)
    claim_config_loads(claims, cwd)
    if not args.skip_cli:
        claim_cli(claims, hato, cwd)

    return claims.report("hato %s, run from %s" % (hato.__version__, cwd))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as exc:
        sys.stderr.write(ascii_only(u"TOOLING FAULT: %s\n" % exc))
        sys.exit(EXIT_FAULT)
