"""
Profil + ganti password / nama / PIN (self):
- GET  /web/profil                    — render profil card + form ubah nama + ganti password + ubah PIN
- POST /web/profil/ganti-password     — validate + StafService.change_own_password
- POST /web/profil/update-nama        — self-edit nama_staf
- POST /web/profil/ubah-pin           — self-edit PIN, butuh current_password sebagai bukti identitas

Catatan: self-edit PIN butuh password karena PIN dipakai untuk otorisasi sensitif
(void item kasir, upsell). Tanpa proof identitas, kalau session bocor maka PIN bisa
diganti oleh attacker.
"""

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.core.security import verify_password
from app.schemas.staf import StafUpdateRequest
from app.services.staf_service import StafService
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    templates,
)


router = APIRouter(tags=["Web Profil"])


def _profil_ctx(user, db, error=None, success=None):
    """Helper - common context for profil.html."""
    return build_shell_context(
        user,
        db=db,
        current_path="/web/profil",
        page_subtitle="Akun & keamanan",
        error=error,
        success=success,
    )


# =============================================================================
# GET /web/profil
# =============================================================================
@router.get("/profil", response_class=HTMLResponse)
def profil_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request, "profil.html", _profil_ctx(user, db))


# =============================================================================
# POST /web/profil/ganti-password
# =============================================================================
@router.post("/profil/ganti-password", response_class=HTMLResponse)
def profil_ganti_password(
    request: Request,
    db: DbSession,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Konfirmasi password tidak cocok dengan password baru."),
        )
    if len(new_password) < 6:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Password baru minimal 6 karakter."),
        )
    if old_password == new_password:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Password baru harus berbeda dari password lama."),
        )

    try:
        StafService(db).change_own_password(
            current_user=user,
            old_password=old_password,
            new_password=new_password,
            request=request,
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            request, "profil.html", _profil_ctx(user, db, error=e.detail),
        )
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error=f"Gagal ganti password: {e!s}"),
        )

    return templates.TemplateResponse(
        request, "profil.html",
        _profil_ctx(user, db, success="Password berhasil diganti. Sesi berikutnya pakai password baru."),
    )


# =============================================================================
# POST /web/profil/update-nama - self-edit nama lengkap
# =============================================================================
@router.post("/profil/update-nama", response_class=HTMLResponse)
def profil_update_nama(
    request: Request,
    db: DbSession,
    nama_staf: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    nama_clean = (nama_staf or "").strip()
    if len(nama_clean) < 1 or len(nama_clean) > 100:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Nama lengkap harus 1-100 karakter."),
        )

    if nama_clean == user.nama_staf:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Nama lengkap tidak berubah."),
        )

    try:
        payload = StafUpdateRequest(nama_staf=nama_clean)
        StafService(db).update_profile(
            id_staf=user.id_staf, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
        db.refresh(user)
    except HTTPException as e:
        return templates.TemplateResponse(
            request, "profil.html", _profil_ctx(user, db, error=e.detail),
        )
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error=f"Gagal ubah nama: {e!s}"),
        )

    return templates.TemplateResponse(
        request, "profil.html",
        _profil_ctx(user, db, success="Nama lengkap berhasil diubah."),
    )


# =============================================================================
# POST /web/profil/ubah-pin - self-edit PIN, butuh password
# =============================================================================
@router.post("/profil/ubah-pin", response_class=HTMLResponse)
def profil_ubah_pin(
    request: Request,
    db: DbSession,
    current_password: str = Form(...),
    new_pin: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    # Verify password lama sebagai bukti identitas
    try:
        if not verify_password(current_password, user.password_hash):
            return templates.TemplateResponse(
                request, "profil.html",
                _profil_ctx(user, db, error="Password lama salah. PIN tidak diubah."),
            )
    except Exception:
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="Gagal verifikasi password."),
        )

    pin_clean = (new_pin or "").strip()
    if pin_clean and (len(pin_clean) < 4 or len(pin_clean) > 20):
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error="PIN harus 4-20 karakter, atau kosongkan untuk hapus PIN."),
        )

    try:
        StafService(db).reset_pin(
            id_staf=user.id_staf,
            new_pin=pin_clean if pin_clean else None,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            request, "profil.html", _profil_ctx(user, db, error=e.detail),
        )
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            request, "profil.html",
            _profil_ctx(user, db, error=f"Gagal ubah PIN: {e!s}"),
        )

    msg = "PIN berhasil di-set." if pin_clean else "PIN berhasil dihapus."
    return templates.TemplateResponse(
        request, "profil.html",
        _profil_ctx(user, db, success=msg),
    )



__all__ = ["router"]
