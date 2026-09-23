"""
Web routes — Audit Integritas ID Pasien (task #18, Lapis-2).

- GET  /web/audit-pasien                  - sisir & tampilkan kandidat duplikat
- POST /web/audit-pasien/dismiss          - tandai pasangan BUKAN duplikat
- POST /web/audit-pasien/batal-dismiss    - cabut penandaan

Role: Owner / Superadmin saja. Ini alat maintenance, bukan meja pendaftaran —
layarnya menampilkan data beberapa pasien berdampingan untuk dibandingkan, jadi
semakin sedikit yang bisa membukanya semakin baik.

TIDAK ADA aksi gabung/hapus di sini. Menggabungkan pasien memindahkan kunjungan,
transaksi, membership, alergi dan riwayat penyakit; kalau salah, rekam medis dua
orang tercampur. Itu modul terpisah yang belum dibangun.
"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.audit_pasien_service import AMBANG_MIRIP_DEFAULT, AuditPasienService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_audit_pasien_role,
    templates,
)

router = APIRouter(tags=["Web Audit Pasien"])


def _can(user) -> bool:
    # BUKAN require_owner_only — namanya menyesatkan, isinya hanya OWNER tanpa
    # Superadmin. Superadmin harus bisa membuka alat maintenance ini.
    return require_audit_pasien_role(user)


@router.get("/audit-pasien", response_class=HTMLResponse)
def audit_pasien_list(request: Request, db: DbSession, ambang: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Audit Integritas ID Pasien hanya untuk Owner / Superadmin.")

    try:
        amb = float(ambang) if ambang else AMBANG_MIRIP_DEFAULT
    except ValueError:
        amb = AMBANG_MIRIP_DEFAULT
    amb = min(max(amb, 0.5), 1.0)  # di bawah 0.5 laporannya jadi sampah

    svc = AuditPasienService(db)
    hasil = svc.scan(ambang=amb)
    ctx = build_shell_context(
        user, db=db, current_path="/web/audit-pasien",
        page_subtitle="Audit Integritas ID Pasien",
        hasil=hasil, dismissed_list=svc.list_dismissed(),
        nonaktif_list=svc.list_nonaktif(),
        ambang=amb,
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "audit_pasien_list.html", ctx)


@router.post("/audit-pasien/dismiss", response_class=HTMLResponse)
async def audit_pasien_dismiss(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    try:
        id_a = int((f.get("id_a") or "").strip())
        id_b = int((f.get("id_b") or "").strip())
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/web/audit-pasien?err={quote('Pasangan tidak dikenali.')}",
            status_code=status.HTTP_303_SEE_OTHER)
    try:
        hasil = AuditPasienService(db).dismiss(
            id_a=id_a, id_b=id_b, alasan=f.get("alasan"),
            actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/audit-pasien?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/audit-pasien?ok={quote(hasil.get('message', 'Ditandai.'))}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.post("/audit-pasien/nonaktifkan", response_class=HTMLResponse)
async def audit_pasien_nonaktifkan(request: Request, db: DbSession):
    """Nonaktifkan SATU pasien duplikat. Tidak menghapus apa pun.

    Nomor RM-nya dipensiunkan: `generate_next_no_rm` mengambil nomor tertinggi yang
    ADA pada tanggal itu, jadi baris yang tetap hidup memastikan nomornya tidak
    pernah terbit ulang untuk orang lain.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    try:
        id_pasien = int((f.get("id_pasien") or "").strip())
    except (TypeError, ValueError):
        return RedirectResponse(url=f"/web/audit-pasien?err={quote('Pasien tidak dikenali.')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    _tujuan = (f.get("digabung_ke") or "").strip()
    try:
        digabung_ke = int(_tujuan) if _tujuan else None
    except ValueError:
        digabung_ke = None
    try:
        hasil = AuditPasienService(db).nonaktifkan(
            id_pasien=id_pasien, alasan=f.get("alasan") or "",
            digabung_ke=digabung_ke, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/audit-pasien?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/audit-pasien?ok={quote(hasil.get('message', 'Dinonaktifkan.'))}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.post("/audit-pasien/aktifkan", response_class=HTMLResponse)
async def audit_pasien_aktifkan(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    try:
        id_pasien = int((f.get("id_pasien") or "").strip())
    except (TypeError, ValueError):
        return RedirectResponse(url=f"/web/audit-pasien?err={quote('Pasien tidak dikenali.')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        hasil = AuditPasienService(db).aktifkan(
            id_pasien=id_pasien, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/audit-pasien?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/audit-pasien?ok={quote(hasil.get('message', 'Diaktifkan.'))}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.post("/audit-pasien/batal-dismiss", response_class=HTMLResponse)
async def audit_pasien_batal_dismiss(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    try:
        id_a = int((f.get("id_a") or "").strip())
        id_b = int((f.get("id_b") or "").strip())
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/web/audit-pasien?err={quote('Pasangan tidak dikenali.')}",
            status_code=status.HTTP_303_SEE_OTHER)
    try:
        hasil = AuditPasienService(db).batal_dismiss(
            id_a=id_a, id_b=id_b, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/audit-pasien?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/audit-pasien?ok={quote(hasil.get('message', 'Dicabut.'))}",
        status_code=status.HTTP_303_SEE_OTHER)
