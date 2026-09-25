# -*- coding: utf-8 -*-
u"""
`python -m hato.dev` -- the five release commands (spec/RUNBOOK.md §Step 6).

⭐ EVERY SCANNER HERE IS PROVEN ABLE TO FAIL. A scanner that cannot find a
planted secret is worse than none, so for each one the plant IS the test: a fake
key in five encodings, a key inside a wheel and inside an sdist, an ASS
`Dialogue:` line, an SRT body, a WebVTT body, a page of Japanese, a
`hato.config.json` inside a wheel, and a tracked file edited after the stamp.
Every one names the check that must go red.

⛔ WHAT THIS SUITE STRUCTURALLY CANNOT COVER:

  * The real release. Every wheel here is SYNTHETIC -- built by `make_wheel`
    below, not by `python -m build` -- so nothing here proves `pyproject.toml`
    produces a wheel of this shape. `audit-wheel` run on the real artifact is
    the only thing that can.
  * `verify-install`'s venv. Creating one is slow and needs the network, so this
    suite drives its PURE half -- the parent walk, the PATH scrub, the tool-list
    parse and the assertion set -- against recorded outcomes. ⚠ It therefore
    cannot see a `pip install` that fails, a console script that is not written,
    or a dependency that does not resolve.
  * The real jimaku key. ⛔ Never read here: every key in this file is the
    literal fake below, and the suite asserts no output ever carries it.
  * Whether `stamp` writes the REAL `hato/__init__.py` correctly. It is another
    builder's file (and the vault auto-commits), so `stamp`'s write path is
    exercised only against synthetic trees; only `--check`, which is read-only,
    ever touches this checkout.
"""
import io
import json
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from hato.dev import anchor, claims, install, scan, stamp, wheel
from hato.dev import __main__ as dispatch

ROOT = Path(__file__).resolve().parent.parent

#: ⛔ THE ONLY KEY IN THIS FILE. The real one is never read, never resolved and
#: never written -- LEDGER-HOT.md: never write a secret anywhere inside TheForge,
#: not even for a minute, because the vault auto-commits every ~5 minutes.
FAKE_KEY = u"hk_DEVTOOLS_FAKE_zzzzzzzzWXYZ"
FAKE_HINT = u"\u2026WXYZ"

#: Enough of the GPL-3.0 header for the detector; ⛔ not a transcription of the
#: licence (PYPI-PUBLISHING-DRAFT: the canonical text is fetched, never typed).
GPL_SNIPPET = (u"                    GNU GENERAL PUBLIC LICENSE\n"
               u"                       Version 3, 29 June 2007\n")
THIRD_PARTY = (u"# Dependency licences\n\n"
               u"- anitopy -- MPL-2.0\n- guessit -- LGPL-3.0\n")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def by_name(results):
    return dict((c.name, c) for c in results)


def states(results):
    return dict((c.name, c.state) for c in results)


def red(results, name):
    """The one failing claim called `name`. Asserts it is the ONLY failure."""
    got = by_name(results)
    assert name in got, "no claim called %r (have: %s)" % (name, sorted(got))
    assert got[name].state == claims.FAIL, "%s did not go red: %s" % (name, got[name].saw)
    return got[name]


def all_held(results):
    bad = [(c.name, c.state, c.saw) for c in results if c.state == claims.FAIL]
    assert not bad, "claims failed: %s" % ("; ".join("%s: %s" % (n, s) for n, _, s in bad))
    assert results, "the command measured nothing"


def make_tree(base, version="0.1.0", data=None, siblings=True):
    """A synthetic source checkout: hato/__init__.py and the sibling artifacts."""
    base = Path(base)
    (base / "hato" / "dev").mkdir(parents=True, exist_ok=True)
    (base / "hato" / "__init__.py").write_bytes(
        (u'# -*- coding: utf-8 -*-\nu"""a synthetic hato."""\n'
         u'__version__ = "%s"\n' % version).encode("utf-8"))
    (base / "hato" / "cli.py").write_bytes(b"def main():\n    return 0\n")
    (base / "hato" / "dev" / "__init__.py").write_bytes(b"")
    for rel, body in (data or {}).items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    if siblings:
        (base / "hato-run.cmd").write_bytes(b"@echo off\r\n")
        (base / "pyproject.toml").write_bytes(b'[project]\nname = "hato"\n')
        (base / "LICENSE").write_bytes(GPL_SNIPPET.encode("utf-8"))
        (base / "THIRD_PARTY_LICENSES.md").write_bytes(THIRD_PARTY.encode("utf-8"))
    return base


def make_wheel(path, version="0.1.0", dist_name="hato", members=None,
               launcher=True, gpl=True, third_party=True, record=True,
               record_extra=None, record_drop=()):
    """A synthetic wheel. -> Path. `members` maps member name -> bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = "%s-%s.dist-info" % (dist_name.replace("-", "_"), version)
    inside = {
        "hato/__init__.py": (u'__version__ = "%s"\n' % version).encode("utf-8"),
        "hato/cli.py": b"def main():\n    return 0\n",
        "%s/METADATA" % info: (u"Metadata-Version: 2.1\nName: %s\nVersion: %s\n"
                               u"Summary: synthetic\n\nbody\n"
                               % (dist_name, version)).encode("utf-8"),
        "%s/WHEEL" % info: b"Wheel-Version: 1.0\nGenerator: synthetic\n",
    }
    if launcher:
        inside["hato/hato-run.cmd"] = b"@echo off\r\n"
    if gpl:
        inside["%s/licenses/LICENSE" % info] = GPL_SNIPPET.encode("utf-8")
    if third_party:
        inside["%s/licenses/THIRD_PARTY_LICENSES.md" % info] = THIRD_PARTY.encode("utf-8")
    inside.update(members or {})
    names = sorted(inside)
    with zipfile.ZipFile(str(path), "w") as zf:
        for name in names:
            zf.writestr(name, inside[name])
        if record:
            listed = [n for n in names if n not in record_drop]
            listed.extend(record_extra or [])
            rows = u"".join(u"%s,,\n" % n for n in listed)
            rows += u"%s/RECORD,,\n" % info
            zf.writestr("%s/RECORD" % info, rows.encode("utf-8"))
    return path


def make_sdist(path, members):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(str(path), "w:gz") as tf:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tf.addfile(info, io.BytesIO(body))
    return path


def dist_with(tmp_path, name, body):
    """A `dist/`-shaped directory holding one loose file. -> the directory."""
    d = tmp_path / "dist"
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
    return d


def rendered(results, command="cmd", subject="s"):
    out, err = io.StringIO(), io.StringIO()
    code = claims.report(command, subject, results, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# ===========================================================================
# claims.report -- the shared shape
# ===========================================================================

def test_zero_claims_is_not_a_pass():
    u"""doctrine/verification: a harness that emitted no result line and exited 0
    scored green -- in the one suite written to close a blind spot."""
    code, out, err = rendered([])
    assert code == claims.EXIT_CLAIM_FAILED, "an empty claim list exited %d" % code
    assert "no_claims" in err, "the failure line did not name no_claims: %r" % err


def test_the_failure_line_is_exactly_one_line_on_stderr():
    u"""Pitfall P25: the reporter keeps the FIRST line only."""
    code, out, err = rendered([claims.ok("a", "held"),
                               claims.fail("b", "saw\nthis\nover three lines")])
    assert code == 1, "a failing claim exited %d" % code
    assert err.count("\n") == 1, "stderr had %d lines, not 1: %r" % (err.count("\n"), err)
    assert err.startswith("FAILED cmd: b -- "), "stderr did not name the claim: %r" % err


def test_a_skip_prints_and_does_not_fail():
    code, out, err = rendered([claims.ok("a", "held"), claims.skip("b", "no key")])
    assert code == 0, "a skip failed the command (exit %d)" % code
    assert "SKIP" in out and "no key" in out, "the skip was silent: %r" % out
    assert "1 skipped" in out, "the tally hid the skip: %r" % out


def test_every_failing_claim_is_named_in_the_one_line():
    code, out, err = rendered([claims.fail("a", "x"), claims.fail("b", "y")])
    assert "+1 more: b" in err, "the second failure was not named: %r" % err


# ===========================================================================
# anchor -- patch-kit's contract
# ===========================================================================

def test_an_anchored_edit_resolving_once_is_written(tmp_path):
    p = tmp_path / "f.py"
    p.write_bytes(b'__version__ = "0.0.1"\nother = 1\n')
    edit = anchor.replace_once(p, '__version__ = "0.0.1"', '__version__ = "0.1.0"')
    assert edit.matches == 1 and edit.changed, repr(edit)
    assert p.read_bytes() == b'__version__ = "0.1.0"\nother = 1\n', p.read_bytes()


@pytest.mark.parametrize("body, why", [
    (b'__version__ = "0.0.1"\n__version__ = "0.0.1"\n', "two matches"),
    (b'nothing here\n', "no match"),
], ids=["two_matches", "no_match"])
def test_an_anchor_that_does_not_resolve_once_writes_nothing(tmp_path, body, why):
    u"""TRIGGERS.md: an anchor matching twice edits the wrong place and proves
    nothing about either."""
    p = tmp_path / "f.py"
    p.write_bytes(body)
    with pytest.raises(anchor.AnchorRefused) as err:
        anchor.replace_once(p, '__version__ = "0.0.1"', '__version__ = "9.9.9"')
    assert "NOTHING WRITTEN" in str(err.value), str(err.value)
    assert p.read_bytes() == body, "the file changed on a refusal (%s)" % why


def test_a_crlf_file_keeps_its_own_line_endings(tmp_path):
    u"""patch-kit.md: line endings are per FILE, not per repo."""
    p = tmp_path / "f.py"
    p.write_bytes(b'a = 1\r\n__version__ = "0.0.1"\r\nb = 2\r\n')
    anchor.replace_once(p, '__version__ = "0.0.1"', '__version__ = "0.1.0"')
    raw = p.read_bytes()
    assert raw.count(b"\r\n") == 3, "CRLF count changed: %r" % raw
    assert raw.replace(b"\r\n", b"") .count(b"\n") == 0, "a lone LF appeared: %r" % raw


def test_a_multiline_anchor_matches_a_crlf_file(tmp_path):
    p = tmp_path / "f.py"
    p.write_bytes(b'one\r\ntwo\r\nthree\r\n')
    anchor.replace_once(p, "one\ntwo", "ONE\nTWO")
    assert p.read_bytes() == b'ONE\r\nTWO\r\nthree\r\n', p.read_bytes()


def test_an_identical_replacement_writes_nothing(tmp_path):
    p = tmp_path / "f.py"
    p.write_bytes(b'x = 1\n')
    before = p.stat().st_mtime_ns
    edit = anchor.replace_once(p, "x = 1", "x = 1")
    assert edit.matches == 1 and not edit.changed, repr(edit)
    assert p.stat().st_mtime_ns == before, "the file was rewritten needlessly"


def test_a_write_that_raises_leaves_the_original_whole(tmp_path, monkeypatch):
    u"""🚨 LEDGER-HOT.md: `open(path,'w')` truncates the moment it opens, and a
    write that then raises leaves a ZERO-BYTE file -- how tsubasa's RUNBOOK.md was
    destroyed on 2026-09-07."""
    p = tmp_path / "f.py"
    p.write_bytes(b'__version__ = "0.0.1"\n')

    def boom(src, dst):
        raise OSError("no")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        anchor.replace_once(p, '"0.0.1"', '"0.1.0"')
    assert p.read_bytes() == b'__version__ = "0.0.1"\n', "the original was damaged"
    assert list(tmp_path.glob("f.py.new-*")) == [], "a temp file was left behind"


# ===========================================================================
# stamp
# ===========================================================================

def test_the_stamp_writes_the_version_and_a_content_hash(tmp_path):
    root = make_tree(tmp_path / "t", version="0.1.0.dev0")
    all_held(stamp.write(root, "0.1.0"))
    assert claims.read_source_version(root)[0] == "0.1.0", "the version was not written"
    record = stamp.read_stamp(root)
    assert record["release"] == "0.1.0", record
    assert record["content_hash"].startswith("sha256:"), record["content_hash"]
    assert record["file_count"] == len(record["files"]), record["file_count"]


def test_the_content_hash_is_not_a_timestamp(tmp_path):
    u"""doctrine/release §2: never a timestamp -- it churns on every build in an
    auto-committing repo."""
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    first = stamp.read_stamp(root)
    stamp.write(root, "0.1.0")
    second = stamp.read_stamp(root)
    assert first["content_hash"] == second["content_hash"], "the hash moved on a re-stamp"
    assert "stamped_at" not in json.dumps(first["files"]), "the timestamp leaked into files"


def test_a_different_tree_hashes_differently(tmp_path):
    a = stamp.manifest(make_tree(tmp_path / "a", data={"hato/x.py": "a = 1\n"}))
    b = stamp.manifest(make_tree(tmp_path / "b", data={"hato/x.py": "a = 2\n"}))
    assert stamp.content_hash(a) != stamp.content_hash(b), "two trees hashed the same"


def test_a_rename_alone_changes_the_hash(tmp_path):
    a = stamp.manifest(make_tree(tmp_path / "a", data={"hato/x.py": "a = 1\n"}))
    b = stamp.manifest(make_tree(tmp_path / "b", data={"hato/y.py": "a = 1\n"}))
    assert stamp.content_hash(a) != stamp.content_hash(b), "a rename did not move the hash"


def test_the_stamp_never_hashes_itself_or_build_litter(tmp_path):
    root = make_tree(tmp_path / "t", data={"hato/__pycache__/x.cpython-310.pyc": b"\x00",
                                           "hato/x.pyc": b"\x00"})
    stamp.write(root, "0.1.0")
    hashed = set(stamp.read_stamp(root)["files"])
    assert stamp.STAMP_REL not in hashed, "the record hashed itself -- circular"
    assert not [n for n in hashed if "__pycache__" in n or n.endswith(".pyc")], sorted(hashed)


def test_the_stamp_covers_the_launcher_and_the_published_claims(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    hashed = set(stamp.read_stamp(root)["files"])
    for name in ("hato-run.cmd", "pyproject.toml", "LICENSE", "THIRD_PARTY_LICENSES.md"):
        assert name in hashed, "%s is not in the stamped ship set" % name


def test_check_holds_straight_after_a_stamp(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    all_held(stamp.check(root))


# -- ⭐ THE BREAK-CHECKS ----------------------------------------------------

def test_check_goes_red_when_a_tracked_file_is_edited(tmp_path):
    u"""⭐ THE GATE. doctrine/release §2: 'the stamper existed and was bypassed
    with a hand-written edit hours after it was built, precisely because nothing
    forced it.'"""
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    (root / "hato" / "cli.py").write_bytes(b"def main():\n    return 1\n")
    got = red(stamp.check(root), "content_unchanged")
    assert "hato/cli.py" in got.saw, "the failure did not name the file: %s" % got.saw


def test_check_goes_red_when_the_version_is_hand_bumped(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    anchor.replace_once(root / "hato" / "__init__.py",
                        '__version__ = "0.1.0"', '__version__ = "0.2.0"')
    got = red(stamp.check(root), "version_matches_stamp")
    assert "0.2.0" in got.saw and "0.1.0" in got.saw, got.saw


@pytest.mark.parametrize("action", ["add", "remove"])
def test_check_goes_red_when_the_ship_set_changes(tmp_path, action):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    if action == "add":
        (root / "hato" / "extra.py").write_bytes(b"x = 1\n")
    else:
        (root / "hato" / "cli.py").unlink()
    got = red(stamp.check(root), "ship_set_unchanged")
    assert ("extra.py" if action == "add" else "cli.py") in got.saw, got.saw


def test_check_goes_red_when_nothing_has_been_stamped(tmp_path):
    root = make_tree(tmp_path / "t")
    got = red(stamp.check(root), "stamp_file")
    assert "stamp --release" in got.saw, got.saw


def test_check_is_read_only(tmp_path):
    u"""⛔ The gate runs in front of an upload; it must not be able to fix itself."""
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    before = dict((p, p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file())
    (root / "hato" / "cli.py").write_bytes(b"changed = 1\n")
    before[root / "hato" / "cli.py"] = b"changed = 1\n"
    stamp.check(root)
    after = dict((p, p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file())
    assert after == before, "--check wrote to the tree"


def test_the_release_number_must_be_declared_the_first_time(tmp_path):
    root = make_tree(tmp_path / "t")
    with pytest.raises(claims.Fault) as err:
        stamp.write(root, None)
    assert "DECISION" in str(err.value), str(err.value)


def test_the_second_stamp_may_reuse_the_declared_number(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    all_held(stamp.write(root, None))
    assert stamp.read_stamp(root)["release"] == "0.1.0"


@pytest.mark.parametrize("bad", ["0.1", "v0.1.0", "2026-09-17", "0.1.0-rc1",
                                 "latest", "", "0.1.0.dev"])
def test_a_release_number_that_is_not_one_is_refused(tmp_path, bad):
    u"""PYPI-PUBLISHING-DRAFT §2.7: version numbers are burned for good."""
    root = make_tree(tmp_path / "t")
    with pytest.raises(claims.Fault) as err:
        stamp.write(root, bad)
    assert "release number" in str(err.value), str(err.value)


@pytest.mark.parametrize("good", ["0.1.0", "1.2.3", "0.1.0rc1", "0.1.0a1",
                                  "0.1.0.post1", "0.1.0.dev0"])
def test_the_release_forms_this_project_publishes_are_accepted(tmp_path, good):
    root = make_tree(tmp_path / ("t" + re.sub(r"\W", "", good)))
    all_held(stamp.write(root, good))


def test_a_version_line_that_does_not_resolve_once_is_a_fault(tmp_path):
    root = make_tree(tmp_path / "t")
    (root / "hato" / "__init__.py").write_bytes(
        b'__version__ = "0.1.0"\n__version__ = "0.1.0"\n')
    with pytest.raises(claims.Fault) as err:
        claims.read_source_version(root)
    assert "exactly 1" in str(err.value), str(err.value)


def test_the_stamper_asserts_the_record_it_just_wrote(tmp_path):
    u"""doctrine/evidence: assert something about the artefact you just produced."""
    root = make_tree(tmp_path / "t")
    got = by_name(stamp.write(root, "0.1.0"))
    assert "stamp_satisfies_check" in got, sorted(got)
    assert got["stamp_satisfies_check"].state == claims.OK, got["stamp_satisfies_check"].saw


def test_find_root_refuses_a_directory_with_no_package(tmp_path):
    with pytest.raises(claims.Fault):
        claims.find_root(str(tmp_path))


# ===========================================================================
# audit-wheel
# ===========================================================================

def test_a_good_wheel_holds_every_claim(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    got = wheel.audit(make_wheel(tmp_path / "dist" / "hato-0.1.0-py3-none-any.whl"), root)
    all_held(got)
    assert states(got)["version_matches_stamp"] == claims.OK, states(got)


def test_a_dev_config_in_the_wheel_is_caught_by_name(tmp_path):
    u"""🚨 PITFALL P6, THE WORST IN THE CORPUS. tsubasa 0.1.0 shipped its dev
    config, `cache_root()` read it, and `sync()` raised ConfigError for every
    `pip install` user. Every check was green because every check ran inside a
    checkout."""
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "hato-0.1.0-py3-none-any.whl",
                   members={"hato.config.json": b'{"project": "hato"}'})
    got = red(wheel.audit(w, root), "no_dev_config")
    assert "P6" in got.saw and "hato.config.json" in got.saw, got.saw


def test_a_dev_config_nested_inside_the_wheel_is_caught_too(tmp_path):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl",
                   members={"hato/data/hato.config.json": b"{}"})
    red(wheel.audit(w, root), "no_dev_config")


def test_a_metadata_name_that_was_never_renamed_is_caught(tmp_path):
    u"""PITFALL P1: tsubasa's rename reached its README and its release workflow
    and NOT `name`, and `pip install` failed with 'inconsistent name'. Found by
    chance."""
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl", dist_name="hato-sync")
    got = red(wheel.audit(w, root), "metadata_name")
    assert "inconsistent name" in got.saw and "P1" in got.saw, got.saw


@pytest.mark.parametrize("declared", ["hato", "Hato", "HATO"])
def test_the_name_comparison_normalises_per_pep503(tmp_path, declared):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / ("w-%s.whl" % declared), dist_name=declared)
    assert by_name(wheel.audit(w, root))["metadata_name"].state == claims.OK


def test_a_wheel_built_before_the_stamp_is_caught(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.2.0")
    w = make_wheel(tmp_path / "dist" / "w.whl", version="0.1.0")
    got = wheel.audit(w, root)
    assert states(got)["metadata_version"] == claims.FAIL, states(got)
    assert states(got)["version_matches_stamp"] == claims.FAIL, states(got)
    assert "0.2.0" in by_name(got)["metadata_version"].saw


def test_version_matches_stamp_is_a_loud_skip_when_nothing_is_stamped(tmp_path):
    u"""doctrine/verification: a skip is not a pass, and it must SAY so."""
    root = make_tree(tmp_path / "t")
    got = by_name(wheel.audit(make_wheel(tmp_path / "dist" / "w.whl"), root))
    assert got["version_matches_stamp"].state == claims.SKIP, got["version_matches_stamp"].saw
    assert "stamp" in got["version_matches_stamp"].saw


def test_a_launcher_missing_from_the_REPOSITORY_ROOT_is_caught(tmp_path):
    """🚨 INVERTED 2026-09-17, BY A RULING, AND THE OLD VERSION OF THIS CHECK
    IS WHY THE FIRST PUBLIC CI RUN'S WHEEL JOB WAS RED.

    It used to build a wheel with `launcher=False` and assert the claim went
    red -- i.e. it pinned *"hato-run.cmd must be INSIDE the wheel"*, which is
    what `spec/10-deployment.md` said. ⛔ That was never implementable:
    `package-data` only reaches inside `hato/`, the launcher is at the
    repository root, and moving it there would break the PYTHONPATH guard that
    makes it work at all.

    ⭐ Sonic ruled the question away -- hato ships as a standalone run from a
    clone, with no wheel route -- so the root IS the right place and the claim
    now guards the thing that can still go wrong: the launcher vanishing.

    ⚠ Only ONE thing changes from a good tree: the launcher is deleted. Turning
    `siblings=False` off would also drop LICENSE, the notices and pyproject,
    and then several claims fail at once and this check would pass for a
    reason it never named.
    """
    root = make_tree(tmp_path / "t")
    (root / "hato-run.cmd").unlink()
    w = make_wheel(tmp_path / "dist" / "w.whl", launcher=False)
    got = red(wheel.audit(w, root), "launcher")
    assert "hato-run.cmd" in got.saw, got.saw


def test_a_launcher_absent_from_the_wheel_is_FINE_when_it_is_at_the_root(tmp_path):
    """⭐ The other half of the ruling, and the half a deletion would lose.

    There is no wheel route, so the launcher not being in the wheel is the
    expected state -- not a finding. Without this check, someone restoring the
    old "must be in the wheel" assertion would see every test still green.
    """
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl", launcher=False)
    got = by_name(wheel.audit(w, root))["launcher"]
    assert got.state != claims.FAIL, (
        "the launcher claim went red for a wheel that simply does not carry "
        "the launcher, which is the ruled delivery shape: %s" % got.saw)


def test_a_missing_gpl3_notice_is_caught(tmp_path):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl", gpl=False)
    got = red(wheel.audit(w, root), "gpl3_notice")
    assert "Version 3" in got.saw, got.saw


def test_a_licence_file_that_is_not_gpl3_does_not_count(tmp_path):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl", gpl=False,
                   members={"hato-0.1.0.dist-info/licenses/LICENSE":
                            b"MIT License\nPermission is hereby granted\n"})
    red(wheel.audit(w, root), "gpl3_notice")


@pytest.mark.parametrize("body, missing", [
    (u"- anitopy -- MPL-2.0\n", "guessit"),
    (u"- guessit -- LGPL-3.0\n", "anitopy"),
])
def test_a_dependency_licence_list_missing_one_dependency_is_caught(tmp_path, body, missing):
    u"""anitopy is MPL-2.0 and guessit is LGPL-3.0; both require their notice."""
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / ("w-%s.whl" % missing), third_party=False,
                   members={"hato-0.1.0.dist-info/licenses/THIRD_PARTY_LICENSES.md":
                            body.encode("utf-8")})
    got = red(wheel.audit(w, root), "dependency_licences")
    assert "anitopy" in got.saw and "guessit" in got.saw, got.saw


@pytest.mark.parametrize("member", [
    "tests/test_client.py",
    "hato/tests/test_x.py",
    "_runs/2026-09-17.log",
    "hato/__pycache__/cli.cpython-310.pyc",
    ".pytest_cache/CACHEDIR.TAG",
    "hato.egg-info/PKG-INFO",
    "hato/mutbak-cli.py",
    "hato/cli.py.tmp",
])
def test_every_stray_pattern_is_caught(tmp_path, member):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / ("w-%d.whl" % abs(hash(member))),
                   members={member: b"x"})
    got = red(wheel.audit(w, root), "no_strays")
    assert member in got.saw, got.saw


def test_a_runtime_data_file_missing_from_the_wheel_is_caught(tmp_path):
    u"""PITFALL P7: 'a wheel without its data would install, import and run with
    no error' -- the loaders fail open, so nothing complains."""
    root = make_tree(tmp_path / "t", data={"hato/data/aliases.json": b'{"a": 1}'})
    w = make_wheel(tmp_path / "dist" / "w.whl")
    got = red(wheel.audit(w, root), "runtime_data")
    assert "hato/data/aliases.json" in got.saw and "P7" in got.saw, got.saw


def test_a_runtime_data_file_that_does_ship_holds_the_claim(tmp_path):
    root = make_tree(tmp_path / "t", data={"hato/data/aliases.json": b'{"a": 1}'})
    w = make_wheel(tmp_path / "dist" / "w.whl",
                   members={"hato/data/aliases.json": b'{"a": 1}'})
    got = by_name(wheel.audit(w, root))["runtime_data"]
    assert got.state == claims.OK, got.saw
    assert "1 of 1" in got.saw, "the denominator was not printed: %s" % got.saw


def test_the_runtime_data_claim_prints_a_zero_denominator(tmp_path):
    u"""doctrine/verification: print the denominator, so a vacuous pass is
    visible at a glance rather than reading as a tick ('0 broken of 0')."""
    root = make_tree(tmp_path / "t")
    got = by_name(wheel.audit(make_wheel(tmp_path / "dist" / "w.whl"), root))["runtime_data"]
    assert got.state == claims.OK and "0 non-.py files" in got.saw, got.saw


def test_the_stamp_record_is_excused_from_the_data_claim_by_name(tmp_path):
    root = make_tree(tmp_path / "t")
    stamp.write(root, "0.1.0")
    got = by_name(wheel.audit(make_wheel(tmp_path / "dist" / "w.whl"), root))["runtime_data"]
    assert got.state == claims.OK, got.saw
    assert stamp.STAMP_REL in got.saw and "excused" in got.saw, got.saw


@pytest.mark.parametrize("kwargs, what", [
    ({"record_extra": ["hato/ghost.py"]}, "listed but absent"),
    ({"record_drop": ("hato/cli.py",)}, "unlisted"),
])
def test_a_record_that_disagrees_with_the_zip_is_caught(tmp_path, kwargs, what):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / ("w-%s.whl" % what.split()[0]), **kwargs)
    got = red(wheel.audit(w, root), "record_matches_zip")
    assert what in got.saw, got.saw


def test_a_wheel_with_no_record_is_caught(tmp_path):
    root = make_tree(tmp_path / "t")
    w = make_wheel(tmp_path / "dist" / "w.whl", record=False)
    red(wheel.audit(w, root), "record_matches_zip")


@pytest.mark.parametrize("body", [b"not a zip at all", b""])
def test_a_file_that_is_not_a_wheel_is_a_tooling_fault(tmp_path, body):
    u"""doctrine/verification: a tooling fault gets its own exit code."""
    root = make_tree(tmp_path / "t")
    p = tmp_path / "dist" / "broken.whl"
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(body)
    with pytest.raises(claims.Fault):
        wheel.audit(p, root)


def test_a_wheel_with_no_metadata_is_a_tooling_fault(tmp_path):
    root = make_tree(tmp_path / "t")
    p = tmp_path / "dist" / "w.whl"
    p.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(str(p), "w") as zf:
        zf.writestr("hato/__init__.py", b"x = 1\n")
    with pytest.raises(claims.Fault) as err:
        wheel.audit(p, root)
    assert "METADATA" in str(err.value), str(err.value)


def test_an_unexpanded_glob_is_resolved(tmp_path):
    u"""⚠ The release block is bash; PowerShell hands the glob through unexpanded."""
    w = make_wheel(tmp_path / "dist" / "hato-0.1.0-py3-none-any.whl")
    assert wheel.resolve_wheel(str(tmp_path / "dist" / "hato-*.whl")) == w


def test_a_glob_matching_two_wheels_refuses_rather_than_guessing(tmp_path):
    make_wheel(tmp_path / "dist" / "hato-0.1.0-py3-none-any.whl")
    make_wheel(tmp_path / "dist" / "hato-0.2.0-py3-none-any.whl", version="0.2.0")
    with pytest.raises(claims.Fault) as err:
        wheel.resolve_wheel(str(tmp_path / "dist" / "hato-*.whl"))
    assert "matches 2 files" in str(err.value), str(err.value)


def test_a_glob_matching_nothing_is_a_fault(tmp_path):
    with pytest.raises(claims.Fault):
        wheel.resolve_wheel(str(tmp_path / "dist" / "hato-*.whl"))


def test_the_expected_distribution_name_does_not_come_from_pyproject(tmp_path):
    u"""⭐ THE WHOLE POINT OF P1. METADATA's Name comes FROM pyproject.toml, so a
    check that read the expected name from there could never disagree. This one
    holds the decision itself, so a pyproject that was never renamed is caught."""
    root = make_tree(tmp_path / "t")
    (root / "pyproject.toml").write_bytes(b'[project]\nname = "hato-sync"\n')
    w = make_wheel(tmp_path / "dist" / "w.whl", dist_name="hato-sync")
    red(wheel.audit(w, root), "metadata_name")


# ===========================================================================
# scan-secrets -- ⭐ every one of these plants the thing it must find
# ===========================================================================

NEEDLES = scan.key_needles(FAKE_KEY)

#: ⭐ SPELLED OUT, NOT READ FROM `scan.KEY_CODECS`, and this is not a style
#: choice. Parametrising over the tuple under test means a mutant that SHORTENS
#: it deletes its own witness: pytest then exits 4 with "not found: ...[utf-16-le]"
#: instead of failing the check, and the mutant reads as a SURVIVOR. Measured
#: 2026-09-17 proving M6-18 -- doctrine/verification's "the mutant silently
#: degrades to an exit-code test", arriving from the other direction.
#: `test_the_five_codecs_are_the_doctor_s_alphabet` is what ties the two together.
FIVE_CODECS = ("utf-8", "utf-16-le", "utf-16-be", "cp932", "cp1252")
#: Same hazard, same fix. Mirrors `archives.SUBTITLE_EXTS`.
SUB_EXTS = (".ass", ".ssa", ".srt", ".vtt", ".sub", ".idx", ".sup")


def test_a_planted_key_in_a_loose_file_is_found(tmp_path):
    u"""⭐ THE SINGLE MOST IMPORTANT CHECK IN THIS FILE. A scanner that cannot
    find a planted secret is worse than none."""
    d = dist_with(tmp_path, "notes.txt", u"authorization: %s\n" % FAKE_KEY)
    got = red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "key_bytes_absent")
    assert "THE KEY IS IN THE ARTIFACT" in got.saw, got.saw
    assert FAKE_KEY not in got.saw, "the failure message leaked the key"


def test_a_planted_key_inside_a_wheel_is_found(tmp_path):
    u"""🚨 A zipped secret is still a shipped secret, and `grep dist/` over a
    wheel reads compressed bytes and finds nothing -- which looks clean."""
    w = make_wheel(tmp_path / "dist" / "w.whl",
                   members={"hato/leak.py": (u'KEY = "%s"\n' % FAKE_KEY).encode("utf-8")})
    got = red(scan.scan_secrets(w.parent, NEEDLES, FAKE_HINT), "key_bytes_absent")
    assert "hato/leak.py" in got.saw, got.saw


def test_a_planted_key_inside_an_sdist_tarball_is_found(tmp_path):
    d = tmp_path / "dist"
    make_sdist(d / "hato-0.1.0.tar.gz",
               {"hato-0.1.0/leak.txt": FAKE_KEY.encode("utf-8")})
    got = red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "key_bytes_absent")
    assert "leak.txt" in got.saw, got.saw


def test_a_planted_key_inside_a_wheel_inside_an_sdist_is_found(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("leak.py", FAKE_KEY.encode("utf-8"))
    d = tmp_path / "dist"
    make_sdist(d / "outer.tar.gz", {"inner.whl": inner.getvalue()})
    red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "key_bytes_absent")


@pytest.mark.parametrize("codec", FIVE_CODECS)
def test_the_key_is_found_in_each_of_the_five_encodings(tmp_path, codec):
    d = dist_with(tmp_path, "blob-%s.bin" % codec,
                  b"\x00\x01" + FAKE_KEY.encode(codec) + b"\x02")
    red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "key_bytes_absent")


def test_a_non_ascii_key_is_found_in_bytes_utf8_alone_would_miss(tmp_path):
    u"""⭐ WHY FIVE ENCODINGS IS NOT DECORATION. For an ASCII key three of the
    five produce identical bytes; this proves the breadth does real work."""
    key = u"hk_caf\u00e9_zzzzzzzzzzzzzzWXYZ"
    assert key.encode("cp1252") != key.encode("utf-8"), "the fixture cannot show it"
    needles = scan.key_needles(key)
    d = dist_with(tmp_path, "ansi.txt", key.encode("cp1252"))
    red(scan.scan_secrets(d, needles, u"\u2026WXYZ"), "key_bytes_absent")


def test_a_clean_artifact_holds_the_claim_and_prints_its_denominator(tmp_path):
    w = make_wheel(tmp_path / "dist" / "w.whl")
    got = by_name(scan.scan_secrets(w.parent, NEEDLES, FAKE_HINT))
    assert got["key_bytes_absent"].state == claims.OK, got["key_bytes_absent"].saw
    saw = got["key_bytes_absent"].saw
    assert "member(s)" in saw and "distinct needle" in saw, saw
    assert FAKE_HINT in saw, "the readout did not say which key was searched for: %s" % saw


def test_no_output_ever_carries_the_key(tmp_path):
    u"""🚨 Only the last four characters may ever be printed (LEDGER-HOT.md)."""
    d = dist_with(tmp_path, "leak.txt", FAKE_KEY)
    results = scan.scan_secrets(d, NEEDLES, FAKE_HINT)
    code, out, err = rendered(results, "scan-secrets", str(d))
    assert code == 1, "a planted key exited %d" % code
    for text in (out, err) + tuple(c.saw for c in results):
        assert FAKE_KEY not in text, "the key appeared in output"
        assert FAKE_KEY[:12] not in text, "a 12-character prefix of the key appeared"


@pytest.mark.parametrize("line", [
    u'api_key = "Zk93jfL2mQ8xVb1pTnRs"',
    u'"jimaku_api_key": "Zk93jfL2mQ8xVb1pTnRs"',
    u'HATO_JIMAKU_KEY=Zk93jfL2mQ8xVb1pTnRs',
    u'secret: Zk93jfL2mQ8xVb1pTnRs',
    u'authToken="Zk93jfL2mQ8xVb1pTnRs"',
])
def test_a_key_shaped_literal_is_found_even_when_it_is_not_the_key(tmp_path, line):
    d = dist_with(tmp_path, "cfg.txt", line + u"\n")
    got = red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "no_key_shaped_literal")
    assert "chars" in got.saw, got.saw
    assert "Zk93jfL2mQ8xVb1pTnRs" not in got.saw, "the value was echoed back"


@pytest.mark.parametrize("line", [
    u'api_key = "xxxxxxxxxxxxxxxx"',
    u'api_key = "your_key_here_goes"',
    u'api_key = "<paste-it-here>"',
    u'api_key = os.environ["HATO_JIMAKU_KEY"]',
    u'headers["Authorization"] = self._key.reveal()',
    u'sort_key = "aaaaaaaaaaaaaaaaaa"',
    u'api_key = "TODO_fill_this_in"',
])
def test_a_placeholder_is_not_a_key_shaped_literal(tmp_path, line):
    u"""doctrine/evidence: a check that flags everything forever is how a check
    gets switched off."""
    d = dist_with(tmp_path, "cfg.txt", line + u"\n")
    got = by_name(scan.scan_secrets(d, NEEDLES, FAKE_HINT))
    assert got["no_key_shaped_literal"].state == claims.OK, got["no_key_shaped_literal"].saw


def test_a_wheels_own_record_digests_are_not_key_shaped(tmp_path):
    u"""⚠ THE FALSE-POSITIVE THAT WOULD HAVE KILLED THIS CHECK. A wheel's RECORD
    holds a base64 sha256 for every member, so an entropy-based scan would fire
    on every wheel for ever."""
    p = tmp_path / "dist" / "w.whl"
    p.parent.mkdir(exist_ok=True)
    rows = u"".join(u"hato/m%d.py,sha256=%s,1234\n" % (i, "Ab3" + "x" * 40)
                    for i in range(50))
    with zipfile.ZipFile(str(p), "w") as zf:
        zf.writestr("hato-0.1.0.dist-info/RECORD", rows.encode("utf-8"))
    got = by_name(scan.scan_secrets(p.parent, NEEDLES, FAKE_HINT))
    assert got["no_key_shaped_literal"].state == claims.OK, got["no_key_shaped_literal"].saw


def test_hato_s_own_shipping_source_holds_no_key_shaped_literal():
    u"""The positive control against the real corpus: measured 2026-09-17, the
    only two hits in the whole checkout are the deliberate fakes in tests/, which
    never ship (audit-wheel's no_strays)."""
    hits = []
    for path in sorted((ROOT / "hato").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hits.extend(scan._shaped_hits(path.as_posix(), path.read_bytes()))
    assert not hits, "hato's own source trips the scanner: %s" % hits[:3]


@pytest.mark.parametrize("header", [u"PRIVATE KEY", u"EC PRIVATE KEY", u"OPENSSH PRIVATE KEY",
                                    u"RSA PRIVATE KEY"])
def test_a_private_key_block_is_found_whatever_kind_it_is(tmp_path, header):
    u"""⭐ RUNBOOK 11a -- the update signing key is a PEM file, and this is the wall
    that keeps any private key out of anything published."""
    block = u"-----BEGIN %s-----\nMC4CAQAwBQYDK2VwBCIEIFAKEFAKEFAKE=\n-----END %s-----\n" % (header, header)
    d = dist_with(tmp_path, "notes.txt", block)
    got = red(scan.scan_secrets(d, NEEDLES, FAKE_HINT), "no_private_key_block")
    assert u"notes.txt" in got.saw, got.saw


def test_a_public_key_is_not_a_private_key_block(tmp_path):
    u"""The control: a PUBLIC key -- which hato ships on purpose -- is not flagged."""
    d = dist_with(tmp_path, "public.txt",
                  u"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAFAKE=\n-----END PUBLIC KEY-----\n")
    got = by_name(scan.scan_secrets(d, NEEDLES, FAKE_HINT))
    assert got["no_private_key_block"].state == claims.OK, got["no_private_key_block"].saw


def test_no_key_resolved_is_a_loud_skip_and_never_a_tick(tmp_path):
    w = make_wheel(tmp_path / "dist" / "w.whl")
    got = by_name(scan.scan_secrets(w.parent, {}, "(no key)", no_key_reason="no keyfile"))
    assert got["key_bytes_absent"].state == claims.SKIP, got["key_bytes_absent"].saw
    assert "DEGRADED" in got["key_bytes_absent"].saw, got["key_bytes_absent"].saw


def test_scan_secrets_without_a_key_refuses_rather_than_exiting_zero():
    u"""⛔ The suite drops the key (conftest points HATO_KEYFILE at nothing), so
    this drives the real refusal path -- and it must NOT be exit 0."""
    with pytest.raises(claims.Fault) as err:
        scan.main_secrets([str(ROOT / "hato")])
    assert "no jimaku key resolved" in str(err.value), str(err.value)


def test_an_empty_directory_is_a_fault_not_a_clean_result(tmp_path):
    u"""doctrine/verification: it passed on an empty set -- `0 broken of 0`."""
    (tmp_path / "dist").mkdir()
    with pytest.raises(claims.Fault) as err:
        list(scan.artifacts(tmp_path / "dist"))
    assert "nothing to scan" in str(err.value), str(err.value)


def test_a_missing_directory_is_a_fault(tmp_path):
    with pytest.raises(claims.Fault):
        list(scan.artifacts(tmp_path / "nope"))


def test_the_five_codecs_are_the_doctor_s_alphabet():
    u"""⚠ `hato/doctor.py`'s sniff_encoding is what this follows -- and this is
    the check that notices if the tuple above it is ever shortened."""
    assert scan.KEY_CODECS == FIVE_CODECS, \
        "the codec list changed: %s, expected %s" % (scan.KEY_CODECS, FIVE_CODECS)
    assert len(scan.key_needles(FAKE_KEY)) == 5, scan.key_needles(FAKE_KEY)


# ===========================================================================
# scan-content -- ⭐ each plants a synthetic subtitle payload
# ===========================================================================

#: ⛔ SYNTHETIC. spec/07-test-plan.md: no real media in TheForge, and
#: LEDGER-HOT.md: never bundle, mirror or redistribute subtitle content.
JP_LINES = [
    u"\u3053\u306e\u6751\u306b\u306f\u4f55\u3082\u306a\u3044\u3068\u8a00\u308f\u308c\u3066\u3044\u308b",
    u"\u3060\u304c\u5f7c\u3089\u306f\u305d\u308c\u3092\u77e5\u3089\u306a\u304b\u3063\u305f\u306e\u3060",
    u"\u660e\u65e5\u306e\u671d\u307e\u3067\u306b\u306f\u5168\u3066\u304c\u5909\u308f\u308b\u3060\u308d\u3046",
    u"\u79c1\u305f\u3061\u306f\u305a\u3063\u3068\u3053\u3053\u3067\u5f85\u3063\u3066\u3044\u307e\u3057\u305f",
]

SRT_BODY = (u"1\n00:00:01,000 --> 00:00:03,500\n%s\n\n"
            u"2\n00:00:04,000 --> 00:00:06,250\n%s\n\n" % (JP_LINES[0], JP_LINES[1]))
VTT_BODY = (u"WEBVTT\n\n00:00:01.000 --> 00:00:03.500\n%s\n\n"
            u"00:00:04.000 --> 00:00:06.250\n%s\n" % (JP_LINES[0], JP_LINES[1]))
ASS_BODY = (u"[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
            u"Format: Layer, Start, End, Style, Text\n"
            u"Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,%s\n" % JP_LINES[0])
JP_DOCUMENT = u"\n".join(JP_LINES * 12)


def test_a_planted_ass_dialogue_line_is_rejected(tmp_path):
    u"""⭐ The plant the brief names. One `Dialogue:` line is enough."""
    d = dist_with(tmp_path, "payload.bin", ASS_BODY)
    got = red(scan.scan_content(d), "no_ass_events")
    assert "Dialogue line" in got.saw and "[Events]" in got.saw, got.saw


def test_a_planted_ass_dialogue_line_with_no_events_header_is_still_rejected(tmp_path):
    d = dist_with(tmp_path, "payload.bin",
                  u"Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,%s\n" % JP_LINES[0])
    red(scan.scan_content(d), "no_ass_events")


def test_a_planted_srt_body_is_rejected(tmp_path):
    d = dist_with(tmp_path, "payload.bin", SRT_BODY)
    got = red(scan.scan_content(d), "no_srt_cues")
    assert "SRT cue timings" in got.saw, got.saw


def test_a_planted_webvtt_body_is_rejected(tmp_path):
    d = dist_with(tmp_path, "payload.bin", VTT_BODY)
    got = red(scan.scan_content(d), "no_webvtt")
    assert "WEBVTT" in got.saw, got.saw


def test_a_planted_japanese_document_is_rejected(tmp_path):
    u"""A subtitle body with its timestamps stripped is still a subtitle body."""
    d = dist_with(tmp_path, "payload.bin", JP_DOCUMENT)
    got = red(scan.scan_content(d), "no_cjk_document")
    assert "CJK characters" in got.saw, got.saw


def test_a_shift_jis_subtitle_is_rejected_too(tmp_path):
    u"""🚨 66% of real subtitles are not utf-8. The detectors key on the ASCII
    timestamps, which survive any decode -- which is why `errors='replace'` is
    safe HERE and nowhere near a write."""
    d = dist_with(tmp_path, "payload.bin", SRT_BODY.encode("cp932"))
    red(scan.scan_content(d), "no_srt_cues")


def test_a_utf16_subtitle_is_rejected_too(tmp_path):
    d = dist_with(tmp_path, "payload.bin",
                  b"\xff\xfe" + SRT_BODY.encode("utf-16-le"))
    red(scan.scan_content(d), "no_srt_cues")


@pytest.mark.parametrize("body, check", [
    (ASS_BODY, "no_ass_events"),
    (SRT_BODY, "no_srt_cues"),
    (VTT_BODY, "no_webvtt"),
])
def test_a_subtitle_inside_a_wheel_is_rejected(tmp_path, body, check):
    w = make_wheel(tmp_path / "dist" / ("w-%s.whl" % check),
                   members={"hato/data/sample.bin": body.encode("utf-8")})
    red(scan.scan_content(w.parent), check)


@pytest.mark.parametrize("ext", SUB_EXTS)
def test_a_subtitle_extension_is_rejected_even_when_the_file_is_empty(tmp_path, ext):
    u"""A SECOND, different question: an empty or encrypted subtitle file has no
    structure for any detector to read."""
    d = dist_with(tmp_path, "episode 01" + ext, b"")
    got = red(scan.scan_content(d), "no_subtitle_extension")
    assert ext in got.saw, got.saw


def test_the_subtitle_extension_list_is_the_one_archives_extracts():
    assert scan.SUBTITLE_EXTS == SUB_EXTS, \
        "the extension list changed: %s, expected %s" % (scan.SUBTITLE_EXTS, SUB_EXTS)
    from hato import archives
    assert set(scan.SUBTITLE_EXTS) == set(archives.SUBTITLE_EXTS), \
        "the scan and the extractor disagree about what a subtitle is: %s vs %s" % (
            sorted(scan.SUBTITLE_EXTS), sorted(archives.SUBTITLE_EXTS))


def test_an_api_response_fixture_is_metadata_and_passes(tmp_path):
    u"""spec/10-deployment.md §4.4: API-response fixtures are fine -- they are
    metadata. Subtitle bodies are not ours to redistribute."""
    body = json.dumps([{"id": i, "name": JP_LINES[i % 4],
                        "japanese_name": JP_LINES[(i + 1) % 4]} for i in range(40)],
                      ensure_ascii=False)
    d = dist_with(tmp_path, "entries_11446_files.json", body)
    got = scan.scan_content(d)
    all_held(got)
    assert "JSON" in by_name(got)["no_cjk_document"].saw, by_name(got)["no_cjk_document"].saw


def test_hato_s_own_package_source_is_clean(tmp_path):
    u"""⭐ THE POSITIVE CONTROL AGAINST THE REAL CORPUS. hato's own modules carry
    Japanese in their docstrings; if the detectors fired on them the whole scan
    would be noise."""
    all_held(scan.scan_content(ROOT / "hato"))


def test_the_cjk_floors_sit_above_the_worst_real_file_and_below_a_subtitle():
    u"""⭐ Measured 2026-09-17: the worst non-JSON file in the checkout is
    tests/test_tokens.py. Stated as an invariant, not as a pinned number, so it
    survives the file growing (doctrine/verification)."""
    worst = (ROOT / "tests" / "test_tokens.py").read_bytes().decode("utf-8")
    total, runs = scan.cjk_score(worst)
    assert total > 0 and runs > 0, "the control fixture has no Japanese in it at all"
    assert not (total >= scan.CJK_TOTAL_FLOOR and runs >= scan.CJK_RUNS_FLOOR), \
        "the floors have drifted under a real source file: %d chars, %d runs" % (total, runs)
    body_total, body_runs = scan.cjk_score(JP_DOCUMENT)
    assert body_total >= scan.CJK_TOTAL_FLOOR and body_runs >= scan.CJK_RUNS_FLOOR, \
        "the floors are above a real subtitle body: %d chars, %d runs" % (body_total, body_runs)


def test_no_claim_detail_quotes_the_content_it_found(tmp_path):
    u"""⛔ Those bytes are not ours to reproduce -- not even in a failure line."""
    d = dist_with(tmp_path, "payload.bin", ASS_BODY + SRT_BODY + JP_DOCUMENT)
    for c in scan.scan_content(d):
        for line in JP_LINES:
            assert line not in c.saw, "%s quoted the subtitle content" % c.name


def test_one_stray_timestamp_in_documentation_is_not_a_subtitle(tmp_path):
    u"""A single cue arrow appears in prose describing the format."""
    d = dist_with(tmp_path, "README.md",
                  u"An SRT cue looks like `00:00:01,000 --> 00:00:03,500`.\n")
    got = by_name(scan.scan_content(d))
    assert got["no_srt_cues"].state == claims.OK, got["no_srt_cues"].saw


# ===========================================================================
# verify-install -- the pure half
# ===========================================================================

def test_the_parent_walk_finds_a_config_above_the_directory(tmp_path):
    u"""🚨 'It checks the working directory only; the walk up the parent folders
    was done by hand, once.'"""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (tmp_path / "a" / "hato.config.json").write_bytes(b"{}")
    got = install.parent_config_offenders([deep])
    assert got, ("the walk reported nothing while a/hato.config.json sits two "
                 "levels above %s -- it checked the directory itself only" % deep)
    assert len(got) == 1 and got[0].endswith("a/hato.config.json"), \
        "expected exactly a/hato.config.json, got %s" % got


def test_the_parent_walk_finds_a_config_in_the_directory_itself(tmp_path):
    (tmp_path / "hato.config.json").write_bytes(b"{}")
    assert install.parent_config_offenders([tmp_path]), "the start directory was skipped"


def test_the_parent_walk_is_clean_in_a_bare_directory(tmp_path):
    d = tmp_path / "outside"
    d.mkdir()
    assert install.parent_config_offenders([d]) == [], "a clean chain reported an offender"


def test_the_parent_walk_covers_the_package_chain_not_just_the_working_directory(tmp_path):
    u"""⭐ FOR HATO THIS IS THE CHAIN THAT MATTERS. `paths.find_project_config()`
    defaults to PACKAGE_DIR and walks up from THERE, so a config above
    site-packages reopens P6 even with a spotless working directory."""
    work = tmp_path / "work"
    site = tmp_path / "venv" / "Lib" / "site-packages" / "hato"
    work.mkdir()
    site.mkdir(parents=True)
    (tmp_path / "venv" / "hato.config.json").write_bytes(b"{}")
    assert install.parent_config_offenders([work]) == [], "the work chain is clean"
    got = install.parent_config_offenders([work, site])
    assert len(got) == 1 and got[0].endswith("venv/hato.config.json"), got


def test_a_tsubasa_config_above_the_install_counts_too(tmp_path):
    u"""hato imports tsubasa, and P6 was tsubasa's own config."""
    (tmp_path / "tsubasa.config.json").write_bytes(b"{}")
    assert install.parent_config_offenders([tmp_path]), "tsubasa.config.json was ignored"


def test_the_parent_walk_can_be_driven_without_touching_the_disk():
    seen = []

    def exists(p):
        seen.append(Path(p).as_posix())
        return Path(p).as_posix().endswith("/a/hato.config.json")
    got = install.parent_config_offenders([Path("/a/b/c")], exists=exists)
    assert got == ["/a/hato.config.json"], got
    assert len(seen) >= 8, "the walk only looked at %d candidates" % len(seen)


@pytest.mark.parametrize("filename", ["unrar", "unrar.exe", "7z.exe", "bsdtar"])
def test_path_without_drops_the_directory_holding_the_tool(filename):
    tools = ("unrar", "unar", "7z", "7zz", "bsdtar")
    listing = {"C:/tools/" + filename}
    new, removed = install.path_without(
        tools, "C:/windows;C:/tools;C:/python", pathsep=";",
        lister=lambda p: Path(p).as_posix() in listing)
    assert new == "C:/windows;C:/python", new
    assert len(removed) == 1 and "C:/tools" in removed[0], removed


def test_path_without_keeps_a_path_with_nothing_in_it():
    new, removed = install.path_without(("unrar",), "C:/a;C:/b", pathsep=";",
                                        lister=lambda p: False)
    assert new == "C:/a;C:/b" and removed == [], (new, removed)


def test_the_rar_tool_list_is_parsed_from_archives_and_is_not_empty():
    u"""⭐ A scrub over an empty or stale tool list would leave a tool on PATH and
    make --no-unrar vacuous -- the exact shape of a check that cannot fail."""
    got = install.rar_tools()
    assert "unrar" in got, got
    assert len(got) >= 3, got


def test_a_reworded_archive_message_is_a_fault_not_an_empty_scrub(monkeypatch):
    from hato import archives
    monkeypatch.setattr(archives, "NO_RAR_TOOL", "install unrar and try again")
    with pytest.raises(claims.Fault) as err:
        install.rar_tools()
    assert "no longer says which tools" in str(err.value), str(err.value)


def good_results(version="0.1.0", probe=True):
    out = {
        "offenders": [],
        "chains": ["/tmp/x/outside", "/tmp/x/venv/lib/site-packages/hato"],
        "hato --version": {"rc": 0, "out": "hato %s\n" % version, "err": ""},
        "import hato": {"rc": 0, "out": "%s\n" % version, "err": ""},
        "hato --help": {"rc": 0, "out": "usage: hato <folder>\n\ncommands:\n", "err": ""},
    }
    if probe:
        out["degradation probe"] = {"rc": 0, "err": "", "out":
            "RAR TOOLS: none of 5 found\nZIP: extracted 1 member(s)\n"
            "RAR: refused by name -- ArchiveUnsupported: a .rar can only be unpacked\n"}
    return out


def test_the_assertion_set_holds_on_a_good_run():
    all_held(install.assess(good_results(), "0.1.0", no_unrar=True))


def test_a_config_above_the_install_fails_the_isolation_claim():
    r = good_results()
    r["offenders"] = ["/home/x/hato.config.json"]
    got = red(install.assess(r, "0.1.0", no_unrar=False), "venv_isolated")
    assert "P6" in got.saw and "hato.config.json" in got.saw, got.saw


def test_a_parent_walk_that_never_ran_fails_rather_than_passing():
    u"""doctrine/verification: a wait that cannot be false is not a wait. A
    missing measurement must not read as a clean one."""
    r = good_results()
    del r["offenders"]
    got = red(install.assess(r, "0.1.0", no_unrar=False), "venv_isolated")
    assert "never run" in got.saw, got.saw


@pytest.mark.parametrize("key, name", [
    ("hato --version", "cli_version"),
    ("import hato", "import_version"),
    ("hato --help", "cli_help"),
])
def test_a_step_that_exits_non_zero_fails_its_own_claim(key, name):
    r = good_results()
    r[key] = {"rc": 1, "out": "", "err": "ModuleNotFoundError: No module named 'tsubasa'"}
    got = red(install.assess(r, "0.1.0", no_unrar=False), name)
    assert "exited 1" in got.saw and "tsubasa" in got.saw, got.saw


def test_a_step_that_never_ran_fails_its_own_claim():
    r = good_results()
    del r["hato --version"]
    red(install.assess(r, "0.1.0", no_unrar=False), "cli_version")


def test_the_installed_version_must_equal_the_stamped_one():
    u"""spec/RUNBOOK.md §6: `hato --version` is a SEPARATE check."""
    got = red(install.assess(good_results("0.0.9"), "0.1.0", no_unrar=False), "cli_version")
    assert "hato 0.1.0" in got.saw, got.saw


def test_the_import_and_the_console_script_are_two_claims():
    u"""doctrine/verification: 48 checks imported the driver's functions while the
    COMMAND LINE printed a hardcoded wrong value. The wrapper was the thing that lied."""
    r = good_results()
    r["hato --version"] = {"rc": 0, "out": "hato 0.0.1\n", "err": ""}
    got = states(install.assess(r, "0.1.0", no_unrar=False))
    assert got["cli_version"] == claims.FAIL and got["import_version"] == claims.OK, got


def test_a_traceback_anywhere_fails_its_own_claim():
    r = good_results()
    r["hato --help"]["err"] = "Traceback (most recent call last):\n  File ...\n"
    got = red(install.assess(r, "0.1.0", no_unrar=False), "no_traceback")
    assert "hato --help" in got.saw, got.saw


def test_a_probe_that_still_finds_unrar_fails_rather_than_proving_degradation():
    u"""⭐ THE POSITIVE CONTROL. If the scrub did not take, every claim below it
    is vacuous -- doctrine/evidence: prove the state actually landed."""
    r = good_results()
    r["degradation probe"]["out"] = ("RAR TOOLS: STILL ON PATH: unrar\n"
                                     "ZIP: extracted 1 member(s)\n")
    got = red(install.assess(r, "0.1.0", no_unrar=True), "unrar_absent")
    assert "vacuous" in got.saw, got.saw


def test_a_probe_that_crashes_on_a_rar_fails_the_degradation_claim():
    r = good_results()
    r["degradation probe"]["out"] = ("RAR TOOLS: none of 5 found\n"
                                     "ZIP: extracted 1 member(s)\n"
                                     "RAR: CRASHED RarCannotExec: cannot find unrar\n")
    got = red(install.assess(r, "0.1.0", no_unrar=True), "degrades_not_errors")
    assert "rar_refused_by_name=False" in got.saw, got.saw


def test_a_probe_whose_zip_path_broke_fails_the_degradation_claim():
    r = good_results()
    r["degradation probe"]["out"] = ("RAR TOOLS: none of 5 found\n"
                                     "ZIP: FAILED ArchiveError: nope\n"
                                     "RAR: refused by name -- ArchiveUnsupported: x\n")
    got = red(install.assess(r, "0.1.0", no_unrar=True), "degrades_not_errors")
    assert "zip=False" in got.saw, got.saw


def test_a_missing_probe_fails_rather_than_being_skipped():
    r = good_results(probe=False)
    red(install.assess(r, "0.1.0", no_unrar=True), "unrar_absent")


def test_the_degradation_claims_are_absent_when_no_unrar_was_not_asked_for():
    got = states(install.assess(good_results(probe=False), "0.1.0", no_unrar=False))
    assert "unrar_absent" not in got and "degrades_not_errors" not in got, got


def test_the_degradation_probe_is_valid_python():
    u"""⚠ It is written to a file and run in another interpreter, so a syntax
    error in it would surface only during a real release."""
    source = install._PROBE % {"tools": ["unrar", "7z"]}
    compile(source, "degradation_probe.py", "exec")
    assert "archives.extract" in source, "the probe does not drive the real code path"
    assert "Rar!" in source, "the probe has no rar-magic fixture"


def test_the_probe_never_reads_a_real_subtitle():
    u"""⛔ spec/07-test-plan.md: no real media in TheForge."""
    source = install._PROBE % {"tools": ["unrar"]}
    assert "synthetic" in source, "the probe's fixture is not marked synthetic"
    assert ".mkv" not in source and "D:" not in source, "the probe points at real media"


# ===========================================================================
# the dispatcher
# ===========================================================================

def test_every_command_resolves_to_a_real_function():
    import importlib
    for name, module_name, func_name, why in dispatch.COMMANDS:
        module = importlib.import_module(module_name)
        assert callable(getattr(module, func_name, None)), \
            "%s -> %s.%s is not callable" % (name, module_name, func_name)
        assert why.strip(), "%s has no one-line description" % name


def test_the_runbook_block_invokes_exactly_these_commands():
    u"""⭐ The spec is the source of the command list, so a command the RUNBOOK
    calls and this package does not have is a red suite rather than a release
    that dies at step 1."""
    text = (ROOT / "spec" / "RUNBOOK.md").read_bytes().decode("utf-8")
    invoked = set(re.findall(r"python -m hato\.dev ([a-z\-]+)", text))
    assert invoked, "the RUNBOOK invokes no hato.dev command at all"
    known = set(name for name, _, _, _ in dispatch.COMMANDS)
    assert invoked <= known, "the RUNBOOK calls commands that do not exist: %s" % (
        sorted(invoked - known))


def test_an_unknown_command_exits_two(capsys):
    assert dispatch.main(["publish-everything"]) == claims.EXIT_FAULT
    err = capsys.readouterr().err
    assert "no such command" in err and err.count("\n") == 1, repr(err)


def test_no_arguments_prints_usage_and_exits_two(capsys):
    assert dispatch.main([]) == claims.EXIT_FAULT
    out = capsys.readouterr().out
    assert "usage: python -m hato.dev" in out, repr(out)
    for name, _, _, _ in dispatch.COMMANDS:
        assert name in out, "%s is not in the usage block" % name


def test_help_exits_zero(capsys):
    assert dispatch.main(["--help"]) == claims.EXIT_OK


def test_a_fault_is_one_line_and_never_a_traceback(capsys, monkeypatch):
    monkeypatch.setattr(stamp, "main",
                        lambda argv: (_ for _ in ()).throw(claims.Fault("no wheel\nhere")))
    assert dispatch.main(["stamp"]) == claims.EXIT_FAULT
    err = capsys.readouterr().err
    assert err.count("\n") == 1, "stderr had %d lines: %r" % (err.count("\n"), err)
    assert "Traceback" not in err and "hato.dev stamp: no wheel here" in err, repr(err)


def test_an_unexpected_exception_is_one_line_and_never_a_traceback(capsys, monkeypatch):
    u"""⛔ A traceback in a release block is unreadable in the channel that
    reports it (pitfall P25)."""
    monkeypatch.setattr(stamp, "main",
                        lambda argv: (_ for _ in ()).throw(ZeroDivisionError("x/0")))
    assert dispatch.main(["stamp"]) == claims.EXIT_FAULT
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "ZeroDivisionError: x/0" in err, repr(err)
    assert "Traceback" not in err, repr(err)


def test_check_and_release_together_are_refused(capsys):
    u"""--check is the read-only gate; --release declares a number."""
    assert dispatch.main(["stamp", "--check", "--release", "0.1.0"]) == claims.EXIT_FAULT
    assert "Pick one" in capsys.readouterr().err


def test_the_real_checkout_passes_the_gate_only_after_a_stamp(capsys):
    u"""⛔ READ-ONLY against this checkout: `--check` before anything is stamped
    must exit non-zero, which is exactly what stops a stale version shipping."""
    code = dispatch.main(["stamp", "--check"])
    out = capsys.readouterr()
    assert code in (claims.EXIT_OK, claims.EXIT_CLAIM_FAILED), code
    if code == claims.EXIT_CLAIM_FAILED:
        assert "stamp" in out.err, out.err


def _literals_that_are_not_docstrings(source):
    u"""Every string literal a module could USE as a path. ⚠ Docstrings are
    excluded deliberately -- citing `Workshop/patch-kit/patch-kit.md` in prose is
    the opposite of hardcoding it, and a check that cannot tell them apart would
    ban the citation."""
    import ast
    tree = ast.parse(source)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and body:
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]


def test_nothing_in_hato_dev_hardcodes_a_path_on_this_machine():
    u"""⛔ spec/RUNBOOK.md 0a: the keystore path and the vault's ffmpeg are facts
    about one laptop and must never reach shipping code."""
    patterns = (r"[A-Za-z]:[\\/]Users", r"InfiniteVoid", r"keystore[\\/]",
                r"media-kit", r"patch-kit[\\/]", r"Workshop[\\/]")
    bad = []
    seen = 0
    for path in sorted((ROOT / "hato" / "dev").glob("*.py")):
        for literal in _literals_that_are_not_docstrings(
                path.read_bytes().decode("utf-8")):
            seen += 1
            for pattern in patterns:
                if re.search(pattern, literal):
                    bad.append("%s: %r matches %s" % (path.name, literal[:60], pattern))
    assert seen > 50, "only %d string literals examined -- the check is vacuous" % seen
    assert not bad, "a build-machine path reached the tooling: %s" % bad


def test_hato_dev_is_not_imported_by_the_package_that_ships():
    u"""⚠ hato/__init__.py stays light on purpose; importing dev tooling from it
    would drag argparse, zipfile and tarfile into every run."""
    text = (ROOT / "hato" / "__init__.py").read_bytes().decode("utf-8")
    assert "dev" not in re.findall(r"^from hato import (\w+)", text, re.M), text
    assert "hato.dev" not in text, "hato/__init__.py imports the release tooling"
