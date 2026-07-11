"""
Transaksi models — kasir, detail produk, pembayaran.

Tabel:
- transaksi_kasir (1 baris per pembayaran)
- transaksi_detail_produk (N baris produk per transaksi)
- transaksi_pembayaran (N baris metode pembayaran per transaksi — split payment ready)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    DECIMAL,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    TIMESTAMP,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransaksiKasir(Base):
    """Tabel `transaksi_kasir` — mesin induk uang (1 per pembayaran)."""

    __tablename__ = "transaksi_kasir"

    id_transaksi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=True
    )
    id_staf_kasir: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )

    rincian_tagihan: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Snapshot rincian saat cetak struk (untuk reprint)",
    )
    subtotal: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True
    )
    nominal_diskon: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True
    )
    keterangan_promo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_tagihan: Mapped[float] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=False
    )

    # #362D Membership Activation Financial Flow
    id_membership_aktivasi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_membership.id_membership"), nullable=True,
        comment="FK master_membership kalau transaksi ini juga aktivasi membership",
    )
    nominal_aktivasi_membership: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True,
    )

    waktu_bayar: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    # =========================================================================
    # VOID PEMBAYARAN (DEC-063, #364) — Phase 1
    # Schema disiapkan untuk Phase 2 authorization (PIN/TOKEN/QUEUE).
    # Phase 1: void_approved_by_id_staf = void_by_id_staf (auto-approve).
    # =========================================================================
    status_transaksi: Mapped[str] = mapped_column(
        String(20), default="BAYAR", server_default="BAYAR", nullable=False,
        comment="BAYAR (default) atau VOID",
    )
    void_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    void_by_id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
    )
    void_reason_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    void_reason_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    void_approved_by_id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
    )
    void_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    void_approval_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    late_void: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False,
        comment="TRUE kalau force past-day void",
    )

    # P0-2 (AUDIT_SEHATI_2026-07-10): backstop anti double-submit. Token intent
    # pembayaran per-submit (bukan per-kunjungan → split billing tetap boleh).
    # UNIQUE via index uq_transaksi_kasir_idempotency_key; NULL boleh duplikat.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # =========================================================================
    # FINANCE BRIDGE (M-FIN-1, Tier 1) — kebutuhan Finance Module (Kontrak v2)
    # doc_number = referensi jurnal stabil (TRX-YYYY-MM-######).
    # updated_at = auto-bump untuk sync incremental (tangkap void/koreksi).
    # =========================================================================
    doc_number: Mapped[Optional[str]] = mapped_column(
        String(30), unique=True, nullable=True,
        comment="Nomor dokumen stabil TRX-YYYY-MM-###### (referensi jurnal Finance)",
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=True,
    )

    # FINANCE BRIDGE (M-FIN-4, Tier 3, DORMANT) — PPN penjualan (aktif saat PKP)
    dpp: Mapped[Optional[float]] = mapped_column(
        DECIMAL(14, 2), nullable=True,
        comment="Dasar Pengenaan Pajak (Rp). NULL/0 utk non-PKP.",
    )
    ppn: Mapped[Optional[float]] = mapped_column(
        DECIMAL(14, 2), default=0.00, server_default="0.00", nullable=True,
        comment="PPN keluaran (Rp). 0 utk non-PKP.",
    )
    is_kena_ppn: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, server_default="0", nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<TransaksiKasir(id={self.id_transaksi}, total={self.total_tagihan}, "
            f"status={self.status_transaksi})>"
        )


class TransaksiDetailProduk(Base):
    """Tabel `transaksi_detail_produk` — rincian produk per transaksi."""

    __tablename__ = "transaksi_detail_produk"

    id_detail: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_transaksi: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=False
    )
    id_produk: Mapped[int] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=False
    )
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    harga_satuan: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)

    # DEC-063 — Per-item reverse stok saat void
    # NULL/0 = tidak reverse (klinik tanggung loss)
    # 1 = reverse stok produk ke master_produk.stok_terkini
    void_reverse_stok: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, server_default="0", nullable=True,
    )

    # FINANCE BRIDGE (M-FIN-1, Tier 1)
    # diskon_item = alokasi diskon header ke item (pro-rata) untuk margin per lini.
    # hpp_satuan  = snapshot HPP per unit saat jual (COGS; tahan perubahan master).
    diskon_item: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True,
    )
    hpp_satuan: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
    )


class TransaksiDetailTindakan(Base):
    """Tabel `transaksi_detail_tindakan` — rincian treatment per transaksi (M-FIN-2, Opsi A).

    Simetris dengan transaksi_detail_produk. Menautkan treatment yang ditagih ke
    transaksi pembayaran + snapshot harga/diskon/BHP per treatment (kebutuhan Finance).
    """

    __tablename__ = "transaksi_detail_tindakan"

    id_detail_tindakan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_transaksi: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=False
    )
    id_kunjungan_tindakan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_tindakan.id_kunjungan_tindakan"), nullable=True,
        comment="Eksekusi treatment terkait (opsional).",
    )
    id_treatment: Mapped[int] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=False
    )
    qty: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0", nullable=False)
    harga_satuan: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    diskon_item: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True,
    )
    subtotal: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    bhp_satuan: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="Snapshot BHP per pakai saat jual (COGS treatment).",
    )


class TransaksiPembayaran(Base):
    """Tabel `transaksi_pembayaran` — metode bayar (split payment ready).

    Satu transaksi bisa punya N pembayaran (misal sebagian tunai + QRIS).
    """

    __tablename__ = "transaksi_pembayaran"

    id_pembayaran: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_transaksi: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=False
    )
    metode_bayar: Mapped[str] = mapped_column(String(50), nullable=False)
    nominal: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)

    # FINANCE BRIDGE (M-FIN-4, Tier 3) — tanggal settlement EDC/QRIS ke bank (opsional)
    tgl_settle: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class TransaksiRefund(Base):
    """Tabel `transaksi_refund` — pengembalian atas transaksi lunas (M-FIN-4, G9).

    Beda dari VOID (pembatalan penuh via status_transaksi). Refund = pengembalian
    (mungkin sebagian) atas transaksi yang sudah BAYAR. Untuk jurnal REFUND di Finance.
    """

    __tablename__ = "transaksi_refund"

    id_refund: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_transaksi: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=False,
        comment="Transaksi asal (yang di-refund).",
    )
    doc_number_refund: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tgl_refund: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )
    nilai_refund: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    metode_refund: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    alasan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    id_staf_refund: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )


class KasirClosing(Base):
    """Tabel `kasir_closing` — sesi shift kasir (Buka Kasir -> Tutup Kasir).

    Kasir-1 (Tutup Kasir / Rekonsiliasi). Satu baris per sesi shift kasir.
    Siklus hidup status:
    - OPEN   : dibuat saat "Buka Kasir" — set modal_awal + shift_mulai.
    - CLOSED : dilengkapi saat "Tutup Kasir" — counted fisik per metode,
               selisih, shift_tutup.

    Anchor expected = shift_mulai baris ini (bukan master_staf.waktu_mulai_shift),
    sehingga rekonsiliasi independen dari waktu login.

    Detail per metode disimpan sebagai JSON (keputusan dr. Hansen):
        detail_metode = [
            {"metode_bayar": "TUNAI",  "expected": 0, "counted": 0, "selisih": 0},
            {"metode_bayar": "QRIS",   "expected": 0, "counted": 0, "selisih": 0},
        ]
    Catatan TUNAI: expected sudah termasuk modal_awal (expected_laci).
    Hanya transaksi status_transaksi='BAYAR' yang dihitung (VOID di-exclude).
    """

    __tablename__ = "kasir_closing"

    id_closing: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_staf_kasir: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False,
        comment="Kasir pemilik sesi shift ini",
    )

    # ----- Siklus shift -----
    shift_mulai: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        comment="Waktu Buka Kasir = anchor agregasi expected",
    )
    shift_tutup: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="Waktu Tutup Kasir (NULL selama status OPEN)",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", server_default="OPEN", nullable=False,
        comment="OPEN (sedang berjalan) atau CLOSED (sudah ditutup)",
    )

    # ----- Modal & rekonsiliasi -----
    modal_awal: Mapped[float] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=False,
        comment="Kas awal laci (float) di-set saat Buka Kasir",
    )
    total_expected: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="Total harapan sistem (termasuk modal_awal di TUNAI). Diisi saat tutup.",
    )
    total_counted: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="Total hitungan fisik kasir. Diisi saat tutup.",
    )
    total_selisih: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="total_counted - total_expected (+ lebih / - kurang). Diisi saat tutup.",
    )
    detail_metode: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="Rincian per metode [{metode_bayar, expected, counted, selisih}]",
    )
    catatan: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Wajib diisi bila total_selisih != 0",
    )

    # ----- Audit aktor -----
    id_staf_buka: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Staf yang melakukan Buka Kasir",
    )
    id_staf_tutup: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Staf yang melakukan Tutup Kasir",
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=True,
    )
