"""PWA manifest dinamis — nama app HP ikut nama klinik (Config).

Disajikan di root (/manifest.webmanifest) supaya scope PWA = "/" bersih.
Tidak butuh login (di-fetch browser sebelum/atau saat install).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.deps import DbSession
from app.web.routes._shared import get_klinik_nama_safe

router = APIRouter(tags=["PWA"])

# Naikkan angka ini tiap kali gambar ikon diganti -> memaksa browser/HP
# mengunduh ikon baru (cache PWA sangat keras). v3 = ikon JoDerma.
ICON_VER = "3"


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest(db: DbSession):
    nama = (get_klinik_nama_safe(db) or "Klinik").strip() or "Klinik"
    short = (nama.split()[0] if nama.split() else "Klinik")[:12]
    data = {
        "name": nama,
        "short_name": short,
        "start_url": "/web/dashboard",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0D5C63",
        "icons": [
            {"src": f"/static/icon-192.png?v={ICON_VER}", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": f"/static/icon-512.png?v={ICON_VER}", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": f"/static/icon-192.png?v={ICON_VER}", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": f"/static/icon-512.png?v={ICON_VER}", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JSONResponse(data, media_type="application/manifest+json")
