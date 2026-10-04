"""Paket KLINIS ber-pseudonim untuk Oracle / Council AI.

Tahap A: profil, kunjungan, SOAP, diagnosa, peta gabung.
Tahap B (2026-10-04): tindakan, resep, racikan (+bahan), followup.

PERAN SEHATI DI SINI
--------------------
Sehati **tidak menganalisa**. Ia menyediakan bahan mentah yang siap diolah;
analisisnya di `data_analyst` lalu Council AI (ada medical officer di sana).
Lihat memori proyek `sehati-ekosistem-analisa`.

TERPISAH DARI finance_pack
--------------------------
Hak akses dan jalur keluarnya berbeda. `medical_soap_raw` sudah DIKELUARKAN dari
finance pack (`FINANCE_PACK_EXCLUDE`) — SOAP medis tidak lagi ikut keluar setiap
hari di dalam paket bernama "finance".

⚠ PAKET INI **PSEUDONIM**, BUKAN ANONIM — jangan pernah menyebutnya anonim.
  [Keputusan dr. Hansen] teks bebas dikirim APA ADANYA, karena itu bahan analisis
  paling kaya. Konsekuensinya harus dipegang, bukan dilupakan: anamnesa sering
  memuat nama orang ("diantar suaminya Pak Budi"), nomor telepon, alamat.
  Menyamarkan KOLOM tapi mengirim teks utuh berarti identitas hanya BERPINDAH
  dari kolom ke kalimat. Penyamaran kolom MENGURANGI paparan, tidak menghapusnya.

  Karena itu paket klinis TETAP data rahasia, setara backup database:
  terenkripsi age saat diam, folder drop terbatas, tidak boleh masuk git/cloud/
  folder tersinkron. Di klinik kecil, diagnosa langka + tanggal sudah cukup untuk
  mengenali orang.

⚠ EKSPOR INI MENULIS KE DB. Tidak seperti ekspor finance yang murni baca, ekspor
  klinis membuat baris `pasien_pseudonim` untuk pasien yang belum punya `pid`
  (get-or-create). Disengaja: alurnya tidak menyentuh pendaftaran sama sekali.
"""
from __future__ import annotations

import secrets
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# ======================================================================
# PAGAR: kolom yang TIDAK BOLEH pernah muncul di paket klinis
# ======================================================================
# Dicek per-KUNCI dengan kecocokan PERSIS, bukan substring — `nama` dilarang,
# tapi `nama_dokter`, `nama_staf_pelaksana` dan `nama_snapshot` (nama diagnosa)
# justru DIMINTA dr. Hansen dan harus lolos.
#
# Pagar ini berjalan pada SETIAP baris SETIAP berkas sebelum ditulis. Kalau suatu
# hari ada yang menambah kolom ke sebuah query tanpa memikirkan privasinya,
# ekspornya BERHENTI — bukan diam-diam mengirim nama pasien ke pihak luar.
KOLOM_TERLARANG = frozenset({
    "id_pasien",          # kunci internal; paket memakai `pid`
    "nama", "nama_pasien",
    "no_rm", "nomor_rm",
    "nomor_ktp", "nomor_ktp_lama", "nik", "nik_pasien",
    "alamat",
    "nomor_telepon", "telepon", "no_hp",
    "email_address", "email",
    "no_member",
    "tgl_lahir",          # pengidentifikasi kuat — paket memakai UMUR
    "peresep_luar_nama",  # dokter LUAR klinik: pihak ketiga, tak dibutuhkan analisis
    "peresep_luar_asal",
})


# ======================================================================
# PAGAR KEDUA: kolom UANG tidak boleh ada di paket klinis
# ======================================================================
# [Keputusan dr. Hansen 2026-10-04, saat Tahap B] Paket klinis dipisahkan dari
# finance_pack justru karena hak akses dan jalur keluarnya berbeda. Kalau harga
# ikut di sini, pemisahan itu batal: paket klinis jadi punya nilai komersial dan
# alasan untuk membatasinya jadi kabur.
#
# Ini ditulis sebagai PAGAR, bukan komentar, karena komentar tidak menahan siapa
# pun. `kunjungan_racikan` dan `kunjungan_racikan_bahan` memang punya kolom harga
# tepat di sebelah kolom dosis — menambahkannya ke SELECT hanya butuh satu kata,
# dan tidak akan terlihat salah saat ditulis.
#
# Kecocokan PERSIS seperti KOLOM_TERLARANG, supaya `total_qty` atau `subtotal_bahan_
# dosis` (andai suatu hari ada) tidak ikut tertangkap tanpa alasan.
KOLOM_UANG = frozenset({
    "harga", "harga_satuan", "harga_jual", "harga_beli",
    "subtotal", "subtotal_bahan", "biaya_racik", "total",
    "hpp", "hpp_satuan", "hpp_per_unit",
    "diskon", "diskon_nominal", "diskon_persen",
    "pajak", "pajak_nominal", "pajak_persen",
    "komisi", "komisi_nominal", "komisi_value",
    "grand_total", "total_bayar", "nominal",
})


class KolomUangError(RuntimeError):
    """Kolom uang lolos ke paket klinis. Ekspor DIBATALKAN."""


class KolomTerlarangError(RuntimeError):
    """Kolom identitas lolos ke paket klinis. Ekspor DIBATALKAN."""


def pagar_kolom(nama_dataset: str, rows: list[dict]) -> list[dict]:
    """Tolak seluruh ekspor kalau ada kolom identitas. Return rows kalau bersih.

    Memeriksa baris PERTAMA saja tidak cukup kalau baris punya kunci berbeda,
    jadi seluruh kunci yang pernah muncul dikumpulkan.
    """
    kunci: set[str] = set()
    for r in rows:
        kunci |= set(r.keys())
    haram = sorted(kunci & KOLOM_TERLARANG)
    if haram:
        raise KolomTerlarangError(
            f"Dataset '{nama_dataset}' memuat kolom identitas: {haram}. "
            f"Ekspor klinis DIBATALKAN — tidak ada berkas yang ditulis. "
            f"Kolom ini tidak boleh keluar dari Sehati; pakai `pid` dan `umur_tahun`."
        )
    uang = sorted(kunci & KOLOM_UANG)
    if uang:
        raise KolomUangError(
            f"Dataset '{nama_dataset}' memuat kolom uang: {uang}. "
            f"Ekspor klinis DIBATALKAN. Paket klinis sengaja TERPISAH dari "
            f"finance_pack — hak akses dan jalur keluarnya berbeda. Angka uang "
            f"ada di paket finance; di sini yang dikirim adalah apa yang "
            f"DIBERIKAN ke pasien, bukan berapa harganya."
        )
    return rows


# ======================================================================
def _pid_baru() -> str:
    """Pseudonim ACAK 12 karakter: 'PX' + 10 hex.

    Acak, BUKAN berurutan. Kalau `pid` mencerminkan urutan pendaftaran, siapa pun
    yang memegang paket bisa menebak pasien mana yang mana tanpa tabel petanya.
    `secrets`, bukan `random` — ini nilai yang melindungi identitas pasien.
    """
    return "PX" + secrets.token_hex(5)


class ClinicalExportService:
    """Bangun dataset klinis ber-pseudonim. Rentang tanggal OPSIONAL.

    [Keputusan dr. Hansen] default = SEJAK AWAL DATA. Analisis longitudinal
    (kasus berulang, drop case) butuh seluruh riwayat — dan pasien yang TIDAK
    muncul bulan ini justru yang paling penting, karena itulah drop case-nya.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------ pseudonim
    def _peta_gabung(self) -> dict[int, int]:
        """id_pasien -> id_pasien yang BERTAHAN, mengikuti rantai penggabungan.

        ⚠ Tanpa ini, satu orang yang pernah tercatat dua kali muncul sebagai DUA
          pasien berbeda di seluruh analisis: kasus berulangnya terpecah, riwayat
          kontrolnya terputus, dan tidak ada gejala apa pun bahwa itu terjadi.

        Rantai ditelusuri sampai ujung (A digabung ke B, B digabung ke C -> A
        harus jadi C), dengan pagar siklus: kalau data rusak dan penunjuknya
        berputar, berhenti alih-alih menggantung selamanya.
        """
        langsung = {
            int(r[0]): int(r[1])
            for r in self.db.execute(text(
                "SELECT id_pasien, digabung_ke_id_pasien FROM pasien "
                "WHERE digabung_ke_id_pasien IS NOT NULL")).all()
        }
        hasil: dict[int, int] = {}
        for awal in langsung:
            lihat, kini = {awal}, langsung[awal]
            while kini in langsung and kini not in lihat:
                lihat.add(kini)
                kini = langsung[kini]
            hasil[awal] = kini
        return hasil

    def sinkron_pseudonim(self) -> dict:
        """Pastikan SETIAP pasien punya `pid`. Get-or-create, tanpa UPDATE.

        ⚠ TIDAK PERNAH meng-UPDATE `pid` yang sudah ada. `pid` yang berubah =
          riwayat longitudinal pasien itu terputus, dan tidak akan ada yang
          menyadarinya karena berkasnya tetap terbentuk dengan rapi.
        """
        belum = [int(r[0]) for r in self.db.execute(text(
            "SELECT p.id_pasien FROM pasien p "
            "LEFT JOIN pasien_pseudonim s ON s.id_pasien = p.id_pasien "
            "WHERE s.id_pasien IS NULL ORDER BY p.id_pasien")).all()]
        dibuat = 0
        for pid_pasien in belum:
            # Tabrakan `pid` praktis mustahil (2^40), tapi UNIQUE-nya ada dan
            # kalau tabrakan terjadi lebih baik mencoba lagi daripada gagal.
            for _ in range(5):
                try:
                    self.db.execute(
                        text("INSERT INTO pasien_pseudonim (id_pasien, pid) "
                             "VALUES (:i, :p)"),
                        {"i": pid_pasien, "p": _pid_baru()})
                    dibuat += 1
                    break
                except Exception:
                    self.db.rollback()
            else:
                raise RuntimeError(
                    f"Gagal membuat pid untuk id_pasien={pid_pasien} setelah 5 "
                    f"percobaan. Ekspor dibatalkan.")
        if dibuat:
            self.db.commit()
        total = int(self.db.execute(text(
            "SELECT COUNT(*) FROM pasien_pseudonim")).scalar() or 0)
        n_pasien = int(self.db.execute(text(
            "SELECT COUNT(*) FROM pasien")).scalar() or 0)
        return {"dibuat": dibuat, "total_pid": total, "total_pasien": n_pasien}

    def peta_pid(self) -> dict[int, str]:
        """id_pasien -> pid, SUDAH mengikuti penggabungan.

        Pasien duplikat memetakan ke `pid` pasien yang BERTAHAN, sehingga
        riwayatnya menyatu di mata analis.
        """
        dasar = {
            int(r[0]): str(r[1])
            for r in self.db.execute(text(
                "SELECT id_pasien, pid FROM pasien_pseudonim")).all()
        }
        gabung = self._peta_gabung()
        peta = dict(dasar)
        for dup, bertahan in gabung.items():
            if bertahan in dasar:
                peta[dup] = dasar[bertahan]
        return peta

    # ------------------------------------------------------ bantu
    @staticmethod
    def _umur(tgl_lahir, patokan) -> Optional[int]:
        """Umur penuh dalam tahun pada tanggal `patokan`. None kalau tak diketahui."""
        if not tgl_lahir or not patokan:
            return None
        p = patokan.date() if hasattr(patokan, "date") else patokan
        u = p.year - tgl_lahir.year - ((p.month, p.day) < (tgl_lahir.month, tgl_lahir.day))
        return u if 0 <= u <= 130 else None

    @staticmethod
    def _kelompok_umur(u: Optional[int]) -> str:
        """Kelompok umur kasar. Berguna saat umur persis terlalu spesifik."""
        if u is None:
            return "TIDAK_DIKETAHUI"
        for batas, label in ((2, "0-1"), (6, "2-5"), (12, "6-11"), (18, "12-17"),
                             (26, "18-25"), (36, "26-35"), (46, "36-45"),
                             (56, "46-55"), (66, "56-65")):
            if u < batas:
                return label
        return "65+"

    def _filter_tanggal(self, kolom: str, dari: Optional[date],
                        sampai: Optional[date]) -> tuple[str, dict]:
        """Potongan WHERE untuk rentang OPSIONAL. Kosong = sejak awal data."""
        bagian, params = [], {}
        if dari:
            bagian.append(f"{kolom} >= :tgl_dari")
            params["tgl_dari"] = dari
        if sampai:
            bagian.append(f"{kolom} < DATE_ADD(:tgl_sampai, INTERVAL 1 DAY)")
            params["tgl_sampai"] = sampai
        return (" AND " + " AND ".join(bagian) if bagian else ""), params

    # ------------------------------------------------------ dataset
    def pasien_profil(self, dari=None, sampai=None) -> list[dict]:
        """Profil pasien TANPA identitas. Umur, bukan tanggal lahir.

        Tanggal lahir persis adalah pengidentifikasi kuat; umur menjawab
        pertanyaan klinis yang sama dengan risiko jauh lebih kecil.

        Pasien yang sudah DIGABUNGKAN tidak dikeluarkan sebagai baris sendiri —
        `pid`-nya sama dengan pasien yang bertahan, jadi barisnya akan kembar.
        """
        peta = self.peta_pid()
        hari_ini = date.today()
        rows, sudah = [], set()
        for r in self.db.execute(text(
            "SELECT id_pasien, tgl_lahir, jenis_kelamin, tipe_membership, "
            "       sumber_referensi, digabung_ke_id_pasien "
            "FROM pasien ORDER BY id_pasien")).all():
            if r[5] is not None:      # duplikat yang sudah digabung
                continue
            pid = peta.get(int(r[0]))
            if pid is None or pid in sudah:
                continue
            sudah.add(pid)
            u = self._umur(r[1], hari_ini)
            rows.append({
                "pid": pid,
                "umur_tahun": u,
                "kelompok_umur": self._kelompok_umur(u),
                "jenis_kelamin": r[2] or "",
                "tipe_membership": r[3] or "",
                "sumber_referensi": r[4] or "",
            })
        return pagar_kolom("clinical_pasien_profil", rows)

    def visits(self, dari=None, sampai=None) -> list[dict]:
        """Kunjungan. `keluhan_utama` & `catatan_kontrol` adalah TEKS BEBAS —
        keduanya ikut membuat paket ini rahasia, sama seperti SOAP.

        `umur_tahun_saat_kunjungan` sengaja ada di sini, bukan hanya umur
        sekarang di profil: untuk pertanyaan klinis, yang berarti adalah umur
        pasien SAAT kejadian, bukan umurnya hari ini.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT k.id_kunjungan, k.id_pasien, k.tgl_kunjungan, k.jenis_kunjungan, "
            "       k.status_antrian, k.sumber_pendaftaran, k.keluhan_utama, "
            "       k.tgl_kontrol_selanjutnya, k.catatan_kontrol, "
            "       sd.nama_staf, p.tgl_lahir "
            "FROM kunjungan k "
            "JOIN pasien p ON p.id_pasien = k.id_pasien "
            "LEFT JOIN master_staf sd ON sd.id_staf = k.id_staf_dokter_assigned "
            f"WHERE 1=1 {wh} ORDER BY k.id_kunjungan"), params).all():
            pid = peta.get(int(r[1]))
            if pid is None:
                continue
            rows.append({
                "kid": int(r[0]),
                "pid": pid,
                "tgl_kunjungan": r[2],
                "jenis_kunjungan": r[3] or "",
                "status_antrian": r[4] or "",
                "sumber_pendaftaran": r[5] or "",
                "keluhan_utama": r[6] or "",
                "tgl_kontrol_selanjutnya": r[7],
                "catatan_kontrol": r[8] or "",
                "nama_dokter_assigned": r[9] or "",
                "umur_tahun_saat_kunjungan": self._umur(r[10], r[2]),
            })
        return pagar_kolom("clinical_visits", rows)

    def soap(self, dari=None, sampai=None) -> list[dict]:
        """SOAP — HANYA yang `status_soap='FINAL'`.

        ⚠ Draf yang belum disetujui dokter BUKAN rekam medis. Mengirimnya ke
          analisis berarti menganalisa sesuatu yang belum divalidasi siapa pun —
          dan di apotek, draf memang dibuat oleh apoteker lebih dulu.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("pk.created_at", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT pk.id_kunjungan, pk.id_pasien, sd.nama_staf, pk.anamnesa, "
            "       pk.pemeriksaan_fisik, pk.diagnosa, pk.saran_treatment, "
            "       pk.saran_produk, pk.status_soap, pk.waktu_konsultasi, pk.created_at "
            "FROM pemeriksaan_klinis pk "
            "LEFT JOIN master_staf sd ON sd.id_staf = pk.id_staf_dokter "
            f"WHERE pk.status_soap = 'FINAL' {wh} ORDER BY pk.id_pemeriksaan"),
            params).all():
            pid = peta.get(int(r[1]))
            if pid is None:
                continue
            rows.append({
                "kid": int(r[0]), "pid": pid,
                "nama_dokter": r[2] or "",
                "anamnesa": r[3] or "",
                "pemeriksaan_fisik": r[4] or "",
                "diagnosa": r[5] or "",
                "saran_treatment": r[6] or "",
                "saran_produk": r[7] or "",
                "status_soap": r[8] or "",
                "waktu_konsultasi": r[9],
                "created_at": r[10],
            })
        return pagar_kolom("clinical_soap", rows)

    def diagnosa(self, dari=None, sampai=None) -> list[dict]:
        """Diagnosa TERKODE dari `kunjungan_diagnosa` — belum pernah ikut ekspor.

        Tanpa ini modul analisis hanya menerima narasi tanpa kode, jadi "kasus
        terbanyak" harus ditebak dari teks bebas. Snapshot dipakai (bukan join ke
        `ref_diagnosa`) supaya kode/nama yang dianalisa adalah yang BERLAKU SAAT
        diagnosa dibuat, bukan yang berlaku sekarang.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT kd.id_kunjungan, k.id_pasien, kd.sistem_snapshot, "
            "       kd.kode_snapshot, kd.nama_snapshot, kd.is_primer, kd.urutan, "
            "       kd.catatan, k.tgl_kunjungan "
            "FROM kunjungan_diagnosa kd "
            "JOIN kunjungan k ON k.id_kunjungan = kd.id_kunjungan "
            f"WHERE 1=1 {wh} ORDER BY kd.id_kunjungan, kd.urutan"), params).all():
            pid = peta.get(int(r[1]))
            if pid is None:
                continue
            rows.append({
                "kid": int(r[0]), "pid": pid,
                "sistem_snapshot": r[2] or "",
                "kode_snapshot": r[3] or "",
                "nama_snapshot": r[4] or "",
                "is_primer": 1 if r[5] else 0,
                "urutan": int(r[6] or 0),
                "catatan": r[7] or "",
                "tgl_kunjungan": r[8],
            })
        return pagar_kolom("clinical_diagnosa", rows)

    def pid_gabung(self, dari=None, sampai=None) -> list[dict]:
        """`pid_lama` -> `pid_bertahan` untuk pasien yang digabungkan.

        KENAPA BERKAS INI ADA (tidak ada di rancangan awal):
        Kalau pasien digabungkan SETELAH ekspor pertama, riwayat `pid` lama
        pindah ke `pid` yang bertahan. Di mata analis: satu pasien menghilang,
        pasien lain tiba-tiba bertambah riwayat, tanpa penjelasan — dan ia akan
        menyimpulkan yang salah (drop case palsu, lonjakan palsu).

        Berkas ini menutup lubang itu dan TIDAK membocorkan identitas siapa pun:
        kedua sisinya pseudonim.
        """
        dasar = {
            int(r[0]): str(r[1])
            for r in self.db.execute(text(
                "SELECT id_pasien, pid FROM pasien_pseudonim")).all()
        }
        gabung = self._peta_gabung()   # DI LUAR loop: di dalam = 1 query per baris
        rows = []
        for r in self.db.execute(text(
            "SELECT id_pasien, digabung_ke_id_pasien, nonaktif_at FROM pasien "
            "WHERE digabung_ke_id_pasien IS NOT NULL ORDER BY id_pasien")).all():
            lama = dasar.get(int(r[0]))
            # ujung rantai, bukan penunjuk langsung
            bertahan = dasar.get(gabung.get(int(r[0]), int(r[1])))
            if lama and bertahan:
                rows.append({"pid_lama": lama, "pid_bertahan": bertahan,
                             "waktu_gabung": r[2]})
        return pagar_kolom("clinical_pid_gabung", rows)

    # ------------------------------------------------------ registry
    # Nomor berkas berasal dari POSISI di sini. Menghapus entri akan menggeser
    # nomor berkas dan merusak penerima yang membuka berkas berdasarkan nama —
    # pelajaran dari finance_pack (lihat export_service.FINANCE_PACK_EXCLUDE).
    # Tambahkan di AKHIR, jangan menyisipkan di tengah.
    # ================================================================
    # TAHAP B — tindakan, resep, racikan (+bahan), followup
    # ================================================================
    # [Keputusan dr. Hansen 2026-10-04] KOLOM UANG TIDAK IKUT. Paket klinis baru
    # dipisahkan dari finance_pack justru karena hak akses dan jalur keluarnya
    # berbeda; menaruh harga di sini membatalkan pemisahan itu. Yang dikirim
    # adalah APA YANG DIBERIKAN ke pasien — bahan, dosis, satuan, aturan pakai —
    # bukan berapa harganya. Jangan tambahkan harga_satuan/subtotal/biaya_racik/
    # total tanpa membicarakannya lagi.

    def tindakan(self, dari=None, sampai=None) -> list[dict]:
        """Tindakan per kunjungan.

        ⚠ `kunjungan_tindakan` TIDAK punya kolom snapshot nama, tidak seperti
        `kunjungan_diagnosa` yang punya `nama_snapshot`. Jadi namanya di-JOIN
        dari `master_treatment` SEKARANG. Kalau sebuah tindakan di-rename, SELURUH
        riwayatnya ikut berubah nama di ekspor berikutnya — analis akan melihat
        satu tindakan lenyap dan tindakan lain muncul dengan riwayat panjang.
        Menambal ini butuh migrasi (kolom snapshot), dan Tahap B sengaja tanpa
        migrasi. Dicatat supaya tidak ditemukan sebagai kejutan.

        Pelaksana dikirim sebagai NAMA, bukan id — mengikuti `visits`, yang sudah
        mengirim `nama_dokter` atas permintaan dr. Hansen.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT kt.id_kunjungan_tindakan, kt.id_kunjungan, k.id_pasien, "
            "       mt.nama_treatment, kt.status_tindakan, "
            "       sd.nama_staf, sp.nama_staf, "
            "       kt.waktu_mulai, kt.waktu_selesai, k.tgl_kunjungan, "
            "       kt.id_kuota_member, kt.id_rencana "
            "FROM kunjungan_tindakan kt "
            "JOIN kunjungan k ON k.id_kunjungan = kt.id_kunjungan "
            "LEFT JOIN master_treatment mt ON mt.id_treatment = kt.id_treatment "
            "LEFT JOIN master_staf sd ON sd.id_staf = kt.id_dokter_pelaksana "
            "LEFT JOIN master_staf sp ON sp.id_staf = kt.id_perawat_pelaksana "
            f"WHERE 1=1 {wh} ORDER BY kt.id_kunjungan, kt.id_kunjungan_tindakan"),
                params).all():
            pid = peta.get(int(r[2]))
            if pid is None:
                continue
            rows.append({
                "tid": int(r[0]), "kid": int(r[1]), "pid": pid,
                "nama_tindakan": r[3] or "",
                "status_tindakan": r[4] or "",
                "nama_dokter_pelaksana": r[5] or "",
                "nama_perawat_pelaksana": r[6] or "",
                "waktu_mulai": r[7], "waktu_selesai": r[8],
                "tgl_kunjungan": r[9],
                # Bendera, bukan id: cukup untuk membedakan tindakan yang ditebus
                # dari kuota membership / rencana terapi, tanpa membocorkan kunci.
                "dari_kuota_member": 1 if r[10] else 0,
                "dari_rencana": 1 if r[11] else 0,
            })
        return pagar_kolom("clinical_tindakan", rows)

    def resep(self, dari=None, sampai=None) -> list[dict]:
        """Resep obat jadi per kunjungan.

        `kandungan` dan `golongan` ikut: untuk pertanyaan klinis, yang berarti
        adalah zat aktif dan kelas obatnya, bukan merek dagang. Tanpa itu analis
        harus memetakan 154 nama dagang sendiri.

        `aturan_pakai` TEKS BEBAS — ikut membuat paket ini rahasia.
        ⚠ Tabel `kunjungan_resep` TIDAK memuat `peresep_luar_nama`/`_asal`
        (dokter luar klinik, dilarang oleh KOLOM_TERLARANG); resep luar hidup di
        alur apotek yang terpisah. Diperiksa, bukan diasumsikan.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT kr.id_resep, kr.id_kunjungan, k.id_pasien, "
            "       mp.nama_produk, mp.kandungan, mp.golongan, mp.satuan, "
            "       kr.qty, kr.aturan_pakai, kr.status_item, "
            "       kr.waktu_input, kr.waktu_serah, k.tgl_kunjungan, "
            "       kr.id_resep_asal "
            "FROM kunjungan_resep kr "
            "JOIN kunjungan k ON k.id_kunjungan = kr.id_kunjungan "
            "LEFT JOIN master_produk mp ON mp.id_produk = kr.id_produk "
            f"WHERE 1=1 {wh} ORDER BY kr.id_kunjungan, kr.id_resep"), params).all():
            pid = peta.get(int(r[2]))
            if pid is None:
                continue
            rows.append({
                "rid": int(r[0]), "kid": int(r[1]), "pid": pid,
                "nama_produk": r[3] or "",
                "kandungan": r[4] or "",
                "golongan": r[5] or "",
                "satuan": r[6] or "",
                "qty": float(r[7]) if r[7] is not None else None,
                "aturan_pakai": r[8] or "",
                "status_item": r[9] or "",
                "waktu_input": r[10], "waktu_serah": r[11],
                "tgl_kunjungan": r[12],
                # Iterasi (tebus ulang) — penanda kelangsungan terapi.
                "is_iterasi": 1 if r[13] else 0,
            })
        return pagar_kolom("clinical_resep", rows)

    def racikan(self, dari=None, sampai=None) -> list[dict]:
        """Racikan per kunjungan — INDUK. Bahannya di `clinical_racikan_bahan`.

        TANPA kolom uang (lihat catatan di atas blok Tahap B).
        `nama_snapshot` memang tersimpan di tabel ini, jadi racikan TIDAK punya
        masalah rename yang dimiliki `tindakan`.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT kra.id_kunjungan_racikan, kra.id_kunjungan, k.id_pasien, "
            "       kra.nama_snapshot, kra.jenis_racik, kra.jumlah_unit, "
            "       kra.aturan_pakai, kra.status_item, kra.waktu_serah, "
            "       k.tgl_kunjungan, kra.id_kunjungan_racikan_asal "
            "FROM kunjungan_racikan kra "
            "JOIN kunjungan k ON k.id_kunjungan = kra.id_kunjungan "
            f"WHERE 1=1 {wh} ORDER BY kra.id_kunjungan, kra.id_kunjungan_racikan"),
                params).all():
            pid = peta.get(int(r[2]))
            if pid is None:
                continue
            rows.append({
                "racid": int(r[0]), "kid": int(r[1]), "pid": pid,
                "nama_snapshot": r[3] or "",
                "jenis_racik": r[4] or "",
                "jumlah_unit": float(r[5]) if r[5] is not None else None,
                "aturan_pakai": r[6] or "",
                "status_item": r[7] or "",
                "waktu_serah": r[8],
                "tgl_kunjungan": r[9],
                "is_iterasi": 1 if r[10] else 0,
            })
        return pagar_kolom("clinical_racikan", rows)

    def racikan_bahan(self, dari=None, sampai=None) -> list[dict]:
        """Bahan penyusun tiap racikan — dosis dan kekuatan, TANPA harga.

        `pid` dan `kid` ikut walau bisa dijangkau lewat `racid`, supaya berkas ini
        bisa dianalisa sendiri tanpa menggabung dulu — pola yang sama dipakai
        berkas Tahap A.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("k.tgl_kunjungan", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT b.id_kunjungan_racikan_bahan, b.id_kunjungan_racikan, "
            "       kra.id_kunjungan, k.id_pasien, "
            "       b.nama_snapshot, b.dosis_per_unit, b.satuan_dosis, "
            "       b.kekuatan_snapshot, b.mode_hitung, b.dipakai, "
            "       b.satuan_dipakai, k.tgl_kunjungan "
            "FROM kunjungan_racikan_bahan b "
            "JOIN kunjungan_racikan kra "
            "  ON kra.id_kunjungan_racikan = b.id_kunjungan_racikan "
            "JOIN kunjungan k ON k.id_kunjungan = kra.id_kunjungan "
            f"WHERE 1=1 {wh} ORDER BY b.id_kunjungan_racikan, "
            "b.id_kunjungan_racikan_bahan"), params).all():
            pid = peta.get(int(r[3]))
            if pid is None:
                continue
            rows.append({
                "bid": int(r[0]), "racid": int(r[1]), "kid": int(r[2]), "pid": pid,
                "nama_snapshot": r[4] or "",
                "dosis_per_unit": float(r[5]) if r[5] is not None else None,
                "satuan_dosis": r[6] or "",
                # decimal(10,3) di DB, BUKAN teks — ketahuan saat uji dengan data
                # nyata. `r[7] or ""` akan mengubah 0 jadi string kosong dan
                # mengirim objek Decimal untuk nilai lain.
                "kekuatan_snapshot": float(r[7]) if r[7] is not None else None,
                "mode_hitung": r[8] or "",
                "dipakai": float(r[9]) if r[9] is not None else None,
                "satuan_dipakai": r[10] or "",
                "tgl_kunjungan": r[11],
            })
        return pagar_kolom("clinical_racikan_bahan", rows)

    def followup(self, dari=None, sampai=None) -> list[dict]:
        """Jejak kontrol — INI ALASAN UTAMA TAHAP B ADA.

        Tanpa berkas ini, modul analisis melihat pasien datang lalu berhenti, dan
        tidak bisa membedakan "sembuh lalu tidak perlu kembali" dari "hilang tanpa
        kontrol". `status` membedakannya:
            PENDING / CONFIRMED / RESCHEDULED -> masih dalam alur
            NO_ANSWER                         -> dihubungi, tidak menjawab
            CANCELLED                         -> membatalkan
        NO_ANSWER dan CANCELLED itulah sinyal drop case yang dicari.

        ⚠ DISARING PER `due_date`, bukan per tanggal kunjungan. Followup justru
        hidup SESUDAH kunjungannya; memakai tgl_kunjungan membuat followup yang
        jatuh tempo di luar rentang ikut hilang, dan drop case paling telat
        justru yang paling penting terlihat.

        `catatan` TEKS BEBAS — petugas menuliskan hasil menelepon di sana, jadi
        ia bisa memuat nama dan nomor orang. Dikirim apa adanya sesuai keputusan
        dr. Hansen; itu bagian dari kenapa paket ini rahasia.
        """
        peta = self.peta_pid()
        wh, params = self._filter_tanggal("f.due_date", dari, sampai)
        rows = []
        for r in self.db.execute(text(
            "SELECT f.id_followup, f.id_pasien, f.id_kunjungan, "
            "       mt.nama_treatment, f.jenis, f.due_date, f.status, "
            "       f.waktu_handle, f.catatan, f.created_at "
            "FROM followup f "
            "LEFT JOIN master_treatment mt ON mt.id_treatment = f.id_treatment "
            f"WHERE 1=1 {wh} ORDER BY f.due_date, f.id_followup"), params).all():
            pid = peta.get(int(r[1]))
            if pid is None:
                continue
            rows.append({
                "fid": int(r[0]), "pid": pid,
                "kid": int(r[2]) if r[2] is not None else None,
                "nama_treatment": r[3] or "",
                "jenis": r[4] or "",
                "due_date": r[5],
                "status": r[6] or "",
                "waktu_handle": r[7],
                "catatan": r[8] or "",
                "created_at": r[9],
            })
        return pagar_kolom("clinical_followup", rows)

    REGISTRY: tuple[dict, ...] = (
        {"name": "clinical_pasien_profil", "method": "pasien_profil"},
        {"name": "clinical_visits", "method": "visits"},
        {"name": "clinical_soap", "method": "soap"},
        {"name": "clinical_diagnosa", "method": "diagnosa"},
        {"name": "clinical_pid_gabung", "method": "pid_gabung"},
        # --- Tahap B (2026-10-04) ---
        # DITAMBAHKAN DI AKHIR dengan sengaja: nomor urut berkas (01_, 02_, …)
        # berasal dari urutan di sini. Menyisipkan di tengah akan menomori ulang
        # berkas Tahap A, dan penerima yang sudah menyimpan riwayat akan melihat
        # berkas "baru" yang sebenarnya sama.
        {"name": "clinical_tindakan", "method": "tindakan"},
        {"name": "clinical_resep", "method": "resep"},
        {"name": "clinical_racikan", "method": "racikan"},
        {"name": "clinical_racikan_bahan", "method": "racikan_bahan"},
        {"name": "clinical_followup", "method": "followup"},
    )


__all__ = [
    "ClinicalExportService", "KOLOM_TERLARANG", "KOLOM_UANG",
    "KolomTerlarangError", "KolomUangError", "pagar_kolom",
]
