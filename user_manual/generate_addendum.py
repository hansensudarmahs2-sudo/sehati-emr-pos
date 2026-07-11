"""
Generate Manual Operasional Addendum v1 — fitur baru (Juni 2026).

Sections:
- Cover + Daftar Isi
- Bab 1: Pengaturan Klinik (Multi-Tenant) — Owner
- Bab 2: Cetak Nota & Resume Medis — Kasir + Dokter
- Bab 3: Series Treatment Lengkap — Dokter + FO + Kasir
- Bab 4: Dropdown Pencarian Cepat (Tom Select) — semua role
- Bab 5: Flow Tambah Tindakan Setelah Bayar — Dokter + Kasir
- Bab 6: Aturan Penting & Batasan Sistem

Run:
    cd user_manual
    python3 generate_addendum.py
"""
import os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


BASE_DIR = Path(__file__).parent
SCREENSHOTS = BASE_DIR / "screenshots"
OUTPUT = BASE_DIR / "Manual_Operasional_Addendum_v1.docx"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def add_heading(doc, text, level=1, color=None):
    """Add heading with optional color override."""
    p = doc.add_heading(text, level=level)
    if color:
        for run in p.runs:
            run.font.color.rgb = color
    return p


def add_paragraph(doc, text, bold=False, italic=False, size=11):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    return p


def add_numbered_list(doc, items, start=1):
    """Add numbered list (items: list of str)."""
    for i, text in enumerate(items, start=start):
        p = doc.add_paragraph(style="List Number")
        p.add_run(text)


def add_bullet_list(doc, items):
    for text in items:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(text)


def add_screenshot(doc, filename, caption, width_inches=5.5):
    """Add screenshot with caption below."""
    path = SCREENSHOTS / filename
    if not path.exists():
        # Add placeholder text
        p = doc.add_paragraph()
        r = p.add_run(f"[Screenshot tidak ditemukan: {filename}]")
        r.italic = True
        r.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
        return
    doc.add_picture(str(path), width=Inches(width_inches))
    # Caption
    last_para = doc.paragraphs[-1]
    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(f"Gambar: {caption}")
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def add_callout_box(doc, title, body, color="amber"):
    """Add highlighted callout box (single-cell table)."""
    colors = {
        "amber": ("FEF3C7", "92400E"),
        "blue": ("DBEAFE", "1E40AF"),
        "red": ("FEE2E2", "991B1B"),
        "green": ("D1FAE5", "065F46"),
    }
    bg_hex, _ = colors.get(color, colors["amber"])

    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    cell = table.cell(0, 0)
    # Set cell shading
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), bg_hex)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)

    p1 = cell.paragraphs[0]
    r1 = p1.add_run(title)
    r1.bold = True
    r1.font.size = Pt(11)

    p2 = cell.add_paragraph()
    r2 = p2.add_run(body)
    r2.font.size = Pt(10)


def page_break(doc):
    doc.add_page_break()


# ─────────────────────────────────────────────────────────────────────────────
# Build the document
# ─────────────────────────────────────────────────────────────────────────────

def build():
    doc = Document()

    # Default font + page setup
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Margins
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # ═══════════ COVER ═══════════
    cover_p = doc.add_paragraph()
    cover_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cover_p.add_run("\n\n\n")
    r = cover_p.add_run("MANUAL OPERASIONAL")
    r.bold = True
    r.font.size = Pt(28)

    cover_sub = doc.add_paragraph()
    cover_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cover_sub.add_run("ADDENDUM v1 — Fitur Baru Juni 2026")
    r.bold = True
    r.font.size = Pt(18)
    r.font.color.rgb = RGBColor(0x05, 0x96, 0x69)

    cover_desc = doc.add_paragraph()
    cover_desc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cover_desc.add_run(
        "\n\nDokumen ini melengkapi Manual Operasional utama dengan fitur baru "
        "yang ditambahkan pada periode Mei-Juni 2026:"
    )
    r.font.size = Pt(11)

    fitur_list_p = doc.add_paragraph()
    fitur_list_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fitur_list_p.add_run(
        "Cetak Nota & Resume  •  Multi-Tenant Klinik  •  "
        "Series Treatment  •  Pencarian Dropdown  •  Flow Reopen"
    )
    r.italic = True
    r.font.size = Pt(11)

    # Footer cover
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph()
    foot_p = doc.add_paragraph()
    foot_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = foot_p.add_run("Versi 1.0 — Diterbitkan 6 Juni 2026")
    r.italic = True
    r.font.size = Pt(10)
    r = foot_p.add_run("\nUntuk Internal Klinik")
    r.italic = True
    r.font.size = Pt(10)

    page_break(doc)

    # ═══════════ DAFTAR ISI ═══════════
    add_heading(doc, "Daftar Isi", level=1)
    toc_items = [
        ("Bab 1", "Pengaturan Klinik (Multi-Tenant)"),
        ("Bab 2", "Cetak Nota & Resume Medis"),
        ("Bab 3", "Series Treatment Lengkap"),
        ("Bab 4", "Dropdown Pencarian Cepat"),
        ("Bab 5", "Flow Tambah Tindakan Setelah Bayar"),
        ("Bab 6", "Aturan Penting & Batasan Sistem"),
        ("Lampiran", "Daftar Screenshot Referensi"),
    ]
    for tag, title in toc_items:
        p = doc.add_paragraph()
        r = p.add_run(f"{tag}: {title}")
        r.font.size = Pt(12)
    page_break(doc)

    # ═══════════ BAB 1: SETTINGS KLINIK ═══════════
    add_heading(doc, "Bab 1 — Pengaturan Klinik (Multi-Tenant)", level=1)
    add_paragraph(doc,
        "Sistem sekarang mendukung pengaturan identitas klinik secara dinamis. "
        "Nama klinik, alamat, telepon, NPWP, dan logo dapat diubah kapan saja oleh "
        "Owner tanpa perlu mengubah kode program. Semua tampilan (topbar, nota, "
        "resume medis) akan otomatis ikut menggunakan identitas yang baru.")
    add_paragraph(doc, "Akses Fitur Ini", bold=True, size=12)
    add_bullet_list(doc, [
        "Role yang bisa akses: Owner dan Superadmin.",
        "Menu: sidebar kiri → Settings → Klinik.",
        "URL langsung: /web/settings/klinik",
    ])

    add_heading(doc, "1.1 Edit Identitas Klinik", level=2)
    add_paragraph(doc,
        "Form settings menampilkan field nama klinik, alamat lengkap, telepon, "
        "email, NPWP, dan footer untuk nota cetak. Setiap field bisa diisi atau "
        "dikosongkan sesuai kebutuhan.")
    add_screenshot(doc, "01_settings_klinik_form.png",
        "Form Settings Klinik — semua field bisa diisi sesuai kebutuhan klinik.")

    add_heading(doc, "1.2 Upload Logo Klinik", level=2)
    add_paragraph(doc,
        "Logo klinik dapat di-upload dalam format PNG dengan ukuran maksimal "
        "500 KB. Logo akan ditampilkan di topbar aplikasi dan di header nota cetak.")
    add_callout_box(doc, "Tips Logo",
        "Pakai PNG transparan dengan resolusi minimal 300x300 px supaya tetap "
        "tajam saat dicetak. Hindari logo dengan latar putih full karena akan "
        "berbeda dengan background topbar abu-abu sistem.", color="blue")
    add_screenshot(doc, "02_settings_logo_upload.png",
        "Bagian upload logo dengan preview logo yang sedang aktif.")

    add_heading(doc, "1.3 Perubahan Tampil di Topbar", level=2)
    add_paragraph(doc,
        "Setelah Bapak/Ibu menyimpan perubahan, refresh browser sekali. "
        "Nama klinik baru akan langsung muncul di topbar atas, sidebar, halaman "
        "login, dan di semua nota cetak.")
    add_screenshot(doc, "03_topbar_after_change.png",
        "Topbar setelah identitas klinik diperbarui — nama klinik aktif "
        "ditampilkan di pojok kiri atas.")
    page_break(doc)

    # ═══════════ BAB 2: PRINT MODULE ═══════════
    add_heading(doc, "Bab 2 — Cetak Nota & Resume Medis", level=1)
    add_paragraph(doc,
        "Sistem menyediakan dua jenis cetakan: Nota Pembayaran (untuk Kasir) "
        "dan Resume Medis SOAP (untuk Dokter). Keduanya tersedia dalam dua ukuran "
        "kertas: A5 (untuk printer kantor biasa) dan Thermal 80mm (untuk printer "
        "struk POS).")

    add_heading(doc, "2.1 Cetak Nota Pembayaran (Kasir)", level=2)
    add_paragraph(doc,
        "Di halaman tagihan kasir, setelah pembayaran berhasil diproses, "
        "muncul tombol Cetak Nota A5 dan Cetak Nota Thermal. Tombol bisa "
        "diklik untuk menampilkan preview print di browser.")
    add_screenshot(doc, "04_kasir_tagihan_normal.png",
        "Halaman tagihan kasir dengan rincian tindakan + produk + total.")

    add_heading(doc, "2.2 Preview Nota A5", level=2)
    add_paragraph(doc,
        "Format A5 cocok untuk printer kantor biasa. Berisi: header klinik "
        "lengkap (nama, alamat, telepon, NPWP), nomor transaksi, daftar tindakan, "
        "daftar produk, ringkasan biaya, dan tanda tangan kasir.")
    add_screenshot(doc, "05_kasir_nota_a5_preview.png",
        "Preview nota A5 di print dialog browser.")

    add_heading(doc, "2.3 Preview Nota Thermal 80mm", level=2)
    add_paragraph(doc,
        "Format Thermal 80mm cocok untuk printer struk POS. Layout lebih "
        "ringkas, font lebih besar, dan optimized untuk kertas struk.")
    add_screenshot(doc, "06_kasir_nota_thermal_preview.png",
        "Preview nota thermal 80mm untuk printer POS.")

    add_heading(doc, "2.4 Auto-Print Setelah Pembayaran Lunas", level=2)
    add_paragraph(doc,
        "Sistem otomatis menampilkan halaman konfirmasi pembayaran sukses + "
        "auto-trigger print dialog 1 detik setelah halaman muncul. Kasir tinggal "
        "klik Print di dialog browser. Ini menghemat waktu Kasir tidak perlu "
        "navigasi balik untuk cetak nota.")
    add_screenshot(doc, "07_kasir_confirm_autoprint.png",
        "Halaman konfirmasi pembayaran lunas dengan auto-print aktif.")

    add_heading(doc, "2.5 Card 'Tidak Ada Tagihan' (Rp 0)", level=2)
    add_paragraph(doc,
        "Khusus untuk Series Treatment sesi 2 dan seterusnya yang sudah dibayar "
        "di sesi 1: kasir akan melihat card khusus 'Tidak Ada Tagihan' dengan "
        "tombol Selesaikan & Cetak Nota. Tombol ini tidak menerima input nominal "
        "(bypass otomatis) karena memang tidak ada tagihan.")
    add_screenshot(doc, "08_kasir_rp0_card.png",
        "Card 'Tidak Ada Tagihan' untuk series treatment sesi lanjutan.")

    add_heading(doc, "2.6 Cetak Resume Medis (Dokter)", level=2)
    add_paragraph(doc,
        "Dokter dapat mencetak Resume Medis (SOAP) per kunjungan dari halaman "
        "Riwayat Pasien. Setiap entry SOAP punya tombol Cetak Resume di pojok "
        "kanan. Format: A5 atau Thermal 80mm.")
    add_screenshot(doc, "09_dokter_riwayat_cetak_btn.png",
        "Tombol Cetak Resume di halaman Riwayat Pasien per entry SOAP.")
    add_screenshot(doc, "10_dokter_soap_a5_preview.png",
        "Preview Resume Medis SOAP A5 — berisi anamnesa, pemeriksaan, "
        "diagnosa, terapi, dan rencana lanjutan.")
    add_screenshot(doc, "11_dokter_soap_thermal_preview.png",
        "Preview Resume Medis SOAP Thermal — versi ringkas untuk printer struk.")
    page_break(doc)

    # ═══════════ BAB 3: SERIES TREATMENT ═══════════
    add_heading(doc, "Bab 3 — Series Treatment Lengkap", level=1)
    add_paragraph(doc,
        "Series Treatment adalah treatment yang dilakukan beberapa sesi terjadwal "
        "(contoh: paket 5x Facial Acne, paket 10x Laser Toning). Sistem mendukung "
        "alur lengkap mulai dari setup harga paket, pemilihan saat SOAP, "
        "pembayaran sekaligus, sampai eksekusi sesi lanjutan.")

    add_callout_box(doc, "Model Penagihan Series Treatment",
        "Pasien membayar paket lengkap (N sesi × harga_paket) di sesi 1. "
        "Sesi 2 sampai sesi N tidak ada tagihan tambahan — pasien tinggal "
        "datang dan eksekusi tindakan. Tidak ada masa kadaluarsa (no expiry).",
        color="green")

    add_heading(doc, "3.1 Setup Harga Paket (Owner)", level=2)
    add_paragraph(doc,
        "Owner pertama-tama harus set field Harga Paket Series di Master "
        "Treatment. Field ini opsional — kalau kosong, sistem akan pakai harga "
        "normal dikalikan jumlah sesi. Kalau diisi, sistem akan pakai harga "
        "paket (biasanya lebih murah dari harga normal × jumlah).")
    add_screenshot(doc, "12_master_treatment_harga_paket.png",
        "Form Master Treatment dengan field 'Harga Paket Series' (border amber).")

    add_heading(doc, "3.2 Dokter Centang Series saat SOAP", level=2)
    add_paragraph(doc,
        "Saat input SOAP, dokter centang checkbox 'Series' di baris tindakan "
        "yang akan jadi series, lalu isi jumlah sesi (misal: 5). Sistem akan "
        "otomatis: (1) bikin 1 KunjunganTindakan untuk sesi 1 hari ini, (2) bikin "
        "5 - 1 = 4 rencana series untuk sesi 2-5 dengan status PENDING.")
    add_screenshot(doc, "13_dokter_soap_series_checkbox.png",
        "SOAP form bagian Rekomendasi Tindakan — checkbox Series + input "
        "jumlah sesi.")

    add_heading(doc, "3.3 Kasir Tagih Paket di Sesi 1", level=2)
    add_paragraph(doc,
        "Saat kasir buka halaman tagihan untuk pasien yang punya tindakan "
        "series, sistem otomatis hitung: harga_paket × jumlah_sesi. Pasien bayar "
        "sekali, dan sisa sesi sudah lunas.")
    add_screenshot(doc, "14_kasir_tagihan_paket_sesi1.png",
        "Tagihan kasir sesi 1 series — total = jumlah_sesi × harga_paket.")

    add_heading(doc, "3.4 FO Booking Sesi Berikutnya", level=2)
    add_paragraph(doc,
        "Saat pasien datang untuk sesi 2 (atau seterusnya), FO buka Cari Pasien. "
        "Sistem otomatis cek apakah pasien punya rencana series PENDING. Kalau "
        "ada, di dropdown +Antrian muncul section amber 'Lanjut Series' dengan "
        "tombol 'Sesi N/Total — Nama Tindakan'. FO klik tombol itu, sistem akan "
        "bikin kunjungan baru hari ini dengan status ANTRI_TREATMENT (langsung "
        "ke Ruang Tindakan, tanpa konsultasi dokter dulu).")
    add_screenshot(doc, "15_fo_search_lanjut_series.png",
        "Dropdown +Antrian dengan section 'Lanjut Series' aktif.")

    add_heading(doc, "3.5 Detail Pasien — Lihat Rencana Aktif", level=2)
    add_paragraph(doc,
        "Halaman Detail Pasien menampilkan card 'Rencana Series Aktif' yang "
        "list semua series yang masih PENDING dengan tombol 'Pakai Sesi N' untuk "
        "shortcut booking.")
    add_screenshot(doc, "16_fo_pasien_detail_rencana.png",
        "Card 'Rencana Series Aktif' di halaman Detail Pasien.")
    add_screenshot(doc, "17_pakai_sesi_button.png",
        "Tombol 'Pakai Sesi N' close-up.", width_inches=3.0)
    page_break(doc)

    # ═══════════ BAB 4: SEARCHABLE DROPDOWN ═══════════
    add_heading(doc, "Bab 4 — Dropdown Pencarian Cepat", level=1)
    add_paragraph(doc,
        "Semua dropdown produk dan tindakan di sistem sekarang dilengkapi fitur "
        "pencarian cepat (Tom Select). Tidak perlu scroll panjang lagi untuk "
        "cari obat/tindakan tertentu — tinggal ketik nama atau kode, dan daftar "
        "akan otomatis ter-filter.")

    add_heading(doc, "4.1 Cara Menggunakan", level=2)
    add_numbered_list(doc, [
        "Klik dropdown — daftar lengkap muncul.",
        "Mulai ketik 2-3 huruf nama produk/tindakan.",
        "Daftar otomatis ter-filter sesuai pencarian.",
        "Klik item yang dimaksud — dropdown menutup dengan pilihan aktif.",
    ])

    add_screenshot(doc, "18_dropdown_closed.png",
        "Dropdown dalam keadaan tertutup dengan placeholder text.")
    add_screenshot(doc, "19_dropdown_open_typing.png",
        "Dropdown terbuka dengan input pencarian aktif — daftar ter-filter.")
    add_screenshot(doc, "20_dropdown_selected.png",
        "Dropdown setelah item terpilih.")

    add_heading(doc, "4.2 Lokasi Dropdown Searchable", level=2)
    add_bullet_list(doc, [
        "SOAP Dokter — pilih Tindakan dan Resep Produk.",
        "FO Beli Produk — pilih produk yang dibeli pasien.",
        "Perawat Upsell — pilih tindakan atau produk tambahan saat eksekusi.",
        "Master Treatment & Master Produk — saat tambah komponen.",
    ])

    add_callout_box(doc, "Tips Cepat",
        "Untuk obat dengan nama mirip (contoh: AMOXICILLIN 250 vs 500), "
        "ketik nomor dosis dulu — sistem akan langsung sortir ke atas. "
        "Untuk tindakan, ketik kategori (laser, facial, peeling) untuk "
        "lihat semua tindakan dalam kategori.", color="blue")
    page_break(doc)

    # ═══════════ BAB 5: FLOW TAMBAH TINDAKAN ═══════════
    add_heading(doc, "Bab 5 — Flow Tambah Tindakan Setelah Bayar", level=1)
    add_paragraph(doc,
        "Skenario yang sering terjadi: pasien konsultasi, awalnya hanya beli "
        "obat (tanpa tindakan), sudah bayar di kasir, lalu di tengah jalan "
        "berubah pikiran ingin tambah tindakan. Sistem mendukung alur ini "
        "dengan beberapa aturan untuk menjaga akuntabilitas.")

    add_heading(doc, "5.1 Flow Lengkap Tambah Tindakan", level=2)
    add_numbered_list(doc, [
        "Pasien konsul → dokter resep produk saja → pasien antri bayar.",
        "Kasir bayar produk → transaksi pertama tercatat.",
        "Pasien berubah pikiran → kembali ke dokter untuk Ubah Konsul.",
        "Dokter buka antrian → klik Ubah Konsul (boleh walau status ANTRI_OBAT).",
        "Dokter tambah tindakan baru → simpan SOAP.",
        "Sistem otomatis ubah status pasien dari ANTRI_OBAT/ANTRI_BAYAR ke ANTRI_TREATMENT.",
        "Pasien muncul di antrian Ruang Tindakan → perawat eksekusi tindakan.",
        "Setelah selesai, sistem ubah status ke ANTRI_BAYAR.",
        "Kasir buka tagihan → muncul banner 'Tagihan Tambahan' dengan rincian items baru saja.",
        "Kasir proses pembayaran → transaksi kedua tercatat terpisah dari transaksi pertama.",
    ])

    add_callout_box(doc, "PENTING — Cap 1x Reopen",
        "Sistem hanya mengizinkan MAKSIMAL 1 KALI penambahan tindakan setelah "
        "pembayaran pertama. Setelah 2 transaksi terbentuk di kunjungan yang "
        "sama, sistem akan MENOLAK penambahan tindakan lebih lanjut dengan "
        "pesan error: 'Kunjungan ini sudah 2x dibayar. Untuk tindakan tambahan, "
        "daftarkan kunjungan baru untuk pasien hari ini via FO.' Ini bertujuan "
        "menjaga audit trail tetap rapi dan mencegah eskalasi tidak terkontrol.",
        color="red")

    add_heading(doc, "5.2 Kapan Harus Daftarkan Kunjungan Baru?", level=2)
    add_paragraph(doc,
        "Ada 2 situasi yang mengharuskan FO mendaftarkan kunjungan baru, "
        "bukan reopen:")
    add_bullet_list(doc, [
        "Kunjungan sudah 2 kali dibayar (limit cap reopen tercapai).",
        "Pasien datang di hari yang berbeda dari kunjungan asli.",
    ])
    add_paragraph(doc,
        "Cara daftarkan kunjungan baru: FO buka Cari Pasien → klik +Antrian "
        "di hasil pencarian → pilih jenis antrian (Konsultasi/Tindakan/Bayar).")

    add_heading(doc, "5.3 Banner 'Tagihan Tambahan' di Kasir", level=2)
    add_paragraph(doc,
        "Halaman tagihan kasir akan menampilkan banner amber besar di atas card "
        "pasien kalau kunjungan ini reopen. Banner berisi link ke nota transaksi "
        "sebelumnya untuk referensi. Items yang ditampilkan hanya items BARU "
        "(tindakan/resep yang ditambahkan setelah pembayaran terakhir).")
    page_break(doc)

    # ═══════════ BAB 6: ATURAN PENTING ═══════════
    add_heading(doc, "Bab 6 — Aturan Penting & Batasan Sistem", level=1)

    add_heading(doc, "6.1 Series Treatment", level=2)
    add_bullet_list(doc, [
        "Harga paket SETARA dengan harga normal × jumlah sesi kalau field kosong.",
        "Disarankan harga paket lebih murah dari harga normal × jumlah, sebagai insentif.",
        "Tidak ada masa kadaluarsa — sesi PENDING tetap valid sampai dipakai.",
        "Sesi tidak boleh dipindahkan ke pasien lain.",
        "Kasir tidak boleh override harga paket (gunakan diskon di kasir kalau perlu).",
    ])

    add_heading(doc, "6.2 Reopen Kunjungan", level=2)
    add_bullet_list(doc, [
        "Maksimal 1 kali reopen per kunjungan (2 transaksi total).",
        "Dokter tetap bisa edit SOAP (anamnesa/diagnosa) kapan saja, asal tidak menambah tindakan baru.",
        "Status COMPLETED dan BATAL tetap tidak bisa diubah.",
    ])

    add_heading(doc, "6.3 Multi-Tenant Klinik", level=2)
    add_bullet_list(doc, [
        "Hanya Owner dan Superadmin yang bisa ubah Settings Klinik.",
        "Logo maksimal 500 KB, format PNG.",
        "Perubahan langsung berlaku setelah disimpan, tidak perlu restart.",
    ])

    add_heading(doc, "6.4 Cetak Nota & Resume", level=2)
    add_bullet_list(doc, [
        "Format A5: cocok untuk printer kantor biasa (Epson, HP, Canon).",
        "Format Thermal 80mm: cocok untuk printer struk POS (XPrinter, Epson TM-T82).",
        "Auto-print: 1 detik delay setelah halaman konfirmasi muncul.",
        "Cetak ulang nota lama: buka halaman tagihan kunjungan terkait → klik Cetak Nota.",
    ])

    add_heading(doc, "6.5 Searchable Dropdown", level=2)
    add_bullet_list(doc, [
        "Pencarian case-insensitive (huruf besar/kecil sama).",
        "Pencarian fuzzy: ketik sebagian nama, sistem cari yang mirip.",
        "Untuk produk: bisa cari berdasarkan nama atau kode produk.",
        "Untuk tindakan: bisa cari berdasarkan nama tindakan atau singkatannya.",
    ])
    page_break(doc)

    # ═══════════ LAMPIRAN ═══════════
    add_heading(doc, "Lampiran — Daftar Screenshot Referensi", level=1)
    add_paragraph(doc, "Total: 20 gambar dalam dokumen ini.")

    daftar = [
        ("01", "settings_klinik_form.png", "Form Settings Klinik full"),
        ("02", "settings_logo_upload.png", "Bagian upload logo"),
        ("03", "topbar_after_change.png", "Topbar setelah ubah nama klinik"),
        ("04", "kasir_tagihan_normal.png", "Halaman tagihan kasir normal"),
        ("05", "kasir_nota_a5_preview.png", "Preview nota A5"),
        ("06", "kasir_nota_thermal_preview.png", "Preview nota Thermal 80mm"),
        ("07", "kasir_confirm_autoprint.png", "Confirmation page setelah bayar"),
        ("08", "kasir_rp0_card.png", "Card 'Tidak Ada Tagihan' Rp 0"),
        ("09", "dokter_riwayat_cetak_btn.png", "Tombol Cetak Resume di Riwayat"),
        ("10", "dokter_soap_a5_preview.png", "Preview Resume SOAP A5"),
        ("11", "dokter_soap_thermal_preview.png", "Preview Resume SOAP Thermal"),
        ("12", "master_treatment_harga_paket.png", "Form Master Treatment Harga Paket"),
        ("13", "dokter_soap_series_checkbox.png", "SOAP form checkbox Series"),
        ("14", "kasir_tagihan_paket_sesi1.png", "Tagihan paket sesi 1"),
        ("15", "fo_search_lanjut_series.png", "FO dropdown Lanjut Series"),
        ("16", "fo_pasien_detail_rencana.png", "Detail Pasien card Rencana Aktif"),
        ("17", "pakai_sesi_button.png", "Tombol Pakai Sesi N close-up"),
        ("18", "dropdown_closed.png", "Dropdown searchable closed"),
        ("19", "dropdown_open_typing.png", "Dropdown searchable open + typing"),
        ("20", "dropdown_selected.png", "Dropdown searchable selected"),
    ]
    for num, fn, desc in daftar:
        p = doc.add_paragraph()
        r = p.add_run(f"{num}. {fn}")
        r.bold = True
        r.font.size = Pt(10)
        r = p.add_run(f" — {desc}")
        r.font.size = Pt(10)

    # ─────────────────────────────────────────────────────────────────────────
    # SAVE
    # ─────────────────────────────────────────────────────────────────────────
    doc.save(OUTPUT)
    print(f"\n✓ Dokumen disimpan ke: {OUTPUT}")
    print(f"  Ukuran: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build()
