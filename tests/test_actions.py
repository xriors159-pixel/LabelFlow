"""Один проход по меткам и действия меню без запуска Photoshop."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actions
import config
import move_green
from tests.test_xmp_label import (
    XMP_SIGNATURE,
    _app1,
    _attribute_packet,
    _jpeg,
    _packet,
    _write,
    tempfile_directory,
)


def _photo(label: str) -> bytes:
    return _jpeg(_app1(XMP_SIGNATURE + _attribute_packet(label)))


def _rated(label: str | None, rating: int) -> bytes:
    label_attr = f'    xmp:Label="{label}"\n' if label else ""
    body = (
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
        f"{label_attr}"
        f'    xmp:Rating="{rating}">\n'
        "  </rdf:Description>"
    )
    return _jpeg(_app1(XMP_SIGNATURE + _packet(body)))


def setUpModule() -> None:
    global _default_config
    _default_config = patch("config.load", side_effect=config.default_settings)
    _default_config.start()


def tearDownModule() -> None:
    _default_config.stop()


def _album(root: Path) -> Path:
    scanned = root / "Свадьба" / "Полный отчет"
    scanned.mkdir(parents=True)
    return scanned


class ClassifyTest(unittest.TestCase):
    def test_splits_green_and_orange_in_one_pass(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            green = _write(scanned, "001.jpg", _photo("Зеленый"))
            _write(scanned, "002.jpg", _photo("Оранжевый "))
            orange = _write(scanned, "003.jpg", _photo("Оранжевый"))
            _write(scanned, "004.jpg", _photo("Красный"))
            nested = scanned / "внутри"
            nested.mkdir()
            _write(nested, "005.jpg", _photo("Зеленый"))

            calls: list[Path] = []
            real_read = move_green.read_xmp_label

            def counting(path: Path):
                calls.append(path)
                return real_read(path)

            with patch("move_green.read_xmp_label", side_effect=counting):
                found_green, found_orange, errors = move_green.classify_folder(scanned)

            self.assertEqual(errors, [])
            self.assertEqual(found_green, [green])
            self.assertEqual(found_orange, [orange])
            self.assertEqual(len(calls), 4)


class ProcessAllTest(unittest.TestCase):
    def test_decline_does_nothing(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            green = _write(scanned, "001.jpg", _photo("Зеленый"))
            orange = _write(scanned, "002.jpg", _photo("Оранжевый"))
            questions: list[str] = []
            notes: list[str] = []
            with patch("photoshop.launch_photoshop") as launch:
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: questions.append(text) or False,
                    notify=notes.append,
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(questions), 1)
            self.assertIn("Будет выполнено:", questions[0])
            self.assertIn("Зеленых → Подрядчики: 1", questions[0])
            self.assertIn("Оранжевых → Photoshop: 1", questions[0])
            self.assertIn("Выполнить обработку?", questions[0])
            self.assertEqual(notes, [])
            launch.assert_not_called()
            self.assertTrue(green.is_file())
            self.assertTrue(orange.is_file())
            self.assertFalse((scanned.parent / "Подрядчики").exists())

    def test_accept_moves_green_then_opens_orange_once(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            green = _write(scanned, "001.jpg", _photo("Зеленый"))
            orange = _write(scanned, "фото (1).jpg", _photo("Оранжевый"))
            destination = scanned.parent / "Подрядчики"
            executable = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe")
            notes: list[str] = []

            def launch(exe: Path, files: list[Path]) -> None:
                self.assertEqual(exe, executable)
                self.assertEqual(files, [orange])
                self.assertFalse(green.exists())
                self.assertTrue((destination / "001.jpg").is_file())
                self.assertTrue(orange.is_file())

            with (
                patch("photoshop.find_photoshop", return_value=executable),
                patch("photoshop.launch_photoshop", side_effect=launch) as mocked,
            ):
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: True,
                    notify=notes.append,
                )
            self.assertEqual(code, 0)
            self.assertEqual(mocked.call_count, 1)
            self.assertIn("Обработка завершена.", notes[0])
            self.assertIn("Зеленых → Подрядчики: 1", notes[0])
            self.assertIn("Оранжевых → Photoshop: 1", notes[0])
            self.assertFalse((scanned / "Подрядчики").exists())

    def test_move_decline_leaves_files(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            source = _write(scanned, "001.jpg", _photo("Зеленый"))
            code = actions.move_labeled(
                scanned,
                confirm=lambda text: False,
                notify=lambda text: None,
            )
            self.assertEqual(code, 0)
            self.assertTrue(source.is_file())
            self.assertFalse((scanned.parent / "Подрядчики").exists())

    def test_move_reports_count(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "001.jpg", _photo("Зеленый"))
            notes: list[str] = []
            code = actions.move_labeled(
                scanned,
                confirm=lambda text: True,
                notify=notes.append,
            )
            self.assertEqual(code, 0)
            self.assertEqual(notes, ["Перемещено: 1"])
            self.assertTrue((scanned.parent / "Подрядчики" / "001.jpg").is_file())

    def test_empty_labels_are_not_errors(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "001.jpg", _photo("Красный"))
            move_notes: list[str] = []
            all_notes: list[str] = []
            self.assertEqual(
                actions.move_labeled(scanned, confirm=lambda text: True, notify=move_notes.append),
                0,
            )
            self.assertEqual(
                actions.process_all(scanned, confirm=lambda text: True, notify=all_notes.append),
                0,
            )
            self.assertEqual(move_notes, [actions.NOT_FOUND_GREEN])
            self.assertEqual(all_notes, [actions.NOT_FOUND_BOTH])

    def test_configured_folder_replaces_default_destination(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "001.jpg", _photo("Зеленый"))
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(True, "move", "Брак"))
            actions.move_labeled(
                scanned,
                confirm=lambda text: True,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertTrue((scanned.parent / "Брак" / "001.jpg").is_file())
            self.assertFalse((scanned.parent / "Подрядчики").exists())

    def test_configured_program_is_launched(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            orange = _write(scanned, "002.jpg", _photo("Оранжевый"))
            program = root / "Viewer.exe"
            program.write_bytes(b"MZ")
            settings = config.default_settings()
            settings.set_rule("orange", config.LabelRule(True, "open", str(program)))
            with (
                patch("photoshop.find_photoshop") as find,
                patch("photoshop.launch_photoshop") as launch,
            ):
                actions.open_photoshop(
                    scanned,
                    confirm=lambda text: True,
                    notify=lambda text: None,
                    settings=settings,
                )
            find.assert_not_called()
            launch.assert_called_once_with(program, [orange])


class ProcessPlanTest(unittest.TestCase):
    def _settings(self) -> config.Settings:
        settings = config.default_settings()
        settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
        settings.set_rule("yellow", config.LabelRule(False, "none", ""))
        return settings

    def test_several_colors_share_one_confirmation(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            green = _write(scanned, "g.jpg", _photo("Зеленый"))
            orange = _write(scanned, "o.jpg", _photo("Оранжевый"))
            red = _write(scanned, "r.jpg", _photo("Красный"))
            executable = root / "Photoshop.exe"
            executable.write_bytes(b"MZ")
            settings = self._settings()
            settings.set_rule("orange", config.LabelRule(True, "open", str(executable)))
            questions: list[str] = []

            def launch(exe: Path, files: list[Path]) -> None:
                self.assertEqual(exe, executable)
                self.assertEqual(files, [orange])
                self.assertFalse(green.exists())
                self.assertFalse(red.exists())

            with patch("photoshop.launch_photoshop", side_effect=launch) as mocked:
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: questions.append(text) or True,
                    notify=lambda text: None,
                    settings=settings,
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(questions), 1)
            self.assertIn("Зеленых → Подрядчики: 1", questions[0])
            self.assertIn("Оранжевых → Photoshop: 1", questions[0])
            self.assertIn("Красных → Брак: 1", questions[0])
            self.assertEqual(mocked.call_count, 1)
            self.assertTrue((scanned.parent / "Подрядчики" / "g.jpg").is_file())
            self.assertTrue((scanned.parent / "Брак" / "r.jpg").is_file())
            self.assertTrue(orange.is_file())

    def test_move_for_several_colors(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "g.jpg", _photo("Зеленый"))
            _write(scanned, "r.jpg", _photo("Красный"))
            settings = config.default_settings()
            settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
            settings.set_rule("orange", config.LabelRule(False, "none", ""))
            with patch("photoshop.launch_photoshop") as launch:
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: True,
                    notify=lambda text: None,
                    settings=settings,
                )
            self.assertEqual(code, 0)
            launch.assert_not_called()
            self.assertTrue((scanned.parent / "Подрядчики" / "g.jpg").is_file())
            self.assertTrue((scanned.parent / "Брак" / "r.jpg").is_file())

    def test_open_for_several_programs(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            orange = _write(scanned, "o.jpg", _photo("Оранжевый"))
            blue = _write(scanned, "b.jpg", _photo("Синий"))
            viewer = root / "Viewer.exe"
            other = root / "Other.exe"
            viewer.write_bytes(b"MZ")
            other.write_bytes(b"MZ")
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(False, "none", ""))
            settings.set_rule("orange", config.LabelRule(True, "open", str(viewer)))
            settings.set_rule("blue", config.LabelRule(True, "open", str(other)))
            questions: list[str] = []
            with patch("photoshop.find_photoshop") as find, patch("photoshop.launch_photoshop") as launch:
                actions.process_all(
                    scanned,
                    confirm=lambda text: questions.append(text) or True,
                    notify=lambda text: None,
                    settings=settings,
                )
            find.assert_not_called()
            self.assertEqual(launch.call_count, 2)
            self.assertEqual(launch.call_args_list[0].args, (viewer, [orange]))
            self.assertEqual(launch.call_args_list[1].args, (other, [blue]))
            self.assertIn("Оранжевых → Viewer: 1", questions[0])
            self.assertIn("Синих → Other: 1", questions[0])

    def test_same_program_is_launched_once(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            orange = _write(scanned, "a.jpg", _photo("Оранжевый"))
            yellow = _write(scanned, "b.jpg", _photo("Желтый"))
            viewer = root / "Viewer.exe"
            viewer.write_bytes(b"MZ")
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(False, "none", ""))
            settings.set_rule("orange", config.LabelRule(True, "open", str(viewer)))
            settings.set_rule("yellow", config.LabelRule(True, "open", str(viewer)))
            with patch("photoshop.launch_photoshop") as launch:
                actions.process_all(
                    scanned,
                    confirm=lambda text: True,
                    notify=lambda text: None,
                    settings=settings,
                )
            launch.assert_called_once_with(viewer, [orange, yellow])

    def test_decline_runs_nothing(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            green = _write(scanned, "g.jpg", _photo("Зеленый"))
            red = _write(scanned, "r.jpg", _photo("Красный"))
            settings = self._settings()
            questions: list[str] = []
            with patch("photoshop.launch_photoshop") as launch:
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: questions.append(text) or False,
                    notify=lambda text: None,
                    settings=settings,
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(questions), 1)
            launch.assert_not_called()
            self.assertTrue(green.is_file())
            self.assertTrue(red.is_file())
            self.assertFalse((scanned.parent / "Подрядчики").exists())
            self.assertFalse((scanned.parent / "Брак").exists())

    def test_none_action_is_skipped(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            yellow = _write(scanned, "y.jpg", _photo("Желтый"))
            _write(scanned, "g.jpg", _photo("Зеленый"))
            questions: list[str] = []
            actions.process_all(
                scanned,
                confirm=lambda text: questions.append(text) or False,
                notify=lambda text: None,
                settings=self._settings(),
            )
            self.assertNotIn("Желтых", questions[0])
            self.assertTrue(yellow.is_file())

    def test_unknown_and_missing_labels_are_ignored(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            unknown = _write(scanned, "u.jpg", _photo("Бирюзовый"))
            bare = _write(scanned, "bare.jpg", _jpeg())
            _write(scanned, "g.jpg", _photo("Зеленый"))
            questions: list[str] = []
            actions.process_all(
                scanned,
                confirm=lambda text: questions.append(text) or False,
                notify=lambda text: None,
            )
            self.assertNotIn("Бирюзовый", questions[0])
            self.assertTrue(unknown.is_file())
            self.assertTrue(bare.is_file())
            self.assertFalse((scanned.parent / "Подрядчики").exists())

    def test_missing_program_file_does_not_launch_per_file(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            orange = _write(scanned, "o.jpg", _photo("Оранжевый"))
            _write(scanned, "g.jpg", _photo("Зеленый"))
            settings = config.default_settings()
            settings.set_rule("orange", config.LabelRule(True, "open", str(root / "missing.exe")))
            notes: list[str] = []
            with patch("photoshop.launch_photoshop") as launch, patch("photoshop.find_photoshop") as find:
                code = actions.process_all(
                    scanned,
                    confirm=lambda text: True,
                    notify=notes.append,
                    settings=settings,
                )
            self.assertEqual(code, 1)
            launch.assert_not_called()
            find.assert_not_called()
            self.assertTrue(orange.is_file())
            self.assertTrue((scanned.parent / "Подрядчики" / "g.jpg").is_file())
            self.assertIn("Программа не найдена.", notes[0])

    def test_existing_destination_file_is_not_overwritten(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            destination = scanned.parent / "Подрядчики"
            destination.mkdir()
            existing = destination / "001.jpg"
            existing.write_bytes(b"keep-me")
            _write(scanned, "001.jpg", _photo("Зеленый"))
            _write(scanned, "002.jpg", _photo("Зеленый"))
            settings = config.default_settings()
            settings.set_rule("orange", config.LabelRule(False, "none", ""))
            notes: list[str] = []
            code = actions.process_all(
                scanned,
                confirm=lambda text: "Зеленых → Подрядчики: 2" in text,
                notify=notes.append,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertEqual(existing.read_bytes(), b"keep-me")
            self.assertTrue((scanned / "001.jpg").is_file())
            self.assertTrue((destination / "002.jpg").is_file())
            self.assertFalse((scanned / "002.jpg").exists())
            self.assertIn("Пропущено: 1", notes[0])
            self.assertIn("Зеленых → Подрядчики: 1", notes[0])


class ApplyLabelTest(unittest.TestCase):
    def test_move_uses_the_saved_color_and_folder(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "r.jpg", _photo("Красный"))
            _write(scanned, "g.jpg", _photo("Зеленый"))
            settings = config.default_settings()
            settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
            code = actions.apply_label(
                scanned,
                "red",
                confirm=lambda text: "Переместить их в папку «Брак»?" in text,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertTrue((scanned.parent / "Брак" / "r.jpg").is_file())
            self.assertTrue((scanned / "g.jpg").is_file())

    def test_open_uses_the_saved_program(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            blue = _write(scanned, "b.jpg", _photo("Синий"))
            viewer = root / "Viewer.exe"
            viewer.write_bytes(b"MZ")
            settings = config.default_settings()
            settings.set_rule("blue", config.LabelRule(True, "open", str(viewer)))
            with patch("photoshop.find_photoshop") as find, patch("photoshop.launch_photoshop") as launch:
                code = actions.apply_label(
                    scanned,
                    "blue",
                    confirm=lambda text: text.endswith("Открыть их в Viewer?"),
                    notify=lambda text: None,
                    settings=settings,
                )
            find.assert_not_called()
            launch.assert_called_once_with(viewer, [blue])
            self.assertEqual(code, 0)

    def test_decline_leaves_files(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            red = _write(scanned, "r.jpg", _photo("Красный"))
            settings = config.default_settings()
            settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
            code = actions.apply_label(
                scanned,
                "red",
                confirm=lambda text: False,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertTrue(red.is_file())
            self.assertFalse((scanned.parent / "Брак").exists())


class StarRatingTest(unittest.TestCase):
    def test_star_is_used_when_color_has_no_action(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "stars.jpg", _rated(None, 2))
            _write(scanned, "green-stars.jpg", _rated("Зеленый", 2))
            settings = config.default_settings()
            settings.set_rule("star2", config.LabelRule(True, "move", "Двойка"))
            questions: list[str] = []
            code = actions.process_all(
                scanned,
                confirm=lambda text: questions.append(text) or True,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertIn("2★ → Двойка: 1", questions[0])
            self.assertIn("Зеленых → Подрядчики: 1", questions[0])
            self.assertTrue((scanned.parent / "Двойка" / "stars.jpg").is_file())
            self.assertTrue((scanned.parent / "Подрядчики" / "green-stars.jpg").is_file())

    def test_windows_and_exif_stars_use_star_filters(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            from tests.test_xmp_label import _exif_app1

            windows = (
                '  <rdf:Description rdf:about=""\n'
                '    xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/"\n'
                '    MicrosoftPhoto:Rating="99"/>'
            )
            _write(scanned, "windows.jpg", _jpeg(_app1(XMP_SIGNATURE + _packet(windows))))
            _write(scanned, "exif.jpg", _jpeg(_exif_app1(rating=1)))
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(False, "none", ""))
            settings.set_rule("orange", config.LabelRule(False, "none", ""))
            settings.set_rule("star5", config.LabelRule(True, "move", "Пять"))
            settings.set_rule("star1", config.LabelRule(True, "move", "Одна"))
            code = actions.process_all(
                scanned,
                confirm=lambda text: True,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertTrue((scanned.parent / "Пять" / "windows.jpg").is_file())
            self.assertTrue((scanned.parent / "Одна" / "exif.jpg").is_file())


class FolderLocationTest(unittest.TestCase):
    def test_three_places_receive_their_files(self) -> None:
        with tempfile_directory() as root:
            scanned = _album(root)
            _write(scanned, "a.jpg", _photo("Зеленый"))
            _write(scanned, "b.jpg", _photo("Красный"))
            _write(scanned, "c.jpg", _photo("Синий"))
            chosen = root / "Выбранная"
            chosen.mkdir()
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(True, "move", "РядомФото", config.FOLDER_BESIDE_PHOTOS))
            settings.set_rule("red", config.LabelRule(True, "move", "РядомПапка", config.FOLDER_BESIDE_SCAN))
            settings.set_rule("blue", config.LabelRule(True, "move", str(chosen), config.FOLDER_BROWSE))
            settings.set_rule("orange", config.LabelRule(False, "none", ""))
            questions: list[str] = []
            code = actions.process_all(
                scanned,
                confirm=lambda text: questions.append(text) or True,
                notify=lambda text: None,
                settings=settings,
            )
            self.assertEqual(code, 0)
            self.assertIn("Зеленых → РядомФото (рядом с фотографиями): 1", questions[0])
            self.assertIn("Красных → РядомПапка: 1", questions[0])
            self.assertTrue((scanned / "РядомФото" / "a.jpg").is_file())
            self.assertTrue((scanned.parent / "РядомПапка" / "b.jpg").is_file())
            self.assertTrue((chosen / "c.jpg").is_file())
            self.assertFalse((scanned / "a.jpg").exists())


if __name__ == "__main__":
    unittest.main()
