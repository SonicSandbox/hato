# -*- coding: utf-8 -*-
"""
The jimaku API key. Read at runtime; never stored, printed, logged or copied.

    key = resolve_key()        # -> Key, or raises KeyMissing saying what to do
    key.hint                   # "…ab12" -- the ONLY part that may ever be shown
    key.source                 # "HATO_JIMAKU_KEY" | "HATO_KEYFILE: <path>" | ...
    key.reveal()               # the raw value, for the Authorization header ONLY
    save_key_from(src)         # copy a key into <root>/key.txt -> (Key, Path)

Order (RUNBOOK 1c): $HATO_JIMAKU_KEY, then the key FILE -- $HATO_KEYFILE, then
`<root>/key.txt`, then the source tree's keystore path. The file's LAST non-empty
line is the key; the lines above it are documentation.

⭐ `<root>/key.txt` IS THE ANSWER TO "where does a stranger's key go" (the open
question in spec/05-interface.md §The window). It is a plain file in per-user app
data, owner-only where the OS has permissions, and the window writes it through
`save_key_from` -- the same code, so the two can never disagree.

🚨 THE KEY IS NEVER IN config.toml, NEVER IN A LOG, NEVER IN AN ERROR MESSAGE.
Every raise below names the PATH and what to do, never the value; `hato config`
refuses a key-shaped field outright; and nothing here writes anywhere but
`paths.key_file_path()`.

🚨 THE VALUE CANNOT BE PRINTED BY ACCIDENT. `repr`, `str` and `format` all return
the hint. A log line, an f-string or a traceback that includes the object shows
four characters, never the key -- a structural guard, because "never print it" as
a rule is exactly the kind that gets broken by someone who has just read it
(doctrine/robustness).
"""
import os
from pathlib import Path

from hato import paths

#: What `--set-from` writes above the key, so the file explains itself to whoever
#: opens it next. ⚠ The key is the LAST line; everything above it is documentation.
_FILE_HEADER = (
    "# hato's jimaku API key. Get one at https://jimaku.cc/account -> Developer Access.\n"
    "# The key is the LAST non-empty line of this file; lines above it are notes.\n"
    "# Never commit this file, never paste it into config.toml.\n")


class KeyMissing(Exception):
    """No usable key. The message names where it looked and what would fix it."""


class Key(object):
    __slots__ = ("_value", "source")

    def __init__(self, value, source):
        self._value = value
        self.source = source

    def reveal(self):
        """The raw key. ⛔ For the Authorization header and nothing else."""
        return self._value

    @property
    def hint(self):
        tail = self._value[-4:] if len(self._value) >= 4 else ""
        return u"…" + tail if tail else u"(shorter than 4 characters)"

    def __repr__(self):
        return "<jimaku key from %s, ending %s>" % (self.source, self.hint)

    __str__ = __repr__

    def __format__(self, spec):
        return repr(self)

    def __reduce__(self):
        # Pickling would carry the value into whatever file or process gets it.
        raise TypeError("a jimaku key is never serialised")


def read_key_file(path):
    """The key on the LAST non-empty line of `path`. -> str, or raise KeyMissing.

    ⛔ Every message names the path and nothing else -- a refusal that echoed the
    line back would put the key in a terminal, a log and a bug report at once.
    """
    try:
        # utf-8-sig: a key file saved by Notepad carries a BOM, and it must
        # not become part of anything.
        with open(str(path), encoding="utf-8-sig") as fh:
            lines = [ln.strip() for ln in fh.read().splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        raise KeyMissing("The key file %s could not be read: %s" % (path, exc))
    if not lines:
        raise KeyMissing("The key file %s is empty. The key goes on its last "
                         "line." % path)
    value = lines[-1]
    if value.startswith("#"):
        raise KeyMissing(
            "The last line of %s looks like a comment, not a key. The key goes "
            "on the LAST line; documentation goes above it." % path)
    return value


def _a_repository(folder):
    """-> what KIND of git repository `folder` is, or None.

    ⚠ `.git` covers a working tree, and it may be a FILE as well as a directory
    (a linked worktree or a submodule writes `gitdir: ...` into one), which is why
    this is `.exists()` and not `.is_dir()`.

    🚨 But a repository does not have to have one. A BARE repository -- what a
    `--bare` clone, a Gitea/GitHub server-side repo and `git init --bare` all
    produce -- IS the git directory: `HEAD`, `objects/` and `refs/` sit at its
    top level and there is no `.git` entry anywhere. Looking only for `.git`
    accepted the write (measured 2026-09-17), and "a secret must never be inside
    a repository" is not a statement about layouts.
    """
    if (folder / ".git").exists():
        return "a git working tree"
    if ((folder / "HEAD").is_file() and (folder / "objects").is_dir()
            and (folder / "refs").is_dir()):
        return "a BARE git repository (HEAD + objects/ + refs/, no .git entry)"
    return None


def _refuse_a_repo(destination):
    """⛔ Never write a secret inside a git repository.

    LEDGER-HOT.md's first rule, made structural: TheForge auto-commits every ~5
    minutes and git history has no undo, so a key.txt written under a checkout --
    a HATO_CACHE pointed at the vault, a portable install inside a repo -- is
    published before anyone notices. One walk up the parents, and it cannot happen.
    """
    for folder in [destination.parent] + list(destination.parent.parents):
        kind = _a_repository(folder)
        if kind is not None:
            raise KeyMissing(
                "Refusing to write the key to %s: %s is %s, and a "
                "secret inside one is committed and pushed before anyone notices "
                "(git history has no undo). Point HATO_CACHE at a folder outside "
                "every repository, or set $HATO_JIMAKU_KEY instead."
                % (destination, folder, kind))


def _owner_only(path):
    """Owner-only permissions, where the OS has them. -> True when applied.

    ⚠ POSIX only. Windows' file mode is a read-only flag, not an ACL: chmod there
    would make the file READ-ONLY without making it private, which is worse than
    doing nothing because it reads as protection. Windows' per-user
    %LOCALAPPDATA% is the protection that actually applies.
    """
    if os.name == "nt":
        return False
    os.chmod(str(path), 0o600)
    return True


def check_key_value(value):
    """A raw key string -> the cleaned key, or raise KeyMissing.

    ⭐ THE SAME SENTENCES `read_key_file` USES, BECAUSE THERE ARE NOW TWO ROADS
    IN (RUNBOOK 7a): a file, and stdin from the window's key field. A refusal
    the file gives and the pipe does not is the "two roads into one setting"
    defect LEDGER.md §data records -- one validator, so they cannot disagree.

    ⛔ Every message names what is wrong and never echoes the value. A refusal
    that quoted the line back would put the key in a terminal, a log and a bug
    report at once.
    """
    cleaned = (value or u"").strip()
    if not cleaned:
        raise KeyMissing("No key was given. Get one at https://jimaku.cc/account "
                         "-> Developer Access.")
    if cleaned.startswith("#"):
        raise KeyMissing("That looks like a comment, not a key. Paste the key "
                         "itself from https://jimaku.cc/account -> Developer "
                         "Access.")
    if len(cleaned.splitlines()) > 1:
        raise KeyMissing("A key is one line, and %d were given. Paste just the "
                         "key." % len(cleaned.splitlines()))
    if any(ch.isspace() for ch in cleaned):
        raise KeyMissing("That key has a space in it, so it is probably a "
                         "sentence or a copied label rather than the key.")
    return cleaned


def save_key_value(value, destination=None):
    """Put a key STRING into <root>/key.txt. -> (Key, Path).

    ⭐ THE NON-FILE ROAD (RUNBOOK 7a). `--set-from` takes a path, so the window's
    key field would have had to write the secret to a temp file before hato
    would take it -- a SECOND copy of the key on disk, against LEDGER-HOT.md's
    first rule. The key's final home is a file either way; what this removes is
    the temporary one.

    🚨 TEMP-PLUS-RENAME, AND OWNER-ONLY BEFORE THE BYTES (LEDGER-HOT.md). The temp
    file is created with mode 0600 by `os.open`, so the key is never readable by
    anyone else even for the instant between write and chmod -- and `open(path,'w')`
    on the destination would truncate an existing, working key file the moment it
    opened, losing it if the write then raised.
    """
    destination = Path(paths.key_file_path() if destination is None else destination)
    value = check_key_value(value)                  # validated BEFORE anything is written
    return _write_key(value, destination)


def save_key_from(source, destination=None):
    """Copy the key out of `source` into <root>/key.txt. -> (Key, Path)."""
    source = Path(source)
    destination = Path(paths.key_file_path() if destination is None else destination)
    if not source.is_file():
        raise KeyMissing("No key file at %s. Save the key from "
                         "https://jimaku.cc/account -> Developer Access to a text "
                         "file first, then point --set-from at it." % source)
    if source.resolve() == destination.resolve():
        raise KeyMissing("%s is already hato's key file -- nothing to copy."
                         % destination)
    value = read_key_file(source)                      # validated BEFORE anything is written
    return _write_key(value, destination)


def _write_key(value, destination):
    """The shared write. ⛔ Both roads land here; neither has its own copy."""
    _refuse_a_repo(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".new-%d" % os.getpid())
    try:
        handle = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_FILE_HEADER)
            fh.write(value + "\n")
        _owner_only(temp)
        os.replace(str(temp), str(destination))
    finally:
        if temp.exists():
            try:
                temp.unlink()               # a failed write leaves NOTHING behind
            except OSError:
                pass
    _owner_only(destination)
    return Key(value, "%s: %s" % ("key.txt in hato's data folder", destination)), destination


def resolve_key(start=None):
    """-> Key, or raise KeyMissing."""
    env = os.environ.get("HATO_JIMAKU_KEY")
    if env is not None:
        value = env.strip()
        if not value:
            raise KeyMissing(
                "HATO_JIMAKU_KEY is set but empty. Unset it to use the key "
                "file, or set it to the key from https://jimaku.cc/account.")
        return Key(value, "HATO_JIMAKU_KEY")

    path, source = paths.keystore_file(start)
    if path is None:
        raise KeyMissing(
            "No jimaku key: %s. Set HATO_JIMAKU_KEY, or HATO_KEYFILE to a file "
            "whose last line is the key (https://jimaku.cc/account -> "
            "Developer Access)." % source)
    if not path.is_file():
        raise KeyMissing(
            "No jimaku key: the key file %s does not exist (from %s). Put the "
            "key on the last line of that file (`hato key --set-from <file>` "
            "does it for you), or set HATO_JIMAKU_KEY." % (path, source))
    return Key(read_key_file(path), "%s: %s" % (source, path))
