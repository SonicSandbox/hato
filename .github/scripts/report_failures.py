# -*- coding: utf-8 -*-
"""Put the failing test NAMES somewhere a person with no credentials can read them.

    python .github/scripts/report_failures.py --label "ubuntu-latest py3.12"
    python .github/scripts/report_failures.py --require-failures --summary "$GITHUB_STEP_SUMMARY"

Exit 1 when a failure was found (and an annotation was emitted); exit 0 when the
run was clean and nothing was emitted; exit 2 when this tool itself could not run.

===========================================================================
🚨 WHY THIS EXISTS AT ALL -- pitfall P14, measured, five channels, one worked
===========================================================================
There is no `gh` CLI and no GitHub token on the build machine. When CI goes red:

  1. `GET /repos/{o}/{r}/actions/jobs/{id}/logs` -> "Must have admin rights to
     Repository" to an anonymous request.
  2. An uploaded log artifact -> downloading it needs authentication.
  3. Printing the failure into the job log -> the same wall as 1.
  4. `$GITHUB_STEP_SUMMARY` -> the check-run API returns `"summary": null`; the
     web page fetches it client-side.
  5. ✅ `::error::` ANNOTATIONS. `GET /repos/{o}/{r}/check-runs/{job_id}/annotations`
     is PUBLIC on a public repo, and the job id IS the check-run id.

So the failing test names go into an annotation. Everything else here -- the
readable dump, the step summary -- is for whoever does have rights, and none of
it is allowed to be load-bearing.

===========================================================================
⛔ THE FOUR RULES THIS FILE IS SHAPED BY, EACH PAID FOR
===========================================================================
* **P15 -- THE ANNOTATION IS WRITTEN BEFORE ANYTHING ELSE IS PRINTED.** On
  Windows this reporter once exited GREEN and emitted NOTHING: a failure message
  carrying Japanese hit a cp1252 stdout, UnicodeEncodeError killed it, and
  `|| true` in the workflow swallowed the corpse. Ordering is the guard, not
  decoration -- the machine-readable line must not depend on the human-readable
  dump surviving. ⛔ And nothing in the workflow may wrap this in `|| true`.
* **EVERY BYTE EMITTED IS ASCII, by construction.** Non-ASCII is escaped with
  `backslashreplace`, so a Japanese filename arrives as `\\u9ce9` rather than as
  an exception. ⚠ The test asserts ASCII, NOT cp1252: a mutant putting an em
  dash back SURVIVED a cp1252 check, because cp1252 has an em dash.
* **P25 -- NAME PLUS A ONE-LINE CAUSE.** A CI run once annotated
  "Tk could not start (1 attempt):" with the cause cut off, because the reporter
  took line one and the test put the detail on line two. So the cause here is
  the first NON-EMPTY line of the message, and the body is the fallback.
* **NEWLINES ARE PERCENT-ENCODED OR ONLY THE FIRST LINE SURVIVES.** `%` is
  escaped first, or it eats the escapes it is about to write.

⚠ It reads the JUnit XML `run_tests.py` writes (`_runs/<stamp>/<suite>.xml`),
never stdout. `tail -n 60` of a suite's console output has scrolled the one line
that mattered off the top, and it cost a second full run to learn a name the
first run already had.
"""
import argparse
import glob
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

EXIT_OK = 0
EXIT_FOUND = 1
EXIT_FAULT = 2

#: The API truncates a long annotation, and a truncated one that lost the test
#: NAMES is worth nothing. Names first, capped.
DEFAULT_MAX = 25
#: Per-failure cause, characters.
CAUSE_CHARS = 200
#: Lines of message+body per failure in the readable dump.
DUMP_LINES = 25


def ascii_only(text):
    """-> str containing nothing above U+007F. ⛔ Never raises.

    ⚠ `backslashreplace` rather than `replace`: a filename mangled to `???` has
    lost the thing that made it interesting, and this project's corpus is
    Japanese. `\\u9ce9` is ugly and it is still the answer.
    """
    if not isinstance(text, type(u"")):
        text = u"%s" % (text,)
    return text.encode("ascii", "backslashreplace").decode("ascii")


def encode(text):
    """Percent-encode a workflow command's MESSAGE. ⛔ `%` FIRST, or it eats its
    own escapes -- `\\n` becomes `%0A` becomes `%250A` if the order is wrong."""
    return (text.replace(u"%", u"%25")
                .replace(u"\r", u"%0D")
                .replace(u"\n", u"%0A"))


def encode_property(text):
    """Percent-encode a workflow command's PROPERTY value -- `title=` here.

    🚨 A COLON IN A PROPERTY VALUE BREAKS THE COMMAND. GitHub parses
    `::error title=X::message` by splitting on `::`, and properties are a
    comma-separated `k=v` list -- so an unescaped `:` or `,` inside a title
    silently eats the rest of the properties, or the message. Measured here
    2026-09-17: a title reading `failures: no run log` produced a line no
    annotation parser matched at all.
    """
    return (encode(text).replace(u":", u"%3A").replace(u",", u"%2C"))


#: A line that is nothing but an exception type. ⚠ pytest's JUnit `message`
#: attribute for `assert False, "\\ndetail"` is exactly `AssertionError:` -- the
#: type, a colon, and nothing else. Taking it as the cause is pitfall P25
#: reproduced: the name survives and the reason does not.
BARE_EXCEPTION = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Warning|Failed)?\s*:\s*$")
#: pytest writes the failing assertion into the `<failure>` BODY, each line
#: prefixed `E`. That is where the detail actually lives.
PYTEST_ERROR_LINE = re.compile(r"^E\s+(.*)$")


def cause(message, body):
    """The one line that says WHY -- P25, and it took two attempts.

    ⛔ NOT `message.splitlines()[0]`, and not "the first non-empty line" either.
    The sibling project's CI annotated `Tk could not start (1 attempt):` with
    the cause cut off, because the reporter took line one and the test put the
    detail on line two. The first version of THIS function then annotated
    `AssertionError:` for the same reason one level down: pytest's `message`
    attribute is the bare exception header, and the detail is in the body.

    So: pytest's own `E` lines first, then the message, then the rest of the
    body -- skipping any line that is only an exception type, and keeping that
    type as a prefix so the annotation reads `AssertionError: the real reason`.
    """
    body_lines = (body or u"").splitlines()
    ordered = [m.group(1) for m in
               (PYTEST_ERROR_LINE.match(l.strip()) for l in body_lines) if m]
    ordered += (message or u"").splitlines()
    ordered += body_lines

    header = u""
    for line in ordered:
        stripped = line.strip()
        if not stripped:
            continue
        if BARE_EXCEPTION.match(stripped):
            header = header or stripped
            continue
        return (u"%s %s" % (header, stripped)).strip() if header else stripped
    return header


def xml_files(runs_dir):
    """Every JUnit XML under `runs_dir`, newest layout first.

    `run_tests.py` writes `<runLogDir>/<stamp>/<suite>.xml`; a bare
    `<runLogDir>/<suite>.xml` is accepted too so a hand-driven pytest can be
    read by the same tool.
    """
    found = sorted(glob.glob(os.path.join(runs_dir, "*", "*.xml")))
    found += sorted(glob.glob(os.path.join(runs_dir, "*.xml")))
    return found


def failures_in(path):
    """-> [(kind, xml basename, test name, message, body), ...] for one file."""
    out = []
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        for case in suite.iter("testcase"):
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is None:
                    continue
                where = case.get("classname") or ""
                name = case.get("name") or "<unnamed>"
                out.append((kind.upper(), os.path.basename(path),
                            ("%s::%s" % (where.split(".")[-1], name)
                             if where else name),
                            (node.get("message") or u"").strip(),
                            (node.text or u"").strip()))
    return out


def collect(runs_dir):
    """-> (failures, files read, [unreadable file, reason]).

    ⚠ An unreadable XML is reported, never skipped. A truncated file is exactly
    what a killed runner leaves behind, and silence there reads as "clean".
    """
    found, read, broken = [], [], []
    for path in xml_files(runs_dir):
        try:
            found.extend(failures_in(path))
        except Exception as exc:                        # noqa: BLE001 - any parse fault
            broken.append((os.path.basename(path),
                           "%s: %s" % (type(exc).__name__, exc)))
        else:
            read.append(path)
    return found, read, broken


def annotation_lines(failures, broken, limit):
    """The lines that go INSIDE the annotation: name plus a one-line cause."""
    lines = []
    for kind, xml, name, message, body in failures[:limit]:
        why = cause(message, body) or u"(the failure carried no message)"
        lines.append(u"%s %s::%s -- %s" % (kind, xml, name, why[:CAUSE_CHARS]))
    if len(failures) > limit:
        lines.append(u"...and %d more" % (len(failures) - limit))
    for xml, why in broken:
        lines.append(u"UNREADABLE %s -- %s" % (xml, why[:CAUSE_CHARS]))
    return lines


def empty_reason(runs_dir, read, broken):
    """What to say when the job failed and no testcase did. ⚠ Three different
    diagnoses, and telling them apart is the whole value of this branch."""
    if broken and not read:
        return (u"every JUnit XML under %s failed to parse. A killed or "
                u"out-of-disk runner leaves exactly this." % runs_dir)
    if not read:
        return (u"no JUnit XML at all under %s -- the runner never got as far as "
                u"writing one. A collection error, an import error in conftest, "
                u"or the runner itself. See the job log." % runs_dir)
    return (u"%d JUnit XML file(s) read and NOT ONE testcase failed, yet the job "
            u"is red. So a LATER step failed -- the wheel audit, the examples, "
            u"the docs check -- or the runner exited non-zero for its own "
            u"reason (a suite reporting zero checks is a TOOLING fault here, "
            u"not a failure)." % len(read))


def emit_annotation(title, lines, stream):
    """⛔ CALLED BEFORE ANY OTHER OUTPUT. One physical line, ASCII, encoded.

    ⚠ The title goes through `encode_property`, not `encode`: a `:` or a `,` in
    a property value breaks the whole command.
    """
    text = encode(ascii_only(u"\n".join(lines)))
    stream.write(u"::error title=%s::%s\n"
                 % (encode_property(ascii_only(title)), text))
    stream.flush()


def dump(failures, read, broken, label, stream):
    """The readable form, for whoever has rights to the log. ASCII too."""
    write = lambda s: stream.write(ascii_only(s))            # noqa: E731
    write(u"\n===== %s: the runner's own record =====\n" % (label or "failures"))
    write(u"%d JUnit XML file(s) read\n" % len(read))
    for xml, why in broken:
        write(u"UNREADABLE  %s -- %s\n" % (xml, why))
    for kind, xml, name, message, body in failures:
        write(u"\n%s  %s::%s\n" % (kind, xml, name))
        for line in (message.splitlines() + body.splitlines())[-DUMP_LINES:]:
            write(u"    %s\n" % line)
    write(u"\n%d failing test(s) named above\n" % len(failures))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python .github/scripts/report_failures.py",
        description="emit failing test names as ::error:: annotations")
    parser.add_argument("--runs", default="_runs", metavar="DIR",
                        help="the runner's log directory (default: _runs)")
    parser.add_argument("--label", default="", metavar="TEXT",
                        help="job identity, so a pasted annotation says which cell")
    parser.add_argument("--summary", metavar="PATH",
                        help="also append the readable dump here ($GITHUB_STEP_SUMMARY)")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX, metavar="N",
                        help="annotate at most N failures (default: %d)" % DEFAULT_MAX)
    parser.add_argument("--require-failures", action="store_true",
                        help="the job is known to be red: say so even when no "
                             "testcase failed, and still exit non-zero")
    args = parser.parse_args(argv)

    # ⚠ ASCII with backslashreplace on the way out, so this reporter cannot be
    # killed by its own subject matter even if `ascii_only` were bypassed. Belt
    # as well as braces: P15's cause was a reporter dying on its own input.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="ascii", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    if not os.path.isdir(args.runs):
        if not args.require_failures:
            sys.stdout.write("no %s directory; nothing to report\n" % args.runs)
            return EXIT_OK
        emit_annotation("%s: no run log" % (args.label or "failures"),
                        [empty_reason(args.runs, [], [])], sys.stdout)
        return EXIT_FOUND

    try:
        failures, read, broken = collect(args.runs)
    except Exception as exc:                            # noqa: BLE001
        # ⛔ A TOOLING FAULT ANNOUNCES ITSELF AS ONE (doctrine/verification), and
        # it still uses the one channel that can be read without credentials.
        emit_annotation("the failure reporter itself could not run",
                        [u"%s: %s" % (type(exc).__name__, exc)], sys.stdout)
        return EXIT_FAULT

    if failures or broken:
        title = u"%d failing test(s)%s" % (len(failures),
                                           u" -- " + args.label if args.label else u"")
        emit_annotation(title, annotation_lines(failures, broken, args.max),
                        sys.stdout)
    elif args.require_failures:
        emit_annotation(u"no failing test, and the job is red%s"
                        % (u" -- " + args.label if args.label else u""),
                        [empty_reason(args.runs, read, broken)], sys.stdout)
    # ⭐ ELSE: NOTHING IS EMITTED AND THE EXIT IS 0. A reporter that annotates a
    # green run trains people to ignore annotations, which is the one channel
    # that works.

    dump(failures, read, broken, args.label, sys.stdout)
    if args.summary:
        try:
            with io.open(args.summary, "a", encoding="utf-8") as fh:
                fh.write(u"## %s -- what failed\n\n```\n" % (args.label or "failures"))
                dump(failures, read, broken, args.label, fh)
                fh.write(u"```\n")
        except OSError as exc:
            # ⚠ NOT fatal. The summary is the channel that came back `null` from
            # the API; losing it must never cost the annotation above.
            sys.stdout.write("could not write the step summary: %s\n" % exc)

    if failures or broken or args.require_failures:
        return EXIT_FOUND
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
