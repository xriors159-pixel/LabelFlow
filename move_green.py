"""Перемещает JPG с цветовой меткой XMP xmp:Label = «Зеленый».

Папка назначения лежит на уровень выше сканируемой:

    destination = scanned_folder.parent / "Подрядчики"

Например, «E:\\фотографии\\Свадьба\\Полный отчет» отдаёт файлы в
«E:\\фотографии\\Свадьба\\Подрядчики».

В JPEG пакет XMP лежит в сегменте APP1 с сигнатурой
``http://ns.adobe.com/xap/1.0/``. Свойство Label относится к пространству
имён ``http://ns.adobe.com/xap/1.0/``. Lightroom, Photo Mechanic и Bridge
пишут его атрибутом описания RDF — именно так программы показывают строку
вида «xmp / Label = Оранжевый»:

    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/"
                     xmp:Label="Зеленый"/>

Допустима и элементная форма ``<xmp:Label>Зеленый</xmp:Label>``.
Префикс (xmp, xap и любой другой) не важен: сравниваются URI пространства
имён и точное значение строки.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

TARGET_LABEL = "Зеленый"
ORANGE_LABEL = "Оранжевый"
DEST_DIR_NAME = "Подрядчики"
JPEG_SUFFIXES = {".jpg", ".jpeg"}

XMP_NAMESPACE = "http://ns.adobe.com/xap/1.0/"
XMP_LABEL = f"{{{XMP_NAMESPACE}}}Label"
XMP_RATING = f"{{{XMP_NAMESPACE}}}Rating"
MS_PHOTO_NAMESPACE = "http://ns.microsoft.com/photo/1.0/"
MS_PHOTO_RATING = f"{{{MS_PHOTO_NAMESPACE}}}Rating"
XMP_APP1_SIGNATURE = b"http://ns.adobe.com/xap/1.0/\x00"
EXIF_APP1_SIGNATURE = b"Exif\x00\x00"
_EXIF_RATING = 0x4746
_EXIF_RATING_PERCENT = 0x4749
# Проценты, которыми Проводник Windows записывает звёзды.
_PERCENT_STARS = {1: 1, 25: 2, 50: 3, 75: 4, 99: 5, 100: 5}

# Маркеры JPEG без поля длины.
_STANDALONE_MARKERS = frozenset([0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)])
_SOS_MARKER = 0xDA


@dataclass
class ScanResult:
    jpegs: list[Path] = field(default_factory=list)
    matches: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def _iter_xmp_packets(path: Path):
    """Отдаёт стандартные XMP-пакеты из APP1, не читая сжатые данные снимка."""
    for kind, payload in _iter_metadata(path):
        if kind == "xmp":
            yield payload


def _iter_metadata(path: Path):
    """XMP и EXIF из APP1. Сканирование останавливается на SOS."""
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            return
        while True:
            marker = _read_marker(handle)
            if marker is None or marker == 0x00:
                return
            if marker in _STANDALONE_MARKERS:
                if marker == 0xD9:
                    return
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                return
            segment_length = int.from_bytes(length_bytes, "big")
            if segment_length < 2:
                return
            payload = handle.read(segment_length - 2)
            if len(payload) != segment_length - 2:
                return
            if marker == 0xE1 and payload.startswith(XMP_APP1_SIGNATURE):
                yield "xmp", payload[len(XMP_APP1_SIGNATURE) :]
            elif marker == 0xE1 and payload.startswith(EXIF_APP1_SIGNATURE):
                yield "exif", payload[len(EXIF_APP1_SIGNATURE) :]
            if marker == _SOS_MARKER:
                return


def _read_marker(handle) -> int | None:
    byte = handle.read(1)
    if byte != b"\xff":
        return None
    while byte == b"\xff":
        byte = handle.read(1)
        if not byte:
            return None
    return byte[0]


def _parse_xmp_root(packet: bytes) -> ET.Element | None:
    cleaned = packet.strip(b"\x00")
    for candidate in (cleaned, _xml_slice(cleaned)):
        if not candidate:
            continue
        try:
            return ET.fromstring(candidate)
        except ET.ParseError:
            continue
    return None


def _xml_slice(packet: bytes) -> bytes | None:
    start = packet.find(b"<")
    end = packet.rfind(b">")
    if start < 0 or end <= start:
        return None
    return packet[start : end + 1]


def _label_from_xmp_packet(packet: bytes) -> str | None:
    root = _parse_xmp_root(packet)
    if root is None:
        return None
    for element in root.iter():
        if XMP_LABEL in element.attrib:
            return element.attrib[XMP_LABEL]
        if element.tag == XMP_LABEL:
            return element.text or ""
    return None


def _rating_text(element: ET.Element) -> str:
    text = (element.text or "").strip()
    if text:
        return text
    for child in element.iter():
        if child is element:
            continue
        nested = (child.text or "").strip()
        if nested:
            return nested
    return ""


def _stars_from_count(raw: str | None) -> int | None:
    """1–5, либо столько же символов ★ или *."""
    if raw is None:
        return None
    text = raw.strip()
    if text in {"1", "2", "3", "4", "5"}:
        return int(text)
    if text and set(text) <= {"★"} and 1 <= len(text) <= 5:
        return len(text)
    if text and set(text) <= {"*"} and 1 <= len(text) <= 5:
        return len(text)
    return None


def _stars_from_percent(raw: str | None) -> int | None:
    counted = _stars_from_count(raw)
    if counted is not None:
        return counted
    if raw is None:
        return None
    text = raw.strip()
    if not text.isdigit():
        return None
    return _PERCENT_STARS.get(int(text))


def _rating_value(raw: str | None) -> int | None:
    return _stars_from_count(raw)


def _fields_from_xmp_packet(packet: bytes) -> tuple[str | None, int | None, int | None]:
    """Метка, xmp:Rating и MicrosoftPhoto:Rating. Разбор Label не меняется."""
    root = _parse_xmp_root(packet)
    if root is None:
        return None, None, None
    label = None
    xmp_rating = None
    ms_rating = None
    for element in root.iter():
        if label is None:
            if XMP_LABEL in element.attrib:
                label = element.attrib[XMP_LABEL]
            elif element.tag == XMP_LABEL:
                label = element.text or ""
        if xmp_rating is None:
            if XMP_RATING in element.attrib:
                xmp_rating = _stars_from_count(element.attrib[XMP_RATING])
            elif element.tag == XMP_RATING:
                xmp_rating = _stars_from_count(_rating_text(element))
        if ms_rating is None:
            if MS_PHOTO_RATING in element.attrib:
                ms_rating = _stars_from_percent(element.attrib[MS_PHOTO_RATING])
            elif element.tag == MS_PHOTO_RATING:
                ms_rating = _stars_from_percent(_rating_text(element))
        if label is not None and xmp_rating is not None and ms_rating is not None:
            break
    return label, xmp_rating, ms_rating


def _ratings_from_exif(payload: bytes) -> tuple[int | None, int | None]:
    """EXIF Rating (1–5) и RatingPercent из IFD0. Битый сегмент даёт пустой результат."""
    if len(payload) < 8:
        return None, None
    if payload[:2] == b"II":
        order = "little"
    elif payload[:2] == b"MM":
        order = "big"
    else:
        return None, None
    if int.from_bytes(payload[2:4], order) != 42:
        return None, None
    offset = int.from_bytes(payload[4:8], order)
    if offset < 0 or offset + 2 > len(payload):
        return None, None
    count = int.from_bytes(payload[offset : offset + 2], order)
    rating = None
    percent = None
    entry = offset + 2
    for _ in range(min(count, 256)):
        if entry + 12 > len(payload):
            break
        tag = int.from_bytes(payload[entry : entry + 2], order)
        kind = int.from_bytes(payload[entry + 2 : entry + 4], order)
        number = int.from_bytes(payload[entry + 4 : entry + 8], order)
        raw = payload[entry + 8 : entry + 12]
        if number == 1 and kind in {3, 4}:
            width = 2 if kind == 3 else 4
            value = int.from_bytes(raw[:width], order)
            if tag == _EXIF_RATING and value in {1, 2, 3, 4, 5}:
                rating = value
            elif tag == _EXIF_RATING_PERCENT:
                percent = _PERCENT_STARS.get(value)
        entry += 12
    return rating, percent


def read_xmp_label(path: Path) -> str | None:
    """Возвращает первое значение xmp:Label или None, если свойства нет."""
    for packet in _iter_xmp_packets(path):
        label = _label_from_xmp_packet(packet)
        if label is not None:
            return label
    return None


def read_xmp_fields(path: Path) -> tuple[str | None, int | None]:
    """Метка и звёзды: xmp:Rating, символы ★/*, MicrosoftPhoto:Rating, EXIF.

    Если в файле несколько записей, берётся первая найденная в этом порядке.
    Числовой xmp:Rating важнее процентов Windows и тегов EXIF.
    Когда в файле звёзд нет, берётся рейтинг из каталога XnView MP.
    """
    label = None
    xmp_rating = None
    ms_rating = None
    exif_rating = None
    exif_percent = None
    for kind, payload in _iter_metadata(path):
        if kind == "xmp":
            found_label, found_xmp, found_ms = _fields_from_xmp_packet(payload)
            if label is None and found_label is not None:
                label = found_label
            if xmp_rating is None and found_xmp is not None:
                xmp_rating = found_xmp
            if ms_rating is None and found_ms is not None:
                ms_rating = found_ms
        else:
            found_rating, found_percent = _ratings_from_exif(payload)
            if exif_rating is None and found_rating is not None:
                exif_rating = found_rating
            if exif_percent is None and found_percent is not None:
                exif_percent = found_percent
        if label is not None and xmp_rating is not None:
            break
    if xmp_rating is not None:
        rating = xmp_rating
    elif ms_rating is not None:
        rating = ms_rating
    elif exif_rating is not None:
        rating = exif_rating
    else:
        rating = exif_percent
    if rating is None:
        rating = xnview_catalog_rating(path)
    return label, rating


def _xnview_db_path() -> Path | None:
    """Каталог XnView MP. Звёзды из него не всегда записаны в JPEG."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    path = Path(appdata) / "XnViewMP" / "XnView.db"
    if path.is_file():
        return path
    return None


def _folder_path_variants(folder: Path) -> list[str]:
    """Варианты пути, как их хранит XnView: прямые слэши и слэш в конце."""
    seen: list[str] = []
    candidates = [folder]
    try:
        candidates.append(folder.resolve())
    except OSError:
        pass
    for item in candidates:
        text = str(item).replace("/", "\\")
        forward = text.replace("\\", "/")
        slash = forward if forward.endswith("/") else forward + "/"
        for value in (slash, forward, text):
            if value not in seen:
                seen.append(value)
    return seen


_xnview_cache: dict[tuple[str, int, str], dict[str, int]] = {}


def xnview_catalog_rating(path: Path) -> int | None:
    """Рейтинг 1–5 из каталога XnView для этого файла, если программа его записала."""
    table = _xnview_folder_ratings(path.parent)
    if not table:
        return None
    return table.get(path.name.casefold())


def _xnview_folder_ratings(folder: Path) -> dict[str, int]:
    db = _xnview_db_path()
    if db is None:
        return {}
    try:
        stamp = db.stat().st_mtime_ns
    except OSError:
        return {}
    key = (os.path.normcase(str(db)), stamp, os.path.normcase(os.path.abspath(folder)))
    cached = _xnview_cache.get(key)
    if cached is not None:
        return cached
    loaded = _query_xnview_ratings(db, folder)
    _xnview_cache[key] = loaded
    return loaded


def _query_xnview_ratings(db: Path, folder: Path) -> dict[str, int]:
    uri = "file:" + db.resolve().as_posix() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return {}
    try:
        folder_id = None
        for name in _folder_path_variants(folder):
            row = connection.execute(
                "SELECT FolderID FROM Folders WHERE Pathname = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if row is not None:
                folder_id = row[0]
                break
        if folder_id is None:
            return {}
        found: dict[str, int] = {}
        for filename, rating in connection.execute(
            "SELECT Filename, Rating FROM Images WHERE FolderID = ?",
            (folder_id,),
        ):
            if isinstance(rating, int) and rating in {1, 2, 3, 4, 5} and isinstance(filename, str):
                found[filename.casefold()] = rating
        return found
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def _jpeg_files(folder: Path) -> tuple[list[Path], list[str]]:
    errors: list[str] = []
    try:
        entries = list(folder.iterdir())
    except OSError as exc:
        return [], [f"{folder}: {exc}"]

    jpegs: list[Path] = []
    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError as exc:
            errors.append(f"{entry.name}: {exc}")
            continue
        if entry.suffix.lower() not in JPEG_SUFFIXES:
            continue
        jpegs.append(entry)

    jpegs.sort(key=lambda item: item.name.casefold())
    return jpegs, errors


def _label_of(path: Path, errors: list[str]) -> str | None:
    try:
        return read_xmp_label(path)
    except OSError as exc:
        errors.append(f"{path.name}: {exc}")
        return None


def scan_folder(folder: Path, expected_label: str = TARGET_LABEL) -> ScanResult:
    result = ScanResult()
    jpegs, errors = _jpeg_files(folder)
    result.jpegs = jpegs
    result.errors = errors
    for path in jpegs:
        if _label_of(path, result.errors) == expected_label:
            result.matches.append(path)
    return result


def classify_folder(folder: Path) -> tuple[list[Path], list[Path], list[str]]:
    """Один проход по JPG: зелёные и оранжевые собираются вместе."""
    jpegs, errors = _jpeg_files(folder)
    green: list[Path] = []
    orange: list[Path] = []
    for path in jpegs:
        label = _label_of(path, errors)
        if label == TARGET_LABEL:
            green.append(path)
        elif label == ORANGE_LABEL:
            orange.append(path)
    return green, orange, errors


def labels_in_folder(folder: Path) -> tuple[list[tuple[Path, str | None, int | None]], list[str]]:
    """Один проход: точный xmp:Label и xmp:Rating каждого JPG."""
    jpegs, errors = _jpeg_files(folder)
    labeled: list[tuple[Path, str | None, int | None]] = []
    for path in jpegs:
        try:
            label, rating = read_xmp_fields(path)
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
            label, rating = None, None
        labeled.append((path, label, rating))
    return labeled, errors


def destination_for(folder: Path, dest_name: str = DEST_DIR_NAME, location: str = "beside_scan") -> Path:
    """Папка назначения: выбранный путь, рядом с фото или рядом со сканируемой."""
    if location == "browse":
        return Path(dest_name)
    if location == "beside_photos":
        return folder / dest_name
    return folder.parent / dest_name


def _same_dir(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def confirm_move(count: int) -> bool:
    prompt = (
        f"Переместить эти {count} фотографий в папку '{DEST_DIR_NAME}'? [y/N] "
    )
    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() == "y"


def move_matches(
    folder: Path,
    matches: list[Path],
    dest_name: str = DEST_DIR_NAME,
    location: str = "beside_scan",
) -> tuple[int, int, list[str]]:
    """Перемещает файлы через rename. Существующий файл назначения не затирается.

    При ошибке исходный файл остаётся на месте: rename на том же диске
    либо переносит файл целиком, либо не меняет его.
    """
    dest_dir = destination_for(folder, dest_name, location)
    shown = Path(dest_name).name if location == "browse" else dest_name
    moved = 0
    skipped = 0
    messages: list[str] = []
    pending: list[Path] = []

    if _same_dir(folder, dest_dir):
        for src in matches:
            messages.append(
                f"ОШИБКА: {src.name} — папка назначения совпадает с выбранной. "
                "Файл оставлен на месте"
            )
        return moved, skipped, messages

    for src in matches:
        dest = dest_dir / src.name
        if dest.exists():
            skipped += 1
            messages.append(
                f"ПРОПУСК: {src.name} — файл уже есть в папке «{shown}», "
                "не перезаписан"
            )
            continue
        pending.append(src)

    if not pending:
        return moved, skipped, messages

    try:
        dest_dir.mkdir(exist_ok=True)
    except OSError as exc:
        for src in pending:
            messages.append(
                f"ОШИБКА: {src.name} — не удалось создать папку "
                f"«{shown}»: {exc}. Файл оставлен на месте"
            )
        return moved, skipped, messages

    for src in pending:
        dest = dest_dir / src.name
        try:
            # os.replace здесь нельзя: он перезаписывает существующий файл.
            src.rename(dest)
        except FileExistsError:
            skipped += 1
            messages.append(
                f"ПРОПУСК: {src.name} — файл уже есть в папке «{shown}», "
                "не перезаписан"
            )
        except OSError as exc:
            messages.append(
                f"ОШИБКА: {src.name} — {exc}. Файл оставлен на месте"
            )
        else:
            moved += 1
            messages.append(f"ПЕРЕМЕЩЁН: {src.name} -> {dest}")
    return moved, skipped, messages


def _print_summary(moved: int, skipped: int, errors: int) -> None:
    print()
    print(f"Успешно перемещено: {moved}")
    print(f"Пропущено: {skipped}")
    print(f"Ошибок: {errors}")


def run(folder: Path) -> int:
    print(f"Папка: {folder}")

    if not folder.is_dir():
        print(f"ОШИБКА: папка не найдена: {folder}", file=sys.stderr)
        return 1

    destination = destination_for(folder)
    if _same_dir(folder, destination):
        print(f"Папка «{DEST_DIR_NAME}» — это папка назначения, она не сканируется.")
        _print_summary(0, 0, 0)
        return 0

    print(f"Папка назначения: {destination}")

    scan = scan_folder(folder)
    print(f"Найдено JPG: {len(scan.jpegs)}")
    print(f"С меткой «{TARGET_LABEL}»: {len(scan.matches)}")

    for message in scan.errors:
        print(f"ОШИБКА: {message}")

    if not scan.matches:
        print()
        print("Нет фотографий для перемещения.")
        _print_summary(0, 0, len(scan.errors))
        return 1 if scan.errors else 0

    print()
    print("Будут перемещены:")
    for path in scan.matches:
        print(f"  {path.name}")
    print()

    if not confirm_move(len(scan.matches)):
        print("Операция отменена.")
        _print_summary(0, 0, len(scan.errors))
        return 1 if scan.errors else 0

    print()
    moved, skipped, messages = move_matches(folder, scan.matches)
    for message in messages:
        print(message)
    move_errors = sum(message.startswith("ОШИБКА:") for message in messages)
    error_count = len(scan.errors) + move_errors
    _print_summary(moved, skipped, error_count)
    return 1 if error_count else 0


def _pause_if_console() -> None:
    """Окно, открытое из Проводника, иначе закрывается до чтения итога."""
    if not getattr(sys, "frozen", False) or sys.stdin is None:
        return
    if not sys.stdin.isatty():
        return
    try:
        input("Нажмите Enter, чтобы закрыть...")
    except (EOFError, KeyboardInterrupt):
        print()


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--install-context-menu"]:
        import context_menu

        return context_menu.install()
    if argv == ["--uninstall-context-menu"]:
        import context_menu

        return context_menu.uninstall()
    if argv == ["--tray"] or (not argv and getattr(sys, "frozen", False)):
        import tray

        return tray.run()
    if argv == ["--settings"]:
        import settings_window

        return settings_window.run()
    if len(argv) == 3 and argv[0] == "--label":
        import actions

        folder = Path(os.path.abspath(Path(argv[2]).expanduser()))
        try:
            return actions.apply_label(folder, argv[1])
        except Exception:
            import win_message

            win_message.show_error("Не удалось выполнить операцию.")
            return 1
    if len(argv) == 2 and argv[0] in {"--process-all", "--move", "--open-orange"}:
        import actions

        folder = Path(os.path.abspath(Path(argv[1]).expanduser()))
        try:
            if argv[0] == "--process-all":
                return actions.process_all(folder)
            if argv[0] == "--move":
                return actions.move_labeled(folder)
            return actions.open_photoshop(folder)
        except Exception:
            import win_message

            win_message.show_error("Не удалось выполнить операцию.")
            return 1
    if len(argv) != 1 or argv[0].startswith("-"):
        message = 'Использование: python move_green.py "E:\\Wedding"'
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif getattr(sys, "frozen", False):
            import win_message

            win_message.show_info(message)
        return 1
    folder = Path(os.path.abspath(Path(argv[0]).expanduser()))
    if getattr(sys, "frozen", False):
        import actions

        return actions.move_labeled(folder)
    code = run(folder)
    _pause_if_console()
    return code


if __name__ == "__main__":
    sys.exit(main())
