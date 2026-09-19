# -*- coding: utf-8 -*-
"""
One shape for every claim the release tools make, and one way of printing it.

    claims.ok(name, saw)      the claim holds, and what was measured
    claims.fail(name, saw)    it does not, and what was seen INSTEAD
    claims.skip(name, why)    it could not be made -- ⛔ printed, never silent
    claims.report(cmd, subject, claims)   -> the exit code

⭐ WHY A CLAIM CARRIES `saw` AND NOT A BOOLEAN. doctrine/verification: a check
that passed on an empty set reported `0 broken of 0`. Every `saw` here prints
its denominator, so a vacuous pass is visible at a glance rather than reading
as a tick.

⚠ A SKIP IS NOT A PASS. It prints as SKIP with the reason, is counted in the
final line, and does not fail the command -- because the alternative (failing)
is how a release gate gets switched off. The one exception is `scan-secrets`
with no key, which refuses outright: there the skipped half IS the claim.

🚨 THE FAILURE LINE GOES TO STDERR, ON ITS OWN, IN ONE LINE. Pitfall P25: a CI
annotation ended "Tk could not start (1 attempt):" with the cause cut off,
because the reporter keeps the first line only. stdout gets the full readout for
a human; stderr gets exactly the one line a machine will keep.
"""
import sys
from pathlib import Path

#: The three states. `OK`/`FAIL`/`SKIP` are what print.
OK = "ok"
FAIL = "FAIL"
SKIP = "SKIP"

#: `python -m hato.dev <cmd>` exit codes.
EXIT_OK = 0
EXIT_CLAIM_FAILED = 1
EXIT_FAULT = 2


class Fault(Exception):
    """⛔ THE TOOL COULD NOT RUN -- not "the claim failed".

    A missing wheel, an unreadable zip, a bad argument, no source tree. It exits
    2 and says so, because doctrine/verification measured four wrong diagnoses
    from a tooling fault that rendered identically to a real failure.
    """


class Claim(object):
    __slots__ = ("name", "state", "saw")

    def __init__(self, name, state, saw):
        self.name = name
        self.state = state
        self.saw = saw

    def __repr__(self):
        return "<Claim %s %s: %s>" % (self.name, self.state, self.saw)


def ok(name, saw):
    return Claim(name, OK, saw)


def fail(name, saw):
    return Claim(name, FAIL, saw)


def skip(name, why):
    return Claim(name, SKIP, why)


def utf8_stdio():
    """🚨 LEDGER-HOT.md: Windows Python defaults to cp1252 and a Japanese
    filename in a claim's `saw` would raise UnicodeEncodeError while PRINTING
    the failure -- turning a readable verdict into a traceback."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def report(command, subject, results, out=None, err=None):
    """Print every claim, then ONE summary line. -> an exit code.

    ⭐ The summary names the count of each state, so `0 claims` can never read
    as a pass: a command that measured nothing exits non-zero.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    results = list(results)

    out.write(u"hato.dev %s  %s\n" % (command, subject))
    for c in results:
        out.write(u"  %-5s %-24s %s\n" % (c.state, c.name, c.saw))

    failed = [c for c in results if c.state == FAIL]
    skipped = [c for c in results if c.state == SKIP]
    held = [c for c in results if c.state == OK]

    if not results:
        line = (u"FAILED %s: no_claims -- the command measured nothing, and exit 0 "
                u"is not a pass (doctrine/verification)" % command)
        out.write(line + u"\n")
        err.write(line + u"\n")
        return EXIT_CLAIM_FAILED

    tally = u"%d held, %d failed, %d skipped" % (len(held), len(failed), len(skipped))
    if failed:
        line = u"FAILED %s: %s -- %s" % (command, failed[0].name, failed[0].saw)
        if len(failed) > 1:
            line += u"  (+%d more: %s)" % (len(failed) - 1,
                                           u", ".join(c.name for c in failed[1:]))
        out.write(u"%s\n%s\n" % (tally, line))
        err.write(line.replace(u"\n", u" ") + u"\n")
        return EXIT_CLAIM_FAILED

    out.write(u"OK %s: %s\n" % (command, tally))
    return EXIT_OK


def find_root(explicit=None, start=None):
    """The source tree that holds the `hato` package. -> Path, or raise Fault.

    ⛔ Walks UP from this module, never from the working directory: the release
    block is run from wherever the operator happens to be, and `spec/10-deployment.md`
    §The Windows launcher is the same rule for the launcher -- resolve every path
    from the file's own location, never from `.`.
    """
    if explicit is not None:
        root = Path(explicit).resolve()
        if not (root / "hato" / "__init__.py").is_file():
            raise Fault("--root %s does not hold hato/__init__.py" % root)
        return root
    here = Path(start).resolve() if start is not None else Path(__file__).resolve().parent
    for d in [here] + list(here.parents):
        if (d / "hato" / "__init__.py").is_file():
            return d
    raise Fault("no hato source tree above %s -- pass --root <checkout>" % here)


def read_source_version(root):
    """`__version__` as it is written in hato/__init__.py. -> (str, Path).

    ⭐ READ FROM THE FILE, NOT BY IMPORTING. An `import hato` during a release
    resolves to whatever is on sys.path -- which at that moment may be an
    installed wheel of the PREVIOUS version -- and the claim is about the tree
    being released.
    """
    import re
    path = Path(root) / "hato" / "__init__.py"
    text = path.read_bytes().decode("utf-8")
    found = re.findall(r'^__version__\s*=\s*"([^"]*)"', text, re.M)
    if len(found) != 1:
        raise Fault('hato/__init__.py has %d lines matching __version__ = "..." '
                    "-- expected exactly 1" % len(found))
    return found[0], path
