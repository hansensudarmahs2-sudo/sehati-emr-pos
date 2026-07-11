"""Cek cepat konfigurasi + koneksi modul Antropometri. Jalankan: python cek_antro.py"""
from app.services.antro_report_service import AntroReportService

print("enabled():", AntroReportService.enabled())
try:
    from app.config import settings
    print("ANTRO_BASE_URL   :", settings.antro_base_url or "(kosong)")
    print("ANTRO_INTAKE_TOKEN:", "(terisi)" if settings.antro_intake_token else "(kosong)")
except Exception as e:
    print("baca settings gagal:", e)

# Uji koneksi nyata ke modul (butuh run_web.bat modul menyala)
try:
    svc = AntroReportService()
    hasil = svc.daftar("RM-000123")
    print("pull /reports OK:", hasil)
except Exception as e:
    print("pull /reports gagal (wajar bila modul belum menyala):", type(e).__name__, e)
