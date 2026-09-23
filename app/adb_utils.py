#!/usr/bin/env python3
"""
adb_utils.py (versi GUI)

Beda dengan versi CLI: modul ini TIDAK PERNAH memanggil input() atau
mencetak ke terminal. Semua keputusan yang butuh interaksi user (pilih
device kalau lebih dari satu, dsb) diserahkan sepenuhnya ke main_gui.py
lewat event/queue - supaya main thread GUI tidak pernah nge-freeze.

Juga mendukung adb.exe yang dibundel langsung di dalam .exe hasil build
PyInstaller (lihat _bundled_adb_path), dengan fallback ke adb di PATH
sistem untuk mode development / kalau bundling gagal.
"""

import os
import shutil
import subprocess
import sys
from typing import List, Optional

# Windows: cegah munculnya jendela console hitam berkedip tiap kali adb
# dipanggil dari aplikasi GUI yang tidak punya console sendiri.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AdbNotFoundError(Exception):
    pass


def _bundled_adb_path() -> Optional[str]:
    """Cari adb.exe yang dibundel di dalam .exe (hasil PyInstaller --onefile),
    atau di folder vendor/platform-tools saat dijalankan sebagai script biasa
    (mode development, belum di-build)."""
    exe_name = "adb.exe" if sys.platform == "win32" else "adb"

    if getattr(sys, "frozen", False):
        # PyInstaller onefile mengekstrak data yang di-bundle ke folder
        # sementara sys._MEIPASS setiap kali aplikasi dijalankan.
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidate = os.path.join(base, "platform-tools", exe_name)
        if os.path.isfile(candidate):
            return candidate
        return None

    # Mode development: cari di ../vendor/platform-tools relatif file ini
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "vendor", "platform-tools", exe_name))
    if os.path.isfile(candidate):
        return candidate
    return None


def find_adb_path() -> str:
    """Cari adb: prioritaskan yang dibundel di dalam app, fallback ke PATH sistem."""
    bundled = _bundled_adb_path()
    if bundled:
        return bundled
    path_adb = shutil.which("adb")
    if path_adb:
        return path_adb
    raise AdbNotFoundError(
        "adb tidak ditemukan. Aplikasi ini seharusnya sudah membawa adb sendiri "
        "(bundled) - kemungkinan build-nya tidak menyertakan folder platform-tools. "
        "Alternatif: install Android Platform Tools manual dan pastikan ada di PATH."
    )


def list_devices(adb_path: str, timeout: int = 10) -> List[str]:
    """Mengembalikan list serial number perangkat berstatus 'device' (siap pakai).
    Tidak pernah raise untuk kegagalan biasa (adb belum kenal device dll) -
    cukup mengembalikan list kosong supaya alur GUI tetap bisa menampilkan
    layar 'perangkat tidak ditemukan' dengan rapi."""
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return []
    devices = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


class AdbSession:
    """Sesi audit ke satu perangkat spesifik. `serial` WAJIB sudah
    ditentukan oleh caller (GUI) sebelum membuat instance ini - kelas ini
    murni eksekusi command, tidak melakukan pemilihan device apa pun."""

    def __init__(self, serial: str, adb_path: Optional[str] = None, timeout: int = 10, verbose: bool = False):
        self.serial = serial
        self.adb_path = adb_path or find_adb_path()
        self.timeout = timeout
        self.verbose = verbose
        self._cache = {}

    def clear_cache(self):
        self._cache.clear()

    def shell(self, command: str, use_cache: bool = True) -> str:
        if use_cache and command in self._cache:
            return self._cache[command]
        try:
            result = subprocess.run(
                [self.adb_path, "-s", self.serial, "shell", command],
                capture_output=True, text=True, timeout=self.timeout,
                creationflags=CREATE_NO_WINDOW,
            )
            output = result.stdout.strip()
        except Exception:
            output = ""
        if use_cache:
            self._cache[command] = output
        return output

    def shell_first_match(self, commands: List[str]) -> str:
        for cmd in commands:
            out = self.shell(cmd)
            if out:
                return out
        return ""

    def getprop(self, key: str) -> str:
        return self.shell(f"getprop {key}")
