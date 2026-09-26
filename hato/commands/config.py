# -*- coding: utf-8 -*-
"""Show the resolved config, or check that the jimaku key resolves.

    hato config --show [--json]      every value, and where it came from
    hato config --check-key [--json] found or MISSING, and from where

⛔ --check-key prints the key's LAST FOUR CHARACTERS and nothing more
(LEDGER-HOT.md). The Key object cannot print more even if asked to.
"""
import json
import os
import sys
from pathlib import Path

from hato import config as _config
from hato import credentials, paths

EXIT_OK = 0
EXIT_FAILED = 1


def register(parser):
    # ⚠ NOT `required=True` ANY MORE, and bare `hato config` is STILL a usage
    # error -- `run()` ends with one. The group had to open up so the write
    # flags below can be combined and repeated in a single atomic write; the
    # refusal moved, it did not go away, and a check pins it.
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--show", action="store_true",
                      help="print the resolved config and where each value came from")
    what.add_argument("--check-key", action="store_true",
                      help="say whether the jimaku key resolves, and from where")
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    # ⭐ THE WRITE SIDE (RUNBOOK 7a). Every flag here is REPEATABLE and they
    # COMBINE, because the window's Settings tab can change several things at
    # once and a per-change write would leave the file half-applied if the
    # second one were refused. One Config, validated once, written once.
    write = parser.add_argument_group(
        "changing a setting",
        "Each of these edits config.toml. They can be combined and repeated, "
        "and are applied as ONE change: if any is refused, nothing is written.")
    write.add_argument("--set", metavar="KEY=VALUE", action="append", default=[],
                       dest="set_pairs",
                       help="set one setting, e.g. --set candidates=5")
    write.add_argument("--add-folder", metavar="DIR", action="append", default=[],
                       help="watch this folder (absolute path)")
    write.add_argument("--remove-folder", metavar="DIR", action="append", default=[],
                       help="stop watching this folder")
    write.add_argument("--add-skip", metavar="DIR", action="append", default=[],
                       help="never look inside this folder, even under a watched one")
    write.add_argument("--remove-skip", metavar="DIR", action="append", default=[],
                       help="stop skipping this folder")


def _show(args):
    try:
        cfg = _config.load()
    except (_config.ConfigError, paths.PathError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("hato: config is wrong -- %s\n" % exc)
        return EXIT_FAILED
    d = cfg.as_dict()
    if args.json:
        d["ok"] = True
        print(json.dumps(d, ensure_ascii=False, sort_keys=True))
        return EXIT_OK

    where = "HATO_CONFIG" if cfg.path_source == "HATO_CONFIG" else "default location"
    found = "found" if cfg.file_exists else "not found -- documented defaults in use"
    print("config.toml  %s" % cfg.path)
    print("             %s  (%s)" % (found, where))
    print("data root    %s  (%s)" % (d["data_root"], d["data_root_source"]))
    print("")

    def row(name, shown, origin_key=None):
        # ⚠ 13, not 11: `skip_embedded` (2026-09-17) is longer than every key that
        # came before it and pushed its own value past the column. Caught by LOOKING
        # at the readout -- every check here asserts content, and a column that no
        # longer lines up is still, to all of them, correct.
        # ⚠ 15 since the Layer 14 pass (Z14-6): `format_fallback`, shown at last. A
        # check asserts the column now -- one position for every row.
        print("  %-15s = %-44s %s" % (name, shown, cfg.origin(origin_key or name)))

    row("folders", ", ".join(cfg.folders) if cfg.folders else "(none)")
    # ⚠ A SETTING NOBODY CAN SEE IS NOT A SETTING. This readout is where a
    # person checks what is in force, and `skip_folders` silently removes
    # videos from every run -- so it is the LAST thing that should be invisible.
    row("skip_folders", ", ".join(cfg.skip_folders) if cfg.skip_folders else "(none)")
    row("lang", cfg.lang)
    row("out", cfg.out or "(beside the video)")
    row("subs_dir", str(cfg.subs_dir_resolved))
    row("candidates", str(cfg.candidates))
    row("archives", "true" if cfg.archives else "false")
    row("allow_ai", "true" if cfg.allow_ai else "false")
    row("recurse", "true" if cfg.recurse else "false")
    # ⚠ A setting nobody can SEE is not a setting. Both of these were added on
    # 2026-09-17 and the readout is where a person checks what is in force.
    row("skip_embedded", "true" if cfg.skip_embedded else "false")
    # 🚨 Z14-6 (the Layer 14 pass): these three were set in the window and never
    # shown here. A check derives every key from SCHEMA now.
    row("prefer_format", cfg.prefer_format)
    row("format_fallback", "true" if cfg.format_fallback else "false")
    row("watch", "true" if cfg.watch else "false")
    row("schedule", cfg.schedule)
    row("surasura_dir", cfg.surasura_dir or "(off)")
    row("auto_update", "true" if cfg.auto_update else "false")
    row("log.path", str(cfg.log_path_resolved), "log.path")
    row("log.keep", str(cfg.log_keep), "log.keep")
    return EXIT_OK


def _check_key(args):
    try:
        key = credentials.resolve_key()
    except (credentials.KeyMissing, paths.PathError) as exc:
        if args.json:
            print(json.dumps({"found": False, "reason": str(exc)}, ensure_ascii=False))
        else:
            print("jimaku key   MISSING")
            print("             %s" % exc)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"found": True, "hint": key.hint, "source": key.source},
                         ensure_ascii=False))
    else:
        print("jimaku key   found, ending %s" % key.hint)
        print("             from %s" % key.source)
    return EXIT_OK


def _changes_asked_for(args):
    """-> True when any write flag was given."""
    return bool(args.set_pairs or args.add_folder or args.remove_folder
                or args.add_skip or args.remove_skip)


def _folder_list(existing, adding, removing, what):
    """One folder list, plus/minus. -> [str]

    ⭐ A REMOVE THAT MATCHED NOTHING IS REFUSED, NOT IGNORED. Silently
    succeeding at removing a folder that was never there tells somebody their
    library is no longer being scanned when it still is -- doctrine/robustness'
    *refuse loudly, never drop silently*, which this module's own reader
    already applies to an unknown key.

    ⚠ COMPARED AS RESOLVED PATHS. `D:\\Anime` and `D:/Anime/` are one folder,
    and a person removing one by typing it will not reproduce the separator
    and trailing slash they originally added.
    """
    def norm(p):
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))

    out = list(existing)
    for raw in removing:
        wanted = norm(raw)
        matched = [f for f in out if norm(f) == wanted]
        if not matched:
            raise _config.ConfigError(
                "%s is not in %s, so there is nothing to remove. It holds: %s"
                % (raw, what, ", ".join(out) if out else "(nothing)"))
        out = [f for f in out if norm(f) != wanted]
    for raw in adding:
        # ⚠ NO `isabs` CHECK HERE, AND THAT IS DELIBERATE -- removed 2026-09-18
        # after mutant M7a-09 SURVIVED. There was one, and deleting it changed
        # nothing observable: `config.parse` refuses a relative path through
        # `_absolute()`, in the SAME sentence, before anything is written. A
        # second validator in the command layer contradicts this step's own
        # design -- one writer, one schema, one validator -- and a guard that
        # cannot be observed to work is a guard nobody can maintain.
        # ⛔ The refusal itself is still checked: see
        # `test_a_relative_folder_is_refused_by_the_same_sentence_the_file_gives`.
        full = str(Path(os.path.expanduser(raw)))
        if any(norm(f) == norm(full) for f in out):
            continue                       # ⚠ adding twice is a no-op, not a fault
        out.append(full)
    return out


def _write(args):
    """Apply every change asked for, as ONE validated write."""
    try:
        cfg = _config.load()
    except (_config.ConfigError, paths.PathError) as exc:
        return _fail(args, "config is wrong, so it cannot be changed -- %s" % exc)

    changes = {}
    try:
        for pair in args.set_pairs:
            if "=" not in pair:
                raise _config.ConfigError(
                    "--set takes KEY=VALUE, got %r. For example: "
                    "--set candidates=5" % pair)
            name, raw = pair.split("=", 1)
            name = name.strip()
            changes[name] = _config.coerce(name, raw)
        if args.add_folder or args.remove_folder:
            changes["folders"] = _folder_list(
                cfg.folders, args.add_folder, args.remove_folder, "folders")
        if args.add_skip or args.remove_skip:
            changes["skip_folders"] = _folder_list(
                cfg.skip_folders, args.add_skip, args.remove_skip, "skip_folders")
        fresh = _config.with_changes(cfg, **changes)
        written = _config.save(fresh)
    except (_config.ConfigError, paths.PathError, OSError) as exc:
        return _fail(args, str(exc))

    if args.json:
        d = fresh.as_dict()
        d["ok"] = True
        d["written"] = str(written)
        d["changed"] = sorted(changes)
        print(json.dumps(d, ensure_ascii=False, sort_keys=True))
        return EXIT_OK
    print("config.toml  %s" % written)
    for name in sorted(changes):
        print("  %-13s = %s" % (name, _shown(fresh, name)))
    return EXIT_OK


def _shown(cfg, name):
    value = getattr(cfg, name, None)
    if isinstance(value, (list, tuple)):
        return ", ".join(value) if value else "(none)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _fail(args, message):
    if args.json:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        sys.stderr.write("hato: %s\n" % message)
    return EXIT_FAILED


def run(args):
    writing = _changes_asked_for(args)
    if writing and (args.show or args.check_key):
        return _fail(args, "--show and --check-key read the config; the other "
                           "flags change it. Run them separately, so what you "
                           "are shown is not half a change.")
    if writing:
        return _write(args)
    if args.show:
        return _show(args)
    if args.check_key:
        return _check_key(args)
    # ⛔ BARE `hato config` IS STILL A USAGE ERROR. The mutually-exclusive group
    # above used to enforce it with `required=True`; the write flags made that
    # impossible, so the refusal lives here and a check pins it.
    sys.stderr.write(
        "hato config: say what to do. --show reads the settings, --check-key "
        "checks the jimaku key, and --set / --add-folder / --remove-folder / "
        "--add-skip / --remove-skip change them.\n")
    return 2
