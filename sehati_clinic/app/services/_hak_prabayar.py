"""Hak tindakan PRABAYAR — SATU definisi (bayar dulu tahap 4, RENCANA_BAYAR_DULU_TAHAP4.md).

Hak lahir di `TreatmentService.simpan_sebagai_hak` (T4-1): tindakan yang sudah dibayar di
muka lalu tidak dikerjakan → `pasien_rencana_treatment` ber-`sumber_rencana = PRABAYAR`,
`id_referensi_sumber` = tindakan asalnya, `tgl_target_akhir` = tanggal bayar + 6 bulan.

Pemakai (jangan menulis ulang aturannya di tempat lain — CLAUDE.md §4.1):
- `SeriesService.list_active_for_pasien` / `use_session` (T4-2) — berlaku atau tidak;
- `KasirService._compute_charge` (T4-2) — hak yang dipakai = Rp 0 (`adalah_hak`,
  `sesi1_pernah_lunas`);
- `_batal_tindakan.bereskan_satu_tindakan` (T4-2) — sesi 1 yang pernah lunas tidak
  membatalkan series-nya bila dipakai lagi lalu di-Batalkan;
- refund per tindakan & daftar Finance (T4-3, T4-5) — berlaku + nilai.

Kedaluwarsa dihitung dari TANGGAL, tidak ada penulis status `EXPIRED` dan tidak ada job
latar (gaya proyek: status tidak diubah diam-diam oleh jam). Hari terakhir masih berlaku.
⚠ Hanya untuk PRABAYAR: `tgl_target_akhir` series dokter TIDAK ditegakkan (keputusan
rancangan T4 §3) — jangan memanggil `berlaku()` untuk rencana sumber lain.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KunjunganTindakan, TransaksiDetailTindakan, TransaksiKasir
from app.db.models._enums import SumberRencanaEnum


def adalah_hak(rencana) -> bool:
    s = getattr(rencana, "sumber_rencana", None)
    return getattr(s, "value", s) == SumberRencanaEnum.PRABAYAR.value


def berlaku(rencana, hari_ini: Optional[date] = None) -> bool:
    """Hak masih boleh dipakai / direfund pada `hari_ini` (default: hari ini)."""
    akhir = rencana.tgl_target_akhir
    return akhir is None or (hari_ini or date.today()) <= akhir


def sisa_hari(rencana, hari_ini: Optional[date] = None) -> Optional[int]:
    if rencana.tgl_target_akhir is None:
        return None
    return (rencana.tgl_target_akhir - (hari_ini or date.today())).days


def nilai(db: Session, rencana) -> Optional[Decimal]:
    """Nilai BERSIH yang dibayar untuk tindakan asal hak ini = snapshot
    `transaksi_detail_tindakan.subtotal` transaksi pembayarnya (sudah dikurangi porsi
    diskon). Tidak ada rumus baru. None bila snapshot tidak ditemukan."""
    if not rencana.id_referensi_sumber:
        return None
    return db.execute(
        select(TransaksiDetailTindakan.subtotal)
        .join(KunjunganTindakan, (KunjunganTindakan.id_kunjungan_tindakan
                                  == TransaksiDetailTindakan.id_kunjungan_tindakan)
              & (KunjunganTindakan.id_transaksi == TransaksiDetailTindakan.id_transaksi))
        .where(KunjunganTindakan.id_kunjungan_tindakan == rencana.id_referensi_sumber)
    ).scalars().first()


def sesi1_pernah_lunas(db: Session, rencana, kecuali_id_tindakan: Optional[int] = None) -> bool:
    """Sesi 1 series (pembawa harga paket) yang tindakannya pernah LUNAS lalu disimpan
    sebagai hak (T4-1, keputusan P2): ada tindakan BATAL di rencana ini yang ditagih
    transaksi BAYAR. BATAL tanpa transaksi (Batalkan sebelum bayar) atau transaksinya VOID
    BUKAN bukti. `kecuali_id_tindakan` = tindakan yang sedang dinilai (bukan bukti dirinya)."""
    if (rencana.urutan_sesi or 1) != 1:
        return False
    q = (select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
         .join(TransaksiKasir, TransaksiKasir.id_transaksi == KunjunganTindakan.id_transaksi)
         .where(KunjunganTindakan.id_rencana == rencana.id_rencana)
         .where(KunjunganTindakan.status_tindakan == "BATAL")
         .where(TransaksiKasir.status_transaksi == "BAYAR"))
    if kecuali_id_tindakan is not None:
        q = q.where(KunjunganTindakan.id_kunjungan_tindakan != kecuali_id_tindakan)
    return (db.execute(q).scalar() or 0) > 0
