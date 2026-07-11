"""
Manajemen Staf - Owner/Superadmin/Admin only:
- GET  /web/staf                                  - list + filter role + filter aktif
- GET  /web/staf/tambah                           - form tambah user baru
- POST /web/staf/tambah                           - submit user baru
- GET  /web/staf/{id_staf}                        - detail staf
- POST /web/staf/{id_staf}/update-profile         - edit nama_staf
- POST /web/staf/{id_staf}/set-pin                - set/reset PIN target user
- POST /web/staf/{id_staf}/reset-password         - Owner/Admin reset password staf lain
- POST /web/staf/{id_staf}/toggle-active          - aktifkan/nonaktifkan akun

Route order: /staf/tambah HARUS sebelum /staf/{id_staf}, supaya FastAPI
tidak match "tambah" sebagai integer id_staf.
"""

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from pydantic import ValidationError

from app.core.deps import DbSession
from app.db.models import StafRoleEnum
from app.schemas.staf import StafCreateRequest, StafUpdateRequest
from app.services.staf_service import StafService
from app.web.routes._shared import (
    build_shell_context,
    friendly_validation_error,
    get_user_from_cookie,
    require_owner_only,
    require_staf_mgmt_role,
    templates,
)


router = APIRouter(tags=["Web Manajemen Staf"])


# =============================================================================
# GET /web/staf - list + filter
# =============================================================================
@router.get("/staf", response_class=HTMLResponse)
def staf_list_page(request: Request, db: DbSession, role: str = "", only_active: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem;font-family:sans-serif'>"
            "403 - Hanya Owner/Superadmin/Admin yang boleh akses halaman ini.</div>",
            status_code=403,
        )

    role_filter = None
    if role:
        try:
            role_filter = StafRoleEnum(role)
        except ValueError:
            role_filter = None
    only_active_bool = only_active == "1"

    staf_list = StafService(db).list_all(only_active=only_active_bool, role=role_filter)
    success_msg = request.query_params.get("ok")

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/staf",
        page_subtitle="Kelola akun staf klinik",
        data=[s.model_dump() for s in staf_list],
        total=len(staf_list),
        roles=[r.value for r in StafRoleEnum],
        filter_role=role,
        only_active=only_active_bool,
        success=success_msg,
    )
    return templates.TemplateResponse(request, "staf_list.html", ctx)


# =============================================================================
# GET /web/staf/tambah - form
# =============================================================================
@router.get("/staf/tambah", response_class=HTMLResponse)
def staf_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/staf",
        page_subtitle="Tambah user baru",
        roles=[r.value for r in StafRoleEnum],
        form={},
        error=None,
    )
    return templates.TemplateResponse(request, "staf_form.html", ctx)


# =============================================================================
# POST /web/staf/tambah - submit
# =============================================================================
@router.post("/staf/tambah", response_class=HTMLResponse)
def staf_tambah_submit(
    request: Request,
    db: DbSession,
    username: str = Form(...),
    password: str = Form(...),
    nama_staf: str = Form(...),
    role: str = Form(...),
    pin: str = Form(""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    ctx_base = build_shell_context(
        user,
        db=db,
        current_path="/web/staf",
        page_subtitle="Tambah user baru",
        roles=[r.value for r in StafRoleEnum],
        form={"username": username, "nama_staf": nama_staf, "role": role, "pin": pin},
    )

    try:
        role_enum = StafRoleEnum(role)
    except ValueError:
        return templates.TemplateResponse(
            request, "staf_form.html",
            {**ctx_base, "error": f"Role tidak valid: {role}"},
        )

    try:
        payload = StafCreateRequest(
            username=username, password=password, nama_staf=nama_staf,
            role=role_enum, pin=pin if pin else None,
        )
    except ValidationError as e:
        return templates.TemplateResponse(
            request, "staf_form.html",
            {**ctx_base, "error": friendly_validation_error(e)},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request, "staf_form.html",
            {**ctx_base, "error": f"Data tidak valid: {e!s}"},
        )

    try:
        created = StafService(db).register_staf_baru(
            payload=payload, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            request, "staf_form.html", {**ctx_base, "error": e.detail},
        )
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            request, "staf_form.html", {**ctx_base, "error": f"Gagal: {e!s}"},
        )

    return RedirectResponse(
        url=f"/web/staf?ok=User+{created.username}+berhasil+dibuat",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/staf/{id_staf} - detail
# =============================================================================
@router.get("/staf/{id_staf}", response_class=HTMLResponse)
def staf_detail_page(request: Request, db: DbSession, id_staf: int):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    try:
        staf_data = StafService(db).get_by_id(id_staf)
    except HTTPException as e:
        return HTMLResponse(
            f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>",
            status_code=e.status_code,
        )

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/staf",
        page_subtitle="Detail staf",
        staf=staf_data.model_dump(),
        current_user_id=user.id_staf,
        current_user_role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        success=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "staf_detail.html", ctx)


# =============================================================================
# POST /web/staf/{id_staf}/update-profile - Owner/Admin edit nama_staf
# =============================================================================
@router.post("/staf/{id_staf}/update-profile")
def staf_update_profile(
    request: Request,
    db: DbSession,
    id_staf: int,
    nama_staf: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    nama_clean = (nama_staf or "").strip()
    if len(nama_clean) < 1 or len(nama_clean) > 100:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Nama+staf+1-100+karakter",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        payload = StafUpdateRequest(nama_staf=nama_clean)
        StafService(db).update_profile(
            id_staf=id_staf, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Gagal:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/staf/{id_staf}?ok=Nama+berhasil+diubah",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/staf/{id_staf}/set-pin - Owner/Admin set/reset PIN target user
# Kosong = hapus PIN.
# =============================================================================
@router.post("/staf/{id_staf}/set-pin")
def staf_set_pin(
    request: Request,
    db: DbSession,
    id_staf: int,
    new_pin: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    pin_clean = (new_pin or "").strip()

    if pin_clean and (len(pin_clean) < 4 or len(pin_clean) > 20):
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=PIN+harus+4-20+karakter+atau+kosongkan+untuk+hapus",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        StafService(db).reset_pin(
            id_staf=id_staf,
            new_pin=pin_clean if pin_clean else None,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Gagal:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = "PIN+berhasil+di-set" if pin_clean else "PIN+berhasil+dihapus"
    return RedirectResponse(
        url=f"/web/staf/{id_staf}?ok={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/staf/{id_staf}/reset-password
# =============================================================================
@router.post("/staf/{id_staf}/reset-password")
def staf_reset_password(
    request: Request,
    db: DbSession,
    id_staf: int,
    new_password: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    if len(new_password) < 6:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Password+min+6+karakter",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        StafService(db).reset_password(
            id_staf=id_staf, new_password=new_password,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Gagal:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/staf/{id_staf}?ok=Password+berhasil+direset",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/staf/{id_staf}/toggle-active
# =============================================================================
@router.post("/staf/{id_staf}/toggle-active")
def staf_toggle_active(
    request: Request,
    db: DbSession,
    id_staf: int,
    is_active: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_staf_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Forbidden.</div>", status_code=403)

    # Lock-out guard
    if id_staf == user.id_staf:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Tidak+boleh+nonaktifkan+akun+sendiri",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    new_state = is_active == "1"
    try:
        StafService(db).set_active(
            id_staf=id_staf, is_active=new_state,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Gagal:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    state_label = "diaktifkan" if new_state else "dinonaktifkan"
    state_label = "diaktifkan" if new_state else "dinonaktifkan"
    return RedirectResponse(
        url=f"/web/staf/{id_staf}?ok=Akun+berhasil+{state_label}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/staf/{id_staf}/ubah-role — Owner-only (#326)
# =============================================================================
@router.post("/staf/{id_staf}/ubah-role")
def staf_ubah_role(
    id_staf: int,
    request: Request,
    db: DbSession,
    new_role: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Hanya+Owner+yang+bisa+ubah+role+staf",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        new_role_enum = StafRoleEnum(new_role)
    except ValueError:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Role+{new_role}+tidak+valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        StafService(db).update_role(
            id_staf=id_staf,
            new_role=new_role_enum,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/staf/{id_staf}?err=Gagal:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/staf/{id_staf}?ok=Role+berhasil+diubah+ke+{new_role}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
