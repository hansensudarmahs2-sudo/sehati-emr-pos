"""Web route — Export paket KLINIS ber-pseudonim (Oracle / Council AI).

- GET  /web/clinical-export      - status paket terakhir + tombol
- POST /web/clinical-export/run  - jalankan ekspor

Role: Owner / Superadmin [keputusan dr. Hansen 2026-09-30], lewat himpunan
SENDIRI `CLINICAL_EXPORT_ROLES` — bukan memakai ulang himpunan lain yang isinya
kebetulan sama hari ini.

⚠ Paket ini memuat SOAP dan teks bebas SELURUH pasien, terenkripsi age. Ia
  PSEUDONIM, BUKAN ANONIM. Layar ini harus mengatakannya, bukan menyembunyikannya
  di balik tombol yang terasa biasa.

⚠ Berbeda dari ekspor finance, ekspor ini MENULIS ke DB (membuat `pid` untuk
  pasien yang belum punya). Karena itu ia POST, bukan GET.
"""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services import clinical_export_batch as core
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_clinical_export_role,
    templates,
)

router = APIRouter(tags=["Web Clinical Export"])


def _parse_tgl(s):
    """String kosong -> None (= sejak awal data). Tanggal ngawur -> None juga.

    Sengaja PERMISIF: rentang kosong adalah default yang benar, jadi input yang
    tidak terbaca jatuh ke default, tidak ke error.
    """
    try:
        return date.fromisoformat((s or "").strip()) if (s or "").strip() else None
    except ValueError:
        return None


@router.get("/clinical-export", response_class=HTMLResponse)
def clinical_export_landing(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_clinical_export_role(user):
        return forbidden("Export paket klinis hanya untuk Owner / Superadmin.")

    drop = core.DEFAULT_DROP
    # Kenapa siap/tidak-siap dihitung di sini: kalau `age` atau kuncinya tidak
    # ada, lebih baik petugas tahu SEBELUM menekan tombol daripada menemukan
    # kegagalan sesudahnya.
    masalah = None
    try:
        core.periksa_drop(drop)
        core._recipient()
    except Exception as e:
        masalah = str(e)

    riwayat = core.read_log(drop)[-10:][::-1] if masalah is None else []
    ctx = build_shell_context(
        user, db=db, current_path="/web/clinical-export",
        page_subtitle="Export Paket Klinis",
        drop=drop, masalah=masalah, riwayat=riwayat,
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "clinical_export.html", ctx)


@router.post("/clinical-export/run", response_class=HTMLResponse)
def clinical_export_run(
    request: Request,
    db: DbSession,
    tgl_dari: str = Form(""),
    tgl_sampai: str = Form(""),
    force: str = Form(""),
    paham: str = Form(""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_clinical_export_role(user):
        return forbidden("Tidak berhak.")

    # Pagar di SISI SERVER, bukan hanya checkbox di HTML: paket ini memuat SOAP
    # seluruh pasien dan keluar dari klinik. Petugas harus menyatakan paham.
    if not (paham or "").strip():
        return RedirectResponse(
            url="/web/clinical-export?err=" + quote(
                "Centang dulu pernyataan bahwa paket ini pseudonim (bukan anonim) "
                "dan akan diperlakukan sebagai data rahasia."),
            status_code=status.HTTP_303_SEE_OTHER)

    try:
        res = core.smart_export(
            db, tgl_dari=_parse_tgl(tgl_dari), tgl_sampai=_parse_tgl(tgl_sampai),
            force=bool((force or "").strip()),
            triggered_by=f"ui:{user.username}")
    except Exception as e:
        return RedirectResponse(
            url="/web/clinical-export?err=" + quote(f"{type(e).__name__}: {e}"),
            status_code=status.HTTP_303_SEE_OTHER)

    if res["status"] == "no_change":
        return RedirectResponse(
            url="/web/clinical-export?err=" + quote(
                "Isi paket IDENTIK dengan ekspor terakhir untuk rentang yang sama — "
                "tidak ada berkas baru ditulis. Centang 'tulis walau isinya sama' "
                "kalau tetap ingin paket baru."),
            status_code=status.HTTP_303_SEE_OTHER)

    p = res.get("pseudonim") or {}
    return RedirectResponse(
        url="/web/clinical-export?ok=" + quote(
            f"Paket klinis ditulis: {res['zip']} — {res['total_rows']} baris, "
            f"{p.get('total_pid', '?')} pid ({p.get('dibuat', 0)} baru), "
            f"terenkripsi age."),
        status_code=status.HTTP_303_SEE_OTHER)
