"""Поиск установленного Adobe Photoshop и один запуск со списком файлов.

shell=True не используется: аргументы передаются списком в CreateProcess,
поэтому пробелы, кириллица и скобки остаются частью пути.
"""

from __future__ import annotations

import os
import re
import subprocess
import winreg
from pathlib import Path

# CreateProcessW принимает командную строку не длиннее 32767 символов.
COMMAND_LINE_LIMIT = 32767

_APP_PATH_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
)
_ADOBE_KEYS = (
    r"SOFTWARE\Adobe\Photoshop",
    r"SOFTWARE\WOW6432Node\Adobe\Photoshop",
)
_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
_REGISTRY_ROOTS = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
_READ_FLAGS = (
    winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
    winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
)


def find_photoshop(
    adobe_roots: list[Path] | None = None,
    registry_lookup=None,
) -> Path | None:
    """Сначала стандартные каталоги Adobe, затем реестр Windows."""
    roots = default_adobe_roots() if adobe_roots is None else adobe_roots
    standard = _standard_executables(roots)
    if standard:
        return _newest(standard)
    lookup = _registry_executables if registry_lookup is None else registry_lookup
    try:
        registered = [path for path in lookup() if path.is_file()]
    except OSError:
        registered = []
    if not registered:
        return None
    return _newest(registered)


def default_adobe_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if not value:
            continue
        root = Path(value) / "Adobe"
        key = os.path.normcase(str(root))
        if key in seen:
            continue
        seen.add(key)
        roots.append(root)
    return roots


def command_line(exe: Path, files: list[Path]) -> str:
    return subprocess.list2cmdline([str(exe), *[str(path) for path in files]])


def fits_in_command_line(exe: Path, files: list[Path]) -> bool:
    return len(command_line(exe, files)) < COMMAND_LINE_LIMIT


def launch_photoshop(exe: Path, files: list[Path]) -> None:
    """Один процесс Photoshop, каждый файл — отдельный аргумент."""
    subprocess.Popen(
        [str(exe), *[str(path) for path in files]],
        shell=False,
    )


def normalize_registered_path(value: str) -> Path | None:
    text = value.strip().strip('"')
    if not text:
        return None
    head, separator, tail = text.rpartition(",")
    if separator and tail.isdigit():
        text = head.strip().strip('"')
    if not text:
        return None
    path = Path(text)
    if path.suffix.lower() == ".exe":
        return path
    return path / "Photoshop.exe"


def _standard_executables(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        try:
            if not root.is_dir():
                continue
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if not child.is_dir() or not _is_photoshop_name(child.name):
                    continue
            except OSError:
                continue
            exe = child / "Photoshop.exe"
            if exe.is_file():
                found.append(exe)
    return found


def _is_photoshop_name(name: str) -> bool:
    folded = name.casefold()
    if "photoshop" not in folded:
        return False
    if "elements" in folded or "lightroom" in folded:
        return False
    return True


def _newest(paths: list[Path]) -> Path:
    return max(paths, key=_version_key)


def _version_key(path: Path) -> tuple[int, int, str]:
    numbers = [int(item) for item in re.findall(r"\d+", path.parent.name)]
    years = [number for number in numbers if number >= 1990]
    versions = [number for number in numbers if number < 1990]
    year = max(years) if years else 0
    version = max(versions) if versions else 0
    return (year, version, path.parent.name.casefold())


def _registry_executables() -> list[Path]:
    found: list[Path] = []
    found.extend(_app_path_executables())
    found.extend(_adobe_key_executables())
    found.extend(_uninstall_executables())
    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _app_path_executables() -> list[Path]:
    found: list[Path] = []
    for root in _REGISTRY_ROOTS:
        for subkey in _APP_PATH_KEYS:
            value = _query_default(root, subkey)
            if value is None:
                continue
            path = normalize_registered_path(value)
            if path is not None and path.is_file():
                found.append(path)
    return found


def _adobe_key_executables() -> list[Path]:
    found: list[Path] = []
    for root in _REGISTRY_ROOTS:
        for subkey in _ADOBE_KEYS:
            for child in _subkeys(root, subkey):
                value = _query_value(root, subkey + "\\" + child, "ApplicationPath")
                if value is None:
                    continue
                path = normalize_registered_path(value)
                if path is not None and path.is_file():
                    found.append(path)
    return found


def _uninstall_executables() -> list[Path]:
    found: list[Path] = []
    for root in _REGISTRY_ROOTS:
        for subkey in _UNINSTALL_KEYS:
            for child in _subkeys(root, subkey):
                child_path = subkey + "\\" + child
                display_name = _query_value(root, child_path, "DisplayName")
                if display_name is None or not _is_photoshop_name(display_name):
                    continue
                for value_name in ("DisplayIcon", "InstallLocation"):
                    value = _query_value(root, child_path, value_name)
                    if value is None:
                        continue
                    path = normalize_registered_path(value)
                    if path is not None and path.is_file():
                        found.append(path)
                        break
    return found


def _query_default(root: int, subkey: str) -> str | None:
    return _query_value(root, subkey, "")


def _query_value(root: int, subkey: str, name: str) -> str | None:
    for access in _READ_FLAGS:
        try:
            with winreg.OpenKey(root, subkey, 0, access) as key:
                value, kind = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        if kind == winreg.REG_SZ and isinstance(value, str):
            return value
        if kind == winreg.REG_EXPAND_SZ and isinstance(value, str):
            return os.path.expandvars(value)
    return None


def _subkeys(root: int, subkey: str) -> list[str]:
    names: list[str] = []
    for access in _READ_FLAGS:
        try:
            with winreg.OpenKey(root, subkey, 0, access) as key:
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except OSError:
            continue
        if names:
            break
    return names
