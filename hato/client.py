# -*- coding: utf-8 -*-
"""
The jimaku client (spec/RUNBOOK.md 2a and 2c). Every request hato makes to
jimaku.cc goes through here.

    client = JimakuClient(key)                  key: a hato.credentials.Key
    client.search("frieren")                    -> [entry dict]   1 metered call
    client.search("Kamen Rider Decade", anime=False)
    client.search(anilist_id=154587)
    client.files(11446)                         -> [file dict]    1 metered call
    client.download(file)                       -> bytes          unmetered, sent with no key
    client.metered · client.unmetered · client.last_rate_headers · client.waits

    session = RecordedSession("tests/fixtures") `--fixtures DIR`: recorded responses,
    client = JimakuClient(key, session)         served by the real requests machinery,
                                                never a socket

Every rule below was measured (spec/08-research.md) and is a check in
tests/test_client.py:

- 🚨 `Authorization: <key>` RAW -- no `Bearer`. Set per request by an auth object,
  never on the session, so a download cannot inherit it and ~/.netrc cannot
  replace it.
- 🚨 A 401 RAISES KeyRejected ONCE. A rejected request still spends quota, so it is
  never retried, and every later call on this client raises KeyRejected without
  touching the network: the run stops (spec/06-edge-cases.md §4).
- ⛔ AN EMPTY QUERY IS REFUSED BEFORE THE REQUEST. No query scores 100 and returns
  the entire catalogue (4,533 entries, measured).
- ⛔ `episode=` IS NEVER SENT. The server runs anitomy over every filename and
  silently drops what it cannot parse. `files()` takes an entry id and nothing
  else, and the id must be a plain number, so nothing can ride in on it.
- ⚠ AN INVALID ENTRY ID IS A 404 through the API (measured 2026-09-17) ->
  EntryNotFound. The url guard stays as defence: every file's url must be
  https://jimaku.cc with a PARSED, unquoted path under /entry/<id>/download/ --
  the urls are absolute and percent-encoded, so a raw startswith() would refuse
  every real file.
- ⭐ RATE LIMITS ARE READ, NEVER MODELLED. Each metered answer's headers are kept;
  at `remaining` 0 the next call waits for `x-ratelimit-reset` (an integer epoch,
  measured), and ⚠ WHEN THAT HEADER IS ABSENT OR UNREADABLE IT WAITS THE
  DOCUMENTED WINDOW ANYWAY -- `remaining: 0` alone says the budget is gone, and
  this API is already known to omit rate-limit headers (measured). A 429 honours
  `x-ratelimit-reset-after` (fractional, and ABSENT outside a 429 -- measured),
  else `reset`, else one window.
- ⛔ A FILE IS REFUSED FOR ITS NAME AS WELL AS ITS URL. A jimaku file has no
  episode field -- the number lives only in `name` -- and every caller indexes
  `file["name"]`, so a listed file without one is refused, not returned.
- ⭐ EVERY WAIT IS JITTERED. A request every 1.500 s forever is a strange shape in
  someone's access log.
- THE UNREACHABLE LADDER. A request that never got an HTTP answer is retried after
  5 s, 15 s, 45 s (jittered; the 45 s rung repeats). The 6th consecutive such
  failure, across the whole run, raises Unreachable, and no further attempt is
  ever made. Any HTTP answer -- whatever its status -- resets the count.
- ⛔ HATO_NO_NETWORK=1 REFUSES EVERY CALL before a session is touched
  (NetworkDisabled) -- except through a RecordedSession, which cannot reach a
  network by construction.

Decisions made here where the spec left room (each stated in the build report):

- a 5xx is an ANSWER, not an outage: raised once as JimakuError, never retried.
  A retry spends quota on a server that just said it is failing, and a
  scheduled run comes back tomorrow
- a 3xx is refused, never followed: none was ever measured, and following one
  could carry the key to another host
- `metered` counts ANSWERS from /api, every status (a 401, a 404 and a 429 each
  spend quota); an attempt that never got an answer is not an API call
- a download is capped (MAX_DOWNLOAD_BYTES) and a body past the cap is aborted and
  raised, never truncated; a connection dropped mid-body is a DownloadError and
  is not retried -- the server was reached, and the fetch loop moves on
- downloads are not paced: they are unmetered, and a folder's worth is the burst
  a browser would make
"""
import http.client
import io
import json
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import requests
from requests.adapters import BaseAdapter
from requests.auth import AuthBase
from requests.structures import CaseInsensitiveDict

from hato import __version__, credentials

API = "https://jimaku.cc/api"
HOST = "jimaku.cc"
USER_AGENT = "hato/%s" % __version__

RATE_HEADERS = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                "x-ratelimit-reset-after")

#: (connect, read) seconds.
API_TIMEOUT = (10, 30)
DOWNLOAD_TIMEOUT = (10, 60)
#: A jittered gap between consecutive metered calls, in seconds.
PACE = (1.0, 2.0)
#: jimaku's documented window: 25 requests / 60 s per IP. An epoch-derived wait is
#: never longer than this -- a `reset` further out than one window says the local
#: clock disagrees with the server's, not that the budget needs longer to refill.
WINDOW = 60.0
#: Added to every rate-limit wait, so a wait never lands exactly on the boundary.
RESET_JITTER = (0.25, 1.25)
#: The most one request may wait on 429s, in total. Past it: RateLimited.
MAX_RATE_WAIT = 120.0
#: The unreachable ladder, and its jitter as a multiplier (never shorter than the rung).
LADDER = (5.0, 15.0, 45.0)
LADDER_JITTER = (1.0, 1.25)
#: Consecutive attempts with no HTTP answer, across the run, before it stops.
UNREACHABLE_STOP = 6
#: The largest file on the recorded entries is 6.4 MB (a .7z of bitmap subtitles);
#: a subtitle is tens of KB. A body past this is aborted, never kept truncated.
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
_CHUNK = 64 * 1024

#: No HTTP answer came back. ChunkedEncodingError is a body that dropped inside a
#: non-streamed API call; a streamed download's body is handled apart.
_NO_ANSWER = (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
              requests.exceptions.ChunkedEncodingError)
_DIGITS = re.compile(r"[0-9]+\Z")


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class JimakuError(Exception):
    """A jimaku request could not do what was asked. `status` is the HTTP status
    when there was an answer, else None."""

    def __init__(self, message, status=None):
        super(JimakuError, self).__init__(message)
        self.status = status


class EmptyQuery(JimakuError):
    """An empty query was refused before any request -- it returns the catalogue."""


class KeyRejected(JimakuError):
    """jimaku answered 401. The run stops: every retry would spend quota too."""


class NetworkDisabled(JimakuError):
    """HATO_NO_NETWORK=1: nothing was sent."""


class Unreachable(JimakuError):
    """UNREACHABLE_STOP consecutive attempts got no answer. The run stops."""


class EntryNotFound(JimakuError):
    """jimaku has no such entry (HTTP 404)."""


class BadFile(JimakuError):
    """jimaku listed something hato cannot treat as a file. Never downloaded."""


class BadFileUrl(BadFile):
    """A file's url is not jimaku's download route for its entry. Never downloaded."""


class BadFileName(BadFile):
    """A file has no usable `name`. There is no episode field on a jimaku file --
    the episode number exists ONLY inside the name -- and every caller indexes
    `file["name"]` directly, so a nameless file is not a file."""


class DownloadError(JimakuError):
    """A download came back unusable: empty, truncated, HTML, too big, or dropped."""


class DownloadNotFound(JimakuError):
    """The download 404'd -- the file list is stale. The fetch loop re-lists once."""


class RateLimited(JimakuError):
    """429s asked for more waiting than MAX_RATE_WAIT. Stopped rather than hang."""


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _number(value):
    """A header value as a float, or None. Both `reset` and `reset-after` may be
    fractional (spec/03-permissions.md)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n and abs(n) != float("inf") else None


def _plain_id(what, value):
    """-> a positive int. A str is accepted only when it is ASCII digits, so
    `"11446?episode=1"` can never reach a URL."""
    if type(value) is int and value > 0:            # ⚠ bool is an int: True is not 1
        return value
    if isinstance(value, str) and _DIGITS.match(value) and int(value) > 0:
        return int(value)
    raise ValueError("%s must be a plain positive number, got %r -- nothing else may "
                     "ride into a request" % (what, value))


def _file_name(file, what="a file"):
    """-> the file's name, or raise BadFileName.

    🚨 `files()` validated every url and NOTHING else, so a file with no `name`
    key came back intact into callers that index `file["name"]` -- measured
    2026-09-17. A jimaku file carries no episode field: the episode number lives
    only inside the name (spec/08-research.md), the kept original is named from
    it (`<stem>.ja.<ext>`, Whitelist 1), and the ranker reads it. There is
    nothing hato can do with a nameless one but refuse it by name.
    """
    if not isinstance(file, dict):
        raise BadFileName("%s must be one of the dicts files() returned, got %s"
                          % (what, type(file).__name__))
    name = file.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BadFileName("refused a file jimaku listed with no usable name (%r): the "
                          "episode number and the language tag live only in the name, so "
                          "there is nothing to match, rank or save it as -- %s"
                          % (name, file.get("url") or "and it has no url either"))
    return name


def _file_url(file, entry_id=None):
    """-> the file's url, or raise BadFileUrl. ⛔ Tested on the PARSED url: the host
    must be jimaku.cc over https, and the unquoted path /entry/<id>/download/<name>
    -- for `entry_id`, when given. Measured: every real url is absolute and
    percent-encoded, so testing the raw string would refuse every real file."""
    if not isinstance(file, dict):
        raise BadFileUrl("a file must be one of the dicts files() returned, got %s"
                         % type(file).__name__)
    url, name = file.get("url"), file.get("name")
    label = name if isinstance(name, str) and name else "(a file with no name)"
    if not isinstance(url, str) or not url.strip():
        raise BadFileUrl("refused %s: it has no url" % label)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise BadFileUrl("refused %s: its url does not parse (%s) -- %s" % (label, exc, url))
    if (parts.scheme.lower() != "https" or (parts.hostname or "").lower() != HOST
            or port not in (None, 443) or parts.username or parts.password):
        raise BadFileUrl("refused %s: its url is not https://%s -- %s" % (label, HOST, url))
    if parts.query or parts.fragment:
        raise BadFileUrl("refused %s: its url carries a query or a fragment -- %s" % (label, url))
    segments = unquote(parts.path).split("/")
    if (len(segments) < 5 or segments[0] != "" or segments[1] != "entry"
            or not _DIGITS.match(segments[2]) or segments[3] != "download"
            or not "/".join(segments[4:]).strip()
            or any(s in (".", "..") for s in segments[4:])):
        raise BadFileUrl("refused %s: its url path is not /entry/<id>/download/<name> -- %s"
                         % (label, url))
    if entry_id is not None and int(segments[2]) != entry_id:
        raise BadFileUrl("refused %s: its url belongs to entry %s, not entry %d -- %s"
                         % (label, segments[2], entry_id, url))
    return url


#: ⭐ THE ONE FILE-URL GUARD, under a public name. `hato doctor` downloads through
#: this and not a second copy of it: its own two-line version took `url` from the
#: file dict and prefixed the site only when it started with `/`, so a crafted
#: `https://evil.example/entry/...` was fetched and the readout said `download ok
#: HTTP 200` -- measured 2026-09-17. An alias, never a reimplementation: one
#: object, two names, so the two can never disagree.
file_url = _file_url
file_name = _file_name


def _looks_like_html(data):
    """A subtitle never starts with `<!DOCTYPE` or `<html` (spec/06-edge-cases.md §4)."""
    head = bytes(data[:512])
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    head = head.lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def _server_says(resp):
    """` -- "<error>"` from jimaku's JSON error body, or ""."""
    try:
        said = json.loads(resp.content.decode("utf-8")).get("error")
    except Exception:
        return ""
    return ' -- "%s"' % said if isinstance(said, str) and said else ""


def _json_list(resp, what):
    try:
        data = json.loads(resp.content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise JimakuError("jimaku answered %s with a body that is not UTF-8 JSON (%s)"
                          % (what, exc), status=resp.status_code)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise JimakuError("jimaku answered %s with %s, not a list of objects"
                          % (what, type(data).__name__), status=resp.status_code)
    return data


class _RawKey(AuthBase):
    """`Authorization: <key>`, raw -- the server passes the header's string straight
    to its session validator. There is no Bearer prefix."""

    def __init__(self, key):
        self._key = key

    def __call__(self, request):
        request.headers["Authorization"] = self._key.reveal()
        return request


class _NoKey(AuthBase):
    """Downloads take no auth extractor at all. Strips any Authorization the session
    carries, and -- being an auth object -- stops ~/.netrc from adding one."""

    def __call__(self, request):
        request.headers.pop("Authorization", None)
        return request


# ---------------------------------------------------------------------------
# recorded responses -- `--fixtures DIR`
# ---------------------------------------------------------------------------

class NoRecording(LookupError):
    """No recorded response answers a request. Nothing was sent anywhere."""


def network_disabled(session):
    """True when HATO_NO_NETWORK=1 forbids a request through `session`. Only a
    RecordedSession -- which has no transport but the disk -- is exempt."""
    return os.environ.get("HATO_NO_NETWORK") == "1" and not isinstance(session, RecordedSession)


def _request_key(url):
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    return (scheme, (parts.hostname or "").lower(),
            parts.port or {"https": 443, "http": 80}.get(scheme),
            unquote(parts.path),
            tuple(sorted(parse_qsl(parts.query, keep_blank_values=True))))


class _RecordedAdapter(BaseAdapter):
    def __init__(self, owner):
        super(_RecordedAdapter, self).__init__()
        self._owner = owner

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        return self._owner._answer(request)

    def close(self):
        pass


class RecordedSession(requests.Session):
    """A requests.Session whose ONLY transport is what `hato doctor --capture`
    recorded -- `<stem>.json` beside `<stem>.meta.json`, anywhere under `directory`.
    requests still builds every URL, parameter and header; the answer comes from
    disk. ⛔ It cannot reach a network: every scheme is served by the recorded
    adapter, and nothing can be mounted over it.

    A request matches a recording on scheme, host, port, the unquoted path and the
    decoded query pairs (so `+` and `%20` agree). ⚠ `search?query=frieren` was
    recorded twice -- with the real key and with a deliberately invalid one -- and
    the session cannot see which key made a recording, so an answer that is not a
    401 wins; `stems=` picks recordings explicitly. ⛔ A recording kept as metadata
    only (a subtitle body, the catalogue dump) has no body, and is refused, never
    faked.
    """

    def __init__(self, directory, stems=None):
        self._sealed = False
        super(RecordedSession, self).__init__()
        for adapter in self.adapters.values():
            adapter.close()
        self.adapters.clear()
        self.trust_env = False
        self.directory = Path(directory)
        #: [{"method", "url", "headers"}] -- every request, as requests prepared it
        self.calls = []
        self._recordings = {}
        self._load(stems)
        self._adapter = _RecordedAdapter(self)
        self.adapters["https://"] = self._adapter
        self.adapters["http://"] = self._adapter
        self._sealed = True

    def mount(self, prefix, adapter):
        if getattr(self, "_sealed", False):
            raise TypeError("a RecordedSession serves recordings only -- nothing may be "
                            "mounted over it")
        super(RecordedSession, self).mount(prefix, adapter)

    def get_adapter(self, url):
        return self._adapter

    def _load(self, stems):
        if not self.directory.is_dir():
            raise NoRecording("--fixtures %s: no such folder" % self.directory)
        wanted = set(stems) if stems is not None else None
        found = set()
        for meta_path in sorted(self.directory.rglob("*.meta.json")):
            stem = meta_path.name[:-len(".meta.json")]
            if wanted is not None and stem not in wanted:
                continue
            with open(str(meta_path), encoding="utf-8") as fh:
                meta = json.load(fh)
            url = meta.get("url") or meta.get("final_url")
            if not isinstance(url, str) or not url:
                continue
            self._recordings.setdefault(_request_key(url), []).append(
                (stem, meta, meta_path.with_name(stem + ".json")))
            found.add(stem)
        if wanted is not None and wanted - found:
            raise NoRecording("no recording named %s under %s"
                              % (", ".join(sorted(wanted - found)), self.directory))
        if not found:
            raise NoRecording("no recordings (*.meta.json) under %s" % self.directory)

    def _answer(self, request):
        self.calls.append({"method": request.method, "url": request.url,
                           "headers": dict(request.headers)})
        if request.method != "GET":
            raise NoRecording("only GET is ever recorded, not %s %s" % (request.method, request.url))
        found = self._recordings.get(_request_key(request.url))
        if not found:
            raise NoRecording("nothing recorded under %s answers GET %s -- recordings are made "
                              "by `hato doctor --capture`, never by hand"
                              % (self.directory, request.url))
        stem, meta, body_path = sorted(found, key=lambda r: (r[1].get("status") == 401, r[0]))[0]
        if not meta.get("body_kept"):
            raise NoRecording("%s was recorded as metadata only, so there is no body to serve (%s)"
                              % (stem, meta.get("note") or "no note"))
        resp = requests.Response()
        resp.status_code = int(meta.get("status"))
        resp.reason = http.client.responses.get(resp.status_code, "")
        resp.headers = CaseInsensitiveDict(meta.get("response_headers") or {})
        resp.raw = io.BytesIO(body_path.read_bytes())
        resp.url = request.url
        resp.request = request
        return resp


# ---------------------------------------------------------------------------
# the client
# ---------------------------------------------------------------------------

class JimakuClient(object):
    """One client per run: its counters, its stops and its rate-limit reading
    belong to the run."""

    def __init__(self, key, session=None, *, sleep=time.sleep, clock=time.time, rng=None,
                 max_download_bytes=MAX_DOWNLOAD_BYTES):
        if not isinstance(key, credentials.Key):
            raise TypeError("key must be a hato.credentials.Key -- a bare string would "
                            "print whole in a traceback")
        if type(max_download_bytes) is not int or max_download_bytes <= 0:
            raise ValueError("max_download_bytes must be a positive int, got %r"
                             % (max_download_bytes,))
        self._key = key
        self._session = session
        self._sleep = sleep
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self.max_download_bytes = max_download_bytes
        #: HTTP answers from /api -- every status. What the CLI prints as "N API calls".
        self.metered = 0
        #: HTTP answers from the download route.
        self.unmetered = 0
        #: The rate-limit headers of the last metered answer, verbatim (--verbose).
        self.last_rate_headers = {}
        #: [(seconds, why)] -- every wait this client made.
        self.waits = []
        self._remaining = None
        self._reset_at = None
        self._last_metered_at = None
        self._failures = 0
        self._rejected = None           # KeyRejected's message, once jimaku refused the key
        self._unreachable = None        # Unreachable's message, once the run stopped

    def __repr__(self):
        return "<hato JimakuClient, key ending %s, %d metered, %d unmetered>" % (
            self._key.hint, self.metered, self.unmetered)

    # -- the three calls ------------------------------------------------------

    def search(self, query=None, *, anime=True, anilist_id=None):
        """-> [entry dict]. `anime` defaults to TRUE server-side and gates before the
        match: a live-action entry returns [] until asked with anime=False."""
        if query is not None and not isinstance(query, str):
            raise TypeError("query must be a str, got %s" % type(query).__name__)
        if not isinstance(anime, bool):
            raise TypeError("anime must be True or False, got %r" % (anime,))
        text = (query or "").strip()
        if anilist_id is not None:
            anilist_id = _plain_id("anilist_id", anilist_id)
        if not text and anilist_id is None:
            raise EmptyQuery("refused to search jimaku with an EMPTY query: no query scores 100 "
                             "and returns the entire catalogue. Nothing was sent.")
        params = []
        if text:
            params.append(("query", text))
        if not anime:
            params.append(("anime", "false"))
        if anilist_id is not None:
            params.append(("anilist_id", str(anilist_id)))
        what = "GET /api/entries/search?%s" % "&".join("%s=%s" % kv for kv in params)
        resp = self._api("/entries/search", params, what)
        if resp.status_code != 200:
            raise JimakuError("jimaku answered HTTP %d on %s%s"
                              % (resp.status_code, what, _server_says(resp)),
                              status=resp.status_code)
        return _json_list(resp, what)

    def files(self, entry_id):
        """-> every file on the entry, as jimaku lists it. ⛔ No `episode=`, ever."""
        entry_id = _plain_id("entry_id", entry_id)
        what = "GET /api/entries/%d/files" % entry_id
        resp = self._api("/entries/%d/files" % entry_id, None, what)
        if resp.status_code == 404:
            raise EntryNotFound("jimaku has no entry %d (HTTP 404 on %s%s)"
                                % (entry_id, what, _server_says(resp)), status=404)
        if resp.status_code != 200:
            raise JimakuError("jimaku answered HTTP %d on %s%s"
                              % (resp.status_code, what, _server_says(resp)),
                              status=resp.status_code)
        listed = _json_list(resp, what)
        for item in listed:
            _file_name(item)            # ⛔ BOTH halves, or a nameless file rides through
            _file_url(item, entry_id)
        return listed

    def download(self, file):
        """-> the file's bytes, exactly as served. Unmetered, and sent with NO key."""
        name = _file_name(file, "the file to download")
        url = _file_url(file)
        size = file.get("size")
        size = size if type(size) is int and size > 0 else None
        self._refuse_if_stopped()
        self._refuse_if_offline()
        what = "the download of %s" % name
        resp = self._send(url, None, _NoKey(), True, DOWNLOAD_TIMEOUT, what)
        self.unmetered += 1
        body = bytearray()
        try:
            if resp.status_code == 404:
                raise DownloadNotFound("%s is gone (HTTP 404) -- the file list is stale" % name,
                                       status=404)
            if resp.status_code != 200:
                raise DownloadError("%s answered HTTP %d" % (what, resp.status_code),
                                    status=resp.status_code)
            declared = _number(resp.headers.get("content-length"))
            if (declared is not None and not resp.headers.get("content-encoding")
                    and declared > self.max_download_bytes):
                raise DownloadError("%s declares %d bytes, past the %d-byte cap -- nothing was "
                                    "read" % (what, declared, self.max_download_bytes), status=200)
            try:
                for chunk in resp.iter_content(_CHUNK):
                    body += chunk
                    if len(body) > self.max_download_bytes:
                        raise DownloadError("%s passed the %d-byte cap -- aborted, nothing kept"
                                            % (what, self.max_download_bytes), status=200)
            except requests.exceptions.RequestException as exc:
                raise DownloadError("%s dropped after %d bytes (%s: %s)"
                                    % (what, len(body), type(exc).__name__, exc), status=200)
        finally:
            resp.close()
        if not body:
            raise DownloadError("%s came back EMPTY -- a zero-byte subtitle is never kept" % what,
                                status=200)
        if _looks_like_html(body):
            raise DownloadError("%s came back as an HTML page, not a subtitle" % what, status=200)
        if size is not None and len(body) < size:
            raise DownloadError("%s is truncated: %d of the %d bytes jimaku lists"
                                % (what, len(body), size), status=200)
        return bytes(body)

    # -- the machinery ----------------------------------------------------------

    def _refuse_if_stopped(self):
        if self._rejected is not None:
            raise KeyRejected(self._rejected, status=401)
        if self._unreachable is not None:
            raise Unreachable(self._unreachable)

    def _refuse_if_offline(self):
        if network_disabled(self._session):
            raise NetworkDisabled("HATO_NO_NETWORK=1 -- the network is switched off, so nothing "
                                  "was sent to jimaku. Unset it, or serve recorded responses "
                                  "with --fixtures DIR.")

    def _http(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _wait(self, seconds, why):
        if seconds <= 0:
            return
        self.waits.append((seconds, why))
        self._sleep(seconds)

    def _send(self, url, params, auth, stream, timeout, what):
        """One request, climbing the unreachable ladder until it gets an HTTP answer
        or the run stops."""
        while True:
            try:
                resp = self._http().get(url, params=params, auth=auth, stream=stream,
                                        headers={"User-Agent": USER_AGENT}, timeout=timeout,
                                        allow_redirects=False)
            except _NO_ANSWER as exc:
                self._failures += 1
                if self._failures >= UNREACHABLE_STOP:
                    self._unreachable = (
                        "jimaku could not be reached %d times in a row (last: %s on %s: %s). "
                        "hato stopped here rather than fail every file one by one -- check the "
                        "connection and run again."
                        % (self._failures, type(exc).__name__, what, exc))
                    raise Unreachable(self._unreachable)
                rung = LADDER[min(self._failures, len(LADDER)) - 1]
                self._wait(rung * self._rng.uniform(*LADDER_JITTER),
                           "%s got no answer (%s), attempt %d of at most %d"
                           % (what, type(exc).__name__, self._failures, UNREACHABLE_STOP))
                continue
            except requests.exceptions.RequestException as exc:
                raise JimakuError("%s could not be sent (%s: %s)" % (what, type(exc).__name__, exc))
            self._failures = 0
            return resp

    def _pace(self):
        if self._last_metered_at is not None:
            gap = self._rng.uniform(*PACE)
            elapsed = self._clock() - self._last_metered_at
            if elapsed < gap:
                self._wait(gap - elapsed, "pacing between metered calls")
        if self._remaining is not None and self._remaining <= 0:
            if self._reset_at is None:
                # 🚨 The wait used to require a readable `reset`, so `remaining: 0`
                # with the header ABSENT, empty or non-numeric bought no wait at
                # all -- measured 2026-09-17, and not hypothetical: this API
                # already omits x-ratelimit-reset-after on 200, 401 and 404, so a
                # header hato needs going missing is the normal case, not the
                # strange one. "Read the headers and obey them"
                # (spec/03-permissions.md) cannot mean "obey them only when they
                # parse": `remaining: 0` on its own says the budget is gone, and
                # the documented window is what refills it.
                self._wait(WINDOW + self._rng.uniform(*RESET_JITTER),
                           "x-ratelimit-remaining is 0 and no readable x-ratelimit-reset "
                           "came with it: waiting jimaku's documented %.0f s window" % WINDOW)
            else:
                until = self._reset_at - self._clock()
                if until > 0:
                    self._wait(min(until, WINDOW) + self._rng.uniform(*RESET_JITTER),
                               "x-ratelimit-remaining is 0: waiting for x-ratelimit-reset")
                # ⚠ A reset already in the past is not a missing one: the window it
                # names has refilled, so there is nothing left to wait for.
            self._remaining = None

    def _after_429(self, headers):
        after = _number(headers.get("x-ratelimit-reset-after"))
        if after is not None and after >= 0:
            base = after
        else:
            reset = _number(headers.get("x-ratelimit-reset"))
            base = min(max(reset - self._clock(), 0.0), WINDOW) if reset is not None else WINDOW
        return base + self._rng.uniform(*RESET_JITTER)

    def _note_rate(self, headers):
        kept = {}
        for name in RATE_HEADERS:
            value = headers.get(name)
            if value is not None:
                kept[name] = value
        self.last_rate_headers = kept
        self._remaining = _number(kept.get("x-ratelimit-remaining"))
        reset = _number(kept.get("x-ratelimit-reset"))
        if reset is None:
            # ⭐ Whichever of the two the server sent. `reset-after` was measured
            # ABSENT on 200, 401 and 404 -- but "absent here" is not "never sent",
            # and obeying the one that arrived is the rule.
            after = _number(kept.get("x-ratelimit-reset-after"))
            reset = self._clock() + after if after is not None and after >= 0 else None
        self._reset_at = reset
        # ⛔ NOT modelled locally: a metered answer with no x-ratelimit-remaining at
        # all leaves the budget UNKNOWN, and hato paces rather than invent a number
        # (spec/03-permissions.md: "do not model the budget locally and hope").

    def _api(self, path, params, what):
        self._refuse_if_stopped()
        self._refuse_if_offline()
        waited = 0.0
        while True:
            self._pace()
            resp = self._send(API + path, params, _RawKey(self._key), False, API_TIMEOUT, what)
            self.metered += 1
            self._last_metered_at = self._clock()
            self._note_rate(resp.headers)
            status = resp.status_code
            if status == 401:
                self._rejected = (
                    "jimaku REJECTED the API key ending %s (HTTP 401 on %s). A rejected request "
                    "still spends quota, so hato sent nothing more. Mint a new key at "
                    "https://jimaku.cc/account" % (self._key.hint, what))
                raise KeyRejected(self._rejected, status=401)
            if status == 429:
                wait = self._after_429(resp.headers)
                if waited + wait > MAX_RATE_WAIT:
                    raise RateLimited(
                        "jimaku answered HTTP 429 on %s and the headers ask for a %.1f s wait "
                        "(%s) -- with %.1f s already waited that passes hato's %.0f s cap, so it "
                        "stopped instead of hanging"
                        % (what, wait, ", ".join("%s: %s" % kv for kv in
                                                 sorted(self.last_rate_headers.items()))
                           or "no rate-limit headers", waited, MAX_RATE_WAIT), status=429)
                waited += wait
                self._wait(wait, "HTTP 429 on %s" % what)
                # The 429's wait IS the reset wait: its `remaining: 0` must not buy a
                # second one before the retry.
                self._remaining = None
                continue
            if 300 <= status < 400:
                raise JimakuError("jimaku answered HTTP %d on %s, redirecting to %s -- hato never "
                                  "follows a redirect" % (status, what,
                                                          resp.headers.get("location") or "nowhere"),
                                  status=status)
            return resp
