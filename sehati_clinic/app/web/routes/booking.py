"""
Web routes — Modul Booking (kalender bulan). Ref BOOKING_MODULE_DESIGN.md (Fase 1).

- GET  /web/booking                       - kalender bulan (?bulan=YYYY-MM)
- GET  /web/booking/hari/{tgl}            - detail booking 1 hari + aksi
- GET  /web/booking/tambah                - form booking baru (?tgl=)
- POST /web/booking/tambah
- GET  /web/booking/{id}/edit             - form edit
- POST /web/booking/{id}/edit
- POST /web/booking/{id}/confirm | /cancel | /reschedule
(check-in → Kunjungan: Langkah 4)

Role: FO + Kasir + Admin + Owner + Superadmin.
Pola commit: service flush → route commit.
"""

import calendar as _cal
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.booking_service import BookingService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_dokter_aktif_list,
    get_user_from_cookie,
    login_redirect,
    require_antrian_mgmt_role,
    require_kasir_role,
    templates,
)

router = APIRouter(tags=["Web Booking"])


def _login():
    return login_redirect()


def _403():
    return forbidden("Halaman Booking hanya untuk FO / Kasir / Admin / Owner.")


def _can(user) -> bool:
    return require_antrian_mgmt_role(user) or require_kasir_role(user)


def _parse_bulan(bulan: str | None) -> tuple[int, int]:
    today = date.today()
    if not bulan:
        return today.year, today.month
    try:
        y, m = bulan.split("-")
        return int(y), int(m)
    except (ValueError, AttributeError):
        return today.year, today.month


def _shift_bulan(y: int, m: int, delta: int) -> str:
    idx = (y * 12 + (m - 1)) + delta
    return f"{idx // 12:04d}-{(idx % 12) + 1:02d}"


# =============================================================================
# GET /web/booking — kalender bulan
# =============================================================================
@router.get("/booking", response_class=HTMLResponse)
def booking_kalender(request: Request, db: DbSession, bulan: str = None):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()

    y, m = _parse_bulan(bulan)
    weeks_dates = _cal.Calendar(firstweekday=0).monthdatescalendar(y, m)
    weeks = [
        [{"day": d.day, "iso": d.isoformat(), "in_month": (d.month == m)} for d in wk]
        for wk in weeks_dates
    ]
    bookings = BookingService(db).list_bulan(y, m)  # {iso: [..]}

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/booking",
        page_subtitle="Kalender Booking",
        weeks=weeks,
        bookings=bookings,
        bulan_label=f"{_cal.month_name[m]} {y}",
        bulan_now=f"{y:04d}-{m:02d}",
        bulan_prev=_shift_bulan(y, m, -1),
        bulan_next=_shift_bulan(y, m, +1),
        today_iso=date.today().isoformat(),
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "booking_kalender.html", ctx)


# =============================================================================
# GET /web/booking/hari/{tgl} — detail 1 hari
# =============================================================================
@router.get("/booking/hari/{tgl}", response_class=HTMLResponse)
def booking_hari(tgl: str, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    try:
        d = date.fromisoformat(tgl)
    except ValueError:
        return HTMLResponse("<div style='padding:2rem'>Tanggal invalid.</div>", status_code=400)
    items = BookingService(db).list_tanggal(d)
    ctx = build_shell_context(
        user, db=db, current_path="/web/booking",
        page_subtitle=f"Booking {d.strftime('%d/%m/%Y')}",
        tgl=d, tgl_iso=d.isoformat(), items=items,
        is_hari_ini=(d == date.today()),
        bulan_kembali=f"{d.year:04d}-{d.month:02d}",
        flash=request.query_params.get("ok"), flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "booking_hari.html", ctx)


# =============================================================================
# GET form tambah / edit
# =============================================================================
@router.get("/booking/tambah", response_class=HTMLResponse)
def booking_form_tambah(request: Request, db: DbSession, tgl: str = None):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    svc = BookingService(db)
    ctx = build_shell_context(
        user, db=db, current_path="/web/booking", page_subtitle="Booking Baru",
        mode="tambah", booking=None, tgl_default=(tgl or date.today().isoformat()),
        members=svc.list_members(), dokter_list=get_dokter_aktif_list(db),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "booking_form.html", ctx)


@router.get("/booking/{id_booking}/edit", response_class=HTMLResponse)
def booking_form_edit(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    svc = BookingService(db)
    try:
        b = svc.get(id_booking)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.detail}</div>", status_code=e.status_code)
    ctx = build_shell_context(
        user, db=db, current_path="/web/booking", page_subtitle="Edit Booking",
        mode="edit", booking=b, tgl_default=b.tgl_rencana.isoformat(),
        members=svc.list_members(), dokter_list=get_dokter_aktif_list(db),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "booking_form.html", ctx)


# =============================================================================
# POST tambah / edit / confirm / cancel / reschedule
# =============================================================================
def _redir(url, ok=None, err=None):
    q = f"?ok={quote(ok)}" if ok else (f"?err={quote(err)}" if err else "")
    return RedirectResponse(url=url + q, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/booking/tambah", response_class=HTMLResponse)
async def booking_tambah(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    f = await request.form()
    try:
        b = BookingService(db).create(
            id_pasien=int(f.get("id_pasien")),
            tgl=f.get("tgl_rencana"), jam=f.get("jam_rencana"),
            id_staf_dokter_dituju=(int(f["id_staf_dokter_dituju"]) if f.get("id_staf_dokter_dituju") else None),
            keluhan_utama=f.get("keluhan_utama"), catatan=f.get("catatan"),
            actor_id_staf=user.id_staf, request=request,
        )
        db.commit()
    except HTTPException as e:
        return _redir("/web/booking/tambah", err=str(e.detail))
    except Exception as e:
        db.rollback()
        return _redir("/web/booking/tambah", err=f"Gagal: {e!s}")
    return _redir(f"/web/booking?bulan={b.tgl_rencana.year:04d}-{b.tgl_rencana.month:02d}", ok="Booking dibuat.")


@router.post("/booking/{id_booking}/edit", response_class=HTMLResponse)
async def booking_edit(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    f = await request.form()
    try:
        b = BookingService(db).edit(
            id_booking,
            tgl=f.get("tgl_rencana"), jam=f.get("jam_rencana"),
            id_staf_dokter_dituju=(int(f["id_staf_dokter_dituju"]) if f.get("id_staf_dokter_dituju") else None),
            keluhan_utama=f.get("keluhan_utama"), catatan=f.get("catatan"),
            actor_id_staf=user.id_staf, request=request,
        )
        db.commit()
    except HTTPException as e:
        return _redir(f"/web/booking/{id_booking}/edit", err=str(e.detail))
    except Exception as e:
        db.rollback()
        return _redir(f"/web/booking/{id_booking}/edit", err=f"Gagal: {e!s}")
    return _redir(f"/web/booking/hari/{b.tgl_rencana.isoformat()}", ok="Booking diperbarui.")


def _simple_action(action, id_booking, request, db, user, **kw):
    svc = BookingService(db)
    b = getattr(svc, action)(id_booking, actor_id_staf=user.id_staf, request=request, **kw)
    db.commit()
    return b


@router.post("/booking/{id_booking}/confirm", response_class=HTMLResponse)
async def booking_confirm(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    tgl = BookingService(db).get(id_booking).tgl_rencana.isoformat()
    try:
        _simple_action("confirm", id_booking, request, db, user)
    except HTTPException as e:
        return _redir(f"/web/booking/hari/{tgl}", err=str(e.detail))
    return _redir(f"/web/booking/hari/{tgl}", ok="Booking dikonfirmasi.")


@router.post("/booking/{id_booking}/cancel", response_class=HTMLResponse)
async def booking_cancel(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    tgl = BookingService(db).get(id_booking).tgl_rencana.isoformat()
    try:
        _simple_action("cancel", id_booking, request, db, user)
    except HTTPException as e:
        return _redir(f"/web/booking/hari/{tgl}", err=str(e.detail))
    return _redir(f"/web/booking/hari/{tgl}", ok="Booking dibatalkan.")


@router.post("/booking/{id_booking}/reschedule", response_class=HTMLResponse)
async def booking_reschedule(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    f = await request.form()
    old_tgl = BookingService(db).get(id_booking).tgl_rencana.isoformat()
    try:
        new = BookingService(db).reschedule(
            id_booking, tgl_baru=f.get("tgl_rencana"), jam_baru=f.get("jam_rencana"),
            actor_id_staf=user.id_staf, request=request,
        )
        db.commit()
    except HTTPException as e:
        return _redir(f"/web/booking/hari/{old_tgl}", err=str(e.detail))
    except Exception as e:
        db.rollback()
        return _redir(f"/web/booking/hari/{old_tgl}", err=f"Gagal: {e!s}")
    return _redir(f"/web/booking/hari/{new.tgl_rencana.isoformat()}", ok="Booking dijadwalkan ulang.")


@router.post("/booking/{id_booking}/checkin", response_class=HTMLResponse)
async def booking_checkin(id_booking: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return _login()
    if not _can(user):
        return _403()
    f = await request.form()
    tujuan = f.get("status_antrian") or "ANTRI_KONSULTASI"
    tgl = BookingService(db).get(id_booking).tgl_rencana.isoformat()
    try:
        result = BookingService(db).check_in(
            id_booking, status_antrian=tujuan,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return _redir(f"/web/booking/hari/{tgl}", err=str(e.detail))
    except Exception as e:
        db.rollback()
        return _redir(f"/web/booking/hari/{tgl}", err=f"Gagal: {e!s}")
    data = result.get("data", {}) if isinstance(result, dict) else {}
    nomor = data.get("nomor_antrean", "?")
    label = "Tindakan" if tujuan == "ANTRI_TREATMENT" else "Konsultasi"
    return _redir(f"/web/booking/hari/{tgl}", ok=f"Check-in ({label}) sukses — nomor antrean #{nomor}.")


__all__ = ["router"]
