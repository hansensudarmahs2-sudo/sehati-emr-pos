"""
KasirClosingService — Buka Kasir / Tutup Kasir / Rekonsiliasi (Kasir-1).

Alur (DEC-074 era, keputusan dr. Hansen 2026-06-27):
1. buka_kasir(id_staf_kasir, modal_awal): buat sesi `kasir_closing` status OPEN,
   set shift_mulai = anchor agregasi + modal_awal (kas laci). Cegah double-open.
2. get_closing_preview(id_staf_kasir): hitung EXPECTED per metode sejak shift_mulai,
   EXCLUDE transaksi VOID (status_transaksi='BAYAR' saja — perbaiki gap rekap lama).
   TUNAI: expected_laci = modal_awal + penjualan_tunai.
3. tutup_kasir(...): terima counted fisik per metode, hitung selisih = counted-expected,
   simpan closing record (detail per metode = JSON), status -> CLOSED.

Metode kanonik: TUNAI / QRIS / DEBIT / KREDIT / TRANSFER.
Anchor expected = kasir_closing.shift_mulai (independen dari login),
basis waktu = datetime.now() (WIB, konsisten dengan rekap_shift / waktu_mulai_shift; A4/DEC-052).

Audit: BUKA_KASIR, TUTUP_KASIR. Tidak ada PDF disimpan (slip Z-report transien).
"""

from datetime import datetime, time as _time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KasirClosing, TransaksiKasir, TransaksiPembayaran
from app.repositories.staf_repo import StafRepository
from app.services.audit_service import AuditService


# Urutan kanonik untuk tampilan + agregasi
METODE_KANONIK = ["TUNAI", "QRIS", "DEBIT", "KREDIT", "TRANSFER"]


class KasirClosingService:
    def __init__(self, db: Session):
        self.db = db
        self.staf_repo = StafRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # HELPERS
    # =========================================================================
    def get_open_session(self, id_staf_kasir: int) -> Optional[KasirClosing]:
        """Sesi kasir status OPEN milik kasir ini (paling baru), atau None."""
        stmt = (
            select(KasirClosing)
            .where(KasirClosing.id_staf_kasir == id_staf_kasir)
            .where(KasirClosing.status == "OPEN")
            .order_by(KasirClosing.id_closing.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _penjualan_per_metode(self, id_staf_kasir: int, sejak: datetime) -> dict:
        """Total penjualan SISTEM per metode sejak `sejak`, EXCLUDE VOID.

        Hanya transaksi status_transaksi='BAYAR' yang dihitung — ini yang
        membenahi gap rekap lama (aggregate_pembayaran_shift tidak exclude VOID).
        Return dict {METODE: Decimal}.
        """
        stmt = (
            select(
                TransaksiPembayaran.metode_bayar,
                func.sum(TransaksiPembayaran.nominal),
            )
            .join(
                TransaksiKasir,
                TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi,
            )
            .where(TransaksiKasir.id_staf_kasir == id_staf_kasir)
            .where(TransaksiKasir.waktu_bayar >= sejak)
            .where(TransaksiKasir.status_transaksi == "BAYAR")
            .group_by(TransaksiPembayaran.metode_bayar)
        )
        rows = self.db.execute(stmt).all()
        result = {m: Decimal("0") for m in METODE_KANONIK}
        for metode, total in rows:
            key = (metode or "").upper()
            result[key] = result.get(key, Decimal("0")) + Decimal(str(total or 0))
        return result

    def _build_rows(self, penjualan: dict, modal: Decimal) -> tuple:
        """Bangun daftar expected per metode + total_expected.

        TUNAI: expected = modal_awal + penjualan_tunai (expected_laci).
        Non-tunai: expected = penjualan sistem.
        Return (rows, total_expected).
        """
        rows = []
        total_expected = Decimal("0")
        for metode in METODE_KANONIK:
            jual = penjualan.get(metode, Decimal("0"))
            is_tunai = metode == "TUNAI"
            exp = (modal + jual) if is_tunai else jual
            total_expected += exp
            rows.append({
                "metode_bayar": metode,
                "penjualan_sistem": jual,
                "modal_awal": modal if is_tunai else Decimal("0"),
                "expected": exp,
            })
        return rows, total_expected

    # =========================================================================
    # BUKA KASIR
    # =========================================================================
    def buka_kasir(
        self,
        id_staf_kasir: int,
        modal_awal,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> KasirClosing:
        """Buat sesi kasir OPEN dengan modal awal. Cegah double-open."""
        existing = self.get_open_session(id_staf_kasir)
        if existing is not None:
            raise HTTPException(
                400,
                f"Sudah ada sesi kasir OPEN (#{existing.id_closing}). "
                f"Tutup kasir dulu sebelum buka sesi baru.",
            )
        modal = Decimal(str(modal_awal or 0))
        if modal < 0:
            raise HTTPException(400, "Modal awal tidak boleh negatif.")

        now = datetime.now()
        actor = actor_id_staf or id_staf_kasir
        sesi = KasirClosing(
            id_staf_kasir=id_staf_kasir,
            shift_mulai=now,
            status="OPEN",
            modal_awal=modal,
            id_staf_buka=actor,
        )
        self.db.add(sesi)
        self.db.flush()
        self.audit.log(
            aksi="BUKA_KASIR",
            id_staf=actor,
            tabel_target="kasir_closing",
            id_target=sesi.id_closing,
            data_baru={"modal_awal": float(modal), "shift_mulai": now.isoformat()},
            keterangan=f"Buka kasir kasir_id={id_staf_kasir}, modal Rp {modal}",
            request=request,
        )
        self.db.commit()
        self.db.refresh(sesi)
        return sesi

    # =========================================================================
    # PREVIEW TUTUP KASIR
    # =========================================================================
    def get_closing_preview(self, id_staf_kasir: int) -> dict:
        """Tampilkan expected per metode untuk sesi OPEN kasir ini."""
        sesi = self.get_open_session(id_staf_kasir)
        if sesi is None:
            raise HTTPException(
                400, "Belum ada sesi kasir OPEN. Lakukan 'Buka Kasir' dulu."
            )
        modal = Decimal(str(sesi.modal_awal or 0))
        penjualan = self._penjualan_per_metode(id_staf_kasir, sesi.shift_mulai)
        rows, total_expected = self._build_rows(penjualan, modal)
        return {
            "id_closing": sesi.id_closing,
            "id_staf_kasir": id_staf_kasir,
            "shift_mulai": sesi.shift_mulai,
            "modal_awal": modal,
            "metode": rows,
            "total_expected": total_expected,
        }

    def _pending_antrian_hari_ini(self) -> dict:
        """Hitung pasien yang MASIH aktif/antri hari ini (belum settle), per status.

        Aktif = semua `status_antrian` KECUALI terminal (COMPLETED, BATAL).
        Dipakai guard `tutup_kasir` (hard block, keputusan 2026-07-10): status antri
        yang tertinggal tak auto-transisi, jadi harus diselesaikan / diubah FO dulu.
        """
        from datetime import date as _date
        from sqlalchemy import func as _f, select as _sel
        from app.db.models import Kunjungan

        _TERMINAL = ("COMPLETED", "BATAL")
        rows = self.db.execute(
            _sel(Kunjungan.status_antrian, _f.count())
            .where(
                _f.date(Kunjungan.tgl_kunjungan) == _date.today(),
                Kunjungan.status_antrian.notin_(_TERMINAL),
            )
            .group_by(Kunjungan.status_antrian)
        ).all()
        return {s: int(n) for s, n in rows if s is not None}

    # =========================================================================
    # TUTUP KASIR
    # =========================================================================
    def tutup_kasir(
        self,
        id_staf_kasir: int,
        counted_per_metode: dict,
        catatan: Optional[str] = None,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> KasirClosing:
        """Tutup sesi: hitung selisih per metode + total, simpan closing record.

        counted_per_metode = {"TUNAI": 500000, "QRIS": 0, ...} (boleh sebagian).
        Catatan WAJIB kalau total_selisih != 0.
        """
        sesi = self.get_open_session(id_staf_kasir)
        if sesi is None:
            raise HTTPException(400, "Belum ada sesi kasir OPEN untuk ditutup.")

        # HARD BLOCK (2026-07-10): tolak tutup kasir kalau masih ada pasien antri hari ini.
        # Status antri yang tertinggal tak auto-transisi → wajib diselesaikan (bayar/serah)
        # atau FO ubah status pasien yang tersangkut dulu.
        pending = self._pending_antrian_hari_ini()
        if pending:
            ringkas = ", ".join(f"{s}={n}" for s, n in sorted(pending.items()))
            raise HTTPException(
                400,
                f"Masih ada pasien belum selesai hari ini ({ringkas}). "
                "Selesaikan (bayar / serah obat) dulu, atau minta FO mengubah status "
                "pasien yang tersangkut, sebelum menutup kasir.",
            )

        modal = Decimal(str(sesi.modal_awal or 0))
        penjualan = self._penjualan_per_metode(id_staf_kasir, sesi.shift_mulai)

        detail = []
        total_expected = Decimal("0")
        total_counted = Decimal("0")
        for metode in METODE_KANONIK:
            jual = penjualan.get(metode, Decimal("0"))
            is_tunai = metode == "TUNAI"
            exp = (modal + jual) if is_tunai else jual
            counted = Decimal(str(counted_per_metode.get(metode, 0) or 0))
            if counted < 0:
                raise HTTPException(400, f"Counted {metode} tidak boleh negatif.")
            selisih = counted - exp
            total_expected += exp
            total_counted += counted
            detail.append({
                "metode_bayar": metode,
                "penjualan_sistem": float(jual),
                "modal_awal": float(modal) if is_tunai else 0.0,
                "expected": float(exp),
                "counted": float(counted),
                "selisih": float(selisih),
                # Setoran tunai = porsi penjualan yg disetor (counted - modal). Hanya TUNAI.
                "setoran_tunai": float(counted - modal) if is_tunai else None,
            })

        total_selisih = total_counted - total_expected
        catatan_clean = (catatan or "").strip()
        if total_selisih != 0 and not catatan_clean:
            raise HTTPException(
                400,
                f"Selisih total Rp {total_selisih} (tidak nol) — catatan wajib diisi.",
            )

        now = datetime.now()
        sesi.shift_tutup = now
        sesi.status = "CLOSED"
        sesi.total_expected = total_expected
        sesi.total_counted = total_counted
        sesi.total_selisih = total_selisih
        sesi.detail_metode = detail
        sesi.catatan = catatan_clean or None
        sesi.id_staf_tutup = actor_id_staf or id_staf_kasir
        self.db.flush()

        self.audit.log(
            aksi="TUTUP_KASIR",
            id_staf=actor_id_staf or id_staf_kasir,
            tabel_target="kasir_closing",
            id_target=sesi.id_closing,
            data_baru={
                "total_expected": float(total_expected),
                "total_counted": float(total_counted),
                "total_selisih": float(total_selisih),
                "detail_metode": detail,
            },
            keterangan=f"Tutup kasir #{sesi.id_closing}, selisih total Rp {total_selisih}",
            request=request,
        )
        self.db.commit()
        self.db.refresh(sesi)
        return sesi

    # =========================================================================
    # LAPORAN OWNER (dipakai Langkah 4)
    # =========================================================================
    def list_closings(
        self,
        tgl=None,
        id_staf_kasir: Optional[int] = None,
    ) -> list:
        """Daftar closing CLOSED, opsional filter tanggal (shift_tutup) + kasir."""
        stmt = select(KasirClosing).where(KasirClosing.status == "CLOSED")
        if id_staf_kasir is not None:
            stmt = stmt.where(KasirClosing.id_staf_kasir == id_staf_kasir)
        if tgl is not None:
            start = datetime.combine(tgl, _time.min)
            end = datetime.combine(tgl, _time.max)
            stmt = stmt.where(KasirClosing.shift_tutup >= start)
            stmt = stmt.where(KasirClosing.shift_tutup <= end)
        stmt = stmt.order_by(KasirClosing.shift_tutup.desc())
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["KasirClosingService", "METODE_KANONIK"]
