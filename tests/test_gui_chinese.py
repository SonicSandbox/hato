# -*- coding: utf-8 -*-
u"""
⭐ LAYER 20 -- the window's Chinese card: there for a Chinese hato or a Surasura with a
Chinese library, and ⛔ NOWHERE for a Japanese learner, who sees hato exactly as before.

`QT_QPA_PLATFORM=offscreen` is set before PyQt6 is imported, as `test_gui_widgets` does.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

import _surasura
from hato import credentials
from hato.gui import app as gui_app


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


def make(**over):
    state = gui_app.build_state_from([], {}, **over)
    window = gui_app.HatoWindow(state)
    window.spawned = []
    window.spawn = window.spawned.append
    window.show_tab(gui_app.TAB_SET)
    return window


def titles(window):
    return [w.text() for w in window.findChildren(QLabel) if w.objectName() == u"cardtitle"]


def buttons(window):
    return {b.property(gui_app.KEEP) or b.objectName(): b for b in window.findChildren(QPushButton)}


def test_a_japanese_learner_sees_no_chinese_card(qapp):
    window = make(key_hint=u"…ab12")
    assert u"CHINESE SUBTITLES" not in titles(window), titles(window)
    texts = u" ".join(w.text() for w in window.findChildren(QLabel))
    assert u"assrt" not in texts and u"OpenSubtitles" not in texts


def test_the_card_names_both_sources_their_keys_and_assrts_credit(qapp):
    window = make(key_hint=u"…ab12", chinese=True,
                  zh_hints={u"assrt": u"…XY12", u"opensubtitles": None})
    names = titles(window)
    assert names.index(u"CHINESE SUBTITLES") == names.index(u"JIMAKU KEY") + 1, names
    texts = u" ".join(w.text() for w in window.findChildren(QLabel))
    assert u"assrt.net — set, ending …XY12" in texts
    assert u"OpenSubtitles — not set" in texts
    assert u"字幕服务由 assrt.net 提供" in texts and u"https://assrt.net" in texts
    assert u"5 downloads a day" in texts
    assert u"Most Chinese subtitles are .srt" in texts, u"the default (.ass only) is said"
    kept = [b for b in window.findChildren(QPushButton)
            if (b.property(gui_app.KEEP) or u"").startswith(u"key.choose.")]
    assert sorted(b.property(gui_app.KEEP) for b in kept) == [u"key.choose.assrt",
                                                         u"key.choose.opensubtitles"]


def test_7_9_where_surasura_sends_the_learner_is_this_windows_tab_and_card(qapp):
    u"""⭐ 09-hato-layer.md §7.9 (b): `hato key --show --service … --json` tells Surasura where
    a Chinese key is set (`key.WHERE_TO_SET`), and Surasura's card says it. ⛔ The words are
    this window's own -- its tab, then its card -- or the learner looks for a place that
    is not there."""
    from hato.commands import key as key_cmd
    app, tab, card = [part.strip() for part in key_cmd.WHERE_TO_SET.split(u"→")]
    window = make(chinese=True, zh_hints={u"assrt": None, u"opensubtitles": None})
    assert app == u"hato" and window.tab_buttons[gui_app.TAB_SET].text() == tab
    assert card.upper() in titles(window), titles(window)


def test_with_the_format_fallback_on_the_srt_line_is_not_said(qapp):
    window = make(chinese=True, format_fallback=True, zh_hints={})
    texts = u" ".join(w.text() for w in window.findChildren(QLabel))
    assert u"Most Chinese subtitles are .srt" not in texts


def test_a_chinese_hato_needs_a_chinese_key_not_jimakus(qapp):
    window = make(chinese_runs=True, chinese=True, key_hint=None, folders=[u"D:\Anime"],
                  zh_hints={u"assrt": None, u"opensubtitles": u"…os12"})
    assert window.has_key()
    window.state.zh_hints = {u"assrt": None, u"opensubtitles": None}
    assert not window.has_key()
    assert window.start_run() is None
    assert u"no assrt.net or OpenSubtitles key" in window.state.live
    japanese = make(key_hint=None, folders=[u"D:\Anime"])
    assert not japanese.has_key() and japanese.start_run() is None
    assert japanese.state.live == u"no jimaku key — add one in Settings", u"1.0.0's words"


def test_saving_a_chinese_key_goes_through_stdin_with_its_service(qapp, monkeypatch):
    window = make(chinese=True, zh_hints={u"assrt": None, u"opensubtitles": None})
    seen = []

    class Saved(object):
        returncode = 0

        def __init__(self, out):
            self.out = out

        def communicate(self, timeout=None):
            return (self.out, b"")

    def spawn(argv, **kw):
        seen.append((argv, kw))
        if u"--test" in argv:
            return Saved(b'{"ok": true, "connected": true, "said": "Connected \\u2014 the key '
                         b'works (20 requests a minute left)"}\n')
        return Saved(b'{"ok": true}\n')

    class Dialog(object):
        def __init__(self, *a, **kw):
            seen.append(("dialog", kw))

        def exec(self):
            return gui_app.QDialog.DialogCode.Accepted

        def value(self):
            return u"assrtTokenValue0000000000000XY12"

    window.spawn = spawn
    monkeypatch.setattr(gui_app, "KeyDialog", Dialog)
    assert window.choose_zh_key(u"assrt") is True
    assert seen[0] == ("dialog", {u"replacing": False, u"service": u"assrt"})
    save_argv, save_kw = seen[1]
    assert save_argv[-6:] == [u"key", u"--set-from", u"-", u"--json", u"--service", u"assrt"]
    assert u"assrtTokenValue" not in u" ".join(save_argv), u"never in argv"
    assert save_kw[u"stdin_text"].strip() == u"assrtTokenValue0000000000000XY12"
    assert seen[2][0][-2:] == [u"--service", u"assrt"] and u"--test" in seen[2][0]
    assert window.state.zh_hints[u"assrt"] == u"…XY12"
    assert window.state.zh_status[u"assrt"] == (
        u"Connected — the key works (20 requests a minute left)", True)
    assert window.state.key_hint is None, u"jimaku's hint is never touched"


def test_a_jimaku_key_save_keeps_its_argv_exactly(qapp, monkeypatch):
    window = make()
    seen = []

    class Saved(object):
        returncode = 0

        def communicate(self, timeout=None):
            return (b'{"ok": true}\n', b"")

    window.spawn = lambda argv, **kw: seen.append(argv) or Saved()
    assert window.set_key(u"jimakuKey0001") is True
    assert seen[0][-4:] == [u"key", u"--set-from", u"-", u"--json"], u"no --service for jimaku"


def test_surasura_with_a_chinese_library_brings_the_card(tmp_path, monkeypatch):
    drop = _surasura.install(tmp_path, monkeypatch)
    assert gui_app.surasura_has_chinese() is False, u"a Japanese library alone"
    _surasura.install(tmp_path, monkeypatch,
                      drop_folders={u"ja": str(drop), u"zh": str(tmp_path / u"zh" / u"Hato")})
    assert gui_app.surasura_has_chinese() is True


def test_settings_from_disk_reads_no_chinese_key_for_a_japanese_learner(tmp_path, monkeypatch):
    monkeypatch.setenv("HATO_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("HATO_CACHE", str(tmp_path / "data"))
    monkeypatch.setenv("HOUSEKI_TOOLS_DIR", str(tmp_path / "tools"))
    asked = []
    real = credentials.resolve_key
    monkeypatch.setattr(credentials, "resolve_key",
                        lambda start=None, service="jimaku": asked.append(service) or real(
                            start, service))
    state = gui_app.settings_from_disk()
    assert state.chinese is False and asked == [u"jimaku"], asked
    (tmp_path / "config.toml").write_text(u'lang = "zh"\n', encoding="utf-8")
    state = gui_app.settings_from_disk()
    assert state.chinese_runs and state.chinese
    assert sorted(state.zh_hints) == [u"assrt", u"opensubtitles"]


def test_a_chinese_shows_head_says_it_was_searched_by_title_not_a_jimaku_entry(qapp):
    import test_gui_widgets as w
    row = w.added(episode=1, name=u"[Nekomoe kissaten] Sousou no Frieren - 01.chs.ass")
    row[u"source"], row[u"jimaku_entry"] = u"assrt.net or OpenSubtitles", None
    window = gui_app.HatoWindow(gui_app.build_state_from([row], w.summary(), **dict(
        w.SETTINGS, now=w.NOW8)))
    window.spawn = lambda *a, **k: None
    window.show_tab(gui_app.TAB_SUBS)
    tips = u" ".join(x.toolTip() for x in window.findChildren(QLabel)
                     if x.objectName() == u"info")
    texts = u" ".join(tips.split())             # the tip is wrapped: compare its words
    assert u"Searched for on assrt.net or OpenSubtitles by its title" in texts, texts[:400]
    assert u"Matched to jimaku entry" not in texts
