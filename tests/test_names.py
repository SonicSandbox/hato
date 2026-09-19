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
from pathlib import Path

from hato import names

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
