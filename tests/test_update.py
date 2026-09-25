# -*- coding: utf-8 -*-
u"""
Auto-update -- RUNBOOK LAYER 11. Ruled by Sonic 2026-09-24: *"I take all your
leans"* -- the whole folder, downloaded and proven quietly, SIGNED, the window never
restarting under a person, the previous version kept.

===========================================================================
11a -- THE RELEASE CONTRACT
===========================================================================

The manifest steers what is written into a person's program folder, so its parser
is strict and every refusal is its own case (LEDGER.md §harness: one case per run,
an input ONLY the guard under test rejects). The signature is checked with
throwaway keys made in each check's own temp folder -- ⛔ never the real signing
key, which lives in the keystore and is read by nothing here.

⚠ WHAT THIS FILE CANNOT SEE: whether GitHub still answers in the shape recorded
here, or whether a FROZEN build carries PyCryptodome -- the smoke drives the built
bytes for that (RUNBOOK 11h).
"""
import base64
import hashlib
import json
import os
import zipfile

import pytest

from hato import update
from hato.dev import signing
from hato.dev.claims import Fault

pytest.importorskip("Cryptodome", reason="the `update` extra (pycryptodomex) is not installed")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _key(folder, name="signing.pem"):
    u"""A throwaway key in the check's own folder -> (path, public half)."""
    path = folder / name
    return path, signing.keygen(path)


def _manifest(**over):
    fields = dict(version=u"1.0.5", zip_name=u"hato-1.0.5-windows-x64.zip", zip_size=123,
                  zip_sha256=u"a" * 64, min_from=u"1.0.4", critical=False,
                  notes=(u"Run now opens the window's run again.",),
                  entries={u"hato.exe": u"1" * 64, u"hato-cli.exe": u"2" * 64,
                           u"hato-watch.exe": u"3" * 64, u"hato-update.exe": u"4" * 64,
                           u"_internal": u"", u"LICENSE": u"5" * 64})
    fields.update(over)
    return update.Manifest(**fields)


def _raw(**over):
    return update.manifest_bytes(_manifest(**over))


def _edited(edit):
    u"""The canonical manifest's JSON, changed by `edit(dict)` -> bytes."""
    data = json.loads(_raw().decode("utf-8"))
    edit(data)
    return json.dumps(data).encode("utf-8")


def _bundle_zip(folder, version=u"1.0.5", extra=None):
    u"""A zip shaped like `package_standalone.build_zip`'s: one top-level `hato/`."""
    path = folder / (u"hato-%s-windows-x64.zip" % version)
    members = {u"hato/hato.exe": b"window", u"hato/hato-cli.exe": b"cli",
               u"hato/hato-watch.exe": b"tray", u"hato/hato-update.exe": b"swapper",
               u"hato/_internal/python310.dll": b"runtime",
               u"hato/_internal/hato/data/hato.ico": b"icon",
               u"hato/LICENSE": b"GPL", u"hato/README.md": b"read me"}
    members.update(extra or {})
    with zipfile.ZipFile(str(path), "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


# ---------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    (u"1.0.4", (1, 0, 4)), (u"10.20.30", (10, 20, 30)),
    (u"1.0", None), (u"v1.0.4", None), (u"1.0.4 ", None), (u"1.0.4-rc1", None),
    (u"", None), (None, None), (104, None)])
def test_a_version_is_strict_x_y_z(text, want):
    u"""⚠ surasura's own doc: `2.2` read OLDER than `2.2.0`, and a copy was offered
    itself as an update. One shape, or nothing."""
    assert update.parse_version(text) == want


def test_newer_compares_numbers_not_text():
    assert update.is_newer(u"1.0.10", u"1.0.9")
    assert not update.is_newer(u"1.0.9", u"1.0.10")
    assert not update.is_newer(u"1.0.4", u"1.0.4"), u"the same version is not newer"


def test_an_unreadable_version_is_never_newer():
    u"""⛔ Fail closed: a version this code cannot read cannot be installed."""
    assert not update.is_newer(u"2.0", u"1.0.4")
    assert not update.is_newer(u"1.0.5", u"garbage")


# ---------------------------------------------------------------------------
# the manifest
# ---------------------------------------------------------------------------

def test_a_manifest_round_trips_through_its_own_bytes():
    manifest = _manifest()
    assert update.parse_manifest(update.manifest_bytes(manifest)) == manifest


def test_the_bytes_are_canonical_so_a_signature_can_cover_them():
    u"""Sorted keys, one trailing newline: the same manifest, the same bytes."""
    assert update.manifest_bytes(_manifest()) == update.manifest_bytes(_manifest())
    assert update.manifest_bytes(_manifest()).endswith(b"}\n")


REFUSALS = [
    ("not json", lambda d: None, b"{not json"),
    ("not an object", lambda d: None, b"[1, 2]"),
    ("format 2", lambda d: d.update(format=2), None),
    ("format as a bool", lambda d: d.update(format=True), None),
    ("version not x.y.z", lambda d: d.update(version=u"1.0"), None),
    ("zip named for another version", lambda d: d["zip"].update(name=u"hato-1.0.6-windows-x64.zip"), None),
    ("zip size zero", lambda d: d["zip"].update(size=0), None),
    ("zip size a bool", lambda d: d["zip"].update(size=True), None),
    ("zip sha256 short", lambda d: d["zip"].update(sha256=u"a" * 63), None),
    ("zip sha256 upper case", lambda d: d["zip"].update(sha256=u"A" * 64), None),
    ("min_from after the version", lambda d: d.update(min_from=u"1.0.6"), None),
    ("min_from unreadable", lambda d: d.update(min_from=u"one"), None),
    ("critical as a string", lambda d: d.update(critical=u"yes"), None),
    ("too many notes", lambda d: d.update(notes=[u"a note"] * 9), None),
    ("an empty note", lambda d: d.update(notes=[u"  "]), None),
    ("a note too long", lambda d: d.update(notes=[u"x" * 201]), None),
    ("a note with a control character", lambda d: d.update(notes=[u"bell\x07"]), None),
    # ⚠ WITH a valid sha256: given "" the file rule refused it first, and M11a-06 --
    # the name rule deleted -- survived (LEDGER.md: a check another guard rescued).
    ("an entry climbing out", lambda d: d["entries"].update({u"..": u"b" * 64}), None),
    ("an entry with a separator", lambda d: d["entries"].update({u"a/b": u"b" * 64}), None),
    ("an entry naming a drive", lambda d: d["entries"].update({u"C:": u"b" * 64}), None),
    ("a file entry with no sha256", lambda d: d["entries"].update({u"LICENSE": u""}), None),
    ("the runtime folder with a sha256", lambda d: d["entries"].update({u"_internal": u"b" * 64}), None),
    ("the swapper missing", lambda d: d["entries"].pop(u"hato-update.exe"), None),
    ("the window missing", lambda d: d["entries"].pop(u"hato.exe"), None),
]


@pytest.mark.parametrize("label, edit, raw", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_a_manifest_that_cannot_be_trusted_is_refused_by_name(label, edit, raw):
    u"""One refusal per case, each an input only that rule rejects."""
    with pytest.raises(update.ManifestError):
        update.parse_manifest(raw if raw is not None else _edited(edit))


def test_the_control_every_refusal_above_starts_from_is_accepted():
    u"""⚠ The positive control: were the base manifest itself refused, every
    refusal above would pass for the wrong reason."""
    assert update.parse_manifest(_edited(lambda d: None)).version == u"1.0.5"


# ---------------------------------------------------------------------------
# the signature
# ---------------------------------------------------------------------------

def test_a_signature_by_a_trusted_key_verifies(tmp_path):
    path, public = _key(tmp_path)
    raw = _raw()
    assert update.verify_signature(raw, signing.sign(raw, path), keys=(public,))


def test_one_changed_byte_is_refused(tmp_path):
    path, public = _key(tmp_path)
    raw = _raw()
    signature = signing.sign(raw, path)
    changed = raw.replace(b"1.0.5", b"1.0.6", 1)
    assert changed != raw
    assert not update.verify_signature(changed, signature, keys=(public,))


def test_a_key_hato_does_not_trust_is_refused(tmp_path):
    path, _public = _key(tmp_path)
    _other, stranger = _key(tmp_path, "other.pem")
    raw = _raw()
    assert not update.verify_signature(raw, signing.sign(raw, path), keys=(stranger,))


def test_a_second_trusted_key_is_how_a_key_is_rotated(tmp_path):
    path, public = _key(tmp_path)
    _other, older = _key(tmp_path, "older.pem")
    raw = _raw()
    assert update.verify_signature(raw, signing.sign(raw, path), keys=(older, public))


@pytest.mark.parametrize("signature", [u"", u"not base64!", base64.b64encode(b"x" * 63).decode(),
                                       None, 64], ids=["empty", "garbled", "63 bytes", "none", "int"])
def test_a_missing_or_garbled_signature_is_refused_and_never_raises(tmp_path, signature):
    _path, public = _key(tmp_path)
    assert update.verify_signature(_raw(), signature, keys=(public,)) is False


def test_with_no_trusted_key_nothing_verifies(tmp_path):
    u"""⛔ An empty trust list is a refusal, never a pass."""
    path, _public = _key(tmp_path)
    raw = _raw()
    assert not update.verify_signature(raw, signing.sign(raw, path), keys=())


def test_without_pycryptodome_nothing_verifies(tmp_path, monkeypatch):
    u"""A source install without the `update` extra can be TOLD a release is out
    and can never install one: it cannot prove the signature."""
    import sys
    path, public = _key(tmp_path)
    raw = _raw()
    signature = signing.sign(raw, path)
    monkeypatch.setitem(sys.modules, "Cryptodome", None)
    monkeypatch.setitem(sys.modules, "Cryptodome.Signature", None)
    assert update.verify_signature(raw, signature, keys=(public,)) is False


# ---------------------------------------------------------------------------
# the key -- made once, never inside a repository, never overwritten
# ---------------------------------------------------------------------------

def test_keygen_writes_a_private_key_and_answers_with_the_public_half(tmp_path):
    path, public = _key(tmp_path)
    assert b"PRIVATE KEY" in path.read_bytes()
    assert len(base64.b64decode(public)) == 32
    assert signing.public_half(path) == public
    assert not (tmp_path / "signing.pem.new").exists(), u"the temp file was left behind"


def test_keygen_never_overwrites_a_key(tmp_path):
    u"""⛔ A second key would silently orphan every install trusting the first."""
    path, _public = _key(tmp_path)
    before = path.read_bytes()
    with pytest.raises(Fault):
        signing.keygen(path)
    assert path.read_bytes() == before


def test_keygen_refuses_a_folder_inside_a_git_work_tree(tmp_path):
    u"""🚨 A private key inside a work tree is one `git add` from being published."""
    (tmp_path / ".git").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    with pytest.raises(Fault) as err:
        signing.keygen(deep / "signing.pem")
    assert u"work tree" in u"%s" % err.value
    assert not (deep / "signing.pem").exists()


def test_hato_trusts_at_least_one_well_formed_key():
    u"""🚨 An empty or mangled trust list makes EVERY install refuse EVERY update --
    silently, since refusing is the safe answer. So it is asserted here."""
    assert update.PUBLIC_KEYS, u"hato trusts no key: no update could ever install"
    for key in update.PUBLIC_KEYS:
        assert len(base64.b64decode(key, validate=True)) == 32, key


def test_the_keystore_key_on_this_machine_is_one_hato_trusts():
    u"""On the release machine only: the key that will sign is a key the installs
    trust. ⚠ SKIPPED anywhere else -- CI and every clone have no keystore, and
    that is correct."""
    path, source = signing._paths().signing_key_file()
    if path is None or not path.is_file():
        pytest.skip(u"no signing key here (%s) -- not the release machine" % source)
    assert signing.public_half(path) in update.PUBLIC_KEYS, (
        u"the keystore's key is not in PUBLIC_KEYS: a release signed with it would be "
        u"refused by every install")


def test_the_configured_key_lives_outside_the_vault():
    u"""The path `hato.config.json` names resolves outside every work tree -- the
    keystore -- whatever is or is not in it."""
    path, source = signing._paths().signing_key_file()
    assert path is not None, source
    assert not signing.inside_repository(path.parent), path


# ---------------------------------------------------------------------------
# the manifest is built FROM the zip that is published
# ---------------------------------------------------------------------------

def test_the_manifest_is_read_out_of_the_zip(tmp_path):
    zip_path = _bundle_zip(tmp_path)
    manifest = signing.build_manifest(zip_path, notes=(u"One change.",))
    assert manifest.version == u"1.0.5"
    assert manifest.zip_size == zip_path.stat().st_size
    assert manifest.zip_sha256 == hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert manifest.entries[u"hato.exe"] == hashlib.sha256(b"window").hexdigest()
    assert manifest.entries[u"_internal"] == u""
    assert set(manifest.entries) == {u"hato.exe", u"hato-cli.exe", u"hato-watch.exe",
                                     u"hato-update.exe", u"_internal", u"LICENSE",
                                     u"README.md"}


def test_a_zip_with_anything_outside_its_hato_folder_is_refused(tmp_path):
    zip_path = _bundle_zip(tmp_path, extra={u"stray.txt": b"x"})
    with pytest.raises(Fault):
        signing.build_manifest(zip_path)


def test_a_zip_the_client_would_refuse_is_never_given_a_manifest(tmp_path):
    u"""⭐ The client's own parser is the gate: a zip without the swapper builds no
    manifest, so no release can publish one."""
    path = tmp_path / "hato-1.0.5-windows-x64.zip"
    with zipfile.ZipFile(str(path), "w") as archive:
        archive.writestr(u"hato/hato.exe", b"window")
    with pytest.raises(Fault) as err:
        signing.build_manifest(path)
    assert u"would be refused" in u"%s" % err.value


def test_the_written_pair_is_checked_the_way_an_install_checks_it(tmp_path):
    zip_path = _bundle_zip(tmp_path)
    key, public = _key(tmp_path)
    signing.write_manifest(zip_path, key, notes=(u"One change.",))
    raw = (tmp_path / update.MANIFEST_NAME).read_bytes()
    sig = (tmp_path / update.SIGNATURE_NAME).read_text(encoding="ascii")
    assert update.verify_signature(raw, sig, keys=(public,))
    got = dict((c.name, c.state) for c in signing.check_written(zip_path, keys=(public,)))
    assert got == {u"signature_verifies": u"ok", u"manifest_parses": u"ok",
                   u"zip_matches": u"ok"}, got


def test_a_pair_signed_by_a_key_hato_does_not_carry_fails_the_release(tmp_path):
    u"""🚨 The release's own claim: signed, but by a key no install trusts, is a
    release every install would refuse."""
    zip_path = _bundle_zip(tmp_path)
    key, _public = _key(tmp_path)
    signing.write_manifest(zip_path, key)
    got = dict((c.name, c.state) for c in signing.check_written(zip_path, keys=()))
    assert got[u"signature_verifies"] == u"FAIL", got


def test_a_rebuilt_zip_beside_an_old_manifest_fails_the_release(tmp_path):
    u"""surasura's doc: a zip rebuilt after its manifest failed every client's
    checksum, silently. Here the release's own claim fails first."""
    zip_path = _bundle_zip(tmp_path)
    key, public = _key(tmp_path)
    signing.write_manifest(zip_path, key)
    with zipfile.ZipFile(str(zip_path), "a") as archive:
        archive.writestr(u"hato/NOTES.txt", b"rebuilt")
    got = dict((c.name, c.state) for c in signing.check_written(zip_path, keys=(public,)))
    assert got[u"zip_matches"] == u"FAIL", got


# ===========================================================================
# 11b -- THE CHECK, against a fake GitHub serving the RECORDED answer's shape
#
# ⭐ LEDGER-HOT: seed every fixture in the WIRE's shape. Every synthetic asset
# below is a copy of the recorded zip asset with its values changed, so the
# fields hato reads are the fields GitHub sends.
# ===========================================================================

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "update", "releases_latest_1.0.3.json")
DOWNLOAD = u"https://github.com/SonicSandbox/hato/releases/download/v%s/%s"


def _recorded():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)["release"]


class _Wire(object):
    u"""A fake GitHub: the release JSON at LATEST_URL, and asset bodies by URL."""

    def __init__(self, release, files=None, down=False):
        self.release, self.files, self.down = release, dict(files or {}), down
        self.asked = []

    def __call__(self, url, limit):
        self.asked.append(url)
        if self.down:
            raise update.FetchError(u"no route to host")
        if url == update.LATEST_URL:
            body = json.dumps(self.release).encode("utf-8")
        elif url in self.files:
            body = self.files[url]
        else:
            raise update.FetchError(u"answered 404")
        if len(body) > limit:
            raise update.FetchError(u"more than %d bytes" % limit)
        return body


def _published(tmp_path, monkeypatch, tag=u"v1.0.5", trust=True, **edit):
    u"""A 1.0.5 release as GitHub would list it -> (_Wire, Manifest). `edit`
    changes the zip asset's recorded fields (size, digest), or drops it."""
    key, public = _key(tmp_path, "release.pem")
    monkeypatch.setattr(update, "PUBLIC_KEYS", (public,) if trust else ())
    zip_path = _bundle_zip(tmp_path)
    manifest = signing.build_manifest(zip_path, notes=(u"Needs you says when it looks again.",))
    raw = update.manifest_bytes(manifest)
    signature = signing.sign(raw, key).encode("ascii")
    shape = _recorded()["assets"][0]

    def asset(name, size, body_hash):
        a = dict(shape)
        a.update(name=name, size=size, digest=u"sha256:" + body_hash,
                 browser_download_url=DOWNLOAD % (tag[1:], name))
        return a

    zip_asset = asset(manifest.zip_name, manifest.zip_size, manifest.zip_sha256)
    if edit.pop("drop_zip", False):
        zip_asset = None
    elif edit:
        zip_asset.update(edit)
    release = dict(_recorded())
    release.update(tag_name=tag, name=u"hato " + tag[1:],
                   html_url=u"https://github.com/SonicSandbox/hato/releases/tag/" + tag)
    release["assets"] = [a for a in (
        zip_asset,
        asset(update.MANIFEST_NAME, len(raw), hashlib.sha256(raw).hexdigest()),
        asset(update.SIGNATURE_NAME, len(signature), hashlib.sha256(signature).hexdigest()),
    ) if a is not None]
    files = {DOWNLOAD % (tag[1:], update.MANIFEST_NAME): raw,
             DOWNLOAD % (tag[1:], update.SIGNATURE_NAME): signature}
    return _Wire(release, files), manifest


def _check(wire, tmp_path, current=u"1.0.4", frozen=True, windows=True, folder=None):
    return update.check(current, get=wire, frozen=frozen, windows=windows,
                        install_dir=str(folder if folder is not None else tmp_path))


def test_the_recorded_answer_on_its_own_version_is_up_to_date(tmp_path):
    u"""The real shape is readable, and the same version is not an update."""
    got = _check(_Wire(_recorded()), tmp_path, current=u"1.0.3")
    assert (got.kind, got.version) == (update.NONE, u"1.0.3"), got


def test_the_recorded_release_carries_no_manifest_so_an_older_copy_is_only_told(tmp_path):
    u"""1.0.3 was published before the contract existed: a copy older than it is
    TOLD, never handed an unsigned zip -- the first real case this code meets."""
    got = _check(_Wire(_recorded()), tmp_path, current=u"1.0.2")
    assert (got.kind, got.reason) == (update.TELL, update.UNREADABLE), got


def test_a_signed_consistent_release_is_ready(tmp_path, monkeypatch):
    wire, manifest = _published(tmp_path, monkeypatch)
    got = _check(wire, tmp_path)
    assert got.kind == update.READY, got
    assert got.manifest == manifest
    assert got.zip_url == DOWNLOAD % (u"1.0.5", manifest.zip_name)
    assert got.notes == (u"Needs you says when it looks again.",)
    assert got.page.endswith(u"/v1.0.5")


def test_a_copy_run_from_source_is_told_and_never_asked_about_signatures(tmp_path, monkeypatch):
    u"""⭐ Source is asked FIRST: even a release this copy could not prove is
    simply *out*, and a checkout updates itself with git."""
    wire, _manifest = _published(tmp_path, monkeypatch, trust=False)
    got = _check(wire, tmp_path, frozen=False)
    assert (got.kind, got.reason) == (update.TELL, update.SOURCE), got
    assert got.notes, u"what changed was not carried to the telling"


def test_another_platform_is_told(tmp_path, monkeypatch):
    wire, _manifest = _published(tmp_path, monkeypatch)
    got = _check(wire, tmp_path, windows=False)
    assert (got.kind, got.reason) == (update.TELL, update.PLATFORM), got


def test_a_release_signed_by_a_key_hato_does_not_trust_is_only_told(tmp_path, monkeypatch):
    wire, _manifest = _published(tmp_path, monkeypatch, trust=False)
    got = _check(wire, tmp_path)
    assert (got.kind, got.reason) == (update.TELL, update.UNSIGNED), got
    assert got.manifest is None and got.zip_url is None


@pytest.mark.parametrize("edit", [
    dict(digest=u"sha256:" + u"0" * 64), dict(size=1), dict(drop_zip=True)],
    ids=["github-records-another-hash", "another-size", "no-zip"])
def test_a_release_whose_records_disagree_is_only_told(tmp_path, monkeypatch, edit):
    u"""The signed manifest, the tag and GitHub's own record of the zip must agree."""
    wire, _manifest = _published(tmp_path, monkeypatch, **edit)
    got = _check(wire, tmp_path)
    assert (got.kind, got.reason) == (update.TELL, update.MISMATCH), got


def test_a_manifest_for_another_version_than_its_tag_is_only_told(tmp_path, monkeypatch):
    wire, _manifest = _published(tmp_path, monkeypatch, tag=u"v1.0.6")
    got = _check(wire, tmp_path)
    assert (got.kind, got.reason) == (update.TELL, update.MISMATCH), got


def test_an_absent_github_digest_is_not_a_disagreement(tmp_path, monkeypatch):
    u"""⚠ Fail open on the ABSENT field (it arrived in 2025), closed on a different
    one: the signed manifest already names the hash."""
    wire, _manifest = _published(tmp_path, monkeypatch, digest=None)
    assert _check(wire, tmp_path).kind == update.READY


def test_a_copy_older_than_the_releases_min_from_is_only_told(tmp_path, monkeypatch):
    u"""1.0.3 has no updater to take a release in place: it downloads one by hand."""
    wire, _manifest = _published(tmp_path, monkeypatch)
    got = _check(wire, tmp_path, current=u"1.0.3")
    assert (got.kind, got.reason) == (update.TELL, update.TOO_OLD), got


def test_a_folder_that_cannot_be_written_is_only_told(tmp_path, monkeypatch):
    u"""MEASURED, not assumed from the path: a file is really made and removed."""
    wire, _manifest = _published(tmp_path, monkeypatch)
    got = _check(wire, tmp_path, folder=tmp_path / "not-there")
    assert (got.kind, got.reason) == (update.TELL, update.FOLDER), got
    assert not list(tmp_path.glob(".hato-probe-*")), u"the probe file was left behind"


@pytest.mark.parametrize("release", [
    None, {u"tag_name": u"latest"}, {u"tag_name": u"v1.0"}, {u"name": u"no tag"}],
    ids=["offline", "a-tag-that-is-not-a-version", "a-short-version", "no-tag"])
def test_offline_or_unreadable_is_silent(tmp_path, release):
    u"""⛔ Offline is silent (surasura): no error, no indicator -- NONE."""
    wire = _Wire(release, down=release is None)
    got = _check(wire, tmp_path)
    assert got.kind == update.NONE, got


def test_the_real_fetch_never_opens_a_socket_with_the_network_off(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    with pytest.raises(update.FetchError) as err:
        update.fetch(update.LATEST_URL, 1024)
    assert u"switched off" in u"%s" % err.value
    assert update.check(u"1.0.4", frozen=True, windows=True,
                        install_dir=str(tmp_path)).kind == update.NONE


def test_a_check_is_owed_once_a_day_and_after_a_clock_goes_back():
    now = 1000000.0
    assert update.due({}, now)
    assert not update.due({u"checked_at": now - 3600}, now)
    assert update.due({u"checked_at": now - update.CHECK_EVERY_SECONDS}, now)
    assert update.due({u"checked_at": now + 3600}, now), u"a future stamp was trusted"
    assert update.due({u"checked_at": True}, now), u"a bool was read as a time"


def test_the_state_survives_a_round_trip_and_a_broken_file_means_ask_again(tmp_path):
    path = tmp_path / "update-state.json"
    update.save_state({u"skipped": u"1.0.5"}, path)
    state = update.remember(update.Decision(update.NONE, version=u"1.0.4"), 42.0, path)
    assert state[u"skipped"] == u"1.0.5", u"remembering a check forgot a skipped version"
    assert update.load_state(path)[u"checked_at"] == 42.0
    path.write_text(u"{not json", encoding="utf-8")
    assert update.load_state(path) == {}


# ===========================================================================
# 11c -- STAGING, while hato keeps running: everything that can fail slowly
# happens here, and a failure leaves nothing behind
# ===========================================================================

def _serve(data, chunk=7):
    u"""A fake download: `data` in small blocks, so the counting is exercised."""
    def get(_url):
        for at in range(0, len(data), chunk):
            yield data[at:at + chunk]
    return get


def _ready(tmp_path, monkeypatch):
    u"""A READY decision for a real signed 1.0.5 zip -> (decision, the zip's bytes)."""
    wire, manifest = _published(tmp_path, monkeypatch)
    decision = _check(wire, tmp_path)
    assert decision.kind == update.READY, decision
    zip_bytes = (tmp_path / manifest.zip_name).read_bytes()
    return decision, zip_bytes


def test_two_folders_under_one_temp_share_a_volume(tmp_path):
    assert update.same_volume(tmp_path, tmp_path / "not" / "made" / "yet")


def test_a_download_is_counted_hashed_and_renamed_only_when_whole(tmp_path):
    data = b"a program zip" * 100
    dest = tmp_path / "hato.zip"
    seen = []
    update.download(u"u", dest, len(data), hashlib.sha256(data).hexdigest(),
                    progress=lambda done, total: seen.append((done, total)),
                    get=_serve(data))
    assert dest.read_bytes() == data
    assert seen[-1] == (len(data), len(data)) and len(seen) > 1, seen[:3]
    assert [d for d, _t in seen] == sorted(d for d, _t in seen), u"progress went backwards"
    assert not (tmp_path / "hato.zip.part").exists()


@pytest.mark.parametrize("case", ["runs-past-its-size", "another-hash", "cut-short"])
def test_a_download_that_is_not_the_releases_leaves_nothing(tmp_path, case):
    data = b"a program zip" * 100
    size, digest, served = len(data), hashlib.sha256(data).hexdigest(), data
    if case == "runs-past-its-size":
        served = data + b"more"
    elif case == "another-hash":
        served = data[:-1] + b"X"
    else:
        served = data[:-10]
    dest = tmp_path / "hato.zip"
    with pytest.raises(update.StageError):
        update.download(u"u", dest, size, digest, get=_serve(served))
    assert not dest.exists() and not (tmp_path / "hato.zip.part").exists()


def test_a_download_stops_reading_the_moment_it_passes_its_size(tmp_path):
    u"""⚠ The final size check would ALSO refuse an over-long download -- after
    reading all of it. So the cap's own check counts what was READ: a server
    sending gigabytes is stopped one block past the size, not at the end."""
    size, block = 1000, b"x" * 100
    served = []

    def endless(_url):
        for _ in range(100000):                  # ~10 MB if nothing stops it
            served.append(len(block))
            yield block

    with pytest.raises(update.StageError):
        update.download(u"u", tmp_path / "hato.zip", size, u"0" * 64, get=endless)
    assert sum(served) <= size + len(block), u"read %d bytes past a %d-byte release" % (
        sum(served), size)


def test_a_sweep_never_reaches_outside_its_own_folder(tmp_path):
    u"""⛔ doctrine/robustness: a destructive sweep is scoped by SHAPE."""
    root, outside = tmp_path / "stage", tmp_path / "theirs.txt"
    root.mkdir()
    outside.write_text(u"a person's file", encoding="utf-8")
    update._remove(str(root), str(outside))
    update._remove(str(root), str(root / ".." / "theirs.txt"))
    assert outside.read_text(encoding="utf-8") == u"a person's file"
    inside = root / "old.zip"
    inside.write_bytes(b"x")
    update._remove(str(root), str(inside))
    assert not inside.exists(), u"the control: a file inside IS removed"


def test_a_failed_download_is_a_sentence_and_leaves_nothing(tmp_path):
    def broken(_url):
        yield b"first"
        raise update.StageError(u"the download stopped (ConnectionError)")
    dest = tmp_path / "hato.zip"
    with pytest.raises(update.StageError):
        update.download(u"u", dest, 100, u"0" * 64, get=broken)
    assert not list(tmp_path.iterdir()), list(tmp_path.iterdir())


def test_a_bundle_unpacks_into_its_own_hato_folder(tmp_path):
    zip_path = _bundle_zip(tmp_path)
    folder = update.unpack(zip_path, tmp_path / "staged")
    assert sorted(os.listdir(folder)) == sorted([u"LICENSE", u"README.md", u"_internal",
                                                 u"hato-cli.exe", u"hato-update.exe",
                                                 u"hato-watch.exe", u"hato.exe"])
    with open(os.path.join(folder, u"_internal", u"python310.dll"), "rb") as handle:
        assert handle.read() == b"runtime"
    assert not (tmp_path / "staged.part").exists()


@pytest.mark.parametrize("member", [u"stray.txt", u"hato/../escape.txt", u"hato/C:/x.txt"],
                         ids=["outside-hato", "climbing-out", "a-drive"])
def test_a_zip_member_that_would_land_outside_is_refused_before_a_byte(tmp_path, member):
    u"""⛔ judged by archives.py's own rules, over EVERY member, before writing."""
    zip_path = _bundle_zip(tmp_path, extra={member: b"x"})
    with pytest.raises(update.StageError):
        update.unpack(zip_path, tmp_path / "staged")
    assert not (tmp_path / "staged").exists() and not (tmp_path / "staged.part").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_a_zip_holding_a_link_is_refused(tmp_path):
    zip_path = _bundle_zip(tmp_path)
    info = zipfile.ZipInfo(u"hato/link")
    info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(str(zip_path), "a") as archive:
        archive.writestr(info, b"C:/Windows")
    with pytest.raises(update.StageError):
        update.unpack(zip_path, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


def test_a_zip_with_more_members_than_hato_ever_has_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "MAX_BUNDLE_MEMBERS", 3)
    with pytest.raises(update.StageError):
        update.unpack(_bundle_zip(tmp_path), tmp_path / "staged")


def _unpacked(tmp_path):
    zip_path = _bundle_zip(tmp_path)
    return update.unpack(zip_path, tmp_path / "staged"), signing.build_manifest(zip_path)


def test_the_unpacked_program_is_checked_against_its_manifest(tmp_path):
    folder, manifest = _unpacked(tmp_path)
    update.validate(folder, manifest, version_of=lambda _f: u"1.0.5")


@pytest.mark.parametrize("damage", ["an-unlisted-file", "a-missing-file", "a-changed-file",
                                    "runtime-not-a-folder", "reports-another-version"])
def test_an_unpacked_program_that_is_not_the_releases_is_refused(tmp_path, damage):
    folder, manifest = _unpacked(tmp_path)
    version = u"1.0.5"
    if damage == "an-unlisted-file":
        with open(os.path.join(folder, u"extra.dll"), "wb") as handle:
            handle.write(b"x")
    elif damage == "a-missing-file":
        os.remove(os.path.join(folder, u"README.md"))
    elif damage == "a-changed-file":
        with open(os.path.join(folder, u"hato.exe"), "ab") as handle:
            handle.write(b"!")
    elif damage == "runtime-not-a-folder":
        import shutil
        shutil.rmtree(os.path.join(folder, u"_internal"))
        with open(os.path.join(folder, u"_internal"), "wb") as handle:
            handle.write(b"x")
    else:
        version = u"1.0.4"
    with pytest.raises(update.StageError):
        update.validate(folder, manifest, version_of=lambda _f: version)


def test_a_downloaded_hato_that_will_not_start_is_said_so_not_called_version_none(tmp_path):
    u"""⛔ ADVERSARY 2026-09-24 A2: a security program holding the new exe made the
    screen say the download "reports None" -- the engine's word, not a person's."""
    folder, manifest = _unpacked(tmp_path)
    with pytest.raises(update.StageError) as told:
        update.validate(folder, manifest, version_of=lambda _f: None)
    assert u"would not start" in str(told.value)
    assert u"None" not in str(told.value)


def test_staging_a_ready_release_writes_the_whole_hand_off(tmp_path, monkeypatch):
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    install = tmp_path / "install"
    install.mkdir()
    root = tmp_path / "stage"
    pending = update.stage(decision, u"1.0.4", str(install), get=_serve(zip_bytes, 4096),
                           version_of=lambda _f: u"1.0.5", root=str(root))
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    assert (hand[u"from"], hand[u"to"]) == (u"1.0.4", u"1.0.5")
    assert hand[u"install"] == os.path.abspath(str(install))
    assert sorted(os.listdir(hand[u"staged"])) == sorted(decision.manifest.entries)
    assert hand[u"previous"] == os.path.join(str(root), u"previous", u"1.0.4")
    assert hand[u"entries"] == decision.manifest.entries
    assert (hand[u"window"], hand[u"tray"]) == (False, False)
    assert not os.listdir(str(root / "download")), u"the spent zip was kept"


def test_the_hand_off_lists_hatos_own_entries_and_never_a_persons_files(tmp_path, monkeypatch):
    u"""⛔ Only hato's own entries move out; a person's file beside them stays."""
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    install = tmp_path / "install"
    (install / "_internal").mkdir(parents=True)
    for name in (u"hato.exe", u"hato-cli.exe", u"hato-watch.exe", u"LICENSE",
                 u"my notes.txt", u"shortcut.lnk"):
        (install / name).write_bytes(b"x")
    pending = update.stage(decision, u"1.0.4", str(install), get=_serve(zip_bytes, 4096),
                           version_of=lambda _f: u"1.0.5", root=str(tmp_path / "stage"))
    with open(pending, encoding="utf-8") as handle:
        old = json.load(handle)[u"old_entries"]
    assert old == [u"LICENSE", u"_internal", u"hato-cli.exe", u"hato-watch.exe", u"hato.exe"], old


def test_a_staging_failure_leaves_nothing_of_itself(tmp_path, monkeypatch):
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    root = tmp_path / "stage"
    with pytest.raises(update.StageError):
        update.stage(decision, u"1.0.4", str(tmp_path), get=_serve(zip_bytes),
                     version_of=lambda _f: u"9.9.9", root=str(root))
    assert not (root / "staged" / "1.0.5").exists()
    assert not os.listdir(str(root / "download"))
    assert not (root / update.PENDING_NAME).exists()


def test_staging_starts_from_nothing_but_keeps_the_kept_version_and_the_result(tmp_path,
                                                                              monkeypatch):
    u"""An older release staged and never installed, and a download a crash cut
    off, are ~70-130 MB each: gone. ⛔ The version kept for Go back and a result
    the window has not read yet are not staging's to touch."""
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    root = tmp_path / "stage"
    stale = root / "staged" / "1.0.4a" / "hato"
    stale.mkdir(parents=True)
    (stale / "hato.exe").write_bytes(b"never installed")
    (root / "download").mkdir()
    (root / "download" / "hato-1.0.4a-windows-x64.zip.part").write_bytes(b"cut off")
    spent = root / update.swapper_copy_name(u"1.0.4a")
    spent.write_bytes(b"a swapper that already ran")
    kept = root / "previous" / "1.0.3"
    kept.mkdir(parents=True)
    (kept / "hato.exe").write_bytes(b"Go back")
    (root / update.RESULT_NAME).write_text(u"{}", encoding="utf-8")
    install = tmp_path / "install"
    install.mkdir()
    update.stage(decision, u"1.0.4", str(install), get=_serve(zip_bytes, 4096),
                 version_of=lambda _f: u"1.0.5", root=str(root))
    assert os.listdir(str(root / "staged")) == [u"1.0.5"], os.listdir(str(root / "staged"))
    assert os.listdir(str(root / "download")) == []
    assert not spent.exists(), u"a spent swapper copy stayed"
    assert (kept / "hato.exe").read_bytes() == b"Go back"
    assert (root / update.RESULT_NAME).is_file()


def test_only_a_ready_decision_is_ever_staged(tmp_path):
    with pytest.raises(update.StageError):
        update.stage(update.Decision(update.TELL, u"1.0.5", update.SOURCE), u"1.0.4",
                     str(tmp_path), root=str(tmp_path / "stage"))


# ---------------------------------------------------------------------------
# ⭐ THE SEAM -- what staging and *Go back* write is what the swapper reads.
# Two halves built separately (11c, 11d): nothing else proves they agree.
# ---------------------------------------------------------------------------

def _installed(tmp_path):
    u"""An installed 1.0.4 under a Japanese-named folder, a person's file beside it."""
    install = tmp_path / u"ツール置き場" / u"hato"
    (install / u"_internal").mkdir(parents=True)
    (install / u"_internal" / u"python310.dll").write_bytes(b"old runtime")
    for name in (u"hato.exe", u"hato-cli.exe", u"hato-watch.exe", u"hato-update.exe",
                 u"LICENSE"):
        (install / name).write_bytes(b"old " + name.encode())
    (install / u"my notes.txt").write_bytes(b"theirs")
    return install


def _swapped(pending_path, says):
    u"""The REAL swapper over a hand-off, with a fake Windows -> (exit code, ops)."""
    import _fakewin                                   # tests/ is on sys.path
    from hato import swap
    clock = _fakewin.Clock()
    ops = _fakewin.Ops(says=says)
    return swap.run(str(pending_path), quiet=True, ops=ops, clock=clock,
                    sleep=clock.sleep), ops


def _staged_over(tmp_path, monkeypatch, root=u"stage", current=u"1.0.4"):
    u"""1.0.4 installed, 1.0.5 staged beside it -> (install, root, pending path).
    `root=None`: where hato itself would stage (`update.stage_root`). `current`: the
    copy that staged it -- `--apply` hands off only what the RUNNING copy prepared."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    install = _installed(tmp_path)
    root = update.stage_root(str(install)) if root is None else tmp_path / root
    pending = update.stage(decision, current, str(install), get=_serve(zip_bytes, 4096),
                           version_of=lambda _f: u"1.0.5", root=str(root))
    return install, root, pending


def test_what_staging_writes_is_what_the_swapper_accepts(tmp_path, monkeypatch):
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    code, ops = _swapped(pending, says=u"1.0.5")
    result = json.loads((root / update.RESULT_NAME).read_text(encoding="utf-8"))
    assert (code, result[u"status"]) == (0, u"success"), result
    assert (install / u"hato.exe").read_bytes() == b"window"
    assert (install / u"hato-update.exe").read_bytes() == b"swapper"
    assert (install / u"_internal" / u"python310.dll").read_bytes() == b"runtime"
    assert (install / u"my notes.txt").read_bytes() == b"theirs"
    assert (root / u"previous" / u"1.0.4" / u"hato.exe").read_bytes() == b"old hato.exe"
    assert ops.asked == [u"hato-cli.exe"], u"the new command line was never run"


def test_going_back_is_what_the_swapper_accepts_and_can_itself_be_undone(tmp_path,
                                                                          monkeypatch):
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert _swapped(pending, says=u"1.0.5")[0] == 0
    assert update.kept_version(str(install), u"1.0.5", root=str(root)) == u"1.0.4"
    back = update.go_back_pending(str(install), u"1.0.5", root=str(root))
    code, _ops = _swapped(back, says=u"1.0.4")
    assert code == 0, (root / update.RESULT_NAME).read_text(encoding="utf-8")
    assert (install / u"hato.exe").read_bytes() == b"old hato.exe"
    assert (install / u"_internal" / u"python310.dll").read_bytes() == b"old runtime"
    assert not (install / u"README.md").exists(), u"1.0.5's own file stayed in 1.0.4"
    assert (install / u"my notes.txt").read_bytes() == b"theirs"
    assert (root / u"previous" / u"1.0.5" / u"hato.exe").read_bytes() == b"window", \
        u"going back did not keep the version it replaced -- it could not be undone"
    assert update.kept_version(str(install), u"1.0.4", root=str(root)) == u"1.0.5"
    update.reconcile(str(install), root=str(root))      # the returning window reads it
    assert update.skipped() == u"1.0.5", \
        u"an automatic update would quietly re-install what a person just removed"
    result = json.loads((root / update.RESULT_NAME).read_text(encoding="utf-8"))
    assert result[u"going_back"] is True, u"the window would call going back an update"


def test_a_kept_file_changed_before_going_back_is_refused(tmp_path, monkeypatch):
    u"""The kept entries are hashed when *Go back* is asked: a file changed in
    `previous\\` after that is refused, and 1.0.5 stays."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert _swapped(pending, says=u"1.0.5")[0] == 0
    back = update.go_back_pending(str(install), u"1.0.5", root=str(root))
    (root / u"previous" / u"1.0.4" / u"hato.exe").write_bytes(b"changed since")
    code, _ops = _swapped(back, says=u"1.0.4")
    assert code == 1
    assert (install / u"hato.exe").read_bytes() == b"window", u"a changed file went in"


def test_there_is_nothing_to_go_back_to_until_a_whole_version_is_kept(tmp_path):
    root, install = tmp_path / "stage", tmp_path / "install"
    install.mkdir()
    assert update.kept_version(str(install), u"1.0.5", root=str(root)) is None
    kept = root / "previous" / "1.0.4"
    (kept / "_internal").mkdir(parents=True)
    for name in (u"hato.exe", u"hato-cli.exe"):
        (kept / name).write_bytes(b"x")
    assert update.kept_version(str(install), u"1.0.5", root=str(root)) is None, \
        u"a kept version missing hato-watch.exe was offered"
    (kept / "hato-watch.exe").write_bytes(b"x")
    assert update.kept_version(str(install), u"1.0.5", root=str(root)) == u"1.0.4"
    assert update.kept_version(str(install), u"1.0.4", root=str(root)) is None, \
        u"the version already installed was offered as the one to go back to"
    with pytest.raises(update.StageError):
        update.go_back_pending(str(install), u"1.0.4", root=str(root))


def test_the_hand_off_starts_the_new_swapper_from_outside_the_install(tmp_path, monkeypatch):
    u"""⭐ The NEW version's own swapper, copied OUT of the payload into the staging
    root under its version's name, and the hand-off says what to start again."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    (root / update.swapper_copy_name(u"1.0.5")).write_bytes(b"a spent copy")
    started = []
    update.hand_off(pending, window=True, tray=True, tray_pid_file=tmp_path / "watch.pid",
                    start=lambda argv: started.append(argv) or u"proc")
    copy = root / update.swapper_copy_name(u"1.0.5")
    assert started == [[str(copy), u"--pending", os.path.abspath(pending)]], started
    assert copy.read_bytes() == b"swapper", u"not the NEW version's swapper"
    assert not str(copy).startswith(str(install)), u"the swapper runs from inside the install"
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    assert (hand[u"window"], hand[u"tray"]) == (True, True)
    assert hand[u"tray_pid_file"] == str(tmp_path / "watch.pid")
    from hato import paths
    assert hand[u"log"] == str(paths.default_log_path()), u"the swapper was given no log"


def test_the_trays_quiet_hand_off_asks_for_no_splash(tmp_path, monkeypatch):
    _install, _root, pending = _staged_over(tmp_path, monkeypatch)
    started = []
    update.hand_off(pending, tray=True, quiet=True, start=started.append)
    assert started[0][-1] == u"--quiet", started


def test_a_new_version_with_no_updater_is_never_handed_off(tmp_path, monkeypatch):
    _install, _root, pending = _staged_over(tmp_path, monkeypatch)
    with open(pending, encoding="utf-8") as handle:
        staged = json.load(handle)[u"staged"]
    os.remove(os.path.join(staged, update.SWAPPER_NAME))
    started = []
    with pytest.raises(update.StageError) as caught:
        update.hand_off(pending, window=True, start=started.append)
    assert started == [], u"a swapper was started with no updater to run"
    assert u"carries no updater" in u"%s" % caught.value, u"%s" % caught.value


def _result_file(root, **fields):
    result = {u"from": u"1.0.4", u"to": u"1.0.5", u"status": u"success", u"touched": True}
    result.update(fields)
    os.makedirs(str(root), exist_ok=True)
    update.save_json(os.path.join(str(root), update.RESULT_NAME), result)


def test_a_failed_update_is_turned_away_so_nothing_retries_it_in_a_loop(tmp_path,
                                                                        monkeypatch):
    u"""⛔ The tray would stage and install it again every night otherwise."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    root = tmp_path / "stage"
    _result_file(root, status=u"failed")
    got = update.reconcile(str(tmp_path), root=str(root))
    assert got[u"status"] == u"failed" and update.skipped() == u"1.0.5"
    assert os.path.isfile(os.path.join(str(root), update.RESULT_NAME)), \
        u"the tray took the result the window has to show"
    assert update.reconcile(str(tmp_path), consume=True, root=str(root)) is not None
    assert not os.path.exists(os.path.join(str(root), update.RESULT_NAME))
    assert update.reconcile(str(tmp_path), root=str(root)) is None


def test_a_successful_update_is_not_turned_away(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    _result_file(tmp_path / "stage")
    update.reconcile(str(tmp_path), root=str(tmp_path / "stage"))
    assert update.skipped() is None
    update.skip(u"1.0.5")
    update.skip(None)
    assert update.skipped() is None, u"Try again could not forget a turned-away version"


def test_what_is_staged_is_read_from_the_disk(tmp_path, monkeypatch):
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) == u"1.0.5"
    assert update.staged_version(str(install), u"1.0.5", root=str(root)) is None, \
        u"a release no newer than this copy read as waiting"
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    import shutil
    shutil.rmtree(hand[u"staged"])
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) is None, \
        u"a hand-off whose folder is gone read as waiting"


def test_a_go_back_hand_off_is_not_a_release_waiting(tmp_path, monkeypatch):
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    hand[u"going_back"] = True
    update.save_json(pending, hand)
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) is None


def test_the_answer_carries_the_downloads_size():
    decision = update.Decision(update.READY, u"1.0.5", manifest=_manifest(zip_size=67400000))
    assert decision.as_dict()[u"size"] == 67400000
    assert update.Decision(update.NONE).as_dict()[u"size"] is None


def _release_trio(tmp_path, extra=None):
    u"""A zip, update.json and update.json.sig written as a release writes them, and
    a fake GitHub publishing them -> (zip path, public key, files by URL, release)."""
    key, public = _key(tmp_path, "release.pem")
    zip_path = _bundle_zip(tmp_path, extra=extra)
    signing.write_manifest(zip_path, key, notes=(u"a note",))
    base = u"https://github.com/SonicSandbox/hato/releases/download/v1.0.5/"
    files, assets = {}, []
    for name in (zip_path.name, update.MANIFEST_NAME, update.SIGNATURE_NAME):
        body = (tmp_path / name).read_bytes()
        files[base + name] = body
        assets.append({u"name": name, u"size": len(body), u"browser_download_url": base + name,
                       u"digest": u"sha256:" + hashlib.sha256(body).hexdigest()})
    release = {u"tag_name": u"v1.0.5", u"assets": assets}
    return zip_path, public, files, release


def _github(release, files, latest=None):
    def fetch(url, limit):
        if url == update.LATEST_URL:
            return json.dumps(latest if latest is not None else release).encode("utf-8")
        if url.endswith(u"/releases/tags/" + release[u"tag_name"]):
            return json.dumps(release).encode("utf-8")
        if url in files:
            return files[url]
        raise update.FetchError(u"answered 404")
    return fetch


def test_the_published_release_is_checked_the_way_an_install_checks_it(tmp_path):
    zip_path, public, files, release = _release_trio(tmp_path)
    from hato.dev import claims
    got = signing.check_published(zip_path, keys=(public,), fetch=_github(release, files))
    states = dict((c.name, c.state) for c in got)
    for name in (u"published_" + zip_path.name, u"published_update.json",
                 u"published_update.json.sig", u"github_digest", u"signature_verifies",
                 u"manifest_parses", u"zip_matches", u"the_latest_release",
                 u"manifest_names_this_release", u"an_install_takes_it"):
        assert states.get(name) == claims.OK, (name, got)


@pytest.mark.parametrize("damage, claim", [
    (u"changed-manifest", u"published_update.json"),
    (u"missing-signature", u"published_update.json.sig"),
    (u"another-digest", u"github_digest"),
    (u"a-strangers-key", u"signature_verifies"),
    (u"another-release", u"published_update.json")],
    ids=[u"changed-manifest", u"missing-signature", u"another-digest", u"a-strangers-key",
         u"another-release"])
def test_a_published_release_that_is_not_the_local_one_fails(tmp_path, damage, claim):
    u"""Each damage is caught by the claim NAMED for it -- ⚠ not merely by some
    claim: two guards on one fact hide each other's deletion.
    `another-release`: a whole, VALID trio -- signed with a trusted key -- that is not
    the one built here (an older upload, the wrong folder). It agrees with itself,
    so only the comparison with the LOCAL files can catch it."""
    zip_path, public, files, release = _release_trio(tmp_path)
    keys = (public,)
    if damage == u"another-release":
        other = tmp_path / u"other"
        other.mkdir()
        _zip, other_key, files, _r = _release_trio(other, extra={u"hato/_internal/x.dll": b"x"})
        for asset in release[u"assets"]:
            body = files[asset[u"browser_download_url"]]
            asset[u"digest"] = u"sha256:" + hashlib.sha256(body).hexdigest()
        keys = (public, other_key)
    elif damage == u"changed-manifest":
        url = [u for u in files if u.endswith(update.MANIFEST_NAME)][0]
        files[url] = files[url].replace(b"a note", b"A note")
    elif damage == u"missing-signature":
        release[u"assets"] = [a for a in release[u"assets"]
                              if a[u"name"] != update.SIGNATURE_NAME]
    elif damage == u"another-digest":
        release[u"assets"][0][u"digest"] = u"sha256:" + u"0" * 64
    else:
        keys = (_key(tmp_path, "stranger.pem")[1],)
    from hato.dev import claims
    got = signing.check_published(zip_path, keys=keys, fetch=_github(release, files))
    states = dict((c.name, c.state) for c in got)
    assert states.get(claim) == claims.FAIL, (damage, claim, got)


def test_a_detached_start_really_starts_the_program(tmp_path):
    u"""The one real process the hand-off starts, with its flags: the OS must take
    them (a breakaway a job forbids falls back rather than failing)."""
    import sys
    proc = update.start_detached([sys.executable, u"-c", u"import sys; sys.exit(3)"])
    assert proc.wait(30) == 3


def test_a_hand_off_with_nothing_staged_is_a_sentence(tmp_path):
    with pytest.raises(update.StageError) as caught:
        update.hand_off(tmp_path / "absent.json", start=lambda argv: None)
    assert u"no update ready" in u"%s" % caught.value


# ---------------------------------------------------------------------------
# `hato update` -- the command the window, the tray and a person all use
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ADVERSARY 2026-09-24 (LAYER 11z) -- surface A, check + stage, and C3b/C4/C9
# ---------------------------------------------------------------------------

def _nested(depth=60000):
    return (u"[" * depth).encode("ascii")


def test_a_manifest_nested_past_pythons_limit_is_refused_by_name():
    u"""A1: 60 KB of `[` raised RecursionError -- not a ValueError -- out of the parser."""
    with pytest.raises(update.ManifestError) as caught:
        update.parse_manifest(_nested())
    assert u"nested" in u"%s" % caught.value


def test_a_release_whose_manifest_is_nested_past_pythons_limit_is_still_told(tmp_path,
                                                                           monkeypatch):
    u"""🚨 A1: the manifest is read for its NOTES before the signature, so anyone able to
    publish a release could raise out of every install's check. ⭐ Told -- a release IS
    out -- never NONE: that would be the check's own net catching what the parser let
    through (the net has its own check, below)."""
    wire, _manifest = _published(tmp_path, monkeypatch)
    url = [u for u in wire.files if u.endswith(update.MANIFEST_NAME)][0]
    wire.files[url] = _nested()
    got = _check(wire, tmp_path)
    assert (got.kind, got.version) == (update.TELL, u"1.0.5"), got


def test_the_check_never_raises_whatever_escapes_the_decision(monkeypatch):
    u"""A1: `check()` says *never raises*; its net is what holds that for the next
    error nobody has thought of yet."""
    def broken(*args):
        raise RuntimeError(u"something new")

    monkeypatch.setattr(update, "_decide", broken)
    assert update.check(u"1.0.4").kind == update.NONE


@pytest.mark.parametrize("name", [update.STATE_NAME, update.PENDING_NAME, update.RESULT_NAME])
def test_a_local_file_nested_past_pythons_limit_reads_as_absent(tmp_path, monkeypatch, name):
    u"""A1, the local readers: the state, the hand-off and the result each read as
    absent, never as a crash of the window, the tray or a command."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    install = _installed(tmp_path)
    root = update.stage_root(str(install))
    os.makedirs(str(root), exist_ok=True)
    target = update.state_path() if name == update.STATE_NAME else root / name
    os.makedirs(os.path.dirname(str(target)), exist_ok=True)
    with open(str(target), "wb") as handle:
        handle.write(_nested())
    assert update.load_state() == {} or name != update.STATE_NAME
    assert update.staged_version(str(install), u"1.0.4") is None
    assert update.reconcile(str(install)) is None
    if name == update.PENDING_NAME:
        with pytest.raises(update.StageError):
            update.hand_off(str(target), start=lambda argv: u"proc")


@pytest.mark.parametrize("text", [u"1.0.4\n", u"01.0.4", u"1.00.4", u"0001.0000.0004",
                                  u"١.٠.٤", u"１.０.４",
                                  u"१.०.४"])
def test_a_version_is_ascii_digits_with_no_leading_zero_and_nothing_after(text):
    u"""A7: `\\d` took any Unicode digit, `$` a trailing newline, `{1,4}` a leading zero
    -- and this layer compares versions as STRINGS in six places."""
    assert update.parse_version(text) is None, text


def test_a_version_with_a_zero_part_is_still_a_version():
    assert update.parse_version(u"0.0.1") == (0, 0, 1)
    assert update.parse_version(u"10.20.3000") == (10, 20, 3000)


def test_a_stage_that_lost_a_file_is_no_longer_waiting(tmp_path, monkeypatch):
    u"""🚨 A5: a security program quarantining the staged updater left a stage that read
    as waiting until a newer release came out -- every hand-off failing, the tray's
    loop logging it every minute. Whole, or not staged."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) == u"1.0.5"
    with open(pending, encoding="utf-8") as handle:
        staged = json.load(handle)[u"staged"]
    os.remove(os.path.join(staged, update.SWAPPER_NAME))
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) is None


def test_a_stage_that_lists_nothing_is_not_waiting(tmp_path, monkeypatch):
    u"""The 11z gate (G1): M11f-29 survived -- since A5 a stage missing any entry it
    lists is not waiting, which made the folder check decide nothing alone -- except
    for a hand-off listing NONE, where `all()` of nothing is true: it read as waiting."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    hand[u"entries"] = {}
    update.save_json(pending, hand)
    assert update.staged_version(str(install), u"1.0.4", root=str(root)) is None


def test_two_installs_never_share_a_staging_root(tmp_path, monkeypatch):
    u"""🚨 A6: two copies of hato on one volume shared `update\\`: one copy found the
    other's stage waiting, and its hand-off swapped the OTHER folder."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    one, two = tmp_path / u"Desktop" / u"hato", tmp_path / u"Downloads" / u"hato"
    one.mkdir(parents=True)
    two.mkdir(parents=True)
    assert update.stage_root(str(one)) != update.stage_root(str(two))
    assert update.stage_root(str(one)) == update.stage_root(str(one) + os.sep), \
        u"one folder, spelled twice, got two roots"


def test_a_stage_prepared_for_another_copy_is_not_waiting_here(tmp_path, monkeypatch):
    u"""A6, the second wall: a hand-off naming another folder -- a moved install, an
    older shared root -- is never this copy's."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    other = tmp_path / u"another" / u"hato"
    other.mkdir(parents=True)
    assert update.staged_version(str(other), u"1.0.4", root=str(root)) is None
    with pytest.raises(update.StageError) as caught:
        update.hand_off(pending, install=str(other), start=lambda argv: u"proc")
    assert u"another copy" in u"%s" % caught.value
    update.hand_off(pending, install=str(install), start=lambda argv: u"proc")


@pytest.mark.parametrize("current, why", [(u"1.0.5", u"not newer"), (u"1.0.6", u"not newer"),
                                          (u"1.0.3", u"prepared by")],
                         ids=[u"the-same-version", u"a-newer-copy", u"another-writer"])
def test_a_hand_off_is_refused_unless_it_updates_this_copy(tmp_path, monkeypatch, current, why):
    u"""🚨 A3: `hato update --apply` put a 1.0.2 staged under 1.0.1 over a hand-installed
    1.0.3, and kept 1.0.3's files as `previous\\1.0.1`. The hand-off now knows the copy
    it hands off from: written by it, and newer than it."""
    # ⚠ each wall ALONE: for "not newer" the stage is this copy's own, so only the
    # version can be what is wrong -- the "prepared by" wall would otherwise fire first
    writer = current if why == u"not newer" else u"1.0.4"
    install, root, pending = _staged_over(tmp_path, monkeypatch, current=writer)
    started = []
    with pytest.raises(update.StageError) as caught:
        update.hand_off(pending, current=current, install=str(install), start=started.append)
    assert started == [] and why in u"%s" % caught.value, u"%s" % caught.value
    (tmp_path / u"control").mkdir()
    control = _staged_over(tmp_path / u"control", monkeypatch)
    update.hand_off(control[2], current=u"1.0.4", install=str(control[0]), start=started.append)
    assert started, u"the control: the copy that wrote it may hand it off"


def test_a_swap_that_touched_nothing_turns_nothing_away(tmp_path, monkeypatch):
    u"""🚨 C3b: a swap that gave up because hato was still running changed NOTHING -- the
    release never failed -- and it was turned away all the same."""
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    root = tmp_path / "stage"
    _result_file(root, status=u"failed", touched=False,
                 reason=u"hato was still running, so nothing was changed")
    update.reconcile(str(tmp_path), root=str(root))
    assert update.skipped() is None, u"a release that never failed was turned away"


def test_going_back_writes_its_own_hand_off_and_turns_away_only_once_it_worked(
        tmp_path, monkeypatch):
    u"""🚨 C4: Go back OVERWROTE `pending.json` and turned the current version away
    BEFORE its hand-off could fail -- so a failed Go back left the newer staged release
    pointing BACK, and *Restart now* went back to 1.0.4 instead of on to 1.0.6."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert _swapped(pending, says=u"1.0.5")[0] == 0
    staged_before = None
    back = update.go_back_pending(str(install), u"1.0.5", root=str(root))
    assert os.path.basename(back) != update.PENDING_NAME, u"Go back took the staged hand-off"
    assert update.skipped() is None, u"turned away before anything went back"
    assert _swapped(back, says=u"1.0.4")[0] == 0
    update.reconcile(str(install), root=str(root))
    assert update.skipped() == u"1.0.5", u"what a person went back from is not turned away"
    assert staged_before is None


def test_a_go_back_with_no_updater_says_so_in_its_own_words(tmp_path, monkeypatch):
    u"""C4c: *"the new version carries no updater"* -- about a Go back, whose updater is
    THIS copy's own."""
    install, root, pending = _staged_over(tmp_path, monkeypatch)
    assert _swapped(pending, says=u"1.0.5")[0] == 0
    back = update.go_back_pending(str(install), u"1.0.5", root=str(root))
    with pytest.raises(update.StageError) as caught:
        update.hand_off(back, swapper=str(install / u"no-such-updater.exe"),
                        start=lambda argv: u"proc")
    assert u"new version" not in u"%s" % caught.value and u"go back" in u"%s" % caught.value


def test_unpack_refuses_an_escaping_member_even_past_the_name_rules(tmp_path, monkeypatch):
    u"""A9: unpack's own wall -- every target inside the folder being written -- was
    witnessed by nothing: the name rules refused every escaping name first. ⛔ Two
    guards that back each other up witness neither; this one is tested ALONE."""
    from hato import archives
    monkeypatch.setattr(archives, "unsafe_name", lambda name: None)
    zip_path = tmp_path / u"escape.zip"
    import zipfile
    with zipfile.ZipFile(str(zip_path), "w") as archive:
        archive.writestr(u"hato/../../escaped.txt", b"out")
    with pytest.raises(update.StageError):
        update.unpack(str(zip_path), str(tmp_path / u"into"))
    assert not (tmp_path / u"escaped.txt").exists()


def _args(**over):
    import argparse
    from hato.commands import update as command
    parser = argparse.ArgumentParser()
    command.register(parser)
    args = parser.parse_args([])
    for name, value in over.items():
        setattr(args, name, value)
    return args


def test_the_command_says_offline_plainly_and_never_invents_a_version(capsys, monkeypatch):
    from hato.commands import update as command
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    assert command.run(_args(), now=1000.0) == command.EXIT_OK
    assert u"did not answer" in capsys.readouterr().out
    assert command.run(_args(json=True), now=1000.0) == command.EXIT_OK
    said = json.loads(capsys.readouterr().out)
    assert (said[u"type"], said[u"kind"], said[u"version"]) == (u"update", u"none", None)


def test_the_command_tells_without_a_reason_code(capsys, monkeypatch):
    u"""⛔ The engine's vocabulary never reaches a person: `source` is a sentence."""
    from hato.commands import update as command
    monkeypatch.setattr(update, "check", lambda *a, **k: update.Decision(
        update.TELL, u"1.0.5", update.SOURCE, page=u"https://example.invalid/r"))
    command.run(_args(), now=1000.0)
    out = capsys.readouterr().out
    assert u"git pull" in out and u"1.0.5" in out and u"source\n" not in out, out


def test_if_due_answers_from_memory_without_the_network(capsys, monkeypatch):
    from hato.commands import update as command
    update.save_state({u"checked_at": 1000.0, u"decision": update.Decision(
        update.TELL, u"1.0.5", update.SOURCE).as_dict()})
    monkeypatch.setattr(update, "check", lambda *a, **k: pytest.fail(u"asked GitHub"))
    command.run(_args(if_due=True, json=True), now=1000.0 + 3600)
    said = json.loads(capsys.readouterr().out)
    assert (said[u"kind"], said[u"version"]) == (u"tell", u"1.0.5"), said


def test_a_remembered_answer_never_offers_the_version_now_installed(capsys, monkeypatch):
    u"""🚨 The answer was saved BEFORE the update installed: read back as-is, the new
    window would offer itself -- "1.0.5 is ready" on 1.0.5 -- until the next day."""
    from hato import __version__
    from hato.commands import update as command
    update.save_state({u"checked_at": 1000.0, u"decision": update.Decision(
        update.READY, __version__, notes=(u"what changed",)).as_dict()})
    monkeypatch.setattr(update, "check", lambda *a, **k: pytest.fail(u"asked GitHub"))
    command.run(_args(if_due=True, json=True), now=1000.0 + 3600)
    said = json.loads(capsys.readouterr().out)
    assert (said[u"kind"], said[u"version"]) == (u"none", __version__), said
    assert said[u"notes"] == [u"what changed"], u"the installed version's notes were lost"


def test_staging_from_the_command_streams_progress_then_says_staged(capsys, monkeypatch, tmp_path):
    from hato.commands import update as command
    decision, zip_bytes = _ready(tmp_path, monkeypatch)
    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.setattr(update, "check", lambda *a, **k: decision)
    monkeypatch.setattr(update, "stream", _serve(zip_bytes, 4096))
    monkeypatch.setattr(update, "installed_version", lambda _f: u"1.0.5")
    monkeypatch.setattr(command, "install_dir", lambda: str(install))
    assert command.run(_args(stage=True, json=True, progress=True)) == command.EXIT_OK
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    kinds = [l[u"type"] for l in lines]
    assert kinds[-1] == u"staged" and u"progress" in kinds, kinds
    assert lines[-1][u"version"] == u"1.0.5" and os.path.isfile(lines[-1][u"pending"])
    last = [l for l in lines if l[u"type"] == u"progress"][-1]
    assert last[u"done"] == last[u"total"] == len(zip_bytes)


def _frozen_at(monkeypatch, install, tray=None, others=()):
    u"""This copy frozen at `install`, a tray running as `tray` (a pid) or none, and
    `others` running beside it -> the list every stop and start is recorded in."""
    import sys
    from hato import watch
    from hato.commands import update as command
    calls = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(command, "install_dir", lambda: str(install))
    monkeypatch.setattr(command, "running_beside",
                        lambda _i: list(others) + ([tray] if tray else []))
    monkeypatch.setattr(watch, "watching_pid", lambda: tray)
    monkeypatch.setattr(watch, "stop_running_watcher", lambda: calls.append(u"stop") or tray)
    monkeypatch.setattr(update, "start_detached", lambda argv: calls.append(argv) or u"proc")
    return calls


def _said(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_apply_from_a_checkout_is_told_to_use_git(capsys, monkeypatch):
    import sys
    from hato.commands import update as command
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert command.run(_args(apply=True, json=True)) == command.EXIT_FAILED
    assert u"git pull" in _said(capsys)[u"reason"]


WINDOWS_ONLY = pytest.mark.skipif(not __import__("sys").platform.startswith("win"),
                                  reason=u"the packaged hato, and so --apply, is Windows'")


@WINDOWS_ONLY
def test_apply_is_refused_while_the_window_or_a_run_is_open(capsys, monkeypatch, tmp_path):
    u"""⛔ The swapper would wait a minute for them and give up, telling nobody."""
    from hato.commands import update as command
    from hato import __version__
    install, _root, _pending = _staged_over(tmp_path, monkeypatch, root=None,
                                            current=__version__)
    calls = _frozen_at(monkeypatch, install, tray=4242, others=[777])
    assert command.run(_args(apply=True, json=True)) == command.EXIT_FAILED
    assert u"close hato's window first" in _said(capsys)[u"reason"]
    assert calls == [], u"the tray was stopped or a swapper started: %s" % calls


@WINDOWS_ONLY
def test_apply_stops_the_tray_and_hands_off_to_start_everything_again(capsys, monkeypatch,
                                                                      tmp_path):
    from hato.commands import update as command
    from hato import __version__
    install, root, pending = _staged_over(tmp_path, monkeypatch, root=None,
                                          current=__version__)
    calls = _frozen_at(monkeypatch, install, tray=4242)
    assert command.run(_args(apply=True, json=True)) == command.EXIT_OK
    said = _said(capsys)
    assert (said[u"type"], said[u"version"]) == (u"applying", u"1.0.5"), said
    copy = os.path.join(str(root), update.swapper_copy_name(u"1.0.5"))
    assert calls == [u"stop", [copy, u"--pending", os.path.abspath(pending)]], calls
    with open(pending, encoding="utf-8") as handle:
        hand = json.load(handle)
    assert (hand[u"window"], hand[u"tray"]) == (True, True), hand


@WINDOWS_ONLY
def test_a_failed_apply_never_costs_the_tray(capsys, monkeypatch, tmp_path):
    from hato import watch
    from hato.commands import update as command
    from hato import __version__
    install, _root, pending = _staged_over(tmp_path, monkeypatch, root=None,
                                           current=__version__)
    with open(pending, encoding="utf-8") as handle:
        os.remove(os.path.join(json.load(handle)[u"staged"], update.SWAPPER_NAME))
    calls = _frozen_at(monkeypatch, install, tray=4242)
    assert command.run(_args(apply=True, json=True)) == command.EXIT_FAILED
    assert calls == [u"stop", watch.watch_argv()], u"the tray was not started again: %s" % calls


@WINDOWS_ONLY
def test_rollback_hands_off_with_the_CURRENT_swapper(capsys, monkeypatch, tmp_path):
    u"""*Go back* runs the version that wrote the hand-off -- not the kept one's."""
    from hato import __version__
    from hato.commands import update as command
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    install = _installed(tmp_path)
    kept = update.stage_root(str(install)) / u"previous" / u"0.9.9"
    (kept / u"_internal").mkdir(parents=True)
    for name in (u"hato.exe", u"hato-cli.exe", u"hato-watch.exe", u"hato-update.exe"):
        (kept / name).write_bytes(b"kept " + name.encode())
    calls = _frozen_at(monkeypatch, install)
    assert command.run(_args(rollback=True, json=True)) == command.EXIT_OK, capsys.readouterr()
    copy = calls[-1][0]
    assert not os.path.abspath(copy).startswith(str(install) + os.sep), \
        u"the swapper would run from INSIDE the folder it empties: %s" % copy
    with open(copy, "rb") as handle:
        assert handle.read() == b"old hato-update.exe", u"the kept version's swapper ran"
    with open(calls[-1][2], encoding="utf-8") as handle:
        hand = json.load(handle)
    assert (hand[u"from"], hand[u"to"], hand[u"going_back"]) == (__version__, u"0.9.9", True)


@pytest.fixture
def auto(monkeypatch, tmp_path):
    u"""`hato update --auto` as the tray and the daily run call it: frozen, Windows,
    automatic, its own store -> {checks, stages, run()}."""
    import sys
    from hato import config
    from hato.commands import update as command
    # ⚠ WINDOWS', AS `--apply` IS: off Windows `--auto` returns before it asks
    # anything, by design, so every check below would fail there on the platform --
    # not on hato (read before the 1.0.4 push; `WINDOWS_ONLY` above)
    if not sys.platform.startswith("win"):
        pytest.skip(u"the packaged hato, and so --auto, is Windows'")
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(command, "install_dir", lambda: str(tmp_path / "install"))
    world = {u"checks": 0, u"stages": [], u"answer": update.Decision(update.NONE, u"0.0.1"),
             u"auto": True}

    class Cfg(object):
        pass

    def load():
        cfg = Cfg()
        cfg.auto_update = world[u"auto"]
        return cfg

    def check(*a, **k):
        world[u"checks"] += 1
        return world[u"answer"]

    monkeypatch.setattr(config, "load", load)
    monkeypatch.setattr(update, "check", check)
    monkeypatch.setattr(update, "stage", lambda decision, *a, **k: world[u"stages"].append(
        decision.version))
    world[u"run"] = lambda now=1000000.0: command.run(_args(auto=True), now=now)
    return world


def _newer():
    from hato import __version__
    major, minor, patch = update.parse_version(__version__)
    return u"%d.%d.%d" % (major, minor, patch + 1)


def test_auto_fetches_a_new_release_quietly(auto):
    auto[u"answer"] = update.Decision(update.READY, _newer())
    assert auto[u"run"]() == 0
    assert (auto[u"checks"], auto[u"stages"]) == (1, [_newer()])


@pytest.mark.parametrize("why", [u"switched-off", u"from-source", u"turned-away"])
def test_auto_does_nothing_when_it_may_not(auto, monkeypatch, why):
    import sys
    auto[u"answer"] = update.Decision(update.READY, _newer())
    if why == u"switched-off":
        auto[u"auto"] = False
    elif why == u"from-source":
        monkeypatch.delattr(sys, "frozen", raising=False)
    else:
        update.skip(_newer())
    assert auto[u"run"]() == 0
    assert auto[u"stages"] == [], why


def test_auto_asks_github_once_a_day(auto):
    auto[u"run"](now=1000000.0)
    auto[u"run"](now=1000000.0 + 3600)
    assert auto[u"checks"] == 1, u"asked GitHub twice in a day"


def test_auto_fetches_what_the_window_already_found_today(auto):
    u"""⚠ The window's check made today's answer; `--auto` must not wait a day to
    fetch it just because the answer is not its own."""
    update.save_state({u"checked_at": 1000000.0 - 60,
                       u"decision": update.Decision(update.READY, _newer()).as_dict()})
    auto[u"answer"] = update.Decision(update.READY, _newer())
    auto[u"run"]()
    assert auto[u"stages"] == [_newer()]


def test_auto_never_fetches_a_version_that_just_failed_to_go_in(auto, tmp_path):
    u"""The swap failed and put the old version back; the tray's next `--auto` reads
    that first -- or it would fetch the same version and try again every night."""
    root = update.stage_root(str(tmp_path / "install"))
    _result_file(root, status=u"failed", to=_newer())
    auto[u"answer"] = update.Decision(update.READY, _newer())
    auto[u"run"]()
    assert auto[u"stages"] == [], u"a version that failed to go in was fetched again"


def test_auto_writes_nothing_when_there_is_nothing_to_do(auto):
    from hato import paths
    log = str(paths.default_log_path())
    before = open(log, encoding="utf-8").read() if os.path.exists(log) else u""
    auto[u"run"]()
    after = open(log, encoding="utf-8").read() if os.path.exists(log) else u""
    assert auto[u"checks"] == 1 and after == before, u"an up-to-date day was logged"


def test_a_staging_failure_is_said_and_written_to_the_log(capsys, monkeypatch):
    from hato import paths
    from hato.commands import update as command
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    assert command.run(_args(stage=True, json=True)) == command.EXIT_FAILED
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert said[u"type"] == u"error" and said[u"reason"], said
    with open(str(paths.default_log_path()), encoding="utf-8") as handle:
        assert u"=== hato update " in handle.read()


def test_the_command_is_reachable_through_the_dispatch_table(capsys, monkeypatch):
    u"""⭐ `cli.COMMANDS` is what the frozen build derives its imports from."""
    from hato import cli
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    assert cli.main([u"update", u"--json"]) == 0
    assert json.loads(capsys.readouterr().out)[u"type"] == u"update"


def test_verify_release_fails_a_release_installs_are_never_offered(tmp_path):
    u"""🚨 A4: verify-release read the TAG's release and never `releases/latest` -- the
    one an install asks for. A release that is not the latest verified green."""
    from hato.dev import claims
    zip_path, public, files, release = _release_trio(tmp_path)
    got = signing.check_published(zip_path, keys=(public,), fetch=_github(
        release, files, latest=dict(release, tag_name=u"v1.0.6")))
    assert dict((c.name, c.state) for c in got)[u"the_latest_release"] == claims.FAIL, got


def test_verify_release_fails_a_signed_release_published_as_another_version(tmp_path):
    u"""🚨 A4: a zip built and signed as 1.0.5, renamed 1.0.6 and published as v1.0.6
    with its valid manifest, passed all seven claims -- and every install refused it."""
    import shutil
    from hato.dev import claims
    zip_path, public, _files, _release = _release_trio(tmp_path)
    renamed = tmp_path / u"hato-1.0.6-windows-x64.zip"
    shutil.copy(str(zip_path), str(renamed))
    base = u"https://github.com/SonicSandbox/hato/releases/download/v1.0.6/"
    files, assets = {}, []
    for name, local in ((renamed.name, renamed),
                        (update.MANIFEST_NAME, tmp_path / update.MANIFEST_NAME),
                        (update.SIGNATURE_NAME, tmp_path / update.SIGNATURE_NAME)):
        body = local.read_bytes()
        files[base + name] = body
        assets.append({u"name": name, u"size": len(body), u"browser_download_url": base + name,
                       u"digest": u"sha256:" + hashlib.sha256(body).hexdigest()})
    got = signing.check_published(renamed, keys=(public,), fetch=_github(
        {u"tag_name": u"v1.0.6", u"assets": assets}, files))
    states = dict((c.name, c.state) for c in got)
    assert states[u"manifest_names_this_release"] == claims.FAIL, got


def test_verify_release_asks_the_client_itself(tmp_path):
    u"""A4: the check an install makes, made -- a zip asset GitHub lists at another size
    is the same bytes by every other claim here, and every install calls it MISMATCH."""
    from hato.dev import claims
    zip_path, public, files, release = _release_trio(tmp_path)
    release[u"assets"][0][u"size"] += 1
    got = signing.check_published(zip_path, keys=(public,), fetch=_github(release, files))
    states = dict((c.name, c.state) for c in got)
    assert states[u"an_install_takes_it"] == claims.FAIL, got


def test_auto_tries_a_failing_stage_once_a_day_not_every_hour(auto, monkeypatch):
    u"""🚨 A2: the READY answer is remembered BEFORE staging, so a stage that failed the
    same way every time was owed again an hour later -- 24 downloads of 67 MB a day."""
    tries = []

    def failing(decision, *a, **k):
        tries.append(decision.version)
        raise update.StageError(u"the downloaded hato would not start to say its version")

    monkeypatch.setattr(update, "stage", failing)
    auto[u"answer"] = update.Decision(update.READY, _newer())
    for hour in range(24):
        auto[u"run"](now=1000000.0 + hour * 3600)
    assert tries == [_newer()], u"%d attempts in one day" % len(tries)
    auto[u"run"](now=1000000.0 + 25 * 3600)
    assert len(tries) == 2, u"never tried again the next day"


def test_auto_never_fetches_a_release_already_staged(auto, monkeypatch):
    u"""A10: `--auto`'s *already staged* guard was witnessed by nothing -- a mutant that
    fetched the staged 67 MB again at every due check survived."""
    monkeypatch.setattr(update, "staged_version", lambda install, current: _newer())
    auto[u"answer"] = update.Decision(update.READY, _newer())
    auto[u"run"]()
    assert auto[u"checks"] == 1 and auto[u"stages"] == [], u"what is staged was fetched again"


def test_an_answer_that_could_not_tell_is_never_remembered(monkeypatch):
    u"""C9: saved, an offline NONE hid a release already downloaded and verified for a
    whole day -- no pill, and *When I close hato* installed nothing."""
    from hato.commands import update as command
    update.save_state({u"checked_at": 5.0,
                       u"decision": update.Decision(update.READY, u"9.9.9").as_dict()})
    monkeypatch.setenv("HATO_NO_NETWORK", "1")
    command.run(_args(json=True), now=1000.0)
    state = update.load_state()
    assert state[u"checked_at"] == 5.0 and state[u"decision"][u"kind"] == u"ready", state


@WINDOWS_ONLY
def test_apply_hands_off_only_what_this_copy_prepared(capsys, monkeypatch, tmp_path):
    u"""🚨 A3: 1.0.2 staged under 1.0.1 and never applied; 1.0.3 installed by hand;
    `hato update --apply` put 1.0.2 over it -- and kept 1.0.3 as `previous\\1.0.1`."""
    from hato.commands import update as command
    install, _root, _pending = _staged_over(tmp_path, monkeypatch, root=None, current=u"0.0.1")
    calls = _frozen_at(monkeypatch, install)
    assert command.run(_args(apply=True, json=True)) == command.EXIT_FAILED
    assert u"prepared by hato 0.0.1" in _said(capsys)[u"reason"]
    assert [c for c in calls if isinstance(c, list)] == [], u"a swapper was started"

