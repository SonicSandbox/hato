# -*- coding: utf-8 -*-
"""
The window's subprocess driver -- RUNBOOK 7c, spec/05-interface.md §The window.

⛔ NOTHING HERE IMPORTS QT, and that is the point. The subprocess, the
decoding, the parse and the counts are where the failures live; a check that
needs a display is a check that gets skipped on every CI runner hato has.
The painting is LOOKED at instead, and its defects are recorded as such.

Structurally cannot cover: what the window actually renders. A row can carry
the right three values and still be unreadable -- `gui-mock/` and the
screenshot loop are where that is settled.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from hato.gui import run as gui_run


def fake_cli(*lines, **kwargs):
    u"""-> a HATO_CLI value that prints `lines` and exits `code`.

    ⭐ A REAL CHILD PROCESS, not a stubbed Popen. The pipes, the threads, the
    decoding and the exit code are exactly the things this module exists to
    get right, and a fake process object proves none of them.
    """
    code = kwargs.pop("code", 0)
    stderr = kwargs.pop("stderr", [])
    script = (
        "import sys\n"
        "for line in %r: sys.stdout.write(line + chr(10)); sys.stdout.flush()\n"
        "for line in %r: sys.stderr.write(line + chr(10))\n"
        "sys.exit(%d)\n" % (list(lines), list(stderr), code))
    return json.dumps([sys.executable, "-c", script])


def video(**over):
    obj = {"type": "video", "video": "D:\\Anime\\x.mkv", "name": "x.mkv",
           "outcome": "CONFIDENT", "skip": None, "output_path": "D:\\Anime\\x.ja.ass",
           "episode": 1, "tsubasa": {"match_rate": 0.82}, "attempts": []}
    obj.update(over)
    return obj


# ---------------------------------------------------------------------------
# what gets run
# ---------------------------------------------------------------------------

def test_from_source_it_runs_the_module(monkeypatch):
    monkeypatch.delenv("HATO_CLI", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert gui_run.cli_argv() == [sys.executable, "-m", "hato"]


def test_frozen_it_runs_the_console_exe_beside_the_bundle(monkeypatch):
    u"""⛔ `-m` on a frozen bundle re-enters the GUI and opens a SECOND window
    rather than running the CLI."""
    monkeypatch.delenv("HATO_CLI", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join("C:\\app", "hato.exe"))
    argv = gui_run.cli_argv()
    assert len(argv) == 1
    assert "-m" not in argv
    # 🚨 AND IT MUST NOT BE THE WINDOW. Sonic ruled 2026-09-18 that `hato.exe`
    # is the window a person clicks, so the CLI is `hato-cli.exe`. ⛔ A
    # `startswith("hato")` assertion here was true of BOTH names and would
    # have watched the window spawn itself for ever.
    assert os.path.basename(argv[0]) in ("hato-cli.exe", "hato-cli")
    assert os.path.basename(argv[0]) != os.path.basename(sys.executable)


def test_a_folder_override_beginning_with_a_bracket_is_not_read_as_json(monkeypatch):
    u"""🚨 Half this corpus's release groups are `[Erai-raws]`, `[SubsPlease]`.
    *"Starts with a bracket, therefore JSON"* turns an ordinary directory into
    a JSONDecodeError raised out of `Runner.__init__`."""
    monkeypatch.setenv("HATO_CLI", "[Erai-raws] hato.exe")
    assert gui_run.cli_argv() == ["[Erai-raws] hato.exe"]


def test_a_json_list_override_is_used_as_the_command(monkeypatch):
    monkeypatch.setenv("HATO_CLI", json.dumps(["py", "-3", "-m", "hato"]))
    assert gui_run.cli_argv() == ["py", "-3", "-m", "hato"]


def test_the_run_always_asks_for_json_and_progress(monkeypatch):
    monkeypatch.delenv("HATO_CLI", raising=False)
    argv = gui_run.argv_for(["D:\\Anime"])
    assert "--json" in argv and "--progress" in argv


def test_every_folder_is_made_absolute(monkeypatch):
    u"""⚠ A GUI's working directory is wherever the shortcut pointed -- on
    Windows routinely System32."""
    monkeypatch.delenv("HATO_CLI", raising=False)
    argv = gui_run.argv_for(["Anime"])
    assert argv[-1] == os.path.abspath("Anime")
    assert os.path.isabs(argv[-1])


def test_a_run_with_no_folder_is_refused_in_words_a_person_can_act_on():
    with pytest.raises(ValueError) as exc:
        gui_run.argv_for([])
    assert "Settings" in str(exc.value) or "folder" in str(exc.value)


def test_a_manual_pick_names_exactly_that_pair(monkeypatch):
    monkeypatch.delenv("HATO_CLI", raising=False)
    argv = gui_run.argv_for_pair("D:\\A\\x.mkv", "D:\\A\\sub.ass")
    assert argv[-4:-1] == ["sync", os.path.abspath("D:\\A\\x.mkv"),
                           os.path.abspath("D:\\A\\sub.ass")]


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="a Windows console")
def test_the_child_gets_no_console_of_its_own():
    u"""🚨 A GUI parent has no console, so each child allocates one and it
    flashes over the app and steals focus."""
    kwargs = gui_run.no_console_kwargs()
    assert kwargs["creationflags"] & 0x08000000
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW


@pytest.mark.parametrize("platform,kept", [
    (u"offscreen", False),
    (u"minimal", False),
    (u"vnc", False),
    (u"windows", True),
    (u"wayland", True),
])
def test_a_headless_qt_platform_is_never_passed_to_a_child(platform, kept):
    u"""🚨 THE BUG SONIC HIT TWICE, 2026-09-18: *"it's in the tray but can't see
    the UI. both the tray click and hato shortcut doesn't work."*

    ⭐ THE WINDOW WAS RUNNING PERFECTLY THE WHOLE TIME. With
    `QT_QPA_PLATFORM=offscreen` inherited it builds every widget, enters its
    event loop, answers the single-instance socket -- and draws to nowhere.
    Measured on the live stuck process: alive, responding, 65.7 MB, window
    handle 0. It then HOLDS the instance name, so every later launch stands
    down in favour of a window nobody can see. Both symptoms, one cause.

    ⚠ It arrives by INHERITANCE. One shell with that variable set starts a
    tray, and the tray passes it to every window it opens from then on.

    ⛔ Only the values that make a GUI invisible are dropped: a deliberate
    `windows` or `wayland` override is somebody's real choice.
    """
    env = gui_run.child_env({u"QT_QPA_PLATFORM": platform})
    if kept:
        assert env.get(u"QT_QPA_PLATFORM") == platform
    else:
        assert u"QT_QPA_PLATFORM" not in env, (
            u"a child would inherit %r and render to nowhere" % platform)


def test_the_last_run_is_remembered_and_read_back(tmp_path):
    u"""⭐ SONIC, 2026-09-18: *"it should also have the most recent run stuff."*

    Settings loaded on open and results did not, so reopening showed an empty
    Subtitles tab under a header naming the time of a run whose rows were gone
    -- which reads as though the run had done nothing.

    ⛔ REMEMBERED, NOT RE-RUN. A run spends metered requests against a
    25-per-60s budget, and opening a window is not asking for one.
    """
    path = tmp_path / "last-run.json"
    rows = [video(), video(outcome="REFUSED", output_path=None)]
    summary = {"type": "run", "api_calls": 4, "seconds": 1.5}

    assert gui_run.save_last_run(rows, summary, path=path) == path
    back_rows, back_summary, saved_at = gui_run.load_last_run(path=path)
    assert back_rows == rows
    assert back_summary == summary
    assert saved_at, u"nothing recorded WHEN it was saved"


def test_no_memory_is_not_a_broken_window(tmp_path):
    u"""⛔ NEVER RAISES. A missing file is a first launch; a truncated or
    hand-edited one is a file somebody broke. Neither is a reason the window
    will not open, and both mean the same thing: no memory."""
    assert gui_run.load_last_run(path=tmp_path / "absent.json") == ([], {}, u"")

    broken = tmp_path / "half.json"
    broken.write_text(u'{"rows": [{"type": "vid', encoding="utf-8")
    assert gui_run.load_last_run(path=broken) == ([], {}, u"")

    wrong = tmp_path / "wrong.json"
    wrong.write_text(u'["not", "a", "dict"]', encoding="utf-8")
    assert gui_run.load_last_run(path=wrong) == ([], {}, u"")


def test_a_failed_save_leaves_the_previous_memory_whole(tmp_path, monkeypatch):
    u"""🚨 `open(path,'w')` truncates ON OPEN, so a raise mid-write would leave
    zero bytes -- and the next launch would read that as *no previous run*
    rather than as a broken one."""
    path = tmp_path / "last-run.json"
    gui_run.save_last_run([video()], {"api_calls": 1}, path=path)
    before = path.read_bytes()

    def boom(*a, **k):
        raise OSError("the disk went away")

    monkeypatch.setattr(gui_run.os, "replace", boom)
    assert gui_run.save_last_run([video()], {"api_calls": 9}, path=path) is None
    assert path.read_bytes() == before


def test_only_ONE_module_decides_a_child_process_environment():
    u"""🚨 THREE COPIES EXISTED AND THE THIRD WAS WRONG (2026-09-18).

    `hato/watch.py` built its own child environment, set the UTF-8 variables
    and omitted `PYTHONPATH`. A tray started from a shortcut therefore spawned
    `-m hato.gui` with the shortcut's working directory, which died instantly
    on `ModuleNotFoundError` -- and the spawn caught only `OSError`, so
    *"Open hato"* did nothing at all, silently. *"Run now"* from the tray was
    broken the same way. Sonic found it; no check could, because each copy was
    self-consistent.

    ⭐ THE COPIES COULD NOT SHARE BY IMPORT, which is why they drifted: the
    window may import Qt, the watcher may NOT import the window, and neither
    could reach the other. The answer was a module both already depend on --
    `paths`, which imports nothing but the stdlib.

    ⚠ Asserted on `PYTHONPATH`, the half that was missing, rather than on the
    UTF-8 lines all three got right.
    """
    import pathlib
    root = pathlib.Path(gui_run.__file__).resolve().parent.parent
    offenders = []
    for path in sorted(root.rglob(u"*.py")):
        if u"__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        # ⛔ Assignment, not mention: `env.get("PYTHONPATH", ...)` reads one and
        # is not a second opinion about what it should be.
        if u'env["PYTHONPATH"]' in text or u"env['PYTHONPATH']" in text:
            offenders.append(path.name)
    assert offenders == [u"paths.py"], (
        u"a child process's PYTHONPATH is decided in %s. It belongs in "
        u"paths.py alone -- the window and the watcher cannot import each "
        u"other, so a second copy is how one of them silently loses it."
        % u", ".join(offenders))


def test_the_child_is_told_to_speak_utf8_and_where_the_package_is(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    env = gui_run.child_env({"PATH": "x"})
    assert env["PYTHONIOENCODING"] == "utf-8"
    import hato
    parent = os.path.dirname(os.path.dirname(os.path.abspath(hato.__file__)))
    assert env["PYTHONPATH"].split(os.pathsep)[0] == parent


# ---------------------------------------------------------------------------
# 🚨 the engine's vocabulary, and the partition
# ---------------------------------------------------------------------------

def test_the_word_refused_never_reaches_a_person():
    u"""🚨 `05-interface.md`, from Sonic: *"when it says 'refused' it's quite
    alarming."* It is tsubasa's word for *the timing did not hold*, and to
    somebody who can fix it in two clicks it reads as an accusation.

    ⭐ The vocabulary is enumerable precisely so this negative is assertable.
    """
    words = gui_run.interface_words()
    assert words
    for word in words:
        assert "refus" not in word.lower()
        assert word.upper() != word, "an ENGINE CONSTANT leaked into the interface"
    assert gui_run.outcome_word(video(outcome="REFUSED")) == gui_run.NEEDS_YOU


def test_a_confident_row_with_nothing_written_is_not_called_added():
    u"""🚨 A dry run and a failed write both leave outcome CONFIDENT with no
    output_path, and the outcome field cannot see either. tsubasa's GUI said
    "1 synced" for both until an adversarial pass caught it."""
    assert gui_run.outcome_word(video()) == gui_run.ADDED
    assert gui_run.outcome_word(video(output_path=None)) == gui_run.FAILED


def test_a_skipped_row_is_skipped_whatever_its_outcome_says():
    assert gui_run.outcome_word(video(skip="present")) == gui_run.SKIPPED
    assert gui_run.outcome_word(video(skip="no-track", outcome=None)) == gui_run.SKIPPED


def test_nothing_on_jimaku_yet_is_not_a_failure():
    assert gui_run.outcome_word(video(outcome="NOT_FOUND", output_path=None)) \
        == gui_run.NOT_YET


def test_the_categories_partition(monkeypatch):
    u"""🚨 A subset presented as a sibling is how eight files became eleven on
    the one line a person reads at a glance."""
    rows = [video(), video(output_path=None), video(outcome="REFUSED"),
            video(outcome="NOT_FOUND"), video(skip="present"),
            video(outcome="ERROR")]
    got = gui_run.counts(rows)
    assert sum(got.values()) == len(rows)
    assert set(got) == gui_run.interface_words()      # every key present, even at 0


def test_a_match_rate_of_zero_is_not_the_same_as_no_match_rate():
    u"""⚠ `0` means *it matched nothing*, which is a real answer. An absent
    rate must not become zero."""
    assert gui_run.match_percent(video(tsubasa={"match_rate": 0.0})) == 0
    assert gui_run.match_percent(video(tsubasa=None)) is None
    assert gui_run.match_percent(video(tsubasa={"match_rate": 0.825})) == 82


def test_the_best_attempt_supplies_the_rate_when_nothing_was_written():
    row = video(outcome="REFUSED", tsubasa=None, output_path=None,
                attempts=[{"match_rate": 0.31}, {"match_rate": 0.57}])
    assert gui_run.match_percent(row) == 57


# ---------------------------------------------------------------------------
# driving a real child
# ---------------------------------------------------------------------------

def drive(monkeypatch, cli, timeout=20.0):
    monkeypatch.setenv("HATO_CLI", cli)
    runner = gui_run.Runner(argv=gui_run.cli_argv()).start()
    events, deadline = [], time.time() + timeout
    while time.time() < deadline:
        events.extend(runner.drain())
        done = runner.finished()
        if done is not None:
            events.extend(runner.drain())
            return done, events
        time.sleep(0.01)
    runner.stop()
    raise AssertionError("the child never finished")


def test_a_real_child_is_read_line_by_line(monkeypatch):
    done, events = drive(monkeypatch, fake_cli(
        json.dumps({"type": "progress", "phase": "start"}),
        json.dumps(video()),
        json.dumps({"type": "run", "api_calls": 4, "seconds": 1.5})))
    assert done.code == 0
    assert len(done.rows) == 1
    assert done.api_calls == 4
    assert [e.get("type") for e in events] == ["progress", "video", "run"]


def test_exit_1_is_something_needing_a_pick_and_not_a_failure(monkeypatch):
    u"""⛔ Only exit 2 means the command could not be run. Exit 1 is the whole
    value proposition: hato fetched something and the timing did not hold."""
    done, _ = drive(monkeypatch, fake_cli(
        json.dumps(video(outcome="REFUSED", output_path=None)),
        json.dumps({"type": "run"}), code=1))
    assert done.code == 1
    assert done.could_not_run is False
    assert done.counts[gui_run.NEEDS_YOU] == 1


def test_exit_2_is_the_one_that_means_it_could_not_run(monkeypatch):
    done, _ = drive(monkeypatch, fake_cli(code=2, stderr=["hato: no folder"]))
    assert done.could_not_run is True
    assert "no folder" in done.stderr


def test_stderr_is_an_information_channel_not_a_failure(monkeypatch):
    u"""⚠ hato puts NDJSON on stdout and its own notes on stderr, so a pipe
    stays pure NDJSON and a person is still told what happened."""
    done, events = drive(monkeypatch, fake_cli(
        json.dumps({"type": "run"}), stderr=["hato: 3 videos were skipped"]))
    assert done.code == 0
    assert any(e.get("type") == "note" for e in events)


def test_a_line_on_stdout_that_is_not_ndjson_is_surfaced_not_swallowed(monkeypatch):
    u"""⛔ Anything non-NDJSON on stdout is a defect in hato's own grammar
    (`_say`'s gate). Discarding it here is how it would stay invisible."""
    done, events = drive(monkeypatch, fake_cli(
        "hato: something English leaked", json.dumps({"type": "run"})))
    assert any(e.get("type") == "unparsed" for e in events)


def test_the_run_is_not_finished_while_its_last_lines_are_still_in_the_pipe(
        monkeypatch):
    u"""⚠ A process can exit with output still buffered. A window built on
    `poll() is not None` paints a run missing its final rows -- intermittently,
    and more often on a fast machine."""
    done, _ = drive(monkeypatch, fake_cli(
        *([json.dumps(video())] * 40 + [json.dumps({"type": "run"})])))
    assert len(done.rows) == 40
    assert done.summary.get("type") == "run"
