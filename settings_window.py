"""Окно «Настройки LabelFlow».

Таблица как в черновике: слева цвет или звёзды, справа одно поле «Действие».
«Переместить в папку» открывает окно расположения папки.
«Открыть программу» открывает выбор EXE.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config

_PLACEHOLDER = "<Действие>"
_MOVE = "Переместить в папку"
_OPEN = "Открыть программу"
_ROW_HEIGHT = 36
_MARK_WIDTH = 52


class _Row:
    def __init__(self, info: config.LabelInfo, rule: config.LabelRule, parent: ttk.Frame, row: int) -> None:
        self.info = info
        self._action = "none"
        self._folder = ""
        self._location = rule.folder_location if rule.folder_location in config.FOLDER_LOCATIONS else config.FOLDER_BESIDE_SCAN
        self._program = ""
        if rule.enabled and rule.action == "move":
            self._action = "move"
            self._folder = rule.parameter
        elif rule.enabled and rule.action == "open":
            self._action = "open"
            self._program = rule.parameter

        mark = tk.Frame(
            parent,
            width=_MARK_WIDTH,
            height=_ROW_HEIGHT,
            bg=info.swatch or "white",
            highlightthickness=1,
            highlightbackground="black",
        )
        mark.grid(row=row, column=0, sticky="nsew")
        mark.grid_propagate(False)
        if info.swatch is None:
            tk.Label(mark, text=info.title, bg="white", fg="black", font=("Segoe UI", 12)).place(
                relx=0.5, rely=0.5, anchor="center"
            )

        cell = tk.Frame(parent, height=_ROW_HEIGHT, bg="white", highlightthickness=1, highlightbackground="black")
        cell.grid(row=row, column=1, sticky="nsew")
        cell.grid_propagate(False)
        self.choice = tk.Menubutton(
            cell,
            text=self._caption(),
            anchor="w",
            relief="flat",
            bd=0,
            bg="white",
            activebackground="#f2f2f2",
            padx=10,
            font=("Segoe UI", 10),
            direction="below",
        )
        self.choice.pack(fill="both", expand=True)
        menu = tk.Menu(self.choice, tearoff=0, font=("Segoe UI", 10))
        menu.add_command(label=_MOVE, command=self._choose_move)
        menu.add_command(label=_OPEN, command=self._choose_open)
        menu.add_separator()
        menu.add_command(label=_PLACEHOLDER, command=self._clear)
        self.choice.configure(menu=menu)

    def _caption(self) -> str:
        if self._action == "move" and self._folder:
            return f"{_MOVE} — {config.folder_display_name(self._folder, self._location)}"
        if self._action == "open" and self._program:
            return f"{_OPEN} — {config.program_display_name(self._program)}"
        return _PLACEHOLDER

    def _refresh(self) -> None:
        self.choice.configure(text=self._caption())

    def _choose_move(self) -> None:
        location = self._location if self._action == "move" else config.FOLDER_BESIDE_PHOTOS
        name = self._folder if self._action == "move" else ""
        chosen = ask_folder_place(self.choice.winfo_toplevel(), name, location)
        if chosen is None:
            return
        self._location, self._folder = chosen
        self._action = "move"
        self._refresh()

    def _choose_open(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.choice.winfo_toplevel(),
            title="Выбор программы",
            filetypes=[("Программы", "*.exe"), ("Все файлы", "*.*")],
        )
        if not selected:
            return
        self._action = "open"
        self._program = selected
        self._refresh()

    def _clear(self) -> None:
        self._action = "none"
        self._folder = ""
        self._program = ""
        self._refresh()

    def set_action(self, action: str) -> None:
        self._action = action if action in {"none", "move", "open"} else "none"
        self._refresh()

    def set_location(self, location: str) -> None:
        if location in config.FOLDER_LOCATIONS:
            self._location = location
        self._refresh()

    def set_parameter(self, value: str) -> None:
        if self._action == "move":
            self._folder = value
        elif self._action == "open":
            self._program = value
        self._refresh()

    def chosen_action(self) -> str:
        return self._action

    def folder_location(self) -> str:
        return self._location

    def parameter_value(self) -> str:
        if self._action == "move":
            return self._folder.strip()
        if self._action == "open":
            return self._program.strip()
        return ""


class SettingsEditor:
    def __init__(self, master: tk.Misc | None = None, settings: config.Settings | None = None) -> None:
        self.window = tk.Tk() if master is None else tk.Toplevel(master)
        self.window.withdraw()
        self.window.title("Настройки LabelFlow")
        self.window.resizable(False, False)
        self.window.configure(bg="white")
        loaded = config.load() if settings is None else settings
        self._hidden = {item.key: loaded.rule(item.key) for item in config.LABELS if item.key == "none"}
        self.rows: dict[str, _Row] = {}
        self._build(loaded)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

    def _build(self, settings: config.Settings) -> None:
        frame = ttk.Frame(self.window, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        visible = [item for item in config.LABELS if item.key != "none"]
        for index, info in enumerate(visible):
            self.rows[info.key] = _Row(info, settings.rule(info.key), frame, index)
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(visible), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Сохранить", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Отмена", command=self.cancel).pack(side="left", padx=(8, 0))

    def show(self) -> None:
        self.window.update_idletasks()
        width = max(self.window.winfo_reqwidth(), 520)
        height = self.window.winfo_reqheight()
        x = max((self.window.winfo_screenwidth() - width) // 2, 0)
        y = max((self.window.winfo_screenheight() - height) // 2, 0)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.deiconify()
        if not isinstance(self.window, tk.Tk):
            _own_taskbar_button(self.window)
        self.window.lift()
        self.window.focus_force()

    def alive(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def validate(self) -> str | None:
        for info in config.LABELS:
            row = self.rows.get(info.key)
            if row is None:
                continue
            action = row.chosen_action()
            if action == "move":
                error = config.folder_place_error(row.parameter_value(), row.folder_location())
            elif action == "open":
                error = config.program_error(row.parameter_value())
            else:
                error = None
            if error:
                return f"«{info.title}»: {error}"
        return None

    def collect(self) -> config.Settings:
        labels = {}
        for info in config.LABELS:
            row = self.rows.get(info.key)
            if row is None:
                labels[info.key] = self._hidden[info.key]
                continue
            action = row.chosen_action()
            labels[info.key] = config.LabelRule(
                enabled=action != "none",
                action=action,
                parameter=row.parameter_value(),
                folder_location=row.folder_location(),
            )
        return config.Settings(labels)

    def save(self) -> bool:
        error = self.validate()
        if error:
            messagebox.showerror("Настройки LabelFlow", error, parent=self.window)
            return False
        config.save(self.collect())
        import context_menu

        if context_menu.install() != 0:
            messagebox.showerror(
                "Настройки LabelFlow",
                "Настройки сохранены, но контекстное меню Проводника не обновлено.",
                parent=self.window,
            )
        self.window.destroy()
        return True

    def cancel(self) -> None:
        self.window.destroy()


def ask_folder_place(parent: tk.Misc, initial: str, location: str) -> tuple[str, str] | None:
    """Окно расположения папки. None — отмена, иначе (режим, путь или имя)."""
    dialog = tk.Toplevel(parent)
    dialog.title("Расположение папки")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.configure(bg="white")
    style = ttk.Style(dialog)
    style.configure("Hint.TLabel", foreground="#8A8A8A")

    place = location if location in config.FOLDER_LOCATIONS else config.FOLDER_BESIDE_PHOTOS
    mode = tk.StringVar(value=place)
    browse_value = tk.StringVar(value=initial if place == config.FOLDER_BROWSE else "")
    photos_value = tk.StringVar(value=initial if place == config.FOLDER_BESIDE_PHOTOS else "")
    scan_value = tk.StringVar(value=initial if place == config.FOLDER_BESIDE_SCAN else "")

    ttk.Label(dialog, text="Расположение папки:", font=("Segoe UI", 10, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 10)
    )
    ttk.Radiobutton(dialog, text="Выбрать папку", value=config.FOLDER_BROWSE, variable=mode).grid(
        row=1, column=0, sticky="w", padx=(16, 12), pady=6
    )
    browse_entry = ttk.Entry(dialog, textvariable=browse_value, width=36)
    browse_entry.grid(row=1, column=1, sticky="ew", pady=6)
    browse_button = ttk.Button(dialog, text="Обзор...", command=lambda: _browse())
    browse_button.grid(row=1, column=2, sticky="w", padx=(8, 16), pady=6)

    ttk.Radiobutton(
        dialog, text="Рядом с фотографиями", value=config.FOLDER_BESIDE_PHOTOS, variable=mode, command=lambda: _focus(photos_entry)
    ).grid(row=2, column=0, sticky="w", padx=(16, 12), pady=6)
    photos_entry = ttk.Entry(dialog, textvariable=photos_value, width=36)
    photos_entry.grid(row=2, column=1, sticky="ew", pady=6)
    ttk.Label(dialog, text="Например: Подрядчики", style="Hint.TLabel").grid(
        row=2, column=2, sticky="w", padx=(8, 16)
    )

    ttk.Radiobutton(
        dialog,
        text="Рядом со сканируемой папкой",
        value=config.FOLDER_BESIDE_SCAN,
        variable=mode,
        command=lambda: _focus(scan_entry),
    ).grid(row=3, column=0, sticky="w", padx=(16, 12), pady=6)
    scan_entry = ttk.Entry(dialog, textvariable=scan_value, width=36)
    scan_entry.grid(row=3, column=1, sticky="ew", pady=6)
    ttk.Label(dialog, text="Например: Подрядчики", style="Hint.TLabel").grid(
        row=3, column=2, sticky="w", padx=(8, 16)
    )

    result: dict[str, tuple[str, str] | None] = {"value": None}

    def _focus(entry: ttk.Entry) -> None:
        _sync()
        if str(entry.cget("state")) == "normal":
            entry.focus_set()
            entry.selection_range(0, "end")

    def _browse() -> None:
        selected = filedialog.askdirectory(parent=dialog, title="Выбрать папку", mustexist=True)
        if not selected:
            return
        browse_value.set(selected)
        mode.set(config.FOLDER_BROWSE)
        _sync()

    def _sync(*_args: object) -> None:
        current = mode.get()
        browse_entry.configure(state="readonly" if current == config.FOLDER_BROWSE else "disabled")
        browse_button.configure(state="normal")
        photos_entry.configure(state="normal" if current == config.FOLDER_BESIDE_PHOTOS else "disabled")
        scan_entry.configure(state="normal" if current == config.FOLDER_BESIDE_SCAN else "disabled")

    def accept() -> None:
        current = mode.get()
        if current == config.FOLDER_BROWSE:
            value = browse_value.get()
        elif current == config.FOLDER_BESIDE_PHOTOS:
            value = photos_value.get()
        else:
            current = config.FOLDER_BESIDE_SCAN
            value = scan_value.get()
        error = config.folder_place_error(value, current)
        if error:
            messagebox.showerror("Расположение папки", error, parent=dialog)
            return
        result["value"] = (current, value.strip())
        dialog.destroy()

    def dismiss() -> None:
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.grid(row=4, column=0, columnspan=3, sticky="e", padx=16, pady=(12, 14))
    ttk.Button(buttons, text="ОК", command=accept).pack(side="left")
    ttk.Button(buttons, text="Отмена", command=dismiss).pack(side="left", padx=(8, 0))
    dialog.columnconfigure(1, weight=1)
    dialog.protocol("WM_DELETE_WINDOW", dismiss)
    dialog.bind("<Return>", lambda _event: accept())
    dialog.bind("<Escape>", lambda _event: dismiss())
    mode.trace_add("write", _sync)
    _sync()
    dialog.update_idletasks()
    dialog.grab_set()
    if place == config.FOLDER_BESIDE_PHOTOS:
        photos_entry.focus_set()
    elif place == config.FOLDER_BESIDE_SCAN:
        scan_entry.focus_set()
    parent.wait_window(dialog)
    return result["value"]


def _own_taskbar_button(window: tk.Misc) -> None:
    """Дочернее окно трея должно быть обычным окном на панели задач."""
    import ctypes

    user32 = ctypes.windll.user32
    get_long = user32.GetWindowLongPtrW
    set_long = user32.SetWindowLongPtrW
    get_long.restype = ctypes.c_ssize_t
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    set_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    style = get_long(window.winfo_id(), -20)
    set_long(window.winfo_id(), -20, (style | 0x00040000) & ~0x00000080)
    window.withdraw()
    window.deiconify()


def run() -> int:
    _dpi()
    config.ensure()
    editor = SettingsEditor()
    editor.show()
    editor.window.mainloop()
    return 0


def _dpi() -> None:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            return
