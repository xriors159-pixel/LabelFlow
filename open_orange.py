"""Открывает JPG с точной меткой xmp:Label = «Оранжевый» в Adobe Photoshop.

Список файлов берётся из move_green.scan_folder. Отдельный разбор XMP не нужен.
Подтверждение — стандартное окно Windows с кнопками Да/Нет.
"""

from __future__ import annotations

from pathlib import Path

import move_green

ORANGE_LABEL = move_green.ORANGE_LABEL
NOT_FOUND_MESSAGE = "Оранжевые фотографии не найдены."
PHOTOSHOP_MISSING_MESSAGE = "Adobe Photoshop не найден."
PHOTOSHOP_FAILED_MESSAGE = "Не удалось запустить Adobe Photoshop."
TOO_MANY_FILES_MESSAGE = "Слишком много файлов для одного запуска Adobe Photoshop."


def orange_files(folder: Path) -> list[Path]:
    """JPG непосредственно в папке, у которых xmp:Label равен «Оранжевый»."""
    return move_green.scan_folder(folder, ORANGE_LABEL).matches


def run(folder: Path, *, confirm=None, find=None, launch=None, notify=None) -> int:
    import actions

    return actions.open_photoshop(
        folder,
        confirm=confirm,
        find=find,
        launch=launch,
        notify=notify,
    )
