# -*- coding: utf-8 -*-
u"""The release half of the update signature -- RUNBOOK 11a.

    python -m hato.dev keygen            make the PRIVATE key, once, in the keystore,
                                         and print the PUBLIC half for
                                         `hato.update.PUBLIC_KEYS`
    python -m hato.dev update-manifest --zip <zip> [--notes FILE] [--min-from X.Y.Z]
                                         [--critical]
                                         update.json + update.json.sig beside the zip,
                                         built FROM the zip, then checked the way every
                                         install will check it

🚨 THE PRIVATE KEY NEVER ENTERS A REPOSITORY -- ASSERTED, NOT REMEMBERED
(doctrine/robustness §Secrets). `keygen` refuses a target inside any git work tree
(it looks for `.git` in every folder above), refuses to overwrite a key that exists
-- a second key would silently orphan every install that trusts the first -- and
prints only the public half, which is safe anywhere.

⭐ BUILT FROM THE ZIP, NOT FROM `dist/`. The manifest's size, sha256 and entries
are read out of the very archive that is published, so a rebuilt zip beside an old
manifest cannot happen here: surasura's doc records that exact failure, silent,
on every client.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

from hato import update
from hato.dev import claims
from hato.dev.claims import Fault, fail, ok

#: The first release that carries an updater: the oldest version that can take
#: a newer one in place. Every release before it is installed by hand, once.
FIRST_UPDATER = u"1.0.4"

_ZIP_NAME = re.compile(r"^hato-(\d{1,4}\.\d{1,4}\.\d{1,4})-windows-x64\.zip$")


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------

def inside_repository(folder):
    u"""True when `folder`, or any folder above it, holds `.git` -- a work tree."""
    here = Path(folder).resolve()
    for d in [here] + list(here.parents):
        if (d / ".git").exists():
            return True
    return False


def default_key_path():
    path, why = _paths().signing_key_file()
    if path is None:
        raise Fault(why)
    return Path(path)


def _paths():
    from hato import paths
    return paths


def _crypto():
    u"""-> (ECC, eddsa) from PyCryptodome -- the `update` extra. ⛔ Absent is a
    sentence naming the extra, never a bare ImportError (test_packaging)."""
    try:
        from Cryptodome.PublicKey import ECC
        from Cryptodome.Signature import eddsa
    except ImportError:
        raise Fault(u"signing needs the `update` extra -- pip install pycryptodomex")
    return ECC, eddsa


def keygen(path):
    u"""Write a new Ed25519 private key to `path` (PEM). -> the public half, base64.

    ⛔ Refuses: a path that exists · a folder that does not · a folder inside a
    git work tree. Temp-plus-rename, so a failed write leaves no half a key."""
    path = Path(path)
    if path.exists():
        raise Fault(u"%s already exists -- a second key would orphan every install "
                    u"that trusts the first. Remove it yourself if you mean it" % path)
    if not path.parent.is_dir():
        raise Fault(u"%s does not exist -- the keystore folder is made by a person, "
                    u"not by this tool" % path.parent)
    if inside_repository(path.parent):
        raise Fault(u"%s is inside a git work tree -- a private key there is one "
                    u"`git add` from being published" % path.parent)
    ECC, _eddsa = _crypto()
    key = ECC.generate(curve=u"Ed25519")
    pem = key.export_key(format=u"PEM")
    temp = path.with_name(path.name + u".new")
    with open(str(temp), "x", encoding="ascii", newline="\n") as handle:
        handle.write(pem + u"\n")
    os.replace(str(temp), str(path))
    return _public_of(key)


def _public_of(key):
    return base64.b64encode(key.public_key().export_key(format=u"raw")).decode("ascii")


def _load(path):
    ECC, _eddsa = _crypto()
    try:
        with open(str(path), encoding="ascii") as handle:
            return ECC.import_key(handle.read())
    except (OSError, ValueError) as exc:
        raise Fault(u"the signing key at %s could not be read (%s)" % (path, exc))


def public_half(path):
    u"""-> the base64 public half of the private key at `path`."""
    return _public_of(_load(path))


def sign(raw, path):
    u"""-> the base64 Ed25519 signature of exactly `raw`, by the key at `path`."""
    _ECC, eddsa = _crypto()
    signature = eddsa.new(_load(path), u"rfc8032").sign(raw)
    return base64.b64encode(signature).decode("ascii")


# ---------------------------------------------------------------------------
# the manifest
# ---------------------------------------------------------------------------

def _entries_of(archive):
    u"""The zip's top-level program entries -> {name: sha256 or ''} (folders '').
    ⛔ One top-level folder, `hato/`, and nothing else: that is the archive
    `package_standalone.build_zip` makes, and anything else is not a hato zip."""
    entries = {}
    for info in archive.infolist():
        parts = info.filename.replace(u"\\", u"/").split(u"/")
        if parts[0] != u"hato" or len(parts) < 2 or not parts[1]:
            raise Fault(u"%r is not inside the zip's one top-level folder, hato/"
                        % info.filename)
        name = parts[1]
        if len(parts) > 2:                       # inside a top-level folder
            entries.setdefault(name, u"")
            continue
        if info.is_dir():
            entries.setdefault(name, u"")
            continue
        entries[name] = hashlib.sha256(archive.read(info)).hexdigest()
    return entries


def build_manifest(zip_path, notes=(), min_from=FIRST_UPDATER, critical=False):
    u"""-> the Manifest for the zip at `zip_path`, read out of the zip itself."""
    zip_path = Path(zip_path)
    match = _ZIP_NAME.match(zip_path.name)
    if not match:
        raise Fault(u"%s is not named hato-X.Y.Z-windows-x64.zip" % zip_path.name)
    try:
        with zipfile.ZipFile(str(zip_path)) as archive:
            entries = _entries_of(archive)
    except zipfile.BadZipFile as exc:
        raise Fault(u"%s is not a readable zip (%s)" % (zip_path, exc))
    manifest = update.Manifest(match.group(1), zip_path.name, zip_path.stat().st_size,
                               update.sha256_file(str(zip_path)), min_from,
                               bool(critical), notes, entries)
    # ⭐ The client's own parser is the gate: a manifest it would refuse is never
    # written, so a release cannot publish one.
    try:
        update.parse_manifest(update.manifest_bytes(manifest))
    except update.ManifestError as exc:
        raise Fault(u"the manifest built from %s would be refused: %s" % (zip_path.name, exc))
    return manifest


def write_manifest(zip_path, key_path, notes=(), min_from=FIRST_UPDATER, critical=False):
    u"""update.json and update.json.sig beside the zip. -> (manifest, raw, signature)"""
    manifest = build_manifest(zip_path, notes, min_from, critical)
    raw = update.manifest_bytes(manifest)
    signature = sign(raw, key_path)
    folder = Path(zip_path).parent
    for name, data in ((update.MANIFEST_NAME, raw),
                       (update.SIGNATURE_NAME, (signature + u"\n").encode("ascii"))):
        temp = folder / (name + u".new")
        with open(str(temp), "wb") as handle:
            handle.write(data)
        os.replace(str(temp), str(folder / name))
    return manifest, raw, signature


def check_written(zip_path, keys=None):
    u"""The claims a release relies on, read back from what was WRITTEN."""
    folder = Path(zip_path).parent
    raw = (folder / update.MANIFEST_NAME).read_bytes()
    sig = (folder / update.SIGNATURE_NAME).read_text(encoding="ascii")
    out = []
    if update.verify_signature(raw, sig, keys):
        out.append(ok("signature_verifies", u"by a key hato trusts (update.PUBLIC_KEYS)"))
    else:
        out.append(fail("signature_verifies",
                        u"no key in update.PUBLIC_KEYS verifies it -- every install would "
                        u"refuse this release"))
    try:
        manifest = update.parse_manifest(raw)
        out.append(ok("manifest_parses", u"%s, %d entries" % (manifest.version,
                                                             len(manifest.entries))))
    except update.ManifestError as exc:
        return out + [fail("manifest_parses", u"%s" % exc)]
    digest = update.sha256_file(str(zip_path))
    out.append((ok if digest == manifest.zip_sha256 else fail)(
        "zip_matches", u"sha256 %s" % digest[:16]))
    return out


def check_published(zip_path, keys=None, fetch=None):
    u"""The PUBLISHED release, read back from GitHub the way an install reads it.
    -> [claim]

    ⭐ doctrine/release: *verify by hash -- "it succeeded" is not "the right bytes
    are live"*. The zip, `update.json` and its signature are downloaded from the
    release's own asset URLs, each must be the LOCAL file's bytes, GitHub's own
    `digest` must agree, and the downloaded pair is checked exactly as
    `check_written` checks the written one -- signature, parse, zip. ⛔ Never the
    upload's report of itself."""
    import tempfile
    fetch = fetch or update.fetch
    zip_path = Path(zip_path)
    match = _ZIP_NAME.match(zip_path.name)
    if not match:
        return [fail("zip_named", u"%s is not hato-X.Y.Z-windows-x64.zip" % zip_path.name)]
    version = match.group(1)
    tag = u"v" + version
    out = []
    try:
        release = json.loads(fetch(u"https://api.github.com/repos/%s/releases/tags/%s"
                                   % (update.REPO, tag), 1 << 20).decode("utf-8"))
    except Exception as exc:                  # noqa: BLE001 -- a claim, never a traceback
        return [fail("release_readable", u"%s: %s" % (tag, exc))]
    # 🚨 AS AN INSTALL SEES IT (ADVERSARY 2026-09-24, A4): an install asks for
    # releases/LATEST. A tag's release that is not the latest -- a prerelease, a
    # draft, an older tag -- is one no install is ever offered, and it verified.
    try:
        latest = json.loads(fetch(update.LATEST_URL, update.MAX_RELEASE_BYTES)
                            .decode("utf-8")).get(u"tag_name")
    except Exception as exc:                  # noqa: BLE001
        latest = u"unreadable (%s)" % type(exc).__name__
    out.append((ok if latest == tag else fail)(
        "the_latest_release", u"releases/latest is %s -- an install asks for that one" % latest))
    assets = dict((a.get(u"name"), a) for a in release.get(u"assets") or []
                  if isinstance(a, dict))
    folder = Path(tempfile.mkdtemp(prefix=u"hato-published-"))
    try:
        for name, limit in ((zip_path.name, update.MAX_BUNDLE_BYTES),
                            (update.MANIFEST_NAME, 1 << 20),
                            (update.SIGNATURE_NAME, 1 << 16)):
            asset = assets.get(name)
            if asset is None:
                out.append(fail("published_" + name, u"not among the release's assets"))
                continue
            try:
                body = fetch(asset[u"browser_download_url"], limit)
            except Exception as exc:          # noqa: BLE001
                out.append(fail("published_" + name, u"%s" % exc))
                continue
            (folder / name).write_bytes(body)
            local = (zip_path.parent / name).read_bytes()
            out.append((ok if body == local else fail)(
                "published_" + name, u"%d bytes, %s the local file" % (
                    len(body), u"identical to" if body == local else u"DIFFERENT from")))
        recorded = (assets.get(zip_path.name) or {}).get(u"digest")
        if isinstance(recorded, str) and recorded:
            local_sha = update.sha256_file(str(zip_path))
            out.append((ok if recorded == u"sha256:" + local_sha else fail)(
                "github_digest", u"GitHub records %s" % recorded[:23]))
        manifest = None
        if (folder / update.MANIFEST_NAME).is_file():
            try:
                manifest = update.parse_manifest((folder / update.MANIFEST_NAME).read_bytes())
            except update.ManifestError:
                pass                          # check_written below says so
        if manifest is not None:
            # ⛔ A signed 1.0.5 published as v1.0.6 verified green -- and every install
            # refused it (ADVERSARY 2026-09-24, A4). The manifest names the tag's
            # version and THIS zip, or it is not this release.
            names = manifest.version == version and manifest.zip_name == zip_path.name
            out.append((ok if names else fail)(
                "manifest_names_this_release", u"version %s and %s, for tag %s"
                % (manifest.version, manifest.zip_name, tag)))
        if all(c.state == claims.OK for c in out) and (folder / zip_path.name).is_file():
            out.extend(check_written(folder / zip_path.name, keys))
        if all(c.state == claims.OK for c in out) and manifest is not None:
            # ⭐ AND THE CLIENT ITSELF: a copy at `min_from`, frozen on Windows, asking
            # GitHub now -- the answer every install will get.
            if update.is_newer(version, manifest.min_from):
                said = update.check(manifest.min_from, get=fetch, frozen=True, windows=True,
                                    install_dir=str(folder), keys=keys)
                takes = said.kind == update.READY and said.version == version
                out.append((ok if takes else fail)(
                    "an_install_takes_it", u"hato %s asking now: %s %s %s" % (
                        manifest.min_from, said.kind, said.version, said.reason or u"")))
            else:
                out.append(claims.skip(
                    "an_install_takes_it", u"min_from is %s itself -- no install updates to "
                    u"it on its own (the first release with an updater)" % version))
    finally:
        import shutil
        shutil.rmtree(str(folder), ignore_errors=True)
    return out


# ---------------------------------------------------------------------------
# the commands
# ---------------------------------------------------------------------------

def main_keygen(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev keygen",
                                     description=u"make the update signing key, once")
    parser.add_argument("--path", help=u"default: keystore.signingRelative")
    args = parser.parse_args(argv)
    claims.utf8_stdio()
    path = Path(args.path) if args.path else default_key_path()
    public = keygen(path)
    print(u"hato.dev keygen  wrote the PRIVATE key to %s" % path)
    print(u"  public half (put it in hato/update.py PUBLIC_KEYS): %s" % public)
    print(u"  ⚠ back that file up: without it, installs stop updating themselves")
    return claims.EXIT_OK


def main_manifest(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev update-manifest",
                                     description=u"update.json + its signature, from the zip")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--notes", help=u"a text file, one short line per change")
    parser.add_argument("--min-from", default=FIRST_UPDATER)
    parser.add_argument("--critical", action="store_true")
    parser.add_argument("--key", help=u"default: keystore.signingRelative")
    args = parser.parse_args(argv)
    notes = ()
    if args.notes:
        with open(args.notes, encoding="utf-8") as handle:
            notes = tuple(line.strip() for line in handle if line.strip())
    key = Path(args.key) if args.key else default_key_path()
    write_manifest(args.zip, key, notes, args.min_from, args.critical)
    return claims.report("update-manifest", args.zip, check_written(args.zip))


def main_verify_release(argv):
    parser = argparse.ArgumentParser(
        prog="python -m hato.dev verify-release",
        description=u"download the PUBLISHED release and check it as an install would")
    parser.add_argument("--zip", required=True,
                        help=u"the local zip; update.json and its .sig beside it")
    args = parser.parse_args(argv)
    claims.utf8_stdio()
    return claims.report("verify-release", args.zip, check_published(args.zip))


__all__ = ["FIRST_UPDATER", "build_manifest", "check_published", "check_written",
           "default_key_path", "inside_repository", "keygen", "main_keygen",
           "main_manifest", "main_verify_release", "public_half", "sign",
           "write_manifest"]
