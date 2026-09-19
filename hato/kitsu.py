# -*- coding: utf-8 -*-
"""
Kitsu -- the fallback when jimaku's own search misses twice (spec/02-data-model.md
§Identification): Kitsu's fuzzy search -> the anime's /mappings -> its AniList id ->
jimaku `search?anilist_id=`. Two Kitsu calls, and only for a show jimaku did not find.

    kitsu = KitsuClient()
    hits = kitsu.search("sousou no friern")    -> [anime resource]  (JSON:API `data`)
    kitsu.anilist_id(46474)                    -> 154587, or None
    kitsu.calls · kitsu.waits

Measured (spec/08-research.md §Identity resolution); each a check in
tests/test_identify.py:

- ⚠ HIGH RECALL, LOW PRECISION. Junk input returns 76 confident results. This module
  therefore RANKS NOTHING: it returns what Kitsu said, in Kitsu's order, and
  hato.resolution scores every hit itself.
- ⚠ PERCENT-ENCODE CJK EXPLICITLY. Unencoded, 葬送のフリーレン silently returned Attack
  on Titan. The query string is built here, every character outside the unreserved
  set encoded -- byte for byte the request that was recorded.
- AniList itself is never called: its search is token-exact (a confirmer, never a
  discoverer), it 403s without a Referer, and its ToS forbids mass collection.
- ⛔ HATO_NO_NETWORK=1 refuses every call before a session is touched, exactly as the
  jimaku client does (a RecordedSession is exempt).

Decisions where the spec left room:
- no retry ladder: a Kitsu failure is a KitsuError, identification reports it and
  caches nothing, so the next run simply asks again
- one jittered 1-2 s gap before every Kitsu call after the first
- ⚠ only the FIRST page of /mappings is read (Kitsu's default page holds 10; the
  recorded show has 2). A show whose AniList mapping sits on a later page reads as
  having none -- stated in the reason, never guessed
"""
import json
import random
import re
import time
from urllib.parse import quote

import requests

from hato import __version__
from hato.client import EmptyQuery, NetworkDisabled, network_disabled

KITSU = "https://kitsu.io/api/edge"
#: Hits asked for. The recorded searches used 5; more is more noise to score.
PAGE_LIMIT = 5
TIMEOUT = (10, 30)
PACE = (1.0, 2.0)
USER_AGENT = "hato/%s" % __version__
ANILIST_SITE = "anilist/anime"

_DIGITS = re.compile(r"[0-9]+\Z")


class KitsuError(Exception):
    """Kitsu gave no usable answer. Identification reports it and caches nothing."""


def _kitsu_id(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and _DIGITS.match(value) and int(value) > 0:
        return int(value)
    raise ValueError("a Kitsu anime id is a plain positive number, got %r" % (value,))


def _resources(data, what):
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise KitsuError("%s: the answer has no `data` list" % what)
    return [item for item in items if isinstance(item, dict)]


class KitsuClient(object):

    def __init__(self, session=None, *, sleep=time.sleep, rng=None):
        self._session = session
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()
        #: HTTP answers from Kitsu. Counted apart from jimaku's metered calls.
        self.calls = 0
        #: [(seconds, why)]
        self.waits = []
        self._asked = False

    def __repr__(self):
        return "<hato KitsuClient, %d call%s>" % (self.calls, "" if self.calls == 1 else "s")

    def search(self, text):
        """-> Kitsu's anime resources for `text`, unranked."""
        if not isinstance(text, str):
            raise TypeError("text must be a str, got %s" % type(text).__name__)
        text = text.strip()
        if not text:
            raise EmptyQuery("refused to search Kitsu with an EMPTY text -- it would match "
                             "everything. Nothing was sent.")
        url = "%s/anime?filter%%5Btext%%5D=%s&page%%5Blimit%%5D=%d" % (
            KITSU, quote(text, safe=""), PAGE_LIMIT)
        return _resources(self._get(url, "Kitsu search for %r" % text), "Kitsu search")

    def anilist_id(self, kitsu_anime_id):
        """-> the AniList id Kitsu maps this anime to, or None."""
        anime = _kitsu_id(kitsu_anime_id)
        what = "Kitsu mappings of anime %d" % anime
        for mapping in _resources(self._get("%s/anime/%d/mappings" % (KITSU, anime), what), what):
            attributes = mapping.get("attributes")
            if not isinstance(attributes, dict) or attributes.get("externalSite") != ANILIST_SITE:
                continue
            value = attributes.get("externalId")
            if type(value) is int and value > 0:
                return value
            if isinstance(value, str) and _DIGITS.match(value) and int(value) > 0:
                return int(value)
        return None

    def _get(self, url, what):
        if network_disabled(self._session):
            raise NetworkDisabled("HATO_NO_NETWORK=1 -- the network is switched off, so nothing "
                                  "was sent to Kitsu. Unset it, or serve recorded responses "
                                  "with --fixtures DIR.")
        if self._asked:
            gap = self._rng.uniform(*PACE)
            self.waits.append((gap, "pacing between Kitsu calls"))
            self._sleep(gap)
        self._asked = True
        if self._session is None:
            self._session = requests.Session()
        try:
            resp = self._session.get(url, timeout=TIMEOUT, allow_redirects=False,
                                     headers={"Accept": "application/vnd.api+json",
                                              "User-Agent": USER_AGENT})
        except requests.exceptions.RequestException as exc:
            raise KitsuError("%s got no answer (%s: %s)" % (what, type(exc).__name__, exc))
        try:
            self.calls += 1
            if resp.status_code != 200:
                raise KitsuError("%s: Kitsu answered HTTP %d" % (what, resp.status_code))
            try:
                return json.loads(resp.content.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise KitsuError("%s: the answer is not UTF-8 JSON (%s)" % (what, exc))
        finally:
            resp.close()
