# -*- coding: utf-8 -*-
"""`python -m hato.dev <command>` -- the five commands spec/RUNBOOK.md §6 invokes.

⛔ EXIT CODES ARE THE INTERFACE.

    0   every claim held
    1   a claim failed -- ONE line on stderr naming it and what it saw
    2   the tool could not run: a bad argument, a missing wheel, no source tree
        (doctrine/verification: a tooling fault gets its own exit code and
        announces itself as a tooling fault -- a path guard that refused every
        request once rendered identically to a broken app, and cost four wrong
        diagnoses)

⛔ AND NEVER A TRACEBACK. Everything below is wrapped: an unexpected exception
becomes one line naming the command, the exception type and its message. A
traceback in a release block is unreadable in the channel that reports it
(pitfall P25: a CI annotation keeps the FIRST line only).
"""
import sys

from hato.dev import claims
from hato.dev.claims import EXIT_FAULT, Fault

#: name -> (module path, the function that takes argv and returns an exit code)
COMMANDS = (
    ("stamp", "hato.dev.stamp", "main",
     "write hato/__init__.py's version + the tree's content hash; --check is the gate"),
    ("audit-wheel", "hato.dev.wheel", "main",
     "the wheel's manifest, claim by claim, before publishing"),
    ("scan-secrets", "hato.dev.scan", "main_secrets",
     "no secret anywhere in the artifact -- wheels and sdists unpacked"),
    ("scan-content", "hato.dev.scan", "main_content",
     "no third-party subtitle BODY in the artifact (fixtures are metadata)"),
    ("verify-install", "hato.dev.install", "main",
     "a clean venv outside every checkout; --no-unrar proves the degradation path"),
)

_BY_NAME = dict((name, (module, func)) for name, module, func, _ in COMMANDS)


def usage():
    lines = ["usage: python -m hato.dev <command> [flags]",
             "",
             "the release block (spec/RUNBOOK.md §Step 6 -- read doctrine/release first):"]
    for name, _, _, why in COMMANDS:
        lines.append("  %-15s %s" % (name, why))
    return "\n".join(lines)


def main(argv=None):
    claims.utf8_stdio()
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(usage() + "\n")
        return claims.EXIT_OK if argv else EXIT_FAULT

    name = argv[0]
    if name not in _BY_NAME:
        sys.stderr.write("hato.dev: no such command %r -- one of: %s\n"
                         % (name, ", ".join(sorted(_BY_NAME))))
        return EXIT_FAULT

    module_name, func_name = _BY_NAME[name]
    try:
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, func_name)(argv[1:])
    except Fault as exc:
        sys.stderr.write("hato.dev %s: %s\n" % (name, str(exc).replace("\n", " ")))
        return EXIT_FAULT
    except SystemExit as exc:                  # argparse's own --help / usage error
        return exc.code if isinstance(exc.code, int) else EXIT_FAULT
    except KeyboardInterrupt:
        sys.stderr.write("hato.dev %s: interrupted -- nothing was published\n" % name)
        return EXIT_FAULT
    except Exception as exc:                   # ⛔ one line, never a traceback
        sys.stderr.write("hato.dev %s: %s: %s\n"
                         % (name, type(exc).__name__, str(exc).replace("\n", " ")))
        return EXIT_FAULT


if __name__ == "__main__":
    sys.exit(main())
