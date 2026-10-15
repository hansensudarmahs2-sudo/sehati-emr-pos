"""Anggota sebuah SERIES treatment — SATU definisi (Audit T4-11, 2026-10-16).

Tidak ada kolom "id series". SOAP (`PemeriksaanService`) membuat rencana satu series secara
BERURUTAN dalam satu simpan: sesi 1 (di-flush lebih dulu), lalu sesi 2..N. Maka anggota series
yang sesi 1-nya R = rencana dengan kunci yang sama (pasien, treatment, kunjungan pembuat),
`id_rencana >= R`, dan `id_rencana <` sesi 1 BERIKUTNYA dengan kunci yang sama.

Dulu tiga tempat memakai "semua rencana dengan kunci itu" — benar selama satu kunjungan hanya
melahirkan SATU series per treatment. Dua series treatment yang sama di satu kunjungan (SOAP
berisi dua, atau reopen) membuat:
- harga sesi 1 = per_sesi × (N1 + N2) — sesi yang sudah dibayar ditagih lagi (kasir);
- pagar "sesi 1 lunas" memakai sesi 1 series LAIN — sesi 2 series yang belum dibayar lolos
  (series_service);
- void membatalkan sisa sesi series lain yang sudah lunas (kasir, jalur bayar-dulu).

Status rencana TIDAK disaring: harga paket ditetapkan oleh rencananya, dan tetap sama walau
sesi kemudian DONE/CANCELLED (nota & tampilan menghitung ulang sesudahnya).
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PasienRencanaTreatment as _PRT


def _kunci(r):
    return (_PRT.id_pasien == r.id_pasien, _PRT.id_treatment == r.id_treatment,
            _PRT.id_kunjungan_pembuat == r.id_kunjungan_pembuat)


def sesi1_dari(db: Session, rencana) -> Optional[_PRT]:
    """Sesi 1 dari series tempat `rencana` berada (rencana itu sendiri bila sesi 1)."""
    if (rencana.urutan_sesi or 1) <= 1:
        return rencana
    if not rencana.id_kunjungan_pembuat:
        return None
    return db.execute(
        select(_PRT).where(*_kunci(rencana))
        .where(_PRT.urutan_sesi == 1)
        .where(_PRT.id_rencana < rencana.id_rencana)
        .order_by(_PRT.id_rencana.desc()).limit(1)
    ).scalar_one_or_none()


def _filter_anggota(sesi1):
    berikut = (select(func.min(_PRT.id_rencana)).where(*_kunci(sesi1))
               .where(_PRT.urutan_sesi == 1)
               .where(_PRT.id_rencana > sesi1.id_rencana)).scalar_subquery()
    return (*_kunci(sesi1), _PRT.id_rencana >= sesi1.id_rencana,
            (berikut.is_(None)) | (_PRT.id_rencana < berikut))


def jumlah_sesi(db: Session, sesi1) -> int:
    """Banyak sesi dalam series ini (≥ 1)."""
    return int(db.execute(select(func.count(_PRT.id_rencana))
                          .where(*_filter_anggota(sesi1))).scalar() or 1)


def anggota(db: Session, sesi1) -> list:
    """Semua rencana series ini (sesi 1..N)."""
    return list(db.execute(select(_PRT).where(*_filter_anggota(sesi1))
                           .order_by(_PRT.id_rencana)).scalars().all())
