# -*- coding: utf-8 -*-
"""The docs may not drift from the API they describe.

    python .github/scripts/check_docs.py --docs docs --examples examples
    python .github/scripts/check_docs.py --allow-empty      # until the docs land

Checked against the `hato` that is INSTALLED -- never against the source tree,
because the claim is about what a reader of the published package gets:

  * every ```python block in the docs compiles, and every example file compiles;
  * every `hato.<name>` the code in them uses exists;
  * every field a documented field table names is a real field of that class.

Exit 0 when everything holds; 1 naming each problem; 2 when this tool itself
could not run.

===========================================================================
⛔ THE FAILURE MODE THIS FILE IS SHAPED AGAINST: PASSING BECAUSE THERE WAS
   NOTHING TO CHECK
===========================================================================
`docs/` and `examples/` do not exist yet -- they are a later wave. A docs
checker that exits 0 on a missing directory is the "0 broken of 0" pass
doctrine/verification names:

  "It passed on an empty set. `No broken images` reported `0 broken of 0` --
   the fixture had none at all. Print the denominator in the detail string, so
   a vacuous pass is visible at a glance."

⭐ So ZERO BLOCKS IS A FAILURE, LOUDLY, and `--allow-empty` is the only way to
get a pass out of it -- which makes the exemption a visible decision in the
workflow file rather than a property of this script. ⛔ Remove `--allow-empty`
from `ci.yml` the day `docs/` lands; until then a green run here means
"nothing to check", and it SAYS so on every line.

⚠ A name is only counted as API USAGE when it appears in a ```python block, in
an `import`, or in an example file. Prose mentions a path called `hato.log` and
a config called `hato.config.json`; scanning raw prose for `hato.<word>` turned
those into two confident, wrong findings, and a checker that cries wolf is a
checker somebody switches off (doctrine/evidence).
"""
import argparse
import importlib
import io
import os
import re
import sys

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_FAULT = 2

#: ```python fenced blocks. ⚠ `py` and `python3` are the same claim.
BLOCK = re.compile(r"```(?:python|py|python3)[^\n]*\n(.*?)```", re.S)
#: `hato.<name>` -- collected only from code, never from prose. See the header.
REFERENCE = re.compile(r"\bhato\.([A-Za-z_]\w*)")
#: `import hato.x` / `from hato.x import y`, anywhere in the file.
IMPORTS = re.compile(r"^\s*(?:import|from)\s+hato\.([A-Za-z_]\w*)", re.M)
#: A documented field table: `| `Result` field | Holds |`, or any class name.
FIELD_TABLE = re.compile(r"^\|\s*`?(\w+)`?\s+fields?\s*\|", re.I | re.M)
#: Backticked identifiers inside a table row's first cell.
CELL_NAMES = re.compile(r"`(\w+)`")
#: Names that look like a file extension, not an attribute. Reported, not hidden.
EXTENSION_LIKE = frozenset((
    "json", "log", "toml", "cmd", "exe", "py", "md", "txt", "lock", "db",
    "config", "ini", "yml", "yaml", "zip", "whl", "cfg"))


def ascii_only(text):
    """⚠ ASCII out, always. This project's docs carry Japanese, and a reporter
    that dies on its own subject matter is `report_failures.py`'s pitfall P15."""
    if not isinstance(text, type(u"")):
        text = u"%s" % (text,)
    return text.encode("ascii", "backslashreplace").decode("ascii")


def read(path):
    return io.open(path, encoding="utf-8").read()


def markdown_files(directory):
    out = []
    for where, _dirs, files in os.walk(directory):
        for name in sorted(files):
            if name.lower().endswith(".md"):
                out.append(os.path.join(where, name))
    return sorted(out)


def python_files(directory):
    out = []
    for where, _dirs, files in os.walk(directory):
        for name in sorted(files):
            if name.endswith(".py"):
                out.append(os.path.join(where, name))
    return sorted(out)


def real_fields(cls):
    """Every name `cls` genuinely carries: slots up the MRO, properties,
    dataclass fields, annotations.

    ⚠ `__slots__` ALONE IS NOT THE ANSWER. A class using plain attributes, a
    dataclass, or a base class's slots would come back with an empty set, and
    `named - set()` is every documented field -- a wall of false problems on a
    perfectly correct table.
    """
    names = set()
    for klass in getattr(cls, "__mro__", [cls]):
        slots = getattr(klass, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        names.update(slots or ())
        names.update(getattr(klass, "__annotations__", {}) or {})
        for name, value in vars(klass).items():
            if isinstance(value, property) or callable(value):
                names.add(name)
            elif not name.startswith("__"):
                names.add(name)
    names.update(getattr(cls, "_fields", ()) or ())
    for field in getattr(cls, "__dataclass_fields__", {}) or {}:
        names.add(field)
    return names


def check_blocks(label, text, problems):
    """-> the number of ```python blocks, and their source joined."""
    blocks = BLOCK.findall(text)
    for number, block in enumerate(blocks, 1):
        try:
            compile(block, "%s, python block %d" % (label, number), "exec")
        except SyntaxError as exc:
            problems.append("%s: python block %d does not compile: %s"
                            % (label, number, exc))
    return blocks


def check_names(label, sources, package, problems, ignored):
    """Every `hato.<name>` used in `sources` exists on the installed package."""
    names = set()
    for source in sources:
        names.update(REFERENCE.findall(source))
        names.update(IMPORTS.findall(source))
    for name in sorted(names):
        if hasattr(package, name):
            continue
        try:
            importlib.import_module("%s.%s" % (package.__name__, name))
            continue
        except ImportError:
            pass
        if name in EXTENSION_LIKE:
            # ⚠ NAMED, NOT SILENT. If `hato.log` really were meant to be an
            # attribute, the ignore list is where the lie would hide -- so the
            # count is printed and the names are printed with it.
            ignored.add(name)
            continue
        problems.append("%s uses %s.%s, which does not exist on the installed "
                        "package" % (label, package.__name__, name))
    return names


def check_field_tables(label, text, package, problems, min_fields):
    """-> the number of field tables read. Every field they name must be real."""
    tables = 0
    for match in FIELD_TABLE.finditer(text):
        class_name = match.group(1)
        tables += 1
        cls = getattr(package, class_name, None)
        if cls is None:
            problems.append("%s documents a `%s` field table, but the installed "
                            "package does not export %s"
                            % (label, class_name, class_name))
            continue
        body = text[match.end():].split("\n\n", 1)[0]
        named = set()
        for row in body.splitlines():
            if not row.startswith("|"):
                continue
            cells = row.split("|")
            if len(cells) > 1:
                named.update(CELL_NAMES.findall(cells[1]))
        named.discard(class_name)
        real = real_fields(cls)
        for field in sorted(named - real):
            problems.append("%s: the %s field table names `%s`, which %s does "
                            "not have" % (label, class_name, field, class_name))
        # ⚠ THE VACUITY GUARD ON THIS CHECK ITSELF. A table whose rows stopped
        # matching the row pattern reads 0 fields and reports 0 problems, which
        # is indistinguishable from a correct table until someone renames a
        # field and nothing goes red.
        if len(named) < min_fields:
            problems.append("%s: only %d field(s) were read from the %s table, "
                            "so this check proves little (wanted >= %d) -- the "
                            "row format probably changed"
                            % (label, len(named), class_name, min_fields))
    return tables


def encode(text):
    """Percent-encode a workflow command's message. ⛔ `%` first, or it eats its
    own escapes. ⚠ A `SyntaxError`'s text and a Windows path both carry `%`."""
    return (ascii_only(text).replace(u"%", u"%25")
            .replace(u"\r", u"%0D").replace(u"\n", u"%0A"))


def emit(problems, stream):
    inside_actions = bool(os.environ.get("GITHUB_ACTIONS"))
    for problem in problems:
        if inside_actions:
            # ⛔ THE ONE CHANNEL READABLE WITHOUT CREDENTIALS (pitfall P14).
            # ⚠ No colon in the title, and the message is percent-encoded --
            # see `report_failures.py::encode_property`.
            stream.write(u"::error title=docs drift::%s\n" % encode(problem))
        else:
            stream.write(ascii_only(u"PROBLEM: %s\n" % problem))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python .github/scripts/check_docs.py",
        description="the docs and examples may not drift from the installed API")
    parser.add_argument("--docs", default="docs", metavar="DIR",
                        help="directory of markdown docs (default: docs)")
    parser.add_argument("--examples", default="examples", metavar="DIR",
                        help="directory of runnable examples (default: examples)")
    parser.add_argument("--package", default="hato", metavar="NAME",
                        help="the installed package to check against")
    parser.add_argument("--allow-empty", action="store_true",
                        help="permit a pass when there is nothing to check. "
                             "⛔ remove this from ci.yml the day docs/ lands")
    parser.add_argument("--min-fields", type=int, default=5, metavar="N",
                        help="a field table reading fewer than N fields is a "
                             "problem, not a pass (default: 5)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="ascii", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    try:
        package = importlib.import_module(args.package)
    except Exception as exc:                            # noqa: BLE001
        sys.stdout.write(ascii_only(
            u"::error title=docs drift::could not import %s: %s: %s\n"
            % (args.package, type(exc).__name__, exc)))
        sys.stdout.write(ascii_only(
            u"TOOLING FAULT: `import %s` failed, so nothing below would be a "
            u"claim about the installed API.\n" % args.package))
        return EXIT_FAULT

    problems, ignored = [], set()
    blocks = tables = 0
    docs_seen = examples_seen = 0

    if os.path.isdir(args.docs):
        for path in markdown_files(args.docs):
            docs_seen += 1
            text = read(path)
            found = check_blocks(path, text, problems)
            blocks += len(found)
            check_names(path, found, package, problems, ignored)
            tables += check_field_tables(path, text, package, problems,
                                         args.min_fields)
    else:
        sys.stdout.write("SKIP  %s does not exist yet\n" % args.docs)

    if os.path.isdir(args.examples):
        for path in python_files(args.examples):
            examples_seen += 1
            source = read(path)
            try:
                compile(source, path, "exec")
            except SyntaxError as exc:
                problems.append("%s does not compile: %s" % (path, exc))
                continue
            check_names(path, [source], package, problems, ignored)
    else:
        sys.stdout.write("SKIP  %s does not exist yet\n" % args.examples)

    # ⭐ THE DENOMINATOR, ON EVERY RUN. This line is what makes a vacuous pass
    # visible without reading the exit code.
    sys.stdout.write(
        "checked %d markdown file(s), %d python block(s), %d field table(s), "
        "%d example(s) against %s %s\n"
        % (docs_seen, blocks, tables, examples_seen, args.package,
           getattr(package, "__version__", "?")))
    if ignored:
        sys.stdout.write("ignored %d extension-like name(s): %s\n"
                         % (len(ignored), ", ".join(sorted(ignored))))

    nothing = (blocks == 0 and examples_seen == 0)
    if nothing:
        message = ("found 0 documented python blocks and 0 examples -- there is "
                   "NOTHING HERE TO CHECK, so a pass would mean nothing "
                   "(looked in %s and %s)" % (args.docs, args.examples))
        if args.allow_empty:
            # ⚠ LOUD, AND ASCII. A skip nobody can see in the log is a pass.
            sys.stdout.write("EMPTY, ALLOWED: %s\n" % message)
            sys.stdout.write("THIS RUN PROVED NOTHING ABOUT THE DOCS.\n")
        else:
            problems.append(message)

    emit(problems, sys.stdout)
    sys.stdout.write("%d problem(s)\n" % len(problems))
    return EXIT_PROBLEMS if problems else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
