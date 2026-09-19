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

# 3. key-shaped strings -- three plausible shapes of the real thing
def plant_key(text):
    def go(t):
        with open(os.path.join(t, "hato", "leak.py"), "w", encoding="utf-8") as fh:
            fh.write(u'KEY = "%s"\n' % text)
    return go

for label, text in (
    (u"AAAAA-prefixed", u"AAAAAbcdefghijklmnop"),
    (u"dashed triple",  u"abcdefgh-ijkl-mnop"),
    (u"api_key= form",  u"placeholder"),
):
    if label == u"api_key= form":
        def go(t):
            with open(os.path.join(t, "hato", "leak.py"), "w", encoding="utf-8") as fh:
                fh.write(u'api_key = "abcdefghijklmnopqrst"\n')
        s, k = case(label, go)
    else:
        s, k = case(label, plant_key(text))
    print(u"planted %-16s secrets=%r" % (label, k))
    if not k: fails.append(u"key shape %r NOT caught" % label)

print()
if fails:
    print(u"FAIL  %d" % len(fails))
    for f in fails:
        print(u"   - %s" % f)
    sys.exit(1)
print(u"OK  audit half is proven able to fail on every planted case, and clean on a clean tree.")
