# -*- mode: python ; coding: utf-8 -*-
# Оконное приложение: Explorer не должен открывать окно консоли.
# Модули действий импортируются по флагу командной строки, поэтому они указаны явно.

a = Analysis(
    ['move_green.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'context_menu',
        'open_orange',
        'photoshop',
        'actions',
        'win_message',
        'config',
        'settings_window',
        'tray',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LabelFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='LabelFlow.manifest',
)
