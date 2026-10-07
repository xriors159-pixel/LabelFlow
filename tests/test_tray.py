"""Правый клик по значку не вызывает tkinter из оконной процедуры."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tray


def setUpModule() -> None:
    import tkinter as tk

    global _root
    _root = tk.Tk()
    _root.withdraw()


def tearDownModule() -> None:
    _root.quit()
    _root.destroy()


class TrayMenuTest(unittest.TestCase):
    def test_callback_does_not_open_menu_itself(self) -> None:
        app = tray.TrayApp(_root)
        opened: list[str] = []
        app.show_menu = lambda: opened.append("menu")  # type: ignore[method-assign]

        result = app._on_message(0, tray._CALLBACK, 1, tray._WM_RBUTTONUP)

        self.assertEqual(result, 0)
        self.assertTrue(app._menu_requested)
        self.assertEqual(opened, [])

    def test_context_menu_message_requests_menu(self) -> None:
        app = tray.TrayApp(_root)
        app._on_message(0, tray._CALLBACK, 1, tray._WM_CONTEXTMENU)
        self.assertTrue(app._menu_requested)

    def test_double_click_requests_settings_not_menu(self) -> None:
        app = tray.TrayApp(_root)
        result = app._on_message(0, tray._CALLBACK, 1, tray._WM_LBUTTONDBLCLK)
        self.assertEqual(result, 0)
        self.assertTrue(app._settings_requested)
        self.assertFalse(app._menu_requested)

    def test_posted_double_click_opens_settings_without_abort(self) -> None:
        app = tray.TrayApp(_root)
        opened: list[str] = []
        app.open_settings = lambda: opened.append("settings")  # type: ignore[method-assign]
        self.assertTrue(app.start())
        try:
            posted = tray.user32.PostMessageW(app._hwnd, tray._CALLBACK, 1, tray._WM_LBUTTONDBLCLK)
            self.assertTrue(posted)
            deadline = time.time() + 2
            while time.time() < deadline and not opened:
                _root.update()
                time.sleep(0.02)
            self.assertEqual(opened, ["settings"])
            self.assertFalse(app._menu_requested)
        finally:
            app.stop()

    def test_other_tray_messages_do_not_request_menu(self) -> None:
        app = tray.TrayApp(_root)
        app._on_message(0, tray._CALLBACK, 1, 0x0204)  # WM_RBUTTONDOWN
        self.assertFalse(app._menu_requested)

    def test_posted_right_click_opens_menu_without_abort(self) -> None:
        """Сообщение проходит через настоящую оконную процедуру, как у Explorer."""
        app = tray.TrayApp(_root)
        opened: list[str] = []
        app.show_menu = lambda: opened.append("menu")  # type: ignore[method-assign]
        self.assertTrue(app.start())
        try:
            posted = tray.user32.PostMessageW(app._hwnd, tray._CALLBACK, 1, tray._WM_RBUTTONUP)
            self.assertTrue(posted)
            deadline = time.time() + 2
            while time.time() < deadline and not opened:
                _root.update()
                time.sleep(0.02)
            self.assertEqual(opened, ["menu"])
        finally:
            app.stop()

    def test_settings_command_opens_settings(self) -> None:
        app = tray.TrayApp(_root)
        opened: list[str] = []
        app.open_settings = lambda: opened.append("settings")  # type: ignore[method-assign]
        with patch.object(tray.user32, "TrackPopupMenu", return_value=tray._CMD_SETTINGS):
            app.show_menu()
        _root.update()
        self.assertEqual(opened, ["settings"])

    def test_exit_command_closes_tray(self) -> None:
        app = tray.TrayApp(_root)
        closed: list[str] = []
        app.exit = lambda: closed.append("exit")  # type: ignore[method-assign]
        with patch.object(tray.user32, "TrackPopupMenu", return_value=tray._CMD_EXIT):
            app.show_menu()
        _root.update()
        self.assertEqual(closed, ["exit"])
