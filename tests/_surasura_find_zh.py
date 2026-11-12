# -*- coding: utf-8 -*-
u"""
⭐ LAYER 20 + 09-hato-layer.md §7.9 -- drive the scratch Surasura's OWN Chinese finder
(`app/no_subs.py`) against this hato, for `test_connect_e2e.py::test_20`. Run by the scratch
clone's Python, from the scratch base (RUNBOOK 16a), never by pytest:

    surasura-3.0\\.venv\\Scripts\\python <this file> setup
    surasura-3.0\\.venv\\Scripts\\python <this file> find <library folder>
    surasura-3.0\\.venv\\Scripts\\python <this file> look <library folder>

`setup` builds the scratch root's CHINESE library with the Chinese yes (`subs_with_hato_zh`)
and has `surasura-cli status --lang zh` write surasura.json (its `drop_folders.zh`). `find`
adds the folder as a source, looks at it (its videos with no subtitle wait) and runs
`no_subs.find` for zh, as the window's looks do. `look` looks at the folder again (what hato
wrote beside a video fills its waiting item, no second one). Each prints one JSON line.
⛔ Every Surasura process runs in the scratch root (`make_root.env()`): never Sonic's.
"""
import json
import os
import subprocess
import sys

BASE = os.getcwd()                      # the test runs this from the scratch base
sys.path.insert(0, BASE)
import make_root  # noqa: E402

os.environ.update(make_root.env())
sys.path.insert(0, make_root.CLONE)
os.chdir(make_root.CLONE)
LANG = "zh"


def _store():
    from app import library_store, path_utils
    return library_store.open_store(LANG, path_utils.get_data_path(LANG),
                                    path_utils.get_user_files_path(LANG))


def _items(store):
    return [dict(zip(("id", "rel_path", "availability"), row)) for row in store.conn.execute(
        "SELECT id, rel_path, availability FROM items ORDER BY id").fetchall()]


def setup():
    from tests import connect_helpers as c
    c.library(LANG, connect=False, arrivals=True, subs_with_hato_zh=True)
    said = subprocess.run([make_root.WRAPPER, "status", "--lang", LANG], capture_output=True,
                          env=make_root.env(), cwd=BASE)
    with open(os.path.join(make_root.TOOLS, "surasura.json"), encoding="utf-8") as f:
        return {"status_exit": said.returncode, "surasura.json": json.load(f)}


def find(folder):
    from app import no_subs, sources
    src = os.path.abspath(folder)
    with _store() as store:
        known = {os.path.normcase(r["path"]): r["id"] for r in store.sources(counts=False)}
        root = known.get(os.path.normcase(src)) or store.add_source(src)
        sources.scan(store, LANG, root, first=True)
        waiting = [(v.rel, v.video) for v in no_subs.waiting(store)]
        found = no_subs.find(store, LANG, {no_subs.SETTING_ZH: True})
        notes = {rel: no_subs.note(rel, LANG) for rel, _v in waiting}
        try:
            with open(no_subs.state_path(LANG), encoding="utf-8") as f:
                state = json.load(f)
        except FileNotFoundError:
            state = None                # hato was never asked: the finder kept nothing
        return {"waiting": waiting, "find": found, "notes": notes, "state": state,
                "hato_finds": no_subs.hato_finds(language=LANG),
                "beside_on": no_subs.beside_on(), "items": _items(store)}


def look(folder):
    from app import no_subs, sources
    src = os.path.abspath(folder)
    with _store() as store:
        root = {os.path.normcase(r["path"]): r["id"]
                for r in store.sources(counts=False)}[os.path.normcase(src)]
        sources.scan(store, LANG, root)
        return {"items": _items(store), "waiting": [(v.rel, v.video) for v in no_subs.waiting(store)],
                "beside": sorted(os.listdir(src))}


if __name__ == "__main__":
    arm = sys.argv[1]
    got = {"setup": setup, "find": find, "look": look}[arm](*sys.argv[2:])
    print(json.dumps(got, ensure_ascii=False, default=str))
