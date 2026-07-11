"""
Web route: Export ke Finance sekarang (file-drop, DEC-066-R2).

Tombol MANUAL / kontingensi untuk Owner + Superadmin. Jalur normal tetap scheduler
harian 05:00 WIB; halaman ini untuk test & bila otomasi gagal.

SMART: cek 'content fingerprint' periode yang diminta terhadap export terakhir
(periode+entity sama) di export_log.jsonl. Bila identik -> tampilkan halaman
konfirmasi (soft warning) sebelum benar-benar menulis ZIP. force=1 = tetap export.

Route:
- GET  /web/finance-export           landing: info batch terakhir + form periode
- POST /web/finance-export/run       jalankan (force=0 default). Bila identik & !force
                                     -> render konfirmasi. Bila berubah/force -> export.
"""
from datetime import date

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services import finance_export_batch as core
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_finance_export_role,
    forbidden,
    login_redirect,
    templates,
)

router = APIRouter(tags=["Web Finance Export"])

ENTITY = "KLN"  # single-clinic (DEC-066-R2)


def _guard(request: Request, db):
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, login_redirect()
    if not require_finance_export_role(user):
        return None, forbidden("Hanya Owner / Superadmin yang boleh Export ke Finance.")
    return user, None


def _default_period():
    """Selaras dengan cron: awal bulan berjalan .. hari ini."""
    today = date.today()
    return today.replace(day=1), today


def _drop_dir() -> str:
    return core.DEFAULT_DROP


def _render_landing(request, db, user, *, period_from, period_to, notice=None, result=None):
    last = core.last_matching(_drop_dir(), ENTITY, period_from, period_to)
    recent = list(reversed(core.read_log(_drop_dir())))[:8]
    ctx = build_shell_context(
        user, db=db, current_path="/web/finance-export",
        page_subtitle="Export manual ke folder Finance (kontingensi / test)",
        entity=ENTITY,
        period_from=period_from.isoformat(),
        period_to=period_to.isoformat(),
        drop_dir=_drop_dir(),
        last=last,
        recent=recent,
        notice=notice,
        result=result,
    )
    return templates.TemplateResponse(request, "finance_export.html", ctx)


@router.get("/finance-export", response_class=HTMLResponse)
def finance_export_landing(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    d0, d1 = _default_period()
    return _render_landing(request, db, user, period_from=d0, period_to=d1)


def _parse_period(tgl_dari, tgl_sampai):
    d0, d1 = _default_period()
    try:
        if tgl_dari:
            d0 = date.fromisoformat(tgl_dari)
        if tgl_sampai:
            d1 = date.fromisoformat(tgl_sampai)
    except ValueError:
        return None, None, "Format tanggal harus YYYY-MM-DD."
    if d0 > d1:
        return None, None, "Tanggal 'dari' tidak boleh setelah 'sampai'."
    return d0, d1, None


@router.post("/finance-export/run", response_class=HTMLResponse)
def finance_export_run(
    request: Request,
    db: DbSession,
    tgl_dari: str = Form(""),
    tgl_sampai: str = Form(""),
    force: str = Form("0"),
):
    user, resp = _guard(request, db)
    if resp:
        return resp

    d0, d1, err = _parse_period(tgl_dari, tgl_sampai)
    if err:
        d0, d1 = _default_period()
        return _render_landing(request, db, user, period_from=d0, period_to=d1,
                               notice={"level": "error", "text": err})

    is_force = str(force) in ("1", "true", "on", "yes")
    try:
        res = core.smart_export(
            db, _drop_dir(), ENTITY, d0, d1,
            force=is_force, triggered_by=user.username, mode="manual",
        )
    except Exception as e:  # noqa: BLE001
        return _render_landing(request, db, user, period_from=d0, period_to=d1,
                               notice={"level": "error", "text": f"Gagal export: {e}"})

    if res["status"] == "no_change":
        # Soft warning + halaman konfirmasi (tetap export y/n)
        return _render_landing(request, db, user, period_from=d0, period_to=d1, result=res,
                               notice={"level": "confirm", "text":
                                       "Data identik dengan export terakhir — belum perlu export."})

    # exported
    if res.get("forced_identical"):
        txt = "Export dibuat (dipaksa walau data identik)."
    elif res.get("changed"):
        txt = "Export dibuat — ada perubahan data."
    else:
        txt = "Export dibuat — periode baru."
    return _render_landing(request, db, user, period_from=d0, period_to=d1, result=res,
                           notice={"level": "ok", "text": txt})


__all__ = ["router"]
