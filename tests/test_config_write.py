# -*- coding: utf-8 -*-
"""
The config WRITER and the non-file key route -- RUNBOOK 7a,
spec/05-interface.md §The window.

🚨 WHY THIS SUITE EXISTS. `hato config` was READ-ONLY, and the ruled Settings
tab edits the watched folders, the skipped folders, the schedule and the key.
Two-thirds of that tab had no mechanism behind it, and the gap survived a table
that marked the row ✅ -- because the check was *"does the command exist"* and
the question was *"can the interface do its job through it"*.

Structurally cannot cover: that the WINDOW calls these and paints the refusals
-- that is RUNBOOK 7e, and its checks drive the real widgets. What is proved
here is that there is exactly one writer, that it cannot write anything the
reader would refuse, and that a failed write leaves the previous file intact.
"""
import os
import sys
from pathlib import Path

import pytest

from hato import config, credentials, pipeline
from hato import cli


def load_from(tmp_path, text=u""):
    p = tmp_path / "config.toml"
    p.write_bytes(text.encode("utf-8"))
    return config.load(p)


# ---------------------------------------------------------------------------
# the round trip -- one writer, one schema, one validator
# ---------------------------------------------------------------------------

def test_what_is_written_reads_back_as_the_same_settings(tmp_path):
    cfg = load_from(tmp_path)
    fresh = config.with_changes(
        cfg, folders=[str(tmp_path / "Anime")], candidates=7, archives=True,
        lang="ja", recurse=False)
    config.save(fresh)
    again = config.load(tmp_path / "config.toml")
    for name in config.SCHEMA:
        assert getattr(again, name) == getattr(fresh, name), name
    assert (again.log_path, again.log_keep) == (fresh.log_path, fresh.log_keep)


def test_every_schema_key_is_written_so_a_person_can_read_what_is_in_force(tmp_path):
    u"""⚠ Every key but the ones an older hato has never heard of, at their
    default -- the check below says why. Once set, those are written too."""
    text = config.dumps(load_from(tmp_path))
    for name in config.SCHEMA:
        if name in config.NEWER_KEYS:
            continue
        assert (u"\n%s = " % name) in text, name
    changed = config.with_changes(load_from(tmp_path), prefer_format=u"srt",
                                  format_fallback=True, auto_update=False)
    text = config.dumps(changed)
    for name in config.NEWER_KEYS:
        assert (u"\n%s = " % name) in text, name


def test_a_file_written_with_the_format_settings_untouched_is_one_1_0_2_can_read(tmp_path):
    u"""🚨 RUNBOOK 9a. An older hato REFUSES a key it does not know -- in every
    version -- and a 1.0.2 tray re-reads this file on every tick and starts every
    run with its own `hato-cli`. Written with `prefer_format` at its default, the
    first setting a person changed in the 1.0.3 window would stop every run their
    old tray, or a daily task pointing at an old copy, ever started.

    Two arms against 1.0.2's key list, VERBATIM from its `config.py` -- ⚠ not
    today's schema minus the new keys: today's parser READS the new keys, so
    shrinking its schema tests neither version (measured: it raised KeyError).
    Untouched, every key is one 1.0.2 knows; changed, one is not -- which is what
    proves the rule is doing something, and why the tray needs a restart then.
    """
    from hato.config import _toml
    known_to_1_0_2 = {"folders", "skip_folders", "lang", "out", "subs_dir", "candidates",
                      "archives", "allow_ai", "recurse", "skip_embedded", "watch",
                      "schedule", "surasura_dir", "log"}
    fresh = config.with_changes(load_from(tmp_path), folders=[str(tmp_path / "Anime")],
                                candidates=4)
    untouched = set(_toml.loads(config.dumps(fresh)))
    changed = set(_toml.loads(config.dumps(config.with_changes(fresh, prefer_format=u"srt"))))
    assert untouched <= known_to_1_0_2, untouched - known_to_1_0_2          # arm 1
    assert changed - known_to_1_0_2 == {"prefer_format"}                    # arm 2


def test_a_file_written_with_updating_untouched_is_one_1_0_3_can_read(tmp_path):
    u"""The same rule for LAYER 11's `auto_update` (RUNBOOK 11f): ON by default, and
    a file that never turned it off must stay one 1.0.3 -- and its tray, or a daily
    task still pointing at it -- can read. Two arms against 1.0.3's key list."""
    from hato.config import _toml
    known_to_1_0_3 = {"folders", "skip_folders", "lang", "out", "subs_dir", "candidates",
                      "archives", "allow_ai", "recurse", "skip_embedded", "watch",
                      "schedule", "surasura_dir", "prefer_format", "format_fallback", "log"}
    fresh = config.with_changes(load_from(tmp_path), folders=[str(tmp_path / "Anime")],
                                prefer_format=u"srt")
    untouched = set(_toml.loads(config.dumps(fresh)))
    changed = set(_toml.loads(config.dumps(config.with_changes(fresh, auto_update=False))))
    assert untouched <= known_to_1_0_3, untouched - known_to_1_0_3          # arm 1
    assert changed - known_to_1_0_3 == {"auto_update"}                      # arm 2


def test_the_writer_raises_when_the_schema_grows_a_key_it_does_not_carry(tmp_path):
    u"""⛔ A key added to SCHEMA and forgotten in the writer must RAISE, not
    vanish from every config.toml hato writes."""
    cfg = load_from(tmp_path)
    config.SCHEMA["invented_key"] = (str, "")
    try:
        with pytest.raises(config.ConfigError) as exc:
            config.dumps(cfg)
        assert "invented_key" in str(exc.value)
    finally:
        del config.SCHEMA["invented_key"]


def test_save_refuses_anything_the_reader_would_refuse_before_it_writes(tmp_path):
    u"""⭐ THE GATE. Not "the writer agrees with the reader" -- the reader IS
    the gate, so a file hato cannot load is unreachable."""
    cfg = load_from(tmp_path)
    target = tmp_path / "config.toml"
    target.write_bytes(b"candidates = 4\n")
    bad = config.parse(u"")
    bad.path = target
    bad.candidates = 0                         # refused by parse(): must be >= 1
    with pytest.raises(config.ConfigError) as exc:
        config.save(bad, target)
    assert "at least 1" in str(exc.value)
    assert target.read_bytes() == b"candidates = 4\n"   # untouched


# ---------------------------------------------------------------------------
# 🚨 the TOML string trap -- a Windows path in a basic string is an escape
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("leaf", [
    u"newanime",        # \n  -- a newline escape in a TOML basic string
    u"Utils",           # \U  -- a unicode escape; TOML REJECTS a short one
    u"tab",             # \t
    u"read",            # \r
    u"日本語のフォルダ",
    u"Bob's Anime",     # forces the basic-string fallback
])
def test_a_windows_path_survives_the_round_trip(tmp_path, leaf):
    folder = str(Path("D:\\") / leaf) if os.name == "nt" else str(Path("/srv") / leaf)
    cfg = config.with_changes(load_from(tmp_path), folders=[folder])
    again = config.parse(config.dumps(cfg))
    assert [Path(f) for f in again.folders] == [Path(folder)]


def test_true_is_written_as_true_and_not_as_one(tmp_path):
    u"""⚠ bool is a subclass of int. Reached by the int branch first,
    `archives = true` becomes `archives = 1`, which parse() then refuses."""
    text = config.dumps(config.with_changes(load_from(tmp_path), archives=True))
    assert u"archives = true" in text
    assert u"archives = 1" not in text


# ---------------------------------------------------------------------------
# a failed write leaves the OLD file -- never zero bytes
# ---------------------------------------------------------------------------

def test_a_write_that_raises_leaves_the_previous_file_whole(tmp_path, monkeypatch):
    u"""🚨 `open(path,'w')` truncates ON OPEN. This destroyed
    tsubasa/spec/RUNBOOK.md on 2026-09-07; a zeroed config.toml would take
    every watched folder out of every run, silently."""
    target = tmp_path / "config.toml"
    target.write_bytes(b"candidates = 4\n")
    cfg = config.load(target)
    original = target.read_bytes()

    def boom(*a, **k):
        raise OSError("the disk went away")

    monkeypatch.setattr(config.os, "replace", boom)
    with pytest.raises(OSError):
        config.save(config.with_changes(cfg, candidates=9), target)
    assert target.read_bytes() == original
    assert list(tmp_path.glob("config.toml.new-*")) == []   # nothing left behind


def test_a_successful_write_leaves_no_temp_file(tmp_path):
    cfg = load_from(tmp_path)
    config.save(config.with_changes(cfg, candidates=6))
    assert list(tmp_path.glob("*.new-*")) == []


# ---------------------------------------------------------------------------
# with_changes
# ---------------------------------------------------------------------------

def test_with_changes_does_not_touch_the_config_it_was_given(tmp_path):
    cfg = load_from(tmp_path, u"candidates = 2\n")
    config.with_changes(cfg, candidates=8)
    assert cfg.candidates == 2


def test_a_refused_change_raises_and_changes_nothing(tmp_path):
    cfg = load_from(tmp_path, u"candidates = 2\n")
    with pytest.raises(config.ConfigError):
        config.with_changes(cfg, lang="jap")
    assert cfg.lang == "ja"


def test_an_unknown_setting_is_refused_by_name(tmp_path):
    with pytest.raises(config.ConfigError) as exc:
        config.with_changes(load_from(tmp_path), candiates=5)
    assert "candiates" in str(exc.value)


# ---------------------------------------------------------------------------
# coerce -- KEY=VALUE off a command line
# ---------------------------------------------------------------------------

def test_coerce_reads_the_two_boolean_words_and_refuses_the_lookalikes():
    assert config.coerce("archives", "true") is True
    assert config.coerce("archives", "False") is False
    for guessable in ("yes", "no", "1", "0", "on", "off", ""):
        with pytest.raises(config.ConfigError):
            config.coerce("archives", guessable)


def test_coerce_refuses_a_list_and_says_which_flag_to_use():
    for name in ("folders", "skip_folders"):
        with pytest.raises(config.ConfigError) as exc:
            config.coerce(name, "D:\\Anime")
        assert "--add-" in str(exc.value)


def test_coerce_refuses_an_unknown_setting_and_lists_the_real_ones():
    with pytest.raises(config.ConfigError) as exc:
        config.coerce("candiates", "5")
    assert "candidates" in str(exc.value)


# ---------------------------------------------------------------------------
# 🚨 skip_folders -- a setting the RUN honours, not merely stores
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inside,folder,want", [
    ("D:\\Anime\\s1\\x.mkv", "D:\\Anime", True),
    ("D:\\Anime\\x.mkv", "D:\\Anime", True),
    # 🚨 THE PREFIX TRAP. `startswith` says yes, and skipping one library would
    # silently take a DIFFERENT one out of every run.
    ("D:\\Anime2\\x.mkv", "D:\\Anime", False),
    ("D:\\Anime\\x.mkv", "D:\\Anime\\s1", False),
    ("D:\\Anime\\x.mkv", "D:\\Anime\\", True),            # a trailing separator
    # 🚨 CASE IS NOT IDENTITY -- on Windows. Marked `nt_only` because on a
    # case-SENSITIVE filesystem the right answer is the opposite one, and a
    # check that demands Windows semantics everywhere is asserting a bug.
    pytest.param("D:\\ANIME\\S1\\x.mkv", "d:\\anime", True,
                 marks=pytest.mark.skipif(
                     os.name != "nt",
                     reason="case-insensitive paths are a Windows fact")),
])
def test_a_video_is_inside_a_skipped_folder_only_when_it_really_is(inside, folder, want):
    u"""⚠ THE POSIX GUARD HERE WAS WRONG AND CI FOUND IT ON THE FIRST RUN THAT
    REACHED A LINUX BOX. It read `folder.lower() != folder` -- but the case
    difference in the fixture is on the OTHER side (`D:\\ANIME` against
    `d:\\anime`), so the folder was already lowercase, the skip never fired,
    and the case ran on a filesystem where its answer is false. The marker
    above states the platform fact where a reader can see it instead.
    """
    if os.name != "nt":
        inside = inside.replace("D:\\", "/").replace("\\", "/")
        folder = folder.replace("D:\\", "/").replace("\\", "/")
    assert pipeline._under_any(inside, [folder]) is want


def test_a_video_in_no_skipped_folder_is_kept_and_an_empty_list_skips_nothing():
    assert pipeline._under_any("D:\\Anime\\x.mkv", []) is False
    assert pipeline._under_any("D:\\Other\\x.mkv", ["D:\\Anime"]) is False


def test_settings_carry_the_skipped_folders_from_the_config(tmp_path):
    watched, skipped = tmp_path / "Anime", tmp_path / "Anime" / "_incoming"
    cfg = config.with_changes(load_from(tmp_path), folders=[str(watched)],
                              skip_folders=[str(skipped)])
    settings = pipeline.Settings.from_config(cfg)
    assert [Path(f) for f in settings.skip_folders] == [skipped]


# ---------------------------------------------------------------------------
# the key -- the non-file road
# ---------------------------------------------------------------------------

def test_a_key_given_as_a_string_lands_in_the_key_file(tmp_path):
    target = tmp_path / "key.txt"
    key, written = credentials.save_key_value(u"  abc123XYZ  ", target)
    assert written == target
    assert key.hint.endswith("XYZ")
    assert credentials.read_key_file(target) == u"abc123XYZ"


@pytest.mark.parametrize("bad,guard", [
    (u"", "empty"),
    (u"   ", "empty after stripping"),
    # 🚨 NO SPACE IN THIS ONE, AND THAT IS THE WHOLE POINT. Written as
    # "# not a key" it was caught by the SPACE guard, so deleting the comment
    # guard entirely left the check green -- mutant M7a-13 survived, and the
    # check passed for a reason other than its name. Measured 2026-09-18, and
    # it is this project's own documented failure: *"the check passed for the
    # opposite of its stated reason"* (HANDOFF.md §6f).
    (u"#notakey", "a comment"),
    (u"two words", "a space"),
    (u"line1\nline2", "more than one line"),
])
def test_the_string_road_and_the_file_road_refuse_the_same_things(bad, guard):
    u"""⭐ One validator. A refusal the file gives and the pipe does not is the
    "two roads into one setting" defect.

    ⚠ ONE CASE PER RUN, not a loop. A loop over overlapping cases means any
    single guard can be deleted without a check noticing, because a later guard
    catches the input the deleted one was named for.
    """
    with pytest.raises(credentials.KeyMissing):
        credentials.check_key_value(bad)


def test_a_refused_key_writes_nothing_at_all(tmp_path):
    target = tmp_path / "key.txt"
    with pytest.raises(credentials.KeyMissing):
        credentials.save_key_value(u"", target)
    assert not target.exists()
    assert list(tmp_path.glob("key.txt.new-*")) == []


def test_replacing_a_key_leaves_the_old_one_if_the_new_one_is_refused(tmp_path):
    target = tmp_path / "key.txt"
    credentials.save_key_value(u"goodkey1", target)
    before = target.read_bytes()
    with pytest.raises(credentials.KeyMissing):
        credentials.save_key_value(u"# a comment", target)
    assert target.read_bytes() == before


def test_the_key_never_reaches_the_config_file(tmp_path):
    u"""🚨 LEDGER-HOT.md's first rule. The writer must be incapable of it."""
    cfg = load_from(tmp_path)
    with pytest.raises(config.ConfigError):
        config.with_changes(cfg, api_key="abc123")
    text = config.dumps(config.with_changes(cfg, candidates=5))
    assert "abc123" not in text


# ---------------------------------------------------------------------------
# through the CLI -- the road the window actually drives
# ---------------------------------------------------------------------------

def cfg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "config.toml"))


def test_set_changes_a_value_and_show_reads_it_back(monkeypatch, tmp_path, capsys):
    cfg_env(monkeypatch, tmp_path)
    assert cli.main(["config", "--set", "candidates=5"]) == 0
    capsys.readouterr()
    assert cli.main(["config", "--show"]) == 0
    out = capsys.readouterr().out
    assert "candidates" in out and "5" in out
    assert "config.toml" in out


def test_add_folder_round_trips_and_removing_one_that_is_absent_is_refused(
        monkeypatch, tmp_path, capsys):
    cfg_env(monkeypatch, tmp_path)
    folder = str(tmp_path / "Anime")
    assert cli.main(["config", "--add-folder", folder]) == 0
    assert [Path(f) for f in config.load().folders] == [Path(folder)]
    capsys.readouterr()
    # ⭐ REFUSED, NOT IGNORED. Succeeding quietly tells somebody their library
    # is no longer scanned when it still is.
    assert cli.main(["config", "--remove-folder", str(tmp_path / "Nope")]) != 0
    assert "nothing to remove" in capsys.readouterr().err
    assert cli.main(["config", "--remove-folder", folder]) == 0
    assert config.load().folders == ()


def test_adding_the_same_folder_twice_is_a_no_op(monkeypatch, tmp_path):
    cfg_env(monkeypatch, tmp_path)
    folder = str(tmp_path / "Anime")
    cli.main(["config", "--add-folder", folder])
    cli.main(["config", "--add-folder", folder])
    assert len(config.load().folders) == 1


def test_a_relative_folder_is_refused_by_the_same_sentence_the_file_gives(
        monkeypatch, tmp_path, capsys):
    cfg_env(monkeypatch, tmp_path)
    assert cli.main(["config", "--add-folder", "Anime"]) != 0
    assert "relative path" in capsys.readouterr().err


def test_several_changes_are_applied_as_one_and_a_refusal_writes_nothing(
        monkeypatch, tmp_path, capsys):
    cfg_env(monkeypatch, tmp_path)
    cli.main(["config", "--set", "candidates=4"])
    capsys.readouterr()
    code = cli.main(["config", "--set", "candidates=9", "--set", "lang=jap"])
    assert code != 0
    assert config.load().candidates == 4          # the good half did NOT land


def test_bare_config_is_still_a_usage_error(monkeypatch, tmp_path, capsys):
    u"""⛔ The mutually-exclusive group used to enforce this with
    required=True; the write flags made that impossible, so the refusal moved
    into run(). This is what stops it being lost in the move."""
    cfg_env(monkeypatch, tmp_path)
    assert cli.main(["config"]) == 2
    assert "say what to do" in capsys.readouterr().err


def test_reading_and_writing_in_one_command_is_refused(monkeypatch, tmp_path, capsys):
    cfg_env(monkeypatch, tmp_path)
    assert cli.main(["config", "--show", "--set", "candidates=5"]) != 0
    assert "separately" in capsys.readouterr().err


def test_add_skip_round_trips_through_the_file(monkeypatch, tmp_path):
    cfg_env(monkeypatch, tmp_path)
    skip = str(tmp_path / "Anime" / "_incoming")
    assert cli.main(["config", "--add-skip", skip]) == 0
    assert [Path(f) for f in config.load().skip_folders] == [Path(skip)]


def test_the_key_can_be_set_from_stdin_without_a_file_on_disk(
        monkeypatch, tmp_path, capsys):
    u"""⭐ `--set-from FILE` would make the window write the secret to a temp
    file first -- a SECOND copy on disk. Through a pipe there is none."""
    target = tmp_path / "key.txt"
    monkeypatch.setattr("hato.paths.key_file_path", lambda: target)

    class Stdin(object):
        buffer = type("B", (), {"read": staticmethod(lambda: b"pipedkey9\n")})()

    monkeypatch.setattr(sys, "stdin", Stdin())
    assert cli.main(["key", "--set-from", "-"]) == 0
    assert credentials.read_key_file(target) == u"pipedkey9"
    assert "pipedkey9" not in capsys.readouterr().out     # only the last four
    assert list(tmp_path.glob("*.new-*")) == []
