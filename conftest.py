# -*- coding: utf-8 -*-
"""
Loaded by pytest before any test module -- so everything here is in force for
module-level test code too.

Three jobs, each STRUCTURAL rather than something a test must remember
(doctrine/robustness: a rule that relies on remembering will be forgotten):

1. IMPORT PATHS. `hato` from this tree and `tsubasa` from the vault checkout named
   in hato.config.json, for this process AND for every `python -m hato`
   subprocess a test starts (via PYTHONPATH).

2. ⭐ ISOLATION. HATO_CACHE, HATO_CONFIG, TSUBASA_CACHE and the key file all
   point into one temp dir. When run_tests.py started us it has already done
   this (HATO_TEST_ROOT is set) and verifies the teardown itself; a builder
   running `python -m pytest tests/test_x.py` directly gets the same redirection
   here. ⛔ No test may read or write the real cache, DB, subs_dir, config or
   keystore (spec/07-test-plan.md). TSUBASA_CACHE matters because the contract
   test runs the REAL tsubasa.sync(), whose results DB and trash live under it.

3. ⛔ ZERO NETWORK. HATO_NO_NETWORK=1 for hato's own HTTP layer (it reaches
   subprocesses), plus an in-process guard on the socket layer that refuses any
   non-loopback connect or name lookup with NetworkForbidden. NetworkForbidden
   is deliberately NOT an OSError: a retry ladder that catches "network
   unreachable" must not swallow it and sleep 5 s / 15 s / 45 s inside a test.
   Only the opt-in `live` suite (HATO_LIVE=1, set by the runner) goes without.
"""
import atexit
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# -- 1. import paths --------------------------------------------------------

def _tsubasa_checkout():
    with open(str(ROOT / "hato.config.json"), encoding="utf-8") as fh:
        rel = json.load(fh)["tsubasa"]["checkoutRelative"]
    return (ROOT / rel).resolve()


TSUBASA_CHECKOUT = _tsubasa_checkout()
for _p in (str(TSUBASA_CHECKOUT), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_pp = [str(ROOT), str(TSUBASA_CHECKOUT)]
for _entry in (os.environ.get("PYTHONPATH") or "").split(os.pathsep):
    if _entry and _entry not in _pp:
        _pp.append(_entry)
os.environ["PYTHONPATH"] = os.pathsep.join(_pp)
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

LIVE = os.environ.get("HATO_LIVE") == "1"


# -- 2. isolation -----------------------------------------------------------

if os.environ.get("HATO_TEST_ROOT"):
    TEST_ROOT = Path(os.environ["HATO_TEST_ROOT"])      # the runner's, verified by it
else:
    TEST_ROOT = Path(tempfile.mkdtemp(prefix="hato-pytest-"))
    os.environ["HATO_TEST_ROOT"] = str(TEST_ROOT)
    atexit.register(shutil.rmtree, str(TEST_ROOT), True)
    os.environ["HATO_CACHE"] = str(TEST_ROOT / "data")
    os.environ["HATO_CONFIG"] = str(TEST_ROOT / "config.toml")
    os.environ["TSUBASA_CACHE"] = str(TEST_ROOT / "tsubasa")
    if not LIVE:
        os.environ.pop("HATO_JIMAKU_KEY", None)
        os.environ["HATO_KEYFILE"] = str(TEST_ROOT / "no-such-key.txt")


# -- 3. zero network --------------------------------------------------------

class NetworkForbidden(RuntimeError):
    """The default suite makes ZERO network calls (spec/07-test-plan.md)."""


_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


def _is_loopback(host):
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host in _LOOPBACK_NAMES or host.startswith("127.")


def _refuse(what, host):
    raise NetworkForbidden(
        "the default suite makes ZERO network calls -- refused %s to %r. Drive "
        "the client off tests/fixtures/api/ (recorded real responses), or put "
        "this check in the opt-in `live` suite." % (what, host))


if not LIVE:
    os.environ["HATO_NO_NETWORK"] = "1"

    _real_connect = socket.socket.connect
    _real_connect_ex = socket.socket.connect_ex
    _real_create_connection = socket.create_connection
    _real_getaddrinfo = socket.getaddrinfo

    def _guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(host):
            _refuse("socket.connect", host)
        return _real_connect(self, address)

    def _guarded_connect_ex(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(host):
            _refuse("socket.connect_ex", host)
        return _real_connect_ex(self, address)

    def _guarded_create_connection(address, *args, **kwargs):
        if not _is_loopback(address[0]):
            _refuse("socket.create_connection", address[0])
        return _real_create_connection(address, *args, **kwargs)

    def _guarded_getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            _refuse("a DNS lookup (socket.getaddrinfo)", host)
        return _real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.create_connection = _guarded_create_connection
    socket.getaddrinfo = _guarded_getaddrinfo
