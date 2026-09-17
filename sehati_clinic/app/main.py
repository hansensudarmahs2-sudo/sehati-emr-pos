"""
Sehati Clinic API — FastAPI entry point.

Untuk run:
    uvicorn app.main:app --reload

Akses dokumentasi otomatis (Swagger UI): http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1 import antropometri as antropometri_router
from app.api.v1 import apotek as apotek_router
from app.api.v1 import auth as auth_router
from app.api.v1 import dokter as dokter_router
from app.api.v1 import kasir as kasir_router
from app.api.v1 import kunjungan as kunjungan_router
from app.api.v1 import master_produk as master_produk_router
from app.api.v1 import pasien as pasien_router
from app.api.v1 import reports as reports_router
from app.api.v1 import ruang_tindakan as ruang_tindakan_router
from app.api.v1 import staf as staf_router
from app.api.v1 import finance as finance_router  # Phase 0 skeleton — DEC-064 11 Juni 2026
from app.config import settings
from app.core.csrf import CSRFMiddleware
from app.web.router import router as web_router
from app.web.routes import pwa as pwa_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler — startup & shutdown hooks."""
    print(f"🚀 {settings.app_name} starting in {settings.app_env} mode")
    print(f"📍 DB target: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    yield
    print("👋 Shutting down...")


# ----- App instance -----
app = FastAPI(
    title=settings.app_name,
    description="Sistem eMR (Electronic Medical Record) + POS (Point of Sale) Klinik Sehati",
    version="0.1.0",
    debug=settings.app_debug,
    lifespan=lifespan,
)


# ----- Middleware: CORS -----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Middleware: Security headers (audit ASVS V14.4.1 — subset murah, no-HTTPS) -----
# PURE ASGI (bukan BaseHTTPMiddleware) supaya TIDAK membuang Set-Cookie CSRF
# (BaseHTTPMiddleware punya bug body/cookie-consumption di Starlette). Hanya append header.
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                have = {k.lower() for k, _ in headers}
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
                ):
                    if name not in have:
                        headers.append((name, value))
            await send(message)

        await self.app(scope, receive, _send)


app.add_middleware(SecurityHeadersMiddleware)

# ----- Middleware: CSRF (only /web/*, skips /api/v1) -----
app.add_middleware(CSRFMiddleware)


# ----- Static files mount (untuk logo upload + future assets) -----
from pathlib import Path as _Path
_STATIC_DIR = _Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
(_STATIC_DIR / "uploads").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ----- Routers -----
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(staf_router.router, prefix="/api/v1")
app.include_router(pasien_router.router, prefix="/api/v1")
app.include_router(kunjungan_router.router, prefix="/api/v1")
app.include_router(dokter_router.router, prefix="/api/v1")
app.include_router(ruang_tindakan_router.router, prefix="/api/v1")
app.include_router(antropometri_router.router, prefix="/api/v1")
app.include_router(kasir_router.router, prefix="/api/v1")
app.include_router(apotek_router.router, prefix="/api/v1")
app.include_router(master_produk_router.router, prefix="/api/v1")
app.include_router(reports_router.router, prefix="/api/v1")
app.include_router(finance_router.router)  # /api/v1/finance/* — Phase 0 skeleton (returns 501)

# ----- Web UI router (no /api/v1 prefix — Jinja2 + HTMX) -----
app.include_router(pwa_router.router)  # /manifest.webmanifest (dinamis)
app.include_router(web_router)


# ----- Root redirect to web UI login -----
@app.get("/", tags=["Meta"], include_in_schema=False)
def root():
    """Root URL — redirect ke web UI login page."""
    return RedirectResponse(url="/web/login", status_code=303)


# ----- API metadata endpoint (JSON, optional) -----
@app.get("/api/meta", tags=["Meta"])
def api_meta():
    """Info dasar API — untuk monitoring / health check tools."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "web_ui": "/web/login",
    }


@app.get("/health", tags=["Meta"])
def health_check():
    return {
        "status": "ok",
        "env": settings.app_env,
        "service": settings.app_name,
    }


@app.get("/health/db", tags=["Meta"])
def health_check_db():
    """Readiness check koneksi DB — TANPA bocorkan versi MySQL / nama DB / error mentah.

    A11 (audit P3): dulu endpoint ini publik & memaparkan VERSION(), DATABASE(),
    dan pesan exception mentah tanpa auth (info-leak untuk recon). Sekarang hanya
    balas connected/disconnected. Detail error ditulis ke log server, bukan ke klien.
    """
    import logging
    from sqlalchemy import text
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logging.getLogger("sehati.health").error("DB health check gagal: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "disconnected"},
        )
