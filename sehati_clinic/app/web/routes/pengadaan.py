"""
Pengadaan / Purchase Order web routes.

Routes:
- GET  /web/pengadaan/pemesanan                                    - list + filter
- GET  /web/pengadaan/pemesanan/baru                               - form tambah
- POST /web/pengadaan/pemesanan/baru                               - submit
- GET  /web/pengadaan/pemesanan/_item-row                          - HTMX partial (+Tambah Item)
- GET  /web/pengadaan/pemesanan/{id}                               - detail
- POST /web/pengadaan/pemesanan/{id}/edit                          - update header (SUBMITTED only)
- POST /web/pengadaan/pemesanan/{id}/approve-ordered               - approve
- POST /web/pengadaan/pemesanan/{id}/cancel                        - cancel
- POST /web/pengadaan/pemesanan/{id}/item/{id_item}/receive        - receive event

Role gates per route — see implementations.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.db.models import (
    InventoryStok,
    MasterProduk,
    StafRoleEnum,
    StatusPemesananEnum,
)
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.master_produk_repo import MasterProdukRepository
from app.repositories.pemesanan_repo import PemesananRepository
from app.repositories.staf_repo import StafRepository
from app.schemas.pengadaan import (
    PemesananCreateRequest,
    PemesananHeaderUpdate,
    PemesananItemCreate,
    ReceiveItemRequest,
)
from app.services.pemesanan_service import PemesananService
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_purchasing_approve_cancel_role,
    require_purchasing_full_role,
    require_purchasing_view_role,
    templates,
)


router = APIRouter(tags=["Web Pengadaan"])


def _403(msg: str = "Forbidden") -> HTMLResponse:
    return HTMLResponse(f"<div style='padding:2rem'>403 - {msg}</div>", status_code=403)


# =============================================================================
# Helpers
# =============================================================================
def _fetch_master_options(db, actor):
    """
    Fetch options dropdowns untuk form tambah PO, filter sesuai role actor.
    Apoteker hanya boleh produk RETAIL, tidak boleh bahan.
    """
    actor_role = actor.role if isinstance(actor.role, StafRoleEnum) else StafRoleEnum(actor.role)
    is_apoteker = actor_role == StafRoleEnum.APOTEKER

    # Produk
    produk_list = MasterProdukRepository(db).list_with_filter(only_active=True, limit=500)
    master_produk = []
    for p in produk_list:
        tipe = (p.tipe_produk.value if hasattr(p.tipe_produk, "value")
                else str(p.tipe_produk))
        if is_apoteker and tipe != "RETAIL":
            continue  # Apoteker tidak boleh CABIN/ALAT
        master_produk.append({
            "id_produk": p.id_produk,
            "kode_produk": p.kode_produk,
            "nama_produk": p.nama_produk,
            "tipe_produk": tipe,
            "satuan": p.satuan,
        })

    # Bahan — Apoteker SKIP
    master_bahan = []
    if not is_apoteker:
        bahan_list = InventoryRepository(db).list_all(limit=500)
        master_bahan = [
            {
                "id_bahan": b.id_bahan,
                "nama_bahan": b.nama_bahan,
                "satuan": b.satuan or "",
                "satuan_pembelian": b.satuan_pembelian or "",
            }
            for b in bahan_list
        ]

    return master_produk, master_bahan, is_apoteker


# =============================================================================
# LIST
# =============================================================================
@router.get("/pengadaan/pemesanan", response_class=HTMLResponse)
def pemesanan_list(
    request: Request, db: DbSession,
    status_f: str = "", tgl_dari: str = "", tgl_sampai: str = "",
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403("Hanya Owner/Superadmin/Purchasing/Apoteker.")

    status_filter = None
    if status_f:
        try:
            status_filter = StatusPemesananEnum(status_f)
        except ValueError:
            pass

    dari = None
    sampai = None
    try:
        if tgl_dari:
            dari = date.fromisoformat(tgl_dari)
        if tgl_sampai:
            sampai = date.fromisoformat(tgl_sampai)
    except ValueError:
        dari, sampai = None, None

    rows = PemesananRepository(db).list_with_filter(
        status=status_filter, tgl_dari=dari, tgl_sampai=sampai, limit=200,
    )
    data = []
    for po, pemesan, jumlah in rows:
        data.append({
            "id_pemesanan": po.id_pemesanan,
            "nomor_po": po.nomor_po,
            "tgl_pemesanan": po.tgl_pemesanan.strftime("%Y-%m-%d %H:%M") if po.tgl_pemesanan else "-",
            "tgl_perkiraan_datang": po.tgl_perkiraan_datang.isoformat() if po.tgl_perkiraan_datang else "-",
            "supplier_nama": po.supplier_nama or "-",
            "status": po.status.value if hasattr(po.status, "value") else str(po.status),
            "nama_staf_pemesan": pemesan.nama_staf if pemesan else f"(staf #{po.id_staf_pemesan})",
            "jumlah_item": jumlah,
            "total_estimasi_biaya": float(po.total_estimasi_biaya) if po.total_estimasi_biaya else None,
        })

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/pemesanan",
        page_subtitle="Pemesanan / Purchase Order",
        data=data, total=len(data),
        status_options=[e.value for e in StatusPemesananEnum],
        status_f=status_f, tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pemesanan_list.html", ctx)


# =============================================================================
# FORM TAMBAH
# =============================================================================
@router.get("/pengadaan/pemesanan/baru", response_class=HTMLResponse)
def pemesanan_baru_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    master_produk, master_bahan, is_apoteker = _fetch_master_options(db, user)

    # ----- Optional prefill dari halaman Suggested Order (apotek) -----
    # Query params: ?prefill_produk=12,34&prefill_qty=20,15
    prefill_rows: list[dict] = []
    prefill_produk_raw = (request.query_params.get("prefill_produk") or "").strip()
    prefill_qty_raw = (request.query_params.get("prefill_qty") or "").strip()
    if prefill_produk_raw:
        try:
            ids = [int(x) for x in prefill_produk_raw.split(",") if x.strip().isdigit()]
            qtys_str = [x.strip() for x in prefill_qty_raw.split(",") if x.strip()]
            # Cari produk valid yang masuk ke master_produk yang user boleh PO
            produk_map = {p["id_produk"]: p for p in master_produk}
            for idx, pid in enumerate(ids):
                if pid not in produk_map:
                    continue  # skip kalau produk bukan retail (apoteker filter) atau invalid
                qty_default = ""
                if idx < len(qtys_str):
                    try:
                        qv = float(qtys_str[idx])
                        if qv > 0:
                            qty_default = qtys_str[idx]
                    except ValueError:
                        pass
                prefill_rows.append({
                    "tipe_item": "PRODUK",
                    "id_produk": pid,
                    "qty_dipesan": qty_default,
                })
        except Exception:
            # Silent fail — kalau ada query param invalid, form tetap render kosong
            prefill_rows = []

    from app.db.models import MasterDistributor
    _distributors = db.query(MasterDistributor).filter(
        MasterDistributor.is_active == True
    ).order_by(MasterDistributor.nama).all()

    # PO-B: apoteker aktif untuk dropdown penanggung jawab (wajib)
    from app.services.klinik_config_service import KlinikConfigService
    apotekers = KlinikConfigService(db).list_apoteker(only_active=True)

    # SHIP-L3: lokasi pengiriman aktif (dropdown "kirim ke")
    from app.db.models import LokasiPengiriman
    _loks = db.query(LokasiPengiriman).filter(LokasiPengiriman.is_active == True).order_by(
        LokasiPengiriman.is_default.desc(), LokasiPengiriman.nama).all()
    lokasi_list = [{"id": l.id_lokasi, "nama": l.nama, "is_default": l.is_default} for l in _loks]
    lokasi_default = next((l["id"] for l in lokasi_list if l["is_default"]), None)

    # PO polish: autofill harga dari PO lampau (harga terakhir per produk/bahan)
    from app.db.models import Pemesanan as _POh, PemesananItem as _POi
    _hrows = (
        db.query(_POi.id_produk, _POi.id_bahan, _POi.harga_satuan)
        .join(_POh, _POi.id_pemesanan == _POh.id_pemesanan)
        .filter(_POi.harga_satuan.isnot(None))
        .order_by(_POh.tgl_pemesanan.desc())
        .limit(2000).all()
    )
    _lhp, _lhb = {}, {}
    for _idp, _idb, _hrg in _hrows:
        if _idp and _idp not in _lhp:
            _lhp[str(_idp)] = float(_hrg)
        if _idb and _idb not in _lhb:
            _lhb[str(_idb)] = float(_hrg)
    from app.web.routes._shared import script_json as _script_json
    last_harga_json = _script_json({"produk": _lhp, "bahan": _lhb})  # P1-4

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/pemesanan",
        page_subtitle="Tambah PO Baru",
        master_produk=master_produk,
        master_bahan=master_bahan,
        is_apoteker=is_apoteker,
        prefill_rows=prefill_rows,
        distributors=[d.nama for d in _distributors],
        apotekers=apotekers,
        lokasi_list=lokasi_list,
        lokasi_default=lokasi_default,
        last_harga_json=last_harga_json,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pemesanan_form.html", ctx)


@router.get("/pengadaan/pemesanan/_item-row", response_class=HTMLResponse)
def pemesanan_item_row(request: Request, db: DbSession):
    """HTMX partial — render 1 row item kosong untuk +Tambah Item."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("<div>Session expired</div>", status_code=401)
    if not require_purchasing_view_role(user):
        return HTMLResponse("<div>403</div>", status_code=403)

    master_produk, master_bahan, is_apoteker = _fetch_master_options(db, user)

    return templates.TemplateResponse(
        request, "_pemesanan_item_row.html",
        {
            "master_produk": master_produk,
            "master_bahan": master_bahan,
            "is_apoteker": is_apoteker,
            "row_idx": request.query_params.get("idx", "0"),
        },
    )


@router.post("/pengadaan/pemesanan/baru", response_class=HTMLResponse)
async def pemesanan_baru_submit(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    form = await request.form()
    supplier_nama = (form.get("supplier_nama") or "").strip() or None
    tgl_perkiraan_raw = (form.get("tgl_perkiraan_datang") or "").strip()
    tgl_perkiraan = None
    if tgl_perkiraan_raw:
        try:
            tgl_perkiraan = date.fromisoformat(tgl_perkiraan_raw)
        except ValueError:
            return RedirectResponse(
                url=f"/web/pengadaan/pemesanan/baru?err={quote('Format tgl perkiraan invalid (YYYY-MM-DD)')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    catatan = (form.get("catatan") or "").strip() or None

    # PO-B: termin, validitas (hari), apoteker PJ (wajib)
    def _int_or_none(v):
        v = (v or "").strip()
        try:
            return int(v) if v else None
        except (ValueError, TypeError):
            return None
    termin_hari = _int_or_none(form.get("termin_hari"))
    validitas_hari = _int_or_none(form.get("validitas_hari"))
    id_apoteker = _int_or_none(form.get("id_apoteker"))
    id_lokasi_pengiriman = _int_or_none(form.get("id_lokasi_pengiriman"))
    if id_apoteker is None:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/baru?err={quote('Pilih apoteker penanggung jawab dulu.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Parse multi-row items: tipe_item[], id_produk[], id_bahan[], qty_dipesan[], harga_satuan[], catatan_item[]
    tipe_items = form.getlist("tipe_item")
    id_produks = form.getlist("id_produk")
    id_bahans = form.getlist("id_bahan")
    qtys = form.getlist("qty_dipesan")
    hargas = form.getlist("harga_satuan")
    catatans = form.getlist("catatan_item")

    items: list[PemesananItemCreate] = []
    for i, tipe in enumerate(tipe_items):
        tipe_clean = (tipe or "").strip().upper()
        if tipe_clean not in ("PRODUK", "BAHAN"):
            continue
        try:
            qty_val = float(qtys[i]) if i < len(qtys) else 0
        except (ValueError, TypeError):
            qty_val = 0
        if qty_val <= 0:
            continue

        id_produk = None
        id_bahan = None
        if tipe_clean == "PRODUK":
            try:
                id_produk = int(id_produks[i]) if i < len(id_produks) and id_produks[i] else None
            except (ValueError, TypeError):
                id_produk = None
            if id_produk is None or id_produk == 0:
                continue
        else:  # BAHAN
            try:
                id_bahan = int(id_bahans[i]) if i < len(id_bahans) and id_bahans[i] else None
            except (ValueError, TypeError):
                id_bahan = None
            if id_bahan is None or id_bahan == 0:
                continue

        harga = None
        if i < len(hargas) and hargas[i]:
            try:
                harga = Decimal(str(hargas[i]))
            except Exception:
                harga = None
        cat = catatans[i].strip() if i < len(catatans) and catatans[i] else None

        items.append(PemesananItemCreate(
            tipe_item=tipe_clean,
            id_produk=id_produk,
            id_bahan=id_bahan,
            qty_dipesan=qty_val,
            harga_satuan=harga,
            catatan_item=cat,
        ))

    if not items:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/baru?err={quote('Minimal 1 item harus diisi')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        payload = PemesananCreateRequest(
            supplier_nama=supplier_nama,
            tgl_perkiraan_datang=tgl_perkiraan,
            catatan=catatan,
            termin_hari=termin_hari,
            validitas_hari=validitas_hari,
            id_apoteker=id_apoteker,
            id_lokasi_pengiriman=id_lokasi_pengiriman,
            items=items,
        )
        created = PemesananService(db).create_pemesanan(
            payload=payload, actor=user, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/baru?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/baru?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/pemesanan/{created.id_pemesanan}?ok={quote(f'PO {created.nomor_po} berhasil dibuat')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# DETAIL
# =============================================================================
@router.get("/pengadaan/pemesanan/{id_pemesanan}", response_class=HTMLResponse)
def pemesanan_detail(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    repo = PemesananRepository(db)
    po = repo.get_by_id(id_pemesanan)
    if po is None:
        return HTMLResponse("<div style='padding:2rem'>404 - PO tidak ditemukan</div>", status_code=404)

    items = repo.get_items_by_po(id_pemesanan)
    receives = repo.get_receives_by_po(id_pemesanan)

    pemesan = StafRepository(db).get_by_id(po.id_staf_pemesan)
    approver = StafRepository(db).get_by_id(po.id_staf_approver) if po.id_staf_approver else None

    po_dict = {
        "id_pemesanan": po.id_pemesanan,
        "nomor_po": po.nomor_po,
        "tgl_pemesanan": po.tgl_pemesanan.strftime("%Y-%m-%d %H:%M") if po.tgl_pemesanan else "-",
        "tgl_perkiraan_datang": po.tgl_perkiraan_datang.isoformat() if po.tgl_perkiraan_datang else None,
        "supplier_nama": po.supplier_nama,
        "status": po.status.value if hasattr(po.status, "value") else str(po.status),
        "nama_staf_pemesan": pemesan.nama_staf if pemesan else f"(staf #{po.id_staf_pemesan})",
        "nama_staf_approver": approver.nama_staf if approver else None,
        "tgl_approve": po.tgl_approve.strftime("%Y-%m-%d %H:%M") if po.tgl_approve else None,
        "catatan": po.catatan,
        "total_estimasi_biaya": float(po.total_estimasi_biaya) if po.total_estimasi_biaya else None,
        "cancel_info": None,  # diisi di bawah kalau status=CANCELLED
    }

    # Kalau CANCELLED, query audit_log untuk alasan + siapa yang cancel + kapan
    if po_dict["status"] == "CANCELLED":
        from sqlalchemy import select as _sel
        from app.db.models import AuditLog
        from app.db.models import MasterStaf as _Staf
        cancel_stmt = (
            _sel(AuditLog, _Staf)
            .outerjoin(_Staf, AuditLog.id_staf == _Staf.id_staf)
            .where(AuditLog.aksi == "PO_CANCEL")
            .where(AuditLog.tabel_target == "pemesanan")
            .where(AuditLog.id_target == id_pemesanan)
            .order_by(AuditLog.id_log.desc())
            .limit(1)
        )
        cancel_row = db.execute(cancel_stmt).first()
        if cancel_row:
            log, canceller = cancel_row
            # Extract alasan dari keterangan format "PO XXX cancelled. Alasan: ..."
            keterangan = log.keterangan or ""
            alasan = "—"
            if "Alasan:" in keterangan:
                alasan = keterangan.split("Alasan:", 1)[1].strip() or "—"
            po_dict["cancel_info"] = {
                "alasan": alasan,
                "nama_canceller": canceller.nama_staf if canceller else f"(staf #{log.id_staf})",
                "tgl_cancel": log.waktu.strftime("%Y-%m-%d %H:%M") if log.waktu else "-",
            }

    items_data = []
    for it in items:
        sisa = float(it.qty_dipesan) - float(it.qty_diterima or 0)
        items_data.append({
            "id_item": it.id_item,
            "tipe_item": it.tipe_item,
            "id_produk": it.id_produk,
            "id_bahan": it.id_bahan,
            "nama_snapshot": it.nama_snapshot,
            "satuan_snapshot": it.satuan_snapshot or "",
            "qty_dipesan": float(it.qty_dipesan),
            "qty_diterima": float(it.qty_diterima or 0),
            "qty_sisa": sisa,
            "is_complete": sisa <= 0,
            "harga_satuan": float(it.harga_satuan) if it.harga_satuan else None,
            "subtotal": float(it.subtotal) if it.subtotal else None,
            "catatan_item": it.catatan_item,
        })

    history = []
    for rcv, staf in receives:
        history.append({
            "id_receive": rcv.id_receive,
            "id_pemesanan_item": rcv.id_pemesanan_item,
            "qty_diterima": float(rcv.qty_diterima),
            "tgl_terima": rcv.tgl_terima.strftime("%Y-%m-%d %H:%M") if rcv.tgl_terima else "-",
            "nama_staf_penerima": staf.nama_staf if staf else f"(staf #{rcv.id_staf_penerima})",
            "nomor_faktur": rcv.nomor_faktur or "-",
            "catatan": rcv.catatan,
        })

    # Role flags untuk button visibility
    user_role = user.role if isinstance(user.role, StafRoleEnum) else StafRoleEnum(user.role)
    is_owner_super = user_role in {StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN}
    is_purchasing_full = user_role in {StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN, StafRoleEnum.PURCHASING}
    is_apoteker = user_role == StafRoleEnum.APOTEKER

    from app.db.models import MasterDistributor as _MD
    _dists = db.query(_MD).filter(_MD.is_active == True).order_by(_MD.nama).all()

    # FK-L5: daftar faktur per pengiriman untuk PO ini
    from app.db.models import FakturPenerimaan as _FP, PemesananReceive as _PR
    faktur_list = []
    for fk in db.query(_FP).filter(_FP.id_pemesanan == id_pemesanan).order_by(_FP.id_faktur).all():
        n_item = db.query(_PR).filter(_PR.id_faktur == fk.id_faktur).count()
        dist = db.get(_MD, fk.id_distributor) if fk.id_distributor else None
        faktur_list.append({
            "id_faktur": fk.id_faktur,
            "nomor_pengiriman": fk.nomor_pengiriman or "-",
            "nomor_faktur": fk.nomor_faktur or "-",
            "tgl": (fk.tgl_faktur.strftime("%d/%m/%Y") if fk.tgl_faktur
                    else (fk.tgl_terima.strftime("%d/%m/%Y") if fk.tgl_terima else "-")),
            "distributor": dist.nama if dist else "-",
            "total_ditagih": float(fk.total_ditagih) if fk.total_ditagih is not None else None,
            "n_item": int(n_item),
        })

    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/pemesanan",
        page_subtitle=f"PO {po.nomor_po}",
        po=po_dict, items=items_data, history=history,
        faktur_list=faktur_list,
        distributors=[d.nama for d in _dists],
        can_edit=(po_dict["status"] == "SUBMITTED" and is_purchasing_full),
        can_approve=(po_dict["status"] == "SUBMITTED" and is_owner_super),
        can_cancel=(po_dict["status"] in ("SUBMITTED", "ORDERED", "PARTIAL_RECEIVED") and is_owner_super),
        can_receive=(po_dict["status"] in ("ORDERED", "PARTIAL_RECEIVED")),
        is_apoteker=is_apoteker,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pemesanan_detail.html", ctx)


# =============================================================================
# EDIT HEADER (SUBMITTED only)
# =============================================================================
@router.post("/pengadaan/pemesanan/{id_pemesanan}/edit", response_class=HTMLResponse)
def pemesanan_edit_header(
    id_pemesanan: int, request: Request, db: DbSession,
    supplier_nama: str = Form(default=""),
    tgl_perkiraan_datang: str = Form(default=""),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_full_role(user):
        return _403()

    tgl = None
    if tgl_perkiraan_datang.strip():
        try:
            tgl = date.fromisoformat(tgl_perkiraan_datang.strip())
        except ValueError:
            return RedirectResponse(
                url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote('Format tanggal invalid')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    try:
        payload = PemesananHeaderUpdate(
            supplier_nama=supplier_nama.strip() or None,
            tgl_perkiraan_datang=tgl,
            catatan=catatan.strip() or None,
        )
        PemesananService(db).update_header(
            id_pemesanan=id_pemesanan, payload=payload, actor=user, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/pemesanan/{id_pemesanan}?ok={quote('Header PO berhasil diupdate')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# APPROVE → ORDERED
# =============================================================================
@router.post("/pengadaan/pemesanan/{id_pemesanan}/approve-ordered")
def pemesanan_approve(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_approve_cancel_role(user):
        return _403("Hanya Owner/Superadmin yang boleh approve PO.")

    try:
        PemesananService(db).approve_to_ordered(
            id_pemesanan=id_pemesanan, actor=user, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/pemesanan/{id_pemesanan}?ok={quote('PO berhasil di-approve ke ORDERED')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# CANCEL
# =============================================================================
@router.post("/pengadaan/pemesanan/{id_pemesanan}/cancel")
def pemesanan_cancel(
    id_pemesanan: int, request: Request, db: DbSession,
    alasan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_approve_cancel_role(user):
        return _403("Hanya Owner/Superadmin yang boleh cancel PO.")

    try:
        PemesananService(db).cancel(
            id_pemesanan=id_pemesanan, actor=user,
            alasan=alasan.strip() or None, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pengadaan/pemesanan/{id_pemesanan}?ok={quote('PO berhasil di-cancel')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# RECEIVE ITEM
# =============================================================================
@router.post("/pengadaan/pemesanan/{id_pemesanan}/item/{id_item}/receive")
def pemesanan_receive(
    id_pemesanan: int, id_item: int, request: Request, db: DbSession,
    qty_diterima: float = Form(..., gt=0),
    nomor_faktur: str = Form(default=""),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    try:
        payload = ReceiveItemRequest(
            id_pemesanan_item=id_item,
            qty_diterima=qty_diterima,
            nomor_faktur=nomor_faktur.strip() or None,
            catatan=catatan.strip() or None,
        )
        result = PemesananService(db).receive_item(
            id_pemesanan=id_pemesanan, payload=payload, actor=user, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = result.get("message", "Receive berhasil") if isinstance(result, dict) else "Receive berhasil"
    return RedirectResponse(
        url=f"/web/pengadaan/pemesanan/{id_pemesanan}?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )



# =============================================================================
# GET /web/pengadaan/pemesanan/{id}/cetak — Print PO (P-L2)
# =============================================================================
@router.get("/pengadaan/pemesanan/{id_pemesanan}/cetak", response_class=HTMLResponse)
def pemesanan_cetak(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    repo = PemesananRepository(db)
    po = repo.get_by_id(id_pemesanan)
    if po is None:
        return HTMLResponse("<div style='padding:2rem'>404 - PO tidak ditemukan</div>", status_code=404)
    _st = po.status.value if hasattr(po.status, "value") else str(po.status)
    if _st not in ("ORDERED", "PARTIAL_RECEIVED", "RECEIVED"):
        return HTMLResponse(
            "<div style='padding:2rem;font-family:sans-serif'>PO belum di-approve — belum bisa dicetak. "
            "<a href='/web/pengadaan/pemesanan/%d'>&larr; Kembali</a></div>" % id_pemesanan,
            status_code=400,
        )
    items = repo.get_items_by_po(id_pemesanan)
    pemesan = StafRepository(db).get_by_id(po.id_staf_pemesan)
    approver = StafRepository(db).get_by_id(po.id_staf_approver) if po.id_staf_approver else None

    from app.services.klinik_config_service import KlinikConfigService
    klinik = KlinikConfigService(db).get_config()

    total = sum((it.subtotal or Decimal("0")) for it in items) if items else Decimal("0")

    ctx = {
        "klinik": klinik,
        "po": po,
        "items": items,
        "pemesan": pemesan,
        "approver": approver,
        "total": total,
    }
    return templates.TemplateResponse(request, "print/po_a5.html", ctx)

__all__ = ["router"]


# =============================================================================
# FAKTUR PENERIMAAN (P-L4) — window terima barang (buat lot) + print reprintable
# =============================================================================
@router.get("/pengadaan/pemesanan/{id_pemesanan}/faktur", response_class=HTMLResponse)
def pemesanan_faktur_form(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    repo = PemesananRepository(db)
    po = repo.get_by_id(id_pemesanan)
    if po is None:
        return HTMLResponse("<div style='padding:2rem'>404 - PO tidak ditemukan</div>", status_code=404)
    st = po.status.value if hasattr(po.status, "value") else str(po.status)
    if st not in ("ORDERED", "PARTIAL_RECEIVED"):
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}?err={quote('PO belum bisa diterima (harus ORDERED).')}",
            status_code=status.HTTP_303_SEE_OTHER)
    items = repo.get_items_by_po(id_pemesanan)
    item_rows = []
    for it in items:
        sisa = float(it.qty_dipesan) - float(it.qty_diterima or 0)
        if sisa <= 0:
            continue
        item_rows.append({
            "id_item": it.id_item, "nama": it.nama_snapshot, "satuan": it.satuan_snapshot or "",
            "sisa": sisa, "harga_order": float(it.harga_satuan or 0),
        })
    from app.db.models import MasterDistributor
    distributors = db.query(MasterDistributor).filter(MasterDistributor.is_active == True).order_by(MasterDistributor.nama).all()
    ctx = build_shell_context(
        user, db=db, current_path="/web/pengadaan/pemesanan",
        page_subtitle=f"Terima Barang — {po.nomor_po}",
        po_nomor=po.nomor_po, id_pemesanan=id_pemesanan, supplier_nama=po.supplier_nama,
        items=item_rows,
        distributors=[{"id": d.id_distributor, "nama": d.nama} for d in distributors],
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pemesanan_faktur_form.html", ctx)


@router.post("/pengadaan/pemesanan/{id_pemesanan}/faktur", response_class=HTMLResponse)
async def pemesanan_faktur_submit(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    f = await request.form()
    id_dist = f.get("id_distributor")
    id_dist = int(id_dist) if (id_dist and str(id_dist).strip()) else None
    nomor_faktur = (f.get("nomor_faktur") or "").strip() or None
    # FK-L3: PPN + total ditagih (reverse-calc) + tgl faktur (faktur-level)
    try:
        ppn_persen = Decimal((f.get("ppn_persen") or "0").strip() or "0")
    except Exception:
        ppn_persen = Decimal("0")
    total_ditagih_raw = (f.get("total_ditagih") or "").strip()
    tgl_faktur_raw = (f.get("tgl_faktur") or "").strip()
    try:
        tgl_faktur = date.fromisoformat(tgl_faktur_raw) if tgl_faktur_raw else None
    except ValueError:
        tgl_faktur = None

    repo = PemesananRepository(db)
    items = repo.get_items_by_po(id_pemesanan)

    received = []
    for it in items:
        qraw = f.get(f"qty_{it.id_item}")
        if not qraw or not str(qraw).strip():
            continue
        try:
            qty = float(qraw)
        except ValueError:
            continue
        if qty <= 0:
            continue
        batch = (f.get(f"batch_{it.id_item}") or "").strip() or None
        ed_raw = (f.get(f"ed_{it.id_item}") or "").strip()
        try:
            ed = date.fromisoformat(ed_raw) if ed_raw else None
        except ValueError:
            ed = None
        harga_order_d = Decimal(str(it.harga_satuan or 0))
        hraw = (f.get(f"harga_{it.id_item}") or "").strip()
        try:
            harga_terima_d = Decimal(hraw) if hraw else harga_order_d
        except Exception:
            harga_terima_d = harga_order_d
        received.append({"it": it, "qty": qty, "batch": batch, "ed": ed,
                         "harga_order": harga_order_d, "harga_terima": harga_terima_d})

    if not received:
        return RedirectResponse(
            url=f"/web/pengadaan/pemesanan/{id_pemesanan}/faktur?err={quote('Belum ada item yang ditandai Terima.')}",
            status_code=status.HTTP_303_SEE_OTHER)

    # Faktur digerakkan oleh HARGA TERIMA per item (source of truth; editable).
    # Total ditagih (Y) opsional -> dipakai rekonsiliasi extra_diskon.
    _q2 = Decimal("0.01")
    ppn_ratio = ppn_persen / Decimal(100)
    X = sum((r["harga_order"] * Decimal(str(r["qty"])) for r in received), Decimal(0))
    S = sum((r["harga_terima"] * Decimal(str(r["qty"])) for r in received), Decimal(0))
    total_computed = (S * (Decimal(1) + ppn_ratio)).quantize(_q2)
    diskon_persen = ((Decimal(1) - (S / X)) * Decimal(100)).quantize(_q2) if X > 0 else Decimal("0.00")
    Y = None
    if total_ditagih_raw:
        try:
            Y = Decimal(total_ditagih_raw)
        except Exception:
            Y = None
    if Y is not None:
        extra_diskon = (total_computed - Y).quantize(_q2)
        total_final = Y.quantize(_q2)
    else:
        extra_diskon = Decimal("0.00")
        total_final = total_computed

    # Buat FAKTUR header (1 faktur = 1 pengiriman)
    from app.db.models import FakturPenerimaan
    from datetime import datetime as _dtnow
    fak = FakturPenerimaan(
        id_pemesanan=id_pemesanan, nomor_faktur=nomor_faktur, id_distributor=id_dist,
        tgl_faktur=tgl_faktur, ppn_persen=(ppn_persen if ppn_persen else None),
        id_staf_penerima=user.id_staf,
        diskon_persen=diskon_persen, extra_diskon=extra_diskon,
        subtotal_order=X.quantize(_q2), subtotal_setelah_diskon=S.quantize(_q2),
        total_ditagih=total_final,
    )
    db.add(fak)
    db.flush()
    fak.nomor_pengiriman = f"SJ-{_dtnow.now().strftime('%y%m%d')}-{fak.id_faktur:04d}"
    db.flush()
    id_faktur_val = fak.id_faktur
    nomor_pengiriman_str = fak.nomor_pengiriman

    svc = PemesananService(db)
    n_ok = 0
    errors = []
    for r in received:
        it = r["it"]
        try:
            payload = ReceiveItemRequest(
                id_pemesanan_item=it.id_item, qty_diterima=r["qty"], nomor_faktur=nomor_faktur,
                batch_no=r["batch"], tgl_ed=r["ed"], harga_terima=r["harga_terima"],
                id_distributor=id_dist, id_faktur=id_faktur_val,
            )
            svc.receive_item(id_pemesanan=id_pemesanan, payload=payload, actor=user, request=request)
            n_ok += 1
        except HTTPException as e:
            errors.append(f"{it.nama_snapshot}: {e.detail}")
        except Exception as e:
            errors.append(f"{it.nama_snapshot}: {e!s}")

    if n_ok == 0:
        msg = "Tidak ada item diterima." + (" " + " | ".join(errors) if errors else "")
        return RedirectResponse(url=f"/web/pengadaan/pemesanan/{id_pemesanan}/faktur?err={quote(msg)}",
                                status_code=status.HTTP_303_SEE_OTHER)
    ok = f"{n_ok} item diterima & lot dibuat (faktur {nomor_pengiriman_str})."
    if errors:
        ok += " Sebagian gagal: " + " | ".join(errors)
    return RedirectResponse(url=f"/web/pengadaan/faktur/{id_faktur_val}/cetak?ok={quote(ok)}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/pengadaan/pemesanan/{id_pemesanan}/faktur/cetak", response_class=HTMLResponse)
def pemesanan_faktur_cetak(id_pemesanan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()
    repo = PemesananRepository(db)
    po = repo.get_by_id(id_pemesanan)
    if po is None:
        return HTMLResponse("<div style='padding:2rem'>404 - PO tidak ditemukan</div>", status_code=404)
    receives = repo.get_receives_by_po(id_pemesanan)  # list of (rcv, staf)
    items = {it.id_item: it for it in repo.get_items_by_po(id_pemesanan)}
    from app.db.models import MasterDistributor
    from app.services.klinik_config_service import KlinikConfigService
    klinik = KlinikConfigService(db).get_config()

    dist_map = {}
    baris = []
    for rcv, staf in receives:
        it = items.get(rcv.id_pemesanan_item)
        harga_order = float(it.harga_satuan or 0) if it and it.harga_satuan is not None else None
        harga_terima = float(rcv.harga_terima) if rcv.harga_terima is not None else None
        selisih = (harga_terima - harga_order) if (harga_order is not None and harga_terima is not None) else None
        dist_nama = None
        if rcv.id_distributor:
            if rcv.id_distributor not in dist_map:
                d = db.get(MasterDistributor, rcv.id_distributor)
                dist_map[rcv.id_distributor] = d
            d = dist_map.get(rcv.id_distributor)
            dist_nama = d.nama if d else None
        baris.append({
            "nomor_po": po.nomor_po, "tgl_pemesanan": po.tgl_pemesanan,
            "nama_item": it.nama_snapshot if it else "-",
            "qty": float(rcv.qty_diterima), "batch_no": rcv.batch_no or "-",
            "tgl_ed": rcv.tgl_ed, "harga_order": harga_order, "harga_terima": harga_terima,
            "selisih": selisih, "distributor": dist_nama, "tgl_terima": rcv.tgl_terima,
            "penerima": staf.nama_staf if staf else "-",
        })
    # header distributor = distributor pertama non-null
    dist_header = next((b["distributor"] for b in baris if b["distributor"]), po.supplier_nama)
    dist_obj = None
    for d in dist_map.values():
        if d:
            dist_obj = d
            break
    ctx = {
        "klinik": klinik, "po": po, "baris": baris,
        "dist_header": dist_header, "dist_obj": dist_obj,
        "penerima_nama": user.nama_staf, "penerima_id": user.id_staf,
    }
    return templates.TemplateResponse(request, "print/faktur_a5.html", ctx)


# =============================================================================
# FK-L4 — Cetak FAKTUR per pengiriman (2 versi: finance / inventory)
# =============================================================================
@router.get("/pengadaan/faktur/{id_faktur}/cetak", response_class=HTMLResponse)
def faktur_dok_cetak(id_faktur: int, request: Request, db: DbSession, versi: str = "finance"):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_purchasing_view_role(user):
        return _403()

    from app.db.models import FakturPenerimaan, PemesananReceive, MasterDistributor
    from app.services.klinik_config_service import KlinikConfigService

    fak = db.get(FakturPenerimaan, id_faktur)
    if fak is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Faktur tidak ditemukan</div>", status_code=404)
    versi = "inventory" if versi == "inventory" else "finance"

    repo = PemesananRepository(db)
    po = repo.get_by_id(fak.id_pemesanan)
    items_po = {it.id_item: it for it in repo.get_items_by_po(fak.id_pemesanan)}
    receives = (db.query(PemesananReceive)
                .filter(PemesananReceive.id_faktur == id_faktur)
                .order_by(PemesananReceive.id_receive).all())

    distributor = db.get(MasterDistributor, fak.id_distributor) if fak.id_distributor else None
    penerima = StafRepository(db).get_by_id(fak.id_staf_penerima) if fak.id_staf_penerima else None
    klinik = KlinikConfigService(db).get_config()

    ppn = float(fak.ppn_persen or 0) / 100
    baris = []
    for i, rcv in enumerate(receives, start=1):
        it = items_po.get(rcv.id_pemesanan_item)
        order = float(it.harga_satuan or 0) if it and it.harga_satuan is not None else 0.0
        terima = float(rcv.harga_terima or 0)
        qty = float(rcv.qty_diterima)
        baris.append({
            "no": i,
            "tgl_terima": rcv.tgl_terima,
            "nama": it.nama_snapshot if it else "-",
            "jml_pesan": float(it.qty_dipesan) if it else None,
            "jml_terima": qty,
            "harga_terima": terima,
            "diskon_rp": round((order - terima) * qty),
            "pajak_rp": round(terima * qty * ppn),
            "total_rp": round(terima * qty * (1 + ppn)),
            "batch_no": rcv.batch_no or "-",
            "tgl_ed": rcv.tgl_ed,
        })

    ctx = {
        "klinik": klinik, "fak": fak, "po": po, "baris": baris, "versi": versi,
        "distributor": distributor, "penerima": penerima,
        "ok": request.query_params.get("ok"),
    }
    return templates.TemplateResponse(request, "print/faktur_dokumen.html", ctx)
