# -*- coding: utf-8 -*-
u"""Sync hato's shipping tree from the vault into this publish clone.

    python packaging/sync_from_vault.py            # DRY RUN -- says what it would do
    python packaging/sync_from_vault.py --apply     # actually does it

⭐ PUBLISH-BY-COPY. The vault (`TheForge/Workshop/hato/`) is the source of truth
for the paths in COPIED below. Everything else in this clone is CLONE-ONLY and
is edited HERE -- README, LICENCE, pyproject, .github, docs, examples.

🚨 THE VAULT'S GIT HISTORY IS NEVER PUBLISHED. TheForge auto-commits every ~5
minutes, its history is long and noisy and NOT audited for secrets. This clone
began as one fresh commit. Nothing is imported, filtered or subtree-split.

⚠ ANYTHING WRITTEN IN THIS CLONE UNDER A COPIED PATH IS DESTROYED BY THE NEXT
SYNC. Write code and tests in the VAULT. tsubasa learned this by writing its
packaging test in the clone and having to move it.

⚠ A DEV-ONLY FILE IN THE COPY LIST SHIPS IN THE REPO. That is tolerable only
because the installed package never reads it -- `hato.config.json` is the
runner's config, and the same class of file is what broke tsubasa 0.1.0 for
every `pip install` user (PYPI-PUBLISHING-DRAFT P6). It must stay EXCLUDED from
the wheel; `python -m hato.dev audit-wheel` asserts that by name.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):          # Windows defaults to cp1252 and
    sys.stdout.reconfigure(encoding="utf-8")    # raises on Japanese filenames

CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: ⛔ NO ACCOUNT NAME IN A PUBLISHED FILE. This clone is public and the vault
#: is one machine's private layout, so the path is DERIVED from where this
#: clone sits rather than written down. `HATO_VAULT` overrides it outright.
#: Corrected 2026-09-18 after the first 1.0.0 push carried a home directory.
VAULT = os.environ.get("HATO_VAULT") or os.path.normpath(
    os.path.join(CLONE, os.pardir, os.pardir,
                 "TheForge", "Workshop", "hato"))

#: Replaced wholesale on every sync. Order is irrelevant; each is a dir or file.
#:
#: ⭐ THE PACKAGING FILES ARE COPIED, NOT CLONE-ONLY -- a deliberate departure
#: from the sibling project, whose `pyproject.toml` / `LICENSE` / `README.md`
#: are edited in its clone. Here `tests/test_packaging.py` ASSERTS their
#: contents (the dependency list against an ast walk of the source, the licence
#: notices against the dependency list, the canonical GPL text, the classifier
#: register). A clone-only copy would be a second version that the suite never
#: sees -- which is exactly how the sibling's README came to tell every reader
#: to install from a git URL while its own docs said otherwise.
COPIED = [
    "hato",
    "tests",
    "spec",
    # ⭐ THE SCREENSHOTS THE README EMBEDS. Without these the front page ships
    # four dead <img> tags -- and README.md IS copied, so the failure is
    # guaranteed rather than possible. `audit_dirs()` below now refuses a new
    # top-level directory that nobody has filed, which is how this was missed.
    "gui-shots",
    # 🚨 THE BUILD SCRIPTS FOR THE WINDOWS BINARY -- GPL-3.0 Corresponding
    # Source. §1: "the scripts used to control compilation and installation".
    # Ship the exe and withhold these and the release is non-compliant; also
    # nobody but the build machine could reproduce the artifact.
    #
    # ⛔ NAMED FILE BY FILE, NOT AS `packaging/`. This clone's own
    # `packaging/` holds THIS script and its tests, and a copied DIRECTORY is
    # replaced wholesale -- adding the directory would delete the sync tool
    # mid-sync. File entries never prune.
    "packaging/hato.spec",
    "packaging/entry_cli.py",
    "packaging/entry_gui.py",
    "packaging/entry_watch.py",
    # ⭐ hato-update.exe, the swapper (1.0.4, LAYER 11) -- `hato.spec` builds it
    "packaging/entry_update.py",
    "packaging/smoke_standalone.py",
    "packaging/package_standalone.py",
    # ⚠ The launcher a Windows Run key points at. `hato/startup.py` registers
    # it by name; without it, "Start with Windows" from a clone is dead.
    "hato-watch.pyw",
    "hato-gui.cmd",
    ".github",
    "run_tests.py",
    "conftest.py",
    "hato.config.json",
    "hato-run.cmd",
    "pyproject.toml",
    "MANIFEST.in",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_LICENSES.md",
    ".gitignore",
    ".gitattributes",
]

#: ⛔ Root files that are deliberately NOT published, and the written reason.
#: Checked from BOTH ENDS by `audit_copy_list()`: a root file that is neither
#: copied nor named here fails the sync, and a name here that has been added to
#: COPIED fails it too -- so the register can only ever shrink.
#:
#: 🚨 THIS EXISTS BECAUSE A NEW SHIPPING FILE WAS SILENTLY NOT PUBLISHED.
#: `MANIFEST.in` was written in the vault to fix a failing CI job, the sync
#: reported "0 changed" because the name was not in COPIED, and the fix never
#: reached the repository. The sync was not wrong -- it copied exactly what it
#: was told -- but "0 changed" after writing a new file reads as success.
#: ⚠ A copy list is a list of things somebody remembered.
NOT_PUBLISHED = {
    "LEDGER.md":        "internal process history, not an artifact",
    "LEDGER-HOT.md":    "internal process history, not an artifact",
    "HANDOFF.md":       "written for the next agent in this vault",
    "CONTEXT.md":       "vault routing; meaningless outside it",
    "_mutants.mjs":     "imports ../app-kit, a vault-relative path -- it cannot run in a clone",
    "ADVERSARY-2026-09-18.md":
                        "an internal review register, same class as the ledgers",
    "ADVERSARY-2026-09-22.md":
                        "an internal review register, same class as the ledgers",
    "ADVERSARY-2026-09-23.md":
                        "an internal review register, same class as the ledgers",
    "ADVERSARY-2026-09-24.md":
                        "an internal review register, same class as the ledgers",
    "ADVERSARY-2026-09-25.md":
                        "an internal review register, same class as the ledgers",
    "REPORT-DRAFT-2026-09-23.md":
                        "a session's working draft of its report to the owner; vault-only",
}

#: ⛔ Top-level DIRECTORIES that are deliberately not published. Same shape and
#: same rule as `NOT_PUBLISHED`, and checked from both ends by `audit_dirs()`.
#:
#: 🚨 THIS REGISTER EXISTS BECAUSE THE FILE AUDIT WAS BLIND TO DIRECTORIES AND
#: SAID SO IN ITS OWN DOCSTRING: *"a new top-level DIRECTORY is a bigger
#: decision than a forgotten line."* Measured 2026-09-18 -- TWO new top-level
#: directories were added in one day and neither was noticed: `gui-shots`
#: (every image the README embeds) and the vault's `packaging` (the entire
#: Windows build, and its GPL Corresponding Source). The sync would have
#: reported success and published neither.
NOT_PUBLISHED_DIRS = {
    "_runs":         "per-run logs; they carry absolute local paths",
    "mutants":       "the mutation ledger drives vault-only tooling",
    "dist":          "build output, never committed",
    "build":         "build output, never committed",
    "gui-mock":      "the design mock the window was built from; superseded by gui-shots",
    "__pycache__":   "bytecode",
    ".pytest_cache": "test runner scratch",
    ".git":          "this clone has its own history, by design",
    "hato.egg-info": "build metadata",
}

#: ⛔ Never copied. Vault-only.
#:
#: The ledgers, the handoff and the CONTEXT are internal process history, not a
#: published artifact.
#:
#: ⭐ AND THE MUTATION TOOLING IS EXCLUDED FOR A MEASURED REASON, not tidiness:
#: `_mutants.mjs` imports `../app-kit/mutants.mjs`, a VAULT-RELATIVE path that
#: does not exist in this clone, so shipping it would publish a tool that
#: cannot run. Verified 2026-09-17 that neither `run_tests.py` nor
#: `conftest.py` references `mutants/` or app-kit, so the suite is whole
#: without them.
NEVER = {
    "LEDGER.md", "LEDGER-HOT.md", "HANDOFF.md", "CONTEXT.md",
    "_mutants.mjs", "_runs", "mutants", ".pytest_cache", "__pycache__",
}

#: Directory names pruned from anything copied.
PRUNE_DIRS = {"__pycache__", ".pytest_cache", "_runs", "mutants", ".git"}

#: 🚨 Strays that must never reach a public commit. The pattern tsubasa used,
#: plus hato's own. Checked against the STAGED tree, after the copy.
STRAY = re.compile(
    r"(mutbak|\.tmp$|\.orig$|\.rej$|/_runs/|__pycache__|\.egg-info|/build/|/dist/|\.pyc$)"
)

#: 🚨 THE SECRET SCAN IS `hato.dev scan-secrets`, INVOKED -- NOT A REGEX HERE.
#:
#: This file carried its own `SECRETISH` pattern for about an hour. On the first
#: real sync it flagged **70 of 124 files**, starting with this directory's own
#: break-check and its deliberately planted fakes. One of its alternatives
#: matched any `word-word-word` identifier chain, which is most of a Python
#: codebase.
#:
#: ⛔ THAT IS THE DANGEROUS FAILURE, NOT THE HARMLESS ONE. `doctrine/release`:
#: *"A permanently-red check is one people learn to scroll past -- which is
#: exactly how a live data exposure survived here."* A scanner that cries wolf
#: on every run is worse than no scanner, because it consumes the attention the
#: real hit would need.
#:
#: ⭐ And it was re-derivation: `hato/dev/scan.py` already does this, tuned
#: against the real corpus (2 hits in 116 files, both deliberate fakes in
#: tests), searching FIVE byte encodings, unpacking archives, and PROVEN able
#: to fail against a planted key. `doctrine/release`: *"The release tooling is
#: INVOKED, never re-authored per project."*
#:
#: ⚠ `scan-content` is deliberately NOT run over the source tree. It is an
#: ARTIFACT check, and on a source tree it correctly reports the synthetic SRT
#: and WebVTT snippets that `tests/test_archives.py`, `tests/test_cache.py` and
#: `tests/test_devtools.py` build inline as fixtures -- legitimate, ours, and
#: never shipped in a wheel. Measured 2026-09-17: 2 of its 5 claims fail on the
#: tree for exactly that reason.
SCAN_SECRETS = ["-m", "hato.dev", "scan-secrets"]

#: ⭐ THE KNOWN PLANTED FAKES, AND WHY THIS REGISTER EXISTS.
#:
#: `scan-secrets` makes two claims. `key_bytes_absent` -- the real key is not in
#: the tree, in any of five encodings -- is the one that matters, and it is a
#: HARD failure here, always. `no_key_shaped_literal` is a shape heuristic, and
#: it cannot tell a planted fixture from a real leak: the files below contain
#: deliberately fake key-shaped strings whose whole job is to prove the scanner
#: can fail.
#:
#: ⛔ NOT "ignore tests/". That would hide a real key pasted into a test, which
#: is exactly where one would get pasted. The register is (path, field) pairs,
#: so a NEW field or a NEW file is still red -- the ratchet, not an off switch.
#:
#: ⚠ Each entry is a claim that someone LOOKED. If one of these ever stops
#: appearing, delete the line -- a stale exemption is an open door.
#: ⚠ Written with six entries first; the stale-exemption report immediately
#: showed three of them were never there. Over-listing an exemption is the
#: quiet version of switching the check off.
#:
#: 🚨 AND THEN IT HAD THE OPPOSITE PROBLEM, WHICH IS THE WORSE ONE. Until
#: 2026-09-19 this register had three entries and the gate said `3 hit(s), 3
#: known planted fixture(s)` -- over a tree holding EIGHT. It was reading the
#: scanner's sentence, which names only the first three. ⭐ Five literals had
#: never been looked at by anybody, through the entire 1.0.0 release. All five
#: turned out to be synthetic, which is luck, not a process. The five below
#: carry the date they were first actually READ.
KNOWN_SHAPED = {
    # ⭐ This folder's own break-check: one fake value written in each of the
    # four shapes `_KEY_SHAPED` claims to recognise, so every one of them has a
    # case proving it can fire -- plus two it must SKIP. Read 2026-09-19.
    ("packaging/test_sync_audit.py", "api_key"),
    ("packaging/test_sync_audit.py", "jimaku_api_key"),
    ("packaging/test_sync_audit.py", "HATO_JIMAKU_KEY"),
    ("packaging/test_sync_audit.py", "auth_token"),
    ("tests/test_devtools.py", "api_key"),            # R2's planted-secret fixtures
    ("tests/test_devtools.py", "jimaku_api_key"),     #   "
    # ⭐ The same `@pytest.mark.parametrize` list as the two above -- one fake
    # value written five ways, so that each SHAPE the scanner claims to catch
    # has a case proving it can fail. Read 2026-09-19.
    ("tests/test_devtools.py", "HATO_JIMAKU_KEY"),
    ("tests/test_devtools.py", "secret"),
    ("tests/test_devtools.py", "authToken"),
    # ⭐ The probe asserting the test runner STRIPS the key from a child's
    # environment; its value says so in words. Read 2026-09-19.
    ("tests/test_runner.py", "HATO_JIMAKU_KEY"),
    # ⭐ A fake env key for `config --check-key`, proving the env route is read
    # and that only the last four characters are shown. Read 2026-09-19.
    ("tests/test_wiring.py", "HATO_JIMAKU_KEY"),
}

#: ⭐ THIS FOLDER'S OWN BREAK-CHECKS, AND THIS LIST IS THEIR ONLY RUNNER.
#:
#: 🚨 Both files sat here unrun until 2026-09-19, and `test_sync_audit.py` had
#: been RED since before 1.0.0 -- three of its cases asserted on the second
#: return value of `audit_staged()`, which that function never populates, so
#: they read `[]` for a planted leak and `[]` for a clean tree alike. ⛔ A
#: check nothing runs is not a check, and this gate is the last thing standing
#: between a mistake and an irreversible public push.
SELF_CHECKS = ("test_copy_list.py", "test_sync_audit.py")

#: ⚠ How many the scanner SAYS it found, which is NOT how many it names --
#: `scan.py` formats `shaped[:3]`. This count is the second instrument: it is
#: compared against `shaped_hits()`, and the two must agree before the register
#: is consulted at all. It is never used to identify a hit.
SHAPED_COUNT = re.compile(r"(\d+) key-shaped literal\(s\)")

TEXTISH = (".py", ".md", ".json", ".toml", ".cmd", ".yml", ".yaml", ".txt", ".cfg", ".ini")


def _walk(root):
    u"""The COPY walk. Prunes what must not be copied and skips bytecode."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            yield os.path.join(dirpath, fn)


def _walk_all(root):
    u"""The AUDIT walk. Prunes ONLY `.git`.

    🚨 THIS FUNCTION EXISTS BECAUSE THE AUDIT USED `_walk` AND WAS THEREFORE
    STRUCTURALLY BLIND TO HALF ITS OWN PATTERN LIST. `STRAY` names
    `__pycache__` and `.pyc`, and `_walk` prunes the first and skips the
    second -- so both patterns read as covered and could NEVER fire. Found by
    planting a `__pycache__` file and watching the audit report clean.
    ⛔ Never audit through a walk that filters what you are auditing for.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def audit_dirs():
    u"""Every top-level DIRECTORY in the vault is copied or filed. -> [problem]

    🚨 THE HOLE THAT LET A WHOLE BUILD GO UNPUBLISHED. See `audit_copy_list`'s
    docstring for what it cost. Same both-ends rule:
      - a vault directory in neither register -> FAIL, name it
      - a name in both registers              -> FAIL, the register lies

    ⚠ A stale entry in `NOT_PUBLISHED_DIRS` is NOT a failure, unlike the file
    register: `dist`, `build` and the caches legitimately come and go.
    """
    problems = []
    top_level = set(item for item in COPIED if "/" not in item)

    #: ⭐ A directory is also accounted for when COPIED names FILES inside it.
    #: `packaging/` is exactly that case: six of its files ship as GPL
    #: Corresponding Source, while this clone's own sync tooling lives in the
    #: same folder and must not be touched -- so the directory is published in
    #: part, deliberately, and naming it wholesale would delete the tool
    #: running this audit.
    partly = set(item.split("/", 1)[0] for item in COPIED if "/" in item)

    for name in sorted((top_level | partly) & set(NOT_PUBLISHED_DIRS)):
        problems.append(
            u"%s is in COPIED and in NOT_PUBLISHED_DIRS -- refusing to guess"
            % name)

    for entry in sorted(os.listdir(VAULT)):
        if not os.path.isdir(os.path.join(VAULT, entry)):
            continue
        if entry in top_level or entry in partly \
                or entry in NOT_PUBLISHED_DIRS or entry in NEVER:
            continue
        problems.append(
            u"%s/ is a vault DIRECTORY in neither register. Add it to COPIED "
            u"if it ships, or to NOT_PUBLISHED_DIRS with the reason." % entry)
    return problems


def audit_partly():
    u"""Every vault file inside a directory COPIED names FILES of is named. -> [problem]

    🚨 THE SAME SILENT SUCCESS, ONE LEVEL DOWN. `packaging/` is published file by
    file (see `audit_dirs`), so a NEW build file there was covered by neither
    audit: 1.0.4's `entry_update.py` -- the updater's own entry, which the
    published `hato.spec` builds -- would have been left out, and the sync would
    have said nothing. Found reading the list before the 1.0.4 sync, 2026-09-24.
    """
    problems = []
    named = set(item for item in COPIED if "/" in item)
    for folder in sorted(set(item.split("/", 1)[0] for item in named)):
        root = os.path.join(VAULT, folder)
        if not os.path.isdir(root):
            continue
        for path in _walk(root):
            rel = (folder + "/" + os.path.relpath(path, root)).replace("\\", "/")
            if rel not in named:
                problems.append(
                    u"%s is in the vault's %s/, which is published file by file, and "
                    u"COPIED does not name it. Add it if it ships." % (rel, folder))
    return problems


def audit_copy_list():
    u"""Every file at the vault's root is COPIED or explicitly NOT_PUBLISHED.

    🚨 THE FAILURE THIS CATCHES IS SILENT AND READS AS SUCCESS. A new root-level
    shipping file that nobody adds to `COPIED` is simply not published, and the
    sync says **"0 changed"** -- which is indistinguishable from "nothing needed
    doing". Measured 2026-09-17: `MANIFEST.in` was written to fix a red CI job
    and never left the vault.

    ⭐ Checked from both ends, so the register can only shrink:
      - a root file in neither list  -> FAIL, name it
      - a name in NOT_PUBLISHED that is also in COPIED -> FAIL, the register lies
      - a name in NOT_PUBLISHED that no longer exists  -> FAIL, stale exemption

    ⚠ Directories are handled by `audit_dirs()`, not here.

    🚨 THIS DOCSTRING USED TO END *"Directories are skipped: a new top-level
    DIRECTORY is a bigger decision than a forgotten line."* That assumption
    failed on 2026-09-18, when TWO new top-level directories were added in a
    day and neither was filed: `gui-shots` (every image the rewritten README
    embeds) and `packaging` (the whole Windows build, and its GPL
    Corresponding Source). The sync would have reported success and published
    neither -- the identical silent-success failure this function exists to
    prevent, in the one shape it had been told not to look at.
    """
    problems = []

    for name in sorted(set(COPIED) & set(NOT_PUBLISHED)):
        problems.append(u"%s is in COPIED and in NOT_PUBLISHED -- refusing to guess" % name)

    for name in sorted(NOT_PUBLISHED):
        if not os.path.exists(os.path.join(VAULT, name)):
            problems.append(u"stale exemption: %s is in NOT_PUBLISHED and does not exist" % name)

    for entry in sorted(os.listdir(VAULT)):
        full = os.path.join(VAULT, entry)
        if os.path.isdir(full):
            continue
        if entry in COPIED or entry in NOT_PUBLISHED:
            continue
        if entry.endswith((".pyc", ".log")) or entry in PRUNE_DIRS:
            continue
        problems.append(
            u"%s sits at the vault root and is in NEITHER list. Add it to COPIED "
            u"if it ships, or to NOT_PUBLISHED with the reason. ⛔ Left out, it is "
            u"silently never published and the sync still says '0 changed'." % entry)

    return problems


def plan():
    u"""What differs between the vault and this clone, per copied path."""
    added, changed, removed, same = [], [], [], 0

    for item in COPIED:
        src, dst = os.path.join(VAULT, item), os.path.join(CLONE, item)
        if not os.path.exists(src):
            print(u"  MISSING IN VAULT  %s" % item)
            continue

        if os.path.isfile(src):
            pairs = [(src, dst, item)]
        else:
            pairs = [
                (p, os.path.join(dst, os.path.relpath(p, src)),
                 os.path.join(item, os.path.relpath(p, src)).replace("\\", "/"))
                for p in _walk(src)
            ]

        for s, d, rel in pairs:
            if not os.path.exists(d):
                added.append(rel)
            elif _sha(s) != _sha(d):
                changed.append(rel)
            else:
                same += 1

        if os.path.isdir(src) and os.path.isdir(dst):
            vault_rel = {os.path.relpath(p, src).replace("\\", "/") for p in _walk(src)}
            for p in _walk(dst):
                rel = os.path.relpath(p, dst).replace("\\", "/")
                if rel not in vault_rel:
                    removed.append(os.path.join(item, rel).replace("\\", "/"))

    return added, changed, removed, same


def _would_commit(rels):
    u"""Which of `rels` git would actually put in a commit.

    ⚠ THE AUDIT USED TO WALK THE FILESYSTEM AND JUDGE EVERYTHING IT FOUND, which
    is the wrong set: what reaches the public repo is what git COMMITS, and git
    honours `.gitignore`. Measured 2026-09-17 on the first real sync -- it
    failed on `packaging/__pycache__/sync_from_vault.cpython-310.pyc`, a file
    `.gitignore` already excludes and git would never have pushed.

    ⛔ That matters more than a cosmetic false alarm. `doctrine/release`: *"A
    permanently-red check is one people learn to scroll past -- which is exactly
    how a live data exposure survived here."* An audit that fires on every
    ordinary `.pyc` trains you to ignore the run in which it fires on a key.

    ⭐ So ignored files are dropped, and the count of them is PRINTED rather
    than hidden -- if `.gitignore` is ever weakened, the number moves.
    """
    if not rels:
        return set(), 0

    # 🚨 NUL-SEPARATED, AND IN BYTES. MEASURED 2026-09-17: the first version
    # passed `input="\n".join(rels)` with `text=True`, and Python's newline
    # translation turned every separator into `\r\n` ON THE WAY IN. git then
    # received paths ending in `\r`, and because a carriage return is a control
    # character it QUOTED them in its reply:
    #
    #   '"packaging/__pycache__/sync_from_vault.cpython-310.pyc\\r"\n'
    #
    # So the echoed path matched nothing in `rels`, nothing was subtracted --
    # 124 paths in, 124 "tracked" out -- and the audit reported a stray it had
    # just been told was ignored. ⚠ The symptom was a FALSE FAILURE, which is
    # the safe direction; the same bug in a check that must catch something is
    # a false pass. ⛔ `-z` removes both the translation and the quoting.
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            cwd=CLONE, input=b"\0".join(r.encode("utf-8") for r in rels),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return set(rels), 0          # ⛔ no git: judge everything, never less

    ignored = {chunk.decode("utf-8", "replace").replace("\\", "/")
               for chunk in proc.stdout.split(b"\0") if chunk}
    return {r for r in rels if r not in ignored}, len(ignored)


def audit_staged():
    u"""⛔ Run AFTER the copy, over the whole clone. Two claims, each its own."""
    strays, secrets = [], []
    candidates = []
    for p in _walk_all(CLONE):          # ⛔ _walk_all, never _walk -- see its docstring
        rel = os.path.relpath(p, CLONE).replace("\\", "/")
        if rel.startswith(".git/"):
            continue
        candidates.append(rel)

    tracked, ignored_count = _would_commit(candidates)
    print(u"  audit: %d file(s) git would commit, %d ignored by .gitignore"
          % (len(tracked), ignored_count))

    for p in _walk_all(CLONE):
        rel = os.path.relpath(p, CLONE).replace("\\", "/")
        if rel.startswith(".git/") or rel not in tracked:
            continue
        if STRAY.search("/" + rel):
            strays.append(rel)
    return strays, secrets


def scan_secrets():
    u"""Invoke `hato.dev scan-secrets` over the staged clone.

    ⚠ RUN FROM THE VAULT, POINTED AT THE CLONE. The key resolves through
    `hato.config.json`'s `keystore.fileRelative`, which is relative to that
    file -- correct in the vault, and it does NOT resolve from the clone, whose
    depth below `InfiniteVoid/` is different. ⭐ That the clone cannot find the
    key is a feature: a published checkout must have no route to it.

    ⛔ Nothing here ever prints the key. The tool prints its last four
    characters at most.
    """
    env = dict(os.environ, PYTHONUTF8="1")
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(VAULT, "..", "tsubasa"), env.get("PYTHONPATH", "")])
    try:
        proc = subprocess.run(
            [sys.executable] + SCAN_SECRETS + [CLONE],
            cwd=VAULT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
    except OSError as exc:
        return 2, u"could not run hato.dev scan-secrets: %s" % exc
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def shaped_hits(root=None):
    u"""EVERY key-shaped literal under `root`, as (relpath, field) pairs.

    ⛔ THE VALUE IS NEVER RETURNED, PRINTED OR STORED -- only where it is and
    what the field is called. The caller compares these against KNOWN_SHAPED.

    ⭐ In-process, over `hato.dev.scan`'s own walker, because the subprocess
    report names only the first three. See the comment at the call site; that
    truncation is what let five unregistered literals sit in a tree this gate
    called clean.

    ⚠ THE IMPORT ROOT IS THIS FILE'S REPOSITORY, NOT `root`. They are the same
    thing in the real run, and deliberately different in the break-check, which
    points the walk at a temp tree with no `hato` in it. Deriving the import
    from `root` would make the test unable to call the function it is testing.

    ⭐ And it is the CLONE's `hato` either way -- the clone is what is about to
    be pushed, so the clone's own scanner is what must read it.
    """
    root = CLONE if root is None else root
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from hato.dev import scan as _scan
    except ImportError as exc:                    # ⛔ refuse, never pass
        raise SystemExit(u"🚨 cannot import the clone's hato.dev.scan (%s). "
                         u"The shape half of the audit cannot run, so NOTHING "
                         u"is pushed." % exc)
    marker = root.replace("\\", "/") + "/"
    out = []
    for label, data in _scan.artifacts(root):
        for hit_label, name, _at, _len in _scan._shaped_hits(label, data):
            rel = str(hit_label).replace("\\", "/")
            if marker in rel:
                rel = rel.split(marker, 1)[1]
            out.append((rel, name))
    return out


def self_check():
    u"""Run this folder's break-checks. -> [] when every one of them passes.

    ⛔ BEFORE the audit, never after. The audit is the thing they prove, and a
    scanner that cannot fail is indistinguishable from a clean tree -- which is
    the exact sentence this project's ledger already carries about auditing
    through a walk that filters for the thing being audited.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for name in SELF_CHECKS:
        path = os.path.join(here, name)
        if not os.path.isfile(path):
            bad.append((name, u"missing -- it is named in SELF_CHECKS"))
            continue
        proc = subprocess.run([sys.executable, path], cwd=CLONE,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            lines = proc.stdout.decode("utf-8", "replace").rstrip().splitlines()
            bad.append((name, u"exit %d -- %s"
                        % (proc.returncode, u" | ".join(lines[-4:]))))
    return bad


def apply_copy():
    for item in COPIED:
        src, dst = os.path.join(VAULT, item), os.path.join(CLONE, item)
        if not os.path.exists(src):
            continue
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst) or CLONE, exist_ok=True)
            shutil.copy2(src, dst)
            continue
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns(*sorted(PRUNE_DIRS), "*.pyc"),
        )


def main():
    ap = argparse.ArgumentParser(description=u"Sync hato's shipping tree into the publish clone.")
    ap.add_argument("--apply", action="store_true",
                    help=u"actually copy. Without it this is a dry run and writes nothing.")
    args = ap.parse_args()

    if not os.path.isdir(VAULT):
        print(u"FAIL  vault not found: %s" % VAULT)
        return 2

    for bad in sorted(NEVER):
        if bad in COPIED:
            print(u"FAIL  %s is in both COPIED and NEVER -- refusing to guess" % bad)
            return 2

    # ⛔ FIRST: can this tool's own checks still fail? Everything below is a
    # claim made BY the thing they test.
    broken = self_check()
    if broken:
        print(u"\nFAIL  this folder's break-checks do not pass, so nothing this "
              u"tool reports about the tree can be believed:")
        for name, why in broken:
            print(u"    %s  %s" % (name, why))
        return 2
    print(u"  self-check: %d break-check(s) green" % len(SELF_CHECKS))

    # ⛔ BEFORE the copy, so a forgotten file is named instead of silently skipped
    gaps = audit_copy_list()
    if gaps:
        print(u"\nFAIL  the copy list does not account for every root file:")
        for g in gaps:
            print(u"    %s" % g)
        return 2

    # 🚨 AND EVERY DIRECTORY. This half was missing, and a whole Windows build
    # plus every README image went unpublished because of it.
    holes = audit_dirs()
    if holes:
        print(u"\nFAIL  the copy list does not account for every directory:")
        for h in holes:
            print(u"    %s" % h)
        return 2

    # 🚨 AND EVERY FILE OF A DIRECTORY PUBLISHED IN PART (`packaging/`)
    parts = audit_partly()
    if parts:
        print(u"\nFAIL  the copy list does not account for every file it publishes in part:")
        for p in parts:
            print(u"    %s" % p)
        return 2

    added, changed, removed, same = plan()

    print(u"\n  vault  %s\n  clone  %s\n" % (VAULT, CLONE))
    print(u"  %d unchanged, %d added, %d changed, %d to remove"
          % (same, len(added), len(changed), len(removed)))
    for label, rows in ((u"ADD", added), (u"CHANGE", changed), (u"REMOVE", removed)):
        for rel in rows[:40]:
            print(u"    %-7s %s" % (label, rel))
        if len(rows) > 40:
            print(u"    %-7s ... and %d more" % ("", len(rows) - 40))

    if not args.apply:
        print(u"\n  DRY RUN -- nothing written. Re-run with --apply.")
        return 0

    apply_copy()
    print(u"\n  copied.")

    strays, _unused = audit_staged()
    if strays:
        print(u"\nFAIL  %d stray file(s) in the staged tree:" % len(strays))
        for rel in strays[:20]:
            print(u"    %s" % rel)
        return 1

    code, output = scan_secrets()

    # ⛔ THE HARD HALF, ALWAYS. If the real key's bytes are anywhere in the tree
    # -- in any of five encodings -- nothing is pushed and no register applies.
    if u"ok    key_bytes_absent" not in output:
        print(u"\n  hato.dev scan-secrets:")
        for line in output.rstrip().splitlines()[-10:]:
            print(u"    %s" % line)
        print(u"\n🚨 FAIL  the key-bytes claim did not hold. NOTHING is pushed.")
        return 1

    for line in output.splitlines():
        if line.strip().startswith(u"ok    key_bytes_absent"):
            print(u"\n  %s" % line.strip())
            break

    # the shape half, against the register
    #
    # 🚨 THIS USED TO READ THE SUBPROCESS'S SENTENCE, AND THE SENTENCE IS
    # TRUNCATED. `hato/dev/scan.py` formats `shaped[:3]`: it says "8 key-shaped
    # literal(s)" and then names three. This gate checks NAMES against the
    # register, so for as long as it read that line it could only ever see
    # three -- and it printed `3 hit(s), 3 known planted fixture(s)` and
    # `audit clean` over a tree holding EIGHT. Five key-shaped literals had
    # never been looked at by anybody, across the whole 1.0.0 release.
    #
    # ⭐ MEASURED 2026-09-19, and the symptom arrived first as an ACCUSATION:
    # a fourth shape (a key-shaped line in a MANIFEST.in COMMENT, of all
    # things) pushed a registered fixture out of the three, and this tool
    # reported that fixture as a *stale exemption* -- the register accusing a
    # file nobody had touched. ⛔ The false stale was the symptom. The missed
    # hits were the defect, and the first fix written here was ALSO wrong: it
    # compared the declared count against the number of `field '<name>'`
    # matches in the report -- 9, because the scanner prints its three-hit
    # summary three times. So the check read `8 > 9`, which is false, and the
    # guard sat there doing nothing. ⭐ A gate that reads a REPORT is measuring
    # the report.
    #
    # ⭐ So enumerate in-process, over the same walker the tool uses, and stop
    # parsing prose. The subprocess is still what makes the `key_bytes_absent`
    # claim -- it resolves the real key, and this must not -- but the shape
    # half is now counted here, uncapped, and the two counts must AGREE.
    declared = [int(n) for n in SHAPED_COUNT.findall(output)]
    pairs = shaped_hits()
    expect = max(declared) if declared else 0
    if expect != len(pairs):
        print(u"\n🚨 FAIL  two instruments disagree about how many key-shaped "
              u"literals are in this tree: the scanner says %d, this walk found "
              u"%d." % (expect, len(pairs)))
        print(u"  Neither number can be trusted until they agree. NOTHING is "
              u"pushed.")
        return 1

    hits = set(pairs)
    unexpected = sorted(h for h in hits if h not in KNOWN_SHAPED)
    stale = sorted(k for k in KNOWN_SHAPED if k not in hits)

    print(u"  key-shaped literals: %d hit(s), %d known planted fixture(s)"
          % (len(hits), len(hits) - len(unexpected)))
    for rel, field in stale:
        print(u"    ⚠ stale exemption, no longer present: %s field %r" % (rel, field))
    if unexpected:
        print(u"\n🚨 FAIL  %d key-shaped literal(s) NOT in the known register:"
              % len(unexpected))
        for rel, field in unexpected:
            print(u"    %s  field %r" % (rel, field))   # ⛔ never the value
        print(u"  Look at each one. If it is another planted fixture, add it to "
              u"KNOWN_SHAPED with a comment. NOTHING is pushed.")
        return 1

    print(u"\n  audit clean: no strays, no key in the tree, no unregistered key shapes.")
    print(u"\n  ⛔ Read `git status` and `git diff --stat` before committing."
          u"\n  ⛔ A first push to a public repo cannot be taken back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
