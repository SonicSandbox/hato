# -*- coding: utf-8 -*-
"""
Step 3c -- archive extraction (spec/06-edge-cases.md §5, RUNBOOK 3c).

⛔ EVERY ARCHIVE HERE IS GENERATED AT TEST TIME, into tmp_path, from synthetic text
written in this file. No archive and no subtitle body is ever kept in the repo -- the
vault auto-commits, and subtitle content is not ours (LEDGER-HOT.md).

    RUNBOOK's floor   zip-slip refused WHOLE, before any member is read, nothing left ·
                      a size bomb refused on its declared sizes AND aborted on actual
                      bytes, its partial output removed · a nested archive never
                      unpacked · a .rar with no unrar tool SKIPPED with a reason
    and               junk ignored · a whole season gives every member · bytes out
                      equal bytes in · sniffed by magic, not by name · zip names read
                      as cp932 / UTF-8 / flagged, then through safe_name · collisions
                      never overwrite · Ctrl-C and a full disk leave nothing ·
                      `hato extract`, into the cache, --into, refused, skipped

How the hostile archives are made, since the libraries refuse to write most of them:
    zip   a ZipInfo whose .filename is set after construction (zipfile rewrites
          backslashes otherwise), RawName for unflagged name bytes, patch_zip for
          headers that lie
    7z    py7zr's own member records rewritten before it writes the header -- py7zr's
          writestr refuses a traversal name (measured 2026-09-17)
    rar   built byte by byte: RAR 2.9 with STORED members, which rarfile reads with no
          tool at all

What this suite STRUCTURALLY cannot cover: real-world archive variety (spec/07); any
RAR member that needs an unpacking TOOL -- none is installed on this machine, so the
no-tool skip and stored members are all that run; RAR5 links and file copies; and
whether a real unrar pipe or a future library stops at a member's declared size --
the running count is tested against a stream double that does not.
"""
import argparse
import binascii
import codecs
import io
import os
import stat
import struct
import sys
import threading
import warnings
import zipfile
from pathlib import Path

import py7zr
import pytest
import rarfile
from py7zr import py7zr as py7zr_core

from hato import archives, cache
from hato.commands import extract as extract_cmd

KiB = 1024
MiB = 1024 * KiB


# ---------------------------------------------------------------------------
# synthetic subtitles -- written here, for these tests, by hand
# ---------------------------------------------------------------------------

def srt_bytes(ep, codec="utf-8", bom=False, newline=u"\r\n"):
    text = newline.join([u"1", u"00:00:01,000 --> 00:00:02,500", u"合成テスト 第%02d話" % ep, u"",
                         u"2", u"00:00:03,000 --> 00:00:04,000", u"synthetic line %d" % ep, u""])
    data = text.encode(codec)
    return codecs.BOM_UTF8 + data if bom else data


def ass_bytes(ep):
    return (u"[Script Info]\r\nTitle: synthetic %02d\r\nScriptType: v4.00+\r\n\r\n[Events]\r\n"
            u"Format: Layer, Start, End, Style, Text\r\n"
            u"Dialogue: 0,0:00:01.00,0:00:02.00,Default,合成 %02d\n" % (ep, ep)).encode("utf-8")


def season(count=12):
    """[(stored name, bytes)] -- a synthetic season mixing what real packs mix: Shift-JIS
    .srt, UTF-8 .srt with a BOM and CRLF, UTF-8 .ass with a stray LF, Japanese names."""
    out = []
    for ep in range(1, count + 1):
        if ep % 3 == 0:
            out.append((u"[合成] Show - %02d [JPN].srt" % ep, srt_bytes(ep, "shift_jis")))
        elif ep % 3 == 1:
            out.append((u"Season 1/[Synth] Show - %02d [JPN].srt" % ep, srt_bytes(ep, bom=True)))
        else:
            out.append((u"Season 1/[Synth] Show - %02d [JPN].ass" % ep, ass_bytes(ep)))
    return out


def basename(name):
    return name.replace(u"\\", u"/").rsplit(u"/", 1)[-1]


def tree(folder):
    folder = Path(folder)
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


# ---------------------------------------------------------------------------
# archive builders
# ---------------------------------------------------------------------------

class RawName(zipfile.ZipInfo):
    """A zip entry whose name BYTES are written exactly as given, UTF-8 flag untouched --
    what a Japanese Windows archiver writes. zipfile itself flags every non-ASCII name."""

    __slots__ = ("raw",)

    def _encodeFilenameFlags(self):
        return self.raw, self.flag_bits


def named(name, **attrs):
    """A ZipInfo carrying `name` verbatim -- backslashes, NULs and all."""
    info = zipfile.ZipInfo("placeholder")
    info.filename = name
    for key, value in attrs.items():
        setattr(info, key, value)
    return info


def make_zip(path, members, method=zipfile.ZIP_DEFLATED):
    """members: [(name or ZipInfo, bytes)]"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                 # "Duplicate name", on purpose
        with zipfile.ZipFile(str(path), "w", method) as zf:
            for name, data in members:
                zf.writestr(name, data)
    return Path(path)


def patch_zip(path, patches):
    """{stored name: {"usize": n, "flags_or": bits, "method": m}} rewritten in BOTH the
    central directory and the local header -- the archive a hostile uploader builds."""
    data = bytearray(Path(path).read_bytes())
    eocd = data.rfind(b"PK\x05\x06")
    count = struct.unpack_from("<H", data, eocd + 10)[0]
    pos = struct.unpack_from("<I", data, eocd + 16)[0]
    done = set()
    for _ in range(count):
        assert data[pos:pos + 4] == b"PK\x01\x02", "patch_zip lost the central directory"
        nlen, elen, clen = struct.unpack_from("<HHH", data, pos + 28)
        local = struct.unpack_from("<I", data, pos + 42)[0]
        name = bytes(data[pos + 46:pos + 46 + nlen]).decode("utf-8")
        if name in patches:
            want = patches[name]
            if "usize" in want:
                struct.pack_into("<I", data, pos + 24, want["usize"])
                struct.pack_into("<I", data, local + 22, want["usize"])
            if "flags_or" in want:
                for off in (pos + 8, local + 6):
                    struct.pack_into("<H", data, off, struct.unpack_from("<H", data, off)[0]
                                     | want["flags_or"])
            if "method" in want:
                struct.pack_into("<H", data, pos + 10, want["method"])
                struct.pack_into("<H", data, local + 8, want["method"])
            done.add(name)
        pos += 46 + nlen + elen + clen
    assert done == set(patches), "patch_zip never found %s" % sorted(set(patches) - done)
    Path(path).write_bytes(bytes(data))
    return Path(path)


def make_7z(path, members, rename=None, symlinks=(), **kwargs):
    """members: [(name, bytes)]. `rename` {written name: stored name} and `symlinks`
    (stored names) rewrite py7zr's own member records BEFORE it writes the header."""
    with py7zr.SevenZipFile(str(path), "w", **kwargs) as z:
        for name, data in members:
            z.writestr(data, name)
        for f in z.files:
            record = f._file_info
            if rename and record["filename"] in rename:
                record["filename"] = rename[record["filename"]]
            if record["filename"] in symlinks:
                record["attributes"] = 0x8000 | ((stat.S_IFLNK | 0o777) << 16)
    return Path(path)


def make_7z_overstated(path, members, filters, extra):
    """A .7z whose header says the LAST member holds `extra` more bytes than its data does:
    py7zr's own header, its sizes rewritten just before it is written."""
    real = py7zr_core.SevenZipFile._write_header

    def lying(self):
        folder = self.header.main_streams.unpackinfo.folders[-1]
        folder.unpacksizes = [size + extra for size in folder.unpacksizes]
        self.header.main_streams.substreamsinfo.unpacksizes[-1] += extra
        return real(self)

    py7zr_core.SevenZipFile._write_header = lying
    try:
        with py7zr.SevenZipFile(str(path), "w", filters=filters) as z:
            for name, data in members:
                z.writestr(data, name)
    finally:
        py7zr_core.SevenZipFile._write_header = real
    return Path(path)


_RAR_BLOCK = struct.Struct("<HBHH")
_RAR_FILE = struct.Struct("<LLBLLBBHL")
RAR_MSDOS, RAR_UNIX = 0, 3


def make_rar3(path, members):
    """members: [(stored name, bytes)] or [(name, bytes, host_os, mode, extra flags)] ->
    a RAR 2.9 archive of STORED members, written byte by byte."""
    out = bytearray(b"Rar!\x1a\x07\x00")
    out += _RAR_BLOCK.pack(0x90CF, 0x73, 0, 13) + b"\0" * 6
    for member in members:
        name, data = member[0], member[1]
        host_os, mode, extra = (member[2:] + (RAR_MSDOS, 0x20, 0)[len(member) - 2:])[:3]
        raw = name.encode("utf-8")
        flags = 0x8000 | extra | (0x0200 if not raw.isascii() else 0)
        header = _RAR_FILE.pack(len(data), len(data), host_os, binascii.crc32(data),
                                (40 << 25) | (1 << 21) | (1 << 16), 29, 0x30, len(raw), mode) + raw
        body = struct.pack("<BHH", 0x74, flags, _RAR_BLOCK.size + len(header)) + header
        out += struct.pack("<H", binascii.crc32(body) & 0xFFFF) + body + data
    end = struct.pack("<BHH", 0x7B, 0, 7)
    out += struct.pack("<H", binascii.crc32(end) & 0xFFFF) + end
    Path(path).write_bytes(bytes(out))
    return Path(path)


RAR_SIGNATURES = {"rar3": b"Rar!\x1a\x07\x00", "rar5": b"Rar!\x1a\x07\x01\x00"}


# ---------------------------------------------------------------------------
# instruments
# ---------------------------------------------------------------------------

@pytest.fixture
def reads(monkeypatch):
    """Counts every member stream a library opens or unpacks: the proof that a refusal
    came BEFORE any member was read -- not after an extraction that was then cleaned up."""
    log = {"zip": 0, "7z": 0, "rar": 0}
    real_zip, real_7z, real_rar = zipfile.ZipFile.open, py7zr.SevenZipFile.extract, rarfile.RarFile.open

    def zip_open(self, name, mode="r", *args, **kwargs):
        if mode == "r":
            log["zip"] += 1
        return real_zip(self, name, mode, *args, **kwargs)

    def sz_extract(self, *args, **kwargs):
        log["7z"] += 1
        return real_7z(self, *args, **kwargs)

    def rar_open(self, name, mode="r", pwd=None):
        log["rar"] += 1
        return real_rar(self, name, mode, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "open", zip_open)
    monkeypatch.setattr(py7zr.SevenZipFile, "extract", sz_extract)
    monkeypatch.setattr(rarfile.RarFile, "open", rar_open)
    return log


class _Tap(object):
    """A real file object that counts every byte hato.archives writes through it."""

    def __init__(self, fh, log):
        self._fh, self._log, self.count = fh, log, 0

    def write(self, data):
        if self._log["before_write"] is not None:
            self._log["before_write"](self, data)
        n = self._fh.write(data)
        self.count += n
        self._log["written"] += n
        self._log["most_in_one_file"] = max(self._log["most_in_one_file"], self.count)
        return n

    def close(self):
        self._fh.close()

    def __getattr__(self, name):
        return getattr(self._fh, name)


@pytest.fixture
def disk(monkeypatch):
    """Every `open` for writing inside hato/archives.py goes through _Tap. Set
    log["before_write"] to act before a write reaches the disk."""
    log = {"written": 0, "most_in_one_file": 0, "opened": 0, "before_write": None}
    real_open = open

    def tapped(file, mode="r", *args, **kwargs):
        fh = real_open(file, mode, *args, **kwargs)
        if any(m in mode for m in "wxa"):
            log["opened"] += 1
            return _Tap(fh, log)
        return fh

    monkeypatch.setattr(archives, "open", tapped, raising=False)
    return log


@pytest.fixture
def rar_gate_open(monkeypatch):
    """rarfile believes a tool exists. STORED RAR3 members need none, so this drives the
    real RAR reading path on a machine that has no tool."""
    monkeypatch.setattr(rarfile, "tool_setup", lambda *args, **kwargs: None)


@pytest.fixture
def no_rar_tool(monkeypatch):
    """Every tool rarfile looks for renamed to something that cannot exist -- the
    no-tool branch on ANY machine, through rarfile's real detection."""
    for attr in ("UNRAR_TOOL", "UNAR_TOOL", "SEVENZIP_TOOL", "SEVENZIP2_TOOL", "BSDTAR_TOOL"):
        monkeypatch.setattr(rarfile, attr, "hato-test-no-such-tool-%s" % attr.lower())
    monkeypatch.setattr(rarfile, "CURRENT_SETUP", None)


def lying_open(monkeypatch, member, payload):
    """zipfile.ZipFile.open hands back `payload` for `member` -- a decompressor that
    ignores the header's size, which zipfile itself never is."""
    real = zipfile.ZipFile.open

    def fake(self, name, mode="r", *args, **kwargs):
        info = name if isinstance(name, zipfile.ZipInfo) else self.getinfo(name)
        if mode == "r" and info.filename == member:
            return payload() if callable(payload) else io.BytesIO(payload)
        return real(self, name, mode, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", fake)


# ---------------------------------------------------------------------------
# a whole season, byte for byte
# ---------------------------------------------------------------------------

def _assert_season_came_out(found, members, into):
    wanted = [(name, data) for name, data in members
              if os.path.splitext(name)[1].lower() in archives.SUBTITLE_EXTS]
    assert found.root == into
    got = [(m.name, m.path.read_bytes()) for m in found.members]
    assert [name for name, _ in got] == [name for name, _ in wanted], (
        "the members that came out are not the %d subtitles in the archive, in order:\n%s"
        % (len(wanted), [name for name, _ in got]))
    for (name, data), member in zip(wanted, found.members):
        assert member.path.read_bytes() == data, "%s did not come out byte for byte" % name
        assert member.size == len(data)
        assert member.path.parent == into, "%s landed at %s, not directly in the root" % (
            name, member.path)
        assert member.path.name == cache.safe_name(basename(name))


def test_a_whole_season_zip_gives_every_subtitle_byte_for_byte(tmp_path):
    members = season() + [(u"Fonts/SYNTH.TTF", b"not a font")]
    archive = make_zip(tmp_path / "Season 1 [JPN].zip", members)
    into = tmp_path / "out"
    before = tree(tmp_path)
    found = archives.extract(archive, into)
    _assert_season_came_out(found, members, into)
    assert sorted(set(tree(tmp_path)) - set(before)) == sorted(
        ["out"] + [os.path.join("out", m.path.name) for m in found.members]), (
        "extract wrote something other than the subtitles, or outside the root")


def test_a_whole_season_7z_gives_every_subtitle_byte_for_byte(tmp_path):
    members = season() + [(u"Fonts/SYNTH.TTF", b"not a font")]
    archive = make_7z(tmp_path / "Season 1 [JPN].7z", members)
    into = tmp_path / "out"
    found = archives.extract(archive, into)
    _assert_season_came_out(found, members, into)
    assert sorted(os.listdir(str(into))) == sorted(m.path.name for m in found.members)


def test_a_stored_rar_is_extracted_byte_for_byte_when_a_tool_is_present(tmp_path, rar_gate_open):
    members = [(u"Season 1\\Show - 01.srt", srt_bytes(1, "shift_jis")),
               (u"Season 1\\Show - 02.ass", ass_bytes(2)),
               (u"第03話.srt", srt_bytes(3, bom=True))]
    archive = make_rar3(tmp_path / "Season 1.rar", members)
    into = tmp_path / "out"
    found = archives.extract(archive, into)
    assert [(m.name, m.path.read_bytes()) for m in found.members] == [
        (name.replace(u"\\", u"/"), data) for name, data in members]


@pytest.mark.parametrize("fmt", ["zip", "7z", "rar"])
def test_bytes_out_equal_bytes_in_shift_jis_bom_and_line_endings_kept(tmp_path, fmt, rar_gate_open):
    members = [(u"sjis - 01.srt", srt_bytes(1, "shift_jis")),
               (u"bom crlf - 02.srt", srt_bytes(2, bom=True, newline=u"\r\n")),
               (u"lf - 03.ass", ass_bytes(3).replace(b"\r\n", b"\n")),
               (u"utf16 - 04.srt", srt_bytes(4, "utf-16"))]
    if fmt == "zip":
        archive = make_zip(tmp_path / "a.zip", members)
    elif fmt == "7z":
        archive = make_7z(tmp_path / "a.7z", members)
    else:
        archive = make_rar3(tmp_path / "a.rar", members)
    found = archives.extract(archive, tmp_path / "out")
    for (name, data), member in zip(members, found.members):
        got = member.path.read_bytes()
        assert got == data, "%s changed on the way out (%d bytes in, %d out, first difference at %s) "\
            "-- a subtitle must never be decoded or re-encoded" % (
                name, len(data), len(got), next((i for i, (a, b) in enumerate(zip(data, got)) if a != b),
                                                min(len(data), len(got))))


# ---------------------------------------------------------------------------
# 🚨 zip-slip: the WHOLE archive, before any member is read
# ---------------------------------------------------------------------------

SLIPS = [
    ("parent", u"../../evil.srt"),
    ("parent-backslash", u"..\\..\\evil.srt"),
    ("parent-inside", u"Season 1/../../../evil.srt"),
    ("absolute", u"/tmp/evil.srt"),
    ("absolute-backslash", u"\\Windows\\evil.srt"),
    ("drive", u"C:\\evil.srt"),
    ("drive-relative", u"C:evil.srt"),
    ("drive-inside", u"Season 1/D:/evil.srt"),
    ("unc", u"\\\\server\\share\\evil.srt"),
    ("dots-and-space", u".. /evil.srt"),
    ("nul", u"evil.exe\x00.srt"),
    ("directory", u"../../evil/"),
]


@pytest.mark.parametrize("label, evil", SLIPS, ids=[s[0] for s in SLIPS])
def test_zip_slip_refuses_the_whole_archive_before_any_member_is_read(tmp_path, reads, label, evil):
    archive = make_zip(tmp_path / "slip.zip", [(u"Season 1/Show - 01.srt", srt_bytes(1)),
                                                (u"Season 1/Show - 02.srt", srt_bytes(2)),
                                                (named(evil), b"evil payload")])
    into = tmp_path / "a" / "b" / "out"
    before = tree(tmp_path)
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, into)
    reason = caught.value.reason
    assert "whole archive is refused" in reason and "evil" in reason, reason
    assert reads["zip"] == 0, (
        "%d member stream(s) were opened before '%s' was refused -- the check must run over the "
        "whole listing BEFORE anything is read, not while extracting" % (reads["zip"], evil))
    assert tree(tmp_path) == before, "a refused archive left something behind: %s" % (
        sorted(set(tree(tmp_path)) - set(before)))


def test_a_traversal_hidden_in_a_junk_member_still_refuses_the_whole_archive(tmp_path, reads):
    archive = make_zip(tmp_path / "slip.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                (u"../../evil.dll", b"MZ not a subtitle")])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "evil.dll" in caught.value.reason and "whole archive" in caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


def test_dots_inside_a_real_name_are_not_a_traversal(tmp_path):
    # Shapes measured in jimaku's catalogue 2026-09-17: 761 real names carry '..' -- e.g.
    # "The Disastrous Life of Saiki K..S02E23.WEBRip.Netflix.ja[cc].srt". Synthetic twins:
    names = [u"Synthetic Show K..S02E23.WEBRip.ja[cc].srt", u"Show - 03 「待って...」.ass",
             u"Vol..2/Show - 04.srt", u"...Show - 05.srt", u"Show - 06 [TV]..srt"]
    members = [(name, srt_bytes(i)) for i, name in enumerate(names, 1)]
    found = archives.extract(make_zip(tmp_path / "dots.zip", members), tmp_path / "out")
    assert [m.name for m in found.members] == names, (
        "a real name with dots inside it was refused or lost -- '..' is a traversal only as a "
        "whole path part")


def test_a_7z_traversal_member_refuses_the_whole_archive_before_unpacking(tmp_path, reads):
    archive = make_7z(tmp_path / "slip.7z", [(u"Show - 01.srt", srt_bytes(1)),
                                             (u"placeholder.srt", b"evil payload")],
                      rename={u"placeholder.srt": u"../../evil.srt"})
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "'../../evil.srt'" in caught.value.reason and "whole archive" in caught.value.reason
    assert reads["7z"] == 0 and not (tmp_path / "out").exists()


def test_a_rar_traversal_member_refuses_the_whole_archive_before_any_read(tmp_path, reads,
                                                                           rar_gate_open):
    archive = make_rar3(tmp_path / "slip.rar", [(u"Show - 01.srt", srt_bytes(1)),
                                                (u"..\\..\\evil.srt", b"evil payload")])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "'../../evil.srt'" in caught.value.reason and "whole archive" in caught.value.reason
    assert reads["rar"] == 0 and not (tmp_path / "out").exists()


def _zip_with_link(path):
    link = zipfile.ZipInfo(u"Show - 02.srt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    return make_zip(path, [(u"Show - 01.srt", srt_bytes(1)), (link, b"../../../outside.srt")])


@pytest.mark.parametrize("fmt", ["zip", "7z", "rar"])
def test_a_link_member_refuses_the_whole_archive(tmp_path, reads, rar_gate_open, fmt):
    if fmt == "zip":
        archive = _zip_with_link(tmp_path / "link.zip")
    elif fmt == "7z":
        archive = make_7z(tmp_path / "link.7z", [(u"Show - 01.srt", srt_bytes(1)),
                                                 (u"Show - 02.srt", b"../../../outside.srt")],
                          symlinks=(u"Show - 02.srt",))
    else:
        archive = make_rar3(tmp_path / "link.rar", [
            (u"Show - 01.srt", srt_bytes(1)),
            (u"Show - 02.srt", b"../../../outside.srt", RAR_UNIX, stat.S_IFLNK | 0o777, 0)])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "'Show - 02.srt' is a link" in caught.value.reason, caught.value.reason
    assert sum(reads.values()) == 0 and not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# bombs: declared sizes up front, ACTUAL bytes while writing
# ---------------------------------------------------------------------------

def test_a_member_declaring_more_than_the_per_file_cap_is_refused_before_it_is_read(tmp_path, reads):
    # Between the two caps, so the total cap cannot be what stops it.
    declared = archives.MAX_MEMBER_BYTES + 1
    assert declared <= archives.MAX_TOTAL_BYTES
    archive = make_zip(tmp_path / "bomb.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                (u"bomb.srt", srt_bytes(2))], zipfile.ZIP_STORED)
    patch_zip(archive, {u"bomb.srt": {"usize": declared}})
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    reason = caught.value.reason
    assert "'bomb.srt' declares" in reason and "per-file cap" in reason, reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


def test_members_declaring_more_than_the_total_cap_are_refused_before_any_is_read(tmp_path, reads):
    each = archives.MAX_MEMBER_BYTES                  # at the per-file cap, never over it
    count = archives.MAX_TOTAL_BYTES // each + 1
    names = [u"Show - %02d.srt" % i for i in range(1, count + 1)]
    archive = make_zip(tmp_path / "bomb.zip", [(n, srt_bytes(i)) for i, n in enumerate(names, 1)],
                       zipfile.ZIP_STORED)
    patch_zip(archive, dict((n, {"usize": each}) for n in names))
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "declare" in caught.value.reason and "in all" in caught.value.reason, caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


def test_more_entries_than_the_cap_is_refused_before_any_is_read(tmp_path, reads, monkeypatch):
    monkeypatch.setattr(archives, "MAX_MEMBERS", 20)
    members = [(u"Show - %02d.srt" % i, srt_bytes(i)) for i in range(1, 22)]
    archive = make_zip(tmp_path / "many.zip", members)
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "21 entries" in caught.value.reason and "20-entry cap" in caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


def test_a_header_that_understates_a_member_cannot_carry_it_past_the_per_file_cap(
        tmp_path, monkeypatch, disk):
    monkeypatch.setattr(archives, "MAX_MEMBER_BYTES", 1 * MiB)
    monkeypatch.setattr(archives, "MAX_TOTAL_BYTES", 64 * MiB)
    archive = make_zip(tmp_path / "liar.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                (u"Show - 02.srt", srt_bytes(2))])
    lying_open(monkeypatch, u"Show - 02.srt", b"\0" * (8 * MiB))
    into = tmp_path / "out"
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, into)
    reason = caught.value.reason
    assert "'Show - 02.srt' passed the 1.0 MB per-file cap" in reason, reason
    assert disk["most_in_one_file"] <= 1 * MiB, (
        "%d bytes of one member reached the disk past a 1 MiB cap -- the cap must be checked on "
        "the bytes as they arrive, not only on the header" % disk["most_in_one_file"])
    assert not into.exists(), "the aborted extraction left %s" % tree(into)


def test_a_header_that_understates_members_cannot_carry_them_past_the_total_cap(
        tmp_path, monkeypatch, disk):
    monkeypatch.setattr(archives, "MAX_MEMBER_BYTES", 64 * MiB)
    monkeypatch.setattr(archives, "MAX_TOTAL_BYTES", 1 * MiB)
    archive = make_zip(tmp_path / "liar.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                (u"Show - 02.srt", srt_bytes(2))])
    lying_open(monkeypatch, u"Show - 02.srt", b"\0" * (8 * MiB))
    into = tmp_path / "out"
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, into)
    assert "passed the 1.0 MB cap" in caught.value.reason, caught.value.reason
    assert disk["written"] <= 1 * MiB, "%d bytes written past a 1 MiB total cap" % disk["written"]
    assert not into.exists()


def test_a_lying_zip_header_aborts_and_removes_what_was_already_extracted(tmp_path, disk):
    # A REAL archive: the bomb member's header says 100 bytes for 1 MiB of deflated data.
    members = [(u"Show - %02d.srt" % i, srt_bytes(i)) for i in (1, 2, 3)]
    archive = make_zip(tmp_path / "liar.zip", members + [(u"Show - 04.srt", b"A" * MiB)])
    patch_zip(archive, {u"Show - 04.srt": {"usize": 100}})
    into = tmp_path / "out"
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, into)
    assert "Show - 04.srt" in caught.value.reason, caught.value.reason
    assert disk["opened"] >= 4 and disk["written"] >= sum(len(d) for _, d in members), (
        "the first three members were never written, so this cannot show they were removed")
    assert not into.exists(), "a failed extraction left its partial output: %s" % tree(into)


def _extract_in_a_thread(archive, into, seconds):
    """-> (still running?, {"found"|"raised": ...}). A daemon thread, so a HANG fails the
    check after `seconds` instead of hanging the suite."""
    result = {}

    def run():
        try:
            result["found"] = archives.extract(archive, into)
        except BaseException as exc:
            result["raised"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    return worker.is_alive(), result


# Measured 2026-09-17: with an overstated member these three make py7zr spin for ever;
# LZMA1, LZMA2, BZip2, ZStandard and PPMd raise on their own.
STALLING_CODERS = {"copy": [{"id": py7zr.FILTER_COPY}],
                   "deflate": [{"id": py7zr.FILTER_DEFLATE}],
                   "x86+copy": [{"id": py7zr.FILTER_X86}, {"id": py7zr.FILTER_COPY}]}
CODERS = {"copy": [{"id": py7zr.FILTER_COPY}], "deflate": [{"id": py7zr.FILTER_DEFLATE}],
          "bzip2": [{"id": py7zr.FILTER_BZIP2}], "lzma2": [{"id": py7zr.FILTER_LZMA2, "preset": 7}],
          "zstd": [{"id": py7zr.FILTER_ZSTD}], "ppmd": [{"id": py7zr.FILTER_PPMD}]}


@pytest.mark.parametrize("coder", sorted(STALLING_CODERS))
def test_a_7z_that_promises_more_than_its_data_holds_is_refused_not_a_hang(tmp_path, coder):
    archive = make_7z_overstated(tmp_path / "stall.7z", [(u"Show - 01.srt", srt_bytes(1))],
                                 STALLING_CODERS[coder], extra=5000)
    into = tmp_path / "out"
    alive, result = _extract_in_a_thread(archive, into, 30)
    assert not alive, (
        "extract() was still unpacking a %s .7z after 30 s -- py7zr spins for ever on a header that "
        "overstates a member, and a scheduled run would hold its lock the whole time" % coder)
    raised = result.get("raised")
    assert isinstance(raised, archives.ArchiveError) and raised.reason == archives.STALLED, (
        repr(raised) if raised is not None else "extract returned %r" % result.get("found"))
    assert not into.exists(), "the stalled extraction left %s" % tree(into)


@pytest.mark.parametrize("coder", sorted(CODERS))
def test_every_7z_coder_unpacks_a_large_member_whole_through_the_stall_guard(tmp_path, coder):
    big = b"".join(srt_bytes(i % 100) for i in range(25000))[:2 * MiB + 7]   # > py7zr's 1 MiB read
    members = [(u"Show - 01.srt", big), (u"Show - 02.srt", srt_bytes(2))]
    archive = make_7z(tmp_path / "big.7z", members, filters=CODERS[coder])
    found = archives.extract(archive, tmp_path / "out")
    assert [(m.name, m.path.read_bytes()) for m in found.members] == members, (
        "a valid %s .7z did not come out whole" % coder)


def test_a_py7zr_without_the_internals_the_stall_guard_needs_unpacks_nothing(tmp_path, monkeypatch):
    archive = make_7z(tmp_path / "s.7z", [(u"Show - 01.srt", srt_bytes(1))])
    monkeypatch.delattr(py7zr_core.Worker, "decompress")
    with pytest.raises(archives.ArchiveUnsupported) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "stalled .7z" in caught.value.reason, caught.value.reason
    assert not (tmp_path / "out").exists()


def test_a_member_shorter_than_its_header_is_damage_not_a_subtitle(tmp_path):
    archive = make_zip(tmp_path / "short.zip", [(u"Show - 01.srt", srt_bytes(1))], zipfile.ZIP_STORED)
    patch_zip(archive, {u"Show - 01.srt": {"usize": 5000}})
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "declared 5000" in caught.value.reason and "damaged" in caught.value.reason, (
        caught.value.reason)
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# nested archives, junk, empties
# ---------------------------------------------------------------------------

def test_a_nested_archive_is_skipped_and_never_unpacked(tmp_path):
    hidden = b"HIDDEN-INNER-SUBTITLE-BYTES"
    inner_zip = make_zip(tmp_path / "inner.zip", [(u"Hidden - 99.srt", hidden)]).read_bytes()
    inner_7z = make_7z(tmp_path / "inner.7z", [(u"Hidden - 98.srt", hidden)]).read_bytes()
    archive = make_zip(tmp_path / "outer.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                 (u"extras/Season 2.zip", inner_zip),
                                                 (u"bonus.7z", inner_7z),
                                                 (u"old.RAR", RAR_SIGNATURES["rar3"])])
    into = tmp_path / "out"
    found = archives.extract(archive, into)
    assert [m.name for m in found.members] == [u"Show - 01.srt"]
    assert found.skipped == [(u"extras/Season 2.zip", archives.NESTED),
                             (u"bonus.7z", archives.NESTED), (u"old.RAR", archives.NESTED)]
    assert os.listdir(str(into)) == [u"Show - 01.srt"], (
        "a nested archive reached the root: %s" % os.listdir(str(into)))
    for path in into.rglob("*"):
        assert hidden not in path.read_bytes(), "the inner archive was unpacked into %s" % path


def test_an_archive_holding_only_a_nested_archive_is_an_error(tmp_path, reads):
    inner = make_zip(tmp_path / "inner.zip", [(u"Show - 01.srt", srt_bytes(1))]).read_bytes()
    archive = make_zip(tmp_path / "outer.zip", [(u"Season 1.zip", inner), (u"Fonts/a.ttf", b"x")])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert caught.value.reason.startswith(archives.NESTED), caught.value.reason
    assert "Season 1.zip" in caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


def test_junk_is_ignored_listed_as_skipped_and_never_written(tmp_path):
    junk = [(u"Fonts/SYNTH.TTF", b"font"), (u"readme.txt", b"read me"), (u"cover.jpg", b"\xff\xd8"),
            (u"Show - 01.mkv", b"\x1aE\xdf\xa3"), (u"release.nfo", b"nfo")]
    archive = make_zip(tmp_path / "junk.zip", [(u"Show - 01.ass", ass_bytes(1))] + junk)
    into = tmp_path / "out"
    found = archives.extract(archive, into)
    assert [m.name for m in found.members] == [u"Show - 01.ass"]
    assert found.skipped == [(name, archives.NOT_A_SUBTITLE) for name, _ in junk]
    assert found.notes == [], "junk is ignored SILENTLY (06 §5) -- skipped is its only report: %s" % (
        found.notes)
    assert os.listdir(str(into)) == [u"Show - 01.ass"], "junk was written: %s" % os.listdir(str(into))


def test_an_empty_subtitle_is_skipped_and_a_directory_is_not_a_member(tmp_path):
    archive = make_zip(tmp_path / "e.zip", [(u"Season 1/", b""), (u"Season 1/Show - 01.srt", srt_bytes(1)),
                                             (u"Season 1/Show - 02.srt", b"")])
    into = tmp_path / "out"
    found = archives.extract(archive, into)
    assert [m.name for m in found.members] == [u"Season 1/Show - 01.srt"]
    assert found.skipped == [(u"Season 1/Show - 02.srt", archives.EMPTY_MEMBER)]
    assert os.listdir(str(into)) == [u"Show - 01.srt"], "a zero-byte subtitle was written"


def test_an_archive_with_no_subtitle_at_all_is_an_error_not_an_empty_success(tmp_path):
    archive = make_zip(tmp_path / "fonts.zip", [(u"Fonts/a.ttf", b"x"), (u"Fonts/b.ttf", b"y")])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert caught.value.reason == "no subtitle in the archive -- 2 files skipped"
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(make_zip(tmp_path / "empty.zip", []), tmp_path / "out")
    assert caught.value.reason == "the archive is empty"


# ---------------------------------------------------------------------------
# .rar with no tool: a SKIP, never a crash, never "broken"
# ---------------------------------------------------------------------------

def _a_rar_tool_is_installed():
    try:
        rarfile.tool_setup(force=True)
        return True
    except rarfile.RarCannotExec:
        return False


def _assert_skipped_for_no_tool(caught, into):
    assert not isinstance(caught.value, archives.ArchiveError), (
        "a missing tool must never read as a broken archive")
    reason = caught.value.reason
    assert "unrar" in reason.lower() and "install" in reason.lower(), reason
    assert not into.exists()


@pytest.mark.parametrize("version", sorted(RAR_SIGNATURES))
def test_a_rar_with_no_unrar_tool_is_skipped_with_a_reason_never_a_crash(tmp_path, version):
    """The branch REALLY reachable on this machine (no unrar/unar/7z/bsdtar on PATH,
    measured 2026-09-17): rarfile.tool_setup() raises RarCannotExec before the bytes are
    parsed. A file carrying only a RAR signature reaches it through the real detection."""
    if _a_rar_tool_is_installed():
        pytest.skip("a RAR tool IS installed here, so the real no-tool branch is unreachable on "
                    "this machine -- the forced-absence check below covers it")
    archive = tmp_path / "Season 1.rar"
    archive.write_bytes(RAR_SIGNATURES[version])
    into = tmp_path / "out"
    with pytest.raises(archives.ArchiveUnsupported) as caught:
        archives.extract(archive, into)
    _assert_skipped_for_no_tool(caught, into)


@pytest.mark.parametrize("what", ["signature only", "a valid stored archive", "named .zip"])
def test_a_rar_with_every_tool_missing_is_skipped_on_any_machine(tmp_path, no_rar_tool, reads, what):
    if what == "signature only":
        archive = tmp_path / "Season 1.rar"
        archive.write_bytes(RAR_SIGNATURES["rar3"])
    elif what == "a valid stored archive":
        archive = make_rar3(tmp_path / "Season 1.rar", [(u"Show - 01.srt", srt_bytes(1))])
    else:
        archive = make_rar3(tmp_path / "Season 1.zip", [(u"Show - 01.srt", srt_bytes(1))])
    into = tmp_path / "out"
    with pytest.raises(archives.ArchiveUnsupported) as caught:
        archives.extract(archive, into)
    _assert_skipped_for_no_tool(caught, into)
    assert reads["rar"] == 0


# ---------------------------------------------------------------------------
# what a file IS, from its bytes
# ---------------------------------------------------------------------------

def test_a_7z_named_zip_is_read_as_a_7z(tmp_path):
    members = [(u"Show - 01.srt", srt_bytes(1))]
    archive = make_7z(tmp_path / "Season 1.zip", members)
    found = archives.extract(archive, tmp_path / "out")
    assert [(m.name, m.path.read_bytes()) for m in found.members] == members


@pytest.mark.parametrize("page", [b"<!DOCTYPE html>\n<html><head><title>404</title></head></html>",
                                  b"\xef\xbb\xbf  \r\n<html lang=\"ja\"><body>error</body></html>"])
def test_an_html_page_named_zip_is_an_error_not_an_archive(tmp_path, page):
    archive = tmp_path / "Season 1.zip"
    archive.write_bytes(page)
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "HTML page" in caught.value.reason, caught.value.reason
    assert not (tmp_path / "out").exists()


def test_an_empty_or_unrecognised_file_is_an_error(tmp_path):
    empty = tmp_path / "empty.zip"
    empty.write_bytes(b"")
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(empty, tmp_path / "out")
    assert "empty" in caught.value.reason
    text = tmp_path / "subtitle.7z"
    text.write_bytes(ass_bytes(1))
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(text, tmp_path / "out")
    assert caught.value.reason.startswith("not a zip, 7z or rar archive"), caught.value.reason


def test_a_corrupt_zip_is_an_error_naming_what_the_reader_said(tmp_path):
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"PK\x03\x04" + b"\0" * 64)
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert caught.value.reason.startswith("could not be read as a zip archive -- BadZipFile"), (
        caught.value.reason)


@pytest.mark.parametrize("name, expected", [
    (u"Season 1 [JPN].zip", True), (u"Season 1 [JPN].7Z", True), (u"old.RAR", True),
    (u"Show - 01.ass", False), (u"Show.7z.ass", False), (u"zip", False), (u"Show.part1.rar", True)])
def test_is_archive_is_a_name_test(name, expected):
    assert archives.is_archive(name) is expected
    assert archives.is_archive(Path(name)) is expected


# ---------------------------------------------------------------------------
# names: zip readings, safe_name, collisions, duplicates
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    sys.version_info[:2] >= (3, 13), strict=True,
    reason=(
        "🚨 UNRESOLVED, AND DELIBERATELY NOT HIDDEN. Fails on Python 3.13 on "
        "ALL THREE operating systems and passes on 3.10-3.12 -- measured across "
        "the public repo's CI matrix, 2026-09-17. So it is a 3.13 behaviour "
        "change in `zipfile`, not a platform issue. ⛔ WHICH SIDE IS BROKEN IS "
        "NOT YET KNOWN: either 3.13 changed how an unflagged name is decoded "
        "(a real defect for 3.13 users of hato/archives.py), or it broke the "
        "RawName helper this check uses to force raw cp932 bytes into the "
        "archive (a harness issue). ⚠ It cannot be settled from the dev machine "
        "-- that is Python 3.10. "
        "⭐ `strict=True` ON PURPOSE: if this starts passing, THAT is reported "
        "too, so the marker cannot go quietly stale. hato's classifiers claim "
        "only 3.10, so nothing is promised about 3.13 while this stands."))
def test_a_cp932_name_without_the_utf8_flag_is_read_as_shift_jis(tmp_path):
    # ソ and 表 end in byte 0x5C -- a backslash to anything reading the name as cp437.
    name = u"ソード 第01話 表.srt"
    entry = RawName(u"placeholder")
    entry.raw = name.encode("cp932")
    found = archives.extract(make_zip(tmp_path / "sjis.zip", [(entry, srt_bytes(1, "shift_jis"))]),
                             tmp_path / "out")
    assert [m.name for m in found.members] == [name], (
        "an unflagged cp932 name came out as %r" % [m.name for m in found.members])
    assert found.members[0].path.name == cache.safe_name(name)
    assert found.notes == ["1 file name was read as Shift-JIS (cp932) -- the archive did not say "
                           "which encoding it used."], found.notes


def test_a_utf8_flagged_name_is_never_re_read(tmp_path):
    # Read as cp437 bytes and then cp932, 'é' + 'm' is the valid pair 0x82 0x6D -> 'Ｎ'.
    name = u"Pokémon - 01.ass"
    found = archives.extract(make_zip(tmp_path / "flagged.zip", [(name, ass_bytes(1))]),
                             tmp_path / "out")
    assert [m.name for m in found.members] == [name], (
        "a UTF-8-flagged name was re-read: %r" % [m.name for m in found.members])
    assert found.notes == []


def test_a_utf8_name_without_the_flag_is_read_as_utf8_not_as_cp932(tmp_path):
    # Its UTF-8 bytes ALSO decode as cp932, into "縺ｲ繧峨′縺ｪ" -- so the order is visible.
    name = u"ひらがな 01.srt"
    entry = RawName(u"placeholder")
    entry.raw = name.encode("utf-8")
    found = archives.extract(make_zip(tmp_path / "mac.zip", [(entry, srt_bytes(1))]), tmp_path / "out")
    assert [m.name for m in found.members] == [name], (
        "an unflagged UTF-8 name came out as %r" % [m.name for m in found.members])


def test_windows_illegal_characters_in_a_member_name_become_fullwidth_twins_on_disk(tmp_path):
    name = u'Re:Zero? - 01 <JPN> "v2" * |final|.ass'
    found = archives.extract(make_zip(tmp_path / "linux.zip", [(name, ass_bytes(1))]), tmp_path / "out")
    member = found.members[0]
    assert member.name == name, "Member.name must keep the name in the archive"
    assert member.path.name == u"Re：Zero？ - 01 ＜JPN＞ ＂v2＂ ＊ ｜final｜.ass", member.path.name
    assert member.path.read_bytes() == ass_bytes(1)
    assert found.notes == ["1 file was saved under a different name -- to be Windows-safe, or to "
                           "keep two same-named files apart."], found.notes


def test_members_whose_names_collide_on_disk_are_all_kept_none_overwritten(tmp_path):
    members = [(u"S1/Show - 01.ass", ass_bytes(1)), (u"S2/Show - 01.ass", ass_bytes(2)),
               (u"S3/SHOW - 01.ASS", ass_bytes(3))]
    into = tmp_path / "out"
    found = archives.extract(make_zip(tmp_path / "c.zip", members), into)
    assert [(m.name, m.path.read_bytes()) for m in found.members] == members, (
        "a member was lost or overwritten by another with the same name on disk")
    names = [m.path.name for m in found.members]
    assert len(set(n.casefold() for n in names)) == 3, names
    assert all(m.path.parent == into for m in found.members)
    assert sorted(os.listdir(str(into))) == sorted(names)


def test_two_members_with_the_same_name_are_refused_as_ambiguous(tmp_path, reads):
    archive = make_zip(tmp_path / "dup.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                               (u"Show - 01.srt", srt_bytes(99))])
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "both named 'Show - 01.srt'" in caught.value.reason, caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# passwords, methods, missing libraries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["zip", "7z", "7z-header", "rar"])
def test_a_password_protected_archive_is_an_error_and_nothing_is_read(tmp_path, reads, rar_gate_open, fmt):
    if fmt == "zip":
        archive = make_zip(tmp_path / "pw.zip", [(u"Show - 01.srt", srt_bytes(1))], zipfile.ZIP_STORED)
        patch_zip(archive, {u"Show - 01.srt": {"flags_or": 0x1}})
        expected = "member 'Show - 01.srt' is password-protected, and hato has no password to give it"
    elif fmt == "7z":
        archive = make_7z(tmp_path / "pw.7z", [(u"Show - 01.srt", srt_bytes(1))], password="synthetic")
        expected = archives.PASSWORD
    elif fmt == "7z-header":
        archive = make_7z(tmp_path / "pw.7z", [(u"Show - 01.srt", srt_bytes(1))], password="synthetic",
                          header_encryption=True)
        expected = archives.PASSWORD
    else:
        archive = make_rar3(tmp_path / "pw.rar", [(u"Show - 01.srt", srt_bytes(1), RAR_MSDOS, 0x20, 0x0004)])
        expected = archives.PASSWORD
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(archive, tmp_path / "out")
    assert caught.value.reason == expected, caught.value.reason
    assert sum(reads.values()) == 0 and not (tmp_path / "out").exists()


def test_a_compression_method_zipfile_cannot_unpack_is_a_skip_not_an_error(tmp_path, reads):
    archive = make_zip(tmp_path / "d64.zip", [(u"Show - 01.srt", srt_bytes(1))], zipfile.ZIP_STORED)
    patch_zip(archive, {u"Show - 01.srt": {"method": 9}})          # Deflate64
    with pytest.raises(archives.ArchiveUnsupported) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "deflate64" in caught.value.reason and "7-Zip" in caught.value.reason, caught.value.reason
    assert reads["zip"] == 0 and not (tmp_path / "out").exists()


@pytest.mark.parametrize("library", ["py7zr", "rarfile"])
def test_a_missing_library_is_a_skip_naming_it_not_a_crash(tmp_path, monkeypatch, library):
    if library == "py7zr":
        archive = make_7z(tmp_path / "s.7z", [(u"Show - 01.srt", srt_bytes(1))])
    else:
        archive = make_rar3(tmp_path / "s.rar", [(u"Show - 01.srt", srt_bytes(1))])
    monkeypatch.setitem(sys.modules, library, None)                # `import` now raises
    with pytest.raises(archives.ArchiveUnsupported) as caught:
        archives.extract(archive, tmp_path / "out")
    assert "pip install %s" % library in caught.value.reason, caught.value.reason
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# the root, and failures that leave nothing
# ---------------------------------------------------------------------------

def test_into_must_be_an_empty_folder_or_not_exist_yet(tmp_path, reads):
    archive = make_zip(tmp_path / "s.zip", [(u"Show - 01.srt", srt_bytes(1))])
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "theirs.txt").write_bytes(b"not ours")
    with pytest.raises(ValueError):
        archives.extract(archive, busy)
    assert os.listdir(str(busy)) == ["theirs.txt"] and (busy / "theirs.txt").read_bytes() == b"not ours"
    a_file = tmp_path / "a file"
    a_file.write_bytes(b"x")
    with pytest.raises(ValueError):
        archives.extract(archive, a_file)
    assert reads["zip"] == 0
    deep = tmp_path / "new" / "deeper" / "out"
    found = archives.extract(archive, deep)
    assert found.root == deep and os.listdir(str(deep)) == [u"Show - 01.srt"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert [m.name for m in archives.extract(archive, empty).members] == [u"Show - 01.srt"]


def _crc_broken_zip(path):
    members = [(u"Show - %02d.srt" % i, srt_bytes(i)) for i in (1, 2, 3)]
    archive = make_zip(path, members, zipfile.ZIP_STORED)
    data = bytearray(archive.read_bytes())
    at = data.find(srt_bytes(3))
    data[at + 5] ^= 0xFF                                    # the third member's body, not its header
    archive.write_bytes(bytes(data))
    return archive


def test_a_failure_after_the_root_was_created_removes_the_root_and_its_new_parents(tmp_path):
    into = tmp_path / "new" / "deeper" / "out"
    with pytest.raises(archives.ArchiveError) as caught:
        archives.extract(_crc_broken_zip(tmp_path / "crc.zip"), into)
    assert "Show - 03.srt" in caught.value.reason and "CRC" in caught.value.reason, caught.value.reason
    assert not (tmp_path / "new").exists(), "the failure left folders it created: %s" % tree(tmp_path / "new")


def test_a_failure_in_an_existing_empty_root_leaves_it_empty_and_in_place(tmp_path):
    into = tmp_path / "workdir"
    into.mkdir()
    with pytest.raises(archives.ArchiveError):
        archives.extract(_crc_broken_zip(tmp_path / "crc.zip"), into)
    assert into.is_dir() and os.listdir(str(into)) == []


def test_ctrl_c_mid_member_removes_everything_and_propagates(tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "s.zip", [(u"Show - %02d.srt" % i, srt_bytes(i)) for i in (1, 2, 3)])

    class Interrupted(io.BytesIO):
        def read(self, *args):
            raise KeyboardInterrupt()

    lying_open(monkeypatch, u"Show - 02.srt", lambda: Interrupted(b""))
    into = tmp_path / "out"
    with pytest.raises(KeyboardInterrupt):
        archives.extract(archive, into)
    assert not into.exists(), "Ctrl-C left %s" % tree(into)


@pytest.mark.parametrize("fmt", ["zip", "7z"])
def test_a_full_disk_is_the_OSError_itself_and_leaves_nothing(tmp_path, disk, fmt):
    members = [(u"Show - %02d.srt" % i, srt_bytes(i) * 50) for i in (1, 2, 3)]
    if fmt == "zip":
        archive = make_zip(tmp_path / "s.zip", members)
    else:
        archive = make_7z(tmp_path / "s.7z", members)

    def full(tap, data):
        if disk["written"] >= len(members[0][1]):
            raise OSError(28, "No space left on device (simulated)")

    disk["before_write"] = full
    into = tmp_path / "out"
    with pytest.raises(OSError) as caught:
        archives.extract(archive, into)
    assert caught.value.errno == 28, (
        "a full disk came out as %s: %s -- hato's own disk failing is not damage in the archive"
        % (type(caught.value).__name__, caught.value))
    assert disk["written"] >= len(members[0][1]), "the simulated full disk never happened"
    assert not into.exists(), "a full disk left %s" % tree(into)


# ---------------------------------------------------------------------------
# `hato extract`
# ---------------------------------------------------------------------------

def _parse(argv):
    parser = argparse.ArgumentParser(prog="hato extract")
    extract_cmd.register(parser)
    return parser.parse_args(argv)


def _work_folders(store):
    work = store / "cache" / "work"
    return sorted(os.listdir(str(work))) if work.is_dir() else []


def test_the_extract_command_has_the_shape_the_cli_loads():
    assert extract_cmd.__doc__.strip().splitlines()[0] == (
        "Unpack one .zip, .7z or .rar into the working cache and list what came out.")
    with pytest.raises(SystemExit):
        _parse([])                                          # the archive is required


def test_hato_extract_lists_members_and_the_root_in_the_working_cache(tmp_path, monkeypatch, capsys):
    store = tmp_path / "store"
    monkeypatch.setenv("HATO_CACHE", str(store))
    members = season(6) + [(u"Fonts/SYNTH.TTF", b"font"), (u"extras.zip", b"PK\x05\x06" + b"\0" * 18)]
    archive = make_7z(tmp_path / "Season 1 [JPN].7z", members)
    assert extract_cmd.run(_parse([str(archive)])) == 0
    out = capsys.readouterr().out
    folders = _work_folders(store)
    assert len(folders) == 1, "expected one extraction folder under the cache's work/, found %s" % folders
    root = store / "cache" / "work" / folders[0]
    assert ("root         %s\n" % root) in out, "the root line does not name %s:\n%s" % (root, out)
    subtitles = [name for name, _ in members if name.endswith((".ass", ".srt"))]
    for name in subtitles:
        assert name in out, "%s is not listed:\n%s" % (name, out)
    assert "subtitles    %d · " % len(subtitles) in out, out
    assert "skipped      2" in out and archives.NESTED in out and archives.NOT_A_SUBTITLE in out, out
    assert sorted(os.listdir(str(root))) == sorted(cache.safe_name(basename(n)) for n in subtitles), (
        "the listing does not match what is in %s" % root)
    assert str(tmp_path / "Season 1 [JPN].7z") in out


def test_hato_extract_into_a_folder_the_user_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    archive = make_zip(tmp_path / "s.zip", [(u"Show - 01.srt", srt_bytes(1))])
    into = tmp_path / "mine"
    assert extract_cmd.run(_parse([str(archive), "--into", str(into)])) == 0
    out = capsys.readouterr().out
    assert ("root         %s\n" % into) in out and "working cache" not in out, out
    assert os.listdir(str(into)) == [u"Show - 01.srt"]
    assert _work_folders(tmp_path / "store") == []


@pytest.mark.parametrize("case", ["traversal", "fails part-way"])
def test_hato_extract_on_a_refused_archive_exits_1_and_leaves_no_folder(tmp_path, monkeypatch, capsys, case):
    store = tmp_path / "store"
    monkeypatch.setenv("HATO_CACHE", str(store))
    if case == "traversal":
        archive = make_zip(tmp_path / "slip.zip", [(u"Show - 01.srt", srt_bytes(1)),
                                                    (u"../../evil.srt", b"evil")])
    else:
        archive = _crc_broken_zip(tmp_path / "crc.zip")
    assert extract_cmd.run(_parse([str(archive)])) == 1
    out = capsys.readouterr().out
    assert "\nERROR        " in out and "nothing was extracted" in out, out
    if case == "traversal":
        assert "'../../evil.srt'" in out and "path traversal" in out, out
    assert _work_folders(store) == [], "a refused archive left %s in the cache" % _work_folders(store)


def test_hato_extract_on_a_rar_with_no_tool_says_skipped_and_names_unrar(tmp_path, monkeypatch, capsys,
                                                                        no_rar_tool):
    store = tmp_path / "store"
    monkeypatch.setenv("HATO_CACHE", str(store))
    archive = tmp_path / "Season 1.rar"
    archive.write_bytes(RAR_SIGNATURES["rar5"])
    assert extract_cmd.run(_parse([str(archive)])) == 1
    out = capsys.readouterr().out
    assert "\nSKIPPED      " in out and "unrar" in out.lower() and "nothing was extracted" in out, out
    assert _work_folders(store) == []


def test_hato_extract_refuses_a_folder_that_is_not_empty_as_a_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    archive = make_zip(tmp_path / "s.zip", [(u"Show - 01.srt", srt_bytes(1))])
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "theirs.txt").write_bytes(b"x")
    assert extract_cmd.run(_parse([str(archive), "--into", str(busy)])) == 2
    assert "not empty" in capsys.readouterr().err
    assert os.listdir(str(busy)) == ["theirs.txt"]


def test_hato_extract_prints_control_characters_in_names_escaped_never_raw(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    archive = make_zip(tmp_path / "esc.zip", [(u"Show\x1b[2J - 01.srt", srt_bytes(1)),
                                               (u"notes31m.txt", b"junk"),
                                               (u"Show - 02\x7f.srt", srt_bytes(2))])
    assert extract_cmd.run(_parse([str(archive)])) == 0
    out = capsys.readouterr().out
    raw = [ch for ch in out if ord(ch) < 32 and ch not in "\n" or 0x7f <= ord(ch) < 0xa0]
    assert not raw, "raw control characters reached the terminal: %r" % sorted(set(raw))
    for shown in (u"Show\\x1b[2J - 01.srt", u"notes\\x9b31m.txt", u"Show - 02\\x7f.srt"):
        assert shown in out, "%r is not in the output, escaped:\n%s" % (shown, out)


def test_hato_extract_on_a_missing_archive_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "store"))
    assert extract_cmd.run(_parse([str(tmp_path / "nope.zip")])) == 1
    out = capsys.readouterr().out
    assert "cannot be read" in out and "nothing was extracted" in out, out
