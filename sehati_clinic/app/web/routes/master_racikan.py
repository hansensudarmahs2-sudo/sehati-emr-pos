"""Master Formula Racikan web routes (Owner + Superadmin).

Formula menyimpan KOMPOSISI (bahan + dosis per unit), bukan harga.
Harga dihitung saat dipakai dari harga bahan terkini + tarif flat ongkos racik.
Service: app/services/racikan_service.py — Desain: Project_Memory/DESAIN_MODUL_RACIKAN.md
"""
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.master_produk_service import MasterProdukService
from app.services.racikan_service import RacikanService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_master_data_role,
    templates,
)

router = APIRouter(tags=["Web Master Racikan"])


def _guard(request, db):
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, login_redirect()
    if not require_master_data_role(user):
        return None, forbidden()
    return user, None


@router.get("/master/racikan", response_class=HTMLResponse)
def racikan_list(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    svc = RacikanService(db)
    keyword = request.query_params.get("q") or None
    jenis = request.query_params.get("jenis") or None
    data = []
    for f in svc.list_formula(keyword=keyword, jenis=jenis):
        data.append({
            "id_racikan": f.id_racikan, "nama": f.nama, "jenis_racik": f.jenis_racik,
            "default_jumlah_unit": f.default_jumlah_unit,
            "jumlah_bahan": len(svc.list_bahan(f.id_racikan)),
            "is_active": bool(f.is_active),
        })
    ctx = build_shell_context(
        user, db=db, current_path="/master/racikan",
        page_subtitle="Master Formula Racikan",
        data=data, keyword=keyword or "", jenis_filter=jenis or "",
        biaya_racik=svc.list_biaya_racik(only_active=False),
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_racikan_list.html", ctx)


@router.post("/master/racikan/tarif/{id_biaya_racik}", response_class=HTMLResponse)
def racikan_tarif_update(id_biaya_racik: int, request: Request, db: DbSession,
                         tarif: float = Form(...)):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        RacikanService(db).update_tarif(id_biaya_racik, tarif)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/master/racikan?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/racikan?ok={quote('Tarif ongkos racik diperbarui.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/master/racikan/tambah", response_class=HTMLResponse)
def racikan_tambah_form(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    ctx = build_shell_context(
        user, db=db, current_path="/master/racikan", page_subtitle="Tambah Formula Racikan",
        form={"jenis_racik": "KAPSUL", "default_jumlah_unit": 15},
        jenis_opts=RacikanService(db).list_biaya_racik(), is_edit=False,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_racikan_form.html", ctx)


@router.post("/master/racikan/tambah", response_class=HTMLResponse)
def racikan_tambah_submit(
    request: Request, db: DbSession,
    nama: str = Form(...), jenis_racik: str = Form(...),
    default_jumlah_unit: int = Form(default=1),
    default_aturan_pakai: str = Form(default=""), catatan: str = Form(default=""),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        created = RacikanService(db).create_formula(
            nama=nama, jenis_racik=jenis_racik, default_jumlah_unit=default_jumlah_unit,
            default_aturan_pakai=default_aturan_pakai.strip() or None,
            catatan=catatan.strip() or None,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/master/racikan/tambah?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/master/racikan/{created.id_racikan}?ok={quote('Formula dibuat. Tambahkan bahannya.')}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.get("/master/racikan/{id_racikan}", response_class=HTMLResponse)
def racikan_edit_form(id_racikan: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    svc = RacikanService(db)
    try:
        f = svc.get_formula(id_racikan)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>",
                            status_code=e.status_code)
    # Pratinjau harga memakai jumlah unit dari query (?n=) atau default formula.
    try:
        n = int(request.query_params.get("n") or f.default_jumlah_unit or 1)
    except (ValueError, TypeError):
        n = f.default_jumlah_unit or 1
    ctx = build_shell_context(
        user, db=db, current_path="/master/racikan",
        page_subtitle=f"Formula — {f.nama}",
        form={
            "id_racikan": f.id_racikan, "nama": f.nama, "jenis_racik": f.jenis_racik,
            "default_jumlah_unit": f.default_jumlah_unit,
            "default_aturan_pakai": f.default_aturan_pakai or "",
            "catatan": f.catatan or "", "is_active": bool(f.is_active),
        },
        jenis_opts=svc.list_biaya_racik(), is_edit=True,
        hitung=svc.hitung(id_racikan, n), preview_n=n,
        master_produks=MasterProdukService(db).list_all(only_active=True, limit=500),
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_racikan_form.html", ctx)


@router.post("/master/racikan/{id_racikan}", response_class=HTMLResponse)
def racikan_edit_submit(
    id_racikan: int, request: Request, db: DbSession,
    nama: str = Form(...), jenis_racik: str = Form(...),
    default_jumlah_unit: int = Form(default=1),
    default_aturan_pakai: str = Form(default=""), catatan: str = Form(default=""),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        RacikanService(db).update_formula(
            id_racikan, nama=nama, jenis_racik=jenis_racik,
            default_jumlah_unit=default_jumlah_unit,
            default_aturan_pakai=default_aturan_pakai.strip() or None,
            catatan=catatan.strip() or None,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/master/racikan/{id_racikan}?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/racikan/{id_racikan}?ok={quote('Formula diperbarui.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/racikan/{id_racikan}/toggle-active", response_class=HTMLResponse)
def racikan_toggle_active(id_racikan: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        RacikanService(db).toggle_active(id_racikan)
    except HTTPException:
        pass
    return RedirectResponse(url="/web/master/racikan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/racikan/{id_racikan}/bahan/tambah", response_class=HTMLResponse)
def racikan_bahan_tambah(
    id_racikan: int, request: Request, db: DbSession,
    id_produk: int = Form(...), dosis_per_unit: float = Form(...),
    satuan_dosis: str = Form(default="mg"),
):
    user, resp = _guard(request, db)
    if resp:
        return resp
    try:
        RacikanService(db).add_bahan(
            id_racikan, id_produk=id_produk, dosis_per_unit=dosis_per_unit,
            satuan_dosis=satuan_dosis,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/master/racikan/{id_racikan}?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/racikan/{id_racikan}?ok={quote('Bahan ditambahkan.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/racikan/{id_racikan}/bahan/{id_racikan_bahan}/hapus", response_class=HTMLResponse)
def racikan_bahan_hapus(id_racikan: int, id_racikan_bahan: int, request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    RacikanService(db).delete_bahan(id_racikan_bahan)
    return RedirectResponse(url=f"/web/master/racikan/{id_racikan}?ok={quote('Bahan dihapus.')}",
                            status_code=status.HTTP_303_SEE_OTHER)
