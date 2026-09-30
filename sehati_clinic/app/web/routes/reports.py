"""
Web Reports routes:
- GET /web/reports                — landing page (list reports yang tersedia)
- GET /web/reports/omzet          — Omzet Bulanan (chart + breakdown)
- GET /web/reports/top-treatment  — Top Treatment ranking

Role gate: REPORTS_ROLES (Owner + Superadmin + Admin).
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.reports_service import ReportsService
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_apoteker_role,
    require_master_data_role,
    require_reports_role,
    require_top_diagnosa_role,
    templates,
)


router = APIRouter(tags=["Web Reports"])


def _403() -> HTMLResponse:
    return HTMLResponse(
        "<div style='padding:2rem'>403 — Hanya Owner/Superadmin/Admin yang boleh akses Laporan.</div>",
        status_code=403,
    )


# =============================================================================
# GET /web/reports — landing page (list reports yang tersedia)
# =============================================================================

def _safe_int(v) -> Optional[int]:
    """Parse query param ke int; return None kalau kosong/invalid.

    Form HTML kirim '' saat field optional dibiarkan kosong, dan FastAPI
    Optional[int] tolak parsing string kosong → 422. Pakai str + manual parse.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


@router.get("/reports", response_class=HTMLResponse)
def reports_landing(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    # REPORTS-COMPART (#324): semua role yang punya akses ke salah satu report
    # boleh akses landing. Template conditional show cards yang relevant saja.
    from app.web.routes._shared import (
        require_kinerja_dokter_role,
        require_rekap_kasir_role,
        require_master_data_role,
        is_dokter_role,
        is_kasir_role,
        is_perawat_role,
    )
    has_any_access = (
        require_reports_role(user)  # Owner/Superadmin/Admin
        or require_kinerja_dokter_role(user)  # + Dokter
        or require_rekap_kasir_role(user)  # + Kasir
        or require_apoteker_role(user)  # + Apoteker (#363B)
        or is_perawat_role(user)  # + Perawat (Komisi Saya)
    )
    if not has_any_access:
        return _403()

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle="Pilih jenis laporan",
        # Conditional cards: kasih flag per access type
        can_see_omzet=require_reports_role(user),
        can_see_top_treatment=require_reports_role(user),
        can_see_top_diagnosa=require_top_diagnosa_role(user),
        can_see_kinerja_dokter=require_kinerja_dokter_role(user),
        can_see_rekap_kasir=require_rekap_kasir_role(user),
        can_see_tutup_kasir=require_rekap_kasir_role(user),
        can_see_rekap_harian=require_reports_role(user),
        can_see_audit_log=require_master_data_role(user),
        can_see_void_report=require_reports_role(user),
        can_see_apoteker_dispensed=require_apoteker_role(user),
        can_see_writeoff_report=require_apoteker_role(user),
        can_see_top_produk=require_apoteker_role(user),
        is_dokter_view=is_dokter_role(user),
        is_kasir_view=is_kasir_role(user),
        can_see_komisi=(require_reports_role(user) or is_dokter_role(user) or is_perawat_role(user)),
    )
    return templates.TemplateResponse(request, "reports_landing.html", ctx)


# =============================================================================
# GET /web/reports/omzet — Omzet Bulanan
# =============================================================================
@router.get("/reports/omzet", response_class=HTMLResponse)
def reports_omzet_bulanan(
    request: Request,
    db: DbSession,
    tahun: Optional[int] = None,
    bulan_dari: Optional[int] = None,
    bulan_sampai: Optional[int] = None,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_reports_role(user):
        return _403()

    today = date.today()
    if tahun is None:
        tahun = today.year
    if bulan_dari is None:
        bulan_dari = 1
    if bulan_sampai is None:
        bulan_sampai = today.month

    try:
        resp = ReportsService(db).omzet_bulanan(
            tahun=tahun, bulan_dari=bulan_dari, bulan_sampai=bulan_sampai,
        )
        data = resp.model_dump()
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    chart_labels = [b["bulan_label"] for b in data["per_bulan"]]
    chart_omzet = [float(b["total_omzet"]) for b in data["per_bulan"]]
    chart_transaksi = [b["jumlah_transaksi"] for b in data["per_bulan"]]
    tahun_options = list(range(today.year - 4, today.year + 2))

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Omzet Bulanan — {tahun}",
        data=data,
        chart_labels=chart_labels,
        chart_omzet=chart_omzet,
        chart_transaksi=chart_transaksi,
        tahun_options=tahun_options,
        tahun_selected=tahun,
        bulan_dari_selected=bulan_dari,
        bulan_sampai_selected=bulan_sampai,
    )
    return templates.TemplateResponse(request, "reports_omzet.html", ctx)


# =============================================================================
# GET /web/reports/top-treatment — Top Treatment ranking
# =============================================================================
@router.get("/reports/top-treatment", response_class=HTMLResponse)
def reports_top_treatment(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    status_filter: str = "SELESAI",
    limit: int = 50,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_reports_role(user):
        return _403()

    today = date.today()
    # Default: 30 hari terakhir
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=30))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        return HTMLResponse(
            "<div style='padding:2rem'>Format tanggal invalid (YYYY-MM-DD)</div>",
            status_code=400,
        )

    if status_filter not in ("SELESAI", "ALL"):
        status_filter = "SELESAI"

    try:
        resp = ReportsService(db).top_treatment(
            tgl_dari=d_dari, tgl_sampai=d_sampai,
            status_filter=status_filter, limit=limit,
        )
        data = resp.model_dump()
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    # Chart: top 10 by omzet (horizontal bar)
    top10 = data["items"][:10]
    chart_labels = [i["nama_treatment"] for i in top10]
    chart_omzet = [float(i["estimasi_omzet"]) for i in top10]
    chart_count = [i["jumlah_dilakukan"] for i in top10]

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Top Treatment {d_dari} sd {d_sampai}",
        data=data,
        chart_labels=chart_labels,
        chart_omzet=chart_omzet,
        chart_count=chart_count,
        tgl_dari_selected=d_dari.isoformat(),
        tgl_sampai_selected=d_sampai.isoformat(),
        status_filter_selected=status_filter,
    )
    return templates.TemplateResponse(request, "reports_top_treatment.html", ctx)


# =============================================================================
# GET /web/reports/kinerja-dokter — Kinerja Dokter ranking
# =============================================================================
@router.get("/reports/kinerja-dokter", response_class=HTMLResponse)
def reports_kinerja_dokter(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    # REPORTS-COMPART (#324): gate extended — Dokter juga bisa akses (own only)
    from app.web.routes._shared import require_kinerja_dokter_role, is_dokter_role
    if not require_kinerja_dokter_role(user):
        return _403()

    today = date.today()
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=30))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        return HTMLResponse(
            "<div style='padding:2rem'>Format tanggal invalid (YYYY-MM-DD)</div>",
            status_code=400,
        )

    # REPORTS-COMPART: auto-filter ke own kalau role=DOKTER (backend enforce)
    force_filter_id = user.id_staf if is_dokter_role(user) else None

    try:
        resp = ReportsService(db).kinerja_dokter(
            tgl_dari=d_dari,
            tgl_sampai=d_sampai,
            force_id_staf_filter=force_filter_id,
        )
        data = resp.model_dump()
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    # Chart: grouped bar (konsul vs tindakan per dokter)
    chart_labels = [i["nama_dokter"] for i in data["items"]]
    chart_konsul = [i["jumlah_konsul"] for i in data["items"]]
    chart_tindakan = [i["jumlah_tindakan"] for i in data["items"]]
    chart_omzet = [float(i["estimasi_omzet"]) for i in data["items"]]

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Kinerja Dokter {d_dari} sd {d_sampai}",
        data=data,
        chart_labels=chart_labels,
        chart_konsul=chart_konsul,
        chart_tindakan=chart_tindakan,
        chart_omzet=chart_omzet,
        tgl_dari_selected=d_dari.isoformat(),
        tgl_sampai_selected=d_sampai.isoformat(),
        # REPORTS-COMPART #324: flag untuk template tampilkan badge "Own only"
        is_own_only=force_filter_id is not None,
    )
    return templates.TemplateResponse(request, "reports_kinerja_dokter.html", ctx)


# =============================================================================
# GET /web/reports/rekap-kasir — Rekap Kasir Shift (REPORTS-COMPART #324)
# Owner/Superadmin/Admin: lihat semua kasir
# Kasir: auto-filter ke own shift
# =============================================================================
@router.get("/reports/rekap-kasir", response_class=HTMLResponse)
def reports_rekap_kasir(
    request: Request,
    db: DbSession,
    tgl: Optional[str] = None,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    from app.web.routes._shared import require_rekap_kasir_role, is_kasir_role
    if not require_rekap_kasir_role(user):
        return _403()

    today = date.today()
    try:
        d_tgl = date.fromisoformat(tgl) if tgl else today
    except ValueError:
        return HTMLResponse(
            "<div style='padding:2rem'>Format tanggal invalid (YYYY-MM-DD)</div>",
            status_code=400,
        )

    # REPORTS-COMPART: auto-filter ke own kalau role=KASIR
    force_filter_id = user.id_staf if is_kasir_role(user) else None

    try:
        data = ReportsService(db).rekap_kasir_shift(
            tgl=d_tgl,
            force_id_staf_filter=force_filter_id,
        )
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    # Chart: bar per kasir
    chart_labels = [k["nama_kasir"] for k in data["per_kasir"]]
    chart_omzet = [float(k["total_omzet"]) for k in data["per_kasir"]]

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Rekap Kasir Shift {d_tgl}",
        data=data,
        chart_labels=chart_labels,
        chart_omzet=chart_omzet,
        tgl_selected=d_tgl.isoformat(),
        is_own_only=force_filter_id is not None,
    )
    return templates.TemplateResponse(request, "reports_rekap_kasir.html", ctx)


# =============================================================================
# GET /web/reports/audit-log — Audit Log Viewer (Owner / Superadmin)
# =============================================================================
@router.get("/reports/audit-log", response_class=HTMLResponse)
def reports_audit_log(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    id_staf: Optional[str] = None,
    aksi: Optional[str] = None,
    tabel_target: Optional[str] = None,
    status_aksi: Optional[str] = None,
    view_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
):
    id_staf = _safe_int(id_staf)
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        # Audit log lebih sensitif — Owner/Superadmin only (pakai MASTER_DATA_ROLES gate)
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Hanya Owner/Superadmin yang boleh akses Audit Log.</div>",
            status_code=403,
        )

    today = date.today()
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=7))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        return HTMLResponse(
            "<div style='padding:2rem'>Format tanggal invalid (YYYY-MM-DD)</div>",
            status_code=400,
        )

    # Sanitize filter values
    aksi_clean = (aksi or "").strip() or None
    tabel_clean = (tabel_target or "").strip() or None
    status_clean = (status_aksi or "").strip().upper() or None
    if status_clean and status_clean not in ("SUCCESS", "FAILED"):
        status_clean = None
    view_clean = (view_filter or "").strip().lower() or None
    if view_clean not in ("only", "exclude"):
        view_clean = None

    try:
        service = ReportsService(db)
        resp = service.audit_log_list(
            tgl_dari=d_dari, tgl_sampai=d_sampai,
            id_staf=id_staf, aksi=aksi_clean,
            tabel_target=tabel_clean, status_aksi=status_clean,
            view_filter=view_clean,
            page=page, page_size=page_size,
        )
        dropdowns = service.audit_log_dropdowns()
        data = resp.model_dump()
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    # Build query string untuk pagination links (preserve filters)
    from urllib.parse import urlencode
    qs_base = {
        "tgl_dari": d_dari.isoformat(),
        "tgl_sampai": d_sampai.isoformat(),
        "page_size": page_size,
    }
    if id_staf:
        qs_base["id_staf"] = id_staf
    if aksi_clean:
        qs_base["aksi"] = aksi_clean
    if tabel_clean:
        qs_base["tabel_target"] = tabel_clean
    if status_clean:
        qs_base["status_aksi"] = status_clean
    if view_clean:
        qs_base["view_filter"] = view_clean

    def page_url(p: int) -> str:
        qs = dict(qs_base, page=p)
        return f"/web/reports/audit-log?{urlencode(qs)}"

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Audit Log {d_dari} sd {d_sampai} ({data['total_count']} entries)",
        data=data,
        dropdowns=dropdowns,
        tgl_dari_selected=d_dari.isoformat(),
        tgl_sampai_selected=d_sampai.isoformat(),
        id_staf_selected=id_staf,
        aksi_selected=aksi_clean or "",
        tabel_selected=tabel_clean or "",
        status_selected=status_clean or "",
        view_selected=view_clean or "",
        page_size_selected=page_size,
        prev_url=page_url(data["page"] - 1) if data["page"] > 1 else None,
        next_url=page_url(data["page"] + 1) if data["page"] < data["total_pages"] else None,
    )
    return templates.TemplateResponse(request, "reports_audit_log.html", ctx)




# =============================================================================
# Phase 6 (#364 DEC-063) — VOID REPORT
# =============================================================================
@router.get("/reports/void", response_class=HTMLResponse)
def reports_void(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    kasir_id: Optional[str] = None,
    voider_id: Optional[str] = None,
    reason: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
):
    # Parse optional int (form '' → None)
    kasir_id = _safe_int(kasir_id)
    voider_id = _safe_int(voider_id)
    """Halaman Reports Void — Owner/Superadmin/Admin only."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_reports_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Hanya Owner/Superadmin/Admin.</div>",
            status_code=403,
        )

    today = date.today()
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=7))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        return HTMLResponse("<div style='padding:2rem'>Format tanggal invalid</div>", status_code=400)

    reason_clean = (reason or "").strip().upper() or None
    valid_reasons = {"SALAH_INPUT", "CUSTOMER_CANCEL", "REFUND_PASCA_TINDAKAN",
                     "ITEM_RUSAK", "DUPLICATE_TRANSAKSI", "OTHER"}
    if reason_clean and reason_clean not in valid_reasons:
        reason_clean = None

    try:
        service = ReportsService(db)
        resp = service.get_void_report(
            tgl_dari=d_dari, tgl_sampai=d_sampai,
            page=page, page_size=page_size,
            kasir_id=kasir_id, voider_id=voider_id, reason=reason_clean,
        )
        data = resp.model_dump()
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    # Build query string untuk pagination
    from urllib.parse import urlencode
    qs_base = {
        "tgl_dari": d_dari.isoformat(),
        "tgl_sampai": d_sampai.isoformat(),
        "page_size": page_size,
    }
    if kasir_id:
        qs_base["kasir_id"] = kasir_id
    if voider_id:
        qs_base["voider_id"] = voider_id
    if reason_clean:
        qs_base["reason"] = reason_clean

    def page_url(p: int) -> str:
        return f"/web/reports/void?{urlencode(dict(qs_base, page=p))}"

    csv_url = f"/web/reports/void/csv?{urlencode(qs_base)}"

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Void Report {d_dari} sd {d_sampai} ({data['total_count']} entries)",
        data=data,
        tgl_dari_selected=d_dari.isoformat(),
        tgl_sampai_selected=d_sampai.isoformat(),
        kasir_id_selected=kasir_id,
        voider_id_selected=voider_id,
        reason_selected=reason_clean or "",
        page_size_selected=page_size,
        prev_url=page_url(data["page"] - 1) if data["page"] > 1 else None,
        next_url=page_url(data["page"] + 1) if data["page"] < data["total_pages"] else None,
        csv_url=csv_url,
    )
    return templates.TemplateResponse(request, "reports_void.html", ctx)


@router.get("/reports/void/csv")
def reports_void_csv(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    kasir_id: Optional[str] = None,
    voider_id: Optional[str] = None,
    reason: Optional[str] = None,
):
    kasir_id = _safe_int(kasir_id)
    voider_id = _safe_int(voider_id)
    """Export CSV semua void dalam rentang filter. Tidak pakai pagination."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_reports_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    today = date.today()
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=7))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        return HTMLResponse("Format tanggal invalid", status_code=400)

    reason_clean = (reason or "").strip().upper() or None

    # Fetch ALL (no pagination) — use big page_size
    resp = ReportsService(db).get_void_report(
        tgl_dari=d_dari, tgl_sampai=d_sampai,
        page=1, page_size=100000,
        kasir_id=kasir_id, voider_id=voider_id, reason=reason_clean,
    )

    # Build CSV in memory
    import csv, io
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "id_transaksi", "id_kunjungan", "no_rm", "nama_pasien",
        "waktu_bayar", "void_at",
        "total_tagihan", "void_reason_code", "void_reason_note",
        "void_approval_method", "late_void",
        "kasir_nama", "voider_nama",
    ])
    for it in resp.items:
        writer.writerow([
            it.id_transaksi, it.id_kunjungan or "", it.no_rm, it.nama_pasien,
            it.waktu_bayar.isoformat() if it.waktu_bayar else "",
            it.void_at.isoformat() if it.void_at else "",
            it.total_tagihan, it.void_reason_code or "", it.void_reason_note or "",
            it.void_approval_method or "", "TRUE" if it.late_void else "FALSE",
            it.kasir_nama or "", it.voider_nama or "",
        ])

    csv_content = buf.getvalue().encode("utf-8")
    filename = f"void_report_{d_dari}_to_{d_sampai}.csv"
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]


# =============================================================================
# #363B - GET /web/reports/apoteker-dispensed
# =============================================================================
@router.get("/reports/apoteker-dispensed", response_class=HTMLResponse)
def reports_apoteker_dispensed(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    apoteker_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    # Default date range: last 7 days
    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=6)
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=6)

    # Parse apoteker_id (str → int kalau valid)
    def _safe_int(s):
        if s is None or s == "":
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
    apoteker_id_int = _safe_int(apoteker_id)

    # Page size whitelist
    if page_size not in (50, 100, 200, 500):
        page_size = 100
    if page < 1:
        page = 1

    try:
        data = ReportsService(db).get_apoteker_dispensed_report(
            tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
            apoteker_id=apoteker_id_int,
            page=page, page_size=page_size,
        )
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/reports'>← Kembali</a></div>",
            status_code=500,
        )

    # CSV link with same filter
    from urllib.parse import urlencode
    csv_params = {
        "tgl_dari": tgl_dari_d.isoformat(),
        "tgl_sampai": tgl_sampai_d.isoformat(),
    }
    if apoteker_id_int is not None:
        csv_params["apoteker_id"] = apoteker_id_int
    csv_url = f"/web/reports/apoteker-dispensed/csv?{urlencode(csv_params)}"

    ctx = build_shell_context(
        user, db=db, current_path="/web/reports/apoteker-dispensed",
        page_subtitle="Rekap Resep Diserahkan Apoteker",
        data=data.model_dump(mode="json"),
        tgl_dari_selected=tgl_dari_d.isoformat(),
        tgl_sampai_selected=tgl_sampai_d.isoformat(),
        apoteker_id_selected=apoteker_id_int,
        page_size_selected=page_size,
        csv_url=csv_url,
    )
    return templates.TemplateResponse(request, "reports_apoteker_dispensed.html", ctx)


@router.get("/reports/apoteker-dispensed/csv")
def reports_apoteker_dispensed_csv(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    apoteker_id: Optional[str] = None,
):
    from fastapi.responses import StreamingResponse
    import csv
    import io
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=6)
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=6)

    def _safe_int(s):
        if s is None or s == "":
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
    apt_id = _safe_int(apoteker_id)

    # Get ALL items (large page_size)
    data = ReportsService(db).get_apoteker_dispensed_report(
        tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
        apoteker_id=apt_id, page=1, page_size=100000,
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    # `jenis` membedakan obat jadi dari racikan. Untuk racikan, `kode_produk`
    # kosong dan `harga_satuan` tidak berlaku — subtotal-nya adalah TOTAL racikan
    # (bahan + ongkos racik) yang sudah terkunci saat diresepkan.
    writer.writerow([
        "waktu_serah", "jenis", "no_rm", "nama_pasien", "kode_produk", "nama_produk",
        "qty", "harga_satuan", "subtotal", "aturan_pakai",
        "apoteker_id", "apoteker_nama", "id_kunjungan",
    ])
    for it in data.items:
        writer.writerow([
            it.waktu_serah.isoformat() if it.waktu_serah else "",
            (f"RACIKAN/{it.jenis_racik}" if it.is_racikan else "OBAT"),
            it.no_rm, it.nama_pasien, it.kode_produk or "", it.nama_produk,
            it.qty, ("" if it.is_racikan else it.harga_satuan), it.subtotal,
            it.aturan_pakai or "",
            it.id_staf_apoteker, it.apoteker_nama, it.id_kunjungan,
        ])

    output.seek(0)
    filename = f"resep_dispensed_{tgl_dari_d.isoformat()}_{tgl_sampai_d.isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# #363C - GET /web/reports/write-off
# =============================================================================
@router.get("/reports/write-off", response_class=HTMLResponse)
def reports_writeoff(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    apoteker_id: Optional[str] = None,
    jenis_mutasi: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=30)  # default 30 hari for write-off
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=30)

    def _safe_int(s):
        if s is None or s == "":
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
    apt_id = _safe_int(apoteker_id)

    jenis_clean = (jenis_mutasi or "").strip().upper()
    if jenis_clean and jenis_clean not in ("EXPIRED", "RUSAK", "PENYESUAIAN"):
        jenis_clean = ""

    if page_size not in (50, 100, 200, 500):
        page_size = 100
    if page < 1:
        page = 1

    try:
        data = ReportsService(db).get_writeoff_report(
            tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
            apoteker_id=apt_id, jenis_mutasi=(jenis_clean or None),
            page=page, page_size=page_size,
        )
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/reports'>← Kembali</a></div>",
            status_code=500,
        )

    from urllib.parse import urlencode
    csv_params = {
        "tgl_dari": tgl_dari_d.isoformat(),
        "tgl_sampai": tgl_sampai_d.isoformat(),
    }
    if apt_id is not None:
        csv_params["apoteker_id"] = apt_id
    if jenis_clean:
        csv_params["jenis_mutasi"] = jenis_clean
    csv_url = f"/web/reports/write-off/csv?{urlencode(csv_params)}"

    ctx = build_shell_context(
        user, db=db, current_path="/web/reports/write-off",
        page_subtitle="Rekap Write-off Produk",
        data=data.model_dump(mode="json"),
        tgl_dari_selected=tgl_dari_d.isoformat(),
        tgl_sampai_selected=tgl_sampai_d.isoformat(),
        apoteker_id_selected=apt_id,
        jenis_selected=jenis_clean,
        page_size_selected=page_size,
        csv_url=csv_url,
    )
    return templates.TemplateResponse(request, "reports_writeoff.html", ctx)


@router.get("/reports/write-off/csv")
def reports_writeoff_csv(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    apoteker_id: Optional[str] = None,
    jenis_mutasi: Optional[str] = None,
):
    from fastapi.responses import StreamingResponse
    import csv
    import io
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=30)
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=30)

    def _safe_int(s):
        if s is None or s == "":
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
    apt_id = _safe_int(apoteker_id)
    jenis_clean = (jenis_mutasi or "").strip().upper()
    if jenis_clean and jenis_clean not in ("EXPIRED", "RUSAK", "PENYESUAIAN"):
        jenis_clean = ""

    data = ReportsService(db).get_writeoff_report(
        tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
        apoteker_id=apt_id, jenis_mutasi=(jenis_clean or None),
        page=1, page_size=100000,
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "waktu", "kode_produk", "nama_produk", "jenis_mutasi",
        "qty_dibuang", "hpp_per_unit", "nominal_loss",
        "stok_sebelum", "stok_sesudah",
        "id_staf_apoteker", "apoteker_nama", "keterangan",
    ])
    for it in data.items:
        writer.writerow([
            it.waktu.isoformat() if it.waktu else "",
            it.kode_produk, it.nama_produk, it.jenis_mutasi,
            it.qty_dibuang, it.hpp_per_unit, it.nominal_loss,
            it.stok_sebelum, it.stok_sesudah,
            it.id_staf_apoteker, it.apoteker_nama,
            (it.keterangan or "").replace("\n", " ").replace("\r", " "),
        ])

    output.seek(0)
    filename = f"writeoff_{tgl_dari_d.isoformat()}_{tgl_sampai_d.isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# #363D - GET /web/reports/top-produk
# =============================================================================
@router.get("/reports/top-produk", response_class=HTMLResponse)
def reports_top_produk(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    sort_by: str = "qty",
    limit: int = 50,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=29)  # default 30 hari
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=29)

    if sort_by not in ("qty", "nominal", "count"):
        sort_by = "qty"
    if limit not in (20, 50, 100, 200, 500):
        limit = 50

    try:
        data = ReportsService(db).get_top_dispensed_products(
            tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
            limit=limit, sort_by=sort_by,
        )
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/reports'>← Kembali</a></div>",
            status_code=500,
        )

    from urllib.parse import urlencode
    csv_url = "/web/reports/top-produk/csv?" + urlencode({
        "tgl_dari": tgl_dari_d.isoformat(),
        "tgl_sampai": tgl_sampai_d.isoformat(),
        "sort_by": sort_by,
        "limit": limit,
    })

    ctx = build_shell_context(
        user, db=db, current_path="/web/reports/top-produk",
        page_subtitle="Top Dispensed Products",
        data=data.model_dump(mode="json"),
        tgl_dari_selected=tgl_dari_d.isoformat(),
        tgl_sampai_selected=tgl_sampai_d.isoformat(),
        sort_by_selected=sort_by,
        limit_selected=limit,
        csv_url=csv_url,
    )
    return templates.TemplateResponse(request, "reports_top_produk.html", ctx)


@router.get("/reports/top-produk/csv")
def reports_top_produk_csv(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    sort_by: str = "qty",
    limit: int = 50,
):
    from fastapi.responses import StreamingResponse
    import csv
    import io
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return _403()

    if not tgl_sampai:
        tgl_sampai_d = date.today()
    else:
        try:
            tgl_sampai_d = date.fromisoformat(tgl_sampai)
        except Exception:
            tgl_sampai_d = date.today()
    if not tgl_dari:
        tgl_dari_d = tgl_sampai_d - timedelta(days=29)
    else:
        try:
            tgl_dari_d = date.fromisoformat(tgl_dari)
        except Exception:
            tgl_dari_d = tgl_sampai_d - timedelta(days=29)

    if sort_by not in ("qty", "nominal", "count"):
        sort_by = "qty"
    if limit < 1 or limit > 500:
        limit = 50

    data = ReportsService(db).get_top_dispensed_products(
        tgl_dari=tgl_dari_d, tgl_sampai=tgl_sampai_d,
        limit=limit, sort_by=sort_by,
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    # Kolom racikan ikut diekspor. `qty_racikan` SENGAJA kolom sendiri dengan
    # satuannya — jangan dijumlahkan dengan `total_qty` di spreadsheet, satuannya
    # berbeda (butir/gram vs satuan jual).
    writer.writerow([
        "rank", "kode_produk", "nama_produk", "tipe_produk", "satuan",
        "total_qty", "total_dispensed_count", "total_unique_kunjungan",
        "avg_qty_per_kunjungan", "harga_satuan", "total_nominal", "stok_terkini",
        "qty_racikan", "satuan_racikan", "racikan_count", "nominal_racikan",
        "hanya_dari_racikan",
    ])
    for it in data.items:
        writer.writerow([
            it.rank, it.kode_produk, it.nama_produk, it.tipe_produk or "", it.satuan,
            it.total_qty, it.total_dispensed_count, it.total_unique_kunjungan,
            round(it.avg_qty_per_kunjungan, 2), it.harga_satuan, it.total_nominal, it.stok_terkini,
            it.qty_racikan, it.satuan_racikan or "", it.racikan_count, it.nominal_racikan,
            "YA" if it.hanya_dari_racikan else "",
        ])

    # Peringkat racikan disusulkan sebagai blok terpisah di CSV yang sama, dengan
    # baris kosong + judul sebagai pemisah. Alasannya sama dengan di layar:
    # nominal racikan sudah memuat bahan, jadi tidak boleh dijumlahkan dengan
    # blok produk di atas.
    if data.racikan:
        writer.writerow([])
        writer.writerow(["RACIKAN — blok terpisah, JANGAN dijumlahkan dengan blok produk di atas"])
        writer.writerow([
            "rank", "nama_racikan", "jenis_racik", "total_batch", "total_unit",
            "total_unique_kunjungan", "total_biaya_racik", "total_nominal",
        ])
        for r in data.racikan:
            writer.writerow([
                r.rank, r.nama, r.jenis_racik, r.total_batch, r.total_unit,
                r.total_unique_kunjungan, r.total_biaya_racik, r.total_nominal,
            ])

    output.seek(0)
    filename = f"top_produk_{tgl_dari_d.isoformat()}_{tgl_sampai_d.isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# GET /web/reports/rekap-harian — Rekap Harian Kasir Analitik (Kasir-2)
# =============================================================================
@router.get("/reports/rekap-harian", response_class=HTMLResponse)
def reports_rekap_harian(request: Request, db: DbSession, tgl: Optional[str] = None):
    from app.services.rekap_harian_service import RekapHarianService

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_reports_role(user):  # Owner / Superadmin / Admin
        return _403()

    today = date.today()
    try:
        d_tgl = date.fromisoformat(tgl) if tgl else today
    except ValueError:
        d_tgl = today

    try:
        data = RekapHarianService(db).rekap(d_tgl)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/reports",
        page_subtitle=f"Rekap Harian Kasir {d_tgl.isoformat()}",
        data=data,
        tgl_selected=d_tgl.isoformat(),
    )
    return templates.TemplateResponse(request, "reports_rekap_harian.html", ctx)


# =============================================================================
# GET /web/reports/komisi — Laporan Komisi Staf (K-L4, DEC-087)
# Akses: Owner/Superadmin/Admin = semua staf; Dokter/Perawat = komisi sendiri.
# =============================================================================
@router.get("/reports/komisi", response_class=HTMLResponse)
def reports_komisi(
    request: Request,
    db: DbSession,
    periode: str = "bulan",
    tgl_dari: str = "",
    tgl_sampai: str = "",
    id_staf: Optional[str] = None,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    from app.web.routes._shared import require_reports_role, is_dokter_role, is_perawat_role
    from app.services.komisi_report_service import KomisiReportService

    is_manajemen = require_reports_role(user)          # Owner/Superadmin/Admin
    is_self = is_dokter_role(user) or is_perawat_role(user)
    if not (is_manajemen or is_self):
        return _403()

    # Kompartmentalisasi: dokter/perawat HANYA lihat komisi sendiri (backend enforce).
    own_only = is_self and not is_manajemen
    force_id = user.id_staf if own_only else _safe_int(id_staf)

    # Resolve rentang tanggal dari preset periode.
    today = date.today()
    if periode == "hari":
        d1 = d2 = today
    elif periode == "minggu":
        d1 = today - timedelta(days=today.weekday())   # Senin minggu ini
        d2 = d1 + timedelta(days=6)
    elif periode == "custom":
        try:
            d1 = date.fromisoformat(tgl_dari)
        except (ValueError, TypeError):
            d1 = today.replace(day=1)
        try:
            d2 = date.fromisoformat(tgl_sampai)
        except (ValueError, TypeError):
            d2 = today
        if d2 < d1:
            d1, d2 = d2, d1
    else:
        periode = "bulan"
        d1 = today.replace(day=1)
        nxt = (d1.replace(day=28) + timedelta(days=4)).replace(day=1)
        d2 = nxt - timedelta(days=1)

    svc = KomisiReportService(db)
    data = svc.laporan(d1, d2, id_staf=force_id)
    staf_list = [] if own_only else svc.list_staf_komisi()

    ctx = build_shell_context(
        user, db=db, current_path="/web/reports",
        page_subtitle="Komisi Staf",
        data=data, staf_list=staf_list, own_only=own_only,
        periode=periode, tgl_dari=d1.isoformat(), tgl_sampai=d2.isoformat(),
        selected_staf=force_id,
    )
    return templates.TemplateResponse(request, "reports_komisi.html", ctx)


# =============================================================================
# Top Diagnosa — "kasus terbanyak" (Langkah 4, 2026-09-30)
# =============================================================================
# Role: require_reports_role (Owner/Superadmin/Admin) — sama dengan Top Treatment.
# Laporan ini TIDAK menampilkan identitas pasien: hanya agregat per diagnosa.
def _tgl_rentang(tgl_dari, tgl_sampai, default_hari=364):
    """Rentang tanggal dari query string, dengan default & tahan input ngawur.

    Default 365 hari (bukan 30): pertanyaan "kasus terbanyak" dan "pasien hilang
    tanpa kontrol" hanya terjawab kalau jendelanya cukup panjang. Jendela 30 hari
    membuat kasus musiman terlihat seperti kasus langka.
    """
    today = date.today()
    try:
        sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        sampai = today
    try:
        dari = (date.fromisoformat(tgl_dari) if tgl_dari
                else sampai - timedelta(days=default_hari))
    except ValueError:
        dari = sampai - timedelta(days=default_hari)
    if dari > sampai:
        dari, sampai = sampai, dari
    return dari, sampai


@router.get("/reports/top-diagnosa", response_class=HTMLResponse)
def reports_top_diagnosa(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    sistem: str = "SEMUA",
    primer: str = "",
    sort_by: str = "pasien",
    limit: int = 50,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_top_diagnosa_role(user):
        return _403()

    d_dari, d_sampai = _tgl_rentang(tgl_dari, tgl_sampai)
    if sistem not in ("SEMUA", "ICD10", "ESTETIK"):
        sistem = "SEMUA"
    if sort_by not in ("pasien", "kunjungan"):
        sort_by = "pasien"
    if limit not in (20, 50, 100, 200, 500):
        limit = 50
    hanya_primer = bool((primer or "").strip())

    try:
        data = ReportsService(db).get_top_diagnosa(
            tgl_dari=d_dari, tgl_sampai=d_sampai, sistem=sistem,
            hanya_primer=hanya_primer, sort_by=sort_by, limit=limit,
        )
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/reports'>← Kembali</a></div>", status_code=500)

    from urllib.parse import urlencode
    q = {"tgl_dari": d_dari.isoformat(), "tgl_sampai": d_sampai.isoformat(),
         "sistem": sistem, "sort_by": sort_by, "limit": limit}
    if hanya_primer:
        q["primer"] = "1"

    ctx = build_shell_context(
        user, db=db, current_path="/web/reports/top-diagnosa",
        page_subtitle="Kasus Terbanyak (Top Diagnosa)",
        data=data,
        tgl_dari_selected=d_dari.isoformat(),
        tgl_sampai_selected=d_sampai.isoformat(),
        sistem_selected=sistem, sort_by_selected=sort_by,
        primer_selected=hanya_primer, limit_selected=limit,
        csv_url="/web/reports/top-diagnosa/csv?" + urlencode(q),
    )
    return templates.TemplateResponse(request, "reports_top_diagnosa.html", ctx)


@router.get("/reports/top-diagnosa/csv")
def reports_top_diagnosa_csv(
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    sistem: str = "SEMUA",
    primer: str = "",
    sort_by: str = "pasien",
    limit: int = 50,
):
    """CSV agregat. TIDAK memuat identitas pasien — hanya hitungan per diagnosa.

    Berbeda dari paket klinis: berkas ini boleh dibuka di Excel dan dibahas,
    karena satu baris = satu diagnosa, bukan satu orang.
    """
    import csv
    import io

    from fastapi.responses import StreamingResponse

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_top_diagnosa_role(user):
        return _403()

    d_dari, d_sampai = _tgl_rentang(tgl_dari, tgl_sampai)
    data = ReportsService(db).get_top_diagnosa(
        tgl_dari=d_dari, tgl_sampai=d_sampai,
        sistem=sistem if sistem in ("ICD10", "ESTETIK") else "SEMUA",
        hanya_primer=bool((primer or "").strip()),
        sort_by=sort_by if sort_by in ("pasien", "kunjungan") else "pasien",
        limit=limit if limit in (20, 50, 100, 200, 500) else 50,
    )

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "sistem", "kode_diagnosa", "nama_diagnosa",
                "jumlah_pasien",
                "jumlah_kunjungan", "kunjungan_per_pasien", "jumlah_primer",
                "persen_kunjungan", "pertama", "terakhir"])
    for it in data["items"]:
        w.writerow([it.get("rank", ""), it["sistem"],
                    it["kode_diagnosa"], it["nama_diagnosa"],
                    it["jumlah_pasien"], it["jumlah_kunjungan"],
                    it["kunjungan_per_pasien"], it["jumlah_primer"],
                    it.get("persen_kunjungan", ""),
                    it["pertama"], it["terakhir"]])
    buf.seek(0)
    nama = f"top_diagnosa_{d_dari}_{d_sampai}.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nama}"'})
