# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file. Jalankan lewat build.bat, atau manual:
#   pyinstaller app.spec --noconfirm
#
# Menghasilkan satu file portable: dist/AndroidAuditTool.exe
# (tanpa console window, adb + AdbWin*.dll ikut ter-bundle di dalamnya)

import os
from PyInstaller.utils.hooks import collect_data_files

app_main = os.path.join(SPECPATH, "app", "main_gui.py")
vendor_dir = os.path.join(SPECPATH, "vendor", "platform-tools")

datas = [(vendor_dir, "platform-tools")]
datas += collect_data_files("customtkinter")

a = Analysis(
    [app_main],
    pathex=[os.path.join(SPECPATH, "app")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AndroidAuditTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # tanpa jendela console hitam (aplikasi GUI murni)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
