# -*- coding: utf-8 -*-
u"""Does the copy-list guard actually name a forgotten root file?

The real failure: MANIFEST.in was written in the vault, was not in COPIED, and
the sync said "0 changed" -- success-shaped silence. Reproduce it.
"""
import importlib.util, os, sys
sys.stdout.reconfigure(encoding="utf-8")
# ⛔ DERIVED, NOT WRITTEN DOWN. This clone is public and an absolute path names
# the account it was written on. Corrected 2026-09-18.
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "sync_from_vault.py")

spec = importlib.util.spec_from_file_location("syncmod", SCRIPT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

fails = []

# 0. control -- as shipped, the register must be complete
gaps = m.audit_copy_list()
print(u"control (as shipped)        %d gap(s)" % len(gaps))
for g in gaps: print(u"    %s" % g[:110])
if gaps: fails.append(u"the register is incomplete as shipped")

# 1. THE REAL BUG: drop MANIFEST.in from COPIED, as it was an hour ago
m.COPIED = [c for c in m.COPIED if c != "MANIFEST.in"]
gaps = m.audit_copy_list()
named = [g for g in gaps if "MANIFEST.in" in g]
print(u"MANIFEST.in dropped         %d gap(s), names it: %s" % (len(gaps), bool(named)))
if named: print(u"    %s" % named[0][:150])
if not named: fails.append(u"a root file missing from COPIED was NOT named")
m.COPIED.append("MANIFEST.in")

# 2. a lying register: a name in both lists
m.NOT_PUBLISHED = dict(m.NOT_PUBLISHED); m.NOT_PUBLISHED["pyproject.toml"] = "nonsense"
gaps = m.audit_copy_list()
both = [g for g in gaps if "COPIED and in NOT_PUBLISHED" in g]
print(u"name in BOTH lists          caught: %s" % bool(both))
if not both: fails.append(u"a name in both lists was not caught")
del m.NOT_PUBLISHED["pyproject.toml"]

# 3. a stale exemption: a name that no longer exists
m.NOT_PUBLISHED["GONE-FOREVER.md"] = "was deleted months ago"
gaps = m.audit_copy_list()
stale = [g for g in gaps if "stale exemption" in g]
print(u"stale exemption             caught: %s" % bool(stale))
if not stale: fails.append(u"a stale exemption was not caught")
del m.NOT_PUBLISHED["GONE-FOREVER.md"]

# 4. a build file in a directory published file by file -- 1.0.4's updater entry,
#    which the published hato.spec builds, was in no list (2026-09-24)
parts = m.audit_partly()
print(u"control (partly published)  %d gap(s)" % len(parts))
for p in parts: print(u"    %s" % p[:110])
if parts: fails.append(u"a file published in part is unnamed as shipped")
m.COPIED = [c for c in m.COPIED if c != "packaging/entry_update.py"]
parts = m.audit_partly()
named = [p for p in parts if "packaging/entry_update.py" in p]
print(u"entry_update.py dropped     %d gap(s), names it: %s" % (len(parts), bool(named)))
if not named: fails.append(u"a packaging file missing from COPIED was NOT named")
m.COPIED.append("packaging/entry_update.py")

print()
if fails:
    print(u"FAIL  %d" % len(fails))
    for f in fails: print(u"   - %s" % f)
    sys.exit(1)
print(u"OK  the guard names a forgotten file, a lying register, a stale exemption and")
print(u"    a forgotten build file, and is silent on the tree as shipped.")
