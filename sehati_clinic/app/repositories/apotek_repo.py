"""
ApotekRepository — queries untuk apotek module.

- list antrian ANTRI_OBAT
- get resep + produk for kunjungan
- get produk for update (lock — anti race)
- update master_produk.stok_terkini
- suggested order analytics
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    MasterProduk,
    Pasien,
    TransaksiDetailProduk,
    TransaksiKasir,
)


class ApotekRepository:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # ANTRIAN ANTRI_OBAT
    # =========================================================================
    def list_antrian_obat(
        self, today: Optional[date] = None
    ) -> list[tuple[Kunjungan, Pasien, int]]:
        """
        List pasien ANTRI_OBAT hari ini + count item resep DIBAYAR.

        Return list of (Kunjungan, Pasien, jumlah_item_obat).
        """
        if today is None:
            today = date.today()

        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .where(Kunjungan.status_antrian == "ANTRI_OBAT")
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        rows = self.db.execute(stmt).all()

        from app.db.models.racikan import KunjunganRacikan as _KRC

        result = []
        for kunjungan, pasien in rows:
            n_item = self.db.execute(
                select(func.count(KunjunganResep.id_resep))
                .where(KunjunganResep.id_kunjungan == kunjungan.id_kunjungan)
                .where(KunjunganResep.status_item == "DIBAYAR")
            ).scalar() or 0
            # Racikan ikut dihitung — kalau tidak, kunjungan berisi racikan saja akan
            # tampil "0 item" di antrian apotek dan dikira tidak ada yang perlu disiapkan.
            n_racik = self.db.execute(
                select(func.count(_KRC.id_kunjungan_racikan))
                .where(_KRC.id_kunjungan == kunjungan.id_kunjungan)
                .where(_KRC.status_item == "DIBAYAR")
            ).scalar() or 0
            result.append((kunjungan, pasien, int(n_item) + int(n_racik)))
        return result

    # =========================================================================
    # DETAIL RESEP
    # =========================================================================
    def get_kunjungan_with_pasien(
        self, id_kunjungan: int
    ) -> Optional[tuple[Kunjungan, Pasien]]:
        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
        )
        row = self.db.execute(stmt).first()
        return (row[0], row[1]) if row else None

    def get_resep_for_apotek(
        self, id_kunjungan: int
    ) -> list[tuple[KunjunganResep, MasterProduk]]:
        """
        List resep di kunjungan ini (exclude BATAL) + master_produk.

        Untuk apotek, biasanya cuma yang DIBAYAR yang relevant. Tapi return
        semua (kecuali BATAL) supaya UI bisa show "ada item yang belum bayar".
        """
        stmt = (
            select(KunjunganResep, MasterProduk)
            .join(MasterProduk, KunjunganResep.id_produk == MasterProduk.id_produk)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .where(KunjunganResep.status_item != "BATAL")
            .order_by(KunjunganResep.id_resep.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def get_resep_dibayar_for_serah(
        self, id_kunjungan: int, only_ids: Optional[list[int]] = None
    ) -> list[KunjunganResep]:
        """List resep DIBAYAR di kunjungan ini — kandidat untuk diserahkan.

        `only_ids` (task #54): batasi ke baris tertentu untuk penyerahan SEBAGIAN.
        None = semua (perilaku lama, dipakai API v1 & alur 'serahkan semua').
        List kosong sengaja tetap berarti "tidak ada" — bukan "semua" — supaya
        permintaan tanpa satu pun centang tidak diam-diam menyerahkan seluruhnya.
        """
        stmt = (
            select(KunjunganResep)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .where(KunjunganResep.status_item == "DIBAYAR")
        )
        if only_ids is not None:
            if not only_ids:
                return []
            stmt = stmt.where(KunjunganResep.id_resep.in_(only_ids))
        return list(self.db.execute(stmt).scalars().all())

    def get_racikan_for_apotek(self, id_kunjungan: int) -> list:
        """Racikan di kunjungan ini (exclude BATAL) + bahannya.

        Return: list[(KunjunganRacikan, list[KunjunganRacikanBahan])]
        """
        from app.db.models.racikan import KunjunganRacikan, KunjunganRacikanBahan

        heads = self.db.execute(
            select(KunjunganRacikan)
            .where(KunjunganRacikan.id_kunjungan == id_kunjungan)
            .where(KunjunganRacikan.status_item != "BATAL")
            .order_by(KunjunganRacikan.id_kunjungan_racikan.asc())
        ).scalars().all()
        out = []
        for h in heads:
            bahan = self.db.execute(
                select(KunjunganRacikanBahan)
                .where(KunjunganRacikanBahan.id_kunjungan_racikan == h.id_kunjungan_racikan)
                .order_by(KunjunganRacikanBahan.id_kunjungan_racikan_bahan.asc())
            ).scalars().all()
            out.append((h, list(bahan)))
        return out

    def get_racikan_dibayar_for_serah(
        self, id_kunjungan: int, only_ids: Optional[list[int]] = None
    ) -> list:
        """Racikan DIBAYAR + bahannya — kandidat untuk diracik & diserahkan.

        `only_ids` (task #54) sama seperti pada resep: None = semua, list = pilihan.
        """
        rows = [
            (h, b) for (h, b) in self.get_racikan_for_apotek(id_kunjungan)
            if h.status_item == "DIBAYAR"
        ]
        if only_ids is not None:
            _sel = set(only_ids)
            rows = [(h, b) for (h, b) in rows if h.id_kunjungan_racikan in _sel]
        return rows

    # =========================================================================
    # STOK PRODUK — get for update (lock) & update
    # =========================================================================
    def get_produk_for_update(self, id_produk: int) -> Optional[MasterProduk]:
        """SELECT ... FOR UPDATE — lock row supaya 2 apoteker tidak bentrok."""
        stmt = (
            select(MasterProduk)
            .where(MasterProduk.id_produk == id_produk)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_stok_produk(
        self,
        produk: MasterProduk,
        delta: float,
    ) -> float:
        """
        Kurangi (atau tambah) stok_terkini. Return stok_akhir.

        `delta` negatif untuk potong (mis. delta=-2.0 untuk serahkan 2 unit).
        Stok diizinkan minus (filosofi klinik — operasional jangan diblok).
        """
        stok_lama = produk.stok_terkini or 0
        stok_baru = stok_lama + delta
        produk.stok_terkini = stok_baru
        self.db.flush()
        return stok_baru

    # =========================================================================
    # SUGGESTED ORDER — analytic query
    # =========================================================================
    def get_qty_terjual_per_produk(
        self,
        sejak: datetime,
    ) -> dict[int, float]:
        """
        Aggregate qty terjual per produk (dari transaksi_detail_produk)
        sejak tanggal tertentu. Return dict {id_produk: total_qty}.
        """
        stmt = (
            select(
                TransaksiDetailProduk.id_produk,
                func.sum(TransaksiDetailProduk.qty).label("total"),
            )
            .join(
                TransaksiKasir,
                TransaksiDetailProduk.id_transaksi == TransaksiKasir.id_transaksi,
            )
            .where(TransaksiKasir.waktu_bayar >= sejak)
            .group_by(TransaksiDetailProduk.id_produk)
        )
        rows = self.db.execute(stmt).all()
        return {int(row[0]): float(row[1] or 0) for row in rows}

    def list_all_produk_active(self) -> list[MasterProduk]:
        """List semua produk aktif (untuk suggested order analysis)."""
        stmt = (
            select(MasterProduk)
            .where(MasterProduk.is_active.is_(True))
            .order_by(MasterProduk.id_produk.asc())
        )
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["ApotekRepository"]
