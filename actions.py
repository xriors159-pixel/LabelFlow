"""Действия пунктов меню: перенос зелёных, открытие оранжевых, обработка всего.

Подтверждения и итоги показываются стандартным окном Windows.
Чтение XMP остаётся в move_green.read_xmp_label.
«Запустить все» берёт действие каждой метки из config.json.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import config
import move_green
import open_orange
import photoshop
import win_message

NOT_FOUND_GREEN = "Зеленые фотографии не найдены."
NOT_FOUND_BOTH = "Нет фотографий для обработки."

_MENU_COLORS = {
    "none": "без метки",
    "red": "красные",
    "orange": "оранжевые",
    "yellow": "желтые",
    "green": "зеленые",
    "blue": "синие",
    "pink": "розовые",
    "purple": "пурпурные",
    "star1": "1★",
    "star2": "2★",
    "star3": "3★",
    "star4": "4★",
    "star5": "5★",
}

# Родительный падеж для строки плана: «Зеленых → Подрядчики: 10».
_PLAN_TITLES = {
    "none": "Без метки",
    "red": "Красных",
    "orange": "Оранжевых",
    "yellow": "Желтых",
    "green": "Зеленых",
    "blue": "Синих",
    "pink": "Розовых",
    "purple": "Пурпурных",
    "star1": "1★",
    "star2": "2★",
    "star3": "3★",
    "star4": "4★",
    "star5": "5★",
}


def move_labeled(folder: Path, *, confirm=None, notify=None, settings=None) -> int:
    confirm = win_message.ask_yes_no if confirm is None else confirm
    notify = win_message.show_info if notify is None else notify
    current = config.load() if settings is None else settings
    dest_name = config.move_folder(current, "green")
    location = config.folder_location(current, "green")
    if not _is_folder(folder, notify):
        return 1
    if dest_name is None:
        notify(NOT_FOUND_GREEN)
        return 0
    if _is_destination(folder, notify, dest_name, location):
        return 0

    matches = move_green.scan_folder(folder).matches
    if not matches:
        notify(NOT_FOUND_GREEN)
        return 0

    question = (
        f"Найдено зеленых фотографий: {len(matches)}\n\n"
        f"Переместить их в папку {_move_place(dest_name, location)}?"
    )
    if not confirm(question):
        return 0

    moved, skipped, messages = move_green.move_matches(folder, matches, dest_name, location)
    notify(_move_report(moved, skipped, messages))
    return 1 if any(message.startswith("ОШИБКА:") for message in messages) else 0


def open_photoshop(folder: Path, *, confirm=None, find=None, launch=None, notify=None, settings=None) -> int:
    confirm = win_message.ask_yes_no if confirm is None else confirm
    notify = win_message.show_info if notify is None else notify
    find = photoshop.find_photoshop if find is None else find
    launch = photoshop.launch_photoshop if launch is None else launch
    current = config.load() if settings is None else settings
    program = config.open_program(current, "orange")
    if not _is_folder(folder, notify):
        return 1
    if program is None:
        notify(open_orange.NOT_FOUND_MESSAGE)
        return 0

    files = open_orange.orange_files(folder)
    if not files:
        notify(open_orange.NOT_FOUND_MESSAGE)
        return 0

    question = (
        f"Найдено оранжевых фотографий: {len(files)}\n\n"
        "Открыть их в Photoshop?"
    )
    if not confirm(question):
        return 0

    opened, error = _open_orange(files, find, launch, program)
    if error is not None:
        notify(error)
        return 1
    notify(f"Открыто в Photoshop: {opened}")
    return 0


def apply_label(
    folder: Path,
    key: str,
    *,
    confirm=None,
    find=None,
    launch=None,
    notify=None,
    settings=None,
) -> int:
    """Один пункт меню: действие метки из config.json на момент вызова."""
    confirm = win_message.ask_yes_no if confirm is None else confirm
    notify = win_message.show_info if notify is None else notify
    find = photoshop.find_photoshop if find is None else find
    launch = photoshop.launch_photoshop if launch is None else launch
    current = config.load() if settings is None else settings
    if key not in {item.key for item in config.LABELS}:
        notify("Неизвестная метка.")
        return 1
    if not _is_folder(folder, notify):
        return 1
    rule = current.rule(key)
    parameter = rule.parameter.strip()
    if not rule.enabled or rule.action not in {"move", "open"} or not parameter:
        notify("Для этой метки действие не задано.")
        return 0
    if rule.action == "move" and _is_destination(folder, notify, parameter, rule.folder_location):
        return 0

    files = [
        path
        for path, label, rating in move_green.labels_in_folder(folder)[0]
        if _matches_row(label, rating, key)
    ]
    color = _MENU_COLORS[key]
    if not files:
        notify("Фотографии с этой меткой не найдены.")
        return 0
    if rule.action == "move":
        question = (
            f"Найдено ({color}): {len(files)}\n\n"
            f"Переместить их в папку {_move_place(parameter, rule.folder_location)}?"
        )
        if not confirm(question):
            return 0
        moved, skipped, messages = move_green.move_matches(folder, files, parameter, rule.folder_location)
        notify(_move_report(moved, skipped, messages))
        return 1 if any(message.startswith("ОШИБКА:") for message in messages) else 0

    program = config.program_display_name(parameter)
    question = f"Найдено ({color}): {len(files)}\n\nОткрыть их в {program}?"
    if not confirm(question):
        return 0
    opened, error = _open_orange(files, find, launch, parameter)
    if error is not None:
        notify(error)
        return 1
    notify(f"Открыто в {program}: {opened}")
    return 0


def process_all(folder: Path, *, confirm=None, find=None, launch=None, notify=None, settings=None) -> int:
    confirm = win_message.ask_yes_no if confirm is None else confirm
    notify = win_message.show_info if notify is None else notify
    find = photoshop.find_photoshop if find is None else find
    launch = photoshop.launch_photoshop if launch is None else launch
    current = config.load() if settings is None else settings
    if not _is_folder(folder, notify):
        return 1
    if _is_configured_destination(folder, notify, current):
        return 0

    plan = _action_plan(folder, current)
    if not plan:
        notify(NOT_FOUND_BOTH)
        return 0

    if not confirm(_plan_question(plan)):
        return 0

    moved_counts, skipped, move_messages = _run_moves(folder, plan)
    opened_groups, open_errors = _run_opens(plan, find, launch)
    notify(_plan_report(plan, moved_counts, opened_groups, skipped, move_messages, open_errors))
    failed = bool(open_errors) or any(message.startswith("ОШИБКА:") for message in move_messages)
    return 1 if failed else 0


@dataclass
class _PlanLine:
    key: str
    title: str
    action: str
    parameter: str
    files: list[Path]
    location: str = config.FOLDER_BESIDE_SCAN


def _action_plan(folder: Path, settings: config.Settings) -> list[_PlanLine]:
    labeled, _errors = move_green.labels_in_folder(folder)
    buckets: dict[str, list[Path]] = {}
    for path, label, rating in labeled:
        info = _bucket_for(label, rating, settings)
        if info is None:
            continue
        buckets.setdefault(info.key, []).append(path)
    plan: list[_PlanLine] = []
    for item in config.LABELS:
        files = buckets.get(item.key)
        if not files:
            continue
        rule = settings.rule(item.key)
        plan.append(
            _PlanLine(
                item.key,
                _PLAN_TITLES[item.key],
                rule.action,
                rule.parameter.strip(),
                files,
                rule.folder_location,
            )
        )
    return plan


def _rule_active(settings: config.Settings, key: str) -> bool:
    rule = settings.rule(key)
    return bool(rule.enabled and rule.action in {"move", "open"} and rule.parameter.strip())


def _bucket_for(label: str | None, rating: int | None, settings: config.Settings) -> config.LabelInfo | None:
    """Цвет важнее звёзд: у файла одно действие."""
    color = _info_for_label(label)
    if color is not None and color.rating is None and _rule_active(settings, color.key):
        return color
    star = _info_for_rating(rating)
    if star is not None and _rule_active(settings, star.key):
        return star
    return None


def _matches_row(label: str | None, rating: int | None, key: str) -> bool:
    info = next((item for item in config.LABELS if item.key == key), None)
    if info is None:
        return False
    if info.rating is not None:
        return rating == info.rating
    matched = _info_for_label(label)
    return matched is not None and matched.key == key


def _info_for_rating(rating: int | None) -> config.LabelInfo | None:
    if rating is None:
        return None
    for item in config.LABELS:
        if item.rating == rating:
            return item
    return None


def _info_for_label(label: str | None) -> config.LabelInfo | None:
    """Точное совпадение с xmp:Label. Пустая метка — это «Нет»."""
    if label:
        for item in config.LABELS:
            if item.xmp is not None and item.xmp == label:
                return item
        return None
    for item in config.LABELS:
        if item.xmp is None and item.rating is None:
            return item
    return None


def _plan_question(plan: list[_PlanLine]) -> str:
    lines = "\n".join(_plan_text(line, len(line.files)) for line in plan)
    return f"Будет выполнено:\n\n{lines}\n\nВыполнить обработку?"


def _move_place(parameter: str, location: str) -> str:
    if location == config.FOLDER_BESIDE_PHOTOS:
        return f"«{parameter}» рядом с фотографиями"
    return f"«{parameter}»"


def _plan_text(line: _PlanLine, count: int) -> str:
    if line.action == "move":
        if line.location == config.FOLDER_BESIDE_PHOTOS:
            target = f"{line.parameter} (рядом с фотографиями)"
        elif line.location == config.FOLDER_BROWSE:
            target = str(Path(line.parameter))
        else:
            target = line.parameter
    else:
        target = config.program_display_name(line.parameter)
    return f"{line.title} → {target}: {count}"


def _program_key(parameter: str) -> str:
    text = parameter.strip()
    if text.casefold() == "photoshop":
        return "photoshop"
    return os.path.normcase(os.path.abspath(text))


def _run_moves(
    folder: Path,
    plan: list[_PlanLine],
) -> tuple[dict[str, int], int, list[str]]:
    moved_counts: dict[str, int] = {}
    skipped = 0
    messages: list[str] = []
    for line in plan:
        if line.action != "move":
            continue
        moved, skipped_now, line_messages = move_green.move_matches(
            folder, line.files, line.parameter, line.location
        )
        moved_counts[line.key] = moved
        skipped += skipped_now
        messages.extend(line_messages)
    return moved_counts, skipped, messages


def _run_opens(plan: list[_PlanLine], find, launch) -> tuple[set[str], list[str]]:
    """Одна программа — один запуск со всеми её файлами."""
    groups: dict[str, list[Path]] = {}
    order: list[tuple[str, str]] = []
    for line in plan:
        if line.action != "open":
            continue
        key = _program_key(line.parameter)
        if key not in groups:
            order.append((key, line.parameter))
            groups[key] = []
        groups[key].extend(line.files)
    opened: set[str] = set()
    errors: list[str] = []
    for key, parameter in order:
        _count, error = _open_orange(groups[key], find, launch, parameter)
        if error is None:
            opened.add(key)
        else:
            errors.append(error)
    return opened, errors


def _plan_report(
    plan: list[_PlanLine],
    moved_counts: dict[str, int],
    opened_groups: set[str],
    skipped: int,
    move_messages: list[str],
    open_errors: list[str],
) -> str:
    lines = ["Обработка завершена.", ""]
    for line in plan:
        if line.action == "move":
            count = moved_counts.get(line.key, 0)
        else:
            count = len(line.files) if _program_key(line.parameter) in opened_groups else 0
        lines.append(_plan_text(line, count))
    if skipped:
        lines.append(f"Пропущено: {skipped}")
    if open_errors:
        lines.append("")
        lines.extend(open_errors)
    if any(message.startswith("ОШИБКА:") for message in move_messages):
        lines.append(f"Ошибок: {sum(message.startswith('ОШИБКА:') for message in move_messages)}")
    return "\n".join(lines)


def _is_configured_destination(folder: Path, notify, settings: config.Settings) -> bool:
    for item in config.LABELS:
        dest_name = config.move_folder(settings, item.key)
        if dest_name and _is_destination(folder, notify, dest_name, config.folder_location(settings, item.key)):
            return True
    return False


def _open_orange(files: list[Path], find, launch, program: str = "Photoshop") -> tuple[int, str | None]:
    executable, error = _executable(program, find)
    if error is not None:
        return 0, error
    if not photoshop.fits_in_command_line(executable, files):
        return 0, open_orange.TOO_MANY_FILES_MESSAGE
    try:
        launch(executable, files)
    except OSError:
        return 0, open_orange.PHOTOSHOP_FAILED_MESSAGE
    return len(files), None


def _move_report(moved: int, skipped: int, messages: list[str]) -> str:
    lines = [f"Перемещено: {moved}"]
    if skipped:
        lines.append(f"Пропущено: {skipped}")
    errors = sum(message.startswith("ОШИБКА:") for message in messages)
    if errors:
        lines.append(f"Ошибок: {errors}")
    return "\n".join(lines)


def _is_folder(folder: Path, notify) -> bool:
    if folder.is_dir():
        return True
    notify(f"ОШИБКА: папка не найдена: {folder}")
    return False


def _executable(program: str, find):
    text = program.strip()
    if text.casefold() == "photoshop":
        try:
            executable = find()
        except OSError:
            return None, open_orange.PHOTOSHOP_MISSING_MESSAGE
        if executable is None:
            return None, open_orange.PHOTOSHOP_MISSING_MESSAGE
        return executable, None
    path = Path(text)
    if not path.is_file():
        return None, "Программа не найдена."
    return path, None


def _is_destination(
    folder: Path,
    notify,
    dest_name: str = move_green.DEST_DIR_NAME,
    location: str = config.FOLDER_BESIDE_SCAN,
) -> bool:
    destination = move_green.destination_for(folder, dest_name, location)
    if not move_green._same_dir(folder, destination):
        return False
    notify(f"Папка «{dest_name}» — это папка назначения, она не сканируется.")
    return True
