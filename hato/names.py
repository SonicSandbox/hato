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
from pathlib import Path


class NameInfo(object):
    """One name, and what tsubasa's parser read in it. Never stored; derived."""

    __slots__ = ("name", "stub", "kind", "title", "season", "episode",
                 "episode_candidates", "lang", "lang_tag", "skipped")

    def __init__(self, name, stub):
        self.name = name              # exactly as given
        self.stub = stub              # the filename the stub was created under
        self.kind = None              # "video" | "subtitle" | None (not a known extension)
        self.title = u""
        self.season = None
        self.episode = None
        self.episode_candidates = ()
        self.lang = None
        self.lang_tag = None
        #: why tsubasa's scan deliberately left this name out (e.g. a creditless
        #: opening), or None
        self.skipped = None

    def __repr__(self):
        return "NameInfo(%r, %s, s=%r e=%r%s)" % (
            self.name[:40], self.kind, self.season, self.episode,
            ", skipped" if self.skipped else "")


def read_names(names, workdir, group_of=None):
    """-> [NameInfo], one per DISTINCT name, in first-seen order.

    `group_of(name) -> hashable or None`: names mapping to the same value share
    a folder (so tsubasa's per-folder scheme can use them); None keeps a name
    alone. Duplicate names are read once (06-edge-cases.md §4: dedupe by name).
    """
    import tsubasa
    from hato.cache import safe_name

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
        stub = safe_name(name)
        path = folder / stub
        if path.exists():
            # Two different names made the same stub -- Windows folds case, and
            # safe_name maps characters. Give the second a folder of its own
            # rather than silently reading the first one twice.
            folder = new_folder()
            path = folder / stub
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
        info.lang = item.lang
        info.lang_tag = item.lang_tag
    for path, reason in scan.skipped.items():
        info = by_stub_path.get(os.path.normcase(str(path)))
        if info is not None:
            info.skipped = reason
    return infos
