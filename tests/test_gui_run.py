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


def test_a_dry_runs_snapshot_is_no_memory(tmp_path):
    u"""🚨 RUNBOOK 8a. A dry run is not a run. hato 1.0.1 still writes its plan
    into this file, and PLANNED rows read as *"something went wrong"* on screen.

    ⭐ The CONTROL is the same file with `dry_run` false, remembered in full --
    without it, a loader that forgot everything would pass.
    """
    path = tmp_path / "last-run.json"
    plan = video(outcome="PLANNED", output_path=None)
    gui_run.save_last_run([plan], {"type": "run", "dry_run": True}, path=path)
    assert gui_run.load_last_run(path=path) == ([], {}, u""), (
        u"a dry run's PLAN was read back as the last run -- the window would "
        u"paint every PLANNED row as 'something went wrong'")

    gui_run.save_last_run([video()], {"type": "run", "dry_run": False}, path=path)
    rows, summary, saved_at = gui_run.load_last_run(path=path)
    assert rows == [video()] and summary.get("type") == "run" and saved_at


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
    assert gui_run.is_skipped(gui_run.outcome_word(video(skip="present")))
    assert gui_run.is_skipped(
        gui_run.outcome_word(video(skip="no-track", outcome=None)))


def test_the_FIVE_skips_do_not_collapse_into_one_reassuring_word():
    u"""🚨 Sonic, 2026-09-19, on the published 1.0.1: *"Katanai and tsuihou
    don't have it even though it says its already subbed in the GUI."*

    Both were true SKIPs and neither meant the video had its subtitle: one is
    an Erai-raws [MultiSub] rip whose Japanese track is INSIDE the container,
    the other downloaded 3 of 10 candidates, kept none, and is retrying
    tomorrow. ⛔ `outcome_word` answered *"already had one"* for both.

    ⚠ The engine always sent `skip`; only the window threw it away. The CLI has
    distinguished all four since 4a."""
    words = set()
    for kind in (u"present", u"embedded", u"negative", u"no-track",
                 u"blacklisted"):
        word = gui_run.outcome_word(video(skip=kind, outcome=None))
        assert gui_run.is_skipped(word), (kind, word)
        words.add(word)
    assert len(words) == 5, u"five skips rendered as %d word(s): %r" % (
        len(words), sorted(words))

    # ⛔ The two from the report, by name, and the exact claim each must NOT make
    retrying = gui_run.outcome_word(video(skip=u"negative", outcome=None))
    assert u"had one" not in retrying and u"alread" not in retrying, retrying
    inside = gui_run.outcome_word(video(skip=u"embedded", outcome=None))
    assert u"inside" in inside, inside


def test_an_unknown_skip_still_renders_as_something():
    u"""⚠ A skip kind this GUI has never heard of must not paint a blank row.
    The engine can add one without the window being rebuilt."""
    word = gui_run.outcome_word(video(skip=u"some-future-skip", outcome=None))
    assert word and gui_run.is_skipped(word), word


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


def test_exit_1_is_a_run_that_STOPPED_and_a_pick_is_exit_0(monkeypatch):
    u"""🚨 ADVERSARY 2026-09-22 A12. This check used to be called *"exit 1 is
    something needing a pick"*, and it pinned the misreading: `hato` exits 0 for
    a run with picks and 1 for a run cut short -- a 401, a server gone, a crash
    -- which the window then painted as *done*."""
    done, _ = drive(monkeypatch, fake_cli(
        json.dumps(video(outcome="REFUSED", output_path=None)),
        json.dumps({"type": "run"}), code=0))
    assert (done.code, done.stopped, done.could_not_run) == (0, False, False)
    assert done.counts[gui_run.NEEDS_YOU] == 1, u"a pick is the tool working, exit 0"
    cut, _ = drive(monkeypatch, fake_cli(
        json.dumps({"type": "run", "stopped": "jimaku rejected the key (401)"}),
        code=1, stderr=["hato: the run stopped early: jimaku rejected the key (401)"]))
    assert cut.stopped is True and cut.could_not_run is False
    assert cut.said == u"the run stopped early: jimaku rejected the key (401)", cut.said


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


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 8e -- Needs you: one list, the honest wait, and a pick that is read
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone          # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


#: ⚠ FORWARD SLASHES in this block, on purpose: it was first written through a shell
#: heredoc, which turned `\\` into `\` and `"C:\hato\cache\x..."` into a syntax error
#: (LEDGER-HOT's heredoc trap, a sixth time). Windows reads either separator.
def tried(name, rate, path="C:/hato/cache/x.ja.ass"):
    return {"name": name, "outcome": "REFUSED", "reason": "the timing did not hold",
            "bytes": 1000, "match_rate": rate, "path": path, "when": "2026-09-21"}


def waiting_row(video="D:/A/ep12.mkv", with_files=True, due=NOW + timedelta(hours=13, minutes=20)):
    return video_row(video=video, outcome="SKIPPED", skip="negative", output_path=None,
                     retry_after=due.isoformat(),
                     tried_before=[tried("a.ass", 0.70), tried("b.srt", 0.47)] if with_files else [])


def video_row(**over):
    row = video(**over)
    row.setdefault("tried_before", [])
    return row


def test_the_pick_sends_force_only_when_asked():
    u"""D6. The flag rides on the end, after --json; the pair stays the pair."""
    plain = gui_run.argv_for_pair("D:/A/x.mkv", "D:/A/sub.ass")
    forced = gui_run.argv_for_pair("D:/A/x.mkv", "D:/A/sub.ass", force=True)
    assert "--force" not in plain and forced[-1] == "--force"
    assert forced[:-1] == plain and plain[-1] == "--json"


def test_a_pick_is_paired_only_when_the_answer_says_a_file_landed():
    u"""🚨 D7. The window painted "paired" at the CLICK, over a child that had died
    on a usage error. The verdict comes from the answer -- never from the click and
    never from an exit code alone."""
    assert gui_run.pick_verdict(0, {"written": True, "forced": False})[0] == gui_run.PAIRED
    assert gui_run.pick_verdict(0, {"written": True, "forced": True})[0] == gui_run.FORCED
    word, why, landed = gui_run.pick_verdict(1, {"written": False, "outcome": "REFUSED",
                                                 "reason": "31% -- no"})
    assert word == gui_run.PICK_REFUSED and why and landed is None
    assert gui_run.pick_verdict(2, {})[0] == gui_run.PICK_FAILED, (
        u"a usage error read as anything but a failure")
    assert gui_run.pick_verdict(0, {})[0] == gui_run.PICK_FAILED, (
        u"exit 0 with no answer was read as a success")


def test_a_skip_that_is_waiting_on_files_is_a_row_a_person_can_pick_from():
    u"""⭐ 4a. `skip: negative` is not "done": with files it is a PICK, without
    them it is WAITING -- and a present or embedded subtitle needs nobody."""
    assert gui_run.problem_kind(waiting_row()) == gui_run.PICK
    assert gui_run.problem_kind(waiting_row(with_files=False)) == gui_run.WAITING
    assert gui_run.problem_kind(video_row(skip="present")) is None
    assert gui_run.problem_kind(video_row(outcome="REFUSED", output_path=None,
                                          attempts=[tried("a.ass", 0.3)])) == gui_run.PICK
    assert gui_run.problem_kind(video_row(outcome="NOT_FOUND")) == gui_run.WAITING
    assert gui_run.problem_kind(video_row(outcome="ERROR")) == gui_run.TROUBLE
    assert gui_run.problem_kind(video_row()) is None


def test_a_refusal_with_nothing_tried_is_trouble_whose_reason_shows_never_a_pick():
    u"""ADVERSARY 2026-09-22 A6. Two videos on one file, a name holding two
    episodes, a name with no number: refused before any download. As a PICK the
    row read *"0 tried · best —"* over nothing, and hid the one sentence that
    says what to do."""
    for reason in (u"this video and ep06.mp4 would be given the SAME subtitle file",
                   u"the video holds episodes 1-2 -- Split the file",
                   u"No episode number was read from the video"):
        row = video_row(outcome="REFUSED", output_path=None, reason=reason)
        assert gui_run.problem_kind(row) == gui_run.TROUBLE, reason


def test_every_file_ever_tried_is_offered_once_best_first():
    row = video_row(outcome="REFUSED", attempts=[tried("c.ass", 0.30), tried("a.ass", 0.72)],
                    tried_before=[tried("a.ass", 0.70), tried("b.srt", None)])
    names = [c["name"] for c in gui_run.candidates_of(row)]
    assert names == ["a.ass", "c.ass", "b.srt"], (
        u"a file offered twice, a stale copy preferred, or an unmeasured one first")
    assert gui_run.candidates_of(row)[0]["match_rate"] == 0.72   # THIS run's copy won


def test_needs_you_keeps_a_problem_the_last_run_never_looked_at():
    u"""🚨 4a's FIRST CAUSE: `last-run.json` is a snapshot of one run, so a run over
    another folder wiped the view. The memory keeps it."""
    other = waiting_row(video="D:/B/ep03.mkv")
    shown = gui_run.needs_you([video_row()], remembered=[other])
    assert [r["video"] for r in shown] == ["D:/B/ep03.mkv"]


def test_needs_you_drops_a_row_the_newer_memory_no_longer_lists():
    u"""⭐ Settled since the snapshot -- a pick landed, a subtitle appeared. ⛔ But a
    clash (a row the state DB never holds) is kept: its absence says nothing."""
    settled = video_row(video="D:/A/ep05.mkv", outcome="REFUSED", output_path=None,
                        attempts=[tried("x.ass", 0.3)])
    clash = video_row(video="D:/A/ep06.mkv", outcome="REFUSED", output_path=None,
                      reason="this video and ep06.mp4 would be given the SAME file")
    shown = gui_run.needs_you([settled, clash], remembered=[])
    assert [r["video"] for r in shown] == ["D:/A/ep06.mkv"]


def test_a_row_a_run_streamed_after_the_memory_wins_and_nothing_is_dropped():
    live = video_row(video="D:/A/ep05.mkv", outcome="REFUSED", output_path=None,
                     attempts=[tried("new.ass", 0.4)])
    stale = waiting_row(video="D:/A/ep05.mkv")
    key = gui_run.problem_key(live)
    assert gui_run.needs_you([live], remembered=[stale], live={key}) == [live]
    assert gui_run.needs_you([live], remembered=[], live={key}) == [live]
    assert gui_run.needs_you([live], remembered=[stale]) == [stale], (
        u"the control: not streamed, the newer memory's copy is the one")


# -- ADVERSARY 2026-09-22: which copy wins is decided per video -------------------------------

def _refused(video, name="x.ass"):
    return video_row(video=video, outcome="REFUSED", output_path=None,
                     attempts=[tried(name, 0.3)], retry_after=NOW.isoformat())


def test_a_look_again_on_one_row_makes_only_that_row_newer_than_the_memory():
    u"""A4. One flag for the whole list: during a look-again on row Y, EVERY stale
    snapshot row beat memory -- a row the person had just paired or blacklisted
    came back asking, and the badge counted it."""
    settled = _refused("D:/A/ep54.mkv")                  # memory: settled since
    looked = _refused("D:/A/ep23.mkv", "fresh.ass")      # streamed by the look-again
    remembered = waiting_row(video="D:/A/ep23.mkv")
    shown = gui_run.needs_you([settled, looked], remembered=[remembered],
                              live={gui_run.problem_key(looked)})
    assert [r["video"] for r in shown] == ["D:/A/ep23.mkv"], (
        u"a row memory settled came back because ANOTHER row was looked at again: %s"
        % [r["video"] for r in shown])
    assert shown[0] is looked, u"the look-again's own copy must win for its own video"


def test_a_newer_row_that_is_no_problem_settles_the_remembered_one():
    u"""A14. A run SETTLED a remembered problem -- and memory's stale copy went on
    asking, because the run's rows were filtered to problems before the merge.
    The footer said "0 added · 1 needs you" beside a Subtitles row saying added."""
    remembered = waiting_row(video="D:/A/ep12.mkv")
    done = video_row(video="D:/A/ep12.mkv")              # CONFIDENT, written
    key = gui_run.problem_key(done)
    assert gui_run.needs_you([done], remembered=[remembered], live={key}) == []
    counts = gui_run.tally([done], [], done=())
    assert counts[gui_run.ADDED] == 1 and counts[gui_run.NEEDS_YOU] == 0, counts


def test_a_problem_memory_cannot_list_is_not_settled_by_its_silence():
    u"""A26. A run over a folder not in Settings -- `hato D:\\Elsewhere` from a
    terminal -- has refusals `hato problems` can never list, and the newer, silent
    memory "settled" them."""
    elsewhere = _refused("E:/Elsewhere/ep05.mkv")
    inside = _refused("D:/A/ep07.mkv")

    def in_scope(row):
        return row["video"].startswith("D:/A/")

    shown = gui_run.needs_you([elsewhere, inside], remembered=[], in_scope=in_scope)
    assert [r["video"] for r in shown] == ["E:/Elsewhere/ep05.mkv"], (
        u"the in-scope row is settled (memory would list it); the other cannot be")


def test_a_cleared_memorys_silence_settles_nothing():
    u"""A27. After *Clear hato's memory* the DB holds nothing, so `hato problems`
    answers [] -- and every row on screen was dropped as "settled", though not
    one of those episodes has a subtitle."""
    row = _refused("D:/A/ep54.mkv")
    assert gui_run.needs_you([row], remembered=[]) == [], u"the control"
    assert gui_run.needs_you([row], remembered=[], trust_rows=True) == [row]


def test_two_spellings_of_one_video_are_one_row_and_one_count():
    u"""A7. The raw path and a normalised one were two identities: two rows under a
    badge of one."""
    upper = _refused("D:/Anime/Show/ep54.mkv")
    lower = dict(upper, video="d:\\anime\\show\\ep54.mkv") if os.name == "nt" \
        else dict(upper)
    shown = gui_run.needs_you([upper, lower], remembered=None)
    assert len(shown) == 1, [r["video"] for r in shown]
    assert gui_run.tally([upper, lower], shown)[gui_run.NEEDS_YOU] == 1


def test_a_pick_that_landed_is_counted_as_added():
    u"""A15. A landed pick was counted nowhere, so the footer summed to less than
    the rows on screen."""
    row = _refused("D:/A/ep54.mkv")
    key = gui_run.problem_key(row)
    counts = gui_run.tally([row], [row], done=[key])
    assert counts[gui_run.ADDED] == 1 and counts[gui_run.NEEDS_YOU] == 0, counts


def test_before_the_memory_answers_the_run_rows_are_shown_as_they_are():
    assert gui_run.needs_you([waiting_row()], remembered=None) == [waiting_row()]


def test_the_wait_is_said_as_a_promise_only_when_something_will_keep_it():
    u"""🚨 4b + D2. With the tray watching, "retrying in 14h" is a promise (it wakes
    for it). Without it -- and with no daily run registered (`daily` not given
    here; `test_gui_widgets` holds that case) -- nothing runs on its own, so the
    sentence says when it becomes DUE. ⚠ Rounded UP: 13h20m is 14h."""
    row = waiting_row()
    assert gui_run.retry_text(row, NOW, watching=True) == u"retrying in 14h"
    assert gui_run.retry_text(row, NOW, watching=False) == u"retry after 14h"
    soon = waiting_row(due=NOW + timedelta(minutes=9, seconds=5))
    assert gui_run.retry_text(soon, NOW, watching=True) == u"retrying in 10m"
    late = waiting_row(due=NOW - timedelta(minutes=1))
    assert gui_run.retry_text(late, NOW, watching=True) == u"retrying now"
    assert gui_run.retry_text(late, NOW, watching=False) == u"retry due"
    month = waiting_row(due=NOW + timedelta(days=29, hours=2))
    assert gui_run.retry_text(month, NOW, watching=True) == u"retrying in 30 days"
    assert gui_run.retry_text(video_row(), NOW, watching=True) == u""


def test_a_subtitle_found_only_after_earlier_files_failed_says_so():
    assert gui_run.found_on_retry(video_row(tried_before=[tried("a.ass", 0.7)]))
    assert not gui_run.found_on_retry(video_row())
    assert not gui_run.found_on_retry(video_row(output_path=None,
                                                tried_before=[tried("a.ass", 0.7)]))


def test_look_again_now_is_one_video_the_wait_skipped_and_its_folder_named():
    argv = gui_run.argv_for_retry("D:/A/ep12.mkv", "D:/A", candidates=3)
    assert argv[argv.index("--only") + 1] == os.path.abspath("D:/A/ep12.mkv")
    assert "--retry-now" in argv and "--force" not in argv, (
        u"look-again must skip the WAIT only -- never re-download a refused file")
    assert argv[argv.index("--candidates") + 1] == "3"
    assert argv[-1] == os.path.abspath("D:/A")


def test_no_new_word_says_refused():
    assert not [w for w in gui_run.interface_words() if "refus" in w.lower()]


def test_probably_not_out_is_exactly_one_past_the_newest_on_offer():
    u"""⭐ RUNBOOK 8f. ⛔ A gap of two is a MISSING episode, not a late one."""
    assert gui_run.probably_not_out({"episode": 23, "newest_offered": 22})
    assert not gui_run.probably_not_out({"episode": 22, "newest_offered": 22}), u"on offer"
    assert not gui_run.probably_not_out({"episode": 24, "newest_offered": 22}), u"a gap"
    assert not gui_run.probably_not_out({"episode": 23, "newest_offered": None})
    assert not gui_run.probably_not_out({"episode": None, "newest_offered": 22})
    assert not gui_run.probably_not_out({"episode": True, "newest_offered": 0}), (
        u"a bool is not an episode number")
    assert not gui_run.probably_not_out({"episode": [23, 24], "newest_offered": 22})


def test_a_pick_the_person_waits_on_is_a_wait_for_exactly_its_date():
    u"""⭐ HANDOFF 4c. Held as long as the retry it was chosen FOR -- a new date (a
    run recorded another negative) or the date passing puts it back asking."""
    row = waiting_row()
    key = gui_run.problem_key(row)
    waits = {key: row["retry_after"]}
    kept, = gui_run.apply_waits([row], waits, NOW)
    assert gui_run.problem_kind(kept) == gui_run.WAITING
    assert gui_run.problem_kind(row) == gui_run.PICK, u"the row handed in was changed"
    counted = gui_run.tally([], [kept])
    assert counted[gui_run.NEEDS_YOU] == 0 and counted[gui_run.NOT_YET] == 1, counted
    moved = dict(row, retry_after=(NOW + timedelta(days=2)).isoformat())
    assert gui_run.problem_kind(gui_run.apply_waits([moved], waits, NOW)[0]) == gui_run.PICK
    later = NOW + timedelta(days=1)
    assert gui_run.problem_kind(gui_run.apply_waits([row], waits, later)[0]) == gui_run.PICK
    assert gui_run.problem_kind(gui_run.apply_waits([row], {}, NOW)[0]) == gui_run.PICK
    nothing = waiting_row(with_files=False)
    assert gui_run.apply_waits([nothing], {gui_run.problem_key(nothing):
                                           nothing["retry_after"]}, NOW)[0] == nothing, (
        u"only a PICK can be waited on -- a wait is already one")


def test_the_waits_survive_the_window_and_a_broken_file_is_none(tmp_path):
    path = tmp_path / "window-waits.json"
    assert gui_run.save_waits({"d:/a/ep12.mkv": "2026-09-23T01:42:04+00:00"}, path)
    assert gui_run.load_waits(path) == {"d:/a/ep12.mkv": "2026-09-23T01:42:04+00:00"}
    path.write_text("{not json", encoding="utf-8")
    assert gui_run.load_waits(path) == {}
    assert gui_run.load_waits(tmp_path / "absent.json") == {}
    assert not [p for p in tmp_path.iterdir() if ".new-" in p.name], u"a temp was left"


def test_clearing_counts_by_default_and_clears_only_with_yes():
    u"""⭐ RUNBOOK 8g. ⛔ The dry count is what the card asks for, and it must
    never be the call that deletes."""
    dry = gui_run.argv_for_clear()
    assert dry[-3:] == ["state", "--clear", "--json"] and "--yes" not in dry
    assert gui_run.argv_for_clear(yes=True)[-1] == "--yes"
    assert "--blacklist" not in gui_run.argv_for_clear(yes=True)
    assert gui_run.argv_for_clear(yes=True, blacklist=True)[-2:] == ["--yes", "--blacklist"]


def test_the_memory_is_counted_in_words_a_person_recognises():
    said = gui_run.memory_summary({"cleared": {"videos": 1, "waiting": 0, "shows": 2,
                                               "attempts": 3}})
    assert said == u"1 video tried · 0 waiting to look again · 2 shows found on jimaku"
    assert gui_run.memory_summary(None) == u"" and gui_run.memory_summary({}) == u""
    assert "row" not in said and "table" not in said
