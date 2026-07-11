"""
Mockup Demo App — Klinik ABC.

Self-contained FastAPI app untuk demo ke partner bisnis.
NO database — semua data in-memory dari demo_data.py.

Halaman:
1. /              → Login page (preset 4 user button)
2. /dashboard     → Dashboard Owner (stats + chart omzet)
3. /antrian       → Antrian Hari Ini → click ke detail pasien
4. /pasien/{id}   → Detail Pasien + SOAP view
5. /kasir         → Tagihan + bayar form
6. /nota          → Nota cetak preview
"""

import sys
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# =============================================================================
# Path resolution untuk PyInstaller bundle
# =============================================================================
def _resource_path(rel: str) -> Path:
    """Resolve path for both dev mode + PyInstaller frozen mode."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).parent / rel


from demo_data import (
    KLINIK, DEMO_USERS, DOKTER, PASIEN, TREATMENT, PRODUK,
    ANTRIAN_HARI_INI, RIWAYAT_SOAP_ANISA,
    get_omzet_7_hari, KINERJA_DOKTER, TOP_TREATMENT, DASHBOARD_STATS,
    TAGIHAN_DEMO, get_nota_demo,
)


app = FastAPI(title="Klinik ABC Demo")
app.mount("/static", StaticFiles(directory=str(_resource_path("static"))), name="static")
templates = Jinja2Templates(directory=str(_resource_path("templates")))


def _ctx(**kwargs):
    """Common context dict for all templates (request will be injected by TemplateResponse)."""
    return {
        "klinik": KLINIK,
        **kwargs,
    }


# =============================================================================
# ROUTE 1 — LOGIN
# =============================================================================
@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", _ctx(users=DEMO_USERS))


@app.post("/login")
def login_submit(username: str = Form(...)):
    # Mockup — semua user langsung berhasil
    return RedirectResponse(url="/dashboard", status_code=303)


# =============================================================================
# ROUTE 2 — DASHBOARD OWNER
# =============================================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    omzet = get_omzet_7_hari()
    return templates.TemplateResponse(request, "dashboard.html", _ctx(
        stats=DASHBOARD_STATS,
        omzet=omzet,
        kinerja_dokter=KINERJA_DOKTER,
        top_treatment=TOP_TREATMENT,
    ))


# =============================================================================
# ROUTE 3 — ANTRIAN HARI INI
# =============================================================================
@app.get("/antrian", response_class=HTMLResponse)
def antrian(request: Request):
    return templates.TemplateResponse(request, "antrian.html", _ctx(
        antrian=ANTRIAN_HARI_INI,
        dokter_list=DOKTER,
    ))


# =============================================================================
# ROUTE 4 — DETAIL PASIEN + SOAP
# =============================================================================
@app.get("/pasien/{id_pasien}", response_class=HTMLResponse)
def detail_pasien(request: Request, id_pasien: int):
    pasien = next((p for p in PASIEN if p["id"] == id_pasien), None)
    if pasien is None:
        return RedirectResponse(url="/antrian", status_code=303)

    # Untuk demo, riwayat SOAP hanya pasien Anisa (id=1)
    riwayat = RIWAYAT_SOAP_ANISA if id_pasien == 1 else []

    # Cek apakah ada antrian aktif
    antrian_aktif = next((a for a in ANTRIAN_HARI_INI if a["id_pasien"] == id_pasien), None)

    return templates.TemplateResponse(request, "pasien_detail.html", _ctx(
        pasien=pasien,
        riwayat=riwayat,
        antrian=antrian_aktif,
        treatment_list=TREATMENT,
        produk_list=PRODUK,
    ))


@app.post("/pasien/{id_pasien}/soap")
def soap_submit(id_pasien: int):
    # Mockup — anggap berhasil simpan, redirect ke antrian
    return RedirectResponse(url=f"/pasien/{id_pasien}?soap_ok=1", status_code=303)


# =============================================================================
# ROUTE 5 — KASIR (tagihan + bayar)
# =============================================================================
@app.get("/kasir", response_class=HTMLResponse)
def kasir(request: Request):
    return templates.TemplateResponse(request, "kasir.html", _ctx(
        tagihan=TAGIHAN_DEMO,
    ))


@app.post("/kasir/bayar")
def kasir_bayar(metode: str = Form(...), nominal: float = Form(...)):
    # Mockup — langsung redirect ke nota
    return RedirectResponse(url="/nota", status_code=303)


# =============================================================================
# ROUTE 6 — NOTA CETAK
# =============================================================================
@app.get("/nota", response_class=HTMLResponse)
def nota(request: Request):
    return templates.TemplateResponse(request, "nota.html", _ctx(
        nota=get_nota_demo(),
    ))


# =============================================================================
# DEMO RESET — bantuan untuk demo (kembali ke login)
# =============================================================================
@app.get("/logout")
def logout():
    return RedirectResponse(url="/", status_code=303)
