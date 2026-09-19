# -*- coding: utf-8 -*-
u"""
The tray icon, in `ctypes` over shell32. RUNBOOK 7f.

    tray = Tray(u"hato", branding_ico, [(u"Open hato", open_it),
                                        (u"Run now", run_it),
                                        None,                 # a separator
                                        (u"Quit", None)])     # None -> quit
    tray.run()                                                # blocks

===========================================================================
⛔ NO GUI TOOLKIT, AND NO hato PIPELINE, IN THIS FILE
===========================================================================

This is the other half of `hato/watch.py` and it lives under the same rule,
for the same measured reason (`gui-mock/MEMORY.md`):

    bare python -- the interpreter alone            12.7 MB
    + a real watch handle and buffer                13.4 MB
    + the tray and window APIs resolved as well     13.4 MB
    PyQt6 QApplication + QSystemTrayIcon            30.6 MB

⭐ **Resolving the tray and window APIs through ctypes cost NOTHING measurable
on top of the watching** -- 13.4 MB either way. A resident Qt tray is 2.3x
that, and every megabyte of it is a toolkit doing nothing while nobody is
looking. ⛔ A `QSystemTrayIcon` here would undo the entire reason the watcher
is a separate program, and `tests/test_watch.py` asserts this file's imports.

===========================================================================
🚨 EVERY ctypes FUNCTION DECLARES argtypes AND EVERY RETURN IS CHECKED
===========================================================================

The rule `hato/watch.py` carries, and it was earned on a measurement that
returned `0.0 MB` for every case because a struct pointer was mis-marshalled
and the return value was never read -- total failure rendered as the hoped-for
answer. ⛔ An unchecked `Shell_NotifyIconW` is the same shape: it returns
FALSE and the icon simply is not there, with nothing raised and nothing
logged.

===========================================================================
⚠ WHY NOT A MESSAGE-ONLY WINDOW
===========================================================================

`HWND_MESSAGE` is the obvious parent for a window that only exists to receive
a callback, and it is wrong here: a message-only window cannot become the
foreground window, and `TrackPopupMenu` on a window that is not foreground
leaves the menu on screen until the next click elsewhere. So this creates an
ordinary window and never shows it.

⚠ AND THE `PostMessage(WM_NULL)` AFTER `TrackPopupMenu` IS NOT SUPERSTITION.
Without it the menu's first dismissal is swallowed and the menu can reappear
or stick -- it is in Microsoft's own guidance for tray menus.
"""
from __future__ import print_function

import ctypes
import sys
from ctypes import wintypes

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_NULL = 0x0000
WM_APP = 0x8000
#: Our own callback message. Anything from WM_APP up is ours to define.
WM_TRAY = WM_APP + 1

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800

CW_USEDEFAULT = -0x80000000
WS_OVERLAPPED = 0x00000000

#: The first menu command id. ⛔ Not 0 -- `TrackPopupMenu` with TPM_RETURNCMD
#: returns 0 to mean *the menu was dismissed*, so an item numbered 0 is
#: indistinguishable from the person pressing Escape.
FIRST_COMMAND = 1


def menu_commands(items):
    u"""[(label, callback) | None] -> [(command_id, label, callback)].

    ⭐ PURE, AND THAT IS DELIBERATE. The id arithmetic is the one part of a
    tray menu that can be wrong in a way nobody sees -- an off-by-one routes
    *Quit* to *Run now* -- and it is the one part that needs no Windows to
    check. Everything below this line needs a real shell; this does not.

    ⛔ A separator consumes NO id. Giving it one is how the ids drift out of
    step with the items after it.
    """
    out = []
    command = FIRST_COMMAND
    for item in items:
        if item is None:
            continue
        label, callback = item
        out.append((command, label, callback))
        command += 1
    return out


def dispatch(items, command):
    u"""-> the callback for `command`, or None. ⛔ Never raises on a stray id.

    A `WM_COMMAND` can arrive for an id this menu never created -- an
    accelerator, a stale message posted before a rebuild. Treating that as a
    lookup failure rather than an error is the difference between a no-op and
    a tray process that dies while the person is holding a menu open.
    """
    for number, _label, callback in menu_commands(items):
        if number == command:
            return callback
    return None


class NOTIFYICONDATAW(ctypes.Structure):
    u"""The Vista-and-later layout. ⚠ `cbSize` IS THE VERSION NEGOTIATION --
    shell32 reads it to decide which fields exist, so a wrong value is not a
    detail: it either refuses outright or reads past the fields you filled."""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


#: 🚨 `ctypes.WINFUNCTYPE` EXISTS ONLY ON WINDOWS, AND THIS LINE RUNS AT
#: IMPORT. Measured on CI 2026-09-18, the first run that reached a Linux or
#: macOS box: `AttributeError: module 'ctypes' has no attribute
#: 'WINFUNCTYPE'` -- raised while COLLECTING `tests/test_watch.py`, so the
#: whole suite errored before a single check ran.
#:
#: ⛔ AND THE MODULE IS SUPPOSED TO SURVIVE THIS. `Tray` refuses off Windows
#: with a written instruction, and there is a check named for exactly that --
#: which could never run, because importing the module to reach it was what
#: failed. A graceful refusal you cannot import is not a graceful refusal.
#:
#: ⚠ The stand-in is never CALLED anywhere: it exists so `WNDCLASSEXW` below
#: can still declare `lpfnWndProc`, and nothing off Windows gets that far.
if hasattr(ctypes, "WINFUNCTYPE"):
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND,
                                 wintypes.UINT, wintypes.WPARAM,
                                 wintypes.LPARAM)
else:                                         # pragma: no cover -- not Windows
    WNDPROC = ctypes.CFUNCTYPE(ctypes.c_longlong)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


def _dlls():
    u"""-> (user32, shell32, kernel32), every function's argtypes declared."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                  wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                   ctypes.c_void_p, wintypes.LPCWSTR]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      wintypes.HWND, wintypes.LPVOID]
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_longlong
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL

    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                          ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    return user32, shell32, kernel32


class TrayError(Exception):
    u"""The tray could not be put up. The message says which call failed."""


class Tray(object):
    u"""One icon in the notification area, and the menu behind it.

    ⚠ `on_activate` fires on a LEFT click or a double click -- opening the
    window is what a person expects from both, and Windows sends the single
    click to a tray icon that has no default action anyway.
    """

    def __init__(self, tooltip, icon_path=None, items=(), on_activate=None):
        if not sys.platform.startswith("win"):
            raise TrayError(
                "hato's tray icon is Shell_NotifyIcon and is Windows-only. On "
                "another platform run hato from cron or a systemd timer -- a "
                "scheduled run finds whatever is new.")
        self.tooltip = tooltip[:127]          # ⚠ szTip is 128 WCHARs INCLUDING the nul
        self.icon_path = icon_path
        self.items = list(items)
        self.on_activate = on_activate
        self._hwnd = None
        self._data = None
        self._proc = None                     # ⛔ held; see _make_window
        self._running = False

    # -- putting it up ----------------------------------------------------

    def _load_icon(self, user32):
        u"""-> an HICON. Falls back to the system icon rather than failing.

        ⛔ `doctrine/architecture`: instruction, not refusal. A tray with the
        generic icon still works; no tray at all means the watcher is running
        and invisible, which is worse than plain.
        """
        if self.icon_path:
            handle = user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON,
                                       0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                return handle
        return user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))

    def _make_window(self, user32, kernel32):
        instance = kernel32.GetModuleHandleW(None)

        def procedure(hwnd, message, wparam, lparam):
            try:
                return self._on_message(hwnd, message, wparam, lparam)
            except Exception:                 # noqa: BLE001
                # ⛔ NEVER let an exception cross back into Windows. A raise
                # inside a WNDPROC unwinds through foreign frames; the process
                # dies with no traceback anybody sees.
                return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        # 🚨 HELD ON THE INSTANCE. A WNDPROC is a C callback into Python; if
        # the only reference is local, Python frees it the moment this returns
        # and Windows calls into freed memory at the first message.
        self._proc = WNDPROC(procedure)

        klass = WNDCLASSEXW()
        klass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        klass.lpfnWndProc = self._proc
        klass.hInstance = instance
        klass.lpszClassName = u"hato_tray_window"
        if not user32.RegisterClassExW(ctypes.byref(klass)):
            raise TrayError("the tray window class could not be registered: %s"
                            % ctypes.WinError(ctypes.get_last_error()))
        # ⚠ An ORDINARY window, never shown -- see the module note on why
        # HWND_MESSAGE is wrong for a menu.
        hwnd = user32.CreateWindowExW(
            0, klass.lpszClassName, u"hato", WS_OVERLAPPED,
            CW_USEDEFAULT, CW_USEDEFAULT, 0, 0, None, None, instance, None)
        if not hwnd:
            raise TrayError("the tray window could not be created: %s"
                            % ctypes.WinError(ctypes.get_last_error()))
        self._klass = klass                   # ⛔ held, same reason as _proc
        return hwnd

    def show(self):
        u"""Put the icon up. -> self"""
        user32, shell32, kernel32 = _dlls()
        self._user32, self._shell32 = user32, shell32
        self._hwnd = self._make_window(user32, kernel32)

        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._load_icon(user32)
        data.szTip = self.tooltip
        # 🚨 CHECKED. A FALSE here is an icon that is simply not in the tray,
        # with nothing raised and nothing logged -- the watcher would sit
        # running and invisible, which is the one outcome the tray exists to
        # prevent.
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            raise TrayError("the tray icon could not be added: %s"
                            % ctypes.WinError(ctypes.get_last_error()))
        self._data = data
        return self

    # -- messages ---------------------------------------------------------

    def _on_message(self, hwnd, message, wparam, lparam):
        user32 = self._user32
        if message == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                if self.on_activate is not None:
                    self.on_activate()
                return 0
            if event == WM_RBUTTONUP:
                self._popup()
                return 0
            return 0
        if message == WM_COMMAND:
            callback = dispatch(self.items, wparam & 0xFFFF)
            if callback is None:
                # ⭐ A NAMED ITEM WITH NO CALLBACK IS *QUIT*. The menu says
                # what it does; the absence of an action is the action.
                self.stop()
            else:
                callback()
            return 0
        if message in (WM_CLOSE, WM_DESTROY):
            self.stop()
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _popup(self):
        user32 = self._user32
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            # ⭐ IDS COME FROM THE SAME PURE FUNCTION THE DISPATCHER USES, so
            # the menu and the routing cannot drift apart -- and a separator,
            # which consumes no id, cannot shift the items after it.
            numbered = iter(menu_commands(self.items))
            for item in self.items:
                if item is None:
                    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                    continue
                number, label, _callback = next(numbered)
                user32.AppendMenuW(menu, MF_STRING,
                                   ctypes.c_void_p(number), label)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # ⚠ FOREGROUND FIRST. TrackPopupMenu on a background window leaves
            # the menu on screen until the next click somewhere else.
            user32.SetForegroundWindow(self._hwnd)
            chosen = user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                point.x, point.y, 0, self._hwnd, None)
            # ⚠ NOT SUPERSTITION -- see the module note.
            user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
            if chosen:
                self._on_message(self._hwnd, WM_COMMAND, chosen, 0)
        finally:
            user32.DestroyMenu(menu)

    # -- running ----------------------------------------------------------

    def pump(self, on_tick=None, tick_ms=1000):
        u"""The message loop. Blocks until `stop()`.

        ⚠ `on_tick` is how the WATCHER's settle timer gets polled: this loop
        owns the thread, so anything periodic has to be invited in rather than
        run beside it.

        🚨 A TIMER, NOT "CALL IT AFTER EACH MESSAGE". `GetMessageW` BLOCKS
        until a message arrives, and a tray process on an idle machine gets
        none for hours -- so a tick hung off the bottom of the loop would fire
        while the person was clicking and never otherwise. **The settle timer
        would never expire, and hato would never run**: a watcher that works
        only while being watched. `SetTimer` is what makes the loop wake on its
        own.
        """
        user32 = self._user32
        self._running = True
        timer = 0
        if on_tick is not None:
            user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_void_p,
                                        wintypes.UINT, ctypes.c_void_p]
            user32.SetTimer.restype = ctypes.c_void_p
            user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_void_p]
            timer = user32.SetTimer(self._hwnd, ctypes.c_void_p(1),
                                    int(tick_ms), None)
            if not timer:
                raise TrayError("the tray's tick timer could not be set: %s"
                                % ctypes.WinError(ctypes.get_last_error()))
        message = wintypes.MSG()
        try:
            while self._running:
                got = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if got == 0:                  # WM_QUIT
                    break
                if got == -1:                 # ⛔ an error, not a message
                    raise TrayError("the tray message loop failed: %s"
                                    % ctypes.WinError(ctypes.get_last_error()))
                if message.message == WM_TIMER and on_tick is not None:
                    on_tick()
                    continue
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if timer:
                user32.KillTimer(self._hwnd, ctypes.c_void_p(1))

    def run(self, on_tick=None):
        u"""show() then pump(). -> None"""
        self.show()
        try:
            self.pump(on_tick=on_tick)
        finally:
            self.close()

    def stop(self):
        self._running = False
        if self._hwnd is not None:
            self._user32.PostQuitMessage(0)

    def close(self):
        u"""⛔ REMOVE THE ICON. A tray icon whose process has gone stays drawn
        until somebody moves the pointer over it -- a dead icon that does
        nothing is worse than none."""
        if self._data is not None and getattr(self, "_shell32", None):
            self._shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data))
            self._data = None
        if self._hwnd is not None and getattr(self, "_user32", None):
            self._user32.DestroyWindow(self._hwnd)
            self._hwnd = None


__all__ = ["FIRST_COMMAND", "NOTIFYICONDATAW", "Tray", "TrayError",
           "WM_TRAY", "dispatch", "menu_commands"]
