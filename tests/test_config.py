# -*- coding: utf-8 -*-
"""
config.toml -- spec/05-interface.md §The config file, RUNBOOK 0a and 5b.

Structurally cannot cover: whether the CLI, hato-run.cmd and the scheduled run
all READ it identically in their real environments -- that is RUNBOOK 5c.
"""
import os
from pathlib import Path

import pytest

from hato import config, paths


def write(tmp_path, text, name="config.toml"):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


def test_a_missing_file_is_the_documented_defaults(tmp_path):
    cfg = config.load(tmp_path / "absent.toml")
    assert cfg.file_exists is False
    got = {name: getattr(cfg, name) for name in config.SCHEMA}
    # ⚠ EVERY list key is stored as a TUPLE, not just `folders`. Written as one
    # hard-coded line it broke the moment `skip_folders` was added (2026-09-18)
    # -- a check failing on the REPRESENTATION of a new key says nothing about
    # the defaults it exists to pin.
    want = {name: (tuple(default) if kind is list else default)
            for name, (kind, default) in config.SCHEMA.items()}
    assert got == want
    assert (cfg.log_path, cfg.log_keep) == ("", 10)
    assert all(cfg.origin(n) == "default" for n in config.SCHEMA)


def test_the_defaults_resolve_under_the_per_user_root(tmp_path):
    cfg = config.load(tmp_path / "absent.toml")
    assert cfg.subs_dir_resolved == paths.default_subs_dir()
    assert cfg.log_path_resolved == paths.default_log_path()
    assert str(cfg.subs_dir_resolved).startswith(os.environ["HATO_TEST_ROOT"])


def test_a_full_file_is_read_and_each_value_says_it_came_from_the_file(tmp_path):
    folder = str(tmp_path / "Anime")
    p = write(tmp_path, u'''
folders    = ["%s"]
lang       = "ja"
out        = "%s"
subs_dir   = "%s"
candidates = 5
archives   = false
allow_ai   = true
recurse    = false

[log]
path = "%s"
keep = 3
''' % tuple(s.replace("\\", "/") for s in (
        folder, str(tmp_path / "Out"), str(tmp_path / "Subs"), str(tmp_path / "hato.log"))))
    cfg = config.load(p)
    assert cfg.file_exists
    assert [Path(f) for f in cfg.folders] == [Path(folder)]
    assert (cfg.candidates, cfg.archives, cfg.allow_ai, cfg.recurse) == (5, False, True, False)
    assert Path(cfg.subs_dir) == tmp_path / "Subs"
    assert cfg.log_keep == 3
    assert cfg.origin("candidates") == "config.toml"
    assert cfg.origin("log.keep") == "config.toml"


def test_HATO_CONFIG_is_honoured(tmp_path, monkeypatch):
    p = write(tmp_path, 'candidates = 7\n', "custom.toml")
    monkeypatch.setenv("HATO_CONFIG", str(p))
    cfg = config.load()
    assert cfg.candidates == 7
    assert (cfg.path, cfg.path_source) == (p, "HATO_CONFIG")


def test_an_unknown_key_is_refused_by_name(tmp_path):
    p = write(tmp_path, 'candiates = 5\n')
    with pytest.raises(config.ConfigError) as err:
        config.load(p)
    assert "candiates" in str(err.value) and "candidates" in str(err.value)


@pytest.mark.parametrize("text, name", [
    ('key = "abc123"\n', "key"),
    ('api_key = "abc123"\n', "api_key"),
    ('[log]\ntoken = "abc123"\n', "token"),
    # 🚨 THE TWO A NAMED LIST COULD NOT KNOW, measured 2026-09-17: both fell
    # through to a generic *"unknown key"*, which never says the one thing a
    # person putting the key in this file needs to hear.
    ('jimaku_api_key = "abc123"\n', "jimaku_api_key"),
    ('[jimaku]\napi_key = "abc123"\n', "api_key"),
    ('[jimaku]\ntoken = "abc123"\n', "token"),
    ('jimaku_credentials = "abc123"\n', "jimaku_credentials"),
])
def test_a_key_shaped_field_is_refused_with_the_reason(tmp_path, text, name):
    p = write(tmp_path, text)
    with pytest.raises(config.ConfigError) as err:
        config.load(p)
    msg = str(err.value)
    assert name in msg and "NEVER in config.toml" in msg
    assert "abc123" not in msg, "the refusal must not echo the secret back"


def test_no_documented_setting_is_mistaken_for_a_secret(tmp_path):
    u"""⚠ THE COST OF WIDENING THE SECRET TEST FROM A LIST TO A SHAPE. A field
    the schema documents must never be refused as key-shaped -- `log.keep` is
    three letters away from `key`, and refusing it would make the documented
    config unloadable."""
    for name in list(config.SCHEMA) + ["log"] + ["log." + n for n in config.LOG_SCHEMA]:
        leaf = name.split(".")[-1]
        assert not config._looks_secret(leaf), name
    # ...and the whole documented file still loads.
    p = write(tmp_path, u'lang = "ja"\ncandidates = 3\narchives = true\n'
                        u'allow_ai = false\nrecurse = true\n\n[log]\nkeep = 10\n')
    assert config.load(p).log_keep == 10


@pytest.mark.parametrize("text, name", [
    ('candidates = true\n', "candidates"),
    ('candidates = "3"\n', "candidates"),
    ('archives = "yes"\n', "archives"),
    ('folders = "D:/Anime"\n', "folders"),
    ('lang = 1\n', "lang"),
    ('[log]\nkeep = "10"\n', "log.keep"),
])
def test_a_wrong_type_is_refused_by_name(tmp_path, text, name):
    p = write(tmp_path, text)
    with pytest.raises(config.ConfigError) as err:
        config.load(p)
    assert name in str(err.value)


@pytest.mark.parametrize("text, name", [
    ('folders = ["Anime"]\n', "folders"),
    ('out = "Subs"\n', "out"),
    ('subs_dir = "kept"\n', "subs_dir"),
    ('[log]\npath = "hato.log"\n', "log.path"),
])
def test_a_relative_path_is_refused_because_the_scheduler_starts_elsewhere(tmp_path, text, name):
    p = write(tmp_path, text)
    with pytest.raises(config.ConfigError) as err:
        config.load(p)
    assert name in str(err.value) and "absolute" in str(err.value)


@pytest.mark.parametrize("lang", ["jap", "ja-JP", "japanese", ""])
def test_a_bad_language_code_is_refused(tmp_path, lang):
    p = write(tmp_path, 'lang = "%s"\n' % lang)
    with pytest.raises(config.ConfigError):
        config.load(p)


def test_the_language_code_is_normalised_to_lower_case(tmp_path):
    assert config.load(write(tmp_path, 'lang = "JA"\n')).lang == "ja"


@pytest.mark.parametrize("text", ['candidates = 0\n', '[log]\nkeep = 0\n'])
def test_counts_below_one_are_refused(tmp_path, text):
    with pytest.raises(config.ConfigError):
        config.load(write(tmp_path, text))


@pytest.mark.parametrize("text, value", [('candidates = 0\n', 0),
                                         ('candidates = -1\n', -1)])
def test_the_candidates_refusal_says_what_it_costs(tmp_path, text, value):
    u"""🚨 The sentence, not just the exception -- because `hato/commands/run.py`
    prints THIS ONE for `--candidates 0` too, and a run that tries nothing still
    writes the negative that takes the folder out for a day."""
    with pytest.raises(config.ConfigError) as err:
        config.load(write(tmp_path, text))
    msg = str(err.value)
    assert "candidates" in msg and "at least 1" in msg and repr(value)[:2] in msg
    assert "skips the folder for a day" in msg, msg
    assert msg.endswith(config.candidates_refusal("candidates", value)
                        .split("must be at least 1, ")[-1])


def test_a_notepad_BOM_does_not_break_the_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes(b"\xef\xbb\xbf" + b"candidates = 4\n")
    assert config.load(p).candidates == 4


def test_invalid_toml_says_so(tmp_path):
    with pytest.raises(config.ConfigError) as err:
        config.load(write(tmp_path, 'candidates = = 3\n'))
    assert "TOML" in str(err.value)
