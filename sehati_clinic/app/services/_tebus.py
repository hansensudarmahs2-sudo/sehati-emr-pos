"""Penanda "sudah ditebus" untuk resep & racikan lama — SATU definisi.

Audit T2-7 (2026-10-13, Project_Memory/AUDIT_MENDALAM_2026-10-13.md): penanda dulu
"ADA salinan" — apa pun status salinannya. Salinan tebus yang kemudian DITUNDA
("sisakan" di kasir), di-void (BATAL), atau kunjungan tebusnya dibatalkan membuat resep
asli HILANG PERMANEN dari daftar tebus: salinannya sendiri tak pernah ditawarkan
(`id_resep_asal` terisi), aslinya tersembunyi. Satu kolom, dua arti (CLAUDE.md §4.1):
"pernah dicoba ditebus" ≠ "benar-benar ditebus".

Kini: sudah ditebus = ada salinan yang MASIH HIDUP — PENDING (sedang ditebus, mencegah
tebus ganda), DIBAYAR, atau DISERAHKAN — di kunjungan yang TIDAK dibatalkan.

Dipakai: ApotekService (daftar tebus resep & racikan), RacikanService.salin_racikan_ke_kunjungan,
dan pagar tebus resep di route apotek (T2-8). Penambah jalur tebus baru: pakai modul ini.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.db.models import Kunjungan, KunjunganResep
from app.db.models.racikan import KunjunganRacikan

SALINAN_HIDUP = ("PENDING", "DIBAYAR", "DISERAHKAN")


def _salinan_resep_hidup(kolom_id_asal):
    s, kj = aliased(KunjunganResep), aliased(Kunjungan)
    return (select(s.id_resep).join(kj, kj.id_kunjungan == s.id_kunjungan)
            .where(s.id_resep_asal == kolom_id_asal)
            .where(s.status_item.in_(SALINAN_HIDUP))
            .where(kj.status_antrian != "BATAL"))


def _salinan_racikan_hidup(kolom_id_asal):
    s, kj = aliased(KunjunganRacikan), aliased(Kunjungan)
    return (select(s.id_kunjungan_racikan).join(kj, kj.id_kunjungan == s.id_kunjungan)
            .where(s.id_kunjungan_racikan_asal == kolom_id_asal)
            .where(s.status_item.in_(SALINAN_HIDUP))
            .where(kj.status_antrian != "BATAL"))


def resep_sudah_ditebus_expr(kolom_id_resep):
    """EXISTS berkorelasi untuk dipakai di WHERE daftar tebus."""
    return _salinan_resep_hidup(kolom_id_resep).exists()


def racikan_sudah_ditebus_expr(kolom_id_racikan):
    return _salinan_racikan_hidup(kolom_id_racikan).exists()


def resep_sudah_ditebus(db: Session, id_resep: int) -> bool:
    return db.execute(_salinan_resep_hidup(id_resep).limit(1)).first() is not None


def racikan_sudah_ditebus(db: Session, id_racikan: int) -> bool:
    return db.execute(_salinan_racikan_hidup(id_racikan).limit(1)).first() is not None
