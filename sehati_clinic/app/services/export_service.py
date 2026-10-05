"""
ExportService — Owner Raw Data Export (C2).

Phase C2.1: Foundation
Phase C2.2: Dataset methods (11 datasets Tier 1+2)
Phase C2.3: Pack assembly + Tier 3 (SOAP, audit)
Phase C2.4: Data Dictionary
"""

import hashlib
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.core.csv_writer import dict_list_to_csv_bytes
from app.core.json_writer import dict_list_to_json_bytes
from app.core.zip_packer import ZipPacker
from app.services._export_columns import COLUMNS_METADATA
from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS
from app.services.audit_service import AuditService


WARNING_THRESHOLD_DAYS = 90
HARD_CAP_ROWS_TOTAL = 200_000


# =========================================================================
# PII Masking Helpers
# =========================================================================
# Dataset yang TIDAK ikut paket Finance (file-drop + tombol UI "Export ke Finance").
# `medical_soap_raw` dikeluarkan 2026-09-30: modul Finance tidak pernah membacanya
# (diverifikasi — `csv_loader.py` hanya membuka berkas 03, 05, 06, 11, 14), dan ia
# memuat anamnesa/pemeriksaan fisik/diagnosa. SOAP medis tidak punya urusan di paket
# keuangan; ia akan pindah ke clinical pack ber-PII-mask.
#
# ⚠ PENOMORAN BERKAS BERASAL DARI POSISI di DATASET_REGISTRY (`enumerate(..., 1)`).
# JANGAN menghapus entrinya dari registry — itu akan menggeser 13/14/15 menjadi
# 12/13/14, sedangkan loader Finance membuka `14_transaction_items_raw.csv` BERDASARKAN
# NAMA PERSIS. Entri tetap di tempatnya; yang disaring hanya penulisannya, sehingga
# paket punya lompatan nomor (11, 13, 14, 15) dan itu memang disengaja.
FINANCE_PACK_EXCLUDE = {"medical_soap_raw"}


def _mask_text(value: Optional[str], mask: bool, prefix: str = "PASIEN_HASH") -> Optional[str]:
    if value is None or value == "":
        return value
    if not mask:
        return value
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{digest}"


def _redact(value: Any, mask: bool, replacement: str = "(redacted)") -> Any:
    return replacement if (mask and value not in (None, "")) else value


def _iso(value) -> Optional[str]:
    """Safe datetime/date → ISO string. None passthrough."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _enum_value(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return str(value)


# =========================================================================
# ExportService
# =========================================================================
class ExportService:

    def __init__(self, db: Session):
        self.db = db

    # =====================================================================
    # PACK (stub C2.1, di-isi C2.3)
    # =====================================================================
    def generate_pack(
        self,
        period: str,
        tgl_dari: date,
        tgl_sampai: date,
        format: str = "csv",
        mask_pii: bool = False,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> tuple[bytes, str]:
        """
        Generate ZIP pack berisi semua dataset (lihat DATASET_REGISTRY) + README + DATA_DICTIONARY.

        Process:
        1. Loop DATASET_REGISTRY
        2. Call get_dataset(name, range, mask_pii) per entry
        3. Serialize ke CSV atau JSON (sesuai format param)
        4. Add ke ZipPacker dengan filename {NN}_{name}.{ext}
        5. Generate README.txt dengan metadata + row counts per file
        6. Add DATA_DICTIONARY.md (placeholder C2.4)

        Hard cap: kalau total row > HARD_CAP_ROWS_TOTAL, raise 413.
        """
        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")
        if format not in ("csv", "json"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "format harus csv atau json")

        packer = ZipPacker()
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        files_summary: list[dict] = []
        total_rows = 0

        # Loop semua dataset dalam registry
        for idx, entry in enumerate(self.DATASET_REGISTRY, start=1):
            name = entry["name"]
            method: Callable = getattr(self, entry["method"])
            columns = entry.get("default_columns")

            # Execute dataset query
            try:
                items = method(tgl_dari, tgl_sampai, mask_pii)
            except Exception as e:
                # Log error tapi jangan abort seluruh pack — tetap include error placeholder
                items = []
                error_note = f"ERROR loading dataset {name}: {e!s}"
                files_summary.append({
                    "filename": f"{idx:02d}_{name}.{format}",
                    "row_count": 0,
                    "description": f"⚠ {error_note}",
                })
                packer.add_file(
                    f"{idx:02d}_{name}_ERROR.txt",
                    error_note.encode("utf-8"),
                )
                continue

            row_count = len(items)
            total_rows += row_count

            # Serialize sesuai format
            if format == "csv":
                content_bytes = dict_list_to_csv_bytes(items, columns=columns)
            else:
                content_bytes = dict_list_to_json_bytes(items, pretty=True)

            filename = f"{idx:02d}_{name}.{format}"
            packer.add_file(filename, content_bytes)
            files_summary.append({
                "filename": filename,
                "row_count": row_count,
                "description": entry.get("description", ""),
            })

        # Hard cap check
        if total_rows > HARD_CAP_ROWS_TOTAL:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"Total rows ({total_rows}) > hard cap ({HARD_CAP_ROWS_TOTAL}). "
                f"Split rentang tanggal lebih kecil.",
            )

        # README dengan metadata + row counts per file
        packer.add_readme(
            title=f"Sehati Clinic — {period.title()} Pack",
            metadata={
                "period": period,
                "range": f"{tgl_dari} sd {tgl_sampai}",
                "format": format,
                "mask_pii": str(mask_pii),
                "datasets_count": len(self.DATASET_REGISTRY),
                "total_rows": total_rows,
                "actor_id_staf": str(actor_id_staf) if actor_id_staf else "(unknown)",
                "generated_utc": ts,
            },
            files_summary=files_summary,
        )

        # DATA_DICTIONARY.md (real — C2.4)
        md_text = self.generate_dictionary_markdown()
        packer.add_data_dictionary(md_text.encode("utf-8"))

        zip_bytes = packer.finalize()
        filename = f"sehati_pack_{period}_{tgl_dari}_to_{tgl_sampai}_{ts}.zip"

        self._audit_export_pack(
            actor_id_staf=actor_id_staf,
            period=period,
            tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
            format=format, mask_pii=mask_pii,
            file_count=packer.file_count,
            total_uncompressed=packer.total_uncompressed_bytes,
            request=request,
        )

        return zip_bytes, filename

    # =====================================================================
    # 01 — daily_operational_summary (Tier 1 Aggregate)
    # =====================================================================
    def export_daily_operational_summary(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import (
            Kunjungan, Pasien, PemeriksaanKlinis,
            KunjunganTindakan, KunjunganResep,
            TransaksiKasir, StatusTindakanEnum, StatusItemResepEnum,
        )
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        kunj = dict(self.db.execute(
            select(func.date(Kunjungan.tgl_kunjungan), func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.tgl_kunjungan >= start_dt)
            .where(Kunjungan.tgl_kunjungan <= end_dt)
            # Kunjungan retur (RETUR_PASIEN) bukan kunjungan klinis (keputusan 11.2).
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
            .group_by(func.date(Kunjungan.tgl_kunjungan))
        ).all())
        pas = dict(self.db.execute(
            select(func.date(Pasien.created_at), func.count(Pasien.id_pasien))
            .where(Pasien.created_at >= start_dt).where(Pasien.created_at <= end_dt)
            .group_by(func.date(Pasien.created_at))
        ).all())
        kons = dict(self.db.execute(
            select(func.date(Kunjungan.tgl_kunjungan), func.count(PemeriksaanKlinis.id_pemeriksaan))
            .join(Kunjungan, Kunjungan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            # Draf apoteker yang belum disetujui bukan konsultasi.
            .where(PemeriksaanKlinis.status_soap == "FINAL")
            .where(Kunjungan.tgl_kunjungan >= start_dt).where(Kunjungan.tgl_kunjungan <= end_dt)
            .group_by(func.date(Kunjungan.tgl_kunjungan))
        ).all())
        tind = dict(self.db.execute(
            select(func.date(KunjunganTindakan.waktu_selesai), func.count(KunjunganTindakan.id_kunjungan_tindakan))
            .where(KunjunganTindakan.waktu_selesai >= start_dt)
            .where(KunjunganTindakan.waktu_selesai <= end_dt)
            .where(KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI)
            .group_by(func.date(KunjunganTindakan.waktu_selesai))
        ).all())
        trx = {r[0]: (r[1], r[2], r[3]) for r in self.db.execute(
            select(
                func.date(TransaksiKasir.waktu_bayar),
                func.count(TransaksiKasir.id_transaksi),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0),
                func.coalesce(func.sum(TransaksiKasir.nominal_diskon), 0),
            )
            .where(TransaksiKasir.waktu_bayar >= start_dt)
            .where(TransaksiKasir.waktu_bayar <= end_dt)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(func.date(TransaksiKasir.waktu_bayar))
        ).all()}
        resep = dict(self.db.execute(
            select(func.date(Kunjungan.tgl_kunjungan), func.count(KunjunganResep.id_resep))
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganResep.id_kunjungan)
            .where(Kunjungan.tgl_kunjungan >= start_dt).where(Kunjungan.tgl_kunjungan <= end_dt)
            .where(KunjunganResep.status_item == StatusItemResepEnum.DIBAYAR)
            .group_by(func.date(Kunjungan.tgl_kunjungan))
        ).all())

        # T32: refund dibukukan di TANGGAL REFUND (bukan tanggal transaksi asal).
        from app.services import _refund_bukuan as _rb
        ref = _rb.refund_per_tanggal(self.db, start_dt, end_dt)

        items = []
        cur = tgl_dari
        while cur <= tgl_sampai:
            t_cnt, t_omz, t_dsk = trx.get(cur, (0, 0, 0))
            t_ref = ref.get(cur, 0)
            items.append({
                "tanggal": cur.isoformat(),
                "jumlah_kunjungan": int(kunj.get(cur, 0)),
                "jumlah_pasien_baru": int(pas.get(cur, 0)),
                "jumlah_konsul_dokter": int(kons.get(cur, 0)),
                "jumlah_tindakan_selesai": int(tind.get(cur, 0)),
                "jumlah_transaksi": int(t_cnt),
                "total_omzet": float(t_omz) - float(t_ref),
                "total_refund": float(t_ref),
                "total_diskon": float(t_dsk),
                "jumlah_resep_dibayar": int(resep.get(cur, 0)),
            })
            cur += timedelta(days=1)
        return items

    # =====================================================================
    # 02 — visits_raw (Tier 2)
    # =====================================================================
    def export_visits_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import Kunjungan, Pasien, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                Kunjungan.id_kunjungan, Kunjungan.tgl_kunjungan, Kunjungan.id_pasien,
                Pasien.no_rm, Pasien.nama, Kunjungan.status_antrian,
                Kunjungan.sumber_pendaftaran, Kunjungan.keluhan_utama,
                Kunjungan.id_staf_fo, MasterStaf.nama_staf, Kunjungan.created_at,
                Kunjungan.jenis_kunjungan,
            )
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            .outerjoin(MasterStaf, MasterStaf.id_staf == Kunjungan.id_staf_fo)
            .where(Kunjungan.tgl_kunjungan >= start_dt)
            .where(Kunjungan.tgl_kunjungan <= end_dt)
            .order_by(Kunjungan.tgl_kunjungan, Kunjungan.id_kunjungan)
        )
        return [
            {
                "id_kunjungan": int(r[0]),
                "tgl_kunjungan": _iso(r[1]),
                "id_pasien": int(r[2]) if r[2] else None,
                "no_rm": r[3],
                "nama_pasien": _mask_text(r[4], mask_pii),
                "status_antrian": r[5],
                "sumber_pendaftaran": r[6],
                "keluhan_utama": r[7],
                "id_staf_fo": int(r[8]) if r[8] else None,
                "nama_fo": r[9],
                "created_at": _iso(r[10]),
                # Tanpa ini kunjungan retur (RETUR_PASIEN) tak bisa dibedakan dari klinis.
                "jenis_kunjungan": r[11],
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 03 — treatments_raw (Tier 2)
    # =====================================================================
    def export_treatments_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import (
            KunjunganTindakan, MasterTreatment, MasterStaf, Kunjungan,
        )
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                KunjunganTindakan.id_kunjungan_tindakan,
                KunjunganTindakan.id_kunjungan,
                Kunjungan.tgl_kunjungan,
                Kunjungan.id_pasien,
                KunjunganTindakan.id_treatment,
                MasterTreatment.nama_treatment,
                MasterTreatment.role_pelaksana,
                MasterTreatment.harga,
                KunjunganTindakan.status_tindakan,
                KunjunganTindakan.id_staf_pelaksana,
                MasterStaf.nama_staf,
                KunjunganTindakan.waktu_mulai,
                KunjunganTindakan.waktu_selesai,
            )
            .join(MasterTreatment, MasterTreatment.id_treatment == KunjunganTindakan.id_treatment)
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganTindakan.id_kunjungan)
            .outerjoin(MasterStaf, MasterStaf.id_staf == KunjunganTindakan.id_staf_pelaksana)
            .where(Kunjungan.tgl_kunjungan >= start_dt)
            .where(Kunjungan.tgl_kunjungan <= end_dt)
            .order_by(Kunjungan.tgl_kunjungan, KunjunganTindakan.id_kunjungan_tindakan)
        )
        items = []
        for r in self.db.execute(stmt).all():
            wm, ws = r[11], r[12]
            durasi = None
            if wm and ws:
                durasi = int((ws - wm).total_seconds() / 60)
            items.append({
                "id_kunjungan_tindakan": int(r[0]),
                "id_kunjungan": int(r[1]),
                "tgl_kunjungan": _iso(r[2]),
                "id_pasien": int(r[3]) if r[3] else None,
                "id_treatment": int(r[4]),
                "nama_treatment": r[5],
                "role_pelaksana": r[6],
                "harga_master": float(r[7]) if r[7] is not None else 0.0,
                "status_tindakan": _enum_value(r[8]),
                "id_staf_pelaksana": int(r[9]) if r[9] else None,
                "nama_pelaksana": r[10],
                "waktu_mulai": _iso(wm),
                "waktu_selesai": _iso(ws),
                "durasi_aktual_menit": durasi,
            })
        return items

    # =====================================================================
    # 04 — products_prescription_sales_raw (Tier 2)
    # =====================================================================
    def export_products_prescription_sales_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import KunjunganResep, MasterProduk, Kunjungan
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                KunjunganResep.id_resep,
                KunjunganResep.id_kunjungan,
                Kunjungan.tgl_kunjungan,
                Kunjungan.id_pasien,
                KunjunganResep.id_produk,
                MasterProduk.kode_produk,
                MasterProduk.nama_produk,
                MasterProduk.tipe_produk,
                MasterProduk.harga_jual,
                KunjunganResep.qty,
                KunjunganResep.aturan_pakai,
                KunjunganResep.status_item,
                KunjunganResep.id_staf_input,
            )
            .join(MasterProduk, MasterProduk.id_produk == KunjunganResep.id_produk)
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganResep.id_kunjungan)
            .where(Kunjungan.tgl_kunjungan >= start_dt)
            .where(Kunjungan.tgl_kunjungan <= end_dt)
            .order_by(Kunjungan.tgl_kunjungan, KunjunganResep.id_resep)
        )
        items = []
        for r in self.db.execute(stmt).all():
            qty = float(r[9]) if r[9] is not None else 0.0
            harga = float(r[8]) if r[8] is not None else 0.0
            items.append({
                "id_resep": int(r[0]),
                "id_kunjungan": int(r[1]),
                "tgl_kunjungan": _iso(r[2]),
                "id_pasien": int(r[3]) if r[3] else None,
                "id_produk": int(r[4]),
                "kode_produk": r[5],
                "nama_produk": r[6],
                "tipe_produk": _enum_value(r[7]),
                "harga_satuan_master": harga,
                "qty": qty,
                "subtotal_estimasi": round(qty * harga, 2),
                "aturan_pakai": r[10],
                "status_item": _enum_value(r[11]),
                "id_staf_input": int(r[12]) if r[12] else None,
            })
        return items

    # =====================================================================
    # 05 — transactions_header_raw (Tier 2)
    # =====================================================================
    def export_transactions_header_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import TransaksiKasir, Kunjungan, Pasien, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                TransaksiKasir.id_transaksi,
                TransaksiKasir.id_kunjungan,
                Kunjungan.id_pasien,
                Pasien.no_rm,
                Pasien.nama,
                TransaksiKasir.waktu_bayar,
                TransaksiKasir.id_staf_kasir,
                MasterStaf.nama_staf,
                TransaksiKasir.subtotal,
                TransaksiKasir.nominal_diskon,
                TransaksiKasir.total_tagihan,
                TransaksiKasir.keterangan_promo,
                TransaksiKasir.status_transaksi,
                TransaksiKasir.doc_number,
                TransaksiKasir.updated_at,
                TransaksiKasir.dpp,
                TransaksiKasir.ppn,
                TransaksiKasir.is_kena_ppn,
            )
            .outerjoin(Kunjungan, Kunjungan.id_kunjungan == TransaksiKasir.id_kunjungan)
            .outerjoin(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            .outerjoin(MasterStaf, MasterStaf.id_staf == TransaksiKasir.id_staf_kasir)
            .where(TransaksiKasir.waktu_bayar >= start_dt)
            .where(TransaksiKasir.waktu_bayar <= end_dt)
            .order_by(TransaksiKasir.waktu_bayar, TransaksiKasir.id_transaksi)
        )
        return [
            {
                "id_transaksi": int(r[0]),
                "id_kunjungan": int(r[1]) if r[1] else None,
                "id_pasien": int(r[2]) if r[2] else None,
                "no_rm": r[3],
                "nama_pasien": _mask_text(r[4], mask_pii),
                "waktu_bayar": _iso(r[5]),
                "id_staf_kasir": int(r[6]) if r[6] else None,
                "nama_kasir": r[7],
                "subtotal": float(r[8]) if r[8] is not None else 0.0,
                "nominal_diskon": float(r[9]) if r[9] is not None else 0.0,
                "total_tagihan": float(r[10]) if r[10] is not None else 0.0,
                "keterangan_promo": r[11],
                "status_transaksi": r[12],
                "doc_number": r[13],
                "updated_at": _iso(r[14]),
                "dpp": float(r[15]) if r[15] is not None else None,
                "ppn": float(r[16]) if r[16] is not None else 0.0,
                "is_kena_ppn": bool(r[17]) if r[17] is not None else False,
                "kode_entitas": "KLN",
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 06 — transactions_detail_raw (Tier 2)
    # =====================================================================
    def export_transactions_detail_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import TransaksiPembayaran, TransaksiKasir
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                TransaksiPembayaran.id_pembayaran,
                TransaksiPembayaran.id_transaksi,
                TransaksiKasir.waktu_bayar,
                TransaksiPembayaran.metode_bayar,
                TransaksiPembayaran.nominal,
                TransaksiKasir.status_transaksi,
                TransaksiPembayaran.tgl_settle,
            )
            .join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiPembayaran.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= start_dt)
            .where(TransaksiKasir.waktu_bayar <= end_dt)
            .order_by(TransaksiKasir.waktu_bayar, TransaksiPembayaran.id_pembayaran)
        )
        return [
            {
                "id_pembayaran": int(r[0]),
                "id_transaksi": int(r[1]),
                "waktu_bayar": _iso(r[2]),
                "metode_bayar": r[3],
                "nominal": float(r[4]) if r[4] is not None else 0.0,
                "status_transaksi": r[5],
                "tgl_settle": _iso(r[6]),
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 14 — transaction_items_raw (M-FIN-2, Opsi A: produk + treatment)
    # =====================================================================
    def export_transaction_items_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import (
            TransaksiKasir, TransaksiDetailProduk, MasterProduk,
            TransaksiDetailTindakan, MasterTreatment,
        )
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)
        rows: list[dict] = []

        stmt_p = (
            select(
                TransaksiDetailProduk.id_transaksi,
                TransaksiKasir.doc_number,
                TransaksiKasir.waktu_bayar,
                MasterProduk.id_produk,
                MasterProduk.nama_produk,
                TransaksiDetailProduk.qty,
                TransaksiDetailProduk.harga_satuan,
                TransaksiDetailProduk.diskon_item,
                TransaksiDetailProduk.subtotal,
                TransaksiDetailProduk.hpp_satuan,
            )
            .join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiDetailProduk.id_transaksi)
            .join(MasterProduk, MasterProduk.id_produk == TransaksiDetailProduk.id_produk)
            .where(TransaksiKasir.waktu_bayar >= start_dt)
            .where(TransaksiKasir.waktu_bayar <= end_dt)
        )
        for r in self.db.execute(stmt_p).all():
            rows.append({
                "id_transaksi": int(r[0]),
                "doc_number": r[1],
                "waktu_bayar": _iso(r[2]),
                "jenis_item": "PRODUK",
                "id_item": int(r[3]) if r[3] is not None else None,
                "nama_item": r[4],
                "qty": float(r[5]) if r[5] is not None else 0.0,
                "harga_satuan": float(r[6]) if r[6] is not None else 0.0,
                "diskon_item": float(r[7]) if r[7] is not None else 0.0,
                "subtotal": float(r[8]) if r[8] is not None else 0.0,
                "hpp_satuan": float(r[9]) if r[9] is not None else None,
                "kode_entitas": "KLN",
            })

        stmt_t = (
            select(
                TransaksiDetailTindakan.id_transaksi,
                TransaksiKasir.doc_number,
                TransaksiKasir.waktu_bayar,
                MasterTreatment.id_treatment,
                MasterTreatment.nama_treatment,
                TransaksiDetailTindakan.qty,
                TransaksiDetailTindakan.harga_satuan,
                TransaksiDetailTindakan.diskon_item,
                TransaksiDetailTindakan.subtotal,
                TransaksiDetailTindakan.bhp_satuan,
            )
            .join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiDetailTindakan.id_transaksi)
            .join(MasterTreatment, MasterTreatment.id_treatment == TransaksiDetailTindakan.id_treatment)
            .where(TransaksiKasir.waktu_bayar >= start_dt)
            .where(TransaksiKasir.waktu_bayar <= end_dt)
        )
        for r in self.db.execute(stmt_t).all():
            rows.append({
                "id_transaksi": int(r[0]),
                "doc_number": r[1],
                "waktu_bayar": _iso(r[2]),
                "jenis_item": "TREATMENT",
                "id_item": int(r[3]) if r[3] is not None else None,
                "nama_item": r[4],
                "qty": float(r[5]) if r[5] is not None else 0.0,
                "harga_satuan": float(r[6]) if r[6] is not None else 0.0,
                "diskon_item": float(r[7]) if r[7] is not None else 0.0,
                "subtotal": float(r[8]) if r[8] is not None else 0.0,
                "hpp_satuan": float(r[9]) if r[9] is not None else None,
                "kode_entitas": "KLN",
            })

        rows.sort(key=lambda x: (x["id_transaksi"], x["jenis_item"]))
        return rows

    # =====================================================================
    # 15 — refunds_raw (M-FIN-4, G9)
    # =====================================================================
    def export_refunds_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import ReturPasien, TransaksiRefund, TransaksiKasir, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)
        stmt = (
            select(
                TransaksiRefund.id_refund,
                TransaksiRefund.id_transaksi,
                TransaksiKasir.doc_number,
                TransaksiRefund.doc_number_refund,
                TransaksiRefund.tgl_refund,
                TransaksiRefund.nilai_refund,
                TransaksiRefund.metode_refund,
                TransaksiRefund.alasan,
                TransaksiRefund.id_staf_refund,
                MasterStaf.nama_staf,
                # Task #54-F: refund kini bisa per ITEM (obat tertunda yang dibatalkan),
                # jadi Finance perlu tahu baris mana yang dikembalikan — tanpa ini
                # refund item tampak seperti refund transaksi utuh.
                TransaksiRefund.jenis_refund,
                TransaksiRefund.id_resep,
                TransaksiRefund.id_kunjungan_racikan,
                # T32: penyetuju PIN untuk refund atas transaksi hari lampau.
                TransaksiRefund.id_staf_otorisasi,
                # Retur dari pasien (2026-10-05): satu retur = satu baris refund.
                ReturPasien.nomor_retur, ReturPasien.jenis, ReturPasien.nilai_retur,
                ReturPasien.selisih_dibayar, ReturPasien.nilai_hangus,
            )
            .outerjoin(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiRefund.id_transaksi)
            .outerjoin(ReturPasien, ReturPasien.id_refund == TransaksiRefund.id_refund)
            .outerjoin(MasterStaf, MasterStaf.id_staf == TransaksiRefund.id_staf_refund)
            .where(TransaksiRefund.tgl_refund >= start_dt)
            .where(TransaksiRefund.tgl_refund <= end_dt)
            .order_by(TransaksiRefund.tgl_refund, TransaksiRefund.id_refund)
        )
        return [
            {
                "id_refund": int(r[0]),
                "id_transaksi": int(r[1]) if r[1] else None,
                "doc_number_asal": r[2],
                "doc_number_refund": r[3],
                "tgl_refund": _iso(r[4]),
                "nilai_refund": float(r[5]) if r[5] is not None else 0.0,
                "metode_refund": r[6],
                "alasan": r[7],
                "id_staf_refund": int(r[8]) if r[8] else None,
                "nama_staf": r[9],
                "jenis_refund": r[10],
                "id_resep": int(r[11]) if r[11] else None,
                "id_kunjungan_racikan": int(r[12]) if r[12] else None,
                "id_staf_otorisasi": int(r[13]) if r[13] else None,
                "nomor_retur": r[14],
                "jenis_retur": (r[15].value if hasattr(r[15], "value") else r[15]) if r[15] else None,
                "nilai_retur": float(r[16]) if r[16] is not None else None,
                "selisih_dibayar": float(r[17]) if r[17] is not None else None,
                "nilai_hangus": float(r[18]) if r[18] is not None else None,
                "kode_entitas": "KLN",
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 07 — inventory_movements_raw (Tier 2)
    # =====================================================================
    def export_inventory_movements_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import (
            InventoryHistory, InventoryStok, MasterProduk, MasterStaf,
        )
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                InventoryHistory.id_history,
                InventoryHistory.waktu_mutasi,
                InventoryHistory.tipe_item,
                InventoryHistory.id_produk,
                MasterProduk.nama_produk,
                InventoryHistory.id_bahan,
                InventoryStok.nama_bahan,
                InventoryHistory.jenis_mutasi,
                InventoryHistory.qty_perubahan,
                InventoryHistory.stok_akhir,
                InventoryHistory.id_staf,
                MasterStaf.nama_staf,
                InventoryHistory.referensi,
                InventoryHistory.keterangan,
                InventoryHistory.hpp_satuan,
                InventoryHistory.nilai_mutasi,
            )
            .outerjoin(MasterProduk, MasterProduk.id_produk == InventoryHistory.id_produk)
            .outerjoin(InventoryStok, InventoryStok.id_bahan == InventoryHistory.id_bahan)
            .outerjoin(MasterStaf, MasterStaf.id_staf == InventoryHistory.id_staf)
            .where(InventoryHistory.waktu_mutasi >= start_dt)
            .where(InventoryHistory.waktu_mutasi <= end_dt)
            .order_by(InventoryHistory.waktu_mutasi, InventoryHistory.id_history)
        )
        return [
            {
                "id_history": int(r[0]),
                "waktu_mutasi": _iso(r[1]),
                "tipe_item": r[2],
                "id_produk": int(r[3]) if r[3] else None,
                "nama_produk": r[4],
                "id_bahan": int(r[5]) if r[5] else None,
                "nama_bahan": r[6],
                "jenis_mutasi": _enum_value(r[7]),
                "qty_perubahan": float(r[8]) if r[8] is not None else 0.0,
                "stok_akhir": float(r[9]) if r[9] is not None else 0.0,
                "id_staf": int(r[10]) if r[10] else None,
                "nama_staf": r[11],
                "referensi": r[12],
                "keterangan": r[13],
                "hpp_satuan": float(r[14]) if r[14] is not None else None,
                "nilai_mutasi": float(r[15]) if r[15] is not None else None,
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 08 — purchasing_orders_header_raw (Tier 2)
    # =====================================================================
    def export_purchasing_orders_header_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import Pemesanan, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                Pemesanan.id_pemesanan,
                Pemesanan.nomor_po,
                Pemesanan.tgl_pemesanan,
                Pemesanan.supplier_nama,
                Pemesanan.tgl_perkiraan_datang,
                Pemesanan.status,
                Pemesanan.id_staf_pemesan,
                MasterStaf.nama_staf,
                Pemesanan.total_estimasi_biaya,
                Pemesanan.catatan,
                Pemesanan.created_at,
                Pemesanan.updated_at,
            )
            .outerjoin(MasterStaf, MasterStaf.id_staf == Pemesanan.id_staf_pemesan)
            .where(Pemesanan.created_at >= start_dt)
            .where(Pemesanan.created_at <= end_dt)
            .order_by(Pemesanan.created_at, Pemesanan.id_pemesanan)
        )
        return [
            {
                "id_pemesanan": int(r[0]),
                "nomor_po": r[1],
                "tgl_pemesanan": _iso(r[2]),
                "supplier_nama": r[3],
                "tgl_perkiraan_datang": _iso(r[4]),
                "status": _enum_value(r[5]),
                "id_staf_pemesan": int(r[6]) if r[6] else None,
                "nama_pemesan": r[7],
                "total_estimasi_biaya": float(r[8]) if r[8] is not None else 0.0,
                "catatan": r[9],
                "created_at": _iso(r[10]),
                "updated_at": _iso(r[11]),
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 09 — purchasing_orders_item_raw (Tier 2)
    # =====================================================================
    def export_purchasing_orders_item_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import Pemesanan, PemesananItem
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                PemesananItem.id_item,
                PemesananItem.id_pemesanan,
                Pemesanan.nomor_po,
                PemesananItem.tipe_item,
                PemesananItem.id_produk,
                PemesananItem.id_bahan,
                PemesananItem.nama_snapshot,
                PemesananItem.satuan_snapshot,
                PemesananItem.qty_dipesan,
                PemesananItem.qty_diterima,
                PemesananItem.harga_satuan,
                PemesananItem.subtotal,
                PemesananItem.catatan_item,
            )
            .join(Pemesanan, Pemesanan.id_pemesanan == PemesananItem.id_pemesanan)
            .where(Pemesanan.created_at >= start_dt)
            .where(Pemesanan.created_at <= end_dt)
            .order_by(PemesananItem.id_pemesanan, PemesananItem.id_item)
        )
        return [
            {
                "id_item": int(r[0]),
                "id_pemesanan": int(r[1]),
                "nomor_po": r[2],
                "tipe_item": r[3],
                "id_produk": int(r[4]) if r[4] else None,
                "id_bahan": int(r[5]) if r[5] else None,
                "nama_snapshot": r[6],
                "satuan_snapshot": r[7],
                "qty_dipesan": float(r[8]) if r[8] is not None else 0.0,
                "qty_diterima": float(r[9]) if r[9] is not None else 0.0,
                "harga_satuan": float(r[10]) if r[10] is not None else 0.0,
                "subtotal": float(r[11]) if r[11] is not None else 0.0,
                "catatan_item": r[12],
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 10 — purchasing_orders_receive_raw (Tier 2)
    # =====================================================================
    def export_purchasing_orders_receive_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import PemesananReceive, Pemesanan, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                PemesananReceive.id_receive,
                PemesananReceive.id_pemesanan_item,
                PemesananReceive.id_pemesanan,
                Pemesanan.nomor_po,
                PemesananReceive.qty_diterima,
                PemesananReceive.tgl_terima,
                PemesananReceive.id_staf_penerima,
                MasterStaf.nama_staf,
                PemesananReceive.nomor_faktur,
                PemesananReceive.catatan,
            )
            .join(Pemesanan, Pemesanan.id_pemesanan == PemesananReceive.id_pemesanan)
            .outerjoin(MasterStaf, MasterStaf.id_staf == PemesananReceive.id_staf_penerima)
            .where(PemesananReceive.tgl_terima >= start_dt)
            .where(PemesananReceive.tgl_terima <= end_dt)
            .order_by(PemesananReceive.tgl_terima, PemesananReceive.id_receive)
        )
        return [
            {
                "id_receive": int(r[0]),
                "id_pemesanan_item": int(r[1]),
                "id_pemesanan": int(r[2]),
                "nomor_po": r[3],
                "qty_diterima_event": float(r[4]) if r[4] is not None else 0.0,
                "tgl_terima": _iso(r[5]),
                "id_staf_penerima": int(r[6]) if r[6] else None,
                "nama_receiver": r[7],
                "nomor_faktur": r[8],
                "catatan": r[9],
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 11 — membership_raw (Tier 2)
    # =====================================================================
    def export_membership_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import (
            PasienMembershipHistory, MasterMembership, Pasien, MasterStaf,
        )
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                PasienMembershipHistory.id_history,
                PasienMembershipHistory.id_pasien,
                Pasien.no_rm,
                Pasien.nama,
                PasienMembershipHistory.id_membership,
                MasterMembership.nama_tier,
                PasienMembershipHistory.tgl_aktif,
                PasienMembershipHistory.tgl_expired,
                PasienMembershipHistory.harga_bayar,
                PasienMembershipHistory.is_active,
                PasienMembershipHistory.id_staf_aktivasi,
                MasterStaf.nama_staf,
                PasienMembershipHistory.id_transaksi_aktivasi,
                PasienMembershipHistory.created_at,
            )
            .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
            .join(Pasien, Pasien.id_pasien == PasienMembershipHistory.id_pasien)
            .outerjoin(MasterStaf, MasterStaf.id_staf == PasienMembershipHistory.id_staf_aktivasi)
            .where(PasienMembershipHistory.created_at >= start_dt)
            .where(PasienMembershipHistory.created_at <= end_dt)
            .order_by(PasienMembershipHistory.created_at, PasienMembershipHistory.id_history)
        )
        return [
            {
                "id_history": int(r[0]),
                "id_pasien": int(r[1]),
                "no_rm": r[2],
                "nama_pasien": _mask_text(r[3], mask_pii),
                "id_membership": int(r[4]),
                "nama_tier": r[5],
                "tgl_aktif": _iso(r[6]),
                "tgl_expired": _iso(r[7]),
                "harga_bayar": float(r[8]) if r[8] is not None else 0.0,
                "is_active": bool(r[9]),
                "id_staf_aktivasi": int(r[10]) if r[10] else None,
                "nama_aktivator": r[11],
                "id_transaksi_aktivasi": int(r[12]) if r[12] else None,
                "created_at": _iso(r[13]),
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 12 — medical_soap_raw
    # =====================================================================
    def export_medical_soap_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import PemeriksaanKlinis, Kunjungan, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                PemeriksaanKlinis.id_pemeriksaan,
                PemeriksaanKlinis.id_kunjungan,
                Kunjungan.tgl_kunjungan,
                PemeriksaanKlinis.id_pasien,
                PemeriksaanKlinis.id_staf_dokter,
                MasterStaf.nama_staf,
                PemeriksaanKlinis.anamnesa,
                PemeriksaanKlinis.pemeriksaan_fisik,
                PemeriksaanKlinis.diagnosa,
                PemeriksaanKlinis.saran_treatment,
                PemeriksaanKlinis.saran_produk,
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            .outerjoin(MasterStaf, MasterStaf.id_staf == PemeriksaanKlinis.id_staf_dokter)
            # Ekspor rekam medis hanya memuat catatan yang SUDAH disetujui dokter —
            # draf apoteker bukan dokumen medis yang sah untuk dikirim keluar.
            .where(PemeriksaanKlinis.status_soap == "FINAL")
            .where(Kunjungan.tgl_kunjungan >= start_dt)
            .where(Kunjungan.tgl_kunjungan <= end_dt)
            .order_by(Kunjungan.tgl_kunjungan, PemeriksaanKlinis.id_pemeriksaan)
        )
        return [
            {
                "id_pemeriksaan": int(r[0]),
                "id_kunjungan": int(r[1]),
                "tgl_kunjungan": _iso(r[2]),
                "id_pasien": int(r[3]) if r[3] else None,
                "id_staf_dokter": int(r[4]) if r[4] else None,
                "nama_dokter": _mask_text(r[5], mask_pii, "DOKTER_HASH"),
                "anamnesa": r[6],
                "pemeriksaan_fisik": r[7],
                "diagnosa": r[8],
                "saran_treatment": r[9],
                "saran_produk": r[10],
            }
            for r in self.db.execute(stmt).all()
        ]

    # =====================================================================
    # 13 — staff_activity_raw (Mode A: metadata only)
    # =====================================================================
    def export_staff_activity_raw(
        self, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> list[dict]:
        from app.db.models import AuditLog, MasterStaf
        self._validate_range(tgl_dari, tgl_sampai)
        start_dt = datetime.combine(tgl_dari, time.min)
        end_dt = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                AuditLog.id_log,
                AuditLog.waktu,
                AuditLog.id_staf,
                MasterStaf.nama_staf,
                MasterStaf.role,
                AuditLog.aksi,
                AuditLog.tabel_target,
                AuditLog.id_target,
                AuditLog.status_aksi,
                AuditLog.keterangan,
                AuditLog.data_lama,
                AuditLog.data_baru,
            )
            .outerjoin(MasterStaf, MasterStaf.id_staf == AuditLog.id_staf)
            .where(AuditLog.waktu >= start_dt)
            .where(AuditLog.waktu <= end_dt)
            .order_by(AuditLog.waktu, AuditLog.id_log)
        )
        return [
            {
                "id_log": int(r[0]),
                "waktu": _iso(r[1]),
                "id_staf": int(r[2]) if r[2] else None,
                "nama_staf": r[3],
                "role_staf": _enum_value(r[4]),
                "aksi": r[5],
                "tabel_target": r[6],
                "id_target": int(r[7]) if r[7] else None,
                "status_aksi": _enum_value(r[8]),
                "keterangan": r[9],
                # ENRICH (Data Analyst): from/to untuk rekonstruksi transisi status.
                "status_lama": (r[10].get("status_antrian") if isinstance(r[10], dict) else None),
                "status_baru": (r[11].get("status_antrian") if isinstance(r[11], dict) else None),
                # payload mentah penuh (bisa berisi PII pada event pasien) -> redaksi saat mask_pii.
                "data_lama": (None if mask_pii else r[10]),
                "data_baru": (None if mask_pii else r[11]),
            }
            for r in self.db.execute(stmt).all()
        ]

        # =====================================================================
    # DATASET REGISTRY (11 datasets Tier 1+2)
    # =====================================================================
    DATASET_REGISTRY: list[dict] = [
        {
            "name": "daily_operational_summary",
            "label": "Daily Operational Summary",
            "description": "1 row per hari: kunjungan, pasien baru, konsul, tindakan, transaksi, omzet, diskon, resep.",
            "method": "export_daily_operational_summary",
            "default_columns": [
                "tanggal", "jumlah_kunjungan", "jumlah_pasien_baru",
                "jumlah_konsul_dokter", "jumlah_tindakan_selesai",
                "jumlah_transaksi", "total_omzet", "total_diskon",
                "jumlah_resep_dibayar",
            ],
        },
        {
            "name": "visits_raw",
            "label": "Visits Raw",
            "description": "1 row per kunjungan dengan info pasien + FO. mask_pii affects nama_pasien.",
            "method": "export_visits_raw",
            "default_columns": [
                "id_kunjungan", "tgl_kunjungan", "id_pasien", "no_rm",
                "nama_pasien", "status_antrian", "sumber_pendaftaran",
                "keluhan_utama", "id_staf_fo", "nama_fo", "created_at",
            ],
        },
        {
            "name": "treatments_raw",
            "label": "Treatments Raw",
            "description": "1 row per tindakan dengan info treatment + pelaksana + durasi aktual.",
            "method": "export_treatments_raw",
            "default_columns": [
                "id_kunjungan_tindakan", "id_kunjungan", "tgl_kunjungan", "id_pasien",
                "id_treatment", "nama_treatment", "role_pelaksana", "harga_master",
                "status_tindakan", "id_staf_pelaksana", "nama_pelaksana",
                "waktu_mulai", "waktu_selesai", "durasi_aktual_menit",
            ],
        },
        {
            "name": "products_prescription_sales_raw",
            "label": "Products Prescription Sales Raw",
            "description": "1 row per item resep (produk) dengan qty + harga + status.",
            "method": "export_products_prescription_sales_raw",
            "default_columns": [
                "id_resep", "id_kunjungan", "tgl_kunjungan", "id_pasien",
                "id_produk", "kode_produk", "nama_produk", "tipe_produk",
                "harga_satuan_master", "qty", "subtotal_estimasi",
                "aturan_pakai", "status_item", "id_staf_input",
            ],
        },
        {
            "name": "transactions_header_raw",
            "label": "Transactions Header Raw",
            "description": "1 row per transaksi kasir dengan total tagihan + diskon. mask_pii affects nama_pasien.",
            "method": "export_transactions_header_raw",
            "default_columns": [
                "id_transaksi", "id_kunjungan", "id_pasien", "no_rm",
                "nama_pasien", "waktu_bayar", "id_staf_kasir", "nama_kasir",
                "subtotal", "nominal_diskon", "total_tagihan", "keterangan_promo",
                "status_transaksi", "doc_number", "updated_at",
                "dpp", "ppn", "is_kena_ppn", "kode_entitas",
            ],
        },
        {
            "name": "transactions_detail_raw",
            "label": "Transactions Detail Raw",
            "description": "1 row per metode bayar per transaksi (split payment ready).",
            "method": "export_transactions_detail_raw",
            "default_columns": [
                "id_pembayaran", "id_transaksi", "waktu_bayar",
                "metode_bayar", "nominal",
                "status_transaksi", "tgl_settle",
            ],
        },
        {
            "name": "inventory_movements_raw",
            "label": "Inventory Movements Raw",
            "description": "1 row per mutasi stok (polymorphic produk + bahan).",
            "method": "export_inventory_movements_raw",
            "default_columns": [
                "id_history", "waktu_mutasi", "tipe_item",
                "id_produk", "nama_produk", "id_bahan", "nama_bahan",
                "jenis_mutasi", "qty_perubahan", "stok_akhir",
                "id_staf", "nama_staf", "referensi", "keterangan",
                "hpp_satuan", "nilai_mutasi",
            ],
        },
        {
            "name": "purchasing_orders_header_raw",
            "label": "Purchasing Orders Header Raw",
            "description": "1 row per PO (header).",
            "method": "export_purchasing_orders_header_raw",
            "default_columns": [
                "id_pemesanan", "nomor_po", "tgl_pemesanan", "supplier_nama",
                "tgl_perkiraan_datang", "status", "id_staf_pemesan", "nama_pemesan",
                "total_estimasi_biaya", "catatan", "created_at", "updated_at",
            ],
        },
        {
            "name": "purchasing_orders_item_raw",
            "label": "Purchasing Orders Item Raw",
            "description": "1 row per item PO (polymorphic produk + bahan).",
            "method": "export_purchasing_orders_item_raw",
            "default_columns": [
                "id_item", "id_pemesanan", "nomor_po", "tipe_item",
                "id_produk", "id_bahan", "nama_snapshot", "satuan_snapshot",
                "qty_dipesan", "qty_diterima", "harga_satuan", "subtotal",
                "catatan_item",
            ],
        },
        {
            "name": "purchasing_orders_receive_raw",
            "label": "Purchasing Orders Receive Raw",
            "description": "1 row per event receive (partial receive ready).",
            "method": "export_purchasing_orders_receive_raw",
            "default_columns": [
                "id_receive", "id_pemesanan_item", "id_pemesanan", "nomor_po",
                "qty_diterima_event", "tgl_terima", "id_staf_penerima",
                "nama_receiver", "nomor_faktur", "catatan",
            ],
        },
        {
            "name": "membership_raw",
            "label": "Membership Raw",
            "description": "1 row per aktivasi membership pasien. mask_pii affects nama_pasien.",
            "method": "export_membership_raw",
            "default_columns": [
                "id_history", "id_pasien", "no_rm", "nama_pasien",
                "id_membership", "nama_tier", "tgl_aktif", "tgl_expired",
                "harga_bayar", "is_active", "id_staf_aktivasi", "nama_aktivator",
                "id_transaksi_aktivasi", "created_at",
            ],
        },
        {
            "name": "medical_soap_raw",
            "label": "Medical SOAP Raw",
            "description": "1 row per SOAP (pemeriksaan_klinis) dengan anamnesa/diagnosa/saran. mask_pii affects nama_dokter.",
            "method": "export_medical_soap_raw",
            "default_columns": [
                "id_pemeriksaan", "id_kunjungan", "tgl_kunjungan", "id_pasien",
                "id_staf_dokter", "nama_dokter", "anamnesa", "pemeriksaan_fisik",
                "diagnosa", "saran_treatment", "saran_produk",
            ],
        },
        {
            "name": "staff_activity_raw",
            "label": "Staff Activity Raw",
            "description": "1 row per audit log event (+ from/to status untuk rekonstruksi transisi).",
            "method": "export_staff_activity_raw",
            "default_columns": [
                "id_log", "waktu", "id_staf", "nama_staf", "role_staf",
                "aksi", "tabel_target", "id_target", "status_aksi", "keterangan",
                "status_lama", "status_baru", "data_lama", "data_baru",
            ],
        },
        {
            "name": "transaction_items_raw",
            "label": "Transaction Items Raw",
            "description": "1 row per item terjual (PRODUK + TREATMENT) ter-link id_transaksi. M-FIN-2 Opsi A. Untuk split pendapatan + COGS per lini di Finance.",
            "method": "export_transaction_items_raw",
            "default_columns": [
                "id_transaksi", "doc_number", "waktu_bayar", "jenis_item",
                "id_item", "nama_item", "qty", "harga_satuan",
                "diskon_item", "subtotal", "hpp_satuan", "kode_entitas",
            ],
        },
        {
            "name": "refunds_raw",
            "label": "Refunds Raw",
            "description": "1 row per refund (pengembalian atas transaksi lunas). M-FIN-4 G9. Beda dari VOID.",
            "method": "export_refunds_raw",
            "default_columns": [
                "id_refund", "id_transaksi", "doc_number_asal", "doc_number_refund",
                "tgl_refund", "nilai_refund", "metode_refund", "alasan",
                "id_staf_refund", "nama_staf", "kode_entitas",
            ],
        },
    ]

    # =====================================================================
    # Helpers
    # =====================================================================
    @staticmethod
    def _validate_range(tgl_dari: date, tgl_sampai: date) -> None:
        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")

    def get_dataset(
        self, name: str, tgl_dari: date, tgl_sampai: date, mask_pii: bool = False,
    ) -> tuple[list[dict], dict]:
        entry = next((d for d in self.DATASET_REGISTRY if d["name"] == name), None)
        if entry is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Dataset '{name}' tidak ditemukan. Tersedia: "
                + ", ".join(d["name"] for d in self.DATASET_REGISTRY),
            )
        method: Callable = getattr(self, entry["method"])
        items = method(tgl_dari, tgl_sampai, mask_pii)
        return items, entry

    # =====================================================================
    # DATA DICTIONARY (C2.4)
    # =====================================================================
    def get_dictionary_data(self) -> list[dict]:
        """
        Combine REGISTRY + COLUMNS_METADATA → list JSON-ready per dataset.
        Strip non-serializable Callable (method ref).
        """
        result = []
        for entry in self.DATASET_REGISTRY:
            name = entry["name"]
            meta = COLUMNS_METADATA.get(name, {})
            result.append({
                "name": name,
                "label": entry.get("label"),
                "description": entry.get("description"),
                "source_tables": meta.get("source_tables", []),
                "filter": meta.get("filter", ""),
                "mask_pii_affects": meta.get("mask_pii_affects", []),
                "columns": meta.get("columns", [
                    {"name": c, "type": "?", "description": "(metadata pending)"}
                    for c in entry.get("default_columns", [])
                ]),
            })
        return result

    def generate_dictionary_markdown(self) -> str:
        """
        Render full data dictionary sebagai Markdown text.
        Output: 1 section per dataset dengan: deskripsi, source tables,
        filter, mask info, table kolom (#, name, type, description).
        """
        data = self.get_dictionary_data()
        total_cols = sum(len(d["columns"]) for d in data)
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = []
        lines.append("# Sehati Clinic — Data Dictionary")
        lines.append("")
        lines.append(f"**Generated:** {ts}")
        lines.append(f"**Datasets:** {len(data)}")
        lines.append(f"**Total Columns:** {total_cols}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Tentang Dictionary Ini")
        lines.append("")
        lines.append("Dokumen ini menjelaskan schema lengkap setiap dataset yang di-export oleh")
        lines.append("modul Owner Raw Data Export. Source-of-truth: `app/services/_export_columns.py`.")
        lines.append("")
        lines.append("**Type convention:**")
        lines.append("- `int`, `float`, `str`, `date`, `datetime`, `bool`")
        lines.append("- Suffix ` | null` menunjukkan field nullable")
        lines.append("- `dict (JSON)` untuk field JSON struktur")
        lines.append("")
        lines.append("**Privacy notes:**")
        lines.append("- Field di list `mask_pii_affects` akan di-hash kalau flag `mask_pii=true`.")
        lines.append("- Selalu pakai `mask_pii=true` saat export untuk AI external / 3rd party.")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Catatan Anomali Data & Nilai Kanonik")
        lines.append("")
        lines.append("Beberapa kolom kategori disimpan sebagai **teks bebas** (bukan enum/kode")
        lines.append("dengan tabel lookup). Untuk pipeline Data Analyst, gunakan nilai kanonik")
        lines.append("berikut dan tangani anomali legacy seperti dicatat.")
        lines.append("")
        lines.append("### `metode_bayar` (transaksi_pembayaran)")
        lines.append("- **Nilai kanonik (live):** `TUNAI`, `QRIS`, `DEBIT`, `KREDIT`, `TRANSFER`.")
        lines.append("- **Legacy import Excel:** memakai `CASH` — secara semantik **sama dengan** `TUNAI`. Normalisasi `CASH` → `TUNAI` saat analisa.")
        lines.append("- **Anomali test:** transaksi paling awal (`id_transaksi` 1-7, satu kasir, 15-16 April 2026) berisi kode angka mentah `1`, `2`, `4`. Ini data uji coba awal pengembangan, **bukan** enum. Tidak ada legend otoritatif — perlakukan sebagai `UNKNOWN` / exclude dari analytics, JANGAN dipetakan ke cash/qris.")
        lines.append("")
        lines.append("### `sumber_pendaftaran` (kunjungan)")
        lines.append("- **Nilai kanonik (live):** `WALK_IN`, `MEMBERSHIP_ONLY`.")
        lines.append("- **Anomali test:** ada baris legacy dengan kode angka (mis. `1` pada kunjungan BATAL) tanpa legend — perlakukan `UNKNOWN`.")
        lines.append("")
        lines.append("### Field kategori lain")
        lines.append("Semua field kategori lain (`status_antrian`, `status_item`, `jenis_mutasi`,")
        lines.append("`tipe_produk`, `tipe_item`, `role_staf`, `aksi`, `status`, dll.) disimpan")
        lines.append("sebagai label teks yang sudah deskriptif — lihat deskripsi per kolom di bawah.")
        lines.append("Tidak ada kode integer tersembunyi pada field-field tersebut.")
        lines.append("")
        lines.append("---")
        lines.append("")

        for idx, ds in enumerate(data, start=1):
            lines.append(f"## {idx:02d}. `{ds['name']}`")
            lines.append("")
            lines.append(f"**Label:** {ds['label']}")
            lines.append("")
            lines.append(f"**Description:** {ds['description']}")
            lines.append("")
            srcs = ", ".join(f"`{t}`" for t in ds["source_tables"]) or "(none)"
            lines.append(f"**Source Tables:** {srcs}")
            lines.append("")
            lines.append(f"**Filter:** {ds['filter']}")
            lines.append("")
            masks = ", ".join(f"`{c}`" for c in ds["mask_pii_affects"]) or "(none)"
            lines.append(f"**Mask PII affects:** {masks}")
            lines.append("")
            lines.append(f"**Columns ({len(ds['columns'])}):**")
            lines.append("")
            lines.append("| # | Column | Type | Description |")
            lines.append("|---|--------|------|-------------|")
            for ci, col in enumerate(ds["columns"], start=1):
                desc = col.get("description", "").replace("|", "\\|")
                lines.append(f"| {ci} | `{col['name']}` | `{col['type']}` | {desc} |")
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    # =====================================================================
    # Audit Hooks
    # =====================================================================
    def _audit_export_pack(
        self, actor_id_staf, period, tgl_dari, tgl_sampai, format, mask_pii,
        file_count, total_uncompressed, request=None,
    ):
        if actor_id_staf is None:
            return
        ket = (
            f"period={period}, range={tgl_dari}..{tgl_sampai}, format={format}, "
            f"mask_pii={mask_pii}, files={file_count}, uncompressed_bytes={total_uncompressed}"
        )
        try:
            AuditService(self.db).log(
                aksi="EXPORT_PACK", id_staf=actor_id_staf,
                tabel_target=None, id_target=None, keterangan=ket, request=request,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

    def audit_export_dataset(
        self, actor_id_staf, dataset_name, tgl_dari, tgl_sampai,
        format, mask_pii, row_count, request=None,
    ):
        if actor_id_staf is None:
            return
        ket = (
            f"dataset={dataset_name}, range={tgl_dari}..{tgl_sampai}, "
            f"format={format}, mask_pii={mask_pii}, rows={row_count}"
        )
        try:
            AuditService(self.db).log(
                aksi="EXPORT_DATASET", id_staf=actor_id_staf,
                tabel_target=None, id_target=None, keterangan=ket, request=request,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

    # =====================================================================
    # Period Helpers
    # =====================================================================
    @staticmethod
    def compute_weekly_range(ending_date: date) -> tuple[date, date]:
        return (ending_date - timedelta(days=7), ending_date)

    @staticmethod
    def compute_monthly_range(ending_date: date) -> tuple[date, date]:
        return (ending_date - timedelta(days=30), ending_date)

    @staticmethod
    def is_range_warning(tgl_dari: date, tgl_sampai: date) -> bool:
        return (tgl_sampai - tgl_dari).days > WARNING_THRESHOLD_DAYS


__all__ = ["ExportService", "WARNING_THRESHOLD_DAYS", "HARD_CAP_ROWS_TOTAL"]
