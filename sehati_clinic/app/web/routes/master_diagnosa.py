"""Master Diagnosa web routes (Owner + Superadmin).

Kamus diagnosa (ICD-10 + estetik internal) + editor paket tindakan/produk.
Modul #24–#27. Service: app/services/diagnosa_service.py
"""
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.repositories.treatment_repo import TreatmentRepository
from app.services.diagnosa_service import DiagnosaService
from app.services.master_produk_service import MasterProdukService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_master_data_role,
    templates,
)

router = APIRouter(tags=["Web Master Diagnosa"])

_SISTEM_OPTS = ["ICD10", "ESTETIK"]


def _guard(request, db):
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, login_redirect()
    if not require_master_data_role(user):
        return None, forbidden()
    return user, None


@router.get("/master/diagnosa", response_class=HTMLResponse)
def diagnosa_list(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    keyword = request.query_params.get("q") or None
    sistem = request.query_params.get("sistem") or None
    data = DiagnosaService(db).list_ref(keyword=keyword, sistem=sistem, limit=1000)
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/diagnosa",
        page_subtitle="Master Diagnosa (ICD-10 + Estetik)",
        data=[{
            "id_diagnosa": d.id_diagnosa,
            "sistem": d.sistem.value if hasattr(d.sistem, "value") else d.sistem,
            "kode": d.kode, "nama": d.nama, "nama_en": d.nama_en,
            "kategori": d.kategori, "default_kontrol_hari": d.default_kontrol_hari,
            "is_active": bool(d.is_active),
        } for d in data],
        keyword=keyword or "", sistem_filter=sistem or "",
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_diagnosa_list.html", ctx)


@router.get("/master/diagnosa/tambah", response_class=HTMLResponse)
def diagnosa_tambah_form(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/diagnosa",
        page_subtitle="Tambah Diagnosa",
        form={"sistem": "ICD10", "default_kontrol_hari": 7},
        sistem_opts=_SISTEM_OPTS, is_edit=False, paket=None,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_diagnosa_form.html", ctx)


@router.post("/master/diagnosa/tambah", response_class=HTMLResponse)
def diagnosa_tambah_submit(
    request: Request, db: DbSession,
    sistem: str = Form(...),
    kode: str = Form(...),
    nama: str = Form(...),
    nama_en: str = Form(default=""),
    kategori: str = Form(default=""),
    default_kontrol_hari: int = Form(default=7),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        created = DiagnosaService(db).create_ref(
            sistem=sistem, kode=kode, nama=nama,
            nama_en=nama_en.strip() or None, kategori=kategori.strip() or None,
            default_kontrol_hari=default_kontrol_hari,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/diagnosa/tambah?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/diagnosa/{created.id_diagnosa}?ok={quote('Diagnosa dibuat. Tambahkan paket bila perlu.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/master/diagnosa/{id_diagnosa}", response_class=HTMLResponse)
def diagnosa_edit_form(id_diagnosa: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    svc = DiagnosaService(db)
    try:
        d = svc.get_ref(id_diagnosa)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    treatments = TreatmentRepository(db).list_master_active(limit=500)
    produks = MasterProdukService(db).list_all(only_active=True, limit=500)
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/diagnosa",
        page_subtitle=f"Edit Diagnosa — {d.kode}",
        form={
            "id_diagnosa": d.id_diagnosa,
            "sistem": d.sistem.value if hasattr(d.sistem, "value") else d.sistem,
            "kode": d.kode, "nama": d.nama, "nama_en": d.nama_en or "",
            "kategori": d.kategori or "", "default_kontrol_hari": d.default_kontrol_hari,
            "is_active": bool(d.is_active),
        },
        sistem_opts=_SISTEM_OPTS, is_edit=True,
        paket=svc.list_paket(id_diagnosa),
        master_treatments=treatments, master_produks=produks,
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_diagnosa_form.html", ctx)


@router.post("/master/diagnosa/{id_diagnosa}", response_class=HTMLResponse)
def diagnosa_edit_submit(
    id_diagnosa: int, request: Request, db: DbSession,
    nama: str = Form(...),
    nama_en: str = Form(default=""),
    kategori: str = Form(default=""),
    default_kontrol_hari: int = Form(default=7),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        DiagnosaService(db).update_ref(
            id_diagnosa, nama=nama, nama_en=nama_en.strip() or None,
            kategori=kategori.strip() or None, default_kontrol_hari=default_kontrol_hari,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/diagnosa/{id_diagnosa}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/diagnosa/{id_diagnosa}?ok={quote('Diagnosa diperbarui.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/diagnosa/{id_diagnosa}/toggle-active", response_class=HTMLResponse)
def diagnosa_toggle_active(id_diagnosa: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        DiagnosaService(db).toggle_active(id_diagnosa)
    except HTTPException:
        pass
    return RedirectResponse(url="/web/master/diagnosa", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/diagnosa/{id_diagnosa}/paket/tambah", response_class=HTMLResponse)
def diagnosa_paket_tambah(
    id_diagnosa: int, request: Request, db: DbSession,
    tipe_item: str = Form(...),
    id_treatment: str = Form(default=""),
    id_produk: str = Form(default=""),
    qty_default: float = Form(default=1),
    aturan_pakai_default: str = Form(default=""),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        DiagnosaService(db).add_paket_item(
            id_diagnosa, tipe_item=tipe_item,
            id_treatment=int(id_treatment) if id_treatment.strip() else None,
            id_produk=int(id_produk) if id_produk.strip() else None,
            qty_default=qty_default,
            aturan_pakai_default=aturan_pakai_default.strip() or None,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/diagnosa/{id_diagnosa}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/diagnosa/{id_diagnosa}?ok={quote('Item paket ditambahkan.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/diagnosa/{id_diagnosa}/paket/{id_paket_item}/hapus", response_class=HTMLResponse)
def diagnosa_paket_hapus(id_diagnosa: int, id_paket_item: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    DiagnosaService(db).delete_paket_item(id_paket_item)
    return RedirectResponse(
        url=f"/web/master/diagnosa/{id_diagnosa}?ok={quote('Item paket dihapus.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
