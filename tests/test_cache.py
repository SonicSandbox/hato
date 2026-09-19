# -*- coding: utf-8 -*-
"""
Step 1a -- the working cache (spec/02-data-model.md, RUNBOOK 1a).

    video_hash   head 64 KiB + tail 64 KiB + size -- proven TWICE: by counting the
                 bytes actually read, and by showing the middle is never looked at
    Cache        content-addressed; temp-plus-rename, so a stored file is never
                 visible half-written; a partial download discarded when its
                 block raises, Ctrl-C included; HATO_CACHE honoured
    safe_name    the nine Windows-illegal characters mapped to fullwidth twins,
                 never dropped; long names cut in the stem, extension kept
    `hato cache --stat`, both modes

What this suite STRUCTURALLY cannot cover: that nothing ELSE in hato writes beside
the media. The cache proves only that its own writes land under its own root; the
media-folder assertion -- no .part, .tmp, original or extracted member lands
there -- belongs to RUNBOOK 4c.
"""
import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

import pytest

from hato import cache, paths
from hato.commands import cache as cache_cmd

KiB = 1024
MiB = 1024 * KiB
# ⚠ The spec's number, written out -- never cache.CHUNK. A check that reads the
# constant it is checking passes when the constant is wrong.
SAMPLE = 64 * KiB


def blob_path(root, data, name):
    """Where the brief says `store` files `data`, derived without the module."""
    digest = hashlib.sha256(data).hexdigest()
    return Path(root) / "blobs" / digest[:2] / digest / name


# -- a tap on cache.py's own `open` ----------------------------------------------

class _Tap(object):
    """A real file object that counts every byte crossing it."""

    def __init__(self, fh, log, before_write):
        self._fh, self._log, self._before_write = fh, log, before_write

    def read(self, *args):
        data = self._fh.read(*args)
        self._log["read"] += len(data)
        return data

    def readall(self):
        data = self._fh.readall()
        self._log["read"] += len(data)
        return data

    def readinto(self, buf):
        n = self._fh.readinto(buf)
        self._log["read"] += n or 0
        return n

    def write(self, data):
        if self._before_write is not None:
            self._before_write(data)
        n = self._fh.write(data)
        self._log["written"] += n
        return n

    def __getattr__(self, name):
        return getattr(self._fh, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._fh.close()
        return False


@pytest.fixture
def tap(monkeypatch):
    """Every `open` inside hato/cache.py goes through _Tap. -> the running log;
    set log["before_write"] to act before each write reaches the disk."""
    log = {"read": 0, "written": 0, "opened": [], "before_write": None}
    real_open = open

    def tapped(file, mode="r", *args, **kwargs):
        fh = real_open(file, mode, *args, **kwargs)
        log["opened"].append(str(file))
        writing = any(m in mode for m in "wxa")
        return _Tap(fh, log, (lambda data: log["before_write"] and log["before_write"](data))
                    if writing else None)

    monkeypatch.setattr(cache, "open", tapped, raising=False)
    return log


# -- video_hash: never the whole video --------------------------------------------

@pytest.mark.parametrize("size", [0, 1, SAMPLE - 1, SAMPLE, SAMPLE + 1, 2 * SAMPLE - 1,
                                  2 * SAMPLE, 2 * SAMPLE + 1, 4 * MiB])
def test_a_video_hash_reads_at_most_128_KiB_whatever_the_size(tmp_path, tap, size):
    video = tmp_path / "Show - 01.mkv"
    video.write_bytes(os.urandom(size))
    cache.video_hash(video)
    assert str(video) in tap["opened"], (
        "video_hash no longer opens the video through cache.open, so this count proves nothing")
    allowed = min(size, 2 * SAMPLE)
    assert tap["read"] == allowed, (
        "video_hash read %d bytes of a %d-byte video, where it should read %d -- %s" % (
            tap["read"], size, allowed,
            "the WHOLE video was hashed" if size > 2 * SAMPLE and tap["read"] >= size
            else "the sample is the wrong size"))


def test_the_middle_of_a_video_is_never_hashed_but_both_ends_are(tmp_path):
    body = bytearray(os.urandom(MiB))
    size = len(body)
    video = tmp_path / "Show - 02.mkv"
    video.write_bytes(bytes(body))
    base = cache.video_hash(video)
    for where, offset, counts in [
            ("the first byte", 0, True),
            ("the last byte of the head", SAMPLE - 1, True),
            ("the first byte past the head", SAMPLE, False),
            ("the middle", size // 2, False),
            ("the last byte before the tail", size - SAMPLE - 1, False),
            ("the first byte of the tail", size - SAMPLE, True),
            ("the last byte", size - 1, True)]:
        flipped = bytearray(body)
        flipped[offset] ^= 0xFF
        video.write_bytes(bytes(flipped))
        got = cache.video_hash(video)
        if counts:
            assert got != base, "changing %s (offset %d) did not change the hash" % (where, offset)
        else:
            assert got == base, ("changing %s (offset %d) changed the hash -- the WHOLE video "
                                 "is being hashed" % (where, offset))


def test_two_videos_with_the_same_ends_but_different_sizes_hash_differently(tmp_path):
    head, tail = os.urandom(SAMPLE), os.urandom(SAMPLE)
    a = tmp_path / "a.mkv"
    b = tmp_path / "b.mkv"
    a.write_bytes(head + b"\0" * (100 * KiB) + tail)
    b.write_bytes(head + b"\0" * (200 * KiB) + tail)
    assert cache.video_hash(a) != cache.video_hash(b), "the file size is not part of the hash"


def test_a_video_no_bigger_than_128_KiB_is_covered_whole(tmp_path):
    for size in (100 * KiB, 2 * SAMPLE):
        body = os.urandom(size)
        video = tmp_path / ("small-%d.mkv" % size)
        video.write_bytes(body)
        base = cache.video_hash(video)
        for offset in range(0, size, 4 * KiB):
            flipped = bytearray(body)
            flipped[offset] ^= 0xFF
            video.write_bytes(bytes(flipped))
            assert cache.video_hash(video) != base, (
                "a %d-byte video: changing offset %d did not change the hash, so it is not "
                "covered whole" % (size, offset))


def test_the_video_hash_is_stable_versioned_and_survives_a_rename(tmp_path):
    body = os.urandom(300 * KiB)
    video = tmp_path / "[Group] Show - 03.mkv"
    video.write_bytes(body)
    first = cache.video_hash(video)
    assert re.match(r"^v1-[0-9a-f]{64}$", first), first
    assert cache.video_hash(video) == first
    renamed = tmp_path / "elsewhere" / "Show S01E03.mkv"
    renamed.parent.mkdir()
    os.replace(str(video), str(renamed))
    assert cache.video_hash(renamed) == first, "a rename changed the hash; the DB row is lost"
    # ⚠ Pinned on purpose: every stored row is keyed on this. A change to how it is
    # computed must bump VIDEO_HASH_VERSION, and this line is what makes that noticed.
    derived = hashlib.sha256(len(body).to_bytes(8, "little") + body[:SAMPLE] + body[-SAMPLE:])
    assert first == "v1-" + derived.hexdigest()


def test_content_hash_and_file_hash_agree_and_cover_every_byte(tmp_path):
    body = os.urandom(3 * MiB + 7)        # crosses file_hash's 1 MiB blocks
    archive = tmp_path / "Season 1.zip"
    archive.write_bytes(body)
    expected = hashlib.sha256(body).hexdigest()
    assert cache.content_hash(body) == expected
    assert cache.file_hash(archive) == expected
    flipped = bytearray(body)
    flipped[len(body) // 2] ^= 0x01
    archive.write_bytes(bytes(flipped))
    assert cache.file_hash(archive) != expected
    with pytest.raises(TypeError):
        cache.content_hash(u"字幕")


# -- where the cache lives ----------------------------------------------------------

def test_the_default_cache_is_the_redirected_per_user_root_never_the_real_one():
    c = cache.Cache()
    assert c.root == paths.data_root() / "cache"
    assert str(c.root).startswith(os.environ["HATO_TEST_ROOT"]), c.root
    assert c.root != paths.default_data_root() / "cache"


def test_HATO_CACHE_is_honoured(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv("HATO_CACHE", str(elsewhere))
    c = cache.Cache()
    # ⚠ Asserted BEFORE anything is written: were HATO_CACHE ignored, the store below
    # would land in the developer's real %LOCALAPPDATA%\hato.
    assert c.root == elsewhere / "cache", (
        "Cache() resolved to %s with HATO_CACHE=%s -- the override is ignored" % (c.root, elsewhere))
    stored = c.store(b"subtitle bytes", "Show - 01.ja.srt")
    assert str(stored).startswith(str(elsewhere / "cache") + os.sep), stored


def test_a_cache_that_was_never_used_is_reported_and_not_created(tmp_path):
    root = tmp_path / "never"
    found = cache.Cache(root).stat()
    assert not root.exists(), "asking about a cache that was never used created %s" % root
    assert found == {"path": str(root), "exists": False, "bytes": 0,
                     "entries": 0, "partial": 0, "work": 0}


# -- store --------------------------------------------------------------------------

def test_store_is_content_addressed_and_a_second_store_writes_nothing(tmp_path):
    c = cache.Cache(tmp_path / "c")
    data = u"1\n00:00:01,000 --> 00:00:02,000\n字幕\n".encode("utf-8")
    path = c.store(data, "Show - 01.ja.srt")
    assert path == blob_path(c.root, data, "Show - 01.ja.srt")
    assert path.read_bytes() == data
    long_ago = 978307200                          # 2001-01-01
    os.utime(str(path), (long_ago, long_ago))
    assert c.store(data, "Show - 01.ja.srt") == path
    assert os.stat(str(path)).st_mtime == long_ago, (
        "storing the same bytes under the same name REWROTE the file")
    beside = c.store(data, "Show - 01.srt")
    assert beside.parent == path.parent and beside != path
    assert c.store(data + b"\n", "Show - 01.ja.srt").parent != path.parent
    assert not list((c.root / "partial").iterdir()), "a temp file was left behind"


def test_store_file_files_the_copy_exactly_where_store_would(tmp_path):
    c = cache.Cache(tmp_path / "c")
    data = os.urandom(2 * MiB + 11)
    src = tmp_path / "download.bin"
    src.write_bytes(data)
    stored = c.store_file(src, "Season 1 [JPN].zip")
    assert stored == blob_path(c.root, data, "Season 1 [JPN].zip")
    assert stored.read_bytes() == data
    assert src.read_bytes() == data, "the source must be copied, never moved"


@pytest.mark.parametrize("how", ["store", "store_file"])
def test_a_stored_file_is_never_visible_half_written(tmp_path, tap, how):
    c = cache.Cache(tmp_path / "c")
    data = os.urandom(3 * MiB)
    name = "Show - 04.ja.ass"
    final = blob_path(c.root, data, name)
    writes = []

    def before_write(block):
        if final.exists():
            raise AssertionError(
                "%s exists while its bytes are still being written (%d bytes in) -- a crash "
                "now leaves a truncated file where a whole one is expected. Write to "
                "partial/ and rename into place" % (final.name, tap["written"]))
        writes.append(len(block))

    tap["before_write"] = before_write
    if how == "store":
        c.store(data, name)
    else:
        src = tmp_path / "src.bin"
        src.write_bytes(data)
        c.store_file(src, name)
    assert writes, "nothing was written through cache.open, so this check saw nothing"
    assert final.read_bytes() == data


def test_a_write_that_fails_part_way_leaves_nothing_behind(tmp_path, tap):
    c = cache.Cache(tmp_path / "c")
    data = os.urandom(3 * MiB)
    src = tmp_path / "src.bin"
    src.write_bytes(data)
    name = "Show - 05.ja.ass"

    def disk_full(block):
        if tap["written"] >= MiB:
            raise OSError(28, "No space left on device (simulated)")

    tap["before_write"] = disk_full
    with pytest.raises(OSError):
        c.store_file(src, name)
    assert tap["written"] >= MiB, "the simulated failure never happened"
    final = blob_path(c.root, data, name)
    assert not final.exists(), "a failed write left %d bytes at %s" % (final.stat().st_size, final)
    assert not list((c.root / "partial").iterdir()), "a failed write left its temp file behind"


def test_a_damaged_stored_file_is_replaced_whole(tmp_path):
    c = cache.Cache(tmp_path / "c")
    data = os.urandom(50 * KiB)
    path = c.store(data, "a.ja.ass")
    path.write_bytes(data[:10])
    assert c.store(data, "a.ja.ass") == path
    assert path.read_bytes() == data


def test_a_source_that_changes_while_it_is_stored_is_refused_not_misfiled(tmp_path, monkeypatch):
    c = cache.Cache(tmp_path / "c")
    src = tmp_path / "src.ass"
    src.write_bytes(b"what is on disk now")
    # file_hash saw the file as it WAS; the copy then reads what it is now
    monkeypatch.setattr(cache, "file_hash", lambda path: hashlib.sha256(b"what it was").hexdigest())
    try:
        c.store_file(src, "a.ja.ass")
    except OSError as exc:
        assert "changed" in str(exc), str(exc)
    else:
        pytest.fail("a source that changed while it was being stored was filed anyway -- under a "
                    "hash that is not its content's, and served as that content for ever")
    filed = [p for p in c.root.rglob("*") if p.is_file()]
    assert filed == [], "content was filed under a hash that is not its own: %s" % filed


# -- download slots and work dirs -----------------------------------------------------

@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, RuntimeError])
def test_a_partial_download_is_discarded_when_the_block_raises(tmp_path, interrupt):
    c = cache.Cache(tmp_path / "c")
    slots = []
    with pytest.raises(interrupt):
        with c.download_slot(".ass") as part:
            slots.append(part)
            assert part.parent == c.root / "partial" and part.name.endswith(".ass.part")
            assert part.is_file() and part.stat().st_size == 0
            part.write_bytes(b"[Script Info]\nTitle: half a subti")
            raise interrupt("stopped mid-download")
    assert slots and not slots[0].exists(), (
        "a %s mid-download left %s behind" % (interrupt.__name__, slots[0].name))
    assert not list((c.root / "partial").iterdir())


def test_a_finished_download_is_committed_through_store_file_and_its_part_removed(tmp_path):
    c = cache.Cache(tmp_path / "c")
    body = u"1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n".encode("utf-8")
    with c.download_slot(".srt") as part:
        part.write_bytes(body)
        stored = c.store_file(part, "Show - 06.ja.srt")
    assert stored.read_bytes() == body
    assert not part.exists() and not list((c.root / "partial").iterdir())
    with c.download_slot() as one, c.download_slot() as two:
        assert one != two


def test_a_download_slot_suffix_must_be_an_extension(tmp_path):
    with pytest.raises(ValueError):
        with cache.Cache(tmp_path / "c").download_slot("/../../evil"):
            pass


@pytest.mark.parametrize("interrupt", [None, KeyboardInterrupt])
def test_a_workdir_is_fresh_and_removed_with_everything_in_it(tmp_path, interrupt):
    c = cache.Cache(tmp_path / "c")
    seen = []
    try:
        with c.workdir(u"Season 1: [JPN].zip") as folder:
            seen.append(folder)
            assert folder.parent == c.root / "work" and folder.is_dir()
            assert not list(folder.iterdir())
            member = folder / "Season 1" / "01.ja.ass"
            member.parent.mkdir()
            member.write_bytes(b"[Script Info]")
            os.chmod(str(member), stat.S_IREAD)        # archives carry read-only members
            if interrupt is not None:
                raise interrupt()
    except BaseException as exc:
        if interrupt is None or not isinstance(exc, interrupt):
            raise
    else:
        assert interrupt is None, "the exception raised inside the block did not propagate"
    assert seen and not seen[0].exists(), "the work folder survived its block"
    assert not list((c.root / "work").iterdir())


# -- safe_name ------------------------------------------------------------------------

TWINS = [(u"<", u"\uff1c"), (u">", u"\uff1e"), (u":", u"\uff1a"), (u'"', u"\uff02"),
         (u"/", u"\uff0f"), (u"\\", u"\uff3c"), (u"|", u"\uff5c"), (u"?", u"\uff1f"),
         (u"*", u"\uff0a")]


@pytest.mark.parametrize("bad, twin", TWINS)
def test_a_windows_illegal_character_becomes_its_fullwidth_twin_never_dropped(bad, twin):
    name = u"[Group] Re%sZero - 01 [JPN].ja.ass" % bad
    got = cache.safe_name(name)
    assert got == u"[Group] Re%sZero - 01 [JPN].ja.ass" % twin, "%r became %r -- %s" % (
        name, got, "the character was DROPPED, which changes the shape of the name"
        if len(got) < len(name) else "it was not mapped to its fullwidth twin")


@pytest.mark.parametrize("name, expected", [
    (u"Show\t- 01\x00.ja.srt", u"Show- 01.ja.srt"),
    (u"Show - 01.ja.srt. . ", u"Show - 01.ja.srt"),
    (u"CON.ass", u"_CON.ass"),
    (u"nul.ja.srt", u"_nul.ja.srt"),
    (u"COM1", u"_COM1"),
    (u"LPT9.txt", u"_LPT9.txt"),
    (u"CONSOLE.ass", u"CONSOLE.ass"),
    (u"...", u"unnamed"),
    (u"", u"unnamed"),
])
def test_names_windows_would_refuse_or_quietly_change_are_made_safe(name, expected):
    assert cache.safe_name(name) == expected


@pytest.mark.parametrize("name", [u"../../evil.ass", u"..", u".", u"a/b\\c.srt",
                                  u"C:\\Windows\\evil.ass"])
def test_a_safe_name_can_never_leave_its_folder(tmp_path, name):
    got = cache.safe_name(name)
    assert got not in (u"", u".", u"..") and u"/" not in got and u"\\" not in got, got
    assert (tmp_path / got).parent == tmp_path


@pytest.mark.parametrize("stem", [u"x" * 300, u"字" * 150,
                                  u"[Group] " + u"Sousou no Frieren 2nd Season " * 12])
def test_an_over_long_name_is_cut_in_its_stem_and_keeps_its_extension(stem):
    got = cache.safe_name(stem + u".ja.ass")
    assert len(got.encode("utf-16-le")) // 2 <= 255, "%d UTF-16 units" % (len(got.encode("utf-16-le")) // 2)
    assert len(got.encode("utf-8")) <= 255, "%d UTF-8 bytes" % len(got.encode("utf-8"))
    assert got.endswith(u".ja.ass"), "the extension was cut: ...%r" % got[-24:]
    assert re.search(u"~[0-9a-f]{8}\\.ja\\.ass$", got), "no hash suffix: ...%r" % got[-24:]
    assert got.startswith(stem[:20])


def test_two_long_names_that_differ_only_past_the_cut_stay_distinct():
    a = cache.safe_name(u"y" * 300 + u" A.ja.ass")
    b = cache.safe_name(u"y" * 300 + u" B.ja.ass")
    assert a != b, ("two long names that differ only past the cut both became ...%r -- a cut name "
                    "needs its hash suffix, or the second file lands on the first" % a[-24:])


def test_a_callers_budget_is_honoured_and_an_impossible_one_refused():
    got = cache.safe_name(u"z" * 200 + u".ja.forced.srt", max_len=64)
    assert len(got) <= 64 and got.endswith(u".ja.forced.srt"), got
    with pytest.raises(ValueError):
        cache.safe_name(u"a.srt", max_len=10)


@pytest.mark.parametrize("name", [u"[Group] Re:Zero - 01 [JPN].ja.ass", u"CON.ass", u"x" * 300 + u".ja.ass",
                                  u"字" * 150 + u".ass", u"a. . ", u"..", u"Show\x01.srt"])
def test_safe_name_is_idempotent(name):
    once = cache.safe_name(name)
    assert cache.safe_name(once) == once


@pytest.mark.skipif(os.name != "nt", reason="MAX_PATH is a Windows limit; elsewhere this does not apply")
def test_a_stored_name_is_cut_to_keep_the_whole_path_inside_MAX_PATH(tmp_path):
    data = b"subtitle bytes"
    digest = hashlib.sha256(data).hexdigest()
    shortest = len(str(tmp_path / "c" / "blobs" / digest[:2] / digest))
    room = 259 - 1 - shortest
    if room < 60:
        pytest.skip("the temp folder is too deep to leave a 60-unit name budget (%d)" % room)
    root = tmp_path / ("c" + "p" * (room - 60))        # leaves exactly 60 units for the name
    stored = cache.Cache(root).store(data, u"[Group] " + u"n" * 150 + u" [JPN].ja.ass")
    assert len(str(stored)) <= 259, "%d characters, past MAX_PATH" % len(str(stored))
    assert stored.name.endswith(u".ja.ass") and len(stored.name) <= 60, stored.name
    assert stored.read_bytes() == data


# -- stat and `hato cache --stat` --------------------------------------------------------

def test_stat_counts_what_is_really_on_disk(tmp_path):
    c = cache.Cache(tmp_path / "c")
    c.store(b"one", "1.ja.srt")
    c.store(b"two", "2.ja.srt")
    c.store(b"two", "2.ja.srt")                   # the same again: still one entry
    c.store(b"two", "2 again.ja.srt")             # same bytes, another name: an entry
    (c.root / "partial").mkdir(exist_ok=True)
    (c.root / "partial" / "killed-run.part").write_bytes(b"x" * 1000)
    (c.root / "work" / "killed-run-1234abcd").mkdir(parents=True)
    on_disk = sum(p.stat().st_size for p in c.root.rglob("*") if p.is_file())
    found = c.stat()
    assert (found["path"], found["exists"]) == (str(c.root), True)
    assert found["entries"] == 3, (
        "stat counts %d entries where 3 files are stored -- leftovers in partial/ and work/ are "
        "not entries: %s" % (found["entries"], found))
    assert found["bytes"] == on_disk and on_disk > 1000, (found["bytes"], on_disk)
    assert (found["partial"], found["work"]) == (1, 1), found


def _parse(argv):
    parser = argparse.ArgumentParser(prog="hato cache")
    cache_cmd.register(parser)
    return parser.parse_args(argv)


def test_the_cache_command_has_the_shape_the_cli_loads():
    assert cache_cmd.__doc__.strip().splitlines()[0] == (
        "Show where the working cache is, how big it is, and how many entries it holds.")
    with pytest.raises(SystemExit):
        _parse([])                                # --stat is required


def test_cache_stat_prints_the_path_the_size_and_the_entry_count(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    c = cache.Cache()
    c.store(os.urandom(3000), "a.ja.ass")
    c.store(os.urandom(5000), "b.ja.ass")
    truth = c.stat()
    assert truth["entries"] == 2

    assert cache_cmd.run(_parse(["--stat"])) == 0
    text = capsys.readouterr().out
    assert re.search(r"^cache\s+%s\s+\(HATO_CACHE\)$" % re.escape(str(c.root)), text, re.M), (
        "the cache line does not name %s and where it came from:\n%s" % (c.root, text))
    assert re.search(r"^size\s+.*\(%s bytes\)$" % format(truth["bytes"], ","), text, re.M), (
        "the size line does not show the %d bytes on disk:\n%s" % (truth["bytes"], text))
    assert re.search(r"^entries\s+%d$" % truth["entries"], text, re.M), (
        "the entries line does not show the cache's %d entries:\n%s" % (truth["entries"], text))

    assert cache_cmd.run(_parse(["--stat", "--json"])) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["ok"] is True and shown["source"] == "HATO_CACHE"
    assert dict((k, shown[k]) for k in truth) == truth


def test_cache_stat_on_a_cache_never_used_says_so_and_creates_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "fresh"))
    assert cache_cmd.run(_parse(["--stat"])) == 0
    assert "not created yet" in capsys.readouterr().out
    assert not (tmp_path / "fresh").exists()


def test_cache_stat_refuses_a_relative_HATO_CACHE(monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", "relative/dir")
    assert cache_cmd.run(_parse(["--stat"])) == 1
    assert "absolute" in capsys.readouterr().err
