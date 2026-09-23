# -*- coding: utf-8 -*-
"""
Identification (spec/RUNBOOK.md 2b): a video's title -> its jimaku entry, and the
resolution cache that makes every later run over that show free.

    ident = identify(title, season=2, client=client, cache=ResolutionCache(), kitsu=kitsu)
    ident.resolved       Resolved(entry_id, entry_name, movie, score, low_confidence,
                                  source, anilist_id) -- or None, and then
    ident.reason         says why (never empty when nothing resolved)
    ident.calls          jimaku metered calls this identification cost
    ident.kitsu_calls · ident.cached · ident.candidates (every scored entry, for --explain)

    cache_key(title, season=None, year=None)    the ONLY way to make a cache key

The chain (spec/02-data-model.md §Identification):

    cache hit .......................................... 0 calls
    jimaku search?query=<title> ........................ 1 call
      no match -> the same with anime=false ............ 2 calls   (live action, tokusatsu)
        no match -> Kitsu search -> Kitsu /mappings -> jimaku search?anilist_id=
                                                         3 calls + 2 Kitsu calls
    a resolution is cached for ever; a miss is not -- the state DB's negative cache
    owns "do not ask again yet"

Rules, each a check in tests/test_identify.py:

- ⛔ AN EMPTY TITLE NEVER BECOMES A REQUEST: EmptyQuery, before the cache or the network.
- ⚠ THE KEY CARRIES THE SEASON AND THE YEAR. Two shows -- or two seasons of one show --
  folding to one key would serve the wrong entry from cache for ever. A key is a JSON
  array only `cache_key` makes, and the store refuses any other string, so a bare
  title can never become one. Case and spacing fold; punctuation does NOT (`Gintama`,
  `Gintama'` and `Gintama.` are different seasons).
- ⚠ THE TITLE IS TSUBASA'S. The trailing 19xx/20xx year anitopy glues on
  (`Kimi no Na wa 2016`, measured) is stripped from the QUERY and kept for the KEY --
  unless nothing would be left (`1917` is a title). Nothing else is re-parsed.
- ⭐ JIMAKU'S SEARCH CARRIES NO SCORE, so every result is scored HERE against the
  entry's `name`, `english_name` and `japanese_name`, each read raw AND through
  tsubasa's parser (hato.names), which is also what reads the entry's season. The same
  parser read the video's name, so its quirks land on both sides alike.
- ⭐ THE SEASON DECIDES between titles that match equally. `query=frieren` returns
  Sousou no Frieren (729) first and its 2nd Season (11446) second -- measured -- and a
  season-2 video must get 11446, a season-1 video 729.
- 🚨 A VIDEO THAT READS NO SEASON MAKES NO SEASON CLAIM, and inventing one is how a
  season-2 video got the season-1 entry silently, for ever (fixed 2026-09-17; see
  `_rank`). `None` is folded to 1 on the ENTRY side only -- jimaku names a first
  season without a number -- never on the video's.
- ⚠ KITSU IS HIGH-RECALL, LOW-PRECISION: its hits are scored the same way, and the
  jimaku entry taken is the one whose `anilist_id` EQUALS the mapping -- never the first.

The scoring, where the spec left room (numbers chosen against the recorded searches):

    similarity  1.0 for the same tokens; else the better of the character ratio and --
                when EVERY query token is in the title -- 0.75 + 0.2 x query/title tokens
    score       similarity, halved when the entry's season is not the video's (None = 1)
    a match     similarity >= MATCH_FLOOR. Below it, an entry is fuzzy-search noise
    LOW CONFIDENCE  the top two matches within CLOSE · or the chosen entry's season is
                not the video's · or its similarity is under CONFIDENT (a fuzzy match)
    no match    on the first search -> the anime=false retry; on both -> Kitsu
"""
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, namedtuple
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from hato import paths
from hato.cache import Cache
from hato.client import EmptyQuery
from hato.kitsu import KitsuError
from hato.names import read_names

FILENAME = "resolution.db"
SCHEMA_VERSION = 1
#: The first element of every key. ⚠ Bump it if the key's normalisation ever
#: changes, so a stored key can never match one made another way.
KEY_VERSION = "hato-resolution-v1"

SOURCE_JIMAKU = "jimaku"
SOURCE_ANIME_FALSE = "jimaku anime=false"
SOURCE_KITSU = "kitsu"
SOURCES = (SOURCE_JIMAKU, SOURCE_ANIME_FALSE, SOURCE_KITSU)

MATCH_FLOOR = 0.6
CONFIDENT = 0.75
CLOSE = 0.05
SEASON_MISMATCH = 0.5

_YEAR_TAIL = re.compile(r"^(?P<title>.*\S)\s+\(?(?P<year>(?:19|20)[0-9]{2})\)?$")
_WORD = re.compile(r"\w+")
#: ⚠ ASCII digits only: str.isdigit() also says yes to `４６` and `²`.
_KITSU_ID = re.compile(r"[0-9]+\Z")


# ---------------------------------------------------------------------------
# values
# ---------------------------------------------------------------------------

_ResolvedFields = namedtuple(
    "Resolved", "entry_id entry_name movie score low_confidence source anilist_id")


class Resolved(_ResolvedFields):
    """A show's jimaku entry. Validated on construction -- the store's CHECKs say the same."""
    __slots__ = ()

    def __new__(cls, entry_id, entry_name, movie, score, low_confidence, source, anilist_id=None):
        if type(entry_id) is not int or entry_id <= 0:
            raise ValueError("entry_id must be jimaku's positive integer id, got %r" % (entry_id,))
        if not isinstance(entry_name, str) or not entry_name.strip():
            raise ValueError("entry_name must be a non-empty string, got %r" % (entry_name,))
        if type(movie) is not bool:
            raise ValueError("movie must be True or False, got %r" % (movie,))
        if type(score) not in (int, float) or not 0.0 <= score <= 1.0:
            raise ValueError("score must be a number from 0 to 1, got %r" % (score,))
        if type(low_confidence) is not bool:
            raise ValueError("low_confidence must be True or False, got %r" % (low_confidence,))
        if source not in SOURCES:
            raise ValueError("source must be one of %s, got %r" % (", ".join(SOURCES), source))
        if anilist_id is not None and (type(anilist_id) is not int or anilist_id <= 0):
            raise ValueError("anilist_id must be None or a positive int, got %r" % (anilist_id,))
        return _ResolvedFields.__new__(cls, entry_id, entry_name, movie, float(score),
                                       low_confidence, source, anilist_id)


Identification = namedtuple("Identification",
                            "resolved calls kitsu_calls cached candidates reason")

#: One scored search result. `id` is jimaku's int, or Kitsu's id string.
Candidate = namedtuple("Candidate",
                       "source id name score similarity season season_ok accepted")


# ---------------------------------------------------------------------------
# titles and keys
# ---------------------------------------------------------------------------

def _season(value):
    if value is None or (type(value) is int and value >= 0):
        return value
    raise ValueError("season must be None or a non-negative int, got %r" % (value,))


def _year(value):
    if value is None or (type(value) is int and 1900 <= value <= 2099):
        return value
    raise ValueError("year must be None or an int from 1900 to 2099, got %r" % (value,))


def _parts(title, season, year):
    """-> (query, season, year, full title). ⛔ EmptyQuery for an empty title."""
    if not isinstance(title, str):
        raise TypeError("title must be a str, got %s" % type(title).__name__)
    full = " ".join(title.split())
    # "Empty" is NO LETTER OR DIGIT at all: whitespace, punctuation or a lone format
    # character would reach jimaku as a query with nothing in it to match.
    if not _WORD.search(unicodedata.normalize("NFKC", full)):
        raise EmptyQuery("refused: the title %r has no letter or digit, and an empty query "
                         "returns jimaku's entire catalogue. Nothing was sent." % (title,))
    query, glued = full, None
    m = _YEAR_TAIL.match(full)
    if m and _WORD.search(unicodedata.normalize("NFKC", m.group("title"))):
        query, glued = m.group("title"), int(m.group("year"))
    season, year = _season(season), _year(year)
    return query, season, (year if year is not None else glued), full


def _key_title(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def cache_key(title, season=None, year=None):
    """-> the resolution cache key for a show. ⚠ The season and the year are part of
    it: a collision would serve the wrong entry from cache for ever."""
    query, season, year, _ = _parts(title, season, year)
    folded = _key_title(query)
    return json.dumps([KEY_VERSION, folded, season, year], ensure_ascii=False,
                      separators=(",", ":"))


def _checked_key(key):
    try:
        parts = json.loads(key) if isinstance(key, str) else None
    except ValueError:
        parts = None
    if not (isinstance(parts, list) and len(parts) == 4 and parts[0] == KEY_VERSION
            and isinstance(parts[1], str) and parts[1]
            and (parts[2] is None or type(parts[2]) is int)
            and (parts[3] is None or type(parts[3]) is int)):
        raise ValueError("%r is not a key made by cache_key() -- a bare title would drop the "
                         "season and the year, and a collision serves the wrong entry for ever"
                         % (key,))
    return key


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _tokens(text):
    return _WORD.findall(unicodedata.normalize("NFKC", text).casefold())


def _similarity(query_tokens, title_tokens):
    if not query_tokens or not title_tokens:
        return 0.0
    if query_tokens == title_tokens:
        return 1.0
    score = SequenceMatcher(None, " ".join(query_tokens), " ".join(title_tokens),
                            autojunk=False).ratio()
    if not Counter(query_tokens) - Counter(title_tokens):
        score = max(score, 0.75 + 0.2 * len(query_tokens) / len(title_tokens))
    return min(score, 1.0)


def _readings(names):
    """name -> (title, season) as tsubasa's parser reads `<name>.mkv`."""
    unique = list(dict.fromkeys(names))
    if not unique:
        return {}
    with Cache().workdir("identify") as work:
        infos = read_names([n + ".mkv" for n in unique], work)
    return dict((info.name[:-len(".mkv")],
                 ("", None) if info.skipped else (info.title or "", info.season))
                for info in infos)


def _season_number(season):
    """⚠ THE ENTRY SIDE ONLY. jimaku names a first season without a number
    (`Sousou no Frieren`, and `… 2nd Season` beside it), so an entry that reads
    no season IS season 1. ⛔ Never applied to the video: see `_entry_season_ok`."""
    return 1 if season is None else season


def _entry_season_ok(entry_season, season):
    """Is this entry compatible with the season the VIDEO read?

    🚨 A VIDEO THAT READS NO SEASON IS NOT A CLAIM OF SEASON 1, and treating it
    as one was a silent, permanent wrong answer. Measured 2026-09-17 on the real
    capture: `[Haruhana] Sousou no Frieren - 29 [WebRip][HEVC-10bit 1080p][JPN].mkv`
    -- the dominant anime convention, and the exact shape `08-research.md` records
    for this entry -- is read by tsubasa as `season=None, episode=29`. Entry 11446
    (2nd Season) was halved for SEASON_MISMATCH and entry 729 (season 1, which has
    no episode 29) won at score 1.00 with `low_confidence=False`. Every video then
    came back NOT FOUND and the wrong entry stayed cached for ever.

    ⭐ A seasonless name is the ABSOLUTE numbering, which spans every season --
    so every entry of the show is compatible with it, they tie, and `_choose`
    says LOW CONFIDENCE rather than picking one silently (06-edge-cases.md §1:
    *"if the top two scores are close ... Do not silently pick"*). The episode
    number is what settles it, and only the pipeline can read it: an entry that
    holds nothing for any video is evidence against itself, and `pipeline._show`
    drops a LOW CONFIDENCE resolution that found nothing.
    """
    return season is None or _season_number(entry_season) == season


def _rank(items, query, full, season, source):
    """items: [(id, display name, [names])] in the source's order -> [Candidate],
    matches first, best first. Position only breaks an exact tie."""
    readings = _readings([n for _, _, names in items for n in names])
    wanted = [_tokens(query)] + ([_tokens(full)] if full != query else [])
    ranked = []
    for position, (item_id, display, names) in enumerate(items):
        best, entry_season = 0.0, None
        for name in names:
            title, read_season = readings.get(name, ("", None))
            if entry_season is None and read_season is not None:
                entry_season = read_season
            for variant in (name, title):
                if variant:
                    have = _tokens(variant)
                    for tokens in wanted:
                        best = max(best, _similarity(tokens, have))
        season_ok = _entry_season_ok(entry_season, season)
        score = best * (1.0 if season_ok else SEASON_MISMATCH)
        ranked.append((position, Candidate(source, item_id, display, round(score, 4),
                                           round(best, 4), entry_season, season_ok,
                                           best >= MATCH_FLOOR)))
    ranked.sort(key=lambda pc: (not pc[1].accepted, -pc[1].score, pc[0]))
    return [c for _, c in ranked]


def _season_words(season):
    return "season 1 (no season in its name)" if season is None else "season %d" % season


def _choose(ranked, season):
    """-> (the top match or None, [why it is LOW CONFIDENCE]).

    ⚠ A MEASURED LIMIT OF THE THIRD DOUBT, recorded 2026-09-17 rather than
    papered over. `a fuzzy title match` tests `similarity < CONFIDENT`, and the
    containment branch of `_similarity` starts at `0.75 + 0.2 x q/t` -- so it
    is at least CONFIDENT (0.75) by construction and the doubt is UNREACHABLE
    for any query whose tokens are all in the title. Measured: `sim("86",
    "Ojamajo Doremi 86") = 0.8167`, CONFIDENT, for an unrelated show.
    ⛔ NOT re-tuned, because the capture falsifies the obvious fix: `86` inside
    `Ojamajo Doremi 86` and `frieren` inside `Sousou no Frieren` are the SAME
    shape -- one token of three, BOTH scoring 0.8167, raw character ratios
    0.2105 and 0.5833, both under MATCH_FLOOR (0.6) -- so any threshold that
    separates them is a number with no evidence, and one that doubts the recorded
    `?query=frieren` search too. The branch is reachable only for a NON-contained
    fuzzy match, and both facts are pinned in tests/test_identify.py. A wrong
    show is Rule 1's to catch (06-edge-cases.md §1).
    """
    matches = [c for c in ranked if c.accepted]
    if not matches:
        return None, []
    top, doubts = matches[0], []
    if len(matches) > 1 and top.score - matches[1].score <= CLOSE:
        doubts.append("the top two scores are within %d points: %s (%d) and %s (%d)" % (
            round(CLOSE * 100), top.name, round(top.score * 100),
            matches[1].name, round(matches[1].score * 100)))
    if not top.season_ok:
        doubts.append("nothing matched %s -- the best title match is %s"
                      % (_season_words(season), _season_words(top.season)))
    if top.similarity < CONFIDENT:
        doubts.append("a fuzzy title match (%d), not an exact or contained one"
                      % round(top.similarity * 100))
    return top, doubts


def _entry_names(entry):
    return [n for n in (entry.get("name"), entry.get("english_name"), entry.get("japanese_name"))
            if isinstance(n, str) and n.strip()]


def _kitsu_names(hit):
    attributes = hit.get("attributes") if isinstance(hit.get("attributes"), dict) else {}
    titles = attributes.get("titles") if isinstance(attributes.get("titles"), dict) else {}
    abbreviated = attributes.get("abbreviatedTitles")
    abbreviated = abbreviated if isinstance(abbreviated, list) else []
    names = [attributes.get("canonicalTitle")] + list(titles.values()) + abbreviated
    return list(dict.fromkeys(n for n in names if isinstance(n, str) and n.strip()))


def _positive_int(value):
    return type(value) is int and value > 0


def _resolved(entry, top, doubts, source, anilist_id):
    flags = entry.get("flags") if isinstance(entry.get("flags"), dict) else {}
    names = _entry_names(entry)
    if anilist_id is None and _positive_int(entry.get("anilist_id")):
        anilist_id = entry.get("anilist_id")
    return Resolved(entry["id"], names[0] if names else "entry %d" % entry["id"],
                    flags.get("movie") is True, min(max(top.score, 0.0), 1.0), bool(doubts),
                    source, anilist_id)


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


# ---------------------------------------------------------------------------
# identify
# ---------------------------------------------------------------------------

def identify(title, *, season=None, year=None, client, cache, kitsu=None):
    """-> Identification. KeyRejected, Unreachable, RateLimited and NetworkDisabled
    propagate: the run stops, and nothing is cached."""
    query, season, year, full = _parts(title, season, year)
    key = cache_key(title, season, year)
    hit = cache.get(key)
    if hit is not None:
        return Identification(hit, 0, 0, True, [],
                              "from the resolution cache -- nothing was asked")

    jimaku_before = client.metered
    kitsu_before = kitsu.calls if kitsu is not None else 0
    candidates, why = [], []
    resolved, doubts = None, []

    for anime, source in ((True, SOURCE_JIMAKU), (False, SOURCE_ANIME_FALSE)):
        results = client.search(query, anime=anime)
        entries = [e for e in results if _positive_int(e.get("id"))]
        ranked = _rank([(e["id"], (_entry_names(e) or ["entry %d" % e["id"]])[0],
                         _entry_names(e)) for e in entries], query, full, season, source)
        candidates.extend(ranked)
        top, doubts = _choose(ranked, season)
        if top is not None:
            entry = next(e for e in entries if e["id"] == top.id)
            resolved = _resolved(entry, top, doubts, source, None)
            break
        why.append('jimaku search%s for "%s" matched nothing (%s)'
                   % ("" if anime else " with anime=false", query,
                      _plural(len(results), "result")))

    if resolved is None and kitsu is None:
        why.append("no Kitsu fallback was given")
    elif resolved is None:
        try:
            hits = kitsu.search(query)
            items = [(h.get("id"), (_kitsu_names(h) or [str(h.get("id"))])[0], _kitsu_names(h))
                     for h in hits
                     if isinstance(h.get("id"), str) and _KITSU_ID.match(h.get("id"))]
            ranked = _rank(items, query, full, season, SOURCE_KITSU)
            candidates.extend(ranked)
            top, doubts = _choose(ranked, season)
            if top is None:
                why.append('Kitsu search for "%s" matched nothing (%s)'
                           % (query, _plural(len(hits), "hit")))
            else:
                anilist = kitsu.anilist_id(top.id)
                if anilist is None:
                    why.append("Kitsu anime %s (%s) has no AniList mapping on its first page"
                               % (top.id, top.name))
                else:
                    results = client.search(anilist_id=anilist)
                    matches = [e for e in results if _positive_int(e.get("id"))
                               and type(e.get("anilist_id")) is int
                               and e.get("anilist_id") == anilist]
                    if not matches:
                        why.append("jimaku has no entry for AniList id %d (Kitsu anime %s, %s)"
                                   % (anilist, top.id, top.name))
                    else:
                        if len(matches) > 1:
                            doubts.append("%d jimaku entries carry AniList id %d"
                                          % (len(matches), anilist))
                        resolved = _resolved(matches[0], top, doubts, SOURCE_KITSU, anilist)
        except KitsuError as exc:
            why.append("the Kitsu fallback failed: %s" % exc)

    calls = client.metered - jimaku_before
    kitsu_calls = kitsu.calls - kitsu_before if kitsu is not None else 0
    if resolved is None:
        return Identification(None, calls, kitsu_calls, False, candidates, "; ".join(why))
    cache.put(key, resolved)
    reason = "%s: %s (score %d)" % (resolved.source, resolved.entry_name,
                                    round(resolved.score * 100))
    if doubts:
        reason += " -- LOW CONFIDENCE: " + "; ".join(doubts)
    return Identification(resolved, calls, kitsu_calls, False, candidates, reason)


# ---------------------------------------------------------------------------
# the resolution cache -- its own store, one accessor
# ---------------------------------------------------------------------------

_SCHEMA = """CREATE TABLE IF NOT EXISTS resolutions (
    key             TEXT    PRIMARY KEY CHECK (length(key) > 0),
    entry_id        INTEGER NOT NULL CHECK (entry_id > 0),
    entry_name      TEXT    NOT NULL CHECK (length(trim(entry_name)) > 0),
    movie           INTEGER NOT NULL CHECK (movie IN (0, 1)),
    score           REAL    NOT NULL CHECK (score >= 0 AND score <= 1),
    low_confidence  INTEGER NOT NULL CHECK (low_confidence IN (0, 1)),
    source          TEXT    NOT NULL CHECK (source IN ('jimaku', 'jimaku anime=false', 'kitsu')),
    anilist_id      INTEGER CHECK (anilist_id IS NULL OR anilist_id > 0),
    resolved_at     TEXT    NOT NULL
)"""
_COLUMNS = ("key", "entry_id", "entry_name", "movie", "score", "low_confidence", "source",
            "anilist_id", "resolved_at")
_UNAVAILABLE = object()


class _Corrupt(Exception):
    """Not a usable SQLite file. Move it aside."""


class _Unusable(Exception):
    """It could not be opened at all. Leave it."""


class _TooNew(Exception):
    """A newer hato wrote it. Leave it untouched."""


class ResolutionCache(object):
    """Normalized title + season + year -> Resolved, for ever. The only code that
    opens resolution.db.

    It CREATES NOTHING until something is stored, and opens a connection per
    operation, so no handle outlives a call (Windows cannot move an open file).
    ⚠ FAIL OPEN, deliberately: this is a cache, rebuildable at a few API calls per
    show. A corrupt file is moved aside and a fresh one started; a file that cannot
    be opened or moved, or that a newer hato wrote, leaves this run resolving in
    memory. Each says so, in one sentence, in `.notes`.
    """

    def __init__(self, path=None, repair=True):
        """`repair=False` -- for a VIEW (a dry `hato state --clear`): a corrupt file
        is left exactly as it is for the next run to repair (ADVERSARY 2026-09-22
        F2: the dry count moved it aside, then crashed on the None that followed)."""
        self.path = Path(path) if path is not None else paths.data_root() / FILENAME
        self.notes = []
        self.persistent = True
        self._memory = {}
        self._repair = bool(repair)

    def __repr__(self):
        return "<hato ResolutionCache %s%s>" % (self.path, "" if self.persistent else " (in memory)")

    def get(self, key):
        """-> Resolved, or None."""
        key = _checked_key(key)
        if not self.persistent or not self.path.is_file():
            return self._memory.get(key)
        row = self._run(lambda conn: conn.execute(
            "SELECT entry_id, entry_name, movie, score, low_confidence, source, anilist_id "
            "FROM resolutions WHERE key = ?", (key,)).fetchone(), write=False)
        if row is _UNAVAILABLE:
            return self._memory.get(key)
        if row is None:
            return None
        return Resolved(row[0], row[1], bool(row[2]), row[3], bool(row[4]), row[5], row[6])

    def put(self, key, resolved):
        key = _checked_key(key)
        if not isinstance(resolved, Resolved):
            raise TypeError("put() stores a Resolved, got %s" % type(resolved).__name__)
        if self.persistent:
            values = (key, resolved.entry_id, resolved.entry_name, int(resolved.movie),
                      resolved.score, int(resolved.low_confidence), resolved.source,
                      resolved.anilist_id, datetime.now(timezone.utc).isoformat(timespec="seconds"))
            done = self._run(lambda conn: conn.execute(
                "INSERT OR REPLACE INTO resolutions (%s) VALUES (%s)"
                % (", ".join(_COLUMNS), ", ".join("?" * len(_COLUMNS))), values), write=True)
            if done is not _UNAVAILABLE:
                return
        self._memory[key] = resolved

    def forget(self, key):
        """Drop one show's resolution, so its next run looks it up again. -> bool
        (True when something was dropped).

        Added by the orchestrator at wiring time (RUNBOOK 2b ruling): a show whose
        every attempted video was REFUSED by timing was probably identified wrong,
        and a cache that keeps a wrong answer "for ever" never gets another chance.
        ⚠ Creates nothing: forgetting in a store that does not exist yet is a no-op.
        """
        key = _checked_key(key)
        dropped = self._memory.pop(key, None) is not None
        if not self.persistent or not self.path.is_file():
            return dropped
        count = self._run(lambda conn: conn.execute(
            "DELETE FROM resolutions WHERE key = ?", (key,)).rowcount, write=True)
        if count is _UNAVAILABLE:
            return dropped
        return dropped or bool(count)

    def clear(self, dry_run=True):
        """Forget every show this cache has found. -> how many (would have) gone.

        ⭐ RUNBOOK 8g. ⛔ DRY BY DEFAULT. ⚠ Creates nothing: a store that does not
        exist yet holds nothing to forget. Each show is found again on its next
        run, for the few requests it cost the first time.
        """
        held = len(self._memory)
        if not dry_run:
            self._memory.clear()
        if not self.persistent or not self.path.is_file():
            return held
        count = self._run(lambda conn: conn.execute(
            "SELECT count(*) FROM resolutions").fetchone()[0], write=False)
        if count is _UNAVAILABLE or count is None:
            return held                     # ⚠ None: a repairing read set the file aside
        if not dry_run:
            self._run(lambda conn: conn.execute("DELETE FROM resolutions"), write=True)
        return held + count

    # -- the file, and what happens when it goes wrong ---------------------------

    def _run(self, op, write):
        for attempt in (1, 2):
            try:
                conn = self._open()
            except _TooNew as exc:
                return self._unavailable(
                    "The resolution cache at %s was written by a newer hato (schema %s; this one "
                    "reads %d), so it was left untouched and this run resolves in memory."
                    % (self.path, exc, SCHEMA_VERSION))
            except _Unusable as exc:
                return self._unavailable(
                    "The resolution cache at %s could not be opened (%s), so this run resolves "
                    "in memory." % (self.path, exc))
            except _Corrupt as exc:
                problem = exc
            else:
                try:
                    result = op(conn)
                    conn.commit()
                    return result
                except sqlite3.DatabaseError as exc:
                    if type(exc) is not sqlite3.DatabaseError:
                        raise
                    problem = exc
                finally:
                    conn.close()
            if attempt == 2:
                return self._unavailable(
                    "The resolution cache at %s was still unreadable after starting fresh (%s), "
                    "so this run resolves in memory." % (self.path, problem))
            if not self._repair:
                return self._unavailable(
                    "The resolution cache at %s is unreadable (%s). It was left exactly as it "
                    "is for the next run to repair." % (self.path, problem))
            try:
                aside = self._move_aside()
            except OSError as exc:
                return self._unavailable(
                    "The resolution cache at %s is unreadable (%s) and could not be moved aside "
                    "(%s), so this run resolves in memory." % (self.path, problem, exc))
            self.notes.append(
                "The resolution cache was unreadable (%s), so it was moved aside to %s and a "
                "fresh one started -- shows will be looked up again." % (problem, aside.name))
            if not write:
                return None
        return None

    def _open(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=5.0)
        except (OSError, sqlite3.Error) as exc:
            raise _Unusable(exc)
        try:
            # ⚠ quick_check FIRST: damaged pages behind a valid header still answer
            # `PRAGMA user_version` (LEDGER.md §data, measured for the state DB).
            check = conn.execute("PRAGMA quick_check(1)").fetchone()
            if not check or check[0] != "ok":
                raise _Corrupt("integrity check reported %r" % (check[0] if check else None,))
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise _TooNew(version)
            if version < SCHEMA_VERSION:
                conn.execute(_SCHEMA)
                conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
                conn.commit()
            have = set(row[1] for row in conn.execute("PRAGMA table_info(resolutions)"))
            missing = [c for c in _COLUMNS if c not in have]
            if missing:
                raise _Corrupt("the resolutions table has no %s" % ", ".join(missing))
        except BaseException as exc:
            conn.close()
            if type(exc) is sqlite3.DatabaseError:
                raise _Corrupt(exc)
            if isinstance(exc, sqlite3.Error):
                raise _Unusable(exc)
            raise
        return conn

    def _move_aside(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        aside = self.path.with_name("%s.corrupt-%s" % (self.path.name, stamp))
        n = 1
        while aside.exists():
            n += 1
            aside = self.path.with_name("%s.corrupt-%s-%d" % (self.path.name, stamp, n))
        os.replace(str(self.path), str(aside))
        side = Path(str(self.path) + "-journal")
        if side.exists():
            try:
                os.replace(str(side), str(aside) + "-journal")
            except OSError:
                pass
        return aside

    def _unavailable(self, note):
        self.persistent = False
        self.notes.append(note)
        return _UNAVAILABLE
