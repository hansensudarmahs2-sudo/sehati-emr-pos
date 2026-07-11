"""
Web Export routes (Owner Raw Data Export — C2):

- GET  /web/export                            — landing dengan 3 cards (Weekly/Monthly/Custom)
- GET  /web/export/pack/weekly.zip            — Weekly pack download (C2.3, stub C2.1)
- GET  /web/export/pack/monthly.zip           — Monthly pack download (C2.3, stub C2.1)
- GET  /web/export/pack/custom.zip            — Custom range pack (C2.3, stub C2.1)
- GET  /web/export/dictionary.{md,json}       — Data dictionary (C2.4)

Role gate: **Owner ONLY** (per decision #1, MVP).

Phase C2.1 (Foundation): landing UI + pack endpoint dengan stub return.
Phase C2.2+: 11 dataset methods di ExportService + pack assembly.
"""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.core.deps import DbSession
from app.core.csv_writer import dict_list_to_csv_bytes
from app.core.json_writer import dict_list_to_json_bytes
from app.services.export_service import ExportService, WARNING_THRESHOLD_DAYS
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_owner_only,
    templates,
)


router = APIRouter(tags=["Web Export"])


def _403() -> HTMLResponse:
    return HTMLResponse(
        "<div style='padding:2rem'>"
        "403 — Hanya Owner yang boleh akses Raw Data Export."
        "<br><span style='color:#666;font-size:0.9em'>"
        "(Untuk MVP, hanya 1 role yang boleh. Superadmin/Admin defer ke phase berikutnya.)"
        "</span></div>",
        status_code=403,
    )


# =============================================================================
# GET /web/export — Landing
# =============================================================================
@router.get("/export", response_class=HTMLResponse)
def export_landing(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    today = date.today()
    # Default anchor date untuk Weekly/Monthly cards = today
    # Default custom range = 7 hari terakhir (sama dengan Weekly)
    weekly_dari, weekly_sampai = ExportService.compute_weekly_range(today)
    monthly_dari, monthly_sampai = ExportService.compute_monthly_range(today)

    # Pass dataset registry untuk Advanced section (strip method ref)
    safe_datasets = [
        {k: v for k, v in d.items() if k != "method"}
        for d in ExportService.DATASET_REGISTRY
    ]
    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/export",
        page_subtitle="Generate paket untuk Data Analyst & Council AI",
        today=today.isoformat(),
        weekly_dari=weekly_dari.isoformat(),
        weekly_sampai=weekly_sampai.isoformat(),
        monthly_dari=monthly_dari.isoformat(),
        monthly_sampai=monthly_sampai.isoformat(),
        warning_threshold_days=WARNING_THRESHOLD_DAYS,
        datasets=safe_datasets,
    )
    return templates.TemplateResponse(request, "export_landing.html", ctx)


# =============================================================================
# GET /web/export/pack/weekly.zip — Weekly Pack
# =============================================================================
@router.get("/export/pack/weekly.zip")
def export_pack_weekly(
    request: Request,
    db: DbSession,
    ending_date: Optional[str] = None,
    format: str = "csv",
    mask_pii: bool = False,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    try:
        end_dt = date.fromisoformat(ending_date) if ending_date else date.today()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format ending_date harus YYYY-MM-DD")

    tgl_dari, tgl_sampai = ExportService.compute_weekly_range(end_dt)
    return _generate_and_stream(
        db, "weekly", tgl_dari, tgl_sampai, format, mask_pii, user, request,
    )


# =============================================================================
# GET /web/export/pack/monthly.zip — Monthly Pack
# =============================================================================
@router.get("/export/pack/monthly.zip")
def export_pack_monthly(
    request: Request,
    db: DbSession,
    ending_date: Optional[str] = None,
    format: str = "csv",
    mask_pii: bool = False,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    try:
        end_dt = date.fromisoformat(ending_date) if ending_date else date.today()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format ending_date harus YYYY-MM-DD")

    tgl_dari, tgl_sampai = ExportService.compute_monthly_range(end_dt)
    return _generate_and_stream(
        db, "monthly", tgl_dari, tgl_sampai, format, mask_pii, user, request,
    )


# =============================================================================
# GET /web/export/pack/custom.zip — Custom Range Pack
# =============================================================================
@router.get("/export/pack/custom.zip")
def export_pack_custom(
    request: Request,
    db: DbSession,
    tgl_dari: str,
    tgl_sampai: str,
    format: str = "csv",
    mask_pii: bool = False,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    try:
        d_dari = date.fromisoformat(tgl_dari)
        d_sampai = date.fromisoformat(tgl_sampai)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format tanggal harus YYYY-MM-DD")

    return _generate_and_stream(
        db, "custom", d_dari, d_sampai, format, mask_pii, user, request,
    )


# =============================================================================
# Helper — generate pack + return Response dengan file download header
# =============================================================================
def _generate_and_stream(
    db, period, tgl_dari, tgl_sampai, format, mask_pii, user, request,
) -> Response:
    if format not in ("csv", "json"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format harus csv atau json")

    try:
        zip_bytes, filename = ExportService(db).generate_pack(
            period=period,
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            format=format,
            mask_pii=mask_pii,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem'>Gagal generate pack: {e!s}</div>",
            status_code=500,
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


# =============================================================================
# GET /web/export/dictionary.{md,json} — Stub for C2.4
# =============================================================================
@router.get("/export/dictionary.md")
def export_dictionary_md(request: Request, db: DbSession):
    """Return data dictionary sebagai Markdown plain text (untuk Council AI / dokumentasi)."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    try:
        md_text = ExportService(db).generate_dictionary_markdown()
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem'>Error generating dictionary: {e!s}</div>",
            status_code=500,
        )

    return Response(
        content=md_text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="DATA_DICTIONARY.md"'},
    )


@router.get("/export/dictionary.json")
def export_dictionary_json(request: Request, db: DbSession):
    """Return data dictionary sebagai JSON (programmatic access untuk Council AI)."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()

    try:
        datasets = ExportService(db).get_dictionary_data()
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error: {e!s}")

    total_cols = sum(len(d["columns"]) for d in datasets)
    return {
        "version": "1.0",
        "generated_utc": datetime.utcnow().isoformat() + "Z",
        "datasets_count": len(datasets),
        "total_columns": total_cols,
        "datasets": datasets,
    }


# =============================================================================
# Per-dataset download (C2.2 — advanced/internal)
# =============================================================================
def _parse_date_pair(tgl_dari: Optional[str], tgl_sampai: Optional[str]) -> tuple[date, date]:
    """Parse query params YYYY-MM-DD ke (date, date). Default: 7 hari terakhir."""
    today = date.today()
    try:
        d_dari = date.fromisoformat(tgl_dari) if tgl_dari else (today - timedelta(days=7))
        d_sampai = date.fromisoformat(tgl_sampai) if tgl_sampai else today
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Format tanggal harus YYYY-MM-DD",
        )
    return d_dari, d_sampai


def _build_dataset_response(
    db, dataset_name: str, format: str,
    tgl_dari: date, tgl_sampai: date,
    mask_pii: bool, user, request,
) -> Response:
    """Generic dispatcher: load dataset, serialize, audit, return Response."""
    if format not in ("csv", "json"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format harus csv atau json")

    try:
        service = ExportService(db)
        items, meta = service.get_dataset(
            dataset_name, tgl_dari, tgl_sampai, mask_pii=mask_pii,
        )
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem'>Gagal load dataset: {e!s}</div>",
            status_code=500,
        )

    columns = meta.get("default_columns")
    if format == "csv":
        body = dict_list_to_csv_bytes(items, columns=columns)
        media = "text/csv; charset=utf-8"
        ext = "csv"
    else:
        body = dict_list_to_json_bytes(items, pretty=True)
        media = "application/json; charset=utf-8"
        ext = "json"

    # Audit
    try:
        service.audit_export_dataset(
            actor_id_staf=user.id_staf,
            dataset_name=dataset_name,
            tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
            format=format, mask_pii=mask_pii,
            row_count=len(items), request=request,
        )
    except Exception:
        pass  # noqa: BLE001 — audit failure tidak block export

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"sehati_{dataset_name}_{tgl_dari}_to_{tgl_sampai}_{ts}.{ext}"
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(body)),
            "X-Rows": str(len(items)),
        },
    )


@router.get("/export/dataset/{dataset_name}/download.csv")
def export_dataset_csv(
    dataset_name: str,
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    mask_pii: bool = False,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()
    d_dari, d_sampai = _parse_date_pair(tgl_dari, tgl_sampai)
    return _build_dataset_response(
        db, dataset_name, "csv", d_dari, d_sampai, mask_pii, user, request,
    )


@router.get("/export/dataset/{dataset_name}/download.json")
def export_dataset_json(
    dataset_name: str,
    request: Request,
    db: DbSession,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    mask_pii: bool = False,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()
    d_dari, d_sampai = _parse_date_pair(tgl_dari, tgl_sampai)
    return _build_dataset_response(
        db, dataset_name, "json", d_dari, d_sampai, mask_pii, user, request,
    )


@router.get("/export/datasets.json")
def export_datasets_list(request: Request, db: DbSession):
    """List semua dataset yang tersedia (untuk Council AI self-discovery)."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return _403()
    # Strip non-serializable Callable
    safe = []
    for d in ExportService.DATASET_REGISTRY:
        safe.append({k: v for k, v in d.items() if k != "method"})
    return {"datasets": safe, "total": len(safe)}


__all__ = ["router"]
