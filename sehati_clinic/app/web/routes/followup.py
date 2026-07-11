"""
Web routes — Modul Follow-up Reminder (#7). Ref FOLLOWUP_REMINDER_DESIGN.md.

- GET  /web/followup                         - worklist (mode=minggu|hari, ?tgl=YYYY-MM-DD)
- POST /web/followup/{id}/confirm
- POST /web/followup/{id}/no-answer
- POST /web/followup/{id}/cancel
- POST /web/followup/{id}/reschedule          (field: due_baru=YYYY-MM-DD)

Role: FO + Kasir + Owner + Superadmin (sama seperti Booking).
Pola commit: service commit internal.
"""

from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.followup_service import FollowupService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_antrian_mgmt_role,
    require_kasir_role,
    templates,
)

router = APIRouter(tags=["Web Follow-up"])

MIN_DATE = date(2000, 1, 1)


def _login():
    return login_redirect()


def _403():
    return forbidden("Halaman Follow-up hanya untuk FO / Kasir / Owner.")


def _can(user) -> bool:
    return require_antrian_mgmt_role(user) or require_kasir_role(user)


def _parse_tgl(tgl: str | None) -> date:
    if not tgl:
        return date.today()
    try:
        return date.fromisoformat(tgl)
    except (ValueError, TypeError):
        return date.today()


def _window(mode: str, anchor: date) -> tuple[date, date, date, date]:
    """Return (start_label, end, prev_anchor, next_anchor)."""
    if mode == "hari":
        return anchor, anchor, anchor - timedelta(days=1), anchor + timedelta(days=1)
    # minggu: Senin..Minggu
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    return start, end, start - timedelta(days=7), start + timedelta(days=7)


def _redir(mode: str, tgl: date, ok: str | None = None, err: str | None = None):
    q = f"?mode={mode}&tgl={tgl.isoformat()}"
    if ok:
        q += f"&ok={quote(ok)}"
    if err:
        q += f"&err={quote(err)}"
    return RedirectResponse(url="/web/followup" + q, status_code=status.HTTP_303_SEE_OTHER)


# =============================================================================
# GET /web/followup — worklist
# =============================================================================
@router.get("/followup", response_class=HTMLResponse)
def followup_list(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()

    mode = request.query_params.get("mode") or "minggu"
    if mode not in ("minggu", "hari"):
        mode = "minggu"
    anchor = _parse_tgl(request.query_params.get("tgl"))
    start, end, prev_anchor, next_anchor = _window(mode, anchor)

    svc = FollowupService(db)
    # Worklist = semua yang masih open dengan due_date <= akhir window (termasuk telat).
    items = svc.list_due(MIN_DATE, end, only_open=True)
    counts = svc.counts_open(MIN_DATE, end)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/followup",
        page_subtitle="Follow-up",
        items=items,
        counts=counts,
        mode=mode,
        anchor=anchor,
        start=start,
        end=end,
        prev_anchor=prev_anchor,
        next_anchor=next_anchor,
        today=date.today(),
        ok=request.query_params.get("ok"),
        err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "followup_list.html", ctx)


# =============================================================================
# POST aksi
# =============================================================================
async def _ctx_after(request: Request) -> tuple[str, date]:
    f = await request.form()
    mode = f.get("mode") or "minggu"
    tgl = _parse_tgl(f.get("tgl"))
    return (mode if mode in ("minggu", "hari") else "minggu"), tgl


@router.post("/followup/{id_followup}/confirm", response_class=HTMLResponse)
async def followup_confirm(id_followup: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    mode, tgl = await _ctx_after(request)
    FollowupService(db).confirm(id_followup, user.id_staf)
    return _redir(mode, tgl, ok="Follow-up dikonfirmasi.")


@router.post("/followup/{id_followup}/no-answer", response_class=HTMLResponse)
async def followup_no_answer(id_followup: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    mode, tgl = await _ctx_after(request)
    FollowupService(db).no_answer(id_followup, user.id_staf)
    return _redir(mode, tgl, ok="Ditandai tidak terjawab.")


@router.post("/followup/{id_followup}/cancel", response_class=HTMLResponse)
async def followup_cancel(id_followup: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    mode, tgl = await _ctx_after(request)
    FollowupService(db).cancel(id_followup, user.id_staf)
    return _redir(mode, tgl, ok="Follow-up dibatalkan.")


@router.post("/followup/{id_followup}/reschedule", response_class=HTMLResponse)
async def followup_reschedule(id_followup: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    f = await request.form()
    mode = f.get("mode") or "minggu"
    mode = mode if mode in ("minggu", "hari") else "minggu"
    tgl = _parse_tgl(f.get("tgl"))
    raw = (f.get("due_baru") or "").strip()
    if not raw:
        return _redir(mode, tgl, err="Tanggal baru wajib diisi.")
    try:
        new_due = date.fromisoformat(raw)
    except ValueError:
        return _redir(mode, tgl, err="Format tanggal baru tidak valid.")
    FollowupService(db).reschedule(id_followup, user.id_staf, new_due)
    return _redir(mode, tgl, ok="Follow-up dijadwalkan ulang.")
