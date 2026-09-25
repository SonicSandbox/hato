# -*- coding: utf-8 -*-
"""
The command line. A thin dispatcher -- every command lives in its own module.

    hato <folder> [<folder> ...] [flags]     the run (spec/05-interface.md)
    hato [flags]                             the same, over config.toml's `folders`
    hato <command> [flags]                   config, doctor, cache, state, ...
    hato --help · hato --version

⭐ BARE `hato` IS THE RUN, NOT THE USAGE SCREEN. `05-interface.md` makes the
folder run the front door and `10-deployment.md` schedules it as `hato --quiet`
with no folder at all, so "no arguments" has to mean *do the job over the
configured folders*. With nothing configured either, the run module prints the
usage screen and the sentence naming the fix -- `--help` is unchanged.

⭐ ONE MODULE PER COMMAND, REGISTERED BELOW BY NAME. The build runs through
parallel builder agents who may never edit an existing source file
(spec/RUNBOOK.md §How this build runs), so a new command is a new file under
hato/commands/ plus ONE line in COMMANDS, added by the orchestrator when it wires
the step in. Each module exposes `register(parser)` and `run(args) -> int`.

Exit codes (spec/10-deployment.md §The Windows launcher, rule 4):
    0  it ran -- a refusal or a NOT FOUND is a normal outcome, not a failure
    1  it could not do what was asked (bad config, no key, unreadable input)
    2  usage error
"""
import argparse
import importlib
import sys

from hato import __version__

#: command name -> module. ⚠ The orchestrator owns this table.
COMMANDS = {
    "config": "hato.commands.config",
    "key": "hato.commands.key",
    "doctor": "hato.commands.doctor",
    "cache": "hato.commands.cache",
    "state": "hato.commands.state",
    "blacklist": "hato.commands.blacklist",
    "identify": "hato.commands.identify",
    "files": "hato.commands.files",
    "align": "hato.commands.align",
    "rank": "hato.commands.rank",
    "extract": "hato.commands.extract",
    "sync": "hato.commands.sync",
    "problems": "hato.commands.problems",
    "update": "hato.commands.update",           # RUNBOOK LAYER 11
}

#: The folder run (spec/RUNBOOK.md 4b + 5a).
RUN_MODULE = "hato.commands.run"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def utf8_stdio():
    """Japanese filenames reach stdout constantly. Windows Python defaults to
    cp1252 and raises on the first one (LEDGER-HOT.md), so reconfigure first."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _summary(module):
    doc = (getattr(module, "__doc__", "") or "").strip().splitlines()
    return doc[0] if doc else ""


def usage():
    lines = ["usage: hato <folder> [<folder> ...] [flags]",
             "       hato [flags]                       the same, over config.toml's folders",
             "       hato <command> [flags]",
             "       hato --version",
             "",
             "commands:"]
    for name in sorted(COMMANDS):
        try:
            mod = importlib.import_module(COMMANDS[name])
            lines.append("  %-10s %s" % (name, _summary(mod)))
        except Exception as exc:  # a broken command must not hide the others
            lines.append("  %-10s (could not load: %s)" % (name, exc))
    lines.extend(_run_flags())
    return "\n".join(lines)


def _run_flags():
    """The FOLDER RUN's own flags, asked of its parser rather than re-listed.

    ⛔ A second copy here would drift from `hato/commands/run.py` the first time
    a flag is added, and `hato --help` is where a person looks for them -- there
    is no `hato <folder> --help` to fall back on, because a folder is not a
    subcommand.
    """
    if RUN_MODULE is None:
        return []
    try:
        module = importlib.import_module(RUN_MODULE)
        parser = argparse.ArgumentParser(prog="hato", add_help=False)
        module.register(parser)
        body = parser.format_help().split("\n")
    except Exception as exc:
        return ["", "the run's flags could not be listed: %s" % exc]
    start = next((i for i, line in enumerate(body)
                  if line.strip().startswith("-")), None)
    return ["", "flags for the folder run:"] + (body[start:] if start else [])


def main(argv=None):
    utf8_stdio()
    argv = sys.argv[1:] if argv is None else list(argv)

    if argv and argv[0] in ("-h", "--help"):
        print(usage())
        return EXIT_OK
    if argv and argv[0] in ("-V", "--version"):
        print("hato %s" % __version__)
        return EXIT_OK

    if argv and argv[0] in COMMANDS:
        module = importlib.import_module(COMMANDS[argv[0]])
        parser = argparse.ArgumentParser(prog="hato " + argv[0],
                                         description=_summary(module))
        module.register(parser)
        args = parser.parse_args(argv[1:])
        return module.run(args)

    if RUN_MODULE is None:
        sys.stderr.write(
            "hato: the folder run is not built yet (spec/RUNBOOK.md 4b). "
            "Known commands: %s\n" % ", ".join(sorted(COMMANDS)))
        return EXIT_USAGE
    module = importlib.import_module(RUN_MODULE)
    parser = argparse.ArgumentParser(prog="hato", description=_summary(module))
    module.register(parser)
    return module.run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
