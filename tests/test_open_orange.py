"""Оранжевая метка, список файлов для Photoshop и отказ от реального запуска."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import open_orange
import photoshop
from tests.test_xmp_label import (
    XMP_SIGNATURE,
    _app1,
    _attribute_packet,
    _jpeg,
    _write,
    tempfile_directory,
)


def setUpModule() -> None:
    global _default_config
    _default_config = patch("config.load", side_effect=config.default_settings)
    _default_config.start()


def tearDownModule() -> None:
    _default_config.stop()


def _orange_jpeg(label: str) -> bytes:
    return _jpeg(_app1(XMP_SIGNATURE + _attribute_packet(label)))


class OrangeLabelTest(unittest.TestCase):
    def test_exact_orange_label_is_detected(self) -> None:
        with tempfile_directory() as folder:
            path = _write(folder, "orange.jpg", _orange_jpeg("Оранжевый"))
            self.assertEqual(open_orange.ORANGE_LABEL, "Оранжевый")
            self.assertIn(path, open_orange.orange_files(folder))

    def test_other_labels_are_not_orange(self) -> None:
        labels = ["оранжевый", "Оранжевый ", "Оранжевый что-то", "Зеленый", "Красный"]
        with tempfile_directory() as folder:
            for index, label in enumerate(labels):
                _write(folder, f"file{index}.jpg", _orange_jpeg(label))
            self.assertEqual(open_orange.orange_files(folder), [])

    def test_finds_only_top_level_orange_files(self) -> None:
        with tempfile_directory() as folder:
            nested = folder / "вложенная"
            nested.mkdir()
            first = _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            _write(folder, "002.jpg", _orange_jpeg("Зеленый"))
            third = _write(folder, "фото (1).jpg", _orange_jpeg("Оранжевый"))
            _write(nested, "003.jpg", _orange_jpeg("Оранжевый"))
            _write(folder, "заметка.txt", "Оранжевый".encode("utf-8"))

            self.assertEqual(open_orange.orange_files(folder), [first, third])

    def test_empty_result_message(self) -> None:
        with tempfile_directory() as folder:
            _write(folder, "green.jpg", _orange_jpeg("Зеленый"))
            notes: list[str] = []
            questions: list[str] = []
            code = open_orange.run(
                folder,
                confirm=questions.append,
                notify=notes.append,
            )
            self.assertEqual(code, 0)
            self.assertEqual(questions, [])
            self.assertIn(open_orange.NOT_FOUND_MESSAGE, notes)

    def test_photoshop_argument_list_quotes_special_paths(self) -> None:
        executable = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe")
        files = [
            Path(r"E:\Photo\Встреча Санфарма\фото (1).jpg"),
            Path(r"E:\Photo\A & B\файл.jpg"),
        ]
        line = photoshop.command_line(executable, files)
        self.assertIn("Photoshop.exe", line)
        self.assertIn("Встреча Санфарма", line)
        self.assertIn("фото (1).jpg", line)
        self.assertIn("A & B", line)
        self.assertTrue(photoshop.fits_in_command_line(executable, files))

    def test_yes_launches_photoshop_once(self) -> None:
        with tempfile_directory() as folder:
            first = _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            _write(folder, "002.jpg", _orange_jpeg("Зеленый"))
            third = _write(folder, "003.jpg", _orange_jpeg("Оранжевый"))
            executable = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe")
            questions: list[str] = []
            with (
                patch("photoshop.find_photoshop", return_value=executable),
                patch("photoshop.launch_photoshop") as launch,
            ):
                code = open_orange.run(
                    folder,
                    confirm=lambda text: questions.append(text) or True,
                    notify=lambda text: None,
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(questions), 1)
            self.assertIn("Найдено оранжевых фотографий: 2", questions[0])
            self.assertIn("Открыть их в Photoshop?", questions[0])
            launch.assert_called_once_with(executable, [first, third])

    def test_no_does_not_launch_or_move(self) -> None:
        with tempfile_directory() as folder:
            source = _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            executable = Path(r"C:\PS\Photoshop.exe")
            with (
                patch("photoshop.find_photoshop", return_value=executable),
                patch("photoshop.launch_photoshop") as launch,
            ):
                code = open_orange.run(
                    folder,
                    confirm=lambda text: False,
                    notify=lambda text: None,
                )
            self.assertEqual(code, 0)
            launch.assert_not_called()
            self.assertTrue(source.is_file())
            self.assertFalse((folder.parent / "Подрядчики").exists())

    def test_missing_photoshop_message(self) -> None:
        with tempfile_directory() as folder:
            _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            notes: list[str] = []
            with (
                patch("photoshop.find_photoshop", return_value=None),
                patch("photoshop.launch_photoshop") as launch,
            ):
                code = open_orange.run(
                    folder,
                    confirm=lambda text: True,
                    notify=notes.append,
                )
            self.assertEqual(code, 1)
            launch.assert_not_called()
            self.assertIn(open_orange.PHOTOSHOP_MISSING_MESSAGE, notes)

    def test_launch_error_has_no_traceback(self) -> None:
        with tempfile_directory() as folder:
            _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            executable = Path(r"C:\PS\Photoshop.exe")
            notes: list[str] = []
            with (
                patch("photoshop.find_photoshop", return_value=executable),
                patch("photoshop.launch_photoshop", side_effect=OSError("boom")),
            ):
                code = open_orange.run(
                    folder,
                    confirm=lambda text: True,
                    notify=notes.append,
                )
            self.assertEqual(code, 1)
            self.assertIn(open_orange.PHOTOSHOP_FAILED_MESSAGE, notes)
            self.assertNotIn("Traceback", "\n".join(notes))

    def test_too_many_files_are_not_opened_one_by_one(self) -> None:
        with tempfile_directory() as folder:
            _write(folder, "001.jpg", _orange_jpeg("Оранжевый"))
            executable = Path(r"C:\PS\Photoshop.exe")
            notes: list[str] = []
            with (
                patch("photoshop.find_photoshop", return_value=executable),
                patch("photoshop.fits_in_command_line", return_value=False),
                patch("photoshop.launch_photoshop") as launch,
            ):
                code = open_orange.run(
                    folder,
                    confirm=lambda text: True,
                    notify=notes.append,
                )
            self.assertIn(open_orange.TOO_MANY_FILES_MESSAGE, notes)
            self.assertEqual(code, 1)
            launch.assert_not_called()

        long_name = "а" * 240
        files = [Path(rf"E:\Photo\{long_name}\{index}.jpg") for index in range(200)]
        self.assertFalse(photoshop.fits_in_command_line(executable, files))


class PhotoshopDiscoveryTest(unittest.TestCase):
    def test_prefers_newer_standard_install(self) -> None:
        with tempfile_directory() as root:
            older = root / "Adobe Photoshop 2024" / "Photoshop.exe"
            newer = root / "Adobe Photoshop 2025" / "Photoshop.exe"
            elements = root / "Adobe Photoshop Elements 2024" / "Photoshop.exe"
            for path in (older, newer, elements):
                path.parent.mkdir()
                path.write_bytes(b"fake")
            found = photoshop.find_photoshop(adobe_roots=[root], registry_lookup=lambda: [])
            self.assertEqual(found, newer)

    def test_registry_is_used_when_standard_install_is_missing(self) -> None:
        with tempfile_directory() as root:
            registered = root / "Custom" / "Photoshop.exe"
            registered.parent.mkdir()
            registered.write_bytes(b"fake")
            empty = root / "empty"
            empty.mkdir()
            found = photoshop.find_photoshop(
                adobe_roots=[empty],
                registry_lookup=lambda: [registered],
            )
            self.assertEqual(found, registered)

    def test_normalize_display_icon(self) -> None:
        path = photoshop.normalize_registered_path(
            r'"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",0'
        )
        self.assertEqual(
            path,
            Path(r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"),
        )
        directory = photoshop.normalize_registered_path(
            r"C:\Program Files\Adobe\Adobe Photoshop 2024\\"
        )
        self.assertEqual(
            directory,
            Path(r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe"),
        )


if __name__ == "__main__":
    unittest.main()
