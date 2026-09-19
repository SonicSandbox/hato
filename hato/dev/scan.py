# -*- coding: utf-8 -*-
"""
The two scans over the built artifacts, before anything is published.

    python -m hato.dev scan-secrets dist/    no secret anywhere in the artifact
    python -m hato.dev scan-content dist/    no third-party subtitle BODY

🚨 WHEELS AND SDISTS ARE UNPACKED. A zipped secret is still a shipped secret, and
`grep dist/` over a `.whl` reads compressed bytes and finds nothing -- which looks
exactly like a clean result. Every member of every archive is scanned, nested
archives included, to a depth cap.

🚨 THE KEY IS READ AND SEARCHED FOR, AND NEVER PRINTED, LOGGED OR WRITTEN.
LEDGER-HOT.md: never write a secret anywhere inside TheForge, not even for a
minute -- the vault auto-commits every ~5 minutes and git history has no undo.
So every member is scanned IN MEMORY (nothing is ever unpacked to disk), and the
only part of the key that any output may carry is its last four characters, via
`credentials.Key.hint`.

⭐ IN FIVE ENCODINGS. `hato/doctor.py`'s `sniff_encoding` is the shape this
follows -- utf-8, utf-16-le, utf-16-be and cp932, plus cp1252, the encoding
Windows Python falls back to when nobody says otherwise (LEDGER-HOT.md). ⚠ For an
ASCII key three of the five produce identical bytes; the search reports how many
DISTINCT needles it actually looked for, so the number is never decoration.

⚠ NOTE ON THE DOCTOR (a spec defect, recorded rather than fixed here): the brief
for this step says the doctor's capture scan searches five encodings. It does
not -- `doctor.Capture._write` tests `key.reveal().encode("utf-8") in data` and
nothing else. What was reused is its SHAPE: check before the bytes are kept, and
refuse the whole write. The five-encoding alphabet comes from `sniff_encoding`.

⛔ SUBTITLE BODIES ARE NOT OURS TO REDISTRIBUTE (spec/10-deployment.md §4.4, and
LEDGER-HOT.md: never bundle, mirror or redistribute subtitle content). API-response
fixtures are metadata and are fine. ⭐ So the detection is STRUCTURAL, not by
filename: SRT cue blocks, WebVTT, ASS `Dialogue:` lines, and a document-sized run
of Japanese in a member that is not JSON.
"""
import argparse
import io
import json
import posixpath
import re
import tarfile
import zipfile
from pathlib import Path

from hato.dev import claims
from hato.dev.claims import Fault, fail, ok

#: ⭐ The five, from `doctor.sniff_encoding` + the cp1252 default Windows Python
#: falls back to. A codec that cannot represent the key is skipped and counted.
KEY_CODECS = ("utf-8", "utf-16-le", "utf-16-be", "cp932", "cp1252")

MiB = 1024 * 1024
#: One member. Above this, only the head is scanned -- and the claim says so.
MAX_MEMBER_BYTES = 64 * MiB
#: Everything together, so a zip bomb is a Fault and not a hang.
MAX_TOTAL_BYTES = 1024 * MiB
#: An archive inside an archive inside the directory. Beyond this it is a Fault.
MAX_DEPTH = 3

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_GZIP_MAGIC = b"\x1f\x8b"

#: A key-shaped literal: a credential-ish FIELD NAME, an assignment, and a value
#: long enough to be a key. ⚠ Anchored on the assignment rather than on entropy,
#: because a wheel's RECORD holds a base64 sha256 for every member and an
#: entropy scan would fire on every wheel for ever -- and doctrine/evidence:
#: "a check that reproduces a settled decision flags everything forever, and that
#: is how a check gets switched off". Measured on hato's own tree 2026-09-17: 2
#: hits, both the deliberate fake keys in tests/, which never ship.
_KEY_SHAPED = re.compile(
    rb"(?i)(?:^|[^A-Za-z0-9_])"
    rb"(hato_jimaku_key|jimaku[_\-]?(?:api[_\-]?)?key|api[_\-]?key|apikey|secret"
    rb"|access[_\-]?token|auth[_\-]?token|bearer)"
    rb"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-.]{16,})")

#: Values that are obviously not a credential. ⛔ Keep this list SHORT: every
#: entry is a hole, and `abc123`-style fakes are deliberately NOT here -- a fake
#: key in a shipped file is still a key-shaped string in the artifact, and the
#: fix is to not ship the file.
_PLACEHOLDER = re.compile(
    rb"(?i)^(x{8,}|0{8,}|y{8,}|your[_\-]|my[_\-]key|put[_\-]|paste|changeme"
    rb"|replace[_\-]?me|todo|example[_\-]|dummy[_\-]|redacted|none$|null$)")

# -- subtitle payloads, structurally ---------------------------------------
#: `00:00:01,000 --> 00:00:03,500` -- SRT's comma-millisecond arrow.
_SRT_CUE = re.compile(r"\d{1,3}:\d{2}:\d{2},\d{1,3}\s*-->\s*\d{1,3}:\d{2}:\d{2},\d{1,3}")
#: WebVTT: the signature, or its dot-millisecond arrow.
_VTT_HEAD = re.compile(r"^﻿?WEBVTT")
_VTT_CUE = re.compile(r"\d{1,3}:\d{2}[:.]\d{2}\.\d{1,3}\s*-->\s*\d{1,3}:\d{2}[:.]\d{2}\.\d{1,3}")
#: ASS/SSA: an events line. `Dialogue: 0,0:00:01.00,...`
_ASS_DIALOGUE = re.compile(r"^Dialogue:\s*\d", re.M)
_ASS_EVENTS = re.compile(r"^\s*\[Events\]", re.M | re.I)
#: A run of Japanese/CJK text.
_CJK_RUN = re.compile(
    u"[　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿"
    u"豈-﫿＀-￯]+")

#: ⭐ MEASURED ON HATO'S OWN TREE, 2026-09-17, so the floors sit above the real
#: maximum instead of a guess (doctrine/evidence: measure the corpus before
#: designing the constraint). Worst non-JSON file in the whole checkout:
#: tests/test_tokens.py at 418 CJK characters in 16 runs of >= 10. A synthetic
#: 48-line stripped subtitle body: 792 characters in 48 runs. Both floors must
#: be met, so a source file full of Japanese docstrings cannot trip it.
CJK_TOTAL_FLOOR = 500
CJK_RUNS_FLOOR = 20
CJK_RUN_LENGTH = 10

#: The extension claim -- a SECOND, different question from the structural ones:
#: it catches an empty, encrypted or already-stripped subtitle file that no
#: detector can read. Mirrors `archives.SUBTITLE_EXTS`.
SUBTITLE_EXTS = (".ass", ".ssa", ".srt", ".vtt", ".sub", ".idx", ".sup")


# ---------------------------------------------------------------------------
# walking the artifacts
# ---------------------------------------------------------------------------

def _kind(data):
    if data[:4] in _ZIP_MAGIC:
        return "zip"
    if data[:2] == _GZIP_MAGIC:
        return "tar"
    if len(data) > 262 and data[257:262] == b"ustar":
        return "tar"
    return None


class _Budget(object):
    def __init__(self):
        self.total = 0

    def spend(self, n, label):
        self.total += n
        if self.total > MAX_TOTAL_BYTES:
            raise Fault("more than %d MiB unpacked by %s -- refusing to keep going"
                        % (MAX_TOTAL_BYTES // MiB, label))


def _members(label, data, depth, budget):
    """Yield (label, bytes) for `data` and, when it is an archive, its members."""
    budget.spend(len(data), label)
    yield label, data
    kind = _kind(data)
    if kind is None:
        return
    if depth >= MAX_DEPTH:
        raise Fault("%s nests archives more than %d deep" % (label, MAX_DEPTH))
    if kind == "zip":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise Fault("%s looks like a zip and could not be opened: %s" % (label, exc))
        try:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    raise Fault("%s!%s declares %d bytes, over the %d MiB member cap"
                                % (label, info.filename, info.file_size,
                                   MAX_MEMBER_BYTES // MiB))
                for pair in _members("%s!%s" % (label, info.filename),
                                     zf.read(info), depth + 1, budget):
                    yield pair
        finally:
            zf.close()
        return
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data))
    except (tarfile.TarError, OSError) as exc:
        raise Fault("%s looks like a tarball and could not be opened: %s" % (label, exc))
    try:
        for info in tf.getmembers():
            if not info.isfile():
                continue
            if info.size > MAX_MEMBER_BYTES:
                raise Fault("%s!%s declares %d bytes, over the %d MiB member cap"
                            % (label, info.name, info.size, MAX_MEMBER_BYTES // MiB))
            handle = tf.extractfile(info)
            if handle is None:
                continue
            for pair in _members("%s!%s" % (label, info.name),
                                 handle.read(), depth + 1, budget):
                yield pair
    finally:
        tf.close()


def artifacts(target):
    """Yield (label, bytes) for every file under `target` and every member inside.

    ⛔ NOTHING IS EVER UNPACKED TO DISK. A member's bytes exist only in this
    process, which is what keeps a scan for the key from writing the key.
    """
    target = Path(target)
    budget = _Budget()
    if target.is_file():
        roots = [target]
    elif target.is_dir():
        roots = sorted(p for p in target.rglob("*") if p.is_file())
    else:
        raise Fault("no such file or directory: %s" % target)
    if not roots:
        raise Fault("%s holds no files -- there is nothing to scan, and exit 0 "
                    "would read as a clean artifact" % target)
    for path in roots:
        for pair in _members(path.as_posix(), path.read_bytes(), 0, budget):
            yield pair


def _decode(data):
    """Text for a structural read. utf-8 first, then the two UTF-16 BOMs.

    ⚠ `errors="replace"` is deliberate and safe HERE: a Shift-JIS subtitle read
    as utf-8 keeps every ASCII byte, so `Dialogue:` and the timestamps -- what
    the detectors key on -- survive intact. ⛔ It would NOT be safe on a subtitle
    hato was about to write (LEDGER-HOT.md: 346 cues turned to U+FFFD and the
    tool still said CONFIDENT); nothing here writes anything.
    """
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    return data.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# scan-secrets
# ---------------------------------------------------------------------------

def key_needles(value):
    """-> {codec: bytes}, one per codec that can represent the key.

    ⚠ Duplicates are kept under each codec name and de-duplicated by the caller
    when it counts, so "5 encodings, 3 distinct needles" is the honest readout
    for an ASCII key rather than a five nobody checked.
    """
    out = {}
    for codec in KEY_CODECS:
        try:
            out[codec] = value.encode(codec)
        except (UnicodeEncodeError, LookupError):
            continue
    return out


def _shaped_hits(label, data):
    out = []
    for m in _KEY_SHAPED.finditer(data):
        value = m.group(2)
        if _PLACEHOLDER.match(value) or len(set(value)) <= 2:
            continue
        out.append((label, m.group(1).decode("ascii", "replace"),
                    m.start(2), len(value)))
    return out


def scan_secrets(target, needles, hint, no_key_reason=None):
    """-> [Claim]. `needles` is {codec: bytes}; ⛔ neither it nor any matched
    value is ever printed -- only `hint` (the last four characters) may be.

    `no_key_reason` set means no key resolved: `key_bytes_absent` becomes a loud
    SKIP rather than a tick, because a scan that cannot look for its own subject
    has not made that claim (doctrine/verification: a skip is not a pass).
    """
    distinct = {}
    for codec, raw in needles.items():
        distinct.setdefault(raw, []).append(codec)
    found = []
    shaped = []
    members = 0
    scanned = 0
    for label, data in artifacts(target):
        members += 1
        scanned += len(data)
        for raw, codecs in distinct.items():
            at = data.find(raw)
            if at >= 0:
                found.append((label, "/".join(codecs), at))
        shaped.extend(_shaped_hits(label, data))

    where = "%d member(s), %d bytes" % (members, scanned)
    if no_key_reason is not None:
        out = [claims.skip("key_bytes_absent",
                           "DEGRADED: no key resolved, so %s were NOT searched for "
                           "it -- only the shape scan below ran (%s)"
                           % (where, no_key_reason))]
    elif found:
        out = [fail("key_bytes_absent",
                    "THE KEY IS IN THE ARTIFACT -- %d hit(s): %s. %s"
                    % (len(found),
                       "; ".join("%s at byte %d as %s" % (l, a, c) for l, c, a in found[:3]),
                       where))]
    else:
        out = [ok("key_bytes_absent",
                  "the key (ending %s) does not appear in %s; %d encoding(s) -> %d "
                  "distinct needle(s) (%s)"
                  % (hint, where, len(needles), len(distinct), ", ".join(sorted(needles))))]

    if shaped:
        out.append(fail("no_key_shaped_literal",
                        "%d key-shaped literal(s): %s"
                        % (len(shaped),
                           "; ".join("%s field %r at byte %d, %d chars"
                                     % (l, n, a, ln) for l, n, a, ln in shaped[:3]))))
    else:
        out.append(ok("no_key_shaped_literal",
                      "no credential-shaped assignment in %s" % where))
    return out


# ---------------------------------------------------------------------------
# scan-content
# ---------------------------------------------------------------------------

def _is_json(data):
    try:
        json.loads(data.decode("utf-8"))
        return True
    except (ValueError, UnicodeDecodeError):
        return False


def cjk_score(text):
    """-> (total CJK characters, runs of at least CJK_RUN_LENGTH)."""
    runs = _CJK_RUN.findall(text)
    return (sum(len(r) for r in runs),
            sum(1 for r in runs if len(r) >= CJK_RUN_LENGTH))


def scan_content(target):
    """-> [Claim]. ⛔ No evidence string ever quotes the content it found: the
    whole point is that those bytes are not ours to reproduce."""
    srt, vtt, ass, cjk, named = [], [], [], [], []
    members = 0
    json_members = 0
    for label, data in artifacts(target):
        members += 1
        text = _decode(data)

        cues = len(_SRT_CUE.findall(text))
        if cues >= 2:
            srt.append((label, "%d SRT cue timings" % cues))
        if _VTT_HEAD.match(text) or len(_VTT_CUE.findall(text)) >= 2:
            vtt.append((label, "WEBVTT signature" if _VTT_HEAD.match(text)
                        else "%d WebVTT cue timings" % len(_VTT_CUE.findall(text))))
        lines = len(_ASS_DIALOGUE.findall(text))
        if lines:
            ass.append((label, "%d ASS Dialogue line(s)%s"
                        % (lines, " under [Events]" if _ASS_EVENTS.search(text) else "")))

        if _is_json(data):
            json_members += 1          # an API-response fixture is metadata
        else:
            total, runs = cjk_score(text)
            if total >= CJK_TOTAL_FLOOR and runs >= CJK_RUNS_FLOOR:
                cjk.append((label, "%d CJK characters in %d runs of >=%d"
                            % (total, runs, CJK_RUN_LENGTH)))

        if posixpath.splitext(label.split("!")[-1])[1].lower() in SUBTITLE_EXTS:
            named.append((label, "a subtitle extension"))

    denominator = "%d member(s)" % members
    cjk_denominator = ("%d member(s), %d of them JSON (metadata, exempt from this "
                       "test)" % (members, json_members))

    def claim(name, hits, what, over=None):
        if hits:
            return fail(name, "%d member(s) carry %s: %s"
                        % (len(hits), what,
                           "; ".join("%s (%s)" % (l, why) for l, why in hits[:3])))
        return ok(name, "no %s in %s" % (what, over or denominator))

    return [
        claim("no_srt_cues", srt, "SRT cue blocks"),
        claim("no_webvtt", vtt, "WebVTT"),
        claim("no_ass_events", ass, "ASS/SSA dialogue"),
        claim("no_cjk_document", cjk, "document-sized runs of Japanese",
              over=cjk_denominator),
        claim("no_subtitle_extension", named, "subtitle file extensions"),
    ]


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def main_secrets(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev scan-secrets")
    parser.add_argument("target", help="dist/, or one artifact")
    parser.add_argument("--allow-no-key", action="store_true",
                        help="run the SHAPE scan only when no key resolves -- the "
                             "strongest half of the claim is then NOT made")
    args = parser.parse_args(argv)

    from hato import credentials, paths
    try:
        key = credentials.resolve_key()
    except (credentials.KeyMissing, paths.PathError) as exc:
        if not args.allow_no_key:
            raise Fault("no jimaku key resolved, so the artifact cannot be searched "
                        "for it -- and a scan that skips its own subject must not "
                        "exit 0 (%s). Pass --allow-no-key for the shape scan alone"
                        % exc)
        return claims.report("scan-secrets", args.target,
                             scan_secrets(args.target, {}, "(no key)",
                                          no_key_reason=str(exc)))

    return claims.report("scan-secrets", args.target,
                         scan_secrets(args.target, key_needles(key.reveal()), key.hint))


def main_content(argv):
    parser = argparse.ArgumentParser(prog="python -m hato.dev scan-content")
    parser.add_argument("target", help="dist/, or one artifact")
    args = parser.parse_args(argv)
    return claims.report("scan-content", args.target, scan_content(args.target))
