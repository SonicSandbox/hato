# -*- coding: utf-8 -*-
"""
The version stamp -- a CONTENT HASH, never a timestamp, never hand-bumped.

    python -m hato.dev stamp --release 0.1.0    declare the number, record the tree
    python -m hato.dev stamp                    re-record the tree at the same number
    python -m hato.dev stamp --check            ⛔ THE GATE. Exit 1 if either drifted

⭐ THE TWO HALVES, AND WHY THEY ARE DIFFERENT THINGS.

`doctrine/release` §2 says derive the version from a content hash of everything
the delivery layer serves -- never a timestamp (it churns on every build in an
auto-committing repo), never a hand-bumped constant. But PyPI needs `0.1.0`, not
a hex digest, and which number comes next is a DECISION (a patch after a broken
publish, a minor after a new capability -- PYPI-PUBLISHING-DRAFT §2.7). So:

    the RELEASE NUMBER is declared, once, by a human, with --release
    the CONTENT HASH is what proves the tree has not drifted since it was declared

`hato/dev/_stamp.json` holds both, plus the per-file digest of every file the
artifact ships -- so a failure names WHICH file drifted instead of saying the
hash is different.

🚨 WHY `--check` EXISTS AT ALL, quoted from the doctrine it comes from: "The
stamper EXISTED and was bypassed with a hand-written edit hours after it was
built, precisely because nothing forced it. Wire `--check` in front of the
upload and a stale version cannot physically ship." So `--check` makes two
separate claims, and the FIRST one is the hand-bump:

    version_matches_stamp   hato/__init__.py's __version__ == _stamp.json's release
    content_unchanged       every shipped file still hashes to what was recorded

⚠ WHY THE STAMP FILE IS `hato/dev/_stamp.json` AND NOT `hato/_stamp.json`. Only
this package reads it, and putting it inside the package that ships would make
"does the wheel carry its data files" (pitfall P7) ambiguous about a file the
installed hato never opens. Under `hato/dev/` the answer is simply "dev tooling,
excused by name", which `audit-wheel` prints.

⛔ THE ONE FILE THIS WRITES OUTSIDE `hato/dev/` IS `hato/__init__.py`, through
`anchor.replace_once` -- exactly one match or nothing at all.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from hato.dev import anchor, claims
from hato.dev.claims import Fault, fail, ok

#: Where the record lives, relative to the source root.
STAMP_REL = "hato/dev/_stamp.json"

#: The package itself -- every file under it, whatever the extension.
PACKAGE = "hato"
#: Beside the package, when present. `hato-run.cmd` ships INSIDE the wheel
#: (spec/10-deployment.md §Release shape); the rest are published claims about it.
SIBLINGS = ("hato-run.cmd", "pyproject.toml", "LICENSE", "LICENSE.txt", "LICENCE",
            "COPYING", "THIRD_PARTY_LICENSES.md", "README.md")
#: ⛔ Never hashed: build litter, and the record itself (it would be circular).
SKIP_DIRS = ("__pycache__", ".pytest_cache", "_runs", ".git")
SKIP_SUFFIXES = (".pyc", ".pyo", ".tmp")

#: PEP 440's release forms this project uses, and nothing looser. A version is a
#: published, permanent claim (PYPI-PUBLISHING-DRAFT §2.7: numbers are burned for
#: good), so a typo must be a refusal rather than an upload.
_RELEASE = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+|\.post\d+|\.dev\d+)?$")

_VERSION_LINE = '__version__ = "%s"'


def _skipped(rel_parts):
    return any(part in SKIP_DIRS for part in rel_parts)


def ship_files(root):
    """Every file the artifact ships. -> {posix relative path: Path}

    ⭐ DERIVED FROM THE TREE, never a hand-written list: a data file added under
    `hato/` next month is hashed without anyone remembering to add it, which is
    the difference between a stamp and a decoration.
    """
    root = Path(root)
    found = {}
    package = root / PACKAGE
    if not package.is_dir():
        raise Fault("no %s/ package under %s" % (PACKAGE, root))
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _skipped(rel.parts) or path.suffix in SKIP_SUFFIXES:
            continue
        posix = rel.as_posix()
        if posix == STAMP_REL:
            continue                        # the record cannot hash itself
        found[posix] = path
    for name in SIBLINGS:
        path = root / name
        if path.is_file():
            found[name] = path
    return found


def digest(path):
    u"""sha256 of a file's CONTENT, with line endings normalised. -> hex

    🚨 THE STAMP USED TO HASH RAW BYTES, AND THAT MADE IT VALID ON EXACTLY ONE
    MACHINE -- the one that wrote it. A content hash is supposed to prove *the
    published commit is the code that was tested*; hashing raw bytes proved
    something narrower and useless: *these files, as this filesystem happens to
    store newlines today.* Git rewrites that on the way in and on the way out.

    ⭐ MEASURED 2026-09-19, and the number moved with the PLATFORM, which is
    what gave it away:

        this working tree (LF, written by sync_from_vault)   72/72 held
        a fresh Windows checkout (core.autocrlf=true -> CRLF)   50 differed
        Linux CI (index bytes; 9 files are stored CRLF)          9 differed

    All 50 were line endings ONLY -- zero files differed in content, zero were
    missing. ⛔ So `release.yml`'s stamp gate failed on the v1.0.0 tag and
    again on v1.0.1, and both times it was reporting the truth about bytes it
    should never have been looking at. A gate that cannot pass anywhere is one
    people learn to scroll past, which is `doctrine/release` in its own words.

    ⚠ WHAT THIS GIVES UP, STATED: the stamp no longer notices a file whose
    ONLY change is its line endings. That is deliberate -- `.gitattributes` is
    what guarantees endings where they are load-bearing (`*.cmd text eol=crlf`
    for `hato-run.cmd`, `-text` on LICENSE and the byte-exact fixtures), and it
    guarantees them on every checkout, which a hash never could.

    ⚠ Binary files are left alone, using git's own heuristic: a NUL byte means
    binary. Git does not convert those either, so their bytes are already the
    same everywhere and normalising would only risk conflating two files.
    """
    data = Path(path).read_bytes()
    if b"\x00" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def manifest(root):
    """-> {posix relative path: sha256 hex} over `ship_files(root)`."""
    return dict((rel, digest(path)) for rel, path in ship_files(root).items())


def content_hash(files):
    """One hash over the whole manifest. -> "sha256:<hex>"

    The digested text is `"<path> <sha256>\\n"` per file, sorted by path -- so a
    RENAME changes it, not just an edit.
    """
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(("%s %s\n" % (rel, files[rel])).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def stamp_path(root):
    return Path(root) / STAMP_REL


def read_stamp(root):
    """-> dict, or None when nothing has been stamped yet."""
    path = stamp_path(root)
    if not path.is_file():
        return None
    try:
        with open(str(path), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise Fault("%s exists but could not be read: %s" % (path, exc))


def _record(release, files):
    return {
        "//": ("hato's version stamp. The RELEASE NUMBER is a decision, declared "
               "with `python -m hato.dev stamp --release X.Y.Z`; the CONTENT HASH "
               "is what `stamp --check` proves has not drifted since. ⛔ Never "
               "hand-edit either -- re-run the stamper (doctrine/release §2)."),
        "release": release,
        "content_hash": content_hash(files),
        "algorithm": ("sha256 over '<posix path> <sha256 of content>\\n' per "
                      "file, sorted by path, utf-8. Per-file content is the "
                      "file's bytes with CRLF normalised to LF unless it holds "
                      "a NUL, so the hash survives git's line-ending rewrite "
                      "and means the same thing on every platform."),
        "file_count": len(files),
        "stamped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "//stamped_at": ("provenance only -- ⛔ NOT part of content_hash. A "
                         "timestamp in the hash would churn on every build in an "
                         "auto-committing repo (doctrine/release §2)."),
        "files": dict(sorted(files.items())),
    }


def check(root):
    """The gate. -> [Claim]. ⛔ Read-only: this never writes anything."""
    root = Path(root)
    on_disk = read_stamp(root)
    if on_disk is None:
        return [fail("stamp_file",
                     "no %s -- nothing has been stamped, so no version can be "
                     "trusted. Run `python -m hato.dev stamp --release X.Y.Z`"
                     % STAMP_REL)]

    out = [ok("stamp_file", "%s, release %s, %d files, stamped %s"
              % (STAMP_REL, on_disk.get("release"), on_disk.get("file_count", -1),
                 on_disk.get("stamped_at", "?")))]

    source_version, source_path = claims.read_source_version(root)
    release = on_disk.get("release")
    if source_version == release:
        out.append(ok("version_matches_stamp",
                      '%s says __version__ = "%s"' % (source_path.name, source_version)))
    else:
        out.append(fail("version_matches_stamp",
                        'hato/__init__.py says "%s" and the stamp says "%s" -- a '
                        "hand-bumped version cannot ship (doctrine/release §2)"
                        % (source_version, release)))

    now = manifest(root)
    was = on_disk.get("files") or {}
    added = sorted(set(now) - set(was))
    removed = sorted(set(was) - set(now))
    if added or removed:
        bits = []
        if added:
            bits.append("%d added (%s)" % (len(added), ", ".join(added[:3])))
        if removed:
            bits.append("%d removed (%s)" % (len(removed), ", ".join(removed[:3])))
        out.append(fail("ship_set_unchanged",
                        "the set of shipped files changed since the stamp: %s"
                        % "; ".join(bits)))
    else:
        out.append(ok("ship_set_unchanged", "%d files, the same names as the stamp"
                      % len(now)))

    drifted = sorted(rel for rel in set(now) & set(was) if now[rel] != was[rel])
    if drifted:
        out.append(fail("content_unchanged",
                        "%d of %d shipped files changed since the stamp: %s"
                        % (len(drifted), len(now), ", ".join(drifted[:3])
                           + (", ..." if len(drifted) > 3 else ""))))
    else:
        out.append(ok("content_unchanged",
                      "%d of %d shipped files hash to the stamp; %s"
                      % (len(now), len(now), content_hash(now))))
    return out


def write(root, release=None):
    """Declare the number, edit the version, record the tree. -> [Claim]."""
    root = Path(root)
    on_disk = read_stamp(root)
    if release is None:
        release = (on_disk or {}).get("release")
        if release is None:
            raise Fault("the release number is a DECISION, not a hash: pass "
                        "--release X.Y.Z the first time (doctrine/release §2)")
    if not _RELEASE.match(release):
        raise Fault("%r is not a release number this project publishes -- expected "
                    "X.Y.Z, optionally aN/bN/rcN/.postN/.devN" % release)

    source_version, source_path = claims.read_source_version(root)
    out = []
    try:
        edit = anchor.replace_once(source_path,
                                   _VERSION_LINE % source_version,
                                   _VERSION_LINE % release)
    except anchor.AnchorRefused as exc:
        raise Fault(str(exc))
    out.append(ok("version_written",
                  '%s: __version__ "%s" -> "%s"%s, %s endings, one anchored match'
                  % (source_path.name, source_version, release,
                     "" if edit.changed else " (already correct, nothing written)",
                     "CRLF" if edit.ending == anchor.CRLF else "LF")))

    files = manifest(root)
    record = _record(release, files)
    data = json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    anchor.write_bytes_once(stamp_path(root), data + b"\n")
    out.append(ok("stamp_written", "%s: release %s, %d files, %s"
                  % (STAMP_REL, release, len(files), record["content_hash"])))

    # ⭐ Assert the artefact this call just produced (doctrine/evidence): the
    # stamp it wrote must satisfy the gate it exists to feed. Without this, a
    # stamper that wrote a record its own --check rejects would report success.
    for c in check(root):
        if c.state != claims.OK:
            out.append(fail("stamp_satisfies_check",
                            "the stamp just written does not pass --check: %s -- %s"
                            % (c.name, c.saw)))
            return out
    out.append(ok("stamp_satisfies_check", "`stamp --check` holds on the record just written"))
    return out


def main(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev stamp",
                                     description=__doc__.strip().splitlines()[0])
    parser.add_argument("--root", metavar="DIR", help="the source checkout to stamp")
    parser.add_argument("--release", metavar="X.Y.Z",
                        help="declare the release number (a decision, not a hash)")
    parser.add_argument("--check", action="store_true",
                        help="⛔ read-only: exit 1 if the stamp on disk disagrees "
                             "with the tree")
    args = parser.parse_args(argv)
    root = claims.find_root(args.root)
    if args.check:
        if args.release:
            raise Fault("--check is read-only; --release declares a number. Pick one")
        return claims.report("stamp --check", str(root), check(root))
    return claims.report("stamp", str(root), write(root, args.release))
