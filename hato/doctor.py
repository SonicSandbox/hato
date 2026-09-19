# -*- coding: utf-8 -*-
"""
`hato doctor` -- is the live API still what we think? A READOUT, not a library.

    readout = collect(session)            # measures; writes nothing
    readout = collect(session, capture_dir=Path(...))   # --capture
    print(render(readout))

This ships BEFORE the client it de-risks (spec/RUNBOOK.md 0b). Everything about
jimaku leaves the process, so the suite can only ever prove hato ASKED
correctly; this answers the other half against the real server.

Rules, each a check in tests/test_doctor.py:

- ⛔ NO LINE IS EVER BLANK. Every line is a value, or MISSING / SKIPPED / FAILED
  with the reason.
- 🚨 A 401 STOPS EVERY FURTHER METERED CALL. It still consumed quota, and so
  would every retry (spec/08-research.md §Rate limiting).
- ⭐ --capture writes each response's body EXACTLY as received, plus a
  `.meta.json` with the date, the URL, the status and the RESPONSE headers.
  ⛔ Never a request header (the key rides in one). ⛔ Never a downloaded
  subtitle body -- that is third-party content and the vault auto-commits
  (spec/10-deployment.md rule 4): the download is recorded as metadata only.
  ⛔ Before any file is kept, its bytes are searched for the key; a hit fails the
  WHOLE capture, from whichever site found it -- see CaptureLeak.
- ⛔ Traps are captured as METADATA where the body would be a mirror: an empty
  query returns the ENTIRE catalogue (Whitelist 2: never mirror it), so only its
  count, status and headers are kept.
- ⛔ A 429 is NOT provoked. It can only be produced by exceeding 25 req/60 s,
  which Whitelist 2 forbids. Recorded as a spec defect; the client builds its
  429 path from a real response's rate-limit headers instead.
- Paced with a JITTERED wait between metered calls (LEDGER.md: a constant
  delay is a strange shape in someone's access log), and 🚨 NO METERED CALL IS
  MADE ONCE x-ratelimit-remaining HAS FALLEN TO 3 -- the readout's own search and
  file listing included, not just the optional captures (see api_get).
- ⛔ THE DOWNLOAD GOES THROUGH THE CLIENT'S URL GUARD. jimaku names the url; a
  readout that fetched whatever host it named and then printed `download ok`
  would be reporting on a server nobody asked about.
"""
import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from hato import __version__, credentials, paths

API = "https://jimaku.cc/api"
SITE = "https://jimaku.cc"
CROWN_JEWEL = 11446        # Sousou no Frieren 2nd Season -- spec/08-research.md
INVALID_ENTRY = 999999
LIVE_ACTION_QUERY = "Kamen Rider Decade"
MOVIE_QUERIES = ("Kimi no Na wa", "Koe no Katachi")
RATE_HEADERS = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                "x-ratelimit-reset-after")
STOP_WHEN_REMAINING = 3
USER_AGENT = "hato/%s (doctor)" % __version__

OK, MISSING, SKIPPED, FAILED = "ok", "MISSING", "SKIPPED", "FAILED"

#: Every stem `--capture` writes, in the order it writes them. ⭐ ONE list, and
#: the suite checks BOTH ends of it: that a real capture run writes exactly these
#: (derived by running one, never restated), and that tests/fixtures/api/ holds a
#: file for each. 🚨 It is the second half that was missing: the 2b builder added
#: `search__query_sousou_no_frieren` and `search__no_match` to the code and the
#: capture was never re-run, so identification could still not be driven offline
#: from a real release-name query and nothing said so.
CAPTURE_STEMS = (
    "search__query_frieren",
    "entries_11446_files",
    "download__sample",
    "search__query_empty",
    "search__live_action_anime_default",
    "search__anime_false_retry",
    "search__movie",
    "entries_movie_flag",
    "entries_invalid_id_files",
    "download__invalid_id",
    "search__query_sousou_no_frieren",
    "search__no_match",
    "search__401_bad_key",
)


class CaptureLeak(BaseException):
    """A captured file contained the key. It was NOT written, and the whole
    capture stops here.

    🚨 A BaseException ON PURPOSE, exactly as SystemExit and KeyboardInterrupt
    are. Every network site in this module is wrapped in
    `except Exception:  # a readout reports, it does not crash` -- which is right
    for a timeout and catastrophic for this: measured 2026-09-17, leaking the key
    into the FIRST captured body was swallowed there, 11 further metered calls
    went out, 21 files were written, and the readout printed a second `search`
    line while the first still read `ok`. Making the class uncatchable by a bare
    `except Exception` fixes it at every site at once, including sites nobody has
    written yet -- a rule that has to be remembered at each new `try` is a rule
    that will be forgotten (doctrine/robustness).

    ⚠ Containment, not disclosure: `Capture._write` checks the bytes BEFORE
    opening anything, so no key has ever reached disk.
    """


class BudgetSpent(Exception):
    """x-ratelimit-remaining is at the floor: the call was never sent."""


class Line(object):
    __slots__ = ("label", "state", "text", "extra")

    def __init__(self, label, state, text, extra=()):
        self.label, self.state, self.text, self.extra = label, state, text, list(extra)


class Readout(object):
    def __init__(self):
        self.lines = []
        self.metered = 0
        self.unmetered = 0
        self.captured = []          # [(Path, what)]
        self.capture_missing = []   # [(name, reason)]
        self.key_rejected = False
        self.critical_failed = False

    def add(self, label, state, text, extra=()):
        self.lines.append(Line(label, state, text, extra))

    #: The lines without which the readout has not answered its question.
    CRITICAL = ("key", "search", "files")

    @property
    def exit_code(self):
        """0 only when the key, the search and the file listing all answered.
        SKIPPED is not an answer: an offline doctor has checked nothing."""
        if self.key_rejected or self.critical_failed:
            return 1
        states = {l.label: l.state for l in self.lines}
        return 0 if all(states.get(name) == OK for name in self.CRITICAL) else 1

    def as_dict(self):
        return {"lines": [{"label": l.label, "state": l.state, "text": l.text,
                           "extra": l.extra} for l in self.lines],
                "metered_calls": self.metered, "unmetered_downloads": self.unmetered,
                "captured": [{"path": str(p), "what": w} for p, w in self.captured],
                "capture_missing": [{"name": n, "reason": r} for n, r in self.capture_missing],
                "key_rejected": self.key_rejected, "exit_code": self.exit_code}


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def sniff_encoding(data):
    """A READOUT of what the bytes are. ⛔ Nothing is decoded for use."""
    if not data:
        return "empty"
    head = data[:64].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        return "HTML, not a subtitle"
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8 (BOM)"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le (BOM)"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be (BOM)"
    for codec, label in (("utf-8", "utf-8"), ("cp932", "shift_jis (cp932)")):
        try:
            data.decode(codec)
            return label
        except UnicodeDecodeError:
            continue
    return "undetermined"


def rate_headers(headers):
    """[(name, value)] verbatim, in a fixed order; MISSING when absent."""
    out = []
    for name in RATE_HEADERS:
        value = headers.get(name)
        out.append((name, value if value is not None else MISSING))
    return out


def _remaining(headers):
    try:
        return float(headers.get("x-ratelimit-remaining"))
    except (TypeError, ValueError):
        return None


def _meta(resp, url, note, body_kept):
    headers = {k.lower(): v for k, v in resp.headers.items() if k.lower() != "set-cookie"}
    body = resp.content or b""
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "captured_by": USER_AGENT,
        "method": "GET",
        "url": url,
        "final_url": getattr(resp, "url", url),
        "status": resp.status_code,
        "response_headers": headers,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "body_kept": body_kept,
        "note": note,
        "provenance": "hato doctor --capture (spec/RUNBOOK.md 0b). Real response "
                      "bytes; never hand-edited -- re-capture instead "
                      "(spec/07-test-plan.md).",
    }


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

#: 🚨 EVERY ENCODING THE KEY MUST BE HUNTED IN BEFORE A CAPTURE IS KEPT.
#: The first four are the ones `sniff_encoding` above can actually report on a
#: jimaku response; cp1252 is here because it is what Windows Python reaches for
#: by default, so it is the one a mistake arrives in.
#: ⛔ Do not shorten this to ("utf-8",) -- that is what it was until 2026-09-17.
KEY_CODECS = ("utf-8", "utf-16-le", "utf-16-be", "cp932", "cp1252")


def key_needles(key):
    """Every byte form of `key` worth searching a response body for.

    🚨 THIS EXISTS BECAUSE THE GUARD WAS UTF-8 ONLY, AND THAT IS NOT A
    THEORETICAL GAP. `--capture` writes into `tests/fixtures/api/`, which is
    inside a vault that auto-commits every ~5 minutes, and git history has no
    undo. A key echoed back in a UTF-16 or Shift-JIS body would have passed
    the check and been committed permanently. Found 2026-09-17 by the builder
    of `hato/dev/scan.py`, whose brief told it to "reuse the doctor's
    approach" -- and the approach turned out to be one encoding.

    ⚠ Byte encodings only. A base64'd or hex'd key is a different search and is
    NOT covered here; `hato/dev/scan.py` records the same gap.
    """
    if not key:
        return ()
    text = key.decode("utf-8", "replace") if isinstance(key, bytes) else key
    found = []
    for codec in KEY_CODECS:
        try:
            raw = text.encode(codec)
        except (UnicodeEncodeError, LookupError):
            continue
        if raw and raw not in found:
            found.append(raw)
    return tuple(found)


class Capture(object):
    """Writes into a directory by temp-plus-rename, and checks every file for
    the key -- in every encoding of it -- before keeping it."""

    def __init__(self, directory, key_bytes, readout):
        self.dir = Path(directory)
        #: kept for the readout and for anything that still reads it
        self.key_bytes = key_bytes
        #: ⭐ what `_write` actually searches. See `key_needles`.
        self.key_needles = key_needles(key_bytes)
        self.readout = readout
        self.dir.mkdir(parents=True, exist_ok=True)

    def _write(self, name, data):
        for needle in self.key_needles:
            if needle in data:
                raise CaptureLeak(
                    "the key appeared in %s -- NOTHING was written" % name)
        target = self.dir / name
        tmp = self.dir / (name + ".tmp")
        with open(str(tmp), "wb") as fh:
            fh.write(data)
        os.replace(str(tmp), str(target))
        self.readout.captured.append((target, name))
        return target

    def body_and_meta(self, stem, resp, url, note):
        self._write(stem + ".json", resp.content or b"")
        self.meta_only(stem, resp, url, note, body_kept=True)

    def meta_only(self, stem, resp, url, note, body_kept=False, extra=None):
        meta = _meta(resp, url, note, body_kept)
        if extra:
            meta.update(extra)
        data = json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        self._write(stem + ".meta.json", data + b"\n")

    def missing(self, name, reason):
        self.readout.capture_missing.append((name, reason))


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

def _pause(sleep, rng):
    sleep(1.0 + rng.random())         # jittered: 1.0-2.0 s, never a constant


def collect(session=None, capture_dir=None, sleep=time.sleep, rng=None,
            key_resolver=credentials.resolve_key, which=shutil.which,
            video=None):
    """-> Readout. `session` is a requests.Session (or a double built from the
    real requests types). None means the real network -- unless
    HATO_NO_NETWORK=1, in which case every network line says SKIPPED."""
    ro = Readout()
    rng = rng or random.Random()

    # -- key ------------------------------------------------------------------
    key = None
    try:
        key = key_resolver()
        ro.add("key", OK, "found, ending %s" % key.hint, ["from %s" % key.source])
    except (credentials.KeyMissing, paths.PathError) as exc:
        ro.add("key", MISSING, str(exc))

    offline = session is None and os.environ.get("HATO_NO_NETWORK") == "1"
    if session is None and not offline:
        import requests
        session = requests.Session()

    capture = None
    if capture_dir is not None:
        capture = Capture(capture_dir, key.reveal().encode("utf-8") if key else None, ro)

    network = key is not None and not offline
    why_not = ("HATO_NO_NETWORK=1 -- the network is switched off" if offline
               else "no key, so no metered call was made")

    #: The rate-limit floor, read off the LAST metered answer. ⛔ Consulted before
    #: EVERY metered call, through the one funnel below.
    budget = {"remaining": None}

    def budget_stop():
        """-> why no further metered call may be made, or None.

        🚨 This used to live inside _capture_traps, so the readout's own search,
        its file listing and the 1.39 MB empty-query catalogue dump never asked
        it: at `remaining: 0` -- and at -4 -- hato still fired all three
        (measured 2026-09-17). The floor belongs to the call, not to the caller.
        """
        if ro.key_rejected:
            return ("HTTP 401 -- jimaku rejected the key, and every further call would "
                    "spend quota too")
        rem = budget["remaining"]
        if rem is not None and rem <= STOP_WHEN_REMAINING:
            return ("x-ratelimit-remaining is %s, at or under hato's floor of %d -- "
                    "stopped rather than approach jimaku's limit"
                    % (("%g" % rem), STOP_WHEN_REMAINING))
        return None

    def api_get(path, params=None, auth=True, raw_key=None):
        """The ONE metered call. Refuses before the floor; counts only answers."""
        stop = budget_stop()
        if stop is not None:
            raise BudgetSpent(stop)
        url = API + path
        headers = {"User-Agent": USER_AGENT}
        if auth:
            headers["Authorization"] = raw_key if raw_key is not None else key.reveal()
        # ⛔ allow_redirects=False, and the count AFTER the answer -- both the
        # client's stated policy (hato/client.py), and doctor had neither: it
        # counted an API call that never happened, and a 3xx would have carried
        # the request, its User-Agent and the readout's verdict to another host.
        resp = session.get(url, params=params, headers=headers, timeout=30,
                           allow_redirects=False)
        ro.metered += 1
        budget["remaining"] = _remaining(resp.headers)
        # ⚠ A 401 on the DELIBERATELY invalid key (the last capture) says nothing
        # about the real one, so only a call made with the real key latches it.
        if resp.status_code == 401 and raw_key is None:
            ro.key_rejected = True
        return resp, url

    def full_url(resp, url, params):
        return getattr(resp, "url", None) or (url + ("?" + "&".join(
            "%s=%s" % kv for kv in params.items()) if params else ""))

    # -- search ---------------------------------------------------------------
    files_list = None
    if network:
        try:
            resp, url = api_get("/entries/search", {"query": "frieren"})
            if resp.status_code == 401:
                ro.key_rejected = True
                ro.add("search", FAILED,
                       "HTTP 401 -- jimaku REJECTED the key. Stopped: every further "
                       "call would spend quota too. Mint a new key at "
                       "https://jimaku.cc/account")
            else:
                results = resp.json() if resp.status_code == 200 else None
                n = len(results) if isinstance(results, list) else "?"
                first = (results[0].get("name") if isinstance(results, list) and results
                         else "(none)")
                state = OK if resp.status_code == 200 else FAILED
                if state == FAILED:
                    ro.critical_failed = True
                ro.add("search", state, "HTTP %d  GET /api/entries/search?query=frieren"
                       % resp.status_code, ["%s result(s), first: %s" % (n, first)])
                ro.add("rate limit", OK if all(v != MISSING for _, v in rate_headers(resp.headers)[:3])
                       else MISSING,
                       "%s: %s" % rate_headers(resp.headers)[0],
                       ["%s: %s" % hv for hv in rate_headers(resp.headers)[1:]])
                if capture:
                    capture.body_and_meta("search__query_frieren", resp,
                                          full_url(resp, url, {"query": "frieren"}),
                                          "jimaku's own fuzzy search, the primary path")
        except Exception as exc:  # a readout reports, it does not crash
            ro.critical_failed = True
            ro.add("search", FAILED, "%s: %s" % (type(exc).__name__, exc))
    else:
        ro.add("search", SKIPPED, why_not)
        ro.add("rate limit", SKIPPED, why_not)

    network = network and not ro.key_rejected

    # -- files ----------------------------------------------------------------
    # ⛔ The floor is asked HERE too, so a budget that ran out says SKIPPED with
    # its reason rather than FAILED with an exception name. api_get refuses it
    # either way -- same function, so the two cannot disagree.
    no_budget = budget_stop() if network else None
    if network and no_budget is None:
        try:
            _pause(sleep, rng)
            resp, url = api_get("/entries/%d/files" % CROWN_JEWEL)
            if resp.status_code == 200:
                files_list = resp.json()
                keys = sorted({k for f in files_list for k in f}) if isinstance(files_list, list) else []
                ro.add("files", OK, "HTTP 200  entry %d: %d files" % (CROWN_JEWEL, len(files_list)),
                       ["keys: %s" % ", ".join(keys)])
                if capture:
                    capture.body_and_meta("entries_%d_files" % CROWN_JEWEL, resp, url,
                                          "THE CROWN JEWEL: absolute+seasonal numbering "
                                          "mixed, several release groups, the "
                                          "[CHS, JPN]/[JPN] pairs. No episode= param.")
            else:
                ro.critical_failed = True
                ro.add("files", FAILED, "HTTP %d  GET /api/entries/%d/files"
                       % (resp.status_code, CROWN_JEWEL))
        except Exception as exc:
            ro.critical_failed = True
            ro.add("files", FAILED, "%s: %s" % (type(exc).__name__, exc))
    else:
        ro.add("files", SKIPPED, no_budget or
               ("key rejected" if ro.key_rejected else why_not))

    # -- one unmetered download -----------------------------------------------
    if network and isinstance(files_list, list) and files_list:
        subs = [f for f in files_list if str(f.get("name", "")).lower().endswith((".ass", ".srt"))
                and (f.get("size") or 0) > 0]
        if subs:
            pick = min(subs, key=lambda f: (f.get("size") or 0, f.get("name")))
            try:
                # ⭐ THE CLIENT'S OWN GUARD, asked before anything is sent -- not a
                # second copy of it. doctor's own version took `url` from the file
                # dict and prefixed the site only when it started with `/`, so a
                # crafted `https://evil.example/entry/...` was fetched and the
                # readout printed `download ok HTTP 200`: a readout claiming jimaku
                # answered when jimaku never heard the request (measured
                # 2026-09-17). The client refuses the identical dict, and that
                # guard survived 22 bypass attempts.
                # ⚠ Imported here and not at module scope: the readout has to load
                # where `requests` is not installed, and this is the one path where
                # a live session already exists.
                from hato import client as _client
                url = _client.file_url(pick, CROWN_JEWEL)
            except Exception as exc:
                ro.add("download", FAILED, "refused BEFORE any request -- %s" % exc,
                       ["jimaku names this url; hato asks the client's guard whether it "
                        "is jimaku's, so the readout can never report on another host"])
            else:
                try:
                    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=60,
                                       allow_redirects=False)
                    ro.unmetered += 1
                    body = resp.content or b""
                    ro.add("download", OK if resp.status_code == 200 else FAILED,
                           "HTTP %d  %s B  %s" % (resp.status_code, format(len(body), ","),
                                                  sniff_encoding(body)),
                           ["%s  (unmetered, no auth)" % pick.get("name")])
                    if capture:
                        capture.meta_only("download__sample", resp, url,
                                          "METADATA ONLY -- the body is third-party subtitle "
                                          "content and is never written into the repo.",
                                          extra={"name": pick.get("name"),
                                                 "sniffed_encoding": sniff_encoding(body)})
                except Exception as exc:
                    ro.add("download", FAILED, "%s: %s" % (type(exc).__name__, exc))
        else:
            ro.add("download", MISSING, "entry %d lists no .ass or .srt file to try" % CROWN_JEWEL)
    else:
        ro.add("download", SKIPPED, "no file list to download from" if network else
               ("key rejected" if ro.key_rejected else why_not))

    # -- the extra captures ---------------------------------------------------
    if capture is not None:
        if network:
            _capture_traps(ro, capture, session, api_get, full_url, sleep, rng, files_list)
        else:
            capture.missing("everything", "no network call was made: " +
                            ("key rejected" if ro.key_rejected else why_not))

    # -- tsubasa --------------------------------------------------------------
    _tsubasa_lines(ro, video)

    # -- archives -------------------------------------------------------------
    # ⚠ Every tool rarfile can extract with, not just `unrar` (found by the 3c
    # builder, 2026-09-17): with 7-Zip or bsdtar on PATH a .rar extracts fine,
    # and a readout saying MISSING there is a readout that lies.
    try:
        import rarfile
        tools = [rarfile.UNRAR_TOOL, rarfile.UNAR_TOOL, rarfile.SEVENZIP_TOOL,
                 rarfile.SEVENZIP2_TOOL, rarfile.BSDTAR_TOOL]
    except ImportError:
        tools = ["unrar", "unar", "7z", "7zz", "bsdtar"]
    found_tool = next((found for found in (which(t) for t in tools) if found), None)
    ro.add("unrar", OK if found_tool else MISSING,
           found_tool if found_tool else ".rar candidates will be skipped with a reason, never a crash",
           [] if found_tool else ["looked for: %s" % ", ".join(tools)])
    try:
        import py7zr
        ro.add("py7zr", OK, getattr(py7zr, "__version__", "importable"))
    except ImportError:
        ro.add("py7zr", MISSING, ".7z candidates will be skipped with a reason, never a crash")

    # -- paths ----------------------------------------------------------------
    for label, getter in (("cache", paths.data_root), ("config", None)):
        try:
            if getter is not None:
                target = getter()
                ro.add(label, OK if _writable(target) else FAILED,
                       "%s  %s" % (target, "writable" if _writable(target) else "NOT writable"),
                       ["from %s" % paths.data_root_source()])
            else:
                cfg_path, source = paths.config_path()
                folder_ok = _writable(cfg_path.parent)
                ro.add(label, OK if folder_ok else FAILED,
                       "%s  %s" % (cfg_path, "found" if cfg_path.is_file()
                                   else "not found -- documented defaults in use"),
                       ["folder %s  (from %s)" % ("writable" if folder_ok else "NOT writable",
                                                  source)])
        except paths.PathError as exc:
            ro.add(label, FAILED, str(exc))

    # ⚠ Nothing is migrated automatically (spec/05-interface.md). hato's non-Windows
    # root moved out of ~/.cache on 2026-09-17 -- because the root holds the kept
    # originals and ~/.cache is wipeable -- so an old folder may still be sitting
    # there. ⛔ One line, and hato moves nothing and deletes nothing.
    old = paths.legacy_data_root()
    if old is not None:
        ro.add("old folder", OK, "%s  left where it is" % old,
               ["hato's folder moved to %s. Nothing was moved or deleted: copy anything "
                "you want to keep (subs/ holds the originals), then delete it yourself."
                % paths.data_root()])

    ro.add("api calls", OK, "%d metered · %d unmetered download%s"
           % (ro.metered, ro.unmetered, "" if ro.unmetered == 1 else "s"))
    return ro


def _writable(folder):
    """Create the folder if needed and prove a file can be made there."""
    try:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / (".hato-doctor-%d.tmp" % os.getpid())
        with open(str(probe), "wb") as fh:
            fh.write(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _tsubasa_lines(ro, video):
    try:
        import tsubasa
    except Exception as exc:
        ro.add("tsubasa", MISSING, "not importable (%s: %s). Install tsubasa-sync, or put "
               "a checkout on PYTHONPATH." % (type(exc).__name__, exc))
        ro.add("self_check", SKIPPED, "tsubasa is not importable")
        ro.add("track reader", SKIPPED, "tsubasa is not importable")
        return
    ro.add("tsubasa", OK, "%s" % getattr(tsubasa, "__version__", "?"),
           ["from %s" % Path(tsubasa.__file__).resolve().parent])
    try:
        check = tsubasa.self_check()
        notes = list(getattr(check, "notes", []) or [])
        ro.add("self_check", OK if check.ok else FAILED,
               "ok" if check.ok else "NOT ok -- %s" % "; ".join(
                   str(p) for p in (getattr(check, "problems", None) or notes) or ["(no reason given)"]),
               ["note: %s" % n for n in notes])
    except Exception as exc:
        ro.add("self_check", FAILED, "%s: %s" % (type(exc).__name__, exc))

    # RUNBOOK T4 / tsubasa RUNBOOK 3f. ⛔ Never tsubasa.container.
    public = getattr(tsubasa, "__all__", [])
    reader = "embedded_subs" if "embedded_subs" in public else None
    if reader is None:
        ro.add("track reader", MISSING,
               "tsubasa exports no public track reader yet (expected "
               "`embedded_subs`, tsubasa RUNBOOK 3f). hato's fetch loop "
               "(RUNBOOK 4b) is blocked on it.")
        return
    extra = []
    if video is not None:
        try:
            result = getattr(tsubasa, reader)(str(video))
            ok = getattr(result, "ok", None)
            if ok is False:
                extra.append("%s: unreadable -- %s" % (video, getattr(result, "reason", "")))
            else:
                tracks = list(getattr(result, "tracks", []))
                extra.append("%s: %d subtitle track(s): %s" % (video, len(tracks), ", ".join(
                    "%s/%s%s" % (getattr(t, "lang", "?"), getattr(t, "codec", "?"),
                                 " text" if getattr(t, "text", False) else " bitmap"
                                 if getattr(t, "bitmap", False) else "") for t in tracks) or "none"))
        except Exception as exc:
            extra.append("reading %s raised %s: %s" % (video, type(exc).__name__, exc))
    else:
        extra.append("pass --video <file> to read one video through it")
    ro.add("track reader", OK, "tsubasa.%s" % reader, extra)


def _capture_traps(ro, capture, session, api_get, full_url, sleep, rng, files_list):
    """The captures beyond the readout.

    ⛔ Not one budget check in here. Every metered call goes through `api_get`,
    which refuses at the floor and after a 401 and raises BudgetSpent, so the
    sequence stops wherever the budget runs out and says what it did not capture
    -- and a capture added later cannot be added with its check left behind.
    """
    try:
        _traps(ro, capture, session, api_get, full_url, sleep, rng)
    except BudgetSpent as exc:
        capture.missing("the rest", str(exc))
    # ⚠ Recorded however far the run got: it is a fact about what can NEVER be
    # captured, not about this run.
    capture.missing("api__429", "NOT PROVOKED: a 429 needs more than 25 requests in 60 s, "
                    "which Whitelist 2 forbids (spec/03-permissions.md). Build the 429 "
                    "path from these real rate-limit headers instead.")


def _traps(ro, capture, session, api_get, full_url, sleep, rng):
    # 1. an EMPTY query: the catalogue-dump trap. Metadata only.
    _pause(sleep, rng)
    resp, url = api_get("/entries/search", {"query": ""})
    try:
        body = resp.json()
        count = len(body) if isinstance(body, list) else None
        first_ids = [e.get("id") for e in body[:3]] if isinstance(body, list) else None
    except ValueError:
        count, first_ids = None, None
    capture.meta_only("search__query_empty", resp, full_url(resp, url, {"query": ""}),
                      "THE CATALOGUE-DUMP TRAP. An empty query scores 100 and returns "
                      "every entry. Kept as a COUNT only: storing the body would mirror "
                      "the catalogue (Whitelist 2).",
                      extra={"entries_returned": count, "first_ids": first_ids})

    # 2. a live-action show: anime=true (the default) gates before the match.
    _pause(sleep, rng)
    resp, url = api_get("/entries/search", {"query": LIVE_ACTION_QUERY})
    capture.body_and_meta("search__live_action_anime_default", resp,
                          full_url(resp, url, {"query": LIVE_ACTION_QUERY}),
                          "anime defaults to TRUE and gates BEFORE the id match: a "
                          "live-action entry returns [] here.")
    _pause(sleep, rng)
    params = {"query": LIVE_ACTION_QUERY, "anime": "false"}
    resp, url = api_get("/entries/search", params)
    capture.body_and_meta("search__anime_false_retry", resp, full_url(resp, url, params),
                          "the retry with anime=false that finds it.")

    # 3. a movie-flagged entry, and its files.
    movie = None
    for query in MOVIE_QUERIES:
        _pause(sleep, rng)
        resp, url = api_get("/entries/search", {"query": query})
        try:
            hits = resp.json()
        except ValueError:
            hits = []
        movie = next((e for e in hits if isinstance(e, dict)
                      and (e.get("flags") or {}).get("movie") is True), None)
        if movie:
            capture.body_and_meta("search__movie", resp, full_url(resp, url, {"query": query}),
                                  "a search whose results include a flags.movie == true entry")
            break
    if movie:
        _pause(sleep, rng)
        resp, url = api_get("/entries/%s/files" % movie.get("id"))
        capture.body_and_meta("entries_movie_flag", resp, url,
                              "files of entry %s (%s), flags.movie == true: episode "
                              "matching is skipped entirely (06-edge-cases.md §3)"
                              % (movie.get("id"), movie.get("name")))
    else:
        capture.missing("entries_movie_flag", "no flags.movie entry in the results for %s"
                        % ", ".join(MOVIE_QUERIES))

    # 4. an invalid entry id -- through the API, and through the unmetered route.
    _pause(sleep, rng)
    resp, url = api_get("/entries/%d/files" % INVALID_ENTRY)
    capture.body_and_meta("entries_invalid_id_files", resp, url,
                          "trap 4: what an invalid entry id returns through the API")
    bad_dl = SITE + "/entry/%d/download/hato-doctor-probe.srt" % INVALID_ENTRY
    try:
        dl = session.get(bad_dl, headers={"User-Agent": USER_AGENT}, timeout=30,
                         allow_redirects=False)
        ro.unmetered += 1
        body = dl.content or b""
        sniffed = sniff_encoding(body)
        # ⛔ The first bytes are kept ONLY when they are an HTML page. Were this
        # route ever to answer with a real subtitle, its opening lines would be
        # third-party content written into an auto-committing repo.
        capture.meta_only("download__invalid_id", dl, bad_dl,
                          "trap 4 on the unmetered route: status, final URL and what "
                          "came back, so the client can tell an error page from a subtitle",
                          extra={"content_type": dl.headers.get("content-type"),
                                 "sniffed": sniffed,
                                 "first_bytes": (body[:160].decode("utf-8", "replace")
                                                 if sniffed == "HTML, not a subtitle"
                                                 else "(not kept: not an HTML page)")})
    except Exception as exc:
        capture.missing("download__invalid_id", "%s: %s" % (type(exc).__name__, exc))

    # 5. what a REAL release filename sends, and a query that matches nothing --
    # both missing from the first capture (found by the 2b builder, 2026-09-17):
    # identification could only be proved offline on `query=frieren`, and the
    # Kitsu fallback ran on derived stand-ins.
    for stem, query, note in (
            ("search__query_sousou_no_frieren", "Sousou no Frieren",
             "what tsubasa's parse of a real release name sends as the query"),
            ("search__no_match", "hato doctor no such show zqxv",
             "a query that matches nothing: the path to the anime=false retry and Kitsu")):
        _pause(sleep, rng)
        resp, url = api_get("/entries/search", {"query": query})
        capture.body_and_meta(stem, resp, full_url(resp, url, {"query": query}), note)

    # 6. a deliberately invalid key -> 401. LAST, and exactly once.
    _pause(sleep, rng)
    resp, url = api_get("/entries/search", {"query": "frieren"},
                        raw_key="hato-doctor-deliberately-invalid-key")
    capture.body_and_meta("search__401_bad_key", resp, full_url(resp, url, {"query": "frieren"}),
                          "a deliberately invalid key. The rate-limit headers show whether "
                          "a 401 still consumes quota (spec/08-research.md).")


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(ro, when=None):
    when = when or datetime.now().strftime("%Y-%m-%d %H:%M")
    out = ["hato doctor  %s  %s" % (__version__, when), ""]
    for line in ro.lines:
        state = "" if line.state == OK else line.state + " -- "
        out.append("  %-13s%s%s" % (line.label, state, line.text))
        for extra in line.extra:
            out.append("  %-13s%s" % ("", extra))
    if ro.captured or ro.capture_missing:
        out.append("")
        out.append("  captured     %d file(s)" % len(ro.captured))
        for path, _ in ro.captured:
            out.append("  %-13s%s" % ("", path))
        for name, reason in ro.capture_missing:
            out.append("  %-13sNOT CAPTURED -- %s: %s" % ("", name, reason))
    return "\n".join(out)
