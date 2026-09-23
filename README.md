# Android Used-Phone Audit Tool (GUI - Windows)

*[Baca dalam Bahasa Indonesia](README.id.md)*

A desktop GUI version of the Android Used-Phone Audit Tool, Windows-only.
The end result is a single portable `AndroidAuditTool.exe` file — the user
just double-clicks it, no need to install Python, ADB, or anything else
(everything is bundled inside the .exe).

> This is a separate project from the CLI version (`android-audit-tool`).
> The check logic (`checks.py`, `scoring.py`) is reused as-is from the
> already-tested CLI version; this project just wraps it in a GUI and
> packages it as an .exe.

> **Note:** as with the CLI tool, all in-app labels, the audit output,
> and code comments are in Indonesian (this tool targets the Indonesian
> used-phone market). This README is in English for discoverability.

## ⚠️ Important limitation

The source code in this repo is **not yet a ready-made `.exe`**. You need
to run `build.bat` once on a Windows machine to produce it yourself,
because:
1. A Windows `.exe` has to be built on Windows (no cross-compiling from
   Linux/Mac)
2. `adb.exe` is an official Google binary you need to download yourself
   from the official source (see installation steps below)

Once built, the resulting `.exe` is portable — you can copy/share it to
other Windows machines without rebuilding.

## Features

- **Modern GUI** (dark theme) with a sidebar navigation per category,
  similar to typical desktop diagnostic tools
- **Same 10 audit categories** as the CLI version: identity, IMEI,
  CPU/RAM, storage, display, battery (+ estimated wear%), thermal,
  sensors, system integrity (root/bootloader/Knox), originality
  indicators
- **Dashboard** with an A–D condition score/grade + red flag list
- **Background scanning** (doesn't freeze the GUI) with a progress
  indicator
- **Auto device detection**, with a picker dialog if more than one phone
  is connected
- **Export** to TXT / JSON / PDF via a save-file dialog
- **adb bundled inside the .exe** — end users don't need to install
  anything

## How to Build

### Step 1: Download the official adb binaries

1. Go to https://developer.android.com/tools/releases/platform-tools
2. Download "SDK Platform-Tools for Windows", extract it
3. Copy these 3 files into this project's `vendor/platform-tools/` folder:
   - `adb.exe`
   - `AdbWinApi.dll`
   - `AdbWinUsbApi.dll`

(Full details in `vendor/platform-tools/BACA_DULU.txt`)

### Step 2: Build

Open Command Prompt in this project's folder, then run:

```bat
build.bat
```

This script automatically installs dependencies (`customtkinter`,
`pyinstaller`, `fpdf2`) via pip, then builds the `.exe` with PyInstaller.
The result is at `dist\AndroidAuditTool.exe`.

### Try it without building first (development mode)

For quick development/testing without waiting for the build process:

```bat
pip install -r requirements.txt
python app\main_gui.py
```

(In this mode adb is still auto-detected from `vendor/platform-tools/`,
so you still need step 1 above first.)

## Using the App

1. Connect the phone via USB, with USB Debugging enabled (same as the
   CLI version — see "Preparing the phone" below)
2. Open `AndroidAuditTool.exe`
3. The app automatically detects and scans the connected device
4. Check the Dashboard (A–D score) or click a category in the sidebar
   for indicator-level detail
5. Click the TXT/JSON/PDF buttons in the sidebar to export the report

## Preparing the phone to be audited

1. Enable **Developer Options**: Settings > About Phone > tap "Build
   Number" 7 times
2. Go to Developer Options > enable **USB Debugging**
3. Connect the phone via USB
4. Tap **Allow** when the "Allow USB debugging?" popup appears
5. If Windows doesn't recognize the device, install the phone vendor's
   official USB driver, or use the
   [Universal ADB Driver](https://adb.clockworkmod.com/)

## Project Structure

```
android-audit-gui/
├── app/
│   ├── main_gui.py      # GUI entry point, all layout & event handling
│   ├── adb_utils.py       # ADB connection (no blocking input, finds bundled adb)
│   ├── checks.py            # 10 audit category logic (reused from CLI version)
│   ├── scoring.py             # score & grade calculation
│   ├── report.py                # plain-text report rendering + json/pdf export
│   └── theme.py                   # color palette & visual constants
├── vendor/platform-tools/           # place adb.exe + dlls here before building
├── app.spec                           # PyInstaller build spec
├── build.bat                            # one-click build script
└── requirements.txt
```

## Design notes

- **Logic (checks.py/scoring.py) is separated from the GUI**: easier to
  test/maintain independently, and stays consistent with the CLI version
- **Every ADB call runs on a background thread**: ADB shell commands are
  blocking and sometimes slow — running them on the main thread would
  freeze the GUI on every scan. The main thread only polls results from
  a queue every 150ms
- **The GUI version of `adb_utils.py` never uses `input()`**: unlike the
  CLI version, which can block waiting for the user to pick a device in
  the terminal, a GUI must stay responsive at all times — device
  selection becomes a dialog window instead of a terminal prompt

## License

MIT — feel free to modify as needed.
