"""Настройки действий для цветовых меток XMP.

Файл лежит в профиле пользователя, а не рядом с EXE:

    %APPDATA%\\LabelFlow\\config.json

Если файла нет или он повреждён, остаются правила, с которыми LabelFlow
уже работает: зелёные переносятся в «Подрядчики», оранжевые открываются
в Photoshop, остальные метки ничего не делают.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ACTIONS = ("none", "move", "open")
PHOTOSHOP_TOKEN = "Photoshop"
FOLDER_BROWSE = "browse"
FOLDER_BESIDE_PHOTOS = "beside_photos"
FOLDER_BESIDE_SCAN = "beside_scan"
FOLDER_LOCATIONS = (FOLDER_BROWSE, FOLDER_BESIDE_PHOTOS, FOLDER_BESIDE_SCAN)
_INVALID_FOLDER_CHARS = set('\\/:*?"<>|')


@dataclass(frozen=True)
class LabelInfo:
    key: str
    title: str
    xmp: str | None
    swatch: str | None
    rating: int | None = None


# Квадраты повторяют яркие метки Photo Mechanic. Звёзды — xmp:Rating от 1 до 5.
LABELS: tuple[LabelInfo, ...] = (
    LabelInfo("none", "Нет", None, "#9A9A9A"),
    LabelInfo("red", "Красный", "Красный", "#E2231A"),
    LabelInfo("orange", "Оранжевый", "Оранжевый", "#F18C1E"),
    LabelInfo("yellow", "Желтый", "Желтый", "#F2D31B"),
    LabelInfo("green", "Зеленый", "Зеленый", "#3AA73A"),
    LabelInfo("blue", "Синий", "Синий", "#2176D6"),
    LabelInfo("pink", "Розовый", "Розовый", "#E83E8C"),
    LabelInfo("purple", "Пурпурный", "Пурпурный", "#8B3DB8"),
    LabelInfo("star1", "1★", None, None, 1),
    LabelInfo("star2", "2★", None, None, 2),
    LabelInfo("star3", "3★", None, None, 3),
    LabelInfo("star4", "4★", None, None, 4),
    LabelInfo("star5", "5★", None, None, 5),
)
_BY_KEY = {item.key: item for item in LABELS}


@dataclass
class LabelRule:
    enabled: bool
    action: str
    parameter: str
    folder_location: str = FOLDER_BESIDE_SCAN


class Settings:
    def __init__(self, labels: dict[str, LabelRule]):
        self.labels = labels

    def rule(self, key: str) -> LabelRule:
        return self.labels[key]

    def set_rule(self, key: str, rule: LabelRule) -> None:
        if key not in _BY_KEY:
            raise KeyError(key)
        self.labels[key] = rule


def config_path() -> Path:
    override = os.environ.get("LABELFLOW_CONFIG")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "LabelFlow" / "config.json"


def default_settings() -> Settings:
    labels: dict[str, LabelRule] = {}
    for item in LABELS:
        if item.key == "green":
            labels[item.key] = LabelRule(True, "move", "Подрядчики")
        elif item.key == "orange":
            labels[item.key] = LabelRule(True, "open", PHOTOSHOP_TOKEN)
        else:
            labels[item.key] = LabelRule(False, "none", "")
    return Settings(labels)


def load(path: Path | None = None) -> Settings:
    """Читает конфигурацию. Отсутствие и порча файла дают значения по умолчанию."""
    target = config_path() if path is None else path
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_settings()
    except OSError:
        return default_settings()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return default_settings()
    if not isinstance(data, dict):
        return default_settings()
    return _parse(data)


def ensure(path: Path | None = None) -> Settings:
    """Создаёт файл со значениями по умолчанию, если его ещё нет."""
    target = config_path() if path is None else path
    if target.is_file():
        return load(target)
    settings = default_settings()
    save(settings, target)
    return settings


def save(settings: Settings, path: Path | None = None) -> None:
    target = config_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_dict(settings), ensure_ascii=False, indent=2) + "\n"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(target)


def to_dict(settings: Settings) -> dict:
    labels = {}
    for item in LABELS:
        rule = settings.rule(item.key)
        entry = {
            "enabled": rule.enabled and rule.action != "none",
            "action": rule.action if rule.action in ACTIONS else "none",
            "action_parameter": rule.parameter,
        }
        if entry["action"] == "move":
            entry["folder_location"] = (
                rule.folder_location if rule.folder_location in FOLDER_LOCATIONS else FOLDER_BESIDE_SCAN
            )
        labels[item.key] = entry
    return {"version": 1, "labels": labels}


def move_folder(settings: Settings, key: str) -> str | None:
    """Имя папки для метки, если для неё включено перемещение."""
    rule = settings.rule(key)
    if not rule.enabled or rule.action != "move":
        return None
    name = rule.parameter.strip()
    return name or None


def open_program(settings: Settings, key: str) -> str | None:
    """Программа для метки: путь к EXE или слово Photoshop."""
    rule = settings.rule(key)
    if not rule.enabled or rule.action != "open":
        return None
    name = rule.parameter.strip()
    return name or None


def folder_location(settings: Settings, key: str) -> str:
    """Куда класть папку: выбранный путь, рядом с фото или рядом со сканируемой."""
    place = settings.rule(key).folder_location
    if place in FOLDER_LOCATIONS:
        return place
    return FOLDER_BESIDE_SCAN


def folder_display_name(parameter: str, location: str) -> str:
    text = parameter.strip()
    if location == FOLDER_BROWSE:
        name = Path(text).name
        return name or text
    return text


def folder_place_error(parameter: str, location: str) -> str | None:
    if location == FOLDER_BROWSE:
        text = parameter.strip()
        if not text:
            return "Выберите папку."
        if not Path(text).is_dir():
            return "Папка не найдена."
        return None
    return folder_name_error(parameter)


def folder_name_error(name: str) -> str | None:
    text = name.strip()
    if not text:
        return "Укажите имя папки."
    if text in {".", ".."} or any(char in _INVALID_FOLDER_CHARS for char in text):
        return 'Имя папки не должно содержать \\ / : * ? " < > |'
    return None


def program_error(parameter: str) -> str | None:
    text = parameter.strip()
    if not text:
        return "Выберите программу."
    if text.casefold() == PHOTOSHOP_TOKEN.casefold():
        return None
    path = Path(text)
    if path.is_file() and path.suffix.casefold() == ".exe":
        return None
    return "Укажите файл программы (.exe)."


def program_display_name(parameter: str) -> str:
    text = parameter.strip()
    if not text or text.casefold() == PHOTOSHOP_TOKEN.casefold():
        return PHOTOSHOP_TOKEN
    return Path(text).stem or text


def _parse(data: dict) -> Settings:
    raw_labels = data.get("labels")
    if not isinstance(raw_labels, dict):
        return default_settings()
    defaults = default_settings()
    labels: dict[str, LabelRule] = {}
    for item in LABELS:
        labels[item.key] = _rule_from(raw_labels.get(item.key), defaults.rule(item.key))
    return Settings(labels)


def _rule_from(value: object, fallback: LabelRule) -> LabelRule:
    if not isinstance(value, dict):
        return fallback
    action = value.get("action", fallback.action)
    if not isinstance(action, str) or action not in ACTIONS:
        action = "none"
    parameter = value.get("action_parameter", value.get("parameter", ""))
    if not isinstance(parameter, str):
        parameter = ""
    enabled = value.get("enabled", action != "none")
    if not isinstance(enabled, bool):
        enabled = action != "none"
    if action == "none":
        enabled = False
    location = value.get("folder_location", fallback.folder_location)
    if not isinstance(location, str) or location not in FOLDER_LOCATIONS:
        location = FOLDER_BESIDE_SCAN
    return LabelRule(enabled, action, parameter, location)
