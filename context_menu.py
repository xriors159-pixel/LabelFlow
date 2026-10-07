"""Регистрация плоского меню LabelFlow в контекстном меню папок.

Пункты берутся из config.json:
    Запустить все
    затем каждое включённое «Переместить …»
    затем каждое включённое «Открыть …»

Порядок задают имена ключей 01, 02, 03: Проводник сортирует команды по ним.
Поиск JPG и чтение XMP остаются в move_green.py.
"""

from __future__ import annotations

import ctypes
import sys
import winreg
from dataclasses import dataclass
from pathlib import Path

import config

MENU_NAME = "LabelFlow"
SHELL_KEY = r"Software\Classes\Directory\shell\LabelFlow"
MENU_KEY = r"Software\Classes\Directory\ContextMenus\LabelFlow"
EXTENDED_SUBCOMMANDS = r"Directory\ContextMenus\LabelFlow"

PROCESS_TITLE = "Запустить все"
EXPLORER_ICON = r"%SystemRoot%\explorer.exe,0"

PROCESS_KEY = MENU_KEY + r"\shell\01ProcessAll"
PROCESS_COMMAND_KEY = PROCESS_KEY + r"\command"

# Винительный падеж множественного числа: «Переместить зеленые в Подрядчики».
_COLOR_NAMES = {
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

_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_IDLIST = 0x0000


def program_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent / "dist" / "LabelFlow.exe"


def flagged_command(exe: Path, flag: str) -> str:
    """Команда для Проводника. Кавычки сохраняют пробелы и кириллицу в пути."""
    exe_text = str(exe)
    if '"' in exe_text:
        raise ValueError("Путь к программе не должен содержать кавычки")
    return f'"{exe_text}" {flag} "%1"'


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def _say(text: str, stream=None) -> None:
    target = sys.stdout if stream is None else stream
    if target is None:
        return
    print(text, file=target)


@dataclass(frozen=True)
class MenuItem:
    key_name: str
    title: str
    flag: str
    icon: str | None

    @property
    def key(self) -> str:
        return MENU_KEY + "\\shell\\" + self.key_name

    @property
    def command_key(self) -> str:
        return self.key + "\\command"


def menu_items(settings: config.Settings) -> list[MenuItem]:
    """Пункты под «Запустить все»: сначала переносы, затем запуск программ."""
    moves: list[tuple[str, str]] = []
    opens: list[tuple[str, str, str]] = []
    for item in config.LABELS:
        rule = settings.rule(item.key)
        if not rule.enabled or rule.action not in {"move", "open"}:
            continue
        parameter = rule.parameter.strip()
        if not parameter:
            continue
        color = _COLOR_NAMES[item.key]
        if rule.action == "move":
            shown = config.folder_display_name(parameter, rule.folder_location)
            moves.append((item.key, f"Переместить {color} в {shown}"))
        else:
            opens.append((item.key, f"Открыть {color} в {config.program_display_name(parameter)}", parameter))
    items: list[MenuItem] = []
    index = 2
    for key, title in moves:
        items.append(MenuItem(f"{index:02d}Move_{key}", title, f"--label {key}", EXPLORER_ICON))
        index += 1
    for key, title, parameter in opens:
        items.append(MenuItem(f"{index:02d}Open_{key}", title, f"--label {key}", _open_icon(parameter)))
        index += 1
    return items


def install(exe: Path | None = None, settings: config.Settings | None = None) -> int:
    _configure_stdio()
    target = (program_path() if exe is None else Path(exe)).resolve()
    if not target.is_file():
        _say(f"ОШИБКА: не найден файл программы: {target}", sys.stderr)
        _say("Соберите его командой install_context_menu.bat", sys.stderr)
        return 1

    current = config.load() if settings is None else settings
    _delete_tree(winreg.HKEY_CURRENT_USER, SHELL_KEY)
    _delete_tree(winreg.HKEY_CURRENT_USER, MENU_KEY)
    _write_values(
        SHELL_KEY,
        [
            ("", ""),
            ("MUIVerb", MENU_NAME),
            ("ExtendedSubCommandsKey", EXTENDED_SUBCOMMANDS),
            ("Icon", str(target)),
        ],
    )
    _write_verb(PROCESS_KEY, PROCESS_TITLE, flagged_command(target, "--process-all"))
    written = [PROCESS_TITLE]
    for item in menu_items(current):
        _write_verb(item.key, item.title, flagged_command(target, item.flag), item.icon)
        written.append(item.title)
    _notify_shell()

    _say("Контекстное меню установлено для текущего пользователя.")
    for title in written:
        _say(f"ПКМ по папке: LabelFlow -> {title}")
    _say("")
    _say("В Windows 11 пункт находится в классическом меню:")
    _say("Shift+ПКМ или «Показать дополнительные параметры».")
    return 0


def uninstall() -> int:
    _configure_stdio()
    _delete_tree(winreg.HKEY_CURRENT_USER, SHELL_KEY)
    _delete_tree(winreg.HKEY_CURRENT_USER, MENU_KEY)
    _notify_shell()
    _say("Пункт LabelFlow удалён из контекстного меню текущего пользователя.")
    return 0


def _open_icon(parameter: str) -> str | None:
    text = parameter.strip()
    if text.casefold() == config.PHOTOSHOP_TOKEN.casefold():
        return photoshop_icon()
    path = Path(text)
    if path.is_file():
        return f"{path},0"
    return None


def photoshop_icon() -> str | None:
    """Значок установленного Photoshop. Индекс 0 — основная иконка exe."""
    import photoshop

    found = photoshop.find_photoshop()
    if found is None:
        return None
    return f"{found},0"


def _write_verb(key_path: str, title: str, command: str, icon: str | None = None) -> None:
    values = [("", title), ("MUIVerb", title)]
    if icon:
        values.append(("Icon", icon))
    _write_values(key_path, values)
    _write_values(key_path + r"\command", [("", command)])


def _access(extra: int = 0) -> int:
    return winreg.KEY_READ | winreg.KEY_WRITE | getattr(winreg, "KEY_WOW64_64KEY", 0) | extra


def _write_values(subkey: str, values: list[tuple[str, str]]) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, _access()) as key:
        for name, value in values:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _delete_tree(root: int, subkey: str) -> None:
    try:
        key = winreg.OpenKey(root, subkey, 0, _access())
    except FileNotFoundError:
        return
    try:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(root, subkey + "\\" + child)
    finally:
        winreg.CloseKey(key)
    winreg.DeleteKey(root, subkey)


def _notify_shell() -> None:
    ctypes.windll.shell32.SHChangeNotify(_SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["install"]:
        return install()
    if argv == ["uninstall"]:
        return uninstall()
    _say("Использование: python context_menu.py install|uninstall", sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
