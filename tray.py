"""Значок LabelFlow в системном трее.

Окно настроек — tkinter. Сам значок регистрируется через Shell_NotifyIcon,
без дополнительных пакетов и без консоли.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import tkinter as tk

import config
import settings_window

_WM_RBUTTONUP = 0x0205
_WM_CONTEXTMENU = 0x007B
_WM_NULL = 0x0000
_WM_APP = 0x8000
_CALLBACK = _WM_APP + 1
_NIF_MESSAGE = 0x00000001
_NIF_ICON = 0x00000002
_NIF_TIP = 0x00000004
_NIM_ADD = 0x00000000
_NIM_DELETE = 0x00000002
_MF_STRING = 0x00000000
_MF_GRAYED = 0x00000001
_MF_SEPARATOR = 0x00000800
_TPM_RIGHTBUTTON = 0x0002
_TPM_RETURNCMD = 0x0100
_GWL_WNDPROC = -4
_CMD_SETTINGS = 2
_CMD_EXIT = 3

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    ctypes.c_ssize_t,
    ctypes.c_ssize_t,
]
user32.CallWindowProcW.restype = ctypes.c_ssize_t


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
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
        ("guidItem", _GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    ctypes.c_ssize_t,
    ctypes.c_ssize_t,
)


def menu_labels() -> tuple[str, ...]:
    return ("LabelFlow", "Настройки", "Выход")


class TrayApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._icon = None
        self._color = None
        self._mask = None
        self._old_proc = None
        self._proc = None
        self._hwnd = 0
        self._added = False
        self._menu_requested = False
        self._showing_menu = False
        self._settings: settings_window.SettingsEditor | None = None

    def start(self) -> bool:
        self.root.update_idletasks()
        self._hwnd = self.root.winfo_id()
        self._icon, self._color, self._mask = _label_icon()
        self._proc = _WNDPROC(self._on_message)
        set_long = user32.SetWindowLongPtrW
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        set_long.restype = ctypes.c_void_p
        self._old_proc = set_long(self._hwnd, _GWL_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p))
        data = self._icon_data()
        if not shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(data)):
            return False
        self._added = True
        self.root.after(0, self._poll_menu)
        return True

    def stop(self) -> None:
        if self._added and self._hwnd:
            data = self._icon_data()
            shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(data))
            self._added = False
        if self._old_proc and self._hwnd:
            user32.SetWindowLongPtrW(self._hwnd, _GWL_WNDPROC, self._old_proc)
            self._old_proc = None
        if self._icon:
            user32.DestroyIcon(self._icon)
            self._icon = None
        if self._color:
            gdi32.DeleteObject(self._color)
            self._color = None
        if self._mask:
            gdi32.DeleteObject(self._mask)
            self._mask = None

    def _poll_menu(self) -> None:
        """Открывает меню из цикла Tk, а не из оконной процедуры.

        Shell вызывает процедуру значка своим SendMessage. Вызов root.after
        прямо оттуда отпускает GIL, и оконный EXE завершается с 0xC0000409
        (PyEval_RestoreThread). Флаг выставляется в процедуре, меню — здесь.
        """
        if not self._added:
            return
        if self._menu_requested and not self._showing_menu:
            self._menu_requested = False
            self._showing_menu = True
            try:
                self.show_menu()
            finally:
                self._showing_menu = False
                self._menu_requested = False
        if self._added:
            self.root.after(50, self._poll_menu)

    def show_menu(self) -> None:
        labels = menu_labels()
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, _MF_STRING | _MF_GRAYED, 1, labels[0])
        user32.AppendMenuW(menu, _MF_STRING, _CMD_SETTINGS, labels[1])
        user32.AppendMenuW(menu, _MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, _MF_STRING, _CMD_EXIT, labels[2])
        point = _POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self._hwnd)
        command = user32.TrackPopupMenu(
            menu,
            _TPM_RETURNCMD | _TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            self._hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        user32.PostMessageW(self._hwnd, _WM_NULL, 0, 0)
        if command == _CMD_SETTINGS:
            self.root.after(0, self.open_settings)
        elif command == _CMD_EXIT:
            self.root.after(0, self.exit)

    def open_settings(self) -> None:
        if self._settings is not None and self._settings.alive():
            self._settings.show()
            return
        self._settings = settings_window.SettingsEditor(master=self.root)
        self._settings.show()

    def exit(self) -> None:
        self.stop()
        self.root.quit()
        self.root.destroy()

    def _icon_data(self) -> _NOTIFYICONDATAW:
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        data.uCallbackMessage = _CALLBACK
        data.hIcon = self._icon
        data.szTip = "LabelFlow"
        return data

    def _on_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == _CALLBACK and (int(lparam) & 0xFFFF) in {_WM_RBUTTONUP, _WM_CONTEXTMENU}:
                self._menu_requested = True
                return 0
            if self._old_proc:
                return user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        except Exception:
            return 0


def run() -> int:
    settings_window._dpi()
    config.ensure()
    import context_menu

    context_menu.install()
    root = tk.Tk()
    root.withdraw()
    app = TrayApp(root)
    if not app.start():
        import win_message

        win_message.show_error("Не удалось показать значок LabelFlow в трее.")
        root.destroy()
        return 1
    try:
        root.mainloop()
    finally:
        app.stop()
    return 0


def _label_icon() -> tuple[int, int, int]:
    """Зелёный и оранжевый квадраты — те же цвета, что у меток в настройках."""
    size = 32
    screen = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(screen)
    color = gdi32.CreateCompatibleBitmap(screen, size, size)
    previous = gdi32.SelectObject(memory, color)
    _fill(memory, 0, 0, size, size, 0x00222222)
    _fill(memory, 5, 8, 10, 16, _colorref(config.LABELS[4].swatch))
    _fill(memory, 17, 8, 10, 16, _colorref(config.LABELS[2].swatch))
    gdi32.SelectObject(memory, previous)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, screen)
    mask = gdi32.CreateBitmap(size, size, 1, 1, None)
    mask_dc = gdi32.CreateCompatibleDC(0)
    old_mask = gdi32.SelectObject(mask_dc, mask)
    gdi32.PatBlt(mask_dc, 0, 0, size, size, 0x00000042)  # BLACKNESS: непрозрачная иконка
    gdi32.SelectObject(mask_dc, old_mask)
    gdi32.DeleteDC(mask_dc)
    info = _ICONINFO(True, 0, 0, mask, color)
    icon = user32.CreateIconIndirect(ctypes.byref(info))
    return icon, color, mask


def _fill(hdc, left: int, top: int, width: int, height: int, colorref: int) -> None:
    brush = gdi32.CreateSolidBrush(colorref)
    rect = wintypes.RECT(left, top, left + width, top + height)
    user32.FillRect(hdc, ctypes.byref(rect), brush)
    gdi32.DeleteObject(brush)


def _colorref(hex_color: str) -> int:
    text = hex_color.removeprefix("#")
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    return red | (green << 8) | (blue << 16)
