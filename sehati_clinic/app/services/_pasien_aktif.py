"""Pagar: kunjungan / booking BARU tidak boleh dibuat untuk pasien NONAKTIF.

Audit mendalam tahap 1 (T1-B, 2026-10-13, Project_Memory/AUDIT_MENDALAM_2026-10-13.md):
pasien yang sudah DIGABUNG masih bisa di-booking dan di-check-in, dan check-in
membuat kunjungan di ID duplikat — riwayatnya terpecah lagi, persis masalah yang
diselesaikan penggabungan, tanpa error apa pun. Sebelum pagar ini hanya tebus resep
apotek yang menolak pasien nonaktif.

Dipakai SEMUA pembuat kunjungan untuk pasien yang sudah ada:
  - KunjunganService.kunjungan_lama   (antrian Cari Pasien, booking check-in, API v1)
  - KunjunganService.beli_produk_lengkap
  - BookingService._get_pasien_membership (buat booking & check-in)
⚠ Kalau menambah jalur baru yang membuat kunjungan untuk pasien lama, panggil ini.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Pasien


def pastikan_pasien_aktif(db: Session, pasien: Pasien) -> None:
    """409 bila pasien nonaktif — pesannya menunjuk pasien yang BERTAHAN (kalau
    hasil penggabungan) supaya petugas langsung tahu harus memakai siapa."""
    if pasien.is_active:
        return
    tujuan = db.get(Pasien, pasien.digabung_ke_id_pasien) if pasien.digabung_ke_id_pasien else None
    arah = (f" — sudah digabung ke {tujuan.nama} (RM {tujuan.no_rm}). Pakai pasien itu"
            if tujuan is not None else "")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(f"Pasien {pasien.nama} (RM {pasien.no_rm}) sudah NONAKTIF{arah}. "
                f"Kunjungan/booking baru tidak boleh dibuat untuk pasien nonaktif — "
                f"riwayatnya akan terpecah lagi."),
    )
