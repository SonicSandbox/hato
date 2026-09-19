# -*- coding: utf-8 -*-
u"""Step R5 -- the three scripts `.github/workflows/` invokes.

⭐ WHY THIS SUITE EXISTS AT ALL. Nothing else in this project can run a GitHub
Actions workflow, so the workflows themselves are unproven until they run. What
IS provable here is every line of Python they call -- and two of those three
scripts are DIAGNOSTIC instruments, which is the category doctrine/evidence says
returns confident wrong answers:

  "the instrument has to hand back the finding, not store it somewhere the
   finding cannot be reached from."

🚨 AND ONE OF THEM HAS ALREADY FAILED IN EXACTLY THAT WAY IN THE SIBLING
PROJECT. Pitfall P15: the failure reporter "exited green and emitted nothing"
on Windows -- non-ASCII output on a cp1252 console, swallowed by `|| true`. So
the reporter is driven against REAL pytest JUnit XML, with a REAL failure, with
a Japanese message and a `%` in it, and the assertions are:

    failures present  -> an annotation IS emitted, and the exit is non-zero
    run clean         -> NO annotation, and the exit is zero

⚠ AND THE ENCODING CHECK ASSERTS ASCII, NOT cp1252. P15's own guard note: "a
mutant putting an em dash back SURVIVED a cp1252 check, because cp1252 has an
em dash."

⛔ WHAT THIS SUITE STRUCTURALLY CANNOT COVER: whether the YAML is valid to
GitHub, whether a runner has the tools the jobs assume, whether Trusted
Publishing authenticates, and whether an annotation emitted here is readable
through the check-runs API. Those need a run on GitHub. The YAML is parsed as
YAML by `test_the_workflows_parse_as_yaml` when PyYAML is importable and is
otherwise reported as an explicit skip -- a parse is not a validation.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".github" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
REPORTER = SCRIPTS / "report_failures.py"
CHECK_DOCS = SCRIPTS / "check_docs.py"
OUTSIDE = SCRIPTS / "outside_checkout.py"

#: Everything these scripts print must survive a cp1252 console (P15).
ANNOTATION = re.compile(r"^::error title=([^:]*)::(.*)$", re.M)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def call(script, args, cwd=None, env=None, python=None):
    """-> (returncode, combined output). ⛔ Never raises on a non-zero exit."""
    base = dict(os.environ)
    base["PYTHONIOENCODING"] = "utf-8"
    base["PYTHONUTF8"] = "1"
    base.pop("GITHUB_ACTIONS", None)
    if env:
        for name, value in env.items():
            if value is None:
                base.pop(name, None)
            else:
                base[name] = value
    proc = subprocess.run([python or sys.executable, str(script)] + list(args),
                          cwd=str(cwd or ROOT), env=base, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=300)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def annotations(output):
    return ANNOTATION.findall(output)


def write(path, text):
    """⚠ Parents first, utf-8 always, `\\n` always -- the reporter is asked to
    read files written on three operating systems."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def assert_ascii(output, what):
    """⚠ ASCII, NOT cp1252. See the module docstring."""
    try:
        output.encode("ascii")
    except UnicodeEncodeError as exc:
        offending = output[exc.start:exc.end]
        raise AssertionError(
            "%s emitted %r (U+%04X), which is not ASCII. A cp1252 console "
            "raises on it and the reporter dies reporting the failure it exists "
            "to report (P15)." % (what, offending, ord(offending[0])))


# ---------------------------------------------------------------------------
# REAL pytest output -- built once, read by several checks
# ---------------------------------------------------------------------------

SAMPLE_SUITE = u'''# -*- coding: utf-8 -*-
def test_this_one_passes():
    assert True


def test_detail_is_on_the_second_line():
    """P25: the reporter used to annotate line one, so this detail vanished."""
    assert False, "\\nthe cause is on line two and it must still be reported"


def test_a_japanese_message_and_a_percent_sign():
    assert False, u"\\u9d29 100% of the cues turned to U+FFFD"
'''

CLEAN_SUITE = u'''def test_nothing_is_wrong():
    assert True
'''


def _pytest_junit(where, source, name):
    """Run REAL pytest on `source` and return the run directory holding its XML.

    ⚠ A hand-written XML would prove the parser and nothing about the FORMAT.
    The reporter's whole job is to read what `run_tests.py` leaves on disk, and
    `run_tests.py` leaves whatever this pytest writes.
    """
    where.mkdir(parents=True, exist_ok=True)
    write(where / ("test_%s.py" % name), source)
    runs = where / "_runs" / "20260917-000000"
    runs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # ⛔ `-p no:cacheprovider` and a cwd outside the repo: this pytest must not
    # load hato's conftest, write into the real _runs/, or touch the vault.
    subprocess.run([sys.executable, "-m", "pytest", "test_%s.py" % name,
                    "-q", "--no-header", "-p", "no:cacheprovider",
                    "--junitxml=%s" % (runs / ("%s.xml" % name))],
                   cwd=str(where), env=env, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=600)
    return runs.parent


@pytest.fixture(scope="module")
def failing_runs(tmp_path_factory):
    """A real `_runs/` holding a real failing suite's XML."""
    return _pytest_junit(tmp_path_factory.mktemp("failing"), SAMPLE_SUITE, "sample")


@pytest.fixture(scope="module")
def clean_runs(tmp_path_factory):
    """A real `_runs/` holding a real PASSING suite's XML."""
    return _pytest_junit(tmp_path_factory.mktemp("clean"), CLEAN_SUITE, "clean")


# ---------------------------------------------------------------------------
# report_failures.py -- it must be able to FAIL and to SUCCEED
# ---------------------------------------------------------------------------

def test_real_failures_produce_one_annotation_naming_every_failing_test(failing_runs):
    code, output = call(REPORTER, ["--runs", str(failing_runs), "--label", "probe"])
    found = annotations(output)
    assert found, ("no ::error:: annotation at all, against a suite with two "
                   "real failures. This IS pitfall P15.\n%s" % output)
    assert code != 0, "the reporter exited 0 while reporting failures\n%s" % output
    body = found[0][1]
    for name in ("test_detail_is_on_the_second_line",
                 "test_a_japanese_message_and_a_percent_sign"):
        assert name in body, "%r is not in the annotation: %s" % (name, body)


def test_the_annotation_is_one_physical_line_with_encoded_newlines(failing_runs):
    """⛔ Percent-encoded, or GitHub keeps only the first line."""
    code, output = call(REPORTER, ["--runs", str(failing_runs)])
    assert code != 0
    line = [l for l in output.splitlines() if l.startswith("::error")]
    assert len(line) == 1, "expected exactly one annotation line, got %d" % len(line)
    assert "%0A" in line[0], (
        "two failures and no %%0A separator: the annotation is one line and "
        "GitHub will show only the first entry\n%s" % line[0])
    assert "\n" not in line[0]


def test_a_percent_sign_is_escaped_before_the_newlines_are(failing_runs):
    """⚠ `%` first, or it eats the escapes it is about to write."""
    _code, output = call(REPORTER, ["--runs", str(failing_runs)])
    line = [l for l in output.splitlines() if l.startswith("::error")][0]
    assert "100%25" in line, (
        "the message said `100%%` and the annotation does not carry `100%%25` "
        "-- the escape order is wrong\n%s" % line)
    assert "%250A" not in line, (
        "`%%0A` was double-escaped to `%%250A`: the newlines were encoded "
        "before the percent signs\n%s" % line)


def test_the_cause_survives_when_it_is_on_the_second_line(failing_runs):
    """🚨 PITFALL P25, by name. The reporter took line one; line one was empty."""
    _code, output = call(REPORTER, ["--runs", str(failing_runs)])
    body = annotations(output)[0][1]
    entry = [part for part in body.split("%0A")
             if "test_detail_is_on_the_second_line" in part]
    assert entry, body
    assert "the cause is on line two" in entry[0], (
        "the annotation named the test and dropped its cause: %r" % entry[0])


def test_every_byte_the_reporter_emits_is_ascii(failing_runs):
    """⚠ ASCII, not cp1252 -- a Japanese failure message must be ESCAPED."""
    _code, output = call(REPORTER, ["--runs", str(failing_runs)])
    assert_ascii(output, "report_failures.py")
    assert "\\u9d29" in output, (
        "the Japanese character was dropped rather than escaped, so the "
        "annotation lost the thing that made the failure identifiable\n%s"
        % output)


# 🚨 TWO GUARDS, TWO WITNESSES -- AND THE MUTATION PASS IS WHAT FORCED THIS.
#
# The reporter is ASCII-safe twice over: `ascii_only()` escapes every string
# BEFORE it is written, and the output stream is separately reconfigured to an
# ASCII-safe encoding. Both are cheap and both are wanted.
#
# ⚠ BUT THEY ARE INDEPENDENT AND REDUNDANT, so breaking either one alone leaves
# the OUTPUT byte-identical -- and `test_every_byte_the_reporter_emits_is_ascii`
# reads only the output. Measured 2026-09-17: M6-36 (the stream reconfigured to
# cp1252/strict) SURVIVED, and the project's own note claimed that mutant was
# "the load-bearing half" while recording that the other half survived too.
# ⛔ Both surviving individually is the signature of redundancy, not of a
# load-bearing half. `doctrine/verification`: if the thing you thought was
# load-bearing is not, find out WHICH before deleting anything.
#
# ⭐ So each guard now has a check that can see it on its own. Neither replaces
# the output check above -- that one proves the two TOGETHER do the job.

def test_ascii_only_escapes_non_ascii_without_help_from_the_stream():
    """⭐ The IN-CODE guard, on its own, with no stream involved at all.

    ⛔ Imported rather than driven through a subprocess, deliberately: every
    other check here reads the reporter's stdout, and stdout is exactly where
    the second guard would mask this one.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("hato_report_failures", str(REPORTER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    got = module.ascii_only(u"鴩 is a pigeon")
    assert got == "\\u9d29 is a pigeon", (
        "ascii_only() returned %r -- it must ESCAPE non-ASCII, not drop or "
        "replace it: a filename mangled to '???' cannot be searched for" % got)
    got.encode("ascii")                      # raises if it lied


def test_the_output_stream_is_configured_ASCII_SAFE_as_the_second_guard():
    """⭐ The BELT to `ascii_only`'s braces, asserted structurally.

    ⚠ THIS IS A CLAIM ABOUT THE SOURCE, NOT ABOUT BEHAVIOUR, and that is not a
    dodge -- it is the only way to see this guard. Its whole purpose is to save
    the reporter *if `ascii_only` were bypassed*, so while `ascii_only` works
    the stream's encoding can never change a single emitted byte. There is no
    output to assert on.

    🚨 P15 is why it exists at all: on Windows the reporter once exited green
    and emitted NOTHING -- non-ASCII output on a cp1252 console, swallowed by
    `|| true`. A frozen app ignored `PYTHONIOENCODING` entirely.
    """
    source = REPORTER.read_text(encoding="utf-8")
    calls = re.findall(r"reconfigure\((.*?)\)", source)
    assert calls, (
        "report_failures.py no longer reconfigures its output stream at all. "
        "That is the guard that survives `ascii_only` being bypassed (P15)")
    for args in calls:
        assert "cp1252" not in args and "mbcs" not in args, (
            "the output stream is reconfigured to a non-ASCII codec (%s) -- a "
            "Japanese failure message then raises on the way out and kills the "
            "reporter reporting it (P15)" % args.strip())
        assert 'encoding="ascii"' in args or "encoding='ascii'" in args, (
            "the output stream is reconfigured without naming the ascii "
            "encoding (%s); ASCII is the only codec that cannot be killed by "
            "its own subject matter" % args.strip())
        assert "backslashreplace" in args, (
            "the output stream is reconfigured to ascii without "
            "backslashreplace (%s), so a Japanese character becomes an error "
            "or a '?' instead of a searchable \\uXXXX escape" % args.strip())


def test_the_annotation_is_written_before_any_other_output(failing_runs):
    """⛔ ORDERING, NOT DECORATION. The readable dump is the part that can die
    on an encoding; when it did, the annotation never got written (P15)."""
    _code, output = call(REPORTER, ["--runs", str(failing_runs), "--label", "probe"])
    lines = output.splitlines()
    first_annotation = next(i for i, l in enumerate(lines) if l.startswith("::error"))
    first_dump = next(i for i, l in enumerate(lines) if "the runner's own record" in l)
    assert first_annotation < first_dump, (
        "the dump was printed before the annotation, so an encoding fault in "
        "the dump would take the annotation with it\n%s" % output)


def test_a_clean_run_emits_nothing_and_exits_zero(clean_runs):
    """⭐ THE OTHER HALF OF THE PROOF. A reporter that annotates every run
    trains people to ignore the one channel that works."""
    code, output = call(REPORTER, ["--runs", str(clean_runs)])
    assert code == 0, "the reporter exited %d on a clean run\n%s" % (code, output)
    assert not annotations(output), (
        "an annotation was emitted for a run with no failures\n%s" % output)


def test_require_failures_speaks_up_when_the_job_is_red_and_no_test_failed(clean_runs):
    """⚠ The job is red and every testcase passed: a LATER step failed. Saying
    nothing there is how a red run becomes unreadable."""
    code, output = call(REPORTER, ["--runs", str(clean_runs), "--require-failures"])
    assert code != 0
    found = annotations(output)
    assert found, output
    assert "NOT ONE testcase failed" in found[0][1], found[0][1]


def test_no_run_directory_at_all_is_reported_differently(tmp_path):
    """⚠ Three diagnoses, and telling them apart is the value of this branch."""
    missing = tmp_path / "never-created"
    code, output = call(REPORTER, ["--runs", str(missing), "--require-failures"])
    assert code != 0
    assert "no JUnit XML at all" in annotations(output)[0][1], output

    code, output = call(REPORTER, ["--runs", str(missing)])
    assert code == 0 and not annotations(output), output


def test_an_unreadable_xml_is_named_rather_than_skipped(tmp_path):
    """⚠ A truncated XML is what a killed or out-of-disk runner leaves."""
    write(tmp_path / "_runs" / "stamp" / "truncated.xml", u"<testsuite><testcase")
    code, output = call(REPORTER, ["--runs", str(tmp_path / "_runs")])
    assert code != 0, "a corrupt XML was read as a clean run\n%s" % output
    assert "UNREADABLE" in annotations(output)[0][1], output


def test_the_annotation_is_capped_and_says_how_many_it_dropped(tmp_path):
    """⚠ The API truncates a long annotation, and a truncated one that lost the
    test NAMES is worth nothing."""
    cases = u"".join(
        u'<testcase classname="t" name="test_%d"><failure message="boom %d"/>'
        u'</testcase>' % (n, n) for n in range(4))
    write(tmp_path / "_runs" / "stamp" / "many.xml",
          u"<testsuite>%s</testsuite>" % cases)
    code, output = call(REPORTER, ["--runs", str(tmp_path / "_runs"), "--max", "2"])
    assert code != 0
    body = annotations(output)[0][1]
    assert "...and 2 more" in body, body
    assert "test_0" in body and "test_1" in body, body


def test_errors_count_as_well_as_failures(tmp_path):
    """⚠ A collection error is an `<error>`, not a `<failure>`. Reading only
    failures reports a red run as clean."""
    write(tmp_path / "_runs" / "stamp" / "err.xml",
          u'<testsuite><testcase classname="t" name="test_x">'
          u'<error message="import blew up"/></testcase></testsuite>')
    code, output = call(REPORTER, ["--runs", str(tmp_path / "_runs")])
    assert code != 0, output
    assert "ERROR" in annotations(output)[0][1], output


def test_the_step_summary_is_written_but_is_never_load_bearing(failing_runs, tmp_path):
    summary = tmp_path / "summary.md"
    code, output = call(REPORTER, ["--runs", str(failing_runs),
                                   "--summary", str(summary)])
    assert code != 0
    assert summary.exists() and "test_detail_is_on_the_second_line" in \
        summary.read_text(encoding="utf-8")
    # ⚠ And an unwritable summary must not cost the annotation.
    code, output = call(REPORTER, ["--runs", str(failing_runs),
                                   "--summary", str(tmp_path / "nope" / "x.md")])
    assert annotations(output), (
        "a summary that could not be written took the annotation with it\n%s"
        % output)


# ---------------------------------------------------------------------------
# check_docs.py -- and the failure mode is PASSING ON AN EMPTY SET
# ---------------------------------------------------------------------------

def test_nothing_to_check_is_loud_and_non_zero(tmp_path):
    """⛔ `docs/` does not exist yet. Exiting 0 here is `0 broken of 0`."""
    code, output = call(CHECK_DOCS, ["--docs", str(tmp_path / "no-docs"),
                                     "--examples", str(tmp_path / "no-examples")])
    assert code != 0, "0 blocks and 0 examples passed silently\n%s" % output
    assert "NOTHING HERE TO CHECK" in output, output


def test_allow_empty_passes_but_says_it_proved_nothing(tmp_path):
    code, output = call(CHECK_DOCS, ["--docs", str(tmp_path / "no-docs"),
                                     "--examples", str(tmp_path / "no-examples"),
                                     "--allow-empty"])
    assert code == 0, output
    assert "PROVED NOTHING" in output.upper(), output
    assert "SKIP" in output, output


def test_a_block_naming_something_the_package_lacks_is_rejected(tmp_path):
    """⭐ The positive control: the checker must be able to go red."""
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"# Usage\n\n```python\nimport hato\nhato.does_not_exist()\n```\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs),
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"])
    assert code != 0, "a call to hato.does_not_exist() passed\n%s" % output
    assert "does_not_exist" in output, output


def test_a_real_reference_is_accepted(tmp_path):
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"# Usage\n\n```python\nimport hato\nprint(hato.__version__)\n"
          u"from hato import paths\nprint(paths.data_root())\n```\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs),
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"])
    assert code == 0, output
    assert "1 python block" in output, output


def test_a_block_that_does_not_compile_is_rejected(tmp_path):
    docs = tmp_path / "docs"
    write(docs / "USAGE.md", u"```python\ndef broken(:\n```\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs),
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"])
    assert code != 0 and "does not compile" in output, output


def test_prose_mentioning_a_path_is_not_read_as_an_api_call(tmp_path):
    """⚠ `hato.log` and `hato.config.json` are FILES. Scanning raw prose for
    `hato.<word>` turned both into confident, wrong findings."""
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"The run log is `hato.log` and the dev config is `hato.config.json`.\n"
          u"\n```python\nimport hato\nprint(hato.__version__)\n```\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs),
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"])
    assert code == 0, output


def test_an_example_that_does_not_compile_is_rejected(tmp_path):
    """⚠ THE FIRST FIXTURE HERE WAS `this is not python`, WHICH COMPILES --
    `this is not python` is a valid expression statement (a name, `is not`, a
    name) and fails only at runtime. The check was correct and the FIXTURE was
    vacuous; doctrine/verification: "the fixture is the first suspect"."""
    examples = tmp_path / "examples"
    write(examples / "one.py", u"import hato\ndef broken(:\n")
    code, output = call(CHECK_DOCS, ["--docs", str(tmp_path / "none"),
                                     "--examples", str(examples)])
    assert code != 0 and "does not compile" in output, output


def test_no_annotation_title_carries_a_raw_colon_or_comma(failing_runs, tmp_path):
    """🚨 FOUND BY THIS HARNESS, 2026-09-17. GitHub splits a workflow command
    on `::` and reads its properties as a comma-separated `k=v` list, so a raw
    `:` or `,` inside `title=` eats the rest of the line. A title reading
    `failures: no run log` produced a line no annotation parser matched -- the
    reporter emitted something and the channel carried nothing, which is P15's
    shape wearing different clothes."""
    runs = [(REPORTER, ["--runs", str(failing_runs), "--label", "os: py3.12"]),
            (REPORTER, ["--runs", str(tmp_path / "gone"), "--require-failures"])]
    for script, args in runs:
        _code, output = call(script, args)
        lines = [l for l in output.splitlines() if l.startswith("::error")]
        assert lines, "no annotation at all from %s\n%s" % (args, output)
        for line in lines:
            title = line[len("::error "):].split("::", 1)[0]
            assert title.startswith("title="), line
            assert ":" not in title[len("title="):], \
                "a raw colon in the title breaks the command: %s" % line
            assert "," not in title[len("title="):], \
                "a raw comma in the title ends the property list: %s" % line


def _stub_package(tmp_path, body):
    """A throwaway importable package, so the field-table check does not wait
    on hato's own public API landing in a sibling builder's file."""
    pkg = tmp_path / "site" / "stubpkg"
    write(pkg / "__init__.py", body)
    return tmp_path / "site"


def test_a_field_table_naming_a_field_the_class_lacks_is_rejected(tmp_path):
    site = _stub_package(tmp_path, u'''
__version__ = "0.0.0"


class Result(object):
    __slots__ = ("video", "subtitle", "verdict", "offset", "matched")
''')
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"| `Result` field | Holds |\n| --- | --- |\n"
          u"| `video` | the video |\n| `subtitle` | the subtitle |\n"
          u"| `verdict` | the verdict |\n| `offset` | the offset |\n"
          u"| `matched` | the match rate |\n| `nonsense` | nothing at all |\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs), "--package", "stubpkg",
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"],
                        env={"PYTHONPATH": str(site)})
    assert code != 0, output
    assert "`nonsense`" in output, output


def test_a_field_table_that_reads_almost_nothing_is_a_problem(tmp_path):
    """⚠ The vacuity guard on the check itself: a row format that stopped
    matching reads 0 fields and reports 0 problems."""
    site = _stub_package(tmp_path, u'''
__version__ = "0.0.0"


class Result(object):
    __slots__ = ("video",)
''')
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"| `Result` field | Holds |\n| --- | --- |\n| `video` | the video |\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs), "--package", "stubpkg",
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"],
                        env={"PYTHONPATH": str(site)})
    assert code != 0, output
    assert "proves little" in output, output


def test_a_documented_class_the_package_does_not_export_is_rejected(tmp_path):
    site = _stub_package(tmp_path, u'__version__ = "0.0.0"\n')
    docs = tmp_path / "docs"
    write(docs / "USAGE.md", u"| `Result` field | Holds |\n| --- | --- |\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs), "--package", "stubpkg",
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"],
                        env={"PYTHONPATH": str(site)})
    assert code != 0, output
    assert "does not export Result" in output, output


def test_check_docs_emits_ascii_and_an_annotation_under_actions(tmp_path):
    docs = tmp_path / "docs"
    write(docs / "USAGE.md",
          u"# 使い方\n\n```python\nimport hato\nhato.nope()\n```\n")
    code, output = call(CHECK_DOCS, ["--docs", str(docs),
                                     "--examples", str(tmp_path / "none"),
                                     "--allow-empty"],
                        env={"GITHUB_ACTIONS": "true"})
    assert code != 0
    assert_ascii(output, "check_docs.py")
    assert annotations(output), output


# ---------------------------------------------------------------------------
# outside_checkout.py -- pitfall P6, and the parent walk
# ---------------------------------------------------------------------------

def _fake_install(tmp_path_factory):
    """A venv whose site-packages holds a COPY of `hato`, and nothing else.

    ⭐ This is the only way to get an all-green run of the guard on this machine:
    there is no `pip install hato` here (no `pyproject.toml` yet -- a sibling
    builder is writing it), so the package is placed the way an install places
    it and imported with NO `PYTHONPATH`. ⛔ `--system-site-packages` so `tomli`
    is importable on Python 3.10, where `tomllib` does not exist.
    """
    base = tmp_path_factory.mktemp("install")
    venv = base / "venv"
    proc = subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                           "--system-site-packages", str(venv)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=600)
    if proc.returncode != 0:
        pytest.skip("could not create a venv: %s"
                    % proc.stdout.decode("utf-8", "replace")[-400:])
    sites = list(venv.glob("lib/python*/site-packages")) + \
        list(venv.glob("Lib/site-packages"))
    if not sites:
        pytest.skip("no site-packages in the venv at %s" % venv)
    shutil.copytree(str(ROOT / "hato"), str(sites[0] / "hato"),
                    ignore=shutil.ignore_patterns("__pycache__", "dev"))
    python = venv / "Scripts" / "python.exe"
    if not python.exists():
        python = venv / "bin" / "python"
    if not python.exists():
        pytest.skip("no interpreter in the venv at %s" % venv)
    # ⛔ The working directory must have NOTHING above it. tmp_path_factory's
    # root is outside the checkout, which is the whole point.
    outside = base / "outside"
    outside.mkdir()
    return python, outside


@pytest.fixture(scope="module")
def fake_install(tmp_path_factory):
    return _fake_install(tmp_path_factory)


SCRUB = {"HATO_CACHE": None, "HATO_CONFIG": None, "HATO_KEYFILE": None,
         "HATO_JIMAKU_KEY": None, "HATO_TEST_ROOT": None, "PYTHONPATH": None,
         "HATO_NO_NETWORK": None}


def test_an_installed_hato_outside_every_checkout_passes_every_claim(fake_install):
    """🚨 THE CLAIM PITFALL P6 IS ABOUT. `config.load()` and the cache paths
    resolve with no `hato.config.json` anywhere above the package OR the cwd."""
    python, outside = fake_install
    code, output = call(OUTSIDE, ["--forbid-under", str(ROOT), "--skip-cli"],
                        cwd=outside, env=SCRUB, python=str(python))
    assert code == 0, (
        "the installed package FAILED outside a checkout -- this is exactly the "
        "defect that shipped as tsubasa 0.1.0\n%s" % output)
    for claim in ("env_overrides_absent", "cwd_no_dev_config",
                  "cwd_no_source_tree", "imported_from_install",
                  "package_no_dev_config", "find_project_config_none",
                  "cache_paths_resolve", "data_root_is_the_default",
                  "config_loads"):
        assert re.search(r"ok\s+%s\b" % claim, output), \
            "claim %r did not report ok:\n%s" % (claim, output)


def test_the_guard_goes_red_inside_the_checkout(fake_install):
    """⭐ THE POSITIVE CONTROL. Run from the source tree, the guard must FAIL --
    a guard that passes everywhere is not a guard. doctrine/evidence: "make the
    instrument disagree with something you already know"."""
    python, _outside = fake_install
    code, output = call(OUTSIDE, ["--forbid-under", str(ROOT), "--skip-cli"],
                        cwd=ROOT, env=SCRUB, python=str(python))
    assert code == 1, "the guard passed inside the checkout\n%s" % output
    assert re.search(r"FAIL\s+cwd_no_dev_config", output), output
    assert re.search(r"FAIL\s+cwd_no_source_tree", output), output
    assert "hato.config.json" in output


def test_the_walk_really_climbs_every_parent(fake_install, tmp_path):
    """🚨 THE PARENT WALK, WHICH THE SIBLING PROJECT DID BY HAND, ONCE.

    Its guard was `test ! -e tsubasa.config.json` in the working directory, and
    the doc says of it: "It checks the working directory only". So the config is
    planted FOUR levels up, where a working-directory check cannot see it.
    """
    python, _outside = fake_install
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    write(tmp_path / "a" / "hato.config.json", u'{"project": "hato"}')
    code, output = call(OUTSIDE, ["--skip-cli"], cwd=deep, env=SCRUB,
                        python=str(python))
    assert code == 1, (
        "a hato.config.json four directories up was not found: the walk does "
        "not climb\n%s" % output)
    assert re.search(r"FAIL\s+cwd_no_dev_config", output), output
    walked = re.search(r"walking (\d+) directories", output)
    assert walked and int(walked.group(1)) >= 5, (
        "the walk reported %s directories from a path five deep -- the "
        "denominator says it stopped early\n%s"
        % (walked and walked.group(1), output))


def test_a_dev_config_above_the_INSTALLED_PACKAGE_is_found(fake_install, tmp_path):
    """🚨 THE CHAIN THE SIBLING PROJECT'S GUARD COULD NOT SEE AT ALL.

    `hato/paths.py::find_project_config(start=None)` walks up from
    `paths.PACKAGE_DIR` -- the INSTALLED package's own folder -- so a
    `hato.config.json` sitting in site-packages, or in the venv root, is read by
    every installed user no matter where they are standing. The sibling's guard
    was `test ! -e tsubasa.config.json` in the WORKING DIRECTORY, which is
    structurally blind to this.

    ⭐ So: the working directory is clean and the PACKAGE's chain is not, and the
    two claims must disagree. ⚠ Restored afterwards, because the fake install is
    module-scoped and every later check reads it.
    """
    python, outside = fake_install

    # 🚨 ASK THE INTERPRETER; DO NOT DO PATH ARITHMETIC ON IT.
    #
    # This block used to be `Path(python).resolve().parent.parent` followed by a
    # glob for `lib/python*/site-packages` / `Lib/site-packages`. It was green on
    # Windows and failed on BOTH macOS and ubuntu, on every Python -- 8 of the
    # 12 matrix jobs in the public repo's second CI run.
    #
    # ⛔ THE CAUSE: in a POSIX venv `bin/python` is a SYMLINK to the system
    # interpreter, so `.resolve()` follows it out of the venv entirely
    # (`/usr/...`), and the glob then planted nothing the guard would ever walk.
    # On Windows the venv's python is a real copy, so `.resolve()` stays put and
    # the same code was correct. ⚠ Pitfall P11 exactly: a test encoding one
    # platform's path semantics without saying so.
    #
    # ⭐ `sysconfig.get_paths()["purelib"]` is what that interpreter itself will
    # import from, on every platform, symlinks or not -- and it is the same
    # answer `paths.PACKAGE_DIR` is derived from, which is the thing under test.
    # ⚠ subprocess directly: `call()` prepends a SCRIPT path, and this needs
    # `python -c`. Passing None through it yields a literal "None" argument.
    probe = subprocess.run(
        [str(python), "-c",
         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = probe.stdout.decode("utf-8", "replace")
    purelib = None
    if probe.returncode == 0 and out.strip():
        purelib = Path(out.strip().splitlines()[-1].strip())
    if purelib is None or not purelib.is_dir():
        raise AssertionError(
            "could not ask the fake install where it imports from: exit %s, "
            "output %r. Not a skip -- a skip here is what let a POSIX-only "
            "failure hide for an entire CI run." % (probe.returncode, out[:400]))

    planted = purelib / "hato.config.json"
    write(planted, u'{"project": "hato"}')
    try:
        code, output = call(OUTSIDE, ["--skip-cli"], cwd=outside, env=SCRUB,
                            python=str(python))
        assert code == 1, (
            "a hato.config.json IN SITE-PACKAGES was not found. Every installed "
            "user would read it, and a working-directory check cannot see "
            "it.\n%s" % output)
        assert re.search(r"FAIL\s+package_no_dev_config", output), output
        # ⭐ THE DIFFERENTIAL: the cwd chain is still clean, so this is not the
        # cwd check firing under another name.
        assert re.search(r"ok\s+cwd_no_dev_config", output), (
            "the cwd claim also failed, so this proves nothing about the "
            "package chain\n%s" % output)
        assert re.search(r"FAIL\s+find_project_config_none", output), (
            "paths.find_project_config() did not report the planted file, so "
            "the claim above is not measuring hato's own mechanism\n%s" % output)
    finally:
        planted.unlink()


def test_an_env_override_is_refused_as_a_precondition(fake_install):
    """⭐ Without this claim, every path claim below it could be green because a
    harness pointed HATO_CACHE at a temp directory."""
    python, outside = fake_install
    env = dict(SCRUB)
    env["HATO_CACHE"] = str(outside / "elsewhere")
    code, output = call(OUTSIDE, ["--skip-cli"], cwd=outside, env=env,
                        python=str(python))
    assert code == 1, output
    assert re.search(r"FAIL\s+env_overrides_absent", output), output
    assert "HATO_CACHE" in output


def test_pythonpath_pointing_at_the_checkout_is_caught(fake_install):
    """🚨 `PYTHONPATH="$PWD"` IS HOW THE SIBLING'S EXAMPLES IMPORTED THE
    CHECKOUT while running "outside" it."""
    python, outside = fake_install
    env = dict(SCRUB)
    env["PYTHONPATH"] = str(ROOT)
    code, output = call(OUTSIDE, ["--forbid-under", str(ROOT), "--skip-cli"],
                        cwd=outside, env=env, python=str(python))
    assert code == 1, output
    assert re.search(r"FAIL\s+(env_overrides_absent|imported_from_install)",
                     output), output


def test_the_guard_reports_a_missing_package_as_a_tooling_fault(tmp_path):
    """⛔ Exit 2, not 1. A guard that cannot import the thing it guards has
    proved nothing either way (doctrine/verification)."""
    code, output = call(OUTSIDE, ["--skip-cli"], cwd=tmp_path,
                        env={"PYTHONPATH": str(tmp_path), "PYTHONHOME": None,
                             "HATO_CACHE": None, "HATO_CONFIG": None},
                        python=sys.executable)
    if code == 0:
        pytest.skip("hato is importable from a bare interpreter on this machine")
    assert code in (1, 2), output
    if code == 2:
        assert "TOOLING FAULT" in output and "could not import hato" in output


def test_the_guard_emits_ascii_only(fake_install):
    python, outside = fake_install
    _code, output = call(OUTSIDE, ["--skip-cli"], cwd=outside, env=SCRUB,
                         python=str(python))
    assert_ascii(output, "outside_checkout.py")


# ---------------------------------------------------------------------------
# the workflows -- parsed, never eyeballed
# ---------------------------------------------------------------------------

def _load_workflows():
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML is not installed here; the workflows are parsed "
                       "in CI by the `yamllint`-free probe in the report and by "
                       "GitHub itself. ⛔ A skip is not a pass.")
    loaded = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        with io.open(str(path), encoding="utf-8") as fh:
            loaded[path.name] = yaml.safe_load(fh)
    return loaded


#: 🚨 INSTRUMENT FAULT, MEASURED 2026-09-17. On this machine `bash` on PATH is
#: `C:\\Windows\\System32\\bash.exe` -- WSL's launcher -- which has no installed
#: distribution and answers EVERY script with "Windows Subsystem for Linux has
#: no installed distributions", in UTF-16, exit non-zero. Twelve blocks reported
#: FAIL and not one had been parsed. doctrine/evidence: a miss must be a MISS.
BASH_CANDIDATES = (r"C:\Program Files\Git\bin\bash.exe",
                   r"C:\Program Files\Git\usr\bin\bash.exe",
                   "/bin/bash", "/usr/bin/bash")
EXPRESSION = re.compile(r"\$\{\{[^}]*\}\}")
RUN_BLOCK = re.compile(r"^(\s*)run:\s*\|\s*$")
HEREDOC_START = re.compile(r"<<'PY'\s*$")


def _real_bash():
    for candidate in BASH_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("bash")
    if found and "ystem32" not in found:
        return found
    return None


def _run_blocks(path):
    """-> [(line number, de-indented body), ...] for every `run: |` block.

    🚨 THE DE-INDENT IS LOAD-BEARING. YAML strips the common leading
    indentation of a block scalar. MEASURED 2026-09-17: the first version of
    this check handed bash the raw lines, so every heredoc terminator (`PY`)
    still carried ten spaces. `<<'PY'` needs it ALONE at column 0, so the
    heredoc was never closed -- bash said "here-document delimited by
    end-of-file" and STILL EXITED 0, and fourteen blocks read as parsed while
    the part that would break on a runner had not been looked at.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    out, index = [], 0
    while index < len(lines):
        match = RUN_BLOCK.match(lines[index])
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        start = index + 1
        body = []
        index = start
        while index < len(lines):
            line = lines[index]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            body.append(line)
            index += 1
        real = [l for l in body if l.strip()]
        shift = min((len(l) - len(l.lstrip()) for l in real), default=0)
        out.append((start + 1,
                    "\n".join(l[shift:] if l.strip() else "" for l in body)))
    return out


def _heredocs(block):
    lines = block.splitlines()
    out, index = [], 0
    while index < len(lines):
        if not HEREDOC_START.search(lines[index]):
            index += 1
            continue
        index += 1
        body = []
        while index < len(lines) and lines[index].rstrip() != "PY":
            body.append(lines[index])
            index += 1
        out.append("\n".join(body) + "\n")
        index += 1
    return out


def test_every_run_block_parses_as_bash():
    """⭐ The workflows have never run, so this is the only thing that reads
    their shell. It caught a real bug in `release.yml`: a prose mention of a
    command inside a double-quoted `echo` -- `like this` -- is COMMAND
    SUBSTITUTION to bash, and it would have RE-RUN the command that had just
    failed, inside the error message reporting the failure."""
    bash = _real_bash()
    if bash is None:
        pytest.skip("no real bash found; WSL's launcher answers every block "
                    "identically and would report every one as a failure")
    total = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, body in _run_blocks(path):
            total += 1
            script = EXPRESSION.sub("EXPR", body)
            proc = subprocess.run([bash, "-n"], input=script.encode("utf-8"),
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=120)
            noise = proc.stdout.decode("utf-8", "replace")
            assert proc.returncode == 0, \
                "%s:%d is not valid bash:\n%s\n--- the block ---\n%s" \
                % (path.name, line_number, noise, script)
            # ⚠ AN UNTERMINATED HEREDOC EXITS 0 with a warning. The return code
            # cannot see it.
            assert "delimited by end-of-file" not in noise, \
                "%s:%d leaves a heredoc unclosed:\n%s" \
                % (path.name, line_number, noise)
    assert total >= 10, "only %d run blocks found; the parser stopped early" % total


def test_no_double_quoted_echo_contains_a_backtick():
    """⛔ The bug `test_every_run_block_parses_as_bash` cannot see: a backtick
    inside double quotes parses perfectly and runs a command."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, body in _run_blocks(path):
            for offset, line in enumerate(body.splitlines(), line_number):
                if line.strip().startswith('echo "'):
                    assert "`" not in line, \
                        "%s:%d a backtick in a double-quoted echo is command " \
                        "substitution: %s" % (path.name, offset, line.strip())


def test_the_python_inside_every_heredoc_compiles():
    """⚠ `bash -n` treats a heredoc body as opaque text, so a syntax error in
    one of these probes would first appear on a runner."""
    total = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, body in _run_blocks(path):
            for number, source in enumerate(_heredocs(body), 1):
                total += 1
                try:
                    compile(source, "%s:%d heredoc %d"
                            % (path.name, line_number, number), "exec")
                except SyntaxError as exc:
                    raise AssertionError(
                        "%s:%d heredoc %d is not valid Python: %s\n%s"
                        % (path.name, line_number, number, exc, source))
    assert total >= 3, (
        "only %d heredocs found. The workflows drive their probes through "
        "`python - <<'PY'` blocks; finding none means this check reads nothing."
        % total)


def test_the_workflows_parse_as_yaml():
    """⛔ Do not eyeball YAML. Parse it."""
    loaded = _load_workflows()
    assert set(loaded) == {"ci.yml", "release.yml"}, sorted(loaded)
    for name, doc in loaded.items():
        assert isinstance(doc, dict), name
        assert doc.get("jobs"), "%s declares no jobs" % name
        for job_name, job in doc["jobs"].items():
            assert job.get("runs-on"), "%s::%s has no runs-on" % (name, job_name)
            assert job.get("steps") or job.get("uses"), \
                "%s::%s has no steps" % (name, job_name)


def test_no_workflow_reads_a_secret():
    """⛔ Trusted Publishing is OIDC. There is nothing else to authenticate, and
    the absence of a secret is a property worth keeping."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "secrets." not in stripped, \
                "%s reads a secret: %s" % (path.name, stripped)


def test_no_script_of_ours_is_wrapped_in_or_true():
    """🚨 P15's SILENCER. `|| true` is what swallowed the reporter's corpse."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if "|| true" not in line:
                continue
            assert not re.search(r"\.github/scripts/\S+\.py", line), \
                "%s:%d wraps one of our scripts in `|| true`: %s" \
                % (path.name, number, line.strip())
            assert "hato.dev" not in line, \
                "%s:%d wraps the release tooling in `|| true`: %s" \
                % (path.name, number, line.strip())


def test_no_workflow_can_publish_anything_anywhere():
    """🚨 RULED BY SONIC 2026-09-17: hato ships as a STANDALONE, not a package.

    *"we don't need the pypi… it's mainly just a github usage that will need the
    gui for an actual github release"*, and *"hato is more of a standalone than
    tsubasa is, in the sense that tsubasa is implemented into other codebases,
    this will likely not be until further notice."*

    ⭐ THIS CHECK REPLACED A WEAKER ONE, AND THE INVERSION IS THE POINT. It used
    to be `test_publish_cannot_run_without_a_version_tag`, which asserted that
    `release.yml`'s publish job EXISTED and was gated on a `v*` tag -- the right
    guarantee while PyPI was in scope, and it is the check that caught the
    sibling project's `workflow_dispatch` hole. The ruling did not relax that
    requirement, it made a stronger one available: there is no publish job at
    all, so the irreversible half is **structurally absent rather than gated**.

    ⛔ An `if:` condition is one edit away from being true. An absent capability
    is not. If PyPI ever returns, this check is the thing that must be
    deliberately rewritten -- which is the intended cost.
    """
    doc = _load_workflows()["release.yml"]
    assert "publish" not in doc["jobs"], (
        "release.yml has a `publish` job again; hato publishes nowhere until "
        "Sonic rules otherwise (spec/10-deployment.md)")

    # ⛔ Not just release.yml, and not just a job NAME -- the capabilities.
    for name, wf in sorted(_load_workflows().items()):
        for job_name, job in sorted((wf.get("jobs") or {}).items()):
            perms = job.get("permissions") or {}
            if isinstance(perms, dict):
                assert perms.get("id-token") != "write", (
                    "%s job %r grants id-token: write, which exists only to "
                    "authenticate an upload" % (name, job_name))
            assert str(job.get("environment") or "") != "pypi", (
                "%s job %r references the pypi environment; no such environment "
                "exists and nothing should ask for one" % (name, job_name))

    # the action itself, read from the text so a comment cannot hide it
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for forbidden in ("gh-action-pypi-publish", "twine upload",
                              "softprops/action-gh-release", "gh release create"):
                assert forbidden not in stripped, (
                    "%s:%d would publish an artifact (%s); hato uploads nowhere "
                    "until Sonic rules otherwise" % (path.name, number, forbidden))


def test_the_live_api_suite_is_never_run_by_a_workflow():
    """🚨 jimaku's budget is 25 requests / 60 s on somebody else's server, and
    failed requests count. The live suite is opt-in by configuration."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for forbidden in ("HATO_LIVE", "test_live.py", "--suite live",
                              "hato doctor", "python -m hato doctor"):
                assert forbidden not in stripped, \
                    "%s:%d would reach the live API: %s" \
                    % (path.name, number, stripped)


def test_every_pinned_action_is_one_we_checked_for_node24():
    """⚠ PITFALL P19. Node 20 leaves GitHub's runners 2026-09-23, and a version
    number does not tell you the runtime: `upload-artifact@v5`,
    `download-artifact@v5` and `download-artifact@v6` are all still node20.
    Each version below was read from that action's own `action.yml` on
    2026-09-17. ⛔ Adding an action means reading its `action.yml` first."""
    verified_node24 = {
        "actions/checkout@v5", "actions/setup-python@v6",
        "actions/upload-artifact@v7", "actions/download-artifact@v7",
        # a composite action -- no JavaScript runtime to age out
        "pypa/gh-action-pypi-publish@release/v1",
    }
    used = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = re.match(r"-?\s*uses:\s*(\S+)", stripped)
            if match:
                used.add(match.group(1))
    unchecked = used - verified_node24
    assert not unchecked, (
        "these actions are used and their `runs.using` was never read: %s"
        % sorted(unchecked))
    assert used, "no `uses:` in any workflow at all"


# ---------------------------------------------------------------------------
# ci_verdict.py -- the gate `publish` needs, so it is the gate
# ---------------------------------------------------------------------------

VERDICT = SCRIPTS / "ci_verdict.py"


def _runs(tmp_path, payload):
    return write(tmp_path / "runs.json", json.dumps(payload))


def test_a_successful_run_reads_as_success(tmp_path):
    path = _runs(tmp_path, {"workflow_runs": [
        {"run_number": 7, "run_attempt": 1, "status": "completed",
         "conclusion": "success", "html_url": "u"}]})
    code, output = call(VERDICT, [str(path)])
    assert code == 0 and output.startswith("success"), output


def test_a_failed_run_reads_as_failed(tmp_path):
    path = _runs(tmp_path, {"workflow_runs": [
        {"run_number": 7, "run_attempt": 1, "status": "completed",
         "conclusion": "failure", "html_url": "u"}]})
    code, output = call(VERDICT, [str(path)])
    assert code == 0 and output.startswith("failed"), output


def test_a_run_still_going_reads_as_pending_not_as_failure(tmp_path):
    """⚠ "not finished" must not read as "not green" -- a tag pushed seconds
    after its branch finds `tests` still running."""
    path = _runs(tmp_path, {"workflow_runs": [
        {"run_number": 7, "run_attempt": 1, "status": "in_progress",
         "conclusion": None}]})
    code, output = call(VERDICT, [str(path)])
    assert code == 0 and output.startswith("pending"), output


def test_the_newest_completed_attempt_wins(tmp_path):
    """⚠ A commit can carry a failure and then a successful re-run -- and the
    reverse. "Any success in the list" would accept an old success followed by
    a real failure."""
    path = _runs(tmp_path, {"workflow_runs": [
        {"run_number": 7, "run_attempt": 1, "status": "completed",
         "conclusion": "success", "html_url": "old"},
        {"run_number": 7, "run_attempt": 2, "status": "completed",
         "conclusion": "failure", "html_url": "new"}]})
    code, output = call(VERDICT, [str(path)])
    assert output.startswith("failed"), output
    assert "attempt 2" in output, output


def test_no_run_at_all_is_missing_not_success(tmp_path):
    path = _runs(tmp_path, {"workflow_runs": []})
    code, output = call(VERDICT, [str(path)])
    assert code == 0 and output.startswith("missing"), output


def test_an_api_error_payload_names_the_permission_problem(tmp_path):
    """⚠ "Resource not accessible by integration" means the job is missing
    `actions: read` -- an entirely different problem from "CI has not run"."""
    path = _runs(tmp_path, {"message": "Resource not accessible by integration"})
    code, output = call(VERDICT, [str(path)])
    assert output.startswith("missing") and "not accessible" in output, output


def test_an_unreadable_payload_is_missing_and_still_exits_zero(tmp_path):
    """⛔ The caller is a `while` loop under `set -e`. A non-zero exit here
    aborts the loop instead of producing a verdict."""
    path = write(tmp_path / "runs.json", u"{not json")
    code, output = call(VERDICT, [str(path)])
    assert code == 0, "exited %d, which would abort the gate's loop" % code
    assert output.startswith("missing"), output

    code, output = call(VERDICT, [str(tmp_path / "absent.json")])
    assert code == 0 and output.startswith("missing"), output


def test_a_grep_for_success_would_have_been_wrong(tmp_path):
    """🚨 THE REASON THIS IS A PARSER AND NOT `grep -q success`. The payload
    carries the word `success` in every run's URLs while the run itself is
    unfinished, and a whole-document grep cannot make a per-run decision."""
    path = _runs(tmp_path, {"workflow_runs": [
        {"run_number": 7, "run_attempt": 1, "status": "in_progress",
         "conclusion": None,
         "display_title": "fix: report success without a token",
         "html_url": "https://github.com/x/y/actions/runs/1"}]})
    raw = path.read_text(encoding="utf-8")
    # ⚠ THE CONTROL FIRST. If the literal word were not in the payload, this
    # test would prove nothing about grep and would still pass.
    assert "success" in raw, "the fixture does not contain the word grep matches"
    code, output = call(VERDICT, [str(path)])
    assert output.startswith("pending"), (
        "`grep -q success` would have said green here, and the run has not "
        "finished\n%s" % output)
