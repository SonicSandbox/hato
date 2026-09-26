# -*- coding: utf-8 -*-
u"""Auto-update: the release contract, the check, and staging. RUNBOOK LAYER 11.

    hato update --check              is a newer hato out, and can THIS copy take it?
    hato update --stage --progress   download it and prove it, while hato keeps running
    hato update --apply              hand it to the swapper (`hato/swap.py`) and close

Ruled by Sonic 2026-09-24 (*"I take all your leans"*): the WHOLE program folder is
replaced; it is downloaded and proven quietly; the window never restarts under a
person; the tray or the 03:00 run installs it while nothing is open; and every
release is SIGNED.

===========================================================================
⭐ THE RELEASE CONTRACT (11a)
===========================================================================

A release carries three assets: the zip, `update.json` and `update.json.sig`. The
manifest names the zip's bytes, the oldest version that may take it in place
(`min_from`), whether it is urgent, a few lines of what changed, and every
top-level entry of the program folder with each file's sha256 -- built from the
SAME zip that is published (`hato.dev update-manifest`).

🚨 WHY A SIGNATURE, NOT ONLY A CHECKSUM. Auto-update turns "whoever can publish a
GitHub release" into "whoever can run code on every install". A checksum
published beside the zip proves it arrived whole and nothing about who made it.
So the manifest is signed (Ed25519) with a key that exists only on the release
machine -- `InfiniteVoid/keystore/`, outside every repository, by construction --
and hato carries the PUBLIC half, which can check a signature and never make one.
⭐ Other people's installs hold nothing and need nothing.

⛔ FAIL CLOSED FOR INSTALLING, OPEN FOR TELLING (doctrine/robustness: choose, and
write the choice down). No signature, a bad one, a manifest this code cannot
read, or a zip GitHub records differently -> nothing is installed; the person is
told a release is out and can download it by hand.

===========================================================================
⛔ NOTHING HAPPENS AT IMPORT
===========================================================================

`hato.api` is a library, and a module that reached the network or the disk when
imported would do it inside whatever program imported hato. A check happens only
when the window, the tray or `hato update` asks. ⚠ PyCryptodome is imported
LAZILY, inside the one function that needs it: it is the `update` extra, and a
source install without it can still be TOLD about a release -- it can only never
install one, which it never does anyway.
"""
import base64
import hashlib
import json
import re

#: The repository whose releases are hato's.
REPO = u"SonicSandbox/hato"
MANIFEST_NAME = u"update.json"
SIGNATURE_NAME = u"update.json.sig"
#: The one zip name a release may carry, derived from its version.
ZIP_TEMPLATE = u"hato-%s-windows-x64.zip"
#: The manifest format this code reads. ⛔ A newer one is not guessed at.
FORMAT = 1

#: ⭐ THE PUBLIC HALVES THAT MAY SIGN A RELEASE -- raw Ed25519, base64. A tuple so
#: a key can be ROTATED: a release signed by a new key ships its public half
#: beside the old one, and a later release may drop the old.
#: ⛔ Public by design -- it verifies and cannot sign (doctrine/robustness: *say
#: which keys are which, in writing*). The private half is the file
#: `hato.config.json` names as `keystore.signingRelative`, made once by
#: `python -m hato.dev keygen`, and it never leaves that folder.
PUBLIC_KEYS = (
    # made 2026-09-24 by `python -m hato.dev keygen` (RUNBOOK 11a)
    u"ug+nhSWr5m0qPoBK1a0Kr6AcWUvm7rnqCKSzTAaFUeo=",
)

#: Every program folder carries these. A manifest missing one is refused.
REQUIRED_ENTRIES = (u"hato.exe", u"hato-cli.exe", u"hato-watch.exe",
                    u"hato-update.exe", u"_internal")
#: Entries that are FOLDERS. Everything else named in a manifest is a file.
FOLDER_ENTRIES = (u"_internal",)
MAX_NOTES = 8
MAX_NOTE_CHARS = 200

#: ⛔ ASCII digits, no leading zero, the WHOLE string (ADVERSARY 2026-09-24, A7): `\d`
#: took any Unicode digit, `$` a trailing newline, and `01.0.4` read as 1.0.4 -- while
#: this layer compares versions as STRINGS (skipped, staged, kept) in six places.
_VERSION = re.compile(r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\Z")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
#: ⛔ A plain name: no separator, no drive, no '..'. The entries steer RENAMES in a
#: person's program folder, so this is a second wall behind the signature.
#: ⚠ A leading `_` is allowed: `_internal` is the runtime's own folder, and the first
#: version of this pattern refused it -- caught by the suite's accepted control.
_ENTRY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
_CONTROL = re.compile(u"[\x00-\x1f\x7f-\x9f]")


#: What reading a JSON file this code did not write can raise. ⚠ RecursionError is
#: NOT a ValueError: 60 KB of `[` escaped every reader here (ADVERSARY 2026-09-24, A1).
_UNREADABLE = (OSError, ValueError, RecursionError)


class ManifestError(ValueError):
    u"""The manifest cannot be trusted as written. Nothing is installed from it."""


def parse_version(text):
    u"""'1.0.4' -> (1, 0, 4); anything else -> None.

    ⚠ STRICT X.Y.Z, and that is measured on the design this copies: surasura's own
    doc records its tag saying 2.2.0 while the app said 2.2, and as tuples
    (2, 2) < (2, 2, 0) -- a copy was offered ITSELF as an update. One shape, or
    nothing."""
    if not isinstance(text, str):
        return None
    match = _VERSION.match(text)
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(candidate, current):
    u"""True when `candidate` is a strictly later X.Y.Z than `current`.
    ⛔ An unreadable version on either side is never newer (fail closed)."""
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


class Manifest(object):
    u"""What one release says about itself. Built by `parse_manifest` or by
    `hato.dev.signing.build_manifest`; never edited after."""

    __slots__ = ("version", "zip_name", "zip_size", "zip_sha256", "min_from",
                 "critical", "notes", "entries")

    def __init__(self, version, zip_name, zip_size, zip_sha256, min_from,
                 critical, notes, entries):
        self.version, self.zip_name, self.zip_size = version, zip_name, zip_size
        self.zip_sha256, self.min_from, self.critical = zip_sha256, min_from, critical
        self.notes = tuple(notes)
        self.entries = dict(entries)

    def as_dict(self):
        return {u"format": FORMAT, u"version": self.version,
                u"zip": {u"name": self.zip_name, u"size": self.zip_size,
                         u"sha256": self.zip_sha256},
                u"min_from": self.min_from, u"critical": self.critical,
                u"notes": list(self.notes), u"entries": dict(self.entries)}

    def __eq__(self, other):
        return isinstance(other, Manifest) and self.as_dict() == other.as_dict()

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return u"<Manifest %s, %d entries>" % (self.version, len(self.entries))


def manifest_bytes(manifest):
    u"""The canonical bytes of a manifest -- what is signed and what is published.
    ⚠ The signature covers these exact BYTES, so the published file is written
    from here and never re-serialised by anything else."""
    return (json.dumps(manifest.as_dict(), indent=2, sort_keys=True,
                       ensure_ascii=False) + u"\n").encode("utf-8")


def _need(obj, name, kind):
    value = obj.get(name)
    # ⚠ bool is an int in Python: `"size": true` must not read as a size of 1.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ManifestError(u"`%s` is missing or not a %s" % (name, kind.__name__))
    return value


def parse_manifest(raw):
    u"""The bytes of `update.json` -> Manifest, or ManifestError naming what is wrong.

    ⛔ STRICT, because it steers what is written into a person's program folder:
    every field present and of its kind; the zip named for the version; `min_from`
    no later than the version; every entry a plain name; each file with its sha256
    and each folder without one."""
    try:
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except RecursionError:
        # 🚨 ADVERSARY 2026-09-24 A1: read for its NOTES before the signature, so
        # anyone able to publish a release could raise out of every check.
        raise ManifestError(u"not JSON hato can read (nested too deeply)")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError(u"not JSON (%s)" % exc)
    if not isinstance(data, dict):
        raise ManifestError(u"not a JSON object")
    fmt = _need(data, u"format", int)
    if fmt != FORMAT:
        raise ManifestError(u"format %d; this hato reads format %d" % (fmt, FORMAT))
    version = _need(data, u"version", str)
    if parse_version(version) is None:
        raise ManifestError(u"`version` %r is not X.Y.Z" % version)
    zip_ = _need(data, u"zip", dict)
    zip_name = _need(zip_, u"name", str)
    if zip_name != ZIP_TEMPLATE % version:
        raise ManifestError(u"the zip is named %r; version %s's is %r"
                            % (zip_name, version, ZIP_TEMPLATE % version))
    zip_size = _need(zip_, u"size", int)
    if zip_size <= 0:
        raise ManifestError(u"the zip's size is %d" % zip_size)
    zip_sha256 = _need(zip_, u"sha256", str)
    if not _SHA256.match(zip_sha256):
        raise ManifestError(u"the zip's sha256 is not 64 lowercase hex digits")
    min_from = _need(data, u"min_from", str)
    if parse_version(min_from) is None or is_newer(min_from, version):
        raise ManifestError(u"`min_from` %r is not an X.Y.Z at or before %s"
                            % (min_from, version))
    critical = _need(data, u"critical", bool)
    notes = _need(data, u"notes", list)
    if len(notes) > MAX_NOTES:
        raise ManifestError(u"%d notes; at most %d" % (len(notes), MAX_NOTES))
    for note in notes:
        if (not isinstance(note, str) or not note.strip()
                or len(note) > MAX_NOTE_CHARS or _CONTROL.search(note)):
            raise ManifestError(u"a note is empty, too long, or not plain text")
    entries = _need(data, u"entries", dict)
    for name, digest in entries.items():
        if not _ENTRY.match(name) or name in (u".", u".."):
            raise ManifestError(u"entry %r is not a plain name" % name)
        if name in FOLDER_ENTRIES:
            if digest != u"":
                raise ManifestError(u"%s is a folder and carries no sha256" % name)
        elif not isinstance(digest, str) or not _SHA256.match(digest):
            raise ManifestError(u"file entry %r has no sha256" % name)
    missing = [name for name in REQUIRED_ENTRIES if name not in entries]
    if missing:
        raise ManifestError(u"the program folder would lack %s" % u", ".join(missing))
    return Manifest(version, zip_name, zip_size, zip_sha256, min_from, critical,
                    notes, entries)


def verify_signature(raw, signature_text, keys=None):
    u"""True only when `signature_text` is an Ed25519 signature of exactly `raw` by
    one of `keys` (default: PUBLIC_KEYS). ⛔ Anything else -- garbled, the wrong
    length, the wrong key, a changed byte, no PyCryptodome, no key at all -- is
    False. Never raises: the answer to "can this be proven?" is yes or no."""
    keys = PUBLIC_KEYS if keys is None else keys
    try:
        text = signature_text.decode("ascii") if isinstance(signature_text, bytes) \
            else signature_text
        signature = base64.b64decode(text.strip(), validate=True)
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return False
    if len(signature) != 64 or not keys:
        return False
    try:
        from Cryptodome.Signature import eddsa
    except ImportError:
        return False                          # cannot prove it -> not proven
    for key in keys:
        try:
            public = eddsa.import_public_key(base64.b64decode(key, validate=True))
            eddsa.new(public, u"rfc8032").verify(raw, signature)
            return True
        except (ValueError, TypeError):
            continue
    return False


def sha256_file(path, chunk=1 << 20):
    u"""-> the lowercase hex sha256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


# ===========================================================================
# 11b -- THE CHECK: is a newer hato out, and can THIS copy take it?
# ===========================================================================

LATEST_URL = u"https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = u"https://github.com/%s/releases/latest" % REPO
#: The release's own JSON, and the manifest -- read whole, and never more than this.
MAX_RELEASE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 1024
#: On its own, at most once a day. *Check now* asks whenever it is pressed.
CHECK_EVERY_SECONDS = 24 * 3600

NONE, READY, TELL = u"none", u"ready", u"tell"

#: Why a newer release is only TOLD, never installed here -- the window words each.
SOURCE = u"source"            # run from a checkout: updating it is git's job
PLATFORM = u"platform"        # not Windows: there is no packaged build to install
FOLDER = u"folder"            # the program folder cannot be written
UNSIGNED = u"unsigned"        # no signature, or not one hato trusts
UNREADABLE = u"manifest"      # the release carries no manifest, or an unreadable one
MISMATCH = u"mismatch"        # the tag, the manifest and GitHub's record of the zip disagree
TOO_OLD = u"too_old"          # this copy is older than the release's `min_from`
#: ⭐ RUNBOOK 12e -- NONE's reason when GitHub refused an address that asked too often
#: (60 an hour, unauthenticated): a WAIT, said as one, never "GitHub did not answer".
RATE_LIMITED = u"rate_limited"


class FetchError(Exception):
    u"""A request that did not bring back what was asked for. Never shown raw.
    `limited`: GitHub refused because this address asked too often -- 403 with no
    requests left, or 429. A wait, not an outage (RUNBOOK 12e)."""

    def __init__(self, message=u"", limited=False):
        Exception.__init__(self, message)
        self.limited = bool(limited)


class Decision(object):
    u"""What one check concluded. `manifest` and `zip_url` only on READY."""

    __slots__ = ("kind", "version", "reason", "notes", "critical", "page",
                 "manifest", "zip_url")

    def __init__(self, kind, version=None, reason=None, notes=(), critical=False,
                 page=RELEASES_PAGE, manifest=None, zip_url=None):
        self.kind, self.version, self.reason = kind, version, reason
        self.notes, self.critical, self.page = tuple(notes), bool(critical), page
        self.manifest, self.zip_url = manifest, zip_url

    def as_dict(self):
        return {u"kind": self.kind, u"version": self.version, u"reason": self.reason,
                u"notes": list(self.notes), u"critical": self.critical,
                u"page": self.page, u"zip_url": self.zip_url,
                u"size": self.manifest.zip_size if self.manifest is not None else None}

    def __repr__(self):
        return u"<Decision %s %s %s>" % (self.kind, self.version, self.reason or u"")


def user_agent():
    from hato import __version__
    return u"hato/%s (+https://github.com/%s)" % (__version__, REPO)


def fetch(url, limit):
    u"""GET `url` -> its bytes, never more than `limit`. Raises FetchError.

    ⛔ HATO_NO_NETWORK=1 refuses before a socket exists, as the jimaku client does
    -- the suite sets it, and a check that reached GitHub from a test would be the
    suite spending someone else's budget."""
    import os
    if os.environ.get("HATO_NO_NETWORK") == "1":
        raise FetchError(u"the network is switched off (HATO_NO_NETWORK)")
    try:
        import requests
    except ImportError:
        raise FetchError(u"requests is not installed")
    try:
        with requests.get(url, headers={u"User-Agent": user_agent(),
                                        u"Accept": u"application/vnd.github+json"},
                          timeout=15, stream=True) as response:
            if response.status_code != 200:
                code, left = response.status_code, response.headers.get(
                    u"X-RateLimit-Remaining")
                # ⭐ 12e: a WAIT -- 429; 403 with no requests left; or 403 carrying
                # `Retry-After`, GitHub's secondary limit (the Layer 12 pass, L12-5)
                wait = response.headers.get(u"Retry-After") is not None
                raise FetchError(u"answered %d" % code,
                                 limited=code == 429 or (code == 403 and left == u"0")
                                 or (code == 403 and wait))
            body = bytearray()
            for block in response.iter_content(64 * 1024):
                body.extend(block)
                if len(body) > limit:
                    raise FetchError(u"more than %d bytes" % limit)
            return bytes(body)
    except requests.RequestException as exc:
        raise FetchError(u"%s" % type(exc).__name__)


def _writable(folder):
    u"""True when a file can really be made in `folder` -- MEASURED, never assumed
    from a path: a Program Files install and a read-only share both look fine."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(dir=str(folder), prefix=u".hato-probe-"):
            return True
    except OSError:
        return False


def _read_manifest(assets, get):
    u"""-> (raw, signature text) for the release's manifest pair, or (None, None)."""
    manifest, signature = assets.get(MANIFEST_NAME), assets.get(SIGNATURE_NAME)
    if not manifest or not signature:
        return None, None
    try:
        raw = get(manifest[u"browser_download_url"], MAX_MANIFEST_BYTES)
        sig = get(signature[u"browser_download_url"], MAX_SIGNATURE_BYTES)
        return raw, sig.decode("ascii", "replace")
    except (KeyError, TypeError, AttributeError):
        return None, None
    # ⚠ a FetchError is NOT caught here: a request that failed is "could not tell"
    # (`_decide`), never "this release cannot be installed" -- remembered a day


def check(current, get=None, frozen=None, windows=None, install_dir=None, keys=None):
    u"""Is a newer hato out, and can THIS copy take it? -> Decision. ⛔ Never raises:
    whatever escapes the decision below is NONE -- the window, the tray and a
    command all call this, and one release must not be able to stop them asking
    (ADVERSARY 2026-09-24, A1)."""
    try:
        return _decide(current, get, frozen, windows, install_dir, keys)
    except Exception:                         # noqa: BLE001 -- the claim above, kept
        return Decision(NONE)


def _decide(current, get=None, frozen=None, windows=None, install_dir=None, keys=None):
    u"""The decision itself -- `check` is its only caller.

    ⛔ FAIL SILENT for the check (surasura: offline is silent): no network, a rate
    limit, no release, a garbled answer -> NONE. ⛔ FAIL CLOSED for installing: a
    newer release this copy cannot take, or cannot PROVE, is TELL with the reason.
    Only a signed, consistent release that a packaged Windows copy can write is
    READY. ⚠ Source and platform are asked FIRST: a checkout is told `git pull`,
    never about signatures it has no use for."""
    import os
    import sys
    get = fetch if get is None else get
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    windows = sys.platform.startswith("win") if windows is None else windows
    try:
        release = json.loads(get(LATEST_URL, MAX_RELEASE_BYTES).decode("utf-8"))
        tag = release[u"tag_name"]
        assets = dict((a[u"name"], a) for a in release.get(u"assets") or ()
                      if isinstance(a, dict) and isinstance(a.get(u"name"), str))
    except FetchError as exc:
        # ⭐ RUNBOOK 12e: asked too often is a WAIT -- and like every NONE without a
        # version, never remembered
        return Decision(NONE, reason=RATE_LIMITED if exc.limited else None)
    except (ValueError, UnicodeDecodeError, KeyError, TypeError, AttributeError):
        return Decision(NONE)
    version = tag[1:] if isinstance(tag, str) and tag.startswith(u"v") else tag
    if not is_newer(version, current):
        return Decision(NONE, version=version if parse_version(version) else None)
    page = release.get(u"html_url") if isinstance(release.get(u"html_url"), str) \
        else RELEASES_PAGE

    try:
        raw, signature = _read_manifest(assets, get)
    except FetchError as exc:
        # 🚨 THE LAYER 12 PASS, L12-6: throttled on the SECOND request, the answer was
        # TELL/manifest -- remembered for a day as *"can't be installed from inside
        # hato"*, and the tray acts only on READY. For a copy that installs, a request
        # that failed is NONE (never remembered); a checkout wants only the notes.
        if frozen and windows:
            return Decision(NONE, reason=RATE_LIMITED if exc.limited else None)
        raw, signature = None, None
    shown = ()
    if raw is not None:
        try:
            shown = parse_manifest(raw).notes    # display only, until it is proven
        except ManifestError:
            pass

    def tell(reason):
        return Decision(TELL, version, reason, notes=shown, page=page)

    if not frozen:
        return tell(SOURCE)
    if not windows:
        return tell(PLATFORM)
    if raw is None:
        return tell(UNREADABLE)
    if not verify_signature(raw, signature, keys):
        return tell(UNSIGNED)
    try:
        manifest = parse_manifest(raw)
    except ManifestError:
        return tell(UNREADABLE)
    zip_asset = assets.get(manifest.zip_name)
    digest = zip_asset.get(u"digest") if isinstance(zip_asset, dict) else None
    if (manifest.version != version or not isinstance(zip_asset, dict)
            or zip_asset.get(u"size") != manifest.zip_size
            or not isinstance(zip_asset.get(u"browser_download_url"), str)
            # ⚠ FAIL OPEN ON AN ABSENT FIELD, CLOSED ON A DIFFERENT ONE: GitHub
            # added `digest` in 2025, and the signed manifest already names the
            # hash. Present and different means two records of one zip disagree.
            or (digest is not None and digest != u"sha256:" + manifest.zip_sha256)):
        return tell(MISMATCH)
    if is_newer(manifest.min_from, current):
        return tell(TOO_OLD)
    folder = install_dir if install_dir is not None else os.path.dirname(sys.executable)
    if not _writable(folder):
        return tell(FOLDER)
    return Decision(READY, version, notes=manifest.notes, critical=manifest.critical,
                    page=page, manifest=manifest, zip_url=zip_asset[u"browser_download_url"])


# ---------------------------------------------------------------------------
# what was last concluded -- so the window and the tray ask GitHub once a day
# ---------------------------------------------------------------------------

STATE_NAME = u"update-state.json"


def state_path():
    from hato import paths
    return paths.data_root() / STATE_NAME


def load_state(path=None):
    u"""-> the saved state, or {} -- ⛔ never raises: a broken file means *ask again*."""
    try:
        with open(str(path or state_path()), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except _UNREADABLE:
        return {}


def save_state(state, path=None):
    u"""Temp-plus-rename (LEDGER-HOT.md): a failed write never leaves half a file."""
    import os
    path = str(path or state_path())
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temp = path + u".new"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(temp, path)


def due(state, now):
    u"""True when a check is owed: never checked, or the last one a day old. ⚠ A
    `checked_at` in the FUTURE (a clock set back) is owed too, not trusted."""
    at = state.get(u"checked_at")
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return True
    return not (0 <= now - at < CHECK_EVERY_SECONDS)


def remember(decision, now, path=None):
    u"""Save what a check concluded, keeping the version a person skipped."""
    state = load_state(path)
    state[u"checked_at"] = now
    state[u"decision"] = decision.as_dict()
    save_state(state, path)
    return state


# ===========================================================================
# 11c -- STAGING: download it, prove it, unpack it -- while hato keeps running
# ===========================================================================
#
# Everything that can fail slowly -- the network, the hash, a bad zip -- happens
# HERE, while the person's hato is still open and nothing of theirs has moved
# (surasura's strongest rule). After it, only local renames are left, and those
# are the swapper's (`hato/swap.py`).

PENDING_NAME = u"pending.json"
#: ⭐ Go back's OWN hand-off (ADVERSARY 2026-09-24, C4): written over pending.json,
#: a Go back that failed left the newer staged release pointing BACK, and *Restart
#: now* went back to 1.0.4 instead of on to 1.0.6.
GO_BACK_NAME = u"goback.json"
RESULT_NAME = u"result.json"
#: Every top-level name any hato program folder has carried. The installed version's
#: own entries are these, as found on disk -- ⛔ anything else in that folder is a
#: person's own, and nothing ever moves it. A release that DROPS an entry keeps its
#: name here, so the old copy still moves out rather than lingering.
KNOWN_ENTRIES = frozenset([u"hato.exe", u"hato-cli.exe", u"hato-watch.exe",
                           u"hato-update.exe", u"_internal", u"LICENSE", u"README.md",
                           u"THIRD_PARTY_LICENSES.md"])
#: A program zip is ~70 MB and unpacks to ~130: walls, not a subtitle archive's caps.
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
MAX_BUNDLE_MEMBERS = 5000
_S_IFMT, _S_IFLNK = 0o170000, 0o120000


class StageError(Exception):
    u"""Staging stopped, and everything it wrote is gone. `str()` is a sentence a
    person can read -- ⛔ never a traceback, never the engine's vocabulary."""


def _existing(path):
    import os
    path = os.path.abspath(str(path))
    while not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def same_volume(a, b):
    u"""True when `a` and `b` (or their nearest existing folders) share a volume."""
    import os
    try:
        return os.stat(_existing(a)).st_dev == os.stat(_existing(b)).st_dev
    except OSError:
        return False


def stage_root(install_dir):
    u"""Where an update is prepared -> Path, on the SAME VOLUME as the install.

    ⭐ The swap is a set of RENAMES, and a rename is instant and atomic only within
    one volume. `%LOCALAPPDATA%\\hato\\update` when it shares the install's volume
    -- the common case, and a synced Desktop then never uploads what is staged --
    else a hidden folder beside the install."""
    import os
    from pathlib import Path
    from hato import paths
    # 🚨 ONE ROOT PER INSTALL (ADVERSARY 2026-09-24, A6): two copies of hato on one
    # volume shared `update\`, so one copy found the OTHER's stage waiting -- and its
    # hand-off swapped the other folder. The folder's name, then its path's hash.
    install = Path(install_dir).resolve()
    name = u"".join(c if c.isascii() and (c.isalnum() or c in u"._-") else u"_"
                    for c in install.name)[:24] or u"hato"
    key = u"%s-%s" % (name, hashlib.sha256(os.path.normcase(str(install))
                                          .encode("utf-8")).hexdigest()[:10])
    data = paths.data_root() / u"update"
    if same_volume(data, install_dir):
        return data / key
    return install.parent / u".hato-update" / key


def same_folder(a, b):
    u"""True when `a` and `b` name one folder, however each was spelled."""
    import os
    try:
        return os.path.normcase(os.path.realpath(str(a))) == \
            os.path.normcase(os.path.realpath(str(b)))
    except (TypeError, ValueError, OSError):
        return False


def _inside(root, path):
    import os
    root, path = os.path.abspath(str(root)), os.path.abspath(str(path))
    return path.startswith(root + os.sep)


def _remove(root, path):
    u"""Remove `path` -- ⛔ ONLY if it lies inside `root`: every sweep here is
    scoped by shape (doctrine/robustness), never by a list of names to spare."""
    import os
    import shutil
    if not _inside(root, path) or not os.path.lexists(str(path)):
        return
    if os.path.isdir(str(path)) and not os.path.islink(str(path)):
        shutil.rmtree(str(path), ignore_errors=True)
    else:
        try:
            os.remove(str(path))
        except OSError:
            pass


def stream(url):
    u"""Yield the body of `url` in blocks -- the one place a program zip is fetched."""
    import os
    if os.environ.get("HATO_NO_NETWORK") == "1":
        raise StageError(u"the network is switched off, so nothing was downloaded")
    try:
        import requests
        with requests.get(url, headers={u"User-Agent": user_agent()}, timeout=30,
                          stream=True) as response:
            if response.status_code != 200:
                raise StageError(u"GitHub answered %d for the download" % response.status_code)
            for block in response.iter_content(1024 * 1024):
                if block:
                    yield block
    except ImportError:
        raise StageError(u"requests is not installed, so nothing was downloaded")
    except StageError:
        raise
    except Exception as exc:                  # noqa: BLE001 -- a sentence, never a traceback
        raise StageError(u"the download stopped (%s)" % type(exc).__name__)


def download(url, dest, size, sha256, progress=None, get=None):
    u"""Stream `url` into `dest`, never past `size` bytes. -> dest.

    ⛔ Written as `dest.part` and renamed only when every byte is counted and the
    hash is the manifest's; any difference removes the part and says so."""
    import os
    get = stream if get is None else get
    part = str(dest) + u".part"
    digest = hashlib.sha256()
    done = 0
    try:
        with open(part, "wb") as out:
            for block in get(url):
                done += len(block)
                if done > size:
                    raise StageError(u"the download ran past the %d bytes the release "
                                     u"names" % size)
                digest.update(block)
                out.write(block)
                if progress is not None:
                    progress(done, size)
        if done != size or digest.hexdigest() != sha256:
            raise StageError(u"the download does not match the release -- it was damaged "
                             u"or replaced on the way, so it was thrown away")
        os.replace(part, str(dest))
        return dest
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def unpack(zip_path, into):
    u"""The zip's one `hato/` folder -> under `into` (made here). -> the hato folder.

    ⛔ EVERY MEMBER IS JUDGED BEFORE A BYTE IS WRITTEN (archives.py's order): inside
    `hato/`, a safe name by archives' own rules, no link, and the counts and sizes
    within their walls. Written under `into.part` and renamed whole."""
    import os
    import shutil
    import zipfile
    from hato import archives
    part = str(into) + u".part"
    if os.path.isdir(part):
        shutil.rmtree(part, ignore_errors=True)
    try:
        archive = zipfile.ZipFile(str(zip_path))
    except (zipfile.BadZipFile, OSError) as exc:
        raise StageError(u"the download is not a readable zip (%s)" % type(exc).__name__)
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_BUNDLE_MEMBERS:
            raise StageError(u"the zip lists %d entries -- not a hato release" % len(infos))
        total = 0
        for info in infos:
            problem = archives.unsafe_name(info.filename)
            parts = info.filename.replace(u"\\", u"/").split(u"/")
            if problem or parts[0] != u"hato":
                raise StageError(u"a file in the zip would land outside hato's folder, so "
                                 u"none of it was unpacked")
            if (info.external_attr >> 16) & _S_IFMT == _S_IFLNK:
                raise StageError(u"the zip holds a link, so none of it was unpacked")
            total += info.file_size
        if total > MAX_BUNDLE_BYTES:
            raise StageError(u"the zip unpacks to more than hato ever is")
        try:
            os.makedirs(part)
            for info in infos:
                target = os.path.join(part, *[p for p in info.filename.replace(
                    u"\\", u"/").split(u"/") if p])
                if not _inside(part, target):
                    raise StageError(u"a file in the zip would land outside hato's folder")
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.open(info) as source, open(target, "wb") as out:
                    shutil.copyfileobj(source, out, 1024 * 1024)
            if os.path.isdir(str(into)):
                shutil.rmtree(str(into), ignore_errors=True)
            os.replace(part, str(into))
        except BaseException:
            shutil.rmtree(part, ignore_errors=True)
            raise
    return os.path.join(str(into), u"hato")


def installed_version(folder):
    u"""What the unpacked `hato-cli.exe --version` says -> 'X.Y.Z' or None.
    ⭐ The BYTES ARE THE VERSION ON THE TIN (smoke 4c), asked of the staged copy."""
    import os
    import re as _re
    import subprocess
    exe = os.path.join(str(folder), u"hato-cli.exe")
    try:
        from hato.gui import run as _run
        extra = _run.no_console_kwargs()
    except Exception:                         # noqa: BLE001
        extra = {}
    try:
        done = subprocess.run([exe, u"--version"], capture_output=True, timeout=60, **extra)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _re.search(r"hato (\d+\.\d+\.\d+)", done.stdout.decode("utf-8", "replace"))
    return match.group(1) if match else None


def validate(folder, manifest, version_of=None):
    u"""The unpacked program IS the manifest's: exactly its entries, each file its
    hash, each folder a folder -- and, frozen, the version it reports."""
    import os
    names = set(os.listdir(str(folder)))
    want = set(manifest.entries)
    if names != want:
        extra, missing = sorted(names - want), sorted(want - names)
        raise StageError(u"the unpacked program is not the release's (%s)" % u"; ".join(
            ([u"not listed: " + u", ".join(extra)] if extra else []) +
            ([u"missing: " + u", ".join(missing)] if missing else [])))
    for name, digest in manifest.entries.items():
        path = os.path.join(str(folder), name)
        if name in FOLDER_ENTRIES:
            if not os.path.isdir(path):
                raise StageError(u"%s should be a folder" % name)
        elif not os.path.isfile(path) or sha256_file(path) != digest:
            raise StageError(u"%s is not the file the release names" % name)
    if version_of is not None:
        said = version_of(folder)
        if said is None:
            # ⛔ not "reports None, not 1.0.5" (ADVERSARY 2026-09-24, A2): a program
            # that will not start -- a security program holding a new exe -- is this
            raise StageError(u"the downloaded hato would not start to say its version, so "
                             u"it was not kept")
        if said != manifest.version:
            raise StageError(u"the downloaded hato says it is %s, not %s, so it was not "
                             u"kept" % (said, manifest.version))


def save_json(path, data):
    u"""Temp-plus-rename, never a half-written file (LEDGER-HOT.md)."""
    import os
    temp = str(path) + u".new"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(temp, str(path))


def stage(decision, current, install_dir, progress=None, get=None, version_of=None,
          root=None):
    u"""Download, prove and unpack a READY release; write the hand-off. -> pending path.

    `pending.json` is the WHOLE contract with the swapper: every path it will touch
    is in it, so the swapper knows nothing about where hato keeps anything. The
    apply step (11f / 11g) sets `window` / `tray` in it before the swapper starts.
    ⛔ Any failure removes what this call wrote and raises StageError."""
    import os
    if decision.kind != READY or decision.manifest is None:
        raise StageError(u"there is no release ready to install")
    manifest = decision.manifest
    root = stage_root(install_dir) if root is None else root
    download_dir = os.path.join(str(root), u"download")
    staged_dir = os.path.join(str(root), u"staged", manifest.version)
    # ⭐ STAGING STARTS FROM NOTHING: a release staged and never installed (a newer
    # one came out first) is ~130 MB, and a download a crash cut off lingers as a
    # `.part`. ⛔ Scoped by shape, inside `root` -- `previous\` (Go back) and
    # result.json (the window may not have read it yet) are never touched.
    for area in (os.path.join(str(root), u"staged"), download_dir):
        for name in (os.listdir(area) if os.path.isdir(area) else ()):
            _remove(root, os.path.join(area, name))
    for name in (os.listdir(str(root)) if os.path.isdir(str(root)) else ()):
        if name.startswith(u"hato-update-") and name.endswith((u".exe", u".exe.part")):
            _remove(root, os.path.join(str(root), name))  # a spent swapper; one in use stays
    _remove(root, os.path.join(str(root), PENDING_NAME))
    os.makedirs(download_dir, exist_ok=True)
    zip_path = os.path.join(download_dir, manifest.zip_name)
    try:
        download(decision.zip_url, zip_path, manifest.zip_size, manifest.zip_sha256,
                 progress, get)
        folder = unpack(zip_path, staged_dir)
        validate(folder, manifest, version_of)
        install = os.path.abspath(str(install_dir))
        mine = KNOWN_ENTRIES | set(manifest.entries)
        pending = {u"format": 1, u"from": current, u"to": manifest.version,
                   u"install": install, u"staged": folder,
                   u"previous": os.path.join(str(root), u"previous", current),
                   u"entries": dict(manifest.entries),
                   u"old_entries": sorted(n for n in os.listdir(install) if n in mine),
                   u"result": os.path.join(str(root), RESULT_NAME),
                   u"window": False, u"tray": False}
        save_json(os.path.join(str(root), PENDING_NAME), pending)
    except BaseException:
        _remove(root, staged_dir)
        _remove(root, zip_path)
        raise
    _remove(root, zip_path)                   # proven and unpacked: the zip is spent
    return os.path.join(str(root), PENDING_NAME)


# ===========================================================================
# THE HAND-OFF -- the swapper started, and its caller gone (11d · 11f · 11g)
# ===========================================================================
#
# ONE function starts the swapper, whoever asks: the window's *Restart now* and
# *When I close hato*, the tray's quiet install, and `hato update --apply` /
# `--rollback`. What differs between them is only what to start again afterwards.

SWAPPER_NAME = u"hato-update.exe"


def swapper_copy_name(version):
    u"""The swapper's file name in the staging root -- ONE PER TARGET VERSION: a
    running exe can be renamed but never replaced, so a copy an earlier hand-off
    left running must never be what this one has to overwrite."""
    return u"hato-update-%s.exe" % version


def start_detached(argv):
    u"""Start `argv` so it OUTLIVES its caller -> the process: its own process group,
    no console, nothing inherited -- and out of the caller's job object when the job
    allows it (a terminal may run hato inside one that kills its children on exit)."""
    import os
    import subprocess
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) |
             getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, close_fds=True,
                  cwd=os.path.dirname(os.path.abspath(argv[0])))
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    if breakaway:
        try:
            return subprocess.Popen(argv, creationflags=flags | breakaway, **kwargs)
        except OSError:
            pass                              # a job that forbids breaking away
    return subprocess.Popen(argv, creationflags=flags, **kwargs)


def hand_off(pending_path, window=False, tray=False, tray_pid_file=None, quiet=False,
             swapper=None, start=None, current=None, install=None):
    u"""Start the swapper on a hand-off -> the started process.

    ⛔ THE CALLER QUITS THE MOMENT THIS RETURNS -- the window closes itself, the tray
    exits: the swapper waits for EVERY process whose program lives in the install
    folder, and gives up (touching nothing) after a minute.

    ⭐ It runs from the STAGING ROOT, never from the folder it is about to empty, and
    it is the NEW version's own copy (`swapper=None`: the staged payload's) -- a fix
    to the swapper travels with the release that needs it. *Go back* hands in the
    CURRENT one instead: that version wrote the hand-off, so it is the one that
    reads it.

    `window` / `tray`: what the swapper starts again once the files are in place.
    `tray_pid_file`: where a new tray records itself -- the swapper's proof that it
    is really watching.

    ⛔ `current` / `install` -- the copy handing off, and every production caller
    names both (ADVERSARY 2026-09-24): a hand-off not written BY this version, or
    one that is not newer (A3: `--apply` put 1.0.2 over a hand-installed 1.0.3), or
    one written for ANOTHER copy's folder (A6), is refused before the swapper
    exists. Go back is the one hand-off to an older version, and says so."""
    import os
    import shutil
    try:
        with open(str(pending_path), encoding="utf-8") as handle:
            pending = json.load(handle)
        staged, version = pending[u"staged"], pending[u"to"]
    except _UNREADABLE + (KeyError, TypeError) as exc:
        raise StageError(u"there is no update ready to install (%s)" % type(exc).__name__)
    if parse_version(version) is None:
        raise StageError(u"the hand-off names no version")
    if install is not None and not same_folder(pending.get(u"install"), install):
        raise StageError(u"what is waiting to install was prepared for another copy of "
                         u"hato, so it was not used")
    if current is not None and pending.get(u"from") != current:
        raise StageError(u"what is waiting to install was prepared by hato %s, not this %s "
                         u"-- it will be downloaded again" % (pending.get(u"from"), current))
    if current is not None and not pending.get(u"going_back") \
            and not is_newer(version, current):
        raise StageError(u"hato %s is not newer than this %s, so it was not installed"
                         % (version, current))
    source = str(swapper) if swapper else os.path.join(str(staged), SWAPPER_NAME)
    if not os.path.isfile(source):
        raise StageError(u"this copy's updater is missing, so hato cannot go back"
                         if pending.get(u"going_back") else
                         u"the new version carries no updater")
    root = os.path.dirname(os.path.abspath(str(pending_path)))
    target = os.path.join(root, swapper_copy_name(version))
    part = target + u".part"
    try:
        shutil.copyfile(source, part)
        os.replace(part, target)
    except OSError as exc:
        _remove(root, part)
        raise StageError(u"the updater could not be put in place (%s)" % exc.__class__.__name__)
    from hato import paths
    pending.update({u"window": bool(window), u"tray": bool(tray),
                    u"tray_pid_file": str(tray_pid_file) if tray_pid_file else None,
                    u"log": str(paths.default_log_path())})
    save_json(pending_path, pending)
    argv = [target, u"--pending", os.path.abspath(str(pending_path))]
    if quiet:
        argv.append(u"--quiet")
    return (start or start_detached)(argv)


def staged_version(install_dir, current, root=None):
    u"""The release staged and waiting to be installed -> 'X.Y.Z', or None.

    ⭐ READ FROM THE DISK, never remembered: the window, the tray and a command each
    ask it, and the staged folder must still be there. ⛔ A *Go back* hand-off is
    not a release waiting, and neither is a version no newer than this copy."""
    import os
    root = stage_root(install_dir) if root is None else root
    try:
        with open(os.path.join(str(root), PENDING_NAME), encoding="utf-8") as handle:
            pending = json.load(handle)
        version, staged = pending[u"to"], pending[u"staged"]
    except _UNREADABLE + (KeyError, TypeError):
        return None
    entries = pending.get(u"entries")
    if pending.get(u"going_back") or not is_newer(version, current) \
            or not os.path.isdir(str(staged)):
        return None
    # 🚨 WHOLE, AND THIS COPY'S (ADVERSARY 2026-09-24): a stage that LOST a file
    # after it was proven -- a security program quarantining the new updater -- read
    # as waiting until a newer release came out, every hand-off failing (A5); and a
    # second copy of hato on the volume found the first one's (A6). ⚠ And one that
    # lists NOTHING is no stage: `all()` of nothing is true (the 11z gate, G1).
    if not isinstance(entries, dict) or not entries or not all(
            os.path.lexists(os.path.join(str(staged), name)) for name in entries):
        return None
    if not same_folder(pending.get(u"install"), install_dir):
        return None
    # 🚨 AND PREPARED BY THIS VERSION (the Layer 12 pass, L12-1): 1.0.5's tray staged
    # 1.0.6, then a Go back to 1.0.4 -- `hand_off` refuses it (*"it will be downloaded
    # again"*), and read as waiting it was never downloaded again: a pill for ever, and
    # `--stage` answering *staged* without a byte. The wall `hand_off` already has.
    if pending.get(u"from") != current:
        return None
    return version


def kept_version(install_dir, current, root=None):
    u"""The version kept for *Go back* -> 'X.Y.Z', or None when there is none whole.
    ⭐ The window's *Go back to X* exists only while this answers (the frozen rule:
    controls vanish when they would be meaningless)."""
    import os
    root = stage_root(install_dir) if root is None else root
    kept = os.path.join(str(root), u"previous")
    try:
        names = os.listdir(kept)
    except OSError:
        return None
    for version in sorted((n for n in names if parse_version(n) and n != current),
                          key=parse_version, reverse=True):
        folder = os.path.join(kept, version)
        if all(os.path.lexists(os.path.join(folder, e)) for e in REQUIRED_ENTRIES
               if e != SWAPPER_NAME):
            return version
    return None


def go_back_pending(install_dir, current, root=None):
    u"""A hand-off that puts the KEPT version back -> the pending path.

    The same contract `stage` writes, so the same swapper, the same proof and the
    same way back: the kept folder is what is swapped IN, and the current version is
    kept in its place -- *Go back* can itself be undone. ⭐ The entries are hashed
    NOW, from the kept bytes, so the swapper's check still means *these are the
    files that were kept*. ⛔ The version gone back from is turned away -- but only
    once the Go back WORKED (`reconcile`): turned away here, before a hand-off that
    could still fail, it stayed turned away over a version still running (C4)."""
    import os
    root = stage_root(install_dir) if root is None else root
    version = kept_version(install_dir, current, root)
    if version is None:
        raise StageError(u"there is no earlier version kept to go back to")
    folder = os.path.join(str(root), u"previous", version)
    entries = {}
    for name in sorted(os.listdir(folder)):
        if name in KNOWN_ENTRIES:
            path = os.path.join(folder, name)
            entries[name] = u"" if name in FOLDER_ENTRIES else sha256_file(path)
    install = os.path.abspath(str(install_dir))
    mine = KNOWN_ENTRIES | set(entries)
    pending = {u"format": 1, u"from": current, u"to": version, u"install": install,
               u"staged": folder,
               u"previous": os.path.join(str(root), u"previous", current),
               u"entries": entries,
               u"old_entries": sorted(n for n in os.listdir(install) if n in mine),
               u"result": os.path.join(str(root), RESULT_NAME),
               u"window": False, u"tray": False, u"going_back": True}
    path = os.path.join(str(root), GO_BACK_NAME)
    save_json(path, pending)
    return path


def settings_for_going_back(version, path=None):
    u"""⭐ 14z (ADVERSARY 2026-09-25, C-1/C-2) -- config.toml made readable by the kept
    `version` before it runs (`config.make_readable_by`). -> [what changed, in words].
    ⛔ Called once the hand-off has STARTED -- a failed one changes nothing -- and before
    this process exits: the swapper waits for it, so the kept tray reads the new file.
    ⛔ Never raises: a file that cannot be read or written is left as it is, and the
    swapper's own proof still puts this version back if the kept one cannot start."""
    from hato import config
    try:
        return config.make_readable_by(version, path)
    except (config.ConfigError, OSError):
        return []


def going_back_words(version, path=None):
    u"""⭐ 14z -- what `settings_for_going_back` would change, in words, for the Go back
    card BEFORE the press. -> [words]. Nothing written; never raises."""
    from hato import config
    try:
        return config.readable_by(config.load(path), version)[1]
    except (config.ConfigError, OSError):
        return []


def skip(version, path=None):
    u"""Remember `version` as one not to install automatically; None forgets it
    (*Try again*: the manual choice, one click away)."""
    state = load_state(path)
    if version is None:
        state.pop(u"skipped", None)
    else:
        state[u"skipped"] = version
    save_state(state, path)


def reconcile(install_dir, consume=False, root=None, state_file=None):
    u"""What the last swap came to -> its result dict, or None when there is none.

    ⭐ ONE READER, for the window and the tray. ⛔ A FAILED update is remembered as
    SKIPPED -- the window says *"hato won't try 1.0.5 again on its own"*, and without
    this the tray would stage and install it again every night, in a loop.
    `consume`: the window, which SHOWS the result, takes the file away; the tray
    leaves it for the window to show."""
    import os
    root = stage_root(install_dir) if root is None else root
    path = os.path.join(str(root), RESULT_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            result = json.load(handle)
    except _UNREADABLE:
        return None
    if not isinstance(result, dict):
        return None
    status, going_back = result.get(u"status"), bool(result.get(u"going_back"))
    if status == u"success" and going_back:
        # ⭐ what a person went back FROM -- turned away now that it is gone (C4)
        left = result.get(u"from")
        if parse_version(left) and skipped(state_file) != left:
            skip(left, state_file)
    elif status != u"success" and not going_back and result.get(u"touched"):
        # 🚨 only a swap that TOUCHED the folder failed the release (C3b): one that
        # gave up because hato was still running changed nothing, and turning its
        # release away left it uninstalled for good
        failed_to = result.get(u"to")
        if parse_version(failed_to) and skipped(state_file) != failed_to:
            skip(failed_to, state_file)
    if consume:
        _remove(root, path)
    return result


def skipped(path=None):
    u"""-> the version a person does not want installed automatically, or None."""
    value = load_state(path).get(u"skipped")
    return value if parse_version(value) else None


__all__ = ["CHECK_EVERY_SECONDS", "Decision", "FOLDER", "FOLDER_ENTRIES", "FORMAT",
           "FetchError", "GO_BACK_NAME", "LATEST_URL", "MANIFEST_NAME", "MISMATCH", "Manifest",
           "ManifestError", "NONE", "PENDING_NAME", "PLATFORM", "PUBLIC_KEYS", "RATE_LIMITED",
           "READY",
           "REPO", "REQUIRED_ENTRIES", "RESULT_NAME", "SIGNATURE_NAME", "SOURCE",
           "STATE_NAME", "SWAPPER_NAME", "StageError", "TELL", "TOO_OLD", "UNREADABLE",
           "UNSIGNED", "ZIP_TEMPLATE", "check", "download", "due", "fetch",
           "go_back_pending", "hand_off", "installed_version", "is_newer", "kept_version",
           "load_state", "manifest_bytes", "parse_manifest", "parse_version", "reconcile",
           "remember", "same_volume", "save_json", "save_state", "sha256_file", "skip",
           "same_folder", "skipped", "staged_version",
           "stage", "stage_root", "start_detached", "state_path", "stream",
           "swapper_copy_name", "unpack", "user_agent", "validate", "verify_signature"]
