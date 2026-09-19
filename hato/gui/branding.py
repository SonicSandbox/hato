# -*- coding: utf-8 -*-
u"""
The mark, found and loaded. RUNBOOK 7c.

    from hato.gui import branding
    app.setWindowIcon(branding.app_icon())
    label.setPixmap(branding.mark_pixmap(40, label.devicePixelRatioF()))

===========================================================================
[!] NOTHING HERE MAY RAISE
===========================================================================

A missing icon is a plainer window; it is not a reason the app will not open.
Every function in this file returns a usable object -- a null `QIcon`, a null
`QPixmap`, `None` for a path -- and the caller paints what it gets. The one
thing that must never happen is an `ImportError`, `OSError` or `KeyError`
escaping into `main()` because a PNG was left out of a wheel.

===========================================================================
[!] THE PATH RESOLVES OFF `hato.__file__`, NEVER OFF THE REPOSITORY
===========================================================================

There are three hosts and they disagree about where the package sits:

  * from source     -> `<repo>/hato/data/`
  * from a wheel    -> `<site-packages>/hato/data/`
  * frozen          -> `<bundle>/hato/data/`, or `sys._MEIPASS/hato/data/`

Resolving through the repository shipped a broken release on tsubasa once:
the file was there on the machine that built it and nowhere on the machine
that installed it. `os.path.dirname(hato.__file__)` is the only expression
that is right on all three.

===========================================================================
[*] EVERY SIZE IS A REAL EXPORT
===========================================================================

`hato/data/` carries `hato-16 .. hato-256`, each one drawn at that size in
the logo pack. [X] Nothing is resampled from the 1024 master, and the master
never enters the wheel (`spec/05-interface.md`: *"only the sizes the window
actually uses get copied into the package"*). `app_icon()` hands the whole
set to one `QIcon` so Qt picks the nearest export for the taskbar, alt-tab
and the window frame; `mark_pixmap()` picks by device pixels, so a 40px mark
on this machine's 2.496 ratio screen loads the 128 rather than blowing up
the 64.
"""
import os

from hato.gui import theme

#: The file name of each export, as copied in. One place, so a rename is one
#: edit and `test_gui_widgets.py` can assert every one of them is on disk.
NAME = u"hato-%d.png"


def data_dir():
    u"""-> the folder holding the icons, or None if it cannot be located.

    [X] Never raises. An interpreter that cannot import `hato` has bigger
    problems than an icon, but it still gets `None` rather than a traceback.
    """
    try:
        import hato
        here = getattr(hato, u"__file__", None)
        if not here:
            return None
        return os.path.join(os.path.dirname(os.path.abspath(here)), u"data")
    except Exception:
        return None


def icon_path(size):
    u"""-> the absolute path of that export, or None if it is not there."""
    folder = data_dir()
    if not folder:
        return None
    try:
        path = os.path.join(folder, NAME % int(size))
    except Exception:
        return None
    return path if os.path.isfile(path) else None


#: ⚠ surasura's mark, at the sizes the settings card uses. RESAMPLED from the
#: one 512 the project publishes -- which is the OPPOSITE of the rule hato's
#: own mark follows, and the difference is that hato's pack ships a real export
#: at every size and surasura's does not. ⛔ Do not read this as licence to
#: resample hato's.
SURASURA_NAME = u"surasura-%d.png"


def surasura_path(size):
    u"""-> the absolute path of surasura's mark at `size`, or None."""
    folder = data_dir()
    if not folder:
        return None
    try:
        path = os.path.join(folder, SURASURA_NAME % int(size))
    except Exception:
        return None
    return path if os.path.isfile(path) else None


def ico_path():
    u"""-> the absolute path of the Windows `.ico`, or None if it is not there.

    ⭐ THE TRAY NEEDS ONE FILE, NOT SEVEN. `Shell_NotifyIcon` takes an `HICON`,
    and `LoadImageW(..., LR_LOADFROMFILE)` reads a `.ico` in one call and picks
    the right entry for the shell's current scale -- where a PNG would have to
    be decoded through GDI+ by hand.

    ⚠ REGENERATE IT FROM THE REAL EXPORTS, never by resampling one of them.
    The logo pack has no vector source, so each entry is the mark drawn at that
    size, and that is the difference between a legible 16px tray icon and mush.
    Built 2026-09-18 with Pillow, verified byte-identical to `hato-16/24/32/48`:

        from PIL import Image
        sizes = [16, 24, 32, 48, 64, 128, 256]
        imgs = [Image.open("hato/data/hato-%d.png" % s).convert("RGBA")
                for s in sizes]
        imgs[-1].save("hato/data/hato.ico", format="ICO",
                      sizes=[(s, s) for s in sizes], append_images=imgs[:-1])

    🚨 BASE IT ON THE LARGEST, AND CHECK THE OUTPUT. Pillow emits no entry
    bigger than the image it is saving, so basing this on the 16 produced a
    valid, plausible, **one-entry** `.ico` with no error of any kind -- six
    sizes silently missing. The entry list alone does not prove it either: it
    cannot tell a real export from a downscale, so the check that settled it
    compared the pixels.

    ⛔ This is build tooling, not a runtime path -- Pillow is NOT a dependency
    and nothing imports it at run time.
    """
    folder = data_dir()
    if not folder:
        return None
    path = os.path.join(folder, u"hato.ico")
    return path if os.path.isfile(path) else None


def available_sizes():
    u"""-> the exports actually present, smallest first. Possibly empty."""
    return tuple(size for size in theme.ICON_SIZES if icon_path(size))


def best_size(wanted):
    u"""-> the export nearest `wanted` without going under it, or the largest.

    [*] NEVER UPSCALES WHEN IT DOES NOT HAVE TO. Asked for 100 device pixels
    it answers 128, not 64 -- a mark drawn at 64 and stretched to 100 is the
    one visible way a real export gets wasted.
    """
    sizes = available_sizes()
    if not sizes:
        return None
    for size in sizes:
        if size >= wanted:
            return size
    return sizes[-1]


def app_icon():
    u"""The window / taskbar icon. -> QIcon, possibly null.

    Every export is added, so Qt chooses rather than scaling.
    """
    try:
        from PyQt6.QtGui import QIcon
    except Exception:
        return None
    icon = QIcon()
    try:
        for size in available_sizes():
            path = icon_path(size)
            if path:
                icon.addFile(path)
    except Exception:
        pass
    return icon


def mark_pixmap(points, ratio=1.0):
    u"""The mark at `points` logical pixels. -> QPixmap, possibly null.

    `ratio` is the widget's `devicePixelRatioF()`. The returned pixmap carries
    it, so Qt draws the high-resolution export at the logical size asked for
    instead of at twice it.
    """
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
    except Exception:
        return None
    try:
        ratio = float(ratio) or 1.0
    except Exception:
        ratio = 1.0
    device = int(round(points * ratio))
    size = best_size(device)
    path = icon_path(size) if size else None
    if not path:
        return QPixmap()
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    if pixmap.width() != device:
        pixmap = pixmap.scaled(device, device,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def surasura_pixmap(points, ratio=1.0):
    u"""surasura's mark at `points` logical pixels. -> QPixmap, possibly null.

    ⚠ Mirrors `mark_pixmap`, including the device-pixel-ratio handling -- a
    mark drawn at 32 and stretched to a 2.5x screen is the one visible way a
    small logo looks cheap. ⛔ Never raises: a missing integration logo is a
    plainer card, not a Settings tab that will not build.
    """
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
    except Exception:
        return None
    try:
        ratio = float(ratio) or 1.0
    except Exception:
        ratio = 1.0
    device = int(round(points * ratio))
    # ⚠ Smallest export NOT under what is needed, so it is never upscaled.
    size = next((s for s in (32, 64, 128) if s >= device), 128)
    path = surasura_path(size)
    if not path:
        return QPixmap()
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    if pixmap.width() != device:
        pixmap = pixmap.scaled(device, device,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


__all__ = ["NAME", "SURASURA_NAME", "app_icon", "available_sizes", "best_size",
           "data_dir", "ico_path", "icon_path", "mark_pixmap",
           "surasura_path", "surasura_pixmap"]
