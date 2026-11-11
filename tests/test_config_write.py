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
                                  format_fallback=True, auto_update=False,
                                  extract_embedded=True, untimed=u"same_provider",
                                  surasura_connect=u"off", favourite_groups=[u"Haruhana"],
                                  write_beside_video=False)
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


def test_a_file_written_with_saving_untouched_is_one_1_0_7_can_read(tmp_path):
    u"""The same rule for 14c's `extract_embedded`: OFF by default, and a file that
    never chose *Save them beside the video* must stay one 1.0.7 -- its tray, or a
    daily task still pointing at it -- can read. Two arms against 1.0.7's key list.
    ⭐ And *Download from jimaku anyway* is `skip_embedded`, which every hato reads:
    choosing it adds no key an old hato refuses."""
    from hato.config import _toml
    known_to_1_0_7 = {"folders", "skip_folders", "lang", "out", "subs_dir", "candidates",
                      "archives", "allow_ai", "recurse", "skip_embedded", "watch",
                      "schedule", "surasura_dir", "prefer_format", "format_fallback",
                      "auto_update", "log"}
    fresh = config.with_changes(load_from(tmp_path), folders=[str(tmp_path / "Anime")],
                                skip_embedded=False, auto_update=False)
    untouched = set(_toml.loads(config.dumps(fresh)))
    changed = set(_toml.loads(config.dumps(config.with_changes(fresh,
                                                               extract_embedded=True))))
    assert untouched <= known_to_1_0_7, untouched - known_to_1_0_7          # arm 1
    assert changed - known_to_1_0_7 == {"extract_embedded"}                 # arm 2


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


# ---------------------------------------------------------------------------
# 🚨 the file road -- what a Mac's TextEdit actually saves (a tester, 2026-11-11)
# ---------------------------------------------------------------------------

#: ⭐ TextEdit's own RTF for one pasted line, as it writes it by default. The LAST
#: line is `\f0\fs24 \cf0 <key>}` -- which 1.2.0 saved as the key and said "saved".
TEXTEDIT_RTF = (b"{\\rtf1\\ansi\\ansicpg1252\\cocoartf2822\n"
                b"\\cocoatextscaling0\\cocoaplatform0{\\fonttbl\\f0\\fswiss\\fcharset0 Helvetica;}\n"
                b"{\\colortbl;\\red255\\green255\\blue255;}\n"
                b"\\pard\\tx566\\pardirnatural\\partightenfactor0\n\n"
                b"\\f0\\fs24 \\cf0 AKfh29dkQmacKEY77}")


def test_a_textedit_rich_text_key_file_is_refused_by_name_and_saves_nothing(tmp_path):
    source, target = tmp_path / "key.rtf", tmp_path / "data" / "key.txt"
    source.write_bytes(TEXTEDIT_RTF)
    with pytest.raises(credentials.KeyMissing) as caught:
        credentials.save_key_from(source, target)
    said = str(caught.value)
    assert "isn't plain text" in said and "Make Plain Text" in said, said
    assert "AKfh29dkQmacKEY77" not in said            # ⛔ never the key
    assert not target.exists()


def test_rich_text_saved_with_a_bom_is_still_rich_text(tmp_path):
    u"""⚠ The check looks past a BOM and leading blank lines, or a file that
    starts `\\ufeff{\\rtf` would reach the line reader as text."""
    source = tmp_path / "key.rtf"
    source.write_bytes(b"\xef\xbb\xbf\r\n" + TEXTEDIT_RTF)
    with pytest.raises(credentials.KeyMissing) as caught:
        credentials.read_key_file(source)
    assert "Make Plain Text" in str(caught.value)


def test_a_utf16_key_file_is_said_to_be_not_plain_text(tmp_path):
    u"""Notepad's "Unicode" and Word documents hold NUL bytes; 1.2.0 decoded or
    errored on them with a codec's words. ⭐ Said as what to do instead."""
    # ⚠ BOTH SHAPES: with its BOM the bytes are not UTF-8 at all; WITHOUT one
    # they decode cleanly as UTF-8 with a NUL between every letter -- and that
    # one only the NUL check catches (M18K-06).
    for name, text in ((u"bom.txt", u"﻿AKfh29dkQmacKEY77\r\n"),
                       (u"nobom.txt", u"AKfh29dkQmacKEY77\r\n")):
        source = tmp_path / name
        source.write_bytes(text.encode("utf-16-le"))
        with pytest.raises(credentials.KeyMissing) as caught:
            credentials.read_key_file(source)
        said = str(caught.value)
        assert "isn't plain text" in said and "UTF-8" in said, (name, said)
        assert "AKfh29dkQmacKEY77" not in said


def test_a_plain_key_file_with_a_bom_crlf_and_a_final_newline_reads_clean(tmp_path):
    u"""The control: a plain file in every shape an editor saves still works."""
    source = tmp_path / "key.txt"
    source.write_bytes(b"\xef\xbb\xbf# my jimaku key\r\n  AKfh29dkQmacKEY77  \r\n\r\n")
    assert credentials.read_key_file(source) == u"AKfh29dkQmacKEY77"


def test_a_last_line_with_a_label_in_it_is_not_taken_as_the_key(tmp_path):
    u"""⭐ The file road gives the space refusal the paste road always gave --
    a formatted export that is not RTF cannot slip `key: …` in as the key."""
    source = tmp_path / "key.txt"
    source.write_text(u"jimaku key: AKfh29dkQmacKEY77\n", encoding="utf-8")
    with pytest.raises(credentials.KeyMissing) as caught:
        credentials.read_key_file(source)
    assert "has a space in it" in str(caught.value)
    assert "AKfh29dkQmacKEY77" not in str(caught.value)


def test_the_cli_refuses_an_rtf_file_and_says_so(monkeypatch, tmp_path, capsys):
    target = tmp_path / "data" / "key.txt"
    monkeypatch.setattr("hato.paths.key_file_path", lambda: target)
    source = tmp_path / "key.rtf"
    source.write_bytes(TEXTEDIT_RTF)
    assert cli.main(["key", "--set-from", str(source)]) == 1
    out = capsys.readouterr()
    assert "isn't plain text" in out.err and "AKfh29dkQmacKEY77" not in out.err + out.out
    assert not target.exists()


def test_a_write_that_fails_says_what_to_do_not_only_an_errno(monkeypatch, tmp_path, capsys):
    target = tmp_path / "data" / "key.txt"
    monkeypatch.setattr("hato.paths.key_file_path", lambda: target)

    def denied(*a, **kw):
        raise PermissionError(13, "Permission denied", str(target) + ".new-1")

    monkeypatch.setattr(credentials, "_write_key", denied)

    class Stdin(object):
        buffer = type("B", (), {"read": staticmethod(lambda: b"AKfh29dkQmacKEY77\n")})()

    monkeypatch.setattr(sys, "stdin", Stdin())
    assert cli.main(["key", "--set-from", "-", "--json"]) == 1
    out = capsys.readouterr().out
    assert "could not be read or written" in out and "HATO_CACHE" in out, out
    assert "AKfh29dkQmacKEY77" not in out


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


def test_going_back_writes_the_file_the_kept_version_can_read(tmp_path):
    u"""⭐ 14z (C-1/C-2) -- REAL against the published 1.0.7: it REFUSES
    `extract_embedded`, so *Go back* after *Save them beside the video* failed every
    time, or left every run refusing its settings. `config.readable_by`: every key the
    kept version never heard of leaves the file -- ⚠ one IN the file at its default too
    (refused all the same) -- *save* becomes *leave them there*, and the version that
    knows the key is left alone."""
    from hato import config
    path = tmp_path / "config.toml"
    config.save(config.with_changes(config.load(path), extract_embedded=True,
                                    skip_embedded=False), path)
    words = config.make_readable_by(u"1.0.7", path)
    text = path.read_text(encoding="utf-8")
    assert u"extract_embedded" not in text and u"skip_embedded = true" in text, text
    assert len(words) == 1 and u"Leave them there" in words[0] and u"1.0.7" in words[0], words
    assert config.make_readable_by(u"1.0.7", path) == [], u"a readable file was rewritten"
    path.write_text(text.replace(u"[log]", u"extract_embedded = false\n\n[log]"),
                    encoding="utf-8")
    assert config.make_readable_by(u"1.0.7", path) == []
    assert u"extract_embedded" not in path.read_text(encoding="utf-8"), (
        u"a hand-written key the kept version refuses was left in the file")
    config.save(config.with_changes(config.load(path), extract_embedded=True), path)
    before = path.read_bytes()
    assert config.make_readable_by(u"1.0.8", path) == [] and path.read_bytes() == before
    # ⭐ LAYER 15: 1.0.9's key is one 1.0.8 AND everything before it has never heard of.
    # ⭐ LAYER 16: and 1.1.0's, one 1.0.9 and everything before it has never heard of.
    assert config.unknown_to(u"1.0.7") == (u"extract_embedded", u"untimed",
                                           u"surasura_connect", u"favourite_groups",
                                           u"write_beside_video")
    assert config.unknown_to(u"1.0.8") == (u"untimed", u"surasura_connect",
                                           u"favourite_groups", u"write_beside_video")
    assert config.unknown_to(u"1.0.9") == (u"surasura_connect", u"favourite_groups",
                                           u"write_beside_video")
    # ⭐ LAYER 17 -- 1.1.0 has never heard of `write_beside_video`
    assert config.unknown_to(u"1.1.0") == (u"write_beside_video",)
    assert config.unknown_to(u"1.1.1") == ()
    assert set(config.unknown_to(u"1.0.2")) == set(config.NEWER_KEYS)


def test_favourite_groups_default_to_nanakoraws_and_are_written_only_once_changed(tmp_path):
    u"""⭐ 16k. Unwritten, the default is NanakoRaws (fork 3) and the file stays one 1.0.9
    can read; changed -- or EMPTIED, which is 1.0.9's order -- it is written and reads back."""
    from hato import config
    cfg = config.load(tmp_path / "config.toml")
    assert cfg.favourite_groups == (u"NanakoRaws",)
    assert u"favourite_groups" not in config.dumps(cfg)
    for names in ([u"Haruhana", u"NanakoRaws"], []):
        changed = config.with_changes(cfg, favourite_groups=names)
        assert u"\nfavourite_groups = " in config.dumps(changed)
        assert config.parse(config.dumps(changed)).favourite_groups == tuple(names)
    assert config.coerce(u"favourite_groups", u" NanakoRaws ,Haruhana,, ") == [u"NanakoRaws",
                                                                            u"Haruhana"]
    assert config.coerce(u"favourite_groups", u"") == []


@pytest.mark.parametrize("value, says", [
    (u"favourite_groups = ['[]']", u"no letters or digits"),
    (u"favourite_groups = ['-']", u"no letters or digits"),
    (u"favourite_groups = ['%s']" % (u"x" * 65), u"longer than 64"),
    (u"favourite_groups = [%s]" % u", ".join(u"'g%d'" % i for i in range(21)), u"at most 20"),
    (u"favourite_groups = 'NanakoRaws'", u"a list of release group names"),
])
def test_a_favourite_groups_line_nothing_could_match_is_refused_by_name(value, says):
    from hato import config
    with pytest.raises(config.ConfigError) as raised:
        config.parse(value)
    assert says in str(raised.value) and u"favourite_groups" in str(raised.value), str(raised.value)


def test_favourites_written_twice_or_bracketed_are_one_name_each():
    from hato import config
    cfg = config.parse(u"favourite_groups = ['[NanakoRaws]', 'Nanako-Raws', ' Haruhana ']")
    assert cfg.favourite_groups == (u"NanakoRaws", u"Haruhana")


def test_going_back_takes_the_favourites_away_and_says_so(tmp_path):
    u"""⭐ 16k -- 1.0.9 REFUSES `favourite_groups`: Go back takes it out of the file (Go
    back's map, `config._GOING_BACK`) and says what it meant."""
    from hato import config
    path = tmp_path / "config.toml"
    config.save(config.with_changes(config.load(path), favourite_groups=[u"Haruhana"]), path)
    words = config.make_readable_by(u"1.0.9", path)
    assert u"favourite_groups" not in path.read_text(encoding="utf-8")
    assert len(words) == 1 and u"Favourite release groups" in words[0] and u"1.0.9" in words[0], words
    assert config.load(path).favourite_groups == (u"NanakoRaws",)    # 1.1.0 reads the default again


def test_16n_F7_a_hand_written_default_favourite_goes_without_a_word(tmp_path):
    u"""R7: the read value is a TUPLE, the default a list -- a hand-written default read as
    changed, and Go back said *"Favourite release groups goes"* for nothing. The key still
    goes (1.0.9 refuses it whatever its value); the words do not."""
    from hato import config
    path = tmp_path / "config.toml"
    path.write_text(u'favourite_groups = ["NanakoRaws"]\n', encoding="utf-8")
    words = config.make_readable_by(u"1.0.9", path)
    assert u"favourite_groups" not in path.read_text(encoding="utf-8"), u"the key stayed for 1.0.9"
    assert words == [], words


@pytest.mark.parametrize("name", [u"Foo]Bar", u"Ab[cd", u"[Foo][Bar]", u"[[Foo]Bar]"])
def test_16z_C4_a_bracket_inside_a_favourite_is_refused_in_words(name):
    u"""Z-C4: `check_groups` took `Foo]Bar` -- which rank reads as the group [Foo] -- and
    `Ab[cd`, which matches nothing. After the outer brackets go, a bracket left INSIDE
    the name is refused, by name, on both roads."""
    from hato import config
    with pytest.raises(config.ConfigError) as raised:
        config.check_groups([name], u"favourite_groups")
    said = str(raised.value)
    assert u"bracket" in said and name in said and u"favourite_groups" in said, said
    with pytest.raises(config.ConfigError):
        config.parse(u"favourite_groups = ['%s']" % name)
    assert config.check_groups([u"[NanakoRaws]", u" [Haruhana] "], u"favourite_groups") == (
        u"NanakoRaws", u"Haruhana")                                  # the control: outer ones go


def test_both_readouts_show_every_setting_the_file_can_hold(monkeypatch, tmp_path, capsys):
    u"""🚨 The Layer 14 pass, Z14-6: the two readouts a person checks what is in force
    with each lost a DIFFERENT setting -- `--show --json` never carried
    `skip_embedded` (14a made it a choice in the window), and the plain one never
    showed `prefer_format`, `format_fallback` or `auto_update`. ⭐ Every key from
    SCHEMA, so the next one cannot be forgotten by either -- and the plain columns
    line up (a longer key pushed them once, and only LOOKING caught it)."""
    import json
    cfg_env(monkeypatch, tmp_path)
    assert cli.main(["config", "--show", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    missing = [name for name in config.SCHEMA if name not in shown]
    assert not missing, u"`hato config --show --json` leaves out %s" % missing
    assert cli.main(["config", "--show"]) == 0
    rows = [line for line in capsys.readouterr().out.splitlines()
            if line.startswith(u"  ") and u" = " in line]
    named = set(line.split(u" = ")[0].strip() for line in rows)
    missing = [name for name in config.SCHEMA if name not in named]
    assert not missing, u"`hato config --show` leaves out %s" % missing
    columns = sorted(set(line.index(u" = ") for line in rows))
    assert len(columns) == 1, u"the values do not line up: at %s" % columns


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


# ===========================================================================
# ⭐ LAYER 15 -- `untimed`, the choice for a video with no subtitle track
# ===========================================================================

def test_15_untimed_is_off_by_default_and_refuses_all_but_its_three_choices(tmp_path):
    u"""🚨 His first constraint -- NOT a default: `off` when nothing says otherwise. And a
    closed set, refused BY NAME (rule 2): a typo must never look like a choice that took."""
    assert config.parse(u"").untimed == u"off"
    for good in (u"off", u"same_provider", u"any_provider"):
        assert config.parse(u'untimed = "%s"\n' % good).untimed == good
    for bad in (u'"on"', u'"Same_Provider"', u'""', u"true", u'"any"'):
        with pytest.raises(config.ConfigError) as caught:
            config.parse(u"untimed = %s\n" % bad)
        assert u"untimed" in str(caught.value), (bad, caught.value)
    with pytest.raises(ValueError):
        pipeline.Settings(folders=[str(tmp_path)], untimed=u"on")


def test_15_the_key_is_written_only_once_chosen_so_an_older_hato_can_read_the_file(tmp_path):
    u"""⭐ An older hato REFUSES a key it never heard of, so at its default `untimed` is left
    out of the file -- and once chosen, the window says the tray must be restarted."""
    path = tmp_path / "config.toml"
    config.save(config.load(path), path)
    assert u"untimed" not in path.read_text(encoding="utf-8")
    config.save(config.with_changes(config.load(path), untimed=u"same_provider"), path)
    assert u"\nuntimed = 'same_provider'\n" in path.read_text(encoding="utf-8")
    assert u"untimed" in config.NEWER_KEYS and ((1, 0, 8), (u"untimed",)) in config.NEWER_THAN
    # ⭐ And *Skip it* -- the window writes `untimed=off` -- takes the key AWAY again: the
    # file an older tray reads is then one it can read
    config.save(config.with_changes(config.load(path), untimed=u"off"), path)
    assert u"untimed" not in path.read_text(encoding="utf-8")


def test_15_going_back_takes_the_road_away_and_says_so_first(tmp_path):
    u"""⭐ `config.readable_by` for 1.0.8 -- kept for *Go back* -- with the road chosen: the
    key leaves the file (the choice becomes *Skip it*, the only one 1.0.8 has), in the
    words of the choice that was made, and the files already placed STAY."""
    path = tmp_path / "config.toml"
    for choice, said in ((u"same_provider", u"Download one from the same provider"),
                         (u"any_provider", u"Download one that fits the episode number")):
        config.save(config.with_changes(config.load(path), untimed=choice), path)
        words = config.make_readable_by(u"1.0.8", path)
        assert u"untimed" not in path.read_text(encoding="utf-8"), choice
        assert words == [u"“%s” becomes “Skip it” — 1.0.8 cannot download a subtitle it "
                         u"cannot time. The ones already downloaded stay." % said], words
        assert config.load(path).untimed == u"off"


def test_16z_A8_go_backs_words_name_the_folder_1_0_9_copies_into(tmp_path):
    u"""⚠ 16z (Z-A8) -- Go back said *"Hand new subtitles to Surasura" goes* while 1.0.x's
    `surasura_dir` stays in the file, and 1.0.9 copies every new subtitle, flat, into its
    `Hato` folder. ⭐ The words name that folder; with none set they stay as they were."""
    from hato import config
    folder = tmp_path / "Surasura library"
    path = tmp_path / "config.toml"
    config.save(config.with_changes(config.load(path), surasura_connect=u"off",
                                    surasura_dir=str(folder)), path)
    words = config.readable_by(config.load(path), u"1.0.9")[1]
    assert len(words) == 1 and str(folder / u"Hato") in words[0], words
    assert words[0].startswith(u"“Hand new subtitles to Surasura” goes — 1.0.9"), words
    config.save(config.with_changes(config.load(path), surasura_dir=u""), path)
    words = config.readable_by(config.load(path), u"1.0.9")[1]
    assert words == [u"“Hand new subtitles to Surasura” goes — 1.0.9 has no such setting"], words


# -- LAYER 17 (H5): write_beside_video -----------------------------------------------------------

def test_17_write_beside_video_is_on_unwritten_and_set_off_through_the_json_door(
        tmp_path, monkeypatch, capsys):
    u"""⭐ H5 -- the key Surasura's hato card reads (`config --show --json`, the LAST line
    of stdout: `no_subs.hato_config`) and writes (`config --set write_beside_video=false
    --json`). On by default and NEVER WRITTEN at its default (1.1.0 refuses a key it has
    never heard of); off, written, shown with where the files go."""
    import json
    from hato import cli
    path = tmp_path / "config.toml"
    monkeypatch.setenv("HATO_CONFIG", str(path))
    assert cli.main(["config", "--show", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert shown["write_beside_video"] is True
    assert cli.main(["config", "--set", "write_beside_video=false", "--json"]) == 0
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert said["ok"] is True and said["write_beside_video"] is False, said
    assert u"write_beside_video = false" in path.read_text(encoding="utf-8")
    assert cli.main(["config", "--show"]) == 0
    text = capsys.readouterr().out
    assert u"write_beside_video" in text and u"subtitles" in text, text
    assert cli.main(["config", "--set", "write_beside_video=no", "--json"]) == 1
    assert u"true or false" in json.loads(capsys.readouterr().out.strip())["error"]
    assert cli.main(["config", "--set", "write_beside_video=true", "--json"]) == 0
    capsys.readouterr()
    assert u"write_beside_video" not in path.read_text(encoding="utf-8"), (
        u"the default was written: 1.1.0 would refuse this file")


def test_17_going_back_to_1_1_0_takes_write_beside_video_away_and_says_so(tmp_path):
    u"""⭐ 14z's rule for 1.1.1's key: Go back to 1.1.0 drops it (on, the only way 1.1.0
    writes), and says so before the press."""
    from hato import config
    path = tmp_path / "config.toml"
    config.save(config.with_changes(config.load(path), write_beside_video=False), path)
    words = config.make_readable_by(u"1.1.0", path)
    assert u"write_beside_video" not in path.read_text(encoding="utf-8")
    assert len(words) == 1 and u"beside the videos" in words[0] and u"1.1.0" in words[0], words
    assert config.make_readable_by(u"1.1.0", path) == []
