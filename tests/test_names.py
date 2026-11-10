# -*- coding: utf-8 -*-
"""
hato/names.py -- tsubasa's parser, reached for a bare name through zero-byte stubs.

This suite asserts the ADAPTER: one answer per distinct name, stubs only inside
the workdir, collisions never read twice, grouping honoured, tsubasa's own
skip reasons carried. What the parser reads in a name is tsubasa's and is
tested there; the few readings asserted below are only there to prove the
adapter handed the parser the right name.

What it structurally cannot cover: whether tsubasa's reading is RIGHT for a
given release -- that is tsubasa's corpus gate and, for hato, the timing verdict.
"""
import json
import os
from pathlib import Path

from hato import names

import pytest


@pytest.fixture
def windows_budget(monkeypatch):
    u"""⚠ 1.1.0's CI: the stub budget is Windows' MAX_PATH rule (`cache.name_budget`);
    elsewhere a name may run to NAME_MAX whatever the folder, so these checks' deep
    workdirs cut nothing. The Windows rule is pinned off Windows: the cut is proven on
    every platform, and Windows runs the real function."""
    from hato import cache
    if os.name != "nt":
        def budget(folder):
            return max(min(cache.NAME_MAX, cache.WIN_PATH_MAX - cache._units(str(folder)) - 1),
                       cache.NAME_MIN)
        monkeypatch.setattr(cache, "name_budget", budget)

ROOT = Path(__file__).resolve().parents[1]
FILES = json.loads((ROOT / "tests" / "fixtures" / "api" / "entries_11446_files.json")
                   .read_text(encoding="utf-8"))


def all_files(folder):
    return sorted(p for p in Path(folder).rglob("*") if p.is_file())


def test_one_answer_per_distinct_name_in_first_seen_order(tmp_path):
    listed = [f["name"] for f in FILES]
    infos = names.read_names(listed + listed[:3], tmp_path)
    assert [i.name for i in infos] == listed          # duplicates read once, order kept
    assert all(i.kind == "subtitle" for i in infos), [i for i in infos if i.kind != "subtitle"]


def test_every_recorded_jimaku_name_reaches_the_parser(tmp_path):
    """Derived from the capture, never pinned: every name either carries an
    episode reading or tsubasa said why it skipped it."""
    infos = names.read_names([f["name"] for f in FILES], tmp_path)
    unread = [i.name for i in infos if i.episode is None and not i.skipped]
    assert not unread, unread
    assert all(i.title for i in infos if not i.skipped)


def test_the_stubs_are_empty_and_only_inside_the_workdir(tmp_path):
    work = tmp_path / "work"
    names.read_names([f["name"] for f in FILES[:10]], work)
    stubs = all_files(work)
    assert len(stubs) == 10
    assert all(p.stat().st_size == 0 for p in stubs)
    assert [p for p in all_files(tmp_path) if not str(p).startswith(str(work))] == []


def test_a_windows_illegal_name_is_still_read(tmp_path):
    info, = names.read_names([u"[Group] Re:Zero kara Hajimeru - 05 [JPN].ass"], tmp_path)
    assert info.stub != info.name and ":" not in info.stub
    assert info.episode == 5 and info.title


def test_two_names_that_fold_to_one_stub_are_both_read(tmp_path):
    """Windows folds case: the second must not silently read the first's stub.

    ⚠ Both names are put in ONE group on purpose. Alone (the default) each gets
    its own folder, so no collision can happen and this check passed with the
    collision branch deleted -- found by mutant M3n-02, 2026-09-17."""
    infos = names.read_names([u"[A] Show - 01.ass", u"[a] show - 01.ASS"], tmp_path,
                             group_of=lambda n: "one release")
    assert len(infos) == 2 and all(i.kind == "subtitle" for i in infos), infos
    assert len(all_files(tmp_path)) == 2, all_files(tmp_path)


def test_names_sharing_a_group_share_a_folder_and_others_do_not(tmp_path):
    listed = [u"[A] Show - 01.ass", u"[A] Show - 02.ass", u"[B] Show - 01.ass"]
    names.read_names(listed, tmp_path, group_of=lambda n: n[:3])
    parents = {p.name: p.parent for p in all_files(tmp_path)}
    assert parents[u"[A] Show - 01.ass"] == parents[u"[A] Show - 02.ass"]
    assert parents[u"[A] Show - 01.ass"] != parents[u"[B] Show - 01.ass"]


def test_every_name_alone_by_default(tmp_path):
    names.read_names([u"[A] Show - 01.ass", u"[A] Show - 02.ass"], tmp_path)
    assert len({p.parent for p in all_files(tmp_path)}) == 2


def test_a_video_name_reads_as_a_video_with_no_language(tmp_path):
    info, = names.read_names([u"[SubsPlease] Sousou no Frieren S2 - 03 (1080p) [ABCD1234].mkv"],
                             tmp_path)
    assert (info.kind, info.lang, info.episode) == ("video", None, 3)


def test_a_creditless_opening_carries_tsubasas_skip_reason(tmp_path):
    info, = names.read_names([u"[Coalgirls] Toradora! - NCOP1 (1280x720).ass"], tmp_path)
    assert info.skipped and "creditless" in info.skipped


def test_an_unknown_extension_is_not_a_video_or_a_subtitle(tmp_path):
    info, = names.read_names([u"[Group] Show - 01.txt"], tmp_path)
    assert info.kind is None


def test_a_name_stating_both_numberings_carries_both(tmp_path):
    u"""v2 (2026-10-11): tsubasa's `dual_numbering`, carried as read -- `S02E06.第34話` is
    season 2 episode 6 AND broadcast 34; its season / episode stay tsubasa's (None, 34)."""
    dual = u"葬送のフリーレン.S02E06.第34話 討伐要請.WEBRip.Amazon.ja-jp[sdh].srt"
    plain = u"葬送のフリーレン.S02E05.北部高原の物流.WEBRip.Amazon.ja-jp[sdh].srt"
    a, b = names.read_names([dual, plain], tmp_path)
    assert (a.season, a.episode, getattr(a, "dual_numbering", None)) == (None, 34, (2, 6, 34))
    assert (b.season, b.episode, getattr(b, "dual_numbering", u"absent")) == (2, 5, None)


def test_an_engine_below_the_floor_still_reads_every_name(tmp_path, monkeypatch):
    u"""16i. The floor is tsubasa 0.1.11, but a source checkout or an older install may hold
    0.1.10, whose `Item` has no `dual_numbering`. Reading it plainly raised for EVERY name,
    so nothing could be aligned at all; read with getattr, the names are read as 1.0.9 read
    them and the bridge is simply unstated."""
    import tsubasa.discover
    monkeypatch.delattr(tsubasa.discover.Item, "dual_numbering")
    dual = u"葬送のフリーレン.S02E06.第34話 討伐要請.WEBRip.Amazon.ja-jp[sdh].srt"
    info, = names.read_names([dual], tmp_path)
    assert (info.episode, info.dual_numbering) == (34, None)


def test_16l_p3_a_long_name_in_a_deep_workdir_keeps_its_episode_and_maxpath(tmp_path, windows_budget):
    """#7: a ~190-character name in a deep workdir passed MAX_PATH and the show read
    nothing. The stub is cut to the cache's own budget -- in its MIDDLE, so the
    episode at the end survives -- and two names cut alike are still both read."""
    work = tmp_path / ("d" * max(1, 80 - len(str(tmp_path))))
    title = u"Isekai " + u"Nagai Taitoru " * 13
    long5 = u"[Group] %s- 05 [JPN].ass" % title
    assert len(long5) >= 190 and len(str(work)) + 1 + len(long5) > 259
    long6 = long5.replace(u"- 05", u"- 06")
    mid = long5[:100] + u"X" + long5[101:]                    # differs only in the cut middle
    infos = names.read_names([long5, long6, mid], work, group_of=lambda n: "one release")
    assert [i.episode for i in infos] == [5, 6, 5], infos
    stubs = all_files(work)
    assert len(stubs) == 3 and max(len(str(p)) for p in stubs) <= 259, stubs
    assert infos[0].stub == infos[2].stub, infos            # the collision really happened


# -- 16l P3 (#7): a long jimaku name's stub must fit Windows' 259-character path ----------

WIN_PATH_MAX = 259
LONG_NAME_LEN = 190


def long_name(episode):
    """A jimaku-shaped name of exactly LONG_NAME_LEN characters: `[Group] <title> - 05 [JPN].ass`."""
    head, tail = u"[Group] ", u" - %02d [JPN].ass" % episode
    title = (u"Kaguya-sama Love Is War Ultra Romantic Extra Long Title " * 5)
    return head + title[:LONG_NAME_LEN - len(head) - len(tail)] + tail


def deep_workdir(tmp_path):
    """Nest folders under tmp_path until a 190-character stub would pass 259 characters."""
    work = tmp_path
    while len(str(work)) + 1 + LONG_NAME_LEN <= WIN_PATH_MAX:
        work = work / "nested_folder_for_long_names"
    assert len(str(work)) + 1 + LONG_NAME_LEN > WIN_PATH_MAX, str(work)
    return work


def test_16l_p3_long_name_is_read_in_a_deep_workdir(tmp_path, windows_budget):
    name = long_name(5)
    assert len(name) == LONG_NAME_LEN
    info, = names.read_names([name], deep_workdir(tmp_path))
    assert info.episode == 5


def test_16l_p3_every_stub_path_fits_windows_limit(tmp_path, windows_budget):
    work = deep_workdir(tmp_path)
    infos = names.read_names([long_name(5), long_name(6)], work)
    stubs = all_files(work)
    assert len(stubs) == 2 and {p.name for p in stubs} == {i.stub for i in infos}, stubs
    too_long = [str(p) for p in stubs if len(str(p)) > WIN_PATH_MAX]
    assert not too_long, [len(s) for s in too_long]


def test_16l_p3_two_long_names_differing_after_cut_both_read(tmp_path, windows_budget):
    a, b = long_name(5), long_name(6)
    assert len(a) == len(b) == LONG_NAME_LEN
    # They differ only in the last 15 characters (the " - 05 [JPN].ass" tail), so any cut
    # short of the episode digits leaves them identical up to the cut.
    first_diff = next(i for i in range(LONG_NAME_LEN) if a[i] != b[i])
    assert first_diff >= LONG_NAME_LEN - 15, first_diff
    infos = names.read_names([a, b], deep_workdir(tmp_path))
    assert len(infos) == 2 and [i.episode for i in infos] == [5, 6], infos


# -- 16z Z-D1: a cut stub must never read differently from the name -------------------------

#: The adversary's sweep (probes d_stub_*): tags long enough that a deep workdir must cut,
#: an episode number that a middle cut lands around, and names past 255 characters.
D1_TAGS = [u" [1080p][WEB-DL][AAC 2.0][x264][Multi-Sub][JPN][ABCD1234]",
           u" (BD 1080p HEVC FLAC) [Japanese subtitles, retimed for the BD release by fans]",
           u" v2 [1080p].ja"]


def d1_batch():
    batch, k = [], 0
    for ep in (12, 7, 24, 105):
        for pad in range(0, 60):
            for t in D1_TAGS:
                for rep in (2, 3):
                    batch.append(u"[Group] Kimi no Na wa " + u"y" * pad + u" - %02d" % ep
                                 + t * rep + u" end%d.ja.srt" % k)
                    k += 1
    return batch


def test_16z_D1_a_cut_stub_reads_the_names_own_numbers_or_is_left_out_with_a_reason(tmp_path, windows_budget):
    u"""Z-D1 (HIGH, wrong-episode class): the stub was cut at a fixed middle -- inside the
    tags -- and spliced a NEW number (`- 12 [1080p]…[AAC 2.~ix…` read episode 2; past 255
    characters a cut inside `[ABCD1234]` read 34/234/1234). Every name is checked against
    the reading of its WHOLE name by the same tsubasa reader `scan()` uses (no stub, no
    cut): a name hato reads must read the same; one it cannot cut safely is left unread,
    with a reason, and never guessed."""
    from tsubasa.naming import episode as reader
    batch = d1_batch()
    work = tmp_path / ("w" * max(1, 120 - len(str(tmp_path))))
    infos = names.read_names(batch, work)
    cut = [i for i in infos if i.stub != i.name]
    assert len(cut) > 500, len(cut)                          # the depth really cuts
    wrong = []
    for i in infos:
        if getattr(i, "unread", None):
            continue
        whole = reader.union(i.name)
        if (i.season, i.episode) != (whole.season, whole.episode):
            wrong.append((i.episode, whole.episode, i.stub))
    assert not wrong, (len(wrong), wrong[:4])
    unread = [i for i in infos if i.unread]
    assert all(i.stub is None and i.kind is None and i.episode is None and u"too long" in i.unread
               for i in unread), unread[:3]
    assert len(unread) < len(cut)                            # most cuts fit in the title, still read
    assert len(all_files(work)) == len(infos) - len(unread)  # an unread name leaves no stub


def test_16z_D1_a_name_left_unread_is_said_in_the_shows_notes_and_offered_nowhere(tmp_path, windows_budget):
    from hato import episodes
    work = tmp_path / ("w" * max(1, 120 - len(str(tmp_path))))
    long12 = (u"[Group] Kimi no Na wa - 12" + D1_TAGS[0] * 3 + u".ja.srt")  # no title to cut
    info, = names.read_names([long12], work / "probe")
    assert getattr(info, "unread", None), info               # it cannot be cut safely
    a = episodes.align([{"name": long12, "size": 1, "url": u"x"}], [], workdir=work)
    assert any(long12 in n and u"too long" in n for n in a.notes), a.notes
    assert not a.per_video and not any(u"tsubasa skips" in n for n in a.notes), a.notes
