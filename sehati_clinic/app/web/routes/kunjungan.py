"""
Antrian Hari Ini (general/FO view):
- GET /web/kunjungan         — page shell + HTMX poll container
- GET /web/kunjungan/list    — HTMX partial, di-poll setiap 10s
"""

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from datetime import datetime

from app.core.deps import DbSession
from app.db.models._enums import StatusAntrianEnum
from app.services.kunjungan_service import KunjunganService
from app.web.routes._shared import (
    build_shell_context,
    get_dokter_aktif_list,
    get_user_from_cookie,
    require_antrian_mgmt_role,
    templates,
)


router = APIRouter(tags=["Web Antrian (Umum)"])


# Valid status transitions — keep in sync dengan KunjunganService._VALID_TRANSITIONS
# Used untuk render dropdown "Ubah" di tabel antrian (UI cue saja, service tetap validate).
VALID_TRANSITIONS = {
    "ANTRI_KONSULTASI": ["KONSULTASI", "BATAL"],
    "KONSULTASI": ["ANTRI_TREATMENT", "ANTRI_BAYAR", "ANTRI_OBAT", "BATAL"],
    "ANTRI_TREATMENT": ["ON_TREATMENT", "BATAL"],
    "ON_TREATMENT": ["ANTRI_BAYAR", "ANTRI_OBAT", "COMPLETED", "BATAL"],
    "ANTRI_BAYAR": ["ANTRI_OBAT", "COMPLETED", "BATAL"],
    "ANTRI_OBAT": ["COMPLETED", "BATAL"],
}


# =============================================================================
# GET /web/kunjungan
# =============================================================================
@router.get("/kunjungan", response_class=HTMLResponse)
def kunjungan_antrian_page(request: Request, db: DbSession):
    """Render halaman antrian umum. Content di-poll via HTMX setiap 10s."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kunjungan",
        page_subtitle="Antrian aktif (auto-refresh 10s)",
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
        # FO-ASSIGN-DOKTER #329: dokter list untuk dropdown di form Ubah Status
        dokter_list=get_dokter_aktif_list(db),
    )
    return templates.TemplateResponse(request, "kunjungan_antrian.html", ctx)


# =============================================================================
# GET /web/kunjungan/list — HTMX partial
# =============================================================================
# =============================================================================
# Warna antrian FO (WARNA_ANTRIAN_FO_DESIGN) — MAX waktu tunggu per-tahap.
# Ambang (yellow_min, red_min) per status. Status tak terdaftar = TIDAK diwarnai (mis. ANTRI_OBAT).
# Timestamp: waktu_masuk_status (fallback tgl_kunjungan). Inline-style (B-028 safe).
# =============================================================================
# (yellow_min, red_min) = menit PERTAMA jadi kuning / merah (band pakai mx >= min).
# Konsul/treatment: <20 hijau, 20-29 kuning, >=30 merah.
# Bayar: <6 hijau, 6-10 kuning, >10 merah (jadi merah pertama = 11).
STAGE_WAIT_THRESHOLDS = {
    "ANTRI_KONSULTASI": (20, 30),
    "ANTRI_TREATMENT": (20, 30),
    "ANTRI_BAYAR": (6, 11),
    # ANTRI_OBAT sengaja tidak diwarnai (racikan) — lihat WARNA_ANTRIAN_FO_DESIGN §9.
}
_STAGE_NEUTRAL = {
    "ANTRI_KONSULTASI": {"border": "#bfdbfe", "bg": "#ffffff", "fg": "#1d4ed8"},
    "ANTRI_TREATMENT": {"border": "#e9d5ff", "bg": "#ffffff", "fg": "#7e22ce"},
    "ANTRI_BAYAR": {"border": "#fde68a", "bg": "#ffffff", "fg": "#b45309"},
}
_BAND_GREEN = {"border": "#34d399", "bg": "#ecfdf5", "fg": "#047857"}
_BAND_YELLOW = {"border": "#f59e0b", "bg": "#fffbeb", "fg": "#b45309"}
_BAND_RED = {"border": "#ef4444", "bg": "#fef2f2", "fg": "#b91c1c"}


def _stage_waits(items) -> dict:
    """MAX menit tunggu per tahap -> band warna. Kunci = status di STAGE_WAIT_THRESHOLDS.
    Timestamp = waktu_masuk_status (fallback tgl_kunjungan). tz basis sama (DEC-080).
    Clamp negatif/None/>24j. Tahap tanpa pasien -> netral (warna dasar tahap)."""
    now = datetime.now()
    maxima = {}
    for it in items:
        st = it.get("status_antrian")
        if st not in STAGE_WAIT_THRESHOLDS:
            continue
        t = it.get("waktu_masuk_status") or it.get("tgl_kunjungan")
        if not isinstance(t, datetime):
            continue
        mins = (now - t).total_seconds() / 60.0
        if mins < 0:
            mins = 0.0
        if mins > 1440:
            continue
        if st not in maxima or mins > maxima[st]:
            maxima[st] = mins
    out = {}
    for st, (ymin, rmin) in STAGE_WAIT_THRESHOLDS.items():
        if st not in maxima:
            out[st] = dict(_STAGE_NEUTRAL[st], max_min=None)
            continue
        mx = int(maxima[st])
        band = _BAND_RED if mx >= rmin else _BAND_YELLOW if mx >= ymin else _BAND_GREEN
        out[st] = dict(band, max_min=mx)
    return out


@router.get("/kunjungan/list", response_class=HTMLResponse)
def kunjungan_antrian_partial(request: Request, db: DbSession):
    """HTMX partial — counter cards + tabel antrian. Di-poll setiap 10s."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse(
            "<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>"
            "Sesi habis, silakan login ulang.</div>",
            status_code=401,
        )

    try:
        antrian_resp = KunjunganService(db).lihat_antrian_hari_ini(exclude_completed=True)
    except Exception as e:
        return HTMLResponse(
            f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Error: {e!s}</div>",
            status_code=500,
        )

    antrian_dict = antrian_resp.model_dump()
    counter = {
        "ANTRI_KONSULTASI": 0,
        "KONSULTASI": 0,
        "ANTRI_TREATMENT": 0,
        "ON_TREATMENT": 0,
        "ANTRI_BAYAR": 0,
        "ANTRI_OBAT": 0,
    }
    for item in antrian_dict.get("data", []):
        st = item.get("status_antrian", "")
        if st in counter:
            counter[st] += 1
        if item.get("jenis_kelamin") and hasattr(item["jenis_kelamin"], "value"):
            item["jenis_kelamin"] = item["jenis_kelamin"].value
        if item.get("tipe_membership") and hasattr(item["tipe_membership"], "value"):
            item["tipe_membership"] = item["tipe_membership"].value

    return templates.TemplateResponse(
        request,
        "_antrian_content.html",
        {
            "antrian": antrian_dict,
            "counter": counter,
            "stage_waits": _stage_waits(antrian_dict.get("data", [])),
            "can_manage_antrian": require_antrian_mgmt_role(user),
            "valid_transitions": VALID_TRANSITIONS,
            # FO-ASSIGN-DOKTER #329: dokter list untuk dropdown di form Ubah Status
            "dokter_list": get_dokter_aktif_list(db),
        },
    )


# =============================================================================
# GET /web/kunjungan/{id_kunjungan}/cetak-nomor — cetak thermal nomor antrian (NA-PRINT)
# Auto-print via _print_base (window.print on load). Non-blocking, ter-audit.
# =============================================================================
@router.get("/kunjungan/{id_kunjungan}/cetak-nomor", response_class=HTMLResponse)
def kunjungan_cetak_nomor(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Tidak berwenang.</div>", status_code=403)
    from app.services.print_service import PrintService
    try:
        ctx = PrintService(db).prepare_antrian_context(id_kunjungan, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<div style='padding:2rem'>Gagal cetak: {e!s}</div>", status_code=500)
    return templates.TemplateResponse(request, "print/antrian_thermal.html", ctx)


# =============================================================================
# POST /web/kunjungan/{id_kunjungan}/ubah-status (Patch 4)
# FO/Admin/Owner/Superadmin ubah status sesuai state machine valid.
# =============================================================================
# =============================================================================
# POST /web/kunjungan/{id_kunjungan}/ubah-dokter (FO-ASSIGN-DOKTER #329 FIX-2)
# Reassign dokter dituju tanpa ubah status_antrian.
# =============================================================================
@router.post("/kunjungan/{id_kunjungan}/ubah-dokter")
def kunjungan_ubah_dokter(
    id_kunjungan: int,
    request: Request,
    db: DbSession,
    id_staf_dokter_assigned: str = Form(""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 — Forbidden.</div>", status_code=403)

    s = (id_staf_dokter_assigned or "").strip()
    id_dokter_int = None
    if s:
        try:
            id_dokter_int = int(s)
        except ValueError:
            id_dokter_int = None

    try:
        KunjunganService(db).ubah_dokter_assigned(
            id_kunjungan=id_kunjungan,
            id_staf_dokter_assigned=id_dokter_int,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = "Dokter+dituju+diupdate" if id_dokter_int and id_dokter_int > 0 else "Dokter+di-clear+(bebas)"
    return RedirectResponse(
        url=f"/web/kunjungan?ok={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/kunjungan/{id_kunjungan}/ubah-status")
def kunjungan_ubah_status(
    id_kunjungan: int,
    request: Request,
    db: DbSession,
    status_baru: str = Form(...),
    id_staf_dokter_assigned: str = Form(""),  # FO-ASSIGN-DOKTER #329 (legacy, sekarang opsional)
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    try:
        status_enum = StatusAntrianEnum(status_baru)
    except ValueError:
        return RedirectResponse(
            url=f"/web/kunjungan?err=Status+tidak+valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # FO-ASSIGN-DOKTER #329: parse optional dokter assignment.
    # 0 / empty = no change. Positive int = set assigned. -1 = clear (NULL).
    id_dokter_int = None
    s = (id_staf_dokter_assigned or "").strip()
    if s:
        try:
            id_dokter_int = int(s)
        except ValueError:
            id_dokter_int = None

    try:
        KunjunganService(db).ubah_status(
            id_kunjungan=id_kunjungan,
            status_baru=status_enum,
            allow_batal=True,
            actor_id_staf=user.id_staf,
            request=request,
            id_staf_dokter_assigned=id_dokter_int,
        )
        # DEC-030: service-owned transaction — service yang commit, router tidak.
    except HTTPException as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/kunjungan?ok=Status+berhasil+diubah+ke+{status_baru}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/kunjungan/{id_kunjungan}/batal (Patch 4)
# Soft cancel — status diset BATAL.
# =============================================================================
@router.post("/kunjungan/{id_kunjungan}/batal")
def kunjungan_batal(
    id_kunjungan: int,
    request: Request,
    db: DbSession,
    catatan_batal: str = Form(""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    # Catatan FO untuk audit trail (Bapak request 10 Juni 2026)
    catatan_clean = (catatan_batal or "").strip()
    if len(catatan_clean) < 5:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote('Catatan batal antrian minimal 5 karakter')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        KunjunganService(db).ubah_status(
            id_kunjungan=id_kunjungan,
            status_baru=StatusAntrianEnum.BATAL,
            allow_batal=True,
            actor_id_staf=user.id_staf,
            request=request,
            catatan_batal=catatan_clean,
        )
    except HTTPException as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kunjungan?err={quote(f'Gagal batal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url="/web/kunjungan?ok=Kunjungan+dibatalkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )
