"""Конфигурация меток: файл в профиле, значения по умолчанию и порча JSON."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


class ConfigTest(unittest.TestCase):
    def test_missing_file_uses_defaults_and_does_not_create_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            settings = config.load(path)
            self.assertFalse(path.exists())
            self._assert_defaults(settings)

    def test_ensure_creates_default_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "config.json"
            created = config.ensure(path)
            self.assertTrue(path.is_file())
            self._assert_defaults(created)
            self._assert_defaults(config.load(path))

    def test_roundtrip_preserves_changed_action_and_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            settings = config.default_settings()
            settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
            settings.set_rule(
                "orange",
                config.LabelRule(True, "open", r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe"),
            )
            config.save(settings, path)
            loaded = config.load(path)
            red = loaded.rule("red")
            orange = loaded.rule("orange")
            self.assertTrue(red.enabled)
            self.assertEqual(red.action, "move")
            self.assertEqual(red.parameter, "Брак")
            self.assertEqual(orange.action, "open")
            self.assertTrue(orange.parameter.endswith("Photoshop.exe"))
            self.assertEqual(loaded.rule("green").action, "move")
            self.assertEqual(loaded.rule("green").parameter, "Подрядчики")
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["labels"]["red"]["action_parameter"], "Брак")
            self.assertEqual(raw["labels"]["red"]["folder_location"], "beside_scan")
            self.assertNotIn("parameter", raw["labels"]["red"])

    def test_ensure_does_not_reset_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            config.ensure(path)
            settings = config.load(path)
            settings.set_rule("blue", config.LabelRule(True, "move", "Синие"))
            config.save(settings, path)
            kept = config.ensure(path)
            self.assertEqual(kept.rule("blue").action, "move")
            self.assertEqual(kept.rule("blue").parameter, "Синие")

    def test_corrupt_json_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text("{", encoding="utf-8")
            self._assert_defaults(config.load(path))
            self.assertEqual(path.read_text(encoding="utf-8"), "{")
            path.write_text(json.dumps(["не объект"]), encoding="utf-8")
            self._assert_defaults(config.load(path))

    def test_unknown_action_becomes_none_for_that_label_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            config.save(config.default_settings(), path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["labels"]["yellow"] = {"enabled": True, "action": "delete", "action_parameter": "x"}
            path.write_text(json.dumps(raw), encoding="utf-8")
            loaded = config.load(path)
            self.assertEqual(loaded.rule("yellow").action, "none")
            self.assertFalse(loaded.rule("yellow").enabled)
            self.assertEqual(loaded.rule("green").action, "move")

    def test_folder_and_program_validation(self) -> None:
        self.assertIsNone(config.folder_name_error("Подрядчики"))
        self.assertIsNotNone(config.folder_name_error(""))
        self.assertIsNotNone(config.folder_name_error(r"папка\внутри"))
        self.assertIsNone(config.program_error("Photoshop"))
        self.assertIsNotNone(config.program_error(""))
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / "Viewer.exe"
            program.write_bytes(b"MZ")
            self.assertIsNone(config.program_error(str(program)))
            self.assertEqual(config.program_display_name(str(program)), "Viewer")
        self.assertEqual(config.program_display_name("Photoshop"), "Photoshop")

    def _assert_defaults(self, settings: config.Settings) -> None:
        green = settings.rule("green")
        orange = settings.rule("orange")
        self.assertTrue(green.enabled)
        self.assertEqual(green.action, "move")
        self.assertEqual(green.parameter, "Подрядчики")
        self.assertEqual(config.move_folder(settings, "green"), "Подрядчики")
        self.assertTrue(orange.enabled)
        self.assertEqual(orange.action, "open")
        self.assertEqual(orange.parameter, "Photoshop")
        self.assertEqual(config.open_program(settings, "orange"), "Photoshop")
        for key in ("none", "red", "yellow", "blue", "pink", "purple", "star1", "star2", "star3", "star4", "star5"):
            rule = settings.rule(key)
            self.assertEqual(rule.action, "none")
            self.assertFalse(rule.enabled)
            self.assertIsNone(config.move_folder(settings, key))
            self.assertIsNone(config.open_program(settings, key))


if __name__ == "__main__":
    unittest.main()
