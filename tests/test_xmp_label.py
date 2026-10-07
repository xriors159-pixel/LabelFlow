"""Проверяет, что xmp:Label читается из JPEG так, как его пишут фотопрограммы."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import move_green

XMP_SIGNATURE = b"http://ns.adobe.com/xap/1.0/\x00"
SCRIPT = Path(__file__).resolve().parent.parent / "move_green.py"


def _app1(payload: bytes) -> bytes:
    return b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload


def _jpeg(*segments: bytes, after_sos: bytes = b"") -> bytes:
    # SOS с пустым заголовком: дальше сканер метаданных идти не должен.
    return b"\xff\xd8" + b"".join(segments) + b"\xff\xda\x00\x02" + after_sos + b"\xff\xd9"


def _packet(body: str, pad: int = 0) -> bytes:
    xml = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="LabelFlow test">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f"{body}\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )
    return xml.encode("utf-8") + (b" " * pad)


def _attribute_packet(label: str, extra: str = "", pad: int = 0) -> bytes:
    body = (
        "  <rdf:Description rdf:about=\"\"\n"
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
        '    xmlns:photomechanic="http://ns.camerabits.com/photomechanic/1.0/"\n'
        '    xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
        f'    xmp:Label="{label}"\n'
        '    photomechanic:ColorClass="3">\n'
        f"{extra}"
        "  </rdf:Description>"
    )
    return _packet(body, pad=pad)


def _write(folder: Path, name: str, data: bytes) -> Path:
    path = folder / name
    path.write_bytes(data)
    return path


class XmpLabelDetectionTest(unittest.TestCase):
    def test_attribute_form_reads_green_and_orange(self) -> None:
        with self._temp_dir() as folder:
            green = _write(
                folder,
                "green.jpg",
                _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый", pad=2048))),
            )
            orange = _write(
                folder,
                "orange.jpg",
                _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Оранжевый"))),
            )

            self.assertEqual(move_green.read_xmp_label(green), "Зеленый")
            self.assertEqual(move_green.read_xmp_label(orange), "Оранжевый")

            scan = move_green.scan_folder(folder)
            self.assertEqual([path.name for path in scan.matches], ["green.jpg"])

    def test_element_form_and_alternate_prefix(self) -> None:
        element = _packet(
            "  <rdf:Description rdf:about=\"\"\n"
            '    xmlns:xmp="http://ns.adobe.com/xap/1.0/">\n'
            "   <xmp:Label>Зеленый</xmp:Label>\n"
            "  </rdf:Description>"
        )
        prefixed = (
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            ' <rdf:Description rdf:about=""\n'
            '   xmlns:xap="http://ns.adobe.com/xap/1.0/"\n'
            '   xap:Label="Зеленый"/>\n'
            "</rdf:RDF>"
        ).encode("utf-8")

        with self._temp_dir() as folder:
            element_path = _write(folder, "element.jpg", _jpeg(_app1(XMP_SIGNATURE + element)))
            prefix_path = _write(folder, "prefix.JPEG", _jpeg(_app1(XMP_SIGNATURE + prefixed)))
            self.assertEqual(move_green.read_xmp_label(element_path), "Зеленый")
            self.assertEqual(move_green.read_xmp_label(prefix_path), "Зеленый")

    def test_exact_string_only(self) -> None:
        samples = {
            "lower.jpg": "зеленый",
            "yo.jpg": "Зелёный",
            "space.jpg": "Зеленый ",
            "other-ns.jpg": None,
        }
        with self._temp_dir() as folder:
            for name, label in samples.items():
                if label is None:
                    packet = _packet(
                        "  <rdf:Description rdf:about=\"\"\n"
                        '    xmlns:other="http://example.com/ns/"\n'
                        '    other:Label="Зеленый"/>'
                    )
                else:
                    packet = _attribute_packet(
                        label,
                        extra="   <dc:description>Зеленый</dc:description>\n",
                    )
                path = _write(folder, name, _jpeg(_app1(XMP_SIGNATURE + packet)))
                self.assertNotEqual(move_green.read_xmp_label(path), move_green.TARGET_LABEL)
            scan = move_green.scan_folder(folder)
            self.assertEqual(scan.matches, [])

    def test_ignores_image_data_and_skips_exif_app1(self) -> None:
        decoy = XMP_SIGNATURE + _attribute_packet("Зеленый")
        orange = _app1(XMP_SIGNATURE + _attribute_packet("Оранжевый"))
        exif = _app1(b"Exif\x00\x00" + b"\x00" * 16)
        data = _jpeg(exif, orange, after_sos=decoy)

        with self._temp_dir() as folder:
            path = _write(folder, "camera.jpg", data)
            self.assertEqual(move_green.read_xmp_label(path), "Оранжевый")

            unlabeled = _write(folder, "bare.jpg", _jpeg(exif, after_sos=decoy))
            self.assertIsNone(move_green.read_xmp_label(unlabeled))

    def test_scan_is_not_recursive_and_keeps_cyrillic_names(self) -> None:
        with self._temp_dir() as folder:
            nested = folder / "Другая"
            nested.mkdir()
            _write(nested, "внутри.jpg", _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый"))))
            _write(folder, "заметка.txt", "Зеленый".encode("utf-8"))
            kept = _write(
                folder,
                "Свадьба.jpg",
                _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый"))),
            )
            _write(folder, "обычное.JPG", _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Красный"))))

            scan = move_green.scan_folder(folder)
            self.assertEqual([path.name for path in scan.jpegs], ["обычное.JPG", "Свадьба.jpg"])
            self.assertEqual(scan.matches, [kept])

    def test_destination_is_sibling_of_scanned_folder(self) -> None:
        scanned = Path(r"E:\фотографии\Свадьба\Полный отчет")
        self.assertEqual(
            move_green.destination_for(scanned),
            Path(r"E:\фотографии\Свадьба\Подрядчики"),
        )

    def test_moves_green_files_next_to_scanned_folder(self) -> None:
        with self._temp_dir() as root:
            scanned = root / "Свадьба" / "Полный отчет"
            scanned.mkdir(parents=True)
            green = _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый")))
            orange = _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Оранжевый")))
            _write(scanned, "001.jpg", green)
            _write(scanned, "002.jpg", orange)
            _write(scanned, "003.jpg", green)

            completed = self._run_cli(scanned, "y\n")
            destination = root / "Свадьба" / "Подрядчики"

            self.assertEqual(completed.returncode, 0)
            self.assertIn("Папка назначения:", completed.stdout)
            self.assertIn(str(destination), completed.stdout)
            self.assertTrue((destination / "001.jpg").is_file())
            self.assertTrue((destination / "003.jpg").is_file())
            self.assertTrue((scanned / "002.jpg").is_file())
            self.assertFalse((scanned / "001.jpg").exists())
            self.assertFalse((scanned / "003.jpg").exists())
            self.assertFalse((scanned / "Подрядчики").exists())
            self.assertEqual(move_green.read_xmp_label(destination / "001.jpg"), "Зеленый")

    def test_move_does_not_overwrite_or_change_bytes(self) -> None:
        with self._temp_dir() as root:
            scanned = root / "Свадьба" / "Полный отчет"
            scanned.mkdir(parents=True)
            payload = _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый")))
            source = _write(scanned, "Свадьба.jpg", payload)
            existing_dir = root / "Свадьба" / move_green.DEST_DIR_NAME
            existing_dir.mkdir()
            existing = _write(existing_dir, "Свадьба.jpg", b"already-there")

            moved, skipped, messages = move_green.move_matches(scanned, [source])
            self.assertEqual((moved, skipped), (0, 1))
            self.assertTrue(source.exists())
            self.assertEqual(existing.read_bytes(), b"already-there")
            self.assertIn("ПРОПУСК", messages[0])
            self.assertFalse((scanned / move_green.DEST_DIR_NAME).exists())

            existing.unlink()
            before = source.read_bytes()
            moved, skipped, messages = move_green.move_matches(scanned, [source])
            dest = existing_dir / "Свадьба.jpg"
            self.assertEqual((moved, skipped), (1, 0))
            self.assertFalse(source.exists())
            self.assertEqual(dest.read_bytes(), before)
            self.assertEqual(move_green.read_xmp_label(dest), "Зеленый")

    def test_move_error_leaves_source_in_place(self) -> None:
        with self._temp_dir() as root:
            scanned = root / "album" / "report"
            scanned.mkdir(parents=True)
            source = _write(
                scanned,
                "green.jpg",
                _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый"))),
            )
            (root / "album" / move_green.DEST_DIR_NAME).write_bytes(b"not-a-directory")
            original = source.read_bytes()

            moved, skipped, messages = move_green.move_matches(scanned, [source])
            self.assertEqual((moved, skipped), (0, 0))
            self.assertTrue(messages[0].startswith("ОШИБКА:"))
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((scanned / move_green.DEST_DIR_NAME).exists())

    def test_cli_waits_for_confirmation(self) -> None:
        with self._temp_dir() as root:
            scanned = root / "Встреча Санфарма" / "удалил"
            scanned.mkdir(parents=True)
            payload = _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Зеленый")))
            source = _write(scanned, "IMG_0002.jpg", payload)
            _write(scanned, "IMG_0001.jpg", _jpeg(_app1(XMP_SIGNATURE + _attribute_packet("Оранжевый"))))
            destination = root / "Встреча Санфарма" / "Подрядчики"

            cancelled = self._run_cli(scanned, "n\n")
            self.assertEqual(cancelled.returncode, 0)
            self.assertIn("Найдено JPG: 2", cancelled.stdout)
            self.assertIn("С меткой «Зеленый»: 1", cancelled.stdout)
            self.assertIn("IMG_0002.jpg", cancelled.stdout)
            self.assertIn("Операция отменена.", cancelled.stdout)
            self.assertIn("Успешно перемещено: 0", cancelled.stdout)
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
            self.assertFalse((scanned / move_green.DEST_DIR_NAME).exists())

            confirmed = self._run_cli(scanned, "yes\n")
            self.assertEqual(confirmed.returncode, 0)
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())

            moved = self._run_cli(scanned, "y\n")
            self.assertEqual(moved.returncode, 0)
            self.assertIn("ПЕРЕМЕЩЁН: IMG_0002.jpg", moved.stdout)
            self.assertIn("Успешно перемещено: 1", moved.stdout)
            self.assertIn("Пропущено: 0", moved.stdout)
            self.assertIn("Ошибок: 0", moved.stdout)
            self.assertFalse(source.exists())
            self.assertTrue((destination / "IMG_0002.jpg").is_file())
            self.assertTrue((scanned / "IMG_0001.jpg").is_file())
            self.assertFalse((scanned / "Подрядчики").exists())

    def _run_cli(self, folder: Path, stdin: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(folder)],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )

    def _temp_dir(self):
        return tempfile_directory()


class tempfile_directory:
    def __enter__(self) -> Path:
        import tempfile

        self._dir = tempfile.TemporaryDirectory()
        return Path(self._dir.name)

    def __exit__(self, exc_type, exc, tb) -> None:
        self._dir.cleanup()


if __name__ == "__main__":
    unittest.main()
