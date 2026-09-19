# -*- coding: utf-8 -*-
"""
hato (鳩, the carrier pigeon) -- finds videos with no Japanese subtitle, fetches
candidates from jimaku.cc, and has tsubasa retime and place them.

    hato <folder>            the front door; does the whole job
    python -m hato doctor    is the live API still what we think?

It IMPORTS tsubasa. tsubasa never imports it (spec/01-scope.md).

⚠ THIS FILE STAYS LIGHT ON PURPOSE. Importing `hato` must not import the
client, the matcher or the pipeline: builders work those modules in parallel and
mutate them to prove their checks, and a package __init__ that imported them all
would turn one builder's deliberate mutant into every other builder's red suite.
⭐ The library API is wired below LAZILY, which is what keeps both true at once.
"""

#: The single source of truth for the version. ⚠ Never hand-bumped at release:
#: spec/RUNBOOK.md step 6 stamps it from a content hash.
__version__ = "1.0.1"

#: ⭐ The published library API (spec/05-interface.md §The library API), wired
#: LAZILY via PEP 562. `from hato import scan` works; plain `import hato` still
#: does not pull in the pipeline, which is the invariant the note above records.
#: 🚨 These names become a permanent compatibility promise at the release TAG --
#: a published name can be added to, never renamed. Do not edit this tuple
#: without reading `05-interface.md` first.
_API = ("scan", "identify", "fetch", "Result", "Results", "Plan", "ConfigProblem",
        "SPEC_FIELDS", "CONFIDENT", "REFUSED", "ERROR", "NOT_FOUND", "SKIPPED",
        "PLANNED", "PRESENT", "BLACKLISTED", "EMBEDDED", "NO_TRACK", "NEGATIVE")


def __getattr__(name):
    if name in _API:
        from hato import api
        return getattr(api, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(list(globals()) + list(_API)))


__all__ = ["__version__"] + list(_API)
