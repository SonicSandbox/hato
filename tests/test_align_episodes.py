# -*- coding: utf-8 -*-
"""
hato/episodes.py -- which of a jimaku entry's files could be which video (RUNBOOK 3a).

Driven by the REAL capture of entry 11446 (tests/fixtures/api) against folders of
zero-byte stub videos with real release names, read through `tsubasa.scan()` --
both numbering conventions, seasonal `S2 - 01..10` and absolute `- 29..38`.

⭐ NOTHING IS PINNED. Where season 2 starts in each numbering, how many episodes
it has, which releases exist and which file is which episode are all read off
the capture through tsubasa's own reading (`hato.names.read_names`). The one
fact of the show a check leans on is what the capture itself shows: a file
numbered seasonally and one numbered absolutely are the same episode when they
differ by the capture's own shift.

⭐ EVERY EDGE CASE FIRST PROVES ITS HARM IS REAL -- that tsubasa reads `SP1`, `29-30`
and `S2 - 11-12` as a plain episode -- so a check cannot pass because the input
was harmless.

What it structurally cannot cover: whether a candidate IS right. That is the
timing verdict's (RUNBOOK 4b); this suite proves who is OFFERED.
"""
import argparse
import json
from pathlib import Path

import pytest
import tsubasa

from hato import archives, episodes, names, rank, tokens
from hato.commands import align as align_command

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "tests" / "fixtures" / "api"
FILES = json.loads((API / "entries_11446_files.json").read_text(encoding="utf-8"))
MOVIE_FILES = json.loads((API / "entries_movie_flag.json").read_text(encoding="utf-8"))


def file_dict(name, size=30000):
    """A file entry for a name that is not in the capture (constructed; the name's
    SHAPE is a measured one). The keys are the capture's own."""
    return {"name": name, "size": size, "last_modified": FILES[0]["last_modified"],
            "url": FILES[0]["url"].rsplit("/", 1)[0] + "/constructed"}


def stubs(folder, video_names):
    folder.mkdir(parents=True, exist_ok=True)
    for n in video_names:
        (folder / n).write_bytes(b"")
    return list(tsubasa.scan(videos=str(folder)).videos)


def seasonal(numbers):
    return [u"[SubsPlease] Sousou no Frieren S2 - %02d (1080p) [ABCD1234].mkv" % n for n in numbers]


def absolute(numbers):
    return [u"[SubsPlease] Sousou no Frieren - %02d (1080p) [ABCD1234].mkv" % n for n in numbers]


def offered(alignment, video):
    return sorted(c.name for c in alignment.per_video.get(str(video.path), ()))


@pytest.fixture(scope="module")
def reading(tmp_path_factory):
    infos = names.read_names([f["name"] for f in FILES], tmp_path_factory.mktemp("reading"),
                             group_of=tokens.release_group)
    return dict((i.name, i) for i in infos)


@pytest.fixture(scope="module")
def season(reading):
    """Season 2 as the capture shows it: its first seasonal episode, the shift to
    the absolute count (the first episode read with NO season), and its length."""
    first = min(i.episode for i in reading.values() if i.season is not None)
    shift = min(i.episode for i in reading.values() if i.season is None) - first
    length = len({i.episode for i in reading.values() if i.season is not None and i.episode < first + shift})
    assert shift > 0 and length > 1, (first, shift, length)
    return {"first": first, "shift": shift, "numbers": list(range(first, first + length))}


def same_episode(file_episode, video_episode, shift):
    return file_episode in (video_episode, video_episode + shift, video_episode - shift)


# ---------------------------------------------------------------------------
# ⭐ the finding this step exists for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("numbering", ["seasonal", "absolute"])
def test_on_entry_11446_releases_resolve_to_different_offsets_and_every_one_is_offered(
        tmp_path, reading, season, numbering):
    shift = season["shift"]
    if numbering == "seasonal":
        videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    else:
        videos = stubs(tmp_path / "v", absolute([n + shift for n in season["numbers"]]))
    assert len(videos) == len(season["numbers"])
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")

    offsets = sorted({d for g in a.groups for d in g.offsets})
    assert offsets == ([0, shift] if numbering == "seasonal" else [-shift, 0]), a.groups
    assert not a.refused and not a.not_found, (a.refused, a.not_found)
    releases = {tokens.release_group(n) for n in reading}
    for video in videos:
        cands = a.per_video[str(video.path)]
        assert {c.group for c in cands} == releases, video.name
        truth = sorted(n for n, i in reading.items() if same_episode(i.episode, video.episode, shift))
        assert sorted(c.name for c in cands) == truth, video.name


def test_pooling_the_releases_into_one_range_gives_a_worse_result(tmp_path, reading, season, monkeypatch):
    """🚨 02-data-model.md: aligning the pooled set produces nonsense. Measured
    here: pooled, the fit ties between 0 and the shift, and every file numbered
    the other way is lost. Pooling goes through the real code path -- only the
    one place a file joins a part is replaced."""
    shift = season["shift"]
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    per_release = episodes.align(FILES, videos, workdir=tmp_path / "a")
    monkeypatch.setattr(episodes, "_part_key", lambda group, info: (u"every release pooled", None))
    pooled = episodes.align(FILES, videos, workdir=tmp_path / "b")

    def right_and_wrong(alignment):
        right = wrong = 0
        for video in videos:
            for c in alignment.per_video.get(str(video.path), ()):
                if same_episode(c.info.episode, video.episode, shift):
                    right += 1
                else:
                    wrong += 1
        return right, wrong

    available = sum(1 for v in videos for i in reading.values() if same_episode(i.episode, v.episode, shift))
    assert right_and_wrong(per_release) == (available, 0)
    right, _wrong = right_and_wrong(pooled)
    assert right < available, (right, available)
    lost = sorted(n for n, i in reading.items() if i.episode not in season["numbers"])
    still = sorted(c.name for v in videos for c in pooled.per_video.get(str(v.path), ()) if c.name in lost)
    assert lost and still == [], still
    assert any(g.quality == "range" for g in per_release.groups)
    assert not any(g.quality == "range" for g in pooled.groups), pooled.groups


def test_a_release_whose_names_read_two_numberings_is_split_and_every_file_lands_on_its_episode(
        tmp_path, reading, season):
    """⚠ Measured on the capture: the Amazon WEBRip reads `S02E06.第34話 …` as 34
    with no season. Aligned ALONE -- nothing to borrow an offset from -- every
    Amazon file must still land on its true episode and no other."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    assert {reading[f["name"]].season is None for f in amazon} == {True, False}, "the capture mixes both"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    assert len(a.groups) == 2 and {g.quality for g in a.groups} == {"overlap"}, a.groups   # two PARTIAL parts
    for f in amazon:
        info = reading[f["name"]]
        true_episode = info.episode if info.season is not None else info.episode - season["shift"]
        where = sorted(v.episode for v in videos if f["name"] in offered(a, v))
        assert where == [true_episode], (f["name"], where)


def test_a_partial_release_takes_the_offset_another_release_fitted_whole(tmp_path, reading, season):
    shift = season["shift"]
    first_five = [f for f in FILES if f["name"].startswith(u"[Haruhana]")
                  and reading[f["name"]].episode < season["first"] + shift + 5]
    whole = [f for f in FILES if f["name"].startswith(u"[KitaujiSub]")]
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(first_five + whole, videos, workdir=tmp_path / "w")
    for f in first_five:
        where = sorted(v.episode for v in videos if f["name"] in offered(a, v))
        assert where == [reading[f["name"]].episode - shift], (f["name"], where)


@pytest.mark.parametrize("arrangement", ["the release is a prefix of the folder",
                                         "the folder is an interior slice of the release"])
def test_an_unbroken_tie_still_holds_the_true_offset_and_is_labelled_a_guess(
        tmp_path, reading, season, arrangement):
    """🚨 ANCHORING TO THE FOLDER'S ENDS ALONE LOSES THE ANSWER whenever your
    folder is an INTERIOR slice of the release: neither end lines up, so the two
    anchors are the two EXTREMES of a tie whose true member sits between them.
    Measured 2026-09-17 on a release numbered 29-40 against episodes 2-9 -- the
    anchors were {+27, +31} and 8 of 8 videos were offered the wrong episode,
    with the true +28 in the tie set, unchosen.

    ⚠ THE OLD CHECK BUILT ONLY THE MIRROR ARRANGEMENT, where an anchor happens
    to BE the true offset. Both are built here, off the same capture, and the
    arrangement is what varies.

    ⭐ Episode numbering starts at 1, so "this part's lowest file is episode 1"
    is a hypothesis with a reason. And the placement is labelled `guess`, not
    `overlap`: an unbroken tie is a coin flip, and `hato/rank.py` tries it LAST.
    """
    shift, numbers = season["shift"], season["numbers"]
    haruhana = [f for f in FILES if f["name"].startswith(u"[Haruhana]")]
    if arrangement.startswith("the release"):
        files = [f for f in haruhana if reading[f["name"]].episode < numbers[0] + shift + 5]
        folder = numbers
    else:
        files = haruhana
        folder = numbers[1:-1]              # both ends interior: nothing to anchor to
    videos = stubs(tmp_path / "v", seasonal(folder))
    have = {reading[f["name"]].episode for f in files}
    assert len(folder) > 1 and have, (folder, have)

    a = episodes.align(files, videos, workdir=tmp_path / "w")
    part, = a.groups
    assert part.quality == "guess" and u"guess" in part.how, part
    assert shift in part.offsets, part                       # ⭐ the TRUE offset survives
    for video in videos:
        if video.episode + shift not in have:
            continue                        # the entry simply has no file for it
        offered_eps = [c.info.episode for c in a.per_video.get(str(video.path), ())]
        assert video.episode + shift in offered_eps, (video.name, offered_eps)


def test_an_offset_that_would_make_a_file_episode_minus_two_is_never_a_hypothesis(
        tmp_path, reading, season):
    """⛔ Rule 0. `29-40` against `2-9` anchored its LAST file to the folder's
    last, which calls its first file *"episode -2"*. Arithmetic, not a
    hypothesis -- and dropping it is free."""
    shift, numbers = season["shift"], season["numbers"]
    files = [f for f in FILES if f["name"].startswith(u"[Haruhana]")]
    lowest = min(reading[f["name"]].episode for f in files)
    videos = stubs(tmp_path / "v", seasonal(numbers[1:-1]))
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    part, = a.groups
    assert part.offsets and shift in part.offsets
    assert all(lowest - d >= episodes.EPISODE_FLOOR for d in part.offsets), part.offsets
    overlaps, _full = episodes._overlaps({e for e in range(lowest, lowest + 12)}, numbers[1:-1])
    assert overlaps and max(overlaps) <= lowest - episodes.EPISODE_FLOOR, sorted(overlaps)


def whole_season_releases(reading, numbers):
    """The capture's releases that carry the WHOLE season at its own numbers,
    each as a list of files. ⚠ Derived, never named: the checks that lean on
    two comparable releases must not pick them by hand."""
    by_group = {}
    for f in FILES:
        by_group.setdefault(tokens.release_group(f["name"]), []).append(f)
    out = [files for _g, files in sorted(by_group.items())
           if {reading[f["name"]].episode for f in files} == set(numbers)
           and {reading[f["name"]].season for f in files} != {None}]
    assert len(out) >= 2, [tokens.release_group(f[0]["name"]) for f in out]
    return out


def test_an_equal_length_release_holding_none_of_your_episodes_scores_range_1_00(
        tmp_path, reading, season):
    """⚠ A RECORDED HAZARD, measured before it was touched. `whole` is satisfied
    by ANY equal-length pair, so a release holding nothing for your folder scores
    `range 1.00`: the capture's own season-2 files for episodes 6-10, against a
    folder of 1-5, fit cleanly at +5 and every video is offered the wrong episode.

    ⛔ NOT CHANGED, on evidence. This IS what `02-data-model.md` specifies --
    *"a group whose range length matches the video count and aligns cleanly is a
    strong hypothesis"* -- and it is the same arithmetic that makes the capture's
    real +28 fit right. The obvious narrowing (a part and the videos that both
    read season 2 must sit at offset 0) is FALSIFIED by the capture itself: its
    Netflix release reads season 2 with ABSOLUTE numbers 29-38, and the rule
    would throw all ten of its files away.

    ⭐ WHAT WAS FIXED IS THE ASYMMETRY AROUND IT -- see the check below.
    """
    numbers = season["numbers"]
    half = len(numbers) // 2
    groups = whole_season_releases(reading, numbers)
    elsewhere = [f for f in groups[0] if reading[f["name"]].episode in numbers[half:]]
    videos = stubs(tmp_path / "v", seasonal(numbers[:half]))

    a = episodes.align(elsewhere, videos, workdir=tmp_path / "w")
    part, = a.groups
    assert (part.quality, part.coverage, part.offsets) == ("range", 1.0, (half,)), part
    for video in videos:
        offered_eps = {c.info.episode for c in a.per_video[str(video.path)]}
        assert offered_eps and video.episode not in offered_eps, (video.name, offered_eps)


def test_a_release_covering_your_folder_at_its_own_numbers_is_tried_first(
        tmp_path, reading, season):
    """⭐ THE ASYMMETRY THAT MADE THE HAZARD ABOVE BITE. A release covering your
    WHOLE folder at the number both sides already name used to be labelled
    `literal` -- *"no fit that stands out"* -- and it was reached only AFTER
    borrowing another release's offset. So it lost to any release that merely
    happened to be the same LENGTH as the folder.

    MEASURED over the capture, every equal-length (release window x folder
    window) arrangement: 1,200 of 1,680 put a wrong-episode candidate at #1, and
    where the two RULED key parts above this one (format, then language) tie it
    was 312 of 480. After: 720 of 1,680, and 0 of 480 -- the remainder is the
    `.ass`-first and single-language rulings, which sit above any fit.
    """
    numbers = season["numbers"]
    half = len(numbers) // 2
    groups = whole_season_releases(reading, numbers)
    wrong = [f for f in groups[0] if reading[f["name"]].episode in numbers[half:]]
    right = groups[1]
    # the two releases share both ruled key parts, so the fit is what decides
    assert ({(tokens.subtitle_format(f["name"]), tokens.language_class(f["name"])) for f in wrong}
            == {(tokens.subtitle_format(f["name"]), tokens.language_class(f["name"])) for f in right})
    videos = stubs(tmp_path / "v", seasonal(numbers[:half]))

    a = episodes.align(wrong + right, videos, workdir=tmp_path / "w")
    covering, = [g for g in a.groups if g.group == tokens.release_group(right[0]["name"])]
    assert covering.quality == "range" and covering.offsets == (0,), covering
    for video in videos:
        top = rank.rank(a.per_video[str(video.path)]).ordered[0].candidate
        assert top.info.episode == video.episode, (video.name, top.name)


def test_two_releases_can_pool_under_one_fingerprint_a_RECORDED_DEFECT(tmp_path, reading, season):
    """⚠ LATENT, NOT OBSERVED -- and left in place on evidence, not on hope.
    `_part_key` is (release group, season read), and an unbracketed name's group
    is its distributor/source fingerprint. Two releases carrying a SOURCE token
    and no distributor share one fingerprint and pool into one part.

    ⭐ MEASURED ON THE CAPTURE: its files make one fingerprint group per real
    release -- the bracketed prefixes, plus `WEBRip.Amazon.ja-jp[sdh]` and
    `WEBRip.Netflix.ja[cc]`, which the distributor token tells apart. There is no
    instance to fix, which is why nothing was changed.

    ⛔ AND THE OBVIOUS FIX IS NOT FREE: refusing to group on a source-only
    fingerprint sends every such name down the "aligned alone" path, where a
    single absolute-numbered file has no range of its own and lands only if some
    other release lends it an offset. So the constructed case is PINNED here,
    with its harm -- and this check goes red the day the rule changes, which is
    when the decision gets made again.
    """
    by_group = {}
    for f in FILES:
        by_group.setdefault(tokens.release_group(f["name"]), []).append(f)
    for group, files in by_group.items():
        stems = {f["name"].split(u".")[0] if not f["name"].startswith(u"[") else group
                 for f in files}
        assert len(stems) == 1, (group, stems)          # ⭐ no real instance

    def pooled(name):
        return (name.replace(u".Amazon.", u".").replace(u".Netflix.", u".")
                    .replace(u".ja-jp[sdh].", u".ja.").replace(u".ja[cc].", u".ja."))

    made = [file_dict(pooled(f["name"]), size=f["size"]) for f in FILES
            if not f["name"].startswith(u"[")]
    assert len({f["name"] for f in made}) == len(made)
    assert len({tokens.release_group(f["name"]) for f in made}) == 1     # ⚠ they POOL

    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(made, videos, workdir=tmp_path / "w")
    landed = {c.name for v in videos for c in a.per_video.get(str(v.path), ())}
    lost = [f["name"] for f in made if f["name"] not in landed]
    assert lost, "the pooling no longer drops files -- re-decide finding 8"
    # ⭐ the same twenty files, told apart as the capture really tells them apart
    apart = episodes.align([file_dict(f["name"], size=f["size"]) for f in FILES
                            if not f["name"].startswith(u"[")],
                           videos, workdir=tmp_path / "x")
    kept = {c.name for v in videos for c in apart.per_video.get(str(v.path), ())}
    assert len(kept) > len(landed), (len(kept), len(landed))


def test_entry_1_to_8_against_folder_1_to_12_offers_the_8_and_the_rest_are_not_found(tmp_path, reading):
    """06-edge-cases.md §2, the spec's own numbers: fetch the 8; the other 4 are
    NOT_FOUND -- not refused, not an error."""
    eight = [f for f in FILES if f["name"].startswith(u"[") and reading[f["name"]].season is not None
             and reading[f["name"]].episode <= 8]
    videos = stubs(tmp_path / "v", seasonal(range(1, 13)))
    a = episodes.align(eight, videos, workdir=tmp_path / "w")
    for video in videos:
        want = sorted(f["name"] for f in eight if reading[f["name"]].episode == video.episode)
        if video.episode <= 8:
            assert offered(a, video) == want and want, video.name
        else:
            assert str(video.path) in a.not_found and str(video.path) not in a.refused, video.name
            assert u"episode %d" % video.episode in a.not_found[str(video.path)]


def test_one_video_matches_literal_numbers_only_and_says_it_is_the_soft_spot(tmp_path, reading, season):
    number = season["numbers"][2]
    videos = stubs(tmp_path / "v", seasonal([number]))
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    literal = sorted(n for n, i in reading.items() if i.episode == number)
    got = a.per_video[str(videos[0].path)]
    assert literal and set(literal) <= set(offered(a, videos[0]))
    # ⚠ AMENDED 2026-09-17: this asserted `== {"literal"}` and was the check that went
    # red when `position` landed -- exactly what it should do. A lone video now ALSO
    # gets the weakest hypothesis from releases that number the season differently,
    # because refusing to offer anything is not one of Rule 1's options.
    assert {c.quality for c in got} <= {"literal", "position"}
    assert any(c.quality == "literal" for c in got)
    note, = [n for n in a.notes if u"soft spot" in n]
    assert u"matched literally" in note


def test_one_video_is_offered_by_position_when_its_number_is_numbered_differently(
        tmp_path, reading, season):
    u"""🚨 THE DEFECT THIS EXISTS FOR, MEASURED LIVE AGAINST THE REAL API 2026-09-17:
    `[SubsPlease] Sousou no Frieren S2 - 01` against entry 11446 was offered
    **nothing at all**, because every release numbers that season 29-38 and
    nothing matched the literal 1. One episode in a folder is the commonest shape
    there is, so the tool produced no subtitle for the ordinary case.

    ⭐ `00-INDEX.md` Rule 1 is the answer: hato proposes, the timing check
    disposes. The weakest honest hypothesis -- *your episode 1 is that release's
    first file* -- is offered, and tsubasa refuses it if the timing does not hold.
    """
    videos = stubs(tmp_path / "v", seasonal([1]))
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")

    by_position = [c for c in a.per_video[str(videos[0].path)] if c.quality == "position"]
    assert by_position, u"a lone video whose number is numbered differently got nothing"
    # ⭐ DERIVED FROM THE CAPTURE, never pinned to a number: episode 1 of the folder
    # must be offered each release's OWN FIRST file, whatever that release calls it.
    for c in by_position:
        name = c.file["name"]
        key = (tokens.release_group(name), reading[name].season)
        mine = [i.episode for n, i in reading.items()
                if (tokens.release_group(n), i.season) == key and i.episode is not None]
        assert reading[name].episode == min(mine), (name, reading[name].episode, min(mine))
        # the mapping it claims is the mapping it applied
        assert reading[name].episode == videos[0].episode + c.offset


def test_a_number_that_cannot_be_a_position_is_offered_nothing(tmp_path, season):
    u"""⛔ THE GUARD, and it is what keeps the hypothesis above honest. Measured in
    the same live run: `[SubsPlease] One Piece - 1121` against releases of a few
    dozen files each proposes NOTHING, because 1121 is not a position inside 33
    files. Without this, every lone video would be handed some release's last file.
    """
    videos = stubs(tmp_path / "v", seasonal([9999]))
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    assert not a.per_video.get(str(videos[0].path)), \
        u"9999 is not a position in any release of this entry"


def test_one_file_against_one_video_proves_no_offset(tmp_path, reading, season):
    """A single pair fits exactly one offset -- that is arithmetic, not evidence."""
    shift = season["shift"]
    number = season["numbers"][2]
    one = [f for f in FILES if f["name"].startswith(u"[Haruhana]")
           and reading[f["name"]].episode == number + shift]
    videos = stubs(tmp_path / "v", seasonal([number]))
    a = episodes.align(one, videos, workdir=tmp_path / "w")
    assert offered(a, videos[0]) == [] and str(videos[0].path) in a.not_found


def releases_by_numbering(reading):
    """-> {"names a season": [file], "absolute": [file]}, off the capture's own
    reading. ⚠ Never a release picked by NAME: the old check selected
    `[NanakoRaws]`, the ONE release in the capture carrying an explicit season,
    so the fixture held the counter-example and the selector removed it."""
    out = {}
    for f in FILES:
        group = tokens.release_group(f["name"])
        out.setdefault(group, []).append(f)
    kinds = {"names a season": [], "absolute": []}
    for group, files in out.items():
        seasons = {reading[f["name"]].season for f in files}
        if seasons == {None}:
            kinds["absolute"].append(files)
        elif None not in seasons:
            kinds["names a season"].append(files)
    assert kinds["names a season"] and kinds["absolute"], kinds
    return dict((k, v[0]) for k, v in kinds.items())


@pytest.mark.parametrize("numbering", ["names a season", "absolute"])
def test_no_release_is_fitted_to_two_different_seasons_of_videos(tmp_path, reading, numbering):
    """🚨 A PART THAT READS NO SEASON IS COMPATIBLE WITH EVERY PARTITION, and
    every one of them used to be FITTED. Measured 2026-09-17: all ten season-1
    videos were offered the season-2 subtitles at offset +28, `range` quality,
    coverage 1.00 -- the highest confidence class there is. Reachable through
    `hato align --explain` and `hato rank --folder`; the fetch loop escapes only
    because it keys shows on (title, season, year) -- a guard in another module
    that nothing here pinned.

    ⭐ A release carries each episode once, so a part is placed in AT MOST ONE
    partition -- and in NONE when two fit it equally well, because there is
    nothing to tell them apart and one file cannot be two episodes.
    """
    files = releases_by_numbering(reading)[numbering]
    numbers = sorted({reading[f["name"]].episode for f in files})
    s1_numbers = [1, 2, 3]
    videos = stubs(tmp_path / "v",
                   [u"[SubsPlease] Sousou no Frieren S1 - %02d (1080p) [ABCD1234].mkv" % n
                    for n in s1_numbers] + seasonal(s1_numbers))
    assert {v.season for v in videos} == {1, 2}
    a = episodes.align(files, videos, workdir=tmp_path / "w")

    for video in videos:
        if video.season == 1:
            assert offered(a, video) == [] and str(video.path) in a.not_found, video.name
    if numbering == "names a season":
        for video in [v for v in videos if v.season == 2]:
            want = sorted(f["name"] for f in files
                          if reading[f["name"]].episode == video.episode)
            assert offered(a, video) == want and want, video.name
        assert [g.against for g in a.groups] == [u"S2 videos"], a.groups
        assert u"season 2 -> S2 videos" in episodes.explain(a)
        return
    # ⭐ The counter-example the old selector removed: an absolute range fits BOTH
    # seasons of a folder that numbers them alike, so it is offered to neither.
    assert numbers[0] > max(s1_numbers), numbers          # the harm is real: it fits at an offset
    for video in videos:
        assert offered(a, video) == [], (video.name, offered(a, video))
    note, = [n for n in a.notes if u"one release cannot be two seasons at once" in n]
    assert u"S1 videos and S2 videos" in note, note
    assert u"placed nowhere" in episodes.explain(a)


def test_a_long_run_is_fitted_on_its_structural_offsets_only(tmp_path):
    """⭐ Rule 4 (spec/00-INDEX.md): a full fit costs files x videos. Past the budget
    only the literal, first-to-first, last-to-last and episode-1 offsets are tried --
    and for a long run numbered alike, or shifted as a whole, the answer is unchanged.

    ⚠ THE REAL CONSTANT IS EXERCISED HERE, in arithmetic; `align` itself is driven
    past the budget by the check below, which is what asserts the NOTE and the
    placement."""
    n = int(episodes.FULL_FIT_BUDGET ** 0.5) + 1
    folder = list(range(1, n + 1))
    overlaps, full = episodes._overlaps(set(folder), folder)
    assert full is False and dict(overlaps) == {0: n}
    overlaps, full = episodes._overlaps({e + 28 for e in folder}, folder)
    assert full is False and max(overlaps, key=overlaps.get) == 28 and overlaps[28] == n
    small = list(range(1, 11))
    overlaps, full = episodes._overlaps(set(small), small)
    # ⛔ Rule 0 cuts the impossible half: the lowest file is episode 1, so an
    # offset above 1 would call it episode 0 or less.
    assert full is True and sorted(overlaps) == list(range(-9, 2))


def test_align_past_the_budget_says_so_and_still_places_every_release(
        tmp_path, reading, season, monkeypatch):
    """🚨 THE OLD CHECK CALLED `_overlaps` DIRECTLY. It proved arithmetic and
    never ran `align` past the budget at all -- so nothing asserted that the
    note is emitted, or that placement past it stays correct.

    ⚠ THE BUDGET IS WHAT VARIES, derived from the capture rather than hardcoded:
    it is lowered to one below the real product of this entry's parts and this
    folder, which is the smallest change that puts the SAME capture on the other
    side of the gate.
    """
    numbers = season["numbers"]
    by_group = {}
    for f in FILES:
        by_group.setdefault(tokens.release_group(f["name"]), []).append(f)
    # the releases that cover the whole season under ONE numbering -- the ones
    # whose true offset is a structural one, so the budget costs them nothing.
    # ⚠ A release whose names read TWO numberings (the capture's Amazon WEBRip)
    # is two small parts, each well under any budget, and would measure nothing.
    whole = [f for files in by_group.values() for f in files
             if len({reading[g["name"]].episode for g in files}) == len(numbers)
             and len({reading[g["name"]].season for g in files}) == 1]
    assert len(whole) > len(numbers), len(whole)
    videos = stubs(tmp_path / "v", seasonal(numbers))
    inside = episodes.align(whole, videos, workdir=tmp_path / "a")
    assert not [n for n in inside.notes if u"full-fit budget" in n], inside.notes

    biggest = max(len(g.episodes) for g in inside.groups)
    monkeypatch.setattr(episodes, "FULL_FIT_BUDGET", biggest * len(numbers) - 1)
    past = episodes.align(whole, videos, workdir=tmp_path / "b")

    notes = [n for n in past.notes if u"full-fit budget" in n]
    assert len(notes) == len(past.groups) and u"episode-1 offsets" in notes[0], notes
    for video in videos:
        want = sorted(f["name"] for f in whole
                      if same_episode(reading[f["name"]].episode, video.episode, season["shift"]))
        assert offered(past, video) == want and want, video.name
    assert offered(past, videos[0]) == offered(inside, videos[0])


# ---------------------------------------------------------------------------
# never range-aligned
# ---------------------------------------------------------------------------

SP1_FILE = u"[Haruhana] Sousou no Frieren - SP1 [WebRip][HEVC-10bit 1080p][JPN].ass"
SP1_VIDEO = u"[SubsPlease] Sousou no Frieren - SP1 (1080p) [ABCD1234].mkv"


def test_a_special_file_is_offered_only_to_the_same_special_literally(tmp_path, season):
    info, = names.read_names([SP1_FILE], tmp_path / "r")
    assert info.episode == 1, "the harm: tsubasa reads SP1 as episode 1"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]) + [SP1_VIDEO])
    a = episodes.align(FILES + [file_dict(SP1_FILE)], videos, workdir=tmp_path / "w")
    special, = [v for v in videos if v.name == SP1_VIDEO]
    for video in videos:
        if video is special:
            assert offered(a, video) == [SP1_FILE]
            assert [(c.quality, c.offset) for c in a.per_video[str(video.path)]] == [("literal", None)]
        else:
            assert SP1_FILE not in offered(a, video), video.name


def test_a_special_video_with_no_literal_match_is_refused_not_range_aligned(tmp_path, season):
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]) + [SP1_VIDEO])
    special, = [v for v in videos if v.name == SP1_VIDEO]
    assert special.episode == 1, "the harm: tsubasa reads the SP1 video as episode 1"
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    assert offered(a, special) == [] and u"special" in a.refused.get(str(special.path), u"")


def test_a_half_episode_is_matched_literally_and_never_rounded(tmp_path):
    half = u"[Haruhana] Sousou no Frieren - 13.5 [WebRip][HEVC-10bit 1080p][JPN].ass"
    files = [file_dict(u"[Haruhana] Sousou no Frieren - %02d [WebRip][HEVC-10bit 1080p][JPN].ass" % n)
             for n in (12, 13, 14)] + [file_dict(half)]
    info, = names.read_names([half], tmp_path / "r")
    assert info.episode == 13.5
    videos = stubs(tmp_path / "v", seasonal([12, 13, 14]) + [u"[SubsPlease] Sousou no Frieren S2 - 13.5 (1080p) [ABCD1234].mkv"])
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    for video in videos:
        assert (half in offered(a, video)) == (video.episode == 13.5), video.name


def test_a_half_episode_video_with_no_literal_file_is_not_found_never_rounded(tmp_path):
    files = [file_dict(u"[Haruhana] Sousou no Frieren - %02d [WebRip][HEVC-10bit 1080p][JPN].ass" % n)
             for n in (12, 13, 14)]
    videos = stubs(tmp_path / "v", seasonal([12, 13, 14]) + [u"[SubsPlease] Sousou no Frieren S2 - 13.5 (1080p) [ABCD1234].mkv"])
    half, = [v for v in videos if v.episode == 13.5]
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    assert offered(a, half) == [] and u"never rounded" in a.not_found[str(half.path)]


def test_a_v2_file_is_offered_for_its_episode_beside_the_original(tmp_path, reading, season):
    shift = season["shift"]
    number = season["numbers"][2]
    original = [n for n in reading if n.startswith(u"[Haruhana]") and reading[n].episode == number + shift
                and u"[JPN]" in n and u"CHS" not in n][0]
    v2 = original.replace(u" - %d " % (number + shift), u" - %dv2 " % (number + shift))
    assert v2 != original and tokens.version(v2) == 2
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(FILES + [file_dict(v2)], videos, workdir=tmp_path / "w")
    for video in videos:
        assert (v2 in offered(a, video)) == (video.episode == number), video.name
        assert (original in offered(a, video)) == (video.episode == number), video.name


# ---------------------------------------------------------------------------
# refused, never guessed
# ---------------------------------------------------------------------------

def test_a_file_holding_two_episodes_is_offered_to_no_video(tmp_path, season):
    two = u"[Haruhana] Sousou no Frieren - 29-30 [WebRip][HEVC-10bit 1080p][JPN].ass"
    info, = names.read_names([two], tmp_path / "r")
    assert info.episode == 29, "the harm: tsubasa reads the first number and says nothing"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(FILES + [file_dict(two)], videos, workdir=tmp_path / "w")
    assert [v.name for v in videos if two in offered(a, v)] == []
    assert any(two in n and u"refused" in n for n in a.notes), a.notes


def test_a_video_holding_two_episodes_is_refused(tmp_path, season):
    two = u"[SubsPlease] Sousou no Frieren S2 - 11-12 (1080p) [ABCD1234].mkv"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]) + [two])
    video, = [v for v in videos if v.name == two]
    assert video.episode == 11, "the harm: tsubasa reads the video as episode 11"
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    assert str(video.path) not in a.per_video and u"11-12" in a.refused[str(video.path)]


def test_a_skipped_file_and_an_archive_are_offered_to_no_video(tmp_path, season):
    ncop = u"[Haruhana] Sousou no Frieren - NCOP1 [WebRip][HEVC-10bit 1080p][JPN].ass"
    archive = u"[Haruhana] Sousou no Frieren - 31 [WebRip][HEVC-10bit 1080p][JPN].7z"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(FILES + [file_dict(ncop), file_dict(archive)], videos, workdir=tmp_path / "w")
    assert [v.name for v in videos if ncop in offered(a, v) or archive in offered(a, v)] == []
    # ...and each is left out for ITS reason, which is what a person reads
    assert any(ncop in n and u"tsubasa skips" in n for n in a.notes), a.notes
    # ⚠ AMENDED 2026-09-17: this asserted the note said "RUNBOOK 3c", which promised
    # archives get opened "and their members aligned then" -- never true of any run,
    # and doubly wrong since Sonic ruled archives OFF by default. The check now asks
    # what a PERSON reads: the file is named, and the sentence names the flag.
    assert any(archive in n and u"--archives" in n for n in a.notes), a.notes


# ---------------------------------------------------------------------------
# the movie path
# ---------------------------------------------------------------------------

FILM = u"Kimi no Na wa (2016).mkv"


def test_a_movie_entry_offers_every_SUBTITLE_to_the_film(tmp_path):
    u"""🚨 Every SUBTITLE, as the episode path always said -- not every file. The
    recorded entry's real `.sup.7z` was offered to the film, downloaded unopened,
    handed to tsubasa as a subtitle and recorded as a 0% timing refusal
    (ADVERSARY 2026-09-23 #10). It is named in a note instead, with the flag."""
    videos = stubs(tmp_path / "v", [FILM])
    a = episodes.align(MOVIE_FILES, videos, workdir=tmp_path / "w", movie=True)
    packs = [f["name"] for f in MOVIE_FILES if archives.is_archive(f["name"])]
    assert packs, u"the recorded movie entry is expected to carry an archive"
    assert offered(a, videos[0]) == sorted(f["name"] for f in MOVIE_FILES
                                           if f["name"] not in packs)
    assert {(c.quality, c.offset) for c in a.per_video[str(videos[0].path)]} == {("movie", None)}
    assert any(packs[0] in n and u"--archives" in n for n in a.notes), a.notes


def test_a_movie_entry_offering_only_an_archive_offers_the_film_nothing(tmp_path):
    u"""⛔ An archive is never "the other format" for a film (#10): with nothing
    but the `.7z`, the film is NOT offered it, and the reason says why."""
    videos = stubs(tmp_path / "v", [FILM])
    only = [f for f in MOVIE_FILES if archives.is_archive(f["name"])]
    a = episodes.align(only, videos, workdir=tmp_path / "w", movie=True)
    assert offered(a, videos[0]) == []
    said = a.not_found[str(videos[0].path)]
    assert u"no subtitle file" in said and u"archive" in said, said


def test_without_the_movie_flag_a_film_is_refused_not_guessed(tmp_path):
    videos = stubs(tmp_path / "v", [FILM])
    assert videos[0].episode is None
    a = episodes.align(MOVIE_FILES, videos, workdir=tmp_path / "w")
    assert offered(a, videos[0]) == [] and u"movie path" in a.refused[str(videos[0].path)]


# ---------------------------------------------------------------------------
# the work done, and the rendering
# ---------------------------------------------------------------------------

def test_each_distinct_name_is_read_once(tmp_path, season, monkeypatch):
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    calls = []
    real = episodes.read_names

    def spy(listed, workdir, group_of=None):
        calls.append(list(listed))
        return real(listed, workdir, group_of=group_of)

    monkeypatch.setattr(episodes, "read_names", spy)
    once = episodes.align(FILES, videos, workdir=tmp_path / "a")
    twice = episodes.align(FILES + FILES[: len(FILES) // 4], videos, workdir=tmp_path / "b")
    assert calls[1] == calls[0] == [f["name"] for f in FILES]
    assert dict((p, sorted(c.name for c in cs)) for p, cs in twice.per_video.items()) == \
        dict((p, sorted(c.name for c in cs)) for p, cs in once.per_video.items())


@pytest.mark.parametrize("numbering", ["seasonal", "absolute"])
def test_explain_shows_every_release_its_range_and_offset_and_every_video_mapping(
        tmp_path, reading, season, numbering):
    shift = season["shift"]
    numbers = season["numbers"] if numbering == "seasonal" else [n + shift for n in season["numbers"]]
    videos = stubs(tmp_path / "v", (seasonal if numbering == "seasonal" else absolute)(numbers))
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    text = episodes.explain(a)
    lines = text.splitlines()
    for g in a.groups:
        row = [l for l in lines if l.lstrip().startswith(g.group) and g.numbering in l]
        assert row and any(("%+d" % d if d else "0") in row[0] for d in g.offsets), (g, row)
    for video in videos:
        head = [l for l in lines if video.name in l]
        count = len(a.per_video[str(video.path)])
        assert head and head[0].rstrip().endswith(u"-- %d files" % count), head
    assert u"REFUSED" not in text and u"NOT FOUND" not in text
    assert all(l == l.rstrip() for l in lines)


def _run_align(argv):
    parser = argparse.ArgumentParser(prog="hato align")
    align_command.register(parser)
    return align_command.run(parser.parse_args(argv))


def test_hato_align_without_a_recorded_list_says_the_live_path_waits_for_2c(tmp_path, capsys):
    tmp_path.joinpath("v").mkdir()
    assert _run_align(["--explain", str(tmp_path / "v"), "11446"]) == 2
    err = capsys.readouterr().err
    assert u"RUNBOOK 2c" in err and u"--files" in err and len(err.strip().splitlines()) == 1


def test_hato_align_prints_exactly_the_explanation_of_the_recorded_capture(tmp_path, capsys, season):
    """The wrapper is what a person reads, so it is held to the library: its body
    must be explain() of the same alignment, line for line."""
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    assert _run_align(["--explain", str(tmp_path / "v"), "11446",
                       "--files", str(API / "entries_11446_files.json")]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert u"entry 11446" in lines[0] and str(tmp_path / "v") in lines[0]
    direct = episodes.explain(episodes.align(FILES, videos, workdir=tmp_path / "w"))
    assert lines[1:] == direct.splitlines()
    assert any(u"+%d" % season["shift"] in l for l in lines)


def test_hato_align_refuses_a_recording_of_another_entry(tmp_path, capsys):
    tmp_path.joinpath("v").mkdir()
    assert _run_align(["--explain", str(tmp_path / "v"), "440",
                       "--files", str(API / "entries_11446_files.json")]) == 1
    assert u"entry 11446, not entry 440" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# ⭐ RUNBOOK 8f -- the newest episode on offer, for *probably not out yet*
# ---------------------------------------------------------------------------
# The shapes are Sonic's own history (state DB, 2026-09-19..21): which release
# names, which numbering, which episodes his folder held when each ran.

def nanako(show, season, numbers):
    return [file_dict(u"[NanakoRaws] %s S%02dE%02d (TV 1080p HEVC AAC).ass" % (show, season, n))
            for n in numbers]


def amazon(title, season, numbers):
    return [file_dict(u"%s.S%02dE%02d.第%d話.WEBRip.Amazon.ja-jp[sdh].srt" % (title, season, n, n))
            for n in numbers]


def subsplease(show, season, numbers):
    return [u"[SubsPlease] %s S%d - %02d (1080p) [ABCD1234].mkv" % (show, season, n)
            for n in numbers]


def newest_by_episode(tmp_path, files, video_names):
    videos = stubs(tmp_path / "v", video_names)
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    return a, videos, dict((v.episode, episodes.newest_offered(a, v)) for v in videos)


def test_sonics_iruma_s4_23_the_fit_slides_and_the_newest_offered_is_still_22(tmp_path):
    """🚨 THE CASE 8f EXISTS FOR, AND WHY ITS FORMULA COULD NOT BE THE FIT'S.

    2026-09-20: Iruma-kun S4 23 was offered NanakoRaws E22 and Amazon E20 and
    E03, and timing refused all three. The fit takes the offset where MOST
    videos land, and with the folder one episode ahead of every release, a shift
    of -1 lands three videos where the true 0 lands two. Read off that placement
    the release "offers 23" and the highlight could never fire.
    """
    files = (nanako(u"Mairimashita! Iruma-kun", 4, range(1, 23))
             + amazon(u"魔入りました！入間くん", 4, range(1, 21)))
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Mairimashita! Iruma-kun", 4, (21, 22, 23)))
    v23 = [v for v in videos if v.episode == 23][0]
    slid = [n for n in offered(a, v23) if u"E23" not in n]
    assert slid, (u"the control: the fit did not slide here, so this check proves nothing "
                  u"-- offered to 23: %s" % offered(a, v23))
    assert newest == {21: 22, 22: 22, 23: 22}, (
        u"the newest episode on offer is 22 -- read off the slid placement it says %r" % newest)


def test_sonics_honzuki_s4_22_one_past_the_newest(tmp_path):
    a, videos, newest = newest_by_episode(
        tmp_path, nanako(u"Honzuki no Gekokujou", 4, range(1, 22)),
        subsplease(u"Honzuki no Gekokujou", 4, (20, 21, 22)))
    assert newest[22] == 21, newest


def test_sonics_tsuihou_12_and_tetsunabe_09_are_on_offer_so_nothing_is_probably_late(tmp_path):
    u"""The two that must NOT highlight: their episode was offered, and refused."""
    shincaps = [file_dict(u"[shincaps] Tsuihou Sareta Tensei Juukishi wa Game Chishiki de Musou "
                          u"Suru - %02d (AT-X 1440x1080 MPEG2 AAC).ass" % n) for n in range(1, 12)]
    a, videos, newest = newest_by_episode(
        tmp_path / "tsuihou",
        nanako(u"Tsuihou Sareta Tensei Juukishi wa Game Chishiki de Musou Suru", 1, range(1, 13))
        + shincaps,
        [u"[SubsPlease] Tsuihou sareta Tensei Juukishi wa Game Chishiki de Musou suru - %02d "
         u"(1080p) [ABCD1234].mkv" % n for n in (11, 12)])
    assert newest[12] is not None and newest[12] >= 12, newest
    a, videos, newest = newest_by_episode(
        tmp_path / "tetsunabe", nanako(u"Tetsunabe no Jan!", 1, range(1, 12)),
        [u"[SubsPlease] Tetsunabe no Jan! - %02d (1080p) [ABCD1234].mkv" % n
         for n in range(2, 12)])
    assert newest[9] is not None and newest[9] >= 9, newest


def test_newest_offered_across_seasonal_and_absolute_releases_of_one_entry(
        tmp_path, reading, season):
    """06-edge-cases.md §2 on the REAL capture: seasonal releases (S2 - 01..) and
    absolute ones (- 29..) in one entry, a folder one episode past the season."""
    last = season["numbers"][-1]
    a, videos, newest = newest_by_episode(tmp_path, FILES,
                                          seasonal(season["numbers"] + [last + 1]))
    assert newest[last + 1] == last, (
        u"one past the season must read the season's last episode, %d: %r" % (last, newest))
    assert set(newest.values()) == {last}, newest


def test_a_release_placed_nowhere_counts_for_nothing(tmp_path, reading, season):
    u"""⛔ A lone file far ahead, same season, placed nowhere -- its number is not
    evidence of anything, and must not hide *probably not out yet*."""
    last = season["numbers"][-1]
    stray = file_dict(u"[Stray] Sousou no Frieren S2 - %02d (1080p).ass" % (last + 30))
    a, videos, newest = newest_by_episode(tmp_path, FILES + [stray],
                                          seasonal(season["numbers"] + [last + 1]))
    placed = [s for s in a.groups if s.group == u"Stray"]
    assert placed and not placed[0].offsets, (
        u"the control: the stray release was placed after all -- %r" % placed)
    assert newest[last + 1] == last, newest


def test_a_release_fitted_against_another_season_says_nothing_about_this_one(tmp_path):
    files = nanako(u"Honzuki no Gekokujou", 3, range(1, 13))
    a, videos, newest = newest_by_episode(
        tmp_path, files,
        subsplease(u"Honzuki no Gekokujou", 3, (11, 12)) + subsplease(u"Honzuki no Gekokujou", 4, (1, 2)))
    assert newest[12] == 12 and newest[1] is None and newest[2] is None, newest


def test_an_absolute_release_fitted_against_another_season_says_nothing_about_this_one(tmp_path):
    u"""The same rule for a release numbered ANOTHER way. An absolute release
    fitted against season 3 is season 3 in the whole-show count; read against
    season 4's videos it said the newest on offer was 12, for a season jimaku
    has no file of. ⚠ The seasonal check above cannot see this any more: a
    season-3 release can never be read as the gap to season 4 (`_across_the_gap`),
    so only an absolute one still needs the partition to keep it out."""
    files = [file_dict(u"[Erai-raws] Honzuki no Gekokujou - %02d [1080p].ass" % n)
             for n in range(25, 37)]
    videos = stubs(tmp_path / "v", subsplease(u"Honzuki no Gekokujou", 3, range(1, 13))
                   + subsplease(u"Honzuki no Gekokujou", 4, (1, 2)))
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    placed = [s for s in a.groups if s.season is None]
    assert placed and placed[0].partition == 3 and placed[0].offsets == (24,), (
        u"the control: the absolute release is not fitted to season 3 at +24 -- %r" % a.groups)
    newest = dict(((v.season, v.episode), episodes.newest_offered(a, v)) for v in videos)
    assert newest[(3, 12)] == 12, u"the control: it speaks for season 3 -- %r" % newest
    assert newest[(4, 1)] is None and newest[(4, 2)] is None, (
        u"a release fitted against season 3 spoke for season 4: %r" % newest)


def test_a_release_numbering_on_through_the_season_is_read_through_its_offset(tmp_path):
    u"""The one same-season case where the offset IS the reading: a release that
    numbers the season's second cour 13-24 against a folder numbered 1-12. ⚠ And
    one video further on, the fit can only GUESS between two upward shifts --
    which proves no number, so nothing is said."""
    files = nanako(u"Kusuriya no Hitorigoto", 2, range(13, 25))
    a, videos, newest = newest_by_episode(
        tmp_path / "cour", files, subsplease(u"Kusuriya no Hitorigoto", 2, range(1, 13)))
    placed = [s for s in a.groups if s.group == u"NanakoRaws"]
    assert placed and placed[0].offsets == (12,), (
        u"the control: the release was not placed at +12 -- %r" % placed)
    assert set(newest.values()) == {12}, newest
    a, videos, newest = newest_by_episode(
        tmp_path / "guess", files, subsplease(u"Kusuriya no Hitorigoto", 2, range(1, 14)))
    assert newest[13] is None, (
        u"a guess between upward shifts said a newest episode: %r" % newest)


def test_an_absolute_release_one_longer_than_the_season_may_hold_the_episode(tmp_path):
    u"""ADVERSARY 2026-09-22 F4a. Sonic's own Iruma folder and releases -- plus ONE
    absolute release numbering season 4 from 66, that DOES carry episode 23 (88).
    It is guessed between two offsets, so it proves no number; but it is the
    season in the whole-show count and one episode LONGER than the newest the
    others prove, so *probably not out yet* would be said over an episode that
    is out. ⚠ The control: Sonic's shape alone still says 22."""
    files = (nanako(u"Mairimashita! Iruma-kun", 4, range(1, 23))
             + [file_dict(u"[Erai-raws] Mairimashita! Iruma-kun - %02d [1080p].ass" % n)
                for n in range(66, 89)])
    videos = subsplease(u"Mairimashita! Iruma-kun", 4, (21, 22, 23))
    _a, _v, alone = newest_by_episode(tmp_path / "alone", files[:22], videos)
    assert alone[23] == 22, u"the control: without the absolute release, 22 -- %r" % alone
    a, found, newest = newest_by_episode(tmp_path / "both", files, videos)
    v23 = [v for v in found if v.episode == 23][0]
    assert [n for n in offered(a, v23) if u"- 88 " in n], (
        u"the control: E23 (88) is not offered at all: %s" % offered(a, v23))
    assert newest[23] is None or newest[23] >= 23, (
        u"episode 23 is on offer (88) and the newest said is %r -- the window would say "
        u"*probably not out yet*" % newest[23])


def test_an_absolute_folder_one_ahead_of_an_absolute_release_reads_its_own_number(tmp_path):
    u"""ADVERSARY 2026-09-22 F4b. The D11 slide in an ABSOLUTE folder: 1110-1122
    against a release of 1109-1121. Read as ANOTHER numbering, the slid placement
    said the release offers 1122 -- which no file anywhere is."""
    files = [file_dict(u"[NanakoRaws] One Piece - %d (TV 1080p HEVC AAC).ass" % n)
             for n in range(1109, 1122)]
    a, videos, newest = newest_by_episode(
        tmp_path, files,
        [u"[SubsPlease] One Piece - %d (1080p) [ABCD1234].mkv" % n for n in range(1110, 1123)])
    assert newest[1122] == 1121, (
        u"the newest file is 1121, and 1122 is one past it: %r" % newest[1122])


def test_a_whole_show_absolute_release_says_nothing_about_this_season(tmp_path):
    u"""⚠ The OTHER side of F4a's rule. An absolute release a little longer than
    the season is that season further on; one numbering the whole show (1-88
    against a season of 22) is not, and must not silence *probably not out
    yet*. 🚨 Its fit is a `range` -- 21-23 lands on the folder's 21-23 at its
    literal number -- and that is the numbers coinciding: between the absolute
    count and season 4 the offset is the episodes before it, never 0."""
    files = (nanako(u"Mairimashita! Iruma-kun", 4, range(1, 23))
             + [file_dict(u"[Erai-raws] Mairimashita! Iruma-kun - %02d [1080p].ass" % n)
                for n in range(1, 89)])
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Mairimashita! Iruma-kun", 4, (21, 22, 23)))
    whole = [s for s in a.groups if s.season is None and s.partition == 4]
    assert whole and whole[0].quality == "range" and whole[0].offsets == (0,), (
        u"the control: the whole-show release is not placed at its literal number as a "
        u"`range` -- the coincidence this check exists for is not here: %r" % a.groups)
    assert newest[23] == 22, (
        u"a release numbering the WHOLE show hid *probably not out yet*: %r" % newest[23])


def test_an_absolute_release_numbered_below_the_season_says_nothing_about_it(tmp_path):
    u"""The same rule the other way round: an absolute release whose numbers sit
    BELOW the season's is a whole-range fit at a NEGATIVE offset -- 1-3 on a
    season-4 folder's 21-23 -- and the absolute count numbers a later season
    HIGHER, never lower. Read as the gap between them, it said 23 is on offer."""
    files = (nanako(u"Mairimashita! Iruma-kun", 4, range(1, 23))
             + [file_dict(u"[Erai-raws] Mairimashita! Iruma-kun - %02d [1080p].ass" % n)
                for n in range(1, 4)])
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Mairimashita! Iruma-kun", 4, (21, 22, 23)))
    low = [s for s in a.groups if s.season is None and s.partition == 4]
    assert low and low[0].quality in episodes.PROVEN and low[0].offsets == (-20,), (
        u"the control: the absolute release is not a range fit at -20 -- %r" % a.groups)
    assert newest[23] == 22, (
        u"an absolute release below the season was read as its gap: newest %r" % newest[23])


def test_a_single_guessed_offset_of_another_numbering_proves_no_newest_episode(tmp_path):
    u"""F4d where it is REACHABLE -- measured by the M8zd builder, after the
    orchestrator had argued it was not: one stray file far outside an absolute
    release's range pushes one of the three anchors out of the tie, and what is
    left is a GUESS at a single offset. Read as proof, it said the newest on
    offer was 25, in a season whose releases stop at 10, and *probably not out
    yet* went silent over an episode nobody has."""
    files = (nanako(u"Mairimashita! Iruma-kun", 4, range(1, 11))
             + [file_dict(u"[Erai-raws] Mairimashita! Iruma-kun - %02d [1080p].ass" % n)
                for n in list(range(66, 76)) + [90]])
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Mairimashita! Iruma-kun", 4, range(1, 12)))
    guessed = [s for s in a.groups if s.season is None]
    assert guessed and guessed[0].quality == "guess" and guessed[0].offsets == (65,), (
        u"the control: the absolute release is not a guess at ONE offset -- %r" % a.groups)
    assert newest[11] == 10, (
        u"a guess of another numbering was read as proof: newest %r for S4 11" % newest[11])


def test_a_first_season_folder_reads_an_absolute_release_at_its_own_number(tmp_path):
    u"""Season 1 and the absolute count are ONE count, from the other side too:
    an absolute release against a season-1 folder one episode ahead of it is
    the slide, read at its own number -- 11 is on offer, 12 probably is not. Read
    as another count, its two guessed offsets proved nothing and the late
    episode was never said."""
    files = [file_dict(u"[Erai-raws] Tetsunabe no Jan! - %02d [1080p].ass" % n)
             for n in range(1, 12)]
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Tetsunabe no Jan!", 1, (11, 12)))
    placed = [s for s in a.groups if s.season is None]
    assert placed and len(placed[0].offsets) == 2, (
        u"the control: the absolute release is not guessed between two offsets -- %r" % a.groups)
    assert newest[12] == 11, (
        u"a season-1 folder read an absolute release as another count: %r" % newest)


def test_a_later_seasons_release_is_read_across_the_gap_into_an_absolute_folder(tmp_path):
    u"""The gap the other way: a folder numbered in the absolute count (13-24 is
    season 2 of a 12-episode show) and a release numbering season 2 from 1. Its
    whole range lands at -12, and -- the season's own release numbering the
    absolute count LOWER -- that offset IS the gap: the newest on offer is 24."""
    files = nanako(u"Honzuki no Gekokujou", 2, range(1, 13))
    a, videos, newest = newest_by_episode(
        tmp_path, files, [u"[SubsPlease] Honzuki no Gekokujou - %02d (1080p) [ABCD1234].mkv" % n
                          for n in range(13, 25)])
    placed = [s for s in a.groups if s.season == 2]
    assert placed and placed[0].offsets == (-12,), (
        u"the control: the season-2 release is not placed at -12 -- %r" % a.groups)
    assert set(newest.values()) == {24}, (
        u"a later season's release was not read across the gap: %r" % newest)


def test_a_literal_guess_of_another_numbering_proves_no_newest_episode(tmp_path):
    u"""ADVERSARY 2026-09-22 F4d. One video, S4 23, and a release numbering the
    whole show 1-87. With one video there is no range to fit, so the release is
    placed on its LITERAL number -- a guess -- and reading that guess as a
    numbering said the newest on offer is 87, in a season of 22."""
    files = [file_dict(u"[Erai-raws] Mairimashita! Iruma-kun - %02d [1080p].ass" % n)
             for n in range(1, 88)]
    a, videos, newest = newest_by_episode(
        tmp_path, files, subsplease(u"Mairimashita! Iruma-kun", 4, (23,)))
    placed = [s for s in a.groups if s.offsets]
    assert placed and all(s.quality not in episodes.PROVEN for s in placed), (
        u"the control: the release was placed by a real range fit -- %r" % a.groups)
    assert newest[23] is None, (
        u"a guess was read as a numbering: newest %r for S4 23" % newest[23])


def test_a_film_and_an_unnumbered_video_have_no_newest(tmp_path):
    class Film(object):
        episode, season = None, None
    a = episodes.align([], [], workdir=tmp_path / "w", movie=True)
    assert episodes.newest_offered(a, Film()) is None
