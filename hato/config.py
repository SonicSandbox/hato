# -*- coding: utf-8 -*-
"""
config.toml -- ONE config, read identically by the CLI, hato-run.cmd and the
scheduled run (spec/05-interface.md §The config file).

    cfg = load()              # documented defaults when the file is missing
    cfg.lang, cfg.candidates, cfg.subs_dir, ...
    cfg.origin("lang")        # "default" or "config.toml"

Rules, each a check in tests/test_config.py:

- ⭐ A MISSING FILE IS THE DOCUMENTED DEFAULTS, never a crash.
- ⛔ AN UNKNOWN KEY IS REFUSED LOUDLY. Silently ignoring `candiates = 5` makes the
  user believe they changed something (doctrine/robustness: refuse loudly, never
  drop silently).
- 🚨 A KEY-SHAPED FIELD IS REFUSED WITH THE REASON. The API key is never in this
  file (LEDGER.md §data) -- it is read from the keystore or $HATO_JIMAKU_KEY.
- ⛔ A RELATIVE PATH IS REFUSED. A scheduled run starts in an unexpected working
  directory (spec/10-deployment.md), so `folders = ["Anime"]` would scan a
  different place from a terminal run.
- ⚠ `true` IS NOT A NUMBER. Python's bool is an int, so `candidates = true` would
  otherwise read as 1.

⚠ `subs_dir` inside a scanned folder is ALSO an error, but it can only be decided
once the run knows its folders (the CLI may add some) -- that check lives with
the run, not here (spec/03-permissions.md §Whitelist 1).
"""
import os
import re
import sys
from pathlib import Path

from hato import paths

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:  # this laptop is 3.10 (spec/01-scope.md §The ratified stack)
    import tomli as _toml


class ConfigError(Exception):
    """config.toml is present and wrong. The message names the key and the fix."""


#: key -> (type, default). The documented schema, spec/05-interface.md.
SCHEMA = {
    "folders": (list, []),
    # ⭐ RUNBOOK 7e. Sonic: *"someone might say 'desktop' and then not want a
    # certain folder checked on desktop."* An exclusion is not the same shape as
    # a blacklisted video -- a video is one content hash, a folder is a subtree
    # of a watched root -- so it is its own list, carved out of `folders`.
    # ⛔ IT IS HONOURED BY THE RUN, not merely stored: `pipeline` drops every
    # video found underneath one. A setting the run ignores is the documented
    # failure *"offered Sonic a setting that did nothing"* (HANDOFF.md §7).
    "skip_folders": (list, []),
    "lang": (str, "ja"),
    "out": (str, ""),
    "subs_dir": (str, ""),
    "candidates": (int, 3),
    "archives": (bool, False),
    "allow_ai": (bool, False),
    "recurse": (bool, True),
    # ⭐ RULED 2026-09-17 (Sonic). TRUE: a video whose own container already holds a
    # Japanese text track is skipped for free -- nothing fetched, nothing asked.
    # FALSE: fetch one anyway, because an embedded track can be a poor one (an SDH
    # rip, a broadcast burn-in) and a fansub .ass may be wanted instead. ⚠ Turning
    # it off is not wasteful: the embedded track becomes the reference the download
    # is timed against, which is the strongest reference there is.
    "skip_embedded": (bool, True),
    # 🚨 ADDED 2026-09-18, AND IT WAS BEING WRITTEN BEFORE IT EXISTED. The
    # window's "Watch for new videos and run" tick sent
    # `hato config --set watch=true`, the schema refused it by name, and the
    # window never reads a child's exit code -- so the box ticked, nothing was
    # saved, and nothing said so. ⛔ *"Offered Sonic a setting that did
    # nothing"* (HANDOFF.md §7), twice over: it did not persist AND it started
    # no watcher.
    # ⚠ OFF BY DEFAULT, ruled: watching needs something resident, and with it
    # off nothing of hato is in memory between runs.
    "watch": (bool, False),
    # 🚨 THE SAME DEFECT AS `watch`, FOUND ONLY BY GOING TO WRITE THE CHECK.
    # The window's time field sent `--set schedule=03:00`, the schema refused
    # it by name, and nothing surfaced the refusal -- so the schedule time has
    # never once saved. ⭐ Three settings were silently inert; two of them
    # nobody had reported.
    # ⚠ THIS IS THE TIME AND NOTHING MORE (D2, 2026-09-23). Whether the daily
    # run is ON is Task Scheduler's to say -- `hato/schedule.py` registers the
    # task and the switch reads it back. ⛔ Never a key saying "on": it would be
    # a second answer, and the switch read ON for days over no task at all.
    "schedule": (str, "03:00"),
    # ⭐ THE surasura INTEGRATION (RUNBOOK 7h). A copy of every subtitle hato
    # successfully aligns is dropped into `<this>/Hato/`, for
    # github.com/SonicSandbox/surasura to pick up.
    # ⚠ OFF BY DEFAULT and empty means off -- most people do not run surasura,
    # and a setting that quietly writes files somewhere new is not one to
    # assume. ⛔ A COPY, never a move: the file beside the video is the one the
    # player loads and hato's own output stays exactly where tsubasa put it.
    "surasura_dir": (str, ""),
}

#: ⚠ `schedule` is HH:MM, 24-hour. A free string here would be written happily
#: and refused later by whatever registers the task -- somewhere the person is
#: not looking.
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def is_clock(value):
    u"""-> True when `value` is a time `schedule` accepts. ⭐ The ONE test: the
    config's own check, the window's time field and `schedule.enable` all ask
    this, so none of them can accept what another refuses."""
    return isinstance(value, str) and bool(_CLOCK.match(value))


LOG_SCHEMA = {
    "path": (str, ""),
    "keep": (int, 10),
}

#: Field names that can only mean somebody is about to put a secret here.
SECRET_SHAPED = {"key", "api_key", "apikey", "jimaku_key", "token", "api_token",
                 "authorization", "auth", "secret", "password"}
#: ⭐ AND THE SHAPES THEY COME IN. `SECRET_SHAPED` is an exact list, and an exact
#: list cannot know `jimaku_api_key` or `[jimaku] api_key` -- both of which fell
#: through to a generic *"unknown key"* that never said the one thing a person
#: putting a key in this file needs to hear (measured 2026-09-17).
#: ⚠ Checked against every schema name by a test: none of `folders`, `lang`,
#: `out`, `subs_dir`, `candidates`, `archives`, `allow_ai`, `recurse`, `path` or
#: `keep` contains any of these.
SECRET_WORDS = ("key", "token", "secret", "password", "auth", "credential")

_TYPE_WORD = {list: "a list of folder paths", str: "a string",
              int: "a whole number", bool: "true or false"}


def _type_ok(value, want):
    if want is int:
        return type(value) is int          # ⚠ bool is a subclass of int
    if want is list:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, want)


# ---------------------------------------------------------------------------
# ⭐ THE REFUSALS, IN ONE PLACE -- BECAUSE THERE ARE TWO ROADS TO EACH
# ---------------------------------------------------------------------------
# `config.toml` is one road into a run's settings and the CLI's flags are the
# other, and `05-interface.md` gives them the same meanings. Every sentence
# below was a sentence config.toml said and the flag did not, so a value the
# file refused by name was accepted from the command line and did the damage the
# file's refusal exists to prevent (`LEDGER.md` §interface, 2026-09-17).
# ⛔ Never a second copy of the words: `hato/commands/run.py` calls these.

def relative_path_refusal(where, raw):
    """⛔ A relative path, on either road. `where` names the setting or flag."""
    return ("%s = %r is a relative path. It must be absolute: a scheduled run "
            "starts in an unexpected working directory, so a relative path "
            "would point somewhere different from a terminal run." % (where, raw))


def candidates_refusal(where, value):
    """⛔ Fewer than one candidate, on either road.

    🚨 The measured damage, and why the sentence says it: `--candidates 0` tried
    nothing, wrote the soft negative that records *it asked*, and the corrected
    run an hour later reported *"asked for recently and not there yet"* and made
    zero API calls. One mistyped digit took the folder out for a day.
    """
    return ("%s must be at least 1, got %d. A run that may try no candidate at "
            "all still writes down that it asked, so the next run skips the "
            "folder for a day without making a single request." % (where, value))


def check_lang(value, where):
    """A language tag both roads must refuse alike. -> the tag, lower-cased.

    ⛔ `ja-JP` is correct BCP 47 and broken on Jellyfin (`05-interface.md`), and
    it was refused here and waved through by `--lang` until 2026-09-17.
    ⚠ This is the NAMING rule only. Whether tsubasa's reader can resolve the tag
    is `hato/present.py`'s answer and nobody else's; the CLI asks both.
    """
    lang = value if isinstance(value, str) else ""
    if lang.lower() == "jap":
        raise ConfigError("%s = 'jap' is not a language code and never was. "
                          "Use 'ja'." % where)
    if not (2 <= len(lang) <= 3 and lang.isascii() and lang.isalpha()):
        raise ConfigError(
            "%s = %r must be a 2- or 3-letter code such as 'ja'. ⚠ Not 'ja-JP' "
            "-- that is broken on Jellyfin (spec/05-interface.md)." % (where, lang))
    return lang.lower()


def _absolute(raw, where):
    """'' stays '' (meaning: the default). Anything else must be absolute."""
    if raw == "":
        return ""
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        raise ConfigError(relative_path_refusal(where, raw))
    return str(p)


class Config(object):
    """The resolved config. Read-only by convention; build a new one to change it."""

    __slots__ = ("folders", "skip_folders", "lang", "out", "subs_dir",
                 "candidates", "archives", "allow_ai", "recurse", "skip_embedded",
                 "watch", "schedule", "surasura_dir", "log_path", "log_keep",
                 "path", "path_source", "file_exists", "_set")

    def origin(self, name):
        """'config.toml' when the file set it, else 'default'."""
        return "config.toml" if name in self._set else "default"

    @property
    def subs_dir_resolved(self):
        """subs_dir, with the empty-means-default rule applied. -> Path"""
        return Path(self.subs_dir) if self.subs_dir else paths.default_subs_dir()

    @property
    def log_path_resolved(self):
        return Path(self.log_path) if self.log_path else paths.default_log_path()

    def as_dict(self):
        return {
            "config": str(self.path), "config_source": self.path_source,
            "config_exists": self.file_exists,
            "folders": list(self.folders), "skip_folders": list(self.skip_folders),
            "lang": self.lang, "out": self.out,
            "subs_dir": self.subs_dir, "subs_dir_resolved": str(self.subs_dir_resolved),
            "candidates": self.candidates, "archives": self.archives,
            "allow_ai": self.allow_ai, "recurse": self.recurse,
            "watch": self.watch, "schedule": self.schedule,
            "surasura_dir": self.surasura_dir,
            "log": {"path": self.log_path, "path_resolved": str(self.log_path_resolved),
                    "keep": self.log_keep},
            "data_root": str(paths.data_root()),
            "data_root_source": paths.data_root_source(),
            "set_in_file": sorted(self._set),
        }


def _looks_secret(leaf):
    """Is this field name a place somebody would put the key? -> bool

    ⚠ The exact list FIRST, then the shapes -- `jimaku_api_key` is in neither an
    exact list nor any schema, and *"unknown key"* is the wrong answer to it.
    """
    low = leaf.lower()
    return low in SECRET_SHAPED or any(word in low for word in SECRET_WORDS)


def _refuse_secret(name, where, leaf=None):
    if _looks_secret(leaf if leaf is not None else name):
        raise ConfigError(
            "%s: %r looks like a place for the API key. The key is NEVER in "
            "config.toml -- it is read from the keystore file or "
            "$HATO_JIMAKU_KEY, so it cannot be synced, shared or committed "
            "with the config. Remove this line." % (where, name))


def parse(text, path=None):
    """TOML text -> Config. Raises ConfigError naming the key and the fix."""
    where = str(path) if path else "config.toml"
    try:
        raw = _toml.loads(text)
    except _toml.TOMLDecodeError as exc:
        raise ConfigError("%s is not valid TOML: %s" % (where, exc))

    values = {k: d for k, (_, d) in SCHEMA.items()}
    log_values = {k: d for k, (_, d) in LOG_SCHEMA.items()}
    set_names = set()

    for name, value in raw.items():
        _refuse_secret(name, where)
        if isinstance(value, dict):
            # 🚨 A TABLE'S CONTENTS ARE READ BEFORE THE TABLE ITSELF IS REFUSED.
            # `[jimaku]\napi_key = "..."` is somebody putting the key in this
            # file, and *"unknown key 'jimaku'"* -- which is what this said until
            # 2026-09-17 -- never tells them why that is the one thing that may
            # never be here.
            for lname in value:
                _refuse_secret("%s.%s" % (name, lname), where, leaf=lname)
        if name == "log":
            if not isinstance(value, dict):
                raise ConfigError("%s: [log] must be a table, got %r" % (where, value))
            for lname, lvalue in value.items():
                _refuse_secret(lname, where)
                if lname not in LOG_SCHEMA:
                    raise ConfigError(
                        "%s: unknown key log.%s. Known: %s" % (
                            where, lname, ", ".join(sorted(LOG_SCHEMA))))
                want = LOG_SCHEMA[lname][0]
                if not _type_ok(lvalue, want):
                    raise ConfigError("%s: log.%s must be %s, got %r" % (
                        where, lname, _TYPE_WORD[want], lvalue))
                log_values[lname] = lvalue
                set_names.add("log." + lname)
            continue
        if name not in SCHEMA:
            raise ConfigError(
                "%s: unknown key %r. Known: %s, [log]. (An unknown key is "
                "refused rather than ignored, so a typo cannot look like a "
                "setting that took.)" % (where, name, ", ".join(sorted(SCHEMA))))
        want = SCHEMA[name][0]
        if not _type_ok(value, want):
            raise ConfigError("%s: %s must be %s, got %r" % (
                where, name, _TYPE_WORD[want], value))
        values[name] = value
        set_names.add(name)

    if values["candidates"] < 1:
        raise ConfigError(candidates_refusal("%s: candidates" % where,
                                             values["candidates"]))
    if log_values["keep"] < 1:
        raise ConfigError("%s: log.keep must be at least 1, got %d" % (
            where, log_values["keep"]))
    lang = check_lang(values["lang"], "%s: lang" % where)

    cfg = Config()
    cfg.folders = tuple(_absolute(f, "folders") for f in values["folders"])
    if any(f == "" for f in cfg.folders):
        raise ConfigError("%s: folders contains an empty entry" % where)
    cfg.skip_folders = tuple(_absolute(f, "skip_folders")
                             for f in values["skip_folders"])
    if any(f == "" for f in cfg.skip_folders):
        raise ConfigError("%s: skip_folders contains an empty entry" % where)
    cfg.lang = lang                        # ⚠ `check_lang` already lower-cased it
    cfg.out = _absolute(values["out"], "out")
    cfg.subs_dir = _absolute(values["subs_dir"], "subs_dir")
    cfg.surasura_dir = _absolute(values["surasura_dir"], "surasura_dir")
    cfg.candidates = values["candidates"]
    cfg.archives = values["archives"]
    cfg.allow_ai = values["allow_ai"]
    cfg.recurse = values["recurse"]
    cfg.skip_embedded = values["skip_embedded"]
    cfg.watch = values["watch"]
    schedule = values["schedule"]
    if not is_clock(schedule):
        raise ConfigError(
            "%s: schedule = %r must be a 24-hour time such as '03:00'. A value "
            "whatever registers the run cannot read would be accepted here and "
            "refused somewhere nobody is looking." % (where, schedule))
    cfg.schedule = schedule
    cfg.log_path = _absolute(log_values["path"], "log.path")
    cfg.log_keep = log_values["keep"]
    cfg._set = frozenset(set_names)
    cfg.path = Path(path) if path else None
    cfg.path_source = None
    cfg.file_exists = False
    return cfg


def load(path=None):
    """-> Config from `path`, else HATO_CONFIG, else the documented location.

    ⭐ Missing file -> documented defaults. Present and wrong -> ConfigError.
    """
    if path is None:
        path, source = paths.config_path()
    else:
        path, source = Path(path), "argument"
    if path.is_file():
        try:
            with open(str(path), encoding="utf-8-sig") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigError("%s could not be read: %s" % (path, exc))
        cfg = parse(text, path)
        cfg.file_exists = True
    else:
        cfg = parse("", path)
        cfg.file_exists = False
    cfg.path = path
    cfg.path_source = source
    return cfg


# ---------------------------------------------------------------------------
# ⭐ THE WRITER (RUNBOOK 7a) -- ONE WRITER, ONE SCHEMA, ONE VALIDATOR
# ---------------------------------------------------------------------------
# 🚨 A PART 1 DEFECT, AND IT HAD BEEN MARKED "VERIFIED". spec/05-interface.md
# §The window rules a Settings tab that edits the watched folders, the skipped
# folders, the schedule and the key -- and `hato config` was READ-ONLY, with no
# `save`, `write` or `dump` anywhere in this module. Two-thirds of that tab had
# no mechanism behind it. Caught by an adversarial pass (HANDOFF.md §4d).
#
# ⛔ THE WINDOW DOES NOT EDIT config.toml ITSELF. Everything above owns a CLOSED
# schema: unknown keys refused by name, relative paths refused, key-shaped
# fields refused. A second writer means two programs disagreeing about one file
# -- the class LEDGER.md §data records as "two roads into one setting", and the
# one this project was already bitten by when `--candidates` accepted a value
# `config.toml` refused.
#
# ⭐ SO THE WRITE ROUND-TRIPS THROUGH parse() BEFORE A BYTE IS WRITTEN. It is not
# that the writer is careful to agree with the reader; it is that nothing can be
# written which the reader would refuse. One validator, so they cannot drift.
#
# ⚠ COMMENTS ARE NOT PRESERVED, and the header says so in the file itself. TOML
# round-tripping needs a library (tomlkit, absent here) and a new hard dependency
# needs a licence check (spec/01-scope.md) -- disproportionate for a closed
# schema of four scalar types. The honest move is to say it where somebody
# editing the file will read it, not to lose it quietly.

#: What a written config.toml opens with. The sentence about comments is a
#: promise being kept, not decoration -- see the note above.
_WRITTEN_HEADER = u"""\
# hato's settings. Written by hato -- `hato config --show` reads it back.
#
# You may edit this by hand. WARNING: hato REWRITES this file whenever a setting
# is changed from the window or from `hato config --set`, and a rewrite does not
# preserve comments or ordering. Anything you add here may be lost the next time
# a setting changes.
#
# The jimaku API key is NEVER in this file. hato refuses to read one here.
# It lives in hato's own folder -- `hato key --set-from <file>`.
"""


def _toml_string(value):
    u"""One TOML string. -> unicode

    LITERAL STRINGS ('...') BY DEFAULT. Every path this schema holds is a
    Windows path, and in a TOML *basic* string a backslash opens an escape: a
    folder under `...\\newanime` carries `\\n` and one under `...\\Utils` carries
    `\\U`, which TOML reads as a unicode escape and rejects outright. A literal
    string has no escapes at all, so a path goes in exactly as it came.

    ⚠ THIS IS A SIMPLIFICATION, NOT THE GUARD -- corrected 2026-09-18 after a
    mutant SURVIVED. An earlier version of this docstring called it "a
    correctness fix rather than a style", and that was false: the fallback
    below escapes backslashes properly, so forcing every string through it is
    also correct. What the literal branch buys is that the common case has no
    escaping to get wrong, which is worth having and is not what was claimed.
    🚨 THE REAL GUARD IS THE ESCAPING ON THE FALLBACK PATH, and it is reached by
    any path containing an apostrophe -- `D:\\Bob's Anime`. Un-escaped, that is
    where a Windows path really does corrupt. Mutant M7a-01 aims there now.

    ⚠ A literal string cannot hold a single quote or a newline, so those fall
    back to a basic string with everything escaped. A folder name may legally
    contain an apostrophe.
    """
    if u"'" not in value and u"\n" not in value and u"\r" not in value:
        return u"'" + value + u"'"
    out = value.replace(u"\\", u"\\\\").replace(u'"', u'\\"')
    out = out.replace(u"\n", u"\\n").replace(u"\r", u"\\r").replace(u"\t", u"\\t")
    return u'"' + out + u'"'


def _toml_value(value):
    u"""One TOML value of a type this schema uses. -> unicode

    ⚠ `bool` BEFORE `int`, ALWAYS. Python's bool is a subclass of int, so an
    `isinstance(value, int)` reached first turns `archives = true` into
    `archives = 1` -- which parse() then refuses as "must be true or false".
    save()'s round-trip would catch it; this is what stops it happening.
    """
    if isinstance(value, bool):
        return u"true" if value else u"false"
    if isinstance(value, int):
        return u"%d" % value
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return u"[]"
        inner = u",\n".join(u"    " + _toml_string(v) for v in value)
        return u"[\n" + inner + u",\n]"
    raise ConfigError("cannot write %r into config.toml: hato's schema holds "
                      "only lists of strings, strings, whole numbers and "
                      "true/false." % (value,))


#: Every SCHEMA key, as read off a Config. ⛔ Not a second list of names: it is
#: checked against SCHEMA on every write, so a key added to the schema and
#: forgotten here RAISES rather than vanishing from every file hato writes.
def _writable(cfg):
    return {
        "folders": list(cfg.folders),
        "skip_folders": list(cfg.skip_folders),
        "lang": cfg.lang,
        "out": cfg.out,
        "subs_dir": cfg.subs_dir,
        "candidates": cfg.candidates,
        "archives": cfg.archives,
        "allow_ai": cfg.allow_ai,
        "recurse": cfg.recurse,
        "skip_embedded": cfg.skip_embedded,
        "watch": cfg.watch,
        "schedule": cfg.schedule,
        "surasura_dir": cfg.surasura_dir,
    }


def dumps(cfg):
    u"""A Config -> the TOML text of a config.toml that reads back as it.

    ⭐ EVERY SCHEMA KEY IS WRITTEN, not only the changed ones. A file showing
    every setting is a file a person can read to learn what is in force -- the
    same argument `hato config --show` already makes -- and it means a default
    that CHANGES between versions cannot silently change an existing install.
    """
    values = _writable(cfg)
    missing = set(SCHEMA) - set(values)
    if missing:
        raise ConfigError(
            "hato cannot write config.toml: the schema has %s and the writer "
            "does not. That is a bug in hato/config.py -- _writable() must "
            "carry every key in SCHEMA." % ", ".join(sorted(missing)))
    out = [_WRITTEN_HEADER]
    for name in SCHEMA:
        out.append(u"%s = %s" % (name, _toml_value(values[name])))
    out.append(u"")
    out.append(u"[log]")
    for name, value in ((u"path", cfg.log_path), (u"keep", cfg.log_keep)):
        out.append(u"%s = %s" % (name, _toml_value(value)))
    return u"\n".join(out) + u"\n"


def save(cfg, path=None):
    u"""Write `cfg` to `path` (else its own). -> Path

    🚨 TEMP-PLUS-RENAME, NEVER `open(path, 'w')`. LEDGER-HOT.md: the truncate
    happens when the file is OPENED, so a raise afterwards leaves zero bytes.
    That destroyed tsubasa/spec/RUNBOOK.md on 2026-09-07, and a config.toml
    zeroed this way would quietly take every watched folder out of every run.

    ⭐ AND THE TEXT IS PARSED BACK BEFORE IT IS WRITTEN. Not defensiveness: it is
    what makes "one writer, one schema, one validator" true rather than
    intended. Anything parse() would refuse is refused here first, in the same
    sentence, so a written file hato cannot load is unreachable.
    """
    target = Path(path) if path is not None else cfg.path
    if target is None:
        raise ConfigError("no path to write the config to")
    text = dumps(cfg)
    parse(text, target)                    # ⛔ the gate. Raises before any write.
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".new-%d" % os.getpid())
    try:
        with open(str(temp), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(str(temp), str(target))
    finally:
        if temp.exists():
            try:
                temp.unlink()              # a failed write leaves NOTHING behind
            except OSError:
                pass
    return target


def coerce(name, raw):
    u"""`--set name=raw` -> a value of the schema's type for `name`.

    ⚠ STRICT ON BOOLEANS, DELIBERATELY. `archives=yes` and `archives=1` are
    refused rather than guessed, because a guess that reads `0` as false and
    `no` as TRUE (a non-empty string) is exactly the shape of a setting somebody
    believes they turned off.
    """
    if name not in SCHEMA:
        raise ConfigError(
            "unknown setting %r. Known: %s. (The folder lists are edited with "
            "--add-folder / --remove-folder and --add-skip / --remove-skip.)"
            % (name, ", ".join(sorted(SCHEMA))))
    want = SCHEMA[name][0]
    if want is list:
        which = "skip" if name == "skip_folders" else "folder"
        raise ConfigError(
            "%s is a list of folders, so --set cannot express it. Use "
            "--add-%s / --remove-%s, one folder at a time." % (name, which, which))
    if want is bool:
        low = raw.strip().lower()
        if low in ("true", "false"):
            return low == "true"
        raise ConfigError("%s must be true or false, got %r. (Only those two "
                          "words -- 'yes', 'on' and '1' are refused rather than "
                          "guessed at.)" % (name, raw))
    if want is int:
        try:
            return int(raw.strip(), 10)
        except ValueError:
            raise ConfigError("%s must be a whole number, got %r" % (name, raw))
    return raw


def with_changes(cfg, **changes):
    u"""A NEW Config, `cfg` plus `changes`, validated. -> Config

    ⛔ The existing Config is never mutated: it is what the file says, and a
    refused change must leave the caller holding the truth rather than a
    half-applied object.

    ⭐ THE SAME GATE AS save(). dumps() + parse() is the only validator, so a
    change that would be refused on write is refused HERE -- while the caller
    can still name which setting and why, rather than at the last moment.
    """
    values = _writable(cfg)
    log_values = {"path": cfg.log_path, "keep": cfg.log_keep}
    for name, value in changes.items():
        if name.startswith("log."):
            log_values[name[4:]] = value
        elif name in values:
            values[name] = value
        else:
            raise ConfigError(
                "unknown setting %r. Known: %s, log.path, log.keep."
                % (name, ", ".join(sorted(SCHEMA))))
    scratch = Config()
    for name, value in values.items():
        setattr(scratch, name, value)
    scratch.folders = tuple(values["folders"])
    scratch.skip_folders = tuple(values["skip_folders"])
    scratch.log_path = log_values["path"]
    scratch.log_keep = log_values["keep"]
    scratch._set = cfg._set
    fresh = parse(dumps(scratch), cfg.path)
    fresh.path = cfg.path
    fresh.path_source = cfg.path_source
    fresh.file_exists = cfg.file_exists
    return fresh
