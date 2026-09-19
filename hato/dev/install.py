# -*- coding: utf-8 -*-
"""
The claim that would have caught tsubasa 0.1.0.

    python -m hato.dev verify-install --no-unrar

🚨 QUOTED FROM THE PROCESS DOC, BECAUSE IT IS THE REASON THIS FILE EXISTS:
"Every check was green because every check ran inside a checkout. 0.1.0 passed
its CI matrix and its release job, and `sync(scan(folder))` raised ConfigError
for every `pip install` user. Found only by installing from PyPI into a clean
venv and running the usage examples OUTSIDE any checkout."

So: a fresh venv in a temp directory, the wheel installed into it, and the CLI
run from that directory -- with no project file in it OR IN ANY PARENT ABOVE IT.

🚨 AND THE PARENT WALK IS NOT OPTIONAL. The process doc's own note on the CI step
that was supposed to cover this: "It checks the working directory only; the walk
up the parent folders was done by hand, once." ⭐ For hato the parents that matter
are NOT the working directory's: `paths.find_project_config()` defaults to
`PACKAGE_DIR` and walks up from THERE -- so the chain above the installed
package (site-packages, the venv, and everything above it) is the one that can
reopen P6. `parent_config_offenders` is given BOTH chains and neither may hold a
`hato.config.json` or a `tsubasa.config.json`.

⚠ PITFALL P24: `python -m build` is not part of Python. When `--build` is asked
for, the frontend goes into a THROWAWAY venv and the wheel is built from there --
never into the system interpreter -- and it is then tested in a SECOND, clean venv.

⚠ PITFALL P22: on Windows, Git Bash's `/tmp` is not Python's temp, and a heredoc
with nested quotes breaks. Every temp path here comes from `tempfile`, and the
multi-line probe is WRITTEN TO A FILE and run by path -- never passed as `-c`.

⛔ THIS COMMAND IS SLOW AND NEEDS THE NETWORK, so it is not in the default suite.
What the suite covers is the part that has ever been wrong: `parent_config_offenders`,
`path_without`, `rar_tools`, and `assess` -- all pure, all driven from synthetic
inputs. The real run is the release block's.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hato.dev import claims
from hato.dev.claims import Fault, fail, ok

#: The files whose presence above an install reopens pitfall P6.
PROJECT_CONFIGS = ("hato.config.json", "tsubasa.config.json")

_TRACEBACK = "Traceback (most recent call last)"


def rar_tools():
    """Every external tool hato looks for before offering a `.rar`. -> tuple

    ⭐ PARSED FROM `archives.NO_RAR_TOOL`, not copied: a scrub over a stale list
    would leave a tool on PATH and make `--no-unrar` vacuous -- the exact shape of
    a check that cannot fail. The suite asserts this parse is non-empty and holds
    "unrar", so a reworded message turns the suite red instead of emptying it.
    """
    from hato import archives
    m = re.search(r"looked for ([^)]+)\)", archives.NO_RAR_TOOL)
    if not m:
        raise Fault("hato/archives.py's NO_RAR_TOOL no longer says which tools it "
                    "looked for, so --no-unrar cannot know what to remove from PATH")
    names = [n.strip() for n in re.split(r",|\band\b", m.group(1)) if n.strip()]
    if not names:
        raise Fault("parsed 0 tool names out of NO_RAR_TOOL")
    return tuple(names)


def parent_config_offenders(starts, names=PROJECT_CONFIGS, exists=None):
    """Every `<dir>/<name>` that exists, walking UP from each start (inclusive).

    -> [str], sorted and de-duplicated. `exists` is injectable so the suite can
    drive the walk without creating directories.
    """
    exists = (lambda p: Path(p).is_file()) if exists is None else exists
    hits = set()
    for start in starts:
        if start is None:
            continue
        here = Path(start)
        for d in [here] + list(here.parents):
            for name in names:
                candidate = d / name
                if exists(candidate):
                    hits.add(candidate.as_posix())
    return sorted(hits)


def path_without(tools, path_value, pathsep=os.pathsep, lister=None):
    """PATH with every directory holding any of `tools` dropped. -> (new, [removed])

    ⚠ On Windows the executable is `unrar.exe`, so each name is tried with the
    suffixes Windows actually uses as well as bare.
    """
    suffixes = ("", ".exe", ".cmd", ".bat", ".com")
    lister = (lambda p: Path(p).is_file()) if lister is None else lister
    kept, removed = [], []
    for entry in (path_value or "").split(pathsep):
        if not entry:
            continue
        found = None
        for tool in tools:
            for suffix in suffixes:
                if lister(Path(entry) / (tool + suffix)):
                    found = tool + suffix
                    break
            if found:
                break
        if found:
            removed.append("%s (%s)" % (entry, found))
        else:
            kept.append(entry)
    return pathsep.join(kept), removed


def assess(results, expected_version, no_unrar):
    """-> [Claim] over RECORDED command outcomes.

    `results` maps a step name to {"rc": int, "out": str, "err": str}, plus
    "offenders": [str] from `parent_config_offenders`. ⭐ Pure on purpose: the
    assertion set is the part that has to be right, and it must be testable
    without making a venv (doctrine/verification: match the run to the question).
    """
    out = []
    offenders = results.get("offenders")
    if offenders is None:
        out.append(fail("venv_isolated",
                        "the parent walk was never run, so nothing proved the "
                        "install is outside every checkout (pitfall P6)"))
    elif offenders:
        out.append(fail("venv_isolated",
                        "%d project config(s) above the install: %s -- an installed "
                        "hato walks UP from its package directory, so this reopens "
                        "pitfall P6" % (len(offenders), ", ".join(offenders[:3]))))
    else:
        out.append(ok("venv_isolated",
                      "no %s in the working directory, the site-packages directory, "
                      "or ANY parent of either (%d chain(s) walked)"
                      % (" / ".join(PROJECT_CONFIGS),
                         len(results.get("chains") or ()) or 2)))

    def step(name, key, want, describe):
        got = results.get(key)
        if got is None:
            out.append(fail(name, "%s was never run" % key))
            return
        if got.get("rc") != 0:
            out.append(fail(name, "%s exited %s: %s" % (key, got.get("rc"),
                                                        _one_line(got))))
            return
        text = (got.get("out") or "").strip()
        if want(text):
            out.append(ok(name, "%s -> %r" % (key, text.splitlines()[0][:90]
                                              if text else "")))
        else:
            out.append(fail(name, "%s exited 0 and %s: %r"
                            % (key, describe, text[:120])))

    step("cli_version", "hato --version",
         lambda t: t == "hato %s" % expected_version,
         "did not print %r" % ("hato %s" % expected_version))
    step("import_version", "import hato",
         lambda t: t == expected_version,
         "did not print %r" % expected_version)
    step("cli_help", "hato --help",
         lambda t: "usage: hato" in t,
         "did not print a usage line")

    noisy = [k for k, v in results.items()
             if isinstance(v, dict) and (_TRACEBACK in (v.get("out") or "")
                                         or _TRACEBACK in (v.get("err") or ""))]
    if noisy:
        out.append(fail("no_traceback",
                        "%d step(s) printed a traceback: %s" % (len(noisy),
                                                                ", ".join(noisy))))
    else:
        out.append(ok("no_traceback", "no step printed a traceback"))

    if no_unrar:
        probe = results.get("degradation probe")
        if probe is None:
            out.append(fail("unrar_absent", "the degradation probe was never run"))
        elif probe.get("rc") != 0:
            out.append(fail("unrar_absent", "the degradation probe exited %s: %s"
                            % (probe.get("rc"), _one_line(probe))))
        else:
            text = probe.get("out") or ""
            scrubbed = re.search(r"^RAR TOOLS: none of ([0-9]+) found$", text, re.M)
            if not scrubbed:
                out.append(fail("unrar_absent",
                                "the probe did not confirm PATH was scrubbed, so "
                                "every claim below it would be vacuous: %r"
                                % text[:120]))
            else:
                out.append(ok("unrar_absent",
                              "none of the %s rar tools is on PATH inside the venv"
                              % scrubbed.group(1)))
                zip_ok = "ZIP: extracted 1" in text
                rar_named = re.search(r"^RAR: refused by name -- ", text, re.M)
                if zip_ok and rar_named:
                    out.append(ok("degrades_not_errors",
                                  "with no rar tool: a zip still extracted, and a "
                                  "rar was refused by name, not by a crash"))
                else:
                    out.append(fail("degrades_not_errors",
                                    "with no rar tool the probe reported zip=%s "
                                    "rar_refused_by_name=%s: %r"
                                    % (bool(zip_ok), bool(rar_named), text[:160])))
    return out


def _one_line(got):
    text = ((got.get("err") or "") + " " + (got.get("out") or "")).strip()
    return (text.splitlines() or [""])[0][:160]


# ---------------------------------------------------------------------------
# the slow half -- ⛔ never in the default suite
# ---------------------------------------------------------------------------

#: ⚠ WRITTEN TO A FILE AND RUN BY PATH (pitfall P22). It builds its own zip and
#: its own rar-magic file: ⛔ no real subtitle from anyone's media, ever
#: (spec/07-test-plan.md -- no real media in TheForge).
_PROBE = u'''# -*- coding: utf-8 -*-
"""Does hato degrade, rather than error, with no rar tool anywhere on PATH?"""
import shutil, sys, zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from hato import archives

tools = %(tools)r
present = [t for t in tools if shutil.which(t)]
if present:
    print("RAR TOOLS: STILL ON PATH: " + ", ".join(present))
else:
    print("RAR TOOLS: none of %%d found" %% len(tools))

here = Path(__file__).resolve().parent
zip_path = here / "probe.zip"
with zipfile.ZipFile(str(zip_path), "w") as zf:
    zf.writestr("probe.srt", b"1\\r\\n00:00:01,000 --> 00:00:02,000\\r\\nsynthetic\\r\\n\\r\\n")
try:
    got = archives.extract(zip_path, here / "out-zip")
    print("ZIP: extracted %%d member(s)" %% len(got.members))
except Exception as exc:
    print("ZIP: FAILED %%s: %%s" %% (type(exc).__name__, exc))

rar_path = here / "probe.rar"
rar_path.write_bytes(b"Rar!\\x1a\\x07\\x00" + b"\\x00" * 64)
try:
    archives.extract(rar_path, here / "out-rar")
    print("RAR: extracted -- which cannot be right with no tool")
except (archives.ArchiveUnsupported, archives.ArchiveError) as exc:
    print("RAR: refused by name -- %%s: %%s" %% (type(exc).__name__, exc.reason[:90]))
except Exception as exc:
    print("RAR: CRASHED %%s: %%s" %% (type(exc).__name__, exc))
'''


def _run(argv, cwd=None, env=None, timeout=900):
    proc = subprocess.run([str(a) for a in argv], cwd=None if cwd is None else str(cwd),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    return {"rc": proc.returncode,
            "out": proc.stdout.decode("utf-8", "replace"),
            "err": proc.stderr.decode("utf-8", "replace"),
            "argv": [str(a) for a in argv]}


def _venv_bin(venv):
    return venv / ("Scripts" if os.name == "nt" else "bin")


def _exe(venv, name):
    suffix = ".exe" if os.name == "nt" else ""
    return _venv_bin(venv) / (name + suffix)


def _make_venv(where, label):
    got = _run([sys.executable, "-m", "venv", str(where)])
    if got["rc"] != 0:
        raise Fault("could not create the %s venv at %s: %s" % (label, where,
                                                                _one_line(got)))
    return where


def build_wheel(root, into):
    """⚠ P24: the build frontend goes into a THROWAWAY venv, never the system
    interpreter, and the wheel is tested in a different one. -> Path"""
    venv = _make_venv(into / "build-venv", "build")
    python = _exe(venv, "python")
    for argv in ([python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                 [python, "-m", "pip", "install", "--quiet", "build"]):
        got = _run(argv)
        if got["rc"] != 0:
            raise Fault("could not install the build frontend: %s" % _one_line(got))
    out = into / "dist"
    got = _run([python, "-m", "build", "--wheel", "--outdir", str(out), str(root)])
    if got["rc"] != 0:
        raise Fault("python -m build failed: %s" % _one_line(got))
    wheels = sorted(out.glob("*.whl"))
    if len(wheels) != 1:
        raise Fault("the build produced %d wheels in %s" % (len(wheels), out))
    return wheels[0]


def newest_wheel(root):
    found = sorted((root / "dist").glob("*.whl"))
    if not found:
        raise Fault("no wheel in %s -- run `python -m build` first, or pass --build"
                    % (root / "dist"))
    return max(found, key=lambda p: p.stat().st_mtime)


def run(root, wheel=None, build=False, no_unrar=False, temp_root=None, keep=False):
    """The real thing. -> ([Claim], the temp directory used)."""
    root = Path(root)
    base = Path(tempfile.mkdtemp(prefix="hato-verify-", dir=None if temp_root is None
                                 else str(temp_root)))
    try:
        # ⭐ BEFORE anything is installed: the temp root itself must be outside
        # every checkout, or the whole run proves nothing.
        above = parent_config_offenders([base])
        if above:
            raise Fault("the temp directory %s has a project config above it (%s) -- "
                        "pass --temp-root pointing somewhere outside every checkout"
                        % (base, ", ".join(above)))

        if wheel is not None:
            wheel_path = Path(wheel)
            if not wheel_path.is_file():
                raise Fault("no such wheel: %s" % wheel_path)
        elif build:
            wheel_path = build_wheel(root, base)
        else:
            wheel_path = newest_wheel(root)

        venv = _make_venv(base / "venv", "clean")
        python = _exe(venv, "python")
        got = _run([python, "-m", "pip", "install", "--quiet", str(wheel_path)])
        if got["rc"] != 0:
            raise Fault("pip install %s failed in the clean venv: %s"
                        % (wheel_path.name, _one_line(got)))

        site = _run([python, "-c",
                     "import hato, pathlib; print(pathlib.Path(hato.__file__).resolve().parent)"])
        if site["rc"] != 0:
            raise Fault("the installed hato could not be imported: %s" % _one_line(site))
        package_dir = Path(site["out"].strip())

        work = base / "outside"                 # ⛔ no project file in it, by construction
        work.mkdir()
        chains = [work, package_dir]
        results = {"offenders": parent_config_offenders(chains),
                   "chains": [str(c) for c in chains]}

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.pop("PYTHONPATH", None)             # ⛔ never the checkout
        removed = []
        if no_unrar:
            env["PATH"], removed = path_without(rar_tools(), env.get("PATH", ""))

        results["hato --version"] = _run([_exe(venv, "hato"), "--version"],
                                         cwd=work, env=env)
        results["import hato"] = _run([python, "-c",
                                       "import hato; print(hato.__version__)"],
                                      cwd=work, env=env)
        results["hato --help"] = _run([_exe(venv, "hato"), "--help"], cwd=work, env=env)

        if no_unrar:
            probe = work / "degradation_probe.py"
            probe.write_bytes((_PROBE % {"tools": list(rar_tools())}).encode("utf-8"))
            results["degradation probe"] = _run([python, str(probe)], cwd=work, env=env)

        expected, _ = claims.read_source_version(root)
        out = assess(results, expected, no_unrar)
        if no_unrar:
            out.append(ok("path_scrubbed",
                          "%d PATH entry(ies) removed for holding a rar tool%s"
                          % (len(removed), ": " + "; ".join(removed[:2]) if removed
                             else " (none were on PATH to begin with)")))
        return out, base
    finally:
        if not keep:
            shutil.rmtree(str(base), ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev verify-install")
    parser.add_argument("--root", metavar="DIR", help="the source checkout")
    parser.add_argument("--wheel", metavar="PATH", help="the wheel to install")
    parser.add_argument("--build", action="store_true",
                        help="build the wheel first, in a throwaway venv (P24)")
    parser.add_argument("--no-unrar", action="store_true",
                        help="drop every rar tool from PATH and assert hato degrades")
    parser.add_argument("--temp-root", metavar="DIR",
                        help="where to make the venv (default: the system temp dir)")
    parser.add_argument("--keep", action="store_true",
                        help="leave the venv behind for diagnosis")
    args = parser.parse_args(argv)
    root = claims.find_root(args.root)
    results, base = run(root, wheel=args.wheel, build=args.build,
                        no_unrar=args.no_unrar, temp_root=args.temp_root,
                        keep=args.keep)
    subject = "%s  (%s)" % (root, base if args.keep else "temp directory removed")
    return claims.report("verify-install", subject, results)
