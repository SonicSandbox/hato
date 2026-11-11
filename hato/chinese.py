# -*- coding: utf-8 -*-
u"""
⭐ LAYER 20 -- CHINESE SUBTITLES: assrt.net (射手网(伪)) first, OpenSubtitles when assrt.net
has nothing. Every request a Chinese run makes goes through here; a Japanese run never
builds this client (`commands/run.py` asks `config.is_chinese` first).

    client = ChineseClient(assrt=Key or None, opensubtitles=Key or None)
    client.search(u"Frieren")     -> [the title itself, as one entry]     no request
    client.files(entry_id)        -> [file dict]   assrt.net: 1-3 metered searches;
                                                   OpenSubtitles, only when assrt.net
                                                   gave nothing: 1-3 more
    client.download(file)         -> bytes         assrt.net: 1 metered detail + the file
                                                   OpenSubtitles: 1 metered POST + the file
    client.metered · client.unmetered · client.notes · client.provider_of(name)

⭐ THE SAME INTERFACE AS `JimakuClient`, so the pipeline -- alignment by each file's own
name, ranking, the timing verdict, the funnel, Surasura's hand-off -- runs unchanged. What
differs is said here once:

- ⭐ THERE IS NO "ENTRY". Neither service has jimaku's one-entry-per-show list. `search`
  answers the title back as one entry (an id made from the title) with NO request, and
  `files` searches by that title. `resolution.identify` never caches it (`jimaku` False):
  the cache's key is the title's, shared with every Japanese run.
- ⭐ ASSRT.NET'S ARCHIVES ARE LISTED BY MEMBER. `sub/search?filelist=1` names every file
  inside a season pack, and `sub/detail` gives each member its OWN download link -- so a
  member is a file like any jimaku file, and nothing is extracted. An upload that is one
  file gets its name from `videoname` plus the format `subtype` names; a download whose
  real name has another extension is refused, never relabelled.
- ⭐ OPENSUBTITLES' FILE NAMES CARRY NO EXTENSION (measured in its recorded answers:
  `Man.of.Steel.German.720p.BluRay.x264-EXQUiSiTE`). hato names one `<name>.<lang>.srt`
  (`zh-cn` / `zh-tw`, the service's own language code, so ranking can put simplified
  first) and asks the download for `sub_format=srt`, the format that name promises. A
  name with no episode number gets the service's own `SxxEyy` added.
- ⛔ ONLY CHINESE. assrt.net uploads whose language list names Chinese (简 · 繁 · 双语) or
  names none; OpenSubtitles `zh-cn` and `zh-tw` only. Machine-translated uploads are left
  out, and said.

The rules, each from the service's own documentation or a recorded answer
(TheForge `Workshop/hato/spec/08-research.md` §LAYER 20):

- 🚨 THE KEYS ARE THE LEARNER'S OWN (`credentials.SERVICES`): assrt.net's token is sent as
  `Authorization: Bearer` -- never in the URL, so no exception text or log carries it --
  and OpenSubtitles' as `Api-Key`. ⛔ Neither ever reaches a download link.
- 🚨 A REJECTED KEY IS NEVER RETRIED (assrt.net `20001 invalid token`, HTTP 400;
  OpenSubtitles HTTP 401/403 "You cannot consume this service"). While listing, the other
  source still answers and the note says so; with neither left the run stops (KeyRejected).
- ⭐ PACED FOR THE SMALLER BUDGET: assrt.net allows 20 requests a minute per token AND per IP
  (one shared pool) -- a metered call every 3.2-4.2 s; OpenSubtitles 5 a second -- every
  1.1-1.6 s. A quota answer (assrt.net `30900`, HTTP 429) waits and asks again, at most
  MAX_RATE_WAIT in all, then RateLimited stops the run.
- ⭐ OPENSUBTITLES' DAILY DOWNLOADS: 5 a day per IP without an account. When its download
  says none remain (`remaining` below 0, HTTP 406/407), every later OpenSubtitles file in
  the run is refused HERE, without a request, with the reset time it gave.
- ⛔ assrt.net asks that its download links are never stored ("每次生成的下载地址都是唯一的
  而且具有一定的有效时间"): a detail answer is reused for DETAIL_TTL seconds within one run,
  never written anywhere.
- ⭐ CREDIT, as assrt.net asks ("使用ASSRT API完全免费，但请在合适的位置添加来源说明及本站链接"):
  `CREDIT` is said in the run's notes whenever assrt.net listed a file, and in Settings.
- ⛔ HATO_NO_NETWORK=1 refuses every call, as the jimaku client does.
"""
import json
import os
import random
import re
import time
import zlib
from urllib.parse import urlsplit

import requests

from hato import __version__, credentials
from hato.client import (DownloadError, DownloadNotFound, EmptyQuery, EntryNotFound,
                         JimakuError, KeyRejected, NetworkDisabled, RateLimited, Unreachable,
                         network_disabled)

ASSRT_API = "https://api.assrt.net/v1"
OPENSUBTITLES_API = "https://api.opensubtitles.com/api/v1"
#: OpenSubtitles asks for the app's name and version (its getting-started page).
USER_AGENT = "hato v%s" % __version__

ASSRT = credentials.ASSRT
OPENSUBTITLES = credentials.OPENSUBTITLES
NAMES = {ASSRT: u"assrt.net", OPENSUBTITLES: u"OpenSubtitles"}
#: How the run's words name where a Chinese file comes from.
WHERE = u"assrt.net or OpenSubtitles"
#: ⭐ assrt.net's own suggested credit, with its link (its API page asks for both).
CREDIT = u"字幕服务由 assrt.net 提供 — https://assrt.net"

API_TIMEOUT = (10, 30)
DOWNLOAD_TIMEOUT = (10, 60)
#: Seconds between metered calls, jittered: 20/min (assrt.net) and 5/s (OpenSubtitles).
PACE = {ASSRT: (3.2, 4.2), OPENSUBTITLES: (1.1, 1.6)}
#: One quota window, waited when a quota answer names no time.
WINDOW = {ASSRT: 60.0, OPENSUBTITLES: 2.0}
RESET_JITTER = (0.25, 1.25)
MAX_RATE_WAIT = 120.0
LADDER = (5.0, 15.0, 45.0)
LADDER_JITTER = (1.0, 1.25)
UNREACHABLE_STOP = 6
#: Result pages read per title. assrt.net answers 15 uploads a page; OpenSubtitles 50.
PAGES = 3
ASSRT_PAGE = 15
#: assrt.net refuses a keyword shorter than 3 characters (`101`).
ASSRT_MIN_QUERY = 3
#: A detail answer's links are reused this long within a run, never stored.
DETAIL_TTL = 600.0
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
_CHUNK = 64 * 1024
OPENSUBTITLES_LANGUAGES = (u"zh-cn", u"zh-tw")
#: The subtitle files hato takes from either source -- text formats tsubasa times.
TEXT_FORMATS = (u"ass", u"ssa", u"srt", u"vtt")
#: assrt.net's language flags (`lang.langlist`) and words (`lang.desc`) that mean Chinese.
_ASSRT_CHINESE_FLAGS = frozenset(("langchs", "langcht", "langdou", "langchi", "langchn"))
_ASSRT_CHINESE_WORDS = (u"简", u"繁", u"簡", u"双语", u"雙語", u"中")
#: A videoname assrt.net gives when its uploader did not say (Bazarr's provider, measured).
_MEANINGLESS = (u"不知道",)
_NO_ANSWER = (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
              requests.exceptions.ChunkedEncodingError)
_ARCHIVE_MAGIC = (b"PK\x03\x04", b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c")
_SXXEYY = re.compile(r"s\d{1,2}\s*e\d{1,4}", re.I)


class SourceError(JimakuError):
    u"""A Chinese source could not do what was asked. A `JimakuError`, so the pipeline's
    per-show handling is the same: one show's failure is that show's."""


def _plural(n, word):
    return u"%d %s%s" % (n, word, u"" if n == 1 else u"s")


def _entry_id(text, taken):
    u"""A positive int for a title, the same in every run; a clash steps to the next free one."""
    n = (zlib.crc32(text.casefold().encode("utf-8")) & 0x7FFFFFFF) or 1
    # ⚠ casefolded both ways: `Frieren` and `frieren` are one title, whichever came first
    while n in taken and taken[n].casefold() != text.casefold():
        n = n % 0x7FFFFFFF + 1
    return n


def _unique(files):
    u"""⭐ Two uploads can carry ONE name (a `videoname` is the VIDEO's release, shared by
    every subtitle for it), and ranking drops a repeated name as a duplicate -- so the
    second upload would never be tried. The later ones get ` (2)`, ` (3)` before the
    extension (and before OpenSubtitles' language tag); the episode tsubasa reads from
    the name is unchanged (measured)."""
    seen = {}
    for f in files:
        name = f["name"]
        key = name.casefold()
        if key not in seen:
            seen[key] = 1
            continue
        seen[key] += 1
        stem, ext = os.path.splitext(name)
        tag = u""
        if f.get("source") == OPENSUBTITLES:
            stem, tag = os.path.splitext(stem)
        f["name"] = u"%s (%d)%s%s" % (stem, seen[key], tag, ext)
    return files


def _base(name):
    u"""A file name as one path segment: no folder (`Season 1/x.ass` -> `x.ass`), no NUL."""
    name = (u"%s" % (name or u"")).replace(u"\\", u"/").split(u"/")[-1]
    return u"".join(ch for ch in name if ch >= u" ").strip().strip(u".").strip()


def _ext(name):
    return os.path.splitext(name)[1][1:].lower()


def _subtype_ext(subtype):
    u"""assrt.net's `subtype` -> a text extension, or None (`VobSub` is pictures).
    `Subrip(srt)` -> srt; `ASS` -> ass."""
    text = (u"%s" % (subtype or u"")).lower()
    found = re.search(r"\(([a-z0-9]+)\)", text)
    word = found.group(1) if found else text.strip()
    return word if word in TEXT_FORMATS else None


def _is_chinese_upload(sub):
    u"""assrt.net's language list says Chinese, or says nothing. -> bool"""
    lang = sub.get("lang") if isinstance(sub.get("lang"), dict) else None
    if not lang:
        return True
    flags = lang.get("langlist") if isinstance(lang.get("langlist"), dict) else {}
    named = [k for k, v in flags.items() if v]
    desc = u"%s" % (lang.get("desc") or u"")
    if not named and not desc.strip():
        return True
    return bool(set(named) & _ASSRT_CHINESE_FLAGS) or any(w in desc for w in _ASSRT_CHINESE_WORDS)


def _assrt_time(value):
    u"""`2015-08-21 22:11:00` (Beijing time, no zone) -> ISO 8601 UTC, or None."""
    found = re.match(r"(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d):(\d\d)", u"%s" % (value or u""))
    if not found:
        return None
    import datetime
    try:
        at = datetime.datetime(*[int(g) for g in found.groups()],
                               tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    except ValueError:
        return None
    return at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _looks_like_html(data):
    head = bytes(data[:512]).lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


class ChineseClient(object):
    u"""One client per Chinese run: its counters, its stops and its pacing belong to the run."""

    #: ⭐ Not jimaku -- `resolution.identify` caches nothing, the pipeline names the source.
    jimaku = False
    where = WHERE

    def __init__(self, assrt=None, opensubtitles=None, session=None, *, sleep=time.sleep,
                 clock=time.time, rng=None, max_download_bytes=MAX_DOWNLOAD_BYTES):
        keys = {ASSRT: assrt, OPENSUBTITLES: opensubtitles}
        for service, key in keys.items():
            if key is not None and not isinstance(key, credentials.Key):
                raise TypeError("the %s key must be a hato.credentials.Key -- a bare string "
                                "would print whole in a traceback" % NAMES[service])
        if assrt is None and opensubtitles is None:
            raise ValueError("a Chinese run needs an assrt.net or an OpenSubtitles key")
        self._keys = keys
        self._session = session
        self._sleep = sleep
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self.max_download_bytes = max_download_bytes
        self.metered = 0
        self.unmetered = 0
        self.waits = []
        #: [str] -- what a listing should say; drained by the pipeline into the show's notes
        self.notes = []
        self._queries = {}              # entry id -> "<title>|<season>", what it searches
        self._seasons = {}              # entry id -> the season identify gave, or None
        self._providers = {}            # file name -> the service it came from
        self._details = {}              # assrt.net id -> (when, the detail answer)
        self._last = {ASSRT: None, OPENSUBTITLES: None}
        self._off = {ASSRT: None, OPENSUBTITLES: None}   # why a source is off for the run
        self._quota_out = None          # OpenSubtitles' downloads are used up: its words
        self._failures = 0
        self._unreachable = None

    def __repr__(self):
        return "<hato ChineseClient, %s, %d metered, %d unmetered>" % (
            ", ".join("%s key ending %s" % (NAMES[s], k.hint)
                      for s, k in sorted(self._keys.items()) if k is not None),
            self.metered, self.unmetered)

    def provider_of(self, name):
        u"""The service a listed file came from (`assrt` / `opensubtitles`), or None."""
        return self._providers.get(name)

    # -- the three calls ------------------------------------------------------

    def search(self, query=None, *, anime=True, anilist_id=None, season=None):
        u"""-> [the title as one entry]. ⛔ No request: neither service lists shows.
        `season` (from `resolution.identify`) is kept with it: OpenSubtitles is asked for
        that season, and a title's seasons are different entries."""
        if query is not None and not isinstance(query, str):
            raise TypeError("query must be a str, got %s" % type(query).__name__)
        if anilist_id is not None:
            return []
        text = (query or u"").strip()
        if not text:
            raise EmptyQuery("refused to search for an EMPTY title -- nothing was sent.")
        season = season if type(season) is int and season > 0 else None
        entry_id = _entry_id(u"%s|%s" % (text, season or u""), self._queries)
        self._queries[entry_id] = u"%s|%s" % (text, season or u"")
        self._seasons[entry_id] = season
        return [{"id": entry_id, "name": text, "flags": {"anime": bool(anime), "movie": False}}]

    def files(self, entry_id):
        u"""-> the title's Chinese files: assrt.net's, or OpenSubtitles' when assrt.net had none."""
        keyed = self._queries.get(entry_id) if type(entry_id) is int else None
        if keyed is None:
            raise EntryNotFound("no title was searched under %r in this run" % (entry_id,))
        text, season = keyed.rsplit(u"|", 1)[0], self._seasons.get(entry_id)
        self._refuse_if_stopped()
        said = []
        listed = []
        failed = None           # ⛔ a source that FAILED is never reported as "nothing there"
        answered = False        # ⛔ nor is one NEVER ASKED (a short title, a rejected key)
        if self._usable(ASSRT):
            if len(text) < ASSRT_MIN_QUERY:
                said.append(u'assrt.net was not asked: "%s" is shorter than the %d characters '
                            u"it searches by" % (text, ASSRT_MIN_QUERY))
            else:
                try:
                    listed, why = self._assrt_files(text)
                except KeyRejected as exc:
                    if not self._usable(OPENSUBTITLES):
                        raise
                    said.append(u"%s -- only OpenSubtitles is asked for the rest of this run" % exc)
                except (RateLimited, NetworkDisabled, Unreachable):
                    raise
                except JimakuError as exc:
                    failed = exc
                else:
                    if why is None:             # `101`: assrt.net would not search it
                        said.append(u'assrt.net would not search "%s" (too short for it)' % text)
                    else:
                        said.append(why)
                        answered = True
        if not listed and self._usable(OPENSUBTITLES):
            try:
                listed, why = self._opensubtitles_files(text, season)
            except KeyRejected as exc:
                if not self._usable(ASSRT):
                    raise
                said.append(u"%s -- only assrt.net is asked for the rest of this run" % exc)
            else:
                said.append(why)
                answered = True
        said = [s for s in said if s]
        if not listed and failed is not None:
            # the failure itself is the raise's to say; the other source's answer is a note
            self.notes.extend(said)
            raise failed
        if not listed and not answered:
            raise SourceError(u'"%s" could not be searched: %s. Add the other source\'s key '
                              u"in Settings -> Chinese subtitles"
                              % (text, u"; ".join(said) or u"no source could be asked"))
        self.notes.extend(said)
        if listed and any(f["source"] == ASSRT for f in listed):
            self.notes.append(CREDIT)
        for f in listed:
            self._providers.setdefault(f["name"], f["source"])
        return listed

    def download(self, file):
        u"""-> the file's bytes, exactly as served. ⛔ No key ever goes to a download link."""
        source = file.get("source") if isinstance(file, dict) else None
        name = file.get("name") if isinstance(file, dict) else None
        if source not in NAMES or not isinstance(name, str) or not name:
            raise DownloadError("%r is not a file a Chinese source listed" % (name,))
        self._refuse_if_stopped()
        if source == ASSRT:
            url, real = self._assrt_link(file)
            if real is not None and _ext(real) != _ext(name):
                raise DownloadError(
                    u"assrt.net's file is %s, not the .%s its listing said -- refused rather "
                    u"than handed on under the wrong name" % (real, _ext(name)))
            try:
                return self._fetch(url, u"the download of %s from assrt.net" % name,
                                   (".assrt.net",))
            except DownloadNotFound:
                # ⚠ the link has expired: the re-listing's retry must ask a fresh detail,
                # never the same dead link again
                self._details.pop(file.get("assrt_id"), None)
                raise
        url = self._opensubtitles_link(file)
        return self._fetch(url, u"the download of %s from OpenSubtitles" % name,
                           (".opensubtitles.com", ".opensubtitles.org"))

    def check_key(self, service):
        u"""`hato key --service X --test`: ONE metered request that only a working key answers.
        -> the sentence to show. Raises KeyRejected / JimakuError.

        assrt.net: `user/quota` (its answer is the requests a minute left). OpenSubtitles:
        one search -- ⚠ its `infos/*` answer ANY key (measured, 2026-11-11), and a search
        spends none of the five downloads a day."""
        if service == ASSRT:
            data = self._assrt("/user/quota", [], u"the assrt.net key check") or {}
            quota = (data.get("user") or {}).get("quota") if isinstance(data.get("user"), dict) else None
            return (u"Connected — the key works (%d requests a minute left)" % quota
                    if type(quota) is int else u"Connected — the key works")
        data, status, _code = self._metered(
            OPENSUBTITLES, "GET", OPENSUBTITLES_API + "/subtitles",
            [("languages", u",".join(OPENSUBTITLES_LANGUAGES)), ("query", u"frieren")], None,
            u"the OpenSubtitles key check")
        if status != 200:
            raise SourceError(u"OpenSubtitles answered HTTP %d on the key check" % status,
                              status=status)
        return u"Connected — the key works"

    # -- assrt.net --------------------------------------------------------------

    def _assrt_files(self, text):
        u"""-> ([file dict], the sentence for the notes)."""
        subs = []
        for page in range(PAGES):
            data = self._assrt("/sub/search", [("q", text), ("cnt", str(ASSRT_PAGE)),
                                               ("pos", str(page * ASSRT_PAGE)),
                                               ("filelist", "1")],
                               u'the assrt.net search for "%s"' % text)
            if data is None:
                if page == 0:
                    return [], None             # never searched: the caller says so
                break
            got = (data.get("sub") or {}).get("subs") if isinstance(data.get("sub"), dict) else None
            got = [s for s in (got or []) if isinstance(s, dict)]
            subs.extend(got)
            if len(got) < ASSRT_PAGE:
                break
        files, foreign, machine, pictures = [], 0, 0, 0
        for sub in subs:
            sub_id = sub.get("id")
            if type(sub_id) is not int or sub_id <= 0:
                continue
            if not _is_chinese_upload(sub):
                foreign += 1
                continue
            if sub.get("vote_machine_translate"):
                machine += 1
                continue
            when = _assrt_time(sub.get("upload_time"))
            members = sub.get("filelist") if isinstance(sub.get("filelist"), list) else []
            if members:
                for member in members:
                    if not isinstance(member, dict):
                        continue
                    name = _base(member.get("f"))
                    if not name or _ext(name) not in TEXT_FORMATS:
                        pictures += 1
                        continue
                    files.append({"name": name, "size": None, "last_modified": when,
                                  "source": ASSRT, "assrt_id": sub_id,
                                  "member": u"%s" % member.get("f")})
                continue
            ext = _subtype_ext(sub.get("subtype"))
            title = _base(sub.get("videoname"))
            if not title or title in _MEANINGLESS:
                title = _base((u"%s" % (sub.get("native_name") or u"")).split(u"/")[0])
            if ext is None or not title:
                pictures += 1
                continue
            name = title if _ext(title) == ext else u"%s.%s" % (title, ext)
            files.append({"name": name, "size": None, "last_modified": when,
                          "source": ASSRT, "assrt_id": sub_id, "member": None})
        left = []
        if foreign:
            left.append(u"%s not in Chinese" % _plural(foreign, u"upload"))
        if machine:
            left.append(u"%s marked machine-translated" % _plural(machine, u"upload"))
        if pictures:
            left.append(u"%s in a format tsubasa cannot time" % _plural(pictures, u"file"))
        why = (u'assrt.net listed %s for "%s"' % (_plural(len(files), u"Chinese file"), text)
               if files else u'assrt.net has no Chinese file for "%s"' % text)
        if left:
            why += u" (left out: %s)" % u", ".join(left)
        return _unique(files), why

    def _assrt_link(self, file):
        u"""-> (the download link, the file's real name or None) from one detail answer."""
        sub_id = file.get("assrt_id")
        if type(sub_id) is not int or sub_id <= 0:
            raise DownloadError("%s carries no assrt.net id" % file.get("name"))
        held = self._details.get(sub_id)
        if held is None or self._clock() - held[0] > DETAIL_TTL:
            data = self._assrt("/sub/detail", [("id", str(sub_id))],
                               u"the assrt.net detail of upload %d" % sub_id, detail=True)
            subs = (data.get("sub") or {}).get("subs") if isinstance((data or {}).get("sub"), dict) else None
            sub = subs[0] if isinstance(subs, list) and subs and isinstance(subs[0], dict) else None
            if sub is None:
                raise DownloadNotFound("assrt.net has no upload %d any more" % sub_id, status=404)
            held = (self._clock(), sub)
            self._details[sub_id] = held
        sub = held[1]
        member = file.get("member")
        if member:
            for entry in sub.get("filelist") or ():
                if isinstance(entry, dict) and entry.get("f") == member and entry.get("url"):
                    return entry["url"], None
            raise DownloadNotFound("upload %d on assrt.net no longer holds %s" % (sub_id, member),
                                   status=404)
        if not sub.get("url"):
            raise DownloadNotFound("assrt.net gave no link for upload %d" % sub_id, status=404)
        return sub["url"], _base(sub.get("filename")) or None

    def _assrt(self, path, params, what, detail=False):
        u"""One metered assrt.net call -> its JSON answer, or None for `101` (too short)."""
        data, status, code = self._metered(ASSRT, "GET", ASSRT_API + path, params, None, what)
        if code == 0 and isinstance(data, dict):
            return data
        if code == 101:
            return None
        if code == 20900 and detail:
            raise DownloadNotFound("%s: assrt.net says it is gone (20900)" % what, status=404)
        said = (data or {}).get("errmsg") if isinstance(data, dict) else None
        raise SourceError(u"assrt.net answered %s on %s%s" % (
            u"error %s" % code if code is not None else u"HTTP %d" % status, what,
            u" (%s)" % said if said else u""), status=status)

    # -- OpenSubtitles ----------------------------------------------------------

    def _opensubtitles_files(self, text, season=None):
        items = []
        for page in range(1, PAGES + 1):
            params = [("languages", u",".join(OPENSUBTITLES_LANGUAGES)), ("query", text.lower())]
            if season is not None and season > 1:
                # ⭐ the season the folder names: season 1 of the same title is not offered
                # for it (each wrong try spends one of the day's five downloads)
                params.append(("season_number", str(season)))
            if page > 1:
                # ⚠ `page=1` is answered with a 301 to the same URL without it (recorded)
                params.append(("page", str(page)))
            data, status, _code = self._metered(
                OPENSUBTITLES, "GET", OPENSUBTITLES_API + "/subtitles", sorted(params), None,
                u'the OpenSubtitles search for "%s"' % text)
            if status != 200 or not isinstance(data, dict):
                raise SourceError(u"OpenSubtitles answered HTTP %d on its search for \"%s\""
                                  % (status, text), status=status)
            got = [d for d in (data.get("data") or []) if isinstance(d, dict)]
            items.extend(got)
            total = data.get("total_pages")
            if not got or type(total) is not int or page >= total:
                break
        files, other, machine, parts = [], 0, 0, 0
        for item in items:
            a = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            lang = u"%s" % (a.get("language") or u"")
            if lang.lower() not in OPENSUBTITLES_LANGUAGES:
                other += 1
                continue
            if a.get("machine_translated") or a.get("ai_translated"):
                machine += 1
                continue
            listed = [f for f in (a.get("files") or []) if isinstance(f, dict)]
            if len(listed) != 1 or type(listed[0].get("file_id")) is not int:
                parts += 1
                continue
            name = self._opensubtitles_name(listed[0].get("file_name") or a.get("release"),
                                            lang.lower(), a.get("feature_details"))
            if not name:
                parts += 1
                continue
            files.append({"name": name, "size": None,
                          "last_modified": a.get("upload_date") if isinstance(
                              a.get("upload_date"), str) else None,
                          "source": OPENSUBTITLES, "file_id": listed[0]["file_id"]})
        left = []
        if other:
            left.append(u"%s in another language" % _plural(other, u"file"))
        if machine:
            left.append(u"%s machine- or AI-translated" % _plural(machine, u"file"))
        if parts:
            left.append(u"%s in several parts or unnamed" % _plural(parts, u"file"))
        why = (u'OpenSubtitles listed %s for "%s"' % (_plural(len(files), u"Chinese file"), text)
               if files else u'OpenSubtitles has no Chinese file for "%s"' % text)
        if left:
            why += u" (left out: %s)" % u", ".join(left)
        return _unique(files), why

    @staticmethod
    def _opensubtitles_name(raw, lang, details):
        u"""`Frieren.S01E05.WEB` + `zh-cn` -> `Frieren.S01E05.WEB.zh-cn.srt`; with no number in
        it, the service's own season and episode are added. -> text or None"""
        base = _base(raw)
        if _ext(base) in TEXT_FORMATS:
            base = os.path.splitext(base)[0]
        if not base:
            return None
        details = details if isinstance(details, dict) else {}
        season, episode = details.get("season_number"), details.get("episode_number")
        if type(episode) is int and episode > 0 and not _SXXEYY.search(base) and not re.search(
                r"(?<!\d)0*%d(?!\d)" % episode, base):
            base = u"%s S%02dE%02d" % (base, season if type(season) is int and season > 0 else 1,
                                       episode)
        return u"%s.%s.srt" % (base, lang)

    def _opensubtitles_link(self, file):
        if self._quota_out is not None:
            raise DownloadError(self._quota_out)
        file_id = file.get("file_id")
        if type(file_id) is not int or file_id <= 0:
            raise DownloadError("%s carries no OpenSubtitles file id" % file.get("name"))
        body = {"file_id": file_id, "sub_format": "srt"}
        what = u"the OpenSubtitles download of %s" % file.get("name")
        data, status, _code = self._metered(OPENSUBTITLES, "POST",
                                            OPENSUBTITLES_API + "/download", None, body, what,
                                            download=True)
        if status in (401, 403):
            # ⚠ the key SEARCHED, so a refused download is not a rejected key: OpenSubtitles
            # may want a signed-in account to download. Its downloads stop for the run;
            # its searches, and assrt.net, carry on.
            self._quota_out = (u"OpenSubtitles refused the download (HTTP %d) though the key "
                               u"searches -- it may want a signed-in account" % status)
            raise DownloadError(self._quota_out, status=status)
        data = data if isinstance(data, dict) else {}
        remaining = data.get("remaining")
        if status in (406, 407) or (status == 200 and type(remaining) is int and remaining < 0):
            self._quota_out = (
                u"OpenSubtitles' downloads for today are used up (%s)%s -- the rest wait for "
                u"the next run" % (u"%s" % (data.get("message") or u"its daily limit").strip(),
                                   u", renewed %s" % data["reset_time_utc"]
                                   if data.get("reset_time_utc") else u""))
            raise DownloadError(self._quota_out, status=status)
        if status == 404:
            raise DownloadNotFound("%s: gone (HTTP 404)" % what, status=404)
        if status != 200 or not isinstance(data.get("link"), str):
            raise DownloadError(u"%s answered HTTP %d%s" % (
                what, status, u" (%s)" % data["message"] if data.get("message") else u""),
                status=status)
        return data["link"]

    # -- the machinery ----------------------------------------------------------

    def _usable(self, service):
        return self._keys[service] is not None and self._off[service] is None

    def _refuse_if_stopped(self):
        if self._unreachable is not None:
            raise Unreachable(self._unreachable)
        if not self._usable(ASSRT) and not self._usable(OPENSUBTITLES):
            raise KeyRejected(u"; ".join(w for w in self._off.values() if w), status=401)
        if network_disabled(self._session):
            raise NetworkDisabled("HATO_NO_NETWORK=1 -- the network is switched off, so nothing "
                                  "was sent to assrt.net or OpenSubtitles.")

    def _http(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _wait(self, seconds, why):
        if seconds > 0:
            self.waits.append((seconds, why))
            self._sleep(seconds)

    def _headers(self, service):
        key = self._keys[service]
        if service == ASSRT:
            return {"User-Agent": USER_AGENT, "Accept": "application/json",
                    "Authorization": "Bearer %s" % key.reveal()}
        return {"User-Agent": USER_AGENT, "Accept": "application/json",
                "Api-Key": key.reveal()}

    def _send(self, method, url, params, body, headers, stream, timeout, what):
        u"""One request, up the unreachable ladder until an HTTP answer or the run stops."""
        while True:
            try:
                if method == "POST":
                    resp = self._http().post(url, json=body, headers=headers, timeout=timeout,
                                             allow_redirects=False)
                else:
                    resp = self._http().get(url, params=params, headers=headers, stream=stream,
                                            timeout=timeout, allow_redirects=False)
            except _NO_ANSWER as exc:
                self._failures += 1
                if self._failures >= UNREACHABLE_STOP:
                    self._unreachable = (
                        u"%s could not be reached %d times in a row (last: %s). hato stopped here "
                        u"rather than fail every file one by one -- check the connection and run "
                        u"again." % (what, self._failures, type(exc).__name__))
                    raise Unreachable(self._unreachable)
                rung = LADDER[min(self._failures, len(LADDER)) - 1]
                self._wait(rung * self._rng.uniform(*LADDER_JITTER),
                           u"%s got no answer (%s), attempt %d of at most %d"
                           % (what, type(exc).__name__, self._failures, UNREACHABLE_STOP))
                continue
            except requests.exceptions.RequestException as exc:
                # ⛔ The exception's own text is never kept: it can carry the request.
                raise SourceError(u"%s could not be sent (%s)" % (what, type(exc).__name__))
            self._failures = 0
            return resp

    def _metered(self, service, method, url, params, body, what, download=False):
        u"""-> (JSON or None, HTTP status, the service's own error code or None).
        `download`: an OpenSubtitles POST /download, whose 401/403 is its caller's to read."""
        self._refuse_if_stopped()
        if not self._usable(service):
            raise KeyRejected(self._off[service] or u"no %s key" % NAMES[service], status=401)
        if not self._keys[service].reveal().isascii():
            # ⛔ a header is Latin-1: a pasted zero-width space or full-width character would
            # raise UnicodeEncodeError carrying the WHOLE header (the key) in its `.object`
            raise SourceError(u"the %s key ending %s holds a character that is not plain ASCII "
                              u"-- paste it again, as plain text" % (NAMES[service],
                                                                     self._keys[service].hint))
        waited = 0.0
        while True:
            last = self._last[service]
            if last is not None:
                gap = self._rng.uniform(*PACE[service])
                if self._clock() - last < gap:
                    self._wait(gap - (self._clock() - last), u"pacing %s" % NAMES[service])
            resp = self._send(method, url, params, body, self._headers(service), False,
                              API_TIMEOUT, what)
            self.metered += 1
            self._last[service] = self._clock()
            status = resp.status_code
            try:
                data = json.loads(resp.content.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                data = None
            finally:
                resp.close()
            code = data.get("status") if service == ASSRT and isinstance(data, dict) else None
            code = code if type(code) is int else None
            if (service == ASSRT and code == 20001) or (
                    service == OPENSUBTITLES and status in (401, 403) and not download):
                self._off[service] = (
                    u"%s REJECTED the key ending %s (%s on %s). A rejected request still spends "
                    u"the budget, so hato asks it nothing more. Get a new one at %s"
                    % (NAMES[service], self._keys[service].hint,
                       u"invalid token" if service == ASSRT else u"HTTP %d" % status, what,
                       credentials.SERVICES[service][2]))
                raise KeyRejected(self._off[service], status=401)
            if status == 429 or code == 30900:
                after = resp.headers.get("retry-after") or resp.headers.get("ratelimit-reset")
                try:
                    wait = min(max(float(after), 0.0), WINDOW[service] * 2) if after else None
                except ValueError:
                    wait = None
                wait = (WINDOW[service] if wait is None else wait) + self._rng.uniform(*RESET_JITTER)
                if waited + wait > MAX_RATE_WAIT:
                    raise RateLimited(u"%s kept answering \"too many requests\" on %s -- with "
                                      u"%.0f s already waited hato stopped instead of hanging"
                                      % (NAMES[service], what, waited), status=429)
                waited += wait
                self._wait(wait, u"%s asked hato to slow down on %s" % (NAMES[service], what))
                continue
            if 300 <= status < 400:
                raise SourceError(u"%s answered HTTP %d on %s -- hato never follows a redirect"
                                  % (NAMES[service], status, what), status=status)
            return data, status, code

    def _fetch(self, url, what, hosts):
        u"""A download link's bytes. Unmetered, sent with NO key; the same checks as jimaku's."""
        parts = urlsplit(url or u"")
        host = (parts.hostname or u"").lower()
        if parts.scheme not in ("https", "http") or not any(
                host == h[1:] or host.endswith(h) for h in hosts):
            raise DownloadError(u"%s points at %s, not the service's own files -- not fetched"
                                % (what, host or u"nowhere"))
        resp = self._send("GET", url, None, None, {"User-Agent": USER_AGENT}, True,
                          DOWNLOAD_TIMEOUT, what)
        self.unmetered += 1
        body = bytearray()
        try:
            if resp.status_code == 404:
                raise DownloadNotFound(u"%s is gone (HTTP 404)" % what, status=404)
            if resp.status_code != 200:
                raise DownloadError(u"%s answered HTTP %d" % (what, resp.status_code),
                                    status=resp.status_code)
            try:
                for chunk in resp.iter_content(_CHUNK):
                    body += chunk
                    if len(body) > self.max_download_bytes:
                        raise DownloadError(u"%s passed the %d-byte cap -- aborted, nothing kept"
                                            % (what, self.max_download_bytes), status=200)
            except requests.exceptions.RequestException as exc:
                raise DownloadError(u"%s dropped after %d bytes (%s)"
                                    % (what, len(body), type(exc).__name__), status=200)
        finally:
            resp.close()
        if not body:
            raise DownloadError(u"%s came back EMPTY -- a zero-byte subtitle is never kept" % what,
                                status=200)
        if _looks_like_html(body):
            raise DownloadError(u"%s came back as an HTML page, not a subtitle" % what, status=200)
        if bytes(body[:8]).startswith(_ARCHIVE_MAGIC):
            raise DownloadError(u"%s came back as an archive, not the subtitle its listing named"
                                % what, status=200)
        return bytes(body)


def build(session=None):
    u"""-> a ChineseClient with whichever of the learner's two keys resolve, or raise
    `credentials.KeyMissing` naming both when neither does."""
    keys, why = {}, []
    for service in (ASSRT, OPENSUBTITLES):
        try:
            keys[service] = credentials.resolve_key(service=service)
        except credentials.KeyMissing as exc:
            keys[service] = None
            why.append(u"%s" % exc)
    if keys[ASSRT] is None and keys[OPENSUBTITLES] is None:
        raise credentials.KeyMissing(
            u"Chinese subtitles come from assrt.net (first) or OpenSubtitles, each with your own "
            u"free key, and neither is set. %s" % u" ".join(why))
    return ChineseClient(assrt=keys[ASSRT], opensubtitles=keys[OPENSUBTITLES], session=session)
