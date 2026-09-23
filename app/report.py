#!/usr/bin/env python3
"""
report.py (versi GUI)
Beda dengan versi CLI: tidak ada rendering terminal/ANSI di sini (itu
sudah jadi tugas widget IndicatorCard di main_gui.py). Modul ini murni
menghasilkan representasi laporan untuk disimpan ke file, dan semua
fungsi save_* menerima path file LENGKAP (hasil pilihan user lewat save
dialog), bukan folder+basename seperti versi CLI.
"""

import json
import os
from datetime import datetime
from typing import Dict, List


def render_plain_text(sections: List[Dict], summary: Dict, device_meta: Dict) -> str:
    lines = []
    lines.append("=" * 62)
    lines.append("  LAPORAN AUDIT KELAYAKAN HP ANDROID BEKAS")
    lines.append("=" * 62)
    lines.append(f"Perangkat : {device_meta.get('brand', 'N/A')} {device_meta.get('model', 'N/A')}")
    lines.append(f"Serial    : {device_meta.get('serial', 'N/A')}")
    lines.append(f"Dibuat    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for i, section in enumerate(sections, 1):
        lines.append(f"\n[{i}] {section['title']}")
        for row in section["rows"]:
            lines.append(f"  - {row['label']:<32}: {row['value']} [{row['status']}]")
            if row.get("note"):
                lines.append(f"      -> {row['note']}")

    lines.append("\n" + "=" * 62)
    lines.append("  RINGKASAN & SKOR KELAYAKAN")
    lines.append("=" * 62)
    lines.append(f"  Skor: {summary['score']}/100  |  Grade: {summary['grade']}")
    lines.append(f"  {summary['description']}")
    if summary["bad_flags"]:
        lines.append(f"\n  Red flags (BAD): {', '.join(summary['bad_flags'])}")
    if summary["warning_flags"]:
        lines.append(f"  Perlu dikonfirmasi (WARNING): {', '.join(summary['warning_flags'])}")
    lines.append("\n" + "=" * 62)

    return "\n".join(lines)


def save_txt(text: str, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def save_json(sections: List[Dict], summary: Dict, device_meta: Dict, path: str) -> str:
    data = {
        "generated_at": datetime.now().isoformat(),
        "device": device_meta,
        "sections": sections,
        "summary": summary,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def save_pdf(sections: List[Dict], summary: Dict, device_meta: Dict, path: str) -> bool:
    """Return True kalau berhasil, False kalau library fpdf2 tidak tersedia
    di build ini (GUI yang memanggil bertanggung jawab menampilkan pesan)."""
    try:
        from fpdf import FPDF
    except ImportError:
        return False

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Laporan Audit Kelayakan HP Android Bekas", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Dibuat: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    model = device_meta.get("model", "N/A")
    brand = device_meta.get("brand", "N/A")
    pdf.cell(0, 6, f"Perangkat: {brand} {model}", ln=True)
    pdf.ln(4)

    status_colors = {"GOOD": (0, 140, 0), "WARNING": (200, 140, 0), "BAD": (200, 0, 0), "INFO": (0, 100, 160)}

    for section in sections:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, section["title"], ln=True)
        pdf.set_font("Helvetica", "", 9)
        for row in section["rows"]:
            r, g, b = status_colors.get(row["status"], (0, 0, 0))
            pdf.set_text_color(r, g, b)
            text = f"- {row['label']}: {row['value']} [{row['status']}]"
            pdf.multi_cell(0, 5, text)
            if row.get("note"):
                pdf.set_text_color(90, 90, 90)
                pdf.multi_cell(0, 5, f"    {row['note']}")
        pdf.ln(2)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Ringkasan & Skor Kelayakan", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Skor: {summary['score']}/100  |  Grade: {summary['grade']}\n{summary['description']}")
    if summary["bad_flags"]:
        pdf.set_text_color(200, 0, 0)
        pdf.multi_cell(0, 6, f"Red flags: {', '.join(summary['bad_flags'])}")
    if summary["warning_flags"]:
        pdf.set_text_color(200, 140, 0)
        pdf.multi_cell(0, 6, f"Perlu dikonfirmasi: {', '.join(summary['warning_flags'])}")

    pdf.output(path)
    return True
