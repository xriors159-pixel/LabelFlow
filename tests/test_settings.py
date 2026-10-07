"""Окно настроек собирает действия и не записывает файл по «Отмена»."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import settings_window


def setUpModule() -> None:
    import tkinter as tk

    global _root
    _root = tk.Tk()
    _root.withdraw()


def tearDownModule() -> None:
    _root.quit()
    _root.destroy()


class SettingsWindowTest(unittest.TestCase):
    def test_form_reads_defaults_and_saves_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            program = Path(temporary) / "Viewer.exe"
            program.write_bytes(b"MZ")
            editor = settings_window.SettingsEditor(master=_root, settings=config.default_settings())
            try:
                self.assertEqual(editor.rows["green"].chosen_action(), "move")
                self.assertEqual(editor.rows["green"].parameter_value(), "Подрядчики")
                self.assertEqual(editor.rows["orange"].chosen_action(), "open")
                self.assertEqual(editor.rows["orange"].parameter_value(), "Photoshop")
                self.assertNotIn("none", editor.rows)
                self.assertEqual(editor.rows["red"].chosen_action(), "none")
                self.assertEqual(editor.rows["red"].parameter_value(), "")
                self.assertEqual(editor.rows["star1"].chosen_action(), "none")
                self.assertEqual(editor.rows["star5"]._caption(), "<Действие>")
                editor.rows["red"].set_action("move")
                editor.rows["red"].set_parameter("Брак")
                editor.rows["blue"].set_action("open")
                editor.rows["blue"].set_parameter(str(program))
                editor.rows["star2"].set_action("move")
                editor.rows["star2"].set_location(config.FOLDER_BESIDE_PHOTOS)
                editor.rows["star2"].set_parameter("Двойка")
                self.assertIsNone(editor.validate())
                with (
                    patch("config.config_path", return_value=path),
                    patch("context_menu.install", return_value=0) as refresh,
                ):
                    self.assertTrue(editor.save())
                refresh.assert_called_once_with()
            finally:
                if editor.alive():
                    editor.window.destroy()
            loaded = config.load(path)
            self.assertEqual(loaded.rule("red").action, "move")
            self.assertEqual(loaded.rule("red").parameter, "Брак")
            self.assertTrue(loaded.rule("red").enabled)
            self.assertEqual(loaded.rule("blue").action, "open")
            self.assertTrue(loaded.rule("blue").parameter.endswith("Viewer.exe"))
            self.assertEqual(config.program_display_name(loaded.rule("blue").parameter), "Viewer")
            self.assertEqual(loaded.rule("green").parameter, "Подрядчики")
            self.assertEqual(loaded.rule("none").action, "none")
            self.assertEqual(loaded.rule("star2").action, "move")
            self.assertEqual(loaded.rule("star2").parameter, "Двойка")
            self.assertEqual(loaded.rule("star2").folder_location, "beside_photos")
            self.assertEqual(loaded.rule("red").folder_location, "beside_scan")
            self.assertEqual(loaded.rule("star5").action, "none")

    def test_invalid_folder_is_rejected(self) -> None:
        editor = settings_window.SettingsEditor(master=_root, settings=config.default_settings())
        try:
            editor.rows["green"].set_parameter(r"a\b")
            error = editor.validate()
            self.assertIsNotNone(error)
            self.assertIn("Зеленый", error or "")
        finally:
            editor.window.destroy()

    def test_cancel_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            config.save(config.default_settings(), path)
            editor = settings_window.SettingsEditor(master=_root, settings=config.load(path))
            try:
                editor.rows["green"].set_parameter("Другое")
                editor.cancel()
            finally:
                if editor.alive():
                    editor.window.destroy()
            self.assertEqual(config.load(path).rule("green").parameter, "Подрядчики")


if __name__ == "__main__":
    unittest.main()
