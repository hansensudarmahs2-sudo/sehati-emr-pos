"""
Apotek web routes:
- GET  /web/apotek                                  - page shell antrian ANTRI_OBAT
- GET  /web/apotek/list                             - HTMX partial antrian (10s poll)
- GET  /web/apotek/kunjungan/{id_kunjungan}         - detail resep + cek stok
- POST /web/apotek/kunjungan/{id_kunjungan}/serahkan
- GET  /web/apotek/suggested-order                  - list produk stok menipis
- GET  /web/apotek/produk/{id_produk}/write-off     - form write-off
- POST /web/apotek/produk/{id_produk}/write-off     - submit write-off

Role gate: Apoteker + Admin + Owner + Superadmin (APOTEKER_ROLES).
"""

from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.repositories.master_produk_repo import MasterProdukRepository
from app.schemas.apotek import SerahkanObatRequest, WriteOffProdukRequest
from app.services.apotek_service import ApotekService
from app.services.master_produk_service import MasterProdukService
from app.web.routes._shared import (
    render_cached,
    build_shell_context,
    get_user_from_cookie,
    require_apoteker_role,
    templates,
)


router = APIRouter(tags=["Web Apotek"])


# =============================================================================
# GET /web/apotek - page shell antrian
# =============================================================================
@router.get("/apotek", response_class=HTMLResponse)
def apotek_antrian_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Apoteker/Admin/Owner.</div>", status_code=403)

    # #363E - Stok Critical stats untuk widget di top page
    stok_low_count = 0
    stok_out_count = 0
    try:
        produks = MasterProdukService(db).list_all(only_active=True, limit=2000)
        for p in produks:
            stok = float(p.stok_terkini or 0)
            stok_min = float(p.stok_minimal or 0)
            if stok <= 0:
                stok_out_count += 1
            elif stok <= stok_min:
                stok_low_count += 1
    except Exception:
        pass  # graceful — page tetap render kalau query gagal

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/apotek",
        page_subtitle="Antrian penyerahan obat",
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
        stok_low_count=stok_low_count,
        stok_out_count=stok_out_count,
    )
    return templates.TemplateResponse(request, "apotek_antrian.html", ctx)


# =============================================================================
# GET /web/apotek/list - HTMX partial antrian
# =============================================================================
@router.get("/apotek/list", response_class=HTMLResponse)
def apotek_antrian_partial(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Sesi habis.</div>", status_code=401)
    if not require_apoteker_role(user):
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>403</div>", status_code=403)

    def _build():
        antrian_resp = ApotekService(db).lihat_antrian()
        antrian_dict = antrian_resp.model_dump()
        total_item = sum(item.get("jumlah_item_obat", 0) or 0 for item in antrian_dict.get("data", []))
        counter = {
            "total_pasien": len(antrian_dict.get("data", [])),
            "total_item_obat": total_item,
        }
        return templates.TemplateResponse(request, "_apotek_antrian_content.html", {"antrian": antrian_dict, "counter": counter})
    try:
        # CACHE tampilan (KESTABILAN §9): antrian apotek sama utk semua apoteker (shared key).
        from app.core.ttl_cache import ANTRIAN_TTL
        return render_cached("antrian:apotek", ANTRIAN_TTL, _build)
    except Exception as e:
        return HTMLResponse(f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Error: {e!s}</div>", status_code=500)


# =============================================================================
# GET /web/apotek/kunjungan/{id_kunjungan} - detail resep
# =============================================================================
@router.get("/apotek/kunjungan/{id_kunjungan}", response_class=HTMLResponse)
def apotek_detail_resep(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    try:
        detail_resp = ApotekService(db).get_detail_resep(id_kunjungan)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    detail_dict = detail_resp.model_dump()

    # V7.2.1 audit AKSES-BACA rekam medis: catat siapa membuka resep pasien.
    try:
        from app.db.models import Kunjungan
        from app.services.audit_service import AuditService
        _kj_audit = db.get(Kunjungan, id_kunjungan)
        if _kj_audit is not None:
            AuditService(db).log_view(
                user.id_staf, _kj_audit.id_pasien,
                keterangan="Buka resep (apotek)", request=request,
            )
    except Exception:
        pass  # audit gagal tidak boleh memblokir tampilan

    # P-L5: preview batch/ED yang akan diserahkan (FEFO) per produk.
    from app.services.inventory_lot_service import InventoryLotService
    _lot = InventoryLotService(db)
    fefo_map = {}
    for o in detail_dict.get("daftar_obat", []):
        idp = o.get("id_produk")
        q = o.get("qty") or 0
        if idp:
            fefo_map[idp] = _lot.peek_fefo(tipe_item="PRODUK", lokasi="RETAIL", qty=q, id_produk=idp)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/apotek",
        page_subtitle=f"Resep - {detail_dict.get('nama_pasien', '-')}",
        detail=detail_dict,
        fefo_map=fefo_map,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "apotek_detail_resep.html", ctx)


# =============================================================================
# POST /web/apotek/kunjungan/{id_kunjungan}/serahkan
# =============================================================================
@router.post("/apotek/kunjungan/{id_kunjungan}/tunda-serah")
async def apotek_tunda_serah(id_kunjungan: int, request: Request, db: DbSession):
    """OBAT TERTUNDA (P1-1): tandai obat menyusul (wajib tgl kirim). Kunjungan → COMPLETED."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    from datetime import date as _date
    f = await request.form()
    raw = (f.get("tgl_janji_kirim") or "").strip()
    catatan = (f.get("catatan_kirim") or "").strip() or None
    tgl = None
    if raw:
        try:
            tgl = _date.fromisoformat(raw)
        except ValueError:
            tgl = None
    if tgl is None:
        return RedirectResponse(
            url=f"/web/apotek/kunjungan/{id_kunjungan}?err={quote('Tanggal kirim/ambil wajib diisi (YYYY-MM-DD).')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        result = ApotekService(db).tunda_serah_obat(
            id_kunjungan=id_kunjungan, tgl_janji_kirim=tgl, catatan=catatan,
            id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/apotek/kunjungan/{id_kunjungan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/apotek/kunjungan/{id_kunjungan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    msg = result.get("message", "Obat ditunda.") if isinstance(result, dict) else "Obat ditunda."
    return RedirectResponse(url=f"/web/apotek?ok={quote(msg)}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/apotek/kunjungan/{id_kunjungan}/serahkan")
async def apotek_serahkan_obat(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    # Task #54 — form boleh mengirim pilihan item. Kalau field-nya sama sekali tidak
    # ada (mis. pemanggil lama), tetap None = "serahkan semua", perilaku lama.
    from datetime import date as _date
    f = await request.form()

    # Penanda bahwa form ini MEMANG form pilih-item. Tanpa penanda, tidak dicentangnya
    # semua kotak tidak bisa dibedakan dari "form lama tanpa kotak sama sekali" — dan
    # menebaknya sebagai 'serahkan semua' persis kebalikan dari maksud petugas.
    _mode_pilih = (f.get("pilih_item") or "").strip() == "1"

    def _ids(nama):
        if not _mode_pilih:
            return None
        out = []
        for v in f.getlist(nama):
            try:
                out.append(int(str(v).strip()))
            except (TypeError, ValueError):
                continue
        return out

    _raw_tgl = (f.get("tgl_janji_kirim_sisa") or "").strip()
    _tgl_sisa = None
    if _raw_tgl:
        try:
            _tgl_sisa = _date.fromisoformat(_raw_tgl)
        except ValueError:
            _tgl_sisa = None

    try:
        payload = SerahkanObatRequest(
            id_kunjungan=id_kunjungan,
            id_resep=_ids("id_resep"),
            id_kunjungan_racikan=_ids("id_kunjungan_racikan"),
            tgl_janji_kirim_sisa=_tgl_sisa,
            catatan_kirim_sisa=(f.get("catatan_kirim_sisa") or "").strip() or None,
        )
        result = ApotekService(db).serahkan_obat(
            payload=payload,
            id_staf_apoteker=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/apotek/kunjungan/{id_kunjungan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/apotek/kunjungan/{id_kunjungan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = result.get("message", "Obat berhasil diserahkan.") if isinstance(result, dict) else "Obat berhasil diserahkan."
    return RedirectResponse(
        url=f"/web/apotek?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/apotek/suggested-order - list produk stok menipis
# =============================================================================
@router.get("/apotek/suggested-order", response_class=HTMLResponse)
def apotek_suggested_order_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    try:
        resp = ApotekService(db).suggested_order()
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    data_dict = resp.model_dump()

    # Group by kategori untuk display
    by_kategori = {"URGENT": [], "RENDAH": [], "AMAN": [], "NO_DATA": []}
    for item in data_dict.get("data", []):
        kat = item.get("kategori", "NO_DATA")
        by_kategori.setdefault(kat, []).append(item)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/apotek",
        page_subtitle="Suggested order - stok analytics",
        data=data_dict,
        by_kategori=by_kategori,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "apotek_suggested_order.html", ctx)


# =============================================================================
# GET /web/apotek/produk/{id_produk}/write-off - form write-off
# =============================================================================
# =============================================================================
# GET /web/apotek/stok - Manajemen Stok page (363A)
# =============================================================================
@router.get("/apotek/stok", response_class=HTMLResponse)
def apotek_stok_page(
    request: Request, db: DbSession,
    keyword: str = "",
    filter_stok: str = "",  # "" | "low" | "out"
):
    """List semua produk apotek dengan filter + action button write-off.

    Filter:
    - keyword: search by nama/kode produk
    - filter_stok: "low" (stok <= stok_minimal), "out" (stok = 0), "" (all)
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from datetime import date as _date
    def _ed_level(ed):
        if ed is None:
            return None
        d = (ed - _date.today()).days
        if d < 30:
            return "danger"   # < 1 bulan / sudah lewat
        if d < 90:
            return "warn"     # < 3 bulan
        return "ok"

    # Fetch produks (RETAIL + CABIN — semua produk apotek)
    produks = MasterProdukService(db).list_all(
        keyword=(keyword.strip() or None), only_active=True, limit=1000,
    )
    # P-L7: agregat lot per produk — ED terdekat (MIN abaikan NULL) + jumlah batch aktif.
    from app.db.models import StokLot as _StokLot
    from sqlalchemy import select as _sel, func as _func
    _lot_rows = db.execute(
        _sel(_StokLot.id_produk, _func.min(_StokLot.tgl_ed), _func.count(_StokLot.id_lot))
        .where(_StokLot.tipe_item == "PRODUK", _StokLot.status == "AKTIF", _StokLot.qty_sisa > 0)
        .group_by(_StokLot.id_produk)
    ).all()
    _lot_map = {pid: (ed, int(cnt)) for pid, ed, cnt in _lot_rows}

    # DYN: ambang efektif = MAX(stok_minimal manual, ROP dinamis)
    from datetime import datetime as _dt, timedelta as _td
    from app.repositories.apotek_repo import ApotekRepository as _AR
    from app.services.reorder_calc import effective_min as _effmin
    from app.db.models import MasterKlinikConfig as _MKC
    _qty90 = _AR(db).get_qty_terjual_per_produk(_dt.now() - _td(days=90))
    _cfg = db.get(_MKC, 1)
    _lead = int(getattr(_cfg, "lead_time_hari", 14) or 14)
    _safety = int(getattr(_cfg, "safety_hari", 7) or 7)

    # Convert ORM to dict + apply filter_stok
    rows = []
    count_low = 0
    count_out = 0
    for p in produks:
        stok = float(p.stok_terkini or 0)
        stok_min = float(p.stok_minimal or 0)
        eff_min = _effmin(p.stok_minimal, _qty90.get(p.id_produk, 0.0), _lead, _safety)
        is_low = stok <= eff_min and stok > 0
        is_out = stok <= 0
        if is_low:
            count_low += 1
        if is_out:
            count_out += 1
        # Apply filter
        if filter_stok == "low" and not is_low:
            continue
        if filter_stok == "out" and not is_out:
            continue
        rows.append({
            "id_produk": p.id_produk,
            "kode_produk": p.kode_produk,
            "nama_produk": p.nama_produk,
            "satuan": p.satuan,
            "tipe_produk": (p.tipe_produk.value if hasattr(p.tipe_produk, "value") else str(p.tipe_produk or "")),
            "stok_terkini": stok,
            "stok_minimal": stok_min,
            "stok_minimal_efektif": eff_min,
            "harga_jual": float(p.harga_jual or 0),
            "hpp_per_unit": float(p.hpp_per_unit or 0),
            "is_low": is_low,
            "is_out": is_out,
            "nearest_ed": _lot_map.get(p.id_produk, (None, 0))[0],
            "batch_count": _lot_map.get(p.id_produk, (None, 0))[1],
            "ed_level": _ed_level(_lot_map.get(p.id_produk, (None, 0))[0]),
        })

    ctx = build_shell_context(
        user, db=db, current_path="/web/apotek/stok",
        page_subtitle=f"Manajemen Stok ({len(rows)} produk)",
        rows=rows,
        keyword=keyword,
        filter_stok=filter_stok,
        count_total=len(produks),
        count_low=count_low,
        count_out=count_out,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "apotek_stok.html", ctx)


@router.get("/apotek/produk/{id_produk}/write-off", response_class=HTMLResponse)
def apotek_write_off_form(id_produk: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    produk = MasterProdukRepository(db).get_by_id(id_produk)
    if produk is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Produk tidak ditemukan.</div>", status_code=404)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/apotek",
        page_subtitle=f"Write-off - {produk.nama_produk}",
        produk={
            "id_produk": produk.id_produk,
            "kode_produk": produk.kode_produk,
            "nama_produk": produk.nama_produk,
            "satuan": produk.satuan,
            "stok_terkini": float(produk.stok_terkini or 0),
        },
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "apotek_write_off_form.html", ctx)


# =============================================================================
# POST /web/apotek/produk/{id_produk}/write-off - submit
# =============================================================================
@router.post("/apotek/produk/{id_produk}/write-off")
def apotek_write_off_submit(
    id_produk: int,
    request: Request,
    db: DbSession,
    jenis_mutasi: str = Form(...),
    qty_dibuang: float = Form(..., gt=0),
    keterangan: str = Form(..., min_length=3, max_length=200),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    try:
        payload = WriteOffProdukRequest(
            id_produk=id_produk,
            jenis_mutasi=jenis_mutasi,
            qty_dibuang=qty_dibuang,
            keterangan=keterangan,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/apotek/produk/{id_produk}/write-off?err={quote(f'Input invalid: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = ApotekService(db).write_off_produk(
            payload=payload,
            id_staf_apoteker=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/apotek/produk/{id_produk}/write-off?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/apotek/produk/{id_produk}/write-off?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = result.get("message", "Write-off berhasil.") if isinstance(result, dict) else "Write-off berhasil."
    return RedirectResponse(
        url=f"/web/apotek/suggested-order?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]


# =============================================================================
# GET /web/apotek/stok/{id_produk} — Detail lot/batch per produk (P-L7)
# =============================================================================
@router.get("/apotek/stok/{id_produk}", response_class=HTMLResponse)
def apotek_stok_detail(id_produk: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    from app.db.models import MasterProduk, StokLot, MasterDistributor
    from sqlalchemy import select as _sel
    produk = db.get(MasterProduk, id_produk)
    if produk is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Produk tidak ditemukan.</div>", status_code=404)
    lots = db.execute(
        _sel(StokLot).where(StokLot.tipe_item == "PRODUK", StokLot.id_produk == id_produk)
        .order_by(
            (StokLot.status != "AKTIF"),      # AKTIF dulu
            StokLot.tgl_ed.is_(None), StokLot.tgl_ed.asc(), StokLot.id_lot.asc(),
        )
    ).scalars().all()
    _dist = {}
    lot_rows = []
    for l in lots:
        dist_nama = None
        if l.id_distributor:
            if l.id_distributor not in _dist:
                _dist[l.id_distributor] = db.get(MasterDistributor, l.id_distributor)
            d = _dist[l.id_distributor]
            dist_nama = d.nama if d else None
        lot_rows.append({
            "batch_no": l.batch_no, "tgl_ed": l.tgl_ed,
            "qty_sisa": float(l.qty_sisa or 0), "qty_masuk": float(l.qty_masuk or 0),
            "harga_terima": float(l.harga_terima) if l.harga_terima is not None else None,
            "distributor": dist_nama, "tgl_masuk": l.tgl_masuk, "status": l.status,
        })
    ctx = build_shell_context(
        user, db=db, current_path="/web/apotek/stok",
        page_subtitle=f"Detail Stok — {produk.nama_produk}",
        produk={"id_produk": produk.id_produk, "nama_produk": produk.nama_produk,
                "kode_produk": produk.kode_produk, "stok_terkini": float(produk.stok_terkini or 0),
                "satuan": produk.satuan},
        lots=lot_rows,
    )
    return templates.TemplateResponse(request, "apotek_stok_detail.html", ctx)


# =============================================================================
# LAPORAN INVENTORY (P-L8): ED bucket, slow-moving, tren harga
# =============================================================================
def _apotek_laporan_guard(request, db):
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return None, HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    return user, None


@router.get("/apotek/laporan/ed", response_class=HTMLResponse)
def apotek_laporan_ed(request: Request, db: DbSession):
    user, resp = _apotek_laporan_guard(request, db)
    if resp:
        return resp
    from app.services.inventory_report_service import InventoryReportService
    data = InventoryReportService(db).ed_report()
    ctx = build_shell_context(user, db=db, current_path="/web/apotek/stok",
                              page_subtitle="Laporan ED", data=data)
    return templates.TemplateResponse(request, "apotek_laporan_ed.html", ctx)


@router.get("/apotek/laporan/slow-moving", response_class=HTMLResponse)
def apotek_laporan_slow(request: Request, db: DbSession):
    user, resp = _apotek_laporan_guard(request, db)
    if resp:
        return resp
    from app.services.inventory_report_service import InventoryReportService
    rows = InventoryReportService(db).slow_moving()
    ctx = build_shell_context(user, db=db, current_path="/web/apotek/stok",
                              page_subtitle="Laporan Slow-Moving", rows=rows)
    return templates.TemplateResponse(request, "apotek_laporan_slow.html", ctx)


@router.get("/apotek/laporan/harga", response_class=HTMLResponse)
def apotek_laporan_harga(request: Request, db: DbSession):
    user, resp = _apotek_laporan_guard(request, db)
    if resp:
        return resp
    from app.services.inventory_report_service import InventoryReportService
    rows = InventoryReportService(db).price_trend()
    ctx = build_shell_context(user, db=db, current_path="/web/apotek/stok",
                              page_subtitle="Tren Harga Pembelian", rows=rows)
    return templates.TemplateResponse(request, "apotek_laporan_harga.html", ctx)
