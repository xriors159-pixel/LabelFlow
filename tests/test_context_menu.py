"""Проверяет команду контекстного меню и запись ключей реестра текущего пользователя."""

from __future__ import annotations

import sys
import unittest
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import context_menu


class ContextMenuTest(unittest.TestCase):
    def test_command_quotes_cyrillic_and_spaces(self) -> None:
        exe = Path(r"E:\Photo\Встреча Санфарма\LabelFlow.exe")
        self.assertEqual(
            context_menu.flagged_command(exe, "--move"),
            r'"E:\Photo\Встреча Санфарма\LabelFlow.exe" --move "%1"',
        )

    def test_install_and_uninstall_roundtrip(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "Встреча Санфарма" / "LabelFlow.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"fake")
            try:
                settings = config.default_settings()
                self.assertEqual(context_menu.install(exe, settings), 0)
                items = context_menu.menu_items(settings)
                move = next(item for item in items if item.key_name.endswith("Move_green"))
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    context_menu.SHELL_KEY,
                    0,
                    context_menu._access(),
                ) as key:
                    menu_name, _ = winreg.QueryValueEx(key, "MUIVerb")
                    extended, _ = winreg.QueryValueEx(key, "ExtendedSubCommandsKey")
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    move.command_key,
                    0,
                    context_menu._access(),
                ) as key:
                    command, _ = winreg.QueryValueEx(key, "")
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    move.key,
                    0,
                    context_menu._access(),
                ) as key:
                    title, _ = winreg.QueryValueEx(key, "MUIVerb")
                    move_icon, _ = winreg.QueryValueEx(key, "Icon")

                self.assertEqual(menu_name, "LabelFlow")
                self.assertEqual(extended, context_menu.EXTENDED_SUBCOMMANDS)
                self.assertEqual(title, "Переместить зеленые в Подрядчики")
                self.assertEqual(move_icon, context_menu.EXPLORER_ICON)
                self.assertEqual(
                    command,
                    context_menu.flagged_command(exe.resolve(), "--label green"),
                )
            finally:
                context_menu.uninstall()

            self.assertFalse(self._key_exists(context_menu.SHELL_KEY))
            self.assertFalse(self._key_exists(context_menu.MENU_KEY))
            self.assertEqual(context_menu.uninstall(), 0)

    def test_flat_menu_replaces_old_items(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "Встреча Санфарма" / "LabelFlow.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"fake")
            try:
                settings = config.default_settings()
                self.assertEqual(context_menu.install(exe, settings), 0)
                items = context_menu.menu_items(settings)
                commands = {context_menu.PROCESS_COMMAND_KEY: "--process-all"}
                expected_titles = {context_menu.PROCESS_KEY: "Запустить все"}
                expected_icons = {context_menu.PROCESS_KEY: None}
                for item in items:
                    commands[item.command_key] = item.flag
                    expected_titles[item.key] = item.title
                    expected_icons[item.key] = item.icon
                self.assertEqual(
                    [item.title for item in items],
                    ["Переместить зеленые в Подрядчики", "Открыть оранжевые в Photoshop"],
                )
                shell_key = context_menu.MENU_KEY + r"\shell"
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    shell_key,
                    0,
                    context_menu._access(),
                ) as key:
                    names = []
                    index = 0
                    while True:
                        try:
                            names.append(winreg.EnumKey(key, index))
                        except OSError:
                            break
                        index += 1
                self.assertEqual(sorted(names), ["01ProcessAll", "02Move_green", "03Open_orange"])
                for key_path, title in expected_titles.items():
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        key_path,
                        0,
                        context_menu._access(),
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "MUIVerb")
                        try:
                            icon, _ = winreg.QueryValueEx(key, "Icon")
                        except FileNotFoundError:
                            icon = None
                    self.assertEqual(value, title)
                    self.assertEqual(icon, expected_icons[key_path])
                resolved = exe.resolve()
                for key_path, flag in commands.items():
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        key_path,
                        0,
                        context_menu._access(),
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                    self.assertEqual(value, context_menu.flagged_command(resolved, flag))
                self.assertFalse(self._key_exists(context_menu.MENU_KEY + r"\shell\MoveGreen"))
                self.assertFalse(self._key_exists(context_menu.MENU_KEY + r"\shell\Orange"))
                self.assertFalse(self._key_exists(context_menu.MENU_KEY + r"\OrangeCascade"))
                self.assertNotIn("Переместить зеленые", expected_titles.values())
            finally:
                context_menu.uninstall()

    def test_custom_rules_replace_menu_items(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "LabelFlow.exe"
            viewer = Path(temporary) / "Viewer.exe"
            exe.write_bytes(b"fake")
            viewer.write_bytes(b"MZ")
            settings = config.default_settings()
            settings.set_rule("green", config.LabelRule(False, "none", ""))
            settings.set_rule("orange", config.LabelRule(False, "none", ""))
            settings.set_rule("red", config.LabelRule(True, "move", "Брак"))
            settings.set_rule("blue", config.LabelRule(True, "open", str(viewer)))
            try:
                self.assertEqual(context_menu.install(exe, settings), 0)
                shell_key = context_menu.MENU_KEY + r"\shell"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, shell_key, 0, context_menu._access()) as key:
                    names = []
                    index = 0
                    while True:
                        try:
                            names.append(winreg.EnumKey(key, index))
                        except OSError:
                            break
                        index += 1
                self.assertEqual(sorted(names), ["01ProcessAll", "02Move_red", "03Open_blue"])
                move = context_menu.menu_items(settings)[0]
                opened = context_menu.menu_items(settings)[1]
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, move.key, 0, context_menu._access()) as key:
                    title, _ = winreg.QueryValueEx(key, "MUIVerb")
                    icon, _ = winreg.QueryValueEx(key, "Icon")
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, opened.key, 0, context_menu._access()) as key:
                    open_title, _ = winreg.QueryValueEx(key, "MUIVerb")
                    open_icon, _ = winreg.QueryValueEx(key, "Icon")
                self.assertEqual(title, "Переместить красные в Брак")
                self.assertEqual(icon, context_menu.EXPLORER_ICON)
                self.assertEqual(open_title, "Открыть синие в Viewer")
                self.assertEqual(open_icon, f"{viewer},0")
                self.assertFalse(self._key_exists(context_menu.MENU_KEY + r"\shell\02Move_green"))
            finally:
                context_menu.uninstall()

    def _key_exists(self, subkey: str) -> bool:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                subkey,
                0,
                context_menu._access(),
            )
        except FileNotFoundError:
            return False
        winreg.CloseKey(key)
        return True


if __name__ == "__main__":
    unittest.main()
