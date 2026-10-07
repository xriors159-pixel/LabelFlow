"""Стандартные окна Windows. Консольный ввод для этих сообщений не используется."""

from __future__ import annotations

import ctypes

_MB_OK = 0x00000000
_MB_YESNO = 0x00000004
_MB_ICONERROR = 0x00000010
_MB_ICONQUESTION = 0x00000020
_MB_ICONINFORMATION = 0x00000040
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000
_IDYES = 6

TITLE = "LabelFlow"


def ask_yes_no(text: str, title: str = TITLE) -> bool:
    """Окно с кнопками Да/Нет. На русской Windows это стандартные кнопки Yes/No."""
    flags = _MB_YESNO | _MB_ICONQUESTION | _MB_SETFOREGROUND | _MB_TOPMOST
    answer = ctypes.windll.user32.MessageBoxW(0, text, title, flags)
    return answer == _IDYES


def show_info(text: str, title: str = TITLE) -> None:
    flags = _MB_OK | _MB_ICONINFORMATION | _MB_SETFOREGROUND | _MB_TOPMOST
    ctypes.windll.user32.MessageBoxW(0, text, title, flags)


def show_error(text: str, title: str = TITLE) -> None:
    flags = _MB_OK | _MB_ICONERROR | _MB_SETFOREGROUND | _MB_TOPMOST
    ctypes.windll.user32.MessageBoxW(0, text, title, flags)
