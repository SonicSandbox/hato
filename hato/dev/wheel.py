# -*- coding: utf-8 -*-
"""
The wheel's manifest, claim by claim, BEFORE anything is published.

    python -m hato.dev audit-wheel dist/hato-*.whl

⭐ EVERY CLAIM HERE IS A PITFALL SOMEONE PAID FOR
(Development Doctrine/PYPI-PUBLISHING-DRAFT §3):

    metadata_name        P1. tsubasa's rename reached its README and its release
                         workflow and NOT `name`, so `pip install` failed with
                         "inconsistent name: expected 'tsubasa-sync', but metadata
                         has 'tsubasa'". ⭐ FOUND BY CHANCE, re-reading the file for
                         an unrelated question
    metadata_version     the wheel is built from the tree that was stamped -- a
                         wheel left in dist/ from before a re-stamp is stale
    version_matches_stamp  the same number a THIRD way (hato/dev/_stamp.json), so
                         one file being right is not the whole claim
    runtime_data         P7. "a wheel without its data would install, import and
                         run with no error" -- hato's loaders fail open too
    launcher             hato-run.cmd is at the REPOSITORY ROOT, where a
                         clone-and-run install needs it. ⚠ INVERTED 2026-09-17:
                         this used to assert it was inside the wheel, per a spec
                         line that was never implementable and that Sonic's
                         standalone ruling then retired. See the claim's comment
    gpl3_notice          spec/10-deployment.md §4.3 -- GPL-3.0 requires it
    dependency_licences  anitopy is MPL-2.0 and guessit is LGPL-3.0. Both require
                         their notices to be carried
    no_dev_config        🚨 P6, THE WORST IN THE CORPUS. tsubasa 0.1.0 shipped its
                         dev config in the wheel, `cache_root()` read it, and
                         `sync()` raised ConfigError for EVERY pip install user.
                         Every check was green because every check ran inside a
                         checkout
    no_strays            tests/, _runs/, __pycache__, .pytest_cache, *.egg-info,
                         mutbak, *.tmp
    record_matches_zip   the dist-info RECORD names exactly what the zip holds

⚠ THE EXPECTED DISTRIBUTION NAME IS DECLARED HERE, NOT READ FROM `pyproject.toml`.
That is the whole point of P1: METADATA's Name comes FROM pyproject.toml, so
comparing the two can never disagree. `DIST_NAME` below is the decision as
spec/10-deployment.md records it, and `--dist-name` is how a rename is carried.
"""
import argparse
import csv
import io
import posixpath
import re
import zipfile
from email.parser import Parser
from pathlib import Path

from hato.dev import claims, stamp
from hato.dev.claims import Fault, fail, ok, skip

#: The DECISION, from spec/10-deployment.md: `[project] name = "hato"`.
#: ⚠ The distribution name may differ from the import name -- tsubasa publishes
#: as `tsubasa-sync` and imports as `tsubasa`. hato's are the same.
DIST_NAME = "hato"

#: Non-`.py` files under `hato/` that deliberately do NOT ship, each with the
#: written reason. ⛔ Anything not listed here must be in the wheel (P7).
DATA_EXCUSED = {
    stamp.STAMP_REL: "release tooling's own record; the installed hato never reads it",
}

#: ⛔ Never in a published wheel. (label, pattern over the zip member name).
STRAY_PATTERNS = (
    ("tests/", re.compile(r"(^|/)tests/")),
    ("_runs/", re.compile(r"(^|/)_runs/")),
    ("__pycache__/", re.compile(r"(^|/)__pycache__/")),
    (".pytest_cache/", re.compile(r"(^|/)\.pytest_cache/")),
    ("*.egg-info", re.compile(r"\.egg-info(/|$)")),
    ("mutbak", re.compile(r"mutbak")),
    ("*.tmp", re.compile(r"\.tmp$")),
)

_DEV_CONFIG = "hato.config.json"
_LICENCE_NAME = re.compile(r"(^|/)(LICEN[SC]E|COPYING)([.\-][^/]*)?$", re.I)
_THIRD_PARTY = re.compile(r"(^|/)(THIRD[_\-.]?PARTY[_\-.]?LICEN[SC]ES?|NOTICE)"
                          r"([.\-][^/]*)?$", re.I)
_DIST_INFO_LICENCE = re.compile(r"\.dist-info/licen[sc]es?/", re.I)
_LAUNCHER = "hato-run.cmd"


def normalise(name):
    """PEP 503 name normalisation, so `Hato_Sync` and `hato-sync` compare equal."""
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def resolve_wheel(pattern):
    """A path, possibly with a `*` the shell did not expand. -> Path, or Fault.

    ⚠ The release block is written for bash, and PowerShell hands globs through
    unexpanded -- so `dist/hato-*.whl` must resolve here rather than landing as a
    literal filename nobody can open.
    """
    raw = str(pattern)
    if "*" in raw or "?" in raw:
        p = Path(raw)
        base = p.parent if str(p.parent) not in ("", ".") else Path(".")
        found = sorted(base.glob(p.name))
        if not found:
            raise Fault("no file matches %s" % raw)
        if len(found) > 1:
            raise Fault("%s matches %d files (%s) -- name the one to audit"
                        % (raw, len(found), ", ".join(f.name for f in found)))
        return found[0]
    path = Path(raw)
    if not path.is_file():
        raise Fault("no such file: %s" % path)
    return path


def open_wheel(path):
    """-> (zipfile.ZipFile, [names]). A wheel is a zip; anything else is a Fault."""
    try:
        zf = zipfile.ZipFile(str(path))
    except (zipfile.BadZipFile, OSError) as exc:
        raise Fault("%s is not a readable wheel: %s" % (path, exc))
    bad = zf.testzip()
    if bad is not None:
        zf.close()
        raise Fault("%s has a corrupt member: %s" % (path, bad))
    return zf, zf.namelist()


def metadata(zf, names):
    """The parsed `*.dist-info/METADATA`. -> (message, its member name)."""
    found = [n for n in names if re.match(r"^[^/]+\.dist-info/METADATA$", n)]
    if len(found) != 1:
        raise Fault("%d files match *.dist-info/METADATA -- expected exactly 1"
                    % len(found))
    text = zf.read(found[0]).decode("utf-8", "replace")
    return Parser().parsestr(text), found[0]


def record_names(zf, names):
    """The first column of `*.dist-info/RECORD`. -> (set, its member name)|(None, None)."""
    found = [n for n in names if re.match(r"^[^/]+\.dist-info/RECORD$", n)]
    if len(found) != 1:
        return None, None
    text = zf.read(found[0]).decode("utf-8", "replace")
    rows = csv.reader(io.StringIO(text))
    return set(r[0] for r in rows if r and r[0]), found[0]


def source_data_files(root):
    """Every non-`.py` file inside the SOURCE package. -> {posix rel: Path}

    ⭐ THE DENOMINATOR FOR `runtime_data`, DERIVED. A hand-written list of data
    files is a list that goes stale the first time someone adds one -- and the
    failure (P7) is silent, because the loaders fail open.
    """
    root = Path(root)
    out = {}
    for path in (root / stamp.PACKAGE).rglob("*"):
        if not path.is_file() or path.suffix in (".py",) + stamp.SKIP_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in stamp.SKIP_DIRS for part in rel.parts):
            continue
        out[rel.as_posix()] = path
    return out


def audit(path, root, dist_name=DIST_NAME):
    """-> [Claim] over the wheel at `path`."""
    zf, names = open_wheel(path)
    try:
        return _audit(zf, names, path, root, dist_name)
    finally:
        zf.close()


def _text(zf, name, limit=4 << 20):
    return zf.read(name)[:limit].decode("utf-8", "replace")


def _audit(zf, names, path, root, dist_name):
    out = []
    meta, meta_name = metadata(zf, names)

    got_name = meta.get("Name")
    if normalise(got_name) == normalise(dist_name):
        out.append(ok("metadata_name", "%s Name = %r" % (meta_name, got_name)))
    else:
        out.append(fail("metadata_name",
                        "the distribution is %r and %s says Name = %r -- `pip "
                        "install` refuses this with \"inconsistent name\" (pitfall P1)"
                        % (dist_name, meta_name, got_name)))

    got_version = meta.get("Version")
    source_version, source_path = claims.read_source_version(root)
    if got_version == source_version:
        out.append(ok("metadata_version", "%s Version = %r, and %s agrees"
                      % (meta_name, got_version, source_path.name)))
    else:
        out.append(fail("metadata_version",
                        "the wheel says Version = %r and hato/__init__.py says %r -- "
                        "this wheel was built from a different tree, or before the "
                        "stamp" % (got_version, source_version)))

    record = stamp.read_stamp(root)
    if record is None:
        out.append(skip("version_matches_stamp",
                        "no %s -- run `python -m hato.dev stamp` first"
                        % stamp.STAMP_REL))
    elif record.get("release") == got_version:
        out.append(ok("version_matches_stamp", "%s release = %r"
                      % (stamp.STAMP_REL, record.get("release"))))
    else:
        out.append(fail("version_matches_stamp",
                        "the wheel says %r and the stamp declares %r"
                        % (got_version, record.get("release"))))

    # -- runtime data (P7) --------------------------------------------------
    wanted = source_data_files(root)
    excused = dict((rel, why) for rel, why in DATA_EXCUSED.items() if rel in wanted)
    must_ship = sorted(set(wanted) - set(excused))
    inside = set(names)
    absent = [rel for rel in must_ship if rel not in inside]
    denominator = "%d of %d non-.py file(s) under %s/" % (
        len(must_ship) - len(absent), len(must_ship), stamp.PACKAGE)
    note = denominator + (
        "; %d excused (%s)" % (len(excused), ", ".join(sorted(excused))) if excused else "")
    if absent:
        out.append(fail("runtime_data",
                        "%s -- MISSING from the wheel: %s. A wheel without its data "
                        "installs, imports and runs with no error (pitfall P7)"
                        % (note, ", ".join(absent))))
    elif not must_ship:
        out.append(ok("runtime_data",
                      "0 non-.py files under %s/ -- there is no package data to "
                      "carry yet%s"
                      % (stamp.PACKAGE,
                         "; %d excused (%s)" % (len(excused), ", ".join(sorted(excused)))
                         if excused else "")))
    else:
        out.append(ok("runtime_data", note + " present"))

    # -- the launcher -------------------------------------------------------
    # 🚨 THIS CLAIM WAS INVERTED 2026-09-17, BY A RULING, AND THE OLD VERSION
    # WAS THE ONE THING THAT MADE THE FIRST PUBLIC CI RUN'S WHEEL JOB RED.
    #
    # It asserted `hato-run.cmd` was INSIDE the wheel, because
    # spec/10-deployment.md said it *"ships INSIDE it and is copied to a
    # user-chosen location on first run"*. ⛔ That line was never
    # implementable: `package-data` only reaches inside `hato/`, the launcher
    # is at the repository root, and MOVING it there would break the very
    # PYTHONPATH guard that makes it work -- the launcher adds its own folder
    # to the path only when `hato\__init__.py` sits BESIDE it, which is true
    # of a checkout and false of an installed copy. There was also never a
    # copy-out command in the CLI to do the second half.
    #
    # ⭐ Sonic ruled the question away: hato ships as a STANDALONE, run from a
    # clone, with no wheel route at all (spec/10-deployment.md §RULED). So the
    # launcher living at the repository root is not a gap -- it is the design,
    # and the root is exactly where the standalone path needs it.
    #
    # ⛔ The claim is kept rather than deleted, pointed at the thing that can
    # still go wrong: the launcher going MISSING. An absent check would let it
    # vanish silently, and it is the only user-facing artifact that is not a
    # Python entry point.
    in_wheel = [n for n in names if posixpath.basename(n) == _LAUNCHER]
    at_root = (root / _LAUNCHER).is_file()
    if not at_root:
        out.append(fail("launcher",
                        "%s is not at the repository root (%s). hato is run from a "
                        "clone (spec/10-deployment.md §RULED), and that launcher is "
                        "the only user-facing artifact that is not a Python entry "
                        "point -- without it there is no double-click path"
                        % (_LAUNCHER, root)))
    elif in_wheel:
        out.append(ok("launcher",
                      "%s at the repository root, and also in the wheel at %s -- "
                      "harmless, but the wheel is not the delivery route"
                      % (_LAUNCHER, ", ".join(in_wheel))))
    else:
        out.append(ok("launcher",
                      "%s at the repository root, where a clone-and-run install "
                      "needs it; deliberately NOT in the wheel (there is no wheel "
                      "route -- spec/10-deployment.md §RULED)" % _LAUNCHER))

    # -- the licences -------------------------------------------------------
    gpl = []
    for n in names:
        if _LICENCE_NAME.search(n) or _DIST_INFO_LICENCE.search(n):
            body = _text(zf, n).upper()
            if "GNU GENERAL PUBLIC LICENSE" in body and "VERSION 3" in body:
                gpl.append(n)
    if gpl:
        out.append(ok("gpl3_notice", "GPL-3.0 text in %s" % ", ".join(gpl)))
    else:
        out.append(fail("gpl3_notice",
                        "no member carries the GNU General Public License Version 3 "
                        "text (looked at %d licence-named members of %d)"
                        % (sum(1 for n in names if _LICENCE_NAME.search(n)
                               or _DIST_INFO_LICENCE.search(n)), len(names))))

    third = []
    for n in names:
        if _THIRD_PARTY.search(n) or _DIST_INFO_LICENCE.search(n):
            body = _text(zf, n).lower()
            if "anitopy" in body and "guessit" in body:
                third.append(n)
    if third:
        out.append(ok("dependency_licences",
                      "anitopy (MPL-2.0) and guessit (LGPL-3.0) both named in %s"
                      % ", ".join(third)))
    else:
        out.append(fail("dependency_licences",
                        "no member names both anitopy and guessit -- MPL-2.0 and "
                        "LGPL-3.0 each require their notice to be carried "
                        "(spec/10-deployment.md §4.3)"))

    # -- 🚨 P6, by name -----------------------------------------------------
    dev_config = [n for n in names if posixpath.basename(n) == _DEV_CONFIG]
    if dev_config:
        out.append(fail("no_dev_config",
                        "%s IS IN THE WHEEL at %s -- this is pitfall P6: tsubasa "
                        "0.1.0 shipped its dev config, the installed package read "
                        "it, and every pip install user got a ConfigError"
                        % (_DEV_CONFIG, ", ".join(dev_config))))
    else:
        out.append(ok("no_dev_config",
                      "no %s in %d members (pitfall P6)" % (_DEV_CONFIG, len(names))))

    # -- strays -------------------------------------------------------------
    hits = []
    for label, pattern in STRAY_PATTERNS:
        matched = [n for n in names if pattern.search(n)]
        if matched:
            hits.append("%s (%d, e.g. %s)" % (label, len(matched), matched[0]))
    if hits:
        out.append(fail("no_strays", "the wheel carries: " + "; ".join(hits)))
    else:
        out.append(ok("no_strays", "%d members, none matching any of the %d stray "
                                   "patterns" % (len(names), len(STRAY_PATTERNS))))

    # -- the manifest itself ------------------------------------------------
    listed, record_name = record_names(zf, names)
    if listed is None:
        out.append(fail("record_matches_zip",
                        "no single *.dist-info/RECORD -- the wheel has no manifest"))
    else:
        in_zip = set(names) - set([record_name])
        missing = sorted(in_zip - listed)
        phantom = sorted(listed - in_zip - set([record_name]))
        if missing or phantom:
            out.append(fail("record_matches_zip",
                            "%s and the zip disagree: %d member(s) unlisted (%s), "
                            "%d listed but absent (%s)"
                            % (record_name, len(missing), ", ".join(missing[:3]) or "-",
                               len(phantom), ", ".join(phantom[:3]) or "-")))
        else:
            out.append(ok("record_matches_zip", "%s lists all %d members"
                          % (record_name, len(in_zip))))
    return out


def main(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev audit-wheel")
    parser.add_argument("wheel", help="dist/hato-*.whl")
    parser.add_argument("--root", metavar="DIR", help="the source checkout it was built from")
    parser.add_argument("--dist-name", default=DIST_NAME,
                        help="the distribution name METADATA must declare (default: %s)"
                             % DIST_NAME)
    args = parser.parse_args(argv)
    path = resolve_wheel(args.wheel)
    root = claims.find_root(args.root)
    return claims.report("audit-wheel", str(path), audit(path, root, args.dist_name))
