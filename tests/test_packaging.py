# -*- coding: utf-8 -*-
u"""
Is what we are about to PUBLISH true? RUNBOOK step R3.

===========================================================================
EVERY FIELD IN pyproject.toml IS A PUBLISHED CLAIM, AND UPLOADED METADATA
CANNOT BE EDITED
===========================================================================

A wrong value does not get fixed; it stays on that version for ever, and the
version number is burned. So every claim in `pyproject.toml`, `LICENSE` and
`THIRD_PARTY_LICENSES.md` is asserted here -- and asserted against something
DERIVED, never against a second copy of the same list.

That distinction is the whole design of this file. The reference project
(`Development Doctrine/PYPI-PUBLISHING-DRAFT-2026-09-16.md`) shipped five
packaging defects, and each one survived because the only thing that agreed
with the metadata was a human reading it:

  P1  the distribution name was ruled in prose and never written into `name`;
      found by chance, days later
  P2  `project.urls` pointed at a GitHub path whose owner segment was a
      placeholder written before the repo existed -- guard: "manual grep only"
  P3  `requires-python` and the classifiers claimed four Pythons when one had
      run
  P4  a console script pointed at a module that did not exist. Building never
      imports an entry point, so nothing raised -- guard: "none automated"
  P6  the DEV CONFIG shipped inside the package, `cache_root()` found it, and
      the headline call raised `ConfigError` for every `pip install` user,
      while every check was green **because every check ran inside a checkout**

P2's and P4's guards are recorded there as still open. They are built here.

===========================================================================
WHAT THIS SUITE STRUCTURALLY CANNOT COVER
===========================================================================

It tests DECLARATIONS, not an artifact. It never builds a wheel -- the build
frontend is not installed on this machine (pitfall P24) and a build is slow.
So it cannot see:

  - what is actually inside a built wheel or sdist. `python -m hato.dev
    audit-wheel` opens the artifact; this reads the instructions for making it
  - whether the installed package runs OUTSIDE a checkout. That is the exact
    blindness that shipped P6, and no declaration check can close it: it needs
    a clean venv in a folder with no project files above it
  - whether a licence IDENTIFIER in THIRD_PARTY_LICENSES.md is still correct.
    It checks that every declared dependency is NAMED there, which is the part
    that goes stale silently
  - whether a classifier string is a real trove classifier (`trove-classifiers`
    is not installed here; PyPI rejects the upload, which burns the version)
  - whether the name `hato` is still free on PyPI, or whether the version is
    already published. Both need the network, and the default suite makes ZERO
    network calls

Two dependencies are used and neither is added by this file: `packaging` and
`tomli` are both pytest's own requirements (`packaging>=22` and
`tomli>=1; python_version < "3.11"`), so they are present wherever pytest is.
"""
import ast
import fnmatch
import importlib
import io
import os
import re
import sys

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:                                   # this laptop is 3.10 (spec/01-scope.md)
    import tomli as _toml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, u"hato")
PYPROJECT = os.path.join(ROOT, u"pyproject.toml")
LICENSE = os.path.join(ROOT, u"LICENSE")
NOTICES = os.path.join(ROOT, u"THIRD_PARTY_LICENSES.md")

#: The import name a distribution provides, where it differs from the
#: distribution name. ONE entry, and it is the trap the spec was amended for:
#: `pip install tsubasa-sync`, `import tsubasa`. Recorded from the engine's own
#: PyPI metadata (https://pypi.org/pypi/tsubasa-sync/0.1.5/json, read
#: 2026-09-17). Every key must be a declared requirement -- checked below, so
#: this table cannot outlive the dependency it describes.
#: ⚠ A DISTRIBUTION'S NAME IS NOT ITS IMPORT NAME, and canonicalisation makes
#: that worse rather than better: `canonicalize_name` lower-cases, so `PyQt6`
#: becomes `pyqt6` and matches no import site under hato/. Left to the default
#: rule the window's toolkit read as *declared nowhere* AND as *imported
#: nowhere* at the same time -- two checks disagreeing with each other about
#: one package, which is the tell that the mapping and not the code was wrong.
PROVIDES = {u"tsubasa-sync": (u"tsubasa",), u"pyqt6": (u"PyQt6",),
            # RUNBOOK 11a -- the distribution and its import name differ
            u"pycryptodomex": (u"Cryptodome",)}

#: What a declared requirement's EXTRA installs, where hato imports it itself.
#: ONE entry: `tsubasa-sync[parsing]` is how anitopy and guessit reach every
#: install, and `hato doctor` asks each of them to number a name -- the engine's
#: wrapper swallows a parser that fails, so asking through it proves nothing
#: (ADVERSARY 2026-09-22 D1). ⛔ A health check, not a second parser: nothing
#: under hato/ reads a name with them. Recorded from the engine's own metadata,
#: https://pypi.org/pypi/tsubasa-sync/0.1.6/json read 2026-09-22 --
#: `anitopy>=2.1; extra == "parsing"`, `guessit>=3.4; extra == "parsing"`.
#: ⚠ Never counted as UNUSED: they are the engine's, and hato not importing
#: them would be no fault. Every key must be a declared requirement WITH that
#: extra -- checked below, so this cannot outlive what it describes.
EXTRA_PROVIDES = {(u"tsubasa-sync", u"parsing"): (u"anitopy", u"guessit")}

#: Modules that are STDLIB from a later Python than the floor, so they are
#: neither third-party nor declarable. Each must be imported behind a
#: `sys.version_info` test -- asserted, not assumed.
STDLIB_FROM = {u"tomllib": (3, 11)}

#: Python versions a run has actually PROVEN, with the evidence. Checked from
#: BOTH ends: no classifier may claim a version absent from here, and the
#: interpreter running this suite must be present -- so a new runner forces
#: the register to grow instead of being quietly ignored.
PROVEN_PYTHONS = {
    (3, 10): u"this machine, Python 3.10.0 -- the full suite, 2026-09-17",

    # ⭐ ADDED 2026-09-17 from the public repo's FIRST CI run,
    # github.com/SonicSandbox/hato/actions/runs/35312011707 -- 12 matrix jobs
    # across ubuntu/windows/macos x 3.10-3.13. The interpreter ran the suite on
    # each of these, which is exactly what the assertion below asks.
    #
    # ⚠ AND HERE IS WHAT THAT RUN DID NOT PROVE. It was RED. Every failure was
    # environment coupling, not a language difference: `tests/_media.py`
    # resolving the vault's bundled ffmpeg through a relative path meaningless
    # on a runner (18 of 22 per job), `py7zr` absent because the install step
    # named no extra, and this very register refusing an unrecorded
    # interpreter. ⛔ So these rows record "the suite EXECUTED here", which is
    # the claim the check below makes -- they do NOT record "hato works on
    # 3.11-3.13", and no classifier claims it either. The classifiers stay at
    # 3.10 until a GREEN run on each, which is the other direction of this
    # register and is deliberately a separate, later decision.
    (3, 11): u"CI run 35312011707, 2026-09-17 -- suite executed, run was red "
             u"on environment coupling only; ⛔ no classifier claims 3.11 yet",
    (3, 12): u"CI run 35312011707, 2026-09-17 -- suite executed, run was red "
             u"on environment coupling only; ⛔ no classifier claims 3.12 yet",
    (3, 13): u"CI run 35312011707, 2026-09-17 -- suite executed, run was red "
             u"on environment coupling only; ⛔ no classifier claims 3.13 yet",
}

#: Files the release needs that are NOT inside the package and therefore
#: cannot be reached by any package-data glob. name -> the written reason.
#: Checked from both ends, the way `doctor.CAPTURE_STEMS` is: a file named
#: here that HAS moved into the package turns this red, so the register can
#: only ever shrink.
LAUNCHER_GAP = {
    u"hato-run.cmd": (
        u"⭐ NOT A GAP ANY MORE -- RULED 2026-09-17. hato ships as a STANDALONE "
        u"run from a clone, with no wheel route at all, so the launcher living "
        u"at the repository root IS the design and no package-data glob needs "
        u"to reach it. ⛔ It must also STAY there: the launcher adds its own "
        u"folder to PYTHONPATH only when hato/__init__.py sits BESIDE it, so "
        u"moving it into the package would break the one path that works. "
        u"This entry is kept so the file cannot silently vanish."),
    u"hato-gui.cmd": (
        u"⭐ THE WINDOW'S LAUNCHER, and it lives beside hato-run.cmd for the "
        u"same ruled reason: hato is CLONED AND RUN, so the repository root is "
        u"where a launcher belongs and no package-data glob needs to reach it. "
        u"⛔ It must STAY there for a second reason of its own -- it puts its "
        u"own folder on PYTHONPATH so `-m hato.gui` resolves however the "
        u"shortcut was launched, and that only works while hato/__init__.py "
        u"sits beside it. ⚠ It differs from its sibling in exactly two ways, "
        u"both because it opens a window rather than printing: it uses "
        u"pythonw.exe, so no console sits behind the window for its lifetime, "
        u"and it never pauses, because there is no output to read. "
        u"Added 2026-09-18 with the desktop shortcut."),
}

#: Tokens that mean "nobody filled this in". The uppercase ones are matched
#: case-sensitively on purpose, so this file's own prose can discuss them.
PLACEHOLDERS_EXACT = (u"OWNER", u"TODO", u"FIXME", u"XXX", u"PLACEHOLDER",
                      u"CHANGEME", u"REPLACEME")
PLACEHOLDERS_ANY_CASE = (u"example.com", u"example.org", u"your-name",
                         u"yourname", u"your-repo", u"my-package")
#: `<anything>` on one line. `>=` and `python_version < '3.11'` do not match:
#: both halves of a pair are required.
ANGLE_PLACEHOLDER = re.compile(u"<[^<>\n]{1,40}>")

MIN_LICENCE_BYTES = 30000


# ---------------------------------------------------------------------------
# reading the declarations
# ---------------------------------------------------------------------------

def _pyproject():
    with io.open(PYPROJECT, u"rb") as fh:
        return _toml.load(fh)


def _text(path):
    with io.open(path, u"r", encoding=u"utf-8") as fh:
        return fh.read()


def _non_comment_text(text):
    u"""`pyproject.toml` with every comment removed.

    A trap discussed in a comment is not a published claim, so the dependency
    scans below run over this. Naive `#` splitting is correct here ONLY while
    no `#` sits inside a string, which is asserted as its own check.
    """
    return u"\n".join(line.split(u"#", 1)[0] for line in text.splitlines())


#: `tsubasa` as a REQUIREMENT -- the bare name followed by a version operator,
#: or quoted on its own. `tsubasa-sync` is excluded by the trailing guard.
#: ⛔ ONE COPY, used by the real check AND by the control that proves it can
#: fail. A second copy inside the control is how the control stayed green
#: while the check's own regex was replaced with one that matches nothing --
#: measured here on 2026-09-17, by breaking it.
_BARE_TSUBASA = re.compile(u"(?<![\\w.\\-])tsubasa(?![-\\w])\\s*[><=!~]")
_QUOTED_TSUBASA = re.compile(u"[\"']tsubasa[\"']")


def _bare_tsubasa_hits(text):
    body = _non_comment_text(text)
    return _BARE_TSUBASA.findall(body), _QUOTED_TSUBASA.findall(body)


def _requirements(cfg):
    u"""[(Requirement, where)] over dependencies AND every optional extra."""
    out = []
    project = cfg[u"project"]
    for raw in project.get(u"dependencies", []):
        out.append((Requirement(raw), u"dependencies"))
    for extra, items in (project.get(u"optional-dependencies") or {}).items():
        for raw in items:
            out.append((Requirement(raw), u"optional-dependencies[%s]" % extra))
    return out


def _hard_names(cfg):
    return set(canonicalize_name(Requirement(raw).name)
               for raw in cfg[u"project"].get(u"dependencies", []))


def _import_names_for(req):
    u"""The top-level modules a requirement provides -- and its extras'."""
    canon = canonicalize_name(req.name)
    names = set(PROVIDES[canon]) if canon in PROVIDES else {canon.replace(u"-", u"_")}
    for extra in req.extras:
        names |= set(EXTRA_PROVIDES.get((canon, extra), ()))
    return names


def _package_data_globs(cfg):
    u"""{package: [glob]} from [tool.setuptools.package-data], or {}."""
    return ((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
            .get(u"package-data") or {})


# ---------------------------------------------------------------------------
# deriving the truth from the source tree
# ---------------------------------------------------------------------------

def _py_files():
    for base, dirs, names in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != u"__pycache__"]
        for name in sorted(names):
            if name.endswith(u".py"):
                yield os.path.join(base, name)


def _guards(node, parents):
    u"""How this import is protected: (in_try_importerror, in_function, version_gated)."""
    in_try = in_func = versioned = False
    cur = node
    while id(cur) in parents:
        parent = parents[id(cur)]
        if isinstance(parent, ast.Try) and any(cur is s for s in parent.body):
            for handler in parent.handlers:
                name = u"" if handler.type is None else ast.dump(handler.type)
                if (handler.type is None or u"ImportError" in name
                        or u"ModuleNotFoundError" in name or u"'Exception'" in name
                        or u"id='Exception'" in name):
                    in_try = True
        elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            in_func = True
        elif isinstance(parent, ast.If) and u"version_info" in ast.dump(parent.test):
            versioned = True
        cur = parent
    return in_try, in_func, versioned


def _import_sites():
    u"""{top-level module: [site]} for every import anywhere under hato/.

    ast, not grep: a comment, a docstring or a string mentioning a module name
    is not an import, and an import inside a function is exactly the thing the
    optional/hard distinction turns on.
    """
    sites = {}
    for path in _py_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, u"/")
        with io.open(path, u"r", encoding=u"utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = [alias.name.split(u".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue                        # relative: hato itself
                tops = [(node.module or u"").split(u".")[0]]
            else:
                continue
            in_try, in_func, versioned = _guards(node, parents)
            for top in tops:
                sites.setdefault(top, []).append({
                    u"file": rel, u"line": node.lineno, u"try": in_try,
                    u"func": in_func, u"versioned": versioned})
    return sites


def _third_party_sites():
    stdlib = set(getattr(sys, u"stdlib_module_names", ()))
    assert stdlib, u"sys.stdlib_module_names is empty, so nothing can be classified"
    out = {}
    for name, sites in _import_sites().items():
        if name == u"hato" or name in stdlib:
            continue
        out[name] = sites
    return out


def _non_py_files_under(root):
    u"""Every non-.py file inside a package directory, relative to it.

    Takes a root so the coverage logic below can be pointed at a synthetic
    package and PROVEN able to fail -- hato carries no data files today, and a
    check that only ever runs against an empty set is worth nothing.
    """
    found = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != u"__pycache__"]
        for name in sorted(names):
            if not name.endswith(u".py"):
                rel = os.path.relpath(os.path.join(base, name), root)
                found.append(rel.replace(os.sep, u"/"))
    return found


def _non_py_files_in_package():
    return _non_py_files_under(PKG)


def _uncovered(found, globs):
    u"""Which of `found` no package-data glob reaches."""
    patterns = list(globs.get(u"hato", [])) + list(globs.get(u"*", []))
    return [rel for rel in found
            if not any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)]


def _globs_matching_nothing(found, globs):
    u"""Which declared globs reach no file at all."""
    empty = []
    for package, patterns in sorted(globs.items()):
        for pattern in patterns:
            if not any(fnmatch.fnmatch(rel, pattern) for rel in found):
                empty.append(u"%s: %s" % (package, pattern))
    return empty


def _packages_in_tree():
    u"""Every importable package under the repo root, derived from __init__.py."""
    out = []
    for base, dirs, names in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != u"__pycache__"]
        if u"__init__.py" in names:
            rel = os.path.relpath(base, ROOT).replace(os.sep, u".")
            out.append(rel)
    return sorted(out)


def _floor(cfg):
    u"""The (major, minor) requires-python claims as its lowest member."""
    spec = cfg[u"project"][u"requires-python"]
    found = re.findall(u">=\\s*(\\d+)\\.(\\d+)", spec)
    assert len(found) == 1, (
        u"requires-python is %r and this check can only read a single '>=' floor "
        u"-- teach it the new form before changing the declaration" % spec)
    return (int(found[0][0]), int(found[0][1]))


def _classifier_pythons(cfg):
    out = set()
    for line in cfg[u"project"].get(u"classifiers", []):
        hit = re.match(u"^Programming Language :: Python :: (\\d+)\\.(\\d+)$", line)
        if hit:
            out.add((int(hit.group(1)), int(hit.group(2))))
    return out


# ===========================================================================
# 1 -- it parses, and it is the name that was checked
# ===========================================================================

def test_pyproject_parses_and_the_distribution_is_named_hato():
    u"""The name is the one thing a rename reaches everywhere EXCEPT.

    P1: the rename went into the README and the release workflow and not into
    `name`, so an install under the intended name failed with *"inconsistent
    name"* -- and a tag would have tried to publish the wrong project.
    """
    assert os.path.isfile(PYPROJECT), u"there is no pyproject.toml at %s" % PYPROJECT
    cfg = _pyproject()
    assert u"project" in cfg, u"pyproject.toml has no [project] table"
    got = cfg[u"project"].get(u"name")
    assert got == u"hato", (
        u"[project] name is %r, not 'hato' -- the distribution name is what pip "
        u"installs and what a trusted publisher is configured for" % (got,))


def test_build_system_names_a_real_backend():
    u"""Without [build-system] a build falls back to legacy setuptools
    behaviour, which reads none of the tables below."""
    cfg = _pyproject()
    bs = cfg.get(u"build-system") or {}
    assert bs.get(u"build-backend") == u"setuptools.build_meta", (
        u"build-backend is %r -- every [tool.setuptools] table in this file is "
        u"read by that backend and by nothing else" % (bs.get(u"build-backend"),))
    assert any(u"setuptools" in item for item in bs.get(u"requires", [])), (
        u"[build-system] requires is %r and names no setuptools"
        % (bs.get(u"requires"),))


# ===========================================================================
# 2 -- ONE source of truth for the version
# ===========================================================================

def test_the_version_is_DYNAMIC_and_resolves_to_hato___version__():
    u"""Two places holding one version is one you can bump and leave stale,
    and the release proof rests on the live artifact's version equalling the
    local one. RUNBOOK step 6 stamps `hato/__init__.py` from a content hash."""
    cfg = _pyproject()
    project = cfg[u"project"]
    assert u"version" not in project, (
        u"[project] version is written statically as %r AND the stamper writes "
        u"hato/__init__.py -- one of the two will go stale"
        % (project.get(u"version"),))
    assert u"version" in project.get(u"dynamic", []), (
        u"[project] declares neither a static version nor dynamic = ['version']")

    attr = (((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
             .get(u"dynamic") or {}).get(u"version") or {}).get(u"attr")
    assert attr == u"hato.__version__", (
        u"[tool.setuptools.dynamic] version.attr is %r, not 'hato.__version__' "
        u"-- that attribute is the single source RUNBOOK step 6 stamps" % (attr,))

    import hato
    Version(hato.__version__)           # raises InvalidVersion if unusable
    assert hato.__version__.strip(), u"hato.__version__ is empty"


# ===========================================================================
# 3 -- THE CHECK THAT MATTERS: the dependency list is TRUE, not remembered
# ===========================================================================

def test_every_third_party_import_under_hato_is_DECLARED():
    u"""What makes the dependency list true rather than remembered.

    spec/01-scope.md's list was written before the code and is wrong three
    ways: it names `httpx` where the built client imports `requests`, and it
    names `anitopy` and `guessit` as hato's own (LEDGER-HOT.md forbids a second
    filename parser here -- they arrive through the engine's own `parsing`
    extra). ⚠ Since 2026-09-22 `hato doctor` imports both, to ask each to
    number a name (D1): declared through that extra, `EXTRA_PROVIDES`.

    Walked with ast, so a module name in a comment or a docstring is not
    mistaken for an import.
    """
    cfg = _pyproject()
    reqs = _requirements(cfg)
    declared = set()
    for req, _where in reqs:
        declared |= _import_names_for(req)
    for (dist, extra), _names in EXTRA_PROVIDES.items():
        assert any(canonicalize_name(req.name) == dist and extra in req.extras
                   for req, _where in reqs), (
            u"EXTRA_PROVIDES names %s[%s], which pyproject.toml no longer declares -- "
            u"the modules it lists are not installed by anything" % (dist, extra))
    via_extras = set(n for names in EXTRA_PROVIDES.values() for n in names)

    sites = _third_party_sites()
    assert sites, (
        u"no third-party imports were found anywhere under hato/, which cannot "
        u"be true -- the ast walk or the stdlib classification is broken")

    missing = []
    for name in sorted(sites):
        if name in declared or name in STDLIB_FROM:
            continue
        first = sites[name][0]
        missing.append(u"%s (%s:%d)" % (name, first[u"file"], first[u"line"]))
    assert not missing, (
        u"imported under hato/ and declared nowhere in pyproject.toml: %s -- "
        u"add each to [project] dependencies, or to an optional extra if every "
        u"import of it is guarded (%d third-party modules seen in total)"
        % (u", ".join(missing), len(sites)))

    unused = sorted(name for name in declared
                    if name not in sites and name not in STDLIB_FROM
                    and name not in via_extras)
    assert not unused, (
        u"declared in pyproject.toml and imported nowhere under hato/: %s -- a "
        u"dependency the code does not use is as wrong as a missing one"
        % (u", ".join(unused),))


def test_a_module_that_is_STDLIB_LATER_is_version_gated_and_not_declared():
    u"""`tomllib` is stdlib from 3.11 and does not exist at the floor, so it
    can neither be declared nor imported unconditionally. hato/config.py holds
    exactly that branch, and `tomli` carries the matching marker."""
    sites = _third_party_sites()
    for name, since in STDLIB_FROM.items():
        found = sites.get(name)
        if not found:
            continue
        for site in found:
            assert site[u"versioned"] or site[u"try"], (
                u"%s is stdlib only from Python %d.%d and is imported at %s:%d "
                u"with no sys.version_info test around it"
                % (name, since[0], since[1], site[u"file"], site[u"line"]))


def test_anything_declared_ONLY_as_an_extra_is_never_imported_at_module_level():
    u"""The claim an extra makes is *the package installs and imports without
    it*. One unguarded top-level import breaks that for every install, and
    nothing in a build would say so.

    Both of hato's optional packages ARE installed on this machine, so no
    import blocker here could prove anything -- pitfall P13 is a test that
    "passed while blocking nothing". This asserts the source instead, which
    cannot be fooled by what happens to be on the machine.
    """
    cfg = _pyproject()
    hard = _hard_names(cfg)
    sites = _third_party_sites()

    extra_only = {}
    for req, where in _requirements(cfg):
        if where == u"dependencies":
            continue
        if canonicalize_name(req.name) in hard:
            continue
        for name in _import_names_for(req):
            extra_only[name] = where

    assert extra_only, (
        u"no optional extras are declared, so this check is vacuous -- delete "
        u"it or restore the extra it guards")

    for name, where in sorted(extra_only.items()):
        found = sites.get(name) or []
        assert found, (
            u"%s is declared in %s and imported nowhere under hato/"
            % (name, where))
        bare = [u"%s:%d" % (s[u"file"], s[u"line"]) for s in found
                if not (s[u"try"] or s[u"func"])]
        assert not bare, (
            u"%s is only in %s, so it may be absent -- but it is imported at "
            u"module top level at %s, which breaks `import hato` for every "
            u"install without the extra" % (name, where, u", ".join(bare)))

        # PER FILE, not once across the whole package. Measured 2026-09-17:
        # a single `guarded` list over every site made this a coin flip --
        # stripping archives.py's try/except left doctor.py's satisfying the
        # check, so the module that must degrade no longer did and nothing
        # said so. Each module that reaches for an absent package handles its
        # absence itself.
        by_file = {}
        for site in found:
            by_file.setdefault(site[u"file"], []).append(site)
        unhandled = sorted(path for path, sites in by_file.items()
                           if not any(s[u"try"] for s in sites))
        assert not unhandled, (
            u"%s is optional, so it may be absent -- but %s import(s) it with "
            u"no try/except ImportError anywhere in the file, so a user there "
            u"gets a bare ImportError instead of the named skip"
            % (name, u", ".join(unhandled)))


# ===========================================================================
# 4 -- an entry point is only a string, and building never imports it
# ===========================================================================

def test_every_declared_script_target_IMPORTS_and_has_its_attribute():
    u"""P4: the reference project shipped `tsubasa-gui` pointing at a module
    that did not exist. It was caught by a human reading the file, and its
    guard is recorded there as open. This is that guard."""
    cfg = _pyproject()
    project = cfg[u"project"]
    targets = {}
    for table in (u"scripts", u"gui-scripts"):
        for command, target in (project.get(table) or {}).items():
            targets[u"%s (%s)" % (command, table)] = target
    assert targets, u"[project.scripts] declares no console script at all"

    for label, target in sorted(targets.items()):
        assert u":" in target, (
            u"%s points at %r, which has no 'module:attr' colon" % (label, target))
        module_name, _, attr = target.partition(u":")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise AssertionError(
                u"%s points at %r and importing %s raised %s: %s -- pip writes "
                u"this string into a launcher without ever importing it"
                % (label, target, module_name, type(exc).__name__, exc))
        fn = getattr(module, attr, None)
        assert callable(fn), (
            u"%s points at %r but %s.%s is %r, not something callable"
            % (label, target, module_name, attr, fn))


# ===========================================================================
# 5 -- the engine is `tsubasa-sync`; a bare `tsubasa` is SOMEBODY ELSE
# ===========================================================================

def test_the_engine_is_tsubasa_sync_and_never_the_unrelated_tsubasa():
    u"""`tsubasa` on PyPI is an unrelated AI-personas framework. Declared as
    written in the spec's first draft, hato would have installed somebody
    else's package and failed on its first `import tsubasa` -- or worse, not
    failed. The floor is 0.1.8: the first release reading `.jp.` as Japanese,
    which the present-check relies on (RUNBOOK 9c)."""
    cfg = _pyproject()
    reqs = _requirements(cfg)

    engine = [r for r, _ in reqs if canonicalize_name(r.name) == u"tsubasa-sync"]
    assert len(engine) == 1, (
        u"expected exactly one tsubasa-sync requirement, found %d in %r"
        % (len(engine), [str(r) for r, _ in reqs]))
    req = engine[0]

    # 🚨 THE FLOOR IS 0.1.8 (RUNBOOK 9c, 2026-09-23), AND IT IS A CAPABILITY:
    # the first release reading `.jp.` as Japanese, which the present-check now
    # relies on (`test_existing`'s `.jp` check). 0.1.7 would read a user's
    # `.jp.srt` as no language and fetch beside it. ⚠ The reasons the older
    # floors mattered are kept below, so raising it did not delete them.
    assert req.specifier.contains(u"0.1.8", prereleases=True), (
        u"the engine requirement is %r, which does not admit 0.1.8" % str(req))
    assert not req.specifier.contains(u"0.1.7", prereleases=True), (
        u"the engine requirement is %r, which still admits 0.1.7 -- it reads "
        u"`.jp.` as no language, so hato would fetch beside a Japanese `.jp.srt` "
        u"(RUNBOOK 9c); see pyproject.toml's comment before lowering it" % str(req))
    assert not req.specifier.contains(u"0.1.5", prereleases=True), (
        u"the engine requirement is %r, which still admits 0.1.5" % str(req))
    assert not req.specifier.contains(u"0.1.4", prereleases=True), (
        u"the engine requirement is %r, which still admits 0.1.4 -- 0.1.4 "
        u"predates the display-name reader and cannot satisfy the present-check"
        % str(req))
    assert u"parsing" in req.extras, (
        u"the engine requirement is %r and asks for no 'parsing' extra -- "
        u"spec/01-scope.md ratifies anitopy primary with guessit as fallback, "
        u"and the parser lives in the engine" % str(req))

    wrong = [str(r) for r, _ in reqs if canonicalize_name(r.name) == u"tsubasa"]
    assert not wrong, (
        u"pyproject.toml declares a dependency on the distribution 'tsubasa': "
        u"%s -- that name on PyPI belongs to an unrelated project" % wrong)


def test_no_declaration_anywhere_in_the_file_names_a_bare_tsubasa():
    u"""The parsed check above only sees the two dependency tables. This one
    reads the whole file, so a requirement added under some future table
    cannot slip past -- comments excluded, because a trap discussed in a
    comment is not a published claim."""
    text = _text(PYPROJECT)

    inside_string = [
        i for i, line in enumerate(text.splitlines(), 1)
        if u"#" in line and (line[:line.find(u"#")].count(u'"') % 2
                             or line[:line.find(u"#")].count(u"'") % 2)]
    assert not inside_string, (
        u"a '#' sits inside a string on line(s) %s, so stripping comments by "
        u"'#' is no longer safe -- this check reads the file that way"
        % (inside_string,))

    operator_form, quoted_form = _bare_tsubasa_hits(text)
    assert not operator_form and not quoted_form, (
        u"a requirement on the bare name 'tsubasa' appears in pyproject.toml "
        u"(%r / %r) -- the distribution is 'tsubasa-sync'; 'tsubasa' is an "
        u"unrelated project on PyPI" % (operator_form, quoted_form))


# ===========================================================================
# 6 -- GPL-3.0, and a LICENSE that is the canonical text
# ===========================================================================

def test_the_licence_is_GPL_3_or_later_and_agrees_with_the_classifier():
    cfg = _pyproject()
    declared = cfg[u"project"].get(u"license")
    value = declared.get(u"text") if isinstance(declared, dict) else declared
    assert value == u"GPL-3.0-or-later", (
        u"[project] license is %r -- spec/01-scope.md ratifies GPL-3.0, which "
        u"is also what lets this project read Bazarr's and Sonarr's source"
        % (declared,))

    licence_classifiers = [c for c in cfg[u"project"].get(u"classifiers", [])
                           if c.startswith(u"License ::")]
    for line in licence_classifiers:
        assert u"GNU General Public License v3 or later" in line, (
            u"a licence classifier says %r while [project] license says %r"
            % (line, value))


def test_LICENSE_is_the_CANONICAL_GPL_3_text_and_not_a_transcription():
    u"""Fetched, never typed: GitHub's licences API served these 35,149 bytes
    and they are byte-identical to the engine's own copy (sha256
    3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986).

    A size floor plus the header is the check, not a byte comparison -- but a
    floor alone would pass on GPL-2 text with the title swapped, so the
    version line and a phrase only version 3 contains are asserted too.
    """
    assert os.path.isfile(LICENSE), (
        u"there is no LICENSE file at %s, and GPL-3.0 requires the notice to "
        u"travel with the work" % LICENSE)
    size = os.path.getsize(LICENSE)
    assert size >= MIN_LICENCE_BYTES, (
        u"LICENSE is %d bytes -- the canonical GPL-3.0 text is 35,149, so this "
        u"is a stub, a placeholder or a truncated copy" % size)

    body = _text(LICENSE)
    first = body.splitlines()[0]
    assert u"GNU GENERAL PUBLIC LICENSE" in first, (
        u"LICENSE does not open with the GPL title; its first line is %r"
        % (first[:80],))
    assert u"Version 3, 29 June 2007" in body, (
        u"LICENSE does not carry the version 3 line -- an earlier GPL, or an "
        u"edited header")
    assert u"13. Use with the GNU Affero General Public License" in body, (
        u"LICENSE has no section 13 Affero heading, which only version 3 "
        u"contains -- this is a different GNU licence, or an edited one")
    assert u"TERMS AND CONDITIONS" in body, (
        u"LICENSE has no TERMS AND CONDITIONS heading -- it is a summary, not "
        u"the licence")


def test_BOTH_notices_are_declared_as_licence_files_so_they_SHIP():
    u"""MEASURED, and it is why this check exists: setuptools' default for
    `license-files` is LICEN[CS]E* / COPYING* / NOTICE* / AUTHORS*, anchored
    at the start of the name. `THIRD_PARTY_LICENSES.md` begins with THIRD and
    matches none of them, so on the default it would have been left out of
    every artifact while the repository looked complete -- and anitopy's
    MPL-2.0 and guessit's LGPL-3.0 both oblige carrying it."""
    cfg = _pyproject()
    declared = ((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
                .get(u"license-files"))
    assert declared, (
        u"no license-files are declared, so the default globs apply and "
        u"THIRD_PARTY_LICENSES.md ships with nothing")
    for name in (os.path.basename(LICENSE), os.path.basename(NOTICES)):
        assert any(fnmatch.fnmatch(name, pattern) for pattern in declared), (
            u"%s matches none of the declared license-files %r, so it would "
            u"not travel with the artifact" % (name, declared))


# ===========================================================================
# 7 -- adding a dependency without its notice FAILS
# ===========================================================================

def test_THIRD_PARTY_LICENSES_names_every_declared_dependency():
    u"""Derived from pyproject.toml, so the two cannot drift. Extra names are
    checked too: `tsubasa-sync[parsing]` is how anitopy and guessit reach
    every install, and a reader has to be told that."""
    assert os.path.isfile(NOTICES), u"there is no THIRD_PARTY_LICENSES.md"
    body = _text(NOTICES).lower()
    cfg = _pyproject()

    missing = []
    for req, where in _requirements(cfg):
        canon = canonicalize_name(req.name)
        if canon not in body and req.name.lower() not in body:
            missing.append(u"%s (from %s)" % (req.name, where))
        for extra in sorted(req.extras):
            if extra.lower() not in body:
                missing.append(u"the '%s' extra of %s" % (extra, req.name))
    for extra in (cfg[u"project"].get(u"optional-dependencies") or {}):
        if extra.lower() not in body:
            missing.append(u"hato's own '%s' extra" % extra)

    assert not missing, (
        u"declared in pyproject.toml and not named in THIRD_PARTY_LICENSES.md: "
        u"%s -- every dependency's licence and obligation belongs there, and "
        u"the file ships with the artifact" % (u"; ".join(missing),))


def test_the_notices_state_the_subtitle_content_position():
    u"""The one licence question this project lives inside. Subtitle files on
    jimaku carry no stated licence; hato downloads them to the user's own
    machine at their request and redistributes none of them."""
    body = _text(NOTICES).lower()
    for phrase in (u"no stated licence", u"redistribut", u"jimaku"):
        assert phrase in body, (
            u"THIRD_PARTY_LICENSES.md never says %r -- the subtitle-content "
            u"position has to be written down where a redistributor looks"
            % phrase)


# ===========================================================================
# 8 -- P2: a placeholder is a published lie, and it cannot be edited later
# ===========================================================================

def test_nothing_in_pyproject_is_a_PLACEHOLDER():
    u"""P2: the reference project's first pyproject.toml carried a GitHub path
    whose owner segment was never filled in, and its recorded guard is
    *"manual grep only -- not automated"*. hato's public repository does not
    exist yet, so there is no urls table at all: an absent field is honest."""
    text = _text(PYPROJECT)

    hits = [token for token in PLACEHOLDERS_EXACT if token in text]
    hits += [token for token in PLACEHOLDERS_ANY_CASE
             if re.search(re.escape(token), text, re.I)]
    angles = ANGLE_PLACEHOLDER.findall(text)
    assert not hits and not angles, (
        u"pyproject.toml carries placeholder text %r%s -- uploaded metadata "
        u"cannot be edited, so it would stay on that version for ever"
        % (hits, u" and angle-bracket placeholder(s) %r" % (angles,) if angles else u""))


def test_any_declared_url_is_a_real_https_url():
    u"""There is no [project.urls] table today. When one is added, it must be
    real -- this is what stops the reference project's defect recurring, and
    it must not be vacuous while the table is absent, so the absence is
    asserted out loud rather than skipped."""
    cfg = _pyproject()
    urls = cfg[u"project"].get(u"urls") or {}
    if not urls:
        assert u"urls" not in cfg[u"project"], (
            u"[project.urls] exists and is empty, which publishes nothing and "
            u"says nothing -- remove it or fill it in")
        return
    for label, value in sorted(urls.items()):
        assert value.startswith(u"https://"), (
            u"[project.urls] %s is %r, which is not an https URL" % (label, value))
        assert not ANGLE_PLACEHOLDER.search(value), (
            u"[project.urls] %s is %r and still holds a placeholder" % (label, value))
        assert not any(token in value for token in PLACEHOLDERS_EXACT), (
            u"[project.urls] %s is %r and still holds a placeholder" % (label, value))


# ===========================================================================
# 9 -- P7: a wheel missing its data installs, imports and runs with no error
# ===========================================================================

def test_package_data_covers_every_non_py_file_the_PACKAGE_carries():
    u"""Derived by walking hato/, never a remembered list.

    P7: the loaders fail open, so a wheel built without its data installs
    cleanly, imports cleanly, runs cleanly and is quietly wrong. hato carries
    NO data files at all right now -- and a check that passes on an empty set
    is worth nothing unless the denominator is visible, so it is printed.
    """
    found = _non_py_files_in_package()
    globs = _package_data_globs(_pyproject())
    print(u"non-.py files inside hato/: %d %s" % (len(found), found))

    uncovered = _uncovered(found, globs)
    assert not uncovered, (
        u"inside hato/ and matched by no package-data glob: %s -- the wheel "
        u"would install, import and run without them, raising nothing "
        u"(%d non-.py file(s) in the package, globs %r)"
        % (uncovered, len(found), globs))


def test_every_package_data_glob_MATCHES_something():
    u"""A glob for a file that is not there ships nothing and raises nothing,
    which is P7 arriving from the other direction."""
    globs = _package_data_globs(_pyproject())
    found = _non_py_files_in_package()
    empty = _globs_matching_nothing(found, globs)
    assert not empty, (
        u"package-data glob(s) %s match no file under hato/ -- setuptools "
        u"ignores an empty glob silently, so the wheel simply lacks them"
        % (empty,))


def test_the_package_data_COVERAGE_LOGIC_can_actually_fail():
    u"""hato carries no data files, so both checks above pass on an empty set
    today -- which is exactly the shape of a green check that blocks nothing.

    So the mechanism is pointed at a synthetic package instead, in a temp dir:
    one file a glob reaches, one it does not, and one glob that reaches
    nothing. If the first of these three assertions ever stops holding, the
    two checks above are vacuous in both senses.
    """
    import tempfile

    fake = tempfile.mkdtemp(prefix=u"hato-r3-pkgdata-")
    os.makedirs(os.path.join(fake, u"data"))
    for rel in (u"data/table.tsv", u"data/vocab.json"):
        with io.open(os.path.join(fake, rel.replace(u"/", os.sep)),
                     u"w", encoding=u"utf-8") as fh:
            fh.write(u"x")
    found = _non_py_files_under(fake)
    assert sorted(found) == [u"data/table.tsv", u"data/vocab.json"], found

    assert _uncovered(found, {u"hato": [u"data/*.json"]}) == [u"data/table.tsv"], (
        u"the coverage logic did not notice a data file no glob reaches, so "
        u"the package-data check above cannot fail")
    assert _uncovered(found, {u"hato": [u"data/*"]}) == [], (
        u"the coverage logic reports a covered file as uncovered")
    assert _globs_matching_nothing(found, {u"hato": [u"data/*.png"]}) == [
        u"hato: data/*.png"], (
        u"the empty-glob logic did not notice a glob matching nothing")


def test_the_windows_launcher_is_INSIDE_the_package_or_in_the_written_register():
    u"""spec/10-deployment.md: `hato-run.cmd` *"ships INSIDE the wheel and is
    copied to a user-chosen location on first run"*. It sits at the repository
    root, which no package-data glob can reach, and moving it was not this
    step's territory -- so the gap is a named register rather than a silence.

    Checked from both ends, the way `doctor.CAPTURE_STEMS` is: the moment the
    file moves into the package, the register entry turns this red, so it can
    only ever shrink.
    """
    globs = _package_data_globs(_pyproject())
    inside = set(_non_py_files_in_package())

    at_root = sorted(name for name in os.listdir(ROOT)
                     if name.lower().endswith(u".cmd"))
    for name in at_root:
        assert name in LAUNCHER_GAP, (
            u"%s sits at the repository root, cannot be reached by any "
            u"package-data glob, and is not in this suite's written register "
            u"-- say in one line why it lives there and whether anything is "
            u"supposed to carry it" % name)

    for name, reason in sorted(LAUNCHER_GAP.items()):
        assert reason.strip(), u"%s is in the register with no reason" % name
        if name in inside or (u"hato/" + name) in inside:
            patterns = list(globs.get(u"hato", [])) + list(globs.get(u"*", []))
            assert any(fnmatch.fnmatch(name, p) for p in patterns), (
                u"%s has moved inside hato/ but is still in this suite's gap "
                u"register and still absent from package-data -- add the glob "
                u"and delete the register entry" % name)
            raise AssertionError(
                u"%s now lives inside the package, so its gap register entry "
                u"is stale -- delete it" % name)
        assert os.path.isfile(os.path.join(ROOT, name)), (
            u"%s is in the gap register and does not exist at the repository "
            u"root either -- the register names a file nothing has" % name)


# ===========================================================================
# 10 -- P6: THE WORST ONE. The dev config must not ship
# ===========================================================================

def test_hato_config_json_is_EXCLUDED_from_the_distribution():
    u"""P6, and every check was green because every check ran inside a
    checkout. The reference project shipped its development config in 0.1.0;
    `cache_root()` found it and the headline call raised `ConfigError` for
    every `pip install` user. The version was yanked.

    hato's equivalent is `hato.config.json`, and `paths.find_project_config()`
    walks UP from the package looking for it. It is asserted BY NAME.
    """
    name = u"hato.config.json"
    at_root = os.path.join(ROOT, name)
    assert os.path.isfile(at_root), (
        u"%s is not at the repository root any more, so everything this check "
        u"claims about where it lives is stale" % name)
    assert not os.path.isfile(os.path.join(PKG, name)), (
        u"%s is inside hato/, where package data comes from -- it is the dev "
        u"config and it must never reach an installed package" % name)
    assert name not in _non_py_files_in_package(), (
        u"%s is somewhere inside the package tree" % name)

    globs = _package_data_globs(_pyproject())
    for package, patterns in sorted(globs.items()):
        for pattern in patterns:
            assert not fnmatch.fnmatch(name, pattern), (
                u"package-data %s: %r matches %s, which must never ship"
                % (package, pattern, name))

    setuptools_cfg = (_pyproject().get(u"tool", {}).get(u"setuptools", {}) or {})
    assert setuptools_cfg.get(u"include-package-data") is False, (
        u"include-package-data is %r -- with it on, what lands in the wheel "
        u"depends on which build-time plugins happen to be installed, so two "
        u"machines building this commit can ship different files"
        % (setuptools_cfg.get(u"include-package-data"),))

    manifest = os.path.join(ROOT, u"MANIFEST.in")
    if os.path.isfile(manifest):
        for line in _text(manifest).splitlines():
            bare = line.strip()
            assert not (bare.startswith(u"include") and name in bare), (
                u"MANIFEST.in line %r pulls %s into the sdist" % (bare, name))


def test_an_INSTALLED_package_finds_NO_project_config():
    u"""The behaviour behind the declaration above, and the half that shipped
    broken in the reference project. Driven against a tree this check builds
    itself, because a check that passes on state it did not create is not a
    check -- and with a POSITIVE CONTROL, since `None` from a walk that never
    walks would look identical.
    """
    import tempfile

    from hato import paths

    base = tempfile.mkdtemp(prefix=u"hato-r3-installed-")
    site = os.path.join(base, u"site-packages", u"hato")
    os.makedirs(site)

    assert paths.find_project_config(start=site) is None, (
        u"paths.find_project_config() found a project config above %s, where "
        u"nothing planted one -- an installed package would read a developer's "
        u"tree" % site)

    planted = os.path.join(base, u"hato.config.json")
    with io.open(planted, u"w", encoding=u"utf-8") as fh:
        fh.write(u'{"project": "positive control"}')
    found = paths.find_project_config(start=site)
    assert found is not None and os.path.samefile(str(found), planted), (
        u"the positive control failed: a hato.config.json two levels above %s "
        u"was not found, so the None above proves nothing about the walk"
        % site)


# ===========================================================================
# 11 -- P3: a classifier is a claim, and an open range claims the future
# ===========================================================================

def test_no_classifier_claims_a_PYTHON_THAT_NOTHING_HAS_RUN():
    u"""P3: the reference project's classifiers claimed 3.11 to 3.13 before
    any of them had run, and its own draft records the open top end as
    unresolved.

    Checked from both ends. Over-claiming fails; and the interpreter running
    this suite must be in the register, so a new runner forces the evidence to
    be written down instead of being quietly ignored.
    """
    cfg = _pyproject()
    floor = _floor(cfg)
    claimed = _classifier_pythons(cfg)

    assert claimed, (
        u"no 'Programming Language :: Python :: X.Y' classifier at all, so the "
        u"PyPI page says nothing about which Python this needs")
    assert min(claimed) == floor, (
        u"requires-python's floor is %d.%d and the lowest classifier is %d.%d "
        u"-- the two are read by different tools and must agree"
        % (floor[0], floor[1], min(claimed)[0], min(claimed)[1]))

    over = sorted(v for v in claimed if v not in PROVEN_PYTHONS)
    assert not over, (
        u"classifiers claim Python %s and nothing has run %s -- add a row to "
        u"PROVEN_PYTHONS with the evidence, or drop the classifier"
        % (u", ".join(u"%d.%d" % v for v in over),
           u"them" if len(over) > 1 else u"it"))

    running = sys.version_info[:2]
    assert running in PROVEN_PYTHONS, (
        u"this suite is running on Python %d.%d, which is not in "
        u"PROVEN_PYTHONS -- record it with the evidence, and add the matching "
        u"classifier now that a run proves it" % running)

    below = sorted(v for v in PROVEN_PYTHONS if v < floor)
    assert not below, (
        u"PROVEN_PYTHONS names %s, below requires-python's floor of %d.%d"
        % (u", ".join(u"%d.%d" % v for v in below), floor[0], floor[1]))


def test_the_wheel_would_carry_hato_AND_every_subpackage():
    u"""`hato/commands/` is loaded by importlib from cli.py's COMMANDS table.
    A narrower packages pattern would build a wheel that installs and imports
    cleanly and then fails on the first subcommand -- for installed users
    only, and never in a checkout."""
    cfg = _pyproject()
    find = ((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
            .get(u"packages") or {}).get(u"find")
    explicit = ((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
                .get(u"packages"))
    patterns = list((find or {}).get(u"include") or [])
    if isinstance(explicit, list):
        patterns = list(explicit)
    assert patterns, (
        u"neither [tool.setuptools.packages.find] include nor an explicit "
        u"packages list is declared, so what the wheel holds is whatever "
        u"setuptools auto-discovery guesses in a flat layout")

    packages = _packages_in_tree()
    assert u"hato" in packages and len(packages) > 1, (
        u"only %r were found under hato/, so this check has nothing to prove"
        % (packages,))
    missed = [name for name in packages
              if not any(fnmatch.fnmatch(name, p) for p in patterns)]
    assert not missed, (
        u"package(s) %s exist on disk and match none of %r, so they would be "
        u"left out of the wheel while every check in a checkout stayed green"
        % (missed, patterns))


def test_every_PATH_pyproject_names_actually_exists():
    u"""A readme or licence pointing at a missing file fails the build, and
    the README IS the PyPI project page, frozen per version. There is no
    README.md in this tree yet, so no readme field is declared."""
    cfg = _pyproject()
    project = cfg[u"project"]

    readme = project.get(u"readme")
    if readme:
        name = readme if isinstance(readme, str) else readme.get(u"file")
        if name:
            assert os.path.isfile(os.path.join(ROOT, name)), (
                u"[project] readme names %r and there is no such file" % name)

    declared = project.get(u"license")
    if isinstance(declared, dict) and declared.get(u"file"):
        assert os.path.isfile(os.path.join(ROOT, declared[u"file"])), (
            u"[project] license.file names %r and there is no such file"
            % declared[u"file"])

    for pattern in (((cfg.get(u"tool", {}).get(u"setuptools", {}) or {})
                     .get(u"license-files")) or []):
        matches = [name for name in os.listdir(ROOT)
                   if fnmatch.fnmatch(name, pattern)]
        assert matches, (
            u"license-files pattern %r matches nothing at the repository root"
            % pattern)


# ===========================================================================
# the instruments this file rests on -- proven before they are trusted
# ===========================================================================

def test_the_requirement_reader_and_the_comment_stripper_actually_WORK():
    u"""Every check above rests on two instruments, and a silent instrument
    produces a green suite that blocks nothing (P13, P15).

    So each is pointed at an answer already known: one string it must parse
    exactly, one line it must flag, and one line it must NOT flag.
    """
    req = Requirement(u"tsubasa-sync[parsing]>=0.1.5")
    assert canonicalize_name(req.name) == u"tsubasa-sync"
    assert req.extras == {u"parsing"}
    assert req.specifier.contains(u"0.1.5") and not req.specifier.contains(u"0.1.4")

    marked = Requirement(u"tomli>=1.1; python_version < '3.11'")
    assert marked.marker is not None, (
        u"the requirement reader dropped an environment marker, so a "
        u"version-specific dependency would read as unconditional")

    # ⛔ THE SAME FUNCTION the real check calls -- not a second copy of its
    # regex. Measured 2026-09-17: with a copy here, replacing the real regex
    # with one that matches nothing left BOTH green, because a file with no
    # bare requirement looks identical to a scanner that cannot see one.
    assert _bare_tsubasa_hits(u'dependencies = ["tsubasa>=0.1"]')[0] == [u"tsubasa>"], (
        u"the bare-tsubasa scan does not flag a real bare requirement, so the "
        u"check built on it can never fail")
    assert _bare_tsubasa_hits(u'dependencies = ["tsubasa"]')[1] == [u'"tsubasa"'], (
        u"the bare-tsubasa scan does not flag an unpinned bare requirement")
    assert _bare_tsubasa_hits(
        u'dependencies = ["x"]  # tsubasa>=0.1 was the trap') == ([], []), (
        u"the bare-tsubasa scan flags a comment, so discussing the trap in "
        u"this file would turn the check red for the wrong reason")
    assert _bare_tsubasa_hits(
        u'dependencies = ["tsubasa-sync[parsing]>=0.1.5"]') == ([], []), (
        u"the bare-tsubasa scan flags the CORRECT distribution name")


def test_the_import_walk_sees_the_imports_that_are_actually_there():
    u"""The dependency check is only worth what this walk is worth. Pointed at
    three facts read out of the source by hand on 2026-09-17."""
    sites = _third_party_sites()

    assert u"requests" in sites, (
        u"the ast walk found no `requests` import, and hato/client.py imports "
        u"it at module top level -- the walk is broken")
    top_level = [s for s in sites[u"requests"]
                 if s[u"file"] == u"hato/client.py" and not s[u"func"]]
    assert top_level, (
        u"the walk did not see requests imported at hato/client.py's top "
        u"level, so its unguarded/guarded distinction is not working")

    assert u"py7zr" in sites and all(s[u"try"] or s[u"func"]
                                     for s in sites[u"py7zr"]), (
        u"py7zr is imported unguarded somewhere, or the walk cannot see the "
        u"try/except around it -- sites: %r" % (sites.get(u"py7zr"),))

    assert u"httpx" not in sites, (
        u"hato imports httpx after all, which the dependency list does not "
        u"declare -- spec/01-scope.md left HTTP to the builder's choice and "
        u"the built client chose requests")


# ---------------------------------------------------------------------------
# 🚨 THE FROZEN BUILD -- RUNBOOK 7g
#
# ⛔ The three executable NAMES are a contract with code that already shipped.
# `gui/run.py::cli_argv`, `watch.py::watch_argv` and `watch.py::open_window`
# each build a sibling of `sys.executable` BY NAME when frozen. Rename one in
# the spec and nothing fails to build -- the bundle is produced, it launches,
# and the first spawn dies looking for a file that is not there.
#
# ⚠ These read the spec's SYNTAX TREE and compare it against what the real
# functions return, never against a second list written here.
# ---------------------------------------------------------------------------

PACKAGING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), u"packaging")
SPEC_PATH = os.path.join(PACKAGING_DIR, u"hato.spec")


def _spec_source():
    with io.open(SPEC_PATH, encoding=u"utf-8") as fh:
        return fh.read()


def _exe_names_from_spec():
    u"""Every `name=` handed to an `EXE(...)` in the spec. -> sorted [str]"""
    names = []
    for node in ast.walk(ast.parse(_spec_source())):
        if isinstance(node, ast.Call) and \
                getattr(node.func, u"id", None) == u"EXE":
            for keyword in node.keywords:
                if keyword.arg == u"name" and \
                        isinstance(keyword.value, ast.Constant):
                    names.append(keyword.value.value)
    return sorted(names)


def test_the_frozen_spec_and_its_three_entry_scripts_exist():
    assert os.path.isfile(SPEC_PATH), SPEC_PATH
    for script in (u"entry_cli.py", u"entry_gui.py", u"entry_watch.py"):
        assert os.path.isfile(os.path.join(PACKAGING_DIR, script)), script


def test_the_three_FROZEN_names_are_exactly_what_the_code_SPAWNS(tmp_path,
                                                                 monkeypatch):
    u"""🚨 THE CONTRACT, ROUND-TRIPPED THROUGH THE REAL FUNCTIONS.

    Not a list compared against a list: `sys.frozen` is faked, the three
    argv builders are CALLED, and their basenames must equal the names the
    spec actually builds.
    """
    from hato import watch
    from hato.gui import run as gui_run

    suffix = u".exe" if sys.platform.startswith(u"win") else u""
    bundle = tmp_path / u"bundle"
    bundle.mkdir()

    monkeypatch.delenv(u"HATO_CLI", raising=False)
    monkeypatch.setattr(sys, u"frozen", True, raising=False)
    monkeypatch.setattr(sys, u"executable", str(bundle / (u"hato-gui" + suffix)))

    spawned = []
    monkeypatch.setattr(watch.subprocess, u"Popen",
                        lambda argv, **kw: spawned.append(argv))
    watch.open_window()
    assert spawned, u"open_window spawned nothing"

    from hato import update
    from_code = set([
        os.path.basename(gui_run.cli_argv()[0]),      # hato.exe
        os.path.basename(watch.watch_argv()[0]),      # hato-watch.exe
        os.path.basename(spawned[0][0]),              # hato-gui.exe
        # ⭐ LAYER 11 -- the hand-off copies THIS name out of a staged release,
        # and an install refuses a release whose manifest lacks it.
        update.SWAPPER_NAME if suffix else update.SWAPPER_NAME[:-4],
    ])
    from_spec = set(name + suffix for name in _exe_names_from_spec())

    assert from_code == from_spec, (
        u"the spec builds %s but the code spawns %s -- a frozen bundle would "
        u"launch and then fail at the first spawn"
        % (sorted(from_spec), sorted(from_code)))


def test_the_spec_DERIVES_the_dynamic_command_table_rather_than_copying_it():
    u"""🚨 THE ONE THAT WOULD HAVE SHIPPED EVERY SUBCOMMAND DEAD.

    `hato/cli.py` imports each command through `importlib.import_module` from
    a dict, which PyInstaller's static analysis cannot see. ⛔ A hand-written
    copy of that list in the spec is a second thing to keep in step, and when
    it drifts the failure is silent until somebody runs that one command.
    """
    source = _spec_source()
    assert u"from hato.cli import COMMANDS" in source, \
        u"the spec must read the dispatch table, not restate it"
    assert u"COMMANDS.values()" in source

    from hato.cli import COMMANDS
    copied = sorted(module for module in COMMANDS.values()
                    if (u'"%s"' % module) in source or (u"'%s'" % module) in source)
    assert copied == [], (
        u"the spec hard-codes %s -- derive them from COMMANDS instead, or a "
        u"command added later freezes dead" % copied)


@pytest.mark.parametrize(u"script,module", [
    (u"entry_cli.py", u"hato.cli"),
    (u"entry_gui.py", u"hato.gui"),
    (u"entry_watch.py", u"hato.watch"),
])
def test_each_frozen_entry_point_is_a_ONE_LINER_over_main(script, module):
    u"""⛔ A frozen entry point that grew its own behaviour is a second answer
    to every question `hato/__main__.py` already answers -- and it is the copy
    nobody runs during development, so it drifts unnoticed."""
    with io.open(os.path.join(PACKAGING_DIR, script), encoding=u"utf-8") as fh:
        tree = ast.parse(fh.read())

    imported = [(node.module, tuple(a.name for a in node.names))
                for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert (module, (u"main",)) in imported, \
        u"%s must import main from %s, got %s" % (script, module, imported)

    defined = [node.name for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    assert defined == [], \
        u"%s defines %s -- it must stay a one-liner" % (script, defined)

    assert u"sys.exit(main())" in ast.unparse(tree), (
        u"%s must exit with main()'s code: a frozen bundle whose entry point "
        u"returns None exits 0 no matter what happened" % script)


def test_Qt_is_EXCLUDED_from_the_CLI_and_the_WATCHER_but_not_the_window():
    u"""🚨 THE 13.4-vs-30.6 MB ARGUMENT, EXPRESSED AS A BUILD.

    `hato/watch.py` is a separate process for one measured reason. ⛔ If Qt
    reaches the watcher's or the CLI's analysis, the saving is gone and the
    third executable is pure cost -- and nothing else in this project would
    notice, because the bundle still builds and still runs.
    """
    tree = ast.parse(_spec_source())
    chosen = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not (isinstance(value, ast.Call)
                and getattr(value.func, u"id", None) == u"_analysis"):
            continue
        script = value.args[0].value
        chosen[script] = getattr(value.args[1], u"id", None)

    assert chosen.get(u"entry_cli.py") == u"NO_QT", chosen
    assert chosen.get(u"entry_watch.py") == u"NO_QT", chosen
    assert chosen.get(u"entry_gui.py") == u"EXCLUDE", chosen
    assert u'NO_QT = EXCLUDE + ["PyQt6"]' in _spec_source()


def _call_assigned(name):
    u"""The Call assigned to `name` in the spec. -> ast.Call"""
    for node in ast.walk(ast.parse(_spec_source())):
        if isinstance(node, ast.Assign) and any(
                getattr(t, u"id", None) == name for t in node.targets):
            return node.value
    raise AssertionError(u"the spec assigns no %s" % name)


def test_the_swapper_is_ONEFILE_and_carries_nothing_of_the_other_three():
    u"""⭐ LAYER 11 -- `hato-update.exe` runs from OUTSIDE the program folder while
    that folder is renamed away, so it must carry its own runtime (onefile: its
    binaries and data go INTO the exe, no `exclude_binaries`) and nothing the
    others need -- starting with the library API `hato/__init__.py` wires lazily.
    ⛔ And it lands in the program folder only AFTER the COLLECT, which clears it."""
    exe = _call_assigned(u"update_exe")
    keywords = dict((k.arg, k.value) for k in exe.keywords)
    assert u"exclude_binaries" not in keywords, u"the swapper would lean on _internal"
    assert ast.unparse(exe.args[2]) == u"update.binaries", ast.unparse(exe.args[2])
    assert getattr(keywords[u"console"], u"value", None) is False
    analysis = _call_assigned(u"update")
    assert ast.unparse(analysis.args[0]).endswith(u"'entry_update.py')]")
    source = _spec_source()
    for heavy in (u"hato.api", u"tsubasa", u"numpy", u"requests", u"Cryptodome"):
        assert u'"%s"' % heavy in source.split(u"SWAPPER_EXCLUDE")[1], heavy
    assert source.index(u"coll = COLLECT(") < source.index(u'"hato", "hato-update.exe")'), \
        u"the swapper is copied into the folder before the COLLECT clears it"


def test_zipping_an_unpacked_release_writes_every_name_once(tmp_path):
    u"""⚠ The rehearsal zips an UNPACKED release, which already holds the licence, the
    notices and the README -- and `build_zip` adds the repository's copies after the
    bundle's. Measured: `UserWarning: Duplicate name: 'hato/LICENSE'`. The repository's
    copy is the one that ships; the bundle's is skipped, and only at its top."""
    import importlib.util
    import zipfile
    loader = importlib.util.spec_from_file_location(
        u"hato_package_standalone", os.path.join(PACKAGING_DIR, u"package_standalone.py"))
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    bundle = tmp_path / u"hato"
    (bundle / u"_internal" / u"docs").mkdir(parents=True)
    (bundle / u"hato.exe").write_bytes(b"exe")
    for name in module.ALONGSIDE:
        (bundle / name).write_text(u"an old copy", encoding=u"utf-8")
    (bundle / u"_internal" / u"docs" / u"LICENSE").write_text(u"a package's own", encoding=u"utf-8")
    out = tmp_path / u"out.zip"
    module.build_zip(str(bundle), str(out))
    with zipfile.ZipFile(str(out)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), sorted(n for n in names if names.count(n) > 1)
        assert archive.read(u"hato/LICENSE") != b"an old copy", u"the bundle's copy shipped"
        assert u"hato/_internal/docs/LICENSE" in names, u"a package's own licence was dropped"


def test_the_swapper_carries_the_splashs_picture_of_hato():
    u"""⭐ The splash reads hato's mark beside `hato/splash.py` -- inside a onefile that
    is `_MEIPASS/hato/data`, and only if the spec PUT it there. Forgotten, the card
    draws with a hole where the mark belongs and nothing says so (the smoke's
    `--selftest` reads which mark the BUILT swapper found)."""
    analysis = _call_assigned(u"update")
    keywords = dict((k.arg, k.value) for k in analysis.keywords)
    assert ast.unparse(keywords[u"datas"]) == u"SPLASH_DATA", ast.unparse(keywords[u"datas"])
    collected = _call_assigned(u"SPLASH_DATA")
    assert ast.unparse(collected) == \
        u"collect_data_files('hato', includes=['data/hato-*.png'])", ast.unparse(collected)
    marks = [n for n in os.listdir(os.path.join(ROOT, u"hato", u"data"))
             if re.match(r"^hato-\d+\.png$", n)]
    assert marks, u"the control: hato/data holds no marks for the pattern to find"


def test_the_swappers_entry_imports_nothing_of_hato_but_the_swap_and_its_splash():
    with io.open(os.path.join(PACKAGING_DIR, u"entry_update.py"), encoding=u"utf-8") as fh:
        tree = ast.parse(fh.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(u"%s.%s" % (node.module, a.name) for a in node.names)
    assert u"hato.swap" in imported, u"the control: the walk found the swapper"
    ours = sorted(n for n in imported if n.startswith(u"hato"))
    assert set(ours) <= {u"hato.swap", u"hato.splash"}, ours


if __name__ == u"__main__":
    raise SystemExit(pytest.main([__file__, u"-q"]))
