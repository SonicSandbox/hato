# -*- coding: utf-8 -*-
"""
An anchored edit that resolves to EXACTLY ONE match, or writes nothing.

    anchor.replace_once(path, frm, to)   -> Edit(matches, ending)  | AnchorRefused
    anchor.write_bytes_once(path, data)  temp-plus-rename, no truncate

⭐ THIS IS [[patch-kit]]'s CONTRACT, AND THE CONTRACT IS THE POINT
(TRIGGERS.md: "an anchor matching twice edits the wrong place and proves nothing
about either"). Three rules, all three enforced below:

    exactly once     `frm` matching 0 or 2+ times is a refusal, not a warning
    all or nothing   resolved to an offset BEFORE a byte is written
    its own endings  the anchor matches ending-agnostically; the file keeps its own

⚠ WHY patch-kit IS NOT INVOKED HERE, since TRIGGERS.md says never to re-derive
it. `Workshop/patch-kit/apply.mjs` is Node, and it lives at a path on one
laptop. `python -m hato.dev stamp` runs in the release block and in CI, on a
runner with no Node and no vault -- and spec/RUNBOOK.md 0a forbids shipping code
that knows where this vault keeps its tools. So the TOOL could not be called and
its GUARANTEE had to travel instead: one function, thirty lines, its own checks
below, and every rule named. ⛔ This is not licence to hand-roll the next one --
any edit inside the workspace still goes through apply.mjs.

🚨 AND NEVER `open(path, "w")`. LEDGER-HOT.md: it truncates the moment it opens,
so a write that then raises leaves a ZERO-BYTE file -- which is how
`tsubasa/spec/RUNBOOK.md` was destroyed on 2026-09-07 by a one-liner that hit a
UnicodeEncodeError AFTER the truncate. Every write here goes to a sibling temp
file and is renamed over the target, so a failure leaves the original intact.
"""
import os
from pathlib import Path

CRLF = "\r\n"
LF = "\n"


class AnchorRefused(Exception):
    """The anchor did not resolve to exactly one match. NOTHING was written."""


class Edit(object):
    __slots__ = ("path", "matches", "ending", "changed")

    def __init__(self, path, matches, ending, changed):
        self.path = path
        self.matches = matches
        self.ending = ending
        self.changed = changed

    def __repr__(self):
        return "<Edit %s matches=%d ending=%s changed=%s>" % (
            self.path, self.matches, "CRLF" if self.ending == CRLF else "LF", self.changed)


def dominant_ending(text):
    """CRLF when the file has any, else LF. -> "\\r\\n" | "\\n"

    ⚠ patch-kit.md: line endings are per FILE, not per repo -- in one project a
    module was 100% CRLF while every harness beside it was 100% LF, and an anchor
    built with \\n matched zero times, which reads as a bad anchor rather than an
    encoding difference.
    """
    crlf = text.count(CRLF)
    lf = text.count(LF) - crlf
    return CRLF if crlf > lf else LF


def write_bytes_once(path, data):
    """Write `data` to `path` through a sibling temp file and a rename. -> Path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".new-%d" % os.getpid())
    try:
        handle = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        os.replace(str(temp), str(path))
    finally:
        if temp.exists():
            try:
                temp.unlink()          # a failed write leaves NOTHING behind
            except OSError:
                pass
    return path


def replace_once(path, frm, to, encoding="utf-8"):
    """Replace `frm` with `to` in `path`, exactly once. -> Edit | AnchorRefused.

    `frm` and `to` are written with plain \\n; both are translated to the file's
    own ending before anything is matched or spliced.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnchorRefused("%s could not be read: %s -- NOTHING WRITTEN" % (path, exc))
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise AnchorRefused("%s is not %s: %s -- NOTHING WRITTEN" % (path, encoding, exc))

    ending = dominant_ending(text)
    needle = frm.replace(CRLF, LF).replace(LF, ending)
    payload = to.replace(CRLF, LF).replace(LF, ending)

    matches = text.count(needle)
    if matches != 1:
        raise AnchorRefused(
            "REFUSED: the anchor matched %d time(s) in %s -- NOTHING WRITTEN "
            "(anchor: %r)" % (matches, path, frm[:70]))

    if needle == payload:
        return Edit(path, 1, ending, False)

    write_bytes_once(path, text.replace(needle, payload, 1).encode(encoding))
    return Edit(path, 1, ending, True)
