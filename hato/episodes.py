# -*- coding: utf-8 -*-
"""
Episode range alignment -- which of a jimaku entry's files could be which video
(spec/02-data-model.md §Episode alignment, spec/06-edge-cases.md §2-3, RUNBOOK 3a).

    alignment = align(files, videos, workdir=w)              # a TV entry
    alignment = align(files, videos, workdir=w, movie=True)  # flags.movie == true
    print(explain(alignment))

⭐ THE MECHANISM. hato sees BOTH sides -- the entry's whole file list and the
user's whole folder -- so it never has to know a release's numbering
convention. It lays each release's episode numbers against the folder's and
reads the offset off the best fit:

    videos on disk        1  2  3 …  10
    Haruhana's files     29 30 31 …  38     -> offset +28
    NanakoRaws' files     1  2  3 …  10     -> offset 0

🚨 PER RELEASE, NEVER POOLED. Entry 11446 mixes both conventions; pooled, the
fit ties between 0 and +28, and every file numbered 29-38 is lost (a check in
tests/test_align_episodes.py measures exactly that).

⚠ A RELEASE'S NUMBERS ARE NOT ONE NUMBERING -- measured on the capture: the
Amazon WEBRip reads `S02E06.第34話 …` as episode 34 with no season, and its
siblings as season 2. So a release is split by the season tsubasa read before
anything is fitted, and each part is placed on its own.

⭐ WHEN A PART CANNOT PLACE ITSELF -- its best fit ties (Amazon's 34-36 fit
anywhere from +26 to +33 against 1-10) -- the tie is broken, in this order, by:
    0. ⛔ an offset that would make one of the part's own files an episode below
       zero is not a hypothesis at all, and is dropped before anything else.
    1. its OWN release: a release carries each episode once, so the part lands
       where the rest of its release leaves videos open. Amazon's seasonal part
       covers 1-5 and 9-10; only +28 puts 34-36 on 6-8. (Measured: fed the Amazon
       release alone, rules 2-4 place it at +26 and +33 -- both wrong.)
    2. an offset another release of this entry fitted CLEANLY (whole range, one
       answer): +28 from Haruhana. Offsets are shared; files never are.
    3. the literal number (offset 0) -- "entry 1-8, folder 1-12" fetches the 8.
       ⭐ When offset 0 covers EVERY video, that is not "no fit stands out": it
       is your whole folder matched at the number both sides already name, and
       it is a `range` fit like any other.
    4. ⚠ A GUESS, and labelled one: anchoring its lowest episode to episode 1,
       and its first and last to the folder's. The timing verdict refuses the
       wrong ones, and `hato/rank.py` tries a guess LAST.
       🚨 Anchoring to the folder's ends ALONE loses the answer whenever your
       folder is an INTERIOR slice of the release -- measured 2026-09-17: a
       release numbered 29-40 against a folder of episodes 2-9 anchored to
       {+27, +31} and offered 8 of 8 videos the wrong episode, with the true
       +28 sitting in the tie set, unchosen. Episode numbering starts at 1, so
       "this part's lowest file is episode 1" is a hypothesis with a reason.
    otherwise it is placed nowhere, and a note says why.

🚨 ONE PART, ONE SEASON. A part that reads no season is compatible with every
season a folder holds -- and every one of them used to be FITTED. Measured on
the capture: all ten season-1 videos were offered the season-2 subtitles at
offset +28 with `range` quality and coverage 1.00. A release carries each
episode once, so a part is placed in AT MOST ONE partition, and in none when
two fit it equally well.

⛔ NEVER RANGE-ALIGNED, matched literally or not at all:
    a special (tokens.is_special)     SP1 <-> SP1, and never episode 1
    a half episode (13.5)             13.5 <-> 13.5, never rounded
⛔ REFUSED, never guessed: a file or a video holding several episodes.
⚠ ONE VIDEO has no range to fit -- only literal numbers are matched. The known
soft spot (02-data-model.md §Where this breaks); every such alignment says so.

This module decides who is OFFERED. hato/rank.py decides who goes first, and
the timing verdict decides who is right.

⛔ hato never parses a title, season or episode here: they are tsubasa's
readings -- hato.names.read_names for the entry's names, the discovered video
items for the folder. The other facts about a name are hato/tokens.py's.
"""
import collections

from hato import tokens
from hato.names import read_names

#: Best first. `movie` is its own path and is never compared with the others.
#: ⭐ `guess` is rule 4's unbroken tie, and it sits BELOW `literal` on purpose:
#: a literal number is what both sides wrote down, an anchor is a coin flip
#: between the members of a tie. Ranking it as an `overlap` put a wrong-episode
#: guess at #1 ahead of a correctly-placed release (measured 2026-09-17).
#: ⚠ ORDER IS RANKING: `rank.py` sorts on `QUALITIES.index`, strongest first.
#: ⭐ `position` (2026-09-17) is deliberately the weakest episode hypothesis there
#: is -- it is what a SINGLE video gets when nothing matched its number literally,
#: and it exists because staying silent is not one of hato's options (Rule 1: hato
#: proposes, the timing check disposes).
QUALITIES = ("range", "overlap", "literal", "guess", "position", "movie")

#: ⛔ The lowest episode number a file can be after an offset is applied.
#: `S01E00` exists, so 0 -- but an offset that makes a file episode -2 is
#: arithmetic with no meaning and is never a hypothesis.
EPISODE_FLOOR = 0

#: A part is fitted against every offset while files x videos stays under this.
#: ⭐ Rule 4 (spec/00-INDEX.md): a full fit is quadratic, and a long-running
#: show (1,700 Doraemon files against a 1,700-video folder) would spend seconds
#: on offsets no release uses. Above it, only the structural offsets are
#: fitted -- literal, first-to-first and last-to-last -- and the note says so.
FULL_FIT_BUDGET = 250000


class Candidate(object):
    """One jimaku file offered for one video. Derived; never stored."""

    __slots__ = ("file", "info", "group", "offset", "quality", "coverage", "reason")

    def __init__(self, file, info, group, offset, quality, coverage, reason):
        self.file = file            # the jimaku dict, untouched
        self.info = info            # tsubasa's reading of its name (hato.names.NameInfo)
        self.group = group          # tokens.release_group(name)
        self.offset = offset        # file episode - video episode; None for literal / movie
        self.quality = quality      # one of QUALITIES
        self.coverage = coverage    # 0..1 -- the share of its part's episodes that land on a video
        self.reason = reason        # one sentence, for a person

    @property
    def name(self):
        return self.file["name"]

    def __repr__(self):
        return "Candidate(%r, %s, offset=%r, %.2f)" % (self.name[:48], self.quality,
                                                        self.offset, self.coverage)


#: ⭐ A part never fitted against any videos (`_one_partition_each` found it fits
#: two seasons equally). Not None: None is a real partition, the videos that
#: read no season.
UNFITTED = object()

#: The reason a video with no readable episode number is refused. ⭐ ONE copy:
#: the pipeline records it as that video's soft negative, and `hato problems`
#: recognises it by EQUALITY -- hato's own sentence, never engine prose -- so it
#: files the video with "had a problem", as the run does, instead of under "not
#: on jimaku yet" (ADVERSARY 2026-09-22 F20).
NO_EPISODE = (u"No episode number was read from the video; a film goes through the "
              u"movie path, and nothing else is guessed.")


class GroupSummary(object):
    """One part of one release, as it was placed -- the rows of `--explain`."""

    __slots__ = ("group", "season", "episodes", "files", "offsets", "quality",
                 "coverage", "how", "against", "partition")

    def __init__(self, group, season, episodes, files, against=None):
        self.group = group
        self.season = season            # the season tsubasa read; None = absolute numbering
        self.episodes = episodes        # sorted tuple of the part's episode numbers
        self.files = files              # how many files the part holds
        #: which videos it was fitted against, when the folder reads several
        #: seasons ("S1 videos", "absolute-numbered videos"); None when it reads one
        self.against = against
        #: ⭐ RUNBOOK 8f -- the same fact as a KEY: the video season it was fitted
        #: against, or UNFITTED. `against` is words for a person.
        self.partition = UNFITTED
        self.offsets = ()               # () when it could not be placed
        self.quality = None
        self.coverage = 0.0
        self.how = u""

    @property
    def numbering(self):
        return u"absolute" if self.season is None else u"season %d" % self.season

    def __repr__(self):
        return "GroupSummary(%r, %s, offsets=%r, %s)" % (self.group, self.numbering,
                                                         self.offsets, self.quality)


class Alignment(object):
    """What `align` found. Every video in `videos` is in exactly one of
    `per_video`, `refused` or `not_found`."""

    __slots__ = ("per_video", "refused", "not_found", "groups", "notes",
                 "videos", "files", "movie")

    def __init__(self, videos, files, movie):
        self.per_video = collections.OrderedDict()  # video path -> [Candidate]
        self.refused = collections.OrderedDict()    # video path -> reason
        self.not_found = collections.OrderedDict()  # video path -> reason
        self.groups = []                            # [GroupSummary]
        self.notes = []                             # sentences
        self.videos = videos                        # the videos, in episode order
        self.files = files                          # the distinct file dicts
        self.movie = movie


# ---------------------------------------------------------------------------
# align
# ---------------------------------------------------------------------------

def align(files, videos, *, workdir, movie=False):
    """-> Alignment. `files`: jimaku file dicts. `videos`: tsubasa discovered
    video items (or anything with .path .name .title .season .episode
    .episode_candidates). `workdir`: where hato.names may put its stubs."""
    files, dropped = _distinct(files)
    videos = sorted(videos, key=_video_order)
    result = Alignment(videos, files, movie)
    if dropped:
        result.notes.append(u"%d duplicate or nameless file entr%s ignored; each name is read once."
                            % (dropped, "y was" if dropped == 1 else "ies were"))
    infos = read_names([f["name"] for f in files], workdir, group_of=tokens.release_group)
    by_name = dict((i.name, i) for i in infos)
    if movie:
        _align_movie(result, files, by_name)
    else:
        _align_episodes(result, files, by_name)
    if not videos:
        result.notes.append(u"There are no videos to align against.")
    return result


def _distinct(files):
    seen, out, dropped = set(), [], 0
    for f in files:
        name = f.get("name") if isinstance(f, dict) else None
        if not name or name in seen:
            dropped += 1
            continue
        seen.add(name)
        out.append(f)
    return out, dropped


def _video_order(video):
    ep = video.episode
    return (video.season is None, video.season or 0,
            ep is None, ep if isinstance(ep, (int, float)) else 0, str(video.path))


def _is_whole(number):
    return isinstance(number, int) or (isinstance(number, float) and number.is_integer())


def _fmt_ep(number):
    return u"%d" % number if _is_whole(number) else u"%s" % number


def _fmt_offset(offset):
    return u"0" if offset == 0 else u"%+d" % offset


def _ranges(numbers):
    """(1, 2, 3, 5, 9, 10) -> '1-3, 5, 9-10'"""
    out, run = [], []
    for n in sorted(numbers):
        if run and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(run)
        run = [n]
    if run:
        out.append(run)
    return u", ".join(u"%d" % r[0] if len(r) == 1 else u"%d-%d" % (r[0], r[-1]) for r in out)


# -- the movie path -----------------------------------------------------------

def _align_movie(result, files, by_name):
    """06-edge-cases.md §3: skip episode matching entirely -- every file on the
    entry is a candidate for the one video."""
    offered, skipped = [], []
    for f in files:
        info = by_name[f["name"]]
        if info.skipped:
            skipped.append(f["name"])
            continue
        offered.append((f, info, tokens.release_group(f["name"])))
    counts = collections.Counter(group for _f, _i, group in offered)
    for group in sorted(counts):
        summary = GroupSummary(group, None, (), counts[group])
        summary.quality, summary.coverage = "movie", 1.0
        summary.how = u"a movie entry: episode numbers are not read"
        result.groups.append(summary)
    for video in result.videos:
        if not offered:
            result.not_found[str(video.path)] = u"The movie entry offers no file to try."
            continue
        result.per_video[str(video.path)] = [
            Candidate(f, info, group, None, "movie", 1.0,
                      u"A movie entry: every file on it is a candidate for the film; "
                      u"the timing verdict tells the cuts apart.")
            for f, info, group in offered]
    if len(result.videos) > 1:
        result.notes.append(
            u"A movie entry was offered %d videos; every file is a candidate for each, "
            u"and only the timing verdict can tell them apart." % len(result.videos))
    if skipped:
        result.notes.append(u"%d file(s) tsubasa skips were left out: %s"
                            % (len(skipped), _listed(skipped)))


# -- the episode path ---------------------------------------------------------

class _Part(object):
    """One release's files that share one numbering: the unit that is fitted."""

    __slots__ = ("group", "season", "files", "episodes")

    def __init__(self, group, season):
        self.group, self.season = group, season
        self.files = []             # [(file, info)]
        self.episodes = set()


def _part_key(group, info):
    """-> (release group, season read). 🚨 THE ONE PLACE A FILE JOINS A PART.
    Per release AND per numbering: never pooled across releases, and a release
    whose names read two numberings is split in two."""
    return (group, info.season)


def _align_episodes(result, files, by_name):
    parts = collections.OrderedDict()   # _part_key -> _Part
    specials, halves = [], []
    refused_files, not_subtitles, skipped, unnumbered = [], [], [], []

    for f in files:
        name = f["name"]
        info = by_name[name]
        if info.skipped:
            skipped.append(name)
            continue
        if info.kind != "subtitle":
            not_subtitles.append(name)
            continue
        span = tokens.episode_span(name)
        if span:
            refused_files.append((name, span))
            continue
        group = tokens.release_group(name)
        if tokens.is_special(name):
            specials.append((f, info, group))
            continue
        if info.episode is None:
            unnumbered.append(name)
            continue
        if not _is_whole(info.episode):
            halves.append((f, info, group))
            continue
        key = _part_key(group, info)
        part = parts.get(key)
        if part is None:
            part = parts[key] = _Part(key[0], key[1])
        part.files.append((f, info))
        part.episodes.add(int(info.episode))

    partitions = collections.OrderedDict()  # video season -> {episode: [video]}
    special_videos, half_videos = [], []
    for video in result.videos:
        path = str(video.path)
        span = tokens.episode_span(video.name)
        if span:
            result.refused[path] = (
                u"The video holds episodes %s -- one subtitle cannot be split between them, "
                u"so it is refused rather than guessed." % u"-".join(str(n) for n in (span[0], span[-1])))
            continue
        if tokens.is_special(video.name):
            special_videos.append(video)
            continue
        if video.episode is None:
            result.refused[path] = NO_EPISODE
            continue
        if not _is_whole(video.episode):
            half_videos.append(video)
            continue
        partitions.setdefault(video.season, {}).setdefault(int(video.episode), []).append(video)
        result.per_video[path] = []

    allowed = _one_partition_each(result, list(parts.values()), partitions)
    for season, by_episode in partitions.items():
        compatible = [p for p in parts.values() if season in allowed[id(p)]]
        _fit_partition(result, compatible, season, by_episode, len(partitions) > 1)

    _match_literally(result, specials, special_videos, halves, half_videos)
    _finish(result, partitions, refused_files, not_subtitles, skipped, unnumbered)


def _overlaps(episodes, video_episodes):
    """offset -> how many of the part's episodes land on a video at that offset.

    ⛔ Offsets that would push one of the part's own files below EPISODE_FLOOR
    are dropped here and never become hypotheses. Measured 2026-09-17: a release
    numbered 29-40 against a folder of episodes 2-9 anchored to +31, which calls
    its first file "episode -2".
    """
    vset = set(video_episodes)
    if len(episodes) * len(vset) <= FULL_FIT_BUDGET:
        counted, full = collections.Counter(e - v for e in episodes for v in vset), True
    else:
        structural = {0, min(episodes) - min(vset), max(episodes) - max(vset),
                      min(episodes) - EPISODE_FLOOR - 1}
        counted = dict((d, sum(1 for e in episodes if e - d in vset)) for d in structural)
        full = False
    lowest = min(episodes)
    return dict((d, c) for d, c in counted.items() if lowest - d >= EPISODE_FLOOR), full


def _one_partition_each(result, parts, partitions):
    """-> {id(part): the set of video seasons it may be fitted against}.

    🚨 A RELEASE CARRIES EACH EPISODE ONCE, so one part cannot be season 1 AND
    season 2. A part that reads NO season is compatible with every partition --
    63 of the capture's 120 files read `season=None` -- and every one of them
    used to be fitted: measured, all ten season-1 videos were offered the
    season-2 subtitles at offset +28, `range` quality, coverage 1.00, the
    highest confidence class there is. Reachable through `hato align --explain`
    and `hato rank --folder`; the fetch loop escaped it only because
    `pipeline._discover` keys shows on (title, season, year), which is a guard
    in another module that nothing here pinned.

    It is kept where it fits BEST, and nowhere when two fit it equally well:
    there is nothing to tell them apart, and offering one file as two different
    episodes is the mistake the per-release rule exists to prevent.
    """
    allowed = {}
    for part in parts:
        seasons = [s for s in partitions
                   if s is None or part.season is None or part.season == s]
        if len(seasons) <= 1:
            allowed[id(part)] = set(seasons)
            continue
        scored = []
        for s in seasons:
            overlaps, _full = _overlaps(part.episodes, sorted(partitions[s]))
            scored.append((max(overlaps.values()) if overlaps else 0, s))
        best = max(count for count, _s in scored)
        winners = [s for count, s in scored if count == best]
        if best and len(winners) == 1:
            allowed[id(part)] = {winners[0]}
            continue
        allowed[id(part)] = set()
        if not best:
            continue
        summary = GroupSummary(part.group, part.season, tuple(sorted(part.episodes)),
                               len(part.files))
        summary.how = (u"placed nowhere: it fits the %s equally well, and a release carries "
                       u"each episode once" % _seasons_text(winners))
        result.groups.append(summary)
        result.notes.append(
            u"%s (%s, episodes %s) fits the %s equally well (%d episode(s) each), so it is "
            u"offered to none of them -- one release cannot be two seasons at once."
            % (part.group, summary.numbering, _ranges(part.episodes),
               _seasons_text(winners), best))
    return allowed


def _seasons_text(seasons):
    return u" and ".join(u"absolute-numbered videos" if s is None else u"S%d videos" % s
                         for s in sorted(seasons, key=lambda s: (s is None, s or 0)))


def _fit_partition(result, parts, season, by_episode, several):
    video_eps = sorted(by_episode)
    fits = []
    for part in parts:
        overlaps, full = _overlaps(part.episodes, video_eps)
        best = max(overlaps.values()) if overlaps else 0
        ties = sorted(d for d, c in overlaps.items() if c == best) if best else []
        summary = GroupSummary(part.group, part.season, tuple(sorted(part.episodes)), len(part.files),
                               None if not several else (u"absolute-numbered videos" if season is None
                                                         else u"S%d videos" % season))
        summary.partition = season
        if not full:
            result.notes.append(
                u"%s (%s): %d episodes against %d videos is past the full-fit budget, so only the "
                u"literal, first/last-anchored and episode-1 offsets were tried."
                % (part.group, summary.numbering, len(part.episodes), len(video_eps)))
        fits.append((part, overlaps, best, ties, summary))

    # pass 1 -- a part with ONE best offset, backed by at least two episodes, places itself
    clean = collections.OrderedDict()   # offset -> [groups that fitted their whole range there]
    decided = {}
    for part, overlaps, best, ties, summary in fits:
        if best >= 2 and len(ties) == 1:
            offset = ties[0]
            whole = best == len(part.episodes) == len(video_eps)
            decided[id(part)] = ([offset], "range" if whole else "overlap",
                                 u"its whole range fits at one offset" if whole
                                 else u"one offset fits best; part of the range lands")
            if whole:
                clean.setdefault(offset, []).append(part.group)

    # what each release's self-placed parts already cover
    video_set = set(video_eps)
    covered = collections.defaultdict(set)
    for part, overlaps, best, ties, summary in fits:
        if id(part) in decided:
            covered[part.group].update(e - d for e in part.episodes for d in decided[id(part)][0]
                                       if e - d in video_set)

    # pass 2 -- a tie is broken by its own release, a clean offset, the literal number, the anchors
    for part, overlaps, best, ties, summary in fits:
        if id(part) in decided or not best:
            continue
        taken = covered.get(part.group)
        if taken:
            open_ = [d for d in ties if not any(e - d in taken for e in part.episodes)]
            if len(open_) == 1:
                landed = sorted(e - open_[0] for e in part.episodes if e - open_[0] in video_set)
                decided[id(part)] = (open_, "overlap",
                                     u"tied on its own; %s puts it on the episodes the rest of its "
                                     u"release leaves open (%s)" % (_fmt_offset(open_[0]), _ranges(landed)))
                continue
            ties = open_ or ties
        # ⭐ OFFSET 0 COVERING EVERY VIDEO is not "no fit stands out" -- it is
        # the whole folder matched at the number BOTH sides wrote down, and it
        # is a `range` fit like any other. It used to be labelled `literal`,
        # which ranks below everything, and it used to be reached only AFTER
        # borrowing another release's offset -- so a complete release lost its
        # own folder to any release that merely happened to be the same LENGTH.
        # Measured over the capture: 1,200 of 1,680 equal-length (release window
        # x folder window) arrangements put a wrong-episode candidate at #1
        # ahead of this one, and where format and language tie -- the two ruled
        # parts above it -- it was 312 of 312.
        # ⚠ Never for a single video: one video has no range to align against
        # (the soft spot), and calling that a range fit claims evidence that is
        # not there. ⚠ And never above rule 1, whose evidence is the release's
        # own files, not another's.
        if 0 in ties and len(video_eps) > 1 and overlaps[0] == len(video_eps):
            decided[id(part)] = ([0], "range",
                                 u"every video matches its literal number")
            continue
        shared = [d for d in ties if d in clean]
        if shared:
            decided[id(part)] = (shared, "overlap", u"tied on its own; %s is where %s fit a whole range" % (
                u" and ".join(_fmt_offset(d) for d in shared),
                u", ".join(sorted(set(g for d in shared for g in clean[d])))))
        elif 0 in ties:
            decided[id(part)] = ([0], "literal", u"tied on its own; the literal number is used")
        elif len(part.episodes) >= 2 and len(video_eps) >= 2:
            # ⚠ A GUESS, and it says so. ⭐ `min - 1` -- "this part's lowest
            # file is episode 1" -- is a hypothesis with a REASON behind it
            # (episode numbering starts at 1), and it is the only one of the
            # three that survives when the folder is an interior slice of the
            # release: 29-40 against episodes 2-9 anchors to {+27, +31} and
            # every video gets the wrong episode, while +28 sits in the tie set
            # unchosen (measured 2026-09-17).
            anchors = sorted(set(ties) & {min(part.episodes) - video_eps[0],
                                          max(part.episodes) - video_eps[-1],
                                          min(part.episodes) - 1})
            if anchors:
                decided[id(part)] = (anchors, "guess",
                                     u"tied on its own; a guess -- %s anchored to the folder's "
                                     u"ends and to episode 1"
                                     % u", ".join(_fmt_offset(d) for d in anchors))

    unplaced, unplaced_parts = [], []
    for part, overlaps, best, ties, summary in fits:
        result.groups.append(summary)
        if id(part) not in decided:
            summary.how = (u"placed nowhere: offsets %s fit equally and nothing broke the tie"
                           % _span_text(ties) if ties else u"placed nowhere: no episode lands on a video")
            unplaced.append(summary)
            unplaced_parts.append((part, summary))
            if len(video_eps) > 1:
                result.notes.append(u"%s (%s, episodes %s) was %s." % (
                    part.group, summary.numbering, _ranges(part.episodes), summary.how))
            continue
        offsets, quality, how = decided[id(part)]
        summary.offsets, summary.quality, summary.how = tuple(offsets), quality, how
        summary.coverage = max(overlaps[d] for d in offsets) / float(len(part.episodes))
        for offset in offsets:
            coverage = overlaps[offset] / float(len(part.episodes))
            for f, info in sorted(part.files, key=lambda fi: fi[0]["name"]):
                target = int(info.episode) - offset
                for video in by_episode.get(target, ()):
                    result.per_video[str(video.path)].append(Candidate(
                        f, info, part.group, None if quality == "literal" else offset, quality,
                        coverage, _reason(part, summary, quality, offset, info, target, len(video_eps))))
    if len(video_eps) == 1:
        # ⭐ THE SOFT SPOT, ANSWERED. Anything still unplaced gets one last, weakest
        # hypothesis -- the video's number read as a POSITION in the release's own
        # range -- and the timing verdict rules on it (Rule 1).
        guessed = _offer_by_position(result, unplaced_parts, video_eps[0], by_episode)
        still = [s for p, s in unplaced_parts if id(p) not in guessed]
        note = (u"One video (episode %s): there is no range to align against, so its number was "
                u"matched literally%s -- the known soft spot (02-data-model.md)."
                % (_fmt_ep(video_eps[0]),
                   u", then by position in each release's own numbering" if guessed else u""))
        if still:
            note += (u" %d release(s) were not offered at all, because the video's number does "
                     u"not fit inside their numbering: %s." % (len(still), _listed(
                         u"%s (%s, %s)" % (s.group, s.numbering, _ranges(s.episodes))
                         for s in still)))
        result.notes.append(note)


#: ⭐ How many items a note NAMES before it counts the rest. A note is a sentence,
#: not an inventory. MEASURED 2026-09-17 against the live API on a real library:
#: One Piece's entry carries 2,018 files, and three of these notes ran to ~70 lines
#: of a 106-line report — the one line a person needed sat under an itemised list
#: nobody reads to the end. ⛔ Nothing is hidden: the COUNT is already in every
#: sentence below, and `hato align --explain` still prints every one.
NOTE_ITEMS = 3


def _listed(items, cap=NOTE_ITEMS):
    u"""`a; b; c, and 33 more` -> text. ⚠ The count is stated, never implied."""
    items = list(items)
    if len(items) <= cap:
        return u"; ".join(items)
    return u"%s, and %d more" % (u"; ".join(items[:cap]), len(items) - cap)


def _offer_by_position(result, unplaced_parts, episode, by_episode):
    u"""One video, matched by its POSITION in a release's own range. -> {id(part)}

    🚨 THE SOFT SPOT, MEASURED LIVE 2026-09-17 AND ANSWERED. `Sousou no Frieren
    S2 - 01` against entry 11446, whose every release numbers the season 29-38:
    nothing matched literally, so hato offered **nothing at all** and the person
    got no subtitle for the commonest shape there is -- one episode in a folder.

    ⭐ Not knowing the offset is not permission to stay silent. `00-INDEX.md`
    Rule 1: *"The timing check is the REFEREE. hato only ever produces a
    hypothesis."* So the weakest honest hypothesis is offered -- *your episode 1
    is that release's first file* -- and tsubasa refuses it if the timing does
    not hold. A wrong guess costs one unmetered download and is recorded, never
    re-fetched.

    ⛔ THE GUARD IS WHAT KEEPS IT HONEST: the video's number must fit INSIDE the
    release's own length. Measured in the same run, `One Piece - 1121` against a
    33-file release proposes nothing, because 1121 is not a position in 33 files.
    ⛔ A half episode (`13.5`) is never guessed by position -- it is matched
    literally or not at all (`06-edge-cases.md` §2).
    """
    offered = set()
    videos = by_episode.get(episode, ())
    if not videos:
        return offered
    try:
        wanted = int(episode)
    except (TypeError, ValueError):
        return offered
    if wanted != episode:                       # ⛔ 13.5 is not a position
        return offered
    for part, summary in unplaced_parts:
        eps = sorted(part.episodes)
        if not (1 <= wanted <= len(eps)):        # ⛔ the guard, and it is load-bearing
            continue
        target = eps[wanted - 1]
        hits = [(f, info) for f, info in part.files if info.episode == target]
        if not hits:
            continue
        offset = target - wanted
        summary.offsets, summary.quality = (offset,), "position"
        summary.coverage = 1.0 / len(eps)
        summary.how = (u"guessed by position: it numbers its %d files %s, so episode %s here "
                       u"would be its %s" % (len(eps), _ranges(part.episodes),
                                             _fmt_ep(episode), _fmt_ep(target)))
        for f, info in sorted(hits, key=lambda fi: fi[0]["name"]):
            for video in videos:
                result.per_video[str(video.path)].append(Candidate(
                    f, info, part.group, offset, "position", summary.coverage,
                    u"%s numbers this season %s, so its episode %s is where episode %s falls "
                    u"by position -- a guess, and the timing decides."
                    % (part.group, _ranges(part.episodes), _fmt_ep(info.episode),
                       _fmt_ep(episode))))
        offered.add(id(part))
    return offered


def _span_text(offsets):
    if len(offsets) > 3 and offsets[-1] - offsets[0] == len(offsets) - 1:
        return u"%s to %s" % (_fmt_offset(offsets[0]), _fmt_offset(offsets[-1]))
    return u", ".join(_fmt_offset(d) for d in offsets)


def _reason(part, summary, quality, offset, info, target, n_videos):
    who = u"%s (%s, episodes %s)" % (part.group, summary.numbering, _ranges(part.episodes))
    if quality == "range":
        return (u"%s fits the %d videos cleanly at offset %s, so its episode %s is episode %s."
                % (who, n_videos, _fmt_offset(offset), _fmt_ep(info.episode), _fmt_ep(target)))
    if quality == "literal":
        return u"%s has no fit that stands out; its number %s is taken literally." % (
            who, _fmt_ep(info.episode))
    if quality == "guess":
        return (u"%s could sit at several offsets and nothing broke the tie, so offset %s is a "
                u"GUESS (%s): its episode %s would be episode %s. The timing verdict decides."
                % (who, _fmt_offset(offset), summary.how, _fmt_ep(info.episode), _fmt_ep(target)))
    return (u"%s fits best at offset %s (%s), so its episode %s is episode %s."
            % (who, _fmt_offset(offset), summary.how, _fmt_ep(info.episode), _fmt_ep(target)))


def _match_literally(result, specials, special_videos, halves, half_videos):
    """Specials and half episodes are never range-aligned (06-edge-cases.md §2)."""
    used = set()
    for video in special_videos:
        path = str(video.path)
        marker = tokens._special_marker(video.name)
        matches = [(f, info, g) for f, info, g in specials
                   if tokens._special_marker(f["name"]) == marker and info.episode == video.episode]
        if not matches:
            result.refused[path] = (
                u"A special (%s) is never range-aligned, and no file on the entry is the same "
                u"special%s literally." % (marker.upper(), u"" if video.episode is None
                                           else u" %s" % _fmt_ep(video.episode)))
            continue
        result.per_video[path] = [Candidate(
            f, info, g, None, "literal", 1.0,
            u"A special is never range-aligned; %s %s matched %s literally." % (
                marker.upper(), u"" if video.episode is None else _fmt_ep(video.episode), f["name"]))
            for f, info, g in matches]
        used.update(f["name"] for f, _i, _g in matches)
    for video in half_videos:
        path = str(video.path)
        matches = [(f, info, g) for f, info, g in halves if info.episode == video.episode]
        if not matches:
            result.not_found[path] = (u"No file on the entry is episode %s; a half episode is "
                                      u"matched literally, never rounded." % _fmt_ep(video.episode))
            continue
        result.per_video[path] = [Candidate(
            f, info, g, None, "literal", 1.0,
            u"A half episode is matched literally: %s is %s, never rounded." % (
                _fmt_ep(info.episode), _fmt_ep(video.episode)))
            for f, info, g in matches]
        used.update(f["name"] for f, _i, _g in matches)
    unmatched = [f["name"] for f, _i, _g in specials + halves if f["name"] not in used]
    if unmatched:
        result.notes.append(u"%d special or half-episode file(s) matched no video literally and are "
                            u"offered to none: %s" % (len(unmatched), _listed(unmatched)))


def _finish(result, partitions, refused_files, not_subtitles, skipped, unnumbered):
    for path in list(result.per_video):
        if result.per_video[path]:
            continue
        del result.per_video[path]
        video = next(v for v in result.videos if str(v.path) == path)
        result.not_found[path] = (u"No release on the entry places a file on episode %s."
                                  % _fmt_ep(video.episode))
    for season, by_episode in partitions.items():
        crowded = [ep for ep, vids in by_episode.items() if len(vids) > 1]
        if crowded:
            result.notes.append(u"Several videos read the same episode (%s); each is offered the "
                                u"same files." % _ranges(crowded))
    if len(partitions) > 1:
        result.notes.append(u"The videos read %d different seasons; each season was aligned on its "
                            u"own." % len(partitions))
    if refused_files:
        result.notes.append(u"%d file(s) hold several episodes and are refused, never guessed: %s"
                            % (len(refused_files), _listed(
                                u"%s (%s)" % (n, u"+".join(str(e) for e in s)) for n, s in refused_files)))
    if not_subtitles:
        # ⚠ AMENDED 2026-09-17: this said archives are opened "by RUNBOOK 3c", which was
        # never true of a run -- 3c built the extractor and nothing called it. Sonic then
        # ruled archives OFF by default (`06-edge-cases.md` §5), so the sentence names the
        # flag instead of promising something that does not happen.
        result.notes.append(u"%d file(s) are archives or otherwise not subtitles; hato does not "
                            u"open them unless --archives is on: %s"
                            % (len(not_subtitles), _listed(not_subtitles)))
    if skipped:
        result.notes.append(u"%d file(s) tsubasa skips were left out: %s"
                            % (len(skipped), _listed(skipped)))
    if unnumbered:
        result.notes.append(u"%d file(s) carry no episode number and are offered to no video: %s"
                            % (len(unnumbered), u"; ".join(unnumbered)))


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 8f -- the newest episode on offer, for *probably not out yet*
# ---------------------------------------------------------------------------

def newest_offered(alignment, video):
    """The newest episode jimaku's releases offer, in `video`'s own numbering. -> int or None

    ⭐ RUNBOOK 8f (HANDOFF 4c): an episode exactly ONE past the newest on offer
    is probably not out yet, and the window says so instead of presenting what
    was tried as a pick.

    🚨 NOT `max(episodes) - offset` OF WHATEVER THE FIT CHOSE, and the reason
    is measured. The fit takes the offset under which MOST videos land, so a
    folder that holds the episode a release does not have yet SLIDES it: a
    release of S04E01-22 against videos 21-23 lands three videos at -1 and
    only two at 0. Sonic's own Iruma-kun S4 23 was offered E22, E20 and E03 on
    2026-09-20 -- the fit's anchors -- and timing refused all three, correctly.
    Read off that placement, the release "offers 23", and the one case this
    exists for could never be said. So a part counts only where its numbering
    is KNOWN:

      the video's own count        its own number. ⛔ A release counted the way
      (`_one_count`: its season,   the video is cannot number an episode LOWER
      absolute against absolute,   than it is, so a negative placement is the
      or absolute against          slide; a single positive one is a release
      season 1)                    numbering on through the season, and is
                                   honoured
      the absolute count against   its newest, moved by that offset
      a LATER season, placed by a
      RANGE fit (`range` /
      `overlap`) at ONE offset
      that can be the gap between
      them (`_across_the_gap`)
      anything else, or placed     nothing -- no number is proved
      nowhere

    ⚠ Absolute against absolute is the SAME count (ADVERSARY 2026-09-22 F4b:
    read as another one, a slid absolute release "offered" an episode no file
    has) -- and so is absolute against season 1, which is where the absolute
    count STARTS: Sonic's Tsuihou 12 and Tetsunabe 09 are a first season's
    release against a folder numbered without one. A literal or position
    placement of another count is a guess (F4d: one video, a whole-show
    release, and a made-up newest episode of 87 in a season of 22).

    🚨 AND BETWEEN THE ABSOLUTE COUNT AND A LATER SEASON THE OFFSET *IS* THE
    EPISODES BEFORE THAT SEASON -- never 0, and one way only. A `range` fit at
    0, or the wrong way, is the numbers coinciding: a whole-show release 1-88
    covers a season-4 folder's 21-23 at its literal number, and reading that
    said the newest on offer is 88 -- which hid *probably not out yet* for an
    episode no release had.

    🚨 AND THE CLAIM IS A POSITIVE ONE, so evidence against it wins. An
    ABSOLUTE release fitted against a season, spanning just MORE episodes than
    the newest proved -- 23 against 22 -- is most likely that season in the
    whole-show count, one episode further on: it may hold this one, and nothing
    is said (F4a: such a release, placed by a guess, DID carry E23, and the
    window said *probably not out yet* over it). ⚠ Its guess cannot say so by
    itself: on the real capture the absolute releases are guessed too, and one
    of their guesses puts the season's LAST file on the late video -- the same
    slide as a seasonal release's. ⛔ Beyond `SPAN_SLACK` it is a whole-show
    release, and its length says nothing about this season.

    ⚠ Only parts fitted against the VIDEO'S OWN partition: in a folder holding
    two seasons, season 1's releases say nothing about season 2's episodes.
    ⛔ A derivation, never stored by this module; a film has no next episode.
    """
    episode = getattr(video, "episode", None)
    if alignment.movie or episode is None or isinstance(episode, bool):
        return None
    season = getattr(video, "season", None)
    mine = [s for s in alignment.groups
            if s.partition is not UNFITTED and s.partition == season and s.episodes]
    newest = None
    for summary in mine:
        if not summary.offsets:
            continue                                # placed nowhere counts for nothing
        top = max(summary.episodes)
        if _one_count(summary.season, season):
            positive = [d for d in summary.offsets if d > 0]
            if len(positive) == 1 and len(summary.offsets) == 1:
                value = top - positive[0]           # numbered on through the season
            elif positive:
                continue                            # a guess among upward shifts
            else:
                value = top                         # 0, or the slide: its own number
        elif (len(summary.offsets) == 1 and summary.quality in PROVEN
              and _across_the_gap(summary.season, summary.offsets[0])):
            value = top - summary.offsets[0]
        else:
            continue                                # a guess proves no number (F4d)
        newest = value if newest is None else max(newest, value)
    if newest is not None and not _one_count(None, season):
        for summary in mine:
            span = max(summary.episodes) - min(summary.episodes) + 1
            if summary.season is None and newest < span <= newest + SPAN_SLACK:
                return None                         # it may hold this episode (F4a)
    return int(newest) if newest is not None else None


def _one_count(release, video):
    """True when two season readings number episodes the SAME way: one season,
    or the absolute count against season 1 -- the absolute count starts there,
    so S01E12 and episode 12 are one episode (`newest_offered`)."""
    return release == video or (release is None and video == 1) or (release == 1 and video is None)


def _across_the_gap(release, offset):
    """True when `offset` can be the gap between the absolute count and a LATER
    season: the episodes before that season, so never 0, and one way only. An
    absolute release numbers the season HIGHER; the season's own release numbers
    the absolute count LOWER. Anything else is the numbers coinciding."""
    return offset > 0 if release is None else offset < 0


#: ⭐ RUNBOOK 8f -- the placements that PROVE a release's numbering: a range of
#: its episodes landed on the folder's at one offset. Everything below them in
#: `QUALITIES` is a hypothesis for the timing check, and proves no number.
PROVEN = ("range", "overlap")

#: How much LONGER than the newest proved an absolute release may be and still
#: read as the same season further on (`newest_offered`, F4a). ⚠ A release is
#: a few episodes ahead at most; past this it counts the whole show.
SPAN_SLACK = 3


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

def explain(alignment):
    """The `hato align --explain` rendering: per release its range, offset and
    fit; per video the file episode each release offers; then what was refused,
    not found, and every note."""
    a = alignment
    out = []
    out.append(u"%s · %d file%s on the entry · %d video%s" % (
        u"MOVIE ENTRY" if a.movie else u"TV ENTRY", len(a.files), u"" if len(a.files) == 1 else u"s",
        len(a.videos), u"" if len(a.videos) == 1 else u"s"))
    out.append(u"Which files could be which video. Ranking is `hato rank`; the timing verdict decides.")
    out.append(u"")

    if a.movie:
        out.append(u"RELEASES -- a movie entry: episode numbers are not read")
        for g in a.groups:
            out.append(u"  %-34s %3d file%s" % (g.group, g.files, u"" if g.files == 1 else u"s"))
    else:
        out.append(u"RELEASES -- each fitted on its own, split where its numbering changes")
        rows = [(u"release", u"numbering", u"files", u"episodes", u"offset", u"fit", u"")]
        for g in a.groups:
            numbering = g.numbering if g.against is None else u"%s -> %s" % (g.numbering, g.against)
            fit = u"-" if g.quality is None else u"%s %d/%d" % (
                g.quality, round(g.coverage * len(g.episodes)), len(g.episodes))
            offsets = u"-" if not g.offsets else (
                u"literal" if g.quality == "literal" else u" ".join(_fmt_offset(d) for d in g.offsets))
            rows.append((g.group, numbering, u"%d" % g.files, _ranges(g.episodes), offsets, fit, g.how))
        widths = [max(len(r[i]) for r in rows) for i in range(6)]
        for r in rows:
            out.append((u"  " + u"  ".join(r[i].ljust(widths[i]) if i != 2 else r[i].rjust(widths[i])
                                          for i in range(6)) + u"  " + r[6]).rstrip())
    out.append(u"")

    out.append(u"VIDEOS")
    for video in a.videos:
        path = str(video.path)
        label = u"ep %s" % (_fmt_ep(video.episode) if video.episode is not None else u"?")
        if path in a.per_video:
            cands = a.per_video[path]
            out.append(u"  %-6s %s  -- %d file%s" % (label, video.name, len(cands),
                                                       u"" if len(cands) == 1 else u"s"))
            out.extend(_offer_lines(cands))
        elif path in a.refused:
            out.append(u"  %-6s %s  -- REFUSED" % (label, video.name))
        else:
            out.append(u"  %-6s %s  -- NOT FOUND" % (label, video.name))

    for title, table in ((u"REFUSED", a.refused), (u"NOT FOUND", a.not_found)):
        if table:
            out.append(u"")
            out.append(title)
            names = dict((str(v.path), v.name) for v in a.videos)
            for path, reason in table.items():
                out.append(u"  %s" % names.get(path, path))
                out.append(u"      %s" % reason)
    if a.notes:
        out.append(u"")
        out.append(u"NOTES")
        for note in a.notes:
            out.append(u"  - %s" % note)
    return u"\n".join(out)


def _offer_lines(cands):
    """One line per (file episode, how it was placed): the releases offering it."""
    by_key = collections.OrderedDict()
    for c in sorted(cands, key=lambda c: (c.quality == "movie", c.quality == "literal",
                                          c.offset if c.offset is not None else 0,
                                          c.info.episode if c.info.episode is not None else 0)):
        if c.quality == "movie":
            key = (u"", u"movie")
        elif c.quality == "literal":
            key = (u"file %s" % _fmt_ep(c.info.episode), u"literal")
        else:
            key = (u"file %s" % _fmt_ep(c.info.episode), u"offset %s" % _fmt_offset(c.offset))
        groups = by_key.setdefault(key, collections.OrderedDict())
        groups[c.group] = groups.get(c.group, 0) + 1
    w0 = max([len(k[0]) for k in by_key] or [0])
    w1 = max([len(k[1]) for k in by_key] or [0])
    return [(u"         %s  %s  %s" % (k[0].ljust(w0), k[1].ljust(w1), u" · ".join(
        g if n == 1 else u"%s ×%d" % (g, n) for g, n in groups.items()))).rstrip()
        for k, groups in by_key.items()]
