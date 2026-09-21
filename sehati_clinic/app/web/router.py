"""
Web router — thin orchestrator.

Cara kerja:
- Setiap domain punya sub-router sendiri di app/web/routes/<domain>.py
- Main `router` (prefix=/web) include semua sub-routers
- Sub-router pakai utilities dari app/web/routes/_shared.py

Rasionalisasi (Juni 3 2026):
File router.py tunggal yang berisi semua route sempat ter-strip oleh
auto-restore beberapa kali. Decomposition jadi modul kecil per-domain
membuat tiap file <300 lines, lebih aman dari truncation, dan lebih
mudah maintainability — Bapak/saya tahu langsung dimana cari route per fitur.
"""

from fastapi import APIRouter

from app.web.routes import (
    cache_stats,
    apotek,
    auth,
    booking,
    dokter,
    export,
    finance_export,
    followup,
    obat_tertunda,
    membership_aktivasi,
    kasir,
    kasir_closing,
    kunjungan,
    master,
    master_diagnosa,
    master_racikan,
    opname,
    pasien,
    pendaftaran,
    pengadaan,
    perawat,
    profil,
    reports,
    retur,
    settings,
    staf,
)
from app.web.routes._shared import templates


# Main /web router — include semua sub-routers
router = APIRouter(prefix="/web", tags=["Web UI"])
router.include_router(auth.router)
router.include_router(cache_stats.router)
router.include_router(booking.router)
router.include_router(pasien.router)
router.include_router(pendaftaran.router)
router.include_router(profil.router)
router.include_router(staf.router)
router.include_router(kunjungan.router)
router.include_router(dokter.router)
router.include_router(kasir.router)
router.include_router(kasir_closing.router)
router.include_router(perawat.router)
router.include_router(apotek.router)
router.include_router(master.router)
router.include_router(master_diagnosa.router)
router.include_router(master_racikan.router)
router.include_router(pengadaan.router)
router.include_router(opname.router)
router.include_router(retur.router)
router.include_router(reports.router)
router.include_router(export.router)
router.include_router(finance_export.router)
router.include_router(followup.router)
router.include_router(obat_tertunda.router)
router.include_router(membership_aktivasi.router)
router.include_router(settings.router)


__all__ = ["router", "templates"]
