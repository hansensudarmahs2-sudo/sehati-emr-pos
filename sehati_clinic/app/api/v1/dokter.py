"""
Dokter endpoints — SOAP input + summary dashboard.

Routes:
    POST  /api/v1/dokter/input-medis              — SOAP + tindakan + resep atomic
    GET   /api/v1/dokter/pasien/{id}/summary      — 4 cardbox dashboard

RBAC:
- Input medis (SOAP write)   : Dokter only (medis), plus Owner/Superadmin untuk koreksi
- Summary dokter (read)      : Dokter, Owner, Superadmin (audit medis)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.pemeriksaan import (
    AntrianDokterResponse,
    HeaderPasienResponse,
    InputMedisRequest,
    InputMedisResponse,
    SummaryDokterResponse,
)
from app.services.pemeriksaan_service import PemeriksaanService


router = APIRouter(prefix="/dokter", tags=["Dokter (SOAP)"])


# =============================================================================
# Role guards
# =============================================================================
_INPUT_MEDIS_ROLES = role_required(
    StafRoleEnum.DOKTER,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
)
_READ_SUMMARY_ROLES = role_required(
    StafRoleEnum.DOKTER,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.ADMIN,
)


# =============================================================================
# INPUT MEDIS — endpoint utama dokter (compound)
# =============================================================================
@router.post(
    "/input-medis",
    response_model=InputMedisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit SOAP + tindakan + resep (1 transaksi atomic)",
)
def input_medis(
    payload: InputMedisRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_INPUT_MEDIS_ROLES)],
):
    """
    Endpoint compound — semua dalam 1 transaksi atomic:

    1. INSERT pemeriksaan_klinis (SOAP)
    2. INSERT tindakan baru:
       - is_series=False → 1 row ke kunjungan_tindakan (perawat eksekusi hari ini)
       - is_series=True → N rows ke pasien_rencana_treatment (sesi 1..N)
    3. INSERT resep produk (kalau ada)
    4. UPDATE kunjungan.status_antrian:
       - Ada tindakan single → ANTRI_TREATMENT (lempar ke perawat)
       - Tidak ada → ANTRI_BAYAR (langsung kasir)

    Validasi:
    - Minimal 1 dari (anamnesa, PF, diagnosa) terisi
    - id_pasien match dengan kunjungan.id_pasien
    - Kunjungan belum COMPLETED/BATAL
    - Semua id_treatment & id_produk exists di master
    """
    service = PemeriksaanService(db)
    return service.input_medis_lengkap(
        payload=payload,
        id_staf_dokter=current_user.id_staf,
        request=request,
    )


# =============================================================================
# SUMMARY DOKTER — 4 cardbox dashboard
# =============================================================================
@router.get(
    "/pasien/{id_pasien}/summary",
    response_model=SummaryDokterResponse,
    status_code=status.HTTP_200_OK,
    summary="Dashboard dokter — 4 cardbox: SOAP / produk dibeli / treatment selesai / foto",
)
def summary_pasien(
    db: DbSession,
    _: Annotated[object, Depends(_READ_SUMMARY_ROLES)],
    id_pasien: int = Path(..., ge=1, description="ID pasien."),
):
    """
    Dashboard dokter saat konsultasi — 4 cardbox terlimit 10 item terakhir:
    - **kiri-atas**: Riwayat SOAP (10 SOAP terakhir, ringkasan anamnesa/diagnosa + full text untuk pop-up)
    - **kiri-bawah**: Produk yang sudah DIBAYAR (10 terakhir)
    - **kanan-bawah**: Treatment yang sudah SELESAI (10 terakhir)
    - **kanan-atas**: Foto before/after (Phase 2, sekarang return list kosong)
    """
    service = PemeriksaanService(db)
    return service.get_summary_pasien(id_pasien)


# =============================================================================
# HEADER PASIEN — 3 grid dashboard atas
# =============================================================================
@router.get(
    "/pasien/{id_pasien}/header",
    response_model=HeaderPasienResponse,
    status_code=status.HTTP_200_OK,
    summary="Header dokter — 3 grid: identitas + alergi + antropometri terakhir + clinical",
)
def header_pasien(
    db: DbSession,
    _: Annotated[object, Depends(_READ_SUMMARY_ROLES)],
    id_pasien: int = Path(..., ge=1, description="ID pasien."),
):
    """
    Header dashboard dokter saat konsultasi — compound dari 3 grid:

    - **grid_kiri_identitas**: nama, usia, jenis kelamin (display) + detail_hover
      (no_rm, membership, telepon, alamat — muncul saat hover).
    - **grid_tengah_alergi**: total + alergi terbaru (sunken textbox) +
      daftar lengkap (pop-up). Hanya alergi yang `is_active=True`.
    - **grid_kanan_antropometri**: data terbaru + BMI + body fat % + lean %
      computed otomatis. Kalau pasien belum pernah diukur, `has_data=false`.

    Composed dari PasienService + AntropometriService — 1 endpoint compound
    untuk efisiensi frontend (mockup ber-grid Bapak tinggal map field).
    """
    service = PemeriksaanService(db)
    return service.get_header_pasien(id_pasien)


# =============================================================================
# ANTRIAN DOKTER — pasien hari ini yang relevant ke dokter
# =============================================================================
@router.get(
    "/antrian",
    response_model=AntrianDokterResponse,
    status_code=status.HTTP_200_OK,
    summary="Antrian dokter hari ini — filter 'yang lewat dokter'",
)
def antrian_dokter(
    db: DbSession,
    _: Annotated[object, Depends(_READ_SUMMARY_ROLES)],
):
    """
    Antrian dokter view dengan filter UX-aware:

    - Status ANTRI_KONSULTASI & KONSULTASI: tampil SEMUA pasien
    - Status ANTRI_TREATMENT / ON_TREATMENT / ANTRI_BAYAR / ANTRI_OBAT:
      tampil HANYA yang sudah ada pemeriksaan_klinis (sudah lewat dokter).
      Pasien yang skip konsultasi (langsung treatment / langsung beli obat)
      TIDAK muncul di sini.
    - Status COMPLETED & BATAL: tidak tampil.

    Counter di response (`counter` field) bantu dokter tahu kapan pasien
    semua clear → bisa pulang awal.

    Contoh use case: dokter selesai konsultasi pasien terakhir. Refresh
    endpoint ini. Kalau `counter.antri_obat = 0` dan semua bucket lain 0,
    artinya tidak ada follow-up pertanyaan obat — dokter boleh pulang.
    """
    service = PemeriksaanService(db)
    return service.lihat_antrian_dokter()
