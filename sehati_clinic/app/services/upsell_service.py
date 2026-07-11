"""
UpsellService — perawat tambah treatment/produk on-the-fly di ruang tindakan.

Pattern dari kode dokter Bapak (`/ruang_tindakan/upsell` line 1395-1465):
- Perawat bisa tambah item (TREATMENT/PRODUK) saat pasien sudah ON_TREATMENT.
- Kalau item butuh otorisasi (master_treatment.butuh_otorisasi=True),
  PIN dokter wajib divalidasi.

Improvement dari kode lama:
- PIN sekarang di-hash bcrypt di DB (di kode lama dokter Bapak pakai raw compare —
  itu security bug yang sudah kita perbaiki di StafService).
- Validasi PIN pakai `verify_password()` bcrypt.
- Cek dokter yang otorisasi: harus role DOKTER (atau Owner/Superadmin), is_active.
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.models import (
    KunjunganResep,
    KunjunganTindakan,
    MasterStaf,
    MasterTreatment,
    StafRoleEnum,
)
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.pemeriksaan_repo import PemeriksaanRepository
from app.repositories.staf_repo import StafRepository
from app.schemas.treatment import UpsellRequest
from app.services.audit_service import AuditService


# Role yang boleh otorisasi upsell treatment butuh_otorisasi
_ROLES_BOLEH_OTORISASI = {
    StafRoleEnum.DOKTER.value,
    StafRoleEnum.OWNER.value,
    StafRoleEnum.SUPERADMIN.value,
}


class UpsellService:
    def __init__(self, db: Session):
        self.db = db
        self.kunjungan_repo = KunjunganRepository(db)
        self.pemeriksaan_repo = PemeriksaanRepository(db)
        self.staf_repo = StafRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # CORE — submit upsell dengan PIN authorization
    # =========================================================================
    def submit_upsell(
        self,
        payload: UpsellRequest,
        id_staf_pengusul: int,
        request: Optional[Request] = None,
    ) -> dict:
        # ----- 1. NORMALIZE tipe_item -----
        tipe_item = payload.tipe_item.upper().strip()
        if tipe_item not in ("TREATMENT", "PRODUK"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"tipe_item '{payload.tipe_item}' tidak dikenali. "
                    "Pilih: TREATMENT atau PRODUK."
                ),
            )

        # ----- 2. VALIDASI KUNJUNGAN -----
        kunjungan = self.kunjungan_repo.get_by_id(payload.id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {payload.id_kunjungan} tidak ditemukan.",
            )
        if kunjungan.status_antrian in ("COMPLETED", "BATAL"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan sudah {kunjungan.status_antrian} — "
                    "tidak bisa upsell lagi."
                ),
            )

        # ----- 3. CEK MASTER ITEM EXISTS + butuh_otorisasi flag -----
        butuh_otorisasi = False
        nama_item_snapshot: Optional[str] = None

        if tipe_item == "TREATMENT":
            treatment = self.db.get(MasterTreatment, payload.id_item)
            if treatment is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"master_treatment dengan id {payload.id_item} tidak ditemukan.",
                )
            if treatment.is_active is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Treatment '{treatment.nama_treatment}' tidak aktif.",
                )
            butuh_otorisasi = bool(treatment.butuh_otorisasi)
            nama_item_snapshot = treatment.nama_treatment
        else:  # PRODUK
            if not self.pemeriksaan_repo.get_produk_exists(payload.id_item):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"master_produk dengan id {payload.id_item} tidak ditemukan.",
                )
            # Untuk Phase 1, produk belum punya butuh_otorisasi. Bisa di-extend nanti.
            nama_item_snapshot = f"Produk #{payload.id_item}"

        # ----- 4. LOGIKA PIN OTORISASI (kalau butuh) -----
        id_dokter_otorisasi: Optional[int] = None

        if butuh_otorisasi:
            # 4a. Field wajib hadir
            if not payload.id_staf_otorisasi or not payload.pin_otorisasi:
                # AUDIT failed authorization attempt
                self.audit.log(
                    aksi="UPSELL_REJECTED_NO_PIN",
                    id_staf=id_staf_pengusul,
                    tabel_target="kunjungan",
                    id_target=payload.id_kunjungan,
                    keterangan=(
                        f"Upsell treatment '{nama_item_snapshot}' butuh otorisasi "
                        "tapi PIN/id_staf dokter tidak dikirim."
                    ),
                    request=request,
                )
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        f"Treatment '{nama_item_snapshot}' butuh otorisasi dokter. "
                        "Harap masukkan PIN dokter."
                    ),
                )

            # 4b. Dokter yang otorisasi exists, aktif, role legitimate
            dokter = self.staf_repo.get_by_id(payload.id_staf_otorisasi)
            dokter_role = (
                dokter.role.value
                if dokter and hasattr(dokter.role, "value")
                else (str(dokter.role) if dokter else None)
            )
            dokter_invalid = (
                dokter is None
                or not dokter.is_active
                or dokter.pin is None
                or dokter_role not in _ROLES_BOLEH_OTORISASI
            )

            # 4c. Validasi PIN — bcrypt verify
            pin_valid = False
            if not dokter_invalid:
                try:
                    pin_valid = verify_password(payload.pin_otorisasi, dokter.pin)
                except Exception:
                    pin_valid = False

            if dokter_invalid or not pin_valid:
                # AUDIT failed (jangan kasih clue: invalid role vs invalid PIN)
                self.audit.log(
                    aksi="UPSELL_REJECTED_PIN_INVALID",
                    id_staf=id_staf_pengusul,
                    tabel_target="master_staf",
                    id_target=payload.id_staf_otorisasi,
                    keterangan=(
                        f"PIN otorisasi salah untuk upsell '{nama_item_snapshot}' "
                        f"di kunjungan {payload.id_kunjungan}. "
                        f"id_staf_otorisasi_diuji={payload.id_staf_otorisasi}"
                    ),
                    request=request,
                )
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="PIN otorisasi dokter salah atau dokter tidak berwenang.",
                )

            id_dokter_otorisasi = dokter.id_staf

        # ----- 5. INSERT — sesuai tipe item -----
        id_record_baru: int
        try:
            if tipe_item == "TREATMENT":
                tindakan = KunjunganTindakan(
                    id_kunjungan=payload.id_kunjungan,
                    id_treatment=payload.id_item,
                    id_staf_pelaksana=id_staf_pengusul,
                )
                self.db.add(tindakan)
                self.db.flush()
                id_record_baru = tindakan.id_kunjungan_tindakan
                pesan = (
                    f"Upsell treatment '{nama_item_snapshot}' berhasil ditambahkan "
                    "ke antrean tindakan."
                )
                tabel_log = "kunjungan_tindakan"
                aksi_log = "UPSELL_TREATMENT"
            else:  # PRODUK
                resep = KunjunganResep(
                    id_kunjungan=payload.id_kunjungan,
                    id_produk=payload.id_item,
                    qty=payload.qty,
                    id_staf_input=id_staf_pengusul,
                )
                self.db.add(resep)
                self.db.flush()
                id_record_baru = resep.id_resep
                pesan = (
                    f"Upsell produk berhasil dimasukkan ke keranjang kasir "
                    f"(qty={payload.qty})."
                )
                tabel_log = "kunjungan_resep"
                aksi_log = "UPSELL_PRODUK"

            # ----- 6. Kembalikan status ke ON_TREATMENT (kalau belum) -----
            status_lama = kunjungan.status_antrian
            if status_lama != "ON_TREATMENT":
                self.kunjungan_repo.update_status(kunjungan, "ON_TREATMENT")

            # ----- 7. AUDIT — TIDAK log PIN raw -----
            self.audit.log(
                aksi=aksi_log,
                id_staf=id_staf_pengusul,
                tabel_target=tabel_log,
                id_target=id_record_baru,
                data_baru={
                    "id_kunjungan": payload.id_kunjungan,
                    "tipe_item": tipe_item,
                    "id_item": payload.id_item,
                    "nama_item": nama_item_snapshot,
                    "qty": payload.qty if tipe_item == "PRODUK" else 1,
                    "butuh_otorisasi": butuh_otorisasi,
                    "id_dokter_otorisasi": id_dokter_otorisasi,
                },
                keterangan=(
                    f"Upsell oleh staf_id={id_staf_pengusul}"
                    + (
                        f", diotorisasi oleh dokter_id={id_dokter_otorisasi}"
                        if id_dokter_otorisasi
                        else " (tanpa otorisasi — item tidak restricted)"
                    )
                ),
                request=request,
            )

            if status_lama != "ON_TREATMENT":
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_pengusul,
                    tabel_target="kunjungan",
                    id_target=payload.id_kunjungan,
                    data_lama={"status_antrian": status_lama},
                    data_baru={"status_antrian": "ON_TREATMENT"},
                    keterangan="Auto-transition saat upsell.",
                    request=request,
                )

            self.db.commit()
            return {
                "status": "success",
                "message": pesan,
                "data": {
                    "tipe_item": tipe_item,
                    "id_item": payload.id_item,
                    "nama_item": nama_item_snapshot,
                    "id_record_baru": id_record_baru,
                    "butuh_otorisasi": butuh_otorisasi,
                    "otorisasi_oleh": id_dokter_otorisasi,
                    "status_kunjungan": "ON_TREATMENT",
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal submit upsell: {str(e)}",
            )


__all__ = ["UpsellService"]
