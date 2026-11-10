# -*- coding: utf-8 -*-
u"""
anime-relations -- an OUTSIDE statement of where a sequel's numbering starts.

    rules = load()                         # the bundled snapshot -> [Rule]
    bridge = bridge_for(rules, 182255)     # Frieren S2 on AniList -> Bridge, or None
    bridge.offset(part_episodes, video_season, video_episodes)   # -> int or None

⭐ THE FILE. `erengy/anime-relations` (Taiga's; public domain; used by jimaku to
redirect an episode). One rule per line:

    - 52991|46474|154587:29-38 -> 59978|49240|182255:1-10!
      MAL | Kitsu | AniList : episodes  ->  the same for the destination

`!` adds the rule "the DESTINATION's own 29-38 are its 1-10" -- a sequel entry
whose fansubs number on from the first season. That self-rule is the only kind
read here: on THIS entry, a number in 29-38 is the entry's episode n - 28. It
is a statement about NUMBERS, never about labels, so Netflix's `S02E34` (a
season tag on an absolute number) reads as 34 like any other.

⛔ FAIL SAFE, ALWAYS. Unknown id, malformed line, a range of one episode, two
rules for one entry that disagree, a range whose two counts overlap: no bridge.
Never a raise -- this is a second opinion, and a missing one costs nothing but
the fit hato already had.

⛔ This is not a filename parser: it reads episode NUMBERS tsubasa already read.
"""
import collections
import datetime
import hashlib
import json
import os
import re
import time

#: The snapshot shipped inside the package. ⚠ The frozen build must carry it.
SNAPSHOT = u"anime-relations.txt"

Rule = collections.namedtuple("Rule", "src dst src_lo src_hi dst_lo dst_hi")
#: ids: (mal, kitsu, anilist), each an int or None ("?"). hi None = open ("?").

_IDS = r"([0-9]+|\?|~)\|([0-9]+|\?|~)\|([0-9]+|\?|~)"
_RANGE = r"([0-9]+)(?:-([0-9]+|\?))?"
_LINE = re.compile(r"^-\s*%s:%s\s*->\s*%s:%s(!?)\s*$" % (_IDS, _RANGE, _IDS, _RANGE))


def _id(text, same=None):
    if text == u"~":
        return same
    if text == u"?":
        return None
    return int(text)


def _hi(lo, text):
    if text is None:
        return lo
    if text == u"?":
        return None
    return int(text)


def parse(text):
    u"""-> [Rule], `!` expanded into its self-rule. Malformed lines are skipped."""
    rules, in_rules = [], False
    for raw in (text or u"").splitlines():
        line = raw.strip()
        if line.startswith(u"::"):
            in_rules = line == u"::rules"
            continue
        if not in_rules or not line.startswith(u"-"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        try:
            g = m.groups()
            src = tuple(_id(x) for x in g[0:3])
            dst = tuple(_id(x, s) for x, s in zip(g[5:8], src))
            src_lo, src_hi = int(g[3]), _hi(int(g[3]), g[4])
            dst_lo, dst_hi = int(g[8]), _hi(int(g[8]), g[9])
        except (TypeError, ValueError):
            continue
        rules.append(Rule(src, dst, src_lo, src_hi, dst_lo, dst_hi))
        if g[10] == u"!":
            rules.append(Rule(dst, dst, src_lo, src_hi, dst_lo, dst_hi))
    return rules


def load(path=None):
    u"""The list hato reads (or `path`) -> [Rule]; [] when it cannot be read.
    ⭐ 16j: with no `path`, the NEWER of the bundled snapshot and the weekly copy in
    hato's cache (`current_text`)."""
    try:
        if path is None:
            return parse(current_text()[0])
        with open(str(path), encoding="utf-8") as fh:
            return parse(fh.read())
    except Exception:   # noqa: BLE001 -- ⛔ a second opinion never stops a run
        return []


class Bridge(object):
    u"""On one entry: numbers in [abs_lo, abs_hi] are the entry's own n - shift.

    `own` is the entry's own count, [own_lo, own_hi]. ⛔ The two never overlap
    (bridge_for refuses one that does), so a number says which count it is in.
    ⚠ 16z (Z-B2): `own_open` -- the rule never said where the own count ENDS (`1-?`);
    `own_hi` is then the list's start less one, which no one stated."""

    __slots__ = ("shift", "abs_lo", "abs_hi", "own_lo", "own_hi", "source", "own_open")

    def __init__(self, shift, abs_lo, abs_hi, own_lo, own_hi, source, own_open=False):
        self.shift, self.source, self.own_open = shift, source, own_open
        self.abs_lo, self.abs_hi, self.own_lo, self.own_hi = abs_lo, abs_hi, own_lo, own_hi

    def _in_abs(self, n):
        return self.abs_lo <= n and (self.abs_hi is None or n <= self.abs_hi)

    def _count(self, numbers):
        u"""-> "abs" | "own" | None: the count EVERY number sits in."""
        numbers = list(numbers)
        if not numbers:
            return None
        if all(self._in_abs(n) for n in numbers):
            return "abs"
        if all(self.own_lo <= n <= self.own_hi for n in numbers):
            return "own"
        return None

    def _files_count(self, numbers):
        u"""-> the count a PART's numbers sit in: `_count`'s, and -- ⭐ 16z (A4) -- "abs" for a
        release that numbers across the seasons: numbers in the absolute count AND numbers
        in NEITHER count (between the two -- the earlier season's) say the release counts on
        from season 1, so its low numbers are season 1's, never this entry's own (a release
        carries each episode once). Only the files that land are placed (pass 0's floor)."""
        counted = self._count(numbers)
        if counted is not None:
            return counted
        numbers = list(numbers)
        between = [n for n in numbers if self.own_hi < n < self.abs_lo]
        if between and any(self._in_abs(n) for n in numbers):
            return "abs"
        return None

    def offset(self, part_episodes, video_season, video_episodes, part_season=None):
        u"""The offset (file episode - video episode) the list states between a part and a
        partition of videos, or None.

        ⛔ VIDEOS ARE READ MORE STRICTLY THAN FILES. A file is ON this entry, so its
        number is the entry's by the list's own meaning. A video is only GUESSED to be
        this show: a seasonless `Show - 05` may be the first season's 5, so a seasonless
        video is placed in the absolute count only (never the entry's own), and a video
        that says season 1 is never bridged into a sequel.
        ⛔ 16z (A6): nor is a FILE that says season 1 (`part_season`): `S1 - 03` on the
        sequel's entry is a mislabel or the first season's, never the sequel's own 3."""
        part = self._files_count(part_episodes)
        videos = self._count(video_episodes)
        if part is None or videos is None:
            return None
        if video_season == 1 or part_season == 1:
            return None
        # ⛔ 16z (Z-B2): an OPEN rule (`13-? -> 1-?`) never said where the own count ends: a
        # video at or past its start may be the own count's 13 (`S2 - 13`, just aired) as
        # well as the absolute 13 -- the list states nothing for it, never an invented end.
        if videos == "abs" and self.own_open:
            return None
        if video_season is None and videos == "own":
            return None
        if part == videos:
            return 0
        return self.shift if part == "abs" else -self.shift


def bridge_for(rules, anilist_id):
    u"""-> Bridge for the entry with this AniList id, or None. ⛔ Fail safe throughout."""
    if not isinstance(anilist_id, int) or isinstance(anilist_id, bool) or anilist_id <= 0:
        return None
    found = []
    for r in rules or ():
        if r.src[2] != anilist_id or r.dst[2] != anilist_id:
            continue
        if r.dst_hi is not None and r.dst_hi <= r.dst_lo:
            continue                                # one episode is a redirect, not a count
        shift = r.src_lo - r.dst_lo
        if shift <= 0:
            continue
        own_hi = r.dst_hi if r.dst_hi is not None else r.src_lo - 1
        if r.src_hi is not None and r.dst_hi is not None and \
                r.src_hi - r.src_lo != r.dst_hi - r.dst_lo:
            continue                                # two lengths: not one shift
        if own_hi >= r.src_lo:
            continue                                # the counts overlap: a number cannot say
        found.append(Bridge(shift, r.src_lo, r.src_hi, r.dst_lo, own_hi, u"anime-relations",
                            own_open=r.dst_hi is None))
    if len(found) != 1:
        return None                                 # none, or several: nothing stated
    return found[0]


_LOADED = []


def for_entry(anilist_id):
    u"""The list's Bridge for this AniList id, or None. Read once per process (a
    refresh in this process reads it again)."""
    if not _LOADED:
        _LOADED.append(load())
    return bridge_for(_LOADED[0], anilist_id)


# ===========================================================================
# 16j -- THE WEEKLY REFRESH (Sonic ruled option 2, 2026-10-11): a copy ships inside
# each release, and hato fetches a newer one at most once a week, with the update
# check. ⛔ A failed, partial or malformed download keeps what hato had, and says
# nothing louder than a log line. ⛔ Never during a run, never blocks one: it runs
# in `hato update --auto` ONLY -- the tray's hourly child and the daily run's; 16z
# (Z-C6): never the window's `--check`, which *Check now* waits on -- and not while a
# run holds the lock (`commands/update.py`).
# ===========================================================================

#: ⭐ The list's own home (the snapshot's header names the repository; its default
#: branch is `master`). One GET, from raw.githubusercontent.com, at most weekly.
REFRESH_URL = u"https://raw.githubusercontent.com/erengy/anime-relations/master/anime-relations.txt"
#: ⭐ "at most once every 7 days": a check made 6 days ago is not due.
REFRESH_EVERY_SECONDS = 7 * 24 * 3600
#: A request that got NO answer (offline, a timeout) tries again the next day rather
#: than the next week -- nothing was served, so nothing was turned away.
RETRY_UNANSWERED_SECONDS = 24 * 3600
MAX_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 20
#: ⚠ 16n (R3): `TIMEOUT_SECONDS` is per socket READ -- a server sending a byte every few
#: seconds never trips it. The whole fetch ends here, whatever it trickles.
DEADLINE_SECONDS = TIMEOUT_SECONDS * 3
#: ⚠ 16z (Z-C3): the most one read asks for -- it returns whatever ONE socket read brings.
PIECE_BYTES = 16 * 1024
_monotonic = time.monotonic
#: A fetched list with fewer than this share of the bundled copy's rules is a broken
#: or truncated file, not a newer list (the file only grows).
MIN_SHARE = 0.9
#: In hato's cache folder (`paths.cache_dir()`, which HATO_CACHE relocates).
CACHED_NAME = u"anime-relations.txt"
STAMP_NAME = u"anime-relations.json"

_META = re.compile(r"^-\s*([a-z_]+)\s*:\s*(.*?)\s*$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class RefreshError(Exception):
    u"""A fetch that brought no list. `answered`: the server said something (a 404, a
    500) -- a weekly wait; False: no answer at all (offline, a timeout) -- a daily one."""

    def __init__(self, message, answered):
        Exception.__init__(self, message)
        self.answered = bool(answered)


def meta(text):
    u"""-> the `::meta` section's `- key: value` lines as a dict (empty if none)."""
    out, inside = {}, False
    for raw in (text or u"").splitlines():
        line = raw.strip()
        if line.startswith(u"::"):
            inside = line == u"::meta"
            continue
        if inside:
            m = _META.match(line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def _today():
    u"""Today, UTC -- a seam the suite pins."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def _not_a_day(value):
    u"""-> why `value` is no `last_modified` date, in words, or None when it is one.
    🚨 16z (Z-C2): ANY `NNNN-NN-NN` was a date -- `2026-99-99`, or a mistyped year,
    sorted after every later list and every release's own copy and pinned that copy for
    good. A real calendar day, no later than tomorrow (UTC: a day of slack for a list
    dated where its author lives)."""
    if not value or not _DAY.match(value):
        return u"no last_modified date"
    try:
        day = datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return u"last_modified %s is no calendar date" % value
    if day > _today() + datetime.timedelta(days=1):
        return u"last_modified %s is after today" % value
    return None


def _day(text):
    u"""-> its `last_modified` (YYYY-MM-DD) or None. ⚠ Compared as text: the format sorts.
    ⚠ 16z: a date `_not_a_day` refuses is None -- on fetch AND on read, so a cached copy
    dated in the future is never "newer"."""
    value = meta(text).get(u"last_modified")
    return value if _not_a_day(value) is None else None


def bundled_path():
    from pathlib import Path
    return Path(__file__).resolve().parent / u"data" / SNAPSHOT


def cached_path():
    from hato import paths
    return paths.cache_dir() / CACHED_NAME


def stamp_path():
    from hato import paths
    return paths.cache_dir() / STAMP_NAME


def _read(path):
    try:
        with open(str(path), encoding="utf-8") as fh:
            return fh.read()
    except Exception:   # noqa: BLE001 -- absent, unreadable, not UTF-8: no copy
        return None


def judge(text, bundled_text, name=u"the bundled copy"):
    u"""-> None when `text` may stand in for the bundled copy, else why not, in words.

    Taken only when it parses (`::meta` version `1.x`, a `::rules` section, at least
    90 % of the bundled copy's rules) and its `last_modified` is not older than the
    bundled copy's (RUNBOOK §16.2). ⭐ 16n: `bundled_text` may be another copy (`name`
    says which), or None -- unreadable: no share or date test against it (R9)."""
    version = meta(text).get(u"version") or u""
    if not re.match(r"^1\.[0-9]", version):
        return u"no ::meta version 1.x (%s)" % (version or u"none")
    if not any(line.strip() == u"::rules" for line in (text or u"").splitlines()):
        return u"no ::rules section"
    have, need = len(parse(text)), len(parse(bundled_text))
    if have < MIN_SHARE * need:
        return u"%d rules where %s has %d" % (have, name, need)
    day, bundled_day = _day(text), _day(bundled_text)
    if day is None:
        return _not_a_day(meta(text).get(u"last_modified"))
    if bundled_day is not None and day < bundled_day:
        return u"older than %s (%s < %s)" % (name, day, bundled_day)
    return None


def current_text():
    u"""-> (the text hato reads, "bundled" | "cached"). ⭐ The NEWER of the two: the
    cached copy only when it is still a good list (judged again on every read -- a
    file can change on disk) and strictly newer than the one this release carries.
    ⭐ 16n: the cheap date first, the whole judge only for a newer copy (R10); an
    unreadable bundled copy leaves a good cached one read (R9)."""
    bundled = _read(bundled_path())
    cached = _read(cached_path())
    if cached is not None and (_day(cached) or u"") > (_day(bundled) or u"") \
            and judge(cached, bundled) is None:
        return cached, u"cached"
    return bundled, u"bundled"


def load_stamp(path=None):
    try:
        with open(str(path or stamp_path()), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:   # noqa: BLE001 -- a broken stamp means: ask again
        return {}


def refresh_due(now, stamp=None):
    u"""True when a fetch is owed: never tried, or the last try is a week old (a day,
    when nothing answered). ⚠ A time in the FUTURE (a clock set back) is owed too."""
    stamp = load_stamp() if stamp is None else stamp
    at = stamp.get(u"tried_at")
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return True
    wait = REFRESH_EVERY_SECONDS if stamp.get(u"answered", True) else RETRY_UNANSWERED_SECONDS
    return not (0 <= now - at < wait)


def _write_atomic(path, data):
    u"""Temp in the same folder -> flush -> fsync -> rename (LEDGER-HOT: never a
    truncate in place). ⛔ The temp never ends `.txt`: nothing reads it as a list."""
    folder = os.path.dirname(str(path))
    os.makedirs(folder, exist_ok=True)
    temp = os.path.join(folder, u".%s.%d.tmp" % (os.path.basename(str(path)), os.getpid()))
    try:
        with open(temp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, str(path))
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def fetch(url=REFRESH_URL):
    u"""GET the list -> its bytes, never more than MAX_BYTES. Raises RefreshError.
    ⛔ HATO_NO_NETWORK=1 refuses before a socket exists, as every hato request does."""
    if os.environ.get("HATO_NO_NETWORK") == "1":
        raise RefreshError(u"the network is switched off (HATO_NO_NETWORK)", answered=False)
    try:
        import requests
    except ImportError:
        raise RefreshError(u"requests is not installed", answered=False)
    import http.client
    from hato.update import user_agent
    started = _monotonic()
    try:
        # ⚠ 16z: `identity` -- the bytes read are the list itself, so Content-Length
        # counts them (and nothing decodes them below urllib3's own reader)
        with requests.get(url, headers={u"User-Agent": user_agent(),
                                        u"Accept-Encoding": u"identity"},
                          timeout=TIMEOUT_SECONDS, stream=True) as response:
            if response.status_code != 200:
                raise RefreshError(u"answered %d" % response.status_code, answered=True)
            coded = (response.headers.get(u"Content-Encoding") or u"identity").strip().lower()
            if coded != u"identity":
                raise RefreshError(u"answered %s, not plain text" % coded, answered=True)
            read = _read_some(response)
            body = bytearray()
            while True:
                block = read(PIECE_BYTES)
                if not block:
                    break
                body.extend(block)
                if len(body) > MAX_BYTES:
                    raise RefreshError(u"more than %d bytes" % MAX_BYTES, answered=True)
                if _monotonic() - started > DEADLINE_SECONDS:
                    # ⚠ 16n (R3): it answered, too slowly -- a weekly wait, as a 404's
                    raise RefreshError(u"no whole list within %d seconds" % DEADLINE_SECONDS,
                                       answered=True)
            # 🚨 16z (Z-C1): urllib3 1.26 hands back a SHORT body, no error, when the
            # connection drops before Content-Length -- a dropped download: a day's wait
            promised = response.headers.get(u"Content-Length")
            if promised is not None and promised.strip() != u"%d" % len(body):
                raise RefreshError(u"cut short: %d of %s bytes" % (len(body), promised.strip()),
                                   answered=False)
            return bytes(body)
    except (requests.RequestException, http.client.HTTPException, OSError,
            _urllib3_error()) as exc:
        # ⚠ 16z: below urllib3 a timeout or a reset is the socket's own error
        # 🚨 1.1.0's CI: urllib3 2.x (the frozen build's) RAISES on a body cut short of
        # its Content-Length -- its own ProtocolError, none of the three above, read
        # through `read1` -- where 1.26 handed back the short body (Z-C1 below)
        cut = _cut_short(exc)
        raise RefreshError(cut or type(exc).__name__, answered=False)


def _urllib3_error():
    u"""-> urllib3's base error (what `raw.read1` raises in urllib3 2.x), or OSError
    when it cannot be reached (then nothing raises it). ⚠ Through `requests.packages`,
    requests' own re-export of the urllib3 it runs on: hato declares requests, never
    urllib3 (`test_every_third_party_import_under_hato_is_DECLARED`)."""
    try:
        import requests
        return requests.packages.urllib3.exceptions.HTTPError
    except (ImportError, AttributeError):
        return OSError


def _cut_short(exc):
    u"""-> "cut short: N of M bytes" when `exc` carries urllib3's IncompleteRead
    (`partial` bytes read, `expected` still owed), else None."""
    for arg in getattr(exc, "args", ()):
        partial, owed = getattr(arg, "partial", None), getattr(arg, "expected", None)
        if isinstance(partial, int) and isinstance(owed, int):
            return u"cut short: %d of %d bytes" % (partial, partial + owed)
    return None


def _read_some(response):
    u"""-> read(n): at most ONE socket read -- whatever has come, at least a byte, b""
    at the end. 🚨 16z (Z-C3): `iter_content(n)` and urllib3's `read(n)` wait for n
    bytes, so a byte every few seconds never let `fetch` look at its deadline (the list
    is ~49 KB: under ONE 64 KiB block). `read1` returns at the first byte. ⛔ A urllib3
    with neither road is refused, never read the old way."""
    raw = response.raw
    read = getattr(raw, "read1", None)                       # urllib3 2.x
    if read is None:
        read = getattr(getattr(raw, "_fp", None), "read1", None)   # 1.26: http.client's own
    if read is None:
        raise RefreshError(u"this urllib3 cannot read a piece at a time", answered=False)
    return read


def refresh(now, get=None, log=None):
    u"""The weekly refresh. -> what happened, one word: `not-due` · `offline` (no call
    made) · `kept` (fetched, or tried, and turned away: the copy hato had stands) ·
    `taken`. ⛔ Never raises."""
    try:
        return _refresh(now, get or fetch, log or _log)
    except Exception as exc:   # noqa: BLE001 -- ⛔ a second opinion never stops anything
        try:
            (log or _log)(u"the anime-relations refresh failed (%s: %s)" % (type(exc).__name__, exc))
        except Exception:      # noqa: BLE001
            pass
        return u"kept"


def _refresh(now, get, log):
    if os.environ.get("HATO_NO_NETWORK") == "1":
        return u"offline"
    if not refresh_due(now):
        return u"not-due"
    # 🚨 16n (R2): ONCE A FETCH WAS TRIED, A STAMP IS WRITTEN -- whatever fails after it
    # (the cache write, `judge`). With none, every hourly child of the tray fetched
    # again. `answered` turns true the moment bytes came: a weekly wait, not a daily one.
    stamp = {u"tried_at": now, u"answered": False}
    try:
        return _fetch_and_take(get, log, stamp)
    except Exception as exc:   # noqa: BLE001 -- ⛔ a second opinion never stops anything
        stamp[u"outcome"] = u"kept: %s: %s" % (type(exc).__name__, exc)
        log(u"the anime-relations refresh failed (%s: %s); the copy hato has stands"
            % (type(exc).__name__, exc))
        return u"kept"
    finally:
        try:
            _write_atomic(stamp_path(), _stamp_bytes(stamp))
        except Exception as exc:   # noqa: BLE001 -- ⚠ best effort: it costs a fetch next hour
            try:
                log(u"the anime-relations stamp was not written (%s)" % type(exc).__name__)
            except Exception:      # noqa: BLE001
                pass


def _fetch_and_take(get, log, stamp):
    u"""One fetch, judged; `stamp` filled in. -> `kept` | `taken`. May raise: `_refresh`
    stamps whatever escapes."""
    try:
        data = get(REFRESH_URL)
    except RefreshError as exc:
        stamp.update(answered=exc.answered, outcome=u"kept: %s" % exc)
        log(u"the anime-relations list was not fetched (%s); the copy hato has stands" % exc)
        return u"kept"
    stamp[u"answered"] = True
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    why = u"not UTF-8 text" if text is None else _turned_away(text)
    if why is not None:
        stamp.update(outcome=u"kept: %s" % why)
        log(u"the fetched anime-relations list was turned away (%s); the copy hato has stands" % why)
        return u"kept"
    _write_atomic(cached_path(), data)
    del _LOADED[:]                     # this process reads the newer copy from now on
    stamp.update(outcome=u"taken", last_modified=_day(text), rules=len(parse(text)),
                 sha256=hashlib.sha256(data).hexdigest())
    return u"taken"


def _turned_away(text):
    u"""-> why a fetched list may not replace what hato has, or None. 🚨 16n (R1): judged
    against the bundled copy AND the copy hato READS NOW -- against the bundled one
    alone, a list older than the cached copy replaced it, and hato read the older.
    🚨 16z (Z-C1): the list ends on a whole line -- a download cut mid-line, with no
    length to hold it to, kept 93 % of the rules and lost the last titles' for a week."""
    if not text.endswith(u"\n"):
        return u"it does not end on a whole line -- cut short"
    why = judge(text, _read(bundled_path()))
    if why is None:
        current, which = current_text()
        if which == u"cached":
            why = judge(text, current, u"the copy hato reads now")
    return why


def _stamp_bytes(stamp):
    return json.dumps(stamp, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")


def _log(message):
    from hato import watch
    watch.complain(u"hato: %s\n" % message, who=u"relations")
