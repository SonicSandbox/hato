# -*- coding: utf-8 -*-
"""
The working cache -- downloads in flight, refused candidates, extracted archives
(spec/02-data-model.md, RUNBOOK 1a). Disposable, always.

    video_hash(path)       head 64 KiB + tail 64 KiB + size. NEVER the whole video
    content_hash(data)     full sha256 of something small (a subtitle, an archive)
    file_hash(path)        the same, streamed from a file
    safe_name(name)        a jimaku filename Windows accepts, with its shape kept
    Cache(root=None)       <root>/blobs/<h[:2]>/<h>/<name>, temp-plus-rename

🚨 NEVER HASH A WHOLE VIDEO. Hashing a 1.4 GB mkv defeats the entire purpose of a
cache (LEDGER.md §data). `video_hash` reads at most 128 KiB whatever the size, so
a re-run over a folder costs the same for a 2 MB file as for a 2 GB one.

⛔ NEVER BESIDE THE MEDIA. `subsync` dropped a 500 KB `.npy` next to the subtitles
it was reading, inside a corpus marked read-only. Everything here lives under
ONE root -- `paths.cache_dir()`, which HATO_CACHE relocates -- and nothing in this
module takes a destination outside it.

🚨 NEVER TRUNCATE IN PLACE. `open(path, 'w')` truncates the moment it opens; a raise
after that leaves zero bytes (LEDGER-HOT.md -- it destroyed tsubasa's RUNBOOK).
Every byte is written to `<root>/partial/` first and renamed into place, so a
path under `blobs/` either does not exist or holds the whole file.

⚠ A Cache CREATES NOTHING until something is stored. `hato cache --stat` on a
machine that never ran must not leave a folder behind -- and a test asserting
the root must be able to fail before anything is written.
"""
import contextlib
import hashlib
import os
import re
import shutil
import stat as _stat
import uuid
from pathlib import Path

from hato import paths

#: `video_hash` samples this much from EACH end of a video.
CHUNK = 64 * 1024
#: Prefixed to every video hash. ⚠ Bump it if CHUNK or the sampled layout ever
#: changes, so a stored row can never match a hash computed another way.
VIDEO_HASH_VERSION = "v1"

#: One path component. NTFS counts UTF-16 units; ext4 counts UTF-8 bytes. Both
#: are held to 255, so a name that fits here fits everywhere.
NAME_MAX = 255
#: The smallest budget a caller may ask for: a readable stem, a hash suffix and
#: an extension of up to three short tokens must still fit.
NAME_MIN = 48
#: MAX_PATH less its terminating NUL. Honoured on Windows, where a path past it
#: fails unless long paths are switched on -- and other programs may not be.
WIN_PATH_MAX = 259

_BLOCK = 1024 * 1024

#: The nine characters Windows refuses in a filename, and their fullwidth twins
#: -- the mapping jimaku-corpus uses. ⛔ Mapped, never dropped: dropping changes
#: the shape of a release name (`Re:Zero` is not `ReZero`).
WIN_TWINS = {
    u"<": u"＜", u">": u"＞", u":": u"：", u'"': u"＂", u"/": u"／",
    u"\\": u"＼", u"|": u"｜", u"?": u"？", u"*": u"＊",
}
#: Device names Windows resolves whatever the extension: `NUL.ass` IS `NUL`.
_RESERVED = re.compile(u"^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])$",
                       re.IGNORECASE)
#: An extension token worth keeping through a truncation: `ass`, `ja`, `forced`.
_EXT_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,8}$")
_EXT_TOKENS_KEPT = 3
_SUFFIX = re.compile(r"^(\.[A-Za-z0-9_-]{1,8}){0,3}$")


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------

def video_hash(path):
    """-> "v1-<sha256 hex>" over (file size, first 64 KiB, last 64 KiB).

    Reads at most 2 x CHUNK bytes whatever the size; a file no larger than that
    is covered whole. The hash survives a rename (spec/06-edge-cases.md §7) and
    changes when the video is replaced with a different rip.
    """
    # buffering=0: every read below is one read of the file, so what is counted
    # is what is really read -- a buffered reader would read ahead past the head.
    with open(os.fspath(path), "rb", buffering=0) as fh:
        size = os.fstat(fh.fileno()).st_size
        digest = hashlib.sha256(size.to_bytes(8, "little"))
        if size <= 2 * CHUNK:
            digest.update(_read_exactly(fh, size, path))
        else:
            digest.update(_read_exactly(fh, CHUNK, path))
            fh.seek(size - CHUNK)
            digest.update(_read_exactly(fh, CHUNK, path))
    return "%s-%s" % (VIDEO_HASH_VERSION, digest.hexdigest())


def _read_exactly(fh, n, path):
    parts, got = [], 0
    while got < n:
        block = fh.read(n - got)
        if not block:
            raise OSError("%s ended after %d of the %d bytes its size promised -- it "
                          "changed while it was being hashed" % (path, got, n))
        parts.append(block)
        got += len(block)
    return b"".join(parts)


def content_hash(data):
    """-> sha256 hex of every byte of `data`."""
    if isinstance(data, str):
        raise TypeError("content_hash takes bytes -- a str would hash an encoding "
                        "of the text, not the file")
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    """-> sha256 hex of every byte of the file at `path`, read in 1 MiB blocks.

    For subtitles and archives. ⛔ Never a video -- that is `video_hash`.
    """
    digest = hashlib.sha256()
    with open(os.fspath(path), "rb") as fh:
        for block in iter(lambda: fh.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------

def _units(s):
    """UTF-16 code units -- what Windows counts, for a component and for MAX_PATH."""
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def _utf8(s):
    return len(s.encode("utf-8", "surrogatepass"))


def _fits(s, max_len):
    return _units(s) <= max_len and _utf8(s) <= NAME_MAX


def _split_ext(name):
    """-> (stem, ext), ext keeping up to three short trailing tokens, so a
    truncation keeps `.ja.ass` and `.ja.forced.srt` whole."""
    parts = name.split(u".")
    kept = []
    i = len(parts) - 1
    while i >= 1 and len(kept) < _EXT_TOKENS_KEPT and _EXT_TOKEN.match(parts[i]):
        kept.insert(0, parts[i])
        i -= 1
    if not kept:
        return name, u""
    return u".".join(parts[:i + 1]), u"." + u".".join(kept)


def safe_name(name, max_len=NAME_MAX):
    """-> `name` as one filename every filesystem hato runs on will accept.

    - the nine Windows-illegal characters become their FULLWIDTH twins (never dropped)
    - control characters are removed
    - trailing dots and spaces are stripped (Windows strips them silently, so the
      name on disk would differ from the name hato holds)
    - a reserved device name (`CON`, `NUL.ass`) gains a leading `_`
    - an over-long name is cut in its STEM and given `~<8 hex>` from the original
      name, keeping its extension -- `.ja.ass` included -- so two long names that
      differ only past the cut stay distinct

    The result never contains a path separator and is never `.` or `..`, so a
    stored name can never leave its folder. Idempotent.
    """
    if not isinstance(name, str):
        raise TypeError("safe_name takes a str, got %r" % (name,))
    if max_len < NAME_MIN:
        raise ValueError("max_len %d is below %d -- no stem, hash suffix and extension "
                         "fit in that" % (max_len, NAME_MIN))
    max_len = min(max_len, NAME_MAX)

    out = []
    for ch in name:
        twin = WIN_TWINS.get(ch)
        if twin is not None:
            out.append(twin)
        elif ord(ch) >= 32:
            out.append(ch)
    s = u"".join(out).rstrip(u" .")
    if not s:
        s = u"unnamed"
    if _RESERVED.match(s.split(u".", 1)[0].rstrip(u" ")):
        s = u"_" + s
    if _fits(s, max_len):
        return s

    stem, ext = _split_ext(s)
    tag = u"~" + hashlib.sha256(name.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    room_units = max_len - _units(tag + ext)
    room_bytes = NAME_MAX - _utf8(tag + ext)
    kept, units, size = [], 0, 0
    for ch in stem:
        u, b = _units(ch), _utf8(ch)
        if units + u > room_units or size + b > room_bytes:
            break
        kept.append(ch)
        units += u
        size += b
    return u"".join(kept) + tag + ext


# ---------------------------------------------------------------------------
# the cache
# ---------------------------------------------------------------------------

def _holds(path, size):
    try:
        st = os.stat(str(path))
    except OSError:
        return False
    return _stat.S_ISREG(st.st_mode) and st.st_size == size


#: How long after an attempt its file may have been stored. ⚠ A download is
#: stored BEFORE its attempt is recorded, so this only has to absorb a clock
#: that is not quite monotonic -- a re-upload is fetched on a later run.
NAMED_SLACK_SECONDS = 600


def _mtime(path):
    try:
        return os.stat(str(path)).st_mtime
    except OSError:
        return float("inf")


def _epoch_of(moment):
    """A datetime (aware, or naive meaning UTC) or epoch seconds -> seconds, or None."""
    if moment is None or isinstance(moment, bool):
        return None
    if isinstance(moment, (int, float)):
        return float(moment)
    try:
        from datetime import timezone
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    except (AttributeError, ValueError, OverflowError, OSError):
        return None


def _discard_file(path):
    """Best effort, and it NEVER raises -- it runs while another exception is on
    its way out, and must not replace it."""
    try:
        os.unlink(str(path))
    except OSError:
        pass


def _remove_file(path):
    try:
        os.unlink(str(path))
    except FileNotFoundError:
        pass


def _writable_then_retry(func, path, exc_info):
    # An extracted archive can carry read-only members, and Windows refuses to
    # delete a read-only file. Clear the bit and try once more; anything else raises.
    try:
        os.chmod(path, _stat.S_IWRITE)
    except OSError:
        raise exc_info[1]
    func(path)


def _remove_tree(path):
    shutil.rmtree(str(path), onerror=_writable_then_retry)


def _discard_tree(path):
    try:
        _remove_tree(path)
    except OSError:
        pass


class Cache(object):
    """The working cache under one root. Nothing is ever written anywhere else."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else paths.cache_dir()
        #: stored name -> [paths], built on the first `find_named` (S7)
        self._named = None

    def __repr__(self):
        return "<hato Cache at %s>" % self.root

    # -- layout ---------------------------------------------------------------

    def _dir(self, name):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _blob_path(self, digest, name):
        folder = self.root / "blobs" / digest[:2] / digest
        budget = NAME_MAX
        if os.name == "nt":
            budget = min(budget, WIN_PATH_MAX - _units(str(folder)) - 1)
        return folder / safe_name(name, max_len=max(budget, NAME_MIN))

    # -- writes ---------------------------------------------------------------

    def store(self, data, name):
        """-> Path of `data` stored as `name`. Content-addressed and idempotent:
        the same bytes under the same name land on the same path, and a second
        call writes nothing."""
        digest = content_hash(data)
        data = bytes(data)
        final = self._blob_path(digest, name)
        if _holds(final, len(data)):
            return final
        self._place(final, digest, [data])
        return final

    def store_file(self, src, name):
        """-> Path of the file at `src` stored as `name`. `src` is copied, never
        moved; a finished download slot is committed this way."""
        src = os.fspath(src)
        digest = file_hash(src)
        final = self._blob_path(digest, name)
        if _holds(final, os.stat(src).st_size):
            return final
        with open(src, "rb") as fh:
            self._place(final, digest, iter(lambda: fh.read(_BLOCK), b""))
        return final

    def _place(self, final, digest, blocks):
        """Temp-plus-rename. The path under blobs/ never holds a partial file.

        The copy is hashed as it is written and must match `digest` BEFORE the
        rename: a source that changed mid-copy would otherwise be filed under
        a hash that is not its own, and served as that content for ever.
        """
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._dir("partial") / ("%s.tmp" % uuid.uuid4().hex)
        copied = hashlib.sha256()
        try:
            with open(str(tmp), "xb") as fh:
                for block in blocks:
                    copied.update(block)
                    fh.write(block)
                fh.flush()
                os.fsync(fh.fileno())
            if copied.hexdigest() != digest:
                raise OSError("the source changed while it was being stored (hashed %s, "
                              "copied %s) -- nothing was kept"
                              % (digest[:12], copied.hexdigest()[:12]))
            os.replace(str(tmp), str(final))
            # ⚠ The name index is stale the moment the store gains a file: a
            # same-name file stored after it was built made an AMBIGUITY look
            # like one answer (the first run of the S7 index, caught by
            # test_cache's two-candidate check).
            self._named = None
        except BaseException:
            _discard_file(tmp)
            raise

    @contextlib.contextmanager
    def download_slot(self, suffix=""):
        """Yield a fresh, empty `.part` path under <root>/partial/.

        Commit by passing the finished file to `store_file` INSIDE the block.
        The `.part` is removed when the block ends, and if the block raises --
        Ctrl-C included -- it is discarded and the exception goes on its way.
        It is created up front, so an unwritable cache fails BEFORE a request
        is spent on a download it could not keep.
        """
        if not _SUFFIX.match(suffix or ""):
            raise ValueError("suffix %r is not an extension like '.ass' or '.ja.srt'" % (suffix,))
        part = self._dir("partial") / ("%s%s.part" % (uuid.uuid4().hex, suffix or ""))
        with open(str(part), "xb"):
            pass
        try:
            yield part
        except BaseException:
            _discard_file(part)
            raise
        _remove_file(part)

    @contextlib.contextmanager
    def workdir(self, label):
        """Yield a fresh, empty directory under <root>/work/, removed with
        everything in it when the block ends -- including when it raises."""
        base = self._dir("work")
        stem = safe_name(label or "work", max_len=NAME_MIN)
        while True:
            folder = base / ("%s-%s" % (stem, uuid.uuid4().hex[:8]))
            try:
                folder.mkdir()
                break
            except FileExistsError:
                continue
        try:
            yield folder
        except BaseException:
            _discard_tree(folder)
            raise
        _remove_tree(folder)

    # -- reads ----------------------------------------------------------------

    def find(self, digest, name):
        """-> the Path `store(data, name)` put `data` at, or None when it is gone.

        ⭐ RUNBOOK 8b. A refusal remembered in the state DB carries the content
        hash of the file that was downloaded, so the SAME file can be offered to
        a person again tomorrow without asking jimaku for it. ⛔ Nothing is
        written, and a digest that is not a sha256 hex finds nothing rather than
        building a path out of it.
        """
        if not isinstance(digest, str) or not re.match(r"^[0-9a-f]{64}$", digest):
            return None
        path = self._blob_path(digest, name)
        return path if path.is_file() else None

    def find_named(self, name, size, not_after=None):
        """-> the one stored file called `name` whose size is `size`, or None.

        ⚠ FOR ROWS RECORDED BEFORE RUNBOOK 8b, which carry no hash. The name alone
        is not an identity -- a re-upload keeps its name and changes its bytes --
        so the SIZE must agree too (jimaku lists it, and the download is exactly
        it), and two such files are an ambiguity, answered with None rather than
        with a guess.

        `not_after` -- the moment the row was recorded (a datetime or epoch
        seconds). 🚨 A re-timed re-upload keeps its name AND its size (timestamps
        are fixed width), so the one file left in the cache could be a LATER
        download, offered under the old row's verdict (ADVERSARY 2026-09-22 F11).
        The refused file was stored when its attempt ran; a file stored well
        after that is not it.

        ⭐ The store's names are indexed ONCE per `Cache` -- a legacy row per video
        per run used to walk the whole store each time (S7).
        """
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            return None
        if self._named is None:
            self._named = self._index_names()
        limit = _epoch_of(not_after)
        # ⚠ The name AS STORED: `_blob_path` shortens it to the Windows path
        # budget, which is the same for every blob folder (one depth, one digest
        # length) -- so a stand-in digest of that length gives the stored name.
        stored = self._blob_path(u"0" * 64, name).name
        found = [path for path in self._named.get(stored, ())
                 if _holds(path, size)
                 and (limit is None or _mtime(path) <= limit + NAMED_SLACK_SECONDS)]
        return found[0] if len(found) == 1 else None

    def _index_names(self):
        """-> {stored name: [paths]} over every blob. Creates nothing."""
        index = {}
        blobs = self.root / "blobs"
        if not blobs.is_dir():
            return index
        for shard in blobs.iterdir():
            if not shard.is_dir():
                continue
            for folder in shard.iterdir():
                if not folder.is_dir():
                    continue
                for path in folder.iterdir():
                    index.setdefault(path.name, []).append(path)
        return index

    def stat(self):
        """-> {path, exists, bytes, entries, partial, work}. Creates nothing.

        `bytes` is everything on disk under the root; `entries` counts stored
        files; `partial` and `work` are downloads and extractions in flight --
        or left behind by a run that was killed.
        """
        out = {"path": str(self.root), "exists": self.root.is_dir(),
               "bytes": 0, "entries": 0, "partial": 0, "work": 0}
        if not out["exists"]:
            return out
        for dirpath, _dirnames, filenames in os.walk(str(self.root)):
            for fname in filenames:
                try:
                    out["bytes"] += os.lstat(os.path.join(dirpath, fname)).st_size
                except OSError:
                    pass    # gone mid-walk: a run is committing, and this is a snapshot
        blobs = self.root / "blobs"
        if blobs.is_dir():
            out["entries"] = sum(1 for p in blobs.glob("*/*/*") if p.is_file())
        partial = self.root / "partial"
        if partial.is_dir():
            out["partial"] = sum(1 for p in partial.iterdir() if p.is_file())
        work = self.root / "work"
        if work.is_dir():
            out["work"] = sum(1 for p in work.iterdir() if p.is_dir())
        return out
