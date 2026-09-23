# Android Used-Phone Audit Tool (GUI - Windows)

*[Read in English](README.md)*

Versi desktop GUI dari Android Used-Phone Audit Tool, khusus Windows.
Hasil akhirnya satu file portable `AndroidAuditTool.exe` — user tinggal
double-click, tidak perlu install Python, ADB, atau apa pun lagi (semua
sudah dibundel di dalam .exe-nya).

> Ini proyek terpisah dari versi CLI (`android-audit-tool`). Logic
> pengecekan (`checks.py`, `scoring.py`) sama persis/reuse dari versi CLI
> yang sudah teruji, cuma dibungkus GUI dan dipaketkan jadi .exe di sini.

## ⚠️ Keterbatasan penting

Source code di repo ini **belum berupa file `.exe` jadi**. Kamu perlu
menjalankan `build.bat` sekali di komputer Windows untuk menghasilkannya
sendiri — ini karena:
1. `.exe` Windows harus di-build di Windows (tidak bisa cross-compile dari
   Linux/Mac)
2. `adb.exe` adalah binary resmi Google yang perlu kamu download sendiri
   dari sumber resminya (lihat langkah instalasi di bawah)

Setelah build sekali, hasil `.exe`-nya portable — bisa disalin/dibagikan
ke komputer Windows lain tanpa perlu build ulang.

## Fitur

- **GUI modern** (dark theme) dengan sidebar navigasi per kategori,
  mirip tool diagnostik desktop pada umumnya
- **10 kategori audit** yang sama dengan versi CLI: identitas, IMEI,
  CPU/RAM, storage, layar, baterai (+ estimasi wear%), thermal, sensor,
  integritas sistem (root/bootloader/Knox), indikasi originalitas
- **Dashboard** dengan skor & grade kelayakan (A–D) + daftar red flag
- **Scan berjalan di background** (tidak nge-freeze GUI) dengan progress
  indicator
- **Auto-deteksi device**, dengan dialog pilihan kalau lebih dari satu
  HP terhubung
- **Export** ke TXT / JSON / PDF lewat dialog save file
- **adb dibundel di dalam .exe** — user akhir tidak perlu install apa pun

## Cara Build

### Langkah 1: Download adb resmi

1. Buka https://developer.android.com/tools/releases/platform-tools
2. Download "SDK Platform-Tools for Windows", extract
3. Copy 3 file berikut ke folder `vendor/platform-tools/` di project ini:
   - `adb.exe`
   - `AdbWinApi.dll`
   - `AdbWinUsbApi.dll`

(Detail lebih lengkap ada di `vendor/platform-tools/BACA_DULU.txt`)

### Langkah 2: Build

Buka Command Prompt di folder project ini, lalu jalankan:

```bat
build.bat
```

Script ini otomatis: install dependency (`customtkinter`, `pyinstaller`,
`fpdf2`) lewat pip, lalu build `.exe` lewat PyInstaller. Hasilnya ada di
`dist\AndroidAuditTool.exe`.

### Coba tanpa build dulu (mode development)

Untuk development/testing cepat tanpa nunggu proses build:

```bat
pip install -r requirements.txt
python app\main_gui.py
```

(Di mode ini adb dicari otomatis dari `vendor/platform-tools/`, jadi
tetap perlu langkah 1 di atas dulu.)

## Cara Pakai Aplikasi

1. Sambungkan HP ke laptop via USB, USB Debugging aktif (sama seperti
   versi CLI — lihat bagian "Persiapan HP" di bawah)
2. Buka `AndroidAuditTool.exe`
3. Aplikasi otomatis mendeteksi & scan device yang terhubung
4. Lihat hasil di Dashboard (skor A–D) atau klik kategori di sidebar
   untuk detail tiap indikator
5. Klik tombol TXT/JSON/PDF di sidebar untuk export laporan

## Persiapan HP yang akan diaudit

1. Aktifkan **Developer Options**: Settings > About Phone > tap "Build
   Number" 7x
2. Masuk Developer Options > aktifkan **USB Debugging**
3. Sambungkan HP via USB
4. Tekan **Allow** saat muncul popup "Allow USB debugging?" di HP
5. Kalau Windows belum kenal device-nya, install driver USB resmi
   vendor HP tersebut, atau pakai
   [Universal ADB Driver](https://adb.clockworkmod.com/)

## Struktur Proyek

```
android-audit-gui/
├── app/
│   ├── main_gui.py      # entry point GUI, semua layout & event handling
│   ├── adb_utils.py       # koneksi ADB (tanpa blocking input, cari adb bundled)
│   ├── checks.py            # logic 10 kategori audit (reuse dari versi CLI)
│   ├── scoring.py             # perhitungan skor & grade
│   ├── report.py                # render laporan txt + save json/pdf
│   └── theme.py                   # palet warna & konstanta tampilan
├── vendor/platform-tools/           # taruh adb.exe + dll di sini sebelum build
├── app.spec                           # PyInstaller build spec
├── build.bat                            # script build sekali klik
└── requirements.txt
```

## Kenapa arsitekturnya begini?

- **Logic (checks.py/scoring.py) dipisah dari GUI**: supaya gampang
  dites & di-maintain terpisah, dan tetap konsisten dengan versi CLI
- **Semua panggilan ADB jalan di background thread**: ADB shell command
  itu blocking & kadang lambat — kalau dijalankan di main thread, GUI
  akan freeze/nge-hang setiap kali scan. Main thread cuma polling hasil
  lewat queue tiap 150ms
- **`adb_utils.py` versi GUI tidak pernah pakai `input()`**: beda dari
  versi CLI yang boleh nge-block nunggu user pilih device di terminal,
  GUI harus selalu responsif — pemilihan device jadi dialog window,
  bukan prompt terminal

## Lisensi

MIT — silakan modifikasi sesuai kebutuhan.
