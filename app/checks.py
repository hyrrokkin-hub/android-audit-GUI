#!/usr/bin/env python3
"""
checks.py
Semua logika pengecekan/audit perangkat Android. Setiap fungsi check_*
mengembalikan list of dict dengan struktur:
    {
        "id": str,             # id stabil (snake_case, Inggris) - JANGAN diubah,
                                # dipakai scoring.py & konsumen JSON eksternal untuk
                                # mengenali indikator ini secara program, independen
                                # dari teks label yang ditampilkan ke user.
        "label": str,           # nama indikator yang ditampilkan ke user (Indonesia)
        "value": str,           # nilai yang ditampilkan
        "status": str,          # GOOD | WARNING | BAD | INFO
        "note": str (optional)  # catatan tambahan
    }

PENTING: "id" dan "label" sengaja dipisah. Kalau suatu saat teks "label"
diubah/diperbaiki/diterjemahkan, "id" harus TETAP SAMA supaya scoring.py
(yang mencocokkan bobot lewat id) tidak diam-diam rusak. Kalau menambah
indikator baru, kasih id baru yang unik & deskriptif (snake_case).

Didesain generik lintas-brand: setiap properti dicoba lewat beberapa
path/command fallback (Samsung, Xiaomi/MIUI, Oppo/ColorOS, Vivo/FuntouchOS,
Pixel/AOSP, dll) supaya tidak error kalau satu vendor tidak menyediakan
properti tertentu.
"""

import re
from typing import Dict, List

from adb_utils import AdbSession

STATUS_GOOD = "GOOD"
STATUS_WARNING = "WARNING"
STATUS_BAD = "BAD"
STATUS_INFO = "INFO"


def _row(id_, label, value, status=STATUS_INFO, note=""):
    return {"id": id_, "label": label, "value": value, "status": status, "note": note}


def _to_float(text, default=None):
    try:
        m = re.search(r"-?\d+\.?\d*", text)
        return float(m.group(0)) if m else default
    except Exception:
        return default


# ==================================================================
# 1. IDENTITAS PERANGKAT & REGION
# ==================================================================
def check_identity(adb: AdbSession) -> List[Dict]:
    rows = []
    brand = adb.getprop("ro.product.brand") or adb.getprop("ro.product.manufacturer")
    manufacturer = adb.getprop("ro.product.manufacturer")
    model = adb.getprop("ro.product.model")
    marketing_name = adb.shell_first_match([
        "getprop ro.product.marketing_name",       # sebagian OEM
        "getprop ro.config.marketing_name",
        "getprop ro.oppo.market.name",              # Oppo/Realme
        "getprop ro.vendor.oplus.market.name",       # Oplus
    ])
    device_codename = adb.getprop("ro.product.device")
    android_ver = adb.getprop("ro.build.version.release")
    sdk_level = adb.getprop("ro.build.version.sdk")
    patch = adb.getprop("ro.build.version.security_patch")
    build_id = adb.getprop("ro.build.display.id")
    build_type = adb.getprop("ro.build.type")
    fingerprint = adb.getprop("ro.build.fingerprint")
    serial = adb.getprop("ro.boot.serialno") or adb.getprop("ro.serialno")

    rows.append(_row("brand_manufacturer", "Brand / Manufacturer",
                      f"{brand.upper() if brand else 'N/A'} ({manufacturer or 'N/A'})", STATUS_GOOD))
    rows.append(_row("model", "Model", model or "N/A", STATUS_GOOD))
    if marketing_name:
        rows.append(_row("marketing_name", "Nama Marketing", marketing_name, STATUS_INFO))
    rows.append(_row("device_codename", "Codename Internal", device_codename or "N/A", STATUS_INFO))
    rows.append(_row("serial_number", "Serial Number", serial or "N/A", STATUS_GOOD if serial else STATUS_WARNING))
    rows.append(_row("android_version", "Versi Android", f"{android_ver or 'N/A'} (SDK {sdk_level or 'N/A'})", STATUS_GOOD))

    # Security patch age check (kasar: hanya cek formatnya ada / tidak terlalu tua)
    if patch:
        status = STATUS_GOOD
        note = ""
        m = re.match(r"(\d{4})-(\d{2})-\d{2}", patch)
        if m:
            year = int(m.group(1))
            if year <= 2020:
                status, note = STATUS_WARNING, "Patch keamanan sudah cukup lama, cek apakah masih dapat update"
        rows.append(_row("security_patch", "Security Patch Level", patch, status, note))
    else:
        rows.append(_row("security_patch", "Security Patch Level", "N/A", STATUS_WARNING))

    rows.append(_row("build_id", "Build ID", build_id or "N/A", STATUS_INFO))

    # Build type: user = release resmi, userdebug/eng = build developer (mencurigakan di unit retail)
    if build_type:
        if build_type == "user":
            rows.append(_row("build_type", "Build Type", build_type, STATUS_GOOD, "Build resmi retail"))
        else:
            rows.append(_row("build_type", "Build Type", build_type, STATUS_BAD,
                              "Build developer/debug - tidak wajar di unit retail, indikasi custom firmware"))

    # Region / CSC hanya relevan untuk Samsung, brand lain pakai carrier/region generik
    if brand and "samsung" in brand.lower():
        csc = adb.getprop("ro.csc.sales_code")
        if csc:
            if csc.upper() == "XID":
                rows.append(_row("csc_region", "Kode Region/CSC", csc, STATUS_GOOD, "Resmi SEIN Indonesia"))
            else:
                rows.append(_row("csc_region", "Kode Region/CSC", csc, STATUS_WARNING, "Unit Inter/Non-SEIN - cek legalitas & garansi"))
    else:
        region = adb.shell_first_match([
            "getprop ro.build.target_region",
            "getprop persist.sys.country",
            "getprop ro.product.locale.region",
        ])
        if region:
            rows.append(_row("csc_region", "Region/Country Code", region, STATUS_INFO))

    rows.append(_row("build_fingerprint", "Build Fingerprint", fingerprint or "N/A", STATUS_INFO))
    return rows


# ==================================================================
# 2. IMEI & KONEKTIVITAS
# ==================================================================
def check_connectivity(adb: AdbSession) -> List[Dict]:
    rows = []
    imei1 = adb.shell("service call iphonesubinfo 1 | cut -c 52-66 | tr -d '.[:space:]'")
    imei1 = re.sub(r"[^0-9]", "", imei1) if imei1 else ""
    if imei1:
        rows.append(_row("imei_slot1", "IMEI Slot 1", imei1, STATUS_GOOD))
    else:
        rows.append(_row("imei_slot1", "IMEI Slot 1", "Tidak terbaca otomatis", STATUS_WARNING,
                          "Android 10+ membatasi akses IMEI via ADB. Cek manual via *#06# atau Settings > About Phone."))
    rows.append(_row("imei_slot2", "IMEI Slot 2 (dual SIM)", "Cek manual", STATUS_INFO,
                      "Pembacaan otomatis slot 2 tidak reliable lintas vendor, verifikasi manual dianjurkan."))

    baseband = adb.getprop("gsm.version.baseband") or adb.getprop("ro.baseband")
    rows.append(_row("baseband_version", "Baseband/Modem Version", baseband or "N/A", STATUS_GOOD if baseband else STATUS_WARNING))

    wifi_mac = adb.shell_first_match([
        "cat /sys/class/net/wlan0/address",
        "settings get secure wifi_mac_address",
    ])
    rows.append(_row("wifi_mac", "WiFi MAC Address", wifi_mac or "N/A", STATUS_GOOD if wifi_mac else STATUS_WARNING))

    bt_mac = adb.shell_first_match([
        "settings get secure bluetooth_address",
        "getprop ro.boot.btmacaddr",
    ])
    rows.append(_row("bluetooth_mac", "Bluetooth MAC Address", bt_mac or "N/A", STATUS_INFO))

    sim_state = adb.shell_first_match([
        "getprop gsm.sim.state",
    ])
    if sim_state:
        rows.append(_row("sim_state", "Status SIM", sim_state, STATUS_INFO))

    return rows


# ==================================================================
# 3. CPU & RAM
# ==================================================================
def check_cpu_ram(adb: AdbSession) -> List[Dict]:
    rows = []
    platform = adb.getprop("ro.board.platform")
    hardware = adb.getprop("ro.hardware")
    abi = adb.getprop("ro.product.cpu.abi")
    cpu_cores = adb.shell("nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo")

    rows.append(_row("chipset_platform", "Chipset/Platform", f"{(hardware or 'N/A').upper()} / {platform or 'N/A'}", STATUS_GOOD))
    rows.append(_row("cpu_abi", "CPU ABI", abi or "N/A", STATUS_INFO))
    if cpu_cores and cpu_cores.strip().isdigit():
        rows.append(_row("cpu_core_count", "Jumlah Core CPU", f"{cpu_cores.strip()} core", STATUS_GOOD))
    else:
        rows.append(_row("cpu_core_count", "Jumlah Core CPU", "N/A", STATUS_WARNING))

    mem_info = adb.shell("cat /proc/meminfo")
    mem_total = re.search(r"MemTotal:\s*(\d+)\s*kB", mem_info)
    mem_avail = re.search(r"MemAvailable:\s*(\d+)\s*kB", mem_info)
    if mem_total:
        total_gb = round(int(mem_total.group(1)) / (1024 * 1024), 2)
        avail_txt = ""
        if mem_avail:
            avail_gb = round(int(mem_avail.group(1)) / (1024 * 1024), 2)
            avail_txt = f" (Tersedia: {avail_gb} GB)"
        rows.append(_row("ram_capacity", "Kapasitas RAM", f"~{total_gb} GB{avail_txt}", STATUS_GOOD))
    else:
        rows.append(_row("ram_capacity", "Kapasitas RAM", "N/A", STATUS_WARNING))

    swap_info = adb.shell("cat /proc/swaps 2>/dev/null | tail -n +2")
    if swap_info:
        rows.append(_row("swap_zram", "Swap/ZRAM", "Aktif", STATUS_INFO, swap_info.splitlines()[0] if swap_info else ""))

    return rows


# ==================================================================
# 4. STORAGE
# ==================================================================
def check_storage(adb: AdbSession) -> List[Dict]:
    rows = []
    df_data = adb.shell("df -k /data | tail -n 1")
    parts = df_data.split()
    if len(parts) >= 4:
        try:
            total_gb = round(int(parts[1]) / (1024 * 1024), 1)
            used_gb = round(int(parts[2]) / (1024 * 1024), 1)
            free_gb = round(int(parts[3]) / (1024 * 1024), 1)
            approx = ("64 GB" if total_gb < 70 else
                      "128 GB" if total_gb < 140 else
                      "256 GB" if total_gb < 280 else
                      "512 GB" if total_gb < 550 else
                      "1 TB" if total_gb < 1100 else f"{total_gb} GB")
            rows.append(_row("storage_total", "Total Storage (approx.)", approx, STATUS_GOOD, f"Partisi /data: {total_gb} GB"))
            used_pct = (used_gb / total_gb * 100) if total_gb else 0
            status = STATUS_GOOD if used_pct < 90 else STATUS_WARNING
            rows.append(_row("storage_used_free", "Terpakai / Sisa", f"Terpakai {used_gb} GB | Sisa {free_gb} GB", status))
        except (ValueError, ZeroDivisionError):
            rows.append(_row("storage_raw", "Storage Raw Info", df_data or "N/A", STATUS_WARNING))
    else:
        rows.append(_row("storage_raw", "Storage Info", "N/A - gagal membaca df", STATUS_WARNING))
    return rows


# ==================================================================
# 5. LAYAR (DISPLAY)
# ==================================================================
def check_display(adb: AdbSession) -> List[Dict]:
    rows = []
    wm_size = adb.shell("wm size")
    wm_density = adb.shell("wm density")
    res_match = re.search(r"Physical size:\s*(\d+x\d+)", wm_size)
    dpi_match = re.search(r"Physical density:\s*(\d+)", wm_density)

    rows.append(_row("screen_resolution", "Resolusi Layar", res_match.group(1) if res_match else "N/A", STATUS_GOOD))
    rows.append(_row("screen_density", "Kerapatan (DPI)", f"{dpi_match.group(1)} DPI" if dpi_match else "N/A", STATUS_INFO))

    refresh_info = adb.shell_first_match([
        "dumpsys display | grep -iE 'refreshRate|peakRefreshRate' | head -n 5",
        "cat /sys/class/graphics/fb0/dynamic_fps 2>/dev/null",
        "dumpsys SurfaceFlinger | grep -i fps | head -n 3",
    ])
    high_refresh = bool(re.search(r"(90|90\.0|120|120\.0|144|144\.0)", refresh_info))
    if high_refresh:
        rate = re.search(r"(90|120|144)", refresh_info).group(1)
        rows.append(_row("refresh_rate", "Refresh Rate", f"{rate} Hz terdeteksi", STATUS_GOOD,
                          "Pastikan opsi high refresh rate aktif di Settings"))
    else:
        rows.append(_row("refresh_rate", "Refresh Rate", "60 Hz / tidak terdeteksi tinggi", STATUS_INFO,
                          "Sebagian device tidak expose info ini via ADB, cek manual di Settings > Display"))

    # Info panel mentah untuk cross-check originalitas manual
    panel_info = adb.shell_first_match([
        "dumpsys SurfaceFlinger | grep -i 'mDisplayName\\|panel'",
        "cat /sys/class/lcd/panel/panel_name 2>/dev/null",
        "cat /sys/class/graphics/fb0/msm_fb_panel_info 2>/dev/null | head -n 3",
    ])
    if panel_info:
        rows.append(_row("panel_info_raw", "Info Panel (raw)", panel_info.splitlines()[0][:80], STATUS_INFO,
                          "Bandingkan manual dengan spek resmi jika ingin cek indikasi layar pernah diganti"))

    rows.append(_row("physical_screen_check", "Cek Fisik Layar", "Manual", STATUS_INFO,
                      "Dead pixel, burn-in, touch response harap dicek langsung"))
    return rows


# ==================================================================
# 6. BATERAI & DAYA
# ==================================================================
def check_battery(adb: AdbSession) -> Dict:
    """Return (rows, extra) dimana extra dipakai scoring.py"""
    rows = []
    extra = {}
    batt = adb.shell("dumpsys battery")

    level = re.search(r"level:\s*(\d+)", batt)
    voltage = re.search(r"voltage:\s*(\d+)", batt)
    temp = re.search(r"temperature:\s*(\d+)", batt)
    health = re.search(r"health:\s*(\d+)", batt)
    technology = re.search(r"technology:\s*(.+)", batt)
    status_charge = re.search(r"status:\s*(\d+)", batt)
    present = re.search(r"present:\s*(true|false)", batt)

    if level:
        lv = int(level.group(1))
        rows.append(_row("battery_level", "Sisa Baterai", f"{lv}%", STATUS_GOOD))
    if present:
        rows.append(_row("battery_present", "Baterai Terdeteksi", present.group(1),
                          STATUS_GOOD if present.group(1) == "true" else STATUS_BAD))
    if technology:
        rows.append(_row("battery_technology", "Jenis Baterai", technology.group(1).strip(), STATUS_GOOD))

    if temp:
        temp_c = float(temp.group(1)) / 10.0
        status = STATUS_GOOD if temp_c < 38.0 else STATUS_WARNING if temp_c <= 42.0 else STATUS_BAD
        rows.append(_row("battery_temperature", "Suhu Baterai", f"{temp_c:.1f} °C", status))
        extra["batt_temp"] = temp_c

    if voltage:
        volt_v = float(voltage.group(1)) / 1000.0
        status = STATUS_GOOD if 3.6 <= volt_v <= 4.4 else STATUS_WARNING
        rows.append(_row("battery_voltage", "Tegangan Baterai", f"{volt_v:.2f} V", status))

    health_map = {
        "1": ("Unknown", STATUS_WARNING),
        "2": ("Good / Sehat", STATUS_GOOD),
        "3": ("Overheat", STATUS_BAD),
        "4": ("Dead / Rusak", STATUS_BAD),
        "5": ("Over Voltage", STATUS_BAD),
        "6": ("Unspecified Failure", STATUS_BAD),
        "7": ("Cold", STATUS_WARNING),
    }
    h_code = health.group(1) if health else "1"
    h_label, h_status = health_map.get(h_code, ("Normal", STATUS_GOOD))
    rows.append(_row("battery_health_status", "Status Kesehatan (sistem)", h_label, h_status))

    # Cycle count - fallback multi vendor
    cycle_raw = adb.shell_first_match([
        "cat /sys/class/power_supply/battery/cycle_count",
        "cat /sys/class/power_supply/bms/cycle_count",          # Xiaomi/Qualcomm bms
        "cat /sys/class/power_supply/battery/batt_cycle",
        "dumpsys battery | grep -i cycle",
    ])
    cycle_num = None
    if cycle_raw:
        m = re.search(r"\d+", cycle_raw)
        if m:
            cycle_num = int(m.group(0))
            status = STATUS_GOOD if cycle_num < 300 else STATUS_WARNING if cycle_num <= 500 else STATUS_BAD
            rows.append(_row("battery_cycle_count", "Siklus Pengisian (Cycle Count)", f"{cycle_num}x", status))
            extra["cycle_count"] = cycle_num
    if cycle_num is None:
        rows.append(_row("battery_cycle_count", "Siklus Pengisian (Cycle Count)", "N/A", STATUS_INFO,
                          "Tidak semua vendor mengekspos cycle count via ADB tanpa root"))

    # Battery wear: design capacity vs full capacity -> health percentage riil
    charge_full = adb.shell_first_match([
        "cat /sys/class/power_supply/battery/charge_full",
        "cat /sys/class/power_supply/bms/charge_full",
    ])
    charge_full_design = adb.shell_first_match([
        "cat /sys/class/power_supply/battery/charge_full_design",
        "cat /sys/class/power_supply/bms/charge_full_design",
    ])
    if charge_full and charge_full_design:
        try:
            full = float(re.search(r"\d+", charge_full).group(0))
            design = float(re.search(r"\d+", charge_full_design).group(0))
            if design > 0:
                wear_pct = round((full / design) * 100, 1)
                status = STATUS_GOOD if wear_pct >= 85 else STATUS_WARNING if wear_pct >= 70 else STATUS_BAD
                rows.append(_row("battery_wear_pct", "Estimasi Kesehatan Baterai (wear)", f"{wear_pct}% dari kapasitas awal", status,
                                  "Dihitung dari charge_full vs charge_full_design"))
                extra["battery_wear_pct"] = wear_pct
        except Exception:
            pass
    else:
        rows.append(_row("battery_wear_pct", "Estimasi Kesehatan Baterai (wear)", "N/A", STATUS_INFO,
                          "sysfs charge_full/charge_full_design tidak terbaca (dibatasi OEM/butuh root)"))

    extra["is_charging"] = bool(status_charge and status_charge.group(1) == "2")
    return rows, extra


# ==================================================================
# 7. THERMAL & PEMAKAIAN
# ==================================================================
def check_thermal(adb: AdbSession, batt_extra: Dict) -> Dict:
    rows = []
    extra = {}
    uptime = adb.shell("uptime")
    rows.append(_row("uptime", "Waktu Nyala (Uptime)", uptime or "N/A", STATUS_INFO))

    boot_reason = adb.shell_first_match([
        "getprop ro.boot.bootreason",
        "getprop sys.boot.reason",
    ])
    if boot_reason:
        status = STATUS_GOOD if boot_reason.lower() in ("reboot", "reboot,normal", "reboot,adb") else STATUS_INFO
        rows.append(_row("last_boot_reason", "Alasan Reboot Terakhir", boot_reason, status))

    thermal_raw = adb.shell_first_match([
        "cat /sys/class/thermal/thermal_zone0/temp",
        "dumpsys thermalservice | grep -i 'mValue' | head -n 1",
    ])
    cpu_temp = None
    if thermal_raw:
        m = re.search(r"-?\d+\.?\d*", thermal_raw)
        if m:
            val = float(m.group(0))
            cpu_temp = val / 1000.0 if val > 1000 else val
            status = STATUS_GOOD if cpu_temp < 40.0 else STATUS_WARNING if cpu_temp <= 48.0 else STATUS_BAD
            rows.append(_row("cpu_temperature", "Suhu Core CPU", f"{cpu_temp:.1f} °C", status))
            extra["cpu_temp"] = cpu_temp

    if batt_extra.get("is_charging") and batt_extra.get("batt_temp", 0) > 38.0:
        rows.append(_row("charging_heat_warning", "Peringatan Suhu saat Cas", "Suhu tinggi saat charging", STATUS_BAD,
                          "Indikasi dipakai berat sambil dicas"))
    else:
        rows.append(_row("charging_heat_warning", "Peringatan Suhu saat Cas", "Normal", STATUS_GOOD))

    max_freq = adb.shell("cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null")
    cur_freq = adb.shell("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null")
    throttling = False
    if max_freq.strip().isdigit() and cur_freq.strip().isdigit():
        if int(cur_freq) < (int(max_freq) * 0.5):
            throttling = True
    rows.append(_row(
        "cpu_throttling", "CPU Throttling",
        "Terindikasi throttling" if throttling else "Normal, tidak throttling",
        STATUS_WARNING if throttling else STATUS_GOOD,
        "Frekuensi CPU dipangkas signifikan - indikasi bekas pemakaian berat/overheat" if throttling else ""
    ))
    extra["throttling"] = throttling
    return rows, extra


# ==================================================================
# 8. MESIN, SENSOR & PMIC
# ==================================================================
def check_hardware_sensors(adb: AdbSession) -> List[Dict]:
    rows = []
    cpu_online = adb.shell("cat /sys/devices/system/cpu/online 2>/dev/null")
    if cpu_online:
        rows.append(_row("cpu_cores_active", "Core CPU Aktif", cpu_online, STATUS_GOOD,
                          "Semua core seharusnya terdaftar aktif di sini"))

    sensor_list = adb.shell("dumpsys sensorservice | grep -iE '^\\s*[0-9]+\\)' | head -n 40")
    if not sensor_list:
        sensor_list = adb.shell("dumpsys sensorservice | grep -i 'type=' | head -n 40")

    expected = ["accelerometer", "gyroscope", "proximity", "light", "magnetic"]
    found = []
    if sensor_list:
        low = sensor_list.lower()
        for s in expected:
            if s in low:
                found.append(s)
        rows.append(_row("sensors_detected", "Sensor Terdeteksi",
                          f"{len(found)}/{len(expected)} sensor umum ditemukan ({', '.join(found) if found else '-'})",
                          STATUS_GOOD if len(found) >= 4 else STATUS_WARNING,
                          "Sensor umum yang tidak terdeteksi bisa indikasi modul rusak/tidak lengkap (perlu cek manual)"))
    else:
        rows.append(_row("sensors_detected", "Sensor Terdeteksi", "N/A - gagal membaca sensorservice", STATUS_WARNING))

    current_now = adb.shell_first_match([
        "dumpsys battery | grep -i current",
        "cat /sys/class/power_supply/battery/current_now 2>/dev/null",
    ])
    if current_now:
        rows.append(_row("pmic_current", "Arus PMIC (current_now)", current_now.strip()[:60], STATUS_INFO))

    return rows


# ==================================================================
# 9. INTEGRITAS SISTEM & ROOT/KNOX
# ==================================================================
def check_system_integrity(adb: AdbSession, brand: str) -> List[Dict]:
    rows = []
    bootstate = adb.getprop("ro.boot.verifiedbootstate")
    flash_locked = adb.getprop("ro.boot.flash.locked")
    tags = adb.getprop("ro.build.tags")

    if bootstate:
        status = STATUS_GOOD if bootstate.lower() == "green" else STATUS_BAD
        rows.append(_row("verified_boot_state", "Verified Boot State", bootstate, status,
                          "green = sistem resmi & utuh" if status == STATUS_GOOD else "Bootloader unlocked/custom - berisiko!"))
    elif flash_locked:
        status = STATUS_GOOD if flash_locked == "1" else STATUS_BAD
        rows.append(_row("bootloader_lock_state", "Bootloader Lock State", "Locked" if flash_locked == "1" else "Unlocked", status))
    else:
        rows.append(_row("bootloader_lock_state", "Status Bootloader", "N/A - tidak terbaca", STATUS_WARNING))

    if tags:
        status = STATUS_GOOD if "release-keys" in tags else STATUS_BAD
        rows.append(_row("build_tags", "Build Tags", tags, status,
                          "release-keys = firmware resmi" if status == STATUS_GOOD else "test-keys terdeteksi - indikasi custom ROM"))

    # Knox khusus Samsung
    if brand and "samsung" in brand.lower():
        knox = adb.shell_first_match([
            "getprop ro.boot.warranty_bit",
            "getprop ro.warranty_bit",
        ])
        if knox:
            if knox.strip() == "0":
                rows.append(_row("knox_warranty_bit", "Samsung Knox Warranty Bit", "0x0", STATUS_GOOD,
                                  "Pabrikan murni, fitur Knox/Samsung Pass utuh"))
            else:
                rows.append(_row("knox_warranty_bit", "Samsung Knox Warranty Bit", f"0x{knox.strip()}", STATUS_BAD,
                                  "Knox tripped - pernah root/custom, sebagian fitur mati permanen"))

    # Root detection generik (berlaku semua brand)
    su_check = adb.shell_first_match([
        "which su",
        "ls /system/bin/su 2>/dev/null",
        "ls /system/xbin/su 2>/dev/null",
    ])
    magisk_check = adb.shell("pm list packages | grep -i magisk")
    if su_check or magisk_check:
        rows.append(_row("root_detection", "Deteksi Root", "Terindikasi rooted (su binary/Magisk ditemukan)", STATUS_BAD))
    else:
        rows.append(_row("root_detection", "Deteksi Root", "Tidak terdeteksi root", STATUS_GOOD))

    return rows


# ==================================================================
# 10. INDIKASI ORIGINALITAS KOMPONEN (offline, informational)
# ==================================================================
def check_originality(adb: AdbSession, batt_extra: Dict) -> List[Dict]:
    """
    Bukan alat forensik pasti - hanya menyandingkan beberapa properti sistem
    untuk mencari KETIDAKKONSISTENAN yang umum terjadi pada unit clone/rebadge
    atau komponen (baterai/layar) yang sudah diganti dengan part aftermarket.
    Semua hasil di sini WAJIB dianggap sebagai indikasi awal, bukan vonis final.
    """
    rows = []

    brand = (adb.getprop("ro.product.brand") or "").lower()
    manufacturer = (adb.getprop("ro.product.manufacturer") or "").lower()
    fingerprint = (adb.getprop("ro.build.fingerprint") or "").lower()

    # 10.1 Konsistensi brand vs manufacturer vs fingerprint
    if brand and manufacturer:
        if brand not in fingerprint and manufacturer not in fingerprint:
            rows.append(_row("brand_fingerprint_consistency", "Konsistensi Brand vs Fingerprint", "Tidak cocok", STATUS_BAD,
                              f"Brand '{brand}'/manufacturer '{manufacturer}' tidak muncul di build fingerprint - "
                              "indikasi unit rebadge/clone atau firmware sudah diubah"))
        else:
            rows.append(_row("brand_fingerprint_consistency", "Konsistensi Brand vs Fingerprint", "Cocok", STATUS_GOOD))

    # 10.2 Baterai: cycle count sangat rendah tapi uptime/usia perangkat lama -> mungkin baterai sudah diganti
    cycle = batt_extra.get("cycle_count")
    wear = batt_extra.get("battery_wear_pct")
    if cycle is not None and wear is not None:
        if cycle < 30 and wear < 90:
            rows.append(_row("battery_replacement_indicator", "Indikasi Baterai Diganti", "Mencurigakan", STATUS_WARNING,
                              f"Cycle count sangat rendah ({cycle}x) tapi wear sudah {wear}% - "
                              "tidak wajar, cek fisik baterai (segel, part number, tanggal produksi)"))
        elif cycle < 30 and wear >= 95:
            rows.append(_row("battery_replacement_indicator", "Indikasi Baterai Diganti",
                              "Kemungkinan baterai baru/original rendah pemakaian", STATUS_INFO))
        else:
            rows.append(_row("battery_replacement_indicator", "Indikasi Baterai Diganti", "Tidak ada anomali signifikan", STATUS_GOOD))
    else:
        rows.append(_row("battery_replacement_indicator", "Indikasi Baterai Diganti", "Data tidak cukup untuk dianalisis", STATUS_INFO))

    # 10.3 Kamera - daftar modul untuk cross-check manual
    camera_info = adb.shell_first_match([
        "dumpsys media.camera | grep -iE 'Facing|Camera ID' | head -n 10",
        "getprop | grep -i camera",
    ])
    if camera_info:
        rows.append(_row("camera_module_detected", "Modul Kamera Terdeteksi",
                          camera_info.splitlines()[0][:80] if camera_info else "N/A", STATUS_INFO,
                          "Bandingkan jumlah & posisi kamera dengan spek resmi model ini"))

    # 10.4 Panel layar - sudah dilaporkan di check_display, di sini cukup catatan silang
    rows.append(_row("originality_note", "Catatan Originalitas", "Hasil di atas adalah indikasi awal berbasis data sistem",
                      STATUS_INFO,
                      "Untuk kepastian, tetap lakukan cek fisik (segel, warna part, kualitas sambungan) "
                      "dan cocokkan IMEI resmi via *#06# dengan dus/invoice"))

    return rows
