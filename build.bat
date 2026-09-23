@echo off
setlocal

echo ============================================================
echo   Build Android Used-Phone Audit Tool (Windows .exe)
echo ============================================================
echo.

if not exist "vendor\platform-tools\adb.exe" (
    echo [!] adb.exe belum ada di vendor\platform-tools\
    echo.
    echo     Download dulu dari:
    echo     https://developer.android.com/tools/releases/platform-tools
    echo.
    echo     Extract, lalu copy adb.exe + AdbWinApi.dll + AdbWinUsbApi.dll
    echo     ke folder vendor\platform-tools\ sebelum build.
    echo     Lihat vendor\platform-tools\BACA_DULU.txt untuk detail.
    echo.
    pause
    exit /b 1
)

echo [1/3] Install dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [!] Gagal install dependencies. Pastikan Python dan pip terinstall.
    pause
    exit /b 1
)

echo.
echo [2/3] Building .exe dengan PyInstaller (bisa makan waktu beberapa menit)...
pyinstaller app.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [!] Build gagal, cek pesan error di atas.
    pause
    exit /b 1
)

echo.
echo [3/3] Selesai!
echo.
echo File hasil build ada di: dist\AndroidAuditTool.exe
echo Tinggal double-click untuk jalankan - tidak perlu install apa pun lagi.
echo.
pause
