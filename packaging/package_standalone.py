# -*- coding: utf-8 -*-
u"""Turn the built bundle into the thing a person downloads. RUNBOOK 7g.

    python packaging/package_standalone.py
    python packaging/package_standalone.py --to "D:/somewhere"

===========================================================================
🚨 THE ZIP IS NOT THE POINT. LEAVING THE REPOSITORY IS THE POINT.
===========================================================================

`dist/standalone/hato/` already contains a complete, Python-free application;
zipping it changes nothing about what it does. ⛔ What the zip buys is the
only test that has ever caught this class of defect: **an artifact driven
from OUTSIDE every checkout.**

⚠ A bundle sitting inside the repository can resolve a path through the
repository and work perfectly there and nowhere else. tsubasa shipped exactly
that once -- `10-deployment.md` records a file *"there on the machine that
built it and nowhere on the machine that installed it"* -- and hato's own
`.github/workflows/release.yml` carries a P6 check for the same reason.

⭐ So `--verify` (on by default) unpacks the zip into a TEMPORARY directory
with no relationship to this tree and runs `smoke_standalone.py` against
THOSE bytes. ⛔ A green smoke in `dist/` proves the build; only this proves
the download.

===========================================================================
⚠ ONE TOP-LEVEL FOLDER INSIDE THE ARCHIVE
===========================================================================

Everything lands under `hato/`, so unzipping in Downloads produces one
folder rather than 1,200 loose files in whatever directory the person
happened to be looking at. ⛔ That is not a nicety: a flat zip extracted onto
a Desktop is an hour of somebody's evening.
"""
from __future__ import print_function

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

#: 🚨 A WINDOWS CONSOLE IS cp1252 AND THIS FILE PRINTS ⛔ AND ⭐. Measured
#: 2026-09-18: the failure branch raised `UnicodeEncodeError` from `print`
#: itself, so the ONE message that mattered -- *"the unpacked copy failed its
#: smoke test, do not publish this"* -- was replaced by a traceback about
#: character encoding. ⛔ The script reported a packaging failure as a crash.
#: ⚠ `errors="replace"` as well, so a console that still cannot encode prints
#: a question mark rather than taking the run down.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUNDLE = os.path.join(ROOT, "dist", "standalone", "hato")


def version():
    u"""-> hato's version, read from the package, never hand-typed."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from hato import __version__
    return __version__


#: 🚨 MUST TRAVEL WITH THE BINARY. hato is GPL-3.0-or-later and the artifact
#: bundles PyQt6 (GPL-3.0), CPython and OpenSSL. GPLv3 §4/§6 require the
#: licence to accompany the object code you CONVEY -- and a zip on a Releases
#: page is conveying.
#:
#: ⛔ The first build of this artifact carried none of them: 265 entries and
#: the only licence files in it belonged to two unrelated packages, collected
#: by accident. Found by an adversarial pass before it was ever published.
#:
#: ⭐ The README earns its place too, for a plainer reason: without it a
#: downloader gets three unlabelled executables and nothing that says which
#: one to run -- and `hato.exe` being the window rather than the CLI is the
#: whole naming ruling.
ALONGSIDE = ["LICENSE", "THIRD_PARTY_LICENSES.md", "README.md"]


def build_zip(bundle, out_path):
    u"""Zip `bundle` under a single top-level `hato/`. -> (files, bytes)"""
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for folder, _dirs, names in os.walk(bundle):
            for name in names:
                full = os.path.join(folder, name)
                # ⚠ `hato/` prefix, then the path RELATIVE to the bundle --
                # never the absolute one, which would bake this machine's
                # directory layout into the archive.
                inside = os.path.join(
                    "hato", os.path.relpath(full, bundle)).replace("\\", "/")
                archive.write(full, inside)
                count += 1
        for name in ALONGSIDE:
            source = os.path.join(ROOT, name)
            if not os.path.isfile(source):
                # ⛔ LOUD. A missing licence is not a thing to carry on past.
                raise SystemExit(
                    u"\n  refusing to build the archive: %s is missing, and "
                    u"the binary may not be conveyed without it.\n" % name)
            archive.write(source, "hato/" + name)
            count += 1
    return count, os.path.getsize(out_path)


def extract(zip_path, where):
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(where)
    return os.path.join(where, "hato")


def verify(zip_path):
    u"""Unpack somewhere unrelated and drive THOSE bytes. -> True when green."""
    temp = tempfile.mkdtemp(prefix="hato-verify-")
    try:
        unpacked = extract(zip_path, temp)
        print(u"\n  verifying the UNPACKED copy at %s\n" % unpacked)
        # ⛔ The smoke script, not a second copy of its checks. It already
        # knows to run in its own store.
        result = subprocess.call(
            [sys.executable, os.path.join(HERE, "smoke_standalone.py"),
             unpacked])
        return result == 0
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=u"Package the frozen hato.")
    parser.add_argument("--to", metavar="DIR",
                        help=u"also unpack a ready-to-run copy here")
    parser.add_argument("--no-verify", action="store_true",
                        help=u"skip the unpacked-elsewhere check (not advised)")
    args = parser.parse_args(argv)

    if not os.path.isdir(BUNDLE):
        print(u"\n  no bundle at %s\n  build it first:\n"
              u"    python -m PyInstaller --noconfirm --distpath dist/standalone "
              u"--workpath build/standalone packaging/hato.spec\n" % BUNDLE)
        return 2

    out_dir = os.path.join(ROOT, "dist")
    name = u"hato-%s-windows-x64.zip" % version()
    out_path = os.path.join(out_dir, name)
    if os.path.exists(out_path):
        os.remove(out_path)

    print(u"\n  packaging %s" % BUNDLE)
    count, size = build_zip(BUNDLE, out_path)
    raw = sum(os.path.getsize(os.path.join(f, n))
              for f, _d, ns in os.walk(BUNDLE) for n in ns)
    print(u"  -> %s" % out_path)
    print(u"     %d files, %.1f MB zipped from %.1f MB on disk (%.0f%%)"
          % (count, size / 1048576.0, raw / 1048576.0,
             100.0 * size / raw if raw else 0))

    ok = True
    if not args.no_verify:
        ok = verify(out_path)
        if not ok:
            print(u"\n  ⛔ the UNPACKED copy failed its smoke test. "
                  u"Do not publish this.\n")

    if args.to:
        # ⛔ NEVER UNPACK A BUILD THAT FAILED ITS OWN VERIFICATION. This used
        # to print "Do not publish this" and then put that exact build on the
        # person's Desktop and call it "ready to run".
        if not ok:
            print(u"  ⛔ not unpacking a copy that failed its own smoke test.\n")
            return 1

        target = os.path.abspath(args.to)
        landing = os.path.join(target, "hato")

        # 🚨 THIS DELETED WHATEVER WAS CALLED `hato` AT THE TARGET, WITH NO
        # CHECK THAT THIS SCRIPT PUT IT THERE. `--to .` from the repository
        # root resolves to `<repo>/hato` -- the Python package. `--to ..`
        # resolves to the whole repository. `ignore_errors=True` meant it
        # deleted what it could and said nothing. Found by an adversarial
        # pass, 2026-09-18, before it cost anything.
        inside_repo = os.path.normcase(landing).startswith(
            os.path.normcase(ROOT) + os.sep) or \
            os.path.normcase(landing) == os.path.normcase(ROOT)
        if inside_repo:
            print(u"  ⛔ refusing: %s is inside the source tree.\n" % landing)
            return 1

        if os.path.isdir(landing):
            # ⚠ Only ever remove something that is recognisably a previous
            # unpack of THIS artifact. The three executables are the contract;
            # one of them being present is the proof.
            if not os.path.isfile(os.path.join(landing, "hato.exe")):
                print(u"  ⛔ refusing: %s exists and is not a hato bundle.\n"
                      % landing)
                return 1
            shutil.rmtree(landing)            # ⛔ not ignore_errors: say so

        extract(out_path, target)
        print(u"\n  unpacked a ready-to-run copy:")
        print(u"     %s" % os.path.join(landing, "hato.exe"))

    print(u"")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
