"""Web routes — Retur Produk (RT-L2). List, buat, approve(=potong lot), cetak Form Retur."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.db.models import MasterDistributor, MasterProduk, ReturProduk, ReturProdukItem, StokLot
from app.services.retur_service import ReturService
from app.web.routes._shared import (
    script_json,
    build_shell_context,
    get_user_from_cookie,
    require_purchasing_view_role,
    templates,
)

router = APIRouter(tags=["Web Retur Produk"])


def _403(msg: str = "Forbidden") -> HTMLResponse:
    return HTMLResponse(f"<div style='padding:2rem'>403 - {msg}</div>", status_code=403)


def _active_lot_options(db):
    from sqlalchemy import select as _sel
    rows = db.execute(
        _sel(StokLot, MasterProduk.nama_produk)
        .join(MasterProduk, StokLot.id_produk == MasterProduk.id_produk)
        .where(StokLot.tipe_item == "PRODUK", StokLot.lokasi == "RETAIL",
               StokLot.status == "AKTIF", StokLot.qty_sisa > 0)
        .order_by(MasterProduk.nama_produk, StokLot.tgl_ed)
    ).all()
    opts = []
    for lot, nama in rows:
        ed = lot.tgl_ed.strftime("%d/%m/%y") if lot.tgl_ed else "-"
        sisa = int(lot.qty_sisa) if lot.qty_sisa == int(lot.qty_sisa) else lot.qty_sisa
        opts.append({
            "id_lot": lot.id_lot,
            "label": f"{nama} · batch {lot.batch_no or '-'} · ED {ed} · sisa {sisa}",
        })
    return opts


@router.get("/pengadaan/retur", response_class=HTMLResponse)
def retur_list(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    rows = db.query(ReturProduk).order_by(ReturProduk.id_retur.desc()).limit(200).all()
    dist_map = {d.id_distributor: d.nama for d in db.query(MasterDistributor).all()}
    data = []
    for r in rows:
        n_item = db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == r.id_retur).count()
        data.append({
            "id_retur": r.id_retur, "nomor_retur": r.nomor_retur,
            "tgl": r.tgl_retur.strftime("%d/%m/%Y %H:%M") if r.tgl_retur else "-",
            "distributor": dist_map.get(r.id_distributor, "-"),
            "status": r.status, "jenis": r.jenis_penyelesaian or "-", "n_item": n_item,
        })
    ctx = build_shell_context(user, db=db, current_path="/web/pengadaan/retur",
                              page_subtitle="Retur Produk", data=data,
                              flash=request.query_params.get("ok"), error=request.query_params.get("err"))
    return templates.TemplateResponse(request, "retur_list.html", ctx)


@router.get("/pengadaan/retur/baru", response_class=HTMLResponse)
def retur_baru_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    distributors = db.query(MasterDistributor).filter(MasterDistributor.is_active == True).order_by(MasterDistributor.nama).all()
    from app.services.klinik_config_service import KlinikConfigService
    apotekers = KlinikConfigService(db).list_apoteker(only_active=True)
    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/retur", page_subtitle="Buat Retur",
        distributors=[{"id": d.id_distributor, "nama": d.nama} for d in distributors],
        apotekers=apotekers,
        lot_options_json=script_json(_active_lot_options(db)),  # P1-4: aman dari </script> breakout
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "retur_form.html", ctx)


@router.post("/pengadaan/retur/baru", response_class=HTMLResponse)
async def retur_baru_submit(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    f = await request.form()
    id_dist = f.get("id_distributor")
    id_dist = int(id_dist) if (id_dist and str(id_dist).strip()) else None
    alasan = (f.get("alasan") or "").strip() or None
    _idap = f.get("id_apoteker")
    id_apoteker = int(_idap) if (_idap and str(_idap).strip()) else None
    id_lots = f.getlist("id_lot")
    qtys = f.getlist("qty")
    alasans = f.getlist("alasan_item")
    items_input = []
    for i, rl in enumerate(id_lots):
        if not rl or not str(rl).strip():
            continue
        try:
            qv = float(qtys[i]) if i < len(qtys) else 0
        except (ValueError, TypeError):
            qv = 0
        if qv <= 0:
            continue
        items_input.append({"id_lot": int(rl), "qty": qv,
                            "alasan_item": alasans[i] if i < len(alasans) else None})
    if id_apoteker is None:
        return RedirectResponse(url=f"/web/pengadaan/retur/baru?err={_q('Pilih apoteker penanggung jawab (SIPA) dulu.')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    if not items_input:
        return RedirectResponse(url=f"/web/pengadaan/retur/baru?err={_q('Pilih minimal 1 lot + qty.')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        r = ReturService(db).create_retur(id_dist, alasan, items_input, user,
                                          id_apoteker=id_apoteker, request=request)
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return RedirectResponse(url=f"/web/pengadaan/retur/baru?err={_q(str(detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/pengadaan/retur/{r.id_retur}?ok={_q(f'Retur {r.nomor_retur} dibuat (DRAFT).')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/pengadaan/retur/{id_retur}", response_class=HTMLResponse)
def retur_detail(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    r = db.get(ReturProduk, id_retur)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Retur tidak ditemukan</div>", status_code=404)
    items = db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == id_retur).all()
    dist = db.get(MasterDistributor, r.id_distributor) if r.id_distributor else None
    from app.repositories.staf_repo import StafRepository
    pembuat = StafRepository(db).get_by_id(r.id_staf_pembuat)
    approver = StafRepository(db).get_by_id(r.id_staf_approver) if r.id_staf_approver else None
    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/retur", page_subtitle=f"Retur {r.nomor_retur}",
        r=r, items=items, distributor=dist.nama if dist else "-",
        pembuat=pembuat.nama_staf if pembuat else "-",
        approver=approver.nama_staf if approver else None,
        can_approve=(r.status == "DRAFT"),
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "retur_detail.html", ctx)


@router.post("/pengadaan/retur/{id_retur}/approve")
def retur_approve(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    try:
        ReturService(db).approve_retur(id_retur, user, request)
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}?err={_q(str(detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}?ok={_q('Retur di-approve — lot dipotong.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/pengadaan/retur/{id_retur}/cetak", response_class=HTMLResponse)
def retur_cetak(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    r = db.get(ReturProduk, id_retur)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404</div>", status_code=404)
    items = db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == id_retur).all()
    dist = db.get(MasterDistributor, r.id_distributor) if r.id_distributor else None
    from app.services.klinik_config_service import KlinikConfigService
    from app.repositories.staf_repo import StafRepository
    klinik = KlinikConfigService(db).get_config()
    pembuat = StafRepository(db).get_by_id(r.id_staf_pembuat)
    ctx = {"klinik": klinik, "r": r, "items": items, "distributor": dist,
           "pembuat": pembuat.nama_staf if pembuat else "-"}
    return templates.TemplateResponse(request, "print/retur_form.html", ctx)


# =============================================================================
# RT-L3 — Input Nota Retur (refund / tukar) + cetak Nota Retur
# =============================================================================
@router.get("/pengadaan/retur/{id_retur}/nota", response_class=HTMLResponse)
def retur_nota_form(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    r = db.get(ReturProduk, id_retur)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404</div>", status_code=404)
    if r.status != "APPROVED":
        return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}?err={_q('Nota hanya untuk retur APPROVED.')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    items = db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == id_retur).all()
    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/retur", page_subtitle=f"Nota Retur {r.nomor_retur}",
        r=r, items=items, error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "retur_nota_form.html", ctx)


@router.post("/pengadaan/retur/{id_retur}/nota")
async def retur_nota_submit(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    f = await request.form()
    jenis = (f.get("jenis") or "").strip().lower()
    nomor_nota = (f.get("nomor_nota") or "").strip() or None
    tgl_raw = (f.get("tgl_nota") or "").strip()
    try:
        tgl_nota = date.fromisoformat(tgl_raw) if tgl_raw else None
    except ValueError:
        tgl_nota = None
    svc = ReturService(db)
    try:
        if jenis == "refund":
            traw = (f.get("total_nilai") or "").strip()
            total = Decimal(traw) if traw else None
            svc.input_nota_refund(id_retur, nomor_nota, tgl_nota, total,
                                  (f.get("catatan_nota") or "").strip() or None, user, request)
        elif jenis == "tukar":
            ids = f.getlist("rep_id_produk")
            batchs = f.getlist("rep_batch")
            eds = f.getlist("rep_ed")
            qtys = f.getlist("rep_qty")
            hargas = f.getlist("rep_harga")
            reps = []
            for i, idp in enumerate(ids):
                if not idp or not str(idp).strip():
                    continue
                try:
                    qv = float(qtys[i]) if i < len(qtys) and qtys[i] else 0
                except (ValueError, TypeError):
                    qv = 0
                if qv <= 0:
                    continue
                ed_raw = eds[i].strip() if i < len(eds) and eds[i] else ""
                try:
                    ed = date.fromisoformat(ed_raw) if ed_raw else None
                except ValueError:
                    ed = None
                try:
                    hv = Decimal(hargas[i]) if i < len(hargas) and hargas[i] else None
                except Exception:
                    hv = None
                reps.append({"id_produk": int(idp), "batch": (batchs[i].strip() if i < len(batchs) and batchs[i] else None),
                             "ed": ed, "qty": qv, "harga": hv})
            svc.input_nota_tukar(id_retur, nomor_nota, tgl_nota, reps, user, request)
        else:
            return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}/nota?err={_q('Pilih jenis penyelesaian.')}",
                                    status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}/nota?err={_q(str(detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/pengadaan/retur/{id_retur}?ok={_q('Nota retur tersimpan — retur SELESAI.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/pengadaan/retur/{id_retur}/nota/cetak", response_class=HTMLResponse)
def retur_nota_cetak(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    r = db.get(ReturProduk, id_retur)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404</div>", status_code=404)
    items = db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == id_retur).all()
    dist = db.get(MasterDistributor, r.id_distributor) if r.id_distributor else None
    from app.services.klinik_config_service import KlinikConfigService
    klinik = KlinikConfigService(db).get_config()
    ctx = {"klinik": klinik, "r": r, "items": items, "distributor": dist}
    return templates.TemplateResponse(request, "print/retur_nota.html", ctx)


from urllib.parse import quote as _q  # noqa: E402

__all__ = ["router"]
