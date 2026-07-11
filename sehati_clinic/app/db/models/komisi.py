"""
Komisi model — ledger komisi staf (Dokter & Perawat).

Tabel:
- komisi_ledger : 1 baris = 1 komisi diperoleh (snapshot saat transaksi dibayar).
                  Ref KOMISI_MODULE_DESIGN.md §4 + DEC-087.

Prinsip:
- SNAPSHOT: nilai komisi dikunci saat bayar (ubah rate master di masa depan tidak mengubah baris ini).
- Basis tanggal = tanggal bayar (kasir). VOID transaksi → status baris jadi VOID.
- sumber/role/status = VARCHAR (fleksibel; divalidasi di service layer, pola StatusAntrianEnum).
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DECIMAL,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KomisiLedger(Base):
    """Baris komisi (snapshot) — 1 per pendapatan komisi per staf per item dibayar."""

    __tablename__ = "komisi_ledger"

    id_komisi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Basis waktu = tanggal bayar (date dari waktu_bayar). Index utk filter periode.
    tanggal: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Sumber transaksi
    id_transaksi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=True, index=True
    )
    id_kunjungan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=True
    )
    id_pasien: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=True
    )

    # Penerima komisi + rolenya saat itu
    id_staf: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False, index=True
    )
    role_snapshot: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="DOKTER / PERAWAT (snapshot)"
    )

    # Asal komisi
    sumber: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="TINDAKAN / PRODUK"
    )
    id_ref: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="id_kunjungan_tindakan atau id_resep"
    )
    nama_item: Mapped[Optional[str]] = mapped_column(
        String(150), nullable=True, comment="Nama treatment/produk (snapshot)"
    )

    # Angka (snapshot)
    harga_jual: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False, server_default="0")
    komisi_tipe: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="PERSEN_HARGA / PERSEN_MARGIN / NOMINAL (snapshot)"
    )
    komisi_value: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True, comment="Nilai rate saat itu (snapshot)"
    )
    komisi_nominal: Mapped[float] = mapped_column(
        DECIMAL(12, 2), nullable=False, server_default="0", comment="Rupiah komisi (snapshot)"
    )

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="AKTIF", comment="AKTIF / VOID"
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<KomisiLedger(id={self.id_komisi}, tgl={self.tanggal}, staf={self.id_staf}, "
            f"{self.sumber} {self.komisi_nominal} {self.status})>"
        )
