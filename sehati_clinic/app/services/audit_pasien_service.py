"""
AuditPasienService — Lapis-2 integritas ID pasien (task #18).

Lapis-1 (`pasien_service.find_duplicate_candidates`) bekerja SAAT pendaftaran dan
sengaja ketat tanpa toleransi typo, supaya meja FO tidak dibanjiri peringatan palsu.
Konsekuensinya: "Budi Santoso" dan "Budo Santoso" lolos sebagai dua orang.

Modul ini menyisir SELURUH tabel pasien dalam sesi maintenance dan menampilkan
kandidat untuk ditinjau MANUSIA. Tidak ada auto-merge, tidak ada auto-delete —
keputusan "ini orang yang sama" menggabungkan rekam medis, dan kalau salah, dua
riwayat pasien tercampur.

Ref: `Project_Memory/AUDIT_ID_PASIEN_DESIGN.md`.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.nik import normalisasi_nik
from app.db.models import Pasien, PasienDuplikatDismiss
from app.services.audit_service import AuditService

# Ambang kemiripan nama (0..1). 0.85 menangkap typo 1-2 huruf pada nama biasa
# tanpa menyeret nama pendek yang kebetulan mirip ("Ani" vs "Ana" = 0.67, lolos).
AMBANG_MIRIP_DEFAULT = 0.85

# Kata yang bukan bagian identitas → dibuang sebelum banding, supaya
# "Budi Santoso" dan "Tn. Budi Santoso" tidak lolos sebagai dua orang.
_GELAR = {
    "tn", "ny", "nn", "sdr", "sdri", "bp", "bpk", "ibu", "bapak",
    "dr", "drg", "ir", "h", "hj", "drs", "dra", "st", "se", "mm",
}


def _norm(teks: Optional[str]) -> str:
    """Normalisasi untuk BANDING, bukan untuk ditampilkan.

    Huruf kecil, aksen dilepas, tanda baca jadi spasi, gelar dibuang, spasi diringkas.
    """
    s = unicodedata.normalize("NFKD", (teks or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = "".join(c if c.isalnum() else " " for c in s)
    kata = [w for w in s.split() if w and w not in _GELAR]
    return " ".join(kata)


def _norm_telepon(teks: Optional[str]) -> str:
    """Hanya angka; awalan +62/62/0 diseragamkan jadi '0'.

    Tanpa ini, '081234' dan '+6281234' terlihat seperti dua nomor berbeda padahal
    orang yang sama — persis cara nomor telepon biasa diketik berbeda-beda.
    """
    d = "".join(c for c in (teks or "") if c.isdigit())
    if d.startswith("62"):
        d = "0" + d[2:]
    elif d and not d.startswith("0"):
        d = "0" + d
    return d


def _levenshtein(a: str, b: str) -> int:
    """Jarak edit, implementasi dua-baris (tanpa dependensi luar)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _mirip(a: str, b: str) -> float:
    """Kemiripan 0..1 = 1 - jarak_edit / panjang_terpanjang."""
    if not a or not b:
        return 0.0
    n = max(len(a), len(b))
    return 1.0 - (_levenshtein(a, b) / n)


class AuditPasienService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    def _dismissed(self) -> set[tuple[int, int]]:
        rows = self.db.execute(
            select(PasienDuplikatDismiss.id_pasien_a, PasienDuplikatDismiss.id_pasien_b)
        ).all()
        return {(r[0], r[1]) for r in rows}

    def scan(self, ambang: float = AMBANG_MIRIP_DEFAULT) -> dict:
        """Sisir seluruh pasien, kembalikan daftar pasangan kandidat + ringkasan.

        Pasangan diberi TINGKAT, dari yang paling meyakinkan:
          NIK      — NIK sama persis. Nyaris pasti orang yang sama.
          KUAT     — nama sama persis + tgl lahir sama.
          SEDANG   — nama sama persis + (alamat ATAU telepon) sama.
          MIRIP    — nama MIRIP (typo) + tgl lahir ATAU telepon sama.

        MIRIP sengaja menuntut satu field pendukung. Nama mirip saja terlalu longgar
        di Indonesia — terlalu banyak nama yang berdekatan secara huruf tapi milik
        orang berbeda, dan laporan yang berisik akan berhenti dibaca.
        """
        # Hanya pasien AKTIF. Yang sudah dinonaktifkan berarti sudah diputuskan —
        # memunculkannya lagi membuat daftar ini tidak pernah habis.
        pasien = list(self.db.execute(
            select(Pasien).where(Pasien.is_active.is_(True))
            .order_by(Pasien.id_pasien.asc())
        ).scalars().all())
        dismissed = self._dismissed()

        # Pra-hitung sekali per pasien — jangan menormalkan ulang di dalam loop
        # berpasangan, jumlah bandingannya tumbuh kuadratik.
        info = []
        for p in pasien:
            info.append({
                "p": p,
                "nama_n": _norm(p.nama),
                "tel_n": _norm_telepon(p.nomor_telepon),
                "alamat_n": _norm(p.alamat),
                # normalisasi_nik, bukan .strip(): kalau ada data lama ber-NIK
                # '0'/'-', .strip() menjadikannya kunci blocking "k:0" sehingga
                # SEMUA pasien tanpa KTP saling muncul sebagai kandidat duplikat.
                "nik_n": normalisasi_nik(p.nomor_ktp) or "",
            })

        # Blocking: hanya banding pasangan yang berbagi "petunjuk" — kata pertama
        # nama, tgl lahir, telepon, atau NIK. Tanpa ini, 10.000 pasien berarti
        # 50 juta bandingan; dengan ini hanya pasangan yang masuk akal yang dihitung.
        ember: dict[str, list[int]] = {}
        for idx, it in enumerate(info):
            kunci = set()
            kata = it["nama_n"].split()
            if kata:
                kunci.add("n:" + kata[0][:4])
                kunci.add("z:" + kata[-1][:4])   # nama belakang, kalau urutannya tertukar
            if it["p"].tgl_lahir:
                kunci.add("d:" + str(it["p"].tgl_lahir))
            if it["tel_n"]:
                kunci.add("t:" + it["tel_n"])
            if it["nik_n"]:
                kunci.add("k:" + it["nik_n"])
            for k in kunci:
                ember.setdefault(k, []).append(idx)

        dilihat: set[tuple[int, int]] = set()
        hasil = []
        for anggota in ember.values():
            if len(anggota) < 2:
                continue
            for i in range(len(anggota)):
                for j in range(i + 1, len(anggota)):
                    a, b = info[anggota[i]], info[anggota[j]]
                    pa, pb = a["p"], b["p"]
                    kunci = (min(pa.id_pasien, pb.id_pasien), max(pa.id_pasien, pb.id_pasien))
                    if kunci in dilihat or kunci in dismissed:
                        continue
                    dilihat.add(kunci)

                    tingkat = None
                    alasan = []
                    skor = 0.0

                    if a["nik_n"] and a["nik_n"] == b["nik_n"]:
                        tingkat, skor = "NIK", 1.0
                        alasan.append(f"NIK sama persis ({a['nik_n']})")
                    else:
                        sama_nama = a["nama_n"] and a["nama_n"] == b["nama_n"]
                        sama_dob = bool(pa.tgl_lahir and pa.tgl_lahir == pb.tgl_lahir)
                        sama_tel = bool(a["tel_n"] and a["tel_n"] == b["tel_n"])
                        sama_alamat = bool(a["alamat_n"] and a["alamat_n"] == b["alamat_n"])
                        if sama_nama and sama_dob:
                            tingkat, skor = "KUAT", 0.95
                            alasan += ["nama sama persis", f"tgl lahir sama ({pa.tgl_lahir})"]
                        elif sama_nama and (sama_tel or sama_alamat):
                            tingkat, skor = "SEDANG", 0.80
                            alasan.append("nama sama persis")
                            if sama_tel:
                                alasan.append("nomor telepon sama")
                            if sama_alamat:
                                alasan.append("alamat sama")
                        else:
                            m = _mirip(a["nama_n"], b["nama_n"])
                            if m >= ambang and (sama_dob or sama_tel):
                                tingkat, skor = "MIRIP", m
                                alasan.append(f"nama mirip ({m:.0%})")
                                if sama_dob:
                                    alasan.append(f"tgl lahir sama ({pa.tgl_lahir})")
                                if sama_tel:
                                    alasan.append("nomor telepon sama")

                    if tingkat is None:
                        continue

                    # Tanda bahaya: jenis kelamin BERBEDA pada pasangan yang lain-lainnya
                    # cocok. Bisa berarti salah input, bisa berarti memang dua orang.
                    beda_jk = (
                        pa.jenis_kelamin is not None and pb.jenis_kelamin is not None
                        and pa.jenis_kelamin != pb.jenis_kelamin
                    )
                    hasil.append({
                        "id_a": pa.id_pasien, "id_b": pb.id_pasien,
                        "tingkat": tingkat, "skor": round(skor, 3),
                        "alasan": alasan, "beda_jenis_kelamin": beda_jk,
                        "a": pa, "b": pb,
                    })

        urut = {"NIK": 0, "KUAT": 1, "SEDANG": 2, "MIRIP": 3}
        hasil.sort(key=lambda h: (urut.get(h["tingkat"], 9), -h["skor"]))
        ringkas = {t: sum(1 for h in hasil if h["tingkat"] == t)
                   for t in ("NIK", "KUAT", "SEDANG", "MIRIP")}
        return {
            "total_pasien": len(pasien),
            "total_kandidat": len(hasil),
            "ringkasan": ringkas,
            "ambang": ambang,
            "dismissed": len(dismissed),
            "kandidat": hasil,
        }

    # ------------------------------------------------------------------
    def dismiss(self, id_a: int, id_b: int, alasan: Optional[str],
                actor_id_staf: int, request: Optional[Request] = None) -> dict:
        """Tandai satu pasangan sebagai BUKAN duplikat, supaya tidak muncul lagi."""
        if id_a == id_b:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pasangan tidak valid.")
        a, b = (id_a, id_b) if id_a < id_b else (id_b, id_a)
        for _id in (a, b):
            if self.db.get(Pasien, _id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Pasien {_id} tidak ditemukan.")
        sudah = self.db.execute(
            select(PasienDuplikatDismiss.id_dismiss).where(
                PasienDuplikatDismiss.id_pasien_a == a,
                PasienDuplikatDismiss.id_pasien_b == b,
            ).limit(1)
        ).first()
        if sudah:
            return {"status": "success", "message": "Pasangan itu memang sudah ditandai."}
        self.db.add(PasienDuplikatDismiss(
            id_pasien_a=a, id_pasien_b=b,
            alasan=(alasan or "").strip() or None, id_staf=actor_id_staf,
        ))
        self.audit.log(
            aksi="AUDIT_PASIEN_DISMISS", id_staf=actor_id_staf, tabel_target="pasien",
            id_target=a,
            data_baru={"id_pasien_a": a, "id_pasien_b": b, "alasan": alasan},
            keterangan=f"Pasangan pasien {a} & {b} dinyatakan BUKAN duplikat.",
            request=request,
        )
        self.db.commit()
        return {"status": "success",
                "message": f"Pasien #{a} & #{b} ditandai bukan duplikat."}

    def batal_dismiss(self, id_a: int, id_b: int, actor_id_staf: int,
                      request: Optional[Request] = None) -> dict:
        """Cabut penandaan — kalau ternyata keliru, pasangan kembali masuk laporan."""
        a, b = (id_a, id_b) if id_a < id_b else (id_b, id_a)
        row = self.db.execute(
            select(PasienDuplikatDismiss).where(
                PasienDuplikatDismiss.id_pasien_a == a,
                PasienDuplikatDismiss.id_pasien_b == b,
            )
        ).scalars().first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Penandaan tidak ditemukan.")
        self.db.delete(row)
        self.audit.log(
            aksi="AUDIT_PASIEN_DISMISS_BATAL", id_staf=actor_id_staf,
            tabel_target="pasien", id_target=a,
            keterangan=f"Penandaan bukan-duplikat untuk pasien {a} & {b} dicabut.",
            request=request,
        )
        self.db.commit()
        return {"status": "success", "message": f"Penandaan #{a} & #{b} dicabut."}

    # ------------------------------------------------------------------
    def _jumlah_riwayat(self, id_pasien: int) -> dict:
        """Berapa banyak jejak yang menempel pada pasien ini.

        Dipakai untuk memberi tahu petugas apa yang akan tertinggal di ID yang
        dinonaktifkan — bukan untuk melarang, tapi supaya keputusannya sadar.
        """
        from sqlalchemy import func
        from app.db.models import Kunjungan, TransaksiKasir

        n_kunj = self.db.execute(
            select(func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.id_pasien == id_pasien)
        ).scalar() or 0
        n_trx = self.db.execute(
            select(func.count(TransaksiKasir.id_transaksi))
            .where(TransaksiKasir.id_pasien == id_pasien)
        ).scalar() or 0
        return {"kunjungan": int(n_kunj), "transaksi": int(n_trx)}

    def nonaktifkan(self, id_pasien: int, alasan: str, actor_id_staf: int,
                    digabung_ke: Optional[int] = None,
                    request: Optional[Request] = None) -> dict:
        """Nonaktifkan satu pasien duplikat. TIDAK menghapus apa pun.

        Yang terjadi: pasien hilang dari pencarian dan dari deteksi duplikat saat
        pendaftaran, NIK-nya DILEPAS (dipindah ke `nomor_ktp_lama`) supaya bisa
        dipakai pasien yang bertahan, dan nomor RM-nya pensiun — tidak akan pernah
        diberikan ke orang lain.

        Riwayat yang terlanjur menempel (kunjungan, transaksi) TETAP di ID ini.
        Memindahkannya adalah penggabungan sungguhan, yang belum dibangun.
        """
        p = self.db.get(Pasien, id_pasien)
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Pasien {id_pasien} tidak ditemukan.")
        if not p.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{p.nama} ({p.no_rm}) sudah nonaktif.")
        if not (alasan or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Alasan WAJIB diisi — ini menyembunyikan seorang pasien.")
        if digabung_ke is not None:
            if digabung_ke == id_pasien:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Tidak bisa menunjuk ke dirinya sendiri.")
            lawan = self.db.get(Pasien, digabung_ke)
            if lawan is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND,
                                    f"Pasien tujuan {digabung_ke} tidak ditemukan.")
            if not lawan.is_active:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Pasien tujuan {lawan.no_rm} juga nonaktif — pilih yang bertahan.")

        riwayat = self._jumlah_riwayat(id_pasien)
        # DISENGAJA .strip(), BUKAN normalisasi_nik(). Di sini tujuannya
        # MEMBEBASKAN slot unique index. Kalau ada baris lama ber-NIK '0',
        # normalisasi_nik() mengembalikan None -> `if nik_dilepas` gagal ->
        # '0' tetap menempel di baris nonaktif dan slot itu terkunci selamanya.
        # Satu fungsi, dua tujuan berbeda — lihat app/core/nik.py.
        nik_dilepas = (p.nomor_ktp or "").strip() or None

        p.is_active = False
        p.nonaktif_at = datetime.now()
        p.nonaktif_alasan = alasan.strip()[:255]
        p.id_staf_nonaktif = actor_id_staf
        p.digabung_ke_id_pasien = digabung_ke
        if nik_dilepas:
            p.nomor_ktp_lama = nik_dilepas
            p.nomor_ktp = None

        self.audit.log(
            aksi="PASIEN_NONAKTIF", id_staf=actor_id_staf, tabel_target="pasien",
            id_target=id_pasien,
            data_lama={"is_active": True, "nomor_ktp": nik_dilepas},
            data_baru={
                "is_active": False, "alasan": p.nonaktif_alasan,
                "digabung_ke_id_pasien": digabung_ke,
                "nik_dilepas": bool(nik_dilepas),
                "riwayat_tertinggal": riwayat,
            },
            keterangan=(
                f"Pasien {p.no_rm} ({p.nama}) dinonaktifkan. "
                f"Riwayat tertinggal: {riwayat['kunjungan']} kunjungan, "
                f"{riwayat['transaksi']} transaksi. No RM DIPENSIUNKAN."
            ),
            request=request,
        )
        self.db.commit()
        pesan = f"{p.nama} ({p.no_rm}) dinonaktifkan."
        if nik_dilepas:
            pesan += " NIK dilepas — sekarang bisa dipakai pasien yang bertahan."
        if riwayat["kunjungan"] or riwayat["transaksi"]:
            pesan += (f" ⚠ {riwayat['kunjungan']} kunjungan & {riwayat['transaksi']} "
                      "transaksi TETAP di ID ini (belum dipindahkan).")
        return {"status": "success", "message": pesan, "data": riwayat}

    def aktifkan(self, id_pasien: int, actor_id_staf: int,
                 request: Optional[Request] = None) -> dict:
        """Kembalikan pasien yang salah dinonaktifkan.

        NIK yang dilepas dipasang kembali HANYA kalau belum diambil pasien lain —
        kalau sudah, NIK-nya dibiarkan kosong supaya tidak bentrok, dan petugas
        memutuskan sendiri milik siapa NIK itu.
        """
        p = self.db.get(Pasien, id_pasien)
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Pasien {id_pasien} tidak ditemukan.")
        if p.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{p.nama} sudah aktif.")

        nik_kembali = False
        if p.nomor_ktp_lama and not p.nomor_ktp:
            bentrok = self.db.execute(
                select(Pasien.id_pasien).where(
                    Pasien.nomor_ktp == p.nomor_ktp_lama,
                    Pasien.id_pasien != id_pasien,
                ).limit(1)
            ).first()
            if not bentrok:
                p.nomor_ktp = p.nomor_ktp_lama
                p.nomor_ktp_lama = None
                nik_kembali = True

        p.is_active = True
        p.nonaktif_at = None
        p.nonaktif_alasan = None
        p.id_staf_nonaktif = None
        p.digabung_ke_id_pasien = None
        self.audit.log(
            aksi="PASIEN_AKTIFKAN", id_staf=actor_id_staf, tabel_target="pasien",
            id_target=id_pasien,
            data_baru={"is_active": True, "nik_dipasang_kembali": nik_kembali},
            keterangan=f"Pasien {p.no_rm} ({p.nama}) diaktifkan kembali.",
            request=request,
        )
        self.db.commit()
        pesan = f"{p.nama} ({p.no_rm}) aktif kembali."
        if p.nomor_ktp_lama and not nik_kembali:
            pesan += (" ⚠ NIK lamanya sudah dipakai pasien lain, jadi dibiarkan kosong — "
                      "tentukan sendiri milik siapa NIK itu.")
        return {"status": "success", "message": pesan}

    def list_nonaktif(self) -> list[dict]:
        """Pasien yang sudah dinonaktifkan — supaya keputusannya bisa ditinjau ulang."""
        rows = self.db.execute(
            select(Pasien).where(Pasien.is_active.is_(False))
            .order_by(Pasien.nonaktif_at.desc())
        ).scalars().all()
        out = []
        for p in rows:
            tujuan = self.db.get(Pasien, p.digabung_ke_id_pasien) if p.digabung_ke_id_pasien else None
            out.append({
                "id_pasien": p.id_pasien, "no_rm": p.no_rm, "nama": p.nama,
                "alasan": p.nonaktif_alasan or "", "nonaktif_at": p.nonaktif_at,
                "nik_lama": p.nomor_ktp_lama or "",
                "tujuan": f"{tujuan.nama} ({tujuan.no_rm})" if tujuan else "",
                "riwayat": self._jumlah_riwayat(p.id_pasien),
            })
        return out

    def list_dismissed(self) -> list[dict]:
        rows = self.db.execute(
            select(PasienDuplikatDismiss).order_by(PasienDuplikatDismiss.id_dismiss.desc())
        ).scalars().all()
        out = []
        for r in rows:
            pa = self.db.get(Pasien, r.id_pasien_a)
            pb = self.db.get(Pasien, r.id_pasien_b)
            out.append({
                "id_a": r.id_pasien_a, "id_b": r.id_pasien_b,
                "nama_a": pa.nama if pa else "(terhapus)",
                "nama_b": pb.nama if pb else "(terhapus)",
                "no_rm_a": pa.no_rm if pa else "—",
                "no_rm_b": pb.no_rm if pb else "—",
                "alasan": r.alasan or "", "created_at": r.created_at,
            })
        return out


__all__ = ["AuditPasienService", "AMBANG_MIRIP_DEFAULT"]
