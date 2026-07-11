"""
MasterTreatmentService — CRUD untuk master_treatment.

Mirror pattern dari MasterProdukService:
- list_all dengan filter
- create + update + set_active dengan audit log
- Owner/Superadmin role di route layer (sini cuma service)
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryStok,
    KategoriKomponenTreatmentEnum,
    MasterTreatment,
    TreatmentKomponen,
)
from app.repositories.treatment_repo import TreatmentRepository
from app.services.audit_service import AuditService


# Role pelaksana valid (sinkron dengan StafRoleEnum)
_VALID_ROLE_PELAKSANA = {
    "Dokter", "Perawat", "FO", "Apoteker", "Kasir", "Admin", "Owner",
}


# =============================================================================
# KOMISI HELPER HYBRID (Task #360, DEC-060)
# Akuntansi standar: komisi MASUK HPP. Tidak ada recursion.
# =============================================================================
KOMISI_TIPE_PERSEN_HARGA = "PERSEN_HARGA"
KOMISI_TIPE_PERSEN_MARGIN = "PERSEN_MARGIN"
KOMISI_TIPE_NOMINAL = "NOMINAL"
KOMISI_TIPE_VALID = {KOMISI_TIPE_PERSEN_HARGA, KOMISI_TIPE_PERSEN_MARGIN, KOMISI_TIPE_NOMINAL}


def _hitung_komisi_satu(tipe: Optional[str], value: float, harga: float, bhp: float) -> float:
    """Hitung 1 komisi (dokter atau perawat) berdasarkan tipe.

    - PERSEN_HARGA: value% × harga jual gross
    - PERSEN_MARGIN: value% × (harga - BHP)
    - NOMINAL: value rupiah flat
    - tipe NULL atau value <= 0 → 0
    """
    if not tipe or value is None or value <= 0:
        return 0.0
    if tipe == KOMISI_TIPE_PERSEN_HARGA:
        return float(harga) * float(value) / 100.0
    elif tipe == KOMISI_TIPE_PERSEN_MARGIN:
        margin = max(0.0, float(harga) - float(bhp))
        return margin * float(value) / 100.0
    elif tipe == KOMISI_TIPE_NOMINAL:
        return float(value)
    return 0.0


def hitung_komisi_treatment(db, treatment, harga_override: Optional[float] = None) -> dict:
    """
    Hitung komisi + HPP + laba dengan formula akuntansi standar (NO recursion):

        Pajak = pajak_nominal (kalau ada) ATAU pajak_persen × harga
        Komisi dokter = _hitung_komisi_satu(tipe, value, harga, BHP)
        Komisi perawat = _hitung_komisi_satu(tipe, value, harga, BHP)
        HPP = BHP + komisi_dokter + komisi_perawat
        Laba kotor = harga - HPP
        Laba bersih = laba_kotor - pajak

    Komisi MASUK HPP/COGS (DEC-060), bukan recursive % laba bersih.
    """
    harga = float(harga_override) if harga_override is not None else float(treatment.harga or 0)
    bhp = float(treatment.bhp_per_pakai_nominal or 0)

    # Pajak: nominal override persen
    if treatment.pajak_nominal is not None and float(treatment.pajak_nominal) > 0:
        pajak = float(treatment.pajak_nominal)
    else:
        pajak = (float(treatment.pajak_persen or 0) / 100.0) * harga

    # Komisi hybrid (tidak recursive!)
    komisi_dokter = _hitung_komisi_satu(
        treatment.komisi_dokter_tipe,
        float(treatment.komisi_dokter_value or 0),
        harga, bhp,
    )
    komisi_perawat = _hitung_komisi_satu(
        treatment.komisi_perawat_tipe,
        float(treatment.komisi_perawat_value or 0),
        harga, bhp,
    )

    # HPP/COGS = BHP + semua komisi (akuntansi standar)
    hpp = bhp + komisi_dokter + komisi_perawat
    laba_kotor = harga - hpp
    laba_bersih = laba_kotor - pajak

    return {
        "harga": harga,
        "bhp": bhp,
        "pajak": pajak,
        "komisi_dokter": komisi_dokter,
        "komisi_perawat": komisi_perawat,
        "hpp": hpp,
        "laba_kotor": laba_kotor,
        "laba_bersih": laba_bersih,
        "komisi_dokter_tipe": treatment.komisi_dokter_tipe,
        "komisi_dokter_value": float(treatment.komisi_dokter_value or 0),
        "komisi_perawat_tipe": treatment.komisi_perawat_tipe,
        "komisi_perawat_value": float(treatment.komisi_perawat_value or 0),
    }


class MasterTreatmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TreatmentRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # READ
    # =========================================================================
    def list_all(
        self,
        keyword: Optional[str] = None,
        only_active: bool = False,
        limit: int = 500,
    ) -> list[MasterTreatment]:
        return self.repo.list_master_all(
            keyword=keyword, only_active=only_active, limit=limit
        )

    def get_by_id(self, id_treatment: int) -> MasterTreatment:
        treatment = self.repo.get_master_by_id(id_treatment)
        if treatment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Treatment dengan ID {id_treatment} tidak ditemukan.",
            )
        return treatment

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_treatment(
        self,
        nama_treatment: str,
        role_pelaksana: str,
        durasi_menit: int,
        harga: float,
        butuh_otorisasi: bool = False,
        default_rentang_mulai_minggu: int = 0,
        default_rentang_akhir_minggu: int = 12,
        harga_paket: Optional[float] = None,
        # KOMISI SYSTEM HYBRID (#360, DEC-060)
        bhp_per_pakai_nominal: float = 0.0,
        komisi_dokter_tipe: Optional[str] = None,
        komisi_dokter_value: float = 0.0,
        komisi_perawat_tipe: Optional[str] = None,
        komisi_perawat_value: float = 0.0,
        pajak_persen: float = 0.0,
        pajak_nominal: Optional[float] = None,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> MasterTreatment:
        # Validasi role_pelaksana
        if role_pelaksana not in _VALID_ROLE_PELAKSANA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"role_pelaksana '{role_pelaksana}' tidak valid. "
                    f"Pilih: {sorted(_VALID_ROLE_PELAKSANA)}."
                ),
            )
        if durasi_menit <= 0:
            raise HTTPException(400, "durasi_menit harus > 0")
        if harga < 0:
            raise HTTPException(400, "harga tidak boleh negatif")

        # Normalize harga_paket: 0 or None → NULL (treat as no paket)
        harga_paket_clean = None
        if harga_paket is not None and harga_paket > 0:
            harga_paket_clean = harga_paket

        treatment = MasterTreatment(
            nama_treatment=nama_treatment.strip(),
            role_pelaksana=role_pelaksana,
            durasi_menit=durasi_menit,
            harga=harga,
            harga_paket=harga_paket_clean,
            is_active=True,
            butuh_otorisasi=butuh_otorisasi,
            default_rentang_mulai_minggu=default_rentang_mulai_minggu,
            default_rentang_akhir_minggu=default_rentang_akhir_minggu,
            bhp_per_pakai_nominal=max(0, bhp_per_pakai_nominal or 0),
            komisi_dokter_tipe=komisi_dokter_tipe if komisi_dokter_tipe in KOMISI_TIPE_VALID else None,
            komisi_dokter_value=max(0, komisi_dokter_value or 0),
            komisi_perawat_tipe=komisi_perawat_tipe if komisi_perawat_tipe in KOMISI_TIPE_VALID else None,
            komisi_perawat_value=max(0, komisi_perawat_value or 0),
            pajak_persen=max(0, pajak_persen or 0),
            pajak_nominal=pajak_nominal if (pajak_nominal and pajak_nominal > 0) else None,
        )
        try:
            created = self.repo.create_master(treatment)
            self.audit.log_create(
                id_staf=actor_id_staf or 0,
                tabel="master_treatment",
                id_target=created.id_treatment,
                data_baru={
                    "nama_treatment": created.nama_treatment,
                    "role_pelaksana": created.role_pelaksana,
                    "durasi_menit": created.durasi_menit,
                    "harga": float(created.harga),
                    "harga_paket": float(created.harga_paket) if created.harga_paket else None,
                    "butuh_otorisasi": bool(created.butuh_otorisasi),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(created)
            return created
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal create treatment: {e!s}")

    # =========================================================================
    # UPDATE
    # =========================================================================
    def update_treatment(
        self,
        id_treatment: int,
        data: dict,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> MasterTreatment:
        treatment = self.get_by_id(id_treatment)

        # Validasi role kalau diubah
        if "role_pelaksana" in data and data["role_pelaksana"] not in _VALID_ROLE_PELAKSANA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"role_pelaksana '{data['role_pelaksana']}' tidak valid.",
            )
        if "durasi_menit" in data and data["durasi_menit"] <= 0:
            raise HTTPException(400, "durasi_menit harus > 0")
        if "harga" in data and data["harga"] < 0:
            raise HTTPException(400, "harga tidak boleh negatif")
        # harga_paket: 0 atau negative → clear (NULL)
        if "harga_paket" in data:
            hp = data["harga_paket"]
            if hp is None or hp <= 0:
                data["harga_paket"] = None
            elif hp < 0:
                raise HTTPException(400, "harga_paket tidak boleh negatif")
        # KOMISI SYSTEM HYBRID (#360, DEC-060): normalize field baru
        for k in ("bhp_per_pakai_nominal", "komisi_dokter_value", "komisi_perawat_value", "pajak_persen"):
            if k in data:
                v = data[k]
                data[k] = max(0, v) if v is not None else 0
        # Tipe: validate enum value
        for k in ("komisi_dokter_tipe", "komisi_perawat_tipe"):
            if k in data:
                v = data[k]
                if v not in KOMISI_TIPE_VALID:
                    data[k] = None
        if "pajak_nominal" in data:
            pn = data["pajak_nominal"]
            if pn is None or pn <= 0:
                data["pajak_nominal"] = None

        try:
            # Normalize numeric fields for diff
            _NUM_FIELDS = (
                "harga", "harga_paket",
                "bhp_per_pakai_nominal", "komisi_dokter_value", "komisi_perawat_value",
                "pajak_persen", "pajak_nominal",
            )
            data_lama = {}
            for k in data.keys():
                if not hasattr(treatment, k):
                    continue
                v = getattr(treatment, k)
                if k in _NUM_FIELDS:
                    data_lama[k] = float(v) if v is not None else None
                else:
                    data_lama[k] = v
            updated = self.repo.update_master(treatment, data)
            data_baru = {}
            for k, v in data.items():
                if k in _NUM_FIELDS:
                    data_baru[k] = float(v) if v is not None else None
                else:
                    data_baru[k] = v
            self.audit.log_update(
                id_staf=actor_id_staf or 0,
                tabel="master_treatment",
                id_target=updated.id_treatment,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(updated)
            return updated
        except HTTPException:
            raise
            self.db.rollback()
            raise HTTPException(500, f"Gagal update treatment: {e!s}")

    # =========================================================================
    # SET ACTIVE
    # =========================================================================
    def set_active(
        self,
        id_treatment: int,
        is_active: bool,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> MasterTreatment:
        treatment = self.get_by_id(id_treatment)
        try:
            old_state = bool(treatment.is_active)
            updated = self.repo.set_active_master(treatment, is_active)
            self.audit.log_update(
                id_staf=actor_id_staf or 0,
                tabel="master_treatment",
                id_target=updated.id_treatment,
                data_lama={"is_active": old_state},
                data_baru={"is_active": is_active},
                request=request,
            )
            self.db.commit()
            self.db.refresh(updated)
            return updated
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal set_active treatment: {e!s}")

    # =========================================================================
    # KOMPONEN TREATMENT (BAHAN / ALAT) — DEC-030 service-owned transaction
    # =========================================================================
    def tambah_komponen(
        self,
        id_treatment: int,
        kategori: KategoriKomponenTreatmentEnum,
        id_bahan: int,
        qty: float,
        satuan: str,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> TreatmentKomponen:
        # Validate treatment exists
        treatment = self.get_by_id(id_treatment)
        # Validate bahan exists
        bahan = self.db.get(InventoryStok, id_bahan)
        if bahan is None:
            raise HTTPException(404, f"Bahan id {id_bahan} tidak ditemukan")
        if qty <= 0:
            raise HTTPException(400, "Qty harus > 0")
        try:
            komponen = TreatmentKomponen(
                id_treatment=id_treatment,
                kategori=kategori,
                id_bahan=id_bahan,
                qty=float(qty),
                satuan=satuan.strip(),
            )
            self.db.add(komponen)
            self.db.flush()
            self.audit.log_create(
                id_staf=actor_id_staf or 0,
                tabel="treatment_komponen",
                id_target=komponen.id_komponen,
                data_baru={
                    "id_treatment": id_treatment,
                    "kategori": kategori.value if hasattr(kategori, "value") else str(kategori),
                    "id_bahan": id_bahan,
                    "nama_bahan": bahan.nama_bahan,
                    "qty": float(qty),
                    "satuan": satuan,
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(komponen)
            return komponen
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal tambah komponen: {e!s}")

    def hapus_komponen(
        self,
        id_komponen: int,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> None:
        komponen = self.db.get(TreatmentKomponen, id_komponen)
        if komponen is None:
            raise HTTPException(404, f"Komponen id {id_komponen} tidak ditemukan")
        try:
            snapshot = {
                "id_treatment": komponen.id_treatment,
                "kategori": komponen.kategori.value if hasattr(komponen.kategori, "value") else str(komponen.kategori),
                "id_bahan": komponen.id_bahan,
                "qty": float(komponen.qty),
                "satuan": komponen.satuan,
            }
            self.db.delete(komponen)
            self.audit.log_delete(
                id_staf=actor_id_staf or 0,
                tabel="treatment_komponen",
                id_target=id_komponen,
                data_lama=snapshot,
                request=request,
            )
            self.db.commit()
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal hapus komponen: {e!s}")
