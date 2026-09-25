# -*- coding: utf-8 -*-
"""
Archive extraction -- one .zip, .7z or .rar into ONE folder the caller names, and
nothing anywhere else (spec/06-edge-cases.md §5, RUNBOOK 3c).

    ARCHIVE_EXTS, is_archive(name)      a NAME test; what a file IS comes from its bytes
    extract(archive_path, into)         -> Extraction(root, members, skipped, notes)
    ArchiveError(reason)                refused, damaged, or not an archive -- an ERROR
    ArchiveUnsupported(reason)          nothing here can read it -- SKIP the candidate

THE ORDER IS THE GUARANTEE. Everything that can refuse an archive runs over its
LISTING, before one byte of any member is read:

    1. sniff the first bytes: a 7z named .zip is a 7z, an HTML error page is an ERROR
    2. list every member -- headers only
    3. ⛔ refuse the WHOLE archive if ANY member, subtitle or junk, climbs out of the
       root ('..', or a dots-and-spaces spelling Windows may read as one), is absolute,
       names a drive or a UNC share, carries a NUL, or is a link; if the listing holds
       more than MAX_MEMBERS entries; or if the DECLARED sizes pass a cap
    4. choose the subtitles; junk and nested archives are skipped, and say so
    5. only then write -- counting ACTUAL bytes against the same caps as they arrive

🚨 ZIP-SLIP REJECTS THE ENTRY OUTRIGHT (LEDGER-HOT.md), not member by member. A member
that escapes the root is an attack on user-uploaded content, and an archive carrying
one is trusted for nothing else.

⛔ EVERY EXTRACTED FILE IS A DIRECT CHILD OF THE ROOT, named through cache.safe_name.
The member's path inside the archive stays in Member.name; on disk the tree is
flattened, so no directory is ever created from archive data and no name can resolve
anywhere but the root. That is a second wall behind step 3, never a substitute for it.

🚨 BYTES OUT EQUAL BYTES IN. A member is copied, never decoded: Shift-JIS stays
Shift-JIS, a BOM stays, CRLF stays (LEDGER-HOT.md: never re-encode a subtitle).

🚨 A FAILURE LEAVES NOTHING. Each member is written under a temp name and renamed when
whole; any failure -- a cap, a CRC error, Ctrl-C, a full disk -- removes every file
this call wrote, and the root too if this call created it.

THE CAPS, from jimaku's own catalogue (238,250 files, measured 2026-09-17): the largest
file of ANY kind is 16.3 MiB, a .7z; the largest loose .ass is 15.3 MiB and the largest
.srt 503 KiB. zipfile, py7zr 1.1.3 and rarfile 4.5 all stop reading a member at its
declared size (measured the same day), so the running count is what holds the caps if
a library -- or a future version of one -- ever does not.

    MAX_MEMBER_BYTES    64 MiB   4x the largest real subtitle
    MAX_TOTAL_BYTES    512 MiB   31x the largest real archive -- room for LZMA's 5-10x on text
    MAX_MEMBERS         10,000   entries of every kind, directories included

🚨 A .7z THAT STALLS IS AN ERROR, NOT A HANG. py7zr spins for ever on a header that
promises more than a COPY, Deflate or BCJ member holds (measured 2026-09-17), which in a
scheduled run is a lock held for ever; _guard_stalls stops the loop from inside.

⛔ FAIL CLOSED. Anything a library raises on hostile or damaged bytes becomes an
ArchiveError naming it, never a crash -- except a missing tool or library, and a
compression method nothing here can unpack, which are ArchiveUnsupported: "install
unrar" must never read as "the archive is broken". An OSError from OUR OWN writes (a
full or read-only disk) is not the archive's fault and leaves as that OSError, after
the cleanup.
"""
import contextlib
import hashlib
import os
import re
import stat as _stat
import sys
import uuid
import zipfile
from pathlib import Path

from hato import cache
from hato.commands.cache import human_bytes

#: What `is_archive` answers for -- a name test only.
ARCHIVE_EXTS = (".zip", ".7z", ".rar")
#: What gets extracted. Everything else in an archive is junk, skipped by name.
SUBTITLE_EXTS = (".ass", ".ssa", ".srt", ".vtt", ".sub", ".idx", ".sup")

MiB = 1024 * 1024
#: One member, declared or actually unpacked.
MAX_MEMBER_BYTES = 64 * MiB
#: Every member together -- declared (junk included: a solid 7z unpacks junk to reach a
#: subtitle) and actually written.
MAX_TOTAL_BYTES = 512 * MiB
#: Entries in the listing, of every kind.
MAX_MEMBERS = 10000

#: The reasons in Extraction.skipped.
NOT_A_SUBTITLE = "not a subtitle"
NESTED = "nested archive, not extracted"
EMPTY_MEMBER = "empty file"

NO_RAR_TOOL = ("a .rar can only be unpacked by an external tool, and none is installed here "
               "(looked for unrar, unar, 7z, 7zz and bsdtar) -- install UnRAR from "
               "https://www.rarlab.com/rar_add.htm, put it on PATH, and run again")
NO_RARFILE = ("reading a .rar needs the rarfile package, which is not installed -- "
              "pip install rarfile")
NO_PY7ZR = ("reading a .7z needs the py7zr package, which is not installed -- "
            "pip install py7zr")
PASSWORD = "the archive is password-protected, and hato has no password to give it"

_CHUNK = 64 * 1024
_FILE, _DIR, _LINK = "file", "dir", "link"
_UTF8_FLAG = 0x800
_ENCRYPTED_FLAG = 0x1
_ZIP_METHODS = frozenset([zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED,
                          zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
_DRIVE = re.compile(r"^[A-Za-z]:")
_MAGIC = ((b"PK\x03\x04", "zip"), (b"PK\x05\x06", "zip"), (b"PK\x07\x08", "zip"),
          (b"7z\xbc\xaf\x27\x1c", "7z"), (b"Rar!\x1a\x07", "rar"))
_HTML = (b"<!doctype", b"<html", b"<head", b"<body", b"<?xml")


# ---------------------------------------------------------------------------
# the public shape
# ---------------------------------------------------------------------------

class ArchiveError(Exception):
    """The archive could not be read or extracted, or it was refused: a member that
    escapes the root, a link, a cap, only a nested archive, damage. An ERROR."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


class ArchiveUnsupported(Exception):
    """Nothing on this machine can read it -- no unrar tool, no py7zr, a compression
    method no library here unpacks. The candidate is SKIPPED with this reason; the
    archive itself may be perfectly good. ⛔ Deliberately NOT an ArchiveError."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


class Member(object):
    """One extracted subtitle. `name` is its path inside the archive, '/'-separated
    (a zip name decoded as described in _zip_name); `path` the file on disk, a direct
    child of the root; `size` its bytes."""

    __slots__ = ("name", "path", "size")

    def __init__(self, name, path, size):
        self.name, self.path, self.size = name, path, size

    def __repr__(self):
        return "<Member %r -> %s, %d bytes>" % (self.name, self.path.name, self.size)


class Extraction(object):
    """`root` (Path) · `members` ([Member], subtitles only, in archive order) ·
    `skipped` ([(name, reason)]) · `notes` ([sentence])."""

    __slots__ = ("root", "members", "skipped", "notes")

    def __init__(self, root, members, skipped, notes):
        self.root, self.members, self.skipped, self.notes = root, members, skipped, notes

    def __repr__(self):
        return "<Extraction %d members, %d skipped, in %s>" % (
            len(self.members), len(self.skipped), self.root)


def is_archive(name):
    """True when `name` ends in .zip, .7z or .rar, in any case. ⚠ A NAME test only --
    extract() decides what a file really is from its first bytes."""
    return os.path.splitext(os.fspath(name))[1].lower() in ARCHIVE_EXTS


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def extract(archive_path, into):
    """Unpack the subtitles in `archive_path` into the folder `into` -> Extraction.

    `into` must be an empty folder, or not exist yet (it is created, parents too).
    ⛔ Nothing is written anywhere else. Raises ArchiveError, ArchiveUnsupported,
    ValueError for an `into` that is a file or not empty, and OSError for a disk that
    will not take the files -- in every case after removing whatever this call wrote.
    """
    archive_path = os.fspath(archive_path)
    root = Path(os.path.abspath(os.fspath(into)))
    _require_usable_root(root)
    kind = _sniff(archive_path)
    arc = _READERS[kind](archive_path)
    try:
        with _reading(kind):
            entries = arc.entries()
        _refuse_unsafe(entries)          # ⛔ EVERY member, before anything is written
        plan = _plan(entries, root)
        files = _Files(root)
        try:
            files.make_root()
            members = arc.write(plan, files)
        except _DiskFailure as exc:
            files.discard()
            raise exc.error from None
        except BaseException:
            files.discard()
            raise
    finally:
        arc.close()
    return Extraction(root, members, plan.skipped, arc.notes + plan.notes)


def _require_usable_root(root):
    if not root.exists():
        return
    if not root.is_dir():
        raise ValueError("%s is a file, not a folder to extract into" % root)
    if any(True for _ in root.iterdir()):
        raise ValueError("%s is not empty -- extraction needs an empty folder, so a refused "
                         "archive can be removed without touching anything else" % root)


def _sniff(path):
    """-> "zip" | "7z" | "rar", from the first bytes, whatever the name says."""
    with open(path, "rb") as fh:
        head = fh.read(512)
    if not head:
        raise ArchiveError("the file is empty (0 bytes), not an archive")
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if head.lstrip(b"\xef\xbb\xbf").lstrip(b" \t\r\n").lower().startswith(_HTML):
        raise ArchiveError("this is an HTML page, not an archive -- the download was "
                           "probably an error page")
    raise ArchiveError("not a zip, 7z or rar archive -- it starts with bytes %s"
                       % head[:4].hex(" "))


# ---------------------------------------------------------------------------
# refusals over the listing
# ---------------------------------------------------------------------------

class _Entry(object):
    """One listing row, the same for every format."""

    __slots__ = ("name", "size", "kind", "ref", "encrypted", "unsupported")

    def __init__(self, name, size, kind, ref, encrypted=False, unsupported=None):
        self.name, self.size, self.kind, self.ref = name, size, kind, ref
        self.encrypted, self.unsupported = encrypted, unsupported


def _parts(name):
    """The path parts of a stored name. Backslash and slash are both separators: an
    archive made on Windows may use either, and Windows honours either."""
    return name.replace(u"\\", u"/").split(u"/")


def _key(name):
    return tuple(p for p in _parts(name) if p not in (u"", u"."))


def _display(name):
    return name.replace(u"\\", u"/")


def _shown(name):
    """A name fit to print: '/'-separated, every control character escaped (C0, DEL and
    C1). ⚠ A member name is uploader-controlled text, and a raw ESC or CSI in it would
    drive the terminal -- or sit in a log -- when it is printed."""
    return u"".join(u"\\x%02x" % ord(ch) if ord(ch) < 32 or 0x7f <= ord(ch) < 0xa0 else ch
                    for ch in _display(name))


def _name_problem(name):
    """-> why a member stored under `name` could land outside the extraction root,
    or None. Judged on the name as hato reads it -- after _zip_name for a zip."""
    if not name.strip():
        return "has no name"
    if u"\x00" in name:
        return "has a NUL byte in its name, a trick to disguise what a file is"
    parts = _parts(name)
    if parts[0] == u"" and len(parts) > 1:
        return "is an absolute path"
    for part in parts:
        if _DRIVE.match(part):
            return "names a drive (%s)" % part[:2]
        if part.count(u".") >= 2 and not part.strip(u". "):
            return "climbs out of the extraction folder ('%s')" % part
    return None


def unsafe_name(name):
    """-> why an archive member stored under `name` could land outside its root, or
    None. ⭐ PUBLIC, AND THE ONE COPY: the update's program zip (RUNBOOK 11c) is
    judged by these same rules as a subtitle archive -- a second copy would drift."""
    return _name_problem(name)


def _refuse_unsafe(entries):
    """⛔ Every refusal that must happen before ANY member is read -- over EVERY entry,
    junk and directories included."""
    if len(entries) > MAX_MEMBERS:
        raise ArchiveError("it lists %s entries, over the %s-entry cap -- a zip bomb, or not "
                           "a subtitle archive" % (format(len(entries), ","),
                                                   format(MAX_MEMBERS, ",")))
    for entry in entries:
        problem = _name_problem(entry.name)
        if problem:
            raise ArchiveError("member '%s' %s, so the whole archive is refused (path "
                               "traversal)" % (_shown(entry.name), problem))
        if entry.kind == _LINK:
            raise ArchiveError("member '%s' is a link, which can point outside the extraction "
                               "folder, so the whole archive is refused" % _shown(entry.name))
    declared = 0
    for entry in entries:
        if entry.kind != _FILE:
            continue
        if entry.size > MAX_MEMBER_BYTES:
            raise ArchiveError("member '%s' declares %s, over the %s per-file cap"
                               % (_shown(entry.name), human_bytes(entry.size),
                                  human_bytes(MAX_MEMBER_BYTES)))
        declared += entry.size
    if declared > MAX_TOTAL_BYTES:
        raise ArchiveError("its members declare %s in all, over the %s cap"
                           % (human_bytes(declared), human_bytes(MAX_TOTAL_BYTES)))


# ---------------------------------------------------------------------------
# what to extract, and under which names
# ---------------------------------------------------------------------------

class _Item(object):
    __slots__ = ("entry", "target")

    def __init__(self, entry):
        self.entry, self.target = entry, None


class _Plan(object):
    def __init__(self):
        self.wanted, self.skipped, self.notes = [], [], []

    def skip(self, entry, reason):
        self.skipped.append((_display(entry.name), reason))


def _plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def _plan(entries, root):
    plan = _Plan()
    seen = set()
    for entry in entries:
        key = _key(entry.name)
        if entry.kind != _FILE or not key:
            continue                        # directories are structure, not members
        if key in seen:
            raise ArchiveError("two members are both named '%s', so which one is meant is "
                               "ambiguous -- refused" % _shown(entry.name))
        seen.add(key)
        ext = os.path.splitext(key[-1])[1].lower()
        if ext in ARCHIVE_EXTS:
            plan.skip(entry, NESTED)
        elif ext not in SUBTITLE_EXTS:
            plan.skip(entry, NOT_A_SUBTITLE)
        elif entry.size == 0:
            plan.skip(entry, EMPTY_MEMBER)
        else:
            plan.wanted.append(_Item(entry))

    for item in plan.wanted:
        if item.entry.encrypted:
            raise ArchiveError("member '%s' is password-protected, and hato has no password "
                               "to give it" % _shown(item.entry.name))
        if item.entry.unsupported:
            raise ArchiveUnsupported("member '%s' %s" % (_shown(item.entry.name),
                                                         item.entry.unsupported))

    if not plan.wanted:
        nested = [name for name, reason in plan.skipped if reason == NESTED]
        if nested:
            raise ArchiveError("%s -- the archive holds no subtitle of its own, only another "
                               "archive ('%s'), and hato unpacks one level" % (NESTED, nested[0]))
        if plan.skipped:
            raise ArchiveError("no subtitle in the archive -- %s skipped"
                               % _plural(len(plan.skipped), "file", "files"))
        raise ArchiveError("the archive is empty")

    _name_targets(plan.wanted, _name_budget(root))

    # Notes carry only what `skipped` does not: junk is ignored SILENTLY (06 §5) and
    # reported in `skipped` alone -- a note repeating it is the noise that rule forbids.
    renamed = sum(1 for item in plan.wanted if item.target != _key(item.entry.name)[-1])
    if renamed:
        plan.notes.append("%s saved under a different name -- to be Windows-safe, or to keep "
                          "two same-named files apart." % _plural(renamed, "file was", "files were"))
    return plan


def _name_budget(root):
    """The longest filename that keeps root + name inside MAX_PATH on Windows."""
    budget = cache.NAME_MAX
    if os.name == "nt":
        units = len(str(root).encode("utf-16-le", "surrogatepass")) // 2
        budget = min(budget, cache.WIN_PATH_MAX - units - 1)
    return max(budget, cache.NAME_MIN)


def _name_targets(items, budget):
    """Give each member a filename in the root: its own base name through safe_name,
    and a short hash of its archive path when that is already taken. Compared
    case-folded, because NTFS is case-insensitive. ⛔ Never two members on one name."""
    taken = set()
    for item in items:
        base = _key(item.entry.name)[-1]
        target = cache.safe_name(base, max_len=budget)
        n = 0
        while target.casefold() in taken:
            n += 1
            stem, ext = cache._split_ext(base)
            tag = hashlib.sha256((u"%s\x00%d" % (item.entry.name, n)).encode(
                "utf-8", "surrogatepass")).hexdigest()[:8]
            target = cache.safe_name(u"%s~%s%s" % (stem, tag, ext), max_len=budget)
        taken.add(target.casefold())
        item.target = target


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

class _DiskFailure(Exception):
    """An OSError from hato's OWN writes, carried through library code untouched so it
    is never mistaken for damage in the archive."""

    def __init__(self, error):
        Exception.__init__(self, str(error))
        self.error = error


class _Files(object):
    """Everything this extraction has put on disk -- so a failure removes exactly that,
    and nothing else -- and the running byte count against the caps."""

    def __init__(self, root):
        self.root = root
        self.total = 0
        self._paths = []
        self._handles = []
        self._made = []

    def make_root(self):
        missing = []
        here = self.root
        while not here.exists() and here.parent != here:
            missing.append(here)
            here = here.parent
        self._made = missing                    # deepest first -- recorded BEFORE they exist
        if missing:
            os.makedirs(str(self.root))

    def member(self, item):
        return _MemberFile(self, item)

    def create(self, path):
        fh = open(str(path), "xb")
        self._paths.append(path)
        self._handles.append(fh)
        return fh

    def close(self, fh):
        self._handles.remove(fh)
        fh.close()

    def rename(self, tmp, final):
        if os.path.lexists(str(final)):
            raise FileExistsError(17, "refusing to overwrite", str(final))
        os.replace(str(tmp), str(final))
        self._paths[self._paths.index(tmp)] = final

    def take(self, entry, written, n):
        """⛔ Count ACTUAL bytes against the caps BEFORE they reach the disk: a header
        that understates a member must not carry it past a cap."""
        if written + n > MAX_MEMBER_BYTES:
            raise ArchiveError("member '%s' passed the %s per-file cap while it was unpacked, "
                               "though its header declared %s -- aborted"
                               % (_shown(entry.name), human_bytes(MAX_MEMBER_BYTES),
                                  human_bytes(entry.size)))
        if self.total + n > MAX_TOTAL_BYTES:
            raise ArchiveError("unpacking passed the %s cap, more than the headers declared "
                               "-- aborted at member '%s'"
                               % (human_bytes(MAX_TOTAL_BYTES), _shown(entry.name)))
        self.total += n

    def discard(self):
        """Best effort, and it NEVER raises: it runs while another exception is on its
        way out, and must not replace it."""
        for fh in list(self._handles):
            try:
                fh.close()
            except OSError:
                pass
        self._handles = []
        for path in reversed(self._paths):
            try:
                os.chmod(str(path), _stat.S_IWRITE)
                os.unlink(str(path))
            except OSError:
                pass
        self._paths = []
        for folder in self._made:
            try:
                os.rmdir(str(folder))
            except OSError:
                pass
        self._made = []


class _MemberFile(object):
    """One member on its way to disk: a temp name in the root, renamed when whole."""

    def __init__(self, files, item):
        self._files, self._item = files, item
        self.written = 0
        self._tmp = files.root / (".hato-%s.part" % uuid.uuid4().hex)
        try:
            self._fh = files.create(self._tmp)
        except OSError as exc:
            raise _DiskFailure(exc)

    def write(self, chunk):
        n = len(chunk)
        if n:
            self._files.take(self._item.entry, self.written, n)
            try:
                self._fh.write(chunk)           # 🚨 the bytes as they came -- never decoded
            except OSError as exc:
                raise _DiskFailure(exc)
            self.written += n
        return n

    def finish(self):
        entry = self._item.entry
        try:
            self._files.close(self._fh)
        except OSError as exc:
            raise _DiskFailure(exc)
        if self.written != entry.size:
            raise ArchiveError("member '%s' unpacked to %d bytes where its header declared %d "
                               "-- the archive is damaged" % (_shown(entry.name), self.written,
                                                             entry.size))
        final = self._files.root / self._item.target
        try:
            self._files.rename(self._tmp, final)
        except OSError as exc:
            raise _DiskFailure(exc)
        return Member(_display(entry.name), final, self.written)


@contextlib.contextmanager
def _reading(kind):
    """Around every library call on archive bytes. ⛔ FAIL CLOSED: whatever a library
    raises on hostile or damaged input becomes an ArchiveError that names it -- never a
    crash -- save the two things that are this machine's lack, not the archive's fault."""
    try:
        yield
    except (ArchiveError, ArchiveUnsupported, _DiskFailure):
        raise
    except Exception as exc:
        raise _translated(kind, exc) from exc


def _translated(kind, exc):
    rar = sys.modules.get("rarfile")
    if rar is not None and isinstance(exc, rar.RarCannotExec):
        return ArchiveUnsupported(NO_RAR_TOOL)
    seven = sys.modules.get("py7zr")
    if seven is not None and isinstance(exc, seven.UnsupportedCompressionMethodError):
        return ArchiveUnsupported("this .7z uses a compression method py7zr cannot unpack -- "
                                  "unpack it by hand with 7-Zip")
    if type(exc).__name__ == "PasswordRequired":
        return ArchiveError(PASSWORD)
    return ArchiveError("could not be read as a %s archive -- %s: %s"
                        % (kind, type(exc).__name__, exc))


def _close_quietly(stream):
    try:
        stream.close()
    except Exception:
        pass


def _copy_members(arc, plan, files):
    """zip and rar: open each wanted member in turn and copy it through."""
    out = []
    for item in plan.wanted:
        member = files.member(item)
        with _reading(arc.kind):
            src = arc.open(item.entry)
        try:
            while True:
                with _reading(arc.kind):
                    chunk = src.read(_CHUNK)
                if not chunk:
                    break
                member.write(chunk)
        except BaseException:
            _close_quietly(src)
            raise
        with _reading(arc.kind):
            src.close()
        out.append(member.finish())
    return out


# ---------------------------------------------------------------------------
# the three formats
# ---------------------------------------------------------------------------

def _zip_name(info):
    """-> (name, codec): the member's name as its archiver meant it, and the reading
    used ("" when zipfile's own stands).

    zipfile reads a name as UTF-8 only when the entry sets flag 0x800, and as cp437
    otherwise -- but a Japanese Windows archiver writes cp932 with no flag. So an
    UNFLAGGED non-ASCII name goes back to its raw bytes, read as UTF-8 if valid, else
    as cp932 if valid, else left as cp437.
    ⛔ A FLAGGED name is never re-read: the flag is the archiver saying what it wrote.
    ⚠ From orig_filename, never filename: on Windows zipfile turns every backslash into
    '/', and 0x5C is the second byte of ソ, 表, 能 and 十 in cp932.
    ⭐ UTF-8 before cp932, measured 2026-09-17 on jimaku's 238,250 real filenames: of
    114,156 non-ASCII names, the cp932 bytes of NONE are valid UTF-8 -- while the UTF-8
    bytes of 11,529 (10%) also decode as cp932, into mojibake. A macOS or Linux
    archiver writes UTF-8 without the flag.
    """
    name = info.orig_filename
    if info.flag_bits & _UTF8_FLAG:
        return name, ""
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name, ""
    if raw.isascii():
        return name, ""
    for codec in ("utf-8", "cp932"):
        try:
            return raw.decode(codec), codec
        except UnicodeDecodeError:
            pass
    return name, ""


class _Zip(object):
    kind = "zip"

    def __init__(self, path):
        self.notes = []
        with _reading(self.kind):
            self._zf = zipfile.ZipFile(path)

    def close(self):
        _close_quietly(self._zf)

    def entries(self):
        out, reread = [], {}
        for info in self._zf.infolist():
            name, codec = _zip_name(info)
            if codec:
                reread[codec] = reread.get(codec, 0) + 1
            if name.endswith((u"/", u"\\")):
                kind = _DIR
            elif _stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                kind = _LINK
            else:
                kind = _FILE
            unsupported = None
            if info.compress_type not in _ZIP_METHODS:
                unsupported = ("is compressed with %s, which Python's zipfile cannot unpack -- "
                               "unpack the archive by hand with 7-Zip" % zipfile.compressor_names.get(
                                   info.compress_type, "method %d" % info.compress_type))
            out.append(_Entry(name, info.file_size, kind, info,
                              encrypted=bool(info.flag_bits & _ENCRYPTED_FLAG),
                              unsupported=unsupported))
        for codec, n in sorted(reread.items()):
            self.notes.append("%s read as %s -- the archive did not say which encoding it used." % (
                _plural(n, "file name was", "file names were"),
                "Shift-JIS (cp932)" if codec == "cp932" else "UTF-8"))
        return out

    def open(self, entry):
        return self._zf.open(entry.ref)

    def write(self, plan, files):
        return _copy_members(self, plan, files)


#: Consecutive calls on which a 7z decompressor may hand back nothing. py7zr reads up to
#: 1 MiB of packed data per call, so a valid stream would need 64 MiB of input with no
#: output at all to trip this; a stalled one trips it in microseconds.
_STALL_CALLS = 64
STALLED = ("the .7z stopped producing data before its members were whole -- its header "
           "promises more than it holds, so it is refused")
NO_STALL_GUARD = ("this py7zr (%s) no longer has the internals hato uses to stop a stalled .7z, "
                  "so no .7z is unpacked -- update hato")


def _guard_stalls(z):
    """🚨 py7zr 1.1.3 unpacks a member with `while out_remaining > 0`, and when a header
    promises more bytes than the data holds, a COPY, Deflate or BCJ+COPY coder returns
    nothing FOREVER: extract() never returned, measured 2026-09-17 (LZMA1, LZMA2, BZip2,
    ZStandard and PPMd raise instead). A scheduled run would spin with its lock held.
    So this archive's worker hands its loop a decompressor that raises STALLED after
    _STALL_CALLS empty answers in a row -- inside the loop, the only place it can stop.
    ⛔ FAIL CLOSED: a py7zr without these internals unpacks nothing, unguarded."""
    worker = getattr(z, "worker", None)
    original = getattr(worker, "decompress", None)
    if original is None:
        import py7zr
        raise ArchiveUnsupported(NO_STALL_GUARD % getattr(py7zr, "__version__", "unknown version"))

    def decompress(fp, folder, *args, **kwargs):
        return original(fp, _StallFolder(folder), *args, **kwargs)

    worker.decompress = decompress


class _StallFolder(object):
    def __init__(self, folder):
        self._folder = folder

    def get_decompressor(self, *args, **kwargs):
        return _StallGuard(self._folder.get_decompressor(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self._folder, name)


class _StallGuard(object):
    def __init__(self, inner):
        self._inner, self._empty = inner, 0

    def decompress(self, *args, **kwargs):
        out = self._inner.decompress(*args, **kwargs)
        if out:
            self._empty = 0
        else:
            self._empty += 1
            if self._empty >= _STALL_CALLS:
                raise ArchiveError(STALLED)
        return out

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _SevenZip(object):
    kind = "7z"

    def __init__(self, path):
        self.notes = []
        try:
            import py7zr
        except ImportError:
            raise ArchiveUnsupported(NO_PY7ZR)
        # ⚠ A FILE OBJECT, not the path: py7zr then unpacks one folder after another in
        # this thread, instead of in parallel threads that reopen the file.
        self._fh = open(path, "rb")
        try:
            with _reading(self.kind):
                self._z = py7zr.SevenZipFile(self._fh, "r")
        except BaseException:
            self._fh.close()
            raise

    def close(self):
        _close_quietly(self._z)
        _close_quietly(self._fh)

    def entries(self):
        if self._z.needs_password():
            raise ArchiveError(PASSWORD)
        out = []
        for f in self._z.files:
            if f.is_directory:
                kind = _DIR
            elif f.is_symlink or f.is_junction:
                kind = _LINK
            else:
                kind = _FILE
            out.append(_Entry(f.filename, f.uncompressed or 0, kind, f))
        return out

    def write(self, plan, files):
        sinks = _SinkFactory(plan, files)
        _guard_stalls(self._z)
        with _reading(self.kind):
            self._z.extract(targets=[item.entry.ref.filename for item in plan.wanted],
                            factory=sinks)
        return sinks.members()


class _SinkFactory(object):
    """py7zr's WriterFactory, by duck type. py7zr pushes each member's bytes into what
    create() returns, so a .7z is written through the same _MemberFile as zip and rar.
    It is handed the member's stored name (less a leading './'), matched by path parts."""

    def __init__(self, plan, files):
        self._files = files
        self._order = plan.wanted
        self._by_key = dict((_key(item.entry.name), item) for item in plan.wanted)
        self._started = set()
        self._done = {}

    def create(self, filename):
        item = self._by_key.get(_key(filename))
        if item is None or item in self._started:
            raise ArchiveError("the 7z reader produced '%s', which was not planned -- refused"
                               % _shown(filename))
        self._started.add(item)
        return _Sink(self, item, self._files.member(item))

    def finished(self, item, member):
        self._done[item] = member

    def members(self):
        out = []
        for item in self._order:
            if item not in self._done:
                raise ArchiveError("member '%s' is listed but never came out of the archive -- "
                                   "it is damaged" % _shown(item.entry.name))
            out.append(self._done[item])
        return out


class _Sink(object):
    """py7zr's Py7zIO, by duck type. close() is py7zr saying the member came out whole
    and its CRC held; a member that fails never reaches it."""

    def __init__(self, factory, item, member_file):
        self._factory, self._item, self._file = factory, item, member_file
        self._closed = False

    def write(self, data):
        return self._file.write(bytes(data))

    def read(self, size=None):
        return b""

    def seek(self, offset, whence=0):
        return 0

    def flush(self):
        pass

    def size(self):
        return self._file.written

    def close(self):
        if not self._closed:
            self._closed = True
            self._factory.finished(self._item, self._file.finish())


class _Rar(object):
    kind = "rar"

    def __init__(self, path):
        self.notes = []
        try:
            import rarfile
        except ImportError:
            raise ArchiveUnsupported(NO_RARFILE)
        with _reading(self.kind):
            rarfile.tool_setup()        # ⛔ FIRST: no tool is a SKIP, whatever the bytes hold
            self._rf = rarfile.RarFile(path, errors="strict")
        self._file_copy = getattr(rarfile, "RAR5_XREDIR_FILE_COPY", 5)

    def close(self):
        _close_quietly(self._rf)

    def entries(self):
        if self._rf.needs_password():
            raise ArchiveError(PASSWORD)
        out = []
        for info in self._rf.infolist():
            redir = getattr(info, "file_redir", None)
            if info.is_symlink() or (redir and redir[0] != self._file_copy):
                kind = _LINK
            elif info.is_dir():
                kind = _DIR
            else:
                kind = _FILE
            out.append(_Entry(info.filename, info.file_size or 0, kind, info))
        return out

    def open(self, entry):
        return self._rf.open(entry.ref)

    def write(self, plan, files):
        return _copy_members(self, plan, files)


_READERS = {"zip": _Zip, "7z": _SevenZip, "rar": _Rar}
