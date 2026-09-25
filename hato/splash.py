# -*- coding: utf-8 -*-
u"""The update splash -- RUNBOOK 11e. The swapper draws it while NO hato window exists.

    card = splash.show(u"1.0.5")       # returns once the card is on screen
    ...                                # the swapper waits, swaps, starts the new window
    card.close()                       # the moment that window shows: it fades away

⭐ THE PICTURE IS THE RULED MOCK -- `gui-mock/mock-update.html` state 4 and
`shots-update/07-4-window-closed.png`: a dark card 360 wide, the mark, *"Updating hato
to 1.0.5"* with the version in coral, *"hato opens again in a moment"*, a coral sweep
along its foot. Every measure below is that stylesheet's, in CSS px, scaled to the
monitor's DPI. ⭐ Its shadow was MEASURED, not guessed (2026-09-24): Chrome draws
`0 26px 70px -18px #000` as a gaussian of sigma 35 over the inset rect -- the
separable model below fits Chrome's own pixels to an rms of 0.004 (DPI 96).

⭐ A LAYERED WINDOW WITH PER-PIXEL ALPHA: the only way Windows 10 draws soft,
anti-aliased corners and a real shadow. Everything but the words is computed HERE,
in plain Python over a byte buffer, so a check reads every pixel with no window
(`tests/test_splash.py`); GDI then draws the words onto the OPAQUE card, where
ClearType has a real ground.

⛔ STDLIB + CTYPES ONLY, AND NOTHING ELSE OF hato: it runs inside `hato-update.exe`
while hato's own folder is renamed away (a static check holds it to this). The
colours are therefore COPIES of `hato/gui/theme.py`'s, and a check pins them.
⛔ NEVER RAISES, NEVER TAKES FOCUS, NEVER CATCHES A CLICK: a splash that cannot be
drawn is a splash not drawn -- the update goes on -- and whatever the person was
typing into keeps the keyboard.
"""
import math
import os
import struct
import sys
import threading
import time
import zlib

#: The ruled tokens, as (r, g, b). ⚠ COPIES of hato/gui/theme.py -- pinned by a check.
CARD_TOP = (0x24, 0x28, 0x31)
CARD_BOTTOM = (0x1F, 0x23, 0x29)
LINE_HI = (0x3A, 0x41, 0x4C)
LINE = (0x2B, 0x30, 0x38)
INK = (0xE7, 0xE9, 0xEC)
INK_DIM = (0x8B, 0x92, 0x9C)
ACCENT = (0xF8, 0xA8, 0x90)

#: The mock's `.splash` rules, in CSS px. ⚠ `box-sizing: border-box`: the 360 holds
#: the border.
WIDTH, BORDER, RADIUS = 360, 1, 12
PAD_TOP, PAD_RIGHT, PAD_BOTTOM, PAD_LEFT = 18, 20, 16, 20
MARK, GAP, RUN = 40, 13, 3
TITLE_PX, SUB_PX, LINE_HEIGHT, SUB_GAP = 14.0, 11.5, 1.5, 1.0
HEIGHT = BORDER + PAD_TOP + MARK + PAD_BOTTOM + RUN + BORDER
#: `box-shadow: 0 26px 70px -18px #000` -- a blur of 70 is a gaussian of sigma 35.
SHADOW_DROP, SHADOW_BLUR, SHADOW_SPREAD = 26.0, 70.0, -18.0
#: The sweep: 38% of the line, `left` from -40% to 100% in 1.4 s, on the ruled curve.
SWEEP_SECONDS, SWEEP_WIDTH, SWEEP_FROM, SWEEP_TO = 1.4, 0.38, -0.40, 1.00
EASE = (0.2, 0.7, 0.3, 1.0)                  # --ease: cubic-bezier(.2,.7,.3,1)
FADE_SECONDS = 0.12                          # --fast
FRAME_MS = 15
#: Segoe UI's ascent and descent per em (2210 and 514 of 2048) -- where CSS puts a
#: baseline in its line box.
ASCENT, DESCENT = 2210 / 2048.0, 514 / 2048.0

TITLE = u"Updating hato to "
#: ⭐ Go back swaps too, with this same splash -- in the window's own words ("Go back
#: to 1.0.3?", "Back on 1.0.3").
TITLE_BACK = u"Going back to hato "
SUBTITLE = u"hato opens again in a moment"
CLASS_NAME = u"hatoUpdateSplash"
WINDOW_TEXT = u"Updating hato"
FACES = ((u"Segoe UI Semibold", 600), (u"Segoe UI", 600))
SUB_FACES = ((u"Segoe UI", 400),)


# ---------------------------------------------------------------------------
# the measures, at one DPI
# ---------------------------------------------------------------------------

def _px(value, scale):
    u"""CSS px -> device px, half up (the browser's snapping, not banker's rounding)."""
    return int(math.floor(value * scale + 0.5))


def _baseline(size, line_height):
    u"""Where CSS puts a baseline in a line box: half the leading, then the ascent."""
    return (line_height - size * (ASCENT + DESCENT)) / 2.0 + size * ASCENT


class Geometry(object):
    u"""The card in DEVICE pixels at one DPI, inside the margin its shadow falls in."""

    def __init__(self, dpi=96):
        self.dpi = int(dpi) if dpi and dpi > 0 else 96
        s = self.scale = self.dpi / 96.0
        self.card_w, self.card_h = _px(WIDTH, s), _px(HEIGHT, s)
        self.border = max(1, int(BORDER * s))
        self.radius = _px(RADIUS, s)
        self.run = max(1, _px(RUN, s))
        # the shadow: the card's rect inset by the spread, dropped, blurred -- and the
        # margin that holds all of it (beyond 2.9 sigma its alpha is under 0.5/255)
        self.sigma = SHADOW_BLUR / 2.0 * s
        inset, drop = -SHADOW_SPREAD * s, SHADOW_DROP * s
        reach = 2.9 * self.sigma
        side = int(math.ceil(reach - inset))
        above = max(0, int(math.ceil(reach - drop - inset)))
        below = max(0, int(math.ceil(reach + drop - inset)))
        self.left, self.top = side, above
        self.right, self.bottom = side + self.card_w, above + self.card_h
        self.width, self.height = self.right + side, self.bottom + below
        self.shadow = (self.left + inset, self.top + drop + inset,
                       self.right - inset, self.bottom + drop - inset)
        # the run line: the padding box's last RUN rows
        self.run_top = self.bottom - self.border - self.run
        self.run_left, self.run_right = self.left + self.border, self.right - self.border
        # the row: the mark, then the two lines, each baseline where CSS puts it
        self.mark = _px(MARK, s)
        self.mark_x = self.left + _px(BORDER + PAD_LEFT, s)
        self.mark_y = self.top + _px(BORDER + PAD_TOP, s)
        self.text_x = self.left + _px(BORDER + PAD_LEFT + MARK + GAP, s)
        self.text_right = self.right - _px(BORDER + PAD_RIGHT, s)
        title_lh, sub_lh = TITLE_PX * LINE_HEIGHT, SUB_PX * LINE_HEIGHT
        block = title_lh + SUB_GAP + sub_lh
        first = BORDER + PAD_TOP + (max(MARK, block) - block) / 2.0
        self.title_base = self.top + _px(first + _baseline(TITLE_PX, title_lh), s)
        self.sub_base = self.top + _px(first + title_lh + SUB_GAP
                                       + _baseline(SUB_PX, sub_lh), s)
        self.title_px, self.sub_px = _px(TITLE_PX, s), _px(SUB_PX, s)


# ---------------------------------------------------------------------------
# the picture, in plain Python -- no window needed to read a pixel
# ---------------------------------------------------------------------------

def ease(progress, curve=EASE):
    u"""cubic-bezier(x1, y1, x2, y2) at a time `progress` in [0, 1] -> [0, 1]."""
    x1, y1, x2, y2 = curve
    if progress <= 0.0 or progress >= 1.0:     # the curve's own ends, exactly
        return 0.0 if progress <= 0.0 else 1.0

    def bezier(t, a, b):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t ** 2 + t ** 3

    lo, hi = 0.0, 1.0
    for _ in range(32):                        # x(t) rises: bisect for the time
        mid = (lo + hi) / 2
        if bezier(mid, x1, x2) < progress:
            lo = mid
        else:
            hi = mid
    return bezier((lo + hi) / 2, y1, y2)


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _opaque(rgb):
    u"""(r, g, b) -> one opaque BGRA pixel."""
    return bytes((int(rgb[2] + 0.5), int(rgb[1] + 0.5), int(rgb[0] + 0.5), 255))


def _clamp(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _cover(a, b, centre, sigma):
    u"""How much of a gaussian of `sigma` centred at `centre` lies in [a, b]."""
    k = sigma * math.sqrt(2.0)
    return 0.5 * (math.erf((b - centre) / k) - math.erf((a - centre) / k))


class Card(object):
    u"""The card at one DPI as premultiplied BGRA rows, top down -- the shadow, the
    gradient, the border, the anti-aliased corners, the mark and the run line.
    `_words()` adds the two lines through GDI; `run_line()` moves the sweep."""

    def __init__(self, geo, mark=None):
        self.geo = geo
        self.pixels = bytearray(geo.width * geo.height * 4)
        self._shadow()
        self._body()
        self._edges = self._corners()
        if mark is not None:
            self._mark(*mark)
        line = geo.run_right - geo.run_left
        size = max(1, int(round(SWEEP_WIDTH * line)))
        self._line = _opaque(LINE)
        self._segment = b"".join(
            _opaque(_mix(LINE, ACCENT, 1.0 - abs(2.0 * (i + 0.5) / size - 1.0)))
            for i in range(size))
        self.run_line(0.0)

    def fill(self, y):
        u"""The card's own colour on row `y`: the gradient over its padding box."""
        geo = self.geo
        span = max(1, geo.card_h - 2 * geo.border)
        return _mix(CARD_TOP, CARD_BOTTOM, _clamp((y + 0.5 - geo.top - geo.border) / span))

    def shadow_at(self, x, y):
        return self._cols[x] * self._rows[y]

    def _shadow(self):
        u"""Black, separable: a blurred RECT is x-coverage times y-coverage (a spread
        of -18 leaves the 12 px corners nothing to round)."""
        geo, px = self.geo, self.pixels
        x0, y0, x1, y1 = geo.shadow
        self._cols = [_cover(x0, x1, x + 0.5, geo.sigma) for x in range(geo.width)]
        self._rows = [_cover(y0, y1, y + 0.5, geo.sigma) for y in range(geo.height)]
        across = bytes(int(255 * c + 0.5) for c in self._cols)
        stride = geo.width * 4
        for y, down in enumerate(self._rows):
            if down * 255 < 0.5:
                continue
            table = bytes(int(q * down + 0.5) for q in range(256))
            px[y * stride + 3:(y + 1) * stride:4] = across.translate(table)

    def _body(self):
        geo, px = self.geo, self.pixels
        stride, b, hi = geo.width * 4, geo.border, _opaque(LINE_HI)
        for y in range(geo.top, geo.bottom):
            if y < geo.top + b or y >= geo.bottom - b:
                row = hi * geo.card_w
            else:
                row = hi * b + _opaque(self.fill(y)) * (geo.card_w - 2 * b) + hi * b
            start = y * stride + geo.left * 4
            px[start:start + geo.card_w * 4] = row

    def _corners(self):
        u"""The four rounded corners, each pixel by how much of it the card and its
        border cover, over the shadow beneath. -> what every frame must redo on the
        run line's rows, {row: (first, last, [(x, inner, ring, under), ...])}: the
        span the card fills whole, and the few pixels ON the curve. ⭐ The rest of a
        corner never changes, so it is drawn once, here -- measured, re-blending every
        corner pixel cost 6.8 ms a frame at DPI 240."""
        geo = self.geo
        r, b = geo.radius, geo.border
        run_rows = set(range(geo.run_top, geo.run_top + geo.run))
        edges = dict((y, [geo.left + r, geo.right - r, []]) for y in run_rows)
        squares = ((geo.left + r, geo.top + r, geo.left, geo.top),
                   (geo.right - r, geo.top + r, geo.right - r, geo.top),
                   (geo.left + r, geo.bottom - r, geo.left, geo.bottom - r),
                   (geo.right - r, geo.bottom - r, geo.right - r, geo.bottom - r))
        for cx, cy, x0, y0 in squares:
            for y in range(y0, y0 + r):
                for x in range(x0, x0 + r):
                    d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                    outer = _clamp(r - d + 0.5)
                    inner = _clamp(r - b - d + 0.5)
                    under = self.shadow_at(x, y) * (1.0 - outer)
                    edge = edges.get(y)
                    if edge is None or outer == 0.0:
                        self._blend(x, y, self.fill(y), inner, outer - inner, under)
                    elif inner == 1.0:
                        edge[0], edge[1] = min(edge[0], x), max(edge[1], x + 1)
                    else:
                        edge[2].append((x, inner, outer - inner, under))
        return edges

    def _blend(self, x, y, fill, inner, ring, under):
        u"""One edge pixel: the fill and the border by their cover, over black shadow."""
        c = [fill[i] * inner + LINE_HI[i] * ring for i in range(3)]
        at = (y * self.geo.width + x) * 4
        self.pixels[at:at + 4] = bytes((int(c[2] + 0.5), int(c[1] + 0.5), int(c[0] + 0.5),
                                        int((inner + ring + under) * 255 + 0.5)))

    def _mark(self, size, bgra):
        u"""hato's mark, premultiplied, laid OVER the card (which is opaque there)."""
        geo, px = self.geo, self.pixels
        for my in range(size):
            row = ((geo.mark_y + my) * geo.width + geo.mark_x) * 4
            for mx in range(size):
                s = my * size * 4 + mx * 4
                alpha = bgra[s + 3]
                if not alpha:
                    continue
                at, keep = row + mx * 4, 1.0 - alpha / 255.0
                for i in range(3):
                    px[at + i] = min(255, int(bgra[s + i] + px[at + i] * keep + 0.5))
                px[at + 3] = 255

    def sweep(self, phase):
        u"""The run line's colours at `phase` in [0, 1) -> BGRA bytes, one per pixel
        of the line's width: the ruled segment pasted onto the plain track."""
        geo = self.geo
        width = geo.run_right - geo.run_left
        size = len(self._segment) // 4
        start = int(math.floor(width * (SWEEP_FROM + (SWEEP_TO - SWEEP_FROM) * ease(phase))
                               + 0.5))
        row = bytearray(self._line * width)
        a, z = max(0, start), min(width, start + size)
        if a < z:
            row[a * 4:z * 4] = self._segment[(a - start) * 4:(z - start) * 4]
        return row

    def run_line(self, phase):
        u"""Move the sweep to `phase` -> (offset, bytes): the rows rewritten, to copy
        into the window's bitmap. ⭐ Only these rows: the words are never repainted."""
        geo, px = self.geo, self.pixels
        colours = self.sweep(phase)
        stride = geo.width * 4
        for y in range(geo.run_top, geo.run_top + geo.run):
            a, z, curve = self._edges[y]
            start = y * stride + a * 4
            px[start:start + (z - a) * 4] = colours[(a - geo.run_left) * 4:
                                                    (z - geo.run_left) * 4]
            for x, inner, ring, under in curve:
                i = (x - geo.run_left) * 4
                fill = LINE if i < 0 or i >= len(colours) else \
                    (colours[i + 2], colours[i + 1], colours[i])
                self._blend(x, y, fill, inner, ring, under)
        first = geo.run_top * stride
        return first, bytes(px[first:first + geo.run * stride])

    def opaque(self):
        u"""Alpha back to 255 across the card's straight body -- GDI writes alpha 0
        where it draws. ⚠ Never the corners: they carry their own cover."""
        geo, px, r = self.geo, self.pixels, self.geo.radius
        stride = geo.width * 4
        for y in range(geo.top, geo.bottom):
            edge = y < geo.top + r or y >= geo.bottom - r
            a, z = (geo.left + r, geo.right - r) if edge else (geo.left, geo.right)
            start = y * stride + a * 4 + 3
            px[start:start + (z - a) * 4:4] = b"\xff" * (z - a)


# ---------------------------------------------------------------------------
# the mark: hato's own PNG, read and scaled here -- plain Python, no imaging library
# ---------------------------------------------------------------------------

def mark_path(size):
    u"""The smallest of hato's marks (`hato/data/hato-<n>.png`) at least `size` px --
    else the largest -> a path, or None. ⭐ Beside this module in the frozen swapper
    too: the spec gives `hato-update.exe` the same `hato/data` files."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"data")
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    sizes = []
    for name in names:
        middle = name[5:-4]
        if name.startswith(u"hato-") and name.endswith(u".png") and middle.isdigit():
            sizes.append(int(middle))
    if not sizes:
        return None
    fits = [n for n in sizes if n >= size]
    return os.path.join(folder, u"hato-%d.png" % (min(fits) if fits else max(sizes)))


def read_png(path):
    u"""An 8-bit RGBA or RGB PNG, not interlaced -> (width, height, RGBA bytes), or
    None for anything else. hato's marks are exactly that."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, chunks, head = 8, [], None
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            chunks.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if head is None:
        return None
    width, height, depth, colour, _method, _filter, interlace = head
    if depth != 8 or interlace != 0 or colour not in (2, 6):
        return None
    bpp = 4 if colour == 6 else 3
    raw = zlib.decompress(b"".join(chunks))
    stride = width * bpp
    out, above, pos = bytearray(height * stride), bytearray(stride), 0
    for y in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + above[i]) & 255
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + above[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = above[i], above[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif kind != 0:
            return None
        out[y * stride:(y + 1) * stride] = line
        above = line
    if bpp == 3:
        rgba = bytearray(width * height * 4)
        rgba[0::4], rgba[1::4], rgba[2::4] = out[0::3], out[1::3], out[2::3]
        rgba[3::4] = b"\xff" * (width * height)
        out = rgba
    return width, height, bytes(out)


def _spans(source, size):
    u"""For each of `size` cells, the source cells it covers and each one's share."""
    ratio = source / float(size)
    out = []
    for cell in range(size):
        a, b = cell * ratio, (cell + 1) * ratio
        shares, i = [], int(a)
        while i < b and i < source:
            part = min(b, i + 1) - max(a, i)
            if part > 1e-9:
                shares.append((i, part / ratio))
            i += 1
        out.append(shares)
    return out


def scale_png(width, height, rgba, size):
    u"""RGBA -> `size` x `size` premultiplied BGRA, each cell the AREA it covers --
    the right filter for making a mark smaller (and premultiplied, so a
    transparent edge never bleeds dark into the colour beside it)."""
    pre = []
    for y in range(height):
        row = []
        for x in range(width):
            i = (y * width + x) * 4
            a = rgba[i + 3] / 255.0
            row.append((rgba[i] * a, rgba[i + 1] * a, rgba[i + 2] * a, rgba[i + 3]))
        pre.append(row)
    across, down = _spans(width, size), _spans(height, size)
    half = []
    for row in pre:
        out = []
        for shares in across:
            r = g = b = a = 0.0
            for i, w in shares:
                pr, pg, pb, pa = row[i]
                r, g, b, a = r + pr * w, g + pg * w, b + pb * w, a + pa * w
            out.append((r, g, b, a))
        half.append(out)
    result = bytearray(size * size * 4)
    for cy, shares in enumerate(down):
        for cx in range(size):
            r = g = b = a = 0.0
            for i, w in shares:
                pr, pg, pb, pa = half[i][cx]
                r, g, b, a = r + pr * w, g + pg * w, b + pb * w, a + pa * w
            at = (cy * size + cx) * 4
            alpha = min(255, int(a + 0.5))
            result[at:at + 4] = bytes((min(alpha, int(b + 0.5)), min(alpha, int(g + 0.5)),
                                       min(alpha, int(r + 0.5)), alpha))
    return bytes(result)


def load_mark(size):
    u"""hato's mark at `size` px -> (size, premultiplied BGRA), or None."""
    path = mark_path(size)
    image = read_png(path) if path else None
    if image is None:
        return None
    return size, scale_png(image[0], image[1], image[2], size)


def paint(version, dpi=96, going_back=False):
    u"""The whole card at `dpi` -> a Card: every pixel, the words included where GDI
    exists (Windows). ⛔ Never raises for the mark or the words: a card without them
    is still the card."""
    geo = Geometry(dpi)
    card = Card(geo, _quietly(load_mark, geo.mark))
    if sys.platform.startswith("win"):
        _quietly(_words, card, u"%s" % (version or u""), going_back)
    return card


def _quietly(call, *args):
    try:
        return call(*args)
    except Exception:                         # noqa: BLE001 -- decoration: never raises
        return None


# ---------------------------------------------------------------------------
# Win32, through ctypes: every function's argtypes declared once (the tray's rule)
# ---------------------------------------------------------------------------

_BOUND = {}
_BIND_LOCK = threading.Lock()


def _api():
    u"""The Win32 functions this module calls, each declared -> a namespace."""
    with _BIND_LOCK:
        if u"api" in _BOUND:
            return _BOUND[u"api"]
        import ctypes
        from ctypes import wintypes as W

        class Api(object):
            pass

        api = Api()
        api.ct, api.W = ctypes, W
        api.LRESULT = ctypes.c_ssize_t
        api.WNDPROC = ctypes.WINFUNCTYPE(api.LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", api.WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                        ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                        ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR),
                        ("hIconSm", W.HICON)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                        ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                        ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                        ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                        ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                        ("SourceConstantAlpha", ctypes.c_ubyte),
                        ("AlphaFormat", ctypes.c_ubyte)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT),
                        ("dwFlags", W.DWORD)]

        api.WNDCLASSEXW, api.BITMAPINFOHEADER = WNDCLASSEXW, BITMAPINFOHEADER
        api.BLENDFUNCTION, api.MONITORINFO = BLENDFUNCTION, MONITORINFO
        u = api.user32 = ctypes.WinDLL("user32", use_last_error=True)
        g = api.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        k = api.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        P, H = ctypes.c_void_p, W.HANDLE
        _declare(k.GetModuleHandleW, W.HMODULE, [W.LPCWSTR])
        _declare(u.RegisterClassExW, W.ATOM, [ctypes.POINTER(WNDCLASSEXW)])
        _declare(u.CreateWindowExW, W.HWND,
                 [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                  ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID])
        _declare(u.DefWindowProcW, api.LRESULT, [W.HWND, W.UINT, W.WPARAM, W.LPARAM])
        _declare(u.DestroyWindow, W.BOOL, [W.HWND])
        _declare(u.IsWindow, W.BOOL, [W.HWND])
        _declare(u.IsWindowVisible, W.BOOL, [W.HWND])
        _declare(u.ShowWindow, W.BOOL, [W.HWND, ctypes.c_int])
        _declare(u.FindWindowW, W.HWND, [W.LPCWSTR, W.LPCWSTR])
        _declare(u.FindWindowExW, W.HWND, [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR])
        _declare(u.GetWindowThreadProcessId, W.DWORD, [W.HWND, ctypes.POINTER(W.DWORD)])

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD),
                        ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                        ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]

        api.PROCESSENTRY32W = PROCESSENTRY32W
        _declare(k.CreateToolhelp32Snapshot, H, [W.DWORD, W.DWORD])
        _declare(k.Process32FirstW, W.BOOL, [H, ctypes.POINTER(PROCESSENTRY32W)])
        _declare(k.Process32NextW, W.BOOL, [H, ctypes.POINTER(PROCESSENTRY32W)])
        _declare(k.CloseHandle, W.BOOL, [H])
        _declare(u.SetTimer, ctypes.c_size_t, [W.HWND, ctypes.c_size_t, W.UINT, P])
        _declare(u.KillTimer, W.BOOL, [W.HWND, ctypes.c_size_t])
        _declare(u.GetMessageW, W.BOOL, [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT])
        _declare(u.TranslateMessage, W.BOOL, [ctypes.POINTER(W.MSG)])
        _declare(u.DispatchMessageW, api.LRESULT, [ctypes.POINTER(W.MSG)])
        _declare(u.PostQuitMessage, None, [ctypes.c_int])
        _declare(u.GetCursorPos, W.BOOL, [ctypes.POINTER(W.POINT)])
        _declare(u.MonitorFromPoint, H, [W.POINT, W.DWORD])
        _declare(u.GetMonitorInfoW, W.BOOL, [H, ctypes.POINTER(MONITORINFO)])
        _declare(u.UpdateLayeredWindow, W.BOOL,
                 [W.HWND, W.HDC, ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), W.HDC,
                  ctypes.POINTER(W.POINT), W.COLORREF, ctypes.POINTER(BLENDFUNCTION),
                  W.DWORD])
        _declare(g.CreateCompatibleDC, W.HDC, [W.HDC])
        _declare(g.DeleteDC, W.BOOL, [W.HDC])
        _declare(g.CreateDIBSection, W.HBITMAP,
                 [W.HDC, ctypes.POINTER(BITMAPINFOHEADER), W.UINT, ctypes.POINTER(P), H,
                  W.DWORD])
        _declare(g.SelectObject, H, [W.HDC, H])
        _declare(g.DeleteObject, W.BOOL, [H])
        _declare(g.CreateFontW, W.HFONT, [ctypes.c_int] * 5 + [W.DWORD] * 8 + [W.LPCWSTR])
        _declare(g.GetTextFaceW, ctypes.c_int, [W.HDC, ctypes.c_int, W.LPWSTR])
        _declare(g.SetBkMode, ctypes.c_int, [W.HDC, ctypes.c_int])
        _declare(g.SetTextColor, W.COLORREF, [W.HDC, W.COLORREF])
        _declare(g.SetTextAlign, W.UINT, [W.HDC, W.UINT])
        _declare(g.GetTextExtentPoint32W, W.BOOL,
                 [W.HDC, W.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.SIZE)])
        _declare(g.ExtTextOutW, W.BOOL,
                 [W.HDC, ctypes.c_int, ctypes.c_int, W.UINT, ctypes.POINTER(W.RECT),
                  W.LPCWSTR, W.UINT, P])
        _declare(g.GdiFlush, W.BOOL, [])
        # ⚠ Windows 10 1607+: an older one has no per-thread DPI, and says so by lacking
        # the functions -- the card is then drawn at 96 and Windows scales it
        api.set_dpi = api.get_dpi_context = api.awareness = api.system_dpi = None
        try:
            _declare(u.SetThreadDpiAwarenessContext, P, [P])
            _declare(u.GetThreadDpiAwarenessContext, P, [])
            _declare(u.GetAwarenessFromDpiAwarenessContext, ctypes.c_int, [P])
            _declare(u.GetDpiForSystem, W.UINT, [])
            api.set_dpi = u.SetThreadDpiAwarenessContext
            api.get_dpi_context = u.GetThreadDpiAwarenessContext
            api.awareness = u.GetAwarenessFromDpiAwarenessContext
            api.system_dpi = u.GetDpiForSystem
        except AttributeError:
            pass
        api.monitor_dpi = None
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            _declare(shcore.GetDpiForMonitor, ctypes.c_long,
                     [H, ctypes.c_int, ctypes.POINTER(W.UINT), ctypes.POINTER(W.UINT)])
            api.monitor_dpi = shcore.GetDpiForMonitor
        except (OSError, AttributeError):
            pass
        _BOUND[u"api"] = api
        return api


def _declare(function, restype, argtypes):
    function.restype, function.argtypes = restype, argtypes


def _colorref(rgb):
    return int(rgb[0]) | (int(rgb[1]) << 8) | (int(rgb[2]) << 16)


def _font(api, dc, faces, px):
    u"""The first of `faces` Windows really has -> an HFONT selected into `dc`.
    ⚠ GDI never refuses a face it lacks: it quietly substitutes -- so ASK which face
    it gave (GetTextFaceW), and try the next when it is not the one asked for."""
    buf = api.ct.create_unicode_buffer(64)
    font = None
    for face, weight in faces:
        candidate = api.gdi32.CreateFontW(-int(px), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
                                          face)
        if not candidate:
            continue
        api.gdi32.SelectObject(dc, candidate)
        if font:                              # ⚠ only once it is no longer selected
            api.gdi32.DeleteObject(font)
        font = candidate
        api.gdi32.GetTextFaceW(dc, 64, buf)
        if buf.value.lower() == face.lower():
            break
    return font


def _words(card, version, going_back):
    u"""The two lines, by GDI, into a bitmap holding the card -- then back into the
    card's pixels, opaque again. ClearType against the card's own colour."""
    api = _api()
    ct, W, g = api.ct, api.W, api.gdi32
    geo = card.geo
    dc = g.CreateCompatibleDC(None)
    if not dc:
        return
    fonts, bitmap = [], None
    try:
        header = api.BITMAPINFOHEADER()
        header.biSize = ct.sizeof(api.BITMAPINFOHEADER)
        header.biWidth, header.biHeight = geo.width, -geo.height          # top down
        header.biPlanes, header.biBitCount = 1, 32
        bits = ct.c_void_p()
        bitmap = g.CreateDIBSection(dc, ct.byref(header), 0, ct.byref(bits), None, 0)
        if not bitmap or not bits.value:
            return
        g.SelectObject(dc, bitmap)
        size = len(card.pixels)
        ct.memmove(bits.value, bytes(card.pixels), size)
        g.SetBkMode(dc, 1)                                                # TRANSPARENT
        g.SetTextAlign(dc, 24)                                            # TA_BASELINE
        clip = W.RECT(geo.text_x, geo.top, geo.text_right, geo.run_top)
        lead = TITLE_BACK if going_back else TITLE
        fonts.append(_font(api, dc, FACES, geo.title_px))
        g.SetTextColor(dc, _colorref(INK))
        g.ExtTextOutW(dc, geo.text_x, geo.title_base, 4, ct.byref(clip), lead, len(lead), None)
        extent = W.SIZE()
        g.GetTextExtentPoint32W(dc, lead, len(lead), ct.byref(extent))
        g.SetTextColor(dc, _colorref(ACCENT))
        g.ExtTextOutW(dc, geo.text_x + extent.cx, geo.title_base, 4, ct.byref(clip),
                      version, len(version), None)
        fonts.append(_font(api, dc, SUB_FACES, geo.sub_px))
        g.SetTextColor(dc, _colorref(INK_DIM))
        g.ExtTextOutW(dc, geo.text_x, geo.sub_base, 4, ct.byref(clip), SUBTITLE,
                      len(SUBTITLE), None)
        g.GdiFlush()
        card.pixels[:] = ct.string_at(bits.value, size)
        card.opaque()
    finally:
        # ⚠ The DC FIRST: GDI refuses to delete an object still selected into one,
        # and a deleted DC lets go of everything it held.
        g.DeleteDC(dc)
        for font in fonts:
            if font:
                g.DeleteObject(font)
        if bitmap:
            g.DeleteObject(bitmap)


# ---------------------------------------------------------------------------
# the window -- its own thread, its own message loop
# ---------------------------------------------------------------------------

WM_DESTROY, WM_CLOSE, WM_TIMER = 0x0002, 0x0010, 0x0113
WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x08, 0x20, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x00080000, 0x08000000
#: ⛔ click-through (TRANSPARENT: its shadow is 200 px of mostly nothing), never
#: activated, never on the taskbar or in Alt-Tab -- and above everything
EX_STYLE = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE)
SW_SHOWNOACTIVATE = 4
ULW_ALPHA, AC_SRC_ALPHA = 0x02, 0x01

_LIVE = {}                  # hwnd -> the window it belongs to, for the one procedure
_CLASS = {}


def _procedure(hwnd, message, wparam, lparam):
    u"""The one window procedure, for every splash in this process.
    ⛔ Nothing may leave it: an exception crossing into Windows kills the process."""
    try:
        window = _LIVE.get(hwnd)
        if window is not None:
            answer = window.on_message(message)
            if answer is not None:
                return answer
        return _api().user32.DefWindowProcW(hwnd, message, wparam, lparam)
    except Exception:                         # noqa: BLE001
        return 0


def _register(api):
    u"""The window class, once per process. 🚨 Its procedure is held HERE, for the life
    of the process: a callback only a local holds is freed, and Windows then calls
    into dead memory (hato/tray.py's rule)."""
    if _CLASS.get(u"atom"):
        return True
    _CLASS[u"proc"] = api.WNDPROC(_procedure)
    klass = api.WNDCLASSEXW()
    klass.cbSize = api.ct.sizeof(api.WNDCLASSEXW)
    klass.lpfnWndProc = _CLASS[u"proc"]
    klass.hInstance = api.kernel32.GetModuleHandleW(None)
    klass.lpszClassName = CLASS_NAME
    _CLASS[u"atom"] = api.user32.RegisterClassExW(api.ct.byref(klass))
    return bool(_CLASS[u"atom"])


class Splash(object):
    u"""The card on screen. `close()` fades it away; idempotent, thread-safe, and
    never raises."""

    def __init__(self, version=u"", going_back=False):
        self.version, self.going_back = version, going_back
        self.hwnd = None
        self.card = None
        self.shown_at = None
        self.closing_at = None
        self._thread = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def alive(self):
        return bool(self._thread is not None and self._thread.is_alive())

    def close(self, wait=1.5):
        u"""Fade out, then go. Waits up to `wait` s for the window to be gone."""
        try:
            with self._lock:
                if self.closing_at is None:
                    self.closing_at = time.monotonic()
            thread = self._thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(wait)
        except Exception:                     # noqa: BLE001 -- decoration: never raises
            pass


def show(version, going_back=False, wait=3.0):
    u"""Put the card up -> a `Splash`, whether or not it could be drawn (never raises).
    Returns once it is on screen, has failed, or `wait` s have passed."""
    splash = Splash(u"%s" % (version or u""), bool(going_back))
    if not sys.platform.startswith("win"):
        return splash
    try:
        splash._thread = threading.Thread(target=_run, args=(splash,), name=u"hato-splash",
                                          daemon=True)
        splash._thread.start()
        splash._ready.wait(wait)
    except Exception:                         # noqa: BLE001
        pass
    return splash


def on_screen(of=None):
    u"""True while a splash is up -- with `of`, only one drawn by process `of` or by a
    process IT started (a onefile updater draws from its child). ⭐ The window asks
    this before it closes itself for an update, so the person never sees NOTHING
    between hato and hato. ⚠ Without `of`, ANY process's splash counts -- another
    one on the desktop let the window go before its own had drawn (ADVERSARY
    2026-09-24, B2). Never raises."""
    if not sys.platform.startswith("win"):
        return False
    try:
        api = _api()
        user32, hwnd = api.user32, None
        while True:
            hwnd = user32.FindWindowExW(None, hwnd, CLASS_NAME, None)
            if not hwnd:
                return False
            if not user32.IsWindowVisible(hwnd):
                continue
            if of is None:
                return True
            owner = api.W.DWORD()
            user32.GetWindowThreadProcessId(hwnd, api.ct.byref(owner))
            if owner.value == of or _parent_pid(api, owner.value) == of:
                return True
    except Exception:                         # noqa: BLE001
        return False


def _parent_pid(api, pid):
    u"""The process that started `pid` -> its pid, or None (a Toolhelp32 snapshot --
    the listing the swapper itself reads)."""
    ct, k = api.ct, api.kernel32
    snap = k.CreateToolhelp32Snapshot(2, 0)                 # TH32CS_SNAPPROCESS
    if not snap or snap == ct.c_void_p(-1).value:
        return None
    try:
        entry = api.PROCESSENTRY32W()
        entry.dwSize = ct.sizeof(api.PROCESSENTRY32W)
        more = k.Process32FirstW(snap, ct.byref(entry))
        while more:
            if entry.th32ProcessID == pid:
                return int(entry.th32ParentProcessID)
            more = k.Process32NextW(snap, ct.byref(entry))
    finally:
        k.CloseHandle(snap)
    return None


def _run(splash):
    u"""The splash thread. ⛔ Every exception stops HERE."""
    try:
        _Window(splash).run()
    except Exception:                         # noqa: BLE001
        pass
    finally:
        splash._ready.set()


class _Window(object):

    def __init__(self, splash):
        self.splash = splash
        self.api = None
        self.hwnd = self.dc = self.bitmap = self.old = None
        self.bits = None

    def _place(self):
        u"""-> (dpi, work area) of the monitor under the pointer -- where the person
        just pressed *Restart now*. ⚠ This thread is made per-monitor aware FIRST, or
        every number below is Windows' 96-DPI fiction."""
        api = self.api
        ct, W = api.ct, api.W
        aware = 0
        if api.set_dpi is not None:
            api.set_dpi(ct.c_void_p(-4))                   # PER_MONITOR_AWARE_V2
            aware = api.awareness(api.get_dpi_context())
        point = W.POINT()
        api.user32.GetCursorPos(ct.byref(point))
        monitor = api.user32.MonitorFromPoint(point, 2)    # NEAREST
        info = api.MONITORINFO()
        info.cbSize = ct.sizeof(api.MONITORINFO)
        if not api.user32.GetMonitorInfoW(monitor, ct.byref(info)):
            return None
        dpi = 96
        if aware == 2 and api.monitor_dpi is not None:
            x, y = W.UINT(), W.UINT()
            if api.monitor_dpi(monitor, 0, ct.byref(x), ct.byref(y)) == 0:
                dpi = int(x.value) or 96
        elif aware == 1 and api.system_dpi is not None:
            dpi = int(api.system_dpi()) or 96
        return dpi, info.rcWork

    def run(self):
        self.api = api = _api()
        ct, W, u, g = api.ct, api.W, api.user32, api.gdi32
        placed = self._place()
        if placed is None or not _register(api):
            return
        dpi, work = placed
        splash = self.splash
        card = splash.card = paint(splash.version, dpi, splash.going_back)
        geo = card.geo
        # the CARD centred in the work area -- its shadow falls below it, as in the mock
        self.origin = W.POINT(work.left + (work.right - work.left - geo.card_w) // 2 - geo.left,
                              work.top + (work.bottom - work.top - geo.card_h) // 2 - geo.top)
        self.size = W.SIZE(geo.width, geo.height)
        if splash.closing_at is not None:
            return                                         # closed before it was up
        hwnd = u.CreateWindowExW(EX_STYLE, CLASS_NAME, WINDOW_TEXT, WS_POPUP,
                                 self.origin.x, self.origin.y, geo.width, geo.height,
                                 None, None, api.kernel32.GetModuleHandleW(None), None)
        if not hwnd:
            return
        self.hwnd = splash.hwnd = hwnd
        _LIVE[hwnd] = self
        try:
            self.dc = g.CreateCompatibleDC(None)
            header = api.BITMAPINFOHEADER()
            header.biSize = ct.sizeof(api.BITMAPINFOHEADER)
            header.biWidth, header.biHeight = geo.width, -geo.height
            header.biPlanes, header.biBitCount = 1, 32
            bits = ct.c_void_p()
            self.bitmap = g.CreateDIBSection(self.dc, ct.byref(header), 0, ct.byref(bits),
                                             None, 0)
            if not self.dc or not self.bitmap or not bits.value:
                return
            self.bits = bits.value
            self.old = g.SelectObject(self.dc, self.bitmap)
            ct.memmove(self.bits, bytes(card.pixels), len(card.pixels))
            if splash.closing_at is not None:
                return
            splash.shown_at = time.monotonic()
            self._present(0)
            u.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            u.SetTimer(hwnd, 1, FRAME_MS, None)
            splash._ready.set()
            message = W.MSG()
            while u.GetMessageW(ct.byref(message), None, 0, 0) > 0:
                u.TranslateMessage(ct.byref(message))
                u.DispatchMessageW(ct.byref(message))
        finally:
            _LIVE.pop(hwnd, None)
            if u.IsWindow(hwnd):
                u.DestroyWindow(hwnd)
            if self.old:
                g.SelectObject(self.dc, self.old)
            if self.bitmap:
                g.DeleteObject(self.bitmap)
            if self.dc:
                g.DeleteDC(self.dc)

    def on_message(self, message):
        if message == WM_TIMER:
            self.frame()
            return 0
        if message == WM_CLOSE:
            self.api.user32.DestroyWindow(self.hwnd)
            return 0
        if message == WM_DESTROY:
            self.api.user32.KillTimer(self.hwnd, 1)
            self.api.user32.PostQuitMessage(0)
            return 0
        return None

    def frame(self):
        u"""One frame: the sweep moved, the fade stepped, the window updated -- and at
        the end of a fade out, the window gone."""
        splash, now = self.splash, time.monotonic()
        alpha = fade(now - splash.shown_at, None if splash.closing_at is None
                     else now - max(splash.closing_at, splash.shown_at))
        if alpha is None:
            self.api.user32.DestroyWindow(self.hwnd)
            return
        offset, rows = splash.card.run_line(((now - splash.shown_at) % SWEEP_SECONDS)
                                            / SWEEP_SECONDS)
        self.api.ct.memmove(self.bits + offset, rows, len(rows))
        self._present(alpha)

    def _present(self, alpha):
        api = self.api
        blend = api.BLENDFUNCTION(0, 0, alpha, AC_SRC_ALPHA)
        api.user32.UpdateLayeredWindow(self.hwnd, None, api.ct.byref(self.origin),
                                       api.ct.byref(self.size), self.dc,
                                       api.ct.byref(api.W.POINT(0, 0)), 0,
                                       api.ct.byref(blend), ULW_ALPHA)


def fade(since_shown, since_closing=None):
    u"""The window's opacity, 0..255 -> or None once a fade out has finished. In over
    --fast on the ruled curve; out the same way when asked to close."""
    opacity = ease(since_shown / FADE_SECONDS) if since_shown < FADE_SECONDS else 1.0
    if since_closing is not None:
        if since_closing >= FADE_SECONDS:
            return None
        opacity = min(opacity, 1.0 - ease(since_closing / FADE_SECONDS))
    return int(round(255 * opacity))


__all__ = ["ACCENT", "CARD_BOTTOM", "CARD_TOP", "CLASS_NAME", "Card", "Geometry", "INK",
           "INK_DIM", "LINE", "LINE_HI", "Splash", "ease", "fade", "load_mark", "mark_path",
           "on_screen", "paint", "read_png", "scale_png", "show"]
