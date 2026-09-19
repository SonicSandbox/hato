# -*- coding: utf-8 -*-
u"""Break-check for the clone sync script's audit half.

A scanner that cannot find a planted problem is worse than none. Plant one of
each, confirm audit_staged() reports it, confirm a clean tree reports nothing.
"""
import importlib.util, os, shutil, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")

# ⛔ DERIVED, NOT WRITTEN DOWN. This clone is public and an absolute path names
# the account it was written on. Corrected 2026-09-18.
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "sync_from_vault.py")

spec = importlib.util.spec_from_file_location("syncmod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = []

def case(name, plant):
    tmp = tempfile.mkdtemp(prefix="hato-audit-")
    try:
        os.makedirs(os.path.join(tmp, "hato"), exist_ok=True)
        with open(os.path.join(tmp, "hato", "ok.py"), "w", encoding="utf-8") as fh:
            fh.write(u"# nothing interesting\nX = 1\n")
        plant(tmp)
        mod.CLONE = tmp
        strays, secrets = mod.audit_staged()
        return strays, secrets
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# 1. a clean tree must be clean -- the positive control. Without it, a scanner
#    that flags everything would "pass" every planted case below.
s, k = case("clean", lambda t: None)
print(u"clean tree          strays=%r secrets=%r" % (s, k))
if s or k: fails.append(u"clean tree was reported dirty -- the scanner flags everything")

# 2. a stray
s, k = case("stray", lambda t: open(os.path.join(t, "hato", "pipeline.py.mutbak"), "w").write("x"))
print(u"planted mutbak      strays=%r" % (s,))
if not any("mutbak" in x for x in s): fails.append(u"mutbak stray NOT caught")

s, k = case("tmp", lambda t: open(os.path.join(t, "scratch.tmp"), "w").write("x"))
print(u"planted .tmp        strays=%r" % (s,))
if not any(x.endswith(".tmp") for x in s): fails.append(u".tmp stray NOT caught")

s, k = case("pycache", lambda t: (os.makedirs(os.path.join(t, "hato", "__pycache__")),
                                  open(os.path.join(t, "hato", "__pycache__", "x.py"), "w").write("x")))
print(u"planted __pycache__ strays=%r" % (s,))
if not any("__pycache__" in x for x in s): fails.append(u"__pycache__ NOT caught")

# 3. key-shaped strings -- the shapes the tool actually claims to catch.
#
# 🚨 THE THREE CASES THAT USED TO BE HERE WERE RED THROUGH THE WHOLE 1.0.0
# RELEASE AND NOBODY KNEW, because nothing ran this file. It is wired into
# `sync_from_vault.py`'s gate now, which is the only runner it will ever have.
#
# ⛔ They asserted on `audit_staged()`'s SECOND return value -- and that
# function never populates it. The shape half lives in the gate, not in the
# stray walk. So `secrets` came back `[]` for a planted leak and `[]` for a
# clean tree alike, and three checks named after three shapes could not tell
# the two apart.
#
# ⛔ Two of them were also asking for something the tool has never claimed.
# `no_key_shaped_literal` is about a credential-shaped ASSIGNMENT: a known
# field NAME and a value. A bare `KEY = "AAAAAbcdefghijklmnop"` is neither,
# and no amount of running this file would have made it become one.
def shaped(text):
    u"""-> the field names `shaped_hits()` finds for one planted line."""
    tmp = tempfile.mkdtemp(prefix="hato-shape-")
    try:
        os.makedirs(os.path.join(tmp, "hato"), exist_ok=True)
        with open(os.path.join(tmp, "hato", "leak.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        return sorted(f for _path, f in mod.shaped_hits(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

for label, line, want in (
    (u"assignment", u'api_key = "abcdefghijklmnopqrst"\n', [u"api_key"]),
    (u"json field", u'"jimaku_api_key": "abcdefghijklmnopqrst"\n',
     [u"jimaku_api_key"]),
    (u"env form",   u'HATO_JIMAKU_KEY=abcdefghijklmnopqrst\n',
     [u"HATO_JIMAKU_KEY"]),
    (u"bearer",     u'auth_token: abcdefghijklmnopqrst\n', [u"auth_token"]),
    # ⭐ AND THE TWO FILTERS. Both measured 2026-09-19, and both of them made a
    # planted positive silently useless before they were understood: a
    # break-check whose fixture the scanner deliberately skips is a green run
    # that proves nothing. `len(set(value)) <= 2` and `_PLACEHOLDER`.
    (u"one repeated char", u'api_key = "zzzzzzzzzzzzzzzzzzzz"\n', []),
    (u"a placeholder",     u'api_key = "your_key_goes_here_xx"\n', []),
):
    got = shaped(line)
    print(u"shape %-18s -> %r" % (label, got))
    if got != want:
        fails.append(u"shape %s: expected %r, got %r" % (label, want, got))

# 4. ⭐ THE SHAPE ENUMERATION -- the half that was blind, and the reason this
#    section exists at all.
#
# 🚨 MEASURED 2026-09-19. The gate used to read `scan-secrets`' SENTENCE, and
# `hato/dev/scan.py` formats `shaped[:3]`: it says how many it found and then
# names three. So the gate printed `3 hit(s), 3 known planted fixture(s)` and
# `audit clean` over a tree holding EIGHT, and five key-shaped literals rode
# through the entire 1.0.0 release without anybody looking at them.
#
# ⛔ FOUR is the number that matters here. Three would have passed the old
# code unchanged, which is exactly how the defect stayed invisible.
def shapes_tree(fields):
    tmp = tempfile.mkdtemp(prefix="hato-shapes-")
    os.makedirs(os.path.join(tmp, "hato"), exist_ok=True)
    for n, field in enumerate(fields):
        with open(os.path.join(tmp, "hato", "leak%d.py" % n), "w",
                  encoding="utf-8") as fh:
            fh.write(u'%s = "abcdefghijklmnopqrst"\n' % field)
    return tmp

PLANTED = (u"api_key", u"jimaku_api_key", u"secret", u"authToken")
tmp = shapes_tree(PLANTED)
try:
    pairs = mod.shaped_hits(tmp)
    got = sorted(f for _path, f in pairs)
    print(u"planted four shapes  enumerated=%r" % (got,))
    if got != sorted(PLANTED):
        fails.append(u"shaped_hits() returned %r, not all four -- it is reading "
                     u"a truncated report again" % (got,))
    # ⛔ and it must hand back WHERE and WHAT-IT-IS-CALLED, never the value
    if any(u"abcdefghijklmnopqrst" in repr(p) for p in pairs):
        fails.append(u"shaped_hits() returned the VALUE, not just the field name")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ⭐ and the control: an enumerator that flags everything would pass the case
#    above without being able to tell a fixture from a leak.
tmp = shapes_tree(())
try:
    with open(os.path.join(tmp, "hato", "ok.py"), "w", encoding="utf-8") as fh:
        fh.write(u"# nothing interesting\nX = 1\n")
    left = mod.shaped_hits(tmp)
    print(u"clean tree           enumerated=%r" % (left,))
    if left:
        fails.append(u"a clean tree enumerated %r -- shaped_hits() flags "
                     u"everything" % (left,))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(u"FAIL  %d" % len(fails))
    for f in fails:
        print(u"   - %s" % f)
    sys.exit(1)
print(u"OK  audit half is proven able to fail on every planted case, and clean on a clean tree.")
