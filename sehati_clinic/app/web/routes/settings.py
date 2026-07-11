"""
Settings web routes (Owner + Superadmin scope):
- GET  /web/settings/klinik              - Render form klinik info
- POST /web/settings/klinik              - Update text fields + paper size
- POST /web/settings/klinik/logo         - Upload logo file
- POST /web/settings/klinik/logo/delete  - Remove logo

Role gate: require_master_data_role (Owner + Superadmin).
Reference: DEC-047 (Print Module).
"""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.klinik_config_service import KlinikConfigService, VALID_PAPER_SIZES
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_master_data_role,
    templates,
)


router = APIRouter(tags=["Web Settings"])


def _403() -> HTMLResponse:
    return HTMLResponse(
        "<div style='padding:2rem'>403 — Hanya Owner/Superadmin yang boleh akses Settings.</div>",
        status_code=403,
    )


# =============================================================================
# GET /web/settings/klinik — Render form
# =============================================================================
@router.get("/settings/klinik", response_class=HTMLResponse)
def settings_klinik_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    svc = KlinikConfigService(db)
    try:
        cfg = svc.get_config()
        apotekers = svc.list_apoteker()
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    cfg_dict = {
        "nama_klinik": cfg.nama_klinik or "",
        "alamat_baris1": cfg.alamat_baris1 or "",
        "alamat_baris2": cfg.alamat_baris2 or "",
        "alamat_baris3": cfg.alamat_baris3 or "",
        "no_telepon": cfg.no_telepon or "",
        "no_whatsapp": cfg.no_whatsapp or "",
        "email": cfg.email or "",
        "website": cfg.website or "",
        "logo_path": cfg.logo_path or "",
        "mini_logo_path": cfg.mini_logo_path or "",
        "footer_text": cfg.footer_text or "",
        "default_paper_nota": cfg.default_paper_nota or "a5",
        "default_paper_soap": cfg.default_paper_soap or "a5",
        "ttd_dokter_text": cfg.ttd_dokter_text or "",
        "no_sia": cfg.no_sia or "",
        "rm_prefix": cfg.rm_prefix or "",
        "kode_klinik": cfg.kode_klinik or "",
        "lead_time_hari": cfg.lead_time_hari if cfg.lead_time_hari is not None else 14,
        "safety_hari": cfg.safety_hari if cfg.safety_hari is not None else 7,
    }

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/settings",
        page_subtitle="Profil Klinik untuk Cetak Nota & Resume",
        config=cfg_dict,
        apotekers=apotekers,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "settings_klinik.html", ctx)


# =============================================================================
# POST /web/settings/klinik — Update text fields + paper size
# =============================================================================
@router.post("/settings/klinik")
async def settings_klinik_submit(
    request: Request,
    db: DbSession,
    nama_klinik: str = Form(...),
    alamat_baris1: str = Form(default=""),
    alamat_baris2: str = Form(default=""),
    alamat_baris3: str = Form(default=""),
    no_telepon: str = Form(default=""),
    no_whatsapp: str = Form(default=""),
    email: str = Form(default=""),
    website: str = Form(default=""),
    footer_text: str = Form(default=""),
    default_paper_nota: str = Form(default="a5"),
    default_paper_soap: str = Form(default="a5"),
    ttd_dokter_text: str = Form(default=""),
    no_sia: str = Form(default=""),
    rm_prefix: str = Form(default=""),
    lead_time_hari: str = Form(default="14"),
    safety_hari: str = Form(default="7"),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    # Quick validation
    if default_paper_nota not in VALID_PAPER_SIZES:
        default_paper_nota = "a5"
    if default_paper_soap not in VALID_PAPER_SIZES:
        default_paper_soap = "a5"

    update_data = {
        "nama_klinik": nama_klinik.strip(),
        "alamat_baris1": alamat_baris1.strip() or None,
        "alamat_baris2": alamat_baris2.strip() or None,
        "alamat_baris3": alamat_baris3.strip() or None,
        "no_telepon": no_telepon.strip() or None,
        "no_whatsapp": no_whatsapp.strip() or None,
        "email": email.strip() or None,
        "website": website.strip() or None,
        "footer_text": footer_text.strip() or None,
        "default_paper_nota": default_paper_nota,
        "default_paper_soap": default_paper_soap,
        "ttd_dokter_text": ttd_dokter_text.strip() or None,
        "no_sia": no_sia.strip() or None,
        "rm_prefix": rm_prefix.strip() or None,
        "lead_time_hari": lead_time_hari.strip() or "14",
        "safety_hari": safety_hari.strip() or "7",
    }

    try:
        KlinikConfigService(db).update_with_audit(
            update_data=update_data,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Gagal update: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Konfigurasi klinik berhasil diperbarui.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/settings/klinik/logo — Upload logo file
# =============================================================================
@router.post("/settings/klinik/logo")
async def settings_klinik_logo_upload(
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    if not file or not file.filename:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote('File logo tidak dipilih.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        file_bytes = await file.read()
        service = KlinikConfigService(db)
        rel_path = service.save_logo(
            file_bytes=file_bytes,
            original_filename=file.filename,
        )
        service.update_with_audit(
            update_data={"logo_path": rel_path},
            actor_id_staf=user.id_staf,
            request=request,
        )
    except Exception as e:
        # service raise HTTPException untuk validation errors
        detail = getattr(e, "detail", str(e))
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Upload gagal: {detail}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Logo berhasil diupload.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/settings/klinik/logo/delete — Remove logo
# =============================================================================
@router.post("/settings/klinik/logo/delete")
def settings_klinik_logo_delete(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        KlinikConfigService(db).delete_logo(
            actor_id_staf=user.id_staf,
            request=request,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Gagal hapus logo: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Logo berhasil dihapus.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/settings/klinik/mini-logo — Upload mini-logo (ikon topbar)
# =============================================================================
@router.post("/settings/klinik/mini-logo")
async def settings_klinik_mini_logo_upload(
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    if not file or not file.filename:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote('File mini-logo tidak dipilih.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        file_bytes = await file.read()
        service = KlinikConfigService(db)
        rel_path = service.save_logo(
            file_bytes=file_bytes,
            original_filename=file.filename,
            basename="mini_logo",
        )
        service.update_with_audit(
            update_data={"mini_logo_path": rel_path},
            actor_id_staf=user.id_staf,
            request=request,
        )
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Upload mini-logo gagal: {detail}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Mini-logo berhasil diupload.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/settings/klinik/mini-logo/delete — Remove mini-logo
# =============================================================================
@router.post("/settings/klinik/mini-logo/delete")
def settings_klinik_mini_logo_delete(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        KlinikConfigService(db).delete_logo(
            actor_id_staf=user.id_staf,
            request=request,
            field="mini_logo_path",
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Gagal hapus mini-logo: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Mini-logo berhasil dihapus.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# APOTEKER (MK-L2) — kelola daftar apoteker + SIPA (dropdown saat buat PO)
# =============================================================================
@router.post("/settings/klinik/apoteker")
async def settings_apoteker_add(
    request: Request,
    db: DbSession,
    nama_apoteker: str = Form(...),
    no_sipa: str = Form(default=""),
    masa_berlaku: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    mb = None
    if masa_berlaku.strip():
        try:
            mb = date.fromisoformat(masa_berlaku.strip())
        except ValueError:
            mb = None
    try:
        KlinikConfigService(db).add_apoteker(
            nama_apoteker=nama_apoteker, no_sipa=no_sipa, masa_berlaku=mb,
            actor_id_staf=user.id_staf, request=request,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Gagal tambah apoteker: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Apoteker ditambahkan.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/klinik/apoteker/{id_apoteker}/toggle")
async def settings_apoteker_toggle(
    id_apoteker: int,
    request: Request,
    db: DbSession,
    active: str = Form(default="1"),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        KlinikConfigService(db).set_apoteker_active(
            id_apoteker=id_apoteker, active=(active == "1"),
            actor_id_staf=user.id_staf, request=request,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/settings/klinik?err={quote(f'Gagal ubah status apoteker: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/settings/klinik?ok={quote('Status apoteker diperbarui.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
