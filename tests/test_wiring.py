# -*- coding: utf-8 -*-
"""
Step 0a -- prove the wiring end to end, one check per layer, each failure
pointing somewhere specific (dev-build §First move).

What this suite STRUCTURALLY cannot cover: whether the real key is VALID (only
`hato doctor` against the live API can say), and whether Task Scheduler's
environment resolves the same paths (RUNBOOK 5c, one real scheduled run).
"""
import json
import os
import pickle
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import conftest
from hato import credentials, paths

ROOT = Path(__file__).resolve().parents[1]


def run_hato(args, cwd, env_extra=None, drop=()):
    env = dict(os.environ)
    for k in drop:
        env.pop(k, None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "hato"] + list(args), cwd=str(cwd),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)


def out(proc):
    return (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


# -- the package --------------------------------------------------------------

def test_package_imports_and_carries_a_version():
    import hato
    assert re.match(r"^\d+\.\d+\.\d+([.-]?(dev|a|b|rc)\d*)?$", hato.__version__), (
        "hato.__version__ is %r -- not a version string" % hato.__version__)


def test_version_flag_matches_the_package():
    import hato
    proc = run_hato(["--version"], cwd=ROOT)
    assert proc.returncode == 0, out(proc)
    assert out(proc).strip() == "hato %s" % hato.__version__


# -- tsubasa resolves to the vault checkout and nowhere else -------------------

# 🚨 THESE TWO CHECKS ARE ABOUT A SOURCE CHECKOUT, AND THEY HAVE TO SAY SO.
#
# Their job: while hato is developed in the vault beside `Workshop/tsubasa`, a
# pip-installed `tsubasa-sync` must not silently shadow that source tree
# (RUNBOOK 0a). That is a statement about a DEVELOPMENT layout.
#
# ⛔ Written unconditionally they fail everywhere else -- in the public clone,
# and in CI, where tsubasa is installed from PyPI and there is no checkout at
# all. A repository whose first CI run is red teaches everyone to ignore CI,
# and pitfall P18 is precisely *"Sonic saw the first red run before the agent
# did."* Pitfall P10 is the same shape from the other side: a test that encoded
# Windows path semantics without saying so, and failed on Linux.
#
# ⚠ THE CONDITION IS NARROW ON PURPOSE: the checkout directory not existing.
# In the vault it exists, so the guard runs and still does its job. If this ever
# skips in the vault, that is itself the finding -- it means the checkout moved.
_CHECKOUT = paths.tsubasa_checkout()
_IN_A_CHECKOUT = _CHECKOUT is not None and _CHECKOUT.is_dir()
_needs_checkout = pytest.mark.skipif(
    not _IN_A_CHECKOUT,
    reason="no tsubasa source checkout beside this tree (%s) -- these two checks "
           "guard the vault's development layout, where a pip-installed "
           "tsubasa-sync must not shadow the source tree. An installed hato has "
           "no checkout to shadow." % (_CHECKOUT,))


@_needs_checkout
def test_tsubasa_resolves_to_the_vault_checkout():
    import tsubasa
    checkout = paths.tsubasa_checkout()
    assert checkout is not None, "hato.config.json names no tsubasa checkout"
    where = Path(tsubasa.__file__).resolve()
    assert str(where).startswith(str(checkout) + os.sep), (
        "`import tsubasa` resolved to %s, not the vault checkout %s -- a "
        "pip-installed tsubasa-sync is shadowing the source tree (RUNBOOK 0a)"
        % (where, checkout))


@_needs_checkout
def test_tsubasa_resolves_to_the_checkout_in_a_subprocess_too():
    """`python -m hato` is how every proof command and the launcher run it."""
    code = "import tsubasa, sys; sys.stdout.write(tsubasa.__file__)"
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(Path.home()),
                          env=dict(os.environ), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120)
    assert proc.returncode == 0, out(proc)
    where = Path(proc.stdout.decode("utf-8")).resolve()
    assert str(where).startswith(str(paths.tsubasa_checkout()) + os.sep), where


def test_tsubasa_is_importable_at_all_however_it_got_here():
    """⭐ WHAT SURVIVES THE SKIP ABOVE, and it is the half that matters to a user.

    The two checks above are about WHERE tsubasa comes from, and they only
    apply in a source checkout. This one asks the question an installed copy
    still has to answer -- is the engine present and the right vintage -- so
    skipping those two never leaves `import tsubasa` unproven.
    """
    import tsubasa
    assert tsubasa.__file__, "tsubasa has no module file"
    parts = tuple(int(n) for n in tsubasa.__version__.split(".")[:3])
    assert parts >= (0, 1, 5), (
        "tsubasa is %s; hato needs >= 0.1.5 for the English display-name reader "
        "its present-check relies on (spec/10-deployment.md)" % tsubasa.__version__)


def test_the_tsubasa_names_hato_pins_are_public():
    """The four frozen shapes (spec/10-deployment.md) -- by their PUBLIC names."""
    import tsubasa
    for name in ("scan", "sync", "Result", "Scan", "SyncReport", "self_check",
                 "parse_subtitle_name", "__version__"):
        assert name in tsubasa.__all__, "tsubasa.__all__ no longer exports %r" % name


# -- config resolves identically from any working directory ------------------

def test_config_show_is_identical_from_three_working_directories(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b" / "deeper" / "still"
    a.mkdir()
    b.mkdir(parents=True)
    seen = []
    for cwd in (ROOT, a, b):
        proc = run_hato(["config", "--show", "--json"], cwd=cwd)
        assert proc.returncode == 0, out(proc)
        seen.append(json.loads(proc.stdout.decode("utf-8")))
    assert seen[0] == seen[1] == seen[2], seen
    assert seen[0]["ok"] is True
    # and it is the REDIRECTED store, never the developer's real one
    assert seen[0]["data_root"] == os.environ["HATO_CACHE"]


def test_config_show_honours_HATO_CONFIG(tmp_path):
    cfg = tmp_path / "elsewhere.toml"
    cfg.write_text('lang = "jpn"\ncandidates = 5\n', encoding="utf-8")
    proc = run_hato(["config", "--show", "--json"], cwd=tmp_path,
                    env_extra={"HATO_CONFIG": str(cfg)})
    assert proc.returncode == 0, out(proc)
    shown = json.loads(proc.stdout.decode("utf-8"))
    assert shown["config"] == str(cfg)
    assert shown["config_source"] == "HATO_CONFIG"
    assert (shown["lang"], shown["candidates"]) == ("jpn", 5)


def test_a_relative_override_is_refused_not_resolved_against_the_cwd(monkeypatch):
    monkeypatch.setenv("HATO_CACHE", "relative/dir")
    with pytest.raises(paths.PathError) as err:
        paths.data_root()
    assert "absolute" in str(err.value)


# -- the key ------------------------------------------------------------------

FAKE_KEY = "hk_TEST_0123456789abcdefghWXYZ"


def _keyfile(tmp_path, body):
    p = tmp_path / "keystore" / "hato-jimaku.txt"
    p.parent.mkdir(parents=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_check_key_reads_the_last_line_and_prints_only_the_last_four(tmp_path):
    kf = _keyfile(tmp_path, "# jimaku key for hato\n# minted 2026-09-07\n%s\n" % FAKE_KEY)
    proc = run_hato(["config", "--check-key"], cwd=tmp_path,
                    env_extra={"HATO_KEYFILE": str(kf)}, drop=("HATO_JIMAKU_KEY",))
    text = out(proc)
    assert proc.returncode == 0, text
    assert "WXYZ" in text
    assert FAKE_KEY not in text
    assert FAKE_KEY[:-4] not in text, "more than the last four characters leaked"
    assert str(kf) in text, "it must say WHERE the key was read from"


def test_the_environment_key_wins_over_the_file(tmp_path):
    kf = _keyfile(tmp_path, "%s\n" % FAKE_KEY)
    proc = run_hato(["config", "--check-key", "--json"], cwd=tmp_path,
                    env_extra={"HATO_KEYFILE": str(kf),
                               "HATO_JIMAKU_KEY": "hk_ENV_zzzzzzzzzzzzQRST"})
    shown = json.loads(proc.stdout.decode("utf-8"))
    assert shown == {"found": True, "hint": u"…QRST", "source": "HATO_JIMAKU_KEY"}


def test_a_missing_key_says_MISSING_where_it_looked_and_exits_nonzero(tmp_path):
    nowhere = tmp_path / "nope.txt"
    proc = run_hato(["config", "--check-key"], cwd=tmp_path,
                    env_extra={"HATO_KEYFILE": str(nowhere)}, drop=("HATO_JIMAKU_KEY",))
    text = out(proc)
    assert proc.returncode == 1, text
    assert "MISSING" in text and str(nowhere) in text


def test_a_comment_on_the_last_line_is_not_taken_as_the_key(tmp_path, monkeypatch):
    kf = _keyfile(tmp_path, "%s\n# a trailing note\n" % FAKE_KEY)
    monkeypatch.delenv("HATO_JIMAKU_KEY", raising=False)
    monkeypatch.setenv("HATO_KEYFILE", str(kf))
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.resolve_key()
    assert "comment" in str(err.value)
    assert FAKE_KEY not in str(err.value)


def test_the_key_object_cannot_print_its_value():
    key = credentials.Key(FAKE_KEY, "test")
    for shown in (repr(key), str(key), "%s" % key, "{}".format(key), f"{key}", f"{key!r}"):
        assert FAKE_KEY not in shown and FAKE_KEY[:-4] not in shown, shown
        assert "WXYZ" in shown
    with pytest.raises(TypeError):
        pickle.dumps(key)
    assert key.reveal() == FAKE_KEY


# -- where hato keeps its things (RUNBOOK 1c) --------------------------------

def test_off_windows_the_root_is_local_share_and_never_dot_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root = paths.default_data_root()
    assert root == tmp_path / ".local" / "share" / "hato", root
    assert ".cache" not in root.parts, (
        "hato's non-Windows root is %s. The root holds subs/ -- the kept originals hato "
        "must never delete -- and ~/.cache is the one directory a user or a cleanup tool "
        "may wipe without being asked (RUNBOOK 1c)" % root)


def test_everything_hato_keeps_hangs_off_the_one_root_and_asking_creates_nothing(
        tmp_path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("HATO_CACHE", str(root))
    assert paths.data_root() == root
    for where in (paths.cache_dir(), paths.state_db_path(), paths.key_file_path(),
                  paths.default_subs_dir(), paths.default_log_path(), paths.lock_path()):
        assert where.parent == root, (
            "%s does not sit in hato's one root %s -- HATO_CACHE relocates the WHOLE "
            "root, so anything outside it escapes a test run's redirection" % (where, root))
    assert paths.key_file_path().name == "key.txt"
    assert not root.exists(), "asking where hato's things live created %s" % root


def test_a_folder_left_by_the_old_non_windows_default_is_noticed_and_never_moved(
        tmp_path, monkeypatch):
    """⛔ Nothing is migrated automatically (spec/05-interface.md)."""
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HATO_CACHE", raising=False)
    old = tmp_path / ".cache" / "hato"
    (old / "subs").mkdir(parents=True)
    kept = old / "subs" / "Show - 01.ja.ass"
    kept.write_text(u"a kept original", encoding="utf-8")

    assert paths.legacy_data_root() == old

    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    assert paths.legacy_data_root() is None, "a relocated root makes the old default noise"
    monkeypatch.delenv("HATO_CACHE")
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    assert paths.legacy_data_root() is None, "Windows never moved -- there is nothing to say"

    assert kept.read_text(encoding="utf-8") == u"a kept original", "the old folder was touched"


def test_the_key_precedence_is_env_then_keyfile_then_key_txt_then_the_keystore(
        tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    root_key = "hk_ROOT_00000000000000ROOT"
    (root / "key.txt").write_text(u"# a stranger's key\n%s\n" % root_key, encoding="utf-8")
    monkeypatch.setenv("HATO_CACHE", str(root))
    monkeypatch.delenv("HATO_JIMAKU_KEY", raising=False)
    monkeypatch.delenv("HATO_KEYFILE", raising=False)

    key = credentials.resolve_key()
    assert key.reveal() == root_key, "key.txt in hato's own root was not read"
    assert str(root / "key.txt") in key.source, key.source

    elsewhere = _keyfile(tmp_path, "%s\n" % FAKE_KEY)
    monkeypatch.setenv("HATO_KEYFILE", str(elsewhere))
    assert credentials.resolve_key().reveal() == FAKE_KEY, "HATO_KEYFILE lost to key.txt"

    monkeypatch.setenv("HATO_JIMAKU_KEY", "hk_ENV_zzzzzzzzzzzzQRST")
    assert credentials.resolve_key().source == "HATO_JIMAKU_KEY", "the environment lost to a file"


def test_a_set_but_missing_HATO_KEYFILE_never_falls_through_to_another_key(
        tmp_path, monkeypatch):
    """⛔ The one thing keeping a test run out of the developer's real keystore."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "key.txt").write_text(FAKE_KEY + "\n", encoding="utf-8")
    absent = tmp_path / "absent.txt"
    monkeypatch.setenv("HATO_CACHE", str(root))
    monkeypatch.setenv("HATO_KEYFILE", str(absent))
    monkeypatch.delenv("HATO_JIMAKU_KEY", raising=False)
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.resolve_key()
    assert str(absent) in str(err.value), (
        "HATO_KEYFILE named a file that is not there and hato read a DIFFERENT key instead "
        "-- the harness points it at a missing file precisely so no test can reach the real "
        "keystore (spec/07-test-plan.md)")
    assert FAKE_KEY not in str(err.value)


def test_key_set_from_writes_key_txt_alone_and_shows_only_the_last_four(tmp_path):
    root = tmp_path / "root"
    source = tmp_path / "pasted.txt"
    source.write_text(u"# pasted from jimaku.cc\n# minted today\n%s\n" % FAKE_KEY,
                      encoding="utf-8")
    env = {"HATO_CACHE": str(root), "HATO_CONFIG": str(tmp_path / "config.toml")}
    dropped = ("HATO_JIMAKU_KEY", "HATO_KEYFILE")

    proc = run_hato(["key", "--set-from", str(source)], cwd=tmp_path, env_extra=env, drop=dropped)
    text = out(proc)
    assert proc.returncode == 0, text
    assert "WXYZ" in text
    assert FAKE_KEY not in text and FAKE_KEY[:-4] not in text, "the key was printed"

    written = root / "key.txt"
    body = written.read_text(encoding="utf-8")
    assert body.splitlines()[-1] == FAKE_KEY, body
    assert body.startswith("#"), "the file must explain itself to whoever opens it next"

    # ⛔ and NOWHERE else hato writes -- config.toml and (when it lands) hato.log included.
    leaked = [p for p in root.rglob("*")
              if p.is_file() and p != written
              and FAKE_KEY in p.read_text(encoding="utf-8", errors="replace")]
    assert leaked == [], "the key is also in %s" % ", ".join(str(p) for p in leaked)

    said = out(run_hato(["key", "--show"], cwd=tmp_path, env_extra=env, drop=dropped))
    assert "WXYZ" in said and str(root / "key.txt") in said, said
    assert FAKE_KEY not in said and FAKE_KEY[:-4] not in said, (
        "`hato key --show` printed more than the last four characters")

    shown = json.loads(run_hato(["key", "--show", "--json"], cwd=tmp_path, env_extra=env,
                                drop=dropped).stdout.decode("utf-8"))
    assert shown["found"] is True and shown["hint"] == u"…WXYZ"
    assert "key.txt" in shown["source"] and FAKE_KEY not in json.dumps(shown)

    config_out = out(run_hato(["config", "--show", "--json"], cwd=tmp_path, env_extra=env,
                              drop=dropped))
    assert FAKE_KEY not in config_out, "the key reached config output"


def test_the_key_file_is_owner_only_where_the_os_has_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    source = tmp_path / "pasted.txt"
    source.write_text(FAKE_KEY + "\n", encoding="utf-8")
    key, written = credentials.save_key_from(source)
    assert key.reveal() == FAKE_KEY and written == tmp_path / "root" / "key.txt"
    applied = credentials._owner_only(written)
    if os.name == "nt":
        assert applied is False, (
            "chmod on Windows sets the READ-ONLY flag, not an ACL -- it would read as "
            "protection while being none. %LOCALAPPDATA% is the per-user boundary there")
    else:
        assert applied is True
        assert stat.S_IMODE(written.stat().st_mode) == 0o600


def test_the_key_is_refused_into_a_git_working_tree_and_nothing_is_written(tmp_path):
    """🚨 LEDGER-HOT.md's first rule, made structural: the vault auto-commits."""
    repo = tmp_path / "vault"
    (repo / ".git").mkdir(parents=True)
    source = tmp_path / "pasted.txt"
    source.write_text(FAKE_KEY + "\n", encoding="utf-8")
    destination = repo / "data" / "key.txt"
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.save_key_from(source, destination)
    assert "git" in str(err.value) and str(repo) in str(err.value)
    assert FAKE_KEY not in str(err.value), "the refusal echoed the key back"
    assert not destination.exists() and not destination.parent.exists()


def test_a_key_file_with_nothing_usable_is_refused_without_echoing_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "root"))
    empty = tmp_path / "empty.txt"
    empty.write_text(u"\n  \n", encoding="utf-8")
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.save_key_from(empty)
    assert "empty" in str(err.value) and str(empty) in str(err.value)
    assert not (tmp_path / "root" / "key.txt").exists()

    commented = tmp_path / "commented.txt"
    commented.write_text(u"%s\n# a trailing note\n" % FAKE_KEY, encoding="utf-8")
    with pytest.raises(credentials.KeyMissing) as err:
        credentials.save_key_from(commented)
    assert "comment" in str(err.value) and FAKE_KEY not in str(err.value)
    assert not (tmp_path / "root" / "key.txt").exists(), (
        "a refused key file still created one -- a half-written key.txt would be read as "
        "the key on the next run")


# -- the harness itself: isolation and the network guard ----------------------

def test_the_per_user_store_is_redirected_away_from_the_real_one():
    real = paths.default_data_root()
    assert paths.data_root() != real
    assert str(paths.data_root()).startswith(os.environ["HATO_TEST_ROOT"])
    assert os.environ["HATO_CONFIG"].startswith(os.environ["HATO_TEST_ROOT"])
    assert os.environ["TSUBASA_CACHE"].startswith(os.environ["HATO_TEST_ROOT"]), (
        "the contract test runs the REAL tsubasa.sync(); its results DB and trash "
        "would land in the developer's real %LOCALAPPDATA%\\tsubasa")
    assert "HATO_JIMAKU_KEY" not in os.environ
    assert os.environ["HATO_KEYFILE"].startswith(os.environ["HATO_TEST_ROOT"])


def test_the_network_guard_is_armed():
    assert os.environ.get("HATO_NO_NETWORK") == "1"
    # Every target is chosen so that even an UNGUARDED attempt -- a mutant, or a
    # guard that broke -- reaches nobody: 192.0.2.1 is TEST-NET-1 (RFC 5737) and
    # `.invalid` is a reserved TLD (RFC 6761). Never jimaku: an unguarded request
    # there spends someone else's metered quota.
    with pytest.raises(conftest.NetworkForbidden):
        socket.create_connection(("192.0.2.1", 9), timeout=1)
    with pytest.raises(conftest.NetworkForbidden):
        socket.getaddrinfo("hato-guard-check.invalid", 443)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(conftest.NetworkForbidden):
            s.connect(("192.0.2.1", 9))
    finally:
        s.close()


def test_the_network_guard_is_not_an_OSError():
    """A retry ladder catching 'unreachable' must not swallow it and sleep."""
    assert not issubclass(conftest.NetworkForbidden, OSError)


def test_requests_is_refused_before_anything_leaves_the_machine():
    import requests
    with pytest.raises(conftest.NetworkForbidden):
        requests.get("https://hato-guard-check.invalid/api/entries/search?query=x", timeout=2)


def test_loopback_is_still_allowed():
    """A local fake server is how the client's real HTTP stack gets exercised."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        c = socket.create_connection(srv.getsockname(), timeout=2)
        c.close()
    finally:
        srv.close()


# -- the product's own import chain, WITHOUT the harness helping --------------

def test_the_entry_point_imports_tsubasa_without_the_harness():
    """🚨 MEASURED 2026-09-17: 693 checks were green while `python -m hato sync`
    died on `ModuleNotFoundError: No module named 'tsubasa'`.

    `conftest` puts the vault checkout on `sys.path` for the suite, so every
    other check here proves hato can import tsubasa *when the harness helps it*.
    A person typing `hato` gets no such help, and nothing noticed. This runs the
    shipped entry point the way they do -- a subprocess with `PYTHONPATH`
    dropped -- through a command whose module imports the port, and so tsubasa.

    ⚠ If this fails, tsubasa is not reachable from a plain interpreter:
    `pip install tsubasa-sync`, or in this vault the dev `.pth`
    (`10-deployment.md` §*Development imports the vault checkout*). That is a
    real answer about the product, not a harness fault -- the tool cannot run.
    """
    proc = run_hato(["sync", "--help"], cwd=ROOT, drop=("PYTHONPATH",))
    text = out(proc)
    assert "ModuleNotFoundError" not in text, text
    assert proc.returncode == 0, text
    assert "video" in text and "subtitle" in text, text


# -- the PUBLISHED library API, on the package ---------------------------------

def test_the_library_api_is_reachable_from_the_package_and_stays_lazy():
    """⭐ `spec/05-interface.md` §*The library API* publishes four names on the
    PACKAGE: `from hato import scan, identify, fetch, Result`.

    🚨 Until 2026-09-17 none of them existed -- `hato.__all__` was
    `['__version__']` -- while the spec, the README and the PyPI page all say
    they do. A published name is a permanent compatibility promise from the
    TAG, so this check exists to make the promise checkable before it is made.

    ⚠ AND IT GUARDS BOTH HALVES AT ONCE. This file's own module docstring
    requires that importing `hato` must NOT import the pipeline: a parallel
    builder's deliberate mutant would otherwise redden every other suite. An
    eager `from hato.api import *` in `__init__.py` satisfies the spec and
    breaks that. The wiring is PEP 562 lazy, and the first assertion below is
    what stops someone "simplifying" it back.

    ⛔ Runs in a SUBPROCESS: `sys.modules` in this process is already polluted
    by every other check in the suite, so an in-process assertion about what
    `import hato` loads is meaningless.
    """
    code = (
        "import sys, hato;"
        "assert 'hato.pipeline' not in sys.modules, 'importing hato imported the pipeline';"
        "from hato import scan, identify, fetch, Result;"
        "assert callable(scan) and callable(identify) and callable(fetch),"
        " 'a published name is not callable';"
        "assert isinstance(Result, type), 'Result is not a class';"
        "expected = {'scan', 'identify', 'fetch', 'Result'};"
        "missing = expected - set(hato.__all__);"
        "assert not missing, 'missing from hato.__all__: %s' % sorted(missing);"
        "assert not hasattr(hato, 'does_not_exist'), 'an unknown name did not raise';"
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                          env=dict(os.environ), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120)
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    assert proc.returncode == 0, text
