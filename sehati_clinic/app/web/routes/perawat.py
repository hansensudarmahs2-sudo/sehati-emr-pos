"""
Perawat / Ruang Tindakan web routes:
- GET /web/ruang-tindakan/antrian                              - page shell
- GET /web/ruang-tindakan/antrian/list                         - HTMX partial (10s poll)
- GET /web/ruang-tindakan/kunjungan/{id_kunjungan}             - detail dengan tindakan rows
- POST /web/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/start
- POST /web/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/end
- POST /web/ruang-tindakan/kunjungan/{id_kunjungan}/upsell     - upsell treatment/produk

Role gate: Perawat + Dokter (read) + Admin + Owner + Superadmin.

Upsell flow:
- Perawat klik tombol "+ Upsell" di halaman detail kunjungan.
- Pilih tipe (TREATMENT/PRODUK), item dari dropdown master, qty.
- Kalau treatment.butuh_otorisasi=1, form akan minta id_dokter + PIN.
- POST submit -> UpsellService.submit_upsell() validasi + insert + audit.
"""

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.db.models import StafRoleEnum
from app.repositories.master_produk_repo import MasterProdukRepository
from app.repositories.staf_repo import StafRepository
from app.repositories.treatment_repo import TreatmentRepository
from app.schemas.treatment import UpsellRequest
from app.services.treatment_service import TreatmentService
from app.services.upsell_service import UpsellService
from app.web.routes._shared import (
    render_cached,
    build_shell_context,
    get_user_from_cookie,
    require_perawat_role,
    templates,
)


router = APIRouter(tags=["Web Perawat"])


# Roles yang boleh otorisasi upsell - sinkron dengan UpsellService._ROLES_BOLEH_OTORISASI
_DOKTER_AUTH_ROLES = {
    StafRoleEnum.DOKTER,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}


# =============================================================================
# GET /web/ruang-tindakan/antrian - page shell
# =============================================================================
@router.get("/ruang-tindakan/antrian", response_class=HTMLResponse)
def perawat_antrian_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_perawat_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Perawat/Dokter/Admin/Owner.</div>", status_code=403)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/ruang-tindakan",
        page_subtitle="Antrian tindakan hari ini",
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "perawat_antrian.html", ctx)


# =============================================================================
# GET /web/ruang-tindakan/antrian/list - HTMX partial
# =============================================================================
@router.get("/ruang-tindakan/antrian/list", response_class=HTMLResponse)
def perawat_antrian_partial(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Sesi habis.</div>", status_code=401)
    if not require_perawat_role(user):
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>403</div>", status_code=403)

    def _build():
        antrian_resp = TreatmentService(db).lihat_antrian(user=user)
        antrian_dict = antrian_resp.model_dump()
        counter = {"tindakan_pending": 0, "tindakan_proses": 0}
        for item in antrian_dict.get("data", []):
            counter["tindakan_pending"] += item.get("tindakan_pending", 0) or 0
            counter["tindakan_proses"] += item.get("tindakan_proses", 0) or 0
        return templates.TemplateResponse(request, "_perawat_antrian_content.html", {"antrian": antrian_dict, "counter": counter})
    try:
        # CACHE tampilan (KESTABILAN §9): TreatmentService.lihat_antrian(user=..) → kunci per-user.
        from app.core.ttl_cache import ANTRIAN_TTL
        return render_cached(f"antrian:perawat:{user.id_staf}", ANTRIAN_TTL, _build)
    except Exception as e:
        return HTMLResponse(f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Error: {e!s}</div>", status_code=500)


# =============================================================================
# GET /web/ruang-tindakan/kunjungan/{id_kunjungan} - detail
# =============================================================================
@router.get("/ruang-tindakan/kunjungan/{id_kunjungan}", response_class=HTMLResponse)
def perawat_kunjungan_detail(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_perawat_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    # K-L0 (DEC-087): dokter hanya boleh buka pasien yang di-assign ke dia (atau "bebas").
    # Cegah dokter lain memulai tindakan pasien orang → salah atribusi komisi.
    _role = (user.role.value if hasattr(user.role, "value") else str(user.role or "")).upper()
    if _role == "DOKTER":
        from app.db.models import Kunjungan
        _kj = db.get(Kunjungan, id_kunjungan)
        if _kj is not None and _kj.id_staf_dokter_assigned not in (user.id_staf, None):
            return HTMLResponse(
                "<div style='padding:2rem'>403 — Pasien ini di-assign ke dokter lain. "
                "Minta FO untuk meng-assign ke Anda bila perlu.</div>",
                status_code=403,
            )

    try:
        detail_resp = TreatmentService(db).get_detail(id_kunjungan)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    detail_dict = detail_resp.model_dump()

    # V7.2.1 audit AKSES-BACA rekam medis: catat siapa membuka rekam tindakan pasien.
    try:
        from app.db.models import Kunjungan
        from app.services.audit_service import AuditService
        _kj_audit = db.get(Kunjungan, id_kunjungan)
        if _kj_audit is not None:
            AuditService(db).log_view(
                user.id_staf, _kj_audit.id_pasien,
                keterangan="Buka rekam tindakan (ruang tindakan)", request=request,
            )
    except Exception:
        pass  # audit gagal tidak boleh memblokir tampilan

    # ----- Fetch dropdown data untuk upsell modal -----
    treatments = TreatmentRepository(db).list_master_active(limit=300)
    master_treatments = [
        {
            "id_treatment": t.id_treatment,
            "nama_treatment": t.nama_treatment,
            "butuh_otorisasi": bool(t.butuh_otorisasi),
        }
        for t in treatments
    ]

    produk_list = MasterProdukRepository(db).list_with_filter(only_active=True, limit=300)
    master_produk = [
        {
            "id_produk": p.id_produk,
            "nama_produk": p.nama_produk,
            "kode_produk": p.kode_produk,
        }
        for p in produk_list
    ]

    semua_staf_aktif = StafRepository(db).list_active()
    dokter_otorisasi_list = [
        {"id_staf": s.id_staf, "nama_staf": s.nama_staf, "role": s.role.value}
        for s in semua_staf_aktif
        if s.role in _DOKTER_AUTH_ROLES and s.pin is not None
    ]

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/ruang-tindakan",
        page_subtitle=f"Tindakan - {detail_dict.get('nama_pasien', '-')}",
        detail=detail_dict,
        master_treatments=master_treatments,
        master_produk=master_produk,
        dokter_otorisasi_list=dokter_otorisasi_list,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "perawat_tindakan.html", ctx)


# =============================================================================
# POST /web/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/start
# =============================================================================
@router.post("/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/start")
def perawat_start_tindakan(id_kunjungan_tindakan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_perawat_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from urllib.parse import quote
    try:
        result = TreatmentService(db).start_tindakan(
            id_kunjungan_tindakan=id_kunjungan_tindakan,
            id_staf_pelaksana=user.id_staf,
            request=request,
            user_role=user.role,  # TODO-NEW-5 #33 role guardrail
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/antrian?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/antrian?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    data = result.get("data", {}) if isinstance(result, dict) else {}
    id_kunjungan = data.get("id_kunjungan")
    if id_kunjungan:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?ok={quote('Tindakan dimulai.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/ruang-tindakan/antrian?ok={quote('Tindakan dimulai.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/end
# =============================================================================
@router.post("/ruang-tindakan/tindakan/{id_kunjungan_tindakan}/end")
def perawat_end_tindakan(id_kunjungan_tindakan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_perawat_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from urllib.parse import quote
    try:
        result = TreatmentService(db).end_tindakan(
            id_kunjungan_tindakan=id_kunjungan_tindakan,
            id_staf_pelaksana=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/antrian?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/antrian?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    data = result.get("data", {}) if isinstance(result, dict) else {}
    id_kunjungan = data.get("id_kunjungan")
    status_baru = data.get("status_kunjungan_baru", "")
    msg = f"Tindakan selesai. Status kunjungan: {status_baru}." if status_baru else "Tindakan selesai."
    if id_kunjungan:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?ok={quote(msg)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/ruang-tindakan/antrian?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/ruang-tindakan/kunjungan/{id_kunjungan}/upsell
# =============================================================================
@router.post("/ruang-tindakan/kunjungan/{id_kunjungan}/upsell")
def perawat_upsell_submit(
    id_kunjungan: int,
    request: Request,
    db: DbSession,
    tipe_item: str = Form(...),
    id_item: int = Form(..., ge=1),
    qty: float = Form(default=1.0, gt=0),
    id_staf_otorisasi: Optional[int] = Form(default=None),
    pin_otorisasi: Optional[str] = Form(default=None),
):
    from urllib.parse import quote

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_perawat_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    # Normalize empty/zero ke None
    if id_staf_otorisasi is not None and id_staf_otorisasi == 0:
        id_staf_otorisasi = None
    pin_clean = pin_otorisasi.strip() if pin_otorisasi else None
    if pin_clean == "":
        pin_clean = None

    try:
        payload = UpsellRequest(
            id_kunjungan=id_kunjungan,
            tipe_item=tipe_item,
            id_item=id_item,
            qty=qty,
            id_staf_otorisasi=id_staf_otorisasi,
            pin_otorisasi=pin_clean,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?err={quote(f'Input invalid: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = UpsellService(db).submit_upsell(
            payload=payload,
            id_staf_pengusul=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?err={quote(f'Gagal upsell: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = result.get("message", "Upsell berhasil.") if isinstance(result, dict) else "Upsell berhasil."
    return RedirectResponse(
        url=f"/web/ruang-tindakan/kunjungan/{id_kunjungan}?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
