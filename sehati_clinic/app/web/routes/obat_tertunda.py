"""
Web routes — Obat Tertunda (P1-1). Ref OBAT_TERTUNDA_DESIGN.md.

- GET  /web/obat-tertunda                      - worklist obat dibayar tapi belum diserah
- POST /web/obat-tertunda/{id}/serahkan        - serah sekarang (potong stok, keluar daftar)
- POST /web/obat-tertunda/{id}/ubah-tgl        - reschedule tgl_janji_kirim

Role: FO / Kasir / Apotek / Owner / Superadmin / Admin (saling mengingatkan).
"""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.schemas.apotek import SerahkanObatRequest
from app.services.apotek_service import ApotekService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_antrian_mgmt_role,
    require_apoteker_role,
    require_kasir_role,
    templates,
)

router = APIRouter(tags=["Web Obat Tertunda"])


def _can(user) -> bool:
    return (
        require_antrian_mgmt_role(user)
        or require_kasir_role(user)
        or require_apoteker_role(user)
    )


@router.get("/obat-tertunda", response_class=HTMLResponse)
def obat_tertunda_list(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Halaman Obat Tertunda hanya untuk FO / Kasir / Apotek / Owner.")
    items = ApotekService(db).list_obat_tertunda()
    today = date.today()
    ctx = build_shell_context(
        user, db=db, current_path="/web/obat-tertunda", page_subtitle="Obat Tertunda",
        items=items, today=today,
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "obat_tertunda_list.html", ctx)


@router.post("/obat-tertunda/{id_kunjungan}/serahkan", response_class=HTMLResponse)
def obat_tertunda_serahkan(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    try:
        ApotekService(db).serahkan_obat(
            payload=SerahkanObatRequest(id_kunjungan=id_kunjungan),
            id_staf_apoteker=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(str(e.detail))}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(f'Gagal: {e!s}')}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/obat-tertunda?ok={quote('Obat diserahkan & stok terpotong.')}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/obat-tertunda/{id_kunjungan}/ubah-tgl", response_class=HTMLResponse)
async def obat_tertunda_ubah_tgl(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    raw = (f.get("tgl_baru") or "").strip()
    tgl = None
    if raw:
        try:
            tgl = date.fromisoformat(raw)
        except ValueError:
            tgl = None
    if tgl is None:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote('Tanggal baru tidak valid.')}", status_code=status.HTTP_303_SEE_OTHER)
    from app.db.models.kunjungan import Kunjungan
    kj = db.get(Kunjungan, id_kunjungan)
    if kj is not None and kj.tgl_janji_kirim is not None:
        kj.tgl_janji_kirim = tgl
        db.commit()
    return RedirectResponse(url=f"/web/obat-tertunda?ok={quote('Tanggal kirim diperbarui.')}", status_code=status.HTTP_303_SEE_OTHER)
