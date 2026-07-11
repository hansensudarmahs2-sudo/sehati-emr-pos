"""
Stock Opname web routes.

Routes (/web/pengadaan/opname/*):
- GET  /                                - list + filter (lokasi, status, tgl)
- GET  /baru                            - form tambah (pick lokasi → list items)
- POST /baru                            - submit (multi-row items dengan qty_fisik)
- GET  /_item-row                       - HTMX partial (+Tambah Item)
- GET  /{id}                            - detail dengan items + selisih
- POST /{id}/approve                    - apply selisih ke stok (Owner/Superadmin)
- POST /{id}/reject                     - reject dengan alasan

Role gate:
- Create + view: PURCHASING_FULL_ROLES (Owner/Superadmin/Purchasing) + APOTEKER untuk RETAIL
- Approve/Reject: OPNAME_APPROVE_ROLES (Owner/Superadmin)
"""

from datetime import date
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from sqlalchemy import select as _select

from app.db.models import (
    InventoryHistory,
    InventoryStok,
    JenisMutasiEnum,
    LokasiOpnameEnum,
    MasterProduk,
    MasterStaf,
    StafRoleEnum,
    StatusOpnameEnum,
    StokLot,
)
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.master_produk_repo import MasterProdukRepository
from app.repositories.opname_repo import OpnameRepository
from app.repositories.staf_repo import StafRepository
from app.schemas.pengadaan import (
    StockOpnameCreateRequest,
    StockOpnameItemInput,
    StockOpnameRejectRequest,
)
from app.services.opname_service import OpnameService
from app.web.routes._shared import (
    script_json,
    build_shell_context,
    get_user_from_cookie,
    require_opname_approve_role,
    require_purchasing_view_role,
    templates,
)


router = APIRouter(tags=["Web Stock Opname"])


def _403(msg: str = "Forbidden") -> HTMLResponse:
    return HTMLResponse(f"<div style='padding:2rem'>403 - {msg}</div>", status_code=403)


def _fetch_items_by_lokasi(db, lokasi: str, actor):
    """Fetch list items yang relevan untuk lokasi opname."""
    items = []
    actor_role = actor.role if isinstance(actor.role, StafRoleEnum) else StafRoleEnum(actor.role)
    is_apoteker = actor_role == StafRoleEnum.APOTEKER

    if lokasi == "RETAIL":
        # P-L9: opname per-batch. Satu baris = satu lot AKTIF (qty_sisa>0) per produk RETAIL.
        # Urutan prioritas hitung: ED TERDEKAT dulu (NULL paling akhir), lalu HARGA JUAL tertinggi
        # → item bernilai bisnis tinggi / paling berisiko ED dicek lebih dulu.
        produk_list = MasterProdukRepository(db).list_with_filter(only_active=True, limit=500)
        produk_map: dict = {}
        for p in produk_list:
            tipe = (p.tipe_produk.value if hasattr(p.tipe_produk, "value")
                    else str(p.tipe_produk))
            if tipe == "RETAIL":
                produk_map[p.id_produk] = p
        lot_rows = db.execute(
            _select(StokLot).where(
                StokLot.tipe_item == "PRODUK",
                StokLot.lokasi == "RETAIL",
                StokLot.status == "AKTIF",
                StokLot.qty_sisa > 0,
            )
        ).scalars().all()
        retail_rows = [(lot, produk_map[lot.id_produk])
                       for lot in lot_rows if lot.id_produk in produk_map]
        # DEFAULT: urut ABJAD nama produk (tie: ED terdekat). Sortir ED/harga = tombol di UI.
        retail_rows.sort(key=lambda lp: (
            (lp[1].nama_produk or "").lower(),
            lp[0].tgl_ed is None,
            lp[0].tgl_ed or date.max,
        ))
        for lot, p in retail_rows:
            items.append({
                "tipe_item": "PRODUK",
                "id_produk": p.id_produk,
                "id_bahan": None,
                "id_lot": lot.id_lot,
                "batch_no": lot.batch_no or "",
                "tgl_ed": lot.tgl_ed.isoformat() if lot.tgl_ed else "",
                "nama": p.nama_produk,
                "kode": p.kode_produk,
                "satuan": p.satuan,
                "qty_sistem": float(lot.qty_sisa or 0),
                "harga_jual": float(p.harga_jual or 0),
            })
    else:  # KABIN atau GUDANG_UTAMA (BAHAN tetap agregat)
        bahan_list = InventoryRepository(db).list_all(limit=500)
        for b in bahan_list:
            qty_sistem = (float(b.stok_kabin or 0) if lokasi == "KABIN"
                          else float(b.stok_gudang_utama or 0))
            items.append({
                "tipe_item": "BAHAN",
                "id_produk": None,
                "id_bahan": b.id_bahan,
                "id_lot": None,
                "batch_no": "",
                "tgl_ed": "",
                "nama": b.nama_bahan,
                "kode": f"BHN-{b.id_bahan}",
                "satuan": b.satuan or "",
                "qty_sistem": qty_sistem,
            })
    return items


# =============================================================================
# LIST
# =============================================================================
@router.get("/pengadaan/opname", response_class=HTMLResponse)
def opname_list(
    request: Request, db: DbSession,
    status_f: str = "", lokasi_f: str = "",
    tgl_dari: str = "", tgl_sampai: str = "",
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    status_filter = None
    if status_f:
        try:
            status_filter = StatusOpnameEnum(status_f)
        except ValueError:
            pass
    lokasi_filter = None
    if lokasi_f:
        try:
            lokasi_filter = LokasiOpnameEnum(lokasi_f)
        except ValueError:
            pass

    dari, sampai = None, None
    try:
        if tgl_dari:
            dari = date.fromisoformat(tgl_dari)
        if tgl_sampai:
            sampai = date.fromisoformat(tgl_sampai)
    except ValueError:
        pass

    rows = OpnameRepository(db).list_with_filter(
        status=status_filter, lokasi=lokasi_filter,
        tgl_dari=dari, tgl_sampai=sampai, limit=200,
    )
    data = []
    for op, pelaksana, jumlah in rows:
        data.append({
            "id_opname": op.id_opname,
            "nomor_opname": op.nomor_opname,
            "tgl_opname": op.tgl_opname.strftime("%Y-%m-%d %H:%M") if op.tgl_opname else "-",
            "lokasi": op.lokasi.value if hasattr(op.lokasi, "value") else str(op.lokasi),
            "status": op.status.value if hasattr(op.status, "value") else str(op.status),
            "nama_staf_pelaksana": pelaksana.nama_staf if pelaksana else f"(staf #{op.id_staf_pelaksana})",
            "jumlah_item": jumlah,
            "total_selisih_value": float(op.total_selisih_value) if op.total_selisih_value else None,
        })

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/opname",
        page_subtitle="Stock Opname",
        data=data, total=len(data),
        status_options=[e.value for e in StatusOpnameEnum],
        lokasi_options=[e.value for e in LokasiOpnameEnum],
        status_f=status_f, lokasi_f=lokasi_f,
        tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "opname_list.html", ctx)


# =============================================================================
# FORM TAMBAH
# =============================================================================
@router.get("/pengadaan/opname/baru", response_class=HTMLResponse)
def opname_baru_form(
    request: Request, db: DbSession,
    lokasi: str = "RETAIL",
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    # Validasi lokasi
    try:
        lokasi_enum = LokasiOpnameEnum(lokasi)
    except ValueError:
        lokasi = "RETAIL"
        lokasi_enum = LokasiOpnameEnum.RETAIL

    actor_role = user.role if isinstance(user.role, StafRoleEnum) else StafRoleEnum(user.role)
    is_apoteker = actor_role == StafRoleEnum.APOTEKER

    # Apoteker hanya boleh opname RETAIL
    if is_apoteker and lokasi != "RETAIL":
        return RedirectResponse(
            url=f"/web/pengadaan/opname?err={quote('Apoteker hanya boleh opname RETAIL')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    items_available = _fetch_items_by_lokasi(db, lokasi, user)

    # P-L9: pilihan produk utk "batch baru ditemukan" (RETAIL) — semua produk RETAIL aktif
    produk_choices = []
    if lokasi == "RETAIL":
        for p in MasterProdukRepository(db).list_with_filter(only_active=True, limit=500):
            tp = p.tipe_produk.value if hasattr(p.tipe_produk, "value") else str(p.tipe_produk)
            if tp == "RETAIL":
                produk_choices.append({
                    "id_produk": p.id_produk, "kode": p.kode_produk, "nama": p.nama_produk,
                })

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/opname",
        page_subtitle=f"Buat Opname — {lokasi}",
        lokasi=lokasi,
        lokasi_options=[e.value for e in LokasiOpnameEnum],
        items_available=items_available,
        produk_choices_json=script_json(produk_choices),  # P1-4: aman dari </script> breakout
        is_apoteker=is_apoteker,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "opname_form.html", ctx)


@router.post("/pengadaan/opname/baru", response_class=HTMLResponse)
async def opname_baru_submit(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    # P-L9: opname RETAIL bisa 300+ baris; naikkan batas field form (default Starlette 1000).
    # (JS di form hanya submit baris yang diisi, jadi payload nyata kecil — ini jaring pengaman.)
    form = await request.form(max_fields=50000)
    lokasi_raw = (form.get("lokasi") or "RETAIL").strip()
    catatan = (form.get("catatan") or "").strip() or None

    # Parse multi-row items
    tipe_items = form.getlist("tipe_item")
    id_produks = form.getlist("id_produk")
    id_bahans = form.getlist("id_bahan")
    id_lots = form.getlist("id_lot")
    batch_nos = form.getlist("batch_no")
    tgl_eds = form.getlist("tgl_ed")
    qty_fisiks = form.getlist("qty_fisik")
    catatan_items = form.getlist("catatan_item")

    items: list[StockOpnameItemInput] = []
    for i, tipe in enumerate(tipe_items):
        tipe_clean = (tipe or "").strip().upper()
        if tipe_clean not in ("PRODUK", "BAHAN"):
            continue
        try:
            qty_f = float(qty_fisiks[i]) if i < len(qty_fisiks) else None
        except (ValueError, TypeError):
            qty_f = None
        if qty_f is None or qty_f < 0:
            continue  # skip row tanpa qty_fisik (mungkin item yang tidak dicek)

        id_produk = None
        id_bahan = None
        if tipe_clean == "PRODUK":
            try:
                id_produk = int(id_produks[i]) if i < len(id_produks) and id_produks[i] else None
            except (ValueError, TypeError):
                id_produk = None
            if id_produk is None or id_produk == 0:
                continue
        else:
            try:
                id_bahan = int(id_bahans[i]) if i < len(id_bahans) and id_bahans[i] else None
            except (ValueError, TypeError):
                id_bahan = None
            if id_bahan is None or id_bahan == 0:
                continue

        cat = catatan_items[i].strip() if i < len(catatan_items) and catatan_items[i] else None

        # P-L9 per-batch (PRODUK): id_lot / batch_no / tgl_ed
        id_lot = None
        batch_no = None
        tgl_ed_val = None
        if tipe_clean == "PRODUK":
            raw_lot = id_lots[i] if i < len(id_lots) else ""
            try:
                id_lot = int(raw_lot) if raw_lot not in (None, "", "0") else None
            except (ValueError, TypeError):
                id_lot = None
            batch_no = (batch_nos[i].strip() or None) if i < len(batch_nos) and batch_nos[i] else None
            raw_ed = tgl_eds[i].strip() if i < len(tgl_eds) and tgl_eds[i] else ""
            if raw_ed:
                try:
                    tgl_ed_val = date.fromisoformat(raw_ed)
                except ValueError:
                    tgl_ed_val = None
            # Lewati baris PRODUK tanpa lot DAN tanpa batch baru (tak ada yang dihitung)
            if id_lot is None and not batch_no and qty_f == 0:
                continue

        items.append(StockOpnameItemInput(
            tipe_item=tipe_clean,
            id_produk=id_produk,
            id_bahan=id_bahan,
            id_lot=id_lot,
            batch_no=batch_no,
            tgl_ed=tgl_ed_val,
            qty_fisik=qty_f,
            catatan_item=cat,
        ))

    if not items:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/baru?lokasi={lokasi_raw}&err={quote('Minimal 1 item harus ada qty_fisik')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        lokasi_enum = LokasiOpnameEnum(lokasi_raw)
        payload = StockOpnameCreateRequest(
            lokasi=lokasi_enum, catatan=catatan, items=items,
        )
        created = OpnameService(db).create_opname(payload=payload, actor=user, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/baru?lokasi={lokasi_raw}&err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/baru?lokasi={lokasi_raw}&err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/opname/{created.id_opname}?ok={quote(f'Opname {created.nomor_opname} berhasil dibuat (status DRAFT)')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# DETAIL
# =============================================================================
@router.get("/pengadaan/opname/{id_opname}", response_class=HTMLResponse)
def opname_detail(id_opname: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    repo = OpnameRepository(db)
    op = repo.get_by_id(id_opname)
    if op is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Opname tidak ditemukan</div>", status_code=404)

    items = repo.get_items_by_opname(id_opname)
    pelaksana = StafRepository(db).get_by_id(op.id_staf_pelaksana)
    approver = StafRepository(db).get_by_id(op.id_staf_approver) if op.id_staf_approver else None

    op_dict = {
        "id_opname": op.id_opname,
        "nomor_opname": op.nomor_opname,
        "tgl_opname": op.tgl_opname.strftime("%Y-%m-%d %H:%M") if op.tgl_opname else "-",
        "lokasi": op.lokasi.value if hasattr(op.lokasi, "value") else str(op.lokasi),
        "status": op.status.value if hasattr(op.status, "value") else str(op.status),
        "nama_staf_pelaksana": pelaksana.nama_staf if pelaksana else f"(staf #{op.id_staf_pelaksana})",
        "nama_staf_approver": approver.nama_staf if approver else None,
        "tgl_approve": op.tgl_approve.strftime("%Y-%m-%d %H:%M") if op.tgl_approve else None,
        "catatan": op.catatan,
        "total_selisih_value": float(op.total_selisih_value) if op.total_selisih_value else None,
    }

    items_data = []
    jumlah_pos = 0
    jumlah_neg = 0
    jumlah_match = 0
    for it in items:
        selisih = float(it.qty_fisik) - float(it.qty_sistem)
        if selisih > 0:
            jumlah_pos += 1
        elif selisih < 0:
            jumlah_neg += 1
        else:
            jumlah_match += 1
        items_data.append({
            "id_opname_item": it.id_opname_item,
            "tipe_item": it.tipe_item,
            "nama_snapshot": it.nama_snapshot,
            "batch_no": it.batch_no or "",
            "tgl_ed": it.tgl_ed.isoformat() if it.tgl_ed else "",
            "qty_sistem": float(it.qty_sistem),
            "qty_fisik": float(it.qty_fisik),
            "selisih": selisih,
            "catatan_item": it.catatan_item,
        })

    user_role = user.role if isinstance(user.role, StafRoleEnum) else StafRoleEnum(user.role)
    is_approver = user_role in {StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN}

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/opname",
        page_subtitle=f"Opname {op.nomor_opname}",
        opname=op_dict, items=items_data,
        jumlah_pos=jumlah_pos, jumlah_neg=jumlah_neg, jumlah_match=jumlah_match,
        can_approve=(op_dict["status"] == "DRAFT" and is_approver),
        can_reject=(op_dict["status"] == "DRAFT" and is_approver),
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "opname_detail.html", ctx)


# =============================================================================
# APPROVE
# =============================================================================
@router.post("/pengadaan/opname/{id_opname}/approve")
def opname_approve(id_opname: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_opname_approve_role(user):
        return _403("Hanya Owner/Superadmin yang boleh approve opname.")

    try:
        result = OpnameService(db).approve(id_opname=id_opname, actor=user, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/{id_opname}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/{id_opname}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = result.get("message", "Opname approved") if isinstance(result, dict) else "Opname approved"
    return RedirectResponse(
        url=f"/web/pengadaan/opname/{id_opname}?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# REJECT
# =============================================================================
@router.post("/pengadaan/opname/{id_opname}/reject")
def opname_reject(
    id_opname: int, request: Request, db: DbSession,
    alasan: str = Form(..., min_length=3, max_length=500),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_opname_approve_role(user):
        return _403("Hanya Owner/Superadmin yang boleh reject opname.")

    try:
        payload = StockOpnameRejectRequest(alasan=alasan.strip())
        OpnameService(db).reject(
            id_opname=id_opname, payload=payload, actor=user, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/{id_opname}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/opname/{id_opname}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/opname/{id_opname}?ok={quote('Opname berhasil di-reject')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )




# =============================================================================
# HISTORY MUTASI — read-only kartu stok per item
# =============================================================================
@router.get("/pengadaan/mutasi", response_class=HTMLResponse)
def history_mutasi(
    request: Request, db: DbSession,
    tipe_item: str = "",
    id_produk: int = 0, id_bahan: int = 0,
    jenis_mutasi: str = "",
    tgl_dari: str = "", tgl_sampai: str = "",
):
    """
    History mutasi inventory_history dengan filter per item + jenis + tgl.
    Read-only view — pelajari riwayat stok masuk/keluar untuk audit.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    from datetime import datetime, time
    from sqlalchemy import and_, select as _sel

    # Build query
    stmt = (
        _sel(InventoryHistory, MasterStaf, InventoryStok, MasterProduk)
        .outerjoin(MasterStaf, InventoryHistory.id_staf == MasterStaf.id_staf)
        .outerjoin(InventoryStok, InventoryHistory.id_bahan == InventoryStok.id_bahan)
        .outerjoin(MasterProduk, InventoryHistory.id_produk == MasterProduk.id_produk)
    )
    conds = []
    if tipe_item in ("PRODUK", "BAHAN"):
        conds.append(InventoryHistory.tipe_item == tipe_item)
    if id_produk and id_produk > 0:
        conds.append(InventoryHistory.id_produk == id_produk)
    if id_bahan and id_bahan > 0:
        conds.append(InventoryHistory.id_bahan == id_bahan)
    if jenis_mutasi:
        try:
            jm = JenisMutasiEnum(jenis_mutasi)
            conds.append(InventoryHistory.jenis_mutasi == jm)
        except ValueError:
            pass
    if tgl_dari:
        try:
            d = date.fromisoformat(tgl_dari)
            conds.append(InventoryHistory.waktu_mutasi >= datetime.combine(d, time.min))
        except ValueError:
            pass
    if tgl_sampai:
        try:
            d = date.fromisoformat(tgl_sampai)
            conds.append(InventoryHistory.waktu_mutasi <= datetime.combine(d, time.max))
        except ValueError:
            pass
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(InventoryHistory.waktu_mutasi.desc()).limit(500)

    rows = db.execute(stmt).all()
    data = []
    for h, staf, bahan, produk in rows:
        nama_item = "(unknown)"
        kode_item = ""
        if h.tipe_item == "PRODUK" and produk:
            nama_item = produk.nama_produk
            kode_item = produk.kode_produk
        elif h.tipe_item == "BAHAN" and bahan:
            nama_item = bahan.nama_bahan
            kode_item = f"BHN-{bahan.id_bahan}"
        data.append({
            "id_history": h.id_history,
            "waktu_mutasi": h.waktu_mutasi.strftime("%Y-%m-%d %H:%M") if h.waktu_mutasi else "-",
            "tipe_item": h.tipe_item,
            "nama_item": nama_item,
            "kode_item": kode_item,
            "jenis_mutasi": h.jenis_mutasi.value if hasattr(h.jenis_mutasi, "value") else str(h.jenis_mutasi),
            "qty_perubahan": float(h.qty_perubahan),
            "stok_akhir": float(h.stok_akhir),
            "referensi": h.referensi or "—",
            "keterangan": h.keterangan or "",
            "nama_staf": staf.nama_staf if staf else f"(staf #{h.id_staf})",
        })

    # Dropdown options
    produk_opts = MasterProdukRepository(db).list_with_filter(only_active=True, limit=500)
    produk_options = [
        {"id_produk": p.id_produk, "label": f"{p.kode_produk} — {p.nama_produk}"}
        for p in produk_opts
    ]
    bahan_opts = InventoryRepository(db).list_all(limit=500)
    bahan_options = [
        {"id_bahan": b.id_bahan, "label": f"{b.nama_bahan}"}
        for b in bahan_opts
    ]

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/mutasi",
        page_subtitle="History Mutasi Stok",
        data=data, total=len(data),
        produk_options=produk_options,
        bahan_options=bahan_options,
        jenis_options=[e.value for e in JenisMutasiEnum],
        tipe_item=tipe_item, id_produk=id_produk, id_bahan=id_bahan,
        jenis_mutasi=jenis_mutasi, tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "history_mutasi.html", ctx)


__all__ = ["router"]
