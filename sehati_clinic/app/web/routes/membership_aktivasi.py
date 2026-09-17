"""Web route — Worklist Membership Menunggu Aktivasi (M4).

GET /web/membership-aktivasi — daftar membership PAID (sudah dibayar) yang
menunggu diaktifkan CS. Tombol Aktifkan memanggil route aktivasi existing
(/web/pasien/{id}/membership/{id_history}/aktifkan?next=/web/membership-aktivasi).

Role: FO / Kasir / Admin / Owner / Superadmin (samakan dgn aksi aktivasi).
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.membership_service import MembershipService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_antrian_mgmt_role,
    require_kasir_role,
    templates,
)

router = APIRouter(tags=["Web Membership Aktivasi"])


def _can(user) -> bool:
    return require_antrian_mgmt_role(user) or require_kasir_role(user)


@router.get("/membership-aktivasi", response_class=HTMLResponse)
def membership_aktivasi_list(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Halaman ini untuk FO / Kasir / Admin / Owner.")
    items = MembershipService(db).list_awaiting_activation()
    ctx = build_shell_context(
        user, db=db, current_path="/web/membership-aktivasi",
        page_subtitle="Membership Menunggu Aktivasi",
        items=items,
        ok=request.query_params.get("ok"),
        err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "membership_aktivasi_list.html", ctx)


__all__ = ["router"]
