"""
StokLot — inventory per-lot (batch + ED) untuk produk retail DAN bahan/BHP.

Ref INVENTORY_LOT_ED_MODULE_DESIGN.md §3/§4 (P-L3). SATU tabel untuk produk & bahan
(kolom `tipe_item` + FK id_produk / id_bahan). FEFO: keluar dari ED terdekat dulu
(lot ED NULL = paling akhir). batch_no & tgl_ed BOLEH NULL (batch pembuka / kasus khusus).

Catatan konsistensi: `stok_terkini` (master_produk) & `stok_gudang_utama/kabin` (inventory_stok)
menjadi CACHE = Σ qty_sisa lot aktif per lokasi. Cache dipelihara saat depletion di-wire (P-L5/P-L6).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DECIMAL, Float, ForeignKey, Integer, String, TIMESTAMP, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StokLot(Base):
    __tablename__ = "stok_lot"

    id_lot: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tipe_item: Mapped[str] = mapped_column(String(10), nullable=False, comment="PRODUK / BAHAN")
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    id_bahan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True
    )
    lokasi: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="RETAIL / GUDANG_UTAMA / KABIN"
    )

    batch_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tgl_ed: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="Expired date (NULL diperbolehkan)")

    qty_masuk: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    qty_sisa: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")

    harga_terima: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True, comment="Harga saat barang datang (snapshot)"
    )
    id_receive: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pemesanan_receive.id_receive"), nullable=True
    )
    id_distributor: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_distributor.id_distributor"), nullable=True
    )

    tgl_masuk: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="AKTIF", comment="AKTIF / HABIS / EXPIRED / WRITEOFF"
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (f"<StokLot(id={self.id_lot}, {self.tipe_item} lok={self.lokasi} "
                f"batch={self.batch_no} ed={self.tgl_ed} sisa={self.qty_sisa} {self.status})>")


class KunjunganLotTerpakai(Base):
    """Jejak lot yang DIPOTONG saat serah obat — untuk restore ke lot ASLI saat void.

    P0-1/H2 (AUDIT_SEHATI_2026-07-10): diisi di `serahkan_obat` per lot FEFO yang
    dikonsumsi. Dibaca `_reverse_stok_per_item` supaya void mengembalikan qty ke lot
    ASLI (ED asli terjaga, FEFO tetap benar) alih-alih membuat lot 'VOID-RETURN' tgl_ed=NULL.
    `reversed_at` mencegah double-restore.
    """
    __tablename__ = "kunjungan_lot_terpakai"

    id_terpakai: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_produk: Mapped[int] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=False
    )
    id_lot: Mapped[int] = mapped_column(ForeignKey("stok_lot.id_lot"), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    # Task #54 — ASAL potongan, per ITEM. Tanpa ini, satu produk yang muncul di DUA
    # baris resep tidak bisa dibedakan saat void: reverse per item jadi menebak.
    # Keduanya NULL pada baris lama (jejak sebelum 2026-09-22) → dibaca dengan cara
    # lama (per produk). Tepat satu dari keduanya terisi pada baris baru.
    id_resep: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_resep.id_resep"), nullable=True
    )
    id_kunjungan_racikan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_racikan.id_kunjungan_racikan"), nullable=True
    )
    reversed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True,
        comment="Diisi saat qty sudah dikembalikan ke lot (void) — cegah double-restore.",
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (f"<KunjunganLotTerpakai(kunjungan={self.id_kunjungan} produk={self.id_produk} "
                f"lot={self.id_lot} qty={self.qty} reversed={self.reversed_at is not None})>")
