#!/usr/bin/env python3
"""
main_gui.py
Entry point aplikasi GUI. Semua panggilan ADB (blocking, bisa lambat)
dijalankan di background thread; main thread (GUI) hanya polling sebuah
queue.Queue tiap ~150ms lewat self.after() - ini pola standar Tkinter
untuk tetap responsif sambil kerja berat di thread lain. JANGAN sentuh
widget Tkinter/CustomTkinter dari thread selain main thread.
"""

import queue
import threading
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

import checks
import report
import scoring
import theme
from adb_utils import AdbNotFoundError, AdbSession, find_adb_path, list_devices

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CATEGORIES = [
    ("dashboard", "🏠  Dashboard"),
    ("identity", "🆔  Identitas Perangkat"),
    ("connectivity", "📶  IMEI & Konektivitas"),
    ("cpu_ram", "⚙️  CPU & RAM"),
    ("storage", "💾  Storage"),
    ("display", "🖥️  Layar"),
    ("battery", "🔋  Baterai & Daya"),
    ("thermal", "🌡️  Thermal & Pemakaian"),
    ("hardware", "🔧  Mesin & Sensor"),
    ("integrity", "🔒  Integritas Sistem"),
    ("originality", "🔍  Indikasi Originalitas"),
]
# Urutan ini HARUS sama dengan urutan `add(...)` di _worker_scan supaya
# index kategori <-> index self.sections tetap sinkron.
SECTION_KEYS = [k for k, _ in CATEGORIES if k != "dashboard"]


class StatusPill(ctk.CTkLabel):
    def __init__(self, master, status, **kwargs):
        color = theme.STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
        text = theme.STATUS_LABELS_ID.get(status, status)
        super().__init__(master, text=f"  {text}  ", fg_color=color, text_color="#0d0f14",
                          corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), **kwargs)


class IndicatorCard(ctk.CTkFrame):
    """Satu baris hasil audit, ditampilkan sebagai kartu: label + badge
    status di kanan atas, value di bawahnya, dan note (kalau ada) dalam
    teks abu-abu kecil paling bawah."""

    def __init__(self, master, row, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=10, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text=row["label"], font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=theme.TEXT_PRIMARY, anchor="w").grid(row=0, column=0, sticky="w")
        StatusPill(top, row["status"]).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(self, text=str(row["value"]), font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_PRIMARY, anchor="w", justify="left",
                     wraplength=680).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 4))

        if row.get("note"):
            ctk.CTkLabel(self, text=f"↳ {row['note']}", font=ctk.CTkFont(size=11),
                         text_color=theme.TEXT_SECONDARY, anchor="w", justify="left",
                         wraplength=680).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))
        else:
            ctk.CTkLabel(self, text="", height=6).grid(row=2, column=0)


class DevicePickerDialog(ctk.CTkToplevel):
    def __init__(self, master, devices, on_select):
        super().__init__(master)
        self.title("Pilih Perangkat")
        self.geometry("380x60")
        self.resizable(False, False)
        self.on_select = on_select

        ctk.CTkLabel(self, text=f"Ditemukan {len(devices)} perangkat, pilih salah satu:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(16, 8))
        for serial in devices:
            ctk.CTkButton(self, text=serial, command=lambda s=serial: self._pick(s)).pack(fill="x", padx=30, pady=4)
        self.geometry(f"380x{80 + 40 * len(devices)}")

        self.transient(master)
        self.grab_set()

    def _pick(self, serial):
        self.on_select(serial)
        self.destroy()


class AuditApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Android Used-Phone Audit Tool")
        self.geometry("1150x720")
        self.minsize(950, 620)
        self.configure(fg_color=theme.BG_DARK)

        self.adb = None
        self.sections = []
        self.all_rows = []
        self.summary = None
        self.device_meta = {}
        self.current_page = "dashboard"
        self.queue = queue.Queue()

        self._build_sidebar()
        self._build_main()
        self._show_connecting_screen()

        threading.Thread(target=self._worker_connect, daemon=True).start()
        self.after(150, self._poll_queue)

    # ---------------------------------------------------------- layout --
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=theme.BG_SIDEBAR)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="📱 Audit Tool", font=ctk.CTkFont(size=19, weight="bold"),
                     text_color=theme.TEXT_PRIMARY).pack(pady=(24, 2), padx=20, anchor="w")
        ctk.CTkLabel(self.sidebar, text="Cek Kelayakan HP Bekas", font=ctk.CTkFont(size=11),
                     text_color=theme.TEXT_SECONDARY).pack(pady=(0, 18), padx=20, anchor="w")

        self.nav_buttons = {}
        for key, label in CATEGORIES:
            btn = ctk.CTkButton(self.sidebar, text=label, anchor="w", fg_color="transparent",
                                 hover_color=theme.BG_CARD, text_color=theme.TEXT_PRIMARY,
                                 font=ctk.CTkFont(size=13), height=36,
                                 command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=12, pady=2)
            if key != "dashboard":
                btn.configure(state="disabled")
            self.nav_buttons[key] = btn

        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)

        self.scan_btn = ctk.CTkButton(self.sidebar, text="🔄  Scan Ulang", height=38,
                                       fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                       command=self._start_rescan, state="disabled")
        self.scan_btn.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(self.sidebar, text="Export Laporan", font=ctk.CTkFont(size=11),
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w", padx=14, pady=(4, 2))

        export_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        export_row.pack(fill="x", padx=12, pady=(0, 16))
        self.export_buttons = []
        for fmt in ("TXT", "JSON", "PDF"):
            b = ctk.CTkButton(export_row, text=fmt, width=60, height=30, state="disabled",
                               fg_color=theme.BG_CARD, hover_color=theme.ACCENT,
                               command=lambda f=fmt.lower(): self._export(f))
            b.pack(side="left", expand=True, padx=3)
            self.export_buttons.append(b)

    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

        self.status_bar = ctk.CTkLabel(self.main, text="Menghubungkan ke perangkat...", anchor="w",
                                        font=ctk.CTkFont(size=11), text_color=theme.TEXT_SECONDARY)
        self.status_bar.pack(side="bottom", fill="x", padx=24, pady=8)

        self.content = ctk.CTkScrollableFrame(self.main, fg_color=theme.BG_DARK)
        self.content.pack(fill="both", expand=True, padx=24, pady=(20, 0))
        self.content.grid_columnconfigure(0, weight=1)

    def _set_status(self, text):
        self.status_bar.configure(text=text)

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    # ------------------------------------------------------ connect flow --
    def _worker_connect(self):
        """Berjalan di background thread. Hanya boleh: hitung/cari data &
        put ke queue. TIDAK BOLEH menyentuh widget."""
        try:
            adb_path = find_adb_path()
        except AdbNotFoundError as e:
            self.queue.put(("adb_missing", str(e)))
            return
        devices = list_devices(adb_path)
        if not devices:
            self.queue.put(("no_device", adb_path))
        elif len(devices) == 1:
            self.queue.put(("device_ready", (adb_path, devices[0])))
        else:
            self.queue.put(("device_choice", (adb_path, devices)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _handle_event(self, kind, payload):
        if kind == "adb_missing":
            self._show_message_screen(
                "⚠️  ADB Tidak Ditemukan", payload, retry=True)
        elif kind == "no_device":
            self._show_message_screen(
                "📵  Perangkat Tidak Ditemukan",
                "Pastikan:\n\n"
                "  1. Kabel USB terhubung dengan baik\n"
                "  2. USB Debugging aktif (Settings > Developer Options)\n"
                "  3. Popup 'Allow USB debugging?' di HP sudah ditekan Allow\n"
                "  4. Driver USB HP sudah terinstall (khusus di Windows)\n\n"
                "Klik 'Coba Lagi' setelah memastikan hal di atas.",
                retry=True,
            )
        elif kind == "device_choice":
            adb_path, devices = payload
            self._show_message_screen("👥  Beberapa Perangkat Terdeteksi",
                                       "Silakan pilih salah satu lewat jendela yang muncul...", retry=False)
            DevicePickerDialog(self, devices, on_select=lambda s: self._on_device_selected(adb_path, s))
        elif kind == "device_ready":
            adb_path, serial = payload
            self._on_device_selected(adb_path, serial)
        elif kind == "scan_progress":
            self._set_status(payload)
        elif kind == "scan_done":
            self._on_scan_done(payload)
        elif kind == "scan_error":
            messagebox.showerror("Error", f"Gagal melakukan scan:\n{payload}")
            self._set_status("Scan gagal - coba klik Scan Ulang")
            self.scan_btn.configure(state="normal")

    def _on_device_selected(self, adb_path, serial):
        self.adb = AdbSession(serial=serial, adb_path=adb_path)
        self._set_status(f"Terhubung: {serial} • Memulai scan...")
        self._show_scanning_screen()
        threading.Thread(target=self._worker_scan, daemon=True).start()

    def _start_rescan(self):
        if not self.adb:
            return
        self.scan_btn.configure(state="disabled")
        for b in self.export_buttons:
            b.configure(state="disabled")
        self.adb.clear_cache()
        self._show_scanning_screen()
        threading.Thread(target=self._worker_scan, daemon=True).start()

    # ---------------------------------------------------------- scanning --
    def _worker_scan(self):
        """Background thread: jalankan semua fungsi check_* lalu kirim
        hasilnya lewat queue. Fungsi check_* sendiri murni logic (tidak
        menyentuh widget sama sekali), jadi aman dipanggil di sini."""
        try:
            sections = []
            all_rows = []

            def add(title, rows):
                sections.append({"title": title, "rows": rows})
                all_rows.extend(rows)

            plan = [
                ("Mengambil identitas perangkat...", "IDENTITAS PERANGKAT & REGION", checks.check_identity, ()),
                ("Mengecek IMEI & konektivitas...", "IMEI & KONEKTIVITAS", checks.check_connectivity, ()),
                ("Membaca CPU & RAM...", "SPESIFIKASI PROSESOR & MEMORI (RAM)", checks.check_cpu_ram, ()),
                ("Mengecek storage...", "KAPASITAS PENYIMPANAN (STORAGE)", checks.check_storage, ()),
                ("Mengecek layar...", "SPESIFIKASI & INTEGRITAS LAYAR", checks.check_display, ()),
            ]
            for msg, title, fn, extra_args in plan:
                self.queue.put(("scan_progress", msg))
                add(title, fn(self.adb, *extra_args))

            self.queue.put(("scan_progress", "Mengaudit baterai..."))
            batt_rows, batt_extra = checks.check_battery(self.adb)
            add("AUDIT BATERAI & DAYA", batt_rows)

            self.queue.put(("scan_progress", "Mengecek thermal..."))
            thermal_rows, _ = checks.check_thermal(self.adb, batt_extra)
            add("BEBAN THERMAL & DETEKSI PENGGUNAAN EKSTREM", thermal_rows)

            self.queue.put(("scan_progress", "Mengecek sensor & mesin..."))
            add("AUDIT MESIN & SENSOR", checks.check_hardware_sensors(self.adb))

            brand = self.adb.getprop("ro.product.brand") or ""
            self.queue.put(("scan_progress", "Mengecek integritas sistem..."))
            add("INTEGRITAS SISTEM & GARANSI (ROOT/BOOTLOADER)", checks.check_system_integrity(self.adb, brand))

            self.queue.put(("scan_progress", "Menganalisis indikasi originalitas..."))
            add("INDIKASI ORIGINALITAS KOMPONEN", checks.check_originality(self.adb, batt_extra))

            device_meta = {
                "brand": self.adb.getprop("ro.product.brand"),
                "model": self.adb.getprop("ro.product.model"),
                "serial": self.adb.serial,
                "android_version": self.adb.getprop("ro.build.version.release"),
            }

            self.queue.put(("scan_done", (sections, all_rows, device_meta)))
        except Exception as e:
            self.queue.put(("scan_error", str(e)))

    def _on_scan_done(self, payload):
        sections, all_rows, device_meta = payload
        self.sections = sections
        self.all_rows = all_rows
        self.device_meta = device_meta
        _, _, _, self.summary = scoring.compute_score(all_rows)

        self.scan_btn.configure(state="normal")
        for b in self.export_buttons:
            b.configure(state="normal")
        for btn in self.nav_buttons.values():
            btn.configure(state="normal")

        self._set_status(f"Scan selesai • {datetime.now().strftime('%H:%M:%S')} • {device_meta.get('serial', '')}")
        self._show_page("dashboard")

    # --------------------------------------------------------------- UI --
    def _show_page(self, key):
        if key != "dashboard" and not self.sections:
            return
        self.current_page = key
        for k, btn in self.nav_buttons.items():
            if btn.cget("state") != "disabled":
                btn.configure(fg_color=theme.ACCENT if k == key else "transparent")
        self._clear_content()

        if key == "dashboard":
            self._render_dashboard()
            return

        idx = SECTION_KEYS.index(key)
        if idx < len(self.sections):
            section = self.sections[idx]
            ctk.CTkLabel(self.content, text=section["title"], font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=theme.TEXT_PRIMARY, anchor="w").pack(fill="x", pady=(0, 16))
            for row in section["rows"]:
                IndicatorCard(self.content, row).pack(fill="x", pady=5)

    def _render_dashboard(self):
        if not self.summary:
            ctk.CTkLabel(self.content, text="Belum ada data. Menunggu hasil scan...",
                         text_color=theme.TEXT_SECONDARY).pack(pady=40)
            return

        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text=f"{(self.device_meta.get('brand') or '').upper()} {self.device_meta.get('model', '')}",
                     font=ctk.CTkFont(size=24, weight="bold"), text_color=theme.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(header,
                     text=f"Android {self.device_meta.get('android_version', 'N/A')} • Serial: {self.device_meta.get('serial', 'N/A')}",
                     font=ctk.CTkFont(size=13), text_color=theme.TEXT_SECONDARY).pack(anchor="w")

        score_card = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD, corner_radius=14)
        score_card.pack(fill="x", pady=(0, 20))
        grade = self.summary["grade"]
        grade_color = theme.GRADE_COLORS.get(grade, theme.ACCENT)

        inner = ctk.CTkFrame(score_card, fg_color="transparent")
        inner.pack(fill="x", padx=24, pady=24)
        ctk.CTkLabel(inner, text=grade, font=ctk.CTkFont(size=52, weight="bold"),
                     text_color=grade_color).pack(side="left", padx=(0, 24))

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(text_col, text=f"Skor Kelayakan: {self.summary['score']}/100",
                     font=ctk.CTkFont(size=17, weight="bold"), text_color=theme.TEXT_PRIMARY,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_col, text=self.summary["description"], font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY, anchor="w", wraplength=560,
                     justify="left").pack(anchor="w", pady=(4, 0))

        if self.summary["bad_flags"]:
            card = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD, corner_radius=12)
            card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(card, text="🚩 Red Flags - perlu ditanyakan ke penjual",
                         font=ctk.CTkFont(size=14, weight="bold"), text_color=theme.STATUS_COLORS["BAD"],
                         anchor="w").pack(anchor="w", padx=16, pady=(12, 4))
            for f in self.summary["bad_flags"]:
                ctk.CTkLabel(card, text=f"•  {f}", text_color=theme.TEXT_PRIMARY,
                             anchor="w").pack(anchor="w", padx=28, pady=1)
            ctk.CTkLabel(card, text="", height=8).pack()

        if self.summary["warning_flags"]:
            card = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD, corner_radius=12)
            card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(card, text="⚠️  Perlu Dikonfirmasi ke Penjual",
                         font=ctk.CTkFont(size=14, weight="bold"), text_color=theme.STATUS_COLORS["WARNING"],
                         anchor="w").pack(anchor="w", padx=16, pady=(12, 4))
            for f in self.summary["warning_flags"]:
                ctk.CTkLabel(card, text=f"•  {f}", text_color=theme.TEXT_PRIMARY,
                             anchor="w").pack(anchor="w", padx=28, pady=1)
            ctk.CTkLabel(card, text="", height=8).pack()

        ctk.CTkLabel(self.content, text="💡 Klik kategori di sidebar kiri untuk lihat detail tiap indikator.",
                     font=ctk.CTkFont(size=12), text_color=theme.TEXT_SECONDARY).pack(anchor="w", pady=(6, 20))

    def _show_connecting_screen(self):
        self._clear_content()
        ctk.CTkLabel(self.content, text="🔌 Menghubungkan ke perangkat...", font=ctk.CTkFont(size=18),
                     text_color=theme.TEXT_PRIMARY).pack(pady=60)

    def _show_scanning_screen(self):
        self._clear_content()
        ctk.CTkLabel(self.content, text="🔍 Sedang melakukan audit...", font=ctk.CTkFont(size=18),
                     text_color=theme.TEXT_PRIMARY).pack(pady=(60, 10))
        progress = ctk.CTkProgressBar(self.content, mode="indeterminate", width=320)
        progress.pack(pady=10)
        progress.start()

    def _show_message_screen(self, title, message, retry=False):
        self._clear_content()
        ctk.CTkLabel(self.content, text=title, font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=theme.TEXT_PRIMARY).pack(pady=(60, 10))
        ctk.CTkLabel(self.content, text=message, font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY, justify="left").pack(pady=(0, 20))
        if retry:
            ctk.CTkButton(self.content, text="🔄  Coba Lagi", command=self._retry_connect).pack()

    def _retry_connect(self):
        self._show_connecting_screen()
        threading.Thread(target=self._worker_connect, daemon=True).start()

    # ----------------------------------------------------------- export --
    def _export(self, fmt):
        if not self.sections:
            return
        raw_name = f"audit_{self.device_meta.get('model', 'device')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        default_name = "".join(c for c in raw_name if c.isalnum() or c in "._-")
        filetypes = {
            "txt": [("Text File", "*.txt")],
            "json": [("JSON File", "*.json")],
            "pdf": [("PDF File", "*.pdf")],
        }[fmt]
        path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", initialfile=default_name, filetypes=filetypes)
        if not path:
            return
        try:
            if fmt == "txt":
                text = report.render_plain_text(self.sections, self.summary, self.device_meta)
                report.save_txt(text, path)
            elif fmt == "json":
                report.save_json(self.sections, self.summary, self.device_meta, path)
            elif fmt == "pdf":
                ok = report.save_pdf(self.sections, self.summary, self.device_meta, path)
                if not ok:
                    messagebox.showwarning("PDF Tidak Tersedia",
                                            "Library fpdf2 tidak tersedia di build ini.\n"
                                            "Export TXT dan JSON tetap berfungsi normal.")
                    return
            messagebox.showinfo("Export Berhasil", f"Laporan disimpan ke:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Gagal", str(e))


def main():
    app = AuditApp()
    app.mainloop()


if __name__ == "__main__":
    main()
