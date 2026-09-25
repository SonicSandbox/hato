# -*- coding: utf-8 -*-
u"""
The update splash -- RUNBOOK 11e. `hato/splash.py`, drawn by the swapper
(`hato-update.exe`) while no hato window exists.

⭐ The picture is computed in plain Python, so most of this file reads PIXELS with no
window at all: the corners, the border, the gradient, the shadow CHROME draws for the
mock's own CSS (its measured values are the reference, below), the sweep, the mark,
and -- through GDI, into a bitmap -- the words. Then one block puts the REAL window
up and reads what Windows composed: its styles, that it took no focus, where it
sits, that the pixels are the canvas's, and that close() takes it away.

⚠ WHAT THIS FILE CANNOT SEE: the FROZEN swapper drawing it (the smoke's rehearsal
watches for it on the built bytes, RUNBOOK 11h), and whether it LOOKS right -- the
shot is looked at against `gui-mock/shots-update/07-4-window-closed.png` (11e).
"""
import ast
import os
import re
import struct
import sys
import threading
import time
import zlib

import pytest

from hato import splash

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(os.path.dirname(HERE), "hato", "splash.py")
WINDOWS = sys.platform.startswith("win")


def px(card, x, y):
    u"""(b, g, r, a) of one canvas pixel."""
    at = (y * card.geo.width + x) * 4
    return tuple(card.pixels[at:at + 4])


def rgb(pixel):
    return (pixel[2], pixel[1], pixel[0])


def near(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# ⛔ stdlib + ctypes only, and nothing else of hato -- it runs in hato-update.exe
# ---------------------------------------------------------------------------

ALLOWED = {u"ctypes", u"math", u"os", u"struct", u"sys", u"threading", u"time", u"zlib"}


def test_the_splash_imports_nothing_but_the_standard_library():
    u"""⛔ It runs inside the onefile swapper while hato's folder is renamed away --
    one `from hato...` would pull in what the swapper excludes, or what is gone."""
    with open(SOURCE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(u".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add((node.module or u"").split(u".")[0] or u".")
    assert {u"ctypes", u"zlib"} <= found, u"the control: the walk found %s" % sorted(found)
    assert found <= ALLOWED, u"hato/splash.py imports %s" % sorted(found - ALLOWED)


def test_its_colours_are_the_themes():
    u"""The splash cannot import the theme (it would pull the window's package into the
    swapper), so it carries COPIES -- and a copy is where a palette drifts."""
    from hato.gui import theme
    for name in (u"CARD_TOP", u"CARD_BOTTOM", u"LINE", u"LINE_HI", u"INK", u"INK_DIM",
                 u"ACCENT"):
        hexed = getattr(theme, name).lstrip(u"#")
        want = tuple(int(hexed[i:i + 2], 16) for i in (0, 2, 4))
        assert getattr(splash, name) == want, u"%s drifted from theme.py" % name


# ---------------------------------------------------------------------------
# the measures -- the mock's, at every DPI
# ---------------------------------------------------------------------------

#: The mock's layout in CSS px, restated here rather than read from the module: the
#: border 1 + the row's padding 18 / 20, the mark 40, the gap 13 -- and the two
#: baselines Chrome lays out for 14 px and 11.5 px Segoe UI at line-height 1.5
#: (the side-by-side against Chrome's own rendering, 2026-09-24: the same rows).
MOCK = {u"mark_x": 21, u"mark_y": 19, u"text_x": 74, u"text_right": 21,
        u"title_base": 35.672, u"sub_base": 54.762}


@pytest.mark.parametrize("dpi", [96, 120, 144, 192, 240, 288])
def test_the_card_is_the_mocks_at_every_dpi(dpi):
    geo = splash.Geometry(dpi)
    s = dpi / 96.0
    at = lambda v: int(v * s + 0.5)                              # noqa: E731
    assert geo.card_w == at(360) and geo.card_h == at(79)
    assert geo.radius == at(12) and geo.border >= 1 and geo.run == at(3)
    assert (geo.mark_x - geo.left, geo.mark_y - geo.top, geo.mark) == \
        (at(MOCK[u"mark_x"]), at(MOCK[u"mark_y"]), at(40)), u"the mark is not where the mock has it"
    assert geo.text_x - geo.left == at(MOCK[u"text_x"]), u"the words start off the mock's column"
    assert geo.right - geo.text_right == at(MOCK[u"text_right"])
    assert (geo.title_base - geo.top, geo.sub_base - geo.top) == \
        (at(MOCK[u"title_base"]), at(MOCK[u"sub_base"])), u"a baseline off the mock's"
    assert geo.left == geo.width - geo.right, u"the card is not centred across its canvas"
    assert geo.height - geo.bottom > geo.top, u"the shadow does not fall BELOW the card"
    assert geo.top < geo.title_base < geo.sub_base < geo.run_top < geo.bottom


# ---------------------------------------------------------------------------
# the picture, with no window
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plain():
    u"""The card at DPI 96 with no mark and no words -- the part plain Python draws."""
    return splash.Card(splash.Geometry(96))


@pytest.mark.parametrize("dpi", [96, 240])
def test_every_pixel_is_premultiplied(dpi):
    u"""⛔ UpdateLayeredWindow reads PREMULTIPLIED alpha: a colour brighter than its
    own alpha is added to the desktop behind it -- a glowing fringe round the card."""
    card = splash.paint(u"1.0.5", dpi)
    data = card.pixels
    bad = [i // 4 for i in range(0, len(data), 4)
           if max(data[i], data[i + 1], data[i + 2]) > data[i + 3]]
    assert not bad, u"%d pixels are not premultiplied, the first at %s" % (
        len(bad), divmod(bad[0], card.geo.width)[::-1])


def test_the_body_is_the_gradient_and_its_edge_is_the_border(plain):
    g = plain.geo
    x = g.right - 40                                     # no words there, ever
    for y in (g.top + g.border, g.top + g.card_h // 2, g.run_top - 1):
        assert px(plain, x, y) == tuple(splash._opaque(plain.fill(y))), y
    assert near(rgb(px(plain, x, g.top + g.border)), splash.CARD_TOP, 2)
    assert near(rgb(px(plain, x, g.run_top - 1)), splash.CARD_BOTTOM, 2)
    mid = g.top + g.card_h // 2
    for where in ((g.left + g.card_w // 2, g.top), (g.left, mid), (g.right - 1, mid),
                  (g.left + g.card_w // 2, g.bottom - 1)):
        assert px(plain, *where) == tuple(splash._opaque(splash.LINE_HI)), where


def test_the_corners_are_round_and_soft(plain):
    u"""Anti-aliased: from the very corner inwards the card's cover only grows, and the
    outline is PART covered where it crosses a pixel -- the border at a fraction of its
    colour, darker than anything the card holds. ⚠ Not the alpha: the shadow under a
    corner is part covered too, jagged or not. Left and right are exact mirrors."""
    g = plain.geo
    alphas = [px(plain, g.left + i, g.top + i)[3] for i in range(g.radius)]
    assert alphas == sorted(alphas) and alphas[-1] == 255, alphas
    assert rgb(px(plain, g.left, g.top)) == (0, 0, 0), u"the card reaches the very corner"
    square = [rgb(px(plain, g.left + dx, g.top + dy)) for dy in range(g.radius)
              for dx in range(g.radius)]
    # ⚠ Darker than the card's DARKEST colour (its gradient's foot): M11e-02 survived
    # a bar at CARD_TOP, because the gradient itself crosses it inside the corner.
    darkest = min(splash.CARD_TOP[0], splash.CARD_BOTTOM[0])
    assert sum(1 for c in square if 0 < c[0] < darkest) >= 2, \
        u"a hard corner: no pixel of the outline is part covered"
    for dy in range(g.radius):
        for dx in range(g.radius):
            left = px(plain, g.left + dx, g.top + dy)
            right = px(plain, g.right - 1 - dx, g.top + dy)
            assert left == right, (dx, dy, left, right)


#: ⭐ THE REFERENCE IS CHROME'S OWN PIXELS: the mock's `.splash` CSS rendered by headless
#: Chrome at DPI 96 over white, alpha = 1 - value/255 (the shadow is black), measured
#: 2026-09-24 at these distances from the card's edge. The native model matched every
#: one within 0.008.
CHROME_SHADOW = (
    (u"below", 1, 0.435), (u"below", 11, 0.380), (u"below", 21, 0.314),
    (u"below", 31, 0.235), (u"below", 41, 0.165), (u"below", 51, 0.106),
    (u"below", 61, 0.059), (u"below", 71, 0.027), (u"below", 81, 0.012),
    (u"right", 1, 0.110), (u"right", 10, 0.078), (u"right", 19, 0.051),
    (u"right", 28, 0.031), (u"right", 37, 0.020), (u"right", 46, 0.012),
    (u"above", 4, 0.078), (u"above", 12, 0.047), (u"above", 20, 0.027),
    (u"above", 28, 0.012))


def test_the_shadow_is_the_one_chrome_draws_for_the_mock(plain):
    g = plain.geo
    cx, cy = g.left + g.card_w // 2, g.top + g.card_h // 2
    where = {u"below": lambda k: (cx, g.bottom + k - 1), u"right": lambda k: (g.right + k - 1, cy),
             u"above": lambda k: (cx, g.top - k)}
    off = []
    for side, k, want in CHROME_SHADOW:
        got = px(plain, *where[side](k))[3] / 255.0
        if abs(got - want) > 0.02:
            off.append(u"%s %d px: %.3f, Chrome %.3f" % (side, k, got, want))
    assert not off, u"the shadow is not the mock's: " + u"; ".join(off)
    for x in (0, g.width - 1):
        for y in (0, g.height - 1):
            assert px(plain, x, y)[3] <= 1, u"the shadow is cut off at the canvas' edge"


def test_the_sweep_runs_along_the_line_on_the_ruled_curve(plain):
    g = plain.geo
    width = g.run_right - g.run_left

    def colours(phase):
        row = plain.sweep(phase)
        return [(row[i + 2], row[i + 1], row[i]) for i in range(0, len(row), 4)]

    assert set(colours(0.0)) == {splash.LINE}, u"at the start the segment is off the left"
    assert splash.ease(0.0) == 0.0 and abs(splash.ease(1.0) - 1.0) < 1e-6
    steps = [splash.ease(i / 20.0) for i in range(21)]
    assert steps == sorted(steps) and splash.ease(0.5) > 0.8, u"not the ruled curve"
    # the moment the segment's left edge is at 30% of the line: its peak at 49%
    half = next(i / 1000.0 for i in range(1000)
                if -0.40 + 1.40 * splash.ease(i / 1000.0) >= 0.30)
    line = colours(half)
    peak = min(range(width), key=lambda i: sum(abs(a - b) for a, b in
                                               zip(line[i], splash.ACCENT)))
    assert abs(peak - 0.49 * width) <= 3, (peak, 0.49 * width)
    assert near(line[peak], splash.ACCENT, 3)
    for colour in line:                                  # only LINE-to-ACCENT mixes
        t = (colour[0] - splash.LINE[0]) / float(splash.ACCENT[0] - splash.LINE[0])
        assert near(colour, [a + (b - a) * t for a, b in zip(splash.LINE, splash.ACCENT)], 2)


def test_a_frame_repaints_only_the_run_line():
    u"""⭐ The words are drawn ONCE, by GDI; a frame that repainted any other row
    would wipe them."""
    card = splash.paint(u"1.0.5", 96)
    g = card.geo
    before = bytes(card.pixels)
    offset, rows = card.run_line(0.37)
    stride = g.width * 4
    assert offset == g.run_top * stride and len(rows) == g.run * stride
    assert bytes(card.pixels[offset:offset + len(rows)]) == rows
    assert card.pixels[:offset] == before[:offset]
    assert card.pixels[offset + len(rows):] == before[offset + len(rows):]
    assert card.pixels[offset:offset + len(rows)] != before[offset:offset + len(rows)], \
        u"the control: the frame moved nothing"


def test_the_run_line_is_clipped_by_the_rounded_corners(plain):
    u"""The mock's card is `overflow: hidden`: the coral line follows the curve, it
    does not square the corners off -- in every frame, wherever the segment is.
    ⭐ The corners are symmetric top to bottom, so each run-line row covers exactly as
    many pixels whole as its mirror row at the top of the card, where no line runs."""
    g = plain.geo

    def whole(y):
        return sum(1 for x in range(g.left, g.right) if px(plain, x, y)[3] == 255)

    for phase in (0.0, 0.05, 0.3, 0.97):
        plain.run_line(phase)
        for y in range(g.run_top, g.run_top + g.run):
            assert whole(y) == whole(g.top + (g.bottom - 1 - y)), \
                u"the line squared a corner off (row %d, phase %s)" % (y - g.run_top, phase)
    plain.run_line(0.0)
    for y in range(g.run_top, g.run_top + g.run):
        for dx in range(g.radius):
            assert px(plain, g.left + dx, y) == px(plain, g.right - 1 - dx, y), (dx, y)


def test_the_sweep_colours_the_curve_too(plain):
    u"""Where the segment passes over a corner, the part-covered pixels on the curve
    take its colour as well -- or the line's end would stay grey while coral runs up
    to it."""
    g = plain.geo
    plain.run_line(0.0)
    # ⚠ the pixels where the border's inner edge crosses the line -- part border, part
    # line, fully covered; the ones on the OUTER edge are border alone and stay grey
    plain_colours = (splash.LINE, splash.LINE_HI)
    curve = [(x, y) for y in range(g.run_top, g.run_top + g.run)
             for x in range(g.left, g.left + g.radius)
             if px(plain, x, y)[3] == 255 and rgb(px(plain, x, y)) not in plain_colours]
    assert curve, u"the control: the run rows have no pixel on the curve"
    grey = dict((p, px(plain, *p)[2]) for p in curve)
    over = next(i / 1000.0 for i in range(1000)
                if -0.40 + 1.40 * splash.ease(i / 1000.0) >= -0.12)   # the left end, lit
    plain.run_line(over)
    assert any(px(plain, *p)[2] > grey[p] for p in curve), u"the curve stayed grey"
    plain.run_line(0.0)


# ---------------------------------------------------------------------------
# the mark: hato's own PNG, read and made smaller here
# ---------------------------------------------------------------------------

def _png(width, height, rgba, filters, colour=6, depth=8, interlace=0):
    u"""A PNG written by hand, one row per filter in `filters` (cycled)."""
    bpp = 4 if colour == 6 else 3
    stride = width * bpp
    raw, above = bytearray(), bytearray(stride)
    for y in range(height):
        line = rgba[y * stride:(y + 1) * stride]
        kind = filters[y % len(filters)]
        out = bytearray(stride)
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = above[i], above[i - bpp] if i >= bpp else 0
            if kind == 0:
                pred = 0
            elif kind == 1:
                pred = a
            elif kind == 2:
                pred = b
            elif kind == 3:
                pred = (a + b) >> 1
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
            out[i] = (line[i] - pred) & 255
        raw += bytes([kind]) + out
        above = bytearray(line)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(
            ">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(bytes(raw)))
            + chunk(b"IEND", b""))


def test_every_filter_a_png_may_use_is_read(tmp_path):
    width, height = 7, 10
    rgba = bytes((x * 37 + y * 11 + c * 53) & 255 for y in range(height) for x in range(width)
                 for c in range(4))
    path = tmp_path / u"filters.png"
    path.write_bytes(_png(width, height, rgba, filters=(0, 1, 2, 3, 4)))
    assert splash.read_png(str(path)) == (width, height, rgba)
    rgb_only = bytes(v for i, v in enumerate(rgba) if i % 4 != 3)
    path.write_bytes(_png(width, height, rgb_only, filters=(4, 3, 2, 1, 0), colour=2))
    got = splash.read_png(str(path))
    assert got[2][3::4] == b"\xff" * (width * height) and got[2][0::4] == rgba[0::4]
    for odd in ({u"interlace": 1}, {u"depth": 16}):
        path.write_bytes(_png(width, height, rgba, (0,), **odd))
        assert splash.read_png(str(path)) is None, odd


def test_a_smaller_mark_is_the_area_it_covers_premultiplied():
    u"""Opaque red beside a TRANSPARENT blue pixel is half-transparent RED: a pixel that
    is not there has no colour to give. A straight average turns every edge of the
    mark towards whatever the transparent pixels happen to hold."""
    red_and_nothing = bytes((255, 0, 0, 255, 0, 0, 255, 0))
    bgra = splash.scale_png(2, 1, red_and_nothing, 1)
    assert bgra == bytes((0, 0, 128, 128)), tuple(bgra)
    flat = bytes((10, 20, 30, 255)) * 16
    assert splash.scale_png(4, 4, flat, 2) == bytes((30, 20, 10, 255)) * 4


def test_the_mark_is_hatos_own_at_the_size_the_card_asks():
    u"""The SMALLEST of hato's marks that is still big enough: area-averaged down, never
    stretched up -- and not the biggest, averaged over twice the pixels it needs."""
    folder = os.path.join(os.path.dirname(HERE), "hato", "data")
    sizes = sorted(int(m.group(1)) for m in (re.match(r"hato-(\d+)\.png$", n)
                                            for n in os.listdir(folder)) if m)
    for size in (40, 50, 100, 140, 999):
        path = splash.mark_path(size)
        assert path and os.path.isfile(path), size
        found = int(re.search(r"hato-(\d+)\.png$", path).group(1))
        fits = [n for n in sizes if n >= size]
        assert found == (fits[0] if fits else sizes[-1]), (size, found, sizes)
    got = splash.load_mark(40)
    assert got and got[0] == 40 and len(got[1]) == 40 * 40 * 4
    alphas = got[1][3::4]
    assert 255 in alphas and 0 in alphas, u"no mark drawn, or no edge to it"
    card = splash.paint(u"1.0.5", 96)
    g = card.geo
    marked = [px(card, g.mark_x + x, g.mark_y + y) for y in range(g.mark) for x in range(g.mark)]
    assert sum(1 for p in marked if p[2] > p[1] + 60) > 100, \
        u"the card has no coral mark where the mock puts it"


# ---------------------------------------------------------------------------
# the words -- GDI, into a bitmap: Windows
# ---------------------------------------------------------------------------

def _ink(card, colour, x0, x1, y0, y1, tol=24):
    return sum(1 for y in range(y0, y1) for x in range(x0, x1)
               if near(rgb(px(card, x, y)), colour, tol))


@pytest.mark.skipif(not WINDOWS, reason=u"the words are drawn by GDI, Windows' own")
@pytest.mark.parametrize("dpi", [96, 240])
def test_the_words_are_where_the_mock_puts_them(dpi):
    card = splash.paint(u"1.0.5", dpi)
    g = card.geo
    cap = int(g.title_px * 0.75)
    title = (g.title_base - cap, g.title_base + 1)
    sub = (g.sub_base - int(g.sub_px * 0.75), g.sub_base + 1)
    assert _ink(card, splash.INK, g.text_x, g.text_right, *title) > 20 * g.scale, \
        u"no title in the title's line"
    first = min(x for y in range(*title) for x in range(g.left, g.right)
                if near(rgb(px(card, x, y)), splash.INK, 24))
    assert g.text_x <= first <= g.text_x + 3 * g.scale, \
        u"the title starts at %d, the mock's column is %d" % (first, g.text_x)
    assert _ink(card, splash.ACCENT, g.text_x, g.text_right, *title) > 10 * g.scale, \
        u"the version is not in coral"
    assert _ink(card, splash.INK_DIM, g.text_x, g.text_right, *sub) > 20 * g.scale, \
        u"no second line"
    assert _ink(card, splash.ACCENT, g.text_x, g.text_right, *sub) == 0
    words = [x for y in range(g.top + g.border, g.run_top) for x in range(g.text_right, g.right - g.radius)
             if px(card, x, y) != tuple(splash._opaque(card.fill(y)))]
    assert not words, u"words past the card's right padding"
    assert all(px(card, x, y)[3] == 255 for y in range(title[0], sub[1])
               for x in range(g.text_x, g.text_right)), u"GDI's alpha 0 was left in the words"


@pytest.mark.skipif(not WINDOWS, reason=u"the words are drawn by GDI, Windows' own")
def test_going_back_says_so_in_the_same_card():
    u"""*Go back* swaps with the same swapper and the same card -- in the window's own
    words, so the version in coral starts after the longer lead."""
    def first_coral(card):
        g = card.geo
        return min(x for y in range(g.title_base - g.title_px, g.title_base + 1)
                   for x in range(g.text_x, g.text_right)
                   if near(rgb(px(card, x, y)), splash.ACCENT, 24))

    ahead, back = splash.paint(u"1.0.5", 96), splash.paint(u"1.0.3", 96, going_back=True)
    assert first_coral(back) > first_coral(ahead) + 5


@pytest.mark.skipif(not WINDOWS, reason=u"GDI's font mapper is Windows'")
def test_a_face_windows_lacks_is_never_used_quietly(monkeypatch):
    u"""⚠ GDI never refuses a face it lacks -- it substitutes another and says nothing.
    The splash ASKS which face it got and moves on to the next it named."""
    api = splash._api()
    dc = api.gdi32.CreateCompatibleDC(None)
    try:
        font = splash._font(api, dc, ((u"No Such Face hato", 600), (u"Segoe UI", 400)), 20)
        buf = api.ct.create_unicode_buffer(64)
        api.gdi32.GetTextFaceW(dc, 64, buf)
        assert font and buf.value == u"Segoe UI", buf.value
    finally:
        api.gdi32.DeleteDC(dc)
        api.gdi32.DeleteObject(font)


# ---------------------------------------------------------------------------
# the fade, and never stopping an update
# ---------------------------------------------------------------------------

def test_it_fades_in_and_out_on_the_ruled_curve():
    assert splash.fade(0.0) == 0 and splash.fade(1.0) == 255
    assert 0 < splash.fade(splash.FADE_SECONDS / 2) < 255
    assert splash.fade(5.0, 0.0) == 255
    assert 0 < splash.fade(5.0, splash.FADE_SECONDS / 2) < 255
    assert splash.fade(5.0, splash.FADE_SECONDS) is None, u"a fade out that never ends"
    assert splash.fade(0.03, 0.03) <= splash.fade(0.03), u"closing while still fading in"


def test_nothing_it_does_can_stop_an_update(monkeypatch):
    u"""⛔ Decoration: a splash that cannot be drawn is a splash not drawn."""
    def broken(*_args):
        raise RuntimeError(u"no")

    monkeypatch.setattr(splash, u"read_png", broken)
    card = splash.paint(u"1.0.5", 96)
    assert card.pixels, u"a mark that cannot be read took the card with it"
    monkeypatch.setattr(splash, u"paint", broken)
    shown = splash.show(u"1.0.5", wait=5.0)
    shown.close()
    shown.close()
    assert not shown.alive() and shown.hwnd is None
    assert splash.show(None, wait=0.0) is not None
    monkeypatch.setattr(splash.sys, u"platform", u"linux")
    elsewhere = splash.show(u"1.0.5")
    assert elsewhere._thread is None and not splash.on_screen()
    elsewhere.close()


@pytest.mark.skipif(not WINDOWS, reason=u"a window is Windows'")
def test_a_card_closed_before_it_is_up_never_shows(monkeypatch):
    u"""The swap can finish before a slow machine has drawn the card: it must then
    never appear, over the new window, with nothing to take it down."""
    release, real = threading.Event(), splash.paint

    def slow(*args, **kwargs):
        release.wait(10)
        return real(*args, **kwargs)

    monkeypatch.setattr(splash, u"paint", slow)
    shown = splash.show(u"1.0.5", wait=0.1)
    assert shown.alive(), u"the control: the card is still being drawn"
    shown.close(wait=0.0)
    release.set()
    shown._thread.join(10)
    # ⚠ THIS card's window, never `on_screen()`: that asks about ANY splash on the
    # desktop, and a real update or a parallel check may have one up
    assert not shown.alive() and shown.hwnd is None


_CHILD = u"""import sys, time
sys.path.insert(0, %r)
from hato import splash
card = splash.show(u"9.9.9")
print("up" if card.hwnd else "no", flush=True)
time.sleep(30)
"""


@pytest.mark.skipif(not WINDOWS, reason=u"a window is Windows'")
def test_a_splash_is_this_updaters_only_when_it_or_its_child_drew_it(tmp_path):
    u"""B2 (ADVERSARY 2026-09-24): `on_screen()` matched the CLASS in every process, so
    another process's card let the window close before its own updater had drawn.
    Scoped: the updater's own splash, or one its child drew (a onefile updater draws
    from its child) -- and no one else's."""
    import subprocess
    script = tmp_path / u"child.py"
    script.write_text(_CHILD % os.path.dirname(HERE), encoding="utf-8")
    child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE)
    try:
        assert child.stdout.readline().strip() == b"up", u"the control: no splash drawn"
        assert splash.on_screen(of=child.pid), u"the child's own splash is not its own"
        assert splash.on_screen(of=os.getpid()), u"a splash my child drew is not mine"
        assert not splash.on_screen(of=4), u"another process's splash counted"
    finally:
        child.terminate()
        child.wait(10)


# ---------------------------------------------------------------------------
# the REAL window: what Windows composed
# ---------------------------------------------------------------------------

def _win32():
    import ctypes
    from ctypes import wintypes as W
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    for name, res, args in (
            ("GetForegroundWindow", W.HWND, []),
            ("GetWindowLongPtrW", ctypes.c_ssize_t, [W.HWND, ctypes.c_int]),
            ("GetWindowRect", W.BOOL, [W.HWND, ctypes.POINTER(W.RECT)]),
            ("GetDpiForWindow", W.UINT, [W.HWND]),
            ("GetDC", W.HDC, [W.HWND]),
            ("ReleaseDC", ctypes.c_int, [W.HWND, W.HDC]),
            ("PrintWindow", W.BOOL, [W.HWND, W.HDC, W.UINT]),
            ("IsWindow", W.BOOL, [W.HWND])):
        getattr(user32, name).restype, getattr(user32, name).argtypes = res, args
    for name, res, args in (
            ("CreateCompatibleDC", W.HDC, [W.HDC]),
            ("CreateCompatibleBitmap", W.HBITMAP, [W.HDC, ctypes.c_int, ctypes.c_int]),
            ("SelectObject", W.HANDLE, [W.HDC, W.HANDLE]),
            ("GetDIBits", ctypes.c_int, [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p,
                                         ctypes.c_void_p, W.UINT]),
            ("DeleteObject", W.BOOL, [W.HANDLE]), ("DeleteDC", W.BOOL, [W.HDC])):
        getattr(gdi32, name).restype, getattr(gdi32, name).argtypes = res, args
    return ctypes, W, user32, gdi32


def _placement(hwnd):
    u"""-> (the window's rect, its monitor's work area), both in DEVICE pixels.
    ⚠ Asked from a per-monitor-aware thread: an unaware one is answered in Windows'
    96-DPI fiction, and a 1318 px card reads as 527."""
    ctypes, W, user32, _gdi32 = _win32()

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT),
                    ("dwFlags", W.DWORD)]

    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.MonitorFromWindow.restype = W.HANDLE
    user32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
    user32.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.POINTER(MONITORINFO)]
    was = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        rect, info = W.RECT(), MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
        return rect, info.rcWork
    finally:
        if was:
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(was))


def _composed(hwnd, width, height):
    u"""What Windows composed for the window -> BGRA bytes, top down.
    ⭐ PrintWindow(PW_RENDERFULLCONTENT) reads the layered window's own surface -- a
    plain BitBlt of the screen leaves a layered window out, and another window on top
    would be in the picture."""
    ctypes, W, user32, gdi32 = _win32()
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(mem, bmp)
    try:
        assert user32.PrintWindow(hwnd, mem, 2), u"PrintWindow refused"

        class Header(ctypes.Structure):
            _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                        ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                        ("image", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG),
                        ("used", W.DWORD), ("important", W.DWORD)]

        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(width * height * 4)
        gdi32.SelectObject(mem, old)
        old = None
        assert gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(header), 0) == height
        return buf.raw
    finally:
        if old:
            gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


@pytest.mark.skipif(not WINDOWS, reason=u"a window is Windows'")
def test_the_real_card_is_on_top_click_through_and_takes_no_focus():
    ctypes, W, user32, _gdi32 = _win32()
    before = user32.GetForegroundWindow()
    shown = splash.show(u"9.9.9")
    try:
        hwnd = shown.hwnd
        assert hwnd and splash.on_screen(), u"no card came up"
        ex = user32.GetWindowLongPtrW(hwnd, -20)
        for name in (u"WS_EX_LAYERED", u"WS_EX_TRANSPARENT", u"WS_EX_TOPMOST",
                     u"WS_EX_TOOLWINDOW", u"WS_EX_NOACTIVATE"):
            assert ex & getattr(splash, name), u"the card is not %s" % name
        assert user32.GetForegroundWindow() == before, u"the card took the focus"
        g = shown.card.geo
        assert g.dpi == user32.GetDpiForWindow(hwnd), u"drawn for a DPI not its monitor's"
        rect, work = _placement(hwnd)
        assert (rect.right - rect.left, rect.bottom - rect.top) == (g.width, g.height)
        card_x, card_y = rect.left + g.left, rect.top + g.top
        assert abs(2 * card_x + g.card_w - (work.left + work.right)) <= 2 and \
            abs(2 * card_y + g.card_h - (work.top + work.bottom)) <= 2, \
            u"the card is not centred on its monitor's work area"
        time.sleep(splash.FADE_SECONDS + 0.25)                   # past the fade in
        shot = _composed(hwnd, g.width, g.height)
        if not any(shot):
            pytest.skip(u"this desktop composes nothing for PrintWindow (a locked or "
                        u"session-0 desktop) -- the pixels cannot be read here")
        x, y = g.right - 40, g.top + g.card_h // 2
        at = (y * g.width + x) * 4
        assert near(shot[at:at + 3], splash._opaque(shown.card.fill(y))[:3], 2), \
            u"Windows composed %s where the card is %s" % (tuple(shot[at:at + 3]),
                                                          tuple(splash._opaque(shown.card.fill(y))))
    finally:
        started = time.monotonic()
        shown.close()
        took = time.monotonic() - started
    assert not shown.alive() and not user32.IsWindow(hwnd), u"the card is still up"
    assert took < 1.0, u"close() took %.2f s" % took
    shown.close()
