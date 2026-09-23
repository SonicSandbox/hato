# -*- coding: utf-8 -*-
"""
The runner's own guarantees, driven against SYNTHETIC projects -- the one piece
that cannot be checked by the thing it checks.

Each check copies run_tests.py into a throwaway project with its own
hato.config.json and tests/, runs it as a subprocess, and asserts on the exit
code AND the message. Both directions where there is a direction: a clean
project is green, the broken one is not (doctrine/robustness: a refusal-only
test passes against a runner that refuses everything).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

GOOD = "def test_one():\n    assert 1 + 1 == 2\n"
EMPTY = "# collects nothing\nX = 1\n"
BAD = "def test_red():\n    assert 'expected' == 'actual', 'NAMED FAILURE MESSAGE'\n"


def project(tmp_path, suites, files, excused=None):
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    shutil.copy(str(ROOT / "run_tests.py"), str(proj / "run_tests.py"))
    cfg = {"project": "synthetic",
           "test": {"harnessDir": "tests", "harnessPattern": "^test_.*\\.py$",
                    "runLogDir": "_runs", "excused": excused or {}, "suites": suites}}
    (proj / "hato.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    for name, body in files.items():
        (proj / "tests" / name).write_text(body, encoding="utf-8")
    return proj


def suite(name, fname, **extra):
    s = {"name": name, "cmd": ["-m", "pytest", "tests/%s" % fname, "-q"]}
    s.update(extra)
    return s


#: Everything the PARENT test process already carries. A check that the runner
#: sets these must not pass on the values it inherited (doctrine/verification:
#: a check that passes on state it did not create is not a check).
INHERITED = ("HATO_NO_NETWORK", "HATO_CACHE", "HATO_CONFIG", "TSUBASA_CACHE",
             "HATO_KEYFILE", "HATO_TEST_ROOT", "HATO_JIMAKU_KEY", "HATO_LIVE")


def run(proj, *args, env_extra=None, clean=False):
    env = dict(os.environ)
    if clean:
        for var in INHERITED:
            env.pop(var, None)
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, "run_tests.py"] + list(args), cwd=str(proj),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=300)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


def test_a_clean_project_is_green(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")], {"test_a.py": GOOD})
    rc, text = run(proj)
    assert rc == 0, text
    assert "GREEN" in text and "1 checks" in text


def test_an_orphaned_harness_fails_the_run_and_is_named(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")],
                   {"test_a.py": GOOD, "test_forgotten.py": GOOD})
    rc, text = run(proj)
    assert rc == 4, text
    assert "ORPHANED HARNESS" in text and "test_forgotten.py" in text
    assert "GREEN" not in text


def test_an_excuse_needs_a_written_reason(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")],
                   {"test_a.py": GOOD, "test_scratch.py": GOOD},
                   excused={"test_scratch.py": ""})
    rc, text = run(proj)
    assert rc == 3, text
    assert "no written reason" in text


def test_an_excused_harness_with_a_reason_is_not_an_orphan(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")],
                   {"test_a.py": GOOD, "test_scratch.py": GOOD},
                   excused={"test_scratch.py": "a finalization gate, run by hand"})
    rc, text = run(proj, "--verify-registration")
    assert rc == 0, text


def test_a_suite_reporting_zero_checks_is_a_tooling_fault_not_a_pass(tmp_path):
    proj = project(tmp_path, [suite("empty", "test_empty.py")], {"test_empty.py": EMPTY})
    rc, text = run(proj)
    assert rc == 3, text
    assert "TOOLING" in text
    assert "GREEN" not in text


def test_a_suite_naming_a_missing_harness_is_a_tooling_fault(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py"), suite("ghost", "test_ghost.py")],
                   {"test_a.py": GOOD})
    rc, text = run(proj)
    assert rc == 3, text
    # the runner's OWN refusal, before anything runs -- not pytest's "file not found"
    assert "a suite names a harness that does not exist" in text, text
    assert "test_ghost.py" in text
    assert not (proj / "_runs").exists(), "a suite ran before the refusal"


def test_a_failing_suite_exits_1_and_its_full_output_is_on_disk(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py"), suite("red", "test_red.py")],
                   {"test_a.py": GOOD, "test_red.py": BAD})
    rc, text = run(proj)
    assert rc == 1, text
    logs = list((proj / "_runs").glob("*/red.txt"))
    assert len(logs) == 1, "the failing suite's output was not written to disk"
    assert "NAMED FAILURE MESSAGE" in logs[0].read_text(encoding="utf-8")


def test_verify_registration_runs_no_suite(tmp_path):
    proj = project(tmp_path, [suite("red", "test_red.py")], {"test_red.py": BAD})
    rc, text = run(proj, "--verify-registration")
    assert rc == 0, text
    assert not (proj / "_runs").exists() or not list((proj / "_runs").glob("*/red.txt"))


def test_a_py_file_that_does_not_parse_is_a_tooling_fault_even_if_nothing_imports_it(
        tmp_path):
    """⭐ HANDOFF §5 -- the gate for the heredoc trap. The broken line is the one a
    shell heredoc made twice in this project: a Windows path whose `\\x` became
    an escape Python refuses. It sits in `packaging/`, which no suite imports --
    so only this gate could see it. ⚠ And a build output is not our source."""
    proj = project(tmp_path, [suite("green", "test_green.py")], {"test_green.py": GOOD})
    rc, text = run(proj, "--verify-registration")
    assert rc == 0 and "every .py parses" in text, "the control is not clean:\n" + text
    (proj / "dist").mkdir()
    (proj / "dist" / "frozen.py").write_text('p = "C:\\hato\\cache\\x0"\n', encoding="utf-8")
    rc, text = run(proj, "--verify-registration")
    assert rc == 0, "a file under dist/ is a build output, not source:\n" + text
    (proj / "packaging").mkdir()
    (proj / "packaging" / "shipped.py").write_text('p = "C:\\hato\\cache\\x0"\n',
                                                   encoding="utf-8")
    rc, text = run(proj, "--verify-registration")
    assert rc == 3, "a .py that does not parse passed the self-check:\n" + text
    assert "packaging" in text and "shipped.py" in text and "line 1" in text, (
        "the fault does not name the file and the line:\n" + text)


def test_an_opt_in_suite_is_registered_but_not_run_by_default(tmp_path):
    proj = project(tmp_path,
                   [suite("a", "test_a.py"),
                    suite("live", "test_live.py", default=False, live=True,
                          why="hits the real server")],
                   {"test_a.py": GOOD, "test_live.py": BAD})
    rc, text = run(proj)
    assert rc == 0, text                        # the red live suite did not run
    assert "opt-in, not run by default: live" in text
    rc2, text2 = run(proj, "live")
    assert rc2 == 1, text2                      # ...and runs when named


def test_opting_out_of_the_default_run_needs_a_reason(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py", default=False)], {"test_a.py": GOOD})
    rc, text = run(proj)
    assert rc == 3, text


def test_an_unknown_suite_name_is_a_tooling_fault(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")], {"test_a.py": GOOD})
    rc, text = run(proj, "nosuch")
    assert rc == 3, text
    assert "no such suite" in text


def test_suites_run_with_the_store_redirected_and_the_network_switched_off(tmp_path):
    probe = (
        "import os\n"
        "def test_env():\n"
        "    root = os.environ['HATO_TEST_ROOT']\n"
        "    for var in ('HATO_CACHE', 'HATO_CONFIG', 'TSUBASA_CACHE', 'HATO_KEYFILE'):\n"
        "        assert os.environ[var].startswith(root), var\n"
        "    assert 'HATO_JIMAKU_KEY' not in os.environ\n"
        "    assert os.environ['HATO_NO_NETWORK'] == '1'\n"
        "    assert os.environ['PYTHONUTF8'] == '1'\n")
    proj = project(tmp_path, [suite("env", "test_env.py")], {"test_env.py": probe})
    rc, text = run(proj, env_extra={"HATO_JIMAKU_KEY": "hk_should_be_removed"}, clean=True)
    assert rc == 0, text


def test_a_test_that_writes_the_REAL_per_user_store_is_an_isolation_fault(tmp_path):
    """🚨 THE LEAK MUST LAND WHERE THIS PLATFORM ACTUALLY KEEPS THE STORE.

    ⛔ This wrote only to `%LOCALAPPDATA%\\hato\\cache`, and it was green on
    Windows and failed on BOTH macOS and ubuntu on every Python -- 8 of the 12
    matrix jobs in the public repo's second CI run. `LOCALAPPDATA` is a Windows
    concept; `hato/paths.py` uses `~/.local/share/hato` everywhere else, so the
    synthetic leak wrote somewhere the runner was never guarding, no isolation
    fault fired, and the check failed for the opposite of the reason it names.

    ⚠ Pitfall P10/P11 again: a test encoding one platform's semantics without
    saying so. The mirror below is tied to `paths.py` by the assertion under it,
    so the two cannot drift apart silently.
    """
    fake_localappdata = tmp_path / "LocalAppData"
    (fake_localappdata / "hato").mkdir(parents=True)

    leak = (
        "import os\n"
        "from pathlib import Path\n"
        "def test_leaks():\n"
        "    if os.name == 'nt':\n"
        "        real = Path(os.environ['LOCALAPPDATA']) / 'hato' / 'cache'\n"
        "    else:\n"
        "        real = Path.home() / '.local' / 'share' / 'hato' / 'cache'\n"
        "    real.mkdir(parents=True, exist_ok=True)\n"
        "    (real / 'x.part').touch()\n")

    proj = project(tmp_path, [suite("leak", "test_leak.py")], {"test_leak.py": leak})
    env = {"LOCALAPPDATA": str(fake_localappdata), "HOME": str(tmp_path),
           "USERPROFILE": str(tmp_path)}
    rc, text = run(proj, env_extra=env)
    assert rc == 5, text
    assert "ISOLATION FAULT" in text


def test_the_leak_scripts_idea_of_the_real_store_matches_hatos_own(monkeypatch, tmp_path):
    """⭐ The tie that stops the check above drifting from `hato/paths.py`.

    The leak script hard-codes the per-user layout for both platforms because it
    runs as a generated file in a synthetic project. ⛔ If `paths.py` ever moves
    the store, this goes red and names the disagreement -- rather than the leak
    quietly writing to a folder nothing guards, which is exactly how the POSIX
    version of that check passed for an entire CI run while proving nothing.
    """
    from hato import paths

    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
        expected = tmp_path / "LocalAppData" / "hato"
    else:
        monkeypatch.setenv("HOME", str(tmp_path))
        expected = tmp_path / ".local" / "share" / "hato"

    monkeypatch.delenv("HATO_CACHE", raising=False)

    # ⛔ NO SKIP HERE, DELIBERATELY. The first draft of this check called a
    # `paths.user_root()` that does not exist and fell back to `pytest.skip` --
    # which would have made it green and useless, the precise failure it was
    # written to prevent. `default_data_root()` is the real name, and it is the
    # platform DEFAULT, which is what the leak script mirrors.
    got = Path(paths.default_data_root())
    assert got == expected, (
        "the leak script in the check above writes under %s, and "
        "hato.paths.default_data_root() says the real per-user root is %s -- "
        "they have drifted, so that check is guarding the wrong folder"
        % (expected, got))


def test_a_run_that_leaves_the_real_store_alone_is_not_an_isolation_fault(tmp_path):
    """The positive control for the check above."""
    fake_localappdata = tmp_path / "LocalAppData"
    (fake_localappdata / "hato" / "cache").mkdir(parents=True)
    proj = project(tmp_path, [suite("a", "test_a.py")], {"test_a.py": GOOD})
    rc, text = run(proj, env_extra={"LOCALAPPDATA": str(fake_localappdata)})
    assert rc == 0, text


def test_a_lock_left_by_a_dead_run_is_taken_over_and_a_live_one_refuses(tmp_path):
    proj = project(tmp_path, [suite("a", "test_a.py")], {"test_a.py": GOOD})
    (proj / "_runs").mkdir()
    lock = proj / "_runs" / ".run.lock"
    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          stdout=subprocess.PIPE, timeout=60)
    lock.write_text('{"pid": %s, "started": "earlier"}' % dead.stdout.decode().strip(),
                    encoding="utf-8")
    rc, text = run(proj)
    assert rc == 0, text
    assert "took over a lock" in text
    # ...and a lock held by a LIVE process (this test's own pid) is a refusal
    lock.write_text('{"pid": %d, "started": "now"}' % os.getpid(), encoding="utf-8")
    rc2, text2 = run(proj)
    assert rc2 == 3, text2
    assert "already in flight" in text2
    lock.unlink()
