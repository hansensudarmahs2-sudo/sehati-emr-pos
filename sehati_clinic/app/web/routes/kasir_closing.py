"""
Web routes — Buka Kasir / Tutup Kasir / Rekonsiliasi (Kasir-1).

- GET  /web/kasir/tutup                  - page: Buka Kasir form ATAU Tutup Kasir preview
- POST /web/kasir/buka                   - buka sesi kasir (set modal awal)
- POST /web/kasir/tutup                  - submit counted per metode -> simpan closing
- GET  /web/kasir/tutup/slip/{id}        - slip Z-report (transien, cetak via window.print)

Role gate: Kasir + Admin + Owner + Superadmin (require_kasir_role).
Slip hanya boleh dilihat pemilik shift (kasir) atau role rekap-kasir (admin/owner).
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.kasir_closing_service import KasirClosingService, METODE_KANONIK
from app.services.klinik_config_service import KlinikConfigService
from app.repositories.staf_repo import StafRepository
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_kasir_role,
    require_rekap_kasir_role,
    templates,
)


router = APIRouter(tags=["Web Kasir Tutup"])


def _login_redirect():
    return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)


def _403():
    return HTMLResponse(
        "<div style='padding:2rem'>403 - Hanya Kasir/Admin/Owner.</div>",
        status_code=403,
    )


def _parse_rupiah(raw: str) -> Decimal:
    """Parse input rupiah: buang pemisah ribuan ('.'/',') dan spasi. Kosong -> 0."""
    cleaned = (raw or "").strip().replace(".", "").replace(",", "").replace(" ", "")
    if cleaned == "":
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise HTTPException(400, f"Angka tidak valid: {raw!r}")


# =============================================================================
# GET /web/kasir/tutup
# =============================================================================
@router.get("/kasir/tutup", response_class=HTMLResponse)
def kasir_tutup_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login_redirect()
    if not require_kasir_role(user):
        return _403()

    svc = KasirClosingService(db)
    sesi = svc.get_open_session(user.id_staf)
    preview = svc.get_closing_preview(user.id_staf) if sesi is not None else None
    # Peringatan proaktif: pasien yang masih antri hari ini (tutup kasir akan ditolak).
    pending_antrian = svc._pending_antrian_hari_ini() if sesi is not None else {}

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kasir/tutup",
        page_subtitle="Tutup Kasir / Rekonsiliasi",
        sesi=sesi,
        preview=preview,
        pending_antrian=pending_antrian,
        metode_list=METODE_KANONIK,
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "kasir_tutup.html", ctx)


# =============================================================================
# POST /web/kasir/buka
# =============================================================================
@router.post("/kasir/buka", response_class=HTMLResponse)
async def kasir_buka(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login_redirect()
    if not require_kasir_role(user):
        return _403()

    form = await request.form()
    try:
        modal = _parse_rupiah(form.get("modal_awal"))
        KasirClosingService(db).buka_kasir(
            id_staf_kasir=user.id_staf,
            modal_awal=modal,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/tutup?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/kasir/tutup?ok={quote('Kasir dibuka. Selamat bertugas!')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/kasir/tutup
# =============================================================================
@router.post("/kasir/tutup", response_class=HTMLResponse)
async def kasir_tutup_submit(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login_redirect()
    if not require_kasir_role(user):
        return _403()

    form = await request.form()
    try:
        counted = {m: _parse_rupiah(form.get(f"counted_{m}")) for m in METODE_KANONIK}
        catatan = (form.get("catatan") or "").strip()
        sesi = KasirClosingService(db).tutup_kasir(
            id_staf_kasir=user.id_staf,
            counted_per_metode=counted,
            catatan=catatan,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/tutup?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/kasir/tutup/slip/{sesi.id_closing}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/kasir/tutup/slip/{id_closing} — slip Z-report (transien)
# =============================================================================
@router.get("/kasir/tutup/slip/{id_closing}", response_class=HTMLResponse)
def kasir_tutup_slip(id_closing: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login_redirect()
    if not require_kasir_role(user):
        return _403()

    from app.db.models import KasirClosing
    sesi = db.get(KasirClosing, id_closing)
    if sesi is None or sesi.status != "CLOSED":
        return HTMLResponse(
            "<div style='padding:2rem'>Closing tidak ditemukan / belum ditutup.</div>",
            status_code=404,
        )
    # Kasir hanya boleh slip sesi yang ia BUKA atau TUTUP (T28: satu laci, bisa dua
    # orang berbeda); admin/owner (rekap-kasir) boleh semua.
    if not require_rekap_kasir_role(user) and user.id_staf not in (
            sesi.id_staf_kasir, sesi.id_staf_tutup):
        return _403()

    klinik = KlinikConfigService(db).get_config()
    staf_repo = StafRepository(db)
    staf = staf_repo.get_by_id(sesi.id_staf_kasir)
    penutup = staf_repo.get_by_id(sesi.id_staf_tutup) if sesi.id_staf_tutup else None
    ctx = {
        "klinik": klinik,
        "sesi": sesi,
        "detail": sesi.detail_metode or [],
        "kasir_nama": staf.nama_staf if staf else "-",
        "penutup_nama": penutup.nama_staf if penutup else None,
        "sesudah_tutup": KasirClosingService(db)._pembayaran_di_luar_jendela(
            sesi, sesudah_tutup=True),
        "tgl_cetak": datetime.now().strftime("%d/%m/%Y %H:%M"),  # A4: WIB (slip)
    }
    return templates.TemplateResponse(request, "print/ztutup_kasir.html", ctx)

# =============================================================================
# GET /web/reports/tutup-kasir — Laporan Tutup Kasir (owner / rekap-kasir role)
# =============================================================================
@router.get("/reports/tutup-kasir", response_class=HTMLResponse)
def reports_tutup_kasir(request: Request, db: DbSession, tgl=None):
    from datetime import date as _date
    from decimal import Decimal as _Dec
    from app.web.routes._shared import is_kasir_role

    user = get_user_from_cookie(request, db)
    if user is None:
        return _login_redirect()
    if not require_rekap_kasir_role(user):
        return _403()

    # Filter tanggal (shift_tutup). Default = HARI INI. tgl='all' = semua tanggal.
    if tgl is None or tgl == "":
        d_tgl = _date.today()
    elif tgl == "all":
        d_tgl = None
    else:
        try:
            d_tgl = _date.fromisoformat(tgl)
        except ValueError:
            d_tgl = _date.today()

    # REPORTS-COMPART: Kasir hanya lihat closing miliknya; admin/owner lihat semua.
    force_id = user.id_staf if is_kasir_role(user) else None

    svc = KasirClosingService(db)
    closings = svc.list_closings(tgl=d_tgl, id_staf_kasir=force_id)

    staf_repo = StafRepository(db)
    nama_cache = {}
    rows = []
    total_expected = _Dec("0")
    total_counted = _Dec("0")
    total_selisih = _Dec("0")
    n_over = 0
    n_short = 0
    for c in closings:
        if c.id_staf_kasir not in nama_cache:
            st = staf_repo.get_by_id(c.id_staf_kasir)
            nama_cache[c.id_staf_kasir] = st.nama_staf if st else f"#{c.id_staf_kasir}"
        sel = _Dec(str(c.total_selisih or 0))
        total_expected += _Dec(str(c.total_expected or 0))
        total_counted += _Dec(str(c.total_counted or 0))
        total_selisih += sel
        if sel > 0:
            n_over += 1
        elif sel < 0:
            n_short += 1
        rows.append({
            "id_closing": c.id_closing,
            "kasir_nama": nama_cache[c.id_staf_kasir],
            "shift_mulai": c.shift_mulai,
            "shift_tutup": c.shift_tutup,
            "modal_awal": c.modal_awal,
            "total_expected": c.total_expected,
            "total_counted": c.total_counted,
            "total_selisih": sel,
            "catatan": c.catatan,
        })

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle="Laporan Tutup Kasir",
        rows=rows,
        tgl_selected=(d_tgl.isoformat() if d_tgl else ""),
        showing_all=(d_tgl is None),
        is_kasir_view=is_kasir_role(user),
        total_expected=total_expected,
        total_counted=total_counted,
        total_selisih=total_selisih,
        n_closing=len(rows),
        n_over=n_over,
        n_short=n_short,
    )
    return templates.TemplateResponse(request, "reports_tutup_kasir.html", ctx)


__all__ = ["router"]
