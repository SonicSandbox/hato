# -*- coding: utf-8 -*-
"""
What tsubasa's parser makes of a NAME -- for names that are not files on disk.

    infos = read_names(names, workdir)                      # each name alone
    infos = read_names(names, workdir, group_of=bracket)    # names sharing a group
                                                            # share a folder

⛔ THIS IS NOT A PARSER. hato never parses a title, a season or an episode itself
(LEDGER-HOT.md: never write a second filename parser -- two copies drift). The
parser is tsubasa's, and its only PUBLIC reading of a name is on the items
`tsubasa.scan()` discovers (`title`, `season`, `episode`, `episode_candidates`,
`lang`, `lang_tag` -- tsubasa spec/05-interface.md §For code built on tsubasa).
`scan()` requires its roots to EXIST. So a name that is not a file -- a jimaku
file list, a filename typed at `hato identify` -- is materialised as a ZERO-BYTE
STUB in a throwaway folder inside the cache, and scanned. `scan()` opens nothing,
so a stub is exactly as good as the real file for this.

⚠ PART 1 DEFECT (recorded in spec/RUNBOOK.md 3a): tsubasa publishes no
name-only parse, and no release group, episode type or version at all. Asking
tsubasa for `parse_name()` would delete this module. Until then this is the one
place hato reaches the parser for a bare name.

⭐ THE FOLDER A STUB SITS IN CHANGES THE ANSWER, deliberately surfaced as
`group_of`. tsubasa infers a per-folder naming SCHEME from sibling names
(`discover.parse_all`, when a folder holds enough of them) and uses it as a
second opinion. A jimaku entry mixes several releases' schemes, so every name
alone (the default) is the neutral reading; stubs grouped by release let each
release's own scheme speak. The folder's NAME never matters -- only who shares
it -- so the folders are numbered.

⛔ Nothing here writes outside `workdir`, and `workdir` is the caller's
(a cache work directory, or a test's tmp_path).
"""
import os
import re
from pathlib import Path


class NameInfo(object):
    """One name, and what tsubasa's parser read in it. Never stored; derived."""

    __slots__ = ("name", "stub", "kind", "title", "season", "episode",
                 "episode_candidates", "dual_numbering", "lang", "lang_tag", "skipped",
                 "unread")

    def __init__(self, name, stub):
        self.name = name              # exactly as given
        self.stub = stub              # the filename the stub was created under, or None
        self.kind = None              # "video" | "subtitle" | None (not a known extension)
        self.title = u""
        self.season = None
        self.episode = None
        self.episode_candidates = ()
        #: ⭐ (season, episode, absolute) when the name states BOTH numberings
        #: (`S02E06.第34話` -> (2, 6, 34)); None otherwise. tsubasa's reading
        #: (`Item.dual_numbering`), never hato's -- a stated bridge between counts.
        self.dual_numbering = None
        self.lang = None
        self.lang_tag = None
        #: why tsubasa's scan deliberately left this name out (e.g. a creditless
        #: opening), or None
        self.skipped = None
        #: ⛔ 16z Z-D1: why hato could not hand tsubasa this name at all (TOO_LONG: no
        #: stub holds it unchanged), or None. Such a name has no stub and reads nothing.
        self.unread = None

    def __repr__(self):
        return "NameInfo(%r, %s, s=%r e=%r%s)" % (
            self.name[:40], self.kind, self.season, self.episode,
            ", skipped" if self.skipped else "")


#: Stands where a stub's middle was cut out. One unit, one byte, and nothing
#: tsubasa reads as a number or a tag.
_CUT = u"~"

#: A leading `[group]`, which the cut keeps whole.
_LEAD_GROUP = re.compile(r"\s*\[[^\[\]]*\]\s*")
#: Where a name's TITLE ends: the first digit (any script's, kanji numerals too), bracket or
#: dot after the group. ⛔ The cut never reaches past it -- what follows holds the numbers.
_TITLE_END = re.compile(r"[\d.\[\](){}<>（）［］【】「」"
                        r"『』〔〕〇零一二三四五"
                        r"六七八九十百千]")

#: NameInfo.unread for a name no stub can hold without changing what it says.
TOO_LONG = (u"its name is too long to read whole in hato's work folder, and shortening it "
            u"outside its title could change its numbers")


def _stub_path(folder, name):
    """-> folder / stub for `name`, inside the SAME budget the cache's blobs use
    (`cache.name_budget`), so the whole path stays inside MAX_PATH -- or None when
    no stub can hold the name without changing what it says.

    🚨 The workdir sits deep in %LOCALAPPDATA%: a ~190-character jimaku name
    passed 259, the stub raised an OSError nothing caught, and the show read
    zero rows (#7, 2026-10-04).
    🚨 16z Z-D1: the cut then fell at a fixed middle -- inside the tags -- and
    spliced a NEW number (`- 12 [1080p]…[AAC 2.~ix…` read episode 2; safe_name's
    own end cut past 255 left `…~34]` from `[ABCD1234]`). A wrong episode.
    ⭐ So the cut is made ONLY inside the TITLE -- after the leading `[group]`,
    before the first digit, bracket or dot -- keeping the title's first and
    last words (`OVA - 01`, `Episode 12`, `第`), so no number is ever touched.
    ⛔ When the title cannot absorb the cut the name gets NO stub (None): read
    as nothing and said, never read as a wrong number. Two names cut to one
    stub are the caller's collision, handled like any other."""
    from hato import tokens
    from hato.cache import _fits, _split_ext, clean_name, name_budget, safe_name

    budget = name_budget(folder)
    whole = clean_name(name)
    if _fits(whole, budget):
        return folder / whole
    stem, ext = _split_ext(whole)
    lead = _LEAD_GROUP.match(stem)
    start = lead.end() if lead else 0
    stop = _TITLE_END.search(stem, start)
    stop = stop.start() if stop else len(stem)
    words = list(re.finditer(r"\S+", stem[start:stop]))
    if len(words) < 3:
        return None                     # no word between the first and the last to cut
    lo, hi = start + words[0].end(), start + words[-1].start()
    inner = stem[lo:hi].strip()         # the spaces that part words stay
    lo = stem.index(inner, lo)
    hi = lo + len(inner)

    def cut_out(k):                     # ⭐ the inner MIDDLE goes, as before
        h = (len(inner) - k) // 2
        return stem[:lo] + inner[:h] + _CUT + inner[h + k:] + stem[hi:] + ext

    if not _fits(cut_out(len(inner)), budget):
        return None                     # even the whole inner title is not enough
    few, many = 0, len(inner)           # each window holds the last: bisect the fewest cut
    while many - few > 1:
        mid = (few + many) // 2
        few, many = (few, mid) if _fits(cut_out(mid), budget) else (mid, many)
    cut = cut_out(many)
    # ⚠ A title word can be a marker (`Title OVA Extended - 01`): a cut that takes one
    # changes what the name IS -- no stub, as for any cut that cannot be made safely.
    if tokens.is_special(cut) != tokens.is_special(whole):
        return None
    # safe_name only as the guard it is: idempotent on a clean name that fits.
    return folder / cut if safe_name(cut, max_len=budget) == cut else None


def read_names(names, workdir, group_of=None):
    """-> [NameInfo], one per DISTINCT name, in first-seen order.

    `group_of(name) -> hashable or None`: names mapping to the same value share
    a folder (so tsubasa's per-folder scheme can use them); None keeps a name
    alone. Duplicate names are read once (06-edge-cases.md §4: dedupe by name).
    """
    import tsubasa

    root = Path(workdir) / "names"
    root.mkdir(parents=True, exist_ok=True)

    seen, order = {}, []
    for name in names:
        if name not in seen:
            seen[name] = None
            order.append(name)

    folder_of_group, next_folder = {}, [0]

    def new_folder():
        next_folder[0] += 1
        d = root / ("%05d" % next_folder[0])
        d.mkdir()
        return d

    infos, by_stub_path = [], {}
    for name in order:
        key = group_of(name) if group_of is not None else None
        if key is None:
            folder = new_folder()
        else:
            folder = folder_of_group.get(key)
            if folder is None:
                folder = folder_of_group[key] = new_folder()
        path = _stub_path(folder, name)
        if path is not None and path.exists():
            # Two different names made the same stub -- Windows folds case,
            # safe_name maps characters, and a deep workdir cuts a long name's
            # middle. Give the second a folder of its own rather than silently
            # reading the first one twice.
            folder = new_folder()
            path = _stub_path(folder, name)
        if path is None:
            info = NameInfo(name, None)
            info.unread = TOO_LONG
            infos.append(info)
            continue
        stub = path.name
        path.write_bytes(b"")
        info = NameInfo(name, stub)
        infos.append(info)
        by_stub_path[os.path.normcase(str(path))] = info

    scan = tsubasa.scan(str(root))
    for item in list(scan.videos) + list(scan.subtitles):
        info = by_stub_path.get(os.path.normcase(str(item.path)))
        if info is None:
            continue
        info.kind = item.kind
        info.title = item.title
        info.season = item.season
        info.episode = item.episode
        info.episode_candidates = tuple(item.episode_candidates)
        # ⚠ getattr: a tsubasa below 0.1.11 (a source checkout, an old install) has no
        # `dual_numbering`, and one missing reading must not stop every name being read --
        # without it the alignment is 1.0.9's, the bridge simply unstated.
        info.dual_numbering = getattr(item, "dual_numbering", None)
        info.lang = item.lang
        info.lang_tag = item.lang_tag
    for path, reason in scan.skipped.items():
        info = by_stub_path.get(os.path.normcase(str(path)))
        if info is not None:
            info.skipped = reason
    return infos
