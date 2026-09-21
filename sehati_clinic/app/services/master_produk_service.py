"""
MasterProdukService — CRUD master produk + restock + set active.

Validasi:
- kode_produk unique
- tipe_produk in {RETAIL, CABIN, ALAT}
- harga_jual >= 0
- stok_terkini >= 0 (saat create)
- id_bahan_sumber: kalau di-set, qty_per_unit_produk juga harus di-set (repacking integrity)

Audit hooks: CREATE, UPDATE, SET_ACTIVE, RESTOCK per aksi.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import MasterProduk, TipeProdukEnum
from app.repositories.master_produk_repo import MasterProdukRepository
from app.schemas.master_produk import (
    MasterProdukCreate,
    MasterProdukUpdate,
    RestockProdukRequest,
)
from app.services.audit_service import AuditService


_VALID_TIPE_PRODUK = {"RETAIL", "CABIN", "ALAT"}


# =============================================================================
# KOMISI HELPER PRODUK HYBRID (Task #361, DEC-060)
# Akuntansi standar: komisi MASUK HPP. Tidak ada recursion.
# =============================================================================
KOMISI_TIPE_PERSEN_HARGA = "PERSEN_HARGA"
KOMISI_TIPE_PERSEN_MARGIN = "PERSEN_MARGIN"
KOMISI_TIPE_NOMINAL = "NOMINAL"
KOMISI_TIPE_VALID = {KOMISI_TIPE_PERSEN_HARGA, KOMISI_TIPE_PERSEN_MARGIN, KOMISI_TIPE_NOMINAL}


def _hitung_komisi_satu(tipe: Optional[str], value: float, harga: float, hpp: float) -> float:
    """Hitung 1 komisi (dokter) berdasarkan tipe untuk produk.

    Untuk produk, basis margin = harga_jual - hpp_per_unit (bukan harga - BHP).
    P2-1: aritmetika pakai Decimal (bukan float) + quantize ke 2dp (ROUND_HALF_UP)
    agar nilai yang disimpan ke komisi_nominal DECIMAL(12,2) bebas galat biner.
    """
    if not tipe or value is None or float(value) <= 0:
        return 0.0
    v = Decimal(str(value)); h = Decimal(str(harga)); c = Decimal(str(hpp))
    if tipe == KOMISI_TIPE_PERSEN_HARGA:
        res = h * v / Decimal("100")
    elif tipe == KOMISI_TIPE_PERSEN_MARGIN:
        margin = h - c
        if margin < 0:
            margin = Decimal("0")
        res = margin * v / Decimal("100")
    elif tipe == KOMISI_TIPE_NOMINAL:
        res = v
    else:
        return 0.0
    return float(res.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def hitung_komisi_produk(produk, harga_override: Optional[float] = None) -> dict:
    """
    Hitung komisi dokter + HPP_total + laba untuk produk yang diresepkan.
    Formula akuntansi standar (NO recursion):

        Pajak = pajak_nominal (kalau ada) ATAU pajak_persen × harga
        Komisi dokter = _hitung_komisi_satu(tipe, value, harga, hpp_per_unit)
        HPP_total = hpp_per_unit + komisi_dokter
        Laba kotor = harga - HPP_total
        Laba bersih = laba_kotor - pajak

    Komisi MASUK HPP/COGS (DEC-060), bukan recursive.
    """
    harga = float(harga_override) if harga_override is not None else float(produk.harga_jual or 0)
    hpp_per_unit = float(produk.hpp_per_unit or 0)

    if produk.pajak_nominal is not None and float(produk.pajak_nominal) > 0:
        pajak = float(produk.pajak_nominal)
    else:
        pajak = (float(produk.pajak_persen or 0) / 100.0) * harga

    komisi_dokter = _hitung_komisi_satu(
        produk.komisi_dokter_tipe,
        float(produk.komisi_dokter_value or 0),
        harga, hpp_per_unit,
    )

    hpp_total = hpp_per_unit + komisi_dokter
    laba_kotor = harga - hpp_total
    laba_bersih = laba_kotor - pajak

    return {
        "harga": harga,
        "hpp_per_unit": hpp_per_unit,
        "pajak": pajak,
        "komisi_dokter": komisi_dokter,
        "hpp_total": hpp_total,
        "laba_kotor": laba_kotor,
        "laba_bersih": laba_bersih,
        "komisi_dokter_tipe": produk.komisi_dokter_tipe,
        "komisi_dokter_value": float(produk.komisi_dokter_value or 0),
    }


class MasterProdukService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = MasterProdukRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # READ
    # =========================================================================
    def get_by_id(self, id_produk: int) -> MasterProduk:
        produk = self.repo.get_by_id(id_produk)
        if produk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Produk dengan ID {id_produk} tidak ditemukan.",
            )
        return produk

    def list_all(
        self,
        keyword: Optional[str] = None,
        tipe: Optional[str] = None,
        only_active: bool = False,
        limit: int = 100,
    ) -> list[MasterProduk]:
        if tipe and tipe.upper() not in _VALID_TIPE_PRODUK:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tipe_produk '{tipe}' tidak valid. Pilih: {sorted(_VALID_TIPE_PRODUK)}.",
            )
        return self.repo.list_with_filter(
            keyword=keyword,
            tipe=tipe.upper() if tipe else None,
            only_active=only_active,
            limit=limit,
        )

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_produk(
        self,
        payload: MasterProdukCreate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterProduk:
        # Validasi tipe
        tipe = payload.tipe_produk.upper().strip()
        if tipe not in _VALID_TIPE_PRODUK:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tipe_produk '{payload.tipe_produk}' tidak valid. Pilih: {sorted(_VALID_TIPE_PRODUK)}.",
            )

        # Validasi unique kode_produk
        existing = self.repo.get_by_kode(payload.kode_produk)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Kode produk '{payload.kode_produk}' sudah dipakai.",
            )

        # Validasi repacking integrity
        if payload.id_bahan_sumber is not None and payload.qty_per_unit_produk is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="qty_per_unit_produk wajib diisi kalau id_bahan_sumber di-set (untuk produk repack).",
            )

        try:
            produk = MasterProduk(
                kode_produk=payload.kode_produk,
                nama_produk=payload.nama_produk,
                tipe_produk=TipeProdukEnum(tipe),
                satuan=payload.satuan,
                harga_jual=payload.harga_jual,
                stok_terkini=payload.stok_terkini,
                stok_minimal=payload.stok_minimal,
                id_bahan_sumber=payload.id_bahan_sumber,
                qty_per_unit_produk=payload.qty_per_unit_produk,
                eligible_member_discount=payload.eligible_member_discount,
                default_iterasi=payload.default_iterasi,
                # TODO-NEW-3 #31 — auto-fill cara pakai resep SOAP
                default_cara_pakai=(
                    (payload.default_cara_pakai or "").strip() or None
                    if hasattr(payload, "default_cara_pakai") else None
                ),
                # Produk topikal: kandungan (boleh tampil) + nama_dagang (merk asli, internal)
                kandungan=(getattr(payload, "kandungan", None) or None),
                nama_dagang=(getattr(payload, "nama_dagang", None) or None),
                golongan=(getattr(payload, "golongan", None) or None),
                # Dasar hitung racikan
                kekuatan_nilai=(getattr(payload, "kekuatan_nilai", None) or None),
                kekuatan_satuan=(getattr(payload, "kekuatan_satuan", None) or None),
                isi_kemasan=(getattr(payload, "isi_kemasan", None) or None),
                satuan_isi=(getattr(payload, "satuan_isi", None) or None),
                is_active=True,
                # KOMISI SYSTEM HYBRID (#361, DEC-060)
                hpp_per_unit=max(0, (getattr(payload, "hpp_per_unit", 0) or 0)),
                komisi_dokter_tipe=(
                    getattr(payload, "komisi_dokter_tipe", None)
                    if getattr(payload, "komisi_dokter_tipe", None) in KOMISI_TIPE_VALID
                    else None
                ),
                komisi_dokter_value=max(0, (getattr(payload, "komisi_dokter_value", 0) or 0)),
                pajak_persen=max(0, (getattr(payload, "pajak_persen", 0) or 0)),
                pajak_nominal=(
                    getattr(payload, "pajak_nominal", None)
                    if (getattr(payload, "pajak_nominal", None) and getattr(payload, "pajak_nominal", 0) > 0)
                    else None
                ),
            )
            self.repo.create(produk)

            self.audit.log_create(
                id_staf=actor_id_staf,
                tabel="master_produk",
                id_target=produk.id_produk,
                data_baru={
                    "kode_produk": produk.kode_produk,
                    "nama_produk": produk.nama_produk,
                    "tipe_produk": tipe,
                    "harga_jual": float(produk.harga_jual or 0),
                    "stok_awal": float(produk.stok_terkini or 0),
                    "is_repack": payload.id_bahan_sumber is not None,
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(produk)
            return produk
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal create produk: {str(e)}",
            )

    # =========================================================================
    # UPDATE — partial
    # =========================================================================
    def update_profile(
        self,
        id_produk: int,
        payload: MasterProdukUpdate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterProduk:
        produk = self.get_by_id(id_produk)
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)

        # Validasi tipe kalau di-update
        if "tipe_produk" in update_data:
            tipe_upper = update_data["tipe_produk"].upper().strip()
            if tipe_upper not in _VALID_TIPE_PRODUK:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"tipe_produk '{update_data['tipe_produk']}' tidak valid.",
                )
            update_data["tipe_produk"] = TipeProdukEnum(tipe_upper)

        # Cek unique kode_produk kalau ganti
        if "kode_produk" in update_data and update_data["kode_produk"] != produk.kode_produk:
            existing = self.repo.get_by_kode(update_data["kode_produk"])
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Kode '{update_data['kode_produk']}' sudah dipakai produk lain.",
                )

        try:
            # Snapshot data lama (untuk audit)
            data_lama = {
                k: (
                    getattr(produk, k).value
                    if hasattr(getattr(produk, k), "value")
                    else (
                        float(getattr(produk, k))
                        if isinstance(getattr(produk, k), Decimal)
                        else getattr(produk, k)
                    )
                )
                for k in update_data.keys()
                if hasattr(produk, k)
            }

            self.repo.update(produk, update_data)

            data_baru = {
                k: (
                    v.value if hasattr(v, "value")
                    else (float(v) if isinstance(v, Decimal) else v)
                )
                for k, v in update_data.items()
            }
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="master_produk",
                id_target=produk.id_produk,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(produk)
            return produk
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal update produk: {str(e)}",
            )

    # =========================================================================
    # SET ACTIVE
    # =========================================================================
    def set_active(
        self,
        id_produk: int,
        is_active: bool,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> MasterProduk:
        produk = self.get_by_id(id_produk)
        try:
            old_state = bool(produk.is_active)
            updated = self.repo.set_active_produk(produk, is_active)
            self.audit.log_update(
                id_staf=actor_id_staf or 0,
                tabel="master_produk",
                id_target=updated.id_produk,
                data_lama={"is_active": old_state},
                request=request,
            )
            self.db.commit()
            self.db.refresh(updated)
            return updated
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal set_active produk: {e!s}")
