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
    # ⚠ AMENDED v2 (2026-10-11): by the number a file is ALIGNED by -- `S02E06.第34話`
    # is season 2's 6 since tsubasa reads both numbers, so it is no longer "the other way".
    # ⚠ AMENDED 16z (A4): pass 0's floor is per LANDING file now, so the names' stated +28 is
    # no longer dropped because the pooled part also holds 01-10. It places every ABSOLUTE
    # file where it belongs and the SEASONAL ones are lost -- still one numbering lost whole,
    # nothing placed wrong, and what is kept is kept by the statement, never by the fit.
    lost = sorted(n for n, i in reading.items() if episodes._numbered(i)[1] in season["numbers"])
    still = sorted(c.name for v in videos for c in pooled.per_video.get(str(v.path), ()) if c.name in lost)
    assert lost and still == [] and _wrong == 0, (still, _wrong)
    assert any(g.quality == "range" for g in per_release.groups)
    assert all(g.how.startswith(episodes.STATED_SAY[u"names"]) for g in pooled.groups
               if g.quality == "range"), pooled.groups


def test_a_release_whose_names_read_two_numberings_is_split_and_every_file_lands_on_its_episode(
        tmp_path, reading, season):
    """⚠ Measured on the capture: the Amazon WEBRip reads `S02E06.第34話 …` as 34
    with no season. Aligned ALONE -- nothing to borrow an offset from -- every
    Amazon file must still land on its true episode and no other.
    ⚠ AMENDED v2 (2026-10-11): tsubasa now reads BOTH numbers (`dual_numbering`), so the
    release is no longer split -- ONE season-2 part, its whole range at 0."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    assert {reading[f["name"]].season is None for f in amazon} == {True, False}, "the capture mixes both"
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    assert len(a.groups) == 1 and a.groups[0].quality == "range" and a.groups[0].season == 2, a.groups
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
    # ⚠ AMENDED v2 (2026-10-11): a release placed by an offset its names or the list
    # STATE is evidence even for one video -- the soft spot is the arithmetic's, not theirs.
    assert {c.quality for c in got if not c.stated} <= {"literal", "position"}
    assert {c.offset for c in got if c.stated} <= {season["shift"]}, got
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


# ---------------------------------------------------------------------------
# ⭐ THE FRIEREN FINDING (2026-09-27, re-measured 2026-10-12): a fit by LENGTH alone
# ---------------------------------------------------------------------------
#
# Entry 11446's Amazon WEBRip is two parts (`S02E01-05, 09-10` read as season 2,
# `S02E06.第34話` read as an absolute 34). Any two runs of equal length fit at ONE
# offset, so its 3-file part "fitted" a 3-video folder at +3 -- `range` -- and the
# untimed road placed episode 34 for 31. These are the witnesses.

_PROVEN = ("range", "overlap")


def _absolute(season_read, episode, season):
    u"""An episode in the capture's absolute count: a seasonal number inside the
    season's own range is shifted; anything else already counts on."""
    if season_read is not None and episode in season["numbers"]:
        return episode + season["shift"]
    return episode


def _wrong_proven(a, videos, season):
    out = []
    for v in videos:
        want = _absolute(v.season, v.episode, season)
        for c in a.per_video.get(str(v.path), ()):
            if c.quality in _PROVEN and _absolute(c.info.season, c.info.episode, season) != want:
                out.append((v.episode, c.name, c.quality, c.offset))
    return out


def _count_on_part(a):
    return [g for g in a.groups if g.group.endswith(u"Amazon.ja-jp[sdh]") and g.season is None]


NETFLIX_LIKE = u"Sousou.no.Frieren.S02E%02d.1080p.NF.WEB-DL.AAC2.0.H.264.mkv"


@pytest.mark.parametrize("naming", ["absolute", "S02E count-on"])
def test_a_part_its_own_release_contradicts_is_not_proven_by_its_length(tmp_path, season, naming):
    u"""WITNESS A. The Amazon release ALONE against three videos of the season's middle.
    ⭐ The harm is real first: the count-on part is exactly as long as the folder and
    sits at a re-numbered offset -- the shape that fits uniquely by length alone."""
    amazon = [f for f in UNDUAL if u".Amazon." in f["name"]]          # v2: a release that SWITCHES
    shift = season["shift"]
    numbers = [n + shift for n in season["numbers"][2:5]]           # 31, 32, 33
    pattern = absolute if naming == "absolute" else (lambda ns: [NETFLIX_LIKE % n for n in ns])
    videos = stubs(tmp_path / "v", pattern(numbers))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    part, = _count_on_part(a)
    assert len(part.episodes) == len(videos) and part.offsets and 0 not in part.offsets, part
    assert _wrong_proven(a, videos, season) == [], _wrong_proven(a, videos, season)
    assert part.quality == "guess" and part.how.startswith(episodes.DISPUTED), part


@pytest.mark.parametrize("naming", ["absolute", "S02E count-on"])
def test_the_whole_entry_offers_no_wrong_episode_as_proven_and_keeps_the_right_ones(
        tmp_path, season, naming):
    u"""WITNESS B. The whole entry against the same three videos: the right files won
    already, but the wrong Amazon file was a FIT -- #2 under `.srt` -- and the untimed
    road tries the next file when the first fails its download or its Japanese read."""
    shift = season["shift"]
    numbers = [n + shift for n in season["numbers"][2:5]]
    pattern = absolute if naming == "absolute" else (lambda ns: [NETFLIX_LIKE % n for n in ns])
    videos = stubs(tmp_path / "v", pattern(numbers))
    a = episodes.align(FILES, videos, workdir=tmp_path / "w")
    assert _wrong_proven(a, videos, season) == [], _wrong_proven(a, videos, season)
    for v in videos:
        right = [c for c in a.per_video[str(v.path)] if c.quality == "range" and c.offset == 0]
        assert len(right) >= 4, (v.name, right)      # Haruhana, Kitauji, Nekomoe, Netflix


def test_a_fragment_of_a_split_release_lends_its_offset_to_no_other_release(tmp_path, season):
    u"""WITNESS C -- found by the 2026-10-11 sweep. Seasonal names S2 05-07 against the
    whole entry: the 3-file Amazon part fitted +29 by length, and pass 2 LENT +29 to every
    absolute release as *"where WEBRip.Amazon fit a whole range"* -- so Haruhana's 34 was a
    proven fit for 05, #1 under `.ass` and `.srt`."""
    videos = stubs(tmp_path / "v", seasonal(season["numbers"][4:7]))   # 05, 06, 07
    a = episodes.align(UNDUAL, videos, workdir=tmp_path / "w")       # v2: a release that SWITCHES
    part, = _count_on_part(a)
    assert len(part.episodes) == len(videos), part                     # the harm is real
    assert _wrong_proven(a, videos, season) == [], _wrong_proven(a, videos, season)
    assert not [g for g in a.groups if u"fit a whole range" in g.how and u"Amazon" in g.how], [
        (g.group, g.how) for g in a.groups]


def test_the_number_both_sides_write_is_never_demoted(tmp_path, season):
    u"""The control: the same split release against 34-36 -- the count-on part sits at
    offset 0, where the file's number IS the video's -- keeps its proven fit."""
    amazon = [f for f in UNDUAL if u".Amazon." in f["name"]]          # v2: a release that SWITCHES
    numbers = [n + season["shift"] for n in season["numbers"][5:8]]   # 34, 35, 36
    videos = stubs(tmp_path / "v", absolute(numbers))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    part, = _count_on_part(a)
    assert part.offsets == (0,) and part.quality in _PROVEN, part
    for v in videos:
        assert [c for c in a.per_video[str(v.path)]
                if c.quality in _PROVEN and c.info.episode == v.episode], v.name


def test_16n_F9_a_release_split_across_two_partitions_lends_nothing(tmp_path, season):
    u"""16n F-9 (adversary A1). WITNESS C with the release's two parts in DIFFERENT
    partitions: a folder of absolute-named 29, 30, 37, 38 and `S2`-named 05-07. Amazon's
    season-2 part (01-05, 09-10) fits the absolute videos best (4 at -28), its 34-36
    fragment the S2 videos (3 at +29, by length) -- so pass 1 of the S2 partition saw ONE
    Amazon part and called the release whole. Haruhana's 33-36 ties there at +28 (true)
    and +29; borrowing the fragment's +29 put 34 on 05, 35 on 06, 36 on 07."""
    shift = season["shift"]
    amazon = [f for f in UNDUAL if u".Amazon." in f["name"]]          # v2: a release that SWITCHES
    haruhana = [f for f in FILES if f["name"].startswith(u"[Haruhana]") and u"[JPN]" in f["name"]
                and int(_re.search(u" - ([0-9]+) ", f["name"]).group(1)) in range(5 + shift, 9 + shift)]
    s2 = stubs(tmp_path / "v", seasonal(season["numbers"][4:7])                  # 05, 06, 07
               + absolute([n + shift for n in season["numbers"][0:2] + season["numbers"][8:10]]))
    a = episodes.align(amazon + haruhana, s2, workdir=tmp_path / "w")
    videos = [v for v in s2 if v.season is not None]
    part, = _count_on_part(a)
    # ⭐ the harm is real: the fragment is fitted against the S2 videos, its season part is not
    assert part.partition == videos[0].season and len(part.episodes) == len(videos), part
    assert [g for g in a.groups if u"Amazon" in g.group and g.season is not None
            and g.partition is None], [(g.group, g.season, g.partition) for g in a.groups]
    haru, = [g for g in a.groups if g.group == u"Haruhana" and g.partition == videos[0].season]
    assert len(haru.episodes) == 4 and haru.offsets, haru            # it IS placed in the S2 videos
    assert not [g for g in a.groups if u"fit a whole range" in g.how and u"Amazon" in g.how], [
        (g.group, g.how) for g in a.groups]
    wrong = _wrong_proven(a, videos, season)
    assert [w for w in wrong if u"Amazon" not in w[1]] == [], wrong
    assert shift in haru.offsets, haru                               # the true offset is still tried
    # 🚨 AND THE FRAGMENT'S OWN FIT (lead's ruling, 16n): `range` +29 by length, and pass 3
    # cannot dispute it -- its season part was fitted against the absolute videos. A fragment
    # of a split release is never WHOLE, so the untimed road refuses it; timing still tries it.
    for v in videos:
        frag = [c for c in a.per_video[str(v.path)] if u"Amazon" in c.name]
        assert frag and not [c for c in frag if _placeable(c)], [
            (c.name, c.quality, c.offset, c.coverage) for c in frag]




def test_releases_that_number_differently_never_dispute_each_other(tmp_path, season):
    u"""A dispute is ONE release against itself. The whole season, seasonal names: every
    release keeps its proven fit -- NanakoRaws at 0 and Haruhana at the season's shift put
    different NUMBERS on video 1, and both are right."""
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(UNDUAL, videos, workdir=tmp_path / "w")      # v2: a release that SWITCHES
    by_group = dict((g.group, g) for g in a.groups if g.season is None or g.group != u"WEBRip.Amazon.ja-jp[sdh]")
    for group in (u"Haruhana", u"KitaujiSub", u"NanakoRaws", u"shincaps"):
        assert by_group[group].quality in _PROVEN, by_group[group]
    assert by_group[u"Haruhana"].offsets == (season["shift"],), by_group[u"Haruhana"]


# ---------------------------------------------------------------------------
# ⭐ v2 (2026-10-11): BOTH NUMBERS READ, AND A STATED BRIDGE
# ---------------------------------------------------------------------------
#
# tsubasa now keeps the second number of `S02E06.第34話` (`Item.dual_numbering`), so
# the Amazon release is ONE season-2 part, and its own names STATE the bridge
# (S2E6 = 34: season 2 starts at 29). anime-relations states the same bridge for
# releases whose names say nothing. A stated offset places a part; the arithmetic
# only decides where nothing states one.

import inspect as _inspect
import re as _re

from hato import untimed as _untimed


def _placeable(c):
    u"""The untimed road's own test where it has one (v1, v2); main's FITS otherwise --
    so a red on main is the BEHAVIOUR, never a missing name."""
    test = getattr(_untimed, "placeable", None)
    return test(c) if test else c.quality in _untimed.FITS


def _stated(c):
    return getattr(c, "stated", None)


def _dual(info):
    return getattr(info, "dual_numbering", None)


def _align(files, videos, workdir, bridge=None):
    if bridge is not None and "bridge" in _inspect.signature(episodes.align).parameters:
        return episodes.align(files, videos, workdir=workdir, bridge=bridge)
    return episodes.align(files, videos, workdir=workdir)

#: The capture's Amazon names with the season-episode taken OFF the three dual
#: files -- a release that really does switch numbering, so changes (1) and (2)
#: keep a witness after both numbers are read.
UNDUAL = [dict(f, name=_re.sub(u"[.]S[0-9]{2}E[0-9]{2}[.](?=第)", u".", f["name"])) for f in FILES]

FRIEREN_S2_ANILIST = 182255


def _bridge():
    try:
        from hato import relations
    except ImportError:
        return object()                      # main: no list to ask -- `_align` drops it
    found = relations.for_entry(FRIEREN_S2_ANILIST)
    assert found is not None and found.shift == 28, found     # the snapshot states it
    return found


def _true_absolute(info, season):
    if _dual(info):
        return _dual(info)[2]
    return _absolute(info.season, info.episode, season)


def test_a_name_stating_both_numberings_joins_its_release_by_season(tmp_path, reading, season):
    u"""WITNESS v2-A. tsubasa reads both numbers of `S02E06.第34話`; the file joins its
    release's season-2 part, and the release is one part with no hole."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    dual = [_dual(reading[f["name"]]) for f in amazon if u"第" in f["name"]]
    assert dual and all(d and d[0] == 2 and d[2] - d[1] == season["shift"] for d in dual), dual
    videos = stubs(tmp_path / "v", seasonal(season["numbers"]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    part, = [g for g in a.groups if u"Amazon" in g.group]
    assert part.season == 2 and list(part.episodes) == season["numbers"], part
    assert part.offsets == (0,) and part.quality == "range", part


@pytest.mark.parametrize("numbers", [[31, 32, 33], [34, 35, 36], [30, 37], [38]])
def test_the_names_state_the_bridge_and_the_right_file_is_placed(tmp_path, reading, season, numbers):
    u"""WITNESS v2-B. Amazon ALONE against absolute-named videos, no list: its own names
    state S2E6 = 34, so 31 is S2E3 -- placed, `stated`, and the untimed road may take it.
    Main placed 34-36 for 31-33 (`range` +3) and v1 placed nothing."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "v", absolute(numbers))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    for v in videos:
        got = [c for c in a.per_video.get(str(v.path), ()) if _placeable(c)]
        assert [_true_absolute(c.info, season) for c in got] == [v.episode], (v.name, got)
        assert _stated(got[0]) == u"names" and got[0].offset == -season["shift"], got


def test_anime_relations_places_a_release_whose_names_state_nothing(tmp_path, reading, season):
    u"""WITNESS v2-C. Haruhana alone (absolute names only) against S2 05-07: nothing in
    its names says where season 2 starts, so without the list it is a tie and waits.
    With anime-relations (182255: 29-38 -> 1-10) it is placed at +28."""
    haruhana = [f for f in FILES if f["name"].startswith(u"[Haruhana]")]
    videos = stubs(tmp_path / "v", seasonal([5, 6, 7]))
    without = episodes.align(haruhana, videos, workdir=tmp_path / "a")
    assert not [c for v in videos for c in without.per_video.get(str(v.path), ())
                if _placeable(c)], u"the harm is real: alone it proves nothing"
    a = _align(haruhana, videos, tmp_path / "b", bridge=_bridge())
    for v in videos:
        got = [c for c in a.per_video[str(v.path)] if _placeable(c)]
        assert got and {c.info.episode for c in got} == {v.episode + season["shift"]}, (v.name, got)
        assert {_stated(c) for c in got} == {u"anime-relations"}, got


def test_a_seasonless_video_is_never_bridged_into_the_sequels_own_count(tmp_path, season):
    u"""GUARD. `Frieren - 05` may be the FIRST season's 5: the list states nothing for it,
    and nothing is placed by the bridge."""
    haruhana = [f for f in FILES if f["name"].startswith(u"[Haruhana]")]
    videos = stubs(tmp_path / "v", absolute([5, 6, 7]))
    a = _align(haruhana, videos, tmp_path / "w", bridge=_bridge())
    assert not [c for v in videos for c in a.per_video.get(str(v.path), ()) if _stated(c)], a.groups


def test_two_sources_that_disagree_state_nothing(tmp_path, season):
    u"""GUARD. The names say +28; a list that says +27 is contradicted, so neither speaks
    (fail safe) and the fit falls back to the arithmetic."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    from hato import relations
    wrong = relations.Bridge(27, 28, 37, 1, 10, u"anime-relations")
    videos = stubs(tmp_path / "v", absolute([31, 32, 33]))
    a = _align(amazon, videos, tmp_path / "w", bridge=wrong)
    assert not [c for v in videos for c in a.per_video.get(str(v.path), ()) if _stated(c)]
    assert not [c for v in videos for c in a.per_video.get(str(v.path), ()) if _placeable(c)
                and c.offset not in (None, 0)], u"change 3 is the last resort, and it holds"


def test_the_list_places_the_platforms_season_tag_on_an_absolute_number(tmp_path, season):
    u"""WITNESS v2-D. Netflix-like video names `S02E31` (a season tag on the absolute number)
    against Amazon alone: the names' bridge cannot speak (both sides read season 2), the
    list reads NUMBERS -- 31 is in 29-38 -- and places S2E3."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "v", [NETFLIX_LIKE % n for n in (31, 32, 33)])
    a = _align(amazon, videos, tmp_path / "w", bridge=_bridge())
    for v in videos:
        got = [c for c in a.per_video[str(v.path)] if _placeable(c)]
        assert [_dual(c.info) or (c.info.season, c.info.episode) for c in got] == [
            (2, v.episode - season["shift"])], (v.name, got)


def test_names_that_state_two_starts_state_none(tmp_path, season):
    u"""GUARD. One season, two files whose names disagree on where it starts (S2E6 = 34,
    S2E7 = 45): the names state no bridge, a note says so, and nothing is placed as stated."""
    amazon = [dict(f, name=f["name"].replace(u"第35話", u"第45話")) for f in FILES
              if u".Amazon." in f["name"]]
    assert any(u"第45話" in f["name"] for f in amazon)
    videos = stubs(tmp_path / "v", absolute([31, 32, 33]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    assert not [c for v in videos for c in a.per_video.get(str(v.path), ()) if _stated(c)]
    assert [n for n in a.notes if u"two different starts" in n], a.notes


def test_a_later_season_written_twice_is_no_bridge(tmp_path):
    u"""GUARD. `S02E06.第6話` -- a platform writing the SEASON's number twice -- would say
    season 2 starts at broadcast episode 1, which no later season can. It states nothing:
    seasonless 05-07 get no stated fit from it."""
    amazon = [dict(f, name=f["name"].replace(u"第34話", u"第6話").replace(u"第35話", u"第7話")
                   .replace(u"第36話", u"第8話")) for f in FILES if u".Amazon." in f["name"]]
    assert any(u"S02E06.第6話" in f["name"] for f in amazon)
    videos = stubs(tmp_path / "v", absolute([5, 6, 7]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w")
    assert not [c for v in videos for c in a.per_video.get(str(v.path), ()) if _stated(c)], [
        (c.name, c.offset, _stated(c)) for v in videos for c in a.per_video.get(str(v.path), ())]


def test_a_stated_part_wins_a_dispute_it_has_less_support_in(tmp_path, season):
    u"""GUARD. The release's season part is stated (-28) but lands only 2 files on 29-32; its
    switched part (`第34-37話`, no season-episode) slides to +5 and lands 4. Support alone
    would keep the slide -- 34 for 29. A stated numbering wins the dispute whatever the count.
    The 37 is constructed in the capture's own shape (`file_dict`).
    ⚠ PORTED 2026-10-31 (the proof queue's anchor preflight): the prototype added this guard
    after its tests diff was taken (`out/2026-10-11-frieren-fix-v2/witness_v2_align_support.py`),
    so 16i's port missed it and MFS-17 named a witness that did not exist -- pytest's "not
    found", which a runner reads as a KILL.
    ⭐ 16o (MFS-17 survived): 16n's fragment rule (F-9) now keeps the slid part off the
    untimed road whether or not it loses the dispute (coverage < 1), so `_placeable` no
    longer sees the dispute. What winning it still decides is the TIMED road's order: the
    slid part is a `guess`, and `rank` tries it after the stated file (`rank.py`: a guess
    after every known number). Left out of the dispute, it was `range` and tried FIRST."""
    amazon = [f for f in UNDUAL if u".Amazon." in f["name"]
              and (u"第" in f["name"] or u".S02E01." in f["name"] or u".S02E02." in f["name"])]
    amazon.append(file_dict(u"葬送のフリーレン.第37話 ヒンメルの自伝.WEBRip.Amazon.ja-jp[sdh].srt"))
    videos = stubs(tmp_path / "v", absolute([29, 30, 31, 32]))
    a = _align(amazon, videos, tmp_path / "w", bridge=_bridge())
    wrong = [(v.episode, c.name, c.quality, c.offset) for v in videos
             for c in a.per_video.get(str(v.path), ())
             if _placeable(c) and _true_absolute(c.info, season) != v.episode]
    assert wrong == [], wrong
    for v in videos:
        ranked = [r.candidate for r in rank.rank(a.per_video.get(str(v.path), ())).ordered]
        right = [i for i, c in enumerate(ranked) if _true_absolute(c.info, season) == v.episode]
        slid = [(i, c.name, c.quality) for i, c in enumerate(ranked)
                if _true_absolute(c.info, season) != v.episode]
        assert slid and all(q == u"guess" for _i, _n, q in slid), (v.episode, slid)
        assert not right or max(right) < min(i for i, _n, _q in slid), (v.episode, slid)


@pytest.mark.parametrize("numbers", [[29, 30, 31], [30, 31, 32]])
def test_a_stated_part_disputes_a_slid_part_of_its_own_release(tmp_path, season, numbers):
    u"""GUARD (found by the v2 sweep, 2026-10-11). A release that really SWITCHES numbering
    (`第34話` with no season-episode), the list ON, videos 29-31: the season part is placed
    by the list at -28; the 3-file absolute part slid to +5 by length. The stated part is the
    other side of that dispute -- left out of it, 34 was a proven fit for 29."""
    amazon = [f for f in UNDUAL if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "v", absolute(numbers))
    a = _align(amazon, videos, tmp_path / "w", bridge=_bridge())
    wrong = [(v.episode, c.name, c.quality, c.offset) for v in videos
             for c in a.per_video.get(str(v.path), ())
             if _placeable(c) and _true_absolute(c.info, season) != v.episode]
    assert wrong == [], wrong


# ---------------------------------------------------------------------------
# LAYER 16, 16i -- what the prototype left to do: the commands pass the list's
# bridge, and every place that explains a placement says when it was STATED
# ---------------------------------------------------------------------------

def test_one_video_placed_by_a_stated_offset_says_so_in_its_note(tmp_path, season):
    u"""16i. A lone video is the soft spot -- unless its place was STATED. Amazon alone
    against `Frieren - 31`: its names state +28, and the note names them (and the release),
    where it used to call the whole thing a literal match. Control: Haruhana alone, the
    names silent and no list -- the note says nothing was stated."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    v = stubs(tmp_path / "v", absolute([31]))
    a = episodes.align(amazon, v, workdir=tmp_path / "w")
    assert [c for c in a.per_video[str(v[0].path)] if _stated(c) == u"names"], a.per_video
    note, = [n for n in a.notes if u"soft spot" in n]
    assert u"STATED by the entry's own names for " in note and u"Amazon" in note, note
    assert u"otherwise matched literally" in note, note

    haruhana = [f for f in FILES if f["name"].startswith(u"[Haruhana]")]
    w = stubs(tmp_path / "h", seasonal([5]))
    b = episodes.align(haruhana, w, workdir=tmp_path / "x")
    note, = [n for n in b.notes if u"soft spot" in n]
    assert u"STATED" not in note and u"its number was matched literally" in note, note


def test_hato_align_with_anilist_says_the_list_states_the_offset(tmp_path, capsys, season):
    u"""16i. `hato align --explain --anilist 182255` hands the command the list's bridge,
    as a run does: Haruhana alone against S2 05-07 is placed at +28 and the row says
    anime-relations stated it. Without --anilist the header says the list was not asked
    and nothing is stated -- the two arms differ ONLY by the flag."""
    listed = tmp_path / "haruhana.json"
    listed.write_text(json.dumps([f for f in FILES if f["name"].startswith(u"[Haruhana]")],
                                 ensure_ascii=False), encoding="utf-8")
    stubs(tmp_path / "v", seasonal([5, 6, 7]))
    base = ["--explain", str(tmp_path / "v"), "11446", "--files", str(listed)]

    assert _run_align(base) == 0
    without = capsys.readouterr().out
    assert u"anime-relations not asked" in without.splitlines()[0], without
    assert u"states offset" not in without, without

    assert _run_align(base + ["--anilist", str(FRIEREN_S2_ANILIST)]) == 0
    with_list = capsys.readouterr().out
    head = with_list.splitlines()[0]
    assert u"AniList 182255" in head and u"29-38 are its own 1-10" in head, head
    assert u"anime-relations states offset +%d" % season["shift"] in with_list, with_list


def test_hato_align_with_an_anilist_the_list_does_not_know_says_so(tmp_path, capsys):
    stubs(tmp_path / "v", seasonal([5]))
    assert _run_align(["--explain", str(tmp_path / "v"), "11446", "--files",
                       str(API / "entries_11446_files.json"), "--anilist", "1"]) == 0
    assert u"anime-relations: no rule for AniList 1" in capsys.readouterr().out.splitlines()[0]


@pytest.mark.parametrize("listed, says", [
    ((), u"the list could not be read"),
    ((u"- ?|?|1:21-24 -> ?|?|9:1-4!", u"- ?|?|1:25-28 -> ?|?|9:1-4!"), u"state no one shift"),
], ids=["unreadable", "disagree"])
def test_16n_F11_a_list_that_could_not_be_read_is_told_from_one_with_no_rule(
        tmp_path, capsys, monkeypatch, listed, says):
    u"""A10: the header said *"no rule for AniList N"* when the list failed to load, or
    when it held several rules for the entry that disagree -- three cases, one sentence."""
    from hato import relations
    rules = relations.parse(u"::rules\n" + u"\n".join(listed) + u"\n")
    monkeypatch.setattr(relations, "load", lambda path=None: list(rules))
    monkeypatch.setattr(relations, "_LOADED", [])
    stubs(tmp_path / "v", seasonal([5]))
    assert _run_align(["--explain", str(tmp_path / "v"), "11446", "--files",
                       str(API / "entries_11446_files.json"), "--anilist", "9"]) == 0
    head = capsys.readouterr().out.splitlines()[0]
    assert says in head and u"no rule for" not in head, head


def test_the_names_state_in_words_that_agree(tmp_path, season):
    u"""16i. *"its names states offset"* was the prototype's grammar. The `how` of a part
    the names place is *"its names state offset -28"*."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    a = episodes.align(amazon, stubs(tmp_path / "v", absolute([31, 32, 33])), workdir=tmp_path / "w")
    text = episodes.explain(a)
    assert u"its names state offset -%d" % season["shift"] in text, text
    assert u"names states" not in text, text



# ---------------------------------------------------------------------------
# 16z -- the Opus adversary's alignment rows (Z-B1, Z-B2, A4-A7). Each one a WRONG
# episode stated (or proven) by a bridge; each fix states nothing rather than guess.
# ---------------------------------------------------------------------------

HARUHANA = u"[Haruhana] Sousou no Frieren - %02d [WebRip][HEVC-10bit 1080p][JPN].ass"
NANAKO = u"[NanakoRaws] Sousou no Frieren S%d - %02d (NTV 1080p HEVC AAC).ass"


def _longer_season(numbers, shift=11):
    u"""A season of 13 after a season of 11 (Oshi no Ko's shape), named as Amazon names
    Frieren: `S02E01.第12話` -- the season's OWN count (1-13) reaches into the absolute
    count (12-24), so `12` alone is season 2's 12 or its 1."""
    return [file_dict(u"葬送のフリーレン.S02E%02d.第%d話.WEBRip.Amazon.ja-jp[sdh].srt" % (n, n + shift))
            for n in numbers]


def _season_episode(c):
    dual = _dual(c.info)
    return dual[1] if dual else c.info.episode


@pytest.mark.parametrize("shape", ["seasonless videos", "seasonless release", "the videos say"])
def test_16z_zb1_a_season_whose_own_count_reaches_its_shift_states_nothing(tmp_path, shape):
    u"""Z-B1 (probe 1). `bridge_for` refuses a list rule whose two counts overlap; the
    names' bridge never asked. +11 from `S02E01.第12話`, with 13 episodes in the season:
    (a) seasonless videos 01-13 numbered by the season -- S2E01 went on video 12 as STATED;
    (b) a seasonless release numbering by the season (`- 12`, `- 13`) went on S2 01-02;
    (c) the names show only E01-E02, but the folder's own `S2 - 13` shows the season is
    longer than the shift -- the same (b), told by the videos."""
    if shape == "seasonless videos":
        files, videos = _longer_season(range(1, 14)), stubs(tmp_path / "v", absolute(range(1, 14)))
        mine = lambda c: u"Amazon" in c.name
        right = lambda c, v: _season_episode(c) == v.episode
    else:
        files = _longer_season(range(1, 14) if shape == "seasonless release" else (1, 2))
        files += [file_dict(HARUHANA % n) for n in (12, 13)]
        videos = stubs(tmp_path / "v", seasonal(range(1, 14)))
        mine = lambda c: u"Haruhana" in c.name
        right = lambda c, v: c.info.episode == v.episode
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    rows = [(v.episode, c.name, c.offset, _stated(c)) for v in videos
            for c in a.per_video.get(str(v.path), ()) if mine(c)]
    assert not [r for r in rows if r[3]], rows
    assert not [(v.episode, c.name) for v in videos for c in a.per_video.get(str(v.path), ())
                if mine(c) and _placeable(c) and not right(c, v)], rows


def test_16z_zb2_an_open_rule_states_nothing_for_a_video_at_or_past_its_start(tmp_path):
    u"""Z-B2 (probe 2). `13-? -> 1-?!` never says where the entry's own count ends, and
    `bridge_for` invents it (12). With S2 01-12 on jimaku and `S2 - 13` just aired, the
    list put S2 **01** on 13 as stated. Now the rule says nothing for 13 -- and, as
    without the list, nothing is placed; below its start it still speaks (01-12 at 0)."""
    from hato import relations
    rule = u"::rules\n- 54852|47240|163142:13-? -> 57612|48397|172192:1-?!\n"
    bridge = relations.bridge_for(relations.parse(rule), 172192)
    assert bridge is not None and (bridge.shift, bridge.abs_lo, bridge.abs_hi) == (12, 13, None)
    files = [file_dict(NANAKO % (2, n)) for n in range(1, 13)]
    videos = stubs(tmp_path / "v", seasonal([13]))
    a = episodes.align(files, videos, workdir=tmp_path / "w", bridge=bridge)
    got = [(c.name, c.offset, _stated(c)) for c in a.per_video.get(str(videos[0].path), ())]
    assert not [g for g in got if g[2]] and not [
        c for c in a.per_video.get(str(videos[0].path), ()) if _placeable(c)], got
    below = stubs(tmp_path / "b", seasonal([3, 4, 5]))
    b = episodes.align(files, below, workdir=tmp_path / "x", bridge=bridge)
    for v in below:
        assert [(c.info.episode, c.offset, _stated(c)) for c in b.per_video[str(v.path)]] == [
            (v.episode, 0, u"anime-relations")], v.name


@pytest.mark.parametrize("source", ["the list", "the names"])
def test_16z_a4_a_whole_show_release_on_the_sequel_entry_is_placed_where_stated(tmp_path, source):
    u"""A4. Haruhana `- 01..38` (both seasons, absolute) on the S2 entry against S2 01-10.
    +28 is stated -- by the list (11-28 are in neither of the entry's counts, so the release
    numbers across the seasons) or by Amazon's `S02E06.第34話` -- and pass 0 dropped it
    because files 01-28 would fall below episode 0; offset 0 then took `range`: S1's n on
    S2's n, all ten. ⭐ The floor is per LANDING file: 29-38 land, as stated."""
    files = [file_dict(HARUHANA % n) for n in range(1, 39)]
    bridge = None
    if source == "the list":
        bridge = _bridge()
    else:
        files += [f for f in FILES if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "v", seasonal(range(1, 11)))
    a = episodes.align(files, videos, workdir=tmp_path / "w", bridge=bridge)
    for v in videos:
        got = [(c.info.episode, c.offset, _stated(c)) for c in a.per_video[str(v.path)]
               if u"Haruhana" in c.name and _placeable(c)]
        assert got == [(v.episode + 28, 28, u"anime-relations" if bridge else u"names")], (v.name, got)


def test_16z_a4_a_stated_offset_that_lands_nothing_vetoes_offset_0(tmp_path):
    u"""A4, the veto. The same release, the names stating +28, and the folder holds S2 11-12
    (aired after the release's 38): +28 lands nothing, and offset 0 -- covering every
    video -- took `range`: S1's 11 and 12 on S2's. A statement that the part numbers
    across the seasons contradicts offset 0: nothing is placed.
    GUARD: a seasonless release numbering the SEASON (`- 01..10`, nothing past the shift)
    is not contradicted -- against S2 01-10 it keeps its own numbers."""
    files = [file_dict(HARUHANA % n) for n in range(1, 39)]
    files += [f for f in FILES if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "v", seasonal([11, 12]))
    a = episodes.align(files, videos, workdir=tmp_path / "w")
    got = [(v.episode, c.name, c.offset, c.quality) for v in videos
           for c in a.per_video.get(str(v.path), ()) if u"Haruhana" in c.name and _placeable(c)]
    assert got == [], got
    own = [file_dict(HARUHANA % n) for n in range(1, 11)] + [f for f in FILES if u".Amazon." in f["name"]]
    videos = stubs(tmp_path / "s", seasonal(range(1, 11)))
    b = episodes.align(own, videos, workdir=tmp_path / "x")
    for v in videos:
        assert [(c.info.episode, c.offset) for c in b.per_video[str(v.path)]
                if u"Haruhana" in c.name and _placeable(c)] == [(v.episode, 0)], v.name


def test_16z_a5_past_the_budget_the_note_names_the_stated_offset(tmp_path, monkeypatch, season):
    u"""A5. Past the full-fit budget only the structural offsets are COUNTED -- but pass 0
    adds the stated one, and the note said it did not. Amazon alone against 31-33, its
    names stating -28 (not a structural offset here): the note names it and who said it."""
    amazon = [f for f in FILES if u".Amazon." in f["name"]]
    monkeypatch.setattr(episodes, "FULL_FIT_BUDGET", 1)
    a = episodes.align(amazon, stubs(tmp_path / "v", absolute([31, 32, 33])), workdir=tmp_path / "w")
    notes = [n for n in a.notes if u"full-fit budget" in n]
    assert notes and all(u"episode-1 offsets" in n for n in notes), a.notes
    stated = u"the offset -%d stated by the entry's own names" % season["shift"]
    assert [n for n in notes if stated in n], notes


def test_16z_a6_a_part_labelled_season_1_is_never_bridged_by_the_list(tmp_path):
    u"""A6 (probe 3). `S1 - 01..10` on the S2 entry -- a mislabel, or the first season's --
    against seasonless 31-33: the list read its numbers as the entry's own count and placed
    S1 03-05 at -28, `range`, stated. A video that says season 1 is never bridged; nor is
    a file that does."""
    files = [file_dict(NANAKO % (1, n)) for n in range(1, 11)]
    videos = stubs(tmp_path / "v", absolute([31, 32, 33]))
    a = episodes.align(files, videos, workdir=tmp_path / "w", bridge=_bridge())
    got = [(v.episode, c.name, c.offset, c.quality, _stated(c)) for v in videos
           for c in a.per_video.get(str(v.path), ()) if _stated(c) or _placeable(c)]
    assert got == [], got


def test_16z_a7_names_that_disagree_with_themselves_silence_the_list_too(tmp_path):
    u"""A7. Amazon's names state two starts for season 2 (`第34話` and a `第45話`), and a
    WRONG list states 27: the names were silent, so the list spoke alone and put S2E04 on
    31. Names that cannot agree on a season say its counts are not what anyone thinks --
    the list does not speak alone there, and the note says so."""
    from hato import relations
    amazon = [dict(f, name=f["name"].replace(u"第35話", u"第45話")) for f in FILES
              if u".Amazon." in f["name"]]
    wrong = relations.Bridge(27, 28, 37, 1, 10, u"anime-relations")
    videos = stubs(tmp_path / "v", absolute([31, 32, 33]))
    a = episodes.align(amazon, videos, workdir=tmp_path / "w", bridge=wrong)
    got = [(v.episode, c.name, c.offset, _stated(c)) for v in videos
           for c in a.per_video.get(str(v.path), ()) if _stated(c)]
    assert got == [], got
    assert [n for n in a.notes if u"two different starts" in n and u"anime-relations" in n], a.notes
